#!/usr/bin/env python3
import time
import threading
import queue
import pigpio
from pynput import keyboard

# ---------------- Pins (BCM) ----------------
STEP = 17
DIR  = 27
EN   = 23

# ---------------- Parameter ----------------
# WICHTIG: STEPS_PER_90 muss zu deinem Microstepping passen!
# Beispiel: 200 Schritte/U (1.8° Motor) -> 50 Schritte für 90° bei Vollschritt (1/1)
# Bei 1/16 Microstepping: 50 * 16 = 800
STEPS_PER_90 = 50

DIR_SETTLE_S = 0.01      # Pause nach Richtungswechsel (wichtig!),,00,,
F_START = 300             # Startfrequenz (Steps/s)
F_RUN   = 900            # Fahrfrequenz (Steps/s) -> falls er hängt: kleiner machen (z.B. 600)
RAMP_STEPS = 15           # Schritte zum sanften Anfahren/Abbremsen
MIN_PULSE_US = 3          # Mindest-Pulsbreite (Treiber-sicher)

# Enable-Logik (für A4988/DRV8825 typisch: LOW = enable)
EN_ENABLE  = 0
EN_DISABLE = 1

# ---------------- pigpio init ----------------
pi = pigpio.pi()  # localhost:8888
if not pi.connected:
    raise RuntimeError("Kann nicht zu pigpio verbinden. Läuft pigpiod? (sudo systemctl enable --now pigpiod)")

for pin in (STEP, DIR, EN):
    pi.set_mode(pin, pigpio.OUTPUT)

#pi.write(EN, EN_ENABLE)     # Motor an
pi.write(STEP, 0)
pi.wave_clear()

# ---------------- Bewegung (mit Rampe) ----------------
def rotate_ramped(direction: int, steps: int):
    """Dreht 'steps' Schritte in 'direction' (1/0) mit kurzer Rampe und sauberem Timing."""
    pi.write(EN, EN_ENABLE)
    pi.write(DIR, 1 if direction else 0)
    time.sleep(DIR_SETTLE_S)

    step_mask = 1 << STEP
    pulses = []

    ramp = min(RAMP_STEPS, steps // 2) if steps >= 2 else 0

    for i in range(steps):
        # lineare Rampe hoch und runter
        if ramp and i < ramp:
            f = F_START + (F_RUN - F_START) * (i / ramp)
        elif ramp and i >= steps - ramp:
            j = steps - 1 - i
            f = F_START + (F_RUN - F_START) * (j / ramp)
        else:
            f = F_RUN

        period_us = int(1_000_000 / max(1, f))
        hi = max(MIN_PULSE_US, period_us // 2)
        lo = max(MIN_PULSE_US, period_us - hi)

        pulses.append(pigpio.pulse(step_mask, 0, hi))   # STEP high
        pulses.append(pigpio.pulse(0, step_mask, lo))   # STEP low

    pi.wave_add_generic(pulses)
    wid = pi.wave_create()
    try:
        pi.wave_send_once(wid)
        while pi.wave_tx_busy():
            time.sleep(0.001)
    finally:
        pi.wave_delete(wid)
    pi.write(EN, EN_DISABLE)
# ---------------- Worker: führt Moves sauber nacheinander aus ----------------
cmd_q = queue.Queue()
stop_event = threading.Event()

def worker():
    while not stop_event.is_set():
        try:
            direction = cmd_q.get(timeout=0.1)
        except queue.Empty:
            continue

        if direction is None:  # Stop-Sentinel
            break

        rotate_ramped(direction, STEPS_PER_90)
        cmd_q.task_done()

t = threading.Thread(target=worker, daemon=True)
t.start()

# ---------------- Keyboard handling (ohne Key-Repeat) ----------------
pressed = set()

def on_press(key):
    if key in pressed:     # Key-Repeat ignorieren
        return
    pressed.add(key)

    if key == keyboard.Key.right:
        print("90° im Uhrzeigersinn")
        cmd_q.put(1)
    elif key == keyboard.Key.left:
        print("90° gegen den Uhrzeigersinn")
        cmd_q.put(0)

def on_release(key):
    pressed.discard(key)
    if key == keyboard.Key.esc:
        return False

print("Bereit: Pfeil LINKS/RECHTS (ESC beendet)")

try:
    with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
        listener.join()
finally:
    # sauber stoppen
    stop_event.set()
    cmd_q.put(None)
    t.join(timeout=1.0)

    pi.write(EN, EN_DISABLE)
    pi.wave_clear()
    pi.stop()