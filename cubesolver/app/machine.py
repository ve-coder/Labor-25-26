"""Ablaufsteuerung: führt Blockprogramme aus, prüft Sicherheitsregeln,
führt das Würfelmodell mit und meldet alles an die Oberfläche.

Blockprogramm (JSON):
  {"name": "...", "blocks": [ {...}, ... ]}
Blocktypen:
  cylinder  {target: U|D|LR|FB, action: extend|retract}
  motor     {side: U|D|L|R|F|B, angle: 90|180|-90|-180, speed}
  pair      {angle, speed}                 L+R gegensinnig = ganzer Würfel
  scan      {}                             Unterseite aufnehmen (9/9 abwarten)
  compute   {}                             Farben prüfen, Lösung berechnen
  execute   {speed}                        Lösung ausführen
  repeat    {times, body: [...]}
  wait      {seconds}
  beep      {pattern: kurz|ok|fertig|fehler}
  home      {}                             Grundstellung: U, F/B, L/R, D einfahren
speed: Zahl (Schritte/s) oder "solve" | "scan" | "regrip" | "manual"
"""
from __future__ import annotations

import json
import threading
import time
import traceback
from pathlib import Path

import cv2

from . import solver, vision
from .config import DATA_DIR
from .cube_model import FACES, NORMALS, CubeModel, format_moves
from .hardware import CYLINDERS, OPPOSITE, SIDES, HardwareError
from .stats import Stats

CYL_OF = {s: c for c, ss in CYLINDERS.items() for s in ss}
SPEED_KEYS = {"solve": "speed_solve", "scan": "speed_scan", "regrip": "speed_regrip", "manual": "speed_manual"}
PROGRAM_DIR = DATA_DIR / "programs"
DEFAULT_PROGRAM_FILE = Path(__file__).resolve().parent.parent / "programs" / "standard.json"


class StopRequested(Exception):
    pass


class SafetyError(RuntimeError):
    pass


class Machine:
    def __init__(self, settings, hardware, camera_mgr, emit=None):
        self.settings = settings
        self.hw = hardware
        self.cam = camera_mgr
        self.emit = emit or (lambda ev: None)
        self.model = CubeModel.blank()  # Wissen der Steuerung über den Würfel
        self.solution = []  # [(Fläche, Viertel)]
        self.solution_text = ""
        self.solution_index = 0
        self.stats = Stats(DATA_DIR / "stats.json")
        self.status = "bereit"  # bereit | läuft | wartet | fehler | gestoppt | fertig
        self.step_label = ""
        self.active_block = None
        self.error = None
        self.log_lines = []
        self.thread = None
        self._stop = threading.Event()
        self.step_mode = False
        self._step_go = threading.Event()
        self.interlocks = True
        self.run_info = {}
        self.program_name = None

    # ===================================================================== Log
    def log(self, text, level="info"):
        line = {"t": time.time(), "level": level, "text": text}
        self.log_lines.append(line)
        self.log_lines = self.log_lines[-300:]
        self.emit({"type": "log", **line})

    def _cube_event(self):
        self.emit({"type": "cube", **self.model.to_json()})

    def snapshot(self):
        return {
            "status": self.status,
            "step": self.step_label,
            "block": self.active_block,
            "error": self.error,
            "mode": self.hw.name,
            "program": self.program_name,
            "step_mode": self.step_mode,
            "interlocks": self.interlocks,
            "solution": self.solution_text,
            "solution_index": self.solution_index,
            "solution_len": len(self.solution),
            "running": self.is_running(),
            "hw": self.hw.state(),
            "camera": self.cam.status(),
            "scanned": sum(1 for s in self.model.stickers if s.rgb is not None),
        }

    def is_running(self):
        return self.thread is not None and self.thread.is_alive()

    # ===================================================================== Start/Stopp
    def start_program(self, program: dict):
        if self.is_running():
            raise RuntimeError("Es läuft bereits ein Ablauf")
        if self.settings["require_light_barrier"] and not self.hw.light_barrier():
            raise RuntimeError("Kein Würfel in der Lichtschranke")
        self._stop.clear()
        self._step_go.clear()
        self.error = None
        self.program_name = program.get("name")
        self.thread = threading.Thread(target=self._run, args=(program,), daemon=True)
        self.thread.start()

    def stop(self):
        self._stop.set()
        self._step_go.set()
        self.hw.all_off()
        if hasattr(self.hw, "stop_flag"):
            self.hw.stop_flag.set()

    def next_step(self):
        self._step_go.set()

    def set_step_mode(self, on: bool):
        self.step_mode = on
        if not on:
            self._step_go.set()

    def _check_stop(self):
        if self._stop.is_set():
            raise StopRequested()

    def _run(self, program):
        self.status = "läuft"
        self.model = CubeModel.blank()
        self.solution, self.solution_text, self.solution_index = [], "", 0
        self._cube_event()
        self.run_info = {"program": program.get("name"), "start": time.time(), "scan_s": 0.0,
                         "compute_s": None, "solve_s": None, "moves": None}
        self.log(f"Start: {program.get('name', 'Programm')}")
        ok = False
        err = None
        try:
            self._exec_list(program.get("blocks", []))
            self.status = "fertig"
            ok = True
            self.log("Ablauf fertig")
            self.hw.beep("fertig")
        except StopRequested:
            self.status = "gestoppt"
            err = "Gestoppt"
            self.log("Gestoppt – Motoren stromlos, Zylinder bleiben stehen", "warn")
        except Exception as e:
            self.status = "fehler"
            err = str(e)
            self.error = err
            self.log(f"Fehler: {e}", "error")
            if not isinstance(e, (SafetyError, HardwareError, solver.CubeStateError, TimeoutError)):
                traceback.print_exc()
            self.hw.beep("fehler")
        finally:
            self.hw.all_off()
            self.active_block = None
            self.step_label = ""
            self.emit({"type": "block", "id": None})
            info = self.run_info
            if info.get("solve_s") is not None or not ok:
                self.stats.add({
                    "program": info.get("program"),
                    "ok": ok and info.get("solve_s") is not None,
                    "error": err,
                    "total_s": round(time.time() - info["start"], 2),
                    "scan_s": round(info.get("scan_s") or 0, 2),
                    "compute_s": info.get("compute_s"),
                    "solve_s": info.get("solve_s"),
                    "moves": info.get("moves"),
                    "mode": self.hw.name,
                })
                self.emit({"type": "stats"})

    # ===================================================================== Interpreter
    def _exec_list(self, blocks):
        for b in blocks:
            self._check_stop()
            self._exec(b)

    def _exec(self, b):
        t = b.get("type")
        if t == "repeat":
            for i in range(int(b.get("times", 1))):
                self._check_stop()
                self._exec_list(b.get("body", []))
            return
        self.active_block = b.get("id")
        self.emit({"type": "block", "id": self.active_block})
        if self.step_mode:
            self.status = "wartet"
            self.step_label = "Einzelschritt: weiter mit „Nächster Schritt“"
            self._step_go.clear()
            while not self._step_go.wait(0.1):
                self._check_stop()
            self._check_stop()
            self.status = "läuft"
        handler = getattr(self, f"_b_{t}", None)
        if handler is None:
            raise ValueError(f"Unbekannter Block {t}")
        handler(b)
        delay = self.settings["pause_between_moves_ms"] / 1000
        if t in ("motor", "pair") and delay:
            time.sleep(delay)

    def _speed(self, v, default="manual"):
        if v is None or v == "":
            v = default
        if isinstance(v, str) and v in SPEED_KEYS:
            return int(self.settings[SPEED_KEYS[v]])
        return max(10, int(float(v)))

    # ----------------------------------------------------------------- Blöcke
    def _b_cylinder(self, b):
        cyl = b["target"]
        ext = b.get("action", "extend") == "extend"
        self.step_label = f"Zylinder {cyl} {'ausfahren' if ext else 'einfahren'}"
        self.set_cylinder(cyl, ext)

    def _b_motor(self, b):
        side = b["side"]
        angle = int(b.get("angle", 90))
        speed = self._speed(b.get("speed"), "manual")
        self.step_label = f"Motor {side} {angle:+d}°"
        self.turn_side(side, angle, speed)

    def _b_pair(self, b):
        angle = int(b.get("angle", 90))
        speed = self._speed(b.get("speed"), "scan")
        self.step_label = f"L+R drehen {angle:+d}°"
        self.turn_pair(angle, speed)

    def _b_wait(self, b):
        sec = float(b.get("seconds", 1))
        self.step_label = f"Warten {sec:g} s"
        end = time.monotonic() + sec
        while time.monotonic() < end:
            self._check_stop()
            time.sleep(0.05)

    def _b_beep(self, b):
        self.hw.beep(b.get("pattern", "kurz"))

    def _b_home(self, b):
        self.step_label = "Grundstellung"
        self.go_home()

    def _b_scan(self, b):
        self.step_label = "Unterseite scannen"
        t0 = time.monotonic()
        self.scan_bottom()
        self.run_info["scan_s"] = self.run_info.get("scan_s", 0) + time.monotonic() - t0

    def _b_compute(self, b):
        self.step_label = "Lösung berechnen"
        t0 = time.monotonic()
        self.compute_solution()
        self.run_info["compute_s"] = round(time.monotonic() - t0, 3)

    def _b_execute(self, b):
        t0 = time.monotonic()
        self.execute_solution(b.get("speed") or "solve")
        self.run_info["solve_s"] = round(time.monotonic() - t0, 2)
        self.run_info["moves"] = len(self.solution)

    # ===================================================================== Aktionen
    def _cyl_at(self, cyl, extended, reeds=None):
        reeds = reeds or self.hw.reeds()
        key = "out" if extended else "in"
        return all(reeds[s][key] for s in CYLINDERS[cyl])

    def _extended(self, side):
        return self.hw.cyl_target[CYL_OF[side]]

    def set_cylinder(self, cyl, extended, check=True):
        if cyl not in CYLINDERS:
            raise SafetyError(f"Unbekannter Zylinder {cyl}")
        if check and self.interlocks and not extended:
            self._check_support_after_retract(cyl)
        self.hw.set_cylinder(cyl, extended)
        self.emit({"type": "cyl", "target": cyl, "extended": extended})
        timeout = self.settings["reed_timeout_s"]
        end = time.monotonic() + timeout
        while not self._cyl_at(cyl, extended):
            if time.monotonic() > end:
                names = " + ".join(CYLINDERS[cyl])
                raise TimeoutError(
                    f"Reed {names} meldet nach {timeout:g} s nicht „{'ausgefahren' if extended else 'eingefahren'}“"
                )
            if self._stop.is_set():
                raise StopRequested()
            time.sleep(0.01)
        time.sleep(self.settings["cylinder_settle_ms"] / 1000)

    def _check_support_after_retract(self, cyl):
        if not self.hw.light_barrier():
            return  # kein Würfel drin
        after = dict(self.hw.cyl_target)
        after[cyl] = False
        held_before = self.hw.cyl_target["D"] or self.hw.cyl_target["LR"] or self.hw.cyl_target["FB"]
        held_after = after["D"] or after["LR"] or after["FB"]
        if held_before and not held_after and cyl != "D":
            raise SafetyError(
                f"{cyl} einfahren würde den Würfel fallen lassen – zuerst D ausfahren oder das andere Greiferpaar schließen"
            )

    def _check_cylinders_settled(self):
        reeds = self.hw.reeds()
        for cyl, ext in self.hw.cyl_target.items():
            if not self._cyl_at(cyl, ext, reeds):
                raise SafetyError(f"Zylinder {cyl} ist nicht in Endlage – Drehen gesperrt")

    def classify_turn(self, side):
        """Was passiert mit dem Würfel, wenn Motor 'side' dreht?
        -> 'free' (Greifer in der Luft), 'layer' (Schichtzug), 'whole' (ganzer Würfel)"""
        if not self._extended(side):
            return "free"
        holders = [s for s in SIDES if s != side and self._extended(s)]
        if not holders:
            return "whole"
        if holders == [OPPOSITE[side]]:
            return "ambiguous"
        return "layer"

    def turn_side(self, side, angle, speed, update_model=True):
        if angle % 90:
            raise SafetyError("Nur Vielfache von 90° erlaubt (Feinjustage im Handbetrieb)")
        q = angle // 90
        if self.interlocks:
            self._check_cylinders_settled()
        kind = self.classify_turn(side)
        if kind == "ambiguous" and self.interlocks:
            raise SafetyError(
                f"Nur der gegenüberliegende Greifer hält – {side} drehen würde die Mittelschicht mitreißen"
            )
        if kind == "whole":
            self.log(f"{side} dreht den ganzen Würfel über Reibung mit")
        steps = q * self.settings["steps_per_90"]
        self.emit({"type": "anim", "kind": kind, "face": side, "quarters": q,
                   "duration": self._anim_ms(steps, speed)})
        self.hw.turn({side: steps}, speed)
        if update_model:
            if kind == "layer":
                self.model.turn_layer(side, q)
            elif kind == "whole":
                self.model.rotate_whole(side, q)
            self._cube_event()

    def turn_pair(self, angle, speed):
        if angle % 90:
            raise SafetyError("Nur Vielfache von 90° erlaubt")
        q = angle // 90
        if self.interlocks:
            self._check_cylinders_settled()
            if not (self._extended("L") and self._extended("R")):
                raise SafetyError("L+R drehen geht nur, wenn L und R ausgefahren sind")
            others = [s for s in ("U", "D", "F", "B") if self._extended(s)]
            if others:
                raise SafetyError(f"L+R drehen gesperrt: {', '.join(others)} ist ausgefahren – Würfel würde verklemmen")
        steps = q * self.settings["steps_per_90"]
        self.emit({"type": "anim", "kind": "whole", "face": "R", "quarters": q,
                   "duration": self._anim_ms(steps, speed)})
        # R im Uhrzeigersinn und L gegen den Uhrzeigersinn (jeweils von außen gesehen)
        self.hw.turn({"R": steps, "L": -steps}, speed)
        self.model.rotate_whole("R", q)
        self._cube_event()

    def _anim_ms(self, steps, speed):
        from .hardware import move_duration

        f = self.settings["sim_time_factor"] if self.hw.name == "sim" else 1.0
        return int(1000 * move_duration(abs(steps), self.settings, speed) * f)

    def go_home(self):
        """Grundstellung: U, dann F/B, dann L/R, zuletzt D (senkt den Würfel ab).
        Hält gerade ein Greiferpaar den Würfel, fährt D vorher aus und fängt ihn auf."""
        t = self.hw.cyl_target
        if self.hw.light_barrier() and not t["D"] and (t["LR"] or t["FB"]):
            self.set_cylinder("D", True, check=False)
        for cyl in ("U", "FB", "LR", "D"):
            if self.hw.cyl_target[cyl]:
                self.set_cylinder(cyl, False, check=False)

    # ----------------------------------------------------------------- Scan
    def scan_bottom(self):
        timeout = self.settings["scan_timeout_s"]
        self.cam.reset()
        end = time.monotonic() + timeout
        self.cam.info_text = "Scan läuft"
        while True:
            self._check_stop()
            self.cam.wait_frame(0.5)
            if self.cam.stable and self.cam.mean_values:
                values = self.cam.mean_values
                break
            if time.monotonic() > end:
                self.cam.info_text = ""
                raise TimeoutError(
                    f"Kamera hat nach {timeout:g} s nur {self.cam.ok_count}/9 Felder stabil erkannt"
                )
        self.cam.info_text = ""
        bottom = self.model.face_stickers("D")
        for st, val in zip(bottom, values):
            st.rgb = tuple(round(v, 1) for v in val)
            st.color = vision.nearest_reference(val)  # vorläufig
        if self.settings["save_scan_images"] and self.cam.last_frame is not None:
            d = DATA_DIR / "scans"
            d.mkdir(parents=True, exist_ok=True)
            fn = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{sum(1 for s in self.model.stickers if s.rgb) // 9}.jpg"
            cv2.imwrite(str(fn), cv2.cvtColor(self.cam.last_frame, cv2.COLOR_RGB2BGR))
        n = sum(1 for s in self.model.stickers if s.rgb is not None)
        self.log(f"Seite gescannt ({n // 9}/6)")
        if n == 54:
            self.classify_all()
        self._cube_event()

    def classify_all(self):
        centers = [self.model.face_stickers(f)[4].id for f in FACES]
        colors, quality = vision.classify({s.id: s.rgb for s in self.model.stickers}, centers)
        for s in self.model.stickers:
            if not getattr(s, "manual", False):
                s.color = colors[s.id]
        self.log(f"Farben über die Mittelsteine kalibriert (Abweichung {quality:.1f})")

    # ----------------------------------------------------------------- Lösen
    def compute_solution(self):
        if not self.model.is_complete():
            missing = 54 - sum(1 for s in self.model.stickers if s.color)
            raise solver.CubeStateError(f"Es fehlen noch {missing} Felder – zuerst alle 6 Seiten scannen")
        cs = self.model.kociemba_string()
        text, moves = solver.solve(cs)
        self.solution, self.solution_text, self.solution_index = moves, text, 0
        self.log(f"Lösung ({len(moves)} Züge): {text or 'schon gelöst'}")
        self.emit({"type": "solution", "text": text, "len": len(moves)})

    def execute_solution(self, speed_spec="solve"):
        """speed_spec wird vor jedem Zug neu gelesen – so wirkt der Regler
        „Lösegeschwindigkeit“ auch während des Lösens."""
        if not self.solution and self.solution_text == "":
            if not self.model.is_solved():
                raise solver.CubeStateError("Keine Lösung berechnet")
        for s in SIDES:
            if not self._extended(s):
                raise SafetyError("Zum Lösen müssen alle Greifer ausgefahren sein")
        for i, (face, q) in enumerate(self.solution):
            self._check_stop()
            if self.step_mode:
                self.status = "wartet"
                self._step_go.clear()
                while not self._step_go.wait(0.1):
                    self._check_stop()
                self.status = "läuft"
            self.solution_index = i
            angle = {1: 90, 2: 180, 3: -90}[q]
            self.step_label = f"Zug {i + 1}/{len(self.solution)}: {format_moves([(face, q)])}"
            self.emit({"type": "move_index", "index": i})
            self.turn_side(face, angle, self._speed(speed_spec, "solve"))
            time.sleep(self.settings["pause_between_moves_ms"] / 1000)
        self.solution_index = len(self.solution)
        self.emit({"type": "move_index", "index": len(self.solution)})

    # ===================================================================== Handbetrieb
    def manual_guard(self):
        if self.is_running():
            raise RuntimeError("Handbetrieb gesperrt, solange ein Ablauf läuft")

    def manual_cylinder(self, cyl, extended):
        self.manual_guard()
        self.set_cylinder(cyl, extended)

    def manual_jog(self, side, steps, speed=None):
        """Motor um beliebige Schritte drehen (auch Feinjustage)."""
        self.manual_guard()
        speed = speed or self.settings["speed_manual"]
        spq = self.settings["steps_per_90"]
        if steps % spq == 0:
            self.turn_side(side, steps // spq * 90, speed)
        else:
            if self.interlocks and self.classify_turn(side) != "free":
                raise SafetyError("Feinjustage nur mit eingefahrenem Greifer")
            self.hw.turn({side: steps}, speed)

    def manual_pair(self, angle):
        self.manual_guard()
        self.turn_pair(angle, self.settings["speed_manual"])

    def set_sticker(self, face, index, color):
        st = self.model.face_stickers(face)[index]
        st.color = color
        st.manual = True
        self._cube_event()
        self.log(f"Feld {face}{index + 1} von Hand auf {color} gesetzt")

    def reset_model(self):
        self.manual_guard()
        self.model = CubeModel.blank()
        self.solution, self.solution_text, self.solution_index = [], "", 0
        self._cube_event()


# ===================================================================== Programme
def list_programs():
    PROGRAM_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in PROGRAM_DIR.glob("*.json"))
    if "standard" not in names:
        names.insert(0, "standard")
    return names


def load_program(name):
    p = PROGRAM_DIR / f"{name}.json"
    if p.exists():
        return json.loads(p.read_text())
    if name == "standard":
        return json.loads(DEFAULT_PROGRAM_FILE.read_text())
    raise FileNotFoundError(name)


def save_program(name, program):
    if not name or any(c in name for c in "/\\.") or len(name) > 60:
        raise ValueError("Ungültiger Programmname")
    PROGRAM_DIR.mkdir(parents=True, exist_ok=True)
    program = dict(program)
    program["name"] = name
    (PROGRAM_DIR / f"{name}.json").write_text(json.dumps(program, indent=2, ensure_ascii=False))
