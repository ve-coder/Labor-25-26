import RPi.GPIO as GPIO
import time
from pynput import keyboard

# Pins definieren
STEP = 17
DIR = 27
EN = 23

# Konfiguration
STEPS_PER_90 = 20000000000  # 200 Schritte/Umdrehung -> 50 Schritte für 90 Grad
DELAY = 0.0003     # Geschwindigkeit der Schritte

GPIO.setmode(GPIO.BCM)
GPIO.setup([STEP, DIR, EN], GPIO.OUT)
GPIO.output(EN, GPIO.LOW) # Motor an

def rotate(direction, steps):
    """ Dreht den Motor in eine Richtung um eine Anzahl an Schritten """
    GPIO.output(DIR, direction)
    for _ in range(steps):
        GPIO.output(STEP, GPIO.HIGH)
        time.sleep(DELAY)
        GPIO.output(STEP, GPIO.LOW)
        time.sleep(DELAY)

def on_press(key):
    try:
        if key == keyboard.Key.right:
            print("90° im Uhrzeigersinn...")
            GPIO.output(EN, GPIO.LOW)
            rotate(GPIO.HIGH, STEPS_PER_90)
            GPIO.output(EN, GPIO.HIGH)
        elif key == keyboard.Key.left:
            print("90° gegen den Uhrzeigersinn...")
            GPIO.output(EN, GPIO.LOW)
            rotate(GPIO.LOW, STEPS_PER_90)
            GPIO.output(EN, GPIO.HIGH)
    except Exception as e:
        print(f"Fehler: {e}")

def on_release(key):
    if key == keyboard.Key.esc:
        # Beendet das Programm bei Druck auf ESC
        return False

print("Steuerung bereit: Pfeiltaste RECHTS / LINKS. (ESC zum Beenden)")

# Tastatur-Listener starten
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()

# Aufräumen
GPIO.output(EN, GPIO.HIGH)
GPIO.cleanup()