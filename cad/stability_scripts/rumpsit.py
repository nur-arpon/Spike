"""Sagittal (2-D, left = right) check of a 'real dog sit': rear paws tucked forward, rump on the desk."""
import math, numpy as np
from spike_model import Robot, leg_points, LEGS, M_LEG, TYRE_R
import servo_load_check_v3_1 as P
R = Robot()
RUMP_C = np.array([8.0, -72.0]); RUMP_R = 8.0          # R8 belly/rump edge centre (y, z), body frame
def pts(fa, ra):
    F = leg_points('FL', *fa); B = leg_points('BL', *ra)
    return F, B
def rest(fa, ra):
    F, B = pts(fa, ra)
    masses = [(R.M_body, R.com_body[1:])] + [(2 * m, p) for m, p in F['thigh'] + F['shin']] + [(2 * m, p) for m, p in B['thigh'] + B['shin']]
    M = sum(m for m, _ in masses); com = sum(m * np.asarray(p) for m, p in masses) / M
    best = None
    for ang in np.radians(np.arange(-10, 50, 0.05)):   # body pitch, + nose up
        n = np.array([math.cos(ang), math.sin(ang)])   # desk normal in body (y, z): nose-up -> normal leans forward
        cand = {'front': F['axle'] - TYRE_R * n, 'rear': B['axle'] - TYRE_R * n, 'rump': RUMP_C - RUMP_R * n}
        h = {k: np.dot(v, n) for k, v in cand.items()}
        low = min(h.values())
        touching = [k for k in h if h[k] - low < 0.3]
        t = np.array([n[1], -n[0]])                      # fore-aft in the desk plane (+ = forward)
        zc = np.dot(com, t); zs = {k: np.dot(cand[k], t) for k in touching}
        if len(touching) >= 2 and min(zs.values()) <= zc <= max(zs.values()):
            best = (ang, touching, cand, t, n, com, M, h); break
    return best, F, B
def loads(fa, ra):
    b, F, B = rest(fa, ra)
    if b is None: return None
    ang, touching, cand, t, n, com, M, h = b
    W = M / 1000 * 9.81
    zc = np.dot(com, t); z = {k: np.dot(cand[k], t) for k in touching}
    ks = sorted(touching, key=lambda k: z[k])
    lo, hi = ks[0], ks[-1]
    Fhi = W * (zc - z[lo]) / (z[hi] - z[lo]); Flo = W - Fhi
    Fk = {k: 0.0 for k in ('front', 'rear', 'rump')}; Fk[lo] = Flo; Fk[hi] = Fhi
    out = {}
    for name, L, contact in (('front', F, cand['front']), ('rear', B, cand['rear'])):
        f = Fk[name] / 2
        hip = f * (np.dot(contact - L['hip'], t)); knee = f * (np.dot(contact - L['knee'], t))
        out[name] = (hip / 98.07, knee / 98.07)
    zcom = zc; margin_fa = min(zc - z[lo], z[hi] - zc)
    return dict(pitch=math.degrees(ang), touching=touching, F=Fk, tq=out, margin=margin_fa, com=com, cand=cand, t=t, n=n, W=W)
if __name__ == '__main__':
    print('front hip/knee | rear hip/knee | pitch | on | loads N | front hip/knee kg.cm (per leg) | rear hip/knee')
    for fa in ((0, 0), (-10, 0), (-20, 0), (-25, 10)):
        for ra in ((0, 0), (10, 15), (20, 30), (25, 40), (25, 45), (30, 45)):
            r = loads(fa, ra)
            if r is None: print(fa, ra, 'no rest'); continue
            print(f'{fa} | {ra} | {r["pitch"]:5.1f} | {"+".join(r["touching"]):16s} | ' +
                  ' '.join(f'{k} {v:.1f}' for k, v in r['F'].items()) +
                  f' | {r["tq"]["front"][0]:+.2f}/{r["tq"]["front"][1]:+.2f} | {r["tq"]["rear"][0]:+.2f}/{r["tq"]["rear"][1]:+.2f}')
