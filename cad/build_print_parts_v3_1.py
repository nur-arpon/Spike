"""Desk Buddy robot dog - printable parts VERSION 3.1 (v3 finished, fixed and slimmed; brief: v3_1_BRIEF.md).

v3.1 = a copy of build_print_parts_v3.py (untouched) with these changes, all INSIDE the parts (the outside look,
silhouette and colours are the approved v3):
  * lighter shells: head 2.4 -> 1.6 (screen frame kept 2.4), tub walls 2.4 -> 1.6 (+ hidden windows behind the
    side panels), lid walls 5.1 / 7.4 -> 1.6 above a 1.8 lip, collar 2.4 -> 1.6, muzzle 2.4 -> 1.8, 2 ribs in the
    head back; the perfboard hub 9 mm further back under the lid (balance); local pads keep
    >= 2.0 under every screw head and ear. 1.6 = 4 lines of a 0.4 nozzle: solid with 2 walls, lightest with 3.
  * printed grams come from the EXPORTED STL through a slicer model (swlib_v3_1.stl_print_estimate, settings in
    swlib_v3_1.SLICER), not from one FILL factor; the balance check uses those grams.
  * tail cap peg 1.2 -> 1.0 (0.6 mm clear of the tail horn), a firmware joint-limit table, labelled exploded
    renders per body section. Output: print_v3_1\\, print_v3_1_stl\\, print_v3_1_png\\, build_v3_1_report.txt.

--- v3 docstring follows ---
Desk Buddy robot dog - printable parts VERSION 3 (covered design, v3_covered_design_proposal.md).

Every part is modelled in ONE global frame (mm): X = the robot's left (+) / right (-), Y = up, Z = forward,
origin at the centre of the torso's bottom face. So the assembly needs no mates: every file is inserted at
the origin and lands in its real place, and every clash can be checked body against body.

Output (owner's folder rule):
    print_v3\\        SolidWorks only  - printed parts, the bought-parts model, the assembly
    print_v3_png\\    pictures
    print_v3_stl\\    STL files for the printer (each one checked against the model after export: size AND volume)

Printed file names: "Printed part (bought parts it holds)".

STATUS (2026-09-26): the whole robot is v3.
  LEGS (sections 1, 2, 5, 7): two-piece clamshell thighs and shins (white outer half + graphite inner cover with
  the knee / paw pod), designed wheels for the 26 x 2.4 O-ring, 13 black hub caps, wires inside, knee cases
  flipped, all paws forward, cross horns everywhere, knee and cap / snap-fit coupons.
  BODY (sections 2-7): tub with R8 chest / rump edges, graphite side panels (4 snap hooks), chest and rump bands
  over the lid screws, belly battery door (4 screws under black plugs), KCD1 flush at the front belly centre,
  raised USB-C charger behind a 13 x 7 pill in the rump band, lid with R6 top, lead combs, tail socket and touch
  ovals, collar, rounded two-part head (5 snap hooks, no screws), bevelled screen frame, flush black port doors
  with matching blanks, muzzle 0.8 forward with identical windows, keyed tapered ears, tail root + tail.

The build report (build_v3_report.txt) checks: one piece per printed part, fits the printer, STL = model, no
solid overlaps anywhere (printed vs bought, bought vs bought), every assembly part in its place, the robot's
centre of mass against its wheel contacts, and the v3 leg clearance sweeps (knee pods vs the belly, paws vs
the desk, paw vs thigh).
"""
import os, sys, math, pythoncom
import swlib_v3_1 as swlib
from swlib_v3_1 import WARM_WHITE, GRAPHITE, BLACK
from win32com.client import VARIANT, Dispatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'print_v3_1')
PNG = os.path.join(HERE, 'print_v3_1_png')
STL = os.path.join(HERE, 'print_v3_1_stl')
REPORT = os.path.join(HERE, 'build_v3_1_report.txt')

# ---------------------------------------------------------------------------------------------
# DESIGN RULES (PLA, Ultimaker 2+ Connect, 0.4 mm nozzle)
W = 2.4          # shell wall
PILOT_R = 1.0    # M2 self-tap pilot: CAD 2.0 mm, prints ~1.6-1.7 mm
BOSS_R = 2.8     # boss OD 5.6
CLEAR_R = 1.3    # M2 clearance: CAD 2.6 mm
CBORE_R = 2.3    # counterbore for the M2 head (head 3.5-4.3 mm)
CBORE_D = 1.3
SLOT_W = 1.8     # horn-screw slots: prints ~1.5 mm, an M2 driven from the horn side bites into it
PLA = 1.24       # g/cm3
FILL = 0.70      # v3.1: MEASURED overall printed / solid with the chosen profile (385.7 / 550.7 g, 2 walls; 0.77
                 # with 3 walls). Information only: every gram in the report comes from the per-part slicer estimate
                 # (see SLICER / printed_grams); v3 guessed 0.75 for every part.
BED = (223.0, 220.0, 205.0)   # Ultimaker 2+ Connect build volume
# v3.1 wall thicknesses (the approved OUTSIDE is unchanged; these move inner faces only)
HEAD_W = 1.6     # head front / back shell (v3 2.4) = 4 lines of 0.4; the screen frame round the window stays 2.4
TUB_W = 1.6      # tub side and end walls (v3 2.4) = 4 lines; the floor stays W = 2.4 (KCD1 recess, door lugs, R8 edges)
LID_WALL = 1.6   # lid side / end walls above the lip (v3 5.1 / 7.4 solid); the lid top stays 2.4
LID_LIP_T = 1.8  # lid locating lip (v3 2.4)
MUZ_W = 1.8      # muzzle side walls and top (floor 2.4 carries the camera board, front 2.4 carries the windows);
                 # 1.8 not 1.6: the top meets the 2.4 front under the R3 round with 1.66 left (1.6 would leave 1.48)
COLLAR_W = 1.6   # collar walls (v3 2.4)
TAIL_CAP_PEG = 1.0   # tail cap split-ring peg length (v3 1.2): 0.6 clear of the tail horn arms
# how each part lies on the printer bed: the build axis (for the printed-mass estimate and the README)
PRINT_AXIS = [('Cap_Tail', 'y'), ('Torso_Bottom', 'y'), ('Side_Panel', 'x'), ('Band_', 'z'), ('Battery_', 'y'),
              ('Screw_Plugs', 'y'), ('Torso_Lid', 'y'), ('Collar', 'y'), ('Head_', 'z'), ('Screen_Washers', 'z'),
              ('Port_', 'x'), ('Muzzle', 'z'), ('Ear_', 'y'), ('Tail', 'y'), ('Thigh_', 'x'), ('Shin_', 'x'),
              ('Wheel_', 'x'), ('Cap_', 'x'), ('Coupon_', 'x'), ('Fit_Test', 'y')]

# ---------------------------------------------------------------------------------------------
# MEASURE ON ARRIVAL - the numbers the fit depends on (research range in brackets)
SV_L = 22.8        # MG90S body length            [22.4-22.8, one clone 23.9]
SV_W = 12.4        # MG90S body width             [12.0-12.7]
SV_SHAFT = 6.0     # shaft centre from shaft end  [5.6-6.4]
SV_TABS = 32.5     # tab tip to tab tip           [32.0-32.6]
SV_TAB_T = 2.8     # tab thickness                [2.4-2.8]
SV_UNDER = 21.0    # case bottom -> tab underside [18.3-21.0]  (worst case: deepest body)
SV_SPLINE = 14.4   # tab underside -> spline top  [14.0-14.4]
SV_HOLES = 28.15   # tab hole spacing             [27.7-28.6]
SV_HOLE_SLOT = 0.45  # pilots are slotted +/- this to take the spread; set 0 once SV_HOLES is measured (thicker web)
SV_TOP_RECT = 4.5  # v3: tab underside -> top of the rectangular gear case   [est. 4-5]
SV_TOP_HUMP = 7.5  # v3: tab underside -> top of the round output boss       [listing: housing 26 - 18.5]
SV_BOSS_R = 5.9    # v3: round output boss radius (dia 11.8)
HORN_OUT = 1.0     # horn outer face above the spline top   [~0.5-1.5, unpublished]
HORN_T = 1.8       # horn arm thickness (pocket depth)      [~1.5-2.0, unpublished]
HORN_W = 6.6       # horn arm pocket width                  [arm 5-6.5 wide at the hub]
HORN_REACH = 17.5  # double-arm horn: centre to tip         [~16-17.5]  (v2 tail only)
CROSS_REACH = 11.5 # cross horn: centre to tip              [~10-11.5]  (v3: every leg joint)
HORN_HUB_R = 4.6   # recess for the horn hub
SCREEN_STACK = 4.5 # Guition glass front -> PCB front       [~4-5, unpublished]
KCD1_X, KCD1_Z = 19.4, 13.0   # rocker cut-out for a 2-3 mm panel (datasheet)
OR_GROOVE_R = 13.9            # v3: wheel groove bottom radius for the 26 mm ID O-ring (+6.9 % stretch)
OR_CS = 2.4                   # O-ring cross-section [2.0-2.65, unpublished]
CAM_L, CAM_H = 57.0, 28.0     # ESP32-S3 CAM board incl. the antenna overhang [57 x 28; PCB alone 51 x 29]
CAM_LENS_X = 16.0             # lens centre from the board's antenna end (camera folded onto the WROOM)
CAM_LENS_Y = 14.0             # lens centre above the board's bottom long edge
CAM_STACK = 10.6              # board front face -> lens-holder front face (WROOM 3.1 + tape 1 + camera ~6.5)
LEAD_D = 2.4                  # v3: MG90S lead twisted into a round bundle [3 wires ~1.1 each; flat ribbon 3.6 x 1.2]
SCREW_HEAD_R, SCREW_HEAD_H = 1.9, 1.6   # M2 pan head [dia 3.5-4.0, 1.3-1.6 tall]

# ---------------------------------------------------------------------------------------------
# LAYOUT
TX, TZ = 42.0, 80.0          # torso half-width, half-length (outer)
TUB_IN, TUB_INZ = TX - TUB_W, TZ - TUB_W     # v3.1 tub inner faces |x| 40.4, |z| 78.4 (v3 39.6, 77.6)
TUB_WIN = (23.0, 7.0, 29.0)                   # v3.1 side-wall window behind each panel: |z| <= 23, y 7-29, R3
TUB_H, LID_TOP = 36.0, 50.0  # tub top, lid top
LIP_Y0 = 31.2                # bottom of the lid's locating lip (clears the PCA9685 standoffs)
LID_SCREW_Y = 32.5           # lid screws through the tub's front and rear walls
HIP_Y = 18.0                 # hip axis height
# legs: hip |z| and which way the HIP servo case runs from its shaft (-1 = toward -Z). The front hips sit well
# forward (case turned inward) so the feet surround the centre of mass - the heavy head is at the front.
LEGS = {+1: (66.0, -1), -1: (-52.0, -1)}
L1, L2 = 38.0, 45.0          # thigh (hip->knee), shin (knee->wheel axle)
KNEE_Y = HIP_Y - L1          # -20
AXLE_Y = KNEE_Y - L2         # -65
BODY_C = SV_L / 2 - SV_SHAFT # servo case centre is 5.4 mm from its shaft (toward the case)

# joint stack along X: [servo tabs][servo turret][horn][printed plate] ...
HIP_SPLINE = TX + SV_SPLINE                              # 56.4
PLATE_GAP = HORN_OUT - HORN_T                            # plate inner face sits 0.8 below the spline top
THIGH_IN = HIP_SPLINE + PLATE_GAP                        # 55.6
THIGH_OUT = THIGH_IN + 4.0                               # 59.6 (v2 plate; v3 uses THIGH_OUT3)
KNEE_SPLINE = THIGH_IN - SV_TAB_T + SV_SPLINE            # 67.2
SHIN_IN = KNEE_SPLINE + PLATE_GAP                        # 66.4
SHIN_OUT = SHIN_IN + 4.0                                 # 70.4 (v2 plate; v3 uses SHIN_OUT3)
WHEEL_SPLINE = SHIN_IN - SV_TAB_T + SV_SPLINE            # 78.0
WHEEL_IN = WHEEL_SPLINE + PLATE_GAP                      # 77.2
WHEEL_OUT = WHEEL_IN + 8.0                               # 85.2

# ---------------------------------------------------------------------------------------------
# v3 LEGS (v3_covered_design_proposal.md, owner decisions 2026-09-26)
FIT = 0.3            # clearance round a servo's gear case and boss in the outer halves
POD_GAP = 0.4        # side gap round a servo case in its pod
LEAD_GAP = 2.6       # gap at BOTH case ends and under the case bottom: the lead (unknown exit end) runs there
SKIN = 1.8           # printed skin / wall
REVEAL = 0.8         # gap between parts that move against each other
LAP = 0.5            # the white outer half laps this far over the graphite cover (the colour break)
LAP_W = 0.8          # wall of that lap rim
LAP_FIT = 0.1        # gap inside the lap rim
FLANK = TX + SV_TAB_T + 1.6 + 0.4 + SKIN                 # 48.6 side panel outer face (body agent)
HIP_CUP_R = HIP_Y                                        # 18: the cup is dia 36, top at y 36 = the tub top
HIP_CUP_RIM = FLANK + REVEAL                             # 49.4
CUP_SKIRT_IN = 16.3                                      # cup skirt r 16.3-18
THIGH_OUT3 = THIGH_IN + 5.0                              # 60.6 thigh outer face
SHIN_COVER_IN = THIGH_OUT3 + REVEAL                      # 61.4
SHIN_OUT3 = WHEEL_IN - REVEAL                            # 76.4 shin outer face
THIGH_COVER_IN = HIP_CUP_RIM                             # 49.4 thigh cover inner face
KNEE_DRUM_R = 17.0
THIGH_W = 26.0                                           # thigh width at mid-thigh
TAPER_Y = -6.5                                           # where the tapered heel leaves the thigh flank
KNEE_UNDER = THIGH_IN - SV_TAB_T                         # 52.8 knee servo tab underside
WHEEL_UNDER = SHIN_IN - SV_TAB_T                         # 63.6 wheel servo tab underside
POD_Y = SV_W / 2 + POD_GAP + SKIN                        # 8.4
TAB_BAND = (-(SV_TABS / 2 - BODY_C + 2.2), SV_TABS / 2 + BODY_C + 2.2)                 # -13.05 .. 23.85
CASE_BAND = (-(SV_SHAFT + LEAD_GAP + SKIN), SV_L - SV_SHAFT + LEAD_GAP + SKIN)         # -10.4 .. 21.2
CASE_CAV = (-(SV_SHAFT + LEAD_GAP), SV_L - SV_SHAFT + LEAD_GAP)                        # -8.6 .. 19.4
TAB_CAV = (-(SV_TABS / 2 - BODY_C + POD_GAP), SV_TABS / 2 + BODY_C + POD_GAP)          # -11.25 .. 22.05
TAB_HOLES = (BODY_C - SV_HOLES / 2, BODY_C + SV_HOLES / 2)                             # -8.675, 19.475
KNEE_POD_IN = KNEE_UNDER - SV_UNDER - LEAD_GAP - SKIN    # 27.4 (proposal 29.6 + the lead gap)
PAW_POD_IN = WHEEL_UNDER - SV_UNDER - LEAD_GAP - SKIN    # 38.2 (proposal 40.4 + the lead gap)
PAW_BAND_IN = WHEEL_UNDER - SCREW_HEAD_H - 0.2 - SKIN    # 60.0 tab band step (room for the tab screw heads)
KNEE_DZ = {+1: +1, -1: -1}   # knee servo case direction: front legs forward, rear legs rearward
PAW_DZ = +1                  # all paws forward (wheel servo case toward +Z) - confirm the gait.py tilt sign
KNEE_POD_Y = (KNEE_Y - POD_Y - 0.4, KNEE_Y + POD_Y)    # pod bottom 0.4 under the heel underside (clean junction)
KNEE_ROOT_R, PAW_ROOT_R = 2.5, 3.0                      # concave fillet where each pod meets its leg
TAB_CAV_R = 1.5              # tab cavity corners (keeps 1.5 wall under the R4 heel/toe corners): MG90S ear corners
                             # must be rounded >= R1.1 or clipped 1 x 45 deg (MEASURE)
CHAN_W = 6.0                 # wire channel width
RIM_R = 15.35                # wheel rim shoulders
TYRE_R = 16.3                # stretched 26 x 2.4 O-ring on the dia 27.8 groove
DESK_Y = AXLE_Y - TYRE_R     # -81.3
CAP_T, CAP_RECESS = 1.6, 1.2 # hub caps stand 0.4 proud
CAP_R = {'hip': 6.0, 'knee': 6.0, 'wheel': 7.0, 'tail': 6.0}
TAIL_CAP_Y = 50.6            # tail cap seat (floor of the dia 12.2 recess in the tail root)
TAIL_Z = -62.0               # tail servo shaft (case runs forward from it)
# snap hook (on the white outer half, catching in the graphite cover); PLA: length / thickness ~ 7
HOOK_T, HOOK_WID, HOOK_BARB = 1.0, 3.5, 0.4

HEAD = dict(x=63.0, y0=60.0, y1=158.0, z0=36.0, z1=80.0)   # 11 mm above the screen for its top-edge plugs (P7 Speak)
BOARD_Y0 = HEAD['y0'] + W + 12.0                # 74.4  Guition board bottom (12 mm plug zone below)
GLASS_Z = HEAD['z1'] - W                        # 77.6  glass front (touches the front wall)
PCB_FRONT = GLASS_Z - SCREEN_STACK              # 73.1
BACK_SCREW_Z = HEAD['z0'] + W + CBORE_R + 0.8   # 41.5: head back-cover screws (counterbore clears the rear edge)
MIC_Y, MIC_Z = 127.5, 59.5                      # v3: clear of the head split (z 46.5), the back's lip and the port door
NECK = dict(x=20.0, z0=46.0, z1=74.0)
LID_NECK_SCREWS = [(sx * 15.0, z) for sx in (-1, 1) for z in (50.5, 69.5)]   # driven up from inside the lid
HEAD_NECK_SCREWS = [(sx * 6.0, z) for sx in (-1, 1) for z in (50.0, 70.0)]   # driven down from inside the head

# muzzle: shallow and low so it hides as little of the screen as possible from above; the camera board
# stands upright behind the front wall with the camera folded onto its WROOM module.
MUZ = dict(x=38.0, y0=40.0, y1=74.0, z0=80.8, z1=98.3)   # v3: 0.8 forward (even gap to head, collar, lid)
MUZ_FZ = MUZ['z1'] - W                          # 95.9 front wall inner face
CAM_PCB_Z = MUZ_FZ - CAM_STACK                  # 85.3 board front face
CAM_Y0 = MUZ['y0'] + W                          # 42.4 board stands on the muzzle floor
LENS_X = -CAM_L / 2 + CAM_LENS_X                # -12.5 (antenna end at -X, USB-C end at +X)
LENS_Y = CAM_Y0 + CAM_LENS_Y                    # 56.4
APDS_X = -LENS_X                                # v3: +12.5, mirrors the lens
MUZ_SCREWS = [(sx * 31.0, y) for sx in (-1, 1) for y in (68.3, 72.0)]   # v3: on the head's flat face (y >= 68)
MUZ_WIN = (12.2, 9.0, 2.0)                      # v3: camera and gesture windows, identical, 0.5 chamfer

TAIL_Y0 = LID_TOP + SV_SPLINE + PLATE_GAP       # 63.6 tail underside (v2 tail)

BAT_Z = (-52.0, 24.0)                           # 2x18650 holder (76 long)
CLAMP_Z = (-40.0, -30.0)                        # battery clamp bar
KCD1_ZC = 59.7                                  # v3: front belly centre, turned 90 deg (cut-out 13 x 19.4, z 50-69.4)
KCD1_RECESS = 2.2                               # v3: the rocker sits flush in this recess
PROT_Z = (28.0, 48.1)                           # protection board, lying across the floor (48.4 along X)
CLIFF_TILT = 25.0                               # desk-edge lasers look this far ahead of straight down
CLIFF_FRONT_X = (7.5, 32.5)                     # |x| of each front desk-edge board (25 long)
CLIFF_FRONT_Z = 58.0                            # low edge of the front incline
CLIFF_REAR_X = (-12.5, 12.5)                    # v3: centred (the tail servo now hangs over it, 2.6 clear)
CLIFF_REAR_Z = -58.0

# ---------------------------------------------------------------------------------------------
# v3 BODY (proposal sections 2-7)
BELLY_R = 8.0            # chest / rump bottom edges (REQUIRED for the knee pod clearance)
LID_LIP_Z = (72.6, 75.0) # lid lip front / rear segments (inner, outer |z|): clear of the thickened band walls
WALL_THICK_Z = 75.3      # |z| of the tub's inner face behind the bands (wall 4.7 there)
LID_SCREWS = [(sx * 25.0, 1) for sx in (-1, 1)] + [(sx * 12.0, -1) for sx in (-1, 1)]   # (x, front/rear) at y 32.5
BAND = dict(x=36.0, y0=8.6, y1=34.6, r=4.0, t=1.6)      # chest / rump bands (72 x 26 R4, 1.6 in a 1.6 recess)
BAND_GAP = 0.2
LASER_WIN = (10.0, 8.0, 2.0, 22.25)             # obstacle laser window: w, h, r, centre y
BAND_HOOK_X, BAND_HOOK_Y = 30.0, 12.0           # 2 snap hooks per band (beam 0.8 thick, 0.3 barb)
DOOR = dict(x=26.0, z0=-54.0, z1=26.0, r=3.0)   # battery door (belly), 0.2 gap round it
DOOR_SCREWS = [(sx * 23.4, z) for sx in (-1, 1) for z in (-48.0, 18.0)]
DOOR_CBORE_R = 2.1                              # counterbore: black plug 1.0 + M2 pan head 1.6
DOOR_LUG_TOP = 9.4                              # v3.1 tub lugs for the door screws (v3 8.6): M2 x 6 ends 0.8 under the top
PLUG_R, PLUG_T = 2.05, 1.0                      # black plugs over the door screws
CHG_X, CHG_Y0, CHG_Z = (18.5, 36.5), 24.35, (-77.5, -46.5)   # USB-C charger, raised above the rear-left hip servo
USB_X, USB_Y = 27.5, CHG_Y0 + 1.6 + 1.63        # receptacle centre (27.5, 27.58)
USB_PILL = (13.0, 7.0)                          # rump band opening (max plug overmould 12.35 x 6.5)
PANEL_IN, PANEL_SKIN = TX, 46.8                 # side panel: standoff face on the tub wall, skin 46.8-48.6 (as v3)
HUB_DZ = -9.0                                   # v3.1: perfboard hub (22 g) moved 9 mm rearward in the lid (balance);
                                                # it stops 0.7 mm in front of the tail socket boss
PANEL_HOOKS = [(z, y) for z in (38.0, -36.0) for y in (8.0, 22.0)]   # 4 snap hooks per panel (no screws)
PANEL_END_R = 4.0        # plan-view round on the panel ends (R6 would leave 0.7 mm over the front hip tabs)
LEAD_EXIT_Y = (26.6, 29.0)   # hip leads: panel slot 26.5-31.5, tub-wall notch from 26.5 up, comb teeth down to 29.0
HB_SPLIT = 46.5          # head front / back split (the back part carries the whole R10 back perimeter)
EAR = dict(x=41.0, z=61.0, half=11.0, t=10.0, h=34.0, tip=5.0, lean=10.0, edge=2.5, sink=1.0)
TAIL_ROOT = dict(r=13.0, y0=47.2, y1=51.8)      # tail root in the lid socket (dia 27.6, floor at 46.4); 1.6 over the
                                                # horn for the horn-screw head under the cap
TAIL_SOCKET = dict(r=13.8, floor=46.4)
TAIL_UNDER = (-68.5, 51.8)                      # tail underside plane: starts here, rises 20 deg rearward
TAIL_SV_UNDER = 33.6                            # tail MG90S tab underside (hangs from the lid rib)
TAIL_RISE = 20.0
TAIL_SCREW_Z = -71.5
HEAD_DOOR = dict(zc=67.4, yc=113.0)             # screen USB-C port door (18 tall x 12 wide, R6), matching blank on +x
MUZ_DOOR = dict(zc=88.3, yc=56.0)               # camera USB-C port door on +x, matching blank on -x
DOOR_L, DOOR_H = 18.0, 12.0


def rng(a, b):
    return (min(a, b), max(a, b))


# =============================================================================================
# 2D OUTLINES FOR THE LEGS
# A leg outline is a closed tangent chain of lines and circles joined by blend arcs, so one fillet or chamfer
# pick point rounds its whole edge. It is written in the leg's side-view coordinates (a, y): a = distance
# along Z from the joint column (measured in the leg's case direction), y = height. Leg.loop() maps it to (z, y).
# =============================================================================================
def _unit2(v):
    L = math.hypot(v[0], v[1])
    return (v[0] / L, v[1] / L)


def _left(d):
    return (-d[1], d[0])


def _poff(pr, t):
    """Offset a primitive t to its LEFT (the interior of a counter-clockwise outline)."""
    if pr[0] == 'L':
        n = _left(pr[2])
        return ('L', (pr[1][0] + t * n[0], pr[1][1] + t * n[1]), pr[2])
    return ('C', pr[1], pr[2] - pr[3] * t, pr[3])


def _isect(A, B, hint):
    if A[0] == 'L' and B[0] == 'L':
        (p, d), (q, e) = A[1:3], B[1:3]
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            raise ValueError('parallel lines do not meet')
        t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
        cands = [(p[0] + t * d[0], p[1] + t * d[1])]
    elif A[0] == 'C' and B[0] == 'C':
        c1, r1, c2, r2 = A[1], A[2], B[1], B[2]
        dd = math.dist(c1, c2)
        a = (r1 * r1 - r2 * r2 + dd * dd) / (2 * dd)
        h2 = r1 * r1 - a * a
        if h2 < -1e-7:
            raise ValueError('circles do not meet')
        h = math.sqrt(max(h2, 0.0))
        ex = ((c2[0] - c1[0]) / dd, (c2[1] - c1[1]) / dd)
        m = (c1[0] + a * ex[0], c1[1] + a * ex[1])
        cands = [(m[0] - h * ex[1], m[1] + h * ex[0]), (m[0] + h * ex[1], m[1] - h * ex[0])]
    else:
        Lp, Cp = (A, B) if A[0] == 'L' else (B, A)
        p, d, c, r = Lp[1], Lp[2], Cp[1], Cp[2]
        w = (p[0] - c[0], p[1] - c[1])
        bq = d[0] * w[0] + d[1] * w[1]
        disc = bq * bq - (w[0] ** 2 + w[1] ** 2 - r * r)
        if disc < -1e-6:
            raise ValueError('line misses circle')
        sq = math.sqrt(max(disc, 0.0))
        cands = [(p[0] + t * d[0], p[1] + t * d[1]) for t in (-bq - sq, -bq + sq)]
    return min(cands, key=lambda q: math.dist(q, hint))


def _foot(pr, q):
    if pr[0] == 'L':
        p, d = pr[1], pr[2]
        t = (q[0] - p[0]) * d[0] + (q[1] - p[1]) * d[1]
        return (p[0] + t * d[0], p[1] + t * d[1])
    u = _unit2((q[0] - pr[1][0], q[1] - pr[1][1]))
    return (pr[1][0] + pr[2] * u[0], pr[1][1] + pr[2] * u[1])


def chain(prims, joins, delta=0.0):
    """Closed outline from primitives, counter-clockwise:
         ('L', point, direction)   straight line, traversed along direction
         ('C', centre, r, s)       circle, s = +1 traversed counter-clockwise (convex), -1 clockwise (a dent)
       joins[i] joins prims[i] to prims[i+1]: ('B', rb, hint) blend arc, rb > 0 convex / rb < 0 concave;
       ('X', hint) plain intersection or tangent point. hint = rough corner position (picks the right solution).
       delta insets the whole outline (lines move inward, circles shrink/grow, blends adjust)."""
    n = len(prims)
    P = [_poff(pr, delta) for pr in prims]
    J = []
    for i in range(n):
        A, B, jn = P[i], P[(i + 1) % n], joins[i]
        if jn[0] == 'B':
            rb = jn[1] - delta
            if rb * jn[1] <= 0:
                raise ValueError(f'blend {i} vanishes at inset {delta}')
            bc = _isect(_poff(A, rb), _poff(B, rb), jn[2])
            t1, t2 = _foot(A, bc), _foot(B, bc)
            J.append((t1, t2, ('A', bc, t1, t2, rb > 0)))
        else:
            q = _isect(A, B, jn[1])
            J.append((q, q, None))
    segs = []
    for i in range(n):
        start, end, pr = J[i - 1][1], J[i][0], P[i]
        if pr[0] == 'L':
            run = (end[0] - start[0]) * pr[2][0] + (end[1] - start[1]) * pr[2][1]
            if run < -1e-6:
                raise ValueError(f'outline line {i} runs backwards ({run:.3f} mm) - blends overlap')
            if run > 1e-6:
                segs.append(('L', start, end))
        elif math.dist(start, end) > 1e-6:
            segs.append(('A', pr[1], start, end, pr[3] > 0))
        if J[i][2] is not None and math.dist(J[i][0], J[i][1]) > 1e-6:
            segs.append(J[i][2])
    if swlib.loop_area(segs) <= 0:
        raise ValueError('outline is not counter-clockwise (or folds over itself)')
    return segs


def map_loop(loop, f, mirror):
    """Map a loop's points with f; mirror=True if f reverses orientation (arcs flip direction)."""
    out = []
    for s in loop:
        if s[0] == 'L':
            out.append(('L', f(s[1]), f(s[2])))
        elif s[0] == 'A':
            out.append(('A', f(s[1]), f(s[2]), f(s[3]), s[4] != mirror))
        else:
            out.append(('C', f(s[1]), s[2]))
    return out


def sector(c, r0, r1, t0, t1):
    """Annular sector r0..r1 from angle t0 to t1 (degrees, counter-clockwise)."""
    P = lambda r, t: (c[0] + r * math.cos(math.radians(t)), c[1] + r * math.sin(math.radians(t)))
    return [('A', c, P(r1, t0), P(r1, t1), True), ('L', P(r1, t1), P(r0, t1)),
            ('A', c, P(r0, t1), P(r0, t0), False), ('L', P(r0, t0), P(r1, t0))]


def thigh_prims(cover=False):
    """Thigh side view in (a, y), a toward the knee servo case (heel side). Hip cup circle, a 26 wide waist,
    the dia 34 knee drum, and a tapered heel over the knee servo's tab band out to a = 23.85."""
    H, K = (0.0, HIP_Y), (0.0, KNEE_Y)
    te = (TAB_BAND[1], KNEE_Y + POD_Y)                       # heel-end top corner (23.85, -11.6)
    tf = (THIGH_W / 2, TAPER_Y)                              # taper meets the flank (13, -4)
    dt = _unit2((tf[0] - te[0], tf[1] - te[1]))
    hip = ('C', H, HIP_CUP_R + 0.4, -1) if cover else ('C', H, HIP_CUP_R, 1)   # the cover dents round the cup
    prims = [hip,
             ('L', (-THIGH_W / 2, 0.0), (0.0, -1.0)),            # body-side flank, down
             ('C', K, KNEE_DRUM_R, 1),                           # knee drum
             ('L', (0.0, KNEE_Y - POD_Y), (1.0, 0.0)),           # heel underside
             ('L', (TAB_BAND[1], 0.0), (0.0, 1.0)),              # heel end
             ('L', te, dt),                                      # tapered heel top
             ('L', (THIGH_W / 2, 0.0), (0.0, 1.0))]              # heel-side flank, up
    top = ('B', 3.5, (-13.0, 5.0)) if cover else ('B', -6.0, (-13.0, 5.5))
    top2 = ('B', 3.5, (13.0, 5.0)) if cover else ('B', -6.0, (13.0, 5.5))
    joins = [top, ('B', -6.0, (-13.0, -9.0)), ('B', -4.0, (14.8, -28.4)), ('B', 4.0, (23.85, -28.4)),
             ('B', 4.0, (23.85, -11.6)), ('B', -6.0, (13.0, -4.0)), top2]
    return prims, joins


def shin_prims():
    """Shin side view in (a, y), a = +Z (every paw forward): dia 34 knee drum, a taper to the paw, and the
    paw band a -13.05..23.85 (the wheel servo's tab band: toe 8.5 in front of the wheel)."""
    K = (0.0, KNEE_Y)
    yt, yb = AXLE_Y + POD_Y, AXLE_Y - POD_Y                 # paw band top -56.6, sole -73.4
    rear = _unit2((6.0, -45.0))
    front = _unit2((6.0, 45.0))
    prims = [('C', K, KNEE_DRUM_R, 1),
             ('L', (-KNEE_DRUM_R, KNEE_Y), rear),                # rear flank, down
             ('C', (TAB_BAND[0] + 4.0, yt - 4.0), 4.0, 1),       # heel-top corner of the paw band
             ('L', (TAB_BAND[0], 0.0), (0.0, -1.0)),             # paw heel end
             ('L', (0.0, yb), (1.0, 0.0)),                       # sole
             ('L', (TAB_BAND[1], 0.0), (0.0, 1.0)),              # toe end
             ('L', (0.0, yt), (-1.0, 0.0)),                      # toe top
             ('L', (11.0, AXLE_Y), front)]                       # front flank, up
    joins = [('B', -8.0, (-16.4, -24.5)), ('X', (-11.9, -57.9)), ('X', (TAB_BAND[0], yt - 4.0)),
             ('B', 4.0, (TAB_BAND[0], yb)), ('B', 4.0, (TAB_BAND[1], yb)), ('B', 4.0, (TAB_BAND[1], yt)),
             ('X', (12.1, yt)), ('B', -8.0, (16.4, -24.5))]
    return prims, joins


def thigh_outline(delta=0.0, cover=False):
    return chain(*thigh_prims(cover), delta=delta)


def shin_outline(delta=0.0):
    return chain(*shin_prims(), delta=delta)


def corridor(tab_corner, fil_c, fil_r, skin=1.0, r=LEAD_D / 2 + 0.1):
    """Lead passage (slot ends P1, P2, radius) in the (X, y) plane at a pod's shaft end: from the end gap under
    the servo tab, past the tab's edge, to the cross channel - threaded between the tab cavity corner and the
    concave R3 fillet where the pod meets the leg, keeping `skin` of wall under that fillet."""
    v = (fil_c[0] - tab_corner[0], fil_c[1] - tab_corner[1])
    dist = math.hypot(*v)
    v = (v[0] / dist, v[1] / dist)
    gap = dist - fil_r - skin
    if gap < 2 * r + 0.05:
        raise ValueError(f'lead corridor too tight: {gap:.2f} mm for a {2 * r:.1f} bundle')
    c = (tab_corner[0] + v[0] * gap / 2, tab_corner[1] + v[1] * gap / 2)
    ax = (v[1], -v[0]) if v[1] < 0 else (-v[1], v[0])
    if ax[0] < 0:
        ax = (-ax[0], -ax[1])
    return (c[0] - 2.2 * ax[0], c[1] - 2.2 * ax[1]), (c[0] + 2.5 * ax[0], c[1] + 2.5 * ax[1]), r, gap


KNEE_CORRIDOR = corridor((KNEE_UNDER - POD_GAP, KNEE_Y + SV_W / 2 + POD_GAP),
                         (THIGH_COVER_IN - KNEE_ROOT_R, KNEE_Y + POD_Y + KNEE_ROOT_R), KNEE_ROOT_R)
PAW_CORRIDOR = corridor((WHEEL_UNDER - POD_GAP, AXLE_Y + SV_W / 2 + POD_GAP),
                        (SHIN_COVER_IN - PAW_ROOT_R, AXLE_Y + POD_Y + PAW_ROOT_R), PAW_ROOT_R)


class Leg:
    """One leg's frame: x = sx * X (X = distance out from the centre line), z = hz + d * a."""
    def __init__(self, sx, sz, d):
        self.sx, self.sz, self.d = sx, sz, d
        self.hz = LEGS[sz][0]

    def z(self, a):
        return self.hz + self.d * a

    def zr(self, a0, a1):
        return rng(self.z(a0), self.z(a1))

    def xr(self, X0, X1):
        return rng(self.sx * X0, self.sx * X1)

    def loop(self, lp):
        return map_loop(lp, lambda q: (self.z(q[0]), q[1]), self.d < 0)

    def pt(self, X, y, a):
        return (self.sx * X, y, self.z(a))


def leg_name(sx, sz):
    return ('Front' if sz > 0 else 'Back') + ('Left' if sx > 0 else 'Right')


class P(swlib.Part):
    """Range-based helpers: B(xr, yr, zr); cylinders given by centre + radius + range along their axis."""
    def B(self, xr, yr, zr, cut=False):
        x0, x1 = rng(*xr); y0, y1 = rng(*yr); z0, z1 = rng(*zr)
        return self.box(x0, x1, y0, y1, z0, z1, cut)

    def CX(self, y, z, r, xr, cut=False):
        return self.cyl_x(y, z, r, *rng(*xr), cut=cut)

    def CY(self, x, z, r, yr, cut=False):
        return self.cyl_y(x, z, r, *rng(*yr), cut=cut)

    def CZ(self, x, y, r, zr, cut=False):
        return self.cyl_z(x, y, r, *rng(*zr), cut=cut)

    # --- v3 leg-frame helpers ------------------------------------------------------------
    def lbox(self, L, ar, yr, Xr, cut=False):
        return self.B(L.xr(*Xr), yr, L.zr(*ar), cut)

    def lcyl(self, L, a, y, r, Xr, cut=False):
        return self.CX(y, L.z(a), r, L.xr(*Xr), cut)

    def lprism(self, L, loops_ay, Xr, cut=False):
        """Outline(s) in (a, y), extruded along X over Xr."""
        loops = [L.loop(lp) for lp in swlib._as_loops(loops_ay)]
        x0, x1 = L.xr(*Xr)
        return self.prism('x', loops, x0, x1, cut)

    def lprism_z(self, L, loop_Xy, ar, cut=False):
        """Outline in (X, y), extruded along Z over the leg's a-range ar."""
        lp = map_loop(loop_Xy, lambda q: (L.sx * q[0], q[1]), L.sx < 0)
        z0, z1 = L.zr(*ar)
        return self.prism('z', lp, z0, z1, cut)

    def lprism_y(self, L, pts_aX, yr, cut=False):
        """Polygon in (a, X), extruded along Y."""
        lp = swlib.rpoly([(L.sx * X, L.z(a)) for a, X in pts_aX], 0.0)
        return self.prism('y', lp, yr[0], yr[1], cut)

    def lrevolve(self, L, a, y, prof_Xr, cut=False):
        """Solid of revolution about the X-parallel axis through (a, y); profile polygon in (X, r)."""
        lp = swlib.rpoly([(L.sx * X, r) for X, r in prof_Xr], 0.0)
        return self.revolve('x', (y, L.z(a)), lp, cut)

    def pilot_slot_x(self, y, z, xr):
        """M2 pilot through a plate normal to X, slotted along Z to take the tab-hole spread."""
        self.B(xr, (y - PILOT_R, y + PILOT_R), (z - PILOT_R - SV_HOLE_SLOT, z + PILOT_R + SV_HOLE_SLOT), cut=True)

    def servo_slot_x(self, y, shaft_z, dz, xr):
        """Opening for an MG90S case (0.3 clearance) + its two tab pilots, in a plate normal to X."""
        zc = shaft_z + dz * BODY_C
        self.B(xr, (y - SV_W / 2 - 0.3, y + SV_W / 2 + 0.3), (zc - SV_L / 2 - 0.3, zc + SV_L / 2 + 0.3), cut=True)
        for d in (-SV_HOLES / 2, SV_HOLES / 2):
            self.pilot_slot_x(y, zc + d, xr)

    def horn_seat_x(self, y, z, sx, x_in, t, arms, reach):
        """v2 horn seat (kept for reference; v3 legs use cross_horn_seat)."""
        d = (sx * (x_in - 0.5), sx * (x_in + HORN_T))
        thru = (sx * (x_in - 1), sx * (x_in + t + 1))
        self.CX(y, z, HORN_HUB_R, d, cut=True)
        for a in arms:
            if a in ('up', 'down'):
                s = 1 if a == 'up' else -1
                self.B(d, (y, y + s * reach), (z - HORN_W / 2, z + HORN_W / 2), cut=True)
                self.B(thru, (y + s * 5.5, y + s * (reach - 1.5)), (z - SLOT_W / 2, z + SLOT_W / 2), cut=True)
            else:
                s = 1 if a == 'fwd' else -1
                self.B(d, (y - HORN_W / 2, y + HORN_W / 2), (z, z + s * reach), cut=True)
                self.B(thru, (y - SLOT_W / 2, y + SLOT_W / 2), (z + s * 5.5, z + s * (reach - 1.5)), cut=True)
        self.CX(y, z, 3.0, thru, cut=True)

    def horn_seat_y(self, x, z, y_face, s, t, arms, reach):
        """Same as horn_seat_x for a plate normal to Y; s = +1 if the plate lies above its horn face."""
        d = rng(y_face - s * 0.5, y_face + s * HORN_T)
        thru = rng(y_face - s * 1, y_face + s * (t + 1))
        self.CY(x, z, HORN_HUB_R, d, cut=True)
        for a in arms:
            if a in ('fwd', 'back'):
                k = 1 if a == 'fwd' else -1
                self.B((x - HORN_W / 2, x + HORN_W / 2), d, (z, z + k * reach), cut=True)
                self.B((x - SLOT_W / 2, x + SLOT_W / 2), thru, (z + k * 5.5, z + k * (reach - 1.5)), cut=True)
            else:
                k = 1 if a == 'left' else -1
                self.B((x, x + k * reach), d, (z - HORN_W / 2, z + HORN_W / 2), cut=True)
                self.B((x + k * 5.5, x + k * (reach - 1.5)), thru, (z - SLOT_W / 2, z + SLOT_W / 2), cut=True)
        self.CY(x, z, 3.0, thru, cut=True)

    def pad_boss(self, x, z, ceiling, down=True, wall=W):
        """Boss hanging from a ceiling (underside at y=ceiling) for a foil touch pad: an M2 x 6 clamps the foil
        tab and the folded wire end. Blind pilot, 0.8 mm skin left on the outside."""
        self.CY(x, z, BOSS_R, (ceiling - 3, ceiling))
        self.CY(x, z, PILOT_R, (ceiling - 3.5, ceiling + wall - 0.8), cut=True)   # v3.1: 0.8 skin in any wall

    # --- v3 joint features ---------------------------------------------------------------
    def cross_horn_seat(self, L, a, y, X_in, X_face, cap_r):
        """4-arm cross horn under a hub cap, in a part whose servo-side face is at X_in and outer face at X_face:
        arm pocket (the horn is screwed in FIRST, from the horn side, into BLIND pilots - 1.0 skin left), hub
        recess, a dia 6 hole for the servo's own horn screw and the screwdriver, and the cap recess."""
        d0, d1 = X_in - 0.5, X_in + HORN_T
        R = CROSS_REACH
        self.lbox(L, (a - HORN_W / 2, a + HORN_W / 2), (y - R, y + R), (d0, d1), cut=True)
        self.lbox(L, (a - R, a + R), (y - HORN_W / 2, y + HORN_W / 2), (d0, d1), cut=True)
        self.lcyl(L, a, y, HORN_HUB_R, (d0, d1), cut=True)
        floor = X_face - CAP_RECESS
        self.lcyl(L, a, y, cap_r + 0.1, (floor, X_face + 0.5), cut=True)
        self.lcyl(L, a, y, 3.0, (d1 - 0.1, floor + 0.1), cut=True)
        r_split = cap_r + 0.1 + 0.5
        for r0, r1, xend in ((5.5, r_split, floor - 1.0), (r_split, R - 1.5, X_face - 1.0)):
            if xend - d1 < 1.5 or r1 - r0 < 1.0:
                continue
            for s in (1, -1):
                self.lbox(L, (a - SLOT_W / 2, a + SLOT_W / 2), (y + s * r0, y + s * r1), (d1 - 0.1, xend), cut=True)
                self.lbox(L, (a + s * r0, a + s * r1), (y - SLOT_W / 2, y + SLOT_W / 2), (d1 - 0.1, xend), cut=True)

    def hook_male(self, L, ah, y, split, relief, tip):
        """Snap hook on a white outer half: a 1.0 thick beam rooted `relief` deep in a slot in the outer half,
        reaching across the split plane to X = tip inside the cover; 0.4 barb facing away from the channel."""
        e = 1 if ah >= 0 else -1
        catch = tip + 1.4
        self.lbox(L, (ah - e * 1.1, ah + e * 1.1), (y - HOOK_WID / 2 - 0.3, y + HOOK_WID / 2 + 0.3),
                  (split - 0.1, split + relief), cut=True)
        prof = [(-0.5, split + relief + 0.2), (0.5, split + relief + 0.2), (0.5, catch), (0.5 + HOOK_BARB, catch),
                (0.5 + HOOK_BARB, tip + 0.8), (0.1, tip), (-0.5, tip)]
        self.lprism_y(L, [(ah + e * u, X) for u, X in prof], (y - HOOK_WID / 2, y + HOOK_WID / 2))

    def hook_female(self, L, ah, y, split, tip):
        """Pocket in a graphite cover that the hook snaps into (entry narrower than the barb, catch ledge)."""
        e = 1 if ah >= 0 else -1
        catch = tip + 1.4
        yr = (y - HOOK_WID / 2 - 0.2, y + HOOK_WID / 2 + 0.2)
        self.lbox(L, (ah - e * 1.0, ah + e * 0.6), yr, (catch + 0.1, split + 0.1), cut=True)
        self.lbox(L, (ah - e * 1.0, ah + e * 1.1), yr, (tip - 0.2, catch + 0.1), cut=True)

    # --- v3 body helpers -----------------------------------------------------------------
    def multi_cut(self, axis, loops, a0, a1):
        """Cut many separate outlines (e.g. an 81-hole grille) with ONE extrude + ONE combine: every tool body
        the extrude makes is subtracted (swlib's cut subtracts only the first one)."""
        before = {b.Name for b in self._bodies()}
        loops = swlib._as_loops(loops)
        plane, fmap, det = self._plane_map(axis)
        self._sketch(plane)
        self._emit(loops, fmap, det)
        self._close()
        lo, hi = min(a0, a1), max(a0, a1)
        f = self.fm.FeatureExtrusion3(True, False, False, 0, 0, (hi - lo) * swlib.MM, 0, False, False, False, False,
                                      0, 0, False, False, False, False, False, True, True,
                                      3 if abs(lo) > 1e-12 else 0, abs(lo) * swlib.MM, lo < 0)
        if f is None:
            raise RuntimeError('multi-cut extrude failed')
        tools = [b for b in self._bodies() if b.Name not in before]
        others = [b for b in self._bodies() if b.Name in before]
        main = max(others, key=lambda bd: bd.GetMassProperties(1000.0)[3])
        self.m.ClearSelection2(True)
        c = self.fm.InsertCombineFeature(15902, main, VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, tools))
        if c is None:
            raise RuntimeError('multi-cut subtract failed')
        self.last = c
        return c

    def oval_y(self, x, z, ax, az, y0, y1, cut=False):
        """Elliptic prism along Y: centre (x, z), semi-axes ax (along X) and az (along Z)."""
        self._sketch('Top Plane')
        s = swlib.TOP_ZSIGN
        cx, cy = x, -z * s
        MM = swlib.MM
        if ax >= az:
            got = self.m.SketchManager.CreateEllipse(cx * MM, cy * MM, 0, (cx + ax) * MM, cy * MM, 0, cx * MM, (cy + az) * MM, 0)
        else:
            got = self.m.SketchManager.CreateEllipse(cx * MM, cy * MM, 0, cx * MM, (cy + az) * MM, 0, (cx + ax) * MM, cy * MM, 0)
        if got is None:
            raise RuntimeError('ellipse refused')
        self._close()
        return self._extrude(min(y0, y1), max(y0, y1), cut)


def rot_rect(c, length, width, deg):
    """Rectangle centred on c (u, v), `length` along the direction deg, as a 4-point polygon."""
    t = math.radians(deg)
    d, n = (math.cos(t), math.sin(t)), (-math.sin(t), math.cos(t))
    hl, hw = length / 2, width / 2
    return [(c[0] + sa * hl * d[0] + sb * hw * n[0], c[1] + sa * hl * d[1] + sb * hw * n[1])
            for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]


def seg_rect(c, r0, r1, width, deg):
    """Rectangle along the ray from c at angle deg, from radius r0 to r1."""
    t = math.radians(deg)
    m = (c[0] + (r0 + r1) / 2 * math.cos(t), c[1] + (r0 + r1) / 2 * math.sin(t))
    return rot_rect(m, r1 - r0, width, deg)


def laser_wedge_pts(sz):
    """Outline (z, y) of the block that holds an obstacle VL53L0X tilted 15 deg down against the front (sz=+1)
    or rear (sz=-1) wall. The board's chip face lies on the slope, its lower edge on the ledge; 45 deg underside."""
    rear = [(-77.6, 8.5), (-71.2, 14.9), (-71.2, 16.4), (-74.19, 16.4), (-77.3, 28.0), (-77.6, 28.0)]
    return [(z if sz < 0 else -z, y) for z, y in rear]


def laser_board_pts(sz):
    n = (math.cos(math.radians(15)), math.sin(math.radians(15)))       # slope normal, into the torso (rear case)
    d, e = (-74.19, 16.4), (-77.3, 28.0)
    rear = [d, e, (e[0] + 2.5 * n[0], e[1] + 2.5 * n[1]), (d[0] + 2.5 * n[0], d[1] + 2.5 * n[1])]
    return [(z if sz < 0 else -z, y) for z, y in rear]


def cliff_geom(zlow, dirz):
    """Incline for a desk-edge VL53L0X (chip face down on the slope, looking CLIFF_TILT ahead of straight down)."""
    t = math.radians(CLIFF_TILT)
    run, rise = 12.0 * math.cos(t), 12.0 * math.sin(t)
    z1 = zlow + dirz * run
    wedge = [(zlow, W), (zlow, W + 0.3), (z1, W + 0.3 + rise), (z1 + dirz * 1.5, W + 0.3 + rise), (z1 + dirz * 1.5, W)]
    n = (-dirz * math.sin(t), math.cos(t))
    p0, p1 = (zlow, W + 0.3), (z1, W + 0.3 + rise)
    board = [p0, p1, (p1[0] + 2.5 * n[0], p1[1] + 2.5 * n[1]), (p0[0] + 2.5 * n[0], p0[1] + 2.5 * n[1])]
    return wedge, board, run, rise


# =============================================================================================
# PRINTED PARTS - torso and head: still v2 (the next agent makes them v3)
# =============================================================================================
def torso_bottom(p):
    iw, il = TX - W, TZ - W                       # inner half sizes 39.6, 77.6
    p.B((-TX, TX), (0, TUB_H), (-TZ, TZ))
    p.B((-iw, iw), (W, TUB_H + 5), (-il, il), cut=True)
    for sx in (-1, 1):
        for sz in (-1, 1):
            hz, dz = LEGS[sz]
            zc = hz + dz * BODY_C
            # hip MG90S: tabs sit on the OUTSIDE of the wall, case goes in through the wall (plug + lead first).
            # 5 mm pads only where the tab screws bite (keeps the floor clear for the charger).
            p.B((sx * (TX - 5), sx * iw), (12, 24), (max(zc - 17.5, -il), min(zc + 17.5, il)))
            p.servo_slot_x(HIP_Y, hz, dz, (sx * (TX - 6.8), sx * (TX + 1)))
            # knee + wheel servo leads come in through the floor (a servo plug passes 8 x 10)
            p.B((sx * 28, sx * 36), (-1, W + 1), (sz * 35, sz * 45), cut=True)
        # PCA9685 standing on each side wall: 4 standoffs with M2 pilots (upper two screwed; the lower two are
        # spacers - a screwdriver cannot reach them square), bottom ledge, inner fence, end fences.
        for zz in (-27.94, 27.94):
            for yy in (8.775, 27.825):
                p.CX(yy, zz, 3.0, (sx * 33.6, sx * iw))
                p.CX(yy, zz, PILOT_R, (sx * 33.0, sx * (iw + 0.8)), cut=True)
        for zr in ((-30, -6), (6, 30)):                  # gap in the middle for the V+ terminal block
            p.B((sx * 32, sx * iw), (W, 5.6), zr)
            p.B((sx * 30.8, sx * 32), (W, 8.0), zr)
        for zr in ((31.4, 33.4), (-33.4, -31.4)):
            p.B((sx * 31, sx * 35), (W, 10.6), zr)
        # battery holder: side lip + clamp post (M2 pilot on top)
        p.B((sx * 20.8, sx * 22.8), (W, W + 4), (-44, 20))
        p.B((sx * 20.8, sx * 26), (W, 20.75), CLAMP_Z)
        p.CY(sx * 23.4, -35, PILOT_R, (8, 21.75), cut=True)
        # protection board fences (board lies across the floor, fuse holder taped on top of it)
        p.B((sx * 24.5, sx * 25.7), (W, W + 3), (PROT_Z[0] - 0.3, PROT_Z[1] + 0.3))
    for zr in ((PROT_Z[0] - 1.5, PROT_Z[0] - 0.3), (PROT_Z[1] + 0.3, PROT_Z[1] + 1.5)):
        p.B((-25.7, 25.7), (W, W + 3), zr)
    # battery holder end stops (holder 76 long + 0.6)
    for zr in ((-54.0, BAT_Z[0] - 0.3), (BAT_Z[1] + 0.3, 26.0)):
        for xr in ((-13, -6), (6, 13)):
            p.B(xr, (W, W + 4), zr)
    # desk-edge lasers: 25 deg inclines so each looks ahead of the wheels, a stop lip, a window under the chip
    for x0, x1, zlow, dirz in [(sx * CLIFF_FRONT_X[0], sx * CLIFF_FRONT_X[1], CLIFF_FRONT_Z, 1) for sx in (-1, 1)] + \
                              [(CLIFF_REAR_X[0], CLIFF_REAR_X[1], CLIFF_REAR_Z, -1)]:
        wedge, _, run, rise = cliff_geom(zlow, dirz)
        p.poly_x(wedge, x0, x1)
        p.B((x0, x1), (W, W + 3), (zlow - dirz * 2.3, zlow - dirz * 1.1))
        xc = (x0 + x1) / 2
        p.B((xc - 5, xc + 5), (-1, W + 0.3 + rise + 1), (zlow + dirz * 1.4, zlow + dirz * (run + 1.0)), cut=True)
    # obstacle lasers on the front and rear walls, tilted 15 deg down to see books and keyboards
    for sz in (-1, 1):
        p.poly_x(laser_wedge_pts(sz), -13, 13)
        p.B((-6, 6), (17, 27.5), (sz * 81, sz * 74), cut=True)
    # KCD1 rocker switch on the belly
    p.B((-KCD1_X / 2, KCD1_X / 2), (-1, W + 1), (KCD1_ZC - KCD1_Z / 2, KCD1_ZC + KCD1_Z / 2), cut=True)
    # USB-C charger: 2 mm pad (lifts the port so the plug clears the floor), fences, port slot in the rear wall
    p.B((21.3, 39.3), (W, 4.4), (-il, -46.6))
    p.B((19.5, 21.3), (W, 7.4), (-75, -53))            # stops before the battery holder
    p.B((21.3, iw), (W, 7.4), (-46.4, -45.2))
    p.B((22.3, 38.3), (3.4, 12.4), (-TZ - 1, -il + 0.5), cut=True)   # 16 x 9: takes fat plug overmoulds
    # lid screws: through front/rear walls, counterbored outside
    for sz in (-1, 1):
        for sx in (-1, 1):
            p.CZ(sx * 25, LID_SCREW_Y, CLEAR_R, (sz * (il - 1), sz * (TZ + 1)), cut=True)
            p.CZ(sx * 25, LID_SCREW_Y, CBORE_R, (sz * (TZ - CBORE_D), sz * (TZ + 1)), cut=True)


def battery_clamp(p):
    p.B((-26, 26), (21.75, 24.75), CLAMP_Z)
    for sx in (-1, 1):
        p.CY(sx * 23.4, -35, CLEAR_R, (20, 26), cut=True)
        p.CY(sx * 23.4, -35, CBORE_R, (24.75 - CBORE_D, 26), cut=True)


def torso_lid(p):
    top = LID_TOP - W                                                    # 47.6 ceiling underside
    p.B((-TX, TX), (TUB_H, LID_TOP), (-TZ, TZ))
    p.B((-39.3, 39.3), (LIP_Y0, TUB_H + 0.5), (-77.3, 77.3))              # lip into the tub
    p.B((-36.9, 36.9), (LIP_Y0 - 1, top), (-74.9, 74.9), cut=True)
    for sz in (-1, 1):
        for sx in (-1, 1):
            p.CZ(sx * 25, LID_SCREW_Y, 3.0, (sz * 71, sz * 77.3))        # lip screw boss
            p.CZ(sx * 25, LID_SCREW_Y, PILOT_R, (sz * 70, sz * 78), cut=True)
    # neck: cable hole + 4 screw holes counterbored from inside
    p.B((-11, 11), (top - 1, LID_TOP + 1), (53, 67), cut=True)
    for x, z in LID_NECK_SCREWS:
        p.CY(x, z, CLEAR_R, (top - 1, LID_TOP + 1), cut=True)
        p.CY(x, z, CBORE_R, (top - 0.5, top + CBORE_D), cut=True)
    # tail MG90S: case drops through the top (plug + lead first), tabs sit on top, 2 pilot bosses underneath
    zc = TAIL_Z + BODY_C
    p.B((-SV_W / 2 - 0.3, SV_W / 2 + 0.3), (top - 1, LID_TOP + 1), (zc - SV_L / 2 - 0.3, zc + SV_L / 2 + 0.3), cut=True)
    for d in (-SV_HOLES / 2, SV_HOLES / 2):
        p.CY(0, zc + d, 2.4, (top - 3, top))            # r 2.4 keeps 0.28 clear of the servo case end
        p.B((-PILOT_R, PILOT_R), (top - 4, LID_TOP + 1), (zc + d - PILOT_R - SV_HOLE_SLOT, zc + d + PILOT_R + SV_HOLE_SLOT), cut=True)
    # side lasers (VL53L0X) stand on a shelf against each side wall; a lip on two posts holds the bottom edge
    # 4.2 mm off the wall (room for parts on both faces); the windows flare outward so the cone clears the wall
    for sx in (-1, 1):
        win = [(36.0, 38.6), (36.9, 38.6), (43.0, 37.2), (43.0, 46.0), (36.9, 44.6), (36.0, 44.6)]
        p.poly_z([(sx * x, y) for x, y in win], -9, 9, cut=True)
        p.B((sx * 32.1, sx * 36.9), (34.4, 35.6), (-13.5, 13.5))
        p.B((sx * 31.5, sx * 32.7), (34.4, 38.0), (-11, 11))
        for zr in ((9, 11), (-11, -9)):
            p.B((sx * 31.5, sx * 32.7), (34.4, top), zr)
    # fences hanging from the ceiling: IMU (21.6 x 16.8), MPR121 (30.5 x 20.3), hub (perfboard cut to 50 x 35)
    fences = [((-9.8, -8.6), (3.6, 26.0)), ((8.6, 9.8), (3.6, 26.0)), ((-9.8, 9.8), (2.4, 3.6)), ((-9.8, 9.8), (26.0, 27.2)),
              ((14.9, 16.1), (16.5, 47.0)), ((14.9, 31.4), (15.3, 16.5)),
              ((-26.4, -25.2), (-37.5, -1.5)), ((25.2, 26.4), (-37.5, -1.5)), ((-26.4, 26.4), (-38.7, -37.5)),
              ((-26.4, 26.4), (-1.5, -0.3))]
    for xr, zr in fences:
        p.B(xr, (top - 2.5, top), zr)
    # hub tie anchors (bridges a cable tie passes under) beside the long hub fences
    for sx in (-1, 1):
        for z in (-30.0, -10.0):
            p.B((sx * 27.4, sx * 31.4), (top - 5, top), (z - 1.5, z + 1.5))
            p.B((sx * 28.4, sx * 30.4), (top - 3.5, top + 0.01), (z - 2, z + 2), cut=True)
    # foil touch pads on the ceiling: back left/right (beside the hub), rump left/right (beside the tail servo)
    for x, z in ((-32.0, -25.0), (32.0, -25.0), (-21.0, -60.0), (21.0, -60.0)):
        p.pad_boss(x, z, top)


def neck(p):
    n = NECK
    p.B((-n['x'], n['x']), (LID_TOP, HEAD['y0']), (n['z0'], n['z1']))
    p.B((-n['x'] + W, n['x'] - W), (LID_TOP - 1, HEAD['y0'] + 1), (n['z0'] + W, n['z1'] - W), cut=True)
    for x, z in LID_NECK_SCREWS + HEAD_NECK_SCREWS:
        p.CY(x, z, 3.0, (LID_TOP, HEAD['y0']))
    for x, z in LID_NECK_SCREWS:                        # blind from below: the two screw sets never meet
        p.CY(x, z, PILOT_R, (LID_TOP - 1, LID_TOP + 8.5), cut=True)
    for x, z in HEAD_NECK_SCREWS:                       # blind from above
        p.CY(x, z, PILOT_R, (HEAD['y0'] - 8.5, HEAD['y0'] + 1), cut=True)


def head_front(p):
    h = HEAD
    ix, iy0, iy1, iz1 = h['x'] - W, h['y0'] + W, h['y1'] - W, h['z1'] - W
    p.B((-h['x'], h['x']), (h['y0'], h['y1']), (h['z0'] + W, h['z1']))
    p.B((-ix, ix), (iy0, iy1), (h['z0'], iz1), cut=True)
    # screen window = active area 95.04 x 53.86 + 1 mm each side, plus a 1.2 mm outer relief so a look from
    # above does not lose the top rows behind the wall
    p.B((-48.5, 48.5), (BOARD_Y0 + 9.34, BOARD_Y0 + 65.2), (iz1 - 1, h['z1'] + 1), cut=True)
    p.B((-50.9, 50.9), (BOARD_Y0 + 6.9, BOARD_Y0 + 67.6), (h['z1'] - 1.2, h['z1'] + 1), cut=True)
    # 4 screen bosses at the board's ear holes (112.6 x 62.1); blind pilots, screws go in from behind
    for x in (-56.3, 56.3):
        for y in (BOARD_Y0 + 4.05, BOARD_Y0 + 66.15):
            p.CZ(x, y, BOSS_R, (PCB_FRONT, iz1))
            p.CZ(x, y, PILOT_R, (PCB_FRONT - 1, h['z1'] - 0.8), cut=True)
    # screen board -X edge: USB-C (receptacle on the back of the PCB) goes through the wall; P1 power plug below it
    # gets a blind pocket in the wall (0.8 mm skin) so its wires can bend
    p.B((-h['x'] - 1, -ix + 0.5), (BOARD_Y0 + 33.1, BOARD_Y0 + 47.1), (PCB_FRONT - 7.2, PCB_FRONT + 0.8), cut=True)
    p.B((-h['x'] + 0.8, -ix + 0.5), (BOARD_Y0 + 20.0, BOARD_Y0 + 33.1), (PCB_FRONT - 11.0, PCB_FRONT + 1.0), cut=True)
    for sx in (-1, 1):
        # MS3625 mic: ring the board sits in + sound hole
        p.CX(MIC_Y, MIC_Z, 8.3, (sx * (ix - 1.2), sx * ix))
        p.CX(MIC_Y, MIC_Z, 7.3, (sx * (ix - 1.3), sx * ix), cut=True)
        p.CX(MIC_Y, MIC_Z, 1.25, (sx * (ix - 1), sx * (h['x'] + 1)), cut=True)
        # back-cover screws: clearance + outside counterbore
        for y in (80, 140):
            p.CX(y, BACK_SCREW_Z, CLEAR_R, (sx * (ix - 1), sx * (h['x'] + 1)), cut=True)
            p.CX(y, BACK_SCREW_Z, CBORE_R, (sx * (h['x'] - CBORE_D), sx * (h['x'] + 1)), cut=True)
    # neck: cable hole + its own 4 screw holes (counterbored inside; fit them before the screen goes in)
    p.B((-11, 11), (h['y0'] - 1, iy0 + 1), (53, 67), cut=True)
    for x, z in HEAD_NECK_SCREWS:
        p.CY(x, z, CLEAR_R, (h['y0'] - 1, iy0 + 1), cut=True)
        p.CY(x, z, CBORE_R, (iy0 - CBORE_D, iy0 + 0.5), cut=True)
    # muzzle: cable hole + 4 screw holes (counterbored inside, below the screen)
    p.B((-10, 10), (63, 72), (iz1 - 1, h['z1'] + 1), cut=True)
    for x, y in MUZ_SCREWS:
        p.CZ(x, y, CLEAR_R, (iz1 - 1, h['z1'] + 1), cut=True)
        p.CZ(x, y, CBORE_R, (iz1 - 0.5, iz1 + CBORE_D), cut=True)
    # foil touch pad on the head's ceiling (behind the screen)
    p.pad_boss(0.0, 46.0, iy1)


def head_back(p):
    h = HEAD
    p.B((-h['x'], h['x']), (h['y0'], h['y1']), (h['z0'], h['z0'] + W))
    p.B((-60.3, 60.3), (h['y0'] + 2.7, h['y1'] - 2.7), (h['z0'] + W - 0.5, h['z0'] + W + 4))     # lip
    p.B((-57.9, 57.9), (h['y0'] + 5.1, h['y1'] - 5.1), (h['z0'] + W, h['z0'] + W + 5), cut=True)
    for sx in (-1, 1):
        for y in (80, 140):
            p.CX(y, BACK_SCREW_Z, BOSS_R, (sx * 55.5, sx * 60.3))
            p.CX(y, BACK_SCREW_Z, PILOT_R, (sx * 54.5, sx * 61), cut=True)
    # speaker grille (speaker faces backwards through it) + speaker fences
    for gx in (-38, -30, -22):
        for gy in (88, 96, 104):
            p.CZ(gx, gy, 1.5, (h['z0'] - 1, h['z0'] + W + 1), cut=True)
    for xr, yr in (((-46.5, -45.3), (79, 112)), ((-14.7, -13.5), (79, 112)), ((-45.3, -14.7), (112.3, 113.5)), ((-45.3, -14.7), (77.5, 78.7))):
        p.B(xr, yr, (h['z0'] + W, h['z0'] + W + 3))
    # BOOT and RESET: poke a straightened paperclip through these to press the screen board's buttons
    for y in (BOARD_Y0 + 24.1, BOARD_Y0 + 16.4):
        p.CZ(51.5, y, 1.5, (h['z0'] - 1, h['z0'] + W + 1), cut=True)


def screen_washers(p):
    """4 washers that go under the screen screws (the ear holes are 3.2 mm, the M2 heads only 3.5-4.3)."""
    for x in (-56.3, 56.3):
        for y in (BOARD_Y0 + 4.05, BOARD_Y0 + 66.15):
            p.CZ(x, y, 3.0, (PCB_FRONT - 1.6 - 0.8, PCB_FRONT - 1.6))
            p.CZ(x, y, 1.2, (PCB_FRONT - 3, PCB_FRONT), cut=True)


def muzzle(p):
    m, fz = MUZ, MUZ_FZ
    ix, iy0, iy1 = m['x'] - W, m['y0'] + W, m['y1'] - W
    p.B((-m['x'], m['x']), (m['y0'], m['y1']), (m['z0'], m['z1']))
    p.B((-ix, ix), (iy0, iy1), (m['z0'] - 1, fz), cut=True)                 # open back: the board slides in
    for sx in (-1, 1):
        # screw blocks joined to the side walls, clear of the board's path, 45 deg underneath (prints face-down)
        p.B((sx * 30.4, sx * (ix + 0.5)), (61.2, iy1), (m['z0'], m['z0'] + 6))
        c = ix + 0.5 - 30.4
        p.poly_y([(sx * 30.4, m['z0'] + 6), (sx * (ix + 0.5), m['z0'] + 6), (sx * (ix + 0.5), m['z0'] + 6 + c)], 61.2, iy1)
        # posts the board's front face rests on (put foam tape on them)
        p.B((sx * 22, sx * 26), (iy0, iy0 + 3), (CAM_PCB_Z, CAM_PCB_Z + 2))
        p.B((sx * 22, sx * 26), (iy1 - 3, iy1), (CAM_PCB_Z, CAM_PCB_Z + 2))
    for x, y in MUZ_SCREWS:
        p.CZ(x, y, PILOT_R, (m['z0'] - 1, m['z0'] + 7), cut=True)
    # USB-C slot in the +X wall for the camera board's two ports
    p.B((ix - 0.5, m['x'] + 1), (iy0 + 0.6, 60.5), (m['z0'] + 0.5, fz - 2), cut=True)
    # OV5640: lens holder pocket (9.1 square) in a boss on the front wall, lens hole 9 mm (holder corners rest)
    p.B((LENS_X - 6.5, LENS_X + 6.5), (LENS_Y - 6.5, LENS_Y + 6.5), (fz - 3, fz))
    p.B((LENS_X - 4.55, LENS_X + 4.55), (LENS_Y - 4.55, LENS_Y + 4.55), (fz - 4, fz + 0.1), cut=True)
    p.CZ(LENS_X, LENS_Y, 4.5, (fz - 1, m['z1'] + 1), cut=True)
    # APDS-9960 gesture: shelf it stands on (chip centred on the window), side fences, window
    ax0, ax1 = 5.0, 25.6
    p.B((ax0, ax1), (iy0, 55.8), (fz - 2.5, fz))
    for xr in ((ax0 - 1.2, ax0), (ax1, ax1 + 1.2)):
        p.B(xr, (iy0, iy1), (fz - 2.5, fz))              # full height: meets the shelf face-to-face, not on an edge
    p.B((ax0 + 4.2, ax1 - 4.2), (59.6, 67.6), (fz - 1, m['z1'] + 1), cut=True)


def ear(p, sx):
    p.B((sx * 30, sx * 52), (HEAD['y1'], HEAD['y1'] + 30), (56, 66))
    p.B((sx * 34, sx * 48), (HEAD['y1'] + 30, HEAD['y1'] + 38), (58, 64))


def tail(p):
    y0 = TAIL_Y0
    p.CY(0, TAIL_Z, 9.0, (y0, y0 + 4))
    p.B((-5, 5), (y0, y0 + 4), (-100, TAIL_Z + HORN_REACH + 1))
    p.B((-2.5, 2.5), (y0, y0 + 26), (-104, -96))
    p.horn_seat_y(0, TAIL_Z, y0, 1, 4, ('fwd', 'back'), HORN_REACH)


def fit_coupon(p):
    """~20 g test print with one of every critical fit. Print this FIRST and try the real parts in it."""
    ox = 150                                          # sits off to the side of the robot
    p.B((ox, ox + 95), (0, W), (0, 60))
    # MG90S wall slot with a 5 mm pad and slotted pilots (same as the torso and legs)
    p.B((ox + 2, ox + 38), (W, 7), (2, 22))
    p.B((ox + 20 - SV_L / 2 - 0.3, ox + 20 + SV_L / 2 + 0.3), (-1, 8), (12 - SV_W / 2 - 0.3, 12 + SV_W / 2 + 0.3), cut=True)
    for dx in (-SV_HOLES / 2, SV_HOLES / 2):
        p.B((ox + 20 + dx - PILOT_R - SV_HOLE_SLOT, ox + 20 + dx + PILOT_R + SV_HOLE_SLOT), (-1, 8), (12 - PILOT_R, 12 + PILOT_R), cut=True)
    # KCD1 cut-out in a 2.4 mm panel
    p.B((ox + 42, ox + 42 + KCD1_X), (-1, W + 1), (4, 4 + KCD1_Z), cut=True)
    # screen boss with blind pilot, M2 clearance + counterbore
    p.CY(ox + 10, 34, BOSS_R, (W, W + SCREEN_STACK))
    p.CY(ox + 10, 34, PILOT_R, (W - 0.8, W + SCREEN_STACK + 1), cut=True)
    p.CY(ox + 22, 34, CLEAR_R, (-1, W + 1), cut=True)
    p.CY(ox + 22, 34, CBORE_R, (W - CBORE_D, W + 1), cut=True)
    # VL53L0X window and APDS window
    p.B((ox + 30, ox + 36), (-1, W + 1), (24, 41), cut=True)
    p.B((ox + 40, ox + 52), (-1, W + 1), (26, 33), cut=True)
    # wheel groove sample (v3: fit the 26 mm O-ring; the groove now reaches past the plate - sample only)
    gy0, gy1 = W + (8 - OR_CS - 0.2) / 2, W + (8 + OR_CS + 0.2) / 2
    p.CY(ox + 78, 22, OR_GROOVE_R + OR_CS / 2 + 0.25, (W, W + 8))
    p.CY(ox + 78, 22, 20, (gy0, gy1), cut=True)
    p.CY(ox + 78, 22, OR_GROOVE_R, (gy0, gy1))
    # horn pocket sample in a 4 mm pad (same as the thighs) - screw a real horn in from the horn side
    p.B((ox + 2, ox + 40), (W, W + 4), (44, 58))
    p.horn_seat_y(ox + 21, 51, W + 4, -1, 4, ('left', 'right'), HORN_REACH)


# =============================================================================================
# PRINTED PARTS - v3 BODY (proposal sections 2-7)
# =============================================================================================
def band_zones(sz):
    """Boxes (x range, y range) where the chest (sz=+1) / rump (-1) wall is thickened to 4.7 behind the band:
    everywhere under the band except behind the obstacle laser (x +-13.3 below y 29) and, at the rump, the
    USB-C charger (x 18.2-36.4, y 22.35-31.4)."""
    z = [(-36.4, -13.3, 8.1, 36.0), (-13.3, 13.3, 29.0, 36.0)]
    if sz > 0:
        z.append((13.3, 36.4, 8.1, 36.0))
    else:
        z += [(13.3, 18.2, 8.1, 36.0), (18.2, 36.4, 8.1, 22.35), (18.2, 36.4, 31.4, 36.0)]
    return z


def torso_bottom_v3(p):
    """TUB (graphite). Uniform 2.4 wall with R8 chest / rump bottom edges (inner R5.6), R1 corners (behind the
    side panels: the seam reads as a groove). Holds the 4 hip MG90S, 2 PCA9685, the protection board and fuse,
    the raised USB-C charger, the KCD1 (front belly, flush), 5 VL53L0X. Battery: on its own belly door."""
    iw, il = TUB_IN, TUB_INZ                      # v3.1: 1.6 walls (inner 40.4 / 78.4); the floor stays W = 2.4
    p.prism('x', swlib.rrect(-TZ, TZ, 0.0, TUB_H, (BELLY_R, BELLY_R, 0.0, 0.0)), -TX, TX)
    # inner R5.6 at the chest / rump: 2.4 under the belly, 1.6 up the end wall, >= 1.6 all round the R8
    p.prism('x', swlib.rrect(-il, il, W, TUB_H + 5, (BELLY_R - W, BELLY_R - W, 0.0, 0.0)), -iw, iw, cut=True)
    p.fillet_safe(1.0, [(sx * TX, 20.0, sz * TZ) for sx in (-1, 1) for sz in (-1, 1)])
    for sx in (-1, 1):
        for sz in (-1, 1):
            hz, dz = LEGS[sz]
            zc = hz + dz * BODY_C
            pz0, pz1 = zc - 17.5, zc + 17.5            # v3.1: a pad that reaches the end wall merges with it
            pz0 = -il - 0.01 if pz0 < -il + 0.5 else pz0
            pz1 = il + 0.01 if pz1 > il - 0.5 else pz1
            p.B((sx * (TX - 5), sx * iw), (12, 24), (pz0, pz1))
            p.servo_slot_x(HIP_Y, hz, dz, (sx * (TX - 6.8), sx * (TX + 1)))
            # hip leads: notch 9 wide from y 26.5 up to the rim, laid in from above (the lid's comb closes it)
            p.B((sx * (iw - 0.1), sx * (TX + 0.1)), (26.5, TUB_H + 0.1), (hz - 4.5, hz + 4.5), cut=True)
        for zz in (-27.94, 27.94):
            for yy in (8.775, 27.825):
                p.CX(yy, zz, 3.0, (sx * 33.6, sx * iw))
                p.CX(yy, zz, PILOT_R, (sx * 33.0, sx * (iw + 0.8)), cut=True)
        for zr in ((-30, -6), (6, 30)):
            p.B((sx * 32, sx * iw), (W, 5.6), zr)
            p.B((sx * 30.8, sx * 32), (W, 8.0), zr)
        for zr in ((31.4, 33.4), (-33.4, -31.4)):
            p.B((sx * 31, sx * 35), (W, 10.6), zr)
        p.B((sx * 24.5, sx * 25.7), (W, W + 3), (PROT_Z[0] - 0.3, PROT_Z[1] + 0.3))
        # side panel snap-hook windows (beam 1.2 thick + 0.6 barb, deflects 0.4 to pass)
        for z, y in PANEL_HOOKS:
            p.B((sx * (iw - 0.1), sx * (TX + 0.1)), (y - 0.4, y + 1.5), (z - 2.1, z + 2.1), cut=True)
        # v3.1 lightening window behind the side panel (hidden): between the PCA9685 standoff pairs, above its
        # ledge, below the lid lip; the top rail (y 29-36) and the floor carry the wall
        p.prism('x', swlib.rrect(-TUB_WIN[0], TUB_WIN[0], TUB_WIN[1], TUB_WIN[2], 3.0), *rng(sx * (iw - 0.1), sx * (TX + 0.1)), cut=True)
    for zr in ((PROT_Z[0] - 1.5, PROT_Z[0] - 0.3), (PROT_Z[1] + 0.3, PROT_Z[1] + 1.5)):
        p.B((-25.7, 25.7), (W, W + 3), zr)
    # desk-edge lasers: inclines, stop lips, R2 windows
    for x0, x1, zlow, dirz in [(sx * CLIFF_FRONT_X[0], sx * CLIFF_FRONT_X[1], CLIFF_FRONT_Z, 1) for sx in (-1, 1)] + \
                              [(CLIFF_REAR_X[0], CLIFF_REAR_X[1], CLIFF_REAR_Z, -1)]:
        wedge, _, run, rise = cliff_geom(zlow, dirz)
        p.poly_x(wedge, x0, x1)
        p.B((x0, x1), (W, W + 3), (zlow - dirz * 2.3, zlow - dirz * 1.1))
        xc = (x0 + x1) / 2
        za, zb = sorted((zlow + dirz * 1.4, zlow + dirz * (run + 1.0)))
        p.rrect_y(xc - 5, xc + 5, za, zb, -1, W + 0.3 + rise + 1, 2.0, cut=True)
    # KCD1: 2.4 panel boss inside, 13 x 19.4 cut-out, 2.2 recess so the rocker is flush with the belly
    kz0, kz1 = KCD1_ZC - KCD1_X / 2, KCD1_ZC + KCD1_X / 2
    p.B((-7.5, 7.5), (W - 0.01, KCD1_RECESS + 2.4), (kz0 - 1.0, kz1 + 1.0))
    p.rrect_y(-7.9, 7.9, KCD1_ZC - 10.9, KCD1_ZC + 10.9, -1, KCD1_RECESS, 1.5, cut=True)
    p.B((-KCD1_Z / 2, KCD1_Z / 2), (-1, KCD1_RECESS + 3), (kz0, kz1), cut=True)
    # battery door opening (the door carries the holder and clamp) + 4 screw lugs over its edges
    p.rrect_y(-DOOR['x'] - 0.2, DOOR['x'] + 0.2, DOOR['z0'] - 0.2, DOOR['z1'] + 0.2, -1, W + 1, DOOR['r'] + 0.2, cut=True)
    for x, z in DOOR_SCREWS:
        s = 1 if x > 0 else -1
        # v3.1: lugs 0.8 taller (top 9.4, pilot to 8.6) so an M2 x 6 fits without piercing the lug top (v3: M2 x 5 max)
        p.B((s * (DOOR['x'] + 0.2), s * 29.0), (W - 0.01, DOOR_LUG_TOP), (z - 4, z + 4))
        p.B((s * 20.9, s * (DOOR['x'] + 0.21)), (W + 1.2, DOOR_LUG_TOP), (z - 4, z + 4))
        p.CY(x, z, PILOT_R, (W + 1.1, DOOR_LUG_TOP - 0.8), cut=True)
    # chest / rump: laser wedges, thickened walls behind the bands, band recess, windows, lid screws, hook slots
    for sz in (-1, 1):
        p.poly_x(laser_wedge_pts(sz), -13, 13)
        # v3.1: the wedge stood on the v3 wall face (77.6); fill to the thin wall and keep >= 0.9 behind the
        # band recess where there is no thickened zone (behind the laser; at the rump also round the USB-C)
        p.B((-13.4, 13.4), (8.1, 29.0), (sz * (TZ - W - 0.1), sz * (il + 0.01)))
        if sz < 0:
            p.B((18.2, 36.4), (22.35, 31.4), (sz * (TZ - W), sz * (il + 0.01)))
        for x0, x1, y0, y1 in band_zones(sz):
            p.B((x0, x1), (y0, y1), (sz * WALL_THICK_Z, sz * (il + 0.01)))
        for x, s in LID_SCREWS:
            if s == sz:
                p.B((x - 3.5, x + 3.5), (29.0, TUB_H), (sz * WALL_THICK_Z, sz * (il + 0.01)))
    if CHG_X:
        p.B(CHG_X, (CHG_Y0 - 2.0, CHG_Y0), (-(il + 0.01), -70.5))      # charger ledge on the rump wall
    for sz in (-1, 1):
        rz = sz * (TZ - BAND['t'])
        p.rrect_z(-BAND['x'] - BAND_GAP, BAND['x'] + BAND_GAP, BAND['y0'] - BAND_GAP, BAND['y1'] + BAND_GAP,
                  rz, sz * (TZ + 1), BAND['r'] + BAND_GAP, cut=True)
        w, h, r, yc = LASER_WIN
        p.rrect_z(-w / 2, w / 2, yc - h / 2, yc + h / 2, sz * 73.0, sz * (TZ + 1), r, cut=True)
        for x, s in LID_SCREWS:
            if s == sz:
                p.CZ(x, LID_SCREW_Y, CLEAR_R, (sz * (WALL_THICK_Z - 0.8), sz * (TZ + 1)), cut=True)
                p.CZ(x, LID_SCREW_Y, CBORE_R, (sz * (TZ - BAND['t'] - 1.6), sz * (TZ + 1)), cut=True)
        for sx in (-1, 1):
            hx = sx * BAND_HOOK_X
            p.B((hx - 2.2, hx + 2.2), (BAND_HOOK_Y - 0.4, BAND_HOOK_Y + 0.9), (sz * (WALL_THICK_Z - 0.1), rz), cut=True)
    # USB-C: the rump wall hugs the receptacle (the "shroud": no board edge shows through the band's pill)
    p.rrect_z(USB_X - 4.7, USB_X + 4.7, USB_Y - 1.85, USB_Y + 1.85, -(TZ + 1), -(TZ - W - 0.5), 1.3, cut=True)


SIDE_LASER_DY = -1.4     # side VL53L0X shelf lowered so the chip sits behind the window (window clear of the R6 top)
SIDE_WIN = (-6.0, 6.0, 36.9, 43.5)                   # z0, z1, y0, y1: 12 x 6.6 stadium + 0.5 chamfer = 13 x 7.6 outline
TOUCH_PADS = [(-30.0, -25.0), (30.0, -25.0), (-28.0, -60.0), (28.0, -60.0)]


LID_BRIDGE_Y = TUB_H + 1.6      # v3.1: the lid keeps its full section from y 36 to here (joins the lip to the wall)
LID_R6 = 6.0                     # the lid's top perimeter round


def lid_wall_loop(half, half_top=None):
    """v3.1 inside outline (u, v=y) of a lid wall cut: flat to y 44, then an arc concentric with the R6 top round
    (so the wall stays LID_WALL thick round it) up to the 2.4 lid top. half = |u| of the wall's inner face."""
    c, r = half + LID_WALL - LID_R6, LID_R6 - LID_WALL          # arc centre |u| (36 / 74) and radius 4.4
    yc, ceil = LID_TOP - LID_R6, LID_TOP - W                     # 44.0, 47.6
    ut = c + math.sqrt(r * r - (ceil - yc) ** 2)                 # where the arc meets the ceiling (38.53 / 76.53)
    return [('L', (-half, LID_BRIDGE_Y), (half, LID_BRIDGE_Y)), ('L', (half, LID_BRIDGE_Y), (half, yc)),
            ('A', (c, yc), (half, yc), (ut, ceil), True), ('L', (ut, ceil), (-ut, ceil)),
            ('A', (-c, yc), (-ut, ceil), (-half, yc), True), ('L', (-half, yc), (-half, LID_BRIDGE_Y))]


def lid_wall_cuts(p):
    """v3.1: hollow the lid's 5.1 (sides) and 7.4 (ends) walls to LID_WALL from the inside, above the bridge
    that joins the lip to the wall. Side cut along z over |z| <= 74, end cut along x over |x| <= 36 (the four
    corners, where the top round wraps the plan corner, stay solid). Invisible from outside."""
    sw_, sz_ = TX - LID_WALL, TZ - LID_WALL                      # 40.4, 78.4
    p.prism('z', lid_wall_loop(sw_), -(sz_ - (LID_R6 - LID_WALL)), sz_ - (LID_R6 - LID_WALL), cut=True)
    p.prism('x', lid_wall_loop(sz_), -(sw_ - (LID_R6 - LID_WALL)), sw_ - (LID_R6 - LID_WALL), cut=True)


def torso_lid_v3(p):
    """LID (warm white). R6 top perimeter, R1 plan corners. Holds the MPU6050, MPR121, perfboard hub, the tail
    MG90S (hangs from a rib, shaft up into the tail socket), 2 side VL53L0X, 4 touch pads; its lip combs clamp the
    hip leads in the tub-wall notches."""
    top = LID_TOP - W                                                    # 47.6 ceiling underside
    p.prism('y', swlib.rrect(-TX, TX, -TZ, TZ, 1.0), TUB_H, LID_TOP)
    p.fillet_safe(6.0, [(0.0, LID_TOP, TZ)])
    zi, zo = LID_LIP_Z
    lo = TUB_IN - 0.3                                                    # v3.1 lip outer 40.1 (0.3 inside the tub wall)
    p.B((-lo, lo), (LIP_Y0, TUB_H + 0.5), (-zo, zo))                     # lip into the tub
    p.B((-(lo - LID_LIP_T), lo - LID_LIP_T), (LIP_Y0 - 1, top), (-zi, zi), cut=True)
    lid_wall_cuts(p)                                                     # v3.1: 1.6 walls above the bridge
    for x, sz in LID_SCREWS:
        p.CZ(x, LID_SCREW_Y, 3.0, (sz * 71, sz * zo))                      # lip screw boss
        p.CZ(x, LID_SCREW_Y, PILOT_R, (sz * 70, sz * (zo + 0.1)), cut=True)
    # hip-lead combs: plug each tub-wall notch from the lip; 3 teeth press the leads onto the notch floor
    for sx in (-1, 1):
        for sz in (-1, 1):
            hz = LEGS[sz][0]
            p.B((sx * 39.2, sx * (TX - 0.05)), (LEAD_EXIT_Y[1] + 0.6, TUB_H + 0.01), (hz - 4.4, hz + 4.4))
            for dz in (-3.0, 0.0, 3.0):
                p.B((sx * 39.2, sx * (TX - 0.05)), (LEAD_EXIT_Y[1], LEAD_EXIT_Y[1] + 0.61), (hz + dz - 0.5, hz + dz + 0.5))
    # neck -> collar: cable hole + 4 screw holes counterbored from inside
    p.B((-11, 11), (top - 1, LID_TOP + 1), (53, 67), cut=True)
    for x, z in LID_NECK_SCREWS:
        p.CY(x, z, CLEAR_R, (top - 1, LID_TOP + 1), cut=True)
        p.CY(x, z, CBORE_R, (top - 0.5, top + CBORE_D), cut=True)
    # tail: MG90S turned 90 deg (case along +x) hanging from two ribs under the ceiling; socket for the root
    for x0, x1 in ((-10.85, -6.3), (17.1, 21.65)):
        p.B((x0, x1), (TUB_H + 0.4, top + 0.01), (TAIL_Z - SV_W / 2, TAIL_Z + SV_W / 2))
    for d in (-SV_HOLES / 2, SV_HOLES / 2):
        p.B((BODY_C + d - PILOT_R - SV_HOLE_SLOT, BODY_C + d + PILOT_R + SV_HOLE_SLOT), (TUB_H + 0.3, TUB_H + 4.5),
            (TAIL_Z - PILOT_R, TAIL_Z + PILOT_R), cut=True)
    sr, sf = TAIL_SOCKET['r'], TAIL_SOCKET['floor']
    p.CY(0, TAIL_Z, sr + 1.2, (sf - 1.2, top + 0.01))
    p.CY(0, TAIL_Z, sr, (sf, LID_TOP + 1), cut=True)
    p.CY(0, TAIL_Z, 4.4, (sf - 2, sf + 0.1), cut=True)
    # side lasers (VL53L0X) on a shelf against each side wall; 12 x 7 stadium window, 1 x 45 chamfer outside
    dy = SIDE_LASER_DY
    for sx in (-1, 1):
        p.B((sx * 32.1, sx * (TUB_IN - 0.3 - LID_LIP_T + 0.01)), (34.4 + dy, 35.6 + dy), (-13.5, 13.5))   # v3.1: to the 1.8 lip
        p.B((sx * 31.5, sx * 32.7), (34.4 + dy, 38.0 + dy), (-11, 11))
        for zr in ((9, 11), (-11, -9)):
            p.B((sx * 31.5, sx * 32.7), (34.4 + dy, top), zr)
        z0, z1, y0, y1 = SIDE_WIN
        p.prism('x', swlib.stadium(z0, z1, y0, y1), *rng(sx * 35.9, sx * (TX + 1)), cut=True)
        p.chamfer_safe(0.5, [(sx * TX, y1, 0.0)])
    # fences hanging from the ceiling: IMU (21.6 x 16.8), MPR121 (30.5 x 20.3), hub (perfboard cut to 50 x 35)
    fences = [((-9.8, -8.6), (3.6, 26.0)), ((8.6, 9.8), (3.6, 26.0)), ((-9.8, 9.8), (2.4, 3.6)), ((-9.8, 9.8), (26.0, 27.2)),
              ((14.9, 16.1), (16.5, 47.0)), ((14.9, 31.4), (15.3, 16.5)),
              ((-26.4, -25.2), (-37.5, -1.5)), ((25.2, 26.4), (-37.5, -1.5)), ((-26.4, 26.4), (-38.7, -37.5)),
              ((-26.4, 26.4), (-1.5, -0.3))]
    fences = fences[:6] + [(xr, (zr[0] + HUB_DZ, zr[1] + HUB_DZ)) for xr, zr in fences[6:]]   # v3.1: hub moved back
    for xr, zr in fences:
        p.B(xr, (top - 2.5, top), zr)
    for sx in (-1, 1):
        for z in (-30.0 + HUB_DZ, -10.0 + HUB_DZ):                      # v3.1: tie anchors follow the hub
            p.B((sx * 27.4, sx * 31.4), (top - 5, top), (z - 1.5, z + 1.5))
            p.B((sx * 28.4, sx * 30.4), (top - 3.5, top + 0.01), (z - 2, z + 2), cut=True)
    # foil touch pads under the ceiling, a 0.3 raised oval over each one on the top
    for x, z in TOUCH_PADS:
        p.pad_boss(x, z, top)
        p.oval_y(x, z, 5.0, 8.0, LID_TOP - 0.01, LID_TOP + 0.3)


def side_panel(p, sx):
    """SIDE PANEL (graphite), x 42 -> 48.6 over the whole tub side: skin 46.8-48.6 on a 1.8 frame + 3 ribs that
    stand on the tub wall. Covers the hip servo tabs, tab screws, gear-case tops and the lead passages. Only
    openings: the dia 13.4 hole for each hip boss and the 9 x 5 lead slot, both under the thigh cup. Held by
    4 snap hooks through windows in the tub wall (no screws) and located by the two hip bosses.
    Printed outer face down (bed edges chamfered)."""
    X = lambda a, b: rng(sx * a, sx * b)
    p.prism('x', swlib.rrect(-TZ, TZ, 0.0, TUB_H, (BELLY_R, BELLY_R, 4.0, 4.0)), *X(PANEL_IN, FLANK))
    R = PANEL_END_R
    cx, cz = FLANK - R, TZ - R
    corner = [('L', (FLANK, cz), (FLANK + 1, cz)), ('L', (FLANK + 1, cz), (FLANK + 1, TZ + 1)),
              ('L', (FLANK + 1, TZ + 1), (cx, TZ + 1)), ('L', (cx, TZ + 1), (cx, TZ)),
              ('A', (cx, cz), (cx, TZ), (FLANK, cz), False)]
    for sz in (-1, 1):
        lp = map_loop(corner, lambda q, a=sx, b=sz: (a * q[0], b * q[1]), sx * sz < 0)
        p.prism('y', lp, -1.0, TUB_H + 1.0, cut=True)
    p.chamfer_safe(1.0, [(sx * FLANK, TUB_H, 0.0), (sx * FLANK, 0.0, 0.0)])
    p.prism('x', swlib.rrect(-77.2, 77.2, 1.8, TUB_H - 1.8, (5.2, 5.2, 2.2, 2.2)), *X(PANEL_IN - 0.1, PANEL_SKIN), cut=True)
    # v3.1 note: a 1.6 skin here would save 2.8 g but sits just behind the centre of mass (the balance margin
    # lost 0.05 mm), so the panels stay exactly v3
    for z in (-20.0, 0.0, 20.0):
        p.B(X(PANEL_IN, PANEL_SKIN + 0.01), (1.79, TUB_H - 1.79), (z - 0.8, z + 0.8))
    for sz in (-1, 1):
        hz = LEGS[sz][0]
        p.CX(HIP_Y, hz, 6.7, X(PANEL_IN - 1, FLANK + 1), cut=True)
        p.prism('x', swlib.rrect(hz - 4.5, hz + 4.5, 26.5, 31.5, 1.0), *X(PANEL_SKIN - 0.1, FLANK + 1), cut=True)
    for z, y in PANEL_HOOKS:
        t = TUB_IN                                  # v3.1: the catch follows the tub wall's inner face (v3 39.6)
        prof = [(PANEL_SKIN + 0.01, y), (t - 1.2, y), (t - 1.2, y + 1.2), (t - 0.5, y + 1.8), (t - 0.1, y + 1.8),
                (t - 0.1, y + 1.2), (PANEL_SKIN + 0.01, y + 1.2)]
        p.poly_z([(sx * a, b) for a, b in prof], z - 1.75, z + 1.75)


def band(p, sz):
    """CHEST (sz=+1) / RUMP (-1) BAND (graphite), 72 x 26 R4 x 1.6, snaps flush into the recess over the lid
    screws (2 hooks, pry notch at the bottom centre). Obstacle-laser window 10 x 8 R2; the rump band also has the
    13 x 7 USB-C pill. Printed outer face down."""
    b = BAND
    p.rrect_z(-b['x'], b['x'], b['y0'], b['y1'], sz * (TZ - b['t']), sz * TZ, b['r'])
    p.chamfer_safe(0.5, [(0.0, b['y1'], sz * TZ)])
    w, h, r, yc = LASER_WIN
    p.rrect_z(-w / 2, w / 2, yc - h / 2, yc + h / 2, sz * (TZ - 2), sz * (TZ + 1), r, cut=True)
    p.chamfer_safe(0.5, [(0.0, yc + h / 2, sz * TZ)])
    if sz < 0:
        L, H = USB_PILL
        p.prism('z', swlib.stadium(USB_X - L / 2, USB_X + L / 2, USB_Y - H / 2, USB_Y + H / 2), -(TZ + 1), -(TZ - 2), cut=True)
        p.chamfer_safe(0.5, [(USB_X, USB_Y + H / 2, -TZ)])
    p.B((-1.5, 1.5), (b['y0'] - 0.1, b['y0'] + 0.8), (sz * (TZ - 0.8), sz * (TZ + 0.1)), cut=True)   # pry notch
    y = BAND_HOOK_Y
    prof = [(TZ - b['t'] + 0.01, y), (74.6, y), (74.6, y + 0.8), (74.9, y + 1.1), (75.2, y + 1.1), (75.2, y + 0.8),
            (TZ - b['t'] + 0.01, y + 0.8)]
    for sx in (-1, 1):
        hx = sx * BAND_HOOK_X
        p.poly_x([(sz * a, c) for a, c in prof], hx - 2.0, hx + 2.0)


def battery_door(p):
    """BATTERY DOOR (graphite), flush in the belly: carries the 2x18650 holder (side fences, end stops) and the
    clamp posts, so the battery comes out without opening the lid. 4 x M2 x 6 into lugs of the tub, heads in
    counterbores under 4 black plugs; pry notch at the rear edge. Printed outer face down."""
    d = DOOR
    p.rrect_y(-d['x'], d['x'], d['z0'], d['z1'], 0.0, W, d['r'])
    p.chamfer_safe(0.5, [(0.0, 0.0, d['z1'])])
    for x, z in DOOR_SCREWS:
        s = 1 if x > 0 else -1
        p.B((s * 20.9, s * 25.9), (W - 0.01, W + 1.2), (z - 4, z + 4))
    for sx in (-1, 1):
        p.B((sx * 20.7, sx * 22.2), (W - 0.01, W + 4), (-44, 14))                 # holder side fences
        p.B((sx * 21.0, sx * 25.8), (W - 0.01, 20.75), CLAMP_Z)                  # clamp posts
        p.CY(sx * 23.4, -35, PILOT_R, (8, 21.75), cut=True)
        for zr in ((-53.8, BAT_Z[0] - 0.3), (BAT_Z[1] + 0.3, 25.8)):            # holder end stops
            p.B((sx * 6, sx * 13), (W - 0.01, W + 4), zr)
    for x, z in DOOR_SCREWS:
        p.CY(x, z, DOOR_CBORE_R, (-1, PLUG_T + SCREW_HEAD_H), cut=True)
        p.CY(x, z, CLEAR_R, (PLUG_T + SCREW_HEAD_H - 0.1, W + 1.3), cut=True)
    p.B((-2.0, 2.0), (-0.1, 0.8), (d['z0'] - 0.1, d['z0'] + 0.9), cut=True)       # pry notch


def screw_plugs(p):
    """4 black plugs pressed over the battery door screws (flush with the belly)."""
    p.merge = False
    for x, z in DOOR_SCREWS:
        p.CY(x, z, PLUG_R, (0.0, PLUG_T))


def collar(p):
    """COLLAR (graphite), replaces the neck: x +-42, z 36-80, y 50-59.2, R3 plan corners, 0.5 chamfers. Four 0.8
    standoffs (the head-screw bosses) give an even 0.8 gap to the head; the cable sleeve rises 1.5 into the head's
    cable hole so no lead shows in the gap. Same 8 screws as v2, all driven from inside. Printed top face down."""
    y0, y1 = LID_TOP, HEAD['y0'] - REVEAL
    p.prism('y', swlib.rrect(-TX, TX, 36.0, 80.0, 3.0), y0, y1)
    p.chamfer_safe(0.5, [(0.0, y0, 80.0)])
    p.chamfer_safe(0.5, [(0.0, y1, 80.0)])
    cw = COLLAR_W                                  # v3.1: thin walls (v3 2.4), inner corners concentric with the R3
    p.prism('y', swlib.rrect(-TX + cw, TX - cw, 36.0 + cw, 80.0 - cw, 3.0 - cw), y0 - 1, y1 - 1.2, cut=True)
    for x, z in LID_NECK_SCREWS:
        p.CY(x, z, 3.0, (y0, y1 - 1.19))
        p.CY(x, z, PILOT_R, (y0 - 1, y0 + 8.4), cut=True)
    for x, z in HEAD_NECK_SCREWS:
        p.CY(x, z, 3.0, (y0, HEAD['y0']))
        p.CY(x, z, PILOT_R, (HEAD['y0'] - 8.5, HEAD['y0'] + 1), cut=True)
    # flange on the lid's flat top: closes the slit the lid's R6 round leaves under the collar walls
    p.prism('y', [swlib.rrect(-TX + cw + 0.01, TX - cw - 0.01, 36.0 + cw - 0.01, 80.0 - cw + 0.01, 3.0 - cw),
                  swlib.rrect(-34.6, 34.6, 36.0 + W + 1.2, 72.6, 1.0)], y0, y0 + 1.2)
    p.prism('y', swlib.rrect(-10.6, 10.6, 53.4, 66.6, 1.5), y1 - 1.21, HEAD['y0'] + 1.5)      # cable sleeve
    p.prism('y', swlib.rrect(-9.0, 9.0, 55.0, 65.0, 1.0), y0 - 1, HEAD['y0'] + 2.0, cut=True)


HEAD_HOOKS = [(x, 1) for x in (-25.0, 0.0, 25.0)] + [(x, -1) for x in (-30.0, 30.0)]   # (x, top/bottom)
HOOK_Z = (51.6, 52.6)                           # barb on the head-back hooks (inside the front half)
HOOK_POCKET = 0.4                               # v3.1 detent pocket depth in the 1.6 head wall (v3 0.7 in 2.4): the
                                                # barb enters 0.2, 0.2 clearance; 1.2 skin behind this 5.2 x 1.8 recess
NECK_PAD_R = 3.4                                # v3.1 pads under the 4 collar-screw heads in the head floor
NECK_NOTCH_X = 9.8                              # v3.1 head-back lip notch |x| over the front collar-screw pads
HEAD_BACK_RIBS = (75.0, 140.0)                  # v3.1 stiffening ribs (y) inside the head back, 1.2 x 3, |x| <= 50
                                                # (on the flat part of the back, y 70-148; under / over the speaker)
EAR_PAD = EAR['sink'] + 2.0 - HEAD_W            # v3.1 pad under each ear pocket (2.0 left under the 1.0 pocket)


def head_shell(p, open_z):
    """The whole head as one rounded shell: R8 long edges (lower/upper side edges), R8 face perimeter, R10 back
    perimeter, 2.4 wall, open on the face at z = open_z. v3.1: HEAD_W (1.8) wall."""
    h = HEAD
    p.prism('z', swlib.rrect(-h['x'], h['x'], h['y0'], h['y1'], 8.0), h['z0'], h['z1'])
    p.fillet(8.0, [(0.0, h['y1'], h['z1'])])
    p.fillet(10.0, [(0.0, h['y1'], h['z0'])])
    p.shell(HEAD_W, [(0.0, 110.0, open_z)])


def head_inner():
    """v3.1 inner faces of the head shell: (x, y0, y1, face z, corner radius)."""
    h = HEAD
    return h['x'] - HEAD_W, h['y0'] + HEAD_W, h['y1'] - HEAD_W, h['z1'] - HEAD_W, 8.0 - HEAD_W


def door_opening(p, sx, zc, yc, x_in, x_out, groove=True):
    """18 x 12 R6 opening for a flush snap-in port door, with the two catch grooves in its straight sides."""
    p.prism('x', swlib.stadium(zc - DOOR_H / 2, zc + DOOR_H / 2, yc - DOOR_L / 2, yc + DOOR_L / 2),
            *rng(sx * (x_in - 0.5), sx * (x_out + 1)), cut=True)
    if groove:
        xm = (x_in + x_out) / 2
        for s in (-1, 1):
            p.B(rng(sx * (xm - 0.6), sx * (xm + 0.6)), (yc - 3.2, yc + 3.2),
                sorted((zc + s * (DOOR_H / 2 - 0.1), zc + s * (DOOR_H / 2 + 0.5))), cut=True)


def head_front_v3(p):
    """HEAD FRONT (warm white), z 46.5 -> 80. Holds the Guition screen (4 blind bosses), the 2 MS3625 mics (rings
    + 3-hole triangles), the head touch pad, the ears (keyed pockets). 45 deg bevelled screen frame with R3
    corners; matching port-door openings on both sides (screen USB-C behind the right one)."""
    h = HEAD
    ix, iy0, iy1, izf, _ = head_inner()          # v3.1: 1.6 shell (61.4 / 61.6 / 156.4 / 78.4)
    iz1 = GLASS_Z                                # 77.6: the glass still seats 2.4 behind the face, as in v3
    head_shell(p, h['z0'])
    p.B((-70, 70), (50, 170), (h['z0'] - 1, HB_SPLIT), cut=True)
    p.chamfer_safe(0.3, [(0.0, h['y1'], HB_SPLIT)])
    # v3.1 screen frame: the face is 2.4 again round the screen (glass seat, 2.2 bevel, the 4 bosses); a plate
    # inside the thin face, the window cut below removes its middle
    p.rrect_z(-59.5, 59.5, 75.0, 144.2, iz1, izf + 0.01, 3.0)
    # screen window: active area + 1 mm, R3 corners, 45 deg bevel through the wall
    wy0, wy1 = BOARD_Y0 + 9.34, BOARD_Y0 + 65.2
    p.rrect_z(-48.5, 48.5, wy0, wy1, iz1 - 1, h['z1'] + 1, 3.0, cut=True)
    p.chamfer_safe(2.2, [(0.0, wy1, h['z1'])])
    for x in (-56.3, 56.3):
        for y in (BOARD_Y0 + 4.05, BOARD_Y0 + 66.15):
            p.CZ(x, y, BOSS_R, (PCB_FRONT, iz1 + 0.3))
            p.CZ(x, y, PILOT_R, (PCB_FRONT - 1, 78.2), cut=True)
    # screen board P1 power plug: blind pocket in the right wall (wires bend into it)
    p.B((-h['x'] + 0.8, -ix + 0.5), (BOARD_Y0 + 20.0, BOARD_Y0 + 33.1), (PCB_FRONT - 11.0, PCB_FRONT + 1.0), cut=True)
    for sx in (-1, 1):
        door_opening(p, sx, HEAD_DOOR['zc'], HEAD_DOOR['yc'], ix, h['x'])
        p.CX(MIC_Y, MIC_Z, 8.3, (sx * (ix - 1.2), sx * (ix + 0.1)))
        p.CX(MIC_Y, MIC_Z, 7.3, (sx * (ix - 1.3), sx * ix), cut=True)
        holes = [swlib.circle((MIC_Z + dz, MIC_Y + dy), 0.4) for dz, dy in ((0.0, 3.0), (-2.6, -1.5), (2.6, -1.5))]
        p.multi_cut('x', holes, sx * (ix - 1), sx * (h['x'] + 1))
    # collar below: cable hole + 4 screws. v3.1: no counterbores in the thin floor; a pad under each head
    # (clamps 2.4, as v3); the head back's lip is notched over the front pair (see head_back_v3)
    for x, z in HEAD_NECK_SCREWS:
        p.CY(x, z, NECK_PAD_R, (iy0 - 0.01, h['y0'] + W))       # clamps 2.4, as v3
    p.B((-11, 11), (h['y0'] - 1, iy0 + 1), (53, 67), cut=True)
    for x, z in HEAD_NECK_SCREWS:
        p.CY(x, z, CLEAR_R, (h['y0'] - 1, iy0 + 1.2), cut=True)
    # muzzle in front: cable hole + 4 screws. v3.1: pads make the face 2.4 under each head (no counterbore)
    for x, y in MUZ_SCREWS:
        p.CZ(x, y, 3.5, (iz1, izf + 0.01))
    p.B((-10, 10), (63, 72), (iz1 - 1, h['z1'] + 1), cut=True)
    for x, y in MUZ_SCREWS:
        p.CZ(x, y, CLEAR_R, (iz1 - 1, h['z1'] + 1), cut=True)
    # touch pad under the top + raised oval over it
    p.pad_boss(0.0, 58.0, iy1, wall=HEAD_W)
    p.oval_y(0.0, 58.0, 8.0, 5.0, h['y1'] - 0.01, h['y1'] + 0.3)
    # ears: 1 mm keyed pocket, peg hole, M2 x 8 hole (screw from inside). v3.1: a pad inside under each ear
    # keeps 2.0 under the pocket (the thin top alone would leave 0.6)
    for sx in (-1, 1):
        xc = sx * EAR['x']
        b = ear_half_at(h['y1'] - EAR['sink']) + 0.2
        p.rrect_y(xc - b - 2.0, xc + b + 2.0, EAR['z'] - EAR['t'] / 2 - 2.2, EAR['z'] + EAR['t'] / 2 + 2.2,
                  iy1 - EAR_PAD, iy1 + 0.01, EAR['edge'] + 2.2)
        p.rrect_y(xc - b, xc + b, EAR['z'] - EAR['t'] / 2 - 0.2, EAR['z'] + EAR['t'] / 2 + 0.2,
                  h['y1'] - EAR['sink'], h['y1'] + 1, EAR['edge'] + 0.2, cut=True)
        p.B((xc - 3.15, xc + 3.15), (iy1 - EAR_PAD - 1, h['y1']), (EAR['z'] - 2.15, EAR['z'] + 2.15), cut=True)
        p.CY(xc + sx * 6.5, EAR['z'], CLEAR_R, (iy1 - EAR_PAD - 1, h['y1']), cut=True)
    # pockets for the head-back snap hooks (v3.1: 0.5 deep, v3 0.7 - the barb enters 0.2)
    for x, s in HEAD_HOOKS:
        yr = (iy1 - 0.1, iy1 + HOOK_POCKET) if s > 0 else (iy0 - HOOK_POCKET, iy0 + 0.1)
        p.B((x - 2.4, x + 2.4), yr, (HOOK_Z[0] - 0.2, HOOK_Z[1] + 0.2), cut=True)


def head_back_v3(p):
    """HEAD BACK (warm white), z 36 -> 46.5: the whole R10 back perimeter, the centred speaker (fences) behind a
    9 x 9 grille, a lip that slides 4 mm into the front half with 5 snap hooks (3 top, 2 bottom; 45 deg release
    faces, so it pulls off). No screws, no BOOT/RST holes."""
    h = HEAD
    head_shell(p, h['z1'])
    p.B((-70, 70), (50, 170), (HB_SPLIT, h['z1'] + 1), cut=True)
    p.chamfer_safe(0.3, [(0.0, h['y1'], HB_SPLIT)])
    # v3.1: the lip follows the front half's thin inner faces (0.2 slide gap, 1.2 lip, as v3)
    ix, iy0, iy1, _, ir = head_inner()
    lip = lambda d: swlib.rrect(-(ix + d), ix + d, iy0 - d, iy1 + d, ir + d)
    inner = lip(-1.4)
    p.prism('z', [lip(0.2), inner], 45.5, HB_SPLIT)
    p.prism('z', [lip(-0.2), inner], HB_SPLIT - 0.01, HB_SPLIT + 4.0)
    # notch over the front pair of collar screws (their pads and heads sit on the head floor at z 50)
    p.B((-NECK_NOTCH_X, NECK_NOTCH_X), (iy0 + 0.1, iy0 + 1.5), (HB_SPLIT - 0.5, HB_SPLIT + 4.1), cut=True)
    for x, s in HEAD_HOOKS:
        ya, yb = (iy1 - 1.4, iy1 - 0.2) if s > 0 else (iy0 + 0.2, iy0 + 1.4)
        for e in (-1, 1):
            p.B(sorted((x + e * 2.0, x + e * 2.6)), (ya - 0.1, yb + 0.1), (47.0, HB_SPLIT + 4.1), cut=True)
        yo = yb if s > 0 else ya                       # the face the barb stands on
        beam = (yo - 1.0, yo) if s > 0 else (yo, yo + 1.0)
        p.B((x - 2.0, x + 2.0), beam, (HB_SPLIT + 3.99, HOOK_Z[1]))
        barb = [(HOOK_Z[0], yo), (HOOK_Z[1], yo), (HOOK_Z[1], yo + s * 0.05), (HOOK_Z[1] - 0.4, yo + s * 0.4),
                (HOOK_Z[0] + 0.4, yo + s * 0.4)]
        p.poly_x([(z, y - s * 0.01) for z, y in barb], x - 2.0, x + 2.0)
    grille = [swlib.circle((a * 2.6, 95.5 + c * 2.6), 0.8) for a in range(-4, 5) for c in range(-4, 5)]
    p.multi_cut('z', grille, h['z0'] - 1, h['z0'] + W + 1)
    for xr, yr in (((-16.5, -15.3), (79, 112)), ((15.3, 16.5), (79, 112)), ((-15.3, 15.3), (112.3, 113.5)),
                   ((-15.3, 15.3), (77.5, 78.7))):
        p.B(xr, yr, (h['z0'] + HEAD_W - 0.01, h['z0'] + HEAD_W + 3))      # v3.1: on the thin back wall
    # v3.1: two ribs stiffen the 1.6 back (the widest thin flat panel), clear of the speaker fences and the grille
    for yr in HEAD_BACK_RIBS:
        p.B((-50.0, 50.0), (yr - 0.6, yr + 0.6), (h['z0'] + HEAD_W - 0.01, h['z0'] + HEAD_W + 3))


def muzzle_v3(p):
    """MUZZLE (warm white), 0.8 in front of the head on 4 standoffs. R6 front-view corners, R3 front perimeter.
    Holds the ESP32-S3 CAM board, the OV5640 (lens pocket) and the APDS-9960 (mirrored to +12.5); identical
    12.2 x 9 R2 windows with 0.5 chamfers; port door on the left (camera USB-C), matching blank on the right."""
    m, fz = MUZ, MUZ_FZ
    ix, iy0, iy1 = m['x'] - MUZ_W, m['y0'] + W, m['y1'] - MUZ_W     # v3.1: 1.8 sides + top; floor + front 2.4
    p.prism('z', swlib.rrect(-m['x'], m['x'], m['y0'], m['y1'], 6.0), m['z0'], m['z1'])
    p.fillet(3.0, [(0.0, m['y1'], m['z1'])])
    # inner corners: R3.6 at the floor (as v3), concentric R4.2 at the top (keeps 1.8 round the R6)
    p.prism('z', swlib.rrect(-ix, ix, iy0, iy1, (3.6, 3.6, 6.0 - MUZ_W, 6.0 - MUZ_W)), m['z0'] - 1, fz, cut=True)
    for sx in (-1, 1):
        p.B((sx * 28.9, sx * (ix + 0.5)), (65.3, iy1 + 0.01), (m['z0'], m['z0'] + 6))          # screw blocks
        c = ix + 0.5 - 28.9
        p.poly_y([(sx * 28.9, m['z0'] + 6), (sx * (ix + 0.5), m['z0'] + 6), (sx * (ix + 0.5), m['z0'] + 6 + c)], 65.3, iy1 + 0.01)
        p.B((sx * 28.9, sx * (ix + 0.01)), (iy0 - 0.01, 60.0), (m['z0'], m['z0'] + 1.2))      # back fins: no look inside
        p.B((sx * 22, sx * 26), (iy0 - 0.01, iy0 + 3), (CAM_PCB_Z, CAM_PCB_Z + 2))            # board rests
        p.B((sx * 22, sx * 26), (iy1 - 3, iy1 + 0.01), (CAM_PCB_Z, CAM_PCB_Z + 2))
        door_opening(p, sx, MUZ_DOOR['zc'], MUZ_DOOR['yc'], ix, m['x'])
    for x, y in MUZ_SCREWS:
        p.CZ(x, y, 2.0, (m['z0'] - 0.8, m['z0'] + 0.01))                                    # 0.8 standoffs
        p.CZ(x, y, PILOT_R, (m['z0'] - 1, m['z0'] + 7), cut=True)
    # OV5640 lens-holder pocket in a boss; APDS-9960 shelf + fences; identical windows
    p.B((LENS_X - 6.5, LENS_X + 6.5), (LENS_Y - 6.5, LENS_Y + 6.5), (fz - 3, fz + 0.01))
    p.B((LENS_X - 4.55, LENS_X + 4.55), (LENS_Y - 4.55, LENS_Y + 4.55), (fz - 4, fz + 0.1), cut=True)
    ax0, ax1 = APDS_X - 10.3, APDS_X + 10.3
    p.B((ax0, ax1), (iy0 - 0.01, LENS_Y - 7.8), (fz - 2.5, fz + 0.01))
    for xr in ((ax0 - 1.2, ax0), (ax1, ax1 + 1.2)):
        p.B(xr, (iy0 - 0.01, iy1 + 0.01), (fz - 2.5, fz + 0.01))
    w, hh, r = MUZ_WIN
    for x in (LENS_X, APDS_X):
        p.rrect_z(x - w / 2, x + w / 2, LENS_Y - hh / 2, LENS_Y + hh / 2, fz - 1, m['z1'] + 1, r, cut=True)
        p.chamfer_safe(0.5, [(x, LENS_Y + hh / 2, m['z1'])])


def ear_geom():
    """Ear front outline: a triangle whose apex is rounded R5 so the tip is EAR['h'] above the head top; base at
    the pocket floor. Returns (half-width at the base, apex height above the base)."""
    yb = HEAD['y1'] - EAR['sink']
    want = EAR['h'] + EAR['sink']
    b, r = EAR['half'] * 1.02, EAR['tip']
    lo, hi = 20.0, 120.0
    for _ in range(80):
        H = (lo + hi) / 2
        top = H - r * math.hypot(b, H) / b + r
        lo, hi = (H, hi) if top < want else (lo, H)
    return b, H, yb


def ear_half_at(y):
    b, H, yb = ear_geom()
    return b * (1 - (y - yb) / H)


def ear_v3(p, sx):
    """EAR (warm white): tapered, R5 tip, R2.5 edges, leaning back 10 deg, sunk 1 mm in a keyed pocket; a 6 x 4
    peg and one M2 x 8 from inside the head hold it (replaceable)."""
    b, H, yb = ear_geom()
    xc, zc, t = sx * EAR['x'], EAR['z'], EAR['t']
    tl = math.tan(math.radians(EAR['lean']))
    y1 = HEAD['y1']
    p.prism('z', swlib.rpoly([(xc - b, yb), (xc + b, yb), (xc, yb + H)], [0.0, 0.0, EAR['tip']]), zc - t / 2 - 9, zc + t / 2 + 1)
    zf = lambda y: zc + t / 2 - (y - y1) * tl
    zb = lambda y: zc - t / 2 - (y - y1) * tl
    p.poly_x([(zf(150), 150), (zc + 20, 150), (zc + 20, 200), (zf(200), 200)], xc - 15, xc + 15, cut=True)
    p.poly_x([(zb(150), 150), (zb(200), 200), (zc - 25, 200), (zc - 25, 150)], xc - 15, xc + 15, cut=True)
    ym = yb + 18.0
    hw = ear_half_at(ym)
    p.fillet_safe(EAR['edge'], [(xc + hw, ym, zf(ym))])
    p.fillet_safe(EAR['edge'], [(xc + hw, ym, zb(ym))])
    p.B((xc - 3, xc + 3), (yb - 5.0, yb + 0.01), (zc - 2, zc + 2))                          # keyed peg
    p.CY(xc + sx * 6.5, zc, PILOT_R, (yb - 0.1, yb + 7.0), cut=True)


def tail_plane_y(z):
    return TAIL_UNDER[1] + (TAIL_UNDER[0] - z) * math.tan(math.radians(TAIL_RISE))


def tail_rib(grow=0.0):
    """Key rib on the root's ramp (grow > 0: the matching slot in the tail), in (z, y)."""
    t = math.radians(TAIL_RISE)
    n = (math.sin(t), math.cos(t))
    A, B = (-71.0 + grow, tail_plane_y(-71.0 + grow)), (-74.5 - grow, tail_plane_y(-74.5 - grow))
    lo, hi = -0.05, 1.2 + grow
    return [(A[0] + lo * n[0], A[1] + lo * n[1]), (B[0] + lo * n[0], B[1] + lo * n[1]),
            (B[0] + hi * n[0], B[1] + hi * n[1]), (A[0] + hi * n[0], A[1] + hi * n[1])]


def tail_root(p):
    """TAIL ROOT (warm white): dia 26 x 4 turntable in the lid socket (0.8 gap all round), on the tail servo's
    cross horn (arms at 45 deg, blind arm pilots), dia 12 hub cap on top; a 20 deg ramp + key rib at the rear
    carries the tail, held by a hidden M2 x 6 from underneath. Printed underside down."""
    tr = TAIL_ROOT
    p.CY(0, TAIL_Z, tr['r'], (tr['y0'], tr['y1']))
    z0 = TAIL_UNDER[0]
    p.poly_x([(z0, tr['y1']), (-76.5, tr['y1']), (-76.5, tail_plane_y(-76.5))], -5.5, 5.5)
    p.poly_x(tail_rib(), -2.0, 2.0)
    p.prism('y', [swlib.circle((0.0, TAIL_Z), 25.0), swlib.circle((0.0, TAIL_Z), tr['r'])], tr['y1'], 58.0, cut=True)
    p.prism('y', [swlib.rrect(-20.0, 20.0, -140.0, -40.0, 0.0), tail_plan(0.3)], tr['y1'], 58.0, cut=True)   # hidden under the tail
    st = TAIL_SV_UNDER + SV_SPLINE                      # spline top 48.0 (2 below the lid top)
    a0, a1 = st + HORN_OUT - HORN_T, st + HORN_OUT
    for deg in (45.0, 135.0):
        p.prism('y', swlib.rpoly(rot_rect((0.0, TAIL_Z), 2 * CROSS_REACH, HORN_W, deg)), a0 - 0.5, a1, cut=True)
    p.CY(0, TAIL_Z, HORN_HUB_R, (a0 - 0.5, a1), cut=True)
    p.CY(0, TAIL_Z, 3.0, (a1 - 0.1, TAIL_CAP_Y + 0.1), cut=True)
    p.CY(0, TAIL_Z, CAP_R['tail'] + 0.1, (TAIL_CAP_Y, tr['y1'] + 0.5), cut=True)
    for deg in (45.0, 135.0, 225.0, 315.0):
        p.prism('y', swlib.rpoly(seg_rect((0.0, TAIL_Z), 6.7, 10.0, SLOT_W, deg)), a1 - 0.1, tr['y1'] - 1.0, cut=True)
    p.CY(0, TAIL_SCREW_Z, 2.2, (tr['y0'] - 0.1, a1), cut=True)
    p.CY(0, TAIL_SCREW_Z, CLEAR_R, (a1 - 0.1, 58.0), cut=True)


def tail_plan(inset=0.0):
    """Tail outline seen from above (x, z): 10 wide at its rounded butt, 5 at the rounded tip."""
    t = math.radians(TAIL_RISE)
    ztip = TAIL_UNDER[0] - 46.0 * math.cos(t) - 0.1
    z0 = TAIL_UNDER[0] - inset
    return swlib.rpoly([(-5.0 + inset, z0), (5.0 - inset, z0), (2.5 - inset, ztip + inset), (-2.5 + inset, ztip + inset)],
                       [4.6 - inset, 4.6 - inset, 2.3 - inset, 2.3 - inset])


def tail_v3(p):
    """TAIL (warm white): separate tapered piece, 10 -> 5 wide, 46 long, rising 20 deg, flat underside; keyed on
    the root's rib and held by one hidden M2 x 6. Printed on its flat underside, no supports."""
    t = math.radians(TAIL_RISE)
    d, n = (-math.cos(t), math.sin(t)), (math.sin(t), math.cos(t))
    A = TAIL_UNDER
    B = (A[0] + 46.0 * d[0], A[1] + 46.0 * d[1])
    Bt = (B[0] + 3.5 * n[0], B[1] + 3.5 * n[1])
    At = (A[0], A[1] + 7.4)
    p.prism('x', swlib.rpoly([A, B, Bt, At], [0.0, 1.5, 1.5, 3.0]), -5.2, 5.2)
    ztip = B[0] - 0.1
    p.prism('y', [swlib.rrect(-20.0, 20.0, -140.0, -60.0, 0.0), tail_plan()], 40.0, 90.0, cut=True)
    zm = -90.0
    ytop = At[1] + (zm - At[0]) * (Bt[1] - At[1]) / (Bt[0] - At[0])
    hw = 5.0 - 2.5 * (A[0] - zm) / (A[0] - ztip)
    if p.fillet_safe(1.5, [(hw, ytop, zm), (-hw, ytop, zm)]):
        p.fillet_safe(1.0, [(hw, ytop, zm), (-hw, ytop, zm)])
    p.poly_x(tail_rib(0.15), -2.15, 2.15, cut=True)
    ys = tail_plane_y(TAIL_SCREW_Z)
    p.CY(0, TAIL_SCREW_Z, PILOT_R, (ys - 0.5, ys + 5.0), cut=True)


def port_door(p, sx, zc, yc, x_in, x_out, blank=False):
    """PORT DOOR (black): flush 18 x 12 R6 plug in the wall opening (0.2 gap), two 0.3 catch bumps in the side
    grooves, a fingernail notch at the bottom. The blank is the same part where there is no port behind it."""
    g = 0.2
    lp = swlib.stadium(zc - DOOR_H / 2 + g, zc + DOOR_H / 2 - g, yc - DOOR_L / 2 + g, yc + DOOR_L / 2 - g)
    p.prism('x', lp, *rng(sx * x_in, sx * x_out))
    p.chamfer_safe(0.3, [(sx * x_out, yc + DOOR_L / 2 - g, zc)])
    xm = (x_in + x_out) / 2
    for s in (-1, 1):
        p.B(rng(sx * (xm - 0.5), sx * (xm + 0.5)), (yc - 3.0, yc + 3.0),
            sorted((zc + s * (DOOR_H / 2 - g - 0.01), zc + s * (DOOR_H / 2 - g + 0.3))))
    p.B(rng(sx * (x_out - 0.6), sx * (x_out + 0.1)), (yc - DOOR_L / 2 + g - 0.1, yc - DOOR_L / 2 + 1.4),
        (zc - 1.5, zc + 1.5), cut=True)
def thigh_outer(p, sx, sz, coupon=False):
    """THIGH OUTER HALF (warm white), x 55.6 -> 60.6 plus the dia 36 hip cup skirt down to the rim at 49.4.
    Printed outer face down, no supports. Holds: the hip servo's cross horn (screwed in from the horn side), the
    knee MG90S (its tabs screw into two blind pilots), 2 snap hooks for the cover."""
    L = Leg(sx, sz, KNEE_DZ[sz])
    split, face = THIGH_IN, THIGH_OUT3
    p.lprism(L, thigh_outline(), (split - LAP, face))                                  # the plate + lap rim
    p.lprism(L, thigh_outline(LAP_W), (split - LAP - 0.1, split), cut=True)             # lap rim hollow
    if not coupon:
        p.lprism(L, [swlib.circle((0.0, HIP_Y), HIP_CUP_R), swlib.circle((0.0, HIP_Y), CUP_SKIRT_IN)],
                 (HIP_CUP_RIM, split))                                                   # hip cup skirt
    # edges: 45 deg chamfer on the outer (print-bed) face, R1.5 on the cup rim
    p.chamfer_safe(1.5, [L.pt(face, KNEE_Y - KNEE_DRUM_R, 0.0)])
    if not coupon:
        p.fillet_safe(1.5, [L.pt(HIP_CUP_RIM, HIP_Y + HIP_CUP_R, 0.0)])
        # hip: cross horn + cap; lead window through the skirt at 6 o'clock (the cover's U-plug fills its floor)
        p.cross_horn_seat(L, 0.0, HIP_Y, split, face, CAP_R['hip'])
        yw = HIP_Y - math.sqrt(CUP_SKIRT_IN ** 2 - 4.0 ** 2) + 0.3
        p.lbox(L, (-4.0, 4.0), (HIP_Y - HIP_CUP_R - 0.6, yw), (HIP_CUP_RIM - 0.1, split), cut=True)
    # knee: tab pilots (blind, 1.0 skin), gear-case pocket, boss bore, lead hole at 12 o'clock
    for a in TAB_HOLES:
        p.lbox(L, (a - PILOT_R - SV_HOLE_SLOT, a + PILOT_R + SV_HOLE_SLOT), (KNEE_Y - PILOT_R, KNEE_Y + PILOT_R),
               (split - 0.1, face - 1.0), cut=True)
    p.lbox(L, (-SV_SHAFT - FIT, SV_L - SV_SHAFT + FIT), (KNEE_Y - SV_W / 2 - FIT, KNEE_Y + SV_W / 2 + FIT),
           (split - 0.1, KNEE_UNDER + SV_TOP_RECT + FIT), cut=True)
    p.lcyl(L, 0.0, KNEE_Y, SV_BOSS_R + 0.8, (split - 0.1, face + 0.5), cut=True)
    p.lcyl(L, 0.0, KNEE_Y + 11.0, 2.25, (split - 0.1, face + 0.5), cut=True)
    # cover screw: M2 x 8 from this face at 6 o'clock, hidden under the shin's knee drum
    p.lcyl(L, 0.0, KNEE_Y - 11.0, CBORE_R, (face - 1.4, face + 0.5), cut=True)
    p.lcyl(L, 0.0, KNEE_Y - 11.0, CLEAR_R, (split - 0.1, face - 1.35), cut=True)
    if not coupon:
        for ah in (-8.5, 8.5):
            p.hook_male(L, ah, -4.0, split, 3.0, split - 4.2)


def thigh_cover(p, sx, sz):
    """THIGH INNER COVER + KNEE POD (graphite), x 49.4 -> 55.6, pod inward to 27.4. Printed open side (x 55.6)
    down, no supports. Holds: the knee MG90S case (touches only at its tabs + a 0.4 end stop), the leads (channel,
    cross channel, lead corridor), and plugs the hip cup's lead window with its U-shaped tongue."""
    L = Leg(sx, sz, KNEE_DZ[sz])
    split = THIGH_IN
    cin = THIGH_COVER_IN
    p.lprism(L, thigh_outline(0.0, cover=True), (cin, split - LAP))
    p.lprism(L, thigh_outline(LAP_W + LAP_FIT, cover=True), (split - LAP - 0.01, split))
    pod = swlib.rrect(*L.zr(*CASE_BAND), *KNEE_POD_Y, (4.0, 4.0, 3.0, 3.0))
    p.prism('x', pod, *L.xr(KNEE_POD_IN, cin))        # exact face contact: an overlap leaves sliver faces
    # edges (root first - it must propagate round the whole pod footprint or SOLIDWORKS refuses it):
    # R2.5 where the pod meets the thigh (also the lead corridor's skin), R3 on the inner face and the pod face
    p.fillet_safe(KNEE_ROOT_R, [L.pt(cin, KNEE_POD_Y[1], 5.0)])
    p.fillet_safe(3.0, [L.pt(cin, -4.0, -THIGH_W / 2)])
    p.fillet_safe(3.0, [L.pt(KNEE_POD_IN, KNEE_POD_Y[0], 5.0)])
    # U-shaped tongue that fills the floor of the cup's lead window (locates the cover's top end)
    yt0, yt1 = HIP_Y - HIP_CUP_R - 0.6, HIP_Y - 14.5
    p.lbox(L, (-3.9, 3.9), (yt0, yt1), (cin, cin + SKIN))
    for s in (-1, 1):
        p.lbox(L, sorted((s * CHAN_W / 2, s * 3.9)), (yt0, yt1), (cin + SKIN - 0.01, split))
    # knee servo: tab cavity, case cavity (2.6 lead gaps at both ends and under the case), tab screw heads
    yc0, yc1 = KNEE_Y - SV_W / 2 - POD_GAP, KNEE_Y + SV_W / 2 + POD_GAP
    p.lprism(L, swlib.rrect(*TAB_CAV, yc0, yc1, TAB_CAV_R), (KNEE_UNDER - POD_GAP, split + 0.1), cut=True)
    p.lprism(L, swlib.rrect(*CASE_CAV, yc0, yc1, (2.0, 2.0, 1.2, 1.2)), (KNEE_UNDER - SV_UNDER - LEAD_GAP, split + 0.1), cut=True)
    for a in TAB_HOLES:
        p.lcyl(L, a, KNEE_Y, SCREW_HEAD_R + 0.4, (KNEE_UNDER - SCREW_HEAD_H - 0.4, KNEE_UNDER - POD_GAP + 0.1), cut=True)
    # leads: channel up the thigh (through the tongue into the hip cup), cross channel over the tabs, corridor
    ch0 = cin + SKIN
    p.lbox(L, (-CHAN_W / 2, CHAN_W / 2), (yc1 - 0.1, yt1 + 0.1), (ch0, split + 0.1), cut=True)
    p.lbox(L, (CASE_CAV[0], CHAN_W / 2), (yc1 - 0.1, KNEE_Y + 12.0), (ch0, split + 0.1), cut=True)
    p1, p2, r, _ = KNEE_CORRIDOR
    p.lprism_z(L, swlib.slot(p1, p2, r), (CASE_CAV[0], -SV_SHAFT), cut=True)
    # fixing: 2 snap-hook pockets, 1 pilot for the M2 x 8 from the thigh's outer face (under the shin drum)
    for ah in (-8.5, 8.5):
        p.hook_female(L, ah, -4.0, split, split - 4.2)
    p.lcyl(L, 0.0, KNEE_Y - 11.0, PILOT_R, (cin + 1.2, split + 0.1), cut=True)
    # 3 vent slots under the pod, 2 end-stop ribs on the pod floor (0.4 under the case bottom)
    for a in (1.0, 4.6, 8.2):
        p.lbox(L, (a, a + 1.2), (KNEE_Y - POD_Y - 0.1, yc0 + 0.1), (33.0, 41.0), cut=True)
    floor = KNEE_UNDER - SV_UNDER - LEAD_GAP
    for s in (-1, 1):
        p.lbox(L, (0.0, 11.0), sorted((KNEE_Y + s * 2.6, KNEE_Y + s * 5.0)), (floor - 0.1, KNEE_UNDER - SV_UNDER - POD_GAP))


def shin_outer(p, sx, sz, coupon=False):
    """SHIN OUTER HALF (warm white), x 66.4 -> 76.4. Printed outer face down. Holds: the knee servo's cross horn
    (under the knee cap), the wheel MG90S 360 (tabs into two blind pilots), 2 snap hooks, the lip that
    locates the cover's knee ring."""
    L = Leg(sx, sz, PAW_DZ)
    split, face = SHIN_IN, SHIN_OUT3
    p.lprism(L, shin_outline(), (split - LAP, face))
    p.lprism(L, shin_outline(LAP_W), (split - LAP - 0.1, split), cut=True)
    p.chamfer_safe(3.0, [L.pt(face, KNEE_Y + KNEE_DRUM_R, 0.0)])
    p.chamfer_safe(3.0, [L.pt(face, AXLE_Y - POD_Y, 5.0)])
    p.cross_horn_seat(L, 0.0, KNEE_Y, split, face, CAP_R['knee'])
    p.lprism(L, sector((0.0, KNEE_Y), 14.4, 15.0, 20.0, 160.0), (split - 2.0, split + 0.05))   # ring locating lip
    if coupon:
        return
    # paw: tab pilots, gear-case pocket, boss bore, spline / hub bore through to the wheel
    for a in TAB_HOLES:
        p.lbox(L, (a - PILOT_R - SV_HOLE_SLOT, a + PILOT_R + SV_HOLE_SLOT), (AXLE_Y - PILOT_R, AXLE_Y + PILOT_R),
               (split - 0.1, split + 4.0), cut=True)
    p.lbox(L, (-SV_SHAFT - FIT, SV_L - SV_SHAFT + FIT), (AXLE_Y - SV_W / 2 - FIT, AXLE_Y + SV_W / 2 + FIT),
           (split - 0.1, WHEEL_UNDER + SV_TOP_RECT + FIT), cut=True)
    p.lcyl(L, 0.0, AXLE_Y, SV_BOSS_R + 0.8, (split - 0.1, WHEEL_UNDER + SV_TOP_HUMP + FIT), cut=True)
    p.lcyl(L, 0.0, AXLE_Y, 4.6, (WHEEL_UNDER + SV_TOP_HUMP, face + 0.5), cut=True)
    # wire channel (this half's part of the hollow x 63.2-74.6)
    p.lbox(L, (-CHAN_W / 2, CHAN_W / 2), (AXLE_Y + SV_BOSS_R + 0.8 + 0.5, KNEE_Y - KNEE_DRUM_R), (split - 0.1, face - SKIN), cut=True)
    # cover screw: M2 x 8 from this face, hidden behind the wheel
    p.lcyl(L, 6.0, -54.0, CBORE_R, (split + 4.5, face + 0.5), cut=True)
    p.lcyl(L, 6.0, -54.0, CLEAR_R, (split - 0.1, split + 4.55), cut=True)
    for ah in (-7.5, 7.5):
        p.hook_male(L, ah, -46.0, split, 4.0, split - 3.4)


def shin_cover(p, sx, sz):
    """SHIN INNER COVER + PAW POD (graphite), x 61.4 -> 66.4, pod inward to 38.2. Printed open side (x 66.4)
    down. Holds: the wheel MG90S case, the leads; its ring (r 15.2-17) walls in the knee lead chamber."""
    L = Leg(sx, sz, PAW_DZ)
    split, cin = SHIN_IN, SHIN_COVER_IN
    hole = swlib.circle((0.0, KNEE_Y), 15.2)
    p.lprism(L, [shin_outline(), hole], (cin, split - LAP))
    p.lprism(L, [shin_outline(LAP_W + LAP_FIT), hole], (split - LAP - 0.01, split))
    band = swlib.rrect(*L.zr(*TAB_BAND), AXLE_Y - POD_Y, AXLE_Y + POD_Y, 4.0)
    p.prism('x', band, *L.xr(PAW_BAND_IN, cin))
    pod = swlib.rrect(*L.zr(*CASE_BAND), AXLE_Y - POD_Y, AXLE_Y + POD_Y, (4.0, 4.0, 3.0, 3.0))
    p.prism('x', pod, *L.xr(PAW_POD_IN, PAW_BAND_IN))
    p.fillet_safe(PAW_ROOT_R, [L.pt(cin, AXLE_Y + POD_Y, 0.0)])          # root first (lead corridor skin)
    p.fillet_safe(1.5, [L.pt(cin, KNEE_Y + KNEE_DRUM_R, 0.0)])
    p.fillet_safe(3.0, [L.pt(PAW_POD_IN, AXLE_Y - POD_Y, 5.0)])
    yc0, yc1 = AXLE_Y - SV_W / 2 - POD_GAP, AXLE_Y + SV_W / 2 + POD_GAP
    p.lprism(L, swlib.rrect(*TAB_CAV, yc0, yc1, TAB_CAV_R), (WHEEL_UNDER - POD_GAP, split + 0.1), cut=True)
    p.lprism(L, swlib.rrect(*CASE_CAV, yc0, yc1, (2.2, 2.2, 1.2, 1.2)), (WHEEL_UNDER - SV_UNDER - LEAD_GAP, split + 0.1), cut=True)
    for a in TAB_HOLES:
        p.lcyl(L, a, AXLE_Y, SCREW_HEAD_R + 0.4, (WHEEL_UNDER - SCREW_HEAD_H - 0.2, WHEEL_UNDER - POD_GAP + 0.1), cut=True)
    # leads: channel up to the knee ring's 6 o'clock window, cross channel over the tabs, corridor
    ch0 = cin + SKIN
    p.lbox(L, (-CHAN_W / 2, CHAN_W / 2), (yc1 - 0.1, KNEE_Y - 14.0), (ch0, split + 0.1), cut=True)
    p.lbox(L, (CASE_CAV[0], CHAN_W / 2), (yc1 - 0.1, -52.0), (ch0, split + 0.1), cut=True)
    p1, p2, r, _ = PAW_CORRIDOR
    p.lprism_z(L, swlib.slot(p1, p2, r), (CASE_CAV[0], -SV_SHAFT), cut=True)
    for ah in (-7.5, 7.5):
        p.hook_female(L, ah, -46.0, split, split - 3.4)
    p.lcyl(L, 6.0, -54.0, PILOT_R, (split - 4.0, split + 0.1), cut=True)
    for a in (2.0, 6.0):
        p.lbox(L, (a, a + 1.2), (AXLE_Y - POD_Y - 0.1, yc0 + 0.1), (44.0, 52.0), cut=True)
    floor = WHEEL_UNDER - SV_UNDER - LEAD_GAP
    for s in (-1, 1):
        p.lbox(L, (0.0, 11.0), sorted((AXLE_Y + s * 2.6, AXLE_Y + s * 5.0)), (floor - 0.1, WHEEL_UNDER - SV_UNDER - POD_GAP))


def wheel_v3(p, sx, sz):
    """WHEEL (graphite), x 77.2 -> 85.2: rim shoulders r 15.35 each side of the O-ring groove (26 x 2.4 NBR, groove
    bottom r 13.9: about 1 mm of the ring shows, like a tread), closed outer face with a 1 x 45 chamfer, cross horn
    pocket inside (blind pilots), dia 6 hole under the dia 14 hub cap."""
    L = Leg(sx, sz, PAW_DZ)
    x0, x1 = WHEEL_IN, WHEEL_OUT
    p.lrevolve(L, 0.0, AXLE_Y, [(x0, 0.0), (x1, 0.0), (x1, RIM_R - 1.0), (x1 - 1.0, RIM_R), (x0 + 0.5, RIM_R),
                                (x0, RIM_R - 0.5)])
    xm = (x0 + x1) / 2
    p.lrevolve(L, 0.0, AXLE_Y, [(xm - (OR_CS + 0.2) / 2, OR_GROOVE_R), (xm + (OR_CS + 0.2) / 2, OR_GROOVE_R),
                                (xm + (OR_CS + 0.2) / 2, RIM_R + 1.0), (xm - (OR_CS + 0.2) / 2, RIM_R + 1.0)], cut=True)
    p.cross_horn_seat(L, 0.0, AXLE_Y, x0, x1, CAP_R['wheel'])


def hub_cap(p, kind, sx=1, sz=1):
    """HUB CAP (black): dia 12 (hip, knee, tail) or 14 (wheel) x 1.6, sits in a 1.2 recess (0.4 proud, 0.4 x 45 top
    chamfer), pressed in by a split ring into the dia 6 horn-screw hole, pry notch at 6 o'clock. Print top down."""
    r = CAP_R[kind]
    ring = [(-1.2, 2.3), (0.0, 2.3), (0.0, 0.0), (CAP_T, 0.0), (CAP_T, r - 0.4), (CAP_T - 0.4, r), (0.0, r),
            (0.0, 3.0), (-1.2, 3.0)]
    if kind == 'tail':
        # v3.1: shorter peg (1.0, v3 1.2) -> 0.6 mm clear of the tail horn arms (their height is an estimate)
        ring_t = [(max(a, -TAIL_CAP_PEG), rr) for a, rr in ring]
        prof = swlib.rpoly([(TAIL_CAP_Y + a, rr) for a, rr in ring_t], 0.0)
        p.revolve('y', (0.0, TAIL_Z), prof)
        for zr, xr in (((TAIL_Z - 3.2, TAIL_Z + 3.2), (-0.4, 0.4)), ((TAIL_Z - 0.4, TAIL_Z + 0.4), (-3.2, 3.2))):
            p.B(xr, (TAIL_CAP_Y - 1.3, TAIL_CAP_Y - 0.02), zr, cut=True)
        p.B((-0.8, 0.8), (TAIL_CAP_Y - 0.1, TAIL_CAP_Y + CAP_T + 0.1), (TAIL_Z - r - 0.1, TAIL_Z - r + 0.8), cut=True)
        return
    L = Leg(sx, sz, 1)
    y, X_face = {'hip': (HIP_Y, THIGH_OUT3), 'knee': (KNEE_Y, SHIN_OUT3), 'wheel': (AXLE_Y, WHEEL_OUT)}[kind]
    X0 = X_face - CAP_RECESS
    p.lrevolve(L, 0.0, y, [(X0 + a, rr) for a, rr in ring])
    p.lbox(L, (-3.2, 3.2), (y - 0.4, y + 0.4), (X0 - 1.3, X0 - 0.02), cut=True)       # ring slits (4 fingers)
    p.lbox(L, (-0.4, 0.4), (y - 3.2, y + 3.2), (X0 - 1.3, X0 - 0.02), cut=True)
    p.lbox(L, (-0.8, 0.8), (y - r - 0.1, y - r + 0.8), (X0 - 0.1, X0 + CAP_T + 0.1), cut=True)   # pry notch


def coupon_knee_thigh(p):
    """KNEE COUPON, thigh end (white): the front-left thigh's knee end cut off above the knee - tab pilots,
    gear-case pocket, boss bore, lead hole, cover-screw counterbore. Screw a real knee MG90S to it."""
    thigh_outer(p, 1, 1, coupon=True)
    L = Leg(1, 1, KNEE_DZ[1])
    p.lbox(L, (-40.0, 40.0), (-2.0, 60.0), (40.0, 70.0), cut=True)


def coupon_knee_shin(p):
    """KNEE COUPON, shin end (white + the cover's ring merged in): the front-left shin's knee drum with the cross
    horn seat, cap recess, and the lead chamber ring with its 6 o'clock window. Fit the horn, press onto the
    coupon servo's spline, thread a lead through the window + the thigh coupon's hole, and sweep it 500 times."""
    shin_outer(p, 1, 1, coupon=True)
    L = Leg(1, 1, PAW_DZ)
    p.lprism(L, [swlib.circle((0.0, KNEE_Y), KNEE_DRUM_R - LAP_W - LAP_FIT), swlib.circle((0.0, KNEE_Y), 15.2)],
             (SHIN_COVER_IN, SHIN_IN + 0.05))
    p.lbox(L, (-CHAN_W / 2, CHAN_W / 2), (KNEE_Y - KNEE_DRUM_R - 1.0, KNEE_Y - 14.0), (SHIN_COVER_IN + SKIN, SHIN_IN), cut=True)
    p.lbox(L, (-40.0, 40.0), (-44.0, -100.0), (60.0, 80.0), cut=True)


def coupon_snap_white(p):
    """SNAP + CAP COUPON, white side: a 5 mm plate like the thigh outer half with one snap hook, a dia 12 cap seat
    and a dia 14 cap seat (each with its dia 6 hole). Clip it into the graphite coupon; press both caps in."""
    L = Leg(1, 1, 1)
    L.hz = 150.0
    p.lbox(L, (-8.0, 40.0), (-8.0, 8.0), (THIGH_IN, THIGH_OUT3))
    p.hook_male(L, 0.0, 0.0, THIGH_IN, 3.0, THIGH_IN - 4.2)
    for a, r in ((15.0, CAP_R['hip']), (31.0, CAP_R['wheel'])):
        p.lcyl(L, a, 0.0, r + 0.1, (THIGH_OUT3 - CAP_RECESS, THIGH_OUT3 + 0.5), cut=True)
        p.lcyl(L, a, 0.0, 3.0, (THIGH_IN - 0.5, THIGH_OUT3 - CAP_RECESS + 0.1), cut=True)


def coupon_snap_graphite(p):
    """SNAP COUPON, graphite side: a 6.2 mm block like the thigh cover with one hook pocket."""
    L = Leg(1, 1, 1)
    L.hz = 150.0
    p.lbox(L, (-6.0, 6.0), (-6.0, 6.0), (THIGH_COVER_IN, THIGH_IN))
    p.hook_female(L, 0.0, 0.0, THIGH_IN, THIGH_IN - 4.2)


# =============================================================================================
# BOUGHT PARTS (one multibody part, every body named after what you are buying)
# =============================================================================================
def servo_v3(p, name, sx, y, shaft_z, dz, under, hip=False):
    """MG90S (v3 shape: rectangular gear case to SV_TOP_RECT, round boss to SV_TOP_HUMP) with its shaft along X
    pointing away from the centre line, a 4-arm cross horn fitted, and its 2 tab screws."""
    zc = shaft_z + dz * BODY_C
    z0, z1 = zc - SV_L / 2, zc + SV_L / 2
    spline_top = under + SV_SPLINE
    n = name + ' - '
    X = lambda a, b: (sx * a, sx * b)
    p.B(X(under - SV_UNDER, under + SV_TOP_RECT), (y - SV_W / 2, y + SV_W / 2), (z0, z1)); p.name_body(n + 'MG90S case')
    p.B(X(under, under + SV_TAB_T), (y - SV_W / 2, y + SV_W / 2), (zc - SV_TABS / 2, z0 - 0.01)); p.name_body(n + 'MG90S tab A')
    p.B(X(under, under + SV_TAB_T), (y - SV_W / 2, y + SV_W / 2), (z1 + 0.01, zc + SV_TABS / 2)); p.name_body(n + 'MG90S tab B')
    p.CX(y, shaft_z, SV_BOSS_R, X(under + SV_TOP_RECT + 0.01, under + SV_TOP_HUMP)); p.name_body(n + 'MG90S boss')
    p.CX(y, shaft_z, 2.45, X(under + SV_TOP_HUMP + 0.01, spline_top)); p.name_body(n + 'MG90S spline')
    arm0, arm1 = spline_top + HORN_OUT - HORN_T, spline_top + HORN_OUT
    p.CX(y, shaft_z, 3.8, X(spline_top - 3.5, arm0 - 0.01)); p.name_body(n + 'horn hub')
    r, w = CROSS_REACH - 0.5, (HORN_W - 0.4) / 2
    p.B(X(arm0, arm1), (y - r, y + r), (shaft_z - w, shaft_z + w)); p.name_body(n + 'horn arms')
    p.B(X(arm0, arm1), (y - w, y + w), (shaft_z - r, shaft_z + r)); p.name_body(n + 'horn arms 2')
    for k, d in enumerate((-SV_HOLES / 2, SV_HOLES / 2)):
        zs = zc + d
        if hip:        # tabs on the outside of the torso wall: screws driven inward, heads on the tab top
            hx, sh = (under + SV_TAB_T + 0.01, under + SV_TAB_T + SCREW_HEAD_H), (under + SV_TAB_T - 6.0, under + SV_TAB_T)
        else:          # tabs under a plate: screws driven outward from the tab underside
            hx, sh = (under - SCREW_HEAD_H, under - 0.01), (under, under + 6.0)
        p.CX(y, zs, SCREW_HEAD_R, X(*hx)); p.name_body(n + f'tab screw {k + 1} head')
        p.CX(y, zs, 0.8, X(*sh)); p.name_body(n + f'tab screw {k + 1} M2x6')


def bought(p):
    p.merge = False
    b = BOARD_Y0
    p.B((-60, 60), (b, b + 70.2), (PCB_FRONT - 1.6, PCB_FRONT)); p.name_body('Guition 4.3in screen - PCB')
    p.B((-53, 53), (b + 1.6, b + 69.0), (PCB_FRONT + 0.01, GLASS_Z)); p.name_body('Guition 4.3in screen - glass')
    p.B((-53, 53), (b + 2, b + 68), (PCB_FRONT - 9.6, PCB_FRONT - 1.61)); p.name_body('Guition 4.3in screen - back parts')
    # camera board standing behind the muzzle's front wall, camera folded onto the WROOM module
    p.B((-CAM_L / 2, CAM_L / 2), (CAM_Y0, CAM_Y0 + CAM_H), (CAM_PCB_Z - 1.6, CAM_PCB_Z)); p.name_body('ESP32-S3 CAM board - PCB')
    p.B((-CAM_L / 2, -3.0), (LENS_Y - 9, LENS_Y + 9), (CAM_PCB_Z + 0.01, CAM_PCB_Z + 3.1)); p.name_body('ESP32-S3 CAM board - WROOM module')
    p.B((-8, 6), (CAM_Y0 + 6, CAM_Y0 + 20), (CAM_PCB_Z - 3.5, CAM_PCB_Z - 1.61)); p.name_body('ESP32-S3 CAM board - microSD (back)')
    p.B((LENS_X - 4.25, LENS_X + 4.25), (LENS_Y - 4.25, LENS_Y + 4.25), (CAM_PCB_Z + 4.1, MUZ_FZ - 0.01)); p.name_body('OV5640 camera - module')
    p.CZ(LENS_X, LENS_Y, 3.9, (MUZ_FZ + 0.01, MUZ_FZ + 1.5)); p.name_body('OV5640 camera - lens')
    p.B((APDS_X - 10.2, APDS_X + 10.2), (LENS_Y - 7.7, LENS_Y + 7.7), (MUZ_FZ - 2.5, MUZ_FZ - 0.01)); p.name_body('APDS-9960 gesture')
    p.B((-60.0, -52.65), (114.5 - 4.47, 114.5 + 4.47), (PCB_FRONT - 1.6 - 3.2, PCB_FRONT - 1.61)); p.name_body('Guition 4.3in screen - USB-C receptacle')
    ix = HEAD['x'] - HEAD_W                     # v3.1: mics sit on the thin wall
    for sx, nm in ((-1, 'right'), (1, 'left')):
        p.CX(MIC_Y, MIC_Z, 7.0, (sx * (ix - 1.2), sx * (ix - 0.01))); p.name_body('MS3625 mic ' + nm)
    p.B((-14, 14), (80, 111), (HEAD['z0'] + HEAD_W + 0.1, HEAD['z0'] + HEAD_W + 15)); p.name_body('Cavity speaker 3W')
    p.B((-20.5, 20.5), (W, W + 19.35), BAT_Z); p.name_body('2x18650 holder + 2x Samsung 35E')
    p.B((-24.2, 24.2), (W + 1, W + 5), PROT_Z); p.name_body('2S 20A protection board')
    p.B((-22.5, 22.5), (W + 5.5, W + 17.5), (31, 45)); p.name_body('Mini blade fuse holder')
    # USB-C charger, raised over the rear-left hip servo: PCB, parts, receptacle through the rump wall
    p.B(CHG_X, (CHG_Y0, CHG_Y0 + 1.6), (CHG_Z[0], CHG_Z[1])); p.name_body('Type-C 2S charging board - PCB')
    p.B((CHG_X[0] + 0.5, CHG_X[1] - 0.5), (CHG_Y0 + 1.61, CHG_Y0 + 6.1), (CHG_Z[0] + 4.0, CHG_Z[1] - 0.5)); p.name_body('Type-C 2S charging board - parts')
    p.B((USB_X - 4.47, USB_X + 4.47), (USB_Y - 1.63, USB_Y + 1.63), (CHG_Z[0] - 1.0, CHG_Z[0] + 6.35)); p.name_body('Type-C 2S charging board - USB-C receptacle')
    # KCD1 rocker, turned 90 deg, flush in its belly recess
    kz = KCD1_ZC
    p.B((-7.5, 7.5), (KCD1_RECESS - 2.0, KCD1_RECESS), (kz - 10.5, kz + 10.5)); p.name_body('KCD1 switch - bezel')
    p.B((-6.3, 6.3), (KCD1_RECESS + 0.01, KCD1_RECESS + 14), (kz - 9.5, kz + 9.5)); p.name_body('KCD1 switch - body')
    p.B((-4, 4), (KCD1_RECESS + 14.01, KCD1_RECESS + 22.8), (kz - 4, kz + 4)); p.name_body('KCD1 switch - terminals')
    for sx in (-1, 1):
        s = 'left' if sx > 0 else 'right'
        p.B((sx * 32, sx * 33.6), (5.6, 31), (-31.1, 31.1)); p.name_body('PCA9685 servo board ' + s)
        p.B((sx * 23.5, sx * 31.99), (22.6, 30.2), (-23, 23)); p.name_body('PCA9685 headers ' + s)
        p.B((sx * 33.61, sx * 37.8), (22.6, 30.2), (-23, 23)); p.name_body('PCA9685 solder tails ' + s)
        p.B((sx * 9.5, sx * 23.49), (22.6, 30.2), (-23, 23)); p.name_body('Servo plugs ' + s)
        p.B((sx * 32.9, sx * 36.8), (35.7 + SIDE_LASER_DY, 47.5 + SIDE_LASER_DY), (-12.5, 12.5)); p.name_body('VL53L0X side laser ' + s)
    for x0, x1, zlow, dirz, nm in [(7.5, 32.5, CLIFF_FRONT_Z, 1, 'front desk-edge left'),
                                   (-32.5, -7.5, CLIFF_FRONT_Z, 1, 'front desk-edge right'),
                                   (CLIFF_REAR_X[0], CLIFF_REAR_X[1], CLIFF_REAR_Z, -1, 'rear desk-edge')]:
        _, board, _, _ = cliff_geom(zlow, dirz)
        p.poly_x(board, x0 + 0.01, x1 - 0.01); p.name_body('VL53L0X ' + nm)
    for sz, nm in ((1, 'front'), (-1, 'rear')):
        p.poly_x(laser_board_pts(sz), -12.5, 12.5); p.name_body(f'VL53L0X {nm} obstacle laser')
    p.B((-8.2, 8.2), (44.2, 47.5), (4.2, 25.4)); p.name_body('MPU6050 IMU')
    p.B((16.3, 31.3), (44.2, 47.5), (16.6, 46.9)); p.name_body('MPR121 touch')
    p.B((-25, 25), (33, 46.6), (-37.3 + HUB_DZ, -1.7 + HUB_DZ)); p.name_body('Perfboard hub (2x Mini560, caps, resistors)')
    # leg servos (v3: knee cases flipped away from the body centre, every paw forward, cross horns), tyres, leads
    for sx in (-1, 1):
        for sz in (-1, 1):
            hz, dz = LEGS[sz]
            leg = ('F' if sz > 0 else 'B') + ('L' if sx > 0 else 'R')
            servo_v3(p, 'Hip ' + leg, sx, HIP_Y, hz, dz, TX, hip=True)
            servo_v3(p, 'Knee ' + leg, sx, KNEE_Y, hz, KNEE_DZ[sz], KNEE_UNDER)
            servo_v3(p, 'Wheel ' + leg + ' (360)', sx, AXLE_Y, hz, PAW_DZ, WHEEL_UNDER)
            L = Leg(sx, sz, 1)
            p.revolve('x', (AXLE_Y, hz), swlib.circle((sx * (WHEEL_IN + WHEEL_OUT) / 2, OR_GROOVE_R + OR_CS / 2 + 0.02), OR_CS / 2))
            p.name_body(f'O-ring tyre {leg} - 26x2.4 NBR')
            # wheel lead (approximate path, proves the passages): shin channel, knee coil, thigh hole + channel, hip coil
            lr = LEAD_D / 2
            p.CY(sx * (SHIN_COVER_IN + SKIN + 1.6), hz, lr, (AXLE_Y + POD_Y + 0.6, KNEE_Y - 15.0)); p.name_body(f'Lead {leg} - wheel, shin channel')
            p.prism('x', L.loop(sector((0.0, KNEE_Y), 8.6, 11.0, -90.0, 90.0)), *L.xr(THIGH_OUT3 + 1.2, THIGH_OUT3 + 3.6))
            p.name_body(f'Lead {leg} - wheel, knee coil')
            p.CX(KNEE_Y + 11.0, hz, 1.0, (sx * (THIGH_COVER_IN + SKIN + 2.6), sx * (THIGH_OUT3 + 1.19))); p.name_body(f'Lead {leg} - wheel, thigh hole')
            p.CY(sx * (THIGH_COVER_IN + SKIN + 2.2), hz, lr, (KNEE_Y + 12.2, HIP_Y - 15.0)); p.name_body(f'Lead {leg} - wheel + knee, thigh channel')
            p.prism('x', L.loop(sector((0.0, HIP_Y), 8.6, 11.0, -90.0, 90.0)), *L.xr(THIGH_COVER_IN + 2.2, THIGH_COVER_IN + 4.6))
            p.name_body(f'Lead {leg} - wheel + knee, hip coil')
            # hip exit: both leads from the hip coil (12 o'clock) through the panel slot and the tub-wall notch
            ly0, ly1 = LEAD_EXIT_Y
            p.B((sx * 37.0, sx * (THIGH_COVER_IN + 3.4)), (ly0, ly1), (hz - 2.5, hz + 2.5)); p.name_body(f'Lead {leg} - wheel + knee, hip exit')
            p.B((sx * 37.0, sx * 39.4), (ly0, ly1), sorted((hz - sz * 2.5, sz * 32.0))); p.name_body(f'Lead {leg} - wheel + knee, along the tub wall')
    # tail servo: turned 90 deg (case along +x), hanging from the lid rib, cross horn at 45 deg under the tail root
    u = TAIL_SV_UNDER
    xc = BODY_C
    p.B((xc - SV_L / 2, xc + SV_L / 2), (u - SV_UNDER, u + SV_TOP_RECT), (TAIL_Z - SV_W / 2, TAIL_Z + SV_W / 2)); p.name_body('Tail - MG90S case')
    p.B((xc - SV_TABS / 2, xc - SV_L / 2 - 0.01), (u, u + SV_TAB_T), (TAIL_Z - SV_W / 2, TAIL_Z + SV_W / 2)); p.name_body('Tail - MG90S tab A')
    p.B((xc + SV_L / 2 + 0.01, xc + SV_TABS / 2), (u, u + SV_TAB_T), (TAIL_Z - SV_W / 2, TAIL_Z + SV_W / 2)); p.name_body('Tail - MG90S tab B')
    p.CY(0, TAIL_Z, SV_BOSS_R, (u + SV_TOP_RECT + 0.01, u + SV_TOP_HUMP)); p.name_body('Tail - MG90S boss')
    st = u + SV_SPLINE
    p.CY(0, TAIL_Z, 2.45, (u + SV_TOP_HUMP + 0.01, st)); p.name_body('Tail - MG90S spline')
    a0, a1 = st + HORN_OUT - HORN_T, st + HORN_OUT
    p.CY(0, TAIL_Z, 3.8, (st - 3.5, a0 - 0.01)); p.name_body('Tail - horn hub')
    for k, deg in enumerate((45.0, 135.0)):
        p.prism('y', swlib.rpoly(rot_rect((0.0, TAIL_Z), 2 * (CROSS_REACH - 0.5), HORN_W - 0.4, deg)), a0, a1)
        p.name_body('Tail - horn arms' + (' 2' if k else ''))
    for k, d in enumerate((-SV_HOLES / 2, SV_HOLES / 2)):
        x = xc + d
        p.CY(x, TAIL_Z, SCREW_HEAD_R, (u - SCREW_HEAD_H, u - 0.01)); p.name_body(f'Tail - tab screw {k + 1} head')
        p.CY(x, TAIL_Z, 0.8, (u, u + 6.0)); p.name_body(f'Tail - tab screw {k + 1} M2x6')
    for nm in ('O-ring', 'KCD1'):
        try:
            p.set_body_color(nm, BLACK)
        except Exception:
            pass


# masses (g) of the bought bodies, by name prefix - used only for the balance check
MASS = [('Guition 4.3in screen - PCB', 45), ('Guition 4.3in screen - glass', 55), ('Guition 4.3in screen - back', 30),
        ('ESP32-S3 CAM board - PCB', 8), ('ESP32-S3 CAM board - WROOM', 3), ('ESP32-S3 CAM board - microSD', 0.5),
        ('OV5640 camera - module', 3), ('OV5640 camera - lens', 0.5), ('APDS-9960', 2), ('VL53L0X', 1.2),
        ('MS3625', 1), ('Cavity speaker', 10), ('2x18650', 104), ('2S 20A protection', 5), ('Mini blade fuse', 6),
        ('Type-C 2S charging board - PCB', 3), ('Type-C 2S charging board - parts', 1.5), ('Type-C 2S charging', 0.5),
        ('KCD1 switch - body', 3), ('KCD1', 0), ('PCA9685 servo board', 9),
        ('PCA9685', 0), ('Servo plugs', 3), ('MPU6050', 2), ('MPR121', 2), ('Perfboard hub', 22),
        ('MG90S case', 13.4), ('horn arms', 0.6), ('horn hub', 0.4), ('tab screw', 0.15), ('O-ring', 0.5),
        ('Lead', 0.8), ('MG90S', 0)]
WIRES = ('wiring and solder (estimate)', 30.0, (0.0, 20.0, 0.0))


def bought_mass(name):
    for key, g in MASS:
        if key in name:
            return g
    return 0.0


# =============================================================================================
PRINTED = [
    ('Torso_Bottom (4 hip MG90S, 2 PCA9685, protection board, fuse holder, USB-C charger, KCD1, 5 VL53L0X)', torso_bottom_v3),
    ('Side_Panel_Left (covers the 2 left hip MG90S)', lambda p: side_panel(p, 1)),
    ('Side_Panel_Right (covers the 2 right hip MG90S)', lambda p: side_panel(p, -1)),
    ('Band_Chest (front obstacle VL53L0X window, covers 2 lid screws)', lambda p: band(p, 1)),
    ('Band_Rump (rear obstacle VL53L0X window, USB-C port, covers 2 lid screws)', lambda p: band(p, -1)),
    ('Battery_Door (18650 holder, battery clamp)', battery_door),
    ('Battery_Clamp (holds the 18650 holder down)', battery_clamp),
    ('Screw_Plugs (cover the 4 battery door screws)', screw_plugs),
    ('Torso_Lid (MPU6050, MPR121, perfboard hub with 2 Mini560, tail MG90S, 2 side VL53L0X, touch pads)', torso_lid_v3),
    ('Collar (cables only)', collar),
    ('Head_Front (Guition 4.3in screen, 2 MS3625 mics, touch pad)', head_front_v3),
    ('Head_Back (cavity speaker)', head_back_v3),
    ('Screen_Washers (4 washers under the Guition screen screws)', screen_washers),
    ('Port_Door_Head (covers the screen USB-C)', lambda p: port_door(p, -1, HEAD_DOOR['zc'], HEAD_DOOR['yc'], HEAD['x'] - HEAD_W, HEAD['x'])),
    ('Port_Blank_Head (matches the port door)', lambda p: port_door(p, 1, HEAD_DOOR['zc'], HEAD_DOOR['yc'], HEAD['x'] - HEAD_W, HEAD['x'])),
    ('Muzzle (ESP32-S3 CAM, OV5640 camera, APDS-9960)', muzzle_v3),
    ('Port_Door_Muzzle (covers the camera USB-C)', lambda p: port_door(p, 1, MUZ_DOOR['zc'], MUZ_DOOR['yc'], MUZ['x'] - MUZ_W, MUZ['x'])),
    ('Port_Blank_Muzzle (matches the port door)', lambda p: port_door(p, -1, MUZ_DOOR['zc'], MUZ_DOOR['yc'], MUZ['x'] - MUZ_W, MUZ['x'])),
    ('Ear_Left (decorative)', lambda p: ear_v3(p, 1)),
    ('Ear_Right (decorative)', lambda p: ear_v3(p, -1)),
    ('Tail_Root (tail cross horn, tail cap)', tail_root),
    ('Tail (decorative, keyed onto the tail root)', tail_v3),
]
for sx in (1, -1):
    for sz in (1, -1):
        ln = leg_name(sx, sz)
        PRINTED += [
            (f'Thigh_{ln}_Outer (knee MG90S tabs, hip cross horn)', lambda p, a=sx, b=sz: thigh_outer(p, a, b)),
            (f'Thigh_{ln}_Cover (knee MG90S case, leads)', lambda p, a=sx, b=sz: thigh_cover(p, a, b)),
            (f'Shin_{ln}_Outer (wheel MG90S 360 tabs, knee cross horn)', lambda p, a=sx, b=sz: shin_outer(p, a, b)),
            (f'Shin_{ln}_Cover (wheel MG90S 360 case, leads)', lambda p, a=sx, b=sz: shin_cover(p, a, b)),
            (f'Wheel_{ln} (wheel cross horn, 26x2.4 O-ring tyre)', lambda p, a=sx, b=sz: wheel_v3(p, a, b)),
        ]
for sx in (1, -1):
    for sz in (1, -1):
        ln = leg_name(sx, sz)
        PRINTED += [
            (f'Cap_Hip_{ln} (covers the hip horn screw)', lambda p, a=sx, b=sz: hub_cap(p, 'hip', a, b)),
            (f'Cap_Knee_{ln} (covers the knee horn screw)', lambda p, a=sx, b=sz: hub_cap(p, 'knee', a, b)),
            (f'Cap_Wheel_{ln} (covers the wheel horn screw)', lambda p, a=sx, b=sz: hub_cap(p, 'wheel', a, b)),
        ]
PRINTED += [
    ('Cap_Tail (covers the tail horn screw)', lambda p: hub_cap(p, 'tail')),
    ('Coupon_Knee_Thigh (knee MG90S - test print)', coupon_knee_thigh),
    ('Coupon_Knee_Shin (knee cross horn, lead chamber - test print)', coupon_knee_shin),
    ('Coupon_Snap_White (snap hook, cap seats - test print)', coupon_snap_white),
    ('Coupon_Snap_Graphite (snap catch - test print)', coupon_snap_graphite),
    ('Fit_Test_Coupon (print first - servo slot, switch, screen boss, windows, O-ring groove, horn pocket)', fit_coupon),
]
EXPECTED_BODIES = {'Screen_Washers': 4, 'Screw_Plugs': 4}
NOT_IN_ROBOT = ('Fit_Test', 'Coupon_')                   # test prints: not in the assembly / clash / mass
COLOR = [('Cap_', BLACK), ('Port_', BLACK), ('Screw_Plugs', BLACK), ('Torso_Bottom', GRAPHITE), ('Side_Panel', GRAPHITE),
         ('Band_', GRAPHITE), ('Battery_Door', GRAPHITE), ('Battery_Clamp', GRAPHITE), ('Torso_Lid', WARM_WHITE),
         ('Collar', GRAPHITE), ('Head_', WARM_WHITE), ('Muzzle', WARM_WHITE), ('Ear_', WARM_WHITE), ('Tail', WARM_WHITE),
         ('Screen_Washers', BLACK), ('_Outer', WARM_WHITE), ('_Cover', GRAPHITE), ('Wheel_', GRAPHITE),
         ('Coupon_Knee', WARM_WHITE), ('Coupon_Snap_White', WARM_WHITE),
         ('Coupon_Snap_Graphite', GRAPHITE)]
BOUGHT_NAME = 'BOUGHT - every purchased part in place'
ASM_NAME = 'Desk Buddy v3.1 - full assembly'


def color_for(short):
    for key, col in COLOR:
        if key in short:
            return col
    return None


def _v():
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def save_part(p, stl=True):
    p.m.SketchManager.AddToDB = False
    return p.save_split(OUT, STL if stl else None, PNG)['sldprt']


def print_axis(short):
    for key, ax in PRINT_AXIS:
        if short.startswith(key):
            return ax
    return 'z'


ALT_SLICER = {'walls': 2}        # also reported: the same parts with 2 walls (the lighter, weaker option)


def printed_grams(name):
    """v3.1: slicer estimate from the EXPORTED STL of a printed part: (grams, fill, grams with ALT_SLICER)."""
    path = os.path.join(STL, name + '.STL')
    ax = print_axis(name.split(' (')[0])
    r = swlib.stl_print_estimate(path, ax)
    alt = swlib.stl_print_estimate(path, ax, s=ALT_SLICER)
    return r['grams'], r['fill'], alt['grams']


def copies(model, label):
    """Temporary copies of every solid body (for the clash check), plus mass-property data (for balance)."""
    out = []
    for b in model.GetBodies2(0, True) or []:
        nm = b.Name if label is None else label
        mp = b.GetMassProperties(1.0)
        out.append((nm, b.Copy(), [v * 1000 for v in b.GetBodyBox()], (mp[0] * 1000, mp[1] * 1000, mp[2] * 1000), mp[3] * 1e6))
    return out


def clash_check(items):
    """Every pair of bodies whose boxes overlap is intersected; report any shared volume over 0.5 mm3.
    Bodies of the same bought item (servo case + its own tabs/horn/screws) are not compared with each other."""
    found = []
    group = lambda n: n.split(' - ')[0]
    for i in range(len(items)):
        ni, bi, xi = items[i][:3]
        for j in range(i + 1, len(items)):
            nj, bj, xj = items[j][:3]
            if group(ni) == group(nj):
                continue
            if any(xi[k] >= xj[k + 3] - 0.01 or xj[k] >= xi[k + 3] - 0.01 for k in range(3)):
                continue
            try:
                res = bi.Copy().Operations2(15901, bj.Copy(), 0)       # 15901 = intersect; typed call returns (bodies, error)
                bodies = res[0] if isinstance(res, tuple) else res
                vol = sum(Dispatch(r).GetMassProperties(1.0)[3] for r in (bodies or [])) * 1e9
            except Exception as ex:
                found.append((ni, nj, -1.0, str(ex)[:60])); continue
            if vol > 0.5:
                found.append((ni, nj, vol, ''))
    return found


def balance(masses):
    """Centre of mass vs the wheel contacts: how far inside the support area it sits on four wheels and with
    each foot lifted (negative = it tips unless the gait first shifts the body)."""
    M = sum(m for _, m, _ in masses)
    c = [sum(m * q[k] for _, m, q in masses) / M for k in range(3)]
    cx = WHEEL_IN + 4.0
    feet = {(sx, sz): (sx * cx, LEGS[sz][0]) for sx in (-1, 1) for sz in (-1, 1)}

    def margin(poly):
        best = 1e9
        for i in range(len(poly)):
            (ax, az), (bx, bz) = poly[i], poly[(i + 1) % len(poly)]
            ex, ez = bx - ax, bz - az
            L = math.hypot(ex, ez)
            ox = sum(q[0] for q in poly) / len(poly); oz = sum(q[1] for q in poly) / len(poly)
            nx, nz = -ez / L, ex / L
            if (ox - ax) * nx + (oz - az) * nz < 0:
                nx, nz = -nx, -nz
            best = min(best, (c[0] - ax) * nx + (c[2] - az) * nz)
        return best
    order = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    rows = [f'BALANCE: total {M:.0f} g, centre of mass x {c[0]:+.1f}  y {c[1]:.1f} ({c[1] - DESK_Y:.0f} mm above the desk)  '
            f'z {c[2]:+.1f} mm (feet at z {LEGS[1][0]:+.0f} / {LEGS[-1][0]:+.0f})',
            f'  on 4 wheels: {margin([feet[k] for k in order]):.1f} mm inside the support area']
    for lift in order:
        tri = [feet[k] for k in order if k != lift]
        nm = ('front ' if lift[1] > 0 else 'rear ') + ('left' if lift[0] > 0 else 'right')
        rows.append(f'  lift {nm:11s} foot: {margin(tri):+6.1f} mm')
    return rows


# =============================================================================================
# v3 LEG CLEARANCE SWEEPS (pure geometry, from the same outlines the parts are built from)
# =============================================================================================
BELLY_R = 8.0            # chest / rump bottom edges (body agent: REQUIRED for these numbers)
HIP_SWING, KNEE_SWING = 30.0, 50.0
SHIN_TILT = (-9.9, 19.8)  # gait.py shin limits, + = toe (long end of the paw) up


def _belly_y(z):
    """Underside of the torso / side panels in side view (y 0, R8 at both ends), None beyond the ends."""
    if abs(z) > TZ:
        return None
    if abs(z) <= TZ - BELLY_R:
        return 0.0
    dz = abs(z) - (TZ - BELLY_R)
    return BELLY_R - math.sqrt(max(BELLY_R ** 2 - dz * dz, 0.0))


def _rot(pt, c, deg):
    t = math.radians(deg)
    dz, dy = pt[0] - c[0], pt[1] - c[1]
    return (c[0] + dz * math.cos(t) - dy * math.sin(t), c[1] + dz * math.sin(t) + dy * math.cos(t))


def _outline_pts(lp, grow=0.0, step=0.4):
    pts = swlib.loop_points(lp, step)
    if not grow:
        return pts
    cx = sum(q[0] for q in pts) / len(pts); cy = sum(q[1] for q in pts) / len(pts)
    out = []
    for i, q in enumerate(pts):                       # push each point out along the outline normal
        a, b = pts[i - 1], pts[(i + 1) % len(pts)]
        t = _unit2((b[0] - a[0], b[1] - a[1]))
        n = (t[1], -t[0])
        if (q[0] - cx) * n[0] + (q[1] - cy) * n[1] < 0:
            n = (-n[0], -n[1])
        out.append((q[0] + grow * n[0], q[1] + grow * n[1]))
    return out


def leg_sweeps():
    rows = ['LEG CLEARANCE SWEEPS (side view, from the build outlines):']
    knee_pod = swlib.rrect(CASE_BAND[0], CASE_BAND[1], *KNEE_POD_Y, (4.0, 4.0, 3.0, 3.0))
    # the R3 concave fillet where the pod meets the thigh cover (x 46.4-49.4) sits 1.04 above the pod at the
    # side panel's outer face (x 48.6); the pod body itself is under the tub and the panel.
    dx = KNEE_ROOT_R - (THIGH_COVER_IN - FLANK)          # root fillet: how far it reaches under the panel
    grow_at_panel = KNEE_ROOT_R - math.sqrt(KNEE_ROOT_R ** 2 - dx * dx) if dx > 0 else 0.0
    worst_all = {}
    for sz in (1, -1):
        hz, d = LEGS[sz][0], KNEE_DZ[sz]
        for label, grow in (('pod', 0.0), ('pod + root fillet under the panel', grow_at_panel)):
            pts = [(hz + d * a, y) for a, y in _outline_pts(knee_pod, grow)]
            worst = (1e9, 0, 0)
            first = {}
            for th10 in range(-int(HIP_SWING * 10), int(HIP_SWING * 10) + 1, 5):
                for q in pts:
                    z, y = _rot(q, (hz, HIP_Y), th10 / 10)
                    by = _belly_y(z)
                    if by is not None and by - y < worst[0]:
                        worst = (by - y, th10 / 10, z)
            for sign in (1, -1):
                for th10 in range(0, 900, 5):
                    hit = False
                    for q in pts:
                        z, y = _rot(q, (hz, HIP_Y), sign * th10 / 10)
                        by = _belly_y(z)
                        if by is not None and by - y < 0:
                            hit = True; break
                    if hit:
                        first[sign] = sign * th10 / 10; break
            worst_all[(sz, label)] = worst[0]
            rows.append(f'  knee pod {"front" if sz > 0 else "rear "} vs belly ({label}): min {worst[0]:5.2f} mm over hip '
                        f'+/-{HIP_SWING:.0f} deg (at {worst[1]:+.1f} deg, z {worst[2]:+.1f}); first touch at '
                        f'{first.get(1, "none")} / {first.get(-1, "none")} deg')
    # paws vs the desk at the shin limits (the wheel stays on the desk: rotate about the axle)
    for label, lp in (('paw band (toe/heel, R4)', swlib.rrect(TAB_BAND[0], TAB_BAND[1], AXLE_Y - POD_Y, AXLE_Y + POD_Y, 4.0)),
                      ('paw pod (R4 lower corners)', swlib.rrect(CASE_BAND[0], CASE_BAND[1], AXLE_Y - POD_Y, AXLE_Y + POD_Y, (4.0, 4.0, 3.0, 3.0)))):
        worst = (1e9, 0)
        for th10 in range(int(SHIN_TILT[0] * 10), int(SHIN_TILT[1] * 10) + 1):
            for q in swlib.loop_points(lp, 0.3):
                z, y = _rot(q, (0.0, AXLE_Y), th10 / 10)
                if y - DESK_Y < worst[0]:
                    worst = (y - DESK_Y, th10 / 10)
        rows.append(f'  {label} vs desk (y {DESK_Y:.1f}): min {worst[0]:.2f} mm over shin tilt {SHIN_TILT[0]}..+{SHIN_TILT[1]} deg (at {worst[1]:+.1f})')
    # paw pod vs belly: hip +/-30 x knee +/-50
    paw = swlib.rrect(TAB_BAND[0], TAB_BAND[1], AXLE_Y - POD_Y, AXLE_Y + POD_Y, 4.0)
    for sz in (1, -1):
        hz = LEGS[sz][0]
        pts = [(hz + a, y) for a, y in swlib.loop_points(paw, 0.6)]
        worst, gait = (1e9, 0, 0), (1e9, 0, 0)
        for kn in range(-int(KNEE_SWING), int(KNEE_SWING) + 1, 2):
            kp = [_rot(q, (hz, KNEE_Y), kn) for q in pts]
            for th in range(-int(HIP_SWING), int(HIP_SWING) + 1, 2):
                for q in kp:
                    z, y = _rot(q, (hz, HIP_Y), th)
                    by = _belly_y(z)
                    if by is not None and by - y < worst[0]:
                        worst = (by - y, th, kn)
                    if by is not None and SHIN_TILT[0] <= th + kn <= SHIN_TILT[1] and by - y < gait[0]:
                        gait = (by - y, th, kn)
        rows.append(f'  paw {"front" if sz > 0 else "rear "} vs belly: min {gait[0]:.1f} mm with the shin inside the gait limits; '
                    f'{worst[0]:.1f} mm over the full hip +/-{HIP_SWING:.0f} x knee +/-{KNEE_SWING:.0f} deg (at hip {worst[1]:+d}, knee {worst[2]:+d})')
    # paw (shin, x 38.2-66.4) vs the thigh + knee pod (x 27.4-60.6) about the knee
    thigh = [(a, y) for a, y in swlib.loop_points(thigh_outline(), 0.6)]
    thigh += swlib.loop_points(swlib.rrect(CASE_BAND[0], CASE_BAND[1], *KNEE_POD_Y, 3.0), 0.6)
    worst = 1e9
    for kn in range(-int(KNEE_SWING), int(KNEE_SWING) + 1, 2):
        for sz in (1, -1):
            d = KNEE_DZ[sz]
            kp = [_rot((a, y), (0.0, KNEE_Y), kn) for a, y in swlib.loop_points(paw, 0.8)]
            for q in kp:
                for t in thigh:
                    worst = min(worst, math.dist(q, (d * t[0], t[1])))
    rows.append(f'  paw vs thigh + knee pod over knee +/-{KNEE_SWING:.0f} deg: min distance {worst:.1f} mm')
    rows.append(f'  lead corridors (gap for a dia {LEAD_D} bundle): knee {KNEE_CORRIDOR[3]:.2f} mm, paw {PAW_CORRIDOR[3]:.2f} mm')
    return rows


JOINT_MARGIN = 2.0       # v3.1: firmware keeps every paw at least this far below the belly


def _paw_clear(hz, th, kn, pts):
    """Smallest gap (mm) between the belly and the paw outline pts (side view) at hip th / knee kn (deg)."""
    best = 1e9
    for q in pts:
        z, y = _rot(_rot(q, (hz, KNEE_Y), kn), (hz, HIP_Y), th)
        by = _belly_y(z)
        if by is not None:
            best = min(best, by - y)
    return best


def joint_limits(margin=JOINT_MARGIN):
    """v3.1 JOINT-LIMIT TABLE for the firmware: at each hip angle (1 deg steps), the knee range (within the servo's
    +/-50) that keeps the paw pod >= margin under the belly. Only the paw POD (|x| 38.2-60) can pass under the body
    (|x| <= 48.6); the paw band / toe (|x| 60-61.4), the shin and the wheel are outboard of it, so the v3 sweep's
    whole-paw outline (-1.6 mm) was conservative. Signs: + moves the foot FORWARD (toward the head)."""
    paw = swlib.rrect(TAB_BAND[0], TAB_BAND[1], AXLE_Y - POD_Y, AXLE_Y + POD_Y, 4.0)
    pod = swlib.rrect(CASE_BAND[0], CASE_BAND[1], AXLE_Y - POD_Y, AXLE_Y + POD_Y, (4.0, 4.0, 3.0, 3.0))
    rows = [f'JOINT LIMITS for the firmware (paw pod >= {margin:.1f} mm under the belly; + = foot forward, - = foot back; '
            f'servo range assumed +/-{KNEE_SWING:.0f}):']
    table = {}
    for sz in (1, -1):
        hz = LEGS[sz][0]
        leg = 'front legs' if sz > 0 else 'rear legs '
        pod_pts = [(hz + a, y) for a, y in swlib.loop_points(pod, 0.5)]
        paw_pts = [(hz + a, y) for a, y in swlib.loop_points(paw, 0.6)]
        worst = min((_paw_clear(hz, th, kn, pod_pts), th, kn) for th in range(-30, 31, 2) for kn in range(-50, 51, 2))
        wpaw = min((_paw_clear(hz, th, kn, paw_pts), th, kn) for th in range(-30, 31, 2) for kn in range(-50, 51, 2))
        rows.append(f'  {leg}: paw pod vs belly {worst[0]:.1f} mm at worst (hip {worst[1]:+d}, knee {worst[2]:+d}); '
                    f'the v3 whole-paw outline gives {wpaw[0]:.1f} mm (it counts the toe, which is outboard of the body)')
        lim = []
        for th in range(-int(HIP_SWING), int(HIP_SWING) + 1):
            ok = [kn for kn in range(-int(KNEE_SWING), int(KNEE_SWING) + 1) if _paw_clear(hz, th, kn, pod_pts) >= margin]
            contiguous = bool(ok) and ok == list(range(ok[0], ok[-1] + 1))
            lim.append((th, ok[0] if ok else None, ok[-1] if ok else None, contiguous))
        table[sz] = lim
        tight = [(th, k0, k1, c) for th, k0, k1, c in lim if k0 is None or k0 > -KNEE_SWING or k1 < KNEE_SWING]
        if not tight:
            rows.append(f'  {leg}: no limit needed inside hip +/-{HIP_SWING:.0f} x knee +/-{KNEE_SWING:.0f}')
            continue
        rows.append(f'  {leg}: ' + '; '.join(f'hip {th:+d}: knee {k0:+d}..{k1:+d}' + ('' if c else ' (NOT one range)')
                                            for th, k0, k1, c in tight))
        h0 = min(t[0] for t in tight if t[0] > 0) if any(t[0] > 0 for t in tight) else None
        if h0 is not None:
            kmax = min(t[2] for t in tight if t[0] >= h0)
            rows.append(f'  {leg}: SIMPLE RULE: when hip >= {h0:+d} deg, keep knee <= {kmax:+d} deg')
        h1 = max(t[0] for t in tight if t[0] < 0) if any(t[0] < 0 for t in tight) else None
        if h1 is not None:
            kmin = max(t[1] for t in tight if t[0] <= h1)
            rows.append(f'  {leg}: SIMPLE RULE: when hip <= {h1:+d} deg, keep knee >= {kmin:+d} deg')
    rows.append(f'  gait limits (shin tilt = hip + knee between {SHIN_TILT[0]} and +{SHIN_TILT[1]} deg) never reach these limits')
    return rows, table


V2_COMPARE = ['  v2 for comparison: total 840 g, centre of mass z +17.4, on 4 wheels 48.6 mm inside, lift front left/right -8.3 / -8.5 mm',
              '  v3 for comparison: total 1058 g, centre of mass z +17.0, on 4 wheels 49.0 mm inside, lift front left/right '
              '-8.2 / -8.0 mm, lift rear right/left +8.2 / +8.0 mm (printed parts at FILL 0.75 = 460 g)',
              '  v3 measured the same way as v3.1 (its own STLs through the same slicer model, 2 walls = 393 g, same bought '
              'parts): total 991 g, centre of mass z +17.4, on 4 wheels 48.6 mm inside, lift front left/right -8.5 / -8.3 mm, '
              'lift rear right/left +8.5 / +8.3 mm (with 3 walls: 48.3 mm). FILL 0.75 on every part over-weighted the '
              'legs (they print at 50-60 % fill), which put the v3 report\'s centre of mass 0.4 mm too far back.']
BODY_NOTES = [
    'BODY (v3 sections 2-7):',
    f'  lower body width {2 * FLANK:.1f} (side panels), belly R{BELLY_R:.0f} at chest and rump, lid top R6, head R8 face / R10 back / R8 side edges',
    f'  hip leads: panel slot 9 x 5 at y 26.5-31.5, tub-wall notch 9 wide from y 26.5 to the rim, lid comb teeth down to y {LEAD_EXIT_Y[1]}',
    f'  USB-C: 13 x 7 pill in the rump band at x {USB_X}, y {USB_Y:.2f}; receptacle face 1.5 behind the band face; charger raised to y {CHG_Y0}',
    f'  KCD1 at the front belly centre, z {KCD1_ZC - KCD1_X / 2:.1f}-{KCD1_ZC + KCD1_X / 2:.1f}, flush in a {KCD1_RECESS} recess; battery door x +-{DOOR["x"]:.0f}, z {DOOR["z0"]:.0f}..{DOOR["z1"]:.0f}',
    f'  tail: servo under the lid (tabs at y {TAIL_SV_UNDER}), root dia {2 * TAIL_ROOT["r"]:.0f} in a dia {2 * TAIL_SOCKET["r"]:.1f} socket, tail rises {TAIL_RISE:.0f} deg',
]
_TAIL_HORN_TOP = TAIL_SV_UNDER + SV_SPLINE + HORN_OUT
V31_NOTES = [
    'v3.1 CHANGES (all inside the parts; outside surfaces as v3):',
    f'  walls: head {HEAD_W} (face 2.4 round the screen), tub sides/ends {TUB_W} (floor {W}), lid walls {LID_WALL} above a '
    f'{LID_LIP_T} lip (top {W}), muzzle sides/top {MUZ_W}, collar {COLLAR_W}; side panels as v3 (1.8 skin); '
    f'tub side windows |z| <= {TUB_WIN[0]:.0f}, y {TUB_WIN[1]:.0f}-{TUB_WIN[2]:.0f} behind the panels',
    f'  balance: perfboard hub (22 g) moved {-HUB_DZ:.0f} mm rearward under the lid (fences and tie anchors with it)',
    f'  tail cap: peg {TAIL_CAP_PEG} long, its bottom at y {TAIL_CAP_Y - TAIL_CAP_PEG:.1f} vs the tail horn top at y '
    f'{_TAIL_HORN_TOP:.1f}: {TAIL_CAP_Y - TAIL_CAP_PEG - _TAIL_HORN_TOP:.1f} mm clear (v3 report: 1.9 mm3 overlap from an older run)',
    f'  head: collar screws on {W - HEAD_W:.1f} pads (2.4 clamped, no counterbores), head-back lip notched |x| <= {NECK_NOTCH_X} over them; '
    f'muzzle screws on {W - HEAD_W:.1f} pads; screen frame plate {W - HEAD_W:.1f}; ears on {EAR_PAD:.1f} pads; snap detent pockets {HOOK_POCKET} deep '
    f'({HEAD_W - HOOK_POCKET:.1f} skin behind them - the one place under 1.6)',
    f'  battery door lugs {DOOR_LUG_TOP} high (v3 8.6) so the door takes M2 x 6; touch-pad screws M2 x 4 (the v3 note said M2 x 6, '
    f'which would pierce the lid top)',
    f'  ribs: 2 stiffening ribs 1.2 x 3 inside the head back at y {HEAD_BACK_RIBS[0]:.0f} and {HEAD_BACK_RIBS[1]:.0f} (the widest thin flat panel); '
    f'the lid top keeps its 2.4 plate and ceiling fences, the side panels their 3 ribs',
]
BODY_AGENT_NOTES = [
    'FOR THE BODY AGENT (numbers the legs were built to):',
    f'  side panel outer face |x| {FLANK:.1f} (thigh cup rim at |x| {HIP_CUP_RIM:.1f}: 0.8 reveal); cup dia {2 * HIP_CUP_R:.0f} about (y {HIP_Y}, z = hip z), skirt r {CUP_SKIRT_IN}-{HIP_CUP_R}',
    f'  hip lead chamber x {FLANK:.1f}-{THIGH_IN:.1f}, r 5.2-16.3; hip boss dia 11.8 top at |x| {TX + SV_TOP_HUMP:.1f} (panel hole dia 13.4); leads leave at 12 o\'clock',
    '  panel wire slot 9.0 x 5.0 at y 26.5-31.5, z = hip z +/-4.5 (inside the cup at every hip angle); tub-wall notch 9 wide from y 26.5 up to the rim',
    f'  chest + rump bottom edges R{BELLY_R:.0f} (REQUIRED); side panels follow the same side profile (bottom R8 at the ends)',
    f'  knee pods reach |x| {KNEE_POD_IN:.1f} inward (top y {KNEE_POD_Y[1]:.1f}) and pass under the belly; paw pods reach |x| {PAW_POD_IN:.1f}',
    '  the v2 belly lead slots (x 28-36, |z| 35-45) are no longer used - delete them',
    f'  tail cap dia 12 x 1.6 at x 0, z {TAIL_Z}, seat (recess floor) at y {TAIL_CAP_Y}: root needs a dia 12.2 x 1.2 recess + dia 6 hole',
    f'  wheel caps stand 0.4 proud: overall width |x| {WHEEL_OUT + 0.4:.1f}; desk at y {DESK_Y:.1f}; stance feet at |x| {WHEEL_IN + 4.0:.1f}',
]


def build_assembly(sw, paths, boxes):
    asm = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    title = asm.GetTitle
    mu = sw.GetMathUtility
    mu._FlagAsMethod('CreateTransform')
    ident = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0])
    added = 0
    # v3.1: open the parts WITHOUT windows. v3 opened 56 visible part windows and kept them; with the parts stage
    # before it that ran SOLIDWORKS out of GDI objects (9275 of the 10000 Windows allows a process) - the
    # "critically low on windowing resources" stop that also ended the last v3 run.
    sw.DocumentVisible(False, 1)                       # 1 = part documents
    try:
        for pth in paths:
            d = sw.OpenDoc6(pth, 1, 1, '', _v(), _v())
            if pth not in boxes and d is not None:     # --assembly-only: expected position = the part's own box
                xs = [b.GetBodyBox() for b in (d.GetBodies2(0, True) or [])]
                if xs:
                    boxes[pth] = [round(min(b[i] for b in xs) * 1000, 1) if i < 3 else round(max(b[i] for b in xs) * 1000, 1)
                                  for i in range(6)]
    finally:
        sw.DocumentVisible(True, 1)
    for pth in paths:
        sw.ActivateDoc3(title, False, 0, _v())
        c = asm.AddComponent5(pth, 0, '', False, '', 0, 0, 0)
        if c is not None:
            # AddComponent5 puts the part's bounding-box CENTRE at the point given; every part is already
            # modelled in its real place, so put its origin back on the assembly origin instead.
            c.Transform2 = mu.CreateTransform(ident)
            box = [round(x * 1000, 1) for x in c.GetBox(False, False)]
            if pth in boxes and max(abs(a - b) for a, b in zip(box, boxes[pth])) > 1.0:
                raise RuntimeError(f'{os.path.basename(pth)} landed at {box}, expected {boxes[pth]}')
            added += 1
    asm.EditRebuild3
    asm.ForceRebuild3(False)
    asm.ClearSelection2(True)
    out = os.path.join(OUT, ASM_NAME + '.SLDASM')
    asm.Extension.SaveAs3(out, 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    for view, tag in (('*Isometric', 'iso'), ('*Front', 'front'), ('*Right', 'side'), ('*Top', 'top'),
                      ('*Back', 'back'), ('*Bottom', 'under')):
        asm.ShowNamedView2(view, -1); asm.ViewZoomtofit2(); asm.ClearSelection2(True)
        asm.Extension.SaveAs3(os.path.join(PNG, f'{ASM_NAME} - {tag}.png'), 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    # v3.1: exploded pictures per body section (real colours); everything is put back afterwards
    global SECTION_ROWS
    try:
        render_sections_real(asm, mu)
    except Exception as ex:
        SECTION_ROWS.append(f'  ERR section renders: {ex}')
    # "inside" picture: every printed shell made see-through (the saved assembly above is unchanged)
    shells = ('Torso_', 'Side_Panel', 'Band_', 'Battery_Door', 'Collar', 'Head_', 'Muzzle', 'Thigh_', 'Shin_',
              'Port_', 'Tail', 'Ear_', 'Wheel_')
    n_see = 0
    for c in asm.GetComponents(True) or []:
        nm = c.Name2
        if not any(k in nm for k in shells):
            continue
        try:
            doc = c.GetModelDoc2
            vals = list(c.MaterialPropertyValues or []) or list(doc.MaterialPropertyValues)
            vals[7] = 0.82
            vals[8] = 0.0
            c.SetMaterialPropertyValues2(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [float(v) for v in vals]), 2, None)
            n_see += 1
        except Exception:
            try:
                c.Visible = 0
                n_see += 1
            except Exception:
                pass
    asm.ShowNamedView2('*Isometric', -1); asm.ViewZoomtofit2(); asm.ClearSelection2(True)
    asm.Extension.SaveAs3(os.path.join(PNG, f'{ASM_NAME} - inside (shells see-through).png'), 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    # v3.1: labels for the section pictures (flat ID colours; nothing is saved to the parts or the assembly)
    try:
        SECTION_ROWS.extend(label_sections(render_sections_ids(asm, mu)))
    except Exception as ex:
        SECTION_ROWS.append(f'  ERR section labels: {ex}')
    return added, n_see


SECTION_ROWS = []


def contact_sheet(names):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return
    cells = []
    for n in names:
        f = os.path.join(PNG, n + '.png')
        if os.path.exists(f):
            cells.append((n, Image.open(f).convert('RGB')))
    if not cells:
        return
    cw, ch, cols = 420, 340, 6
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new('RGB', (cw * cols, ch * rows), 'white')
    try:
        font = ImageFont.truetype('arial.ttf', 13)
    except Exception:
        font = ImageFont.load_default()
    d = ImageDraw.Draw(sheet)
    for k, (n, im) in enumerate(cells):
        im.thumbnail((cw - 10, ch - 60))
        x, y = (k % cols) * cw, (k // cols) * ch
        sheet.paste(im, (x + (cw - im.width) // 2, y + 5))
        words, line, ty = n.split(' '), '', y + ch - 52
        for w in words:
            if d.textlength(line + ' ' + w, font=font) > cw - 12:
                d.text((x + 6, ty), line.strip(), fill='black', font=font); ty += 15; line = ''
            line += ' ' + w
        d.text((x + 6, ty), line.strip(), fill='black', font=font)
    sheet.save(os.path.join(PNG, 'ALL PRINTED PARTS - sheet.png'))


# =============================================================================================
# v3.1 SECTION RENDERS: one exploded, labelled picture per body section (for the PDF assembly guide)
# =============================================================================================
# (title, printed parts {short name: explode offset mm}, bought bodies shown (name fragments), bought labels)
SECTIONS = [
    ('1 Body - tub, side panels, bands, battery door',
     {'Torso_Bottom': (0, 0, 0), 'Side_Panel_Left': (60, 0, 0), 'Side_Panel_Right': (-60, 0, 0),
      'Band_Chest': (0, 0, 50), 'Band_Rump': (0, 0, -50), 'Battery_Door': (0, -55, 0), 'Battery_Clamp': (0, 45, 0),
      'Screw_Plugs': (0, -75, 0)},
     ('PCA9685', 'Servo plugs', '2S 20A', 'Mini blade', 'Type-C', 'KCD1', '2x18650', 'VL53L0X front', 'VL53L0X rear',
      'Hip ', 'hip exit', 'along the tub wall'),
     [('PCA9685 servo board left', 'PCA9685 servo board (x2)'), ('2x18650', '2x18650 holder + cells'),
      ('KCD1 switch - body', 'KCD1 power switch'), ('Type-C 2S charging board - PCB', 'USB-C charger board'),
      ('Hip FL - MG90S case', 'hip MG90S (x4)'), ('VL53L0X front obstacle', 'VL53L0X obstacle laser (x2)')]),
    ('2 Lid - lid, tail root, tail, tail cap',
     {'Torso_Lid': (0, 55, 0), 'Tail_Root': (0, 90, 0), 'Cap_Tail': (0, 110, 0), 'Tail': (0, 100, -30)},
     ('MPU6050', 'MPR121', 'Perfboard', 'VL53L0X side', 'Tail - '),
     [('MPU6050', 'MPU6050 IMU'), ('MPR121', 'MPR121 touch board'), ('Perfboard', 'perfboard hub (2x Mini560)'),
      ('VL53L0X side laser left', 'side VL53L0X (x2)'), ('Tail - MG90S case', 'tail MG90S')]),
    ('3 Head - head, collar, muzzle, ears, port doors',
     {'Head_Front': (0, 0, 55), 'Head_Back': (0, 0, -50), 'Collar': (0, -45, 0), 'Screen_Washers': (0, 0, 0),
      'Port_Door_Head': (-40, 0, 55), 'Port_Blank_Head': (40, 0, 55), 'Muzzle': (0, 0, 110),
      'Port_Door_Muzzle': (40, 0, 110), 'Port_Blank_Muzzle': (-40, 0, 110), 'Ear_Left': (0, 45, 55),
      'Ear_Right': (0, 45, 55)},
     ('Guition', 'ESP32-S3', 'OV5640', 'APDS', 'MS3625', 'Cavity speaker'),
     [('Guition 4.3in screen - glass', 'Guition 4.3in screen'), ('ESP32-S3 CAM board - PCB', 'ESP32-S3 CAM board'),
      ('Cavity speaker', 'speaker'), ('MS3625 mic left', 'MS3625 mic (x2)')]),
    ('4 Leg - front left (the other three are built the same way)',
     {'Thigh_FrontLeft_Cover': (-45, 0, 0), 'Thigh_FrontLeft_Outer': (0, 0, 0), 'Cap_Hip_FrontLeft': (30, 0, 0),
      'Shin_FrontLeft_Cover': (45, 0, 0), 'Shin_FrontLeft_Outer': (80, 0, 0), 'Cap_Knee_FrontLeft': (110, 0, 0),
      'Wheel_FrontLeft': (115, 0, 0), 'Cap_Wheel_FrontLeft': (145, 0, 0)},
     ('Hip FL', 'Knee FL', 'Wheel FL', 'O-ring tyre FL', 'Lead FL'),
     [('Hip FL - MG90S case', 'hip MG90S'), ('Knee FL - MG90S case', 'knee MG90S'),
      ('Wheel FL (360) - MG90S case', 'wheel MG90S 360'), ('O-ring tyre FL', '26x2.4 O-ring tyre')]),
]
ID_COLOURS = [(230, 25, 25), (25, 180, 25), (25, 60, 230), (230, 200, 0), (0, 200, 220), (220, 0, 220), (255, 120, 0),
              (120, 0, 230), (0, 130, 255), (255, 0, 120), (120, 220, 0), (0, 220, 120), (150, 75, 0), (0, 120, 120),
              (140, 0, 60), (70, 0, 140), (255, 160, 160), (160, 255, 160), (160, 160, 255)]


def _flat_mpv(rgb):
    return [rgb[0] / 255, rgb[1] / 255, rgb[2] / 255, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _section_setup(asm, mu, comps, sec):
    """Show only the section's printed parts (moved by their explode offsets) and the bought part."""
    _, parts, _, _ = sec
    for c in comps:
        off = parts.get(c.Name2.split(' (')[0])
        is_bought = c.Name2.startswith('BOUGHT')
        c.Visible = 1 if (off is not None or is_bought) else 0
        d = [v / 1000.0 for v in (off or (0, 0, 0))]
        c.Transform2 = mu.CreateTransform(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8,
                                                  [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, d[0], d[1], d[2], 1.0, 0, 0, 0]))


def _bought_doc(comps):
    for c in comps:
        if c.Name2.startswith('BOUGHT'):
            return c.GetModelDoc2
    return None


def _show_bought_bodies(bdoc, keep):
    n = 0
    for b in bdoc.GetBodies2(0, False) or []:
        vis = any(k in b.Name for k in keep)
        try:
            b.HideBody(not vis)
            n += vis
        except Exception:
            pass
    return n


def _frame(asm):
    """v3.1: the ONE way a section picture is framed (real and ID passes alike): let SOLIDWORKS apply the new
    transforms / visibility first, then zoom to fit twice (a zoom straight after moving parts can fit the old
    layout - it framed the leg section's ID pictures differently from its real picture)."""
    asm.EditRebuild3
    asm.GraphicsRedraw2()
    asm.ShowNamedView2('*Isometric', -1); asm.ViewZoomtofit2()
    asm.GraphicsRedraw2()
    asm.ViewZoomtofit2()
    asm.ClearSelection2(True)


def _save_png(asm, path):
    _frame(asm)
    asm.GraphicsRedraw2()
    asm.Extension.SaveAs3(path, 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    return path


def _sec_file(sec, tag):
    return os.path.join(PNG, f'{ASM_NAME} - section {sec[0].split(" - ")[0]} ({tag}).png')


def render_sections_real(asm, mu):
    """Pass 1 (real colours): every section exploded, saved as '... section N ... (exploded).png'."""
    comps = list(asm.GetComponents(True) or [])
    bdoc = _bought_doc(comps)
    done = []
    for sec in SECTIONS:
        _section_setup(asm, mu, comps, sec)
        if bdoc is not None:
            _show_bought_bodies(bdoc, sec[2])
        done.append(_save_png(asm, _sec_file(sec, 'exploded')))
    # put everything back for the pictures that follow
    ident = [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0]
    for c in comps:
        c.Visible = 1
        c.Transform2 = mu.CreateTransform(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, ident))
    if bdoc is not None:
        for b in bdoc.GetBodies2(0, False) or []:
            try:
                b.HideBody(False)
            except Exception:
                pass
    return done


OTHER_ID = (205, 170, 110)       # every visible, unlabelled item in the ID picture


def _save_png_keep_view(asm, path):
    """Save the picture WITHOUT changing the view (the ID passes must keep the real picture's exact framing)."""
    asm.ClearSelection2(True)
    asm.GraphicsRedraw2()
    asm.Extension.SaveAs3(path, 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    return path


RED_ID, GREY_ID = (200, 0, 0), (128, 128, 128)   # dark red leaves headroom: SOLIDWORKS brightens some colours


def render_sections_ids(asm, mu):
    """Label anchors at exactly the real picture's framing (same parts shown, same zoom-to-fit; afterwards only
    colours / visibility change, never the view). One picture per labelled item: that item red, the other printed
    parts of the section in their real colours, the other bought bodies hidden - so the red pixels are exactly the
    item's VISIBLE pixels (occlusion included), whatever SOLIDWORKS' shading does to the colour (the real colours
    - warm white, graphite, black, the bought parts' blue-grey - are all unsaturated, so none reads as red). The
    colours set here are never saved. Returns [(section, [(label, x, y)], union box, [not visible rows])]."""
    import numpy as np
    from PIL import Image
    comps = list(asm.GetComponents(True) or [])
    bdoc = _bought_doc(comps)
    bcomp = next((c for c in comps if c.Name2.startswith('BOUGHT')), None)
    mask_dir = os.path.join(PNG, 'label masks (flat colours used to place the labels)')
    os.makedirs(mask_dir, exist_ok=True)
    tmp = os.path.join(mask_dir, 'last label mask.png')
    flat = lambda c, col: c.SetMaterialPropertyValues2(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, _flat_mpv(col)), 2, None)
    out = []
    for sec in SECTIONS:
        title, parts, keep, blabels = sec
        _section_setup(asm, mu, comps, sec)
        if bdoc is not None:
            _show_bought_bodies(bdoc, keep)
        _frame(asm)                                                          # the real picture's framing
        mine = [c for c in comps if c.Name2.split(' (')[0] in parts]
        items = [('p', c) for c in mine] + [('b', kl) for kl in blabels]
        anchors, missing, box = [], [], None

        def grab(label):
            nonlocal box
            _save_png_keep_view(asm, tmp)
            m = _hue_mask(np.asarray(Image.open(tmp).convert('RGB')).astype(np.int32), RED_ID)
            ys, xs = np.nonzero(m)
            if len(xs) < 15:
                missing.append(f'  section {title.split(" - ")[0]}: "{label}" not visible in this view ({len(xs)} px) - no label')
                return
            cx, cy = xs.mean(), ys.mean()
            i = np.argmin((xs - cx) ** 2 + (ys - cy) ** 2)
            anchors.append((label, int(xs[i]), int(ys[i])))
            bb = (xs.min(), ys.min(), xs.max(), ys.max())
            box = bb if box is None else (min(box[0], bb[0]), min(box[1], bb[1]), max(box[2], bb[2]), max(box[3], bb[3]))
        # printed parts, one at a time (bought hidden)
        if bcomp is not None:
            bcomp.Visible = 0
        for c in mine:
            for o in mine:                  # clear every override first (setting a colour back does not stick)
                try:
                    o.RemoveMaterialProperty2(2, None)
                except Exception:
                    pass
            flat(c, RED_ID)                 # the others keep their real, unsaturated colours
            short = c.Name2.split(' (')[0]
            tone = {WARM_WHITE: 'warm white', GRAPHITE: 'graphite', BLACK: 'black'}.get(color_for(short), '')
            grab(f'{short} ({tone}, printed)' if tone else short)
        # bought labels, one body at a time (printed parts grey, so they still hide what they cover)
        for o in mine:
            try:
                o.RemoveMaterialProperty2(2, None)
            except Exception:
                pass
        if bdoc is not None and bcomp is not None and blabels:
            bcomp.Visible = 1
            bodies = list(bdoc.GetBodies2(0, False) or [])
            for key, lab in blabels:
                target = next((bd for bd in bodies if key in bd.Name), None)
                if target is None:
                    missing.append(f'  section {title.split(" - ")[0]}: no bought body named "{key}"'); continue
                for bd in bodies:
                    try:
                        bd.HideBody(bd.Name != target.Name)
                    except Exception:
                        pass
                try:
                    target.MaterialPropertyValues2 = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, _flat_mpv(RED_ID))
                except Exception:
                    pass
                grab(lab + ' (bought)')
        out.append((sec, anchors, box, missing))
    return out


def _hue_mask(img, rgb, tol=18.0):
    """Pixels of a shaded body painted `rgb` (a pure hue): same hue within tol deg, clearly coloured, not black."""
    import numpy as np
    f = img.astype(np.float64) / 255.0
    mx, mn = f.max(2), f.min(2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0)
    r, g, b_ = f[..., 0], f[..., 1], f[..., 2]
    d = np.maximum(mx - mn, 1e-9)
    h = np.where(mx == r, ((g - b_) / d) % 6, np.where(mx == g, (b_ - r) / d + 2, (r - g) / d + 4)) * 60.0
    tr = np.array(rgb, float) / 255.0
    tmx, tmn = tr.max(), tr.min()
    td = max(tmx - tmn, 1e-9)
    th = (((tr[1] - tr[2]) / td) % 6 if tmx == tr[0] else ((tr[2] - tr[0]) / td + 2 if tmx == tr[1] else (tr[0] - tr[1]) / td + 4)) * 60.0
    dh = np.abs((h - th + 180.0) % 360.0 - 180.0)
    return (dh < tol) & (sat > 0.35) & (mx > 0.25)


def label_sections(ids):
    """Draw the labels onto the real exploded picture, each pointing at a pixel of its own part (the one nearest the
    centre of the part's visible pixels); crop to the robot plus a margin. Returns report rows."""
    from PIL import Image, ImageDraw, ImageFont
    rows = []
    try:
        font = ImageFont.truetype('arial.ttf', 26); tfont = ImageFont.truetype('arialbd.ttf', 34)
    except Exception:
        font = tfont = ImageFont.load_default()
    for sec, anchors, box, missing in ids:
        rows += missing
        real = _sec_file(sec, 'exploded')
        if box is None:
            rows.append(f'  section {sec[0]}: nothing visible - labels skipped'); continue
        full = Image.open(real).convert('RGB')
        pad = 110
        x0, y0 = max(box[0] - pad, 0), max(box[1] - pad, 0)
        x1, y1 = min(box[2] + pad, full.width), min(box[3] + pad, full.height)
        im = full.crop((x0, y0, x1, y1))
        side, top = 560, 80
        W_, H_ = im.width + 2 * side, max(im.height + top + 20, top + 40 * (len(anchors) // 2 + 2))
        canvas = Image.new('RGB', (W_, H_), 'white')
        canvas.paste(im, (side, top))
        d = ImageDraw.Draw(canvas)
        d.text((24, 20), f'Desk Buddy v3.1 - section {sec[0]} (exploded)', fill='black', font=tfont)
        pts = [(lab, ax - x0 + side, ay - y0 + top) for lab, ax, ay in anchors]
        mid = side + im.width / 2
        for group, left in (([q for q in pts if q[1] < mid], True), ([q for q in pts if q[1] >= mid], False)):
            group.sort(key=lambda q: q[2])
            ylast = top - 40
            for lab, ax, ay in group:
                ty = max(ay, ylast + 40)
                ylast = ty
                tw = d.textlength(lab, font=font)
                tx = side - 30 - tw if left else side + im.width + 30
                lx = side - 22 if left else side + im.width + 22
                d.text((tx, ty - 14), lab, fill='black', font=font)
                d.line([(lx, ty), (ax, ay)], fill=(200, 30, 30), width=3)
                d.ellipse([ax - 6, ay - 6, ax + 6, ay + 6], outline=(200, 30, 30), width=3)
        outp = _sec_file(sec, 'exploded, labelled')
        canvas.save(outp)
        rows.append(f'  section {sec[0].split(" - ")[0]}: {len(anchors)} labels -> {os.path.basename(outp)}')
    return rows


def main_sections():
    """v3.1: redo only the section pictures (real + ID passes + labels) on the saved assembly, in one SOLIDWORKS
    session so the framing matches; nothing is saved to the assembly or the parts. Refreshes the report rows."""
    sw = swlib.app()
    before = open_titles(sw)
    if before:
        raise SystemExit(f'SolidWorks has documents open that this script did not create: {before} - close them first')
    mu = sw.GetMathUtility
    mu._FlagAsMethod('CreateTransform')
    sw.DocumentVisible(False, 1)
    try:
        asm = sw.OpenDoc6(os.path.join(OUT, ASM_NAME + '.SLDASM'), 2, 0, '', _v(), _v())
    finally:
        sw.DocumentVisible(True, 1)
    if asm is None:
        raise SystemExit('could not open the assembly')
    rows = ["SECTION PICTURES (exploded; labels anchored on each part's own pixels):"]
    try:
        render_sections_real(asm, mu)
        rows += label_sections(render_sections_ids(asm, mu))
    except Exception as ex:
        rows.append(f'  ERR section pictures: {ex}')
    for t in open_titles(sw):
        if t not in before:
            try:
                sw.CloseDoc(t)
            except Exception:
                pass
    old = open(REPORT, encoding='utf-8').read().split(chr(10))
    k = next((i for i, r in enumerate(old) if r.startswith('SECTION PICTURES')), None)
    if k is not None:
        e = k + 1
        while e < len(old) and (old[e].startswith('  section') or old[e].startswith('  ERR section')):
            e += 1
        old = old[:k] + rows + old[e:]
    else:
        old += rows
    open(REPORT, 'w', encoding='utf-8').write(chr(10).join(old))
    print(chr(10).join(rows))


def open_titles(sw):
    out, d = [], sw.GetFirstDocument
    while d is not None:
        out.append(d.GetTitle)
        d = d.GetNext
    return out


def gdi_objects(sw):
    """v3.1: GDI objects held by SOLIDWORKS (Windows stops a process at 10000; SOLIDWORKS warns near that)."""
    import ctypes
    try:
        h = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x1000, False, int(swlib._call(sw, 'GetProcessID')))
        n = ctypes.windll.user32.GetGuiResources(h, 0)
        ctypes.windll.kernel32.CloseHandle(h)
        return int(n)
    except Exception:
        return -1


GDI_ASSEMBLY_LIMIT = 6500        # above this after the parts stage: stop, restart SOLIDWORKS, run --assembly-only


def _fast(sw, p, on):
    """v3.1 speed-up while a part is modelled (runtime only, nothing persistent): SOLIDWORKS skips UI, feature-tree
    and graphics updates between API calls. Switched off again before any picture is saved."""
    try:
        sw.CommandInProgress = on
    except Exception:
        pass
    if p is None:
        return
    for obj, attr in ((p.fm, 'EnableFeatureTree'), (p.m.ActiveView, 'EnableGraphicsUpdate')):
        try:
            setattr(obj, attr, not on)
        except Exception:
            pass


def main(only=None):
    """only: list of name fragments - build just those printed parts (for iterating); no assembly then."""
    for d in (OUT, PNG, STL):
        os.makedirs(d, exist_ok=True)
    sw = swlib.app()
    before = open_titles(sw)
    if before:
        raise SystemExit(f'SolidWorks has documents open that this script did not create: {before} - close them first')
    swlib.probe(sw); swlib.probe_axes(sw)
    import time
    t_start = time.time()
    rows, paths, items, total_g, boxes, masses = [], [], [], 0.0, {}, [WIRES]
    total_p = total_alt = 0.0                                   # v3.1: slicer estimate from the exported STLs
    pending = []                                                # (part, [(centroid, share)], 3-wall g, 2-wall g)
    todo = [(n, b) for n, b in PRINTED if not only or any(o in n for o in only)]
    if only:                                                    # iterating: build in the order given
        todo.sort(key=lambda nb: min(i for i, o in enumerate(only) if o in nb[0]))
    for name, build in todo:
        p = P(sw, name)
        short = name.split(' (')[0]
        t_part = time.time()
        try:
            _fast(sw, p, True)
            try:
                build(p)
            finally:
                _fast(sw, p, False)
            nb = len(p.m.GetBodies2(0, True))
            want = EXPECTED_BODIES.get(short, 1)
            col = color_for(short)
            if col:
                p.set_color(col)
            bb = p.bbox_mm()
            size = sorted((bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]), reverse=True)
            grams = p.volume_cm3() * PLA
            path = save_part(p)                              # also exports the STL and checks its size + volume
            stl_path = os.path.join(STL, name + '.STL')
            shells = swlib.stl_shells(stl_path)              # v3.1: pieces counted in the EXPORTED file
            ssize = swlib.stl_size_mm(stl_path)
            pg, pfill, palt = printed_grams(name)
            if not any(k in name for k in NOT_IN_ROBOT):     # test prints are not part of the robot
                paths.append(path)
                boxes[path] = bb
                got = copies(p.m, short)
                items += got
                vtot = sum(vol for _, _, _, _, vol in got) or 1.0
                pending.append((short, [(cen, vol / vtot) for _, _, _, cen, vol in got], pg, palt))
                total_g += grams
                total_p += pg
                total_alt += palt
            fits = all(a <= b for a, b in zip(ssize, sorted(BED, reverse=True)))
            rows.append(f'OK  {short:24s} {ssize[0]:6.1f} x {ssize[1]:5.1f} x {ssize[2]:5.1f} mm  {grams:6.1f} g solid  '
                        f'{pg:6.1f} g printed (fill {pfill:.2f}, bed axis {print_axis(short)}; 2 walls {palt:.1f} g)  '
                        f'bodies={nb} STL shells={shells}{"" if nb == want and shells == want else "  <-- WRONG PIECE COUNT"}'
                        f'{"" if fits else "  <-- TOO BIG FOR THE PRINTER"}  STL size+volume ok')
            print(f'{time.time() - t_start:7.0f}s  {rows[-1]}  ({time.time() - t_part:.0f}s, GDI {gdi_objects(sw)})', flush=True)
            for kind, size_, pt, why in p.skipped:
                rows.append(f'      skipped {kind} {size_} at {tuple(round(c, 2) for c in pt)}: {why[:110]}')
        except Exception as ex:
            rows.append(f'ERR {short:24s} {ex}')
            print(f'{time.time() - t_start:7.0f}s  {rows[-1][:200]}', flush=True)
        sw.CloseDoc(p.m.GetTitle)
    sl = swlib.SLICER
    rows.append(f'    printed total {total_g:.0f} g solid, {total_p:.0f} g as printed (robot parts only; sliced from the '
                f'exported STLs: {sl["walls"]} walls x {sl["line"]} mm, {sl["top_bottom"]} mm top/bottom, '
                f'{sl["infill"] * 100:.0f} % {sl["pattern"]}, {sl["layer"]} mm layers; overall fill {total_p / max(total_g, 1e-9):.3f})')
    rows.append(f'    with {ALT_SLICER["walls"]} walls instead: {total_alt:.0f} g as printed')
    if not only:
        rows += profile_rows(rows)
    # the balance uses each part's grams under the chosen profile, spread over its bodies by volume
    masses += [(short, chosen_grams(short, pg, palt) * share, cen) for short, cs, pg, palt in pending for cen, share in cs]
    if not only:
        p = P(sw, BOUGHT_NAME)
        try:
            _fast(sw, p, True)
            try:
                bought(p)
            finally:
                _fast(sw, p, False)
            paths.append(save_part(p, stl=False))
            boxes[paths[-1]] = p.bbox_mm()
            got = copies(p.m, None)
            items += got
            masses += [(nm, bought_mass(nm), cen) for nm, _, _, cen, _ in got]
            rows.append(f'OK  {BOUGHT_NAME}  bodies={len(p.m.GetBodies2(0, True))}')
        except Exception as ex:
            rows.append(f'ERR {BOUGHT_NAME} {ex}')
        sw.CloseDoc(p.m.GetTitle)
        clashes = clash_check(items)
        rows.append(f'CLASH CHECK: {len(items)} bodies, {len(clashes)} clashes')
        for a, b_, vol, msg in clashes:
            rows.append(f'  CLASH {vol:8.1f} mm3  {a}  <->  {b_}  {msg}')
        items.clear()                  # release ~300 temporary body copies before the assembly loads 56 files
        import gc
        gc.collect()
        print(chr(10).join(rows), flush=True)   # the part / clash results survive even if the assembly step fails
        rows += balance(masses)
        rows += V2_COMPARE
        # v3.1: write the report now too (the last v3 run died in the assembly stage and lost everything)
        tail = leg_sweeps() + joint_limits()[0] + BODY_NOTES + V31_NOTES
        open(REPORT, 'w', encoding='utf-8').write('\n'.join(rows + ['(assembly stage not finished yet)'] + tail))
        gdi = gdi_objects(sw)
        print(f'GDI objects after the parts stage: {gdi}', flush=True)
        if gdi > GDI_ASSEMBLY_LIMIT:
            rows.append(f'ASSEMBLY: postponed - SOLIDWORKS holds {gdi} GDI objects after the parts stage (Windows stops a '
                        f'process at 10000); restart SOLIDWORKS and run build_print_parts_v3_1.py --assembly-only')
        else:
            try:
                n, n_see = build_assembly(sw, paths, boxes)
                rows.append(f'ASSEMBLY: {n} of {len(paths)} files inserted, each checked to sit at its modelled position '
                            f'(inside picture: {n_see} shells made see-through; GDI objects at the end {gdi_objects(sw)})')
                rows.append('SECTION PICTURES (exploded; labels anchored on each part\'s own pixels):')
                rows += SECTION_ROWS
            except Exception as ex:
                rows.append(f'ERR assembly {ex}')
        contact_sheet([n for n, _ in PRINTED])
        rows += tail
    else:
        rows += leg_sweeps() + joint_limits()[0] + BODY_NOTES + V31_NOTES
    for t in open_titles(sw):          # close only what this run opened (the assembly and the parts it loaded)
        if t not in before:
            try:
                sw.CloseDoc(t)
            except Exception:
                pass
    print('\n'.join(rows))
    if not only:
        open(REPORT, 'w', encoding='utf-8').write('\n'.join(rows))
    return rows


STRONG_PARTS = ('Thigh_', 'Shin_')     # leg halves: servo tab, horn and cover screws go into thick slabs
PRINT_LIMIT_G = 400.0                   # brief: printed mass <= 400 g (the AU$350 budget depends on it)
PROFILE = {'mixed': True}               # set by profile_rows: True = leg outer halves 3 walls, the rest 2


def chosen_grams(short, p3, p2, mixed=None):
    """Grams of one part under the chosen profile (p3 / p2 = its 3-wall / 2-wall estimates)."""
    mixed = PROFILE['mixed'] if mixed is None else mixed
    return p3 if (mixed and short.startswith(STRONG_PARTS) and short.endswith('_Outer')) else p2


def profile_rows(report_rows):
    """v3.1: choose the slicer profile from the per-part estimates in the report rows (3 walls and 2 walls each).
    Every shell is designed at 1.6 mm (4 lines of 0.4), so 2 walls print it solid; 3 walls only add grams where a
    part is thicker. Preferred: 2 walls, with the leg OUTER halves at 3 walls (their pilots sit in 5-10 mm
    slabs) - if that keeps the total under PRINT_LIMIT_G with a 10 g margin; otherwise 2 walls for everything."""
    import re
    parts = []
    for r in report_rows:
        m = re.match(r'OK  (\S+)\s.*?([\d.]+) g printed \(fill [\d.]+, bed axis \w; 2 walls ([\d.]+) g\)', r)
        if m and not m.group(1).startswith(('Coupon_', 'Fit_Test')):
            parts.append((m.group(1), float(m.group(2)), float(m.group(3))))
    if not parts:
        return ['PROFILE: no per-part rows found']
    all3 = sum(p3 for _, p3, _ in parts)
    all2 = sum(p2 for _, _, p2 in parts)
    mixed = sum(chosen_grams(s, p3, p2, True) for s, p3, p2 in parts)
    use_mixed = mixed <= PRINT_LIMIT_G - 10.0
    PROFILE['mixed'] = use_mixed
    rows = ['SLICER PROFILE (grams as printed, all 55 robot parts, from the exported STLs):',
            f'  3 walls everywhere: {all3:.1f} g | 2 walls everywhere: {all2:.1f} g | 2 walls + 3 walls on the 8 leg '
            f'outer halves: {mixed:.1f} g',
            f'  CHOSEN: {"2 walls, leg outer halves 3 walls" if use_mixed else "2 walls for every part"} -> '
            f'{mixed if use_mixed else all2:.1f} g (limit {PRINT_LIMIT_G:.0f} g); 0.8 mm top/bottom, 15 % gyroid, '
            f'0.2 mm layers, 0.4 mm lines. Skirts, brims and supports come on top (about 1-3 %).']
    return rows


def main_profile():
    """v3.1: append / refresh the SLICER PROFILE section of an existing report (no SOLIDWORKS needed)."""
    old = open(REPORT, encoding='utf-8').read().split('\n')
    old = [r for r in old if not r.startswith(('SLICER PROFILE', '  3 walls everywhere', '  CHOSEN:'))]
    k = next((i for i, r in enumerate(old) if r.startswith('CLASH CHECK')), len(old))
    rows = profile_rows(old)
    open(REPORT, 'w', encoding='utf-8').write('\n'.join(old[:k] + rows + old[k:]))
    print('\n'.join(rows))


def main_assembly_only():
    """v3.1 recovery: rebuild ONLY the assembly, its pictures and the section pictures from the parts already saved
    in print_v3_1\\ (e.g. after the assembly stage crashed), then replace the report's assembly section."""
    sw = swlib.app()
    before = open_titles(sw)
    if before:
        raise SystemExit(f'SolidWorks has documents open that this script did not create: {before} - close them first')
    paths = [os.path.join(OUT, n + '.SLDPRT') for n, _ in PRINTED if not any(k in n for k in NOT_IN_ROBOT)]
    paths.append(os.path.join(OUT, BOUGHT_NAME + '.SLDPRT'))
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise SystemExit(f'missing parts: {missing}')
    rows = []
    try:
        n, n_see = build_assembly(sw, paths, {})
        rows.append(f'ASSEMBLY: {n} of {len(paths)} files inserted, each checked to sit at its modelled position '
                    f'(assembly-only rerun in a fresh SOLIDWORKS; inside picture: {n_see} shells made see-through; '
                    f'GDI objects at the end {gdi_objects(sw)})')
        rows.append('SECTION PICTURES (exploded; labels anchored on each part\'s own pixels):')
        rows += SECTION_ROWS
    except Exception as ex:
        rows.append(f'ERR assembly {ex}')
    contact_sheet([n for n, _ in PRINTED])
    for t in open_titles(sw):
        if t not in before:
            try:
                sw.CloseDoc(t)
            except Exception:
                pass
    old = open(REPORT, encoding='utf-8').read().split('\n') if os.path.exists(REPORT) else []
    old = [r for r in old if not r.startswith(('ASSEMBLY:', 'SECTION PICTURES', '  section ', '  ERR section', 'ERR assembly',
                                                '(assembly stage not finished yet)'))]
    k = next((i for i, r in enumerate(old) if r.startswith('LEG CLEARANCE SWEEPS')), len(old))
    open(REPORT, 'w', encoding='utf-8').write('\n'.join(old[:k] + rows + old[k:]))
    print('\n'.join(rows))
    return rows


if __name__ == '__main__':
    if sys.argv[1:] == ['--assembly-only']:
        main_assembly_only()
    elif sys.argv[1:] == ['--profile']:
        main_profile()
    elif sys.argv[1:] == ['--sections']:
        main_sections()
    else:
        main([a for a in sys.argv[1:]] or None)
