"""Check the FL-lift transition path stand -> crossing C -> lift B, and the paw travel the wheels must allow."""
import math
import numpy as np
from spike_model import Robot, solve, LEGS, kg

R = Robot()
S = {l: (0.0, 0.0) for l in LEGS}
C = {'FL': (-13.7, 5.3), 'FR': (12.9, -9.4), 'BL': (18.6, -20.5), 'BR': (-5.6, -10.4)}
B = {'FL': (-22.5, -46.8), 'FR': (4.3, -8.9), 'BL': (-2.1, 2.2), 'BR': (-4.0, 49.5)}   # target-10 pose


def lerp(a, b, s):
    return {l: (a[l][0] + (b[l][0] - a[l][0]) * s, a[l][1] + (b[l][1] - a[l][1]) * s) for l in LEGS}


def world2(r, anchor='FR', ref='BL'):
    """In-plane paw coordinates with FR at the origin and FR->BL along a fixed direction."""
    n = r['n']; cps = r['cps']
    e1 = np.cross(n, [0, 0, 1.0]); e1 /= np.linalg.norm(e1); e2 = np.cross(e1, n)
    q = {l: np.array([np.dot(cps[l] - cps[anchor], e1), np.dot(cps[l] - cps[anchor], e2)]) for l in LEGS}
    d = q[ref] / np.linalg.norm(q[ref]); rot = np.array([[d[0], d[1]], [-d[1], d[0]]])
    return {l: rot @ q[l] for l in LEGS}


print('stand -> C (4 paws; loads by the FR-BL-BR tripod are only valid near C, so report margin toward FL)')
for s in np.linspace(0, 1, 6):
    a = lerp(S, C, s)
    r = solve(R, a, ['FR', 'BL', 'BR'])
    pk = max(abs(kg(r['tq'][l][j])) for l in ['FR', 'BL'] for j in (0, 1))
    print(f'  s {s:.1f}: CoM vs FR-BL axis {r["margin"]:+5.1f} mm (neg = FL still loaded), FL gap {r["lift_h"]["FL"]:+.1f}, '
          f'FR/BL peak if they carried it all {pk:.2f}')
print('C -> B (three paws FR BL BR, FL lifting)')
worst = 0
for s in np.linspace(0, 1, 11):
    a = lerp(C, B, s)
    r = solve(R, a, ['FR', 'BL', 'BR'])
    pk = max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0, 1)); worst = max(worst, pk)
    print(f'  s {s:.1f}: margin {r["margin"]:+5.1f}  FL gap {r["lift_h"]["FL"]:5.1f}  pitch {r["pitch"]:+5.1f} roll {r["roll"]:+5.1f}  peak {pk:.2f}')
print(f'  worst peak on C->B {worst:.2f}')
w0 = world2(solve(R, S, ['FR', 'BL', 'BR'])); wC = world2(solve(R, C, ['FR', 'BL', 'BR'])); wB = world2(solve(R, B, ['FR', 'BL', 'BR']))
for tag, w in (('C', wC), ('B', wB)):
    print(f'paw travel on the desk, stand -> {tag} (FR anchored, heading on the FR-BL line), fore-aft mm / lateral mm / wheel deg:')
    for l in LEGS:
        d = w[l] - w0[l]
        print(f'   {l}: {d[1]:+6.1f} / {d[0]:+5.1f}  -> wheel {math.degrees(d[1] / 16.3):+6.1f} deg')
for tag, a in (('stand', S), ('C', C), ('B', B)):
    r = solve(R, a, ['FR', 'BL', 'BR'])
    print(f'IMU at {tag}: pitch {r["pitch"]:+.1f} roll {r["roll"]:+.1f} (desk-normal in body frame; + pitch = nose up)')
