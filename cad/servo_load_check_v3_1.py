"""Desk Buddy v3.1 - servo load check (static + dynamic factor), 2026-09-29.

Read-only analysis. Inputs come from:
  build_v3_1_report.txt  total 983 g, CoM x +0.2 / y 25.5 / z +17.2 (body frame, legs straight)
  build_print_parts_v3_1.py  HIP_Y 18, L1 38 (thigh), L2 45 (shin), LEGS front z +66 / rear z -52,
                             TYRE_R 16.3, WHEEL_IN 77.2 (+4 = tyre centre plane 81.2), SV_L/SV_SHAFT (case offset 5.4),
                             KNEE_DZ (front knee case forward, rear rearward), PAW_DZ +1
  software/firmware/lib/spike_body  POSES, HIP +-30, KNEE +-50, tail +-45, drive speeds
  printed masses: the 2-wall column of build_v3_1_report.txt (the chosen profile)

Frame: x lateral, y up, z forward (toward the head). Units: mm, g, N; torques printed in kg.cm.
Joint sign (firmware): + = foot forward. Knee angle is relative to the thigh; shin tilt = hip + knee.

Run:  python servo_load_check_v3_1.py
"""
import math
import numpy as np

G = 9.81
KGCM = 0.0980665          # 1 kg.cm = 0.0981 N.m = 98.07 N.mm

# ---------------- geometry (build_print_parts_v3_1.py) ----------------
HIP_Y, L1, L2, TYRE_R = 18.0, 38.0, 45.0, 16.3
HIP_Z = {'FL': 66.0, 'FR': 66.0, 'BL': -52.0, 'BR': -52.0}
FOOT_X = {'FL': +81.2, 'BL': +81.2, 'FR': -81.2, 'BR': -81.2}   # tyre centre plane (WHEEL_IN 77.2 + 4)
CASE_OFF = 22.8 / 2 - 6.0                                         # 5.4 mm: servo case centre from its shaft
KNEE_DZ = {'FL': +1, 'FR': +1, 'BL': -1, 'BR': -1}
PAW_DZ = +1
LEGS = ['FL', 'FR', 'BL', 'BR']

# ---------------- masses (build_v3_1_report.txt, 2-wall profile) ----------------
M_TOTAL = 983.0
COM_STAND = np.array([0.2, 25.5, 17.2])
MG90S = 13.4                                   # TowerPro datasheet
# thigh group moves with the hip: outer 7.3 + cover 7.2 + knee MG90S + hip cap 0.2 + horn/screws ~2.0
M_THIGH_SHELL, M_KNEE_SERVO = 7.3 + 7.2 + 0.2 + 2.0, MG90S
# shin group moves with the knee: outer 9.0 + cover 8.1 + caps 0.5 + horns/screws ~2.5 + wheel 2.9 + O-ring 0.6
M_SHIN_SHELL, M_WHEEL_SERVO, M_WHEEL = 9.0 + 8.1 + 0.5 + 2.5, MG90S, 2.9 + 0.6
M_LEG = M_THIGH_SHELL + M_KNEE_SERVO + M_SHIN_SHELL + M_WHEEL_SERVO + M_WHEEL

# ---------------- servo ratings ----------------
STALL_4V8 = 1.8        # kg.cm, TowerPro MG90S datasheet (2.2 at 6.0 V)
STALL_6V0 = 2.2
HOLD_FRAC = 0.35       # continuous-hold limit as a fraction of stall (see the .md for why 35 %)
DYN = 1.5              # dynamic factor for motion
I_STALL = 0.8          # A per MG90S at ~5 V (vendors: 0.7-1.0 A; 750 mA +-10 %)
I_IDLE = 0.01

MU_TYRE = 0.6          # nitrile O-ring on a laminate / wood desk (0.4-0.8)
C_RR = 0.03            # rolling resistance, small hard-cored O-ring tyre (conservative)


def leg_points(leg, hip, knee):
    """Body-frame (y, z) of hip, knee, axle and the segment mass centres for one leg."""
    zh = HIP_Z[leg]
    h, t = math.radians(hip), math.radians(hip + knee)
    hipP = np.array([HIP_Y, zh])
    kneeP = hipP + L1 * np.array([-math.cos(h), math.sin(h)])
    axleP = kneeP + L2 * np.array([-math.cos(t), math.sin(t)])
    perp_t = np.array([math.sin(h), math.cos(h)])      # thigh-normal (points +z when straight)
    perp_s = np.array([math.sin(t), math.cos(t)])
    thigh_c = hipP + 0.5 * (kneeP - hipP)
    knee_sv = kneeP + CASE_OFF * KNEE_DZ[leg] * perp_t
    shin_c = kneeP + 0.5 * (axleP - kneeP)
    wheel_sv = axleP + CASE_OFF * PAW_DZ * perp_s
    return dict(hip=hipP, knee=kneeP, axle=axleP,
                thigh=[(M_THIGH_SHELL, thigh_c), (M_KNEE_SERVO, knee_sv)],
                shin=[(M_SHIN_SHELL, shin_c), (M_WHEEL_SERVO, wheel_sv), (M_WHEEL, axleP)])


def to3(leg, yz):
    return np.array([FOOT_X[leg], yz[0], yz[1]])


# body-only CoM (legs straight at the reference = the report's CoM)
_ref = {l: leg_points(l, 0, 0) for l in LEGS}
_leg_moment = sum(m * to3(l, p) for l in LEGS for m, p in _ref[l]['thigh'] + _ref[l]['shin'])
M_BODY = M_TOTAL - 4 * M_LEG
COM_BODY = (M_TOTAL * COM_STAND - _leg_moment) / M_BODY


def solve_pose(angles, support=LEGS, drive=None):
    """angles: {leg: (hip, knee)}. Returns per-leg dict of hip/knee static torques (N.mm), forces, flags.
    drive: {leg: Fz_N} horizontal (fore-aft) tyre force at each contact, in the desk plane."""
    P = {l: leg_points(l, *angles[l]) for l in LEGS}
    axles = np.array([to3(l, P[l]['axle']) for l in support])
    # desk plane through the supporting axles (least squares), normal pointing up in the body frame
    A = np.c_[axles[:, 0], axles[:, 2], np.ones(len(axles))]
    a, b, c = np.linalg.lstsq(A, axles[:, 1], rcond=None)[0]     # y = a x + b z + c
    n = np.array([-a, 1.0, -b]); n /= np.linalg.norm(n)          # up = against gravity
    gdir = -n
    contacts = {l: to3(l, P[l]['axle']) - TYRE_R * n for l in LEGS}
    # whole-robot CoM
    masses = [(M_BODY, COM_BODY)] + [(m, to3(l, p)) for l in LEGS for m, p in P[l]['thigh'] + P[l]['shin']]
    com = sum(m * p for m, p in masses) / M_TOTAL
    W = M_TOTAL / 1000 * G
    # reactions along n: minimum-norm solution of force + 2 moment equilibria (plate on equal springs)
    e1 = np.cross(n, [1, 0, 0]); e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    rows = [[1.0] * len(support),
            [np.dot(contacts[l] - com, e1) for l in support],
            [np.dot(contacts[l] - com, e2) for l in support]]
    F = np.linalg.pinv(np.array(rows)) @ np.array([W, 0, 0])
    Fn = {l: 0.0 for l in LEGS}
    for l, f in zip(support, F):
        Fn[l] = f
    tips = min(F) < -1e-6
    # fore-aft direction in the desk plane
    fwd = np.array([0, 0, 1.0]) - np.dot([0, 0, 1.0], n) * n; fwd /= np.linalg.norm(fwd)
    out = {}
    for l in LEGS:
        Fvec = Fn[l] * n + (drive.get(l, 0.0) * fwd if drive else 0)
        def moment_about(pt_yz, groups):
            pt = to3(l, pt_yz)
            M = np.cross(contacts[l] - pt, Fvec)[0]
            for m, p in groups:
                M += np.cross(to3(l, p) - pt, m / 1000 * G * gdir)[0]
            return abs(M)
        out[l] = dict(Fn=Fn[l],
                      hip=moment_about(P[l]['hip'], P[l]['thigh'] + P[l]['shin']),
                      knee=moment_about(P[l]['knee'], P[l]['shin']))
    pitch = math.degrees(math.atan2(n[2], n[1]))
    roll = math.degrees(math.atan2(n[0], n[1]))
    return out, dict(tips=tips, com=com, pitch=pitch, roll=roll, n=n)


# ---------------- firmware poses (spike_body.cpp POSES, order FL FR BL BR) ----------------
FW = {
    'stand':        ((0, 0, 0, 0), (0, 0, 0, 0)),
    'sit':          ((-4, -4, -25, -25), (0, 0, 50, 50)),
    'lie / park':   ((25, 25, -25, -25), (-50, -50, 50, 50)),
    'play bow':     ((25, 25, 0, 0), (-50, -50, 0, 0)),
    'lean left':    ((14, 0, -14, 0), (-28, 0, 28, 0)),
    'lean right':   ((0, 14, 0, -14), (0, -28, 0, 28)),
    'lean forward': ((14, 14, 0, 0), (-28, -28, 0, 0)),
}


def fw_angles(name, frac=1.0):
    hips, knees = FW[name]
    return {l: (hips[i] * frac, knees[i] * frac) for i, l in enumerate(LEGS)}


def worst_over_transition(name, **kw):
    """Max torque per joint over the blend stand -> pose (the firmware smoothsteps between them)."""
    best = None
    for s in np.linspace(0, 1, 21):
        res, info = solve_pose(fw_angles(name, s), **kw)
        if best is None:
            best, binfo = {l: dict(res[l]) for l in LEGS}, info
        for l in LEGS:
            for k in ('hip', 'knee', 'Fn'):
                best[l][k] = max(best[l][k], res[l][k])
        binfo = info if s == 1 else binfo
    return best, binfo


def kgcm(nmm):
    return nmm / 1000 / KGCM


def verdict(static_kgcm, stall):
    dyn = static_kgcm * DYN
    if static_kgcm <= HOLD_FRAC * stall and dyn <= 0.7 * stall:
        return 'OK'
    if static_kgcm <= 0.5 * stall and dyn <= stall:
        return 'MARGINAL'
    return 'OVERLOAD'


def main():
    stall = STALL_4V8
    W = M_TOTAL / 1000 * G
    print(f'Desk Buddy v3.1 servo load check   mass {M_TOTAL:.0f} g (W = {W:.2f} N)')
    print(f'  leg below the hip {M_LEG:.1f} g x 4, body {M_BODY:.0f} g, body CoM z {COM_BODY[2]:+.1f} y {COM_BODY[1]:.1f}')
    print(f'  MG90S stall {STALL_4V8} kg.cm at 4.8 V ({STALL_6V0} at 6.0 V); hold limit {HOLD_FRAC:.0%} of stall = '
          f'{HOLD_FRAC * stall:.2f} kg.cm; dynamic factor {DYN}')
    print('  columns: static / x1.5 dynamic torque (kg.cm), stall margin = stall / dynamic, '
          'hold margin = hold limit / static')
    rows = []   # (case, joint, static kg.cm, foot load N)

    def add(case, res, legs=LEGS):
        for l in legs:
            for j in ('hip', 'knee'):
                rows.append((case, f'{j} {l}', kgcm(res[l][j]), res[l]['Fn']))

    # 1. firmware poses, worst over the stand -> pose blend
    print('\nFIRMWARE POSES (body attitude at the end pose; foot loads in N)')
    for name in FW:
        res, info = worst_over_transition(name)
        print(f'  {name:13s} pitch {info["pitch"]:+5.1f} deg roll {info["roll"]:+5.1f} deg  CoM z {info["com"][2]:+5.1f}  '
              + '  '.join(f'{l} {res[l]["Fn"]:.2f}' for l in LEGS) + ('  TIPS' if info['tips'] else ''))
        add(name, res)

    # 2. three legs carry the load (one paw lifted, stand pose)
    print('\nONE PAW LIFTED (stand pose, three legs carry the robot)')
    for lift in LEGS:
        sup = [l for l in LEGS if l != lift]
        res, info = solve_pose(fw_angles('stand'), support=sup)
        tag = 'TIPS OVER (CoM outside the triangle)' if info['tips'] else 'stable'
        print(f'  lift {lift}: ' + '  '.join(f'{l} {res[l]["Fn"]:.2f} N' for l in sup) + f'   {tag}')
        if not info['tips']:
            add(f'lift {lift} (stand)', res, sup)

    # 3. crawl envelope: gait.py is not in the project, so assume a stride of hip +-H with the shin tilt at
    #    the CAD gait limits (-9.9 .. +19.8 deg); every combination of support-leg postures, tipping ones dropped
    for H in (10, 20):
        post = [(h, t - h) for h in (-H, 0, H) for t in (-9.9, 0, 19.8)]
        worst = {}
        for lift in ('BL', 'BR'):          # only the rear lifts are statically stable (report: front -8 mm)
            sup = [l for l in LEGS if l != lift]
            for a in post:
                for b in post:
                    for c in post:
                        ang = {lift: (0, 0)}
                        ang.update(dict(zip(sup, (a, b, c))))
                        res, info = solve_pose(ang, support=sup)
                        if info['tips']:
                            continue
                        for l in sup:
                            for j in ('hip', 'knee'):
                                key = ('front' if l[0] == 'F' else 'rear') + ' ' + j
                                if res[l][j] > worst.get(key, (0,))[0]:
                                    worst[key] = (res[l][j], res[l]['Fn'])
        for key in sorted(worst):
            v, fn = worst[key]
            rows.append((f'crawl, stride hip +-{H}', key, kgcm(v), fn))

    # 4. spin in place (zoomies, happy-dance wiggle): skid steer, lateral scrub resisted by the tyres
    res0, info0 = solve_pose(fw_angles('stand'))
    com = info0['com']
    scrub = sum(MU_TYRE * res0[l]['Fn'] * abs(HIP_Z[l] - com[2]) for l in LEGS)   # N.mm
    Fd = scrub / sum(abs(FOOT_X[l]) for l in LEGS)                                 # N per tyre
    drive = {l: (Fd if FOOT_X[l] > 0 else -Fd) for l in LEGS}
    res, _ = solve_pose(fw_angles('stand'), drive=drive)
    add(f'spin in place (mu {MU_TYRE})', res)
    wheel_spin = Fd * TYRE_R / 1000 / KGCM

    # 5. driving: instant stop (traction-limited skid) and a ramped stop
    roll_F = C_RR * W / 4
    acc_F = lambda a: (M_TOTAL / 1000) * a / 4
    res, _ = solve_pose(fw_angles('stand'), drive={l: -MU_TYRE * res0[l]['Fn'] for l in LEGS})
    add('instant wheel stop (skid)', res)
    res, _ = solve_pose(fw_angles('stand'), drive={l: -acc_F(1.5) * 4 * res0[l]['Fn'] / W for l in LEGS})
    add('ramped stop 1.5 m/s2', res)

    # table
    print(f'\n{"case":28s} {"joint":10s} {"foot N":>6s} {"static":>6s} {"dyn":>6s} {"stall x":>7s} {"hold x":>6s}  verdict')
    worst_case = None
    for case, joint, st, fn in rows:
        dyn = st * DYN
        sm = stall / dyn if dyn > 1e-9 else float('inf')
        hm = HOLD_FRAC * stall / st if st > 1e-9 else float('inf')
        v = verdict(st, stall)
        if worst_case is None or sm < worst_case[0]:
            worst_case = (sm, case, joint, st, dyn)
        print(f'{case:28s} {joint:10s} {fn:6.2f} {st:6.2f} {dyn:6.2f} {min(sm, 99):7.2f} {min(hm, 99):6.2f}  {v}')
    sm, case, joint, st, dyn = worst_case
    print(f'\nWORST: {case} / {joint}: static {st:.2f}, dynamic {dyn:.2f} kg.cm -> stall margin {sm:.2f}x '
          f'at 4.8 V, {STALL_6V0 / dyn:.2f}x at 6.0 V')

    # wheels
    v_max = (60 / 0.11) / 360 * 2 * math.pi * TYRE_R / 1000     # MG90S 360: 0.11 s/60 deg at 4.8 V
    print('\nWHEELS (MG90S 360, stall ~1.8 kg.cm)')
    print(f'  rolling resistance {roll_F:.3f} N per tyre -> {roll_F * TYRE_R / 1000 / KGCM:.3f} kg.cm')
    print(f'  accelerate 0.5 m/s2: {acc_F(0.5):.3f} N per tyre -> {acc_F(0.5) * TYRE_R / 1000 / KGCM:.3f} kg.cm')
    print(f'  spin in place: {Fd:.2f} N per tyre -> {wheel_spin:.3f} kg.cm ({wheel_spin / 1.8:.0%} of stall)')
    print(f'  traction limit per tyre (mu {MU_TYRE}): front {MU_TYRE * res0["FL"]["Fn"]:.2f} N, rear '
          f'{MU_TYRE * res0["BL"]["Fn"]:.2f} N -> a max ~{MU_TYRE * G:.1f} m/s2')
    print(f'  top speed (no load, 4.8 V) ~{v_max:.2f} m/s')

    # tail (vertical shaft: no gravity torque, inertia + speed only)
    L_tail = 0.043
    I = 1.3e-3 * L_tail ** 2 / 3 + 1.9e-3 * 0.008 ** 2
    print('\nTAIL (shaft vertical: gravity gives no torque)')
    for hz, amp in ((3.0, 30), (3.0, 35), (4.0, 40), (1.0, 15)):
        w = 2 * math.pi * hz
        acc = math.radians(amp) * w * w
        speed = math.degrees(math.radians(amp) * w)
        print(f'  wag {hz} Hz +-{amp} deg: inertia torque {I * acc / KGCM:.4f} kg.cm, peak speed {speed:.0f} deg/s '
              f'(servo max ~600 at 4.8 V) -> {"too fast, amplitude will shrink" if speed > 600 else "OK"}')

    # power
    print('\nPOWER (servo rail = Mini560 #1, 5 V, sold as 5 A)')
    for name in FW:
        res, _ = solve_pose(fw_angles(name))
        i = sum(I_IDLE + I_STALL * min(1, kgcm(res[l][j]) / stall) for l in LEGS for j in ('hip', 'knee'))
        print(f'  holding {name:13s} ~{i + 5 * I_IDLE:.2f} A')
    moving = 8 * 0.25 + 4 * 0.25 + 0.2
    startup = 8 * I_STALL + 4 * 0.25 + 0.2
    print(f'  pose change while driving (all moving, 0.25 A each) ~{moving:.1f} A')
    print(f'  8 leg servos starting in the same 20 ms (stall-current inrush) ~{startup:.1f} A')
    print(f'  all 13 stalled at 1.0 A (jam, fall) {13 * 1.0:.0f} A')
    for iout in (moving, 5.0, startup):
        ib = iout * 5.0 / 0.90 / 7.2
        print(f'  {iout:.1f} A at 5 V -> {ib:.1f} A from the pack at 7.2 V; sag at ~0.12 ohm pack+wiring '
              f'{ib * 0.12:.2f} V')


if __name__ == '__main__':
    main()
