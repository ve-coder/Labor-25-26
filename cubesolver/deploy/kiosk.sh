#!/usr/bin/env bash
# Oberfläche im Vollbild auf dem Pi-Bildschirm öffnen (z. B. im Autostart des Desktops)
until curl -s -o /dev/null http://localhost:8000/api/state; do sleep 1; done
exec chromium --kiosk --noerrdialogs --disable-infobars --password-store=basic http://localhost:8000/ 2>/dev/null \
  || exec chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8000/
