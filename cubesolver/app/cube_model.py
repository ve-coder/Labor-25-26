"""Würfelmodell mit 54 Stickern im Raum.

Koordinaten: x zeigt nach rechts (R), y nach oben (U), z nach vorne (F).
Jeder Sticker hat eine feste ID, eine Position (Würfelchen, Werte -1/0/1)
und eine Normale (zeigt aus der Fläche heraus). Drehungen bewegen Position
und Normale. So weiß das Modell jederzeit, welcher Sticker gerade wo ist –
auch nach Drehungen des ganzen Würfels während des Scans.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

FACES = ["U", "R", "F", "D", "L", "B"]  # Kociemba-Reihenfolge

NORMALS = {
    "U": (0, 1, 0),
    "D": (0, -1, 0),
    "R": (1, 0, 0),
    "L": (-1, 0, 0),
    "F": (0, 0, 1),
    "B": (0, 0, -1),
}
AXIS_OF = {"R": "x", "L": "x", "U": "y", "D": "y", "F": "z", "B": "z"}

# Farbe des Mittelsteins im gelösten Standardwürfel (nur für Simulation/Anzeige)
DEFAULT_SCHEME = {"U": "W", "D": "Y", "F": "G", "B": "B", "R": "R", "L": "O"}

COLOR_HEX = {
    "W": "#f4f4f0",
    "Y": "#f2d230",
    "R": "#c8312c",
    "O": "#ee7d22",
    "G": "#2f9e4a",
    "B": "#1f5fc4",
    None: "#8a8a85",
}


def face_of_normal(n):
    for f, v in NORMALS.items():
        if v == tuple(n):
            return f
    raise ValueError(n)


def facelet_index(face: str, pos) -> int:
    """Index 0..8 eines Stickers in der Standard-Netzansicht (wie Kociemba)."""
    x, y, z = pos
    if face == "U":
        row, col = z + 1, x + 1
    elif face == "D":
        row, col = 1 - z, x + 1
    elif face == "F":
        row, col = 1 - y, x + 1
    elif face == "B":
        row, col = 1 - y, 1 - x
    elif face == "R":
        row, col = 1 - y, 1 - z
    elif face == "L":
        row, col = 1 - y, z + 1
    else:
        raise ValueError(face)
    return row * 3 + col


def position_of(face: str, index: int):
    """Umkehrung von facelet_index: Würfelchen-Position eines Netz-Feldes."""
    row, col = divmod(index, 3)
    if face == "U":
        return (col - 1, 1, row - 1)
    if face == "D":
        return (col - 1, -1, 1 - row)
    if face == "F":
        return (col - 1, 1 - row, 1)
    if face == "B":
        return (1 - col, 1 - row, -1)
    if face == "R":
        return (1, 1 - row, 1 - col)
    if face == "L":
        return (-1, 1 - row, col - 1)
    raise ValueError(face)


def _rot(v, axis: str, quarter: int):
    """Dreht Vektor v um axis um quarter * 90° (positiv = gegen den Uhrzeigersinn
    von der positiven Achse aus gesehen)."""
    x, y, z = v
    for _ in range(quarter % 4):
        if axis == "x":
            x, y, z = x, -z, y
        elif axis == "y":
            x, y, z = z, y, -x
        else:
            x, y, z = -y, x, z
    return (x, y, z)


@dataclass
class Sticker:
    id: int
    pos: tuple
    normal: tuple
    color: str | None = None  # erkannte Farbe (W/Y/R/O/G/B) oder None
    rgb: tuple | None = None  # gemessener Farbwert


@dataclass
class CubeModel:
    stickers: list = field(default_factory=list)

    @classmethod
    def blank(cls) -> "CubeModel":
        stickers = []
        i = 0
        for face in FACES:
            for idx in range(9):
                stickers.append(Sticker(i, position_of(face, idx), NORMALS[face]))
                i += 1
        return cls(stickers)

    @classmethod
    def solved(cls, scheme=None) -> "CubeModel":
        scheme = scheme or DEFAULT_SCHEME
        c = cls.blank()
        for s in c.stickers:
            s.color = scheme[face_of_normal(s.normal)]
        return c

    def copy(self) -> "CubeModel":
        return CubeModel([Sticker(s.id, s.pos, s.normal, s.color, s.rgb) for s in self.stickers])

    # ------------------------------------------------------------ Bewegungen
    def turn_layer(self, face: str, quarters: int):
        """Dreht die Schicht 'face' um quarters Vierteldrehungen im Uhrzeigersinn,
        gesehen von außen auf diese Fläche."""
        n = NORMALS[face]
        axis = AXIS_OF[face]
        sign = n[0] + n[1] + n[2]
        q = (-quarters * sign) % 4
        for s in self.stickers:
            if sum(a * b for a, b in zip(s.pos, n)) == 1:
                s.pos = _rot(s.pos, axis, q)
                s.normal = _rot(s.normal, axis, q)

    def rotate_whole(self, face: str, quarters: int):
        """Dreht den ganzen Würfel so, als ob 'face' im Uhrzeigersinn gedreht würde."""
        n = NORMALS[face]
        axis = AXIS_OF[face]
        sign = n[0] + n[1] + n[2]
        q = (-quarters * sign) % 4
        for s in self.stickers:
            s.pos = _rot(s.pos, axis, q)
            s.normal = _rot(s.normal, axis, q)

    def apply_moves(self, moves):
        for m in parse_moves(moves) if isinstance(moves, str) else moves:
            face, q = m
            self.turn_layer(face, q)

    def scramble(self, n=25, rng=None):
        rng = rng or random.Random()
        moves = []
        last = None
        for _ in range(n):
            f = rng.choice([f for f in FACES if f != last])
            q = rng.choice([1, 2, 3])
            moves.append((f, q))
            last = f
        self.apply_moves(moves)
        return format_moves(moves)

    # ------------------------------------------------------------ Abfragen
    def face_stickers(self, face: str):
        """Die 9 Sticker der Fläche an Position 'face', sortiert nach Netz-Index."""
        n = NORMALS[face]
        out = [None] * 9
        for s in self.stickers:
            if s.normal == n:
                out[facelet_index(face, s.pos)] = s
        return out

    def facelets(self):
        """Farben aller Flächen: {"U": [9 Farben], ...} (None = unbekannt)."""
        return {f: [s.color for s in self.face_stickers(f)] for f in FACES}

    def is_complete(self):
        return all(s.color for s in self.stickers)

    def is_solved(self):
        return all(len(set(cols)) == 1 for cols in self.facelets().values())

    def center_colors(self):
        return {f: self.face_stickers(f)[4].color for f in FACES}

    def kociemba_string(self) -> str:
        """Kociemba-String bezogen auf die aktuelle Lage im Gerät.
        Die Farbe des Mittelsteins legt fest, welche Fläche welche Farbe hat –
        deshalb ist die Lage beim Einlegen egal."""
        centers = self.center_colors()
        if None in centers.values():
            raise ValueError("Nicht alle Mittelsteine sind bekannt")
        if len(set(centers.values())) != 6:
            raise ValueError("Mittelsteine haben doppelte Farben: %s" % centers)
        color_to_face = {c: f for f, c in centers.items()}
        out = []
        for f in FACES:
            for s in self.face_stickers(f):
                if s.color not in color_to_face:
                    raise ValueError(f"Unbekannte Farbe {s.color} auf {f}")
                out.append(color_to_face[s.color])
        return "".join(out)

    def to_json(self):
        return {"facelets": self.facelets(), "complete": self.is_complete()}


def parse_moves(text: str):
    """'R U2 F'' -> [("R",1),("U",2),("F",3)]"""
    out = []
    for tok in text.split():
        face = tok[0]
        if face not in NORMALS:
            raise ValueError(f"Unbekannter Zug {tok}")
        if tok.endswith("2"):
            q = 2
        elif tok.endswith("'"):
            q = 3
        else:
            q = 1
        out.append((face, q))
    return out


def format_moves(moves) -> str:
    return " ".join(f + {1: "", 2: "2", 3: "'"}[q % 4] for f, q in moves if q % 4)
