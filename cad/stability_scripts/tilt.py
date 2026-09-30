import numpy as np
from scipy.optimize import differential_evolution
from spike_model import Robot, solve, LEGS, kg
from optimize import bounds_for, unpack, rear_rule_violation, FW, fmt_ang, fmt_tq
R=Robot()
def run(lift, gapmax, sign, cap=0.35, what='roll'):
    sup=[l for l in LEGS if l!=lift]
    def f(x):
        a=unpack(x); r=solve(R,a,sup)
        pk=max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0,1))
        g=r['lift_h'][lift]
        pen=20*max(0,pk-cap)+5*max(0,8-r['margin'])+5*max(0,g-gapmax)+5*max(0,-g)+5*rear_rule_violation(a,FW)
        pen+=sum(5*max(0,1.5-r['pod'][l]) for l in sup)
        return -sign*r[what]/10+pen
    res=differential_evolution(f,bounds_for(FW),seed=3,maxiter=150,popsize=15,tol=1e-8)
    a=unpack(res.x); r=solve(R,a,sup); pk=max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0,1))
    print(f'{what} {"+" if sign>0 else "-"} on tripod without {lift} (4th paw gap<= {gapmax}): roll {r["roll"]:+.1f} pitch {r["pitch"]:+.1f} margin {r["margin"]:+.1f} gap {r["lift_h"][lift]:.1f} peak {pk:.2f}')
    print('    ',fmt_ang(a)); print('    ',fmt_tq(r))
run('BR',0.5,+1); run('BR',0.5,-1); run('BR',30,+1); run('BR',0.5,-1,what='pitch'); run('BR',0.5,+1,what='pitch')
