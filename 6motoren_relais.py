#!/usr/bin/env python3
"""
Kombiniertes Programm: 6 Schrittmotoren + 4 Relais
Tastatur-Steuerung über pynput (non-blocking).
"""
import time
import threading
import queue
import pigpio
from pynput import keyboard

# ==========================================
# MOTOR PINS (BCM)
# ==========================================

# Motor 1 (L/R)
M1_PINS = (17, 27, 23)
# Motor 2 (O/U)
M2_PINS = (6, 5, 22)
# Motor 3 (V/H)
M3_PINS = (8, 25, 24)
# Motor 4
M4_PINS = (13, 14, 15)
# Motor 5
M5_PINS = (16, 18, 9)
# Motor 6
M6_PINS = (10, 11, 12)

MOTORS = {
    1: M1_PINS,
    2: M2_PINS,
    3: M3_PINS,
    4: M4_PINS,
    5: M5_PINS,
    6: M6_PINS,
}

# ==========================================
# RELAIS PINS (BCM) — konfliktfrei mit Motorpins!
# Ursprüngliche Pins (17, 27, 22, 23) wurden von Motoren belegt.
# Neue Zuweisung: GPIO 2, 3, 4, 7
# ==========================================
RELAY_PINS = {
    1: 2,
    2: 3,
    3: 4,
    4: 7,
}

# Relais-Zustand (Active Low: False = AUS, True = AN)
relay_state = {r: False for r in RELAY_PINS}

# ==========================================
# BEWEGUNGSPROFIL
# ==========================================
STEPS_PER_90 = 50
F_START     = 100    # Startgeschwindigkeit (Steps/s)
F_RUN       = 1200   # Max-Geschwindigkeit (Steps/s)
RAMP_STEPS  = 10     # Beschleunigungsweg (Schritte)

EN_ENABLE  = 0
EN_DISABLE = 1

# ==========================================
# SETUP
# ==========================================
pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("Pigpio nicht verbunden. (sudo pigpiod ausgeführt?)")

# Motoren initialisieren
for m_id, (step, dir_pin, en) in MOTORS.items():
    pi.set_mode(step,    pigpio.OUTPUT)
    pi.set_mode(dir_pin, pigpio.OUTPUT)
    pi.set_mode(en,      pigpio.OUTPUT)
    pi.write(step, 0)
    pi.write(en, EN_DISABLE)

# Relais initialisieren (Active Low → AUS = HIGH)
for pin in RELAY_PINS.values():
    pi.set_mode(pin, pigpio.OUTPUT)
    pi.write(pin, 1)

pi.wave_clear()

# ==========================================
# MOTOR-FUNKTION
# ==========================================

def rotate_ramped(step_pin, dir_pin, en_pin, direction, steps):
    """Dreht einen Schrittmotor mit Beschleunigungsrampe."""
    pi.write(en_pin, EN_ENABLE)
    pi.write(dir_pin, 1 if direction else 0)
    time.sleep(0.05)

    step_mask = 1 << step_pin
    pulses = []

    current_ramp = RAMP_STEPS
    if steps < (RAMP_STEPS * 2):
        current_ramp = steps // 2

    for i in range(steps):
        if i < current_ramp:
            factor = i / current_ramp
            f = F_START + (F_RUN - F_START) * factor
        elif i >= steps - current_ramp:
            reverse_i = steps - 1 - i
            factor = reverse_i / current_ramp
            f = F_START + (F_RUN - F_START) * factor
        else:
            f = F_RUN

        period_us = int(1_000_000 / max(1, f))
        hi = 5
        lo = max(5, period_us - hi)

        pulses.append(pigpio.pulse(step_mask, 0,         hi))
        pulses.append(pigpio.pulse(0,         step_mask, lo))

    pi.wave_add_generic(pulses)
    try:
        wid = pi.wave_create()
    except Exception:
        print(f"Fehler Wave Motor an Pin {step_pin} (Buffer voll?)")
        pi.write(en_pin, EN_DISABLE)
        return

    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)

    pi.wave_delete(wid)
    pi.write(en_pin, EN_DISABLE)

# ==========================================
# RELAIS-FUNKTION
# ==========================================

def toggle_relay(relay_id):
    """Schaltet ein Relais um (toggle)."""
    relay_state[relay_id] = not relay_state[relay_id]
    pin = RELAY_PINS[relay_id]
    # Active Low: AN = LOW, AUS = HIGH
    pi.write(pin, 0 if relay_state[relay_id] else 1)
    status = "AN" if relay_state[relay_id] else "AUS"
    print(f"--> Relais {relay_id} (GPIO {pin}) ist jetzt {status}")

# ==========================================
# WORKER-THREAD (Motoren)
# ==========================================
cmd_q = queue.Queue()
stop_event = threading.Event()

def worker():
    print("Motor-Worker läuft...")
    while not stop_event.is_set():
        try:
            task = cmd_q.get(timeout=0.1)
        except queue.Empty:
            continue

        if task is None:
            break

        motor_id, direction = task

        if motor_id in MOTORS:
            step_p, dir_p, en_p = MOTORS[motor_id]
            dir_str = "Rechts/Uhrzeigersinn" if direction else "Links/Gegen-Uhrzeigersinn"
            print(f"Motor {motor_id} (Pin {step_p}) -> {dir_str}")

            # Alle anderen Motoren deaktivieren
            for m, pins in MOTORS.items():
                if m != motor_id:
                    pi.write(pins[2], EN_DISABLE)

            rotate_ramped(step_p, dir_p, en_p, direction, STEPS_PER_90)

        cmd_q.task_done()

t = threading.Thread(target=worker, daemon=True)
t.start()

# ==========================================
# TASTATUR-STEUERUNG
# ==========================================
print("============================================")
print("RUBIK'S CUBE – 6 MOTOREN + 4 RELAIS")
print("--------------------------------------------")
print("Motor 1 : Pfeil Links  / Pfeil Rechts")
print("Motor 2 : Pfeil Oben   / Pfeil Unten")
print("Motor 3 : W / S")
print("Motor 4 : A / D")
print("Motor 5 : Q / E")
print("Motor 6 : 1 / 2")
print("--------------------------------------------")
print("Relais 1: F1  |  Relais 2: F2")
print("Relais 3: F3  |  Relais 4: F4")
print("--------------------------------------------")
print("ESC     : Beenden")
print("============================================")

pressed = set()

def on_press(key):
    if key in pressed:
        return
    pressed.add(key)
    try:
        # --- Pfeiltasten (Motor 1 & 2) ---
        if   key == keyboard.Key.right: cmd_q.put((1, 1))
        elif key == keyboard.Key.left:  cmd_q.put((1, 0))
        elif key == keyboard.Key.up:    cmd_q.put((2, 1))
        elif key == keyboard.Key.down:  cmd_q.put((2, 0))

        # --- Relais (F1–F4) ---
        elif key == keyboard.Key.f1:    toggle_relay(1)
        elif key == keyboard.Key.f2:    toggle_relay(2)
        elif key == keyboard.Key.f3:    toggle_relay(3)
        elif key == keyboard.Key.f4:    toggle_relay(4)

        # --- ESC ---
        elif key == keyboard.Key.esc:
            return False

        # --- Zeichentasten ---
        elif hasattr(key, 'char') and key.char:
            k = key.char.lower()
            if   k == 'w': cmd_q.put((3, 1))
            elif k == 's': cmd_q.put((3, 0))
            elif k == 'd': cmd_q.put((4, 1))
            elif k == 'a': cmd_q.put((4, 0))
            elif k == 'e': cmd_q.put((5, 1))
            elif k == 'q': cmd_q.put((5, 0))
            elif k == '2': cmd_q.put((6, 1))
            elif k == '1': cmd_q.put((6, 0))

    except AttributeError:
        pass

def on_release(key):
    pressed.discard(key)
    if key == keyboard.Key.esc:
        return False

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

# ==========================================
# AUFRÄUMEN
# ==========================================
stop_event.set()
cmd_q.put(None)
t.join()

# Alle Motoren ausschalten
for m_id, (s, d, en) in MOTORS.items():
    pi.write(en, EN_DISABLE)

# Alle Relais ausschalten (Active Low → HIGH)
for pin in RELAY_PINS.values():
    pi.write(pin, 1)

pi.wave_clear()
pi.stop()
