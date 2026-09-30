# RobotDog_Build.py - builds the Desk Buddy robot dog (v3) in Fusion 360.
# Run: Fusion 360 > Utilities > Add-Ins > Scripts and Add-Ins > "+" > pick this folder > Run.
# Units: Fusion's API works in centimetres, the same units as the 3D blueprint page.
# Axes: X = left/right, Y = forward (towards the face), Z = up.
# Every part is its own component, named after the blueprint, so it can be moved or edited on its own.
# Electronics are placeholder blocks at their real sizes, so the shell can be checked for fit.

import adsk.core, adsk.fusion, math, traceback

WALL = 0.2      # 2 mm printed walls
FILLET = 0.6    # rounded corners on the shell

# name, (width X, depth Y, height Z), centre (x, y, z)   -- all cm
ELECTRONICS = [
    ('Screen_Guition_4.3',  (10.5, 0.5, 6.7),  (0, 7.35, 12.5)),
    ('Camera_OV5640_board', (2.6, 0.4, 2.2),   (0, 7.0, 16.5)),
    ('Gesture_APDS9960',    (1.4, 0.3, 0.9),   (3.4, 7.1, 16.5)),
    ('Mic_left',            (0.3, 1.3, 1.0),   (-6.15, 6.0, 13.2)),
    ('Mic_right',           (0.3, 1.3, 1.0),   (6.15, 6.0, 13.2)),
    ('Laser_front',         (1.3, 0.3, 1.0),   (0, 8.35, 8.6)),
    ('Laser_edge_FL',       (1.3, 1.0, 0.3),   (-4.2, 4.9, 3.3)),
    ('Laser_edge_FR',       (1.3, 1.0, 0.3),   (4.2, 4.9, 3.3)),
    ('Laser_rear',          (1.3, 0.3, 1.0),   (0, -7.75, 4.6)),
    ('Laser_edge_rear',     (1.3, 1.0, 0.3),   (2.6, -7.0, 3.3)),
    ('Laser_side_L',        (0.3, 1.3, 1.0),   (-5.25, -0.8, 5.4)),
    ('Laser_side_R',        (0.3, 1.3, 1.0),   (5.25, -0.8, 5.4)),
    ('Battery_2x18650',     (7.6, 4.2, 2.0),   (0, -4.2, 4.5)),
    ('IMU_MPU6050',         (2.1, 1.6, 0.3),   (0, 0.8, 4.1)),
    ('ServoBoard_1_0x40',   (6.2, 2.5, 0.4),   (0, -0.9, 6.9)),
    ('ServoBoard_2_0x41',   (6.2, 2.5, 0.4),   (0, 2.3, 6.9)),
    ('Touch_MPR121',        (3.2, 2.0, 0.3),   (2.6, -3.4, 7.5)),
    ('Speaker_cavity',      (2.6, 1.6, 2.6),   (-3.9, -6.6, 6.8)),
    ('Amp_MAX98357A',       (1.8, 1.8, 0.3),   (-3.9, -4.4, 7.6)),
    ('Charger_2S_USBC',     (2.4, 1.8, 0.3),   (3.9, -6.8, 7.0)),
    ('Buck_Mini560',        (2.2, 1.2, 0.7),   (1.9, -5.6, 7.0)),
    ('Switch_KCD1',         (1.4, 0.6, 1.0),   (3.6, -7.8, 5.0)),
    ('Servo_tail_MG90S',    (1.2, 2.3, 2.3),   (0, -6.9, 7.0)),
]

# shell pieces: name, size, centre, tilt about X (degrees, + = leans back)
SHELL = [
    ('Shell_Torso', (10.4, 13.2, 4.4), (0, -1.1, 5.6), 0),
    ('Shell_Neck',  (5.2, 3.2, 4.2),   (0, 4.3, 9.0), 26),
    ('Shell_Head',  (12.2, 3.2, 9.0),  (0, 6.0, 12.9), 7),
    ('Shell_Snout', (4.6, 2.2, 1.8),   (0, 7.2, 8.7), 0),
]

LEG_HIPS = [(-1, 1, 4.0), (1, 1, 4.0), (-1, -1, -5.8), (1, -1, -5.8)]   # sx, front/back, y
HIP_Z = 4.0


def new_comp(root, name):
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ.component


def block(comp, size, centre):
    """Extrude a box of size (w, d, h) centred on centre, inside comp."""
    w, d, h = size
    x, y, z = centre
    planes = comp.constructionPlanes
    pin = planes.createInput()
    pin.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByReal(z - h / 2))
    plane = planes.add(pin)
    plane.isLightBulbOn = False
    sk = comp.sketches.add(plane)
    P = adsk.core.Point3D.create
    sk.sketchCurves.sketchLines.addTwoPointRectangle(P(x - w / 2, y - d / 2, 0), P(x + w / 2, y + d / 2, 0))
    prof = sk.profiles.item(0)
    ext = comp.features.extrudeFeatures.addSimple(prof, adsk.core.ValueInput.createByReal(h),
                                                  adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    return ext.bodies.item(0)


def cylinder(comp, radius, length, centre, axis='x'):
    x, y, z = centre
    P = adsk.core.Point3D.create
    if axis == 'x':
        pin = comp.constructionPlanes.createInput()
        pin.setByOffset(comp.yZConstructionPlane, adsk.core.ValueInput.createByReal(x - length / 2))
        plane = comp.constructionPlanes.add(pin)
        plane.isLightBulbOn = False
        sk = comp.sketches.add(plane)
        # sketch coordinates on the YZ plane: map model (y, z) through the sketch transform
        c = sk.modelToSketchSpace(P(x - length / 2, y, z))
    else:
        pin = comp.constructionPlanes.createInput()
        pin.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByReal(z - length / 2))
        plane = comp.constructionPlanes.add(pin)
        plane.isLightBulbOn = False
        sk = comp.sketches.add(plane)
        c = P(x, y, 0)
    sk.sketchCurves.sketchCircles.addByCenterRadius(P(c.x, c.y, 0), radius)
    ext = comp.features.extrudeFeatures.addSimple(sk.profiles.item(0), adsk.core.ValueInput.createByReal(length),
                                                  adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    return ext.bodies.item(0)


def tilt(comp, body, degrees, pivot):
    if not degrees:
        return
    m = adsk.core.Matrix3D.create()
    m.setToRotation(math.radians(-degrees), adsk.core.Vector3D.create(1, 0, 0),
                    adsk.core.Point3D.create(*pivot))
    coll = adsk.core.ObjectCollection.create()
    coll.add(body)
    mi = comp.features.moveFeatures.createInput2(coll)
    mi.defineAsFreeMove(m)
    comp.features.moveFeatures.add(mi)


def round_and_hollow(comp, body):
    try:
        edges = adsk.core.ObjectCollection.create()
        for e in body.edges:
            edges.add(e)
        fi = comp.features.filletFeatures.createInput()
        fi.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByReal(FILLET), True)
        comp.features.filletFeatures.add(fi)
    except Exception:
        pass  # a piece too small for the fillet stays square
    ents = adsk.core.ObjectCollection.create()
    ents.add(body)
    si = comp.features.shellFeatures.createInput(ents, False)
    si.insideThickness = adsk.core.ValueInput.createByReal(WALL)
    comp.features.shellFeatures.add(si)


def run(context):
    ui = None
    log = []
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = design.rootComponent
        root.name = 'Desk Buddy v3 - robot dog'

        # shell
        shell_c = new_comp(root, 'Shell (print)')
        for name, size, centre, deg in SHELL:
            try:
                b = block(shell_c, size, centre)
                b.name = name
                round_and_hollow(shell_c, b)
                tilt(shell_c, b, deg, centre)
                log.append('ok  ' + name)
            except Exception as e:
                log.append('ERR ' + name + ': ' + str(e))
        for sx in (-1, 1):   # ears: simple wedges, rotated outward later by hand if wanted
            try:
                b = block(shell_c, (2.2, 1.2, 3.0), (sx * 4.3, 5.8, 18.9))
                b.name = 'Ear_' + ('L' if sx < 0 else 'R')
                log.append('ok  ' + b.name)
            except Exception as e:
                log.append('ERR ear: ' + str(e))

        # electronics placeholders
        elec = new_comp(root, 'Electronics (placeholders)')
        for name, size, centre in ELECTRONICS:
            try:
                block(elec, size, centre).name = name
                log.append('ok  ' + name)
            except Exception as e:
                log.append('ERR ' + name + ': ' + str(e))

        # legs: hip servo, thigh link, knee servo, shin, wheel-foot (FS90R + wheel + rubber toe)
        for sx, fb, y in LEG_HIPS:
            leg_name = ('Front' if fb > 0 else 'Rear') + ('_L' if sx < 0 else '_R')
            leg = new_comp(root, 'Leg ' + leg_name)
            try:
                hx = sx * 5.2
                block(leg, (1.2, 2.3, 2.3), (hx, y, HIP_Z + 1.1)).name = 'Hip_servo_MG90S'
                block(leg, (2.2, 1.0, 0.5), (hx + sx * 2.0, y, HIP_Z)).name = 'Thigh_link (print)'
                block(leg, (1.2, 2.3, 2.3), (hx + sx * 3.3, y, HIP_Z)).name = 'Knee_servo_MG90S'
                block(leg, (0.8, 0.8, 4.0), (hx + sx * 3.7, y, HIP_Z - 2.4)).name = 'Shin (print)'
                block(leg, (1.2, 2.2, 1.4), (hx + sx * 3.6, y, HIP_Z - 4.3)).name = 'Wheel_servo_FS90R'
                cylinder(leg, 0.9, 0.45, (hx + sx * 4.55, y, HIP_Z - 4.5), 'x').name = 'Wheel'
                block(leg, (0.6, 0.6, 0.5), (hx + sx * 3.7, y + fb * 1.1, HIP_Z - 5.0)).name = 'Rubber_toe'
                log.append('ok  leg ' + leg_name)
            except Exception as e:
                log.append('ERR leg ' + leg_name + ': ' + str(e))

        # tail
        tail = new_comp(root, 'Tail (print)')
        try:
            b = cylinder(tail, 0.35, 4.2, (0, -9.0, 9.0), 'z')
            b.name = 'Tail'
            tilt(tail, b, -40, (0, -7.7, 7.6))
            log.append('ok  tail')
        except Exception as e:
            log.append('ERR tail: ' + str(e))

        app.activeViewport.fit()
        errs = [l for l in log if l.startswith('ERR')]
        ui.messageBox('Desk Buddy v3 built.\n{} parts OK, {} errors.\n\n{}'.format(
            len(log) - len(errs), len(errs), '\n'.join(errs) if errs else 'No errors.'))
    except Exception:
        if ui:
            ui.messageBox('Build failed:\n{}'.format(traceback.format_exc()))
