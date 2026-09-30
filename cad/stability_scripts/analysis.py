"""Second-stage analysis: crossing states, give-paw from stand / sit, poses, variants, robustness (scratch)."""
import math, sys, json
import numpy as np
from spike_model import Robot, solve, LEGS, kg, HIP_Z, leg_points, margin4, M_BODY0, COM_BODY0
from optimize import optimise, report, FW, EXT, fmt_ang, fmt_tq, evaluate

R = Robot()
job = sys.argv[1]
out = {}


def save(name, ang, r, peak):
    out[name] = dict(ang=ang, peak=peak, margin=r['margin'], pitch=r['pitch'], roll=r['roll'],
                     Fn={l: float(r['Fn'][l]) for l in LEGS},
                     tq={l: [kg(r['tq'][l][0]), kg(r['tq'][l][1])] for l in LEGS})


if job == 'cross':
    # crossing state: FL still touching (gap 0..0.5 mm), CoM just over the FR-BL axis (margin >= 0.5)
    for lim_name, lim in (('FW', FW), ('EXT', EXT)):
        ang, r, peak, pen = optimise(R, 'FL', 0.5, gap_min=0.0, gap_max=0.5, lim=lim)
        report(f'[{lim_name}] CROSSING (FL touching, CoM over the FR-BL axis)', ang, r, peak, pen, 'FL')
        save('cross_' + lim_name, ang, r, peak)
    ang, r, peak, pen = optimise(R, 'BR', 0.5, gap_min=0.0, gap_max=0.5, lim=FW)
    report('[FW] BR crossing (reference)', ang, r, peak, pen, 'BR')

if job == 'paw':
    # give paw from a stand: FL raised >= 30 mm, axle >= 12 mm ahead of its hip
    for m in (6, 8):
        ang, r, peak, pen = optimise(R, 'FL', m, gap_min=30.0, lim=FW, fwd_paw=12.0)
        report(f'[FW] GIVE PAW from stand, margin>={m}', ang, r, peak, pen, 'FL')
        save(f'paw_stand_{m}', ang, r, peak)
    # give paw from a sit: body nose-up >= 12 deg (sit look)
    sit = lambda r, a: 5 * max(0.0, 12.0 - r['pitch'])
    for m in (6, 8):
        ang, r, peak, pen = optimise(R, 'FL', m, gap_min=30.0, lim=FW, fwd_paw=12.0, extra=sit)
        report(f'[FW] GIVE PAW from SIT (pitch>=12), margin>={m}', ang, r, peak, pen, 'FL')
        save(f'paw_sit_{m}', ang, r, peak)
    # sit with the rear legs in the firmware sit shape (hip -25 / knee +50 both): can the front paw lift?
    fix = {'BL': (-25.0, 50.0), 'BR': (-25.0, 50.0)}
    ang, r, peak, pen = optimise(R, 'FL', 0.0, gap_min=12.0, lim=FW, fix=fix)
    report('[FW] firmware-shaped sit (rear -25/+50), best FL lift: margin>=0 target', ang, r, peak, pen, 'FL')
    # and with the classic-sit look but tail-side rear legs free
    ang, r, peak, pen = optimise(R, 'FL', 8.0, gap_min=12.0, lim=EXT, fwd_paw=12.0, extra=sit)
    report('[EXT] GIVE PAW from SIT, knees +-75, margin>=8', ang, r, peak, pen, 'FL')

if job == 'variants':
    V = {
        'baseline': Robot(),
        'head 20 mm back (CoM -4.6 mm)': Robot(com_shift=(0, 0, -4.6 * 983 / M_BODY0)),
        'rump ballast 60 g at z -72': Robot(extra=[(60.0, (0.0, 20.0, -72.0))]),
        'tail-tip ballast 20 g': Robot(tail_mass=20.0),
        'lighter: -60 g off the body at its CoM': Robot(mass_delta_body=-60.0),
    }
    for name, rob in V.items():
        for m in (8,):
            ang, r, peak, pen = optimise(rob, 'FL', m, lim=FW)
            report(f'[FW] {name}: lift FL margin>={m}', ang, r, peak, pen, 'FL')
            ang2, r2, peak2, pen2 = optimise(rob, 'FL', 0.5, gap_min=0.0, gap_max=0.5, lim=FW)
            print(f'    crossing peak {peak2:.2f} kg.cm (margin {r2["margin"]:+.1f}, pen {pen2:.3f})')

if job == 'tail':
    for tm in (0.0, 20.0):
        rob = Robot(tail_mass=tm)
        st = {l: (0.0, 0.0) for l in LEGS}
        for ta in (-45, 0, 45):
            r = solve(rob, st, ['FR', 'BL', 'BR'], tail_deg=ta)
            print(f'tail mass {tm:4.1f} g, tail {ta:+d} deg: stand lift-FL margin {r["margin"]:+.2f}  CoM x {r["com"][0]:+.2f} z {r["com"][2]:+.2f}')
    # inertial reaction of a wag during a three-paw phase
    for tm in (3.0, 23.0):
        I = tm / 1000 * (0.045) ** 2
        for hz, amp in ((3.0, 30.0), (1.0, 15.0)):
            a = math.radians(amp) * (2 * math.pi * hz) ** 2
            F = tm / 1000 * a * 0.045
            print(f'tail {tm:.0f} g wag {hz} Hz +-{amp}: peak side force {F:.3f} N at ~150 mm height -> '
                  f'{F * 150:.1f} N.mm tipping moment = CoM shift {F * 150 / 9.64:.2f} mm equivalent')

if job == 'poses':
    fwp = {
        'stand': ((0, 0, 0, 0), (0, 0, 0, 0)),
        'sit': ((-4, -4, -25, -25), (0, 0, 50, 50)),
        'lie (shallow)': ((12, 12, -12, -12), (-24, -24, 24, 24)),
        'play bow': ((20, 20, 0, 0), (-40, -40, 0, 0)),
        'lean left': ((14, 0, -14, 0), (-28, 0, 28, 0)),
        'lean forward': ((14, 14, 0, 0), (-28, -28, 0, 0)),
    }
    for name, (hs, ks) in fwp.items():
        ang = {l: (hs[i], ks[i]) for i, l in enumerate(LEGS)}
        m, r = margin4(R, ang)
        peak = max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0, 1))
        print(f'FIRMWARE {name:14s}: 4-paw margin {m:5.1f}  pitch {r["pitch"]:+5.1f} roll {r["roll"]:+5.1f}  '
              f'CoM h {r["h_com"]:.0f}  peak(3-paw calc) {peak:.2f}')

# ---------------- four-paw poses ----------------
from spike_model import contact_point, to3, G as GG
from scipy.optimize import differential_evolution
from optimize import bounds_for, unpack, rear_rule_violation


def solve_4(robot, ang):
    PL = {l: leg_points(l, *ang[l]) for l in LEGS}
    ax = {l: to3(l, PL[l]['axle']) for l in LEGS}
    n = np.array([0, 1.0, 0])
    for _ in range(3):
        cps = {l: contact_point(l, ax[l], n) for l in LEGS}
        A = np.array([[cps[l][0], cps[l][2], 1.0] for l in LEGS]); y = np.array([cps[l][1] for l in LEGS])
        (a, b, c), *_ = np.linalg.lstsq(A, y, rcond=None)
        n = np.array([-a, 1.0, -b]); n /= np.linalg.norm(n)
    resid = max(abs(cps[l][1] - (a * cps[l][0] + b * cps[l][2] + c)) for l in LEGS)
    masses = [(robot.M_body, robot.com_body)] + [(m, to3(l, p)) for l in LEGS for m, p in PL[l]['thigh'] + PL[l]['shin']]
    M = sum(m for m, _ in masses); com = sum(m * np.asarray(p) for m, p in masses) / M
    W = M / 1000 * GG
    e1 = np.cross(n, [0, 0, 1.0]); e1 /= np.linalg.norm(e1); e2 = np.cross(e1, n)
    p0 = cps['FR']
    q = {l: np.array([np.dot(cps[l] - p0, e1), np.dot(cps[l] - p0, e2)]) for l in LEGS}
    hc = np.dot(com - p0, n); c2 = np.array([np.dot(com - hc * n - p0, e1), np.dot(com - hc * n - p0, e2)])
    rows = np.array([[1.0] * 4, [q[l][0] - c2[0] for l in LEGS], [q[l][1] - c2[1] for l in LEGS]])
    F = np.linalg.pinv(rows) @ np.array([W, 0, 0])
    tq = {}
    for i, l in enumerate(LEGS):
        Fv = F[i] * n
        def mom(pt, groups):
            p3 = to3(l, pt); Mx = np.cross(cps[l] - p3, Fv)[0]
            for m, pp in groups:
                Mx += np.cross(to3(l, pp) - p3, m / 1000 * GG * (-n))[0]
            return Mx
        tq[l] = (mom(PL[l]['hip'], PL[l]['thigh'] + PL[l]['shin']), mom(PL[l]['knee'], PL[l]['shin']))
    order = ['FL', 'FR', 'BR', 'BL']; cen = sum(q.values()) / 4; mg = 1e9
    for i in range(4):
        a_, b_ = q[order[i]], q[order[(i + 1) % 4]]; e = b_ - a_; nn = np.array([-e[1], e[0]]) / np.linalg.norm(e)
        if np.dot(cen - a_, nn) < 0: nn = -nn
        mg = min(mg, np.dot(c2 - a_, nn))
    pitch = math.degrees(math.atan2(n[2], n[1])); roll = math.degrees(math.atan2(-n[0], n[1]))
    return dict(tq=tq, F=dict(zip(LEGS, F)), margin=mg, h=hc, pitch=pitch, roll=roll, resid=resid, com=com, c2=c2)


def peak4(r):
    return max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0, 1))


if job == 'poses4':
    fwp = {
        'stand': ((0, 0, 0, 0), (0, 0, 0, 0)),
        'sit': ((-4, -4, -25, -25), (0, 0, 50, 50)),
        'lie (shallow)': ((12, 12, -12, -12), (-24, -24, 24, 24)),
        'play bow': ((20, 20, 0, 0), (-40, -40, 0, 0)),
        'lean left': ((14, 0, -14, 0), (-28, 0, 28, 0)),
        'lean forward': ((14, 14, 0, 0), (-28, -28, 0, 0)),
    }
    base = solve_4(R, {l: (0.0, 0.0) for l in LEGS})
    for name, (hs, ks) in fwp.items():
        ang = {l: (hs[i], ks[i]) for i, l in enumerate(LEGS)}
        r = solve_4(R, ang)
        print(f'FIRMWARE {name:14s}: margin {r["margin"]:5.1f} pitch {r["pitch"]:+5.1f} roll {r["roll"]:+5.1f} '
              f'drop {base["h"] - r["h"]:4.1f} peak {peak4(r):.2f}  ' + fmt_tq(r) + f'  resid {r["resid"]:.1f}')
    targets = {
        'sit (nose-up >= 8 deg)': lambda r: 5 * max(0, 8 - r['pitch']),
        'sit (nose-up >= 12 deg)': lambda r: 5 * max(0, 12 - r['pitch']),
        'lie (body 8 mm lower, level)': lambda r: 5 * max(0, 8 - (base['h'] - r['h'])) + 2 * abs(r['pitch']),
        'lie (body 12 mm lower, level)': lambda r: 5 * max(0, 12 - (base['h'] - r['h'])) + 2 * abs(r['pitch']),
        'play bow (nose-down >= 8 deg)': lambda r: 5 * max(0, 8 + r['pitch']),
        'play bow (nose-down >= 12 deg)': lambda r: 5 * max(0, 12 + r['pitch']),
        'head-tilt lean (roll >= 4 deg left)': lambda r: 5 * max(0, 4 - r['roll']),
        'head-tilt lean (roll >= 6 deg left)': lambda r: 5 * max(0, 6 - r['roll']),
        'lean forward (CoM 10 mm fwd)': lambda r: 5 * max(0, 10 - (r['c2'][1] - base['c2'][1])),
    }
    for name, pen_f in targets.items():
        def f(x):
            ang = unpack(x)
            r = solve_4(R, ang)
            return peak4(r) + pen_f(r) + 10 * max(0, r['resid'] - 0.3) + 5 * rear_rule_violation(ang, FW)
        res = differential_evolution(f, bounds_for(FW), seed=2, maxiter=150, popsize=15, tol=1e-7)
        ang = unpack(res.x); r = solve_4(R, ang)
        print(f'OPT {name:36s}: peak {peak4(r):.2f} pen {res.fun - peak4(r):.2f} margin {r["margin"]:5.1f} '
              f'pitch {r["pitch"]:+5.1f} roll {r["roll"]:+5.1f} drop {base["h"] - r["h"]:4.1f}')
        print(f'      angles {fmt_ang(ang)}   torque {fmt_tq(r)}')
