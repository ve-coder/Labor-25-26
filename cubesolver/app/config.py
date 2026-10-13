"""Einstellungen: Standardwerte + Speicherung in data/settings.json.

SCHEMA beschreibt jede Einstellung für die Einstellungsseite
(Gruppe, Bezeichnung, Typ, Grenzen, Einheit, Hinweis).
"""
from __future__ import annotations

import copy
import json
import os
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CUBESOLVER_DATA", BASE_DIR / "data"))
SETTINGS_FILE = DATA_DIR / "settings.json"

# key, Gruppe, Bezeichnung, Typ, Standard, extra
SCHEMA = [
    # ---------------------------------------------------------------- Betrieb
    ("mode", "Betrieb", "Betriebsart", "choice", "sim",
     {"choices": {"sim": "Simulation (ohne Hardware)", "pi": "Raspberry Pi (echte Hardware)"},
      "hint": "Wirkt nach Neustart des Servers. Umgebungsvariable CUBESOLVER_MODE hat Vorrang.", "restart": True}),
    ("require_light_barrier", "Betrieb", "Start nur mit Würfel in der Lichtschranke", "bool", True, {}),
    ("buzzer_enabled", "Betrieb", "Buzzer", "bool", True, {}),
    ("sim_scramble_moves", "Betrieb", "Simulation: Verdrehzüge", "int", 25, {"min": 0, "max": 60}),
    ("sim_random_orientation", "Betrieb", "Simulation: Würfel zufällig eingelegt", "bool", True, {}),
    ("sim_time_factor", "Betrieb", "Simulation: Zeitfaktor", "float", 1.0,
     {"min": 0.01, "max": 5, "hint": "0,2 = fünfmal schneller als echt"}),

    # ---------------------------------------------------------------- Motoren
    ("steps_per_90", "Motoren", "Schritte pro 90°", "int", 50,
     {"min": 1, "max": 3200, "unit": "Schritte", "hint": "Vollschritt 1,8° = 50, 1/16-Microstepping = 800"}),
    ("speed_solve", "Motoren", "Geschwindigkeit beim Lösen", "int", 1200, {"min": 50, "max": 5000, "unit": "Schritte/s"}),
    ("speed_scan", "Motoren", "Geschwindigkeit beim Scannen (L+R)", "int", 600, {"min": 50, "max": 5000, "unit": "Schritte/s"}),
    ("speed_regrip", "Motoren", "Geschwindigkeit Umsetzen (D allein)", "int", 200, {"min": 20, "max": 3000, "unit": "Schritte/s"}),
    ("speed_manual", "Motoren", "Geschwindigkeit Handbetrieb", "int", 400, {"min": 20, "max": 3000, "unit": "Schritte/s"}),
    ("speed_start", "Motoren", "Startgeschwindigkeit", "int", 100, {"min": 10, "max": 2000, "unit": "Schritte/s"}),
    ("ramp_steps", "Motoren", "Rampe (Beschleunigungsweg)", "int", 10, {"min": 0, "max": 400, "unit": "Schritte"}),
    ("enable_settle_ms", "Motoren", "Wartezeit nach EN an", "int", 50, {"min": 0, "max": 1000, "unit": "ms"}),
    ("pause_between_moves_ms", "Motoren", "Pause zwischen Zügen", "int", 30, {"min": 0, "max": 2000, "unit": "ms"}),
    ("invert_L", "Motoren", "Richtung umkehren L (M1)", "bool", False, {"hint": "Im Handbetrieb prüfen: +90° muss von außen gesehen im Uhrzeigersinn drehen"}),
    ("invert_R", "Motoren", "Richtung umkehren R (M2)", "bool", False, {}),
    ("invert_U", "Motoren", "Richtung umkehren U (M3)", "bool", False, {}),
    ("invert_D", "Motoren", "Richtung umkehren D (M4)", "bool", False, {}),
    ("invert_F", "Motoren", "Richtung umkehren F (M5)", "bool", False, {}),
    ("invert_B", "Motoren", "Richtung umkehren B (M6)", "bool", False, {}),

    # ---------------------------------------------------------------- Pneumatik
    ("reed_timeout_s", "Pneumatik", "Reed-Timeout", "float", 2.0, {"min": 0.2, "max": 20, "unit": "s"}),
    ("cylinder_settle_ms", "Pneumatik", "Beruhigungszeit nach Endlage", "int", 100, {"min": 0, "max": 3000, "unit": "ms"}),
    ("sim_cylinder_time_ms", "Pneumatik", "Simulation: Fahrzeit Zylinder", "int", 300, {"min": 0, "max": 3000, "unit": "ms"}),

    # ---------------------------------------------------------------- Kamera
    ("cam_width", "Kamera", "Bildbreite", "int", 640, {"min": 160, "max": 2028, "unit": "px", "restart": True}),
    ("cam_height", "Kamera", "Bildhöhe", "int", 480, {"min": 120, "max": 1520, "unit": "px", "restart": True}),
    ("cam_fixed_exposure", "Kamera", "Belichtung und Weißabgleich festhalten", "bool", True,
     {"hint": "Nach 2 s Einschwingen werden Belichtung und Weißabgleich eingefroren", "restart": True}),
    ("cam_rotate", "Kamera", "Bild drehen", "choice", "0",
     {"choices": {"0": "0°", "90": "90°", "180": "180°", "270": "270°"},
      "hint": "So einstellen, dass die Unterseite wie in der D-Netzansicht liegt (Vorderseite oben)"}),
    ("cam_mirror", "Kamera", "Bild spiegeln", "bool", False, {"hint": "Kamera schaut von unten – je nach Einbau nötig"}),
    ("grid_cx", "Kamera", "Raster Mitte X", "float", 0.5, {"min": 0, "max": 1, "hint": "Anteil der Bildbreite"}),
    ("grid_cy", "Kamera", "Raster Mitte Y", "float", 0.5, {"min": 0, "max": 1}),
    ("grid_size", "Kamera", "Rastergröße", "float", 0.6, {"min": 0.1, "max": 1, "hint": "Anteil der Bildhöhe"}),
    ("sample_frac", "Kamera", "Messfeld pro Kästchen", "float", 0.4, {"min": 0.1, "max": 0.9}),
    ("stable_frames", "Kamera", "Stabile Bilder für 9/9", "int", 5, {"min": 1, "max": 30}),
    ("stable_threshold", "Kamera", "Stabilitäts-Schwelle", "float", 12.0, {"min": 1, "max": 80, "hint": "Max. Farbabweichung zwischen Bildern"}),
    ("min_brightness", "Kamera", "Mindesthelligkeit Sticker", "int", 35, {"min": 0, "max": 255}),
    ("scan_timeout_s", "Kamera", "Scan-Timeout", "float", 10.0, {"min": 1, "max": 120, "unit": "s"}),
    ("save_scan_images", "Kamera", "Scanbilder speichern (data/scans)", "bool", True, {}),

    # ---------------------------------------------------------------- Pins
    ("pin_step", "Pins (BCM)", "STEP alle Motoren", "int", 18, {"restart": True}),
    ("pin_dir_L", "Pins (BCM)", "Dir 1 (M1 = L)", "int", 5, {"restart": True}),
    ("pin_dir_R", "Pins (BCM)", "Dir 2 (M2 = R)", "int", 6, {"restart": True}),
    ("pin_dir_shared", "Pins (BCM)", "Dir (3–6) (U, D, F, B)", "int", 13, {"restart": True}),
    ("pin_en_L", "Pins (BCM)", "EN1 (L)", "int", 16, {"restart": True}),
    ("pin_en_R", "Pins (BCM)", "EN2 (R)", "int", 20, {"restart": True}),
    ("pin_en_U", "Pins (BCM)", "EN3 (U)", "int", 21, {"restart": True}),
    ("pin_en_D", "Pins (BCM)", "EN4 (D)", "int", 25, {"restart": True}),
    ("pin_en_F", "Pins (BCM)", "EN5 (F)", "int", 8, {"restart": True}),
    ("pin_en_B", "Pins (BCM)", "EN6 (B)", "int", 7, {"restart": True}),
    ("pin_relay_U", "Pins (BCM)", "Relais 1 – U", "int", 17, {"restart": True}),
    ("pin_relay_D", "Pins (BCM)", "Relais 2 – D", "int", 27, {"restart": True}),
    ("pin_relay_LR", "Pins (BCM)", "Relais 3 – L+R", "int", 22, {"restart": True}),
    ("pin_relay_FB", "Pins (BCM)", "Relais 4 – F+B", "int", 23, {"restart": True}),
    ("pin_buzzer", "Pins (BCM)", "Buzzer", "int", 24, {"restart": True}),
    ("pin_light_barrier", "Pins (BCM)", "Lichtschranke", "int", 4, {"restart": True}),
    ("relay_active_low", "Pins (BCM)", "Relais schalten bei low", "bool", True, {"restart": True}),
    ("en_active_low", "Pins (BCM)", "Motor-EN aktiv bei low", "bool", True, {"restart": True}),
    ("light_barrier_active_low", "Pins (BCM)", "Lichtschranke: Würfel = low", "bool", True, {"restart": True}),
    ("mcp_address", "Pins (BCM)", "MCP23017 I2C-Adresse (dezimal, 32 = 0x20)", "int", 32, {"restart": True}),
    ("mcp_bus", "Pins (BCM)", "I2C-Bus", "int", 1, {"restart": True}),
    ("pigpio_host", "Pins (BCM)", "pigpiod Host", "str", "localhost",
     {"hint": "Im Docker-Container die Adresse des Pi-Hosts", "restart": True}),
]

# Belegung der Reed-Kontakte am MCP23017: (Port, Bit) für (eingefahren, ausgefahren)
REED_MAP = {
    "U": (("A", 0), ("A", 1)),
    "D": (("A", 2), ("A", 3)),
    "L": (("A", 4), ("A", 5)),
    "R": (("B", 0), ("B", 1)),
    "F": (("B", 2), ("B", 3)),
    "B": (("B", 4), ("B", 5)),
}

DEFAULTS = {k: d for k, _g, _l, _t, d, _x in SCHEMA}
TYPES = {k: t for k, _g, _l, t, _d, _x in SCHEMA}


class Settings:
    def __init__(self, path: Path = SETTINGS_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.values = copy.deepcopy(DEFAULTS)
        if path.exists():
            try:
                stored = json.loads(path.read_text())
                for k, v in stored.items():
                    if k in DEFAULTS:
                        self.values[k] = self._coerce(k, v)
            except Exception as e:  # kaputte Datei nicht den Start verhindern lassen
                print("Einstellungen konnten nicht gelesen werden:", e)
        env_mode = os.environ.get("CUBESOLVER_MODE")
        if env_mode in ("sim", "pi"):
            self.values["mode"] = env_mode

    def _coerce(self, key, value):
        t = TYPES[key]
        meta = next(x for k, *_r, x in SCHEMA if k == key)
        if t == "bool":
            if isinstance(value, str):
                return value.lower() in ("1", "true", "ja", "on")
            return bool(value)
        if t == "int":
            v = int(float(value))
        elif t == "float":
            v = float(value)
        elif t == "choice":
            v = str(value)
            if v not in meta["choices"]:
                raise ValueError(f"{key}: ungültige Auswahl {v}")
            return v
        else:
            return str(value)
        if "min" in meta and v < meta["min"]:
            raise ValueError(f"{key}: Wert {v} kleiner als {meta['min']}")
        if "max" in meta and v > meta["max"]:
            raise ValueError(f"{key}: Wert {v} größer als {meta['max']}")
        return v

    def __getitem__(self, key):
        return self.values[key]

    def get(self, key, default=None):
        return self.values.get(key, default)

    def update(self, changes: dict):
        with self._lock:
            new = dict(self.values)
            for k, v in changes.items():
                if k not in DEFAULTS:
                    raise KeyError(f"Unbekannte Einstellung {k}")
                new[k] = self._coerce(k, v)
            self.values = new
            self.save()
        return self.values

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.values, indent=2, ensure_ascii=False))
        tmp.replace(self.path)

    def schema(self):
        out = []
        for k, g, label, t, d, extra in SCHEMA:
            item = {"key": k, "group": g, "label": label, "type": t, "default": d, "value": self.values[k]}
            item.update(extra)
            out.append(item)
        return out
