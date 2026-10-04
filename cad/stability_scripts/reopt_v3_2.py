"""v3.2: re-optimise the key lift poses (optimize.py, unchanged) for the v3.2 mass / centre of mass / tyre, so
v3.1 and v3.2 are compared at their OWN best angles (the research keyframes were tuned for v3.1's CoM).
Same targets for every robot: FL lift 12 mm (gait, margin 8), give-paw FL 30 mm up with the axle 12 mm ahead
of the hip (margin 8), crossing (FL still touching, gap <= 1 mm).
Run: python reopt_v3_2.py [v31|v32|v32nb]
"""
import sys
sys.path.insert(0, r'D:\Claude-Projects\RobotCompanion\cad\stability_scripts')
sys.path.insert(0, r'D:\Claude-Projects\RobotCompanion\cad')
which = sys.argv[1] if len(sys.argv) > 1 else 'v32'
if which.startswith('v32'):
    import spike_model_v3_2 as M
    sys.modules['spike_model'] = M          # optimize.py imports spike_model: give it the v3.2 model
else:
    import spike_model as M
import optimize as O

R = M.Robot()
if which == 'v32nb':                         # v3.2 without the ballast slugs
    P = M.P
    R = M.Robot(extra=[(-P.BALLAST_G / 2, tuple(p)) for p in P.BALLAST_POS])
print(f'=== {which}: mass {R.M:.0f} g')
cases = [('lift FL 12 mm (gait), margin 8', dict(lift='FL', margin=8, gap_min=12)),
         ('give paw FL 30 mm, axle 12 ahead, margin 8', dict(lift='FL', margin=8, gap_min=30, fwd_paw=12)),
         ('crossing (FL touching), margin 0.8', dict(lift='FL', margin=0.8, gap_min=0.0, gap_max=1.0))]
for tag, kw in cases:
    lift = kw.pop('lift'); margin = kw.pop('margin')
    ang, r, peak, pen = O.optimise(R, lift, margin, **kw)
    O.report(f'[{which}] {tag}', ang, r, peak, pen, lift)
