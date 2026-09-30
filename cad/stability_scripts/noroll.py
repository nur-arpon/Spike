"""Same crossing / lift optimisation, but the loaded paws may NOT roll or slide on the desk (wheels held)."""
import numpy as np, itertools
from spike_model import Robot, solve, LEGS, kg
from optimize import optimise, report, FW
R=Robot()
def layout(r, legs):
    n=r['n']; c=r['cps']; e1=np.cross(n,[0,0,1.]); e1/=np.linalg.norm(e1); e2=np.cross(e1,n)
    return {l: np.array([np.dot(c[l],e1), np.dot(c[l],e2)]) for l in legs}
def dist_pen(r, ref, legs, tol=1.0):
    q=layout(r,legs); p=0
    for a,b in itertools.combinations(legs,2):
        p+=max(0,abs(np.linalg.norm(q[a]-q[b])-np.linalg.norm(ref[a]-ref[b]))-tol)
    return p
st=solve(R,{l:(0.,0.) for l in LEGS},['FR','BL','BR'])
ref=layout(st,LEGS)
for m in (0.5,):
    angC,rC,pkC,penC=optimise(R,'FL',m,gap_min=0.0,gap_max=0.5,lim=FW,extra=lambda r,a: 10*dist_pen(r,ref,LEGS))
    report('NO-ROLL crossing (all 4 paws keep the stand layout)',angC,rC,pkC,penC,'FL')
    refC=layout(rC,['FR','BL','BR'])
    for mB in (8,10):
        angB,rB,pkB,penB=optimise(R,'FL',mB,gap_min=12,lim=FW,extra=lambda r,a: 10*dist_pen(r,refC,['FR','BL','BR']))
        report(f'NO-ROLL lift FL margin>={mB} (FR BL BR keep the crossing layout)',angB,rB,pkB,penB,'FL')
