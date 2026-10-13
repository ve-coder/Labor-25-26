"""Kamera-Thread: liest laufend Bilder, wertet das Raster aus und hält das
neueste Vorschaubild (JPEG mit Raster) für den Livestream bereit."""
from __future__ import annotations

import threading
import time

from . import vision


class CameraManager:
    def __init__(self, camera, settings, fps=8):
        self.camera = camera
        self.settings = settings
        self.fps = fps
        self.stab = vision.Stabilizer()
        self.jpeg = b""
        self.last_values = None
        self.ok_count = 0
        self.stable = False
        self.mean_values = None
        self.live_colors = None
        self.info_text = ""
        self.last_frame = None
        self.error = None
        self._stop = threading.Event()
        self._new = threading.Condition()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                s = self.settings
                self.stab.frames = s["stable_frames"]
                self.stab.threshold = s["stable_threshold"]
                self.stab.min_brightness = s["min_brightness"]
                frame = vision.orient(self.camera.read(), s)
                vals = vision.sample_grid(frame, s)
                self.stab.push(vals)
                ok, stable, mean = self.stab.status()
                self.last_frame = frame
                self.last_values = vals
                self.ok_count, self.stable, self.mean_values = ok, stable, mean
                self.live_colors = [
                    vision.nearest_reference(v) if max(v) >= s["min_brightness"] else None for v in vals
                ]
                self.jpeg = vision.draw_overlay(frame, s, self.live_colors, ok, stable, self.info_text)
                self.error = None
            except Exception as e:  # Kamera weg o. ä. – weiterversuchen
                self.error = str(e)
                time.sleep(0.5)
            with self._new:
                self._new.notify_all()
            time.sleep(max(0.0, 1.0 / self.fps - (time.monotonic() - t0)))

    def wait_frame(self, timeout=1.0):
        with self._new:
            self._new.wait(timeout)

    def reset(self):
        self.stab.reset()
        self.stable = False

    def status(self):
        return {
            "ok": self.ok_count,
            "stable": self.stable,
            "colors": self.live_colors,
            "error": self.error,
        }

    def close(self):
        self._stop.set()
        self.thread.join(timeout=2)
        self.camera.close()
