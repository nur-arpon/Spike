"""Self-test for swlib_v3.py - builds small parts in SOLIDWORKS and checks every v3 helper against
hand-computed volumes, boxes and distances. Run:  python swlib_v3_selftest.py

It creates its own documents only, closes every one of them, and writes its test files to
%TEMP%\\swlib_v3_selftest (never into the project folders). Exit code 0 = all checks passed.
"""
import os, sys, math, tempfile, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swlib_v3 as S

OUT = os.path.join(tempfile.gettempdir(), 'swlib_v3_selftest')
PI = math.pi
SPANDREL = 1 - PI / 4          # area of a square corner minus its inscribed quarter circle, per r^2
RES = []
MINE = []                      # every document this test opened (closed at the end)


def check(name, got, want, tol):
    ok = got is not None and abs(got - want) <= tol
    RES.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {got if got is None else round(got, 4)}  want {round(want, 4)}  (tol {tol})")
    return ok


def check_true(name, cond, detail=''):
    RES.append(bool(cond))
    print(f"{'PASS' if cond else 'FAIL'}  {name} {detail}")
    return cond


def expect_raise(name, fn, exc=Exception):
    try:
        fn()
    except exc as ex:
        return check_true(name, True, f'(raised: {str(ex)[:90]})')
    return check_true(name, False, '(did not raise)')


def check_box(name, p, want, tol=0.02):
    got = p.bbox_exact()
    ok = got is not None and all(abs(g - w) <= tol for g, w in zip(got, want))
    RES.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name} bbox: got {[round(v, 3) for v in got] if got else None}  want {want}")


def new_part(sw, name):
    p = S.Part(sw, name)
    MINE.append(p.m)
    return p


def vol(p):
    return p.volume_cm3() * 1000.0     # mm3


def edge_dist(p, pt):
    _, d, _ = S.Part._nearest(p._ents('edge'), pt)
    return d


# ---------------------------------------------------------------------------------------------
def t_geometry():
    """Pure-Python outline maths against closed-form areas."""
    radii = (2, 4, 6, 0)
    check('rrect 40x20 R(2,4,6,0) area', S.loop_area(S.rrect(0, 40, 0, 20, radii)), 800 - SPANDREL * (4 + 16 + 36), 1e-9)
    check('rrect dict radii = tuple radii', S.loop_area(S.rrect(0, 40, 0, 20, {'--': 2, '+-': 4, '++': 6})),
          800 - SPANDREL * 56, 1e-9)
    check('stadium 30x10 area', S.loop_area(S.stadium(0, 30, 0, 10)), 20 * 10 + PI * 25, 1e-9)
    check('slot c-c 20, r4 area', S.loop_area(S.slot((0, 0), (20, 0), 4)), 20 * 8 + PI * 16, 1e-9)
    # two-circle hull: sectors r1^2 (pi - phi) + r2^2 phi, plus two right trapezoids (r1 + r2) * Lt
    r1, r2, d = 5.0, 3.0, 20.0
    phi, Lt = math.acos((r1 - r2) / d), math.sqrt(d * d - (r1 - r2) ** 2)
    A_hull = r1 * r1 * (PI - phi) + r2 * r2 * phi + (r1 + r2) * Lt
    check('hull2 r5/r3 d20 area', S.loop_area(S.hull2((0, 0), 5, (20, 0), 3)), A_hull, 1e-9)
    check('hull2 reversed (small first) area', S.loop_area(S.hull2((20, 0), 3, (0, 0), 5)), A_hull, 1e-9)
    # rounded triangle: rounding a corner with interior angle a removes r^2 (cot(a/2) - (pi - a)/2)
    tri = [(0, 0), (30, 0), (0, 20)]
    angs = [PI / 2, math.atan2(20, 30), math.atan2(30, 20)]
    cut = sum(2 * 2 * (1 / math.tan(a / 2) - (PI - a) / 2) for a in angs)
    check('rpoly triangle all R2 area', S.loop_area(S.rpoly(tri, 2)), 300 - cut, 1e-9)
    # a clockwise outline gives a negative area but the same shape
    check('rpoly clockwise = -area', -S.loop_area(S.rpoly(tri[::-1], 2)), 300 - cut, 1e-9)
    expect_raise('rrect radius too big raises', lambda: S.rrect(0, 10, 0, 10, 6), ValueError)
    expect_raise('hull2 circle inside circle raises', lambda: S.hull2((0, 0), 10, (2, 0), 3), ValueError)
    pts = S.loop_points(S.rrect(0, 40, 0, 20, 5), 0.5)
    check_true('loop_points stay on the outline box', all(-1e-9 <= x <= 40 + 1e-9 and -1e-9 <= y <= 20 + 1e-9 for x, y in pts),
               f'({len(pts)} points)')


def t_rrect_planes(sw):
    """Per-corner radii on all three planes: volume, box, and which corner got which radius."""
    radii = (1.0, 2.0, 3.0, 0.0)                    # (u0,v0), (u1,v0), (u1,v1), (u0,v1)
    area = 40 * 20 - SPANDREL * sum(r * r for r in radii)
    corners = [(0, 0), (40, 0), (40, 20), (0, 20)]
    for axis, fn in (('z', 'rrect_z'), ('x', 'rrect_x'), ('y', 'rrect_y')):
        p = new_part(sw, 'rr' + axis)
        getattr(p, fn)(0, 40, 0, 20, 5, 15, radii)
        check(f'rrect_{axis} volume', vol(p), area * 10, 1e-3)
        want = {'z': [0, 0, 5, 40, 20, 15], 'x': [5, 0, 0, 15, 20, 40], 'y': [0, 5, 0, 40, 15, 20]}[axis]
        check_box(f'rrect_{axis}', p, want)
        for (u, v), r in zip(corners, radii):
            pt = {'z': (u, v, 15), 'x': (15, v, u), 'y': (u, 15, v)}[axis]
            # the corner point is r*(sqrt2 - 1) from the corner arc, or on the sharp corner's edges
            check(f'rrect_{axis} corner ({u},{v}) has R{r}', edge_dist(p, pt), r * (math.sqrt(2) - 1), 0.01)


def t_hull_slot(sw):
    r1, r2, d = 5.0, 3.0, 20.0
    phi, Lt = math.acos((r1 - r2) / d), math.sqrt(d * d - (r1 - r2) ** 2)
    A_hull = r1 * r1 * (PI - phi) + r2 * r2 * phi + (r1 + r2) * Lt
    p = new_part(sw, 'hullx')
    p.hull_x((10, -20), 5, (30, -20), 3, 55.6, 60.6)          # (z, y) outline like a thigh
    check('hull_x volume', vol(p), A_hull * 5, 1e-3)
    check_box('hull_x', p, [55.6, -25, 5, 60.6, -15, 33])
    p = new_part(sw, 'sloty')
    p.slot_y((0, 10), (20, 10), 4, 2, 5)                        # (x, z): z 6..14 checks the Top Plane sign
    check('slot_y volume', vol(p), (20 * 8 + PI * 16) * 3, 1e-3)
    check_box('slot_y', p, [-4, 2, 6, 24, 5, 14])
    p = new_part(sw, 'stadz')
    p.prism('z', S.stadium(-15, 15, 30, 40), -3, 3)
    check('stadium prism_z volume', vol(p), (20 * 10 + PI * 25) * 6, 1e-3)
    check_box('stadium prism_z', p, [-15, 30, -3, 15, 40, 3])
    p = new_part(sw, 'hullz')
    p.hull_z((0, 0), 17, (0, -40), 11, 0, 4)                    # knee drum to paw, unequal ends, vertical
    phi2, Lt2 = math.acos((17 - 11) / 40), math.sqrt(1600 - 36)
    check('hull_z vertical volume', vol(p), (17 * 17 * (PI - phi2) + 121 * phi2 + 28 * Lt2) * 4, 1e-3)
    check_box('hull_z vertical', p, [-17, -51, 0, 17, 17, 4])


def t_nested_and_cuts(sw):
    p = new_part(sw, 'ring')
    p.prism('z', [S.circle((0, 0), 10), S.circle((0, 0), 6)], 0, 4)
    check('ring (nested circles) volume', vol(p), PI * (100 - 36) * 4, 1e-3)
    p = new_part(sw, 'plate')
    p.prism('z', [S.rrect(-20, 20, -10, 10, 3), S.slot((-8, 0), (8, 0), 2)], 0, 2)
    check('rrect plate with slot hole volume', vol(p), ((800 - SPANDREL * 4 * 9) - (16 * 4 + PI * 4)) * 2, 1e-3)
    p = new_part(sw, 'cuts')
    p.box(0, 40, 0, 20, 0, 10)
    p.rrect_z(10, 30, 5, 15, 5, 11, 5, cut=True)                # stadium pocket 5 deep from the top
    check('rrect_z cut (stadium pocket)', vol(p), 8000 - (200 - (4 - PI) * 25) * 5, 1e-3)
    p2 = new_part(sw, 'cut2')
    p2.box(0, 40, 0, 20, 0, 10)
    p2.slot_x((2, 10), (8, 10), 2, -1, 41, cut=True)            # (z,y): z 0..10, y 8..12, fully inside
    check('slot_x cut through (exact)', vol(p2), 8000 - (6 * 4 + PI * 4) * 40, 1e-3)
    p2.hull_y((20, 3), 1.5, (20, 7), 2.5, 15, 25, cut=True)    # (x,z) hull pocket from the top, y 15..20
    phi3, Lt3 = math.acos((1.5 - 2.5) / 4), math.sqrt(16 - 1)
    A3 = 1.5 ** 2 * (PI - phi3) + 2.5 ** 2 * phi3 + 4 * Lt3
    check('hull_y cut pocket (exact)', vol(p2), 8000 - (6 * 4 + PI * 4) * 40 - A3 * 5, 1e-3)


def t_fillet_chamfer(sw):
    # each case on its own clean 40 x 20 x 10 box, so every edge still has its full length
    p = new_part(sw, 'fil')
    p.box(0, 40, 0, 20, 0, 10)
    v0 = vol(p)
    p.fillet(2, [(20, 20, 10)])                                  # edge y 20, z 10, along x, 40 long
    check('fillet R2 on a 40 mm edge', vol(p) - v0, -SPANDREL * 4 * 40, 1e-3)
    p = new_part(sw, 'cha')
    p.box(0, 40, 0, 20, 0, 10)
    v0 = vol(p)
    p.chamfer(1.5, [(0, 10, 0)])                                 # edge x 0, z 0, along y - hidden in the iso view
    check('chamfer 1.5 on a hidden 20 mm edge', vol(p) - v0, -0.5 * 1.5 ** 2 * 20, 1e-3)
    p = new_part(sw, 'fail')
    p.box(0, 40, 0, 20, 0, 10)
    v0 = vol(p)
    expect_raise('fillet on a vertex point raises (ambiguous)', lambda: p.fillet(1, [(40, 0, 0)]), S.FeatureFailed)
    expect_raise('fillet with no edge near the point raises', lambda: p.fillet(1, [(100, 100, 100)]), S.FeatureFailed)
    # SOLIDWORKS itself ACCEPTS R15 here (it overflows the 10 mm face and reshapes the part): the guard must stop it
    expect_raise('fillet R15 wider than the 10 mm face raises', lambda: p.fillet(15, [(20, 0, 10)]), S.FeatureFailed)
    expect_raise('chamfer 12 wider than the 10 mm face raises', lambda: p.chamfer(12, [(20, 0, 10)]), S.FeatureFailed)
    check('failed fillets left the model unchanged', vol(p) - v0, 0.0, 1e-6)
    check('selection is clear after a failure', p.m.SelectionManager.GetSelectedObjectCount2(-1), 0, 0)
    skipped = p.fillet_safe(1, [(40, 10, 0), (100, 100, 100)])   # edge x 40, z 0 along y + a point in mid-air
    check('fillet_safe: good edge done', vol(p) - v0, -SPANDREL * 1 * 20, 1e-3)
    check('fillet_safe: bad point skipped and reported', len(skipped), 1, 0)
    check('fillet_safe: recorded in part.skipped', len(p.skipped), 1, 0)
    v0 = vol(p)
    # edges y 0 / y 20 at z 10, along x: no vertex shared with the fillet above
    n_sk = len(p.chamfer_safe(0.5, [(20, 0, 10), (20, 20, 10)]))
    check('chamfer_safe two edges at once', vol(p) - v0, -2 * 0.5 * 0.5 ** 2 * 40, 1e-3)
    check('chamfer_safe skipped none', n_sk, 0, 0)
    p = new_part(sw, 'limit')
    p.box(0, 40, 0, 20, 0, 10)
    v0 = vol(p)
    p.fillet(9, [(20, 0, 10)])                                   # R9 on the 10 mm face: fits, exact
    check('fillet R9 just inside the 10 mm face', vol(p) - v0, -SPANDREL * 81 * 40, 1e-3)
    p = new_part(sw, 'limitc')
    p.box(0, 40, 0, 20, 0, 10)
    v0 = vol(p)
    p.chamfer(9.5, [(20, 0, 10)])
    check('chamfer 9.5 just inside the 10 mm face', vol(p) - v0, -0.5 * 9.5 ** 2 * 40, 1e-3)
    # _drop_feature restores the model (used when a feature comes out empty)
    p = new_part(sw, 'drop')
    p.box(0, 40, 0, 20, 0, 10)
    v0 = vol(p)
    f = p.fillet(0.5, [(40, 20, 5)])                             # edge x 40, y 20, along z
    check('fillet R0.5 on a 10 mm edge', vol(p) - v0, -SPANDREL * 0.25 * 10, 1e-4)
    check_true('drop_feature removes the fillet', p._drop_feature(f))
    check('drop_feature restored the volume', vol(p) - v0, 0.0, 1e-6)
    # tangent-chain fillet round a rounded-rectangle outline from ONE point (Pappus at the corners)
    q = new_part(sw, 'chain')
    q.rrect_z(0, 30, 0, 20, 0, 10, 3)
    v0 = vol(q)
    q.fillet(1, [(15, 20, 10)])
    rho, R = 1.0, 3.0
    per_corner = SPANDREL * rho ** 2 * (PI / 2) * (R - rho + rho / (6 * SPANDREL))
    check('fillet R1 propagates round a R3 rounded outline', vol(q) - v0,
          -(SPANDREL * rho ** 2 * 2 * (24 + 14) + 4 * per_corner), 1e-3)
    q2 = new_part(sw, 'noprop')
    q2.rrect_z(0, 30, 0, 20, 0, 10, 3)
    v0 = vol(q2)
    q2.fillet(1, [(15, 20, 10)], propagate=False)
    # only the 24 mm straight edge: SPANDREL * 24 plus a small run-out blend where it meets the tangent arcs
    # (SOLIDWORKS ends a non-propagated fillet with a blend there, so it is not exact) - far from the -20.05 above
    dv = vol(q2) - v0
    check_true('fillet propagate=False rounds only the picked edge', -1.15 * SPANDREL * 24 <= dv <= -SPANDREL * 24,
               f'(dv {dv:.3f}, straight part alone {-SPANDREL * 24:.3f}, whole outline -20.05)')


def t_shell(sw):
    p = new_part(sw, 'shell')
    p.box(0, 30, 0, 20, 0, 20)
    p.shell(2, [(15, 20, 10)])
    check('shell 2 mm, top open', vol(p), 30 * 20 * 20 - 26 * 18 * 16, 1e-3)
    p2 = new_part(sw, 'shell2')
    p2.box(0, 30, 0, 20, 0, 20)
    p2.shell(1.5, [(15, 20, 10), (15, 10, 0)])                   # top and back open
    check('shell 1.5 mm, two faces open', vol(p2), 12000 - 27 * 18.5 * 18.5, 1e-3)


def t_revolve(sw):
    p = new_part(sw, 'wheel')
    # wheel-like rim about the leg axle: axis along x through y -65, z 66
    p.revolve('x', (-65, 66), S.rrect(77.2, 85.2, 5, 15.35), False)
    check('revolve x rim volume', vol(p), PI * (15.35 ** 2 - 25) * 8, 1e-2)
    check_box('revolve x rim', p, [77.2, -80.35, 50.65, 85.2, -49.65, 81.35])
    p.revolve('x', (-65, 66), S.rrect(80.0, 82.4, 13.9, 16), cut=True)   # O-ring groove
    check('revolve cut groove', vol(p), PI * (15.35 ** 2 - 25) * 8 - PI * (15.35 ** 2 - 13.9 ** 2) * 2.4, 1e-2)
    p2 = new_part(sw, 'cap')
    # domed cap about a vertical axis at (x 10, z -20): profile a 0..3, r 0..6 with the top rim rounded R3
    p2.revolve('y', (10, -20), S.rrect(0, 3, 0, 6, (0, 0, 3, 0)))
    # cylinder r3 h3  +  quarter disc (centre a0 r3, radius 3) revolved: 2*pi*(3*9pi/4 + 9)
    check('revolve y domed cap volume', vol(p2), PI * 9 * 3 + 2 * PI * (3 * 9 * PI / 4 + 9), 1e-2)
    check_box('revolve y domed cap', p2, [4, 0, -26, 16, 3, -14])
    p3 = new_part(sw, 'tube')
    p3.revolve('z', (-30, 5), S.rrect(-10, -4, 2, 4))
    check('revolve z tube volume', vol(p3), PI * (16 - 4) * 6, 1e-2)
    check_box('revolve z tube', p3, [-34, 1, -10, -26, 9, -4])
    p3.revolve('z', (-30, 5), S.rrect(-12, 2, 0, 3))               # rod r 3 overlaps the tube's r 2..4
    check('revolve z merges into the tube', len(p3._bodies()), 1, 0)
    expect_raise('revolve profile crossing the axis raises', lambda: p3.revolve('z', (0, 0), S.rrect(0, 1, -1, 1)), ValueError)


def _iso_faces(path):
    """Median colour of the three visible faces of a centred cube in an isometric PNG (top, front, right)."""
    from PIL import Image
    im = Image.open(path).convert('RGB')
    w, h = im.size

    def at(fx, fy):
        px = [im.getpixel((int(w * fx) + dx, int(h * fy) + dy)) for dx in range(-4, 5) for dy in range(-4, 5)]
        px.sort(key=sum)
        return px[len(px) // 2]
    return [at(.5, .35), at(.40, .62), at(.60, .62)]


def t_color(sw):
    os.makedirs(OUT, exist_ok=True)
    targets = {'warm white': S.WARM_WHITE, 'graphite': S.GRAPHITE, 'black': S.BLACK}
    palette = {k: tuple(round(v * 255) for v in S.rgb01(h)) for k, h in targets.items()}
    palette['SolidWorks default'] = (202, 209, 238)
    for label, hexc in targets.items():
        p = new_part(sw, 'col')
        p.box(-20, 20, -20, 20, -20, 20)
        back = p.set_color(hexc)
        want = S.rgb01(hexc)
        check(f'set_color {label} reads back (R)', back[0], want[0], 1e-3)
        p.m.ShowNamedView2('*Isometric', -1)
        p.m.ViewZoomtofit2()
        p.m.ClearSelection2(True)
        png = os.path.join(OUT, f'colour_{label.replace(" ", "_")}.png')
        e = S.VARIANT(S.pythoncom.VT_BYREF | S.pythoncom.VT_I4, 0)
        p.m.Extension.SaveAs3(png, 0, 1, S.NOTHING, S.NOTHING, e, e)
        faces = _iso_faces(png)
        mean = tuple(round(sum(f[k] for f in faces) / 3) for k in range(3))
        tgt = palette[label]
        nearest = min(palette, key=lambda k: math.dist(mean, palette[k]))
        check_true(f'PNG render of {label} reads as {label}',
                   nearest == label and all(abs(a - b) <= 30 for a, b in zip(mean, tgt)),
                   f'(iso faces {faces}, mean {mean}, target {tgt}, nearest: {nearest})')
    # body colour in a multibody part
    p = new_part(sw, 'bodies')
    p.merge = False
    p.box(0, 10, 0, 10, 0, 10); p.name_body('servo A')
    p.box(20, 30, 0, 10, 0, 10); p.name_body('board B')
    n = p.set_body_color('servo', '#2050A0')
    bodies = {b.Name: b for b in p._bodies()}
    got = list(bodies['servo A'].MaterialPropertyValues2 or [0, 0, 0])
    check('set_body_color hits one body', n, 1, 0)
    check('set_body_color reads back (B)', got[2], 0xA0 / 255, 1e-3)


def t_component_color(sw):
    os.makedirs(OUT, exist_ok=True)
    p = new_part(sw, 'comp_src')
    p.box(0, 10, 0, 10, 0, 10)
    p.set_color(S.GRAPHITE)
    path = os.path.join(OUT, 'component_colour_test.SLDPRT')
    e = S.VARIANT(S.pythoncom.VT_BYREF | S.pythoncom.VT_I4, 0)
    check_true('test part saved', p.m.Extension.SaveAs3(path, 0, 1, S.NOTHING, S.NOTHING, e, e))
    asm = sw.NewDocument(sw.GetUserPreferenceStringValue(9), 0, 0, 0)
    MINE.append(asm)
    comp = asm.AddComponent5(path, 0, '', False, '', 0, 0, 0)
    check_true('component added', comp is not None)
    back = S.set_component_color(comp, S.BLACK)
    check('set_component_color reads back (R)', back[0] if back else None, 0x15 / 255, 1e-3)


def t_save_split(sw):
    p = new_part(sw, 'swlib_v3 save test (nothing)')
    p.rrect_z(0, 30, 0, 20, 0, 8, 4)
    p.fillet(1, [(15, 20, 8)])
    p.set_color(S.WARM_WHITE)
    dirs = [os.path.join(OUT, d) for d in ('parts', 'stl', 'png')]
    out = p.save_split(*dirs)
    check_true('save_split wrote SLDPRT / STL / PNG in their own folders',
               all(os.path.exists(out[k]) for k in ('sldprt', 'stl', 'png')) and
               [os.path.dirname(out[k]) for k in ('sldprt', 'stl', 'png')] == dirs, str(list(out.values())))
    v_stl, v_mod = S.stl_volume_mm3(out['stl']), vol(p)
    check('STL volume vs model (fraction)', abs(v_stl - v_mod) / v_mod, 0.0, 0.05)
    expect_raise('check_stl rejects a wrong volume', lambda: S.check_stl(out['stl'], p.bbox_mm(), v_mod * 1.2), RuntimeError)
    expect_raise('check_stl rejects a wrong size', lambda: S.check_stl(out['stl'], [0, 0, 0, 10, 10, 10]), RuntimeError)


def open_titles(sw):
    out, d = [], sw.GetFirstDocument
    while d is not None:
        out.append(d.GetTitle)
        d = d.GetNext
    return out


def main():
    sw = S.app()
    before = open_titles(sw)
    if before:
        print(f'NOTE: documents already open (left alone): {before}')
    S.probe(sw)
    S.probe_axes(sw)
    print(f'TOP_ZSIGN = {S.TOP_ZSIGN}')
    tests = [('geometry', lambda: t_geometry()), ('rrect planes', t_rrect_planes), ('hull/slot', t_hull_slot),
             ('nested + cuts', t_nested_and_cuts), ('fillet/chamfer', t_fillet_chamfer), ('shell', t_shell),
             ('revolve', t_revolve), ('colour', t_color), ('component colour', t_component_color),
             ('save_split', t_save_split)]
    for name, fn in tests:
        print(f'--- {name}')
        try:
            fn() if name == 'geometry' else fn(sw)
        except Exception:
            RES.append(False)
            print(f'FAIL  {name} crashed:')
            traceback.print_exc(limit=4)
    # close only our own documents (assembly first, then the parts it pulled in)
    for m in reversed(MINE):
        try:
            sw.CloseDoc(m.GetTitle)
        except Exception:
            pass
    left = [t for t in open_titles(sw) if t not in before]
    check_true('no test document left open', not left, str(left))
    n_fail = RES.count(False)
    print(f'=== {len(RES) - n_fail} passed, {n_fail} failed')
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())
