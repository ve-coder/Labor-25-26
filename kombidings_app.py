import queue
import threading
import time

import cv2
from ursina import EditorCamera, Entity, Text, Ursina, application, color, window

from cube_config import CALIB_ORDER, CV_WINDOW, SCAN_ORDER
from cube_solver import solve_cube_string
from cube_validation import ensure_grid_shape, validate_face_grid
from cube_vision import (
    calibrate_face_avg9,
    draw_grid,
    draw_live_labels,
    load_calib,
    put_info,
    save_calib,
    scan_face_3x3,
)
from cube_visual import CubeVisualizer

try:
    from picamera2 import Picamera2
except Exception as e:
    Picamera2 = None
    PICAMERA2_IMPORT_ERROR = str(e)


class RubiksScanApp(Entity):
    def __init__(self):
        super().__init__()

        self.ev_q = queue.Queue()
        self.ev_quit = threading.Event()
        self.solution_moves = []
        self.scan_done = False

        self.scan_text = Text(text="Scan: initialisiere...", position=(-0.85, 0.45), scale=1.2, color=color.white)
        self.step_text = Text(text="Moves: -", position=(-0.85, 0.30), scale=1.6, color=color.yellow)
        self.hint_text = Text(
            text="OpenCV: SPACE=Foto | ESC=Ende   |   Ursina: SPACE=Next Move",
            position=(-0.85, 0.20),
            scale=1.0,
            color=color.white,
        )

        self.cube = CubeVisualizer()

        threading.Thread(target=self.camera_thread, daemon=True).start()

    def report_error(self, message):
        print(f"FEHLER: {message}")
        self.scan_text.text = f"Fehler: {message}"
        self.scan_text.color = color.red
        self.step_text.text = "Moves: -"
        self.step_text.color = color.red

    def camera_error(self, message):
        self.ev_q.put(("error", message))
        self.ev_quit.set()

    def solve_from_stickers(self):
        if self.cube.action_mode:
            return

        cube_string = self.cube.scan_cube_state()
        print("Cube (URFDLB):", cube_string)

        try:
            solution, expanded = solve_cube_string(cube_string)
            self.solution_moves = expanded
            self.scan_done = True
            self.step_text.text = f"Moves: {len(self.solution_moves)}"
            self.step_text.color = color.yellow
            print("Solution:", solution)
        except Exception as exc:
            self.report_error(f"Die Loesung konnte nicht berechnet werden: {exc}")
            self.solution_moves = []
            self.scan_done = True

    def camera_thread(self):
        picam2 = None
        try:
            calib = load_calib()

            if Picamera2 is None:
                raise RuntimeError(
                    "picamera2 ist nicht verfuegbar. Bitte auf dem Zielsystem installieren: pip install picamera2. "
                    f"Technische Details: {PICAMERA2_IMPORT_ERROR}"
                )

            picam2 = Picamera2()
            config = picam2.create_preview_configuration(main={"format": "BGR888", "size": (1280, 720)})
            picam2.configure(config)
            picam2.start()
            time.sleep(0.5)

            cv2.namedWindow(CV_WINDOW, cv2.WINDOW_AUTOSIZE)

            if calib is None:
                calib = {}
                for idx, (lab, name) in enumerate(CALIB_ORDER, 1):
                    self.ev_q.put(("status", f"Kalibrierung {idx}/6: {name}"))
                    while not self.ev_quit.is_set():
                        frame_bgr = picam2.capture_array()
                        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                        draw_grid(frame_bgr)
                        put_info(frame_bgr, [f"KALIB {idx}/6: {name}", "Lege DIESE FARBE voll ins Grid.", "SPACE=Foto  ESC=Ende"])

                        if len(calib) >= 1:
                            live = scan_face_3x3(frame_rgb, calib)
                            draw_live_labels(frame_bgr, live)

                        cv2.imshow(CV_WINDOW, frame_bgr)
                        key = cv2.waitKey(1) & 0xFF
                        if key == 27:
                            self.ev_quit.set()
                            break
                        if key == 32:
                            try:
                                m = calibrate_face_avg9(frame_rgb)
                                if m is None:
                                    raise ValueError(
                                        f"Kalibrierung {name} fehlgeschlagen: Das 3x3-Grid konnte nicht sauber ausgelesen werden."
                                    )
                                calib[lab] = m
                            except Exception as exc:
                                self.ev_q.put(("error", str(exc)))
                                continue
                            break

                    if self.ev_quit.is_set():
                        break

                if not self.ev_quit.is_set() and len(calib) == 6:
                    save_calib(calib)

            for idx, (face_letter, face_name) in enumerate(SCAN_ORDER, 1):
                if self.ev_quit.is_set():
                    break

                self.ev_q.put(("status", f"Scan {idx}/6: {face_name}"))

                while not self.ev_quit.is_set():
                    frame_bgr = picam2.capture_array()
                    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

                    draw_grid(frame_bgr)
                    live = scan_face_3x3(frame_rgb, calib)
                    draw_live_labels(frame_bgr, live)

                    put_info(frame_bgr, [f"SCAN {idx}/6: {face_name}", "Lege DIESE SEITE voll ins Grid.", "SPACE=Foto  ESC=Ende"])

                    cv2.imshow(CV_WINDOW, frame_bgr)
                    key = cv2.waitKey(1) & 0xFF
                    if key == 27:
                        self.ev_quit.set()
                        break
                    if key == 32:
                        try:
                            validate_face_grid(face_letter, live)
                            self.ev_q.put(("face", face_letter, live))
                        except Exception as exc:
                            self.ev_q.put(("error", str(exc)))
                            continue
                        break

            if not self.ev_quit.is_set():
                self.ev_q.put(("solve",))
        except Exception as exc:
            self.camera_error(str(exc))
        finally:
            if picam2 is not None:
                try:
                    picam2.stop()
                except Exception:
                    pass
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
            self.ev_q.put(("done",))

    def update(self):
        while True:
            try:
                msg = self.ev_q.get_nowait()
            except queue.Empty:
                break

            if not msg:
                continue

            if msg[0] == "status":
                self.scan_text.text = msg[1]
                self.scan_text.color = color.white

            elif msg[0] == "face":
                try:
                    _, face_letter, grid = msg
                    ensure_grid_shape(grid, face_letter)
                    validate_face_grid(face_letter, grid)
                    self.cube.apply_face_to_ursina(face_letter, grid)
                except Exception as exc:
                    self.report_error(str(exc))

            elif msg[0] == "solve":
                self.scan_text.text = "Scan fertig. Berechne Loesung..."
                try:
                    self.solve_from_stickers()
                    if self.solution_moves:
                        self.scan_text.text = "Fertig. Ursina: SPACE = Next Move"
                        self.scan_text.color = color.white
                except Exception as exc:
                    self.report_error(str(exc))

            elif msg[0] == "error":
                self.report_error(msg[1])

    def input(self, key):
        if key == "space":
            if self.solution_moves and (not self.cube.action_mode):
                try:
                    move = self.solution_moves.pop(0)
                    self.step_text.text = f"Moves: {len(self.solution_moves)}"
                    face = move[0]
                    direction = -1 if "'" in move else 1
                    self.cube.rotate_side(face, direction, speed=self.cube.move_delay)
                except Exception as exc:
                    self.report_error(f"Der naechste Zug konnte nicht ausgefuehrt werden: {exc}")
            else:
                if self.scan_done:
                    self.report_error(
                        "Es gibt gerade keinen ausfuehrbaren Loesungszug. Pruefe, ob der Scan vollstaendig ist oder druecke Enter fuer eine neue Berechnung."
                    )
                else:
                    self.report_error("Es gibt noch keine Loesung. Zuerst muessen alle 6 Seiten gescannt werden.")

        if key == "enter":
            try:
                self.solve_from_stickers()
            except Exception as exc:
                self.report_error(f"Manuelle Loesung fehlgeschlagen: {exc}")

        if key == "escape":
            self.ev_quit.set()
            application.quit()


def run():
    app = Ursina()
    window.title = "Rubiks Cube - Camera Scan + Solver"
    window.borderless = False
    window.size = (1000, 800)
    window.color = color.gray

    EditorCamera()
    RubiksScanApp()
    app.run()
