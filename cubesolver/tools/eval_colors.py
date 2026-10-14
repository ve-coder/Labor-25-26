#!/usr/bin/env python3
"""Prüft die Farberkennung gegen alle gespeicherten Referenz-Datensätze.

Jeder Datensatz (data/dataset/<name>/labels.json) enthält die Messwerte der
54 Felder, die richtigen Farben (vom Menschen geprüft/korrigiert) und die
Rohbilder der 6 Scans.

  python tools/eval_colors.py               Klassifizierung mit den gespeicherten Messwerten
  python tools/eval_colors.py --resample    Messwerte neu aus den Bildern berechnen
                                            (prüft auch Raster/Messfeld-Änderungen in vision.py)
  python tools/eval_colors.py --current     wie --resample, aber mit den aktuellen Einstellungen
                                            (Raster, Messfeld) statt denen beim Aufnehmen
  python tools/eval_colors.py --json        Ergebnis maschinenlesbar

Regel beim Verbessern: Eine Änderung ist nur gut, wenn die Gesamtzahl der
Fehler sinkt und kein Datensatz schlechter wird.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import vision  # noqa: E402
from app.config import DATA_DIR, Settings  # noqa: E402

COLORS = ["W", "Y", "R", "O", "G", "B"]


def load_sets(folder: Path):
    for f in sorted(folder.glob("*/labels.json")):
        yield f.parent, json.loads(f.read_text())


def resample(folder: Path, data: dict, settings: dict):
    rgb = {}
    for scan in data["scans"]:
        img = cv2.imread(str(folder / scan["image"]))
        if img is None:
            raise FileNotFoundError(folder / scan["image"])
        frame = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)  # Bild ist bereits gedreht/gespiegelt gespeichert
        for sid, val in zip(scan["stickers"], vision.sample_grid(frame, settings)):
            rgb[sid] = val
    return rgb


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--resample", action="store_true")
    ap.add_argument("--current", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dir", default=str(DATA_DIR / "dataset"))
    args = ap.parse_args()
    folder = Path(args.dir)
    sets = list(load_sets(folder))
    if not sets:
        print(f"Keine Datensätze in {folder}. Zuerst scannen und in der Oberfläche „Als Referenz speichern“.")
        return 1
    current = Settings().values if args.current else None

    total = wrong = 0
    confusion = Counter()
    per_set = []
    mistakes = []
    for d, data in sets:
        if args.resample or args.current:
            s = dict(data["settings"])
            if current:
                s.update({k: current[k] for k in s if k in current})
            rgb = resample(d, data, s)
        else:
            rgb = {x["id"]: tuple(x["rgb"]) for x in data["stickers"]}
        pred, quality = vision.classify(rgb, data["center_ids"])
        n_wrong = 0
        for x in data["stickers"]:
            if x["id"] in data["center_ids"]:
                continue
            total += 1
            p = pred[x["id"]]
            confusion[(x["color"], p)] += 1
            if p != x["color"]:
                wrong += 1
                n_wrong += 1
                mistakes.append({"set": data["name"], "field": f'{x["face"]}{x["index"] + 1}',
                                 "true": x["color"], "pred": p, "rgb": [round(v) for v in rgb[x["id"]]]})
        per_set.append({"set": data["name"], "wrong": n_wrong, "quality": round(quality, 1),
                        "note": data.get("note", "")})

    result = {
        "datasets": len(sets), "fields": total, "wrong": wrong,
        "accuracy": round(100 * (total - wrong) / total, 2) if total else None,
        "per_set": per_set, "mistakes": mistakes,
        "confusion": {f"{a}->{b}": n for (a, b), n in sorted(confusion.items()) if a != b},
    }
    if args.json:
        print(json.dumps(result, indent=1))
        return 0

    print(f"Datensätze: {len(sets)}   Felder (ohne Mittelsteine): {total}   "
          f"Fehler: {wrong}   Trefferquote: {result['accuracy']} %")
    print("\nPro Datensatz:")
    for r in per_set:
        print(f"  {r['set']:<20} Fehler {r['wrong']:>2}   Abweichung {r['quality']:>5}  {r['note']}")
    print("\nVerwechslungen (richtig -> erkannt):")
    print("      " + "  ".join(f"{c:>3}" for c in COLORS))
    for a in COLORS:
        print(f"  {a:>3} " + "  ".join(f"{confusion[(a, b)]:>3}" if a != b else "  ·" for b in COLORS))
    if mistakes:
        print("\nFalsch erkannte Felder:")
        for m in mistakes[:60]:
            print(f"  {m['set']}  {m['field']:<4} richtig {m['true']}  erkannt {m['pred']}  RGB {m['rgb']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
