from time import sleep
import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
STEP = 17 # step pin
DIR = 27 # direction pin
EN = 23 # enable pin
GPIO.setup(STEP, GPIO.OUT)
GPIO.setup(DIR, GPIO.OUT)
GPIO.setup(EN, GPIO.OUT)
steps = 5000 # number of steps
usDelay = 950 # number of microseconds
uS = 0.000001 # one microsecond
GPIO.output(EN, GPIO.LOW)
print("[press ctrl+c to end the script]")
try: # Main program loop
    while True:
        GPIO.output(DIR, GPIO.HIGH) # cw direction
        for i in range(steps):
            GPIO.output(STEP, GPIO.HIGH)
            sleep(uS * usDelay)
            GPIO.output(STEP, GPIO.LOW)
            sleep(uS * usDelay)
        sleep(2)
        GPIO.output(DIR, GPIO.LOW) # ccw direction
        for i in range(steps):
            GPIO.output(STEP, GPIO.HIGH)
            sleep(uS * usDelay)
            GPIO.output(STEP, GPIO.LOW)
            sleep(uS * usDelay)
        sleep(2)
# Scavenging work after the end of the program
except KeyboardInterrupt:
    GPIO.output(EN, GPIO.HIGH)