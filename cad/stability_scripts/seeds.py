import json, sys
from spike_model import Robot, solve, LEGS
from optimize import optimise, FW, fmt_ang
from noroll import layout, dist_pen
from v1check import sched
out={}
for name,rob in (('baseline',Robot()),('rump60',Robot(extra=[(60.0,(0.0,20.0,-72.0))]))):
    st=solve(rob,{l:(0.,0.) for l in LEGS},['FR','BL','BR']); ref=layout(st,LEGS)
    best=None
    for seed in (5,9,11,13):
        C,rC,pC,pen=optimise(rob,'FL',0.8,gap_min=0.0,gap_max=0.5,lim=FW,seed=seed,popsize=25,extra=lambda r,a: 5*max(0,5-a['BR'][1])+10*dist_pen(r,ref,LEGS))
        if pen<0.01 and (best is None or pC<best[1]): best=(C,pC,rC)
    C,pC,rC=best; refC=layout(rC,['FR','BL','BR'])
    bb=None
    for seed in (5,9,11):
        B,rB,pB,pen=optimise(rob,'FL',8,gap_min=15,lim=FW,seed=seed,popsize=25,extra=lambda r,a: 10*dist_pen(r,refC,['FR','BL','BR']))
        if pen<0.01 and (bb is None or pB<bb[1]): bb=(B,pB,rB)
    B,pB,rB=bb
    s=sched(rob,C,B)
    print(f'{name}: crossing {pC:.2f} (pitch {rC["pitch"]:+.1f} roll {rC["roll"]:+.1f}) | lift@8 {pB:.2f} (pitch {rB["pitch"]:+.1f} roll {rB["roll"]:+.1f}, gap {rB["lift_h"]["FL"]:.0f}) | path peak {s[0]:.2f}, min margin after lift-off {s[1]:+.1f}')
    print('   C', fmt_ang(C)); print('   B', fmt_ang(B))
    out[name]=dict(C=C,B=B)
json.dump(out,open('v1.json','w'),indent=1)
