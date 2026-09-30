import numpy as np, sys
from spike_model import Robot, solve, LEGS, kg
R=Robot()
C={'FL': (-13.7, 5.3), 'FR': (12.9, -9.4), 'BL': (18.6, -20.5), 'BR': (-5.0, 10.0)}
B={'FL': (-22.5, -46.8), 'FR': (4.3, -8.9), 'BL': (-2.1, 2.2), 'BR': (-4.0, 49.5)}
r=solve(R,C,['FR','BL','BR']); print('C with BR -5/+10: margin %.1f FLgap %.1f peak %.2f'%(r['margin'],r['lift_h']['FL'],max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0,1))))
def pose(s,s0,s1):
    u=min(1,max(0,(s-s0)/(1-s0))) if s0<1 else 0
    v=min(1,max(0,(s-s1)/(1-s1)))
    a={}
    for l in LEGS:
        t = u if l in ('FR','BL') else (v if l=='FL' else min(1,s/0.6))
        a[l]=(C[l][0]+(B[l][0]-C[l][0])*t, C[l][1]+(B[l][1]-C[l][1])*t)
    return a
def path(s0,s1,n=21,verbose=False):
    worst=0; mmin=99
    for s in np.linspace(0,1,n):
        a=pose(s,s0,s1); r=solve(R,a,['FR','BL','BR'])
        pk=max(abs(kg(r['tq'][l][j])) for l in LEGS for j in (0,1)); g=r['lift_h']['FL']
        m=r['margin'] if g>0.3 else 99
        if verbose: print(f'  s {s:.2f}: margin {r["margin"]:+5.1f} FLgap {g:5.1f} peak {pk:.2f} pitch {r["pitch"]:+.1f} roll {r["roll"]:+.1f}')
        worst=max(worst,pk); mmin=min(mmin,m)
    return worst,mmin
res=[]
for s0 in np.arange(0,0.96,0.05):
    for s1 in np.arange(0,0.96,0.05):
        w,m=path(s0,s1); res.append((w,m,s0,s1))
ok=[x for x in res if x[1]>=2.0]
print('schedules with margin>=2 once FL is off:',len(ok))
b=min(ok) if ok else max(res,key=lambda x:x[1])
print('chosen: peak %.2f min margin %.1f  FR/BL release from s=%.2f, FL tuck from s=%.2f (BR crouch over s 0..0.6)'%b)
path(b[2],b[3],11,True)
