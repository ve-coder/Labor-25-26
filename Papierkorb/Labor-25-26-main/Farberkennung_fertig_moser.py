#!/usr/bin/env python3
from picamera2 import Picamera2
import cv2
import time
import json

WINDOW_NAME = "Vorschau"

# --- Button-Konstanten ---
FOTO_BTN_X = 20
FOTO_BTN_Y = 20
FOTO_BTN_W = 160
FOTO_BTN_H = 60

CALIB_BTN_W = 200
CALIB_BTN_H = 40
CALIB_BTN_MARGIN = 20  # Abstand vom rechten Rand

# --- Raster-Konstanten (Zauberwürfel-Seite) ---
GRID_ROWS = 3
GRID_COLS = 3
GRID_CELL_SIZE = 220   # Pixel

# --- Kalibrierung ---
CALIB_FILE = "cube_calibration.json"
CALIB_ORDER = [
    ("W", "WEISS"),
    ("Y", "GELB"),
    ("R", "ROT"),
    ("O", "ORANGE"),
    ("B", "BLAU"),
    ("G", "GRUEN"),
]

# Zustands-Variablen
capture_requested = False
calibrating = False
calib_index = 0
calib_data = {}          # Buchstabe -> (H, S, V)
calib_button_rect = None # (x1, y1, x2, y2)


# -----------------------------------------------------------
# Kalibrierungs-Verwaltung
# -----------------------------------------------------------
def start_calibration():
    global calibrating, calib_index, calib_data
    calibrating = True
    calib_index = 0
    calib_data = {}
    print("Kalibrierung gestartet. Bitte die angezeigten Farbseiten nacheinander im Raster fotografieren.")


def save_calibration():
    if not calib_data:
        return
    data = {
        label: {"h": float(h), "s": float(s), "v": float(v)}
        for label, (h, s, v) in calib_data.items()
    }
    try:
        with open(CALIB_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print("Kalibrierung gespeichert in", CALIB_FILE)
    except Exception as e:
        print("Fehler beim Speichern der Kalibrierung:", e)


def load_calibration():
    global calib_data, calibrating, calib_index
    try:
        with open(CALIB_FILE, "r") as f:
            raw = json.load(f)
        calib_data = {
            label: (float(vals["h"]), float(vals["s"]), float(vals["v"]))
            for label, vals in raw.items()
        }
        if len(calib_data) >= len(CALIB_ORDER):
            calibrating = False
            calib_index = 0
            print("Kalibrierung geladen aus", CALIB_FILE)
        else:
            print("Kalibrierung unvollständig, neue Kalibrierung nötig.")
            start_calibration()
    except Exception:
        print("Keine gültige Kalibrierung gefunden, starte Kalibrierung.")
        start_calibration()


# -----------------------------------------------------------
# Geometrie (Raster)
# -----------------------------------------------------------
def get_grid_origin(frame_width, frame_height):
    grid_w = GRID_COLS * GRID_CELL_SIZE
    grid_h = GRID_ROWS * GRID_CELL_SIZE
    start_x = (frame_width - grid_w) // 2
    start_y = (frame_height - grid_h) // 2
    return start_x, start_y


def measure_center_cell_hsv(frame_rgb):
    """HSV-Mittelwert im Zentrum der mittleren Zelle."""
    h_img, w_img, _ = frame_rgb.shape
    start_x, start_y = get_grid_origin(w_img, h_img)

    center_row = GRID_ROWS // 2  # 1 (0-basiert)
    center_col = GRID_COLS // 2  # 1

    x1 = start_x + center_col * GRID_CELL_SIZE
    y1 = start_y + center_row * GRID_CELL_SIZE
    x2 = x1 + GRID_CELL_SIZE
    y2 = y1 + GRID_CELL_SIZE

    margin = GRID_CELL_SIZE // 4
    cx1 = x1 + margin
    cy1 = y1 + margin
    cx2 = x2 - margin
    cy2 = y2 - margin

    frame_hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
    roi = frame_hsv[cy1:cy2, cx1:cx2]
    if roi.size == 0:
        return None, None, None

    h_mean, s_mean, v_mean, _ = cv2.mean(roi)
    return h_mean, s_mean, v_mean


# -----------------------------------------------------------
# Farberkennung
# -----------------------------------------------------------
def classify_color_hsv(h, s, v):
    """
    Gibt 'W', 'Y', 'R', 'O', 'G', 'B' oder '?' zurück.
    Nutzt zuerst Kalibrierung (Nearest Neighbor in HSV-Raum),
    sonst einfache Default-Schwellen.
    """
    # 1) Falls Kalibrierung vorhanden: Nearest Neighbor
    if calib_data:
        best_label = "?"
        best_dist = 1e12
        for label, (ch, cs, cv) in calib_data.items():
            # Hue ist zyklisch (0..179)
            dh = abs(h - ch)
            if dh > 90:
                dh = 180 - dh
            ds = abs(s - cs)
            dv = abs(v - cv)
            dist = (dh * dh + ds * ds + dv * dv) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_label = label
        return best_label

    # 2) Fallback: grobe feste Grenzen
    if v > 180 and s < 40:
        return "W"
    if v < 50:
        return "?"

    if h < 10 or h >= 170:
        return "R"
    if 10 <= h < 20:
        return "O"
    if 20 <= h < 35:
        return "Y"
    if 35 <= h < 85:
        return "G"
    if 85 <= h < 135:
        return "B"

    return "?"


def detect_cube_colors(frame_rgb):
    """
    Liest alle 3x3-Kästchen im Raster aus und gibt eine 3x3-Matrix
    der erkannten Farbbuchstaben aus.
    """
    h_img, w_img, _ = frame_rgb.shape
    start_x, start_y = get_grid_origin(w_img, h_img)

    frame_hsv = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2HSV)
    face_colors = []

    for row in range(GRID_ROWS):
        row_colors = []
        for col in range(GRID_COLS):
            x1 = start_x + col * GRID_CELL_SIZE
            y1 = start_y + row * GRID_CELL_SIZE
            x2 = x1 + GRID_CELL_SIZE
            y2 = y1 + GRID_CELL_SIZE

            margin = GRID_CELL_SIZE // 4
            cx1 = x1 + margin
            cy1 = y1 + margin
            cx2 = x2 - margin
            cy2 = y2 - margin

            roi = frame_hsv[cy1:cy2, cx1:cx2]
            if roi.size == 0:
                row_colors.append("?")
                continue

            h_mean, s_mean, v_mean, _ = cv2.mean(roi)
            color_label = classify_color_hsv(h_mean, s_mean, v_mean)
            row_colors.append(color_label)
        face_colors.append(row_colors)

    print("Erkannte Farben (oben links -> unten rechts):")
    for row in face_colors:
        print(" ".join(row))
    print("Legende: W=weis, Y=gelb, R=rot, O=orange, G=gruen, B=blau, ?=unbekannt\n")

    return face_colors


def handle_calibration_step(frame_rgb):
    """Einen Kalibrierschritt ausführen (mittlere Zelle der aktuellen Seite)."""
    global calib_index, calibrating

    if calib_index >= len(CALIB_ORDER):
        calibrating = False
        return

    label, name = CALIB_ORDER[calib_index]
    h, s, v = measure_center_cell_hsv(frame_rgb)
    if h is None:
        print("Kalibrierungsschritt fehlgeschlagen (kein ROI). Bitte erneut versuchen.")
        return

    calib_data[label] = (h, s, v)
    print(
        f"Kalibrierung {calib_index + 1}/{len(CALIB_ORDER)}: {name}-Seite "
        f"-> H={h:.1f}, S={s:.1f}, V={v:.1f}"
    )

    calib_index += 1
    if calib_index >= len(CALIB_ORDER):
        calibrating = False
        save_calibration()
        print("Kalibrierung abgeschlossen.\n")


# -----------------------------------------------------------
# Maus-Callback (Buttons)
# -----------------------------------------------------------
def on_mouse(event, x, y, flags, param):
    """Maus-Callback: FOTO-Button und Kalibrierungs-Button."""
    global capture_requested
    if event == cv2.EVENT_LBUTTONDOWN:
        # FOTO-Button
        if (FOTO_BTN_X <= x <= FOTO_BTN_X + FOTO_BTN_W and
                FOTO_BTN_Y <= y <= FOTO_BTN_Y + FOTO_BTN_H):
            capture_requested = True
            return

        # Kalibrierungs-Button
        global calib_button_rect
        if calib_button_rect is not None:
            x1, y1, x2, y2 = calib_button_rect
            if x1 <= x <= x2 and y1 <= y <= y2:
                start_calibration()
                return


# -----------------------------------------------------------
# Hauptprogramm
# -----------------------------------------------------------
def main():
    global capture_requested, calib_button_rect

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"format": "RGB888", "size": (1280, 720)}
    )
    picam2.configure(config)

    picam2.start()
    time.sleep(0.5)

    # vorhandene Kalibrierung laden oder neue starten
    load_calibration()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse)

    while True:
        # Rohbild (ohne Overlays) für Speicherung + Auswertung
        raw_rgb = picam2.capture_array()
        frame_rgb = raw_rgb.copy()

        h_img, w_img, _ = frame_rgb.shape

        # --- 3x3-Raster zeichnen ---
        start_x, start_y = get_grid_origin(w_img, h_img)
        for row in range(GRID_ROWS):
            for col in range(GRID_COLS):
                x1 = start_x + col * GRID_CELL_SIZE
                y1 = start_y + row * GRID_CELL_SIZE
                x2 = x1 + GRID_CELL_SIZE
                y2 = y1 + GRID_CELL_SIZE
                cv2.rectangle(
                    frame_rgb,
                    (x1, y1),
                    (x2, y2),
                    (255, 255, 255),  # RGB: Weiß
                    2,
                )

        # --- FOTO-Button links oben ---
        cv2.rectangle(
            frame_rgb,
            (FOTO_BTN_X, FOTO_BTN_Y),
            (FOTO_BTN_X + FOTO_BTN_W, FOTO_BTN_Y + FOTO_BTN_H),
            (0, 200, 0),  # RGB: Grün
            -1,
        )
        cv2.putText(
            frame_rgb,
            "FOTO",
            (FOTO_BTN_X + 25, FOTO_BTN_Y + 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),  # RGB: Weiß
            2,
            cv2.LINE_AA,
        )

        # --- Kalibrierungs-Button rechts oben ---
        calib_x2 = w_img - CALIB_BTN_MARGIN
        calib_x1 = calib_x2 - CALIB_BTN_W
        calib_y1 = FOTO_BTN_Y
        calib_y2 = calib_y1 + CALIB_BTN_H
        calib_button_rect = (calib_x1, calib_y1, calib_x2, calib_y2)

        cv2.rectangle(
            frame_rgb,
            (calib_x1, calib_y1),
            (calib_x2, calib_y2),
            (0, 0, 200),  # RGB: Blau
            -1,
        )
        cv2.putText(
            frame_rgb,
            "CALIB",
            (calib_x1 + 20, calib_y1 + 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        # --- Status-Text (welche Seite fotografieren) ---
        if calibrating and calib_index < len(CALIB_ORDER):
            label, name = CALIB_ORDER[calib_index]
            status_text = (
                f"Kalibrierung {calib_index + 1}/{len(CALIB_ORDER)}: "
                f"{name}-Seite ins Raster halten und 'FOTO' klicken"
            )
        else:
            status_text = "Erkennung: Würfelseite im Raster ausrichten und 'FOTO' klicken (ESC = Ende)"

        cv2.putText(
            frame_rgb,
            status_text,
            (20, FOTO_BTN_Y + FOTO_BTN_H + 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 0),  # RGB: Gelb
            2,
            cv2.LINE_AA,
        )

        # Unterer Hinweis
        cv2.putText(
            frame_rgb,
            "ESC = Programm beenden, 'CALIB' = Neu kalibrieren",
            (20, h_img - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 0),
            2,
            cv2.LINE_AA,
        )

        # Anzeige (RGB -> BGR)
        frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
        cv2.imshow(WINDOW_NAME, frame_bgr)

        key = cv2.waitKey(1) & 0xFF
        if key == 27:  # ESC
            break

        # Foto-Aufnahme (vom letzten Frame)
        if capture_requested:
            capture_requested = False

            # Dateiname je nach Modus
            if calibrating and calib_index < len(CALIB_ORDER):
                label, _ = CALIB_ORDER[calib_index]
                filename = time.strftime(f"calib_{label}_%Y%m%d_%H%M%S.jpg")
            else:
                filename = time.strftime("foto_%Y%m%d_%H%M%S.jpg")

            raw_bgr = cv2.cvtColor(raw_rgb, cv2.COLOR_RGB2BGR)
            cv2.imwrite(filename, raw_bgr)
            print("Foto gespeichert als:", filename)

            if calibrating:
                # Kalibrierungsbild auswerten (mittlere Zelle)
                handle_calibration_step(raw_rgb)
            else:
                # Normale 3x3-Erkennung
                detect_cube_colors(raw_rgb)

    picam2.stop()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
