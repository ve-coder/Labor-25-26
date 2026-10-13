# Labor-25-26 – Cube-Solver (HTL Jenbach)

Gerät, das einen 3×3-Würfel mit einer Raspberry-Pi-Kamera scannt und mit 6 Schrittmotoren + 4 Pneumatik-Zylindern löst.

## Wo was liegt
- `cubesolver/` – **aktuelle Software** (FastAPI-Backend + Weboberfläche). Details: `cubesolver/README.md`.
- Alles andere im Repo-Hauptordner und `Papierkorb/` sind ältere Einzeltests (Ursina, einzelne Motor-/Relais-Skripte). Nicht mehr weiterentwickeln, nur als Referenz.

## Hardware (Raspberry Pi 4)
- Motoren über eigene Platine: gemeinsamer STEP (GPIO18), DIR1 = L (GPIO5), DIR2 = R (GPIO6), DIR 3–6 gemeinsam für U/D/F/B (GPIO13), EN1–EN6 = L,R,U,D,F,B (16,20,21,25,8,7), EN aktiv low.
- Relais (aktiv low): U 17, D 27, L+R 22, F+B 23. Buzzer 24, Lichtschranke 4.
- Reed-Kontakte an MCP23017 (I2C 0x20), Belegung in `cubesolver/app/config.py → REED_MAP`.
- Kamera sitzt in D und schaut von unten auf den Würfel.
- Ansteuerung über den pigpio-Daemon (`sudo systemctl status pigpiod`).

## Befehle (im Ordner `cubesolver`)
- Tests: `.venv/bin/python -m pytest -q tests`
- Simulation: `.venv/bin/python -m app.main` → http://<pi>:8000
- Echte Hardware: `CUBESOLVER_MODE=pi .venv/bin/python -m app.main` (oder Dienst `cubesolver`)
- Logs des Dienstes: `journalctl -u cubesolver -f`
- I2C prüfen: `i2cdetect -y 1`

## Regeln für Arbeit an der echten Hardware
- **Vor jedem Befehl, der Motoren, Relais oder den Buzzer bewegt, fragen** – auch bei Tests. Es muss jemand am Gerät stehen, der Not-Aus ist in Reichweite.
- Bewegungen nur über die API/den Handbetrieb (`/api/manual/...`), nicht mit eigenen GPIO-Skripten an der Steuerung vorbei.
- Sicherheitsprüfungen (`interlocks`) nie im Code abschalten.
- Ob ein Greifer richtig fährt, kann Claude nicht sehen → beim Menschen nachfragen. Die Kamera kann Claude selbst prüfen: `curl -s localhost:8000/api/camera.jpg -o /tmp/cam.jpg` und das Bild ansehen. Gespeicherte Scans liegen in `data/scans/`.
- Neue Logik zuerst in der Simulation + Tests prüfen, dann an der Hardware.

## Konventionen
- Oberfläche und Meldungen auf Deutsch.
- Drehrichtung: positive Schritte = im Uhrzeigersinn, von außen auf die Seite gesehen (wie Kociemba-Züge).
- Würfelkoordinaten: x = R, y = U, z = F (siehe `app/cube_model.py`).
