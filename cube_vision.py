import json
import os

import cv2
import numpy as np

from cube_config import CALIB_FILE, CALIB_ORDER, DRAW_BGR, GRID_N, GRID_TOTAL, ROI_MARGIN_FRAC, TOL


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


def mean_rgb(roi):
    if roi is None or roi.size == 0:
        return None
    m = roi.reshape(-1, 3).mean(axis=0)
    return float(m[0]), float(m[1]), float(m[2])


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
    for line in lines:
        cv2.putText(frame_bgr, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
        y += 28


def load_calib():
    if not os.path.exists(CALIB_FILE):
        return None
    try:
        with open(CALIB_FILE, "r") as f:
            raw = json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Die Kalibrierdatei {CALIB_FILE} ist keine gueltige JSON-Datei: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"Die Kalibrierdatei {CALIB_FILE} konnte nicht gelesen werden: {exc}") from exc

    expected = {lab for lab, _ in CALIB_ORDER}
    missing = sorted(expected.difference(raw.keys()))
    if missing:
        raise RuntimeError(
            f"Die Kalibrierdatei {CALIB_FILE} ist unvollstaendig. Fehlende Farben: {', '.join(missing)}."
        )

    calib = {}
    for key in expected:
        try:
            value = raw[key]
            calib[key] = (float(value["r"]), float(value["g"]), float(value["b"]))
        except Exception as exc:
            raise RuntimeError(
                f"Die Kalibrierdatei {CALIB_FILE} hat fuer {key} keinen gueltigen r/g/b-Eintrag."
            ) from exc
    return calib


def save_calib(calib):
    raw = {k: {"r": v[0], "g": v[1], "b": v[2]} for k, v in calib.items()}
    try:
        with open(CALIB_FILE, "w") as f:
            json.dump(raw, f, indent=2)
    except OSError as exc:
        raise RuntimeError(f"Kalibrierung konnte nicht in {CALIB_FILE} gespeichert werden: {exc}") from exc


def calibrate_face_avg9(frame_rgb):
    h, w = frame_rgb.shape[:2]
    gx0, gy0, _, _ = grid_rect(w, h)
    samples = []
    for r in range(3):
        for c in range(3):
            roi = cell_roi(frame_rgb, gx0, gy0, r, c)
            m = mean_rgb(roi)
            if m is None:
                return None
            samples.append(m)
    arr = np.array(samples, dtype=np.float32)
    m = arr.mean(axis=0)
    return float(m[0]), float(m[1]), float(m[2])


def classify_rgb(r, g, b, calib):
    best = "?"
    best_d = 1e18
    for label, (cr, cg, cb) in calib.items():
        tr, tg, tb = TOL.get(label, (255, 255, 255))
        dr, dg, db = (r - cr), (g - cg), (b - cb)
        if abs(dr) > tr or abs(dg) > tg or abs(db) > tb:
            continue
        d = dr * dr + dg * dg + db * db
        if d < best_d:
            best_d = d
            best = label
    return best


def scan_face_3x3(frame_rgb, calib):
    h, w = frame_rgb.shape[:2]
    gx0, gy0, _, _ = grid_rect(w, h)
    out = []
    for r in range(3):
        row = []
        for c in range(3):
            roi = cell_roi(frame_rgb, gx0, gy0, r, c)
            m = mean_rgb(roi)
            if m is None:
                row.append("?")
                continue
            rr, gg, bb = m
            row.append(classify_rgb(rr, gg, bb, calib))
        out.append(row)
    return out


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
