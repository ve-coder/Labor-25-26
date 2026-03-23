from gpiozero import OutputDevice
import sys

# Konfiguration der Pins
# IN1 -> GPIO17, IN2 -> GPIO27, IN3 -> GPIO22, IN4 -> GPIO23
# Wir mappen die Tasten "1", "2", "3", "4" auf die entsprechenden GPIOs
RELAY_MAP = {
    "1": 17,
    "2": 27,
    "3": 22,
    "4": 23
}

# Dictionary zum Speichern der aktiven Relais-Objekte
relays = {}

# Initialisierung
try:
    print("Initialisiere Relais... (Active Low)")
    for key, pin in RELAY_MAP.items():
        # active_high=False: .on() schaltet Relais an (GND), .off() schaltet aus (5V)
        # initial_value=False: Startet im Zustand AUS
        relays[key] = OutputDevice(pin, active_high=False, initial_value=False)

    print("--------------------------------------------------")
    print("STEUERUNG:")
    print("Drücke 1, 2, 3 oder 4 und dann ENTER, um das Relais umzuschalten.")
    print("Drücke 'q' oder STRG+C, um zu beenden.")
    print("--------------------------------------------------")

    while True:
        # Benutzereingabe abfragen
        auswahl = input("Welches Relais schalten? (1-4): ")

        if auswahl in relays:
            relay = relays[auswahl]
            relay.toggle() # Schaltet an wenn aus, und aus wenn an

            # Statusanzeige
            status = "AN" if relay.value == 1 else "AUS"
            print(f"--> Relais {auswahl} (GPIO {RELAY_MAP[auswahl]}) ist jetzt {status}")

        elif auswahl.lower() == 'q':
            print("Beende Programm...")
            break
        else:
            print("Ungültige Eingabe. Bitte 1, 2, 3 oder 4 eingeben.")


except KeyboardInterrupt:
    print("\nProgramm durch Benutzer abgebrochen (STRG+C).")

finally:
    # Dieser Block wird IMMER ausgeführt, wenn das Programm endet
    # (egal ob durch Fehler, 'q' oder STRG+C)
    print("Räume auf... Schalte alle Relais in den Ursprungszustand (AUS).")
    if relays:
        for r in relays.values():
            r.off()
            r.close() # Gibt den GPIO-Pin wieder frei
    print("Fertig.")