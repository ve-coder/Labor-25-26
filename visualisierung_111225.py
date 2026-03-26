from ursina import *
import random
import time

# Bibliothek prüfen
try:
    import kociemba
except ImportError:
    print("BITTE INSTALLIEREN: Gehe in Thonny auf Extras -> Pakete verwalten -> Suche 'kociemba' -> Installieren")
    raise SystemExit

app = Ursina()
window.title = "Rubiks Cube - Color Codes (y,r,b,o,g,w)"
window.borderless = False
window.size = (1000, 800)
window.color = color.gray

EditorCamera()

# ==========================================
#              KONFIGURATION
# ==========================================

cubes = [] 
stickers = [] 
pivot = Entity()
action_mode = False

# Lösungsvariablen
solution_moves = []
next_move_time = 0
move_delay = 0.25 

# ==========================================
#              WÜRFEL BAUEN
# ==========================================

def create_cube():
    # HIER SIND JETZT DEINE FARBCODES
    cols = {
        'y': color.yellow,
        'w': color.white, 
        'r': color.red,
        'o': color.orange,
        'g': color.green,
        'b': color.blue
    }

    for x in range(-1, 2):
        for y in range(-1, 2):
            for z in range(-1, 2):
                parent = Entity(model='cube', color=color.black, position=(x,y,z), scale=0.95)
                parent.collider = 'box'
                
                def make_sticker(pos, rot, col_key):
                    s = Entity(parent=parent, model='quad', color=cols[col_key],
                           position=pos, rotation=rot, scale=0.9, double_sided=True, unlit=True)
                    s.color_code = col_key 
                    stickers.append(s)

                # Standard Western Color Scheme Zuordnung
                if x == 1:  make_sticker((0.51, 0, 0), (0, 90, 0), 'r')   # Rechts = Rot
                if x == -1: make_sticker((-0.51, 0, 0), (0, -90, 0), 'o') # Links = Orange
                if y == 1:  make_sticker((0, 0.51, 0), (-90, 0, 0), 'y')  # Oben = Gelb
                if y == -1: make_sticker((0, -0.51, 0), (90, 0, 0), 'w')  # Unten = Weiß
                if z == -1: make_sticker((0, 0, -0.51), (0, 0, 0), 'g')   # Vorne = Grün
                if z == 1:  make_sticker((0, 0, 0.51), (0, 180, 0), 'b')  # Hinten = Blau
                
                cubes.append(parent)

create_cube()

# ==========================================
#              LOGIK
# ==========================================

def rotate_side(side_name, direction, speed=0.2):
    global action_mode
    action_mode = True
    
    # Mapping für Rotation bleibt technisch (U,D,R,L,F,B)
    axis = 'y'
    level = 0
    if side_name == 'U': axis, level = 'y', 1
    elif side_name == 'D': axis, level = 'y', -1
    elif side_name == 'L': axis, level = 'x', -1
    elif side_name == 'R': axis, level = 'x', 1
    elif side_name == 'F': axis, level = 'z', -1
    elif side_name == 'B': axis, level = 'z', 1

    rot_dir = direction
    if side_name in ['B', 'L', 'D']: rot_dir *= -1 
    
    selected = [c for c in cubes if 
                (axis=='x' and round(c.world_x)==level) or
                (axis=='y' and round(c.world_y)==level) or
                (axis=='z' and round(c.world_z)==level)]
    
    pivot.position = (0,0,0)
    pivot.rotation = (0,0,0)
    for c in selected: c.world_parent = pivot
    
    angle = 90 * rot_dir
    
    if speed == 0:
        if axis == 'x': pivot.rotation_x += angle
        elif axis == 'y': pivot.rotation_y += angle
        elif axis == 'z': pivot.rotation_z += angle
        for c in cubes: c.world_parent = scene
        action_mode = False
    else:
        if axis == 'x': pivot.animate_rotation_x(angle, duration=speed)
        elif axis == 'y': pivot.animate_rotation_y(angle, duration=speed)
        elif axis == 'z': pivot.animate_rotation_z(angle, duration=speed)
        invoke(reset_action_mode, delay=speed + 0.05)

def reset_action_mode():
    global action_mode
    for c in cubes: c.world_parent = scene
    action_mode = False

# ==========================================
#              SCANNER & SOLVER
# ==========================================

def get_sticker_at(pos, tolerance=0.4):
    for s in stickers:
        if distance(s.world_position, pos) < tolerance: return s.color_code
    return 'y' # Fallback auf Gelb

def scan_cube_state():
    # Wir scannen die Farben (y, r, g...)
    raw_state = ""
    for z in [1, 0, -1]:
        for x in [-1, 0, 1]: raw_state += get_sticker_at(Vec3(x, 1.5, z))
    for y in [1, 0, -1]:
        for z in [-1, 0, 1]: raw_state += get_sticker_at(Vec3(1.5, y, z))
    for y in [1, 0, -1]:
        for x in [-1, 0, 1]: raw_state += get_sticker_at(Vec3(x, y, -1.5))
    for z in [-1, 0, 1]:
        for x in [-1, 0, 1]: raw_state += get_sticker_at(Vec3(x, -1.5, z))
    for y in [1, 0, -1]:
        for z in [1, 0, -1]: raw_state += get_sticker_at(Vec3(-1.5, y, z))
    for y in [1, 0, -1]:
        for x in [1, 0, -1]: raw_state += get_sticker_at(Vec3(x, y, 1.5))  
    
    # ÜBERSETZUNG: Kociemba versteht nur U,R,F,D,L,B
    # Wir mappen deine Farben auf die Seiten
    # y=Up, w=Down, r=Right, o=Left, g=Front, b=Back
    translation_map = {
        'y': 'U',
        'w': 'D',
        'r': 'R',
        'o': 'L',
        'g': 'F',
        'b': 'B'
    }
    
    # Wir bauen den String um
    translated_state = ""
    for char in raw_state:
        translated_state += translation_map[char]
        
    return translated_state

def solve_cube():
    global solution_moves, next_move_time
    if action_mode: return
    
    try:
        step_text.text = "Berechne..."
        
        # Scannen und Übersetzen
        cube_string = scan_cube_state()
        print(f"Status (Übersetzt): {cube_string}")
        
        # Lösen
        solution_str = kociemba.solve(cube_string)
        print(f"Lösung: {solution_str}")
        
        raw_moves = solution_str.split()
        
        # Liste expandieren (U2 -> U, U)
        expanded_moves = []
        for m in raw_moves:
            if '2' in m:
                single = m.replace('2', '')
                expanded_moves.append(single)
                expanded_moves.append(single)
            else:
                expanded_moves.append(m)
        
        solution_moves = expanded_moves
        next_move_time = time.time()
        
        step_text.text = f"Schritte: {len(solution_moves)}"
        step_text.color = color.white
        
    except Exception as e:
        print(f"Fehler: {e}")
        step_text.text = "Fehler"
        step_text.color = color.red

# ==========================================
#              UPDATE LOOP
# ==========================================

def finish_visuals():
    step_text.text = "Schritte: 0"
    step_text.color = color.green

def update():
    global next_move_time, solution_moves
    
    if solution_moves and not action_mode and time.time() > next_move_time:
        
        move = solution_moves.pop(0)
        
        step_text.text = f"Schritte: {len(solution_moves)}"
        
        if len(solution_moves) == 0:
            invoke(finish_visuals, delay=move_delay)

        face = move[0]
        direction = 1
        if "'" in move: direction = -1
        
        rotate_side(face, direction, speed=0.2)
            
        next_move_time = time.time() + move_delay

    # Manuelle Steuerung
    if not action_mode and not solution_moves:
        if held_keys['shift']:
            if held_keys['u']: rotate_side('U', -1)
            if held_keys['d']: rotate_side('D', -1)
            if held_keys['r']: rotate_side('R', -1)
            if held_keys['l']: rotate_side('L', -1)
            if held_keys['f']: rotate_side('F', -1)
            if held_keys['b']: rotate_side('B', -1)
        else:
            if held_keys['u']: rotate_side('U', 1)
            if held_keys['d']: rotate_side('D', 1)
            if held_keys['r']: rotate_side('R', 1)
            if held_keys['l']: rotate_side('L', 1)
            if held_keys['f']: rotate_side('F', 1)
            if held_keys['b']: rotate_side('B', 1)

def input(key):
    if key == 'enter':
        solve_cube()
    if key == 'space':
        step_text.text = "Mische..."
        step_text.color = color.white
        
        mvs = ['U','D','R','L','F','B']
        for _ in range(25):
            f = random.choice(mvs)
            d = random.choice([1, -1])
            rotate_side(f, d, speed=0)
        
        step_text.text = "Schritte: 0"

# GUI
Text(text='[Leertaste] = Mischen', position=(-0.85, 0.45), scale=1.2)
Text(text='[ENTER] = Lösen', position=(-0.85, 0.40), scale=1.2, color=color.yellow)

step_text = Text(text='Schritte: 0', position=(-0.85, 0.25), scale=2, color=color.white)

app.run()