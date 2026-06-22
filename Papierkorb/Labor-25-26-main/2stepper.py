#!/usr/bin/env python3
import time
import threading
import queue
import pigpio
from pynput import keyboard

# ==========================================
# EINSTELLUNGEN (HIER ANPASSEN!)
# ==========================================

# --- Motor 1 (z.B. Links/Rechts) ---
STEP_1 = 17
DIR_1  = 27
EN_1   = 23  

# --- Motor 2 (z.B. Oben/Unten) ---
# WICHTIG: Trage hier deine ECHTEN Pins ein!
STEP_2 = 6   
DIR_2  = 5   
EN_2   = 22  # Muss ein eigener Pin sein, sonst gehen beide gleichzeitig an!

STEP_3 = 6
DIR_3 = 7
EN_3  = 67  


#15v verwnden!!!
# --- Bewegungsprofil (Rubik's Cube Tuning) ---
# Wie viele Schritte sind 90 Grad?
# Standard 1.8 Grad Motor: 200 Schritte pro Umdrehung.
# 90 Grad = 50 Schritte (bei Vollschritt).
# 90 Grad = 800 Schritte (bei 1/16 Microstepping -> EMPFOHLEN!).
STEPS_PER_90 = 50   

# Geschwindigkeiten (Steps pro Sekunde)
F_START = 100       # Langsam starten (für Drehmoment)
F_RUN   = 1200       # Endgeschwindigkeit
RAMP_STEPS = 10     # Über wie viele Schritte beschleunigt wird (Rampe)

# Enable Logik (0=An, 1=Aus bei A4988/DRV8825)
EN_ENABLE  = 0
EN_DISABLE = 1

# ==========================================

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("Pigpio nicht verbunden. (sudo pigpiod ausgeführt?)")

# Pins initialisieren
all_pins = [STEP_1, DIR_1, EN_1, STEP_2, DIR_2, EN_2]
for pin in all_pins:
    pi.set_mode(pin, pigpio.OUTPUT)

# Alles ausschalten zum Start
pi.write(EN_1, EN_DISABLE)
pi.write(EN_2, EN_DISABLE)
pi.wave_clear()

def rotate_ramped(step_pin, dir_pin, en_pin, direction, steps):
    """Erzeugt eine Wave mit Anfahr-Rampe für maximales Drehmoment."""
    
    # 1. Motor einschalten und kurz warten (Magnetfeld aufbauen)
    pi.write(en_pin, EN_ENABLE)
    pi.write(dir_pin, 1 if direction else 0)
    time.sleep(0.05) # 50ms warten, damit der Motor greift

    step_mask = 1 << step_pin
    pulses = []
    
    # Rampen-Logik: Falls wir weniger Schritte haben als für die Rampe nötig, halbieren wir die Rampe
    current_ramp = RAMP_STEPS
    if steps < (RAMP_STEPS * 2):
        current_ramp = steps // 2

    for i in range(steps):
        # Frequenz berechnen
        if i < current_ramp:
            # Beschleunigen
            factor = i / current_ramp
            f = F_START + (F_RUN - F_START) * factor
        elif i >= steps - current_ramp:
            # Abbremsen
            reverse_i = steps - 1 - i
            factor = reverse_i / current_ramp
            f = F_START + (F_RUN - F_START) * factor
        else:
            # Konstante Fahrt
            f = F_RUN

        # Periodendauer in Mikrosekunden
        period_us = int(1_000_000 / max(1, f))
        
        # Kurze Pulse (High) reichen, Pause (Low) bestimmt die Geschwindigkeit
        hi = 5  
        lo = max(5, period_us - hi)

        pulses.append(pigpio.pulse(step_mask, 0, hi))
        pulses.append(pigpio.pulse(0, step_mask, lo))

    # Wave senden
    pi.wave_add_generic(pulses)
    try:
        wid = pi.wave_create()
    except:
        print("Fehler beim Erstellen der Wave (zu viele Pulse?)")
        pi.write(en_pin, EN_DISABLE)
        return

    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.01)
        
    pi.wave_delete(wid)
    
    # Motor wieder aus (oder an lassen, wenn er den Würfel halten muss)
    pi.write(en_pin, EN_DISABLE)

# --- Worker Thread ---
cmd_q = queue.Queue()
stop_event = threading.Event()

def worker():
    print("Worker Thread gestartet...")
    while not stop_event.is_set():
        try:
            task = cmd_q.get(timeout=0.1)
        except queue.Empty:
            continue

        if task is None: break
        
        motor_id, direction = task
        print(f"Bewege Motor {motor_id}...")

        if motor_id == 1:
            # Sicherstellen, dass Motor 2 aus ist
            pi.write(EN_2, EN_DISABLE)
            rotate_ramped(STEP_1, DIR_1, EN_1, direction, STEPS_PER_90)
        elif motor_id == 2:
            # Sicherstellen, dass Motor 1 aus ist
            pi.write(EN_1, EN_DISABLE)
            rotate_ramped(STEP_2, DIR_2, EN_2, direction, STEPS_PER_90)
            
        cmd_q.task_done()

t = threading.Thread(target=worker, daemon=True)
t.start()

# --- Steuerung ---
print("========================================")
print("RUBIK'S CUBE STEUERUNG")
print("----------------------------------------")
print(f"Motor 1 (L/R) an Pins: S={STEP_1}, D={DIR_1}, E={EN_1}")
print(f"Motor 2 (O/U) an Pins: S={STEP_2}, D={DIR_2}, E={EN_2}")
print("----------------------------------------")
print("PFEIL LINKS/RECHTS -> Motor 1")
print("PFEIL OBEN/UNTEN   -> Motor 2")
print("ESC                -> Beenden")
print("========================================")

pressed = set()

def on_press(key):
    if key in pressed: return
    pressed.add(key)
    try:
        if key == keyboard.Key.right: #motor1
            cmd_q.put((1, 1))
        elif key == keyboard.Key.left:
            cmd_q.put((1, 0))
        elif key == keyboard.Key.up: #motor2
            cmd_q.put((2, 1))
        elif key == keyboard.Key.down:
            cmd_q.put((2, 0))
            #print ("down")
        elif key.char == "w": #motor3
            #cmd_q.put((2, 1))
            print("w")
        elif key == keyboard.s:
            cmd_q.put((2, 0))
            
        elif key == keyboard.Key.esc:
            return False
    except: pass

def on_release(key):
    pressed.discard(key)
    if key == keyboard.Key.esc: return False

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

stop_event.set()
cmd_q.put(None)
t.join()
pi.write(EN_1, EN_DISABLE)
pi.write(EN_2, EN_DISABLE)
pi.stop()