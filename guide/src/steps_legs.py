# Desk Buddy guide - assembly steps, part 3: D Legs, E Tail, F Ears.
# Leg geometry (front-left leg, x > 0 is the robot's left): hip axis y 18, knee y -20, wheel axle y -65,
# front hips z +66, rear hips z -52. Thigh outer half x 55.6-60.6, shin outer 66.4-76.4, wheel 77.2-85.2.

def leg_parts(offsets=None, keep=None):
    """All printed parts of the robot in place (for overview views)."""
    body = [('Torso_Bottom', 'graphite'), ('Torso_Lid', 'white'), ('Side_Panel_Left', 'graphite'),
            ('Side_Panel_Right', 'graphite'), ('Band_Chest', 'graphite'), ('Band_Rump', 'graphite'),
            ('Collar', 'graphite'), ('Head_Front', 'white'), ('Head_Back', 'white'), ('Muzzle', 'white'),
            ('Ear_Left', 'white'), ('Ear_Right', 'white'), ('Tail_Root', 'white'), ('Tail', 'white')]
    for leg in ('FrontLeft', 'FrontRight', 'BackLeft', 'BackRight'):
        body += [(f'Thigh_{leg}_Outer', 'white'), (f'Thigh_{leg}_Cover', 'graphite'), (f'Shin_{leg}_Outer', 'white'),
                 (f'Shin_{leg}_Cover', 'graphite'), (f'Wheel_{leg}', 'graphite'), (f'Cap_Hip_{leg}', 'black'),
                 (f'Cap_Knee_{leg}', 'black'), (f'Cap_Wheel_{leg}', 'black')]
    return [(n, c, (0, 0, 0)) for n, c in body if keep is None or n in keep]


FL_THIGH = ('Thigh_FrontLeft_Outer', 'white', (0, 0, 0))
FL_THIGH_COVER = ('Thigh_FrontLeft_Cover', 'graphite', (0, 0, 0))
FL_SHIN_COVER = ('Shin_FrontLeft_Cover', 'graphite', (0, 0, 0))

STEPS_D = [
    dict(id='D1', title='Which leg is which',
         img=('stl', dict(parts=leg_parts(), cam=(-25, 62), width=1500, labels=[
             ((70, -30, 75), 'FRONT-LEFT: knee servo points forward', 'a'),
             ((-70, -30, 75), 'FRONT-RIGHT', 'a'),
             ((70, -30, -60), 'BACK-LEFT: knee servo points backward', 'a'),
             ((-70, -30, -60), 'BACK-RIGHT', 'a'),
             ((0, 158, 60), 'head = front', 'a'),
         ])),
         need=[('part', 'for each leg: thigh outer + cover, shin outer + cover, wheel, 3 caps'), ('part', 'per leg: 2 MG90S 180 (knee) and 1 MG90S 360 (wheel), all centred')],
         text=['The four legs are built the same way. The pictures in this chapter show the front-left leg; build the other three the same.',
               'Each printed file has its leg in the name, for example Thigh_FrontLeft_Outer. Some shapes are identical, so if you mix two up nothing is lost: the front-left and back-right thighs are the same shape turned round, and so are the front-right and back-left. The two left shins match, the two right shins match, and all four wheels match.',
               'The knee servo body always points away from the middle of the robot: forward on the front legs, backward on the back legs. Every paw (the wheel servo body) points forward.'],
         check='Lay out the four sets on the table in the shape of the robot before you start.',
         mistake='Mixing a left shin with a right leg. Left and right shins are mirror images and do not fit the other side.'),

    dict(id='D2', title='Hip horn into the thigh',
         img=('stl', dict(parts=[FL_THIGH], cam=(-68, 22), width=1300, labels=[
             ((55.6, 18, 66), 'hip horn pocket: 2 x M2x4', 'a'),
             ((55.6, -20, 57.3), 'knee servo tab holes', 'a'),
             ((55.6, -9, 66), 'lead hole at 12 o\'clock', 'a'),
             ((54, 4, 66), 'hip cup lead window (6 o\'clock)', 'a'),
         ])),
         need=[('part', 'thigh outer half'), ('part', 'a 4-arm cross horn from a servo bag'), ('part', '2.0 mm drill bit (turned by hand)'), ('screw', 2, 'M2x4')],
         text=['The holes in the servo horns are about 1.5 mm, too small for an M2 screw. Pick the two opposite arms you will use and open one hole on each to 2 mm by turning the drill bit between your fingers. Use holes between 6.7 and 10 mm from the horn\'s centre.',
               'Lay the horn in the cross-shaped pocket on the inside face of the thigh, at the hip end, with its hub facing out of the pocket, and drive 1 x M2x4 through each opened hole.'],
         check='The horn sits flat in its pocket and cannot turn.',
         mistake='Using M2x6 here. The thigh is thin at the hip, and a longer screw comes out through its outer face.'),

    dict(id='D3', title='Knee servo onto the thigh',
         img=('sec', '4 Leg', dict(crop='hi', hi=['Thigh_Outer'], hi2=['knee MG90S'], labels=[('knee MG90S', 'knee servo, body pointing away from the body', 'a', 0)])),
         need=[('part', 'MG90S 180, centred, lead flagged K + leg name'), ('screw', 2, 'M2x6')],
         text=['Set the knee servo onto the knee end of the thigh outer half, tabs flat on the face, with the round output boss in the round bore. Its body points away from the middle of the robot: forward on a front leg, backward on a back leg.',
               'Fix it with 2 x M2x6 through the tabs into the blind holes. The knee servo\'s lead leaves the body at the end nearest the knee.'],
         check='The servo spline sits in the middle of the bore and the tabs touch the face all the way along.',
         mistake='Turning the servo round so its body points toward the robot\'s middle. It will then hit the belly when the leg swings.'),

    dict(id='D4', title='Knee horn and wheel servo onto the shin',
         img=('sec', '4 Leg', dict(crop='hi', hi=['Shin_Outer'], hi2=['wheel MG90S 360'], labels=[('Shin_Outer', 'shin outer half', 'a', 0), ('wheel MG90S 360', 'wheel servo (360), body forward', 'a', 0)])),
         need=[('part', 'shin outer half'), ('part', 'cross horn (two holes opened to 2 mm)'), ('part', 'MG90S 360, lead flagged W + leg name'), ('screw', 4, 'M2x6')],
         text=['At the knee end of the shin outer half there is a cross-shaped pocket, just like the thigh\'s. Lay a horn in it, hub facing out, and fix it with 2 x M2x6.',
               'At the paw end, set the wheel servo (the 360 degree one) with its tabs on the face and its round boss in the bore, body pointing forward on every leg. Fix it with 2 x M2x6.'],
         check='Both screws of each pair are the same length. The knee horn screws here are M2x6, unlike the thigh.',
         mistake='Fitting a 180 degree servo in the paw. The wheel servos are the 360 degree ones from the pack of four.'),

    dict(id='D5', title='Horn into the wheel',
         img=('sec', '4 Leg', dict(crop='hi', hi=['Wheel'], labels=[('Wheel', 'wheel: horn pocket on the inner face', 'a', 0)])),
         need=[('part', 'wheel'), ('part', 'cross horn (two OUTER holes opened to 2 mm)'), ('screw', 2, 'M2x6')],
         text=['Lay a horn in the cross-shaped pocket on the inner face of the wheel, hub facing out, and fix it with 2 x M2x6 through the outer holes, at least 7.6 mm from the centre.',
               'Put the wheel aside for now. It goes on after the shin cover.'],
         check='The horn is flat in the pocket.',
         mistake='Using the inner horn holes. The screw then misses the thicker part of the wheel.'),

    dict(id='D6', title='Shin cover, with the wheel lead inside',
         img=('sec', '4 Leg', dict(crop='hi', hi=['Shin_Cover'], hi2=['wheel MG90S 360'], labels=[('Shin_Cover', 'shin cover: tongue at the knee ring, 1 x M2x8 under the wheel', 'a', 0)])),
         need=[('part', 'shin cover'), ('screw', 1, 'M2x8')],
         text=['The wheel servo\'s lead runs up the inside of the shin to the knee. Lay it in the channel along the shin outer half, and bring it out through the window in the cover\'s knee ring at 6 o\'clock (the bottom of the ring).',
               'Slide the cover\'s tongue into the knee ring, then press the cover onto the shin until both snap hooks click. The paw pod closes round the wheel servo body.',
               'Drive 1 x M2x8 into the hole in the outer face, under where the wheel will sit.'],
         check='No part of the lead shows along the shin, and about 20 cm of it comes out of the knee ring window.',
         mistake='Trapping the lead under the cover\'s edge. If the cover does not close with a gentle press, open it and re-lay the lead.'),

    dict(id='D7', title='Join the knee (lead half a turn round)', fig_mm=150,
         img=('stl', dict(parts=[FL_THIGH, FL_SHIN_COVER], cam=(90, 8), width=1300,
                          hi=['Shin_FrontLeft_Cover'], labels=[
                              ((64, -34, 66), "lead leaves the knee ring here (6 o'clock)", 'a'),
                              ((60.6, -9, 66), "half a turn round, then in here (12 o'clock)", 'a'),
                              ((60.6, -20, 66), 'knee servo spline', 'a')])),
         need=[('part', 'thigh with knee servo (D3), shin with cover (D6)'), ('part', 'servo\'s own horn screw'), ('part', '12 mm {{black}} knee cap')],
         text=['Hold the thigh and the shin side by side. Pass the wheel lead from the knee ring window half a turn round the knee, then in through the small hole at 12 o\'clock in the thigh face. This loose half turn is what lets the knee bend without pulling the lead.',
               'Check the knee servo is still centred. Hold the leg straight, thigh and shin in one line, and push the shin\'s knee horn onto the knee servo spline.',
               'Drive the servo\'s own horn screw through the 6 mm hole in the shin\'s outer face into the spline. Press the 12 mm cap into its recess, with the cap\'s small notch at the bottom so you can prise it out later.'],
         check='Bend the knee gently to about half way both ways: the lead slides round freely and never tightens.',
         mistake='Fitting the horn one tooth off. If the leg is not straight with the servo centred, pull the shin off and move it one tooth.'),

    dict(id='D8', title='Thigh cover, both leads inside', fig_mm=145,
         img=('sec', '4 Leg', dict(crop='hi', hi=['Thigh_Cover'], hi2=['knee MG90S'], labels=[('Thigh_Cover', 'thigh cover: tongue into the hip cup window, 1 x M2x8', 'a', 0)])),
         need=[('part', 'thigh cover'), ('screw', 1, 'M2x8')],
         text=['Now two leads run up the thigh: the knee servo\'s own lead, from the end of its body nearest the knee, and the wheel lead coming out of the 12 o\'clock hole. Lay both in the channel up the thigh, into the hip cup, and out through the cup\'s window at 6 o\'clock.',
               'Slide the cover\'s tongue into the window at the bottom of the hip cup and press the cover on until both hooks click. The knee pod closes round the knee servo body.',
               'Drive 1 x M2x8 into the hole in the outer face at the bottom of the knee disc. The shin hides it.'],
         check='Both leads come out of the hip cup, and each is at least 20 cm long from there.',
         mistake='Cutting or shortening a lead. The wheel lead needs about 200 mm to reach the servo board and the knee lead about 135 mm.'),

    dict(id='D9', title='Wheel and tyre',
         img=('sec', '4 Leg', dict(crop='hi', hi=['Wheel', 'Cap_Wheel'], hi2=['O-ring tyre'], labels=[('Cap_Wheel', '14 mm wheel cap', 'a', 0), ('O-ring tyre', 'O-ring tyre, 26 x 2.4 mm', 'a', 0)])),
         need=[('part', 'wheel with its horn (D5)'), ('part', 'horn screw'), ('part', '14 mm {{black}} wheel cap'), ('part', 'O-ring, the 31 mm outside-diameter size from the assortment (about 26.2 mm inside, 2.4 mm thick)')],
         text=['Push the wheel\'s horn onto the wheel servo spline. The wheel servo turns all the way round, so there is no "centre" to find here.',
               'Drive the horn screw through the centre hole and press the 14 mm cap in, notch at the bottom.',
               'Pick a 31 mm outside-diameter ring from the O-ring assortment (about 26.2 mm inside, 2.4 mm thick). Stretch it into the groove round the wheel. It should sit snug without twisting, and only about 1 mm of it should show above the rims, like a tread. Check the fit on the first wheel before you do the other three.'],
         check='Spin the wheel by hand: it turns smoothly, the tyre does not wobble, and no part of the rim touches the desk.',
         mistake='Taking the wrong size from the assortment. A ring one size smaller is too tight and rolls; one size bigger falls off. Use the 31 mm outside-diameter rings.'),

    dict(id='D10', title='Leg onto the body', fig_mm=145,
         img=('sec', '4 Leg', dict(crop='hi', hi=['Thigh_Outer', 'Cap_Hip'], hi2=['hip MG90S'], labels=[('hip MG90S', 'hip servo (in the tub)', 'a', 0), ('Cap_Hip', '12 mm hip cap', 'a', 0)])),
         need=[('part', 'the finished leg'), ('part', 'horn screw'), ('part', '12 mm {{black}} hip cap')],
         text=['Pass both leads from the hip cup window half a turn round the hip, then out through the slot in the side panel at 12 o\'clock (just above the round hole) and down into the notch in the tub wall behind it. Lay them in the notch; the lid clamps them later.',
               'Check the hip servo is centred. Hold the leg straight down and push the thigh\'s hip horn onto the hip servo spline.',
               'Drive the horn screw through the 6 mm hole in the thigh\'s outer face, and press the 12 mm cap in, notch at the bottom.'],
         check='Swing the leg gently forward and back by about 30 degrees: the leads move freely in the cup and nothing rubs.',
         mistake='Threading the leads through a closed hole. The tub notch is open at the top on purpose: lay them in from above.'),

    dict(id='D11', title='Range check and joint limits', fig_mm=118,
         img=('stl', dict(parts=leg_parts(keep=None), cam=(90, 5), width=1500, labels=[
             ((86, -65, 66), 'front paw: + moves it toward the head', 'a'),
             ((86, -65, -52), 'back paw', 'a'),
             ((50, 18, 66), 'hip', 'a'), ((62, -20, 66), 'knee', 'a'),
         ], arrows=[((86, -82, 50), (86, -82, 95))])),
         need=[('part', 'all four legs fitted')],
         text=['Before the lid goes on, move every joint through its whole range by hand, slowly: each hip about 30 degrees forward and back, each knee about 50 degrees both ways. Watch the leads in each hip cup and at each knee. Nothing may pinch, rub or pull tight.',
               'Angles count from the straight-down pose. Plus moves the foot forward, toward the head, and minus moves it back. The hip angle turns the thigh; the knee angle turns the shin relative to the thigh. The left and right legs are mirror images, so the firmware maps these angles to each servo\'s own direction.',
               'Front legs need no limit inside hip plus or minus 30 and knee plus or minus 50 degrees. Back legs: when the hip is above plus 25 degrees, keep the knee at or below plus 45 degrees. At hip plus 30 and knee plus 50 the back paw would come within 0.9 mm of the belly; with this rule the gap never drops below 4.6 mm. Walking never gets near these poses. They only matter for tricks like sitting or folding a leg.'],
         check='Every joint moves by hand without catching, and every lead still lies in its channel.',
         mistake='Forcing a joint past a stop. Servo gears strip if you lean on them.'),
]

STEPS_E = [
    dict(id='E1', title='Fit the tail', fig_mm=118,
         img=('sec', '2 Lid', dict(crop='hi', hi=['Tail_Root', 'Tail', 'Cap_Tail'], hi2=['tail MG90S'],
                                  labels=[('Tail', 'tail: 1 x M2x8 from under the root', 'a', 0), ('Tail_Root', 'tail root: horn, 2 x M2x4', 'a', 0),
                                          ('Cap_Tail', '12 mm tail cap', 'a', 0), ('tail MG90S', 'tail servo', 'a', 0)])),
         need=[('part', 'tail root, tail, 12 mm {{black}} tail cap'), ('part', 'cross horn (two holes opened to 2 mm)'), ('screw', 2, 'M2x4'), ('screw', 1, 'M2x8'), ('part', 'horn screw')],
         text=['Lay a horn in the pocket under the tail root and fix it with 2 x M2x4. The root is only 4.6 mm thick, so nothing longer.',
               'Key the tail onto the root and fix it with 1 x M2x8 driven up from under the root. Do this before the root goes on the servo, because you cannot reach the screw afterwards.',
               'Check the tail servo is centred. Push the root into the round socket on top of the lid, horn onto the spline, with the tail pointing straight back. Drive the horn screw through the centre and press the cap in.'],
         check='The tail can swing a little both ways by hand and the root turns without rubbing the socket.',
         mistake='Fitting the tail to the root after the root is on the servo. The tail screw is then out of reach.'),
]

STEPS_F = [
    dict(id='F1', title='Fit the ears',
         img=('sec', '3 Head', dict(hi=['Ear_Left', 'Ear_Right'], arrows=[('Ear_Left', (0, 160)), ('Ear_Right', (0, 160))],
                                   labels=[('Ear_Left', 'left ear', 'a', 0), ('Ear_Right', 'right ear', 'a', 0)])),
         need=[('part', 'left and right ears'), ('screw', 2, 'M2x8')],
         text=['Each ear has a keyed peg that fits one way only into its pocket on top of the head. The ears lean back slightly.',
               'Push each ear into its pocket, then reach inside the head and drive 1 x M2x8 up through the pad under the pocket into the ear.'],
         check='Neither ear moves when you wiggle it.',
         mistake='Forcing an ear into the wrong pocket. If the peg does not drop in, try the other ear.'),
]
