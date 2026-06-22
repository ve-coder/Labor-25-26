from gpiozero import Button
from time import sleep

# Pin 11 auf dem Pi entspricht GPIO 17
# pull_up=True aktiviert den internen Widerstand des Pi
lichtschranke = Button(17, pull_up=True)

print("Starte Lichtschranken-Test... (Abbruch mit STRG+C)")

while True:
    if lichtschranke.is_pressed:
        print("Lichtstrahl UNTERBROCHEN! (Objekt im Schlitz)")
    else:
        print("Schlitz ist FREI.")

    # Eine halbe Sekunde warten, damit der Text nicht zu schnell durchrauscht
    sleep(0.1)