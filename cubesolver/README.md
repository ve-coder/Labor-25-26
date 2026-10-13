# Cube-Solver – Steuerung und Weboberfläche

Scannt einen 3×3-Würfel mit der Kamera in D, berechnet die Lösung (Kociemba) und löst ihn mit 6 Schrittmotoren und 4 Pneumatik-Zylindern. Bedient wird alles über eine Webseite: am Pi-Bildschirm im Vollbild oder von jedem Laptop oder Handy im selben Netz.

- **3D-Würfel:** zeigt live, was die Steuerung weiß. Mit der Maus drehen, mit dem Mausrad zoomen, ein Feld anklicken, um eine falsch erkannte Farbe zu korrigieren.
- **Ablauf als Blockprogramm (Blockly):** Zylinder, Motoren, Scan und Lösen per Drag & Drop. Programme speichern und laden. Der gerade laufende Block leuchtet auf.
- **Steuerung:** Start, Stopp, Grundstellung, Einzelschritt und Lösegeschwindigkeit. Der Regler wirkt auch während des Lösens.
- **Handbetrieb:** jeden Zylinder schalten, jeden Motor um ±90°/180° oder schrittweise drehen, Reed-Anzeige, Buzzer und Lichtschranke.
- **Statistik:** Durchläufe, Erfolgsquote, Scan-, Löse- und Gesamtzeit, Züge und häufigste Fehler.
- **Einstellungen:** Geschwindigkeiten, Rampe, Drehrichtung pro Motor, Kamera (Drehen, Spiegeln, Raster), Timeouts, Pins.
- **Simulation:** Der ganze Ablauf läuft auch ohne Hardware, mit einem simulierten verdrehten Würfel und künstlichem Kamerabild.

## Schnellstart am Laptop (Simulation)

```bash
cd cubesolver
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m app.main            # -> http://localhost:8000
python -m pytest -q tests     # Tests
```

Unter *Einstellungen → Betrieb → Simulation: Zeitfaktor* lässt sich die Simulation beschleunigen (z. B. 0,2).

## Installation am Raspberry Pi 4

```bash
git clone https://github.com/ve-coder/Labor-25-26 && cd Labor-25-26/cubesolver
bash install_pi.sh
```

Das Skript installiert pigpio, picamera2, OpenCV, schaltet I2C ein, legt `.venv` an und richtet den Dienst `cubesolver` ein. Danach:

1. **Boot-Sicherheit:** Den Inhalt von `deploy/config.txt.snippet` in `/boot/firmware/config.txt` eintragen und neu starten. Sonst schalten Relais und Treiber beim Booten kurz ein.
2. **Ohne Hardware testen:** `.venv/bin/python -m app.main`
3. **Mit Hardware:** `CUBESOLVER_MODE=pi .venv/bin/python -m app.main`
4. **Automatisch beim Booten:** `sudo systemctl enable --now cubesolver`. Für den Bildschirm `deploy/kiosk.sh` in den Desktop-Autostart eintragen.

Ist pigpiod oder die Kamera nicht erreichbar, startet die Oberfläche trotzdem und zeigt oben einen roten Hinweis.

## Erste Inbetriebnahme (Reihenfolge einhalten, Not-Aus in Reichweite)

1. `i2cdetect -y 1` zeigt `20` → der MCP23017 ist da.
2. **Handbetrieb, ohne Würfel, Druckluft an:** Jeden Zylinder aus- und einfahren. Die Reed-Lämpchen müssen passend umschalten. Wenn nicht, die Belegung in `app/config.py → REED_MAP` prüfen.
3. **Drehrichtung:** Jeden Motor mit +90° drehen. Von außen auf die Seite gesehen muss er im **Uhrzeigersinn** drehen. Wenn nicht: *Einstellungen → Motoren → Richtung umkehren*.
4. **90° prüfen:** Wenn ein Greifer nach +90° nicht gerade steht, *Schritte pro 90°* bzw. das Microstepping prüfen. Mit −1/+1 Schritt nachjustieren (nur bei eingefahrenem Greifer).
5. **Kamera:** Einen Würfel einlegen, D ausfahren, L+R ausfahren, D einfahren. Im Kamerabild müssen alle 9 Felder im Raster liegen (*Raster Mitte X/Y, Rastergröße*). Dann die **Ausrichtung** prüfen: Im Bild muss oben die Vorderseite des Geräts (F) liegen und links die Seite L. Die Buchstaben F und L am Raster zeigen das an. Halte zum Prüfen einen Finger an die Vorderseite des Würfels. Passt es nicht, *Bild drehen/spiegeln* ändern. Gegenprobe: Einen gelösten Würfel mit genau einem Zug verdrehen und das Programm laufen lassen. Die Lösung muss aus genau einem Zug bestehen, und der Würfel muss danach gelöst sein. Kommt „keine Lösung“ oder ist der Würfel danach nicht gelöst, stimmt die Ausrichtung nicht. Eine falsche Spiegelung erkennt nur diese Probe, nicht die Prüfung vor dem Lösen.
6. Einzelschritt-Modus an und das Standardprogramm Block für Block durchgehen.
7. Dann im normalen Betrieb, zuerst mit niedriger Lösegeschwindigkeit.

## Wie es funktioniert

```
Browser ──HTTP/WebSocket──► app/main.py (FastAPI)
                               │
                               ▼
                         app/machine.py   Ablauf, Blockprogramm, Sicherheitsregeln, Würfelmodell
                          │        │
              app/hardware.py    app/camera.py + app/vision.py
              Pi (pigpio) oder   Kamera (picamera2 oder simuliert),
              Simulation         Raster, Farberkennung
```

- **Würfelmodell (`cube_model.py`):** 54 Sticker mit Position und Richtung im Raum. Jede Drehung des ganzen Würfels (L+R beim Scannen, D beim Umsetzen) dreht auch das Modell. Deshalb weiß der Scan-Block immer, welche Seite gerade unten liegt, und der Würfel darf beliebig eingelegt werden. Die Farbe der Mittelsteine bestimmt die Seiten.
- **Farberkennung (`vision.py`):** Pro Kästchen wird der Median eines inneren Messfelds gebildet. „9/9“ heißt: alle Felder hell genug und über N Bilder stabil. Nach 6 Seiten werden alle 54 Werte den 6 Mittelsteinen zugeordnet (Farbraum Lab, genau 9 je Farbe). Das ist eine Selbstkalibrierung unter dem aktuellen Licht.
- **Sicherheitsregeln (`machine.py`):**
  - L+R drehen nur, wenn U, D, F und B eingefahren sind.
  - Kein Einfahren, das den Würfel fallen ließe.
  - Nicht drehen, solange ein Zylinder fährt.
  - Wenn nur der gegenüberliegende Greifer hält, ist Drehen gesperrt.
  - Zum Lösen müssen alle Greifer ausgefahren sein.
  - Bei Stopp oder Fehler werden die Motoren stromlos, die Zylinder bleiben stehen.
- **Motoren (`hardware.py`):** Der gemeinsame STEP läuft über pigpio-Waves mit Rampe. Gewählt wird der Motor über EN. L und R haben eigene DIR-Pins, U, D, F und B teilen sich einen. Deshalb dreht außer L+R nie ein Paar gleichzeitig.
- **Blockprogramm:** wird als JSON gespeichert (`programs/standard.json`, eigene in `data/programs/`). Das Format ist oben in `app/machine.py` beschrieben.

## Ordner

| Pfad | Inhalt |
| --- | --- |
| `app/` | Backend (Python) |
| `static/` | Oberfläche (HTML/JS, three.js und Blockly liegen lokal in `static/vendor/`) |
| `programs/standard.json` | Standardablauf laut Pinplan |
| `data/` | Einstellungen, eigene Programme, Statistik, Scanbilder (nicht im Git) |
| `deploy/` | systemd-Dienst, Boot-Konfiguration, Kiosk-Start |
| `tests/` | Tests: Würfelmodell, kompletter Simulationslauf, Sicherheitsregeln, API |

## Docker (später)

pigpio wird über den Daemon per Netzwerk angesprochen (Einstellung *pigpiod Host*). Ein Container braucht für Motoren, Relais, Reeds (I2C über pigpio) und Buzzer deshalb keinen Gerätezugriff. Offen ist nur noch die Kamera (libcamera im Container).

## Lizenzen

three.js: MIT (`static/vendor/three.LICENSE`). Blockly: Apache 2.0.
