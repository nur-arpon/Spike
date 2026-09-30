"""Monte-Carlo error budget for a lift pose (scratch)."""
import sys, math
import numpy as np
from spike_model import Robot, solve, LEGS, kg

rng = np.random.default_rng(7)
POSES = {
 'FL lift, target 8 (FW limits)': ({'FL': (-28.1, -44.6), 'FR': (7.5, -17.9), 'BL': (-0.3, -4.4), 'BR': (-3.3, 48.9)}, 'FL'),
 'FL lift, target 10 (FW limits)': ({'FL': (-22.5, -46.8), 'FR': (4.3, -8.9), 'BL': (-2.1, 2.2), 'BR': (-4.0, 49.5)}, 'FL'),
 'FL lift, target 12 (FW limits)': ({'FL': (-29.6, -40.9), 'FR': (2.4, -0.8), 'BL': (-2.9, 6.5), 'BR': (-3.7, 49.1)}, 'FL'),
}
STALL = 1.8 * 0.6 * 98.0665      # realistic clone at 5 V, N.mm
SAG_DEG_PER_STALL = 4.0          # deg of position error at 100 % of stall (critique: 1-2 deg at 30-50 %)


def run(ang, lift, n=1500, com_sd=(1.0, 2.0), tilt_sd=0.7, play_sd=0.8):
    sup = [l for l in LEGS if l != lift]
    r0 = solve(Robot(), ang, sup)
    # worst-case sag direction: each joint gives way in the direction that shrinks the margin
    grad = {}
    for l in LEGS:
        for j in (0, 1):
            a = {k: list(v) for k, v in ang.items()}; a[l][j] += 0.5
            grad[(l, j)] = solve(Robot(), {k: tuple(v) for k, v in a.items()}, sup)['margin'] - r0['margin']
    res = []
    for _ in range(n):
        cx = rng.normal(0, com_sd[0]); cz = rng.normal(0, com_sd[1])
        tx, tz = rng.normal(0, tilt_sd, 2)
        h = r0['h_com']
        shift = (cx + h * math.radians(tx), 0.0, cz + h * math.radians(tz))
        rob = Robot(com_shift=tuple(s * 983 / 714.6 for s in shift))
        a2 = {}
        for l in LEGS:
            hq, kq = r0['tq'][l]
            # sag: the joint gives way in the direction of its load (sign convention: torque sign ~ angle sign)
            sh = -np.sign(grad[(l, 0)]) * SAG_DEG_PER_STALL * abs(hq) / STALL
            sk = -np.sign(grad[(l, 1)]) * SAG_DEG_PER_STALL * abs(kq) / STALL
            a2[l] = (ang[l][0] + sh + rng.normal(0, play_sd), ang[l][1] + sk + rng.normal(0, play_sd))
        res.append(solve(rob, a2, sup)['margin'])
    res = np.array(res)
    return r0['margin'], np.percentile(res, [1, 5, 50]), (res < 0).mean()


for name, (ang, lift) in POSES.items():
    for label, kw in (('uncalibrated (CoM +-2 mm sd, desk 0.7 deg sd, play 0.8 deg sd)', {}),
                      ('scale-measured CoM + IMU-levelled (CoM 0.7 sd, tilt 0.2 sd)', dict(com_sd=(0.5, 0.7), tilt_sd=0.2))):
        m0, p, fail = run(ang, lift, **kw)
        print(f'{name} | {label}: nominal {m0:+.1f}, 1%/5%/50% {p[0]:+.1f}/{p[1]:+.1f}/{p[2]:+.1f}, P(tip) {fail:.2%}')
