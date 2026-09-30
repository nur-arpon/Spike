"""Pose optimiser: minimum peak joint torque for a given stability margin (scratch)."""
import math, sys, json
import numpy as np
from scipy.optimize import differential_evolution
from spike_model import Robot, solve, LEGS, kg, HIP_Z, leg_points, margin4

FW = dict(hip=30.0, knee=50.0, rear_rule=(25.0, 45.0))      # firmware limits (spike_body.h)
EXT = dict(hip=30.0, knee=75.0, rear_rule=(25.0, 45.0))     # knee range opened to +-75 (CAD sweep needed)


def bounds_for(lim):
    b = []
    for l in LEGS:
        b += [(-lim['hip'], lim['hip']), (-lim['knee'], lim['knee'])]
    return b


def unpack(x):
    return {l: (float(x[2 * i]), float(x[2 * i + 1])) for i, l in enumerate(LEGS)}


def rear_rule_violation(ang, lim):
    v = 0.0
    rh, rk = lim['rear_rule']
    for l in ('BL', 'BR'):
        h, k = ang[l]
        if h > rh and k > rk:
            v += (k - rk)
    return v


def evaluate(robot, ang, support, tail=0.0):
    r = solve(robot, ang, support, tail)
    peak = 0.0
    for l in LEGS:
        for j in (0, 1):
            peak = max(peak, abs(r['tq'][l][j]))
    return r, peak


def optimise(robot, lift, margin, gap_min=12.0, gap_max=None, lim=FW, extra=None, seed=1, tail=0.0,
             fix=None, maxiter=150, popsize=15, fwd_paw=None):
    """lift: the raised leg (or None for 4-paw). extra(r, ang) -> penalty for pose look constraints.
    gap_max: for a 'crossing' state (lifted paw still touching)."""
    support = [l for l in LEGS if l != lift]
    bnds = bounds_for(lim)
    if fix:
        for l, (h, k) in fix.items():
            i = LEGS.index(l)
            bnds[2 * i] = (h, h + 1e-6); bnds[2 * i + 1] = (k, k + 1e-6)

    def f(x):
        ang = unpack(x)
        try:
            r, peak = evaluate(robot, ang, support, tail)
        except Exception:
            return 1e6
        pen = 0.0
        pen += 50 * max(0.0, margin - r['margin'])
        g = r['lift_h'][lift]
        pen += 20 * max(0.0, gap_min - g)
        if gap_max is not None:
            pen += 20 * max(0.0, g - gap_max)
        for l in support:
            pen += 20 * max(0.0, 1.5 - r['pod'][l])
        pen += 20 * max(0.0, 5.0 - r['belly'])
        pen += 5 * rear_rule_violation(ang, lim)
        if fwd_paw is not None:        # give-paw look: lifted axle at least this far ahead of its hip
            ax = leg_points(lift, *ang[lift])['axle'][1] - HIP_Z[lift]
            pen += 5 * max(0.0, fwd_paw - ax)
        if extra:
            pen += extra(r, ang)
        return peak / 98.0665 + pen      # kg.cm + penalties
    res = differential_evolution(f, bnds, seed=seed, maxiter=maxiter, popsize=popsize, tol=1e-7, polish=True)
    ang = unpack(res.x)
    r, peak = evaluate(robot, ang, support, tail)
    return ang, r, kg(peak), res.fun - kg(peak)


def fmt_ang(ang):
    return '  '.join(f'{l} {ang[l][0]:+5.1f}/{ang[l][1]:+5.1f}' for l in LEGS)


def fmt_tq(r):
    return '  '.join(f'{l} {kg(r["tq"][l][0]):+.2f}/{kg(r["tq"][l][1]):+.2f}' for l in LEGS)


def report(tag, ang, r, peak, pen, lift):
    print(f'{tag}: peak {peak:.2f} kg.cm  margin {r["margin"]:+.1f}  gap {r["lift_h"][lift]:.1f}  pitch {r["pitch"]:+.1f} '
          f'roll {r["roll"]:+.1f}  pen {pen:.3f}')
    print(f'    angles hip/knee: {fmt_ang(ang)}')
    print(f'    torque hip/knee: {fmt_tq(r)}')
    print(f'    paw loads N: ' + '  '.join(f'{l} {r["Fn"][l]:.2f}' for l in LEGS) +
          '   pod clear: ' + ' '.join(f'{r["pod"][l]:.1f}' for l in LEGS))


if __name__ == '__main__':
    R = Robot()
    which = sys.argv[1] if len(sys.argv) > 1 else 'fl'
    if which == 'fl':
        for lim_name, lim in (('FW', FW), ('EXT', EXT)):
            for m in (0, 4, 6, 8, 10, 12):
                ang, r, peak, pen = optimise(R, 'FL', m, lim=lim)
                report(f'[{lim_name}] lift FL, margin>={m}', ang, r, peak, pen, 'FL')
    if which == 'br':
        for m in (8, 12, 16, 20):
            ang, r, peak, pen = optimise(R, 'BR', m, lim=FW)
            report(f'[FW] lift BR, margin>={m}', ang, r, peak, pen, 'BR')
