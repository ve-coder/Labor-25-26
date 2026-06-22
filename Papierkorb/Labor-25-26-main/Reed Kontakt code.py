from gpiozero import Button
from signal import pause
import time

# ==========================================
# KONFIGURATION: GPIO Pins definieren
# Trage hier die tatsächlichen BCM-Pin-Nummern ein,
# an die deine Reed-Kontakte angeschlossen sind.
# ==========================================

# Beispiel-Pins (Bitte an deine reale Verkabelung anpassen!)
PINS = {
    "Motor1_Eingefahren": 5,
    "Motor1_Ausgefahren": 6,

    "Motor2_Eingefahren": 13,
    "Motor2_Ausgefahren": 19,

    "Motor3_Eingefahren": 26,
    "Motor3_Ausgefahren": 16,

    "Motor4_Eingefahren": 20,
    "Motor4_Ausgefahren": 21,

    "Motor5_Eingefahren": 22,
    "Motor5_Ausgefahren": 23,

    "Motor6_Eingefahren": 24,
    "Motor6_Ausgefahren": 25
}

# ==========================================
# LOGIK: Event-Handler Funktionen
# ==========================================

def zylinder_erreicht_position(name):
    """Wird aufgerufen, wenn ein Reed-Kontakt schließt (Magnet erkannt)."""
    # Wir nehmen den Namen auseinander (z.B. "Motor1_Ausgefahren")
    teile = name.split('_')
    motor = teile[0]
    position = teile[1]

    # Aktuelle Zeit für ein sauberes Log
    zeitstempel = time.strftime("%H:%M:%S")

    print(f"[{zeitstempel}] {motor} ist {position}!")

# ==========================================
# SETUP & HAUPTPROGRAMM
# ==========================================

print("Starte Zylinder-Überwachung... (Abbruch mit STRG+C)")
print("-" * 40)

# Hier speichern wir unsere Sensor-Objekte
sensoren = {}

# Wir initialisieren alle Pins
for name, pin in PINS.items():
    try:
        # Button-Klasse von gpiozero ist perfekt für Reed-Kontakte.
        # pull_up=True aktiviert den internen Widerstand (erwartet Schaltung gegen GND).
        # bounce_time=0.1 entprellt den Schalter (100ms ignorieren nach dem ersten Kontakt),
        # um mehrfache Ausgaben bei einem einzigen Klick zu verhindern.
        sensor = Button(pin, pull_up=True, bounce_time=0.1)

        # Wenn der Sensor "gedrückt" wird (LOW), rufe unsere Funktion auf
        # Wir übergeben den 'name' über eine kleine Lambda-Funktion, damit
        # die Handler-Funktion weiß, WELCHER Sensor ausgelöst hat.
        sensor.when_pressed = lambda n=name: zylinder_erreicht_position(n)

        sensoren[name] = sensor
        print(f"Sensor '{name}' an Pin {pin} initialisiert.")

    except Exception as e:
        print(f"Fehler bei der Initialisierung von Pin {pin} ({name}): {e}")

print("-" * 40)
print("Warte auf Signale der Zylinder...")

# pause() hält das Programm endlos am Laufen, verbraucht aber fast 0% CPU.
# Es wartet einfach im Hintergrund auf die Events (when_pressed), die wir definiert haben.
pause()