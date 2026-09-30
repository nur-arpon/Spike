"""Desk Buddy robot dog - printable parts VERSION 2 (built to fit the real bought parts).

Every part is modelled in ONE global frame (mm): X = the robot's left (+) / right (-), Y = up, Z = forward,
origin at the centre of the torso's bottom face. So the assembly needs no mates: every file is inserted at
the origin and lands in its real place, and every clash can be checked body against body.

Output (owner's folder rule):
    print_v2\\        SolidWorks only  - printed parts, the bought-parts model, the assembly
    print_v2_png\\    pictures
    print_v2_stl\\    STL files for the printer (each one checked against the model after export)

Printed file names: "Printed part (bought parts it holds)".

Where a bought part has no published drawing (clone boards), its mount is ADJUSTABLE rather than tight:
slotted pilots, oversized bays with fences, foam-tape pads. Every such number is in the MEASURE table below -
caliper the real part, change the number, re-run this script, then print.

The build report (build_v2_report.txt) checks: one piece per printed part, fits the printer, STL = model,
no solid overlaps anywhere (printed vs bought, bought vs bought), every assembly part in its place, and the
robot's centre of mass against its wheel contacts (can it lift each foot without tipping).
"""
import os, math, pythoncom, swlib
from win32com.client import VARIANT, Dispatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'print_v2')
PNG = os.path.join(HERE, 'print_v2_png')
STL = os.path.join(HERE, 'print_v2_stl')

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
FILL = 0.75      # printed mass / solid mass (2.4 mm walls, 4 perimeters, 20 % infill)

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
HORN_OUT = 1.0     # horn outer face above the spline top   [~0.5-1.5, unpublished]
HORN_T = 1.8       # horn arm thickness (pocket depth)      [~1.5-2.0, unpublished]
HORN_W = 6.6       # horn arm pocket width                  [arm 5-6.5 wide at the hub]
HORN_REACH = 17.5  # double-arm horn: centre to tip         [~16-17.5]
CROSS_REACH = 11.5 # cross horn: centre to tip              [~10-11.5]
HORN_HUB_R = 4.6   # recess for the horn hub
SCREEN_STACK = 4.5 # Guition glass front -> PCB front       [~4-5, unpublished]
KCD1_X, KCD1_Z = 19.4, 13.0   # rocker cut-out for a 2-3 mm panel (datasheet)
OR_GROOVE_R = 11.75           # wheel groove bottom radius for the 22 mm ID O-ring (+6.8 % stretch)
OR_CS = 2.4                   # O-ring cross-section [2.0-2.65, unpublished]
CAM_L, CAM_H = 57.0, 28.0     # ESP32-S3 CAM board incl. the antenna overhang [57 x 28; PCB alone 51 x 29]
CAM_LENS_X = 16.0             # lens centre from the board's antenna end (camera folded onto the WROOM)
CAM_LENS_Y = 14.0             # lens centre above the board's bottom long edge
CAM_STACK = 10.6              # board front face -> lens-holder front face (WROOM 3.1 + tape 1 + camera ~6.5)

# ---------------------------------------------------------------------------------------------
# LAYOUT
TX, TZ = 42.0, 80.0          # torso half-width, half-length (outer)
TUB_H, LID_TOP = 36.0, 50.0  # tub top, lid top
LIP_Y0 = 31.2                # bottom of the lid's locating lip (clears the PCA9685 standoffs)
LID_SCREW_Y = 32.5           # lid screws through the tub's front and rear walls
HIP_Y = 18.0                 # hip axis height
# legs: hip |z| and which way the servo case runs from its shaft (-1 = toward -Z). The front hips sit well
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
THIGH_OUT = THIGH_IN + 4.0                               # 59.6
KNEE_SPLINE = THIGH_IN - SV_TAB_T + SV_SPLINE            # 67.2
SHIN_IN = KNEE_SPLINE + PLATE_GAP                        # 66.4
SHIN_OUT = SHIN_IN + 4.0                                 # 70.4
WHEEL_SPLINE = SHIN_IN - SV_TAB_T + SV_SPLINE            # 78.0
WHEEL_IN = WHEEL_SPLINE + PLATE_GAP                      # 77.2
WHEEL_OUT = WHEEL_IN + 8.0                               # 85.2
TYRE_R = OR_GROOVE_R + 2 * OR_CS                         # 16.55 max; stretched ring ~14.15 (used below)

HEAD = dict(x=63.0, y0=60.0, y1=158.0, z0=36.0, z1=80.0)   # 11 mm above the screen for its top-edge plugs (P7 Speak)
BOARD_Y0 = HEAD['y0'] + W + 12.0                # 74.4  Guition board bottom (12 mm plug zone below)
GLASS_Z = HEAD['z1'] - W                        # 77.6  glass front (touches the front wall)
PCB_FRONT = GLASS_Z - SCREEN_STACK              # 73.1
BACK_SCREW_Z = HEAD['z0'] + W + CBORE_R + 0.8   # 41.5: head back-cover screws (counterbore clears the rear edge)
MIC_Y, MIC_Z = 126.0, 52.0                      # below the screen's top ears so the board slides past the rings
NECK = dict(x=20.0, z0=46.0, z1=74.0)
LID_NECK_SCREWS = [(sx * 15.0, z) for sx in (-1, 1) for z in (50.5, 69.5)]   # driven up from inside the lid
HEAD_NECK_SCREWS = [(sx * 6.0, z) for sx in (-1, 1) for z in (50.0, 70.0)]   # driven down from inside the head

# muzzle: shallow and low so it hides as little of the screen as possible from above; the camera board
# stands upright behind the front wall with the camera folded onto its WROOM module.
MUZ = dict(x=38.0, y0=40.0, y1=74.0, z0=80.0, z1=97.5)
MUZ_FZ = MUZ['z1'] - W                          # 95.1 front wall inner face
CAM_PCB_Z = MUZ_FZ - CAM_STACK                  # 84.5 board front face
CAM_Y0 = MUZ['y0'] + W                          # 42.4 board stands on the muzzle floor
LENS_X = -CAM_L / 2 + CAM_LENS_X                # -12.5 (antenna end at -X, USB-C end at +X)
LENS_Y = CAM_Y0 + CAM_LENS_Y                    # 56.4
MUZ_SCREWS = [(sx * 33.0, y) for sx in (-1, 1) for y in (64.0, 70.0)]

TAIL_Z = -62.0                                  # tail servo shaft (case runs forward from it)
TAIL_Y0 = LID_TOP + SV_SPLINE + PLATE_GAP       # 63.6 tail underside

BAT_Z = (-52.0, 24.0)                           # 2x18650 holder (76 long)
CLAMP_Z = (-40.0, -30.0)                        # battery clamp bar
KCD1_ZC = -65.0                                 # belly switch
PROT_Z = (28.0, 48.1)                           # protection board, lying across the floor (48.4 along X)
CLIFF_TILT = 25.0                               # desk-edge lasers look this far ahead of straight down
CLIFF_FRONT_X = (7.5, 32.5)                     # |x| of each front desk-edge board (25 long)
CLIFF_FRONT_Z = 58.0                            # low edge of the front incline
CLIFF_REAR_X = (-35.5, -10.5)
CLIFF_REAR_Z = -58.0


def rng(a, b):
    return (min(a, b), max(a, b))


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
        """Servo horn seat in a plate normal to X whose inner (servo-side) face is at |x| = x_in.
        Pocket the horn arm drops into, hub recess, a hole for the horn screw and screwdriver, and slots the
        arm screws bite into (fit the horn to the plate FIRST, screws from the horn side, then onto the spline)."""
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

    def pad_boss(self, x, z, ceiling, down=True):
        """Boss hanging from a ceiling (underside at y=ceiling) for a foil touch pad: an M2 x 6 clamps the foil
        tab and the folded wire end. Blind pilot, 0.8 mm skin left on the outside."""
        self.CY(x, z, BOSS_R, (ceiling - 3, ceiling))
        self.CY(x, z, PILOT_R, (ceiling - 3.5, ceiling + W - 0.8), cut=True)


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
# PRINTED PARTS
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


def thigh(p, sx, sz):
    hz, dz = LEGS[sz]
    zc = hz + dz * BODY_C
    xr = (sx * THIGH_IN, sx * THIGH_OUT)
    p.CX(HIP_Y, hz, 9.0, xr)
    p.B(xr, (-12, HIP_Y + 19), (hz - 6, hz + 6))
    p.B(xr, (KNEE_Y - 11, KNEE_Y + 11), (zc - 19.5, zc + 19.5))
    p.horn_seat_x(HIP_Y, hz, sx, THIGH_IN, 4.0, ('up', 'down'), HORN_REACH)
    p.servo_slot_x(KNEE_Y, hz, dz, (sx * (THIGH_IN - 1), sx * (THIGH_OUT + 1)))


def shin(p, sx, sz):
    hz, dz = LEGS[sz]
    zc = hz + dz * BODY_C
    xr = (sx * SHIN_IN, sx * SHIN_OUT)
    yb = AXLE_Y - 8.5                                   # 2 mm web under the servo opening
    p.CX(KNEE_Y, hz, 9.0, xr)
    p.B(xr, (AXLE_Y + 9, KNEE_Y + 19), (hz - 6, hz + 6))
    p.B(xr, (yb, AXLE_Y + 10), (zc - 19.5, zc + 19.5))
    for ze, s in ((zc + 19.5, 1), (zc - 19.5, -1)):   # 6 mm chamfers so the shin clears the desk when tilted
        p.poly_x([(ze + s, yb - 1), (ze - s * 7, yb - 1), (ze + s, yb + 7)], sx * (SHIN_IN - 1), sx * (SHIN_OUT + 1), cut=True)
    p.horn_seat_x(KNEE_Y, hz, sx, SHIN_IN, 4.0, ('up', 'down'), HORN_REACH)
    p.servo_slot_x(AXLE_Y, hz, dz, (sx * (SHIN_IN - 1), sx * (SHIN_OUT + 1)))


def wheel(p, sx, sz):
    z = LEGS[sz][0]
    g0, g1 = WHEEL_IN + (8 - (OR_CS + 0.2)) / 2, WHEEL_IN + (8 + OR_CS + 0.2) / 2
    p.CX(AXLE_Y, z, OR_GROOVE_R + OR_CS / 2 + 0.25, (sx * WHEEL_IN, sx * WHEEL_OUT))   # rim r 13.2
    p.CX(AXLE_Y, z, 20, (sx * g0, sx * g1), cut=True)
    p.CX(AXLE_Y, z, OR_GROOVE_R, (sx * g0, sx * g1))
    p.horn_seat_x(AXLE_Y, z, sx, WHEEL_IN, 8.0, ('up', 'down', 'fwd', 'back'), CROSS_REACH)


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
    # wheel groove sample (fit the 22 mm O-ring)
    gy0, gy1 = W + (8 - OR_CS - 0.2) / 2, W + (8 + OR_CS + 0.2) / 2
    p.CY(ox + 78, 22, OR_GROOVE_R + OR_CS / 2 + 0.25, (W, W + 8))
    p.CY(ox + 78, 22, 20, (gy0, gy1), cut=True)
    p.CY(ox + 78, 22, OR_GROOVE_R, (gy0, gy1))
    # horn pocket sample in a 4 mm pad (same as the thighs) - screw a real horn in from the horn side
    p.B((ox + 2, ox + 40), (W, W + 4), (44, 58))
    p.horn_seat_y(ox + 21, 51, W + 4, -1, 4, ('left', 'right'), HORN_REACH)


# =============================================================================================
# BOUGHT PARTS (one multibody part, every body named after what you are buying)
# =============================================================================================
def servo_x(p, name, sx, y, shaft_z, dz, tab_face, hip=False, arms=('up', 'down'), reach=HORN_REACH):
    """MG90S with its shaft along X pointing away from the robot's centre line, horn fitted."""
    under = tab_face if hip else tab_face - SV_TAB_T     # hip: tab underside on the wall; legs: tab top on the plate
    zc = shaft_z + dz * BODY_C
    z0, z1 = zc - SV_L / 2, zc + SV_L / 2
    bottom, flat_top = under - SV_UNDER, under - SV_UNDER + 22.8
    spline_top = under + SV_SPLINE
    n = name + ' - '
    p.B((sx * bottom, sx * flat_top), (y - SV_W / 2, y + SV_W / 2), (z0, z1)); p.name_body(n + 'MG90S case')
    p.B((sx * under, sx * (under + SV_TAB_T)), (y - SV_W / 2, y + SV_W / 2), (zc - SV_TABS / 2, z0 - 0.01)); p.name_body(n + 'MG90S tab A')
    p.B((sx * under, sx * (under + SV_TAB_T)), (y - SV_W / 2, y + SV_W / 2), (z1 + 0.01, zc + SV_TABS / 2)); p.name_body(n + 'MG90S tab B')
    p.CX(y, shaft_z, 5.9, (sx * (flat_top + 0.01), sx * (spline_top - 4.1))); p.name_body(n + 'MG90S turret')
    p.CX(y, shaft_z, 2.45, (sx * (spline_top - 4.1 + 0.01), sx * spline_top)); p.name_body(n + 'MG90S spline')
    arm0, arm1 = spline_top + HORN_OUT - HORN_T, spline_top + HORN_OUT
    p.CX(y, shaft_z, 3.8, (sx * (spline_top - 3.5), sx * (arm0 - 0.01))); p.name_body(n + 'horn hub')
    r = reach - 0.5
    if 'up' in arms:
        p.B((sx * arm0, sx * arm1), (y - r, y + r), (shaft_z - (HORN_W - 0.4) / 2, shaft_z + (HORN_W - 0.4) / 2)); p.name_body(n + 'horn arms')
    if 'fwd' in arms:
        p.B((sx * arm0, sx * arm1), (y - (HORN_W - 0.4) / 2, y + (HORN_W - 0.4) / 2), (shaft_z - r, shaft_z + r)); p.name_body(n + 'horn arms 2')


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
    p.B((5.1, 25.5), (55.9, 71.3), (MUZ_FZ - 2.5, MUZ_FZ - 0.01)); p.name_body('APDS-9960 gesture')
    ix = HEAD['x'] - W
    for sx, nm in ((-1, 'right'), (1, 'left')):
        p.CX(MIC_Y, MIC_Z, 7.0, (sx * (ix - 1.2), sx * (ix - 0.01))); p.name_body('MS3625 mic ' + nm)
    p.B((-44, -16), (80, 111), (HEAD['z0'] + W + 0.1, HEAD['z0'] + W + 15)); p.name_body('Cavity speaker 3W')
    p.B((-20.5, 20.5), (W, W + 19.35), BAT_Z); p.name_body('2x18650 holder + 2x Samsung 35E')
    p.B((-24.2, 24.2), (W + 1, W + 5), PROT_Z); p.name_body('2S 20A protection board')
    p.B((-22.5, 22.5), (W + 5.5, W + 17.5), (31, 45)); p.name_body('Mini blade fuse holder')
    p.B((21.3, 39.3), (4.4, 11.3), (-77.5, -46.5)); p.name_body('Type-C 2S charging board')
    p.B((-10.5, 10.5), (-2, 0), (KCD1_ZC - 7.5, KCD1_ZC + 7.5)); p.name_body('KCD1 switch - bezel')
    p.B((-9.5, 9.5), (0.01, 14), (KCD1_ZC - 6.3, KCD1_ZC + 6.3)); p.name_body('KCD1 switch - body')
    p.B((-4, 4), (14.01, 22.8), (KCD1_ZC - 4, KCD1_ZC + 4)); p.name_body('KCD1 switch - terminals')
    for sx in (-1, 1):
        s = 'left' if sx > 0 else 'right'
        p.B((sx * 32, sx * 33.6), (5.6, 31), (-31.1, 31.1)); p.name_body('PCA9685 servo board ' + s)
        p.B((sx * 23.5, sx * 31.99), (22.6, 30.2), (-23, 23)); p.name_body('PCA9685 headers ' + s)
        p.B((sx * 33.61, sx * 37.8), (22.6, 30.2), (-23, 23)); p.name_body('PCA9685 solder tails ' + s)
        p.B((sx * 9.5, sx * 23.49), (22.6, 30.2), (-23, 23)); p.name_body('Servo plugs ' + s)
        p.B((sx * 32.9, sx * 36.8), (35.7, 47.5), (-12.5, 12.5)); p.name_body('VL53L0X side laser ' + s)
    for x0, x1, zlow, dirz, nm in [(7.5, 32.5, CLIFF_FRONT_Z, 1, 'front desk-edge left'),
                                   (-32.5, -7.5, CLIFF_FRONT_Z, 1, 'front desk-edge right'),
                                   (CLIFF_REAR_X[0], CLIFF_REAR_X[1], CLIFF_REAR_Z, -1, 'rear desk-edge')]:
        _, board, _, _ = cliff_geom(zlow, dirz)
        p.poly_x(board, x0 + 0.01, x1 - 0.01); p.name_body('VL53L0X ' + nm)
    for sz, nm in ((1, 'front'), (-1, 'rear')):
        p.poly_x(laser_board_pts(sz), -12.5, 12.5); p.name_body(f'VL53L0X {nm} obstacle laser')
    p.B((-8.2, 8.2), (44.2, 47.5), (4.2, 25.4)); p.name_body('MPU6050 IMU')
    p.B((16.3, 31.3), (44.2, 47.5), (16.6, 46.9)); p.name_body('MPR121 touch')
    p.B((-25, 25), (33, 46.6), (-37.3, -1.7)); p.name_body('Perfboard hub (2x Mini560, caps, resistors)')
    # servos
    for sx in (-1, 1):
        for sz in (-1, 1):
            hz, dz = LEGS[sz]
            leg = ('F' if sz > 0 else 'B') + ('L' if sx > 0 else 'R')
            servo_x(p, 'Hip ' + leg, sx, HIP_Y, hz, dz, TX, hip=True)
            servo_x(p, 'Knee ' + leg, sx, KNEE_Y, hz, dz, THIGH_IN)
            servo_x(p, 'Wheel ' + leg + ' (360)', sx, AXLE_Y, hz, dz, SHIN_IN, arms=('up', 'fwd'), reach=CROSS_REACH)
    # tail servo: shaft up, tabs on the lid top, case forward of the shaft
    zc = TAIL_Z + BODY_C
    under = LID_TOP
    p.B((-SV_W / 2, SV_W / 2), (under - SV_UNDER, under - SV_UNDER + 22.8), (zc - SV_L / 2, zc + SV_L / 2)); p.name_body('Tail - MG90S case')
    p.B((-SV_W / 2, SV_W / 2), (under, under + SV_TAB_T), (zc - SV_TABS / 2, zc - SV_L / 2 - 0.01)); p.name_body('Tail - MG90S tab A')
    p.B((-SV_W / 2, SV_W / 2), (under, under + SV_TAB_T), (zc + SV_L / 2 + 0.01, zc + SV_TABS / 2)); p.name_body('Tail - MG90S tab B')
    st = under + SV_SPLINE
    p.CY(0, TAIL_Z, 5.9, (under - SV_UNDER + 22.81, st - 4.1)); p.name_body('Tail - MG90S turret')
    p.CY(0, TAIL_Z, 2.45, (st - 4.09, st)); p.name_body('Tail - MG90S spline')
    p.CY(0, TAIL_Z, 3.8, (st - 3.5, TAIL_Y0 - 0.01)); p.name_body('Tail - horn hub')
    p.B((-(HORN_W - 0.4) / 2, (HORN_W - 0.4) / 2), (TAIL_Y0, TAIL_Y0 + HORN_T), (TAIL_Z - HORN_REACH + 0.5, TAIL_Z + HORN_REACH - 0.5)); p.name_body('Tail - horn arms')


# masses (g) of the bought bodies, by name prefix - used only for the balance check
MASS = [('Guition 4.3in screen - PCB', 45), ('Guition 4.3in screen - glass', 55), ('Guition 4.3in screen - back', 30),
        ('ESP32-S3 CAM board - PCB', 8), ('ESP32-S3 CAM board - WROOM', 3), ('ESP32-S3 CAM board - microSD', 0.5),
        ('OV5640 camera - module', 3), ('OV5640 camera - lens', 0.5), ('APDS-9960', 2), ('VL53L0X', 1.2),
        ('MS3625', 1), ('Cavity speaker', 10), ('2x18650', 104), ('2S 20A protection', 5), ('Mini blade fuse', 6),
        ('Type-C 2S charging', 5), ('KCD1 switch - body', 3), ('KCD1', 0), ('PCA9685 servo board', 9),
        ('PCA9685', 0), ('Servo plugs', 3), ('MPU6050', 2), ('MPR121', 2), ('Perfboard hub', 22),
        ('MG90S case', 13.4), ('horn arms', 0.6), ('horn hub', 0.4), ('MG90S', 0)]
WIRES = ('wiring and solder (estimate)', 30.0, (0.0, 20.0, 0.0))


def bought_mass(name):
    for key, g in MASS:
        if key in name:
            return g
    return 0.0


# =============================================================================================
PRINTED = [
    ('Torso_Bottom (18650 holder, 4 hip MG90S, 2 PCA9685, protection board, fuse holder, USB-C charger, KCD1, 5 VL53L0X)', torso_bottom),
    ('Battery_Clamp (holds the 18650 holder down)', battery_clamp),
    ('Torso_Lid (MPU6050, MPR121, perfboard hub with 2 Mini560, tail MG90S, 2 side VL53L0X, touch pads)', torso_lid),
    ('Neck (cables only)', neck),
    ('Head_Front (Guition 4.3in screen, 2 MS3625 mics, touch pad)', head_front),
    ('Head_Back (cavity speaker)', head_back),
    ('Screen_Washers (4 washers under the Guition screen screws)', screen_washers),
    ('Muzzle (ESP32-S3 CAM, OV5640 camera, APDS-9960)', muzzle),
    ('Ear_Left (decorative)', lambda p: ear(p, 1)),
    ('Ear_Right (decorative)', lambda p: ear(p, -1)),
    ('Tail (tail MG90S horn)', tail),
]
for sx, sn in ((1, 'Left'), (-1, 'Right')):
    for sz, fn in ((1, 'Front'), (-1, 'Back')):
        PRINTED.append((f'Thigh_{fn}{sn} (knee MG90S, hip servo horn)', lambda p, a=sx, b=sz: thigh(p, a, b)))
        PRINTED.append((f'Shin_{fn}{sn} (wheel MG90S 360, knee servo horn)', lambda p, a=sx, b=sz: shin(p, a, b)))
        PRINTED.append((f'Wheel_{fn}{sn} (wheel servo cross horn, 22 mm O-ring tyre)', lambda p, a=sx, b=sz: wheel(p, a, b)))
PRINTED.append(('Fit_Test_Coupon (print first - servo slot, switch, screen boss, windows, O-ring groove, horn pocket)', fit_coupon))
EXPECTED_BODIES = {'Screen_Washers': 4}
BOUGHT_NAME = 'BOUGHT - every purchased part in place'
ASM_NAME = 'Desk Buddy v2 - full assembly'


def _v():
    return VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)


def save_part(p, stl=True):
    p.m.SketchManager.AddToDB = False
    p.m.ClearSelection2(True)
    path = os.path.join(OUT, p.name + '.SLDPRT')
    p.m.Extension.SaveAs3(path, 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    p.m.ShowNamedView2('*Isometric', 7); p.m.ViewZoomtofit2(); p.m.ClearSelection2(True)
    p.m.Extension.SaveAs3(os.path.join(PNG, p.name + '.png'), 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    if stl:
        sp = os.path.join(STL, p.name + '.STL')
        p.m.ClearSelection2(True)
        p.m.Extension.SaveAs3(sp, 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
        swlib.check_stl(sp, p.bbox_mm())
    return path


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
    Bodies of the same bought item (servo case + its own tabs/horn) are not compared with each other."""
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
    rows = [f'BALANCE: total {M:.0f} g, centre of mass x {c[0]:+.1f}  y {c[1]:.1f} ({c[1] - (AXLE_Y - 14.15):.0f} mm above the desk)  '
            f'z {c[2]:+.1f} mm (feet at z {LEGS[1][0]:+.0f} / {LEGS[-1][0]:+.0f})',
            f'  on 4 wheels: {margin([feet[k] for k in order]):.1f} mm inside the support area']
    for lift in order:
        tri = [feet[k] for k in order if k != lift]
        nm = ('front ' if lift[1] > 0 else 'rear ') + ('left' if lift[0] > 0 else 'right')
        rows.append(f'  lift {nm:11s} foot: {margin(tri):+6.1f} mm')
    return rows


def build_assembly(sw, paths, boxes):
    asm = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    title = asm.GetTitle
    mu = sw.GetMathUtility
    mu._FlagAsMethod('CreateTransform')
    ident = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, [1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0, 1.0, 0, 0, 0])
    added = 0
    for pth in paths:
        sw.OpenDoc6(pth, 1, 1, '', _v(), _v())
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
    for view, tag in (('*Isometric', 'iso'), ('*Front', 'front'), ('*Right', 'side'), ('*Top', 'top')):
        asm.ShowNamedView2(view, -1); asm.ViewZoomtofit2(); asm.ClearSelection2(True)
        asm.Extension.SaveAs3(os.path.join(PNG, f'{ASM_NAME} - {tag}.png'), 0, 1, swlib.NOTHING, swlib.NOTHING, _v(), _v())
    return added


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
    cw, ch, cols = 420, 340, 5
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


def main():
    for d in (OUT, PNG, STL):
        os.makedirs(d, exist_ok=True)
    sw = swlib.app()
    sw.CloseAllDocuments(True)
    swlib.probe(sw); swlib.probe_axes(sw)
    rows, paths, items, total_g, boxes, masses = [], [], [], 0.0, {}, [WIRES]
    for name, build in PRINTED:
        p = P(sw, name)
        short = name.split(' (')[0]
        try:
            build(p)
            nb = len(p.m.GetBodies2(0, True))
            want = EXPECTED_BODIES.get(short, 1)
            bb = p.bbox_mm()
            size = sorted((bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]), reverse=True)
            grams = p.volume_cm3() * PLA
            path = save_part(p)
            if not name.startswith('Fit_Test'):                  # the coupon is not part of the robot
                paths.append(path)
                boxes[path] = bb
                got = copies(p.m, short)
                items += got
                masses += [(short, vol * PLA * FILL, cen) for _, _, _, cen, vol in got]
                total_g += grams
            fits = size[0] <= 223 and size[1] <= 220 and size[2] <= 205
            rows.append(f'OK  {short:18s} {size[0]:6.1f} x {size[1]:5.1f} x {size[2]:5.1f} mm  {grams:6.1f} g solid  '
                        f'bodies={nb}{"" if nb == want else "  <-- WRONG PIECE COUNT"}{"" if fits else "  <-- TOO BIG FOR THE PRINTER"}')
        except Exception as ex:
            rows.append(f'ERR {short:18s} {ex}')
        sw.CloseDoc(p.m.GetTitle)
    rows.append(f'    printed total {total_g:.0f} g solid, about {total_g * FILL:.0f} g as printed')
    p = P(sw, BOUGHT_NAME)
    try:
        bought(p)
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
    rows += balance(masses)
    try:
        n = build_assembly(sw, paths, boxes)
        rows.append(f'ASSEMBLY: {n} of {len(paths)} files inserted, each checked to sit at its modelled position')
    except Exception as ex:
        rows.append(f'ERR assembly {ex}')
    contact_sheet([n for n, _ in PRINTED])
    sw.CloseAllDocuments(True)
    print('\n'.join(rows))
    open(os.path.join(HERE, 'build_v2_report.txt'), 'w', encoding='utf-8').write('\n'.join(rows))


if __name__ == '__main__':
    main()
