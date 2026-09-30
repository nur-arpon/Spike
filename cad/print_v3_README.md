# Desk Buddy - print model v3 (covered design)

Built by `build_print_parts_v3.py` (SolidWorks 2025) from the approved design in
`v3_covered_design_proposal.md`. All parts share one coordinate frame, so the assembly
`print_v3\Desk Buddy v3 - full assembly.SLDASM` needs no mates and every clash is checked body
against body. The results are in `build_v3_report.txt`.

**Status (26 Sep 2026): the legs are v3.** The torso, lid, neck, head, muzzle, ears and tail are still
the v2 parts, painted in the v3 colours. The next build step turns them into v3 (side panels, collar,
tail turntable, battery door, belly switch). Until then the hip lead chambers are open on the body side,
and the tail still has its v2 horn.

| Folder | What is in it |
|---|---|
| `print_v3\` | SolidWorks only: the printed parts, the bought-parts model, the assembly |
| `print_v3_stl\` | one STL per printed part. Each one is checked against the model after export (size and volume) |
| `print_v3_png\` | a picture of every part, 6 views of the assembly, and a sheet of all parts |

v1 and v2 are untouched. Every change from here gets a new version, never an edit of this one.

## What a v3 leg is

Each leg has 8 printed parts. The servos sit exactly where v2 had them.

| Part | Colour | Holds | Print |
|---|---|---|---|
| `Thigh_..._Outer` | warm white | the hip servo's cross horn, the knee MG90S (screwed to it), 2 snap hooks | outer face down, no supports |
| `Thigh_..._Cover` | graphite | the knee servo's case inside the knee pod, the leads | open side (the flat face with the channel) down, no supports |
| `Shin_..._Outer` | warm white | the knee servo's cross horn, the wheel MG90S 360 (screwed to it), 2 snap hooks | outer face down |
| `Shin_..._Cover` | graphite | the wheel servo's case inside the paw pod, the leads, the knee lead chamber ring | open side down |
| `Wheel_...` | graphite | the wheel servo's cross horn, the 26 x 2.4 O-ring tyre | outer face down |
| `Cap_Hip_...`, `Cap_Knee_...` | black | dia 12 hub cap over the horn screw | top face down |
| `Cap_Wheel_...` | black | dia 14 hub cap | top face down |

Plus one `Cap_Tail` (dia 12) for the tail. It is left out of the assembly until the v3 tail root exists,
because the v2 tail servo still sits where the cap goes.

**Numbers from this build** (`build_v3_report.txt`). One leg's parts weigh 61 g solid: thigh outer half
12.6 g, thigh cover 10.5, shin outer half 21.0, shin cover 10.4, wheel 5.7, 3 caps 0.7. That is about 45 g
as printed. Every part is one piece, fits the printer, and its STL was re-read and matches the model.
The clash check found 0 overlaps between 258 bodies (printed parts, servos, horns, tab screws, O-rings and
the lead paths). The whole robot is now about 1026 g. Lifting a front foot needs the body shifted
8.7-8.9 mm first (v2: 8.3-8.5), so the gait's weight shift must be slightly bigger.

**Identical prints.** The front-left and rear-right thighs are the same shape turned round, and so are
the front-right and rear-left. The two left shins are the same, and so are the two right shins. All
four wheels are the same, and so are all the dia 12 caps. The files are separate because each one sits in
its real place in the assembly. In the slicer, a file prints the same whichever leg it is named after.

## Step 1 - print the two coupons first

| Coupon | Files | About | What to test |
|---|---|---|---|
| Knee | `Coupon_Knee_Thigh` + `Coupon_Knee_Shin` | 20 g | Screw a knee MG90S to the thigh end (tabs on the flat face, 2 screws from underneath). Fit a cross horn into the shin end (2 arm screws from the horn side), press it onto the servo spline with its horn screw, press a dia 12 cap in. Thread a servo lead through the ring's window and the thigh end's small hole. Sweep the knee 500 times through +/-50 deg. Check the 0.8 mm gap never rubs, the lead is not pinched, and the cap stays put. |
| Snap and caps | `Coupon_Snap_White` + `Coupon_Snap_Graphite` + one dia 12 and one dia 14 cap | 6 g | Clip the white block into the graphite block: it should click and hold. Press both caps into their seats: they should grip, and come out with a pick in the notch. |

If a fit is wrong, change the number at the top of the script (see Step 2), run it again, and print the
coupon again.

## Step 2 - measure these when the servos arrive

| Number in the script | Guess | What to measure |
|---|---|---|
| `SV_TOP_RECT` | 4.5 | MG90S: underside of the mounting tabs to the top of the rectangular gear case |
| `SV_TOP_HUMP` | 7.5 | MG90S: underside of the tabs to the top of the round boss the spline comes out of (boss dia 11.8) |
| `SV_UNDER`, `SV_SPLINE`, `SV_TAB_T`, `SV_HOLES` | 21.0 / 14.4 / 2.8 / 28.15 | as in v2 |
| tab ear corners | round, R1.1 or more | The tab cavities have R1.5 corners (they keep 1.5 mm of wall under the round heel and toe). If your tab ears are square, file the two corners that face down to 1 x 45 deg. |
| lead exit | either end | Which end of the case the lead comes out of, and how high. The pods leave 2.6 mm at both ends and under the case, so either end works. |
| `LEAD_D` | 2.4 | Twist the 3 servo wires into a round bundle. It must pass a 2.6 mm hole. |
| `CROSS_REACH`, `HORN_T`, `HORN_W` | 11.5 / 1.8 / 6.6 | the cross horn in the servo bag: centre to tip, arm thickness, arm width |
| horn screw holes | 5.5 to 10 mm from the centre | The blind pilot slots run from 5.5 to 10 mm along each arm (6.7 to 10 in the thigh, where the cap recess sits above). |
| `OR_CS` | 2.4 | 26 mm ID O-ring cross-section |

## Assembling one leg

1. **Thigh outer half:** screw a cross horn into the hip pocket from the horn side (2 arm screws into the
   blind pilots). Screw the knee MG90S's tabs to the knee end: 2 x M2 x 6 from the tab side into the
   blind pilots. The case points away from the body: forward on the front legs, backward on the rear
   legs.
2. **Leads:** the knee servo's lead goes out of the pod at the end nearest the knee joint, up the channel.
   The wheel servo's lead comes up the shin, through the ring's window at the bottom of the knee, round
   half a turn, and out through the small hole in the thigh face at 12 o'clock. Both leads go up the thigh
   channel into the hip cup at 6 o'clock.
3. **Thigh cover:** slide its tongue into the window at the bottom of the hip cup, press it on until both
   snap hooks click, then drive the M2 x 8 from the thigh's outer face at the bottom of the knee disc (it
   is hidden under the shin once the knee is assembled).
4. **Shin:** the same way. The wheel servo's tabs screw into the shin outer half, the cover snaps on, and
   its M2 x 8 goes in from the shin's outer face under the wheel (hidden by the wheel).
5. **Joints:** push each horn onto its spline, drive the servo's own horn screw through the dia 6 hole,
   press the cap in with its notch at the bottom.
6. **Wheel:** screw the cross horn into the wheel, push it onto the wheel servo spline, horn screw, cap.
   Stretch the O-ring into the groove.
7. Run every joint through its full range by hand before powering up (the pinch check).

## Screws for the legs (per leg)

| Where | Count | Size |
|---|---|---|
| knee and wheel servo tabs, into blind pilots | 4 | M2 x 6 (servo bag) |
| cross horn arms, from the horn side into blind pilots | 6 (2 per horn) | the small horn screws, or M2 x 6 |
| horn to spline | 3 | the servo's own horn screw |
| cover screws (thigh and shin) | 2 | M2 x 8 |

## Notes the model does not show

- **Hip swing:** keep each hip within +/-30 deg in software. The knee pods pass under the body with
  3.4 mm to spare at 30 deg (2.6 mm counting the rounded root of the pod) and first touch it at about
  37 deg. This needs the 8 mm rounds on the bottom of the chest and rump, which come with the v3 body.
- **Folding a rear leg:** hip +30 deg together with knee +50 deg brings the rear paw up into the belly.
  Inside the gait limits (shin within -9.9 / +19.8 deg) the paws stay more than 40 mm clear.
- **Tilt sign:** all paws point forward. This assumes gait.py's +19.8 deg shin limit means "toe up".
  If it is the other way round, set `PAW_DZ = -1` and run the script again.
- **Leads:** the wheel lead needs about 200 mm to the PCA9685, the knee lead about 135 mm. Don't cut them
  shorter. Stock PVC leads flex at 2 coils per leg; silicone wire lasts longer.
- **Heat:** the pods are closed PLA. Test a knee pod with a thermocouple before long walks (stop above
  45 deg C).
