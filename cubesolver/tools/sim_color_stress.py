#!/usr/bin/env python3
"""Stresstest der Farberkennung in der Simulation: N zufällige Würfel scannen
(gleiche Abfolge wie das Standardprogramm) und zählen, wie oft Farben falsch sind.
  python tools/sim_color_stress.py [anzahl] [farbstreuung]
Farbstreuung = Standardabweichung der Stickerfarben (Standard 8, schwerer: 14)."""
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Settings  # noqa: E402
from app.cube_model import FACES, CubeModel  # noqa: E402
from app.vision import SimCamera, classify, orient, sample_grid  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
spread = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
s = Settings(Path("/tmp/_stress_settings.json"))
bad_runs = bad_fields = 0
for t in range(n):
    true = CubeModel.solved()
    true.scramble(25, random.Random(t))
    know = CubeModel.blank()
    cam = SimCamera(lambda: [st.color for st in true.face_stickers("D")], settings=s, tint=spread)
    cam.rng = np.random.default_rng(t)

    def scan():
        for st, val in zip(know.face_stickers("D"), sample_grid(orient(cam.read(), s), s)):
            st.rgb = val

    for i in range(4):
        scan(); true.rotate_whole("R", 1); know.rotate_whole("R", 1)
    true.rotate_whole("D", 1); know.rotate_whole("D", 1)
    for i in range(4):
        if i in (1, 3):
            scan()
        true.rotate_whole("R", 1); know.rotate_whole("R", 1)
    cols, _q = classify({st.id: st.rgb for st in know.stickers}, [know.face_stickers(f)[4].id for f in FACES])
    for st in know.stickers:
        st.color = cols[st.id]
    diff = sum(a != b for f in FACES for a, b in zip(know.facelets()[f], true.facelets()[f]))
    if diff:
        bad_runs += 1
        bad_fields += diff
print(f"{n} Würfel, Farbstreuung {spread:g}: {bad_runs} fehlerhafte Scans, {bad_fields} falsche Felder")
