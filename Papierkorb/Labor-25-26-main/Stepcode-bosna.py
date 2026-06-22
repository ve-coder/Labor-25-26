import RPi.GPIO as GPIO
import time
import sys

# Pins
STEP = 17
DIR = 27
EN = 23

GPIO.setmode(GPIO.BCM)
GPIO.setup([STEP, DIR, EN], GPIO.OUT)

# Den Motor sicher aktivieren
GPIO.output(EN, GPIO.LOW) # A4988 ist aktiv bei LOW
GPIO.output(DIR, GPIO.HIGH)

print("Motor ist aktiviert. Drücke ENTER zum Stoppen.")

try:
    # Wir nutzen eine Variable, um die Schleife zu steuern
    while True:
        # Ein Puls: An, kurz warten, Aus, kurz warten
        GPIO.output(STEP, GPIO.HIGH)
        time.sleep(0.0005) # Erhöhe diesen Wert auf 0.01, falls er nur summt
        GPIO.output(STEP, GPIO.LOW)
        time.sleep(0.0005)

except KeyboardInterrupt:
    print("\nProgramm beendet.")
finally:
    GPIO.output(EN, GPIO.HIGH) # Motor stromlos machen
    GPIO.cleanup()