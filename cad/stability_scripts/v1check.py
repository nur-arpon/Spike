import numpy as np
from spike_model import Robot, solve, LEGS, kg
from optimize import optimise, report, FW
from noroll import layout, dist_pen
def sched(R,C,B):
    best=None
    for s0 in np.arange(0,0.96,0.05):
        for s1 in np.arange(0,0.96,0.05):
            w=0; m=99
            for s in np.linspace(0,1,21):
                u=min(1,max(0,(s-s0)/(1-s0))); v=min(1,max(0,(s-s1)/(1-s1))); a={}
                for l in LEGS:
                    t=u if l in ('FR','BL') else (v if l=='FL' else min(1,s/0.6))
                    a[l]=(C[l][0]+(B[l][0]-C[l][0])*t, C[l][1]+(B[l][1]-C[l][1])*t)
                r=solve(R,a,['FR','BL','BR']); g=r['lift_h']['FL']
                w=max(w,max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0,1)))
                if g>0.3: m=min(m,r['margin'])
            if best is None or (m>=0.5 and (best[1]<0.5 or w<best[0])) or (best[1]<0.5 and m>best[1]): best=(w,m,s0,s1)
    return best
R=Robot()
C={'FL':(12.1,-8.1),'FR':(2.1,11.5),'BL':(0.3,14.5),'BR':(-2.2,19.8)}
B={'FL':(-24.7,-47.8),'FR':(2.8,6.8),'BL':(2.3,6.3),'BR':(-18.7,49.3)}
print('v1 margin-8 pair schedule: peak %.2f minmargin %.1f s0 %.2f s1 %.2f'%sched(R,C,B))
for name,rob in (('rump 60 g',Robot(extra=[(60.0,(0.0,20.0,-72.0))])),('head back 20',Robot(com_shift=(0,0,-4.6*983/714.6)))):
    st=solve(rob,{l:(0.,0.) for l in LEGS},['FR','BL','BR']); ref=layout(st,LEGS)
    Cx,rC,pC,_=optimise(rob,'FL',0.8,gap_min=0.0,gap_max=0.5,lim=FW,extra=lambda r,a: 5*max(0,5-a['BR'][1])+10*dist_pen(r,ref,LEGS))
    refC=layout(rC,['FR','BL','BR'])
    Bx,rB,pB,_=optimise(rob,'FL',8,gap_min=15,lim=FW,extra=lambda r,a: 10*dist_pen(r,refC,['FR','BL','BR']))
    print(f'{name}, wheels held: crossing {pC:.2f}, lift@8 {pB:.2f}, path', 'peak %.2f minmargin %.1f s0 %.2f s1 %.2f'%sched(rob,Cx,Bx))
