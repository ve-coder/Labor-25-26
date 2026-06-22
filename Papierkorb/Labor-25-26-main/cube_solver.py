from cube_validation import validate_cube_string

try:
    import kociemba
except Exception:
    kociemba = None


def solve_cube_string(cube_string):
    if kociemba is None:
        raise RuntimeError("Der Solver kociemba ist nicht installiert. Installiere ihn mit: pip install kociemba")

    validate_cube_string(cube_string)
    solution = kociemba.solve(cube_string)
    raw_moves = solution.split()

    expanded = []
    for move in raw_moves:
        if "2" in move:
            single = move.replace("2", "")
            expanded.append(single)
            expanded.append(single)
        else:
            expanded.append(move)

    return solution, expanded
