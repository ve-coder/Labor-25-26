"""Prüfung des Würfelzustands und Lösung mit Kociemba."""
from __future__ import annotations

from collections import Counter

from .cube_model import parse_moves

try:
    import kociemba
except Exception:  # pragma: no cover
    kociemba = None


class CubeStateError(ValueError):
    pass


def validate(cube_string: str):
    if len(cube_string) != 54:
        raise CubeStateError(f"Erwartet 54 Felder, erhalten {len(cube_string)}")
    counts = Counter(cube_string)
    bad = {k: v for k, v in counts.items() if v != 9}
    if bad:
        raise CubeStateError(f"Jede Farbe muss 9-mal vorkommen: {dict(counts)}")


def solve(cube_string: str):
    """Liefert (Lösungstext, [(Fläche, Vierteldrehungen), ...])."""
    if kociemba is None:
        raise RuntimeError("kociemba ist nicht installiert (pip install kociemba)")
    validate(cube_string)
    if cube_string == "".join(f * 9 for f in "URFDLB"):
        return "", []
    try:
        text = kociemba.solve(cube_string)
    except ValueError as e:
        raise CubeStateError(
            "Kociemba findet keine Lösung – vermutlich ist eine Farbe falsch erkannt "
            "oder der Würfel ist beim Umsetzen verrutscht"
        ) from e
    return text, parse_moves(text)
