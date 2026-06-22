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
M1_PINS = (17, 27, 23)  # Motor 1 (STEP, DIR, EN)
M2_PINS = (6, 5, 22)    # Motor 2 (STEP, DIR, EN)
M3_PINS = (8, 25, 24)   # Motor 3
M4_PINS = (13, 14, 15)  # Motor 4
M5_PINS = (16, 18, 9)   # Motor 5
M6_PINS = (10, 11, 12)  # Motor 6

MOTORS = {
    1: M1_PINS,
    2: M2_PINS,
    3: M3_PINS,
    4: M4_PINS,
    5: M5_PINS,
    6: M6_PINS
}

# --- Bewegungsprofil ---
STEPS_PER_90 = 50       # 90° Drehung
F_START = 100           # Startgeschwindigkeit
F_RUN   = 1200          # Max Geschwindigkeit
RAMP_STEPS = 10         # Beschleunigungsweg

# Enable Logik
EN_ENABLE  = 0
EN_DISABLE = 1

# ==========================================
# SETUP
# ==========================================

pi = pigpio.pi()
if not pi.connected:
    raise RuntimeError("Pigpio nicht verbunden. (sudo pigpiod ausgeführt?)")

# Alle Pins initialisieren
for m_id, (step, dir_pin, en) in MOTORS.items():
    pi.set_mode(step, pigpio.OUTPUT)
    pi.set_mode(dir_pin, pigpio.OUTPUT)
    pi.set_mode(en, pigpio.OUTPUT)
    pi.write(step, 0)
    pi.write(en, EN_DISABLE)

pi.wave_clear()

# ==========================================
# SYNCHRONE 2-MOTOR BEWEGUNG
# ==========================================

def rotate_two_motors_sync(motor1_id, dir1, motor2_id, dir2, steps):
    """
    Bewegt zwei Motoren EXAKT synchron mit identischen Pulsen.
    Beide Step-Pins werden gleichzeitig in einer Wave angesteuert.
    """
    
    step1, dir_pin1, en1 = MOTORS[motor1_id]
    step2, dir_pin2, en2 = MOTORS[motor2_id]
    
    # Alle anderen Motoren sicherstellen dass sie AUS sind
    for m, pins in MOTORS.items():
        if m not in [motor1_id, motor2_id]:
            pi.write(pins[2], EN_DISABLE)
    
    # Beide Motoren aktivieren und Richtung setzen
    pi.write(en1, EN_ENABLE)
    pi.write(en2, EN_ENABLE)
    pi.write(dir_pin1, 1 if dir1 else 0)
    pi.write(dir_pin2, 1 if dir2 else 0)
    time.sleep(0.05)  # Feldaufbau abwarten
    
    # BEIDE Step-Pins in einer gemeinsamen Maske
    step_mask = (1 << step1) | (1 << step2)
    pulses = []
    
    # Rampen berechnen
    current_ramp = RAMP_STEPS
    if steps < (RAMP_STEPS * 2):
        current_ramp = steps // 2
    
    for i in range(steps):
        # Geschwindigkeit berechnen (Beschleunigung/Bremsung)
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
        
        # BEIDE Pins gleichzeitig HIGH dann LOW
        pulses.append(pigpio.pulse(step_mask, 0, hi))
        pulses.append(pigpio.pulse(0, step_mask, lo))
    
    # Wave erstellen und senden
    pi.wave_add_generic(pulses)
    try:
        wid = pi.wave_create()
    except:
        print(f"⚠️  Wave-Buffer voll! Warte...")
        pi.write(en1, EN_DISABLE)
        pi.write(en2, EN_DISABLE)
        return
    
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.001)
    
    pi.wave_delete(wid)
    
    # Beide Motoren wieder ausschalten
    pi.write(en1, EN_DISABLE)
    pi.write(en2, EN_DISABLE)

# ==========================================
# EINZELMOTOR BEWEGUNG (für andere Tasten)
# ==========================================

def rotate_single(motor_id, direction, steps):
    """Einzelner Motor (wie gehabt)"""
    step_pin, dir_pin, en_pin = MOTORS[motor_id]
    
    # Alle anderen aus
    for m, pins in MOTORS.items():
        if m != motor_id:
            pi.write(pins[2], EN_DISABLE)
    
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
        
        pulses.append(pigpio.pulse(step_mask, 0, hi))
        pulses.append(pigpio.pulse(0, step_mask, lo))
    
    pi.wave_add_generic(pulses)
    try:
        wid = pi.wave_create()
    except:
        print(f"⚠️  Wave-Buffer voll!")
        pi.write(en_pin, EN_DISABLE)
        return
    
    pi.wave_send_once(wid)
    while pi.wave_tx_busy():
        time.sleep(0.001)
    
    pi.wave_delete(wid)
    pi.write(en_pin, EN_DISABLE)

# ==========================================
# WORKER THREAD
# ==========================================

cmd_q = queue.Queue()
stop_event = threading.Event()

def worker():
    print("✅ Worker läuft...")
    while not stop_event.is_set():
        try:
            task = cmd_q.get(timeout=0.1)
        except queue.Empty:
            continue
        
        if task is None:
            break
        
        task_type = task[0]
        
        if task_type == "SYNC":
            # Synchrone 2-Motor Bewegung
            _, m1, dir1, m2, dir2, steps = task
            print(f"🔄 SYNC: Motor {m1} ({'CW' if dir1 else 'CCW'}) + Motor {m2} ({'CW' if dir2 else 'CCW'})")
            rotate_two_motors_sync(m1, dir1, m2, dir2, steps)
            
        elif task_type == "SINGLE":
            # Einzelmotor
            _, motor_id, direction, steps = task
            dir_str = "CW ⟳" if direction else "CCW ⟲"
            print(f"🔧 Motor {motor_id} -> {dir_str}")
            rotate_single(motor_id, direction, steps)
        
        cmd_q.task_done()

t = threading.Thread(target=worker, daemon=True)
t.start()

# ==========================================
# TASTATUR STEUERUNG
# ==========================================

print("\n" + "="*50)
print("🎮  RUBIK'S CUBE - SYNCHRONE STEUERUNG")
print("="*50)
print("⬆️  Pfeil OBEN   : Motor 1 (CW) + Motor 2 (CCW) SYNCHRON")
print("⬇️  Pfeil UNTEN  : Motor 1 (CCW) + Motor 2 (CW) SYNCHRON")
print("⬅️  Pfeil LINKS  : Motor 1 einzeln (CCW)")
print("➡️  Pfeil RECHTS : Motor 1 einzeln (CW)")
print("---")
print("W / S : Motor 3")
print("A / D : Motor 4")
print("Q / E : Motor 5")
print("1 / 2 : Motor 6")
print("---")
print("ESC   : Beenden")
print("="*50 + "\n")

pressed = set()

def on_press(key):
    if key in pressed:
        return
    pressed.add(key)
    
    try:
        # ===== SYNCHRONE BEWEGUNGEN =====
        if key == keyboard.Key.up:
            # Motor 1 im Uhrzeigersinn (CW=1) + Motor 2 GEGEN Uhrzeigersinn (CCW=1)
            cmd_q.put(("SYNC", 1, 1, 2, 1, STEPS_PER_90))
            
        elif key == keyboard.Key.down:
            # Motor 1 gegen Uhrzeigersinn (CCW=0) + Motor 2 IM Uhrzeigersinn (CW=0)
            cmd_q.put(("SYNC", 1, 0, 2, 0, STEPS_PER_90))
        
        # ===== EINZELNE BEWEGUNGEN =====
        elif key == keyboard.Key.right:
            cmd_q.put(("SINGLE", 1, 1, STEPS_PER_90))
        elif key == keyboard.Key.left:
            cmd_q.put(("SINGLE", 1, 0, STEPS_PER_90))
        
        elif key == keyboard.Key.esc:
            return False
        
        # Zeichen-Tasten
        elif hasattr(key, 'char') and key.char:
            k = key.char.lower()
            if k == 'w':
                cmd_q.put(("SINGLE", 3, 1, STEPS_PER_90))
            elif k == 's':
                cmd_q.put(("SINGLE", 3, 0, STEPS_PER_90))
            elif k == 'd':
                cmd_q.put(("SINGLE", 4, 1, STEPS_PER_90))
            elif k == 'a':
                cmd_q.put(("SINGLE", 4, 0, STEPS_PER_90))
            elif k == 'e':
                cmd_q.put(("SINGLE", 5, 1, STEPS_PER_90))
            elif k == 'q':
                cmd_q.put(("SINGLE", 5, 0, STEPS_PER_90))
            elif k == '2':
                cmd_q.put(("SINGLE", 6, 1, STEPS_PER_90))
            elif k == '1':
                cmd_q.put(("SINGLE", 6, 0, STEPS_PER_90))
    
    except AttributeError:
        pass

def on_release(key):
    pressed.discard(key)
    if key == keyboard.Key.esc:
        return False

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

# ==========================================
# CLEANUP
# ==========================================

print("\n🛑 Beende Programm...")
stop_event.set()
cmd_q.put(None)
t.join()

# Alle Motoren aus
for m_id, (s, d, en) in MOTORS.items():
    pi.write(en, EN_DISABLE)

pi.wave_clear()
pi.stop()
print("✅ Sauber beendet.\n")