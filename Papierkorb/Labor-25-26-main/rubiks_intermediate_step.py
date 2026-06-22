#!/usr/bin/env python3
import json
import time
from pathlib import Path

import cv2
import numpy as np

try:
    from picamera2 import Picamera2
except Exception:
    Picamera2 = None

try:
    import kociemba
except Exception:
    kociemba = None

try:
    import pigpio
except Exception:
    pigpio = None

# ============================================================
# Konfiguration
# ============================================================
CALIB_FILE = Path("cube_calib.json")
WINDOW_NAME = "Rubik Scan"

GRID_TOTAL = 660
GRID_N = 3
ROI_MARGIN_FRAC = 0.25

CALIB_ORDER = [
    ("W", "WEISS"),
    ("Y", "GELB"),
    ("R", "ROT"),
    ("O", "ORANGE"),
    ("B", "BLAU"),
    ("G", "GRUEN"),
]

# Reihenfolge zwingend fuer kociemba
SCAN_ORDER = [
    ("U", "OBEN (U)"),
    ("R", "RECHTS (R)"),
    ("F", "VORNE (F)"),
    ("D", "UNTEN (D)"),
    ("L", "LINKS (L)"),
    ("B", "HINTEN (B)"),
]

DRAW_BGR = {
    "W": (255, 255, 255),
    "Y": (0, 255, 255),
    "R": (0, 0, 255),
    "O": (0, 128, 255),
    "G": (0, 255, 0),
    "B": (255, 0, 0),
    "?": (200, 200, 200),
}

# ---------------- Motor-Setup (aus 6motoren.py) ----------------
MOTORS = {
    1: (17, 27, 23),
    2: (6, 5, 22),
    3: (8, 25, 24),
    4: (13, 14, 15),
    5: (16, 18, 9),
    6: (10, 11, 12),
}

STEPS_PER_90 = 50
F_START = 100
F_RUN = 1200
RAMP_STEPS = 10
EN_ENABLE = 0
EN_DISABLE = 1
DIR_SETTLE_S = 0.05

# Gewuenschtes Mapping vom User
# Motor 1: V/V', Motor 2: B/B', Motor 3: L/L', Motor 4: R/R', Motor 5: U/U', Motor 6: D/D'
MOVE_TO_MOTOR = {
    "V": 1,
    "B": 2,
    "L": 3,
    "R": 4,
    "U": 5,
    "D": 6,
}

# Solver liefert F; Hardware soll V nutzen
SOLVER_TO_HW_FACE = {
    "F": "V",
    "B": "B",
    "L": "L",
    "R": "R",
    "U": "U",
    "D": "D",
}


# ============================================================
# Kamera / Farberkennung
# ============================================================
def grid_rect(frame_w, frame_h):
    x0 = (frame_w - GRID_TOTAL) // 2
    y0 = (frame_h - GRID_TOTAL) // 2
    return x0, y0, x0 + GRID_TOTAL, y0 + GRID_TOTAL


def cell_bounds(x0, y0, r, c):
    step = GRID_TOTAL / GRID_N
    cx0 = int(x0 + c * step)
    cy0 = int(y0 + r * step)
    cx1 = int(x0 + (c + 1) * step)
    cy1 = int(y0 + (r + 1) * step)
    return cx0, cy0, cx1, cy1


def cell_roi(frame_rgb, x0, y0, r, c):
    cx0, cy0, cx1, cy1 = cell_bounds(x0, y0, r, c)
    w = cx1 - cx0
    h = cy1 - cy0
    mx = int(w * ROI_MARGIN_FRAC)
    my = int(h * ROI_MARGIN_FRAC)
    rx0, ry0 = cx0 + mx, cy0 + my
    rx1, ry1 = cx1 - mx, cy1 - my
    return frame_rgb[ry0:ry1, rx0:rx1]


def mean_hsv(roi_rgb):
    if roi_rgb is None or roi_rgb.size == 0:
        return None
    hsv = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2HSV)
    h, s, v, _ = cv2.mean(hsv)
    return float(h), float(s), float(v)


def draw_grid(frame_bgr):
    h, w = frame_bgr.shape[:2]
    x0, y0, x1, y1 = grid_rect(w, h)
    cv2.rectangle(frame_bgr, (x0, y0), (x1, y1), (255, 255, 255), 2)
    for i in range(1, GRID_N):
        step = GRID_TOTAL / GRID_N
        vx = int(x0 + i * step)
        vy = int(y0 + i * step)
        cv2.line(frame_bgr, (vx, y0), (vx, y1), (255, 255, 255), 2)
        cv2.line(frame_bgr, (x0, vy), (x1, vy), (255, 255, 255), 2)


def put_info(frame_bgr, lines):
    y = 30
    for text in lines:
        cv2.putText(frame_bgr, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA)
        y += 30


def draw_live_labels(frame_bgr, live_grid):
    if live_grid is None:
        return
    h, w = frame_bgr.shape[:2]
    gx0, gy0, _, _ = grid_rect(w, h)

    for r in range(3):
        for c in range(3):
            cx0, cy0, cx1, cy1 = cell_bounds(gx0, gy0, r, c)
            ch = live_grid[r][c]
            bgr = DRAW_BGR.get(ch, DRAW_BGR["?"])
            (tw, th), _ = cv2.getTextSize(ch, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)
            tx = cx0 + (cx1 - cx0 - tw) // 2
            ty = cy0 + (cy1 - cy0 + th) // 2
            cv2.putText(frame_bgr, ch, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 6, cv2.LINE_AA)
            cv2.putText(frame_bgr, ch, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 1.2, bgr, 3, cv2.LINE_AA)


def load_calibration(path: Path):
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None

    calib = {}
    for label in ["W", "Y", "R", "O", "G", "B"]:
        val = raw.get(label)
        if val is None:
            return None

        if isinstance(val, dict):
            h = float(val["h"])
            s = float(val["s"])
            v = float(val["v"])
        elif isinstance(val, list) and len(val) == 3:
            h, s, v = float(val[0]), float(val[1]), float(val[2])
        else:
            return None

        calib[label] = (h, s, v)

    return calib


def save_calibration(path: Path, calib):
    out = {
        label: [vals[0], vals[1], vals[2]]
        for label, vals in calib.items()
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


def classify_hsv(h, s, v, calib):
    best_label = "?"
    best_dist = 1e18

    for label, (ch, cs, cv) in calib.items():
        dh = abs(h - ch)
        if dh > 90:
            dh = 180 - dh
        ds = abs(s - cs)
        dv = abs(v - cv)
        d = (dh * dh + ds * ds + dv * dv) ** 0.5
        if d < best_dist:
            best_dist = d
            best_label = label

    return best_label


def scan_face_3x3(frame_rgb, calib):
    h, w = frame_rgb.shape[:2]
    gx0, gy0, _, _ = grid_rect(w, h)
    out = []

    for r in range(3):
        row = []
        for c in range(3):
            roi = cell_roi(frame_rgb, gx0, gy0, r, c)
            m = mean_hsv(roi)
            if m is None:
                row.append("?")
                continue
            hh, ss, vv = m
            row.append(classify_hsv(hh, ss, vv, calib))
        out.append(row)

    return out


def calibrate_once_if_needed(picam2, calib_path: Path):
    calib = load_calibration(calib_path)
    if calib is not None:
        print(f"Kalibrierung geladen aus {calib_path}")
        return calib

    print("Keine gueltige Kalibrierung gefunden -> starte Einmal-Kalibrierung.")
    print("Fuer jede Farbe: passende Seite voll ins 3x3-Raster halten, dann SPACE.")

    calib = {}
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

    for idx, (label, name) in enumerate(CALIB_ORDER, 1):
        while True:
            frame_bgr = picam2.capture_array()
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            draw_grid(frame_bgr)
            preview = scan_face_3x3(frame_rgb, calib) if len(calib) > 0 else None
            draw_live_labels(frame_bgr, preview)
            put_info(frame_bgr, [
                f"KALIB {idx}/6: {name}",
                "SPACE=Foto, ESC=Abbruch"
            ])
            cv2.imshow(WINDOW_NAME, frame_bgr)
            key = cv2.waitKey(1) & 0xFF

            if key == 27:
                raise RuntimeError("Kalibrierung abgebrochen.")

            if key == 32:
                h, w = frame_rgb.shape[:2]
                gx0, gy0, _, _ = grid_rect(w, h)
                roi = cell_roi(frame_rgb, gx0, gy0, 1, 1)  # mittlere Zelle
                m = mean_hsv(roi)
                if m is None:
                    print("ROI leer, bitte nochmal.")
                    continue
                calib[label] = m
                print(f"Kalib {idx}/6 {name}: H={m[0]:.1f} S={m[1]:.1f} V={m[2]:.1f}")
                break

    save_calibration(calib_path, calib)
    print(f"Kalibrierung gespeichert in {calib_path}")
    return calib


def scan_all_faces(picam2, calib):
    scanned = {}
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

    for idx, (face_letter, face_name) in enumerate(SCAN_ORDER, 1):
        while True:
            frame_bgr = picam2.capture_array()
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            live = scan_face_3x3(frame_rgb, calib)
            draw_grid(frame_bgr)
            draw_live_labels(frame_bgr, live)
            put_info(frame_bgr, [
                f"SCAN {idx}/6: {face_name}",
                "Seite sauber ausrichten.",
                "SPACE=Uebernehmen, ESC=Abbruch"
            ])
            cv2.imshow(WINDOW_NAME, frame_bgr)
            key = cv2.waitKey(1) & 0xFF

            if key == 27:
                raise RuntimeError("Scan abgebrochen.")

            if key == 32:
                scanned[face_letter] = live
                print(f"Face {face_letter} aufgenommen:")
                for row in live:
                    print(" ".join(row))
                print("")
                break

    return scanned


# ============================================================
# Solver / Zugfolge
# ============================================================
def face_color_mapping_from_centers(scanned_faces):
    # Farbe -> Face-Letter (U,R,F,D,L,B)
    color_to_face = {}
    for face_letter, grid in scanned_faces.items():
        center_color = grid[1][1]
        color_to_face[center_color] = face_letter
    return color_to_face


def build_kociemba_string(scanned_faces):
    color_to_face = face_color_mapping_from_centers(scanned_faces)

    missing = {"W", "Y", "R", "O", "G", "B"} - set(color_to_face.keys())
    if missing:
        raise ValueError(f"Center-Farben unvollstaendig/dupliziert. Fehlend: {missing}")

    chars = []
    for face_letter, _ in SCAN_ORDER:  # URFDLB
        grid = scanned_faces[face_letter]
        for r in range(3):
            for c in range(3):
                cube_color = grid[r][c]
                mapped_face = color_to_face.get(cube_color)
                if mapped_face is None:
                    raise ValueError(f"Unbekannte Farbe im Scan: {cube_color}")
                chars.append(mapped_face)

    cube_string = "".join(chars)
    return cube_string


def expand_moves(moves):
    expanded = []
    for mv in moves:
        if mv.endswith("2"):
            single = mv[:-1]
            expanded.append(single)
            expanded.append(single)
        else:
            expanded.append(mv)
    return expanded


def solver_to_hardware_moves(solver_moves):
    hw_moves = []
    for mv in solver_moves:
        face = mv[0]  # U,R,F,D,L,B
        suffix = mv[1:] if len(mv) > 1 else ""

        hw_face = SOLVER_TO_HW_FACE[face]  # F -> V
        hw_moves.append(hw_face + suffix)

    return hw_moves


# ============================================================
# Motorsteuerung
# ============================================================
class MotorController:
    def __init__(self):
        self.pi = None
        self.enabled = False

        if pigpio is None:
            print("WARNUNG: pigpio Modul fehlt -> Trockenlauf (nur Prints, keine Motoren).")
            return

        pi = pigpio.pi()
        if not pi.connected:
            print("WARNUNG: pigpiod nicht verbunden -> Trockenlauf (nur Prints, keine Motoren).")
            return

        self.pi = pi
        for _, (step_pin, dir_pin, en_pin) in MOTORS.items():
            self.pi.set_mode(step_pin, pigpio.OUTPUT)
            self.pi.set_mode(dir_pin, pigpio.OUTPUT)
            self.pi.set_mode(en_pin, pigpio.OUTPUT)
            self.pi.write(step_pin, 0)
            self.pi.write(en_pin, EN_DISABLE)

        self.pi.wave_clear()
        self.enabled = True
        print("Motorsteuerung aktiv (pigpio verbunden).")

    def close(self):
        if self.pi is None:
            return

        for _, (_, _, en_pin) in MOTORS.items():
            self.pi.write(en_pin, EN_DISABLE)

        self.pi.wave_clear()
        self.pi.stop()

    def _rotate_ramped(self, step_pin, dir_pin, en_pin, direction, steps):
        self.pi.write(en_pin, EN_ENABLE)
        self.pi.write(dir_pin, 1 if direction else 0)
        time.sleep(DIR_SETTLE_S)

        step_mask = 1 << step_pin
        pulses = []

        current_ramp = RAMP_STEPS
        if steps < (RAMP_STEPS * 2):
            current_ramp = max(1, steps // 2)

        for i in range(steps):
            if i < current_ramp:
                factor = i / current_ramp
                freq = F_START + (F_RUN - F_START) * factor
            elif i >= steps - current_ramp:
                reverse_i = steps - 1 - i
                factor = reverse_i / current_ramp
                freq = F_START + (F_RUN - F_START) * factor
            else:
                freq = F_RUN

            period_us = int(1_000_000 / max(1, freq))
            hi = 5
            lo = max(5, period_us - hi)
            pulses.append(pigpio.pulse(step_mask, 0, hi))
            pulses.append(pigpio.pulse(0, step_mask, lo))

        self.pi.wave_add_generic(pulses)
        wid = self.pi.wave_create()
        if wid < 0:
            self.pi.write(en_pin, EN_DISABLE)
            raise RuntimeError(f"Wave create fehlgeschlagen fuer Pin {step_pin}")

        self.pi.wave_send_once(wid)
        while self.pi.wave_tx_busy():
            time.sleep(0.01)
        self.pi.wave_delete(wid)

        self.pi.write(en_pin, EN_DISABLE)

    def execute_move(self, move):
        # erlaubt z.B. R, R', R2, V, V'
        if not move:
            return

        face = move[0]
        suffix = move[1:] if len(move) > 1 else ""

        if face not in MOVE_TO_MOTOR:
            raise ValueError(f"Unbekannter Hardware-Zug: {move}")

        motor_id = MOVE_TO_MOTOR[face]
        step_pin, dir_pin, en_pin = MOTORS[motor_id]

        # Richtung: ohne ' = Uhrzeigersinn(1), mit ' = Gegen-Uhrzeigersinn(0)
        direction = 0 if suffix == "'" else 1
        repeats = 2 if suffix == "2" else 1

        for _ in range(repeats):
            if not self.enabled:
                print(f"[Trockenlauf] Motor {motor_id} -> {move}")
                continue

            # Sicherheit: alle anderen EN deaktivieren
            for other_id, pins in MOTORS.items():
                if other_id != motor_id:
                    self.pi.write(pins[2], EN_DISABLE)

            self._rotate_ramped(step_pin, dir_pin, en_pin, direction, STEPS_PER_90)


def run_move_sequence(moves):
    mc = MotorController()
    try:
        for idx, mv in enumerate(moves, 1):
            print(f"[{idx}/{len(moves)}] {mv}")
            mc.execute_move(mv)
            time.sleep(0.05)
    finally:
        mc.close()


# ============================================================
# Main
# ============================================================
def main():
    if Picamera2 is None:
        raise RuntimeError("picamera2 fehlt. Bitte auf dem Raspberry Pi installieren.")

    if kociemba is None:
        raise RuntimeError("kociemba fehlt. Installieren mit: pip install kociemba")

    print("=== Rubik Zwischenstand: Kalibrieren -> Erkennen -> Lösen -> Motoren ===")
    print("Hinweis: ESC bricht den aktuellen Schritt ab.")

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(main={"format": "BGR888", "size": (1280, 720)})
    picam2.configure(config)
    picam2.start()
    time.sleep(0.5)

    try:
        calib = calibrate_once_if_needed(picam2, CALIB_FILE)
        scanned_faces = scan_all_faces(picam2, calib)

        cube_string = build_kociemba_string(scanned_faces)
        print("Kociemba-String (URFDLB):", cube_string)

        solution = kociemba.solve(cube_string)
        solver_moves = expand_moves(solution.split())
        hw_moves = solver_to_hardware_moves(solver_moves)

        print("\nSolver-Zuege:", " ".join(solver_moves))
        print("Hardware-Zuege (F->V):", " ".join(hw_moves))

        go = input("\nMotoren ausfuehren? (j/n): ").strip().lower()
        if go in ("j", "ja", "y", "yes"):
            run_move_sequence(hw_moves)
            print("Fertig.")
        else:
            print("Motor-Ausfuehrung uebersprungen.")

    finally:
        picam2.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
