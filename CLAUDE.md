# Labor-25-26 – Cube-Solver (HTL Jenbach)

Gerät, das einen 3×3-Würfel mit einer Raspberry-Pi-Kamera scannt und mit 6 Schrittmotoren + 4 Pneumatik-Zylindern löst. Du arbeitest per SSH direkt auf dem Raspberry Pi 4, an dem die Hardware hängt. Der Mensch steht am Gerät.

## Wo was liegt
- `cubesolver/` – **aktuelle Software** (FastAPI-Backend + Weboberfläche). Ausführlich: `cubesolver/README.md`.
- Alles andere im Hauptordner und `Papierkorb/` sind ältere Einzeltests. Nicht weiterentwickeln, nur als Referenz (z. B. alte Pinbelegungen).
- Branch: `cubesolver-web`. Nach jedem funktionierenden Schritt committen (kleine Commits, deutsche Commit-Texte).

| Datei | Zuständig für |
| --- | --- |
| `app/hardware.py` | Motoren (pigpio-Waves, gemeinsamer STEP), Relais, Reeds (MCP23017 über pigpio-I2C), Buzzer, Lichtschranke; `SimHardware` = Simulation |
| `app/vision.py` | Kamera (picamera2), Raster, Messung, Farbklassifizierung (`classify`) |
| `app/camera.py` | Kamera-Thread, Livebild, „9/9 stabil“ |
| `app/machine.py` | Ablauf/Blockprogramm, Sicherheitsregeln, Würfelmodell, Referenzdaten |
| `app/cube_model.py` | Würfelmodell (54 Sticker im Raum), Kociemba-String |
| `app/config.py` | alle Einstellungen inkl. Pins, `REED_MAP` |
| `programs/*.json` | `standard` (Scan + Lösen), `nur_scannen` (für Farb-Referenzdaten) |
| `tools/eval_colors.py` | Farberkennung gegen alle Referenzdaten prüfen |
| `tools/sim_color_stress.py` | Farberkennung mit 300 simulierten Würfeln prüfen |

## Hardware (Raspberry Pi 4) – Soll-Belegung laut Pinplan
- Motoren über eigene Platine: gemeinsamer STEP GPIO18; DIR1 = L (GPIO5), DIR2 = R (GPIO6), DIR 3–6 gemeinsam für U/D/F/B (GPIO13); EN1–EN6 = L,R,U,D,F,B (16,20,21,25,8,7), EN aktiv low. Motor-Nr.: L=M1, R=M2, U=M3, D=M4, F=M5, B=M6.
- Relais (aktiv low): U 17, D 27, L+R 22, F+B 23. Buzzer 24, Lichtschranke 4.
- Reed-Kontakte an MCP23017 (I2C-Bus 1, 0x20), Belegung `app/config.py → REED_MAP`.
- Kamera sitzt in D und schaut von unten. Im Bild muss oben die Gerätevorderseite (F) und links L sein.
- **Ob tatsächlich so verkabelt ist, ist noch nicht bestätigt** → beim ersten Mal nachfragen und Abweichungen in `data/settings.json` (über die Oberfläche/API) eintragen, nicht im Code hart ändern.

## Befehle (im Ordner `cubesolver`)
- Installation: `bash install_pi.sh` (einmalig; fragt sudo)
- Tests: `.venv/bin/python -m pytest -q tests`
- Server Simulation: `.venv/bin/python -m app.main` · echte Hardware: `CUBESOLVER_MODE=pi .venv/bin/python -m app.main` (oder Dienst: `sudo systemctl restart cubesolver`, Logs `journalctl -u cubesolver -f`)
- Oberfläche: `http://<pi-ip>:8000` (`hostname -I` für die IP)
- I2C prüfen: `i2cdetect -y 1` · pigpiod: `systemctl status pigpiod`

### API (für Tests aus der Shell, Server muss laufen)
```bash
curl -s localhost:8000/api/state | python3 -m json.tool        # Zustand, Reeds, Zylinder, Kamera 9/9
curl -s localhost:8000/api/camera.jpg -o /tmp/cam.jpg           # aktuelles Kamerabild mit Raster -> ansehen!
curl -s localhost:8000/api/cube/detail                          # 54 Felder: Messwert, erkannt, aktuell
curl -s localhost:8000/api/log
# BEWEGT HARDWARE – nur nach Freigabe durch den Menschen:
curl -s -X POST localhost:8000/api/manual/cylinder -H 'Content-Type: application/json' -d '{"cyl":"D","extended":true}'
curl -s -X POST localhost:8000/api/manual/jog -H 'Content-Type: application/json' -d '{"side":"U","steps":50}'
curl -s -X POST localhost:8000/api/run -H 'Content-Type: application/json' -d '{"name":"nur_scannen"}'
curl -s -X POST localhost:8000/api/stop
curl -s -X POST localhost:8000/api/home
# Einstellungen ändern (Werte siehe GET /api/settings):
curl -s -X PUT localhost:8000/api/settings -H 'Content-Type: application/json' -d '{"steps_per_90":800}'
```

## Sicherheitsregeln (immer einhalten)
- **Vor jedem Befehl, der Motoren, Relais oder Buzzer bewegt, kurz sagen was passiert und auf Freigabe warten** – auch bei Tests und auch per API/curl. Der Not-Aus muss in Reichweite sein.
- Bewegungen nur über die API bzw. den Handbetrieb, nicht mit eigenen GPIO-Skripten oder `pigs` an der Steuerung vorbei.
- Sicherheitsprüfungen (`interlocks`) nie im Code abschalten oder umgehen.
- Ob ein Greifer/Motor richtig fährt, kannst du nicht sehen → den Menschen fragen. Kamerabilder kannst du selbst ansehen (`/api/camera.jpg`, `data/scans/`, `data/dataset/`).
- Neue Logik zuerst in der Simulation + Tests prüfen, dann an der Hardware.
- Bei unerwartetem Verhalten: `POST /api/stop`, dann analysieren. Nichts „schnell nochmal probieren“.

## Erste Sitzung: Inbetriebnahme (der Reihe nach, jeweils bestätigen lassen)
1. Fragen: Ist nach dem Pinplan oben verkabelt? Gibt es den MCP23017 schon? Welche Treiber (A4988/DRV8825) und welches Microstepping? Relais aktiv low? Ventile monostabil (ohne Strom eingefahren)? Not-Aus vorhanden?
2. `install_pi.sh`, dann `/boot/firmware/config.txt` um `deploy/config.txt.snippet` ergänzen (Neustart nötig – vorher fragen).
3. Tests laufen lassen, Server in **Simulation** starten, Oberfläche im Browser vom Menschen prüfen lassen.
4. Server im Pi-Modus starten (ohne Druckluft, ohne Würfel): `/api/state` → Reeds plausibel? `i2cdetect` zeigt 20?
5. Mit Druckluft, ohne Würfel: jeden Zylinder einzeln aus/ein (Freigabe!) → Reed-Anzeige muss passen, sonst `REED_MAP` korrigieren.
6. Jeder Motor einzeln +90° (Freigabe!): von außen gesehen im Uhrzeigersinn? Sonst `invert_<Seite>` setzen. Steht der Greifer gerade? Sonst `steps_per_90` prüfen.
7. Kamera: Würfel einlegen, D aus, L+R aus, D ein. `camera.jpg` ansehen: Raster auf den 9 Feldern? (`grid_cx/grid_cy/grid_size`). Orientierung: oben F, links L (`cam_rotate`, `cam_mirror`).
8. Einzelschritt-Modus, dann `standard` mit niedriger Lösegeschwindigkeit.

## Farberkennung verbessern (Referenzdaten-Schleife)
Ziel: zuverlässige Erkennung unter dem echten Licht. Vorgehen:
1. Mensch legt einen verdrehten Würfel ein → Programm `nur_scannen` laufen lassen (Freigabe).
2. Mensch korrigiert in der Oberfläche falsch erkannte Felder (Klick auf den 3D-Würfel) und drückt **„Als Referenz speichern“** (oder `POST /api/cube/reference`). Ergebnis landet in `data/dataset/<zeit>/` (labels.json + 6 Bilder).
3. Wiederholen, bis ~10–20 Datensätze da sind (verschiedene Verdrehungen, ruhig auch anderes Licht).
4. Auswerten: `.venv/bin/python tools/eval_colors.py` (gespeicherte Messwerte) und `--resample` (Messwerte neu aus den Bildern, nötig wenn Raster/Messung in `vision.py` geändert wird).
5. Erst Fehlerbilder ansehen (Bilder im Datensatz-Ordner!), dann `vision.py` verbessern. **Eine Änderung gilt nur, wenn die Gesamtfehler sinken und kein Datensatz schlechter wird.** Danach auch `tools/sim_color_stress.py 300 14` und die Tests laufen lassen.
6. Häufige Ursachen: Licht (Reflexe, Tageslicht) – oft besser Licht ändern als Code; Raster sitzt schief; Messfeld zu groß (Rand/Schatten); Rot/Orange und Weiß/Gelb.
Aktueller Stand: optimale Zuordnung (Ungarische Methode, genau 9 je Farbe) gegen Gruppenmittelwerte im Lab-Farbraum; in der Simulation 0 Fehler bei 300 Würfeln (normale Streuung), 38 falsche Felder bei starker Streuung.

## Konventionen
- Oberfläche, Meldungen, Kommentare auf Deutsch.
- Drehrichtung: positive Schritte = im Uhrzeigersinn, von außen auf die Seite gesehen (wie Kociemba-Züge).
- Würfelkoordinaten: x = R, y = U, z = F (siehe `app/cube_model.py`).
- `data/` ist nicht im Git (Einstellungen, Statistik, Scans, Referenzdaten). Referenzdaten bei Bedarf separat sichern.
