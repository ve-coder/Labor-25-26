CV_WINDOW = "Cube Scan (OpenCV)"
GRID_TOTAL = 660
GRID_N = 3
ROI_MARGIN_FRAC = 0.25

CALIB_FILE = "cube_calibration_rgb9.json"

CALIB_ORDER = [
    ("W", "WEISS"),
    ("Y", "GELB"),
    ("R", "ROT"),
    ("O", "ORANGE"),
    ("B", "BLAU"),
    ("G", "GRUEN"),
]

SCAN_ORDER = [
    ("U", "OBEN (U)"),
    ("R", "RECHTS (R)"),
    ("F", "VORNE (F)"),
    ("D", "UNTEN (D)"),
    ("L", "LINKS (L)"),
    ("B", "HINTEN (B)"),
]

TOL = {
    "W": (35, 35, 35),
    "Y": (40, 30, 30),
    "R": (55, 55, 55),
    "O": (55, 55, 55),
    "G": (45, 45, 45),
    "B": (60, 60, 60),
}

DRAW_BGR = {
    "W": (255, 255, 255),
    "Y": (0, 255, 255),
    "R": (0, 0, 255),
    "O": (0, 128, 255),
    "G": (0, 255, 0),
    "B": (255, 0, 0),
    "?": (0, 255, 255),
}

UPPER_TO_CODE = {
    "Y": "y",
    "W": "w",
    "R": "r",
    "O": "o",
    "G": "g",
    "B": "b",
    "?": "y",
}
