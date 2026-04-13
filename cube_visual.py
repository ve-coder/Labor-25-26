from ursina import Entity, Vec3, color, distance, invoke, scene

from cube_config import UPPER_TO_CODE


class CubeVisualizer:
    def __init__(self):
        self.cubes = []
        self.stickers = []
        self.pivot = Entity()
        self.action_mode = False
        self.move_delay = 0.20
        self._create_cube()

    def _create_cube(self):
        cols = {
            "y": color.yellow,
            "w": color.white,
            "r": color.red,
            "o": color.orange,
            "g": color.green,
            "b": color.blue,
        }

        for x in range(-1, 2):
            for y in range(-1, 2):
                for z in range(-1, 2):
                    parent = Entity(model="cube", color=color.black, position=(x, y, z), scale=0.95)
                    parent.collider = "box"

                    def make_sticker(pos, rot, col_key):
                        sticker = Entity(
                            parent=parent,
                            model="quad",
                            color=cols[col_key],
                            position=pos,
                            rotation=rot,
                            scale=0.9,
                            double_sided=True,
                            unlit=True,
                        )
                        sticker.color_code = col_key
                        self.stickers.append(sticker)

                    if x == 1:
                        make_sticker((0.51, 0, 0), (0, 90, 0), "r")
                    if x == -1:
                        make_sticker((-0.51, 0, 0), (0, -90, 0), "o")
                    if y == 1:
                        make_sticker((0, 0.51, 0), (-90, 0, 0), "y")
                    if y == -1:
                        make_sticker((0, -0.51, 0), (90, 0, 0), "w")
                    if z == -1:
                        make_sticker((0, 0, -0.51), (0, 0, 0), "g")
                    if z == 1:
                        make_sticker((0, 0, 0.51), (0, 180, 0), "b")

                    self.cubes.append(parent)

    def reset_action_mode(self):
        for cube in self.cubes:
            cube.world_parent = scene
        self.action_mode = False

    def rotate_side(self, side_name, direction, speed=0.2):
        if side_name not in ["U", "D", "L", "R", "F", "B"]:
            raise ValueError(f"Ungueltiger Zug: {side_name}. Erwartet ist einer von U, D, L, R, F oder B.")
        if direction not in (-1, 1):
            raise ValueError(f"Ungueltige Drehrichtung fuer Zug {side_name}: {direction}. Erwartet ist -1 oder 1.")

        self.action_mode = True

        axis = "y"
        level = 0
        if side_name == "U":
            axis, level = "y", 1
        elif side_name == "D":
            axis, level = "y", -1
        elif side_name == "L":
            axis, level = "x", -1
        elif side_name == "R":
            axis, level = "x", 1
        elif side_name == "F":
            axis, level = "z", -1
        elif side_name == "B":
            axis, level = "z", 1

        rot_dir = direction
        if side_name in ["B", "L", "D"]:
            rot_dir *= -1

        selected = [
            cube
            for cube in self.cubes
            if (axis == "x" and round(cube.world_x) == level)
            or (axis == "y" and round(cube.world_y) == level)
            or (axis == "z" and round(cube.world_z) == level)
        ]

        self.pivot.position = (0, 0, 0)
        self.pivot.rotation = (0, 0, 0)
        for cube in selected:
            cube.world_parent = self.pivot

        angle = 90 * rot_dir

        if speed == 0:
            if axis == "x":
                self.pivot.rotation_x += angle
            elif axis == "y":
                self.pivot.rotation_y += angle
            elif axis == "z":
                self.pivot.rotation_z += angle
            for cube in self.cubes:
                cube.world_parent = scene
            self.action_mode = False
        else:
            if axis == "x":
                self.pivot.animate_rotation_x(angle, duration=speed)
            elif axis == "y":
                self.pivot.animate_rotation_y(angle, duration=speed)
            elif axis == "z":
                self.pivot.animate_rotation_z(angle, duration=speed)
            invoke(self.reset_action_mode, delay=speed + 0.05)

    def get_sticker_entity_at(self, pos, tolerance=0.4):
        for sticker in self.stickers:
            if distance(sticker.world_position, pos) < tolerance:
                return sticker
        return None

    def scan_cube_state(self):
        raw_state = ""

        for z in [1, 0, -1]:
            for x in [-1, 0, 1]:
                sticker = self.get_sticker_entity_at(Vec3(x, 1.5, z))
                raw_state += sticker.color_code if sticker else "y"
        for y in [1, 0, -1]:
            for z in [-1, 0, 1]:
                sticker = self.get_sticker_entity_at(Vec3(1.5, y, z))
                raw_state += sticker.color_code if sticker else "y"
        for y in [1, 0, -1]:
            for x in [-1, 0, 1]:
                sticker = self.get_sticker_entity_at(Vec3(x, y, -1.5))
                raw_state += sticker.color_code if sticker else "y"
        for z in [-1, 0, 1]:
            for x in [-1, 0, 1]:
                sticker = self.get_sticker_entity_at(Vec3(x, -1.5, z))
                raw_state += sticker.color_code if sticker else "y"
        for y in [1, 0, -1]:
            for z in [1, 0, -1]:
                sticker = self.get_sticker_entity_at(Vec3(-1.5, y, z))
                raw_state += sticker.color_code if sticker else "y"
        for y in [1, 0, -1]:
            for x in [1, 0, -1]:
                sticker = self.get_sticker_entity_at(Vec3(x, y, 1.5))
                raw_state += sticker.color_code if sticker else "y"

        translation_map = {
            "y": "U",
            "w": "D",
            "r": "R",
            "o": "L",
            "g": "F",
            "b": "B",
            "?": "?",
        }
        return "".join(translation_map.get(ch, "?") for ch in raw_state)

    def face_positions(self, face_letter):
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
        else:
            raise ValueError(f"Unbekannte Seite {face_letter}. Erwartet ist U, R, F, D, L oder B.")
        return pos

    def apply_face_to_ursina(self, face_letter, grid3x3_upper):
        cols = {
            "y": color.yellow,
            "w": color.white,
            "r": color.red,
            "o": color.orange,
            "g": color.green,
            "b": color.blue,
        }

        positions = self.face_positions(face_letter)
        i = 0
        for r in range(3):
            for c in range(3):
                ch = grid3x3_upper[r][c]
                code = UPPER_TO_CODE.get(ch)
                if code is None:
                    raise ValueError(
                        f"Gesicht {face_letter}: Unbekannte Kamerafarbe {ch} an Zeile {r + 1}, Spalte {c + 1}."
                    )
                sticker = self.get_sticker_entity_at(positions[i], tolerance=0.45)
                if sticker:
                    sticker.color_code = code
                    sticker.color = cols.get(code, color.yellow)
                else:
                    raise ValueError(f"Gesicht {face_letter}: Kein Sticker an Position {i + 1} gefunden.")
                i += 1
