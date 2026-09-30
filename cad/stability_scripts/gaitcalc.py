import numpy as np, itertools, json
from spike_model import Robot, solve, LEGS, kg
from optimize import optimise, report, FW
from noroll import layout, dist_pen
R=Robot()
st=solve(R,{l:(0.,0.) for l in LEGS},['FR','BL','BR']); ref=layout(st,LEGS)
brk=lambda a: 5*max(0,5-a['BR'][1])
out={}
for mode in ('roll','noroll'):
    exC=(lambda r,a: brk(a)) if mode=='roll' else (lambda r,a: brk(a)+10*dist_pen(r,ref,LEGS))
    C,rC,pC,_=optimise(R,'FL',0.8,gap_min=0.0,gap_max=0.5,lim=FW,extra=exC)
    report(f'[{mode}] C',C,rC,pC,0,'FL')
    refC=layout(rC,['FR','BL','BR'])
    exB=(lambda r,a: 0) if mode=='roll' else (lambda r,a: 10*dist_pen(r,refC,['FR','BL','BR']))
    B,rB,pB,_=optimise(R,'FL',10,gap_min=15,lim=FW,extra=exB)
    report(f'[{mode}] B',B,rB,pB,0,'FL')
    # schedule search
    def pose(s,s0,s1):
        u=min(1,max(0,(s-s0)/(1-s0))); v=min(1,max(0,(s-s1)/(1-s1))); a={}
        for l in LEGS:
            t=u if l in ('FR','BL') else (v if l=='FL' else min(1,s/0.6))
            a[l]=(C[l][0]+(B[l][0]-C[l][0])*t, C[l][1]+(B[l][1]-C[l][1])*t)
        return a
    best=None
    for s0 in np.arange(0,0.96,0.05):
        for s1 in np.arange(0,0.96,0.05):
            w=0; m=99
            for s in np.linspace(0,1,21):
                r=solve(R,pose(s,s0,s1),['FR','BL','BR']); g=r['lift_h']['FL']
                w=max(w,max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0,1)))
                if g>0.3: m=min(m,r['margin'])
            if best is None or (m>=0.5 and (best[1]<0.5 or w<best[0])) or (best[1]<0.5 and m>best[1]): best=(w,m,s0,s1)
    print(f'[{mode}] C->B schedule: peak {best[0]:.2f}, min margin after lift-off {best[1]:+.1f}, FR/BL ease from s={best[2]:.2f}, FL tuck from s={best[3]:.2f}, BR crouch over s 0-0.6')
    out[mode]=dict(C=C,B=B,sched=best[2:],peak=[pC,pB,best[0]])
json.dump(out,open('gait.json','w'),indent=1)
