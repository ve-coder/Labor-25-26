#!/usr/bin/env python3
import time
import json
import threading
import queue
import numpy as np
import cv2
from picamera2 import Picamera2

from ursina import *
import random

try:
    import kociemba
except Exception:
    kociemba = None

# =========================
# OpenCV / Scan CONFIG
# =========================
CV_WINDOW = "Cube Scan (OpenCV)"
GRID_TOTAL = 660
GRID_N = 3
ROI_MARGIN_FRAC = 0.25

CALIB_FILE = "cube_calibration_rgb9.json"

# Kalibrier-Reihenfolge: je Farbe 1 Foto, Mittelwert über alle 9 Sticker
CALIB_ORDER = [
    ("W", "WEISS"),
    ("Y", "GELB"),
    ("R", "ROT"),
    ("O", "ORANGE"),
    ("B", "BLAU"),
    ("G", "GRUEN"),
]

# Scan-Reihenfolge (Kociemba): URFDLB
SCAN_ORDER = [
    ("U", "OBEN (U)"),
    ("R", "RECHTS (R)"),
    ("F", "VORNE (F)"),
    ("D", "UNTEN (D)"),
    ("L", "LINKS (L)"),
    ("B", "HINTEN (B)"),
]

# Toleranzen pro Farbe (± pro Kanal in RGB)
TOL = {"W": (35, 35, 35),
    "Y": (40, 30, 30),
    "R": (55, 55, 55),
    "O": (55, 55, 55),
    "G": (45, 45, 45),
    "B": (60, 60, 60),
}


# Live-Overlay Farben (BGR für OpenCV)
DRAW_BGR = {
    "W": (255, 255, 255),
    "Y": (0, 255, 255),
    "R": (0, 0, 255),
    "O": (0, 128, 255),
    "G": (0, 255, 0),
    "B": (255, 0, 0),
    "?": (0, 255, 255),
}

# Kamera-Erkennung (W,Y,R,O,G,B) -> Ursina color_code (y,w,r,o,g,b)
UPPER_TO_CODE = {"Y": "y", "W": "w", "R": "r", "O": "o", "G": "g", "B": "b", "?": "y"}

# =========================
# Ursina Cube (dein Anzeige-Script Stil)
# =========================
app = Ursina()
window.title = "Rubiks Cube - Camera Scan + Solver"
window.borderless = False
window.size = (1000, 800)
window.color = color.gray

EditorCamera()

cubes = []
stickers = []
pivot = Entity()
action_mode = False

solution_moves = []   # expanded (U2 -> U,U)
move_delay = 0.20     # nur für Animation speed
scan_done = False

# UI
scan_text = Text(text="Scan: initialisiere...", position=(-0.85, 0.45), scale=1.2, color=color.white)
step_text = Text(text="Moves: -", position=(-0.85, 0.30), scale=1.6, color=color.yellow)
hint_text = Text(text="OpenCV: SPACE=Foto | ESC=Ende   |   Ursina: SPACE=Next Move", position=(-0.85, 0.20), scale=1.0, color=color.white)

def create_cube():
    cols = {
        'y': color.yellow,
        'w': color.white,
        'r': color.red,
        'o': color.orange,
        'g': color.green,
        'b': color.blue
    }

    for x in range(-1, 2):
        for y in range(-1, 2):
            for z in range(-1, 2):
                parent = Entity(model='cube', color=color.black, position=(x, y, z), scale=0.95)
                parent.collider = 'box'

                def make_sticker(pos, rot, col_key):
                    s = Entity(parent=parent, model='quad', color=cols[col_key],
                               position=pos, rotation=rot, scale=0.9, double_sided=True, unlit=True)
                    s.color_code = col_key
                    stickers.append(s)

                # Western Scheme (wie dein Script)
                if x == 1:  make_sticker((0.51, 0, 0), (0, 90, 0), 'r')    # Right=Red
                if x == -1: make_sticker((-0.51, 0, 0), (0, -90, 0), 'o')  # Left=Orange
                if y == 1:  make_sticker((0, 0.51, 0), (-90, 0, 0), 'y')   # Up=Yellow
                if y == -1: make_sticker((0, -0.51, 0), (90, 0, 0), 'w')   # Down=White
                if z == -1: make_sticker((0, 0, -0.51), (0, 0, 0), 'g')    # Front=Green
                if z == 1:  make_sticker((0, 0, 0.51), (0, 180, 0), 'b')   # Back=Blue

                cubes.append(parent)

create_cube()

def reset_action_mode():
    global action_mode
    for c in cubes:
        c.world_parent = scene
    action_mode = False

def rotate_side(side_name, direction, speed=0.2):
    global action_mode
    action_mode = True

    axis = 'y'
    level = 0
    if side_name == 'U': axis, level = 'y', 1
    elif side_name == 'D': axis, level = 'y', -1
    elif side_name == 'L': axis, level = 'x', -1
    elif side_name == 'R': axis, level = 'x', 1
    elif side_name == 'F': axis, level = 'z', -1
    elif side_name == 'B': axis, level = 'z', 1

    rot_dir = direction
    if side_name in ['B', 'L', 'D']:
        rot_dir *= -1

    selected = [c for c in cubes if
                (axis == 'x' and round(c.world_x) == level) or
                (axis == 'y' and round(c.world_y) == level) or
                (axis == 'z' and round(c.world_z) == level)]

    pivot.position = (0, 0, 0)
    pivot.rotation = (0, 0, 0)
    for c in selected:
        c.world_parent = pivot

    angle = 90 * rot_dir

    if speed == 0:
        if axis == 'x': pivot.rotation_x += angle
        elif axis == 'y': pivot.rotation_y += angle
        elif axis == 'z': pivot.rotation_z += angle
        for c in cubes:
            c.world_parent = scene
        action_mode = False
    else:
        if axis == 'x': pivot.animate_rotation_x(angle, duration=speed)
        elif axis == 'y': pivot.animate_rotation_y(angle, duration=speed)
        elif axis == 'z': pivot.animate_rotation_z(angle, duration=speed)
        invoke(reset_action_mode, delay=speed + 0.05)

# --- Sticker Zugriff (aus deinem Script-Ansatz) ---
def get_sticker_entity_at(pos, tolerance=0.4):
    for s in stickers:
        if distance(s.world_position, pos) < tolerance:
            return s
    return None

def scan_cube_state():
    # Original-Order aus deinem Script (liefert y,w,r,o,g,b) -> übersetzt zu URFDLB
    raw_state = ""
    for z in [1, 0, -1]:
        for x in [-1, 0, 1]:
            s = get_sticker_entity_at(Vec3(x, 1.5, z))
            raw_state += (s.color_code if s else 'y')
    for y in [1, 0, -1]:
        for z in [-1, 0, 1]:
            s = get_sticker_entity_at(Vec3(1.5, y, z))
            raw_state += (s.color_code if s else 'y')
    for y in [1, 0, -1]:
        for x in [-1, 0, 1]:
            s = get_sticker_entity_at(Vec3(x, y, -1.5))
            raw_state += (s.color_code if s else 'y')
    for z in [-1, 0, 1]:
        for x in [-1, 0, 1]:
            s = get_sticker_entity_at(Vec3(x, -1.5, z))
            raw_state += (s.color_code if s else 'y')
    for y in [1, 0, -1]:
        for z in [1, 0, -1]:
            s = get_sticker_entity_at(Vec3(-1.5, y, z))
            raw_state += (s.color_code if s else 'y')
    for y in [1, 0, -1]:
        for x in [1, 0, -1]:
            s = get_sticker_entity_at(Vec3(x, y, 1.5))
            raw_state += (s.color_code if s else 'y')

    translation_map = {'y': 'U', 'w': 'D', 'r': 'R', 'o': 'L', 'g': 'F', 'b': 'B', '?': 'U'}
    return "".join(translation_map.get(ch, 'U') for ch in raw_state)

def solve_from_stickers():
    global solution_moves, scan_done
    if action_mode:
        return

    cube_string = scan_cube_state()
    print("Cube (URFDLB):", cube_string)

    if kociemba is None:
        step_text.text = "kociemba fehlt"
        step_text.color = color.red
        solution_moves = []
        scan_done = True
        return

    try:
        sol = kociemba.solve(cube_string)
        raw = sol.split()

        expanded = []
        for m in raw:
            if '2' in m:
                single = m.replace('2', '')
                expanded.append(single)
                expanded.append(single)
            else:
                expanded.append(m)

        solution_moves = expanded
        scan_done = True
        step_text.text = f"Moves: {len(solution_moves)}"
        step_text.color = color.yellow
        print("Solution:", sol)
    except Exception as e:
        print("Solver Fehler:", e)
        step_text.text = f"Solver Fehler"
        step_text.color = color.red
        solution_moves = []
        scan_done = True

# =========================
# OpenCV / Kamera Funktionen
# =========================
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
    return float(m[0]), float(m[1]), float(m[2])  # R,G,B

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
    for s in lines:
        cv2.putText(frame_bgr, s, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2, cv2.LINE_AA)
        y += 28

def load_calib():
    try:
        with open(CALIB_FILE, "r") as f:
            raw = json.load(f)
        calib = {k: (float(v["r"]), float(v["g"]), float(v["b"])) for k, v in raw.items()}
        if len(calib) == 6:
            return calib
    except Exception:
        pass
    return None

def save_calib(calib):
    raw = {k: {"r": v[0], "g": v[1], "b": v[2]} for k, v in calib.items()}
    with open(CALIB_FILE, "w") as f:
        json.dump(raw, f, indent=2)

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
        d = dr*dr + dg*dg + db*db
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

# =========================
# Event bridge: Kamera -> Ursina
# =========================
ev_q = queue.Queue()
ev_quit = threading.Event()

def face_positions(face_letter):
    # exakt gleiche Reihenfolge wie scan_cube_state() Positions-Scan (dein Script)
    pos = []
    if face_letter == "U":
        for z in [1, 0, -1]:
            for x in [-1, 0, 1]:
                pos.append(Vec3(x, 1.5, z))
    elif face_letter == "R":
        for y in [1, 0, -1]:
            for z in [-1, 0, 1]:
                pos.append(Vec3(1.5, y, z))
    elif face_letter == "F":
        for y in [1, 0, -1]:
            for x in [-1, 0, 1]:
                pos.append(Vec3(x, y, -1.5))
    elif face_letter == "D":
        for z in [-1, 0, 1]:
            for x in [-1, 0, 1]:
                pos.append(Vec3(x, -1.5, z))
    elif face_letter == "L":
        for y in [1, 0, -1]:
            for z in [1, 0, -1]:
                pos.append(Vec3(-1.5, y, z))
    elif face_letter == "B":
        for y in [1, 0, -1]:
            for x in [1, 0, -1]:
                pos.append(Vec3(x, y, 1.5))
    return pos

def apply_face_to_ursina(face_letter, grid3x3_upper):
    """
    grid3x3_upper: 3x3 mit 'W','Y','R','O','G','B' (aus Kamera)
    Setzt Sticker.color + Sticker.color_code (y,w,r,o,g,b) an den 9 Positionen dieser Face.
    """
    cols = {
        'y': color.yellow,
        'w': color.white,
        'r': color.red,
        'o': color.orange,
        'g': color.green,
        'b': color.blue
    }

    positions = face_positions(face_letter)
    i = 0
    for r in range(3):
        for c in range(3):
            ch = grid3x3_upper[r][c]
            code = UPPER_TO_CODE.get(ch, 'y')
            s = get_sticker_entity_at(positions[i], tolerance=0.45)
            if s:
                s.color_code = code
                s.color = cols.get(code, color.yellow)
            i += 1

def camera_thread():
    calib = load_calib()

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(main={"format": "BGR888", "size": (1280, 720)})
    picam2.configure(config)
    picam2.start()
    time.sleep(0.5)

    cv2.namedWindow(CV_WINDOW, cv2.WINDOW_AUTOSIZE)

    # --- Calibration if missing ---
    if calib is None:
        calib = {}
        for idx, (lab, name) in enumerate(CALIB_ORDER, 1):
            ev_q.put(("status", f"Kalibrierung {idx}/6: {name}"))
            while not ev_quit.is_set():
                frame_bgr = picam2.capture_array()
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                draw_grid(frame_bgr)
                put_info(frame_bgr, [
                    f"KALIB {idx}/6: {name}",
                    "Lege DIESE FARBE voll ins Grid.",
                    "SPACE=Foto  ESC=Ende"
                ])

                if len(calib) >= 1:
                    live = scan_face_3x3(frame_rgb, calib)
                    draw_live_labels(frame_bgr, live)

                cv2.imshow(CV_WINDOW, frame_bgr)
                k = cv2.waitKey(1) & 0xFF
                if k == 27:
                    ev_quit.set()
                    break
                if k == 32:
                    m = calibrate_face_avg9(frame_rgb)
                    if m is None:
                        continue
                    calib[lab] = m
                    break

            if ev_quit.is_set():
                break

        if not ev_quit.is_set() and len(calib) == 6:
            save_calib(calib)

    # --- Scan faces ---
    for idx, (face_letter, face_name) in enumerate(SCAN_ORDER, 1):
        if ev_quit.is_set():
            break

        ev_q.put(("status", f"Scan {idx}/6: {face_name}"))

        while not ev_quit.is_set():
            frame_bgr = picam2.capture_array()
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            draw_grid(frame_bgr)
            live = scan_face_3x3(frame_rgb, calib)
            draw_live_labels(frame_bgr, live)

            put_info(frame_bgr, [
                f"SCAN {idx}/6: {face_name}",
                "Lege DIESE SEITE voll ins Grid.",
                "SPACE=Foto  ESC=Ende"
            ])

            cv2.imshow(CV_WINDOW, frame_bgr)
            k = cv2.waitKey(1) & 0xFF
            if k == 27:
                ev_quit.set()
                break
            if k == 32:
                ev_q.put(("face", face_letter, live))
                break

    picam2.stop()
    cv2.destroyAllWindows()

    if not ev_quit.is_set():
        ev_q.put(("solve",))
    ev_q.put(("done",))

# start camera thread
threading.Thread(target=camera_thread, daemon=True).start()

# =========================
# Ursina update + input
# =========================
def update():
    global scan_done
    while True:
        try:
            msg = ev_q.get_nowait()
        except queue.Empty:
            break

        if not msg:
            continue

        if msg[0] == "status":
            scan_text.text = msg[1]

        elif msg[0] == "face":
            _, face_letter, grid = msg
            apply_face_to_ursina(face_letter, grid)

        elif msg[0] == "solve":
            scan_text.text = "Scan fertig. Berechne Lösung..."
            solve_from_stickers()
            scan_text.text = "Fertig. Ursina: SPACE = Next Move"

        elif msg[0] == "done":
            pass

def input(key):
    global solution_moves

    if key == 'space':
        # Schrittweise lösen (nur wenn Scan/solve done & moves vorhanden)
        if solution_moves and (not action_mode):
            move = solution_moves.pop(0)
            step_text.text = f"Moves: {len(solution_moves)}"
            face = move[0]
            direction = -1 if "'" in move else 1
            rotate_side(face, direction, speed=move_delay)
        else:
            # optional: kein scramble, damit SPACE eindeutig "step" bleibt
            pass

    if key == 'enter':
        # manuell nochmal solve (aus aktuell gesetzten Stickern)
        solve_from_stickers()

    if key == 'escape':
        ev_quit.set()
        application.quit()

app.run()
