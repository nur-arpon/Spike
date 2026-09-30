"""Desk Buddy v3.1 - walking options with cheap servos, 2026-09-29.

Builds on servo_load_check_v3_1.py (imported, not changed): same geometry, masses, reaction solver.

Physics used here: the wheels roll, so on a flat desk the desk pushes each paw straight up (plus small
inertia forces). A vertical force F at a paw that sits a horizontal distance d from the hip twists the hip by
F x d, whatever the knee does. So hip load is set by two things only: how hard a paw is loaded (4 paws down
~2-3 N, 3 paws down ~5 N on the diagonal pair) and how far the paw is from under its hip (the stride).

Gaits compared (all slow, wheels held at their stop pulse unless they roll a sliding paw):
  SKATE  all four paws stay on the desk; one leg at a time slides its paw forward on its own wheel, then all
         legs sweep back together to carry the body forward. Nothing ever lifts, so the centre of mass stays
         48 mm inside the four wheels.
  REAR   rear paws lift and step (stable by 8 mm on three legs); front paws slide on their wheels.
  CRAWL  every paw lifts in turn. A front paw can only lift after the body moves back over the rear legs
         (CAD: the centre of mass is 8 mm OUTSIDE the triangle otherwise), so every stance paw sits a
         body-shift distance ahead of its hip on top of the stride.

Run:  python servo_load_check_v3_1_walk_options.py
"""
import math
import itertools
import numpy as np
import servo_load_check_v3_1 as base

L1, L2 = base.L1, base.L2
LEGS = base.LEGS
DYN = base.DYN

# servo sets: (hip stall, knee stall) in kg.cm
SERVOS = {
    'MG90S all, 5 V':            (1.8, 1.8),
    'MG90S all, 6 V':            (2.2, 2.2),
    'MG92B hips + MG90S, 5 V':   (3.1, 1.8),
    'MG92B hips + MG90S, 6 V':   (3.5, 2.2),
    '8 x MG92B, 5 V':            (3.1, 3.1),
    '8 x MG92B, 6 V':            (3.5, 3.5),
}
HOLD = 0.35     # continuous (minutes): pods closed, clone servos
INTER = 0.55    # intermittent: a stance phase of 1-3 s, then a 4-paw rest of at least the same length
PEAK = 0.90     # the x1.5 moving peak must stay under 90 % of stall (never plan to stall)
REL_PEAK = 0.70


def ik(leg, d, H):
    """Hip and knee angles (firmware sign) that put the axle d mm ahead of the hip and H mm below it.
    Crouch branch as the firmware poses: front knees bend backwards (knee -), rear knees forwards (knee +)."""
    r = math.hypot(d, H)
    if r > L1 + L2 - 1e-6:
        return None
    s = +1 if leg[0] == 'F' else -1
    alpha = math.atan2(d, H)
    beta = math.acos((L1 ** 2 + r ** 2 - L2 ** 2) / (2 * L1 * r))
    bend = math.pi - math.acos((L1 ** 2 + L2 ** 2 - r ** 2) / (2 * L1 * L2))
    hip = math.degrees(alpha + s * beta)
    knee = math.degrees(-s * bend)
    if abs(hip) > 30 or abs(knee) > 50:
        return None
    return hip, knee


def worst(offsets, H, support, lift=None, min_force=0.0):
    """Worst hip/knee static torque (kg.cm) over every combination of stance paw offsets."""
    w = {'hip': 0.0, 'knee': 0.0, 'F': 0.0, 'n': 0, 'tip': 0}
    for combo in itertools.product(offsets, repeat=len(support)):
        ang = {}
        ok = True
        for l, d in zip(support, combo):
            a = ik(l, d, H)
            if a is None:
                ok = False
                break
            ang[l] = a
        if not ok:
            continue
        if lift:
            ang[lift] = ik(lift, 0.0, H - 12) or (0, 0)      # swing leg folded up
        res, info = base.solve_pose(ang, support=support)
        if info['tips'] or min(res[l]['Fn'] for l in support) < min_force:
            w['tip'] += 1
            continue
        w['n'] += 1
        for l in support:
            w['hip'] = max(w['hip'], base.kgcm(res[l]['hip']))
            w['knee'] = max(w['knee'], base.kgcm(res[l]['knee']))
            w['F'] = max(w['F'], res[l]['Fn'])
    return w


def body_shift_for_front_lift(H, margin_N=0.8):
    """How far every stance paw must sit ahead of its hip before a front paw can lift (the body moved back)."""
    for s in np.arange(0, 45, 0.5):
        res = worst([s], H, ['FR', 'BL', 'BR'], lift='FL', min_force=margin_N)
        if res['n']:
            return float(s)
    return None


def verdict(static, stall):
    dyn = static * DYN
    if static <= HOLD * stall and dyn <= REL_PEAK * stall:
        return 'reliable'
    if static <= INTER * stall and dyn <= PEAK * stall:
        return 'marginal'
    return 'no'


def main():
    print('Desk Buddy v3.1 walking options  (torques in kg.cm, static; moving peak = x1.5)')
    print(f'limits: reliable = static <= {HOLD:.0%} of stall and peak <= {REL_PEAK:.0%}; '
          f'marginal (intermittent) = static <= {INTER:.0%} and peak <= {PEAK:.0%}; else no')
    H_LIST = (82.0, 80.0, 76.0)  # stance height hip->axle (straight leg = 83)
    cases = []
    for H in H_LIST:
        for D in (6.0, 10.0, 15.0):
            offs = (-D, 0.0, D)
            if any(ik(l, d, H) is None for l in LEGS for d in offs):
                print(f'H {H:.0f}: a paw +-{D:.0f} mm from its hip is out of reach (joint limits / leg length)')
                continue
            cases.append((f'SKATE  H{H:.0f} paw +-{D:.0f} mm', worst(offs, H, LEGS)))
            r = worst(offs, H, ['FL', 'FR', 'BR'], lift='BL', min_force=0.3)
            r2 = worst(offs, H, ['FL', 'FR', 'BL'], lift='BR', min_force=0.3)
            cases.append((f'REAR   H{H:.0f} paw +-{D:.0f} mm',
                          {k: max(r[k], r2[k]) for k in ('hip', 'knee', 'F', 'n', 'tip')}))
        s = body_shift_for_front_lift(H)
        print(f'\nH {H:.0f}: a front paw can lift (0.8 N left on the lightest paw) once the stance paws sit '
              f'{s} mm ahead of their hips')
        if s is not None:
            reach = [d for d in (s - 10, s - 6, s, s + 6, s + 10)
                     if all(ik(l, d, H) is not None for l in ('FR', 'BL', 'BR'))]
            print(f'  reachable stance paw offsets with that shift: {reach} (the stride has to fit in here)')
            r = worst(reach, H, ['FR', 'BL', 'BR'], lift='FL', min_force=0.3)
            cases.append((f'CRAWL  H{H:.0f} shift {s:.0f}, {min(reach):.0f}..{max(reach):.0f}', r))

    print(f'\n{"gait":34s} {"paw N":>5s} {"hip":>5s} {"knee":>5s}   ' +
          '  '.join(f'{k[:22]:>22s}' for k in SERVOS))
    for name, r in cases:
        if not r['n']:
            print(f'{name:34s}  no stable combination')
            continue
        v = []
        for hs, ks in SERVOS.values():
            vh, vk = verdict(r['hip'], hs), verdict(r['knee'], ks)
            order = ['reliable', 'marginal', 'no']
            v.append(max(vh, vk, key=order.index) + f' ({r["hip"] / hs:.0%}/{r["knee"] / ks:.0%})')
        print(f'{name:34s} {r["F"]:5.2f} {r["hip"]:5.2f} {r["knee"]:5.2f}   ' + '  '.join(f'{x:>22s}' for x in v))
    print('\n(percent = static torque / stall, hip/knee)')

    # propulsion and wheel holding
    m = base.M_TOTAL / 1000
    for a in (0.05, 0.2):
        F = m * a / 4
        print(f'body acceleration {a} m/s2: {F:.3f} N per paw -> hip +{F * 99.3 / 1000 / base.KGCM:.3f} kg.cm, '
              f'wheel hold {F * base.TYRE_R / 1000 / base.KGCM:.4f} kg.cm')


if __name__ == '__main__':
    main()
