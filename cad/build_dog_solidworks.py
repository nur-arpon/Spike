"""Builds the Desk Buddy v4 robot dog layout in SOLIDWORKS through its COM API.

Run:  python build_dog_solidworks.py
Output: RobotDog_v4_layout.SLDPRT next to this script.

It is a multibody "layout part": every component is its own named solid body at its real size
and position, standing on the Top Plane. It is used to check fit and balance before the shell is
split into printable parts. Coordinates match the 3D blueprint page (cm, Y up, Z = forward),
with Y shifted so the wheels touch the ground at Y = 0.
"""
import os, math, pythoncom, win32com.client
from win32com.client import VARIANT

Y0 = 2.8                      # lift everything so the wheels sit on the Top Plane
CM = 0.01                     # SOLIDWORKS API works in metres
NOTHING = VARIANT(pythoncom.VT_DISPATCH, None)
WHEEL_ZSIGN = 1

# name, (width X, height Y, depth Z), centre (x, y, z)   all cm, blueprint coordinates
BOXES = [
    # printed shell (solid for now; hollowed when split into print parts)
    ('SHELL_Torso',        (8.0, 4.6, 17.0), (0, 5.6, -1.0)),
    ('SHELL_Neck',         (4.6, 4.6, 3.4),  (0, 9.4, 6.2)),
    ('SHELL_Head',         (12.2, 8.8, 5.4), (0, 13.8, 8.0)),
    ('SHELL_Muzzle',       (5.0, 2.4, 3.6),  (0, 10.6, 11.4)),
    ('SHELL_Ear_L',        (2.2, 3.2, 1.2),  (-4.3, 19.6, 7.2)),
    ('SHELL_Ear_R',        (2.2, 3.2, 1.2),  (4.3, 19.6, 7.2)),
    # electronics
    ('Screen_Guition_4p3', (10.5, 6.7, 1.2), (0, 14.0, 10.35)),   # 12 mm with chips on the back
    ('Camera_ESP32S3_board', (4.0, 2.7, 1.2), (0, 15.0, 8.9)),    # 40 x 27 mm board behind the screen
    ('Camera_OV5640_module', (0.85, 0.85, 0.6), (0, 17.8, 10.4)),  # lens on the forehead, flex cable to the board
    ('Gesture_APDS9960',   (1.4, 0.9, 0.3),  (3.6, 17.9, 10.85)),
    ('Mic_L',              (0.3, 1.0, 1.3),  (-6.25, 14.5, 8.0)),
    ('Mic_R',              (0.3, 1.0, 1.3),  (6.25, 14.5, 8.0)),
    ('Laser_front',        (1.3, 1.0, 0.3),  (0, 10.6, 13.35)),
    ('Laser_edge_FL',      (1.3, 0.3, 1.0),  (-3.0, 3.15, 6.8)),
    ('Laser_edge_FR',      (1.3, 0.3, 1.0),  (3.0, 3.15, 6.8)),
    ('Laser_rear',         (1.3, 1.0, 0.3),  (0, 4.3, -9.65)),
    ('Laser_edge_rear',    (1.3, 0.3, 1.0),  (-2.4, 3.15, -8.8)),
    ('Laser_side_L',       (0.3, 1.0, 1.3),  (-4.15, 6.6, -1.0)),
    ('Laser_side_R',       (0.3, 1.0, 1.3),  (4.15, 6.6, -1.0)),
    ('IMU_MPU6050',        (2.1, 0.3, 1.6),  (0, 3.6, 3.6)),
    ('ServoBoard2_0x41',   (6.2, 0.4, 2.5),  (0, 7.3, 4.6)),
    ('ServoBoard1_0x40',   (6.2, 0.4, 2.5),  (0, 7.3, 1.4)),
    ('Touch_MPR121',       (3.2, 0.3, 2.0),  (0, 7.3, -1.6)),
    ('Battery_2x18650',    (4.2, 2.0, 7.6),  (0, 4.4, -3.0)),
    ('Charger_2S_USBC',    (2.4, 0.3, 1.8),  (2.3, 7.3, -5.0)),
    ('Buck_Mini560',       (2.2, 0.7, 1.2),  (-2.3, 7.1, -5.0)),
    ('Speaker_cavity',     (2.6, 2.6, 1.6),  (-2.2, 5.6, -7.4)),
    ('Amp_MAX98357A',      (1.8, 0.3, 1.8),  (2.3, 5.2, -7.2)),
    ('Switch_KCD1',        (1.4, 1.0, 0.6),  (2.4, 5.2, -9.8)),
    ('Servo_tail',         (1.2, 2.3, 2.3),  (0, 6.9, -8.3)),
    ('Tail',               (0.8, 0.8, 4.0),  (0, 9.0, -11.3)),
]
# legs in the standing pose: shoulder servo, thigh, knee servo, shin, wheel servo (FS90R)
for sx, side in ((-1, 'L'), (1, 'R')):
    for zh, end in ((5.4, 'F'), (-6.8, 'B')):
        n = end + side
        BOXES += [
            (f'Leg{n}_hip_servo',   (1.2, 2.3, 2.3), (sx * 4.65, 5.2, zh)),
            (f'Leg{n}_thigh',       (0.6, 3.6, 1.1), (sx * 5.65, 3.4, zh)),
            (f'Leg{n}_knee_servo',  (1.2, 2.3, 2.3), (sx * 4.85, 1.6, zh)),
            (f'Leg{n}_shin',        (0.6, 3.4, 0.9), (sx * 5.65, -0.1, zh)),
            (f'Leg{n}_wheel_servo', (1.2, 1.4, 2.2), (sx * 5.65, -1.5, zh)),
            (f'Leg{n}_toe',         (0.6, 0.5, 0.6), (sx * 5.65, -2.55, zh + (1.1 if end == 'F' else -1.1))),
        ]
WHEELS = [(f'Leg{e}{s}_wheel', (sx * 6.5, -1.9, zh)) for sx, s in ((-1, 'L'), (1, 'R'))
          for zh, e in ((5.4, 'F'), (-6.8, 'B'))]


def m(v):
    return v * CM


def select_plane(model, name):
    model.ClearSelection2(True)
    ok = model.Extension.SelectByID2(name, 'PLANE', 0, 0, 0, False, 0, NOTHING, 0)
    if not ok:
        raise RuntimeError('could not select ' + name)


def extrude(model, depth, start_offset):
    """Blind extrusion of the active sketch, starting start_offset from the sketch plane."""
    fm = model.FeatureManager
    flip = start_offset < 0
    feat = fm.FeatureExtrusion3(
        True, False, False, 0, 0, m(depth), 0, False, False, False, False, 0, 0,
        False, False, False, False, False, True, True,
        3 if abs(start_offset) > 1e-9 else 0, m(abs(start_offset)), flip)
    if feat is None:
        raise RuntimeError('extrusion failed')
    return feat


def add_box(model, name, size, centre):
    w, h, d = size
    x, y, z = centre
    y += Y0
    select_plane(model, 'Front Plane')            # XY plane, normal +Z
    model.SketchManager.InsertSketch(True)
    model.SketchManager.CreateCenterRectangle(m(x), m(y), 0, m(x + w / 2), m(y + h / 2), 0)
    model.SketchManager.InsertSketch(True)
    feat = extrude(model, d, z - d / 2)
    feat.Name = name


def add_wheel(model, name, centre, r=0.9, width=0.45):
    x, y, z = centre
    y += Y0
    select_plane(model, 'Right Plane')            # YZ plane, normal +X
    model.SketchManager.InsertSketch(True)
    # On the Right Plane, sketch X runs along model -Z and sketch Y along model +Y.
    sp = (-m(z) * WHEEL_ZSIGN, m(y))
    model.SketchManager.CreateCircleByRadius(sp[0], sp[1], 0, m(r))
    model.SketchManager.InsertSketch(True)
    feat = extrude(model, width, x - width / 2)
    feat.Name = name


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, 'RobotDog_v4_layout.SLDPRT')
    app = win32com.client.Dispatch('SldWorks.Application')
    app.Visible = True
    app.CloseAllDocuments(True)
    template = app.GetUserPreferenceStringValue(8)    # swDefaultTemplatePart
    model = app.NewDocument(template, 0, 0, 0)
    if model is None:
        raise SystemExit('Could not create a part. Is a default part template set in SOLIDWORKS?')
    model.SketchManager.AddToDB = True                # skip snapping/inference while sketching
    ok, fail = 0, []
    for name, size, centre in BOXES:
        try:
            add_box(model, name, size, centre); ok += 1
        except Exception as e:
            fail.append(f'{name}: {e}')
    for name, centre in WHEELS:
        try:
            add_wheel(model, name, centre); ok += 1
        except Exception as e:
            fail.append(f'{name}: {e}')
    model.SketchManager.AddToDB = False
    # check the wheel landed where intended (front-left wheel should be at z = +5.4 cm)
    for bd in model.GetBodies2(0, True):
        if bd.Name.startswith('LegFL_wheel') or 'wheel' in bd.Name and 'servo' not in bd.Name:
            bb = bd.GetBodyBox()
            print('wheel body', bd.Name, 'z centre cm = %.2f' % ((bb[2] + bb[5]) / 2 / CM))
    model.ShowNamedView2('*Isometric', 7)
    model.ViewZoomtofit2()
    errs = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    warns = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
    model.Extension.SaveAs3(out, 0, 1, NOTHING, NOTHING, errs, warns)
    print(f'built {ok} bodies, {len(fail)} failed')
    for f in fail:
        print('  FAIL', f)
    print('saved', out if os.path.exists(out) else '(save failed)')


if __name__ == '__main__':
    main()
