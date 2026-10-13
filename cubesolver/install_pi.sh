#!/usr/bin/env bash
# Installation auf dem Raspberry Pi 4 (Raspberry Pi OS 64-Bit).
# Aufruf im Ordner cubesolver:  bash install_pi.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== Systempakete"
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential \
  python3-numpy python3-opencv python3-picamera2 i2c-tools

echo "== pigpio"
if ! sudo apt install -y pigpio python3-pigpio; then
  echo "pigpio nicht im Paketarchiv (neueres Raspberry Pi OS) – baue aus dem Quellcode"
  tmp=$(mktemp -d)
  git clone --depth 1 https://github.com/joan2937/pigpio "$tmp/pigpio"
  make -C "$tmp/pigpio" && sudo make -C "$tmp/pigpio" install
  sudo tee /etc/systemd/system/pigpiod.service >/dev/null <<'EOF'
[Unit]
Description=pigpio daemon
[Service]
Type=forking
ExecStart=/usr/local/bin/pigpiod
[Install]
WantedBy=multi-user.target
EOF
fi
sudo systemctl daemon-reload
sudo systemctl enable --now pigpiod

echo "== I2C einschalten (MCP23017)"
sudo raspi-config nonint do_i2c 0 || true

echo "== Python-Umgebung (nutzt numpy/opencv/picamera2/pigpio aus dem System)"
python3 -m venv --system-site-packages .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install "fastapi>=0.110" "uvicorn>=0.29" "kociemba==1.2.1" pytest httpx

echo "== Dienst einrichten"
sed "s#__DIR__#$(pwd)#g; s#__USER__#$(whoami)#g" deploy/cubesolver.service | sudo tee /etc/systemd/system/cubesolver.service >/dev/null
sudo systemctl daemon-reload
echo
echo "Fertig. Weiter:"
echo "  1) Boot-Sicherheit: Zeilen aus deploy/config.txt.snippet in /boot/firmware/config.txt eintragen, neu starten"
echo "  2) Test in der Simulation:  .venv/bin/python -m app.main   -> http://<pi>:8000"
echo "  3) Echte Hardware:          CUBESOLVER_MODE=pi .venv/bin/python -m app.main"
echo "  4) Automatisch starten:     sudo systemctl enable --now cubesolver"
echo "  5) I2C prüfen:              i2cdetect -y 1   (MCP23017 erscheint als 20)"
