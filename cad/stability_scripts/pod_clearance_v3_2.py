"""v3.2 paw-pod desk clearance for the gait and trick poses (stability_max_research.md, Questions 1-3).

Uses spike_model.py (unchanged) for the body attitude on its three support paws, then samples the REAL paw-pod
surface from build_print_parts_v3_2.py (pod x 38.2 -> 60 from the centre line, profile a -10.4..21.2 (fore-aft),
v -8.4..8.4 about the axle, R4 bottom / R3 top profile corners, inboard perimeter round R_IN) and a v3.2 chamfer
on the inboard lower edge. Every paw (support paws AND the lifted paw) is checked; the number is the lowest
pod point above the desk plane.

Run: python pod_clearance_v3_2.py
"""
import math, sys
import numpy as np
sys.path.insert(0, r'D:\Claude-Projects\RobotCompanion\cad\stability_scripts')
import spike_model_v3_2 as S     # v3.2 mass / CoM / tyre r 17.7 (servo_load_check_v3_2.py)

TYRE_PLANE = 81.2
POD_IN, BAND_IN, BAND_OUT = 38.2, 60.0, 61.4
A0, A1, V = -10.4, 21.2, 8.4
TAB_A0, TAB_A1 = -13.05, 23.85


def profile(a0, a1, v0, v1, rb, rt, step=0.5):
    """Boundary points + outward normals of a rounded rectangle in (a, v)."""
    pts = []
    def arc(c, r, t0, t1):
        n = max(3, int(abs(t1 - t0) * r / step) + 1)
        for k in range(n + 1):
            t = t0 + (t1 - t0) * k / n
            d = (math.cos(t), math.sin(t))
            pts.append(((c[0] + r * d[0], c[1] + r * d[1]), d))
    def line(p, q, nrm):
        L = math.dist(p, q); n = max(2, int(L / step) + 1)
        for k in range(n + 1):
            s = k / n
            pts.append(((p[0] + (q[0] - p[0]) * s, p[1] + (q[1] - p[1]) * s), nrm))
    line((a0 + rb, v0), (a1 - rb, v0), (0, -1))
    arc((a1 - rb, v0 + rb), rb, -math.pi / 2, 0)
    line((a1, v0 + rb), (a1, v1 - rt), (1, 0))
    arc((a1 - rt, v1 - rt), rt, 0, math.pi / 2)
    line((a1 - rt, v1), (a0 + rt, v1), (0, 1))
    arc((a0 + rt, v1 - rt), rt, math.pi / 2, math.pi)
    line((a0, v1 - rt), (a0, v0 + rb), (-1, 0))
    arc((a0 + rb, v0 + rb), rb, math.pi, 1.5 * math.pi)
    return pts


def pod_points(r_in=3.0, chamfer=None, end_chamfer=None):
    """Surface samples (X from the centre line, a, v) of the lower half of the pod + tab band.
    chamfer = (c_x, c_v): a plane cut through the inboard lower edge: removes material with
    (X - POD_IN) / c_x + (v + V) / c_v < 1 (c_x along X, c_v up)."""
    out = []
    for (a, v), (na, nv) in profile(A0, A1, -V, V, 4.0, 3.0):
        if v > 0:
            continue
        for X in np.arange(POD_IN + r_in, BAND_IN + 0.01, 1.0):       # the pod sides
            out.append((X, a, v))
        for k in range(0, 10):                                         # inboard perimeter round
            ph = k / 9 * math.pi / 2
            cx, ca, cv = POD_IN + r_in, a - r_in * na, v - r_in * nv
            out.append((cx - r_in * math.sin(ph), ca + r_in * math.cos(ph) * na, cv + r_in * math.cos(ph) * nv))
    for (a, v), _ in profile(TAB_A0, TAB_A1, -V, V, 4.0, 4.0):       # tab band (x 60 -> 61.4)
        if v <= 0:
            for X in (BAND_IN, BAND_OUT):
                out.append((X, a, v))
    pts = np.array(out)
    if end_chamfer:
        # 45 deg chamfers on the pod's front and rear LOWER edges (a-ends), pod part only (X < BAND_IN)
        c = end_chamfer
        pod = pts[:, 0] < BAND_IN - 1e-6
        sf = ((pts[:, 1] - (A1 - c)) * -1 + c) / c + (pts[:, 2] + V) / c    # front: (A1 - a)/c + (v+V)/c
        sr = (pts[:, 1] - A0) / c + (pts[:, 2] + V) / c
        keep = ~pod | ((((A1 - pts[:, 1]) / c + (pts[:, 2] + V) / c) >= 1.0) & (sr >= 1.0))
        pts = pts[keep]
        for X in np.arange(POD_IN, BAND_IN + 0.01, 0.5):
            for f in np.linspace(0, 1, 9):
                pts = np.vstack([pts, [X, A1 - c * f, -V + c * (1 - f)], [X, A0 + c * f, -V + c * (1 - f)]])
    if chamfer:
        cx, cv = chamfer
        s = (pts[:, 0] - POD_IN) / cx + (pts[:, 2] + V) / cv
        keep = s >= 1.0 - 1e-9
        pts = pts[keep]
        # the chamfer face itself: its lowest points are its edges; sample the face along a
        for (a, v), (na, nv) in profile(A0, A1, -V, V, 4.0, 3.0):
            if v > -V + 4.0 + 1e-6 or nv > -0.2:
                continue
        for a in np.arange(A0, A1 + 0.01, 0.5):
            for f in np.linspace(0, 1, 9):
                X = POD_IN + cx * f
                v = -V + cv * (1 - f)
                # inside the R4 profile ends the face is trimmed by the profile
                da = 0.0
                if a < A0 + 4.0:
                    da = A0 + 4.0 - a
                elif a > A1 - 4.0:
                    da = a - (A1 - 4.0)
                vmin = -V + 4.0 - math.sqrt(max(0.0, 16.0 - da * da)) if da > 0 else -V
                if v >= vmin - 1e-9:
                    pts = np.vstack([pts, [X, a, v]])
    return pts


def clearance(res, angles, pts):
    """Lowest pod point above the desk plane, per leg."""
    n, p0 = res['n'], None
    sup_pts = res['cps']
    # desk plane passes through the contact points of the support paws: use any support contact
    out = {}
    PL = {l: S.leg_points(l, *angles[l]) for l in S.LEGS}
    for l in S.LEGS:
        t = PL[l]['t']
        ax = PL[l]['axle']
        sgn = -1.0 if S.FOOT_X[l] > 0 else 1.0
        down = np.array([-math.cos(t), math.sin(t)])      # along the shin, down (y, z)
        fore = np.array([math.sin(t), math.cos(t)])
        X = pts[:, 0]; a = pts[:, 1]; v = pts[:, 2]
        y = ax[0] + (-v) * down[0] + a * fore[0]
        z = ax[1] + (-v) * down[1] + a * fore[1]
        x = S.FOOT_X[l] + sgn * (TYRE_PLANE - X)
        P3 = np.stack([x, y, z], 1)
        out[l] = float(np.min((P3 - res['p0']) @ n))
    return out


POSES = [  # name, angles FL, FR, BL, BR, lifted leg
    ('stand', dict(FL=(0, 0), FR=(0, 0), BL=(0, 0), BR=(0, 0)), None),
    ('C_FL crossing', dict(FL=(4.2, 3.4), FR=(28.2, -39.6), BL=(20.2, -25.4), BR=(-19.0, 47.9)), None),
    ('B_FL paw up (gait)', dict(FL=(-29.8, -47.6), FR=(12.6, -10.3), BL=(3.0, 5.3), BR=(-18.9, 49.3)), 'FL'),
    ('R_BR back paw up (gait)', dict(FL=(13.2, -24.8), FR=(0.3, -1.0), BL=(0.1, -2.0), BR=(7.0, 33.9)), 'BR'),
    ('give paw from stand 8 mm', dict(FL=(6.8, 43.5), FR=(10.1, -23.2), BL=(-5.2, 4.4), BR=(-0.3, 49.6)), 'FL'),
    ('give paw from stand 6 mm', dict(FL=(-4.4, 40.2), FR=(-4.1, -4.0), BL=(-1.3, -8.1), BR=(-1.2, 49.2)), 'FL'),
    ('give paw puppy sit 8 mm', dict(FL=(25.8, 33.0), FR=(-10.0, 7.3), BL=(-0.7, -9.5), BR=(0.8, 49.8)), 'FL'),
    ('give paw puppy sit 6 mm', dict(FL=(25.1, 3.8), FR=(-12.2, 7.4), BL=(-1.0, -13.1), BR=(0.7, 49.7)), 'FL'),
    ('curious tilt (paw raised)', dict(FL=(-25.4, -46.0), FR=(12.1, -20.9), BL=(-7.2, 13.1), BR=(-3.2, 49.4)), 'FL'),
    ('sniff, back paw raised', dict(FL=(29.5, 40.2), FR=(16.3, 3.1), BL=(21.7, -9.8), BR=(-20.4, 14.7)), 'BR'),
    ('back-paw lift', dict(FL=(29.9, -34.3), FR=(0.9, 1.1), BL=(0.9, 0.8), BR=(-20.6, 48.8)), 'BR'),
    ('sit (8 deg)', dict(FL=(-13.3, -7.5), FR=(-12.7, -7.9), BL=(-12.2, -48.0), BR=(-12.7, -48.0)), None),
]


def run(robot, r_in, chamfer, label, verbose=True, end_chamfer=None):
    pts = pod_points(r_in, chamfer, end_chamfer)
    worst = (1e9, '')
    rows = []
    for name, ang, lifted in POSES:
        ang = {k: tuple(map(float, v)) for k, v in ang.items()}
        if lifted:
            res = S.solve(robot, ang, [l for l in S.LEGS if l != lifted])
            res['p0'] = res['cps'][[l for l in S.LEGS if l != lifted][0]]
        else:
            b = S.solve4(robot, ang)
            res = b[0]
            sup = [l for l in S.LEGS if l != b[2]]
            res['p0'] = res['cps'][sup[0]]
        c = clearance(res, ang, pts)
        m = min(c, key=c.get)
        rows.append((name, c, res['pitch'], res['roll']))
        if c[m] < worst[0]:
            worst = (c[m], f'{name} ({m})')
    if verbose:
        print(f'--- {label}')
        for name, c, pi, ro in rows:
            print(f'  {name:28s} pitch {pi:+5.1f} roll {ro:+5.1f}  ' +
                  '  '.join(f'{l} {c[l]:5.1f}' for l in S.LEGS))
        print(f'  WORST {worst[0]:.2f} mm at {worst[1]}')
    return worst


if __name__ == '__main__':
    import spike_model as S31
    R = S.Robot()
    POSES[:] = [q for q in POSES if not q[0].startswith('sit')]
    S_v32 = S
    globals()['S'] = S31
    run(S31.Robot(), 3.0, None, 'v3.1 (tyre r 16.3, R3 inboard round, no chamfer)')
    globals()['S'] = S_v32
    run(R, 3.0, (3.5, 3.5), 'v3.2 (tyre r 17.7, 3.5 x 45 deg inboard chamfer)')
    print('note: the research "sit (8 deg)" pose (rear knees -48) puts the rear paw pods 6 mm INTO the desk in both '
          'versions - it cannot be used as written (not listed above)')
