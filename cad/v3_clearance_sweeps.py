import math
HIP_Y=18.0; L1=38.0; L2=45.0; TYRE=14.15
def rounded_rect_pts(a0,a1,b0,b1,R,n=24):
    # outline points of a rounded rectangle in (a,b)
    pts=[]
    for (ca,cb,s0) in ((a1-R,b1-R,0),(a0+R,b1-R,90),(a0+R,b0+R,180),(a1-R,b0+R,270)):
        for k in range(n+1):
            t=math.radians(s0+90*k/n); pts.append((ca+R*math.cos(t),cb+R*math.sin(t)))
    return pts
def belly_y(z, zend, R=8.0):
    # underside of torso at z (y=0 flat, rounded R at the end), returns None beyond the end
    if abs(z) <= zend-R: return 0.0
    if abs(z) > zend: return None
    dz=abs(z)-(zend-R); return R-math.sqrt(max(R*R-dz*dz,0))
# knee pod case-hugging part: along case dir a in [-(6+2.2), 16.8+2.2], b +-(6.2+2.2), fillet R4
for leg,hz,dirc in (('front',66.0,+1),('rear',-52.0,-1)):
    worst=(1e9,None)
    pod=rounded_rect_pts(-8.2,19.0,-8.4,8.4,4.0)
    for th10 in range(-300,301,5):
        th=math.radians(th10/10)
        for a,b in pod:
            dz=dirc*a; dy=-L1+b          # relative to hip axis, knee straight below at th=0
            z=hz+dz*math.cos(th)-dy*math.sin(th); y=HIP_Y+dz*math.sin(th)+dy*math.cos(th)
            by=belly_y(z,80.0)
            if by is None: continue
            c=by-y
            if c<worst[0]: worst=(c,th10/10,round(z,1),round(y,1))
    print('knee pod',leg,'min clearance to underside (R8 end edges):',[round(worst[0],2)]+list(worst[1:]))
# paw pod vs desk, long end rising at +tilt
for R in (0.0,4.0,6.0,8.0):
    res=[]
    for name,(a0,a1) in (('case band',(-8.2,19.0)),('tab band',(-13.05,23.85))):
        pod=rounded_rect_pts(a0,a1,-8.4,8.4,R) if R>0 else [(a0,-8.4),(a1,-8.4),(a0,8.4),(a1,8.4)]
        worst=1e9
        for th10 in range(-99,199,1):
            th=math.radians(th10/10)
            for a,b in pod:
                y=b*math.cos(th)+a*math.sin(th)   # + tilt raises +a end
                worst=min(worst,y)
        res.append((name,round(TYRE+worst,2)))
    print('paw R',R,'min height above desk:',res)
# clock-spring loop lengths
for nm,rmin,rmax,wmin,wmax in (('hip',5.2,15.7,150,210),('knee',5.2,14.6,130,230)):
    Lmax=math.radians(wmin)*rmax; Lmin=math.radians(wmax)*rmin
    print(nm,'loop L range %.1f..%.1f'%(Lmin,Lmax))
    L=30 if nm=='hip' else 27
    print('  L',L,'r at wrap min/max: %.1f / %.1f'%(L/math.radians(wmin),L/math.radians(wmax)))
print('--- validation + sensitivity')
def sweep(hz,dirc,a0,a1,bb,R,zend_R):
    pod=rounded_rect_pts(a0,a1,-bb,bb,R) if R>0 else [(a0,-bb),(a1,-bb),(a0,bb),(a1,bb)]
    worst=(1e9,)
    for th10 in range(-300,301,5):
        th=math.radians(th10/10)
        for a,b in pod:
            dz=dirc*a; dy=-L1+b
            z=hz+dz*math.cos(th)-dy*math.sin(th); y=HIP_Y+dz*math.sin(th)+dy*math.cos(th)
            by=belly_y(z,80.0,zend_R) if zend_R>0 else (0.0 if abs(z)<=80 else None)
            if by is None: continue
            if by-y<worst[0]: worst=(round(by-y,2),th10/10,round(z,1))
    return worst
print('current bare front knee case (rearward):',sweep(66,-1,-6,16.8,6.2,0,0))
print('proposed front pod, sharp torso edges:',sweep(66,1,-8.2,19,8.4,4,0))
print('proposed rear pod, sharp torso edges:',sweep(-52,-1,-8.2,19,8.4,4,0))
print('proposed rear pod, R8 edges:',sweep(-52,-1,-8.2,19,8.4,4,8))
print('wrong way: rear pod pointing forward:',sweep(-52,1,-8.2,19,8.4,4,8))
print('wrong way: front pod pointing rearward:',sweep(66,-1,-8.2,19,8.4,4,8))
print('--- hip angle where the pod first touches (R8 end edges)')
def first_touch(hz,dirc,sign):
    pod=rounded_rect_pts(-8.2,19,-8.4,8.4,4.0)
    for th10 in range(0,900,5):
        th=math.radians(sign*th10/10)
        for a,b in pod:
            dz=dirc*a; dy=-L1+b
            z=hz+dz*math.cos(th)-dy*math.sin(th); y=HIP_Y+dz*math.sin(th)+dy*math.cos(th)
            by=belly_y(z,80.0,8.0)
            if by is not None and by-y<0: return sign*th10/10
    return None
for leg,hz,dirc in (('front',66,1),('rear',-52,-1)):
    print(leg,'knee back:',first_touch(hz,dirc,-1),' knee forward:',first_touch(hz,dirc,1))
