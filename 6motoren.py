#!/usr/bin/env python3
import time
import threading
import queue
import pigpio
from pynput import keyboard

# ==========================================
# EINSTELLUNGEN
# ==========================================

# --- Pin Definitionen (BCM Nummern) ---
# Format: (STEPstein, DIRk, ENtner)

# Motor 1 (L/R)
M1_PINS = (17, 27, 23)
# Motor 2 (O/U)
M2_PINS = (6, 5, 22)
# Motor 3 (V/H)
M3_PINS = (8, 25, 24)

# Motor 4 (jetzt sicher ohne I2C Pins)
M4_PINS = (13, 14, 15)    

# Motor 5
M5_PINS = (16, 18, 9)

# Motor 6
M6_PINS = (10, 11, 12)

# Alles in einer Map zusammenfassen für sauberen Code
MOTORS = {
    1: M1_PINS,
    2: M2_PINS,
    3: M3_PINS,
    4: M4_PINS,
    5: M5_PINS,
    6: M6_PINS
}

# --- Bewegungsprofil ---
# TIPP: 1/16 Microstepping nutzen (800 Steps) für mehr Kraft/Laufruhe!
# Aktuell eingestellt: Vollschritt (50 Steps = 90 Grad bei 1.8° Motor)
STEPS_PER_90 = 50       

# Geschwindigkeiten (Steps pro Sekunde)
F_START = 100           # Startgeschwindigkeit (niedrig = mehr Kraft beim Anlauf)
F_RUN   = 1200          # Max Geschwindigkeit
RAMP_STEPS = 10         # Beschleunigungsweg (in Schritten)

# Enable Logik (Bei A4988/DRV8825: Low=An)
EN_ENABLE  = 0
EN_DISABLE = 1

# ==========================================
# SETUP
# ==========================================

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("Pigpio nicht verbunden. (sudo pigpiod ausgeführt?)")

# 1. Alle Pins initialisieren und Motoren ausschalten
for m_id, (step, dir_pin, en) in MOTORS.items():
    pi.set_mode(step, pigpio.OUTPUT)
    pi.set_mode(dir_pin, pigpio.OUTPUT)
    pi.set_mode(en, pigpio.OUTPUT)
    
    pi.write(step, 0)
    pi.write(en, EN_DISABLE) # Sofort aus

pi.wave_clear()

# ==========================================
# FUNKTIONEN
# ==========================================

def rotate_ramped(step_pin, dir_pin, en_pin, direction, steps):
    """Erzeugt eine Wave mit Rampe für einen spezifischen Motor."""
    
    # Motor an und kurz warten (Feldaufbau)
    pi.write(en_pin, EN_ENABLE)
    pi.write(dir_pin, 1 if direction else 0)
    time.sleep(0.05) 

    step_mask = 1 << step_pin
    pulses = []
    
    # Rampen-Logik berechnen
    current_ramp = RAMP_STEPS
    if steps < (RAMP_STEPS * 2):
        current_ramp = steps // 2

    for i in range(steps):
        # Beschleunigen / Bremsen
        if i < current_ramp:
            factor = i / current_ramp
            f = F_START + (F_RUN - F_START) * factor
        elif i >= steps - current_ramp:
            reverse_i = steps - 1 - i
            factor = reverse_i / current_ramp
            f = F_START + (F_RUN - F_START) * factor
        else:
            f = F_RUN

        # Pulsweite berechnen
        period_us = int(1_000_000 / max(1, f))
        hi = 5  # Kurzer Trigger reicht
        lo = max(5, period_us - hi)

        pulses.append(pigpio.pulse(step_mask, 0, hi))
        pulses.append(pigpio.pulse(0, step_mask, lo))

    # Wave erstellen
    pi.wave_add_generic(pulses)
    try:
        wid = pi.wave_create()
    except:
        print(f"Fehler Wave Motor an Pin {step_pin} (Buffer voll?)")
        pi.write(en_pin, EN_DISABLE)
        return

    # Senden
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)
        
    pi.wave_delete(wid)
    pi.write(en_pin, EN_DISABLE) # Strom sparen nach Bewegung

# ==========================================
# WORKER THREAD
# ==========================================
cmd_q = queue.Queue()
stop_event = threading.Event()

def worker():
    print("Worker läuft...")
    while not stop_event.is_set():
        try:
            task = cmd_q.get(timeout=0.1)
        except queue.Empty:
            continue

        if task is None: break
        
        motor_id, direction = task
        
        if motor_id in MOTORS:
            step_p, dir_p, en_p = MOTORS[motor_id]
            dir_str = "Rechts/Uhrzeigersinn" if direction else "Links/Gegen-Uhrzeigersinn"
            print(f"Motor {motor_id} (Pin {step_p}) -> {dir_str}")
            
            # SICHERHEIT: Alle anderen Enable-Pins auf DISABLE zwingen
            for m, pins in MOTORS.items():
                if m != motor_id:
                    pi.write(pins[2], EN_DISABLE)

            rotate_ramped(step_p, dir_p, en_p, direction, STEPS_PER_90)
            
        cmd_q.task_done()

t = threading.Thread(target=worker, daemon=True)
t.start()

# ==========================================
# TASTATUR STEUERUNG
# ==========================================
print("========================================")
print("RUBIK'S CUBE 6-AXIS CONTROL")
print("----------------------------------------")
print("Motor 1: Pfeil Links / Rechts")
print("Motor 2: Pfeil Oben  / Unten")
print("Motor 3: W / S")
print("Motor 4: A / D")
print("Motor 5: Q / E")
print("Motor 6: 1 / 2")
print("ESC    : Beenden")
print("========================================")

pressed = set()

def on_press(key):
    if key in pressed: return
    pressed.add(key)
    try:
        # --- Sonder-Tasten ---
        if key == keyboard.Key.right: cmd_q.put((1, 1))
        elif key == keyboard.Key.left: cmd_q.put((1, 0))
        elif key == keyboard.Key.up:   cmd_q.put((2, 1))
        elif key == keyboard.Key.down: cmd_q.put((2, 0))
        elif key == keyboard.Key.esc:  return False
        
        # --- Zeichen-Tasten ---
        elif hasattr(key, 'char') and key.char:
            k = key.char.lower()
            # Motor 3
            if k == 'w': cmd_q.put((3, 1))
            elif k == 's': cmd_q.put((3, 0))
            # Motor 4
            elif k == 'd': cmd_q.put((4, 1))
            elif k == 'a': cmd_q.put((4, 0))
            # Motor 5
            elif k == 'e': cmd_q.put((5, 1))
            elif k == 'q': cmd_q.put((5, 0))
            # Motor 6
            elif k == '2': cmd_q.put((6, 1))
            elif k == '1': cmd_q.put((6, 0))
            
    except AttributeError:
        pass

def on_release(key):
    pressed.discard(key)
    if key == keyboard.Key.esc: return False

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

# Aufräumen
stop_event.set()
cmd_q.put(None)
t.join()

# Alle Motoren sicher aus
for m_id, (s, d, en) in MOTORS.items():
    pi.write(en, EN_DISABLE)
    
pi.wave_clear()
pi.stop()