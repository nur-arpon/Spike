"""Desk Buddy robot dog - printable parts, version 1 (test-fit prints).

Each part is its own SLDPRT + STL + PNG in print_v1/. Millimetres, 2 mm walls.
Printer limit checked against the Ultimaker 2+ Connect at Deer Park Library (223 x 220 x 205 mm).

Servo = MG90S: body 22.8 x 12.2 mm, shaft 5.9 mm from one end, mounting-tab holes 2.4 mm
beyond each end of the body. M2 self-tapping screws go into 1.8 mm pilot holes.
"""
import os, swlib

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'print_v1')
PLA_DENSITY = 1.24                     # g/cm3
PRICE_PER_10G = 1.10                   # Brimbank Maker Space material charge
BED = (223, 220, 205)
PILOT = 0.9                            # radius of an M2 self-tap pilot hole (1.8 mm)

# servo pocket (12.2 x 22.8 body + 0.2 clearance each side)
SV_W, SV_L, SV_SHAFT = 12.6, 23.2, 5.9


def torso_bottom(p):
    p.box(-40, 40, 0, 34, -85, 85)                              # tub
    p.box(-38, 38, 2, 40, -83, 83, cut=True)                    # hollow, open top
    for zh, inward in ((54, -1), (-68, 1)):                     # hip servo slots, both sides at once
        z_near = zh - SV_SHAFT if inward > 0 else zh + SV_SHAFT
        z_far = z_near + inward * SV_L
        z0, z1 = sorted((z_near, z_far))
        p.box_x(19 - SV_W / 2, 19 + SV_W / 2, z0 - 0.2, z1 + 0.2, -45, 45, cut=True)
        for zt in (z0 - 2.4, z1 + 2.4):                          # tab screw pilots
            p.cyl_x(19, zt, PILOT, -45, 45, cut=True)
    p.box_x(21, 27, -11, -1, -45, 45, cut=True)                 # side laser windows (L + R)
    p.box(-5, 5, 8, 14, -90, -80, cut=True)                     # rear laser window
    p.box(18, 28, 6, 11, -90, -80, cut=True)                    # USB-C charging slot
    p.box(-33, -14, 9, 22, -90, -80, cut=True)                  # KCD1 switch cut-out (19 x 13)
    for x0 in (-36, 24):                                        # front desk-edge laser windows (floor)
        p.box(x0, x0 + 12, -1, 3, 62, 72, cut=True)
    p.box(-30, -18, -1, 3, -80, -70, cut=True)                  # rear desk-edge laser window
    for z in (-30, 30):                                         # lid screws (through the lid's lip)
        p.cyl_x(30, z, PILOT, -45, 45, cut=True)


def torso_lid(p):
    p.box(-40, 40, 34, 46, -85, 85)
    p.box(-38, 38, 30, 44, -83, 83, cut=True)                   # hollow, open bottom
    p.box(-37.6, 37.6, 28, 44.5, -82.6, 82.6)                   # lip that drops inside the tub
    p.box(-35.6, 35.6, 27, 44, -80.6, 80.6, cut=True)
    p.box(-15, 15, 40, 50, 50, 74, cut=True)                    # cable hole under the neck
    p.box(-4, 4, 40, 50, -74, -66, cut=True)                    # tail servo shaft
    for z in (-30, 30):
        p.cyl_x(30, z, PILOT + 0.2, -45, 45, cut=True)          # clearance holes for lid screws


def neck(p):
    p.box(-23, 23, 0, 46, -17, 17)
    p.box(-21, 21, -1, 47, -15, 15, cut=True)                   # open tube: glue top and bottom


def head_front(p):
    p.box(-61, 61, 0, 88, 0, 54)
    p.box(-59, 59, 2, 86, -1, 52, cut=True)                     # hollow, open back
    p.box(-48.5, 48.5, 14, 70, 50, 60, cut=True)                # screen window (visible area)
    p.cyl_z(0, 79, 4.5, 50, 60, cut=True)                       # camera lens
    p.box(28, 40, 76, 82, 50, 60, cut=True)                     # gesture sensor window
    p.cyl_x(52, 27, 1.2, -65, 65, cut=True)                     # mic pinholes, both ears
    for y in (20, 28, 36):                                      # speaker grille, right cheek
        for z in (16, 24, 32):
            p.cyl_x(y, z, 1.5, 55, 65, cut=True)
    p.box(-15, 15, -1, 3, 12, 42, cut=True)                     # cable hole to the neck
    for y in (20, 68):
        p.cyl_x(y, 5, PILOT + 0.2, -65, 65, cut=True)           # back-cover screws


def head_back(p):
    p.box(-61, 61, 0, 88, -2, 0)                                # back plate
    p.box(-58.6, 58.6, 2.4, 85.6, -0.5, 9)                      # lip that fits inside the head
    p.box(-56.6, 56.6, 4.4, 83.6, 0, 10, cut=True)
    p.box(-7, 7, 20, 28, -3, 1, cut=True)                       # USB access for re-flashing the brain
    for y in (20, 68):
        p.cyl_x(y, 5, PILOT, -65, 65, cut=True)


def muzzle(p):
    p.box(-25, 25, 0, 24, 0, 36)
    p.box(-23, 23, 2, 22, -1, 34, cut=True)                     # open back, glues to the face
    p.box(-5, 5, 9, 15, 33, 40, cut=True)                       # front laser window


def ear(p):
    p.box(-11, 11, 0, 32, -6, 6)
    p.box(-9, 9, 2, 30, -4, 7, cut=True)                        # hollow, saves plastic


def tail(p):
    p.box(-6, 6, 0, 10, -10, 10)                                # base that screws to the servo horn
    p.box(-3.6, 3.6, -1, 4, -3.6, 3.6, cut=True)                # horn hub clearance
    for z in (-7, 7):
        p.box(-0.8, 0.8, -1, 11, z - 0.8, z + 0.8, cut=True)    # horn screw holes
    p.cyl_z(0, 6, 3.5, -55, -9)                                 # the tail itself


def leg_thigh(p):
    p.cyl_x(0, 0, 7, 0, 4)                                      # hip hub (servo horn side)
    p.box(0, 4, -36, 0, -5.5, 5.5)                              # thigh bar
    p.box(0, 4, -58, -25, -10, 10)                              # knee servo bracket
    p.cyl_x(0, 0, 3.6, -1, 5, cut=True)                         # horn hub clearance
    for y in (-7, -14):
        p.cyl_x(y, 0, PILOT, -1, 5, cut=True)                   # horn screws
    top = -36 + SV_SHAFT                                        # knee shaft sits on the knee axis
    p.box(-1, 5, top - SV_L, top, -SV_W / 2, SV_W / 2, cut=True)
    for y in (top + 2.4, top - SV_L - 2.4):
        p.cyl_x(y, 0, PILOT, -1, 5, cut=True)


def leg_shin(p):
    p.cyl_x(0, 0, 7, 0, 4)                                      # knee hub
    p.box(0, 4, -34, 0, -4.5, 4.5)                              # shin bar
    p.box(0, 4, -45.5, -14, -10, 10)                            # wheel-servo bracket
    p.box(0, 4, -49, -45, 9, 14)                                # rubber toe pad (stick rubber on it)
    p.cyl_x(0, 0, 3.6, -1, 5, cut=True)
    for y in (-7, -14):
        p.cyl_x(y, 0, PILOT, -1, 5, cut=True)
    bottom = -35 - SV_SHAFT                                     # wheel shaft 35 mm below the knee
    p.box(-1, 5, bottom, bottom + SV_L, -SV_W / 2, SV_W / 2, cut=True)
    for y in (bottom - 2.4, bottom + SV_L + 2.4):
        p.cyl_x(y, 0, PILOT, -1, 5, cut=True)


def wheel(p):
    p.cyl_x(0, 0, 15, 0, 8)                                     # 30 mm wheel
    p.cyl_x(0, 0, 16, 3, 5, cut=True)                           # groove for an O-ring / rubber band tyre
    p.cyl_x(0, 0, 13.5, 3, 5)
    p.cyl_x(0, 0, 3.6, -1, 9, cut=True)                         # horn hub
    for y in (-10, -7, 7, 10):
        p.cyl_x(y, 0, PILOT, -1, 9, cut=True)                   # horn screws


PARTS = [  # name, builder, how many to print
    ('Torso_Bottom', torso_bottom, 1),
    ('Torso_Lid', torso_lid, 1),
    ('Neck', neck, 1),
    ('Head_Front', head_front, 1),
    ('Head_Back', head_back, 1),
    ('Muzzle', muzzle, 1),
    ('Ear', ear, 2),
    ('Tail', tail, 1),
    ('Leg_Thigh', leg_thigh, 4),
    ('Leg_Shin_WheelFoot', leg_shin, 4),
    ('Wheel_30mm', wheel, 4),
]


def main():
    sw = swlib.app()
    sw.CloseAllDocuments(True)
    swlib.probe(sw)
    rows, total_g = [], 0.0
    for name, build, qty in PARTS:
        p = swlib.Part(sw, name)
        try:
            build(p)
            bb = p.bbox_mm()
            size = sorted((bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]), reverse=True)
            fits = all(s <= b for s, b in zip(size, sorted(BED, reverse=True)))
            grams = p.volume_cm3() * PLA_DENSITY
            total_g += grams * qty
            p.save(OUT)
            rows.append(f'{name:20s} x{qty}  {size[0]:6.1f} x {size[1]:5.1f} x {size[2]:5.1f} mm  '
                        f'{grams:5.1f} g each  {"fits" if fits else "TOO BIG"}  bodies={len(p.m.GetBodies2(0, True))}')
        except Exception as e:
            rows.append(f'{name:20s} FAILED: {e}')
        sw.CloseDoc(p.m.GetTitle)
    print('\n'.join(rows))
    print(f'TOTAL plastic about {total_g:.0f} g  ->  about ${total_g / 10 * PRICE_PER_10G:.2f} at Brimbank')


if __name__ == '__main__':
    main()
