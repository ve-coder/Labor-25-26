import RPi.GPIO as GPIO
import time

Rel = 17
GPIO.setmode(GPIO. BCM)
GPIO.setup(Rel, GPIO.OUT)
while True:
    GPIO.output(Rel, GPIO.HIGH)
    print("An")
    time.sleep(1)
    GPIO.output(Rel, GPIO.LOW)
    print("Aus")
    time.sleep(1)