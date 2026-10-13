"""Kamera, Raster-Auswertung und Farbklassifizierung.

Ablauf beim Scannen einer Seite:
  1. Bild holen, gemäß Einstellungen drehen/spiegeln
  2. 3x3-Raster: pro Kästchen den Mittelwert eines inneren Messfelds bilden
  3. "9/9 erkannt" = alle 9 Felder hell genug und über N Bilder stabil
Nach allen 6 Seiten werden die 54 Messwerte über die 6 Mittelsteine
klassifiziert (Selbstkalibrierung unter dem aktuellen Licht), mit der
Bedingung "genau 9 pro Farbe".
"""
from __future__ import annotations

import itertools
import threading
import time
from collections import deque

import cv2
import numpy as np

# grobe Referenzfarben (RGB) – nur für Livevorschau und Farbnamen
REFERENCE_RGB = {
    "W": (220, 220, 215),
    "Y": (225, 200, 40),
    "R": (190, 35, 35),
    "O": (235, 110, 30),
    "G": (40, 160, 70),
    "B": (30, 80, 190),
}


# ===================================================================== Kameras
class BaseCamera:
    def read(self) -> np.ndarray:
        raise NotImplementedError

    def close(self):
        pass


class PiCamera(BaseCamera):
    """Raspberry-Pi-Kamera über picamera2 (apt: python3-picamera2)."""

    def __init__(self, width=640, height=480, fixed_exposure=True):
        from picamera2 import Picamera2  # nur am Pi vorhanden

        self.cam = Picamera2()
        cfg = self.cam.create_preview_configuration(main={"size": (width, height), "format": "RGB888"})
        self.cam.configure(cfg)
        self.cam.start()
        self._lock = threading.Lock()
        if fixed_exposure:
            time.sleep(2.0)  # Automatik einschwingen lassen
            md = self.cam.capture_metadata()
            controls = {"AeEnable": False, "AwbEnable": False}
            if "ExposureTime" in md:
                controls["ExposureTime"] = md["ExposureTime"]
            if "AnalogueGain" in md:
                controls["AnalogueGain"] = md["AnalogueGain"]
            if "ColourGains" in md:
                controls["ColourGains"] = md["ColourGains"]
            self.cam.set_controls(controls)

    def read(self):
        with self._lock:
            frame = self.cam.capture_array()
        # picamera2 "RGB888" liefert die Bytes in der Reihenfolge B,G,R
        return frame[:, :, ::-1].copy()

    def close(self):
        try:
            self.cam.stop()
        except Exception:
            pass


class SimCamera(BaseCamera):
    """Erzeugt ein künstliches Bild der Unterseite des simulierten Würfels."""

    def __init__(self, bottom_provider, width=640, height=480, settings=None):
        self.bottom_provider = bottom_provider  # liefert 9 Farbbuchstaben (D-Netzansicht) oder None
        self.w, self.h = width, height
        self.settings = settings
        self.rng = np.random.default_rng(1)
        # pro Sticker leicht unterschiedliche Farbe, wie echte Aufkleber
        self._tint = {}

    def read(self):
        img = np.full((self.h, self.w, 3), 40, np.uint8)
        colors = self.bottom_provider()
        s = self.settings
        cx = int((s["grid_cx"] if s else 0.5) * self.w)
        cy = int((s["grid_cy"] if s else 0.5) * self.h)
        size = int((s["grid_size"] if s else 0.6) * self.h)
        cell = size // 3
        x0, y0 = cx - size // 2, cy - size // 2
        cv2.rectangle(img, (x0 - 6, y0 - 6), (x0 + size + 6, y0 + size + 6), (15, 15, 15), -1)
        if colors:
            for i, c in enumerate(colors):
                r, col = divmod(i, 3)
                base = np.array(REFERENCE_RGB.get(c, (90, 90, 90)), float)
                key = (i, c)
                if key not in self._tint:
                    self._tint[key] = self.rng.normal(0, 8, 3)
                rgb = np.clip(base + self._tint[key], 0, 255)
                p1 = (x0 + col * cell + 4, y0 + r * cell + 4)
                p2 = (x0 + (col + 1) * cell - 4, y0 + (r + 1) * cell - 4)
                cv2.rectangle(img, p1, p2, tuple(int(v) for v in rgb), -1)
        # Helligkeitsverlauf + Rauschen
        grad = np.linspace(0.85, 1.1, self.w)[None, :, None]
        noise = self.rng.normal(0, 4, img.shape)
        img = np.clip(img * grad + noise, 0, 255).astype(np.uint8)
        # Bild so ausgeben, wie eine verdrehte/gespiegelte Kamera es täte
        if s:
            if s["cam_mirror"]:
                img = img[:, ::-1]
            k = int(s["cam_rotate"]) // 90
            if k:
                img = np.rot90(img, -k)  # inverse der Korrektur in orient()
        return np.ascontiguousarray(img)


# ===================================================================== Auswertung
def orient(frame, settings):
    """Dreht/spiegelt das Kamerabild in die Standard-D-Netzansicht."""
    k = int(settings["cam_rotate"]) // 90
    if k:
        frame = np.rot90(frame, k)
    if settings["cam_mirror"]:
        frame = frame[:, ::-1]
    return np.ascontiguousarray(frame)


def grid_cells(shape, settings):
    h, w = shape[:2]
    size = settings["grid_size"] * min(h, w)
    cx, cy = settings["grid_cx"] * w, settings["grid_cy"] * h
    cell = size / 3
    x0, y0 = cx - size / 2, cy - size / 2
    frac = settings["sample_frac"]
    out = []
    for r in range(3):
        for c in range(3):
            mx = x0 + (c + 0.5) * cell
            my = y0 + (r + 0.5) * cell
            half = cell * frac / 2
            out.append(
                (
                    int(x0 + c * cell), int(y0 + r * cell), int(cell),
                    (int(mx - half), int(my - half), int(mx + half), int(my + half)),
                )
            )
    return out


def sample_grid(frame, settings):
    """Liefert 9 RGB-Mittelwerte (Median über das Messfeld)."""
    vals = []
    h, w = frame.shape[:2]
    for _x, _y, _s, (a, b, c, d) in grid_cells(frame.shape, settings):
        a, b, c, d = max(a, 0), max(b, 0), min(c, w), min(d, h)
        patch = frame[b:d, a:c].reshape(-1, 3)
        if len(patch) == 0:
            vals.append((0.0, 0.0, 0.0))
        else:
            vals.append(tuple(float(v) for v in np.median(patch, axis=0)))
    return vals


def nearest_reference(rgb):
    lab = rgb_to_lab([rgb])[0]
    best, bd = None, 1e9
    for name, ref in REFERENCE_RGB.items():
        d = np.linalg.norm(lab - rgb_to_lab([ref])[0])
        if d < bd:
            best, bd = name, d
    return best


def rgb_to_lab(rgbs):
    arr = np.array(rgbs, np.float32).reshape(1, -1, 3) / 255.0
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2Lab).reshape(-1, 3)
    return lab


class Stabilizer:
    """Prüft, ob die 9 Messwerte über mehrere Bilder ruhig sind."""

    def __init__(self, frames=5, threshold=12.0, min_brightness=35):
        self.frames = frames
        self.threshold = threshold
        self.min_brightness = min_brightness
        self.buf = deque(maxlen=frames)

    def push(self, values):
        self.buf.append(np.array(values, float))

    def status(self):
        """(anzahl_ok, stabil, mittelwerte)"""
        if not self.buf:
            return 0, False, None
        last = self.buf[-1]
        bright_ok = last.max(axis=1) >= self.min_brightness
        if len(self.buf) < self.frames:
            return int(bright_ok.sum()), False, None
        stack = np.stack(self.buf)
        spread = (stack.max(axis=0) - stack.min(axis=0)).max(axis=1)
        ok = bright_ok & (spread <= self.threshold)
        mean = stack.mean(axis=0)
        return int(ok.sum()), bool(ok.all()), [tuple(v) for v in mean]

    def reset(self):
        self.buf.clear()


def classify(sticker_rgbs: dict, center_ids: list):
    """Ordnet alle 54 Sticker einem der 6 Mittelsteine zu (genau 9 je Farbe).

    sticker_rgbs: {sticker_id: (r,g,b)}
    center_ids:   die 6 Sticker-IDs der Mittelsteine
    Rückgabe:     {sticker_id: farbbuchstabe}, {center_id: farbbuchstabe}, Güte
    """
    ids = list(sticker_rgbs.keys())
    labs = rgb_to_lab([sticker_rgbs[i] for i in ids])
    lab_of = dict(zip(ids, labs))
    centers = [lab_of[c] for c in center_ids]

    # Abstand: Helligkeit weniger gewichten (Schatten), Farbton stärker
    def dist(a, b):
        d = a - b
        return float(np.sqrt((0.5 * d[0]) ** 2 + d[1] ** 2 + d[2] ** 2))

    pairs = []
    for sid in ids:
        for k, cl in enumerate(centers):
            pairs.append((dist(lab_of[sid], cl), sid, k))
    pairs.sort()
    assign, count = {}, [0] * 6
    for c_idx, cid in enumerate(center_ids):  # Mittelsteine sind fix
        assign[cid] = c_idx
        count[c_idx] += 1
    for d, sid, k in pairs:
        if sid in assign or count[k] >= 9:
            continue
        assign[sid] = k
        count[k] += 1

    # Farbnamen für die 6 Gruppen: beste Permutation zu den Referenzfarben
    group_lab = []
    for k in range(6):
        members = [lab_of[s] for s, g in assign.items() if g == k]
        group_lab.append(np.mean(members, axis=0))
    names = list(REFERENCE_RGB.keys())
    ref_lab = rgb_to_lab([REFERENCE_RGB[n] for n in names])
    best, best_cost = None, 1e18
    for perm in itertools.permutations(range(6)):
        cost = sum(dist(group_lab[k], ref_lab[perm[k]]) for k in range(6))
        if cost < best_cost:
            best, best_cost = perm, cost
    group_name = {k: names[best[k]] for k in range(6)}

    # Güte: mittlerer Abstand zum eigenen Mittelstein
    quality = float(np.mean([dist(lab_of[s], centers[g]) for s, g in assign.items()]))
    return {s: group_name[g] for s, g in assign.items()}, quality


def draw_overlay(frame, settings, live_colors=None, ok_count=0, stable=False, text=""):
    img = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    color_ok = (117, 158, 29)  # BGR grün
    color_wait = (39, 159, 239)
    for i, (x, y, s, (a, b, c, d)) in enumerate(grid_cells(frame.shape, settings)):
        cv2.rectangle(img, (x, y), (x + s, y + s), color_ok if stable else color_wait, 2)
        cv2.rectangle(img, (a, b), (c, d), (255, 255, 255), 1)
        if live_colors and live_colors[i]:
            rgb = REFERENCE_RGB[live_colors[i]]
            cv2.circle(img, (x + s - 12, y + 12), 7, (rgb[2], rgb[1], rgb[0]), -1)
            cv2.circle(img, (x + s - 12, y + 12), 7, (0, 0, 0), 1)
    # Orientierungshilfe: oben = Gerätevorderseite (F), links = Seite L
    x0, y0, s0, _ = grid_cells(frame.shape, settings)[0]
    x8, y8, s8, _ = grid_cells(frame.shape, settings)[8]
    mid_x, mid_y = (x0 + x8 + s8) // 2, (y0 + y8 + s8) // 2
    cv2.putText(img, "F", (mid_x - 7, max(y0 - 8, 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, "L", (max(x0 - 22, 2), mid_y + 7), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)
    label = f"{ok_count}/9" + (" erkannt" if stable else "")
    cv2.putText(img, label, (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    if text:
        cv2.putText(img, text, (10, img.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return jpg.tobytes() if ok else b""
