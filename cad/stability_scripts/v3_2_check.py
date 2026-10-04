"""v3.2 re-check of the gait / trick keyframes (stability_max_research.md) with the v3.2 mass, centre of mass and
tyre radius (servo_load_check_v3_2.py <- build_v3_2_report.txt), against v3.1 (spike_model.py, unchanged).
Prints margin (mm, in the desk plane), worst hip / knee load (kg.cm) and body pitch / roll per pose.
Run: python v3_2_check.py
"""
import sys
sys.path.insert(0, r'D:\Claude-Projects\RobotCompanion\cad\stability_scripts')
sys.path.insert(0, r'D:\Claude-Projects\RobotCompanion\cad')
import spike_model as A          # v3.1
import spike_model_v3_2 as B     # v3.2
import pod_clearance_v3_2 as C

POSES = [p for p in C.POSES if not p[0].startswith('sit')]


def table(mod, robot, label):
    print(f'--- {label}: mass {robot.M:.0f} g')
    worst = (0, '')
    for name, ang, lifted in POSES:
        ang = {k: tuple(map(float, v)) for k, v in ang.items()}
        if lifted:
            sup = [l for l in mod.LEGS if l != lifted]
            r = mod.solve(robot, ang, sup)
            m = r['margin']
        else:
            m, r = mod.margin4(robot, ang)
        tq = max(abs(v) for l in mod.LEGS for v in r['tq'][l]) / mod.KGCM
        worst = max(worst, (tq, name))
        print(f'  {name:28s} margin {m:6.1f} mm  peak {tq:.2f} kg.cm  pitch {r["pitch"]:+5.1f} roll {r["roll"]:+5.1f}')
    print(f'  WORST joint load {worst[0]:.2f} kg.cm ({worst[1]})')


if __name__ == '__main__':
    table(A, A.Robot(), 'v3.1 (spike_model.py)')
    table(B, B.Robot(), 'v3.2 WITH the 2 ballast slugs (build_v3_2_report.txt)')
    P = B.P
    if getattr(P, 'BALLAST_G', 0):
        bal = [(-P.BALLAST_G / 2, tuple(pos)) for pos in P.BALLAST_POS]
        table(B, B.Robot(extra=bal), 'v3.2 WITHOUT the ballast slugs')
