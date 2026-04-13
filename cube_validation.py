def ensure_grid_shape(grid3x3, face_letter):
    if len(grid3x3) != 3 or any(len(row) != 3 for row in grid3x3):
        raise ValueError(f"Gesicht {face_letter}: Ungueltige 3x3-Datenstruktur beim Anwenden des Scans.")


def validate_face_grid(face_letter, grid3x3):
    ensure_grid_shape(grid3x3, face_letter)
    unknown_cells = []
    for r in range(3):
        for c in range(3):
            if grid3x3[r][c] == "?":
                unknown_cells.append(f"Zeile {r + 1}, Spalte {c + 1}")
    if unknown_cells:
        cells = ", ".join(unknown_cells)
        raise ValueError(
            f"Gesicht {face_letter}: Diese Sticker konnten nicht erkannt werden: {cells}. "
            f"Lege die ganze Seite ruhig, mittig und ohne Reflexionen ins Raster."
        )


def validate_cube_string(cube_string):
    if len(cube_string) != 54:
        raise ValueError(
            f"Ungueltiger Cube-String: erwartet 54 Zeichen, erhalten {len(cube_string)}."
        )

    allowed = set("URFDLB")
    unknown = sorted({ch for ch in cube_string if ch not in allowed})
    if unknown:
        joined = ", ".join(unknown)
        raise ValueError(f"Ungueltiger Cube-String: ungueltige Zeichen gefunden: {joined}.")

    counts = {face: cube_string.count(face) for face in allowed}
    wrong_counts = [f"{face}={count}x" for face, count in sorted(counts.items()) if count != 9]
    if wrong_counts:
        raise ValueError(
            "Ungueltiger Cube-String: jede Farbe muss 9x vorkommen, aktuell "
            + ", ".join(wrong_counts)
            + "."
        )
