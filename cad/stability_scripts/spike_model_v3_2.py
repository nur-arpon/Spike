"""Spike (Desk Buddy v3.1) full 3-D quasi-static model for stability research (scratch, not a project file).

Geometry and masses are the same as cad/servo_load_check_v3_1.py (imported read-only), but this model:
  * finds the body attitude from the three support paws (pitch AND roll), with the tyre contact taken in
    the wheel plane (a thin tyre on a rolled body touches in its own plane),
  * measures the stability margin as the CoM's distance inside the support triangle, in the desk plane,
  * takes any leg angles (not only the firmware crouch branch), extra masses (ballast, tail tip) and a
    CoM shift of the body,
  * checks the paw-pod corners against the desk (roll brings the inboard pod edge down).
Frame: x lateral (+ = robot's left, FL/BL at x +81.2), y up, z forward. mm, g, N; torques N.mm.
"""
import math, sys
import numpy as np
sys.path.insert(0, r'D:\Claude-Projects\RobotCompanion\cad')
import servo_load_check_v3_2 as P   # v3.2 copy: constants only

G = 9.81
KGCM = 98.0665                      # N.mm per kg.cm
LEGS = ['FL', 'FR', 'BL', 'BR']
HIP_Y, L1, L2, TYRE_R = P.HIP_Y, P.L1, P.L2, P.TYRE_R
HIP_Z = dict(P.HIP_Z)
FOOT_X = dict(P.FOOT_X)
M_LEG = P.M_LEG
M_TOTAL0 = P.M_TOTAL
COM_BODY0 = P.COM_BODY.copy()
M_BODY0 = P.M_BODY

# paw pod underside corners relative to the axle, in the shin frame: (inboard mm, along-shin mm below axle, fore-aft)
# pod bottom = axle - POD_Y (8.4) with R3-R4 rounding; spans inboard 2..40 mm from the tyre plane, z -8..+19.
POD_CORNERS = [(din, -7.9, dz) for din in (2.0, 40.0) for dz in (-8.0, 19.0)]


class Robot:
    def __init__(self, extra=(), com_shift=(0.0, 0.0, 0.0), mass_delta_body=0.0, tail_mass=0.0, tail_r=38.0):
        """extra: [(g, (x, y, z))] fixed extra masses in the body frame.
        com_shift: move the BODY-only CoM by this vector (mm) (e.g. head moved back).
        tail_mass: grams at the tail, tail_r mm along the tail from the root (tail rises 20 deg, pivot z -62)."""
        self.extra = list(extra)
        self.M_body = M_BODY0 + mass_delta_body
        self.com_body = COM_BODY0 + np.array(com_shift)
        self.tail_mass, self.tail_r = tail_mass, tail_r
        self.M = self.M_body + 4 * M_LEG + sum(m for m, _ in self.extra) + tail_mass

    def tail_point(self, ang_deg):
        # tail root underside starts 6.5 mm behind the pivot (z -68.5, y 51.8), rises 20 deg rearward;
        # the ballast sits mid-thickness, ~4 mm above the underside.
        a = math.radians(ang_deg)
        r_h = 6.5 + self.tail_r * math.cos(math.radians(20))
        y = 51.8 + self.tail_r * math.sin(math.radians(20)) + 4.0
        return np.array([r_h * math.sin(a), y, -62.0 - r_h * math.cos(a)])


def leg_points(leg, hip, knee):
    zh = HIP_Z[leg]
    h, t = math.radians(hip), math.radians(hip + knee)
    hipP = np.array([HIP_Y, zh])
    kneeP = hipP + L1 * np.array([-math.cos(h), math.sin(h)])
    axleP = kneeP + L2 * np.array([-math.cos(t), math.sin(t)])
    perp_t = np.array([math.sin(h), math.cos(h)])
    perp_s = np.array([math.sin(t), math.cos(t)])
    thigh_c = hipP + 0.5 * (kneeP - hipP)
    knee_sv = kneeP + P.CASE_OFF * P.KNEE_DZ[leg] * perp_t
    shin_c = kneeP + 0.5 * (axleP - kneeP)
    wheel_sv = axleP + P.CASE_OFF * P.PAW_DZ * perp_s
    return dict(hip=hipP, knee=kneeP, axle=axleP, t=t,
                thigh=[(P.M_THIGH_SHELL, thigh_c), (P.M_KNEE_SERVO, knee_sv)],
                shin=[(P.M_SHIN_SHELL, shin_c), (P.M_WHEEL_SERVO, wheel_sv), (P.M_WHEEL, axleP)])


def to3(leg, yz):
    return np.array([FOOT_X[leg], yz[0], yz[1]])


def contact_point(leg, axle3, n):
    """Lowest point of the tyre circle (wheel plane = body y-z plane at the tyre x) for desk normal n."""
    d = -n - np.dot(-n, [1, 0, 0]) * np.array([1.0, 0, 0])
    nd = np.linalg.norm(d)
    d = d / nd if nd > 1e-9 else np.array([0, -1.0, 0])
    return axle3 + TYRE_R * d


def plane_from(points):
    """Plane through 3 points: returns (n, p0) with n pointing +y (up, body frame)."""
    p0, p1, p2 = points
    n = np.cross(p1 - p0, p2 - p0)
    n /= np.linalg.norm(n)
    if n[1] < 0:
        n = -n
    return n, p0


def solve(robot, angles, support, tail_deg=0.0, knee_lim=50.0):
    """angles {leg: (hip, knee)}; support: 3 legs. Returns dict with margin, reactions, torques, attitude."""
    PL = {l: leg_points(l, *angles[l]) for l in LEGS}
    axles = {l: to3(l, PL[l]['axle']) for l in LEGS}
    # iterate the plane: contacts depend on n (tyre in its own plane)
    n = np.array([0, 1.0, 0])
    for _ in range(2):
        cps = {l: contact_point(l, axles[l], n) for l in LEGS}
        n, p0 = plane_from([cps[l] for l in support])
    cps = {l: contact_point(l, axles[l], n) for l in LEGS}
    # masses
    masses = [(robot.M_body, robot.com_body)] + list(robot.extra)
    if robot.tail_mass:
        masses.append((robot.tail_mass, robot.tail_point(tail_deg)))
    for l in LEGS:
        for m, p in PL[l]['thigh'] + PL[l]['shin']:
            masses.append((m, to3(l, p)))
    M = sum(m for m, _ in masses)
    com = sum(m * np.asarray(p) for m, p in masses) / M
    W = M / 1000 * G
    gdir = -n
    # in-plane basis
    e1 = np.cross(n, [0, 0, 1.0]); e1 /= np.linalg.norm(e1)      # lateral in the desk plane
    e2 = np.cross(e1, n)                                          # fore-aft in the desk plane
    h_com = np.dot(com - p0, n)
    cproj = com - h_com * n
    P2 = {l: np.array([np.dot(cps[l] - p0, e1), np.dot(cps[l] - p0, e2)]) for l in support}
    c2 = np.array([np.dot(cproj - p0, e1), np.dot(cproj - p0, e2)])
    pts = [P2[l] for l in support]
    margin = 1e9
    for i in range(3):
        a, b, c = pts[i], pts[(i + 1) % 3], pts[(i + 2) % 3]
        e = b - a
        nn = np.array([-e[1], e[0]]) / np.linalg.norm(e)
        if np.dot(c - a, nn) < 0:
            nn = -nn
        margin = min(margin, np.dot(c2 - a, nn))
    # reactions (statically determinate on 3 paws)
    A = np.array([[1, 1, 1], [P2[l][0] for l in support], [P2[l][1] for l in support]])
    F = np.linalg.solve(A, [W, W * c2[0], W * c2[1]])
    Fn = {l: 0.0 for l in LEGS}
    for l, f in zip(support, F):
        Fn[l] = f
    # joint torques (x-component = about the joint axis)
    tq = {}
    for l in LEGS:
        Fvec = Fn[l] * n

        def mom(pt_yz, groups):
            pt = to3(l, pt_yz)
            Mx = np.cross(cps[l] - pt, Fvec)[0]
            for m, p in groups:
                Mx += np.cross(to3(l, p) - pt, m / 1000 * G * gdir)[0]
            return Mx
        tq[l] = (mom(PL[l]['hip'], PL[l]['thigh'] + PL[l]['shin']), mom(PL[l]['knee'], PL[l]['shin']))
    # clearances: 4th paw above the desk, pod corners, belly
    lifted = [l for l in LEGS if l not in support]
    lift_h = {l: np.dot(cps[l] - p0, n) for l in lifted}
    pod = {}
    for l in LEGS:
        t = PL[l]['t']
        sgn = -1.0 if FOOT_X[l] > 0 else 1.0     # inboard direction
        worst = 1e9
        for din, dy, dz in POD_CORNERS:
            # shin frame: along-shin (down) = (-cos t, sin t) in (y, z); perpendicular (fore) = (sin t, cos t)
            y = PL[l]['axle'][0] + (-dy) * (-math.cos(t)) + dz * math.sin(t)
            z = PL[l]['axle'][1] + (-dy) * math.sin(t) + dz * math.cos(t)
            p3 = np.array([FOOT_X[l] + sgn * din, y, z])
            worst = min(worst, np.dot(p3 - p0, n))
        pod[l] = worst
    belly = min(np.dot(np.array([x, 0.0, z]) - p0, n) for x in (-40, 40) for z in (-72, 72))
    pitch = math.degrees(math.atan2(n[2], n[1]))    # + = nose up (desk normal leans forward in body frame)
    roll = math.degrees(math.atan2(-n[0], n[1]))    # + = left side up? (n leans to -x when the left is high)
    return dict(margin=margin, Fn=Fn, tq=tq, com=com, h_com=h_com, pitch=pitch, roll=roll, n=n, lift_h=lift_h,
                pod=pod, belly=belly, M=M, cps=cps, c2=c2, P2=P2)


def solve4(robot, angles, tail_deg=0.0):
    """Four-paw stance: find which tripod(s) it rests on. Returns the resting solution with its 4th-paw gap.
    For a coplanar set, the paw loads use the equal-spring (minimum-norm) split like the project model."""
    best = None
    for lift in LEGS:
        sup = [l for l in LEGS if l != lift]
        r = solve(robot, angles, sup, tail_deg)
        gap = r['lift_h'][lift]
        if gap >= -0.3 and r['margin'] >= -1e-6:
            if best is None or gap < best[1]:
                best = (r, gap, lift)
    return best


def margin4(robot, angles, tail_deg=0.0):
    """Four-paw margin (distance of the CoM from the support quadrilateral), level-ish stance."""
    r = solve(robot, angles, ['FR', 'BL', 'BR'], tail_deg)
    pts = {l: r['cps'][l] for l in LEGS}
    n = r['n']; p0 = pts['FR']
    e1 = np.cross(n, [0, 0, 1.0]); e1 /= np.linalg.norm(e1); e2 = np.cross(e1, n)
    q = {l: np.array([np.dot(pts[l] - p0, e1), np.dot(pts[l] - p0, e2)]) for l in LEGS}
    c = np.array([np.dot(r['com'] - r['h_com'] * n - p0, e1), np.dot(r['com'] - r['h_com'] * n - p0, e2)])
    order = ['FL', 'FR', 'BR', 'BL']
    m = 1e9
    cen = sum(q.values()) / 4
    for i in range(4):
        a, b = q[order[i]], q[order[(i + 1) % 4]]
        e = b - a; nn = np.array([-e[1], e[0]]) / np.linalg.norm(e)
        if np.dot(cen - a, nn) < 0: nn = -nn
        m = min(m, np.dot(c - a, nn))
    return m, r


def kg(nmm):
    return nmm / KGCM


if __name__ == '__main__':
    R = Robot()
    st = {l: (0.0, 0.0) for l in LEGS}
    print(f'M {R.M:.1f} g, leg {M_LEG:.1f} g, body CoM {COM_BODY0.round(1)}')
    for lift in LEGS:
        r = solve(R, st, [l for l in LEGS if l != lift])
        print(f'stand, lift {lift}: margin {r["margin"]:+.1f} mm (report {"-8.4" if lift[0]=="F" else "+8.4"}), '
              f'CoM height {r["h_com"]:.1f}')
    m, r = margin4(R, st)
    print(f'stand 4-paw margin {m:.1f} (report 48.8 inside)')
