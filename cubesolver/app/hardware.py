"""Hardware-Schicht: echte Ansteuerung am Raspberry Pi (pigpio) und Simulation.

Beide Klassen haben dieselbe Schnittstelle, der Rest des Programms merkt
keinen Unterschied. Alle Methoden blockieren und werden vom Ablauf in einem
Thread aufgerufen.

Begriffe
  Seite / Motor:  "U", "D", "L", "R", "F", "B"
  Zylinder:       "U", "D", "LR", "FB"  (L+R und F+B hängen an je einem Relais)
  Drehrichtung:   positive Schritte = im Uhrzeigersinn, von außen auf die Seite gesehen
"""
from __future__ import annotations

import random
import threading
import time

from .config import REED_MAP
from .cube_model import NORMALS, CubeModel

SIDES = ["U", "D", "L", "R", "F", "B"]
CYLINDERS = {"U": ["U"], "D": ["D"], "LR": ["L", "R"], "FB": ["F", "B"]}
OPPOSITE = {"U": "D", "D": "U", "L": "R", "R": "L", "F": "B", "B": "F"}
MOTOR_NUMBER = {"L": 1, "R": 2, "U": 3, "D": 4, "F": 5, "B": 6}


class HardwareError(RuntimeError):
    pass


def ramp_periods(steps, f_start, f_run, ramp):
    """Periodendauer (µs) je Schritt mit linearer Rampe am Anfang und Ende."""
    f_start = min(f_start, f_run)
    r = min(ramp, steps // 2)
    out = []
    for i in range(steps):
        if r and i < r:
            f = f_start + (f_run - f_start) * (i / r)
        elif r and i >= steps - r:
            f = f_start + (f_run - f_start) * ((steps - 1 - i) / r)
        else:
            f = f_run
        out.append(int(1_000_000 / max(1.0, f)))
    return out


def move_duration(steps, settings, speed):
    return sum(ramp_periods(abs(steps), settings["speed_start"], speed, settings["ramp_steps"])) / 1e6


class BaseHardware:
    name = "base"

    def __init__(self, settings):
        self.settings = settings
        self.cyl_target = {c: False for c in CYLINDERS}  # True = ausfahren
        self.motor_angle = {s: 0.0 for s in SIDES}  # nur zur Anzeige
        self.busy = set()
        self.lock = threading.Lock()

    # --- Schnittstelle ------------------------------------------------------
    def set_cylinder(self, cyl: str, extended: bool):
        raise NotImplementedError

    def reeds(self) -> dict:
        """{seite: {"in": bool, "out": bool}}"""
        raise NotImplementedError

    def turn(self, moves: dict, speed: int):
        """moves = {seite: schritte (mit Vorzeichen)}; alle gleich viele Schritte,
        laufen gleichzeitig über den gemeinsamen STEP-Pin."""
        raise NotImplementedError

    def light_barrier(self) -> bool:
        raise NotImplementedError

    def beep(self, pattern: str):
        raise NotImplementedError

    def all_off(self):
        """Sicherer Zustand: alle Motoren stromlos. Zylinder bleiben, damit der
        Würfel nicht herunterfällt."""
        raise NotImplementedError

    def close(self):
        self.all_off()

    # --- gemeinsame Hilfen ---------------------------------------------------
    def _check_moves(self, moves):
        if not moves:
            raise HardwareError("Keine Motoren angegeben")
        counts = {abs(v) for v in moves.values()}
        if len(counts) != 1:
            raise HardwareError("Gleichzeitig drehende Motoren müssen gleich viele Schritte fahren")
        dirs = {}
        for side, steps in moves.items():
            if side not in SIDES:
                raise HardwareError(f"Unbekannter Motor {side}")
            pin = self._dir_pin(side)
            level = self._dir_level(side, steps)
            if pin in dirs and dirs[pin] != level:
                raise HardwareError(
                    "U, D, F und B teilen sich eine DIR-Leitung und können nicht gleichzeitig "
                    "in unterschiedliche Richtungen drehen"
                )
            dirs[pin] = level
        return dirs

    def _dir_pin(self, side):
        s = self.settings
        return {"L": s["pin_dir_L"], "R": s["pin_dir_R"]}.get(side, s["pin_dir_shared"])

    def _dir_level(self, side, steps):
        level = 1 if steps > 0 else 0
        if self.settings[f"invert_{side}"]:
            level ^= 1
        return level

    def _beep_pattern(self, pattern):
        return {
            "kurz": [(0.08, 0)],
            "ok": [(0.12, 0.08), (0.12, 0)],
            "fertig": [(0.1, 0.06), (0.1, 0.06), (0.35, 0)],
            "fehler": [(0.6, 0.15), (0.6, 0)],
        }.get(pattern, [(0.1, 0)])

    def state(self):
        return {
            "cylinders": dict(self.cyl_target),
            "reeds": self.reeds(),
            "motors": {s: round(self.motor_angle[s], 1) for s in SIDES},
            "busy": sorted(self.busy),
            "light_barrier": self.light_barrier(),
        }


# =============================================================================
class PiHardware(BaseHardware):
    """Echte Hardware über den pigpio-Daemon (sudo systemctl enable --now pigpiod).

    Der Daemon wird per Netzwerk angesprochen – dadurch läuft das Programm später
    auch im Docker-Container, ohne GPIO-Geräte durchreichen zu müssen.
    """

    name = "pi"
    REG_IODIRA, REG_IODIRB, REG_GPPUA, REG_GPPUB, REG_GPIOA, REG_GPIOB = 0x00, 0x01, 0x0C, 0x0D, 0x12, 0x13

    def __init__(self, settings):
        super().__init__(settings)
        import pigpio

        self.pigpio = pigpio
        self.pi = pigpio.pi(settings["pigpio_host"])
        if not self.pi.connected:
            raise HardwareError("pigpiod nicht erreichbar (läuft 'sudo systemctl start pigpiod'?)")
        s = settings
        self.en_pins = {side: s[f"pin_en_{side}"] for side in SIDES}
        self.relay_pins = {c: s[f"pin_relay_{c}"] for c in CYLINDERS}
        self.out_pins = (
            [s["pin_step"], s["pin_dir_L"], s["pin_dir_R"], s["pin_dir_shared"], s["pin_buzzer"]]
            + list(self.en_pins.values())
            + list(self.relay_pins.values())
        )
        # zuerst Pegel setzen, dann auf Ausgang schalten -> kein kurzes Einschalten
        for side, pin in self.en_pins.items():
            self.pi.write(pin, self._en_level(False))
        for cyl, pin in self.relay_pins.items():
            self.pi.write(pin, self._relay_level(False))
        for pin in self.out_pins:
            self.pi.set_mode(pin, pigpio.OUTPUT)
        self.pi.write(s["pin_step"], 0)
        self.pi.write(s["pin_buzzer"], 0)
        self.pi.set_mode(s["pin_light_barrier"], pigpio.INPUT)
        self.pi.set_pull_up_down(s["pin_light_barrier"], pigpio.PUD_UP)
        self.pi.wave_clear()
        # MCP23017 für die Reed-Kontakte: alle Pins Eingang mit Pull-up
        self.mcp = None
        try:
            self.mcp = self.pi.i2c_open(s["mcp_bus"], s["mcp_address"])
            for reg in (self.REG_IODIRA, self.REG_IODIRB, self.REG_GPPUA, self.REG_GPPUB):
                self.pi.i2c_write_byte_data(self.mcp, reg, 0xFF)
        except Exception as e:
            self.mcp = None
            self.mcp_error = str(e)
        self.max_pulses = max(200, self.pi.wave_get_max_pulses() - 10)

    def _en_level(self, on):
        return (0 if on else 1) if self.settings["en_active_low"] else (1 if on else 0)

    def _relay_level(self, on):
        return (0 if on else 1) if self.settings["relay_active_low"] else (1 if on else 0)

    def set_cylinder(self, cyl, extended):
        self.pi.write(self.relay_pins[cyl], self._relay_level(extended))
        self.cyl_target[cyl] = extended

    def reeds(self):
        if self.mcp is None:
            return {side: {"in": False, "out": False, "error": True} for side in SIDES}
        a = self.pi.i2c_read_byte_data(self.mcp, self.REG_GPIOA)
        b = self.pi.i2c_read_byte_data(self.mcp, self.REG_GPIOB)
        port = {"A": a, "B": b}
        out = {}
        for side, ((pi_, bi), (po, bo)) in REED_MAP.items():
            # Kontakt geschlossen = Pin auf GND = 0
            out[side] = {"in": not (port[pi_] >> bi) & 1, "out": not (port[po] >> bo) & 1}
        return out

    def light_barrier(self):
        v = self.pi.read(self.settings["pin_light_barrier"])
        return v == 0 if self.settings["light_barrier_active_low"] else v == 1

    def turn(self, moves, speed):
        with self.lock:
            dirs = self._check_moves(moves)
            steps = abs(next(iter(moves.values())))
            s = self.settings
            for pin, level in dirs.items():
                self.pi.write(pin, level)
            # nur die gewählten Treiber freigeben, alle anderen sicher aus
            for side, pin in self.en_pins.items():
                self.pi.write(pin, self._en_level(side in moves))
            self.busy = set(moves)
            time.sleep(s["enable_settle_ms"] / 1000)
            try:
                periods = ramp_periods(steps, s["speed_start"], speed, s["ramp_steps"])
                mask = 1 << s["pin_step"]
                chunk = self.max_pulses // 2
                for i in range(0, len(periods), chunk):
                    pulses = []
                    for p in periods[i:i + chunk]:
                        pulses.append(self.pigpio.pulse(mask, 0, 5))
                        pulses.append(self.pigpio.pulse(0, mask, max(5, p - 5)))
                    self.pi.wave_add_generic(pulses)
                    wid = self.pi.wave_create()
                    self.pi.wave_send_once(wid)
                    while self.pi.wave_tx_busy():
                        time.sleep(0.002)
                    self.pi.wave_delete(wid)
            finally:
                for pin in self.en_pins.values():
                    self.pi.write(pin, self._en_level(False))
                self.busy = set()
            for side, st in moves.items():
                self.motor_angle[side] = (self.motor_angle[side] + st * 90.0 / s["steps_per_90"]) % 360

    def beep(self, pattern):
        if not self.settings["buzzer_enabled"]:
            return

        def run():
            pin = self.settings["pin_buzzer"]
            for on, off in self._beep_pattern(pattern):
                self.pi.write(pin, 1)
                time.sleep(on)
                self.pi.write(pin, 0)
                time.sleep(off)

        threading.Thread(target=run, daemon=True).start()

    def all_off(self):
        try:
            self.pi.wave_tx_stop()
            for pin in self.en_pins.values():
                self.pi.write(pin, self._en_level(False))
            self.pi.write(self.settings["pin_buzzer"], 0)
        except Exception:
            pass
        self.busy = set()

    def release_all(self):
        """Nur beim Beenden: alle Relais aus (Zylinder fahren ein)."""
        for cyl, pin in self.relay_pins.items():
            self.pi.write(pin, self._relay_level(False))

    def close(self):
        self.all_off()
        try:
            if self.mcp is not None:
                self.pi.i2c_close(self.mcp)
            self.pi.stop()
        except Exception:
            pass


# =============================================================================
class SimHardware(BaseHardware):
    """Simulation: Zylinder mit Fahrzeit, Reeds, Motoren mit realistischer Dauer
    und ein 'echter' verdrehter Würfel, der sich physikalisch plausibel bewegt."""

    name = "sim"

    def __init__(self, settings):
        super().__init__(settings)
        self.cyl_changed = {c: 0.0 for c in CYLINDERS}
        self.cube: CubeModel | None = None
        self.scramble_text = ""
        self.stop_flag = threading.Event()
        self.insert_cube()

    def _f(self):
        return self.settings["sim_time_factor"]

    def insert_cube(self):
        """Legt einen neu verdrehten Würfel in zufälliger Lage ein."""
        c = CubeModel.solved()
        self.scramble_text = c.scramble(self.settings["sim_scramble_moves"])
        if self.settings["sim_random_orientation"]:
            rng = random.Random()
            for _ in range(rng.randint(0, 6)):
                c.rotate_whole(rng.choice(["R", "U", "F"]), rng.randint(1, 3))
        self.cube = c
        return self.scramble_text

    def remove_cube(self):
        self.cube = None

    def set_cylinder(self, cyl, extended):
        if self.cyl_target[cyl] != extended:
            self.cyl_target[cyl] = extended
            self.cyl_changed[cyl] = time.monotonic()

    def _cyl_pos(self, cyl):
        travel = self.settings["sim_cylinder_time_ms"] / 1000 * self._f()
        done = time.monotonic() - self.cyl_changed[cyl] >= travel
        if not done:
            return None  # unterwegs
        return self.cyl_target[cyl]

    def reeds(self):
        out = {}
        for cyl, sides in CYLINDERS.items():
            pos = self._cyl_pos(cyl)
            for side in sides:
                out[side] = {"in": pos is False, "out": pos is True}
        return out

    def light_barrier(self):
        return self.cube is not None

    def _extended(self, side):
        cyl = next(c for c, ss in CYLINDERS.items() if side in ss)
        return self._cyl_pos(cyl) is True

    def turn(self, moves, speed):
        with self.lock:
            self._check_moves(moves)
            steps = abs(next(iter(moves.values())))
            spq = self.settings["steps_per_90"]
            self.busy = set(moves)
            dur = (move_duration(steps, self.settings, speed) + self.settings["enable_settle_ms"] / 1000) * self._f()
            end = time.monotonic() + dur
            start_angles = dict(self.motor_angle)
            try:
                while True:
                    now = time.monotonic()
                    frac = 1.0 if dur <= 0 else min(1.0, 1 - (end - now) / dur)
                    for side, st in moves.items():
                        self.motor_angle[side] = (start_angles[side] + frac * st * 90.0 / spq) % 360
                    if frac >= 1.0:
                        break
                    time.sleep(min(0.02, max(0.0, end - now)))
            finally:
                self.busy = set()
            for side, st in moves.items():
                self.motor_angle[side] = (start_angles[side] + st * 90.0 / spq) % 360
            self._physics(moves, spq)

    def _physics(self, moves, spq):
        """Was macht der echte Würfel bei dieser Motorbewegung?"""
        if self.cube is None:
            return
        any_steps = next(iter(moves.values()))
        if any_steps % spq:
            return  # Feinjustage, keine ganze Vierteldrehung
        q = any_steps // spq
        engaged = [s for s in moves if self._extended(s)]
        if not engaged:
            return  # Greifer drehen in der Luft
        holders = [s for s in SIDES if s not in moves and self._extended(s)]
        if len(moves) == 2:
            a, b = list(moves)
            if OPPOSITE[a] == b and len(engaged) == 2:
                if holders:
                    raise HardwareError(f"Würfel verklemmt: {a}+{b} drehen, aber {''.join(holders)} hält fest")
                self.cube.rotate_whole(a, moves[a] // spq)
            return
        side = engaged[0]
        perpendicular = [h for h in holders if h != OPPOSITE[side]]
        if perpendicular or holders:
            self.cube.turn_layer(side, q)
        else:
            # nur dieser Greifer hält: der ganze Würfel dreht über Reibung mit
            self.cube.rotate_whole(side, q)

    def bottom_colors(self):
        if self.cube is None:
            return None
        return [s.color for s in self.cube.face_stickers("D")]

    def beep(self, pattern):
        pass

    def all_off(self):
        self.busy = set()
