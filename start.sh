#!/bin/bash
set -euo pipefail

APP_DIR="/opt/cube-robot"
REPO_URL="https://github.com/ve-coder/Labor-25-26.git"
MAIN_SCRIPT="kombidings_app.py"

# Repo clonen oder updaten
if [ ! -d "$APP_DIR/.git" ]; then
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
else
    cd "$APP_DIR"
    git pull --ff-only origin main
fi

# Dependencies installieren / upgraden
if [ -f "$APP_DIR/requirements.txt" ]; then
    pip install --user -r "$APP_DIR/requirements.txt" --upgrade
fi

# Hauptanwendung starten
cd "$APP_DIR"
python3 "$MAIN_SCRIPT"
