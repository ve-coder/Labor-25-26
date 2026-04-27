# Labor-25-26

Rubik's Cube Solver Robot – Raspberry Pi Projekt.

## Auto-Update & Deployment System

Der Raspberry Pi kann den neuesten Code automatisch von GitHub laden und die Anwendung neu starten – ohne manuelle Eingriffe.

### Einmalige Einrichtung auf dem Raspberry Pi

```bash
# 1. Startskript und Systemd-Dateien einrichten
sudo cp /path/to/cloned/repo/start.sh /opt/cube-robot/start.sh
sudo chmod +x /opt/cube-robot/start.sh

# 2. Systemd-Dienste und Timer installieren
sudo cp cube-robot.service /etc/systemd/system/
sudo cp cube-robot-update.service /etc/systemd/system/
sudo cp cube-robot-update.timer /etc/systemd/system/

# 3. Dienste aktivieren und starten
sudo systemctl daemon-reload
sudo systemctl enable cube-robot.service
sudo systemctl enable cube-robot-update.timer
sudo systemctl start cube-robot.service
sudo systemctl start cube-robot-update.timer
```

### Status prüfen

```bash
# Status des Hauptdienstes
sudo systemctl status cube-robot.service

# Status des Update-Timers
sudo systemctl status cube-robot-update.timer

# Alle aktiven Timer anzeigen
sudo systemctl list-timers
```

### Manuelles Update auslösen

```bash
sudo systemctl start cube-robot-update.service
```

### Was passiert automatisch?

- **Beim Booten** startet der Service `cube-robot.service` automatisch. Das Startskript `start.sh` klont das Repository (falls noch nicht vorhanden) oder führt `git pull` aus, installiert alle Abhängigkeiten aus `requirements.txt` und startet `kombidings_app.py`.
- **Alle 6 Stunden** (5 Minuten nach dem Boot zum ersten Mal) prüft `cube-robot-update.timer` auf neue Code-Versionen, lädt diese herunter, aktualisiert die Abhängigkeiten und startet den Hauptdienst neu.
- **Bei Fehlern** startet der Dienst nach 10 Sekunden automatisch neu (`Restart=on-failure`).