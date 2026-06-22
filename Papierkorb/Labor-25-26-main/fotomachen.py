from picamera2 import Picamera2, Preview
from datetime import datetime
from pathlib import Path
import time

def main():
    # Foto im selben Ordner wie das Skript speichern
    script_dir = Path(__file__).resolve().parent
    filename = f"test.jpg"
    filepath = script_dir / filename

    picam2 = Picamera2()

    # 1) Konfiguration für Live-Vorschau
    preview_config = picam2.create_preview_configuration()
    # 2) Konfiguration für das hochauflösende Foto
    still_config = picam2.create_still_configuration()

    # Zuerst Preview-Konfiguration aktivieren
    picam2.configure(preview_config)

    # Vorschau-Fenster starten:
    # - QT  -> Fenster in der Desktop-Oberfläche
    # - QTGL -> schneller, braucht aber funktionierende 3D-Beschleunigung
    picam2.start_preview(Preview.QT)

    print("Starte Kamera...")
    picam2.start()

    # kurz warten, damit Belichtung etc. passen
    time.sleep(1)

    # Countdown
    for i in range(3, 0, -1):
        print(i)
        time.sleep(1)

    print(f"Mache Foto: {filepath}")

    # Hier wird kurz auf Still-Konfiguration gewechselt, Foto aufgenommen,
    # danach automatisch wieder zurück auf Preview-Konfiguration
    picam2.switch_mode_and_capture_file(still_config, str(filepath))

    # Vorschau stoppen
    picam2.stop_preview()
    picam2.stop()

    print("Fertig! Bild gespeichert.")

if __name__ == "__main__":
    main()                          