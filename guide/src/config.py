# Desk Buddy assembly guide - build settings.
#
# This is the ONE place for the things that change between rebuilds:
#   * IMG_DIR      - the folder of SolidWorks renders. New renders: point this at the new folder
#                    (or overwrite the files in it) and run `python guide/build.py`.
#   * COLOURS      - the colour names used everywhere in the guide text, tables and labels.
#                    The step text never says a colour word; it says {{white}}, {{graphite}} or
#                    {{black}} and the build swaps in the names below.
#   * MASK_PARTS   - which flat ID colour in each label-mask picture is which part (see REBUILD.md).
import os

GUIDE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))     # ...\RobotCompanion\guide
PROJECT = os.path.dirname(GUIDE)                                         # ...\RobotCompanion

# ---- images (single setting) -------------------------------------------------------------------
IMG_DIR = os.path.join(PROJECT, 'cad', 'print_v3_1_png')
MASK_DIR = os.path.join(IMG_DIR, 'label masks (flat colours used to place the labels)')

# ---- colour names (single setting) -------------------------------------------------------------
# Keys are the CAD colours the parts were designed in; 'name' is what the guide calls them.
# Owner decision 28 Sep 2026: cream and brown "puppy colours". Which part gets which colour is
# still open (OPEN_QUESTIONS.md), so for now every white part is cream and every graphite part brown.
COLOURS = {
    'white':    {'name': 'cream', 'hex': '#E9DCC3'},
    'graphite': {'name': 'brown', 'hex': '#6B4A35'},
    'black':    {'name': 'black', 'hex': '#1E1E1E'},
}
# Which colour each printed part is (first matching file-name pattern wins). The parts tables and the views
# drawn from the STLs both use this. Change it here when the cream / brown split is decided.
PART_COLOUR_RULES = [
    ('Cap_*', 'black'), ('Port_*', 'black'), ('Screw_Plugs*', 'black'), ('Screen_Washers*', 'black'),
    ('Torso_Lid*', 'white'), ('Head_*', 'white'), ('Muzzle*', 'white'), ('Ear_*', 'white'), ('Tail*', 'white'),
    ('*_Outer*', 'white'),
    ('*', 'graphite'),   # tub, bands, side panels, battery door and clamp, collar, leg covers, wheels
]


def part_colour(file_name):
    import fnmatch
    return next(key for pat, key in PART_COLOUR_RULES if fnmatch.fnmatch(file_name, pat))


# True while the pictures are still the first renders (warm white / graphite). The guide then
# prints RENDER_NOTE on the "How to read this guide" page. Set False after the re-render.
RENDERS_SHOW_OLD_COLOURS = True
RENDER_NOTE = ('Most pictures in this edition were rendered before the colours were chosen, so they show the parts '
               'in off-white and dark grey; the plainer views drawn straight from the print files already use the new '
               'colours. Print the off-white parts in {white} and the dark grey parts in {graphite}. The small caps and '
               'covers stay {black}.')

# ---- document -------------------------------------------------------------------------------------
TITLE = 'Desk Buddy'
SUBTITLE = 'Assembly Guide'
VERSION = 'v3.1'
EDITION = 'October 2026'
OUTPUT_PDF = os.path.join(GUIDE, 'Desk Buddy Assembly Guide v3.1.pdf')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

# ---- label masks ----------------------------------------------------------------------------------
# Each section has an "(id colours)" picture (every printed part a flat colour) and an
# "(id colours B - bought)" picture (every labelled bought part a flat colour, the rest grey).
# They were rendered with a slightly different zoom from the real pictures; imgprep.py lines them
# up automatically (scale + shift) and caches the result in src/generated/registration.json.
# Values are the flat RGB colour of each part in those pictures (found with
# `python guide/tools/imgprep.py --survey`, which writes check/mask_survey_*.png).
MASK_PARTS = {
    '1 Body': {
        'printed': {
            'Torso_Bottom': (25, 60, 230), 'Side_Panel_Left': (220, 0, 220), 'Side_Panel_Right': (255, 120, 0),
            'Battery_Door': (230, 200, 0), 'Band_Chest': (0, 200, 220), 'Band_Rump': (25, 180, 25),
            'Battery_Clamp': (255, 44, 44),
        },
        'bought': {
            '2x18650 holder': (255, 0, 255), 'PCA9685 (left)': (0, 0, 255), 'KCD1 switch': (255, 0, 0),
            'USB-C charger': (255, 255, 0), 'hip MG90S': (0, 255, 0),
        },
    },
    '2 Lid': {
        'printed': {'Torso_Lid': (230, 25, 25), 'Tail_Root': (25, 60, 230), 'Tail': (25, 180, 25),
                    'Cap_Tail': (230, 200, 0)},
        'bought': {'perfboard hub': (255, 0, 0), 'tail MG90S': (0, 255, 255), 'MPU6050': (255, 255, 0),
                   'MPR121': (0, 0, 255), 'side VL53L0X': (0, 255, 0)},
    },
    '3 Head': {
        'printed': {'Head_Front': (120, 220, 0), 'Head_Back': (25, 180, 25), 'Muzzle': (230, 200, 0),
                    'Collar': (0, 200, 220), 'Ear_Right': (255, 0, 120), 'Ear_Left': (0, 130, 255),
                    'Port_Door_Head': (25, 60, 230), 'Port_Blank_Head': (220, 0, 220),
                    'Port_Door_Muzzle': (230, 25, 25), 'Port_Blank_Muzzle': (255, 120, 0)},
        'bought': {'Guition screen': (0, 255, 255), 'ESP32-S3 CAM board': (0, 255, 0),
                   'speaker': (255, 255, 0), 'MS3625 mic': (255, 0, 0)},
    },
    '4 Leg': {
        'printed': {'Thigh_Outer': (230, 200, 0), 'Thigh_Cover': (230, 25, 25), 'Shin_Outer': (0, 200, 220),
                    'Shin_Cover': (25, 180, 25), 'Wheel': (220, 0, 220), 'Cap_Wheel': (120, 0, 230),
                    'Cap_Hip': (40, 97, 255), 'Cap_Knee': (255, 193, 0)},
        'bought': {'hip MG90S': (255, 255, 0), 'knee MG90S': (0, 255, 0), 'wheel MG90S 360': (0, 255, 255),
                   'O-ring tyre': (255, 0, 0)},
    },
}
