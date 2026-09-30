# Desk Buddy - print model v3.1 (first print, about 10 Oct 2026)

This is the complete print pack for Desk Buddy, the desk robot dog. It is written for someone who has never
built it before. Read it top to bottom once, then use the tables while you print and assemble.

Everything here is made by `build_print_parts_v3_1.py` (SolidWorks 2025, driven from Python) and checked by the
same script. The raw results are in `build_v3_1_report.txt`. v1, v2 and v3 are untouched.

| Folder / file | What is in it |
|---|---|
| `print_v3_1\` | SolidWorks files only: the 55 robot parts, the 5 test prints, the bought-parts model, the full assembly |
| `print_v3_1_stl\` | one STL per printed part - these are what you print |
| `print_v3_1_png\` | a picture of every part, 7 views of the robot (iso, front, side, back, top, under, inside), and one exploded, labelled picture per body section |
| `build_v3_1_report.txt` | every check the script ran, with its numbers |

## What changed from v3 (and why)

The outside of the robot is exactly the approved v3: same shape, same three colours (warm white, graphite,
black caps), nothing new showing. All the changes are inside.

1. **Lighter.** The hidden walls are thinner:
   - head 2.4 -> 1.6 mm (the frame round the screen stays 2.4, so the glass sits exactly where it did)
   - tub side and end walls 2.4 -> 1.6 mm, plus a hidden window in each side wall behind the side panel
   - lid side and end walls 5.1 / 7.4 mm solid -> 1.6 mm, on a 1.8 mm locating lip
   - collar 2.4 -> 1.6 mm, muzzle sides and top 2.4 -> 1.8 mm
   - two small ribs inside the head back keep its big thin panel stiff

   1.6 mm is exactly 4 lines of a 0.4 mm nozzle, so these walls print solid and clean. Wherever a screw head,
   a servo or the screen presses on a thin wall there is a local pad, so those places are still 2.0 mm or more
   (the one exception is a tiny snap-detent recess; see "Decisions"). The grams are no longer a guess: the script
   slices every exported STL (see "Slicer settings"). Result: **385.7 g as printed** (v3: 393 g with the same
   settings, 457 g with 3 walls).
2. **Balance.** The perfboard hub under the lid sits 9 mm further back than in v3. The lighter lid and tub moved
   the weight forward, and this brings it back: 48.8 mm inside the wheels against 48.6 mm for v3 measured the
   same way (see "Numbers" for why the v3 report said 49.0).
3. **No clashes.** The tail cap's peg is 1.0 mm long instead of 1.2, so it stays 0.6 mm clear of the tail servo's
   horn even if the real horn is a little thicker than the estimate.
4. **Joint limits for the firmware.** One rear-leg pose (hip +30, knee +50) brings the paw pod to 0.9 mm under the
   belly. It never touches, but the firmware should keep 2 mm - see "Joint limits".
5. **Screw fixes found while checking lengths against the model** (v3 notes had these wrong):
   - touch-pad screws are **M2 x 4** (an M2 x 6 would come out through the top of the lid)
   - the horn-arm screws in the **thighs and the tail root are M2 x 4** (their pilots are only 2.2 mm deep)
   - the battery-door lugs in the tub are 0.8 mm taller, so the door takes the same M2 x 6 as everything else
6. The last v3 run had stopped in the assembly stage, so the v3 report was older than the v3 files. v3.1 rebuilt
   and re-checked everything from scratch.

## Before you print anything: measure the servos

The fits depend on a few numbers that the sellers do not publish. They are at the top of the script. When the
servos arrive, measure one with the caliper. If a number is off by more than about 0.2 mm, change it in
`build_print_parts_v3_1.py`, run the script again, and print from the new STLs.

| Number in the script | Value used | What to measure |
|---|---|---|
| `SV_TOP_RECT` | 4.5 | MG90S: underside of the mounting tabs to the top of the rectangular gear case |
| `SV_TOP_HUMP` | 7.5 | MG90S: underside of the tabs to the top of the round boss the spline comes out of (boss dia 11.8) |
| `SV_UNDER`, `SV_SPLINE`, `SV_TAB_T`, `SV_HOLES` | 21.0 / 14.4 / 2.8 / 28.15 | case bottom to tab underside, tab underside to spline top, tab thickness, tab hole spacing |
| tab ear corners | round, R1.1 or more | If your tab ears are square, file the two corners that face down to 1 x 45 deg |
| `LEAD_D` | 2.4 | twist the 3 servo wires into a round bundle; it must pass a 2.6 mm hole |
| `CROSS_REACH`, `HORN_T`, `HORN_W`, `HORN_OUT` | 11.5 / 1.8 / 6.6 / 1.0 | the cross horn in the servo bag: centre to tip, arm thickness, arm width, how far its top sits above the spline |
| `OR_CS` | 2.4 | the 26 mm ID O-ring's cross-section |

## Slicer settings (UltiMaker Cura, Ultimaker 2+ Connect, 0.4 mm nozzle, PLA)

The printed grams in this README assume exactly these settings. The script slices every exported STL with a
small voxel model of Cura's wall / skin / infill rules (`swlib_v3_1.stl_print_estimate`), checked against hand
calculations on test blocks to within 2 %.

| Setting | Value |
|---|---|
| Layer height | 0.2 mm |
| Line width | 0.4 mm |
| Wall line count | **2** (0.8 mm) |
| Top / bottom thickness | 0.8 mm (4 layers) |
| Infill | 15 %, gyroid |
| Supports | none (see note A) |
| Build plate adhesion | brim 5 mm on the long flat parts (plates G1 and W1), skirt on the rest |

**Why 2 walls.** The thin walls in v3.1 are 1.6 mm, exactly 4 lines of a 0.4 mm nozzle, so with 2 walls per side
they print completely solid (the few 1.8 mm walls get a thin gap fill in the middle). Screw bosses, pads and
seats are 2.0 mm or more and print solid as well. More walls only add plastic inside the thick parts (the leg
halves, wheels and ears), where 15 % gyroid is already enough.

What the settings change, for all 55 robot parts (from `build_v3_1_report.txt`):

| Walls | Printed grams | |
|---|---:|---|
| **2 walls (use this)** | **385.7 g** | under the 400 g budget limit with a 14 g margin |
| 2 walls, but 3 on the 8 leg outer halves | 394.3 g | stronger leg screw pilots; only 6 g of margin, so not the default |
| 3 walls everywhere | 422.6 g | over the limit |

Skirts, brims and the odd support add about 1-3 % on top, so expect Cura to say roughly 390-398 g in total.
Overall that is 70 % of the solid volume (the script's `FILL`, now measured: thin shells print at 95-100 %,
the thick leg halves, wheels and ears at 40-60 %).

**Note A - round edges on the bed.** The lid (R6 top edge), the head front (R8 face edge) and the head back
(R10 back edge) are printed with their visible face on the bed, so the first 1-2 mm of that rounded edge grows
outward over nothing. PLA normally prints this with a slightly soft first millimetre. If your first lid shows a
drooping edge, reprint that plate with "Support: touching build plate" at 60 deg, and sand the edge lightly.

## Every printed part

Grams are "as printed" with the settings above. "Plate" says which print job it goes on (next section).
`<leg>` is FrontLeft, FrontRight, BackLeft or BackRight.

| Part | Colour | What it holds | On the bed | Supports | g each | Plate |
|---|---|---|---|---|---:|---|
| `Torso_Bottom` (the tub) | graphite | 4 hip MG90S (tabs outside the wall), 2 PCA9685, protection board, fuse holder, USB-C charger, KCD1 switch, 5 VL53L0X | belly down | none | 49.7 | G1 |
| `Band_Chest` | graphite | front obstacle-laser window; hides 2 lid screws (2 snap hooks) | outer face down | none | 3.5 | G1 |
| `Band_Rump` | graphite | rear obstacle-laser window and the USB-C opening; hides 2 lid screws | outer face down | none | 3.4 | G1 |
| `Side_Panel_Left`, `Side_Panel_Right` | graphite | cover the 2 hip MG90S on their side (4 snap hooks each, no screws) | outer face down | none | 14.9 | G2 |
| `Battery_Door` | graphite | 2x18650 holder and the clamp; 4 screws into the tub | outer (belly) face down | none | 11.1 | G2 |
| `Battery_Clamp` | graphite | holds the 18650 holder down | flat | none | 1.3 | G2 |
| `Collar` | graphite | nothing (cables pass through it); joins the lid to the head | top face down | none | 12.4 | G2 |
| `Torso_Lid` | warm white | MPU6050, MPR121, perfboard hub (2 Mini560), tail MG90S, 2 side VL53L0X, 4 foil touch pads | top face down | note A | 46.0 | W1 |
| `Tail_Root` | warm white | the tail servo's cross horn, the tail cap | underside down | none | 1.6 | W1 |
| `Tail` | warm white | nothing (keyed onto the root, 1 hidden screw) | flat underside down | none | 1.1 | W1 |
| `Ear_Left`, `Ear_Right` | warm white | nothing (1 screw each from inside the head) | standing on the base | none | 2.5 | W1 |
| `Head_Front` | warm white | Guition 4.3in screen, 2 MS3625 mics, head touch pad, both ears | face (screen side) down | note A | 35.8 | W2 |
| `Muzzle` | warm white | ESP32-S3 CAM board, OV5640 camera, APDS-9960 gesture sensor | front face down | none | 11.4 | W2 |
| `Head_Back` | warm white | cavity speaker; clips onto the head front (5 snap hooks) | back face down | note A | 31.0 | W3 |
| `Thigh_<leg>_Outer` x4 | warm white | hip cross horn, knee MG90S (2 tab screws), 2 snap hooks | outer face down | none | 7.3 | 1 on W3, 3 on W4 |
| `Shin_<leg>_Outer` x4 | warm white | knee cross horn, wheel MG90S 360 (2 tab screws), 2 snap hooks | outer face down | none | 9.0 | W4 |
| `Thigh_<leg>_Cover` x4 | graphite | knee MG90S case (in the knee pod), leads | open side down | none | 7.2 | G3 |
| `Shin_<leg>_Cover` x4 | graphite | wheel MG90S 360 case (in the paw pod), leads, knee lead ring | open side down | none | 8.1 | G4 |
| `Wheel_<leg>` x4 | graphite | wheel cross horn, 26 x 2.4 O-ring tyre | outer face down | none | 2.9 | 3 on G3, 1 on G4 |
| `Cap_Hip_<leg>`, `Cap_Knee_<leg>` x8 | black | hide the hip and knee horn screws (dia 12) | top face down | none | 0.2 | B1 |
| `Cap_Wheel_<leg>` x4 | black | hide the wheel horn screws (dia 14) | top face down | none | 0.3 | B1 |
| `Cap_Tail` | black | hides the tail horn screw (dia 12) | top face down | none | 0.2 | B1 |
| `Port_Door_Head`, `Port_Blank_Head` | black | cover for the screen board's USB-C, and its matching blank | outer face down | none | 0.3 | B1 |
| `Port_Door_Muzzle`, `Port_Blank_Muzzle` | black | cover for the camera board's USB-C, and its matching blank | outer face down | none | 0.4 | B1 |
| `Screw_Plugs` (4 in one file) | black | hide the 4 battery-door screws | flat | none | 0.1 | B1 |
| `Screen_Washers` (4 in one file) | black | go under the 4 screen screws | flat | none | 0.1 | B1 |
| **Robot total (55 files)** | | | | | **385.7 g** | |
| `Fit_Test_Coupon` | any | test: servo slot, KCD1 cut-out, screen boss, windows, O-ring groove, horn pocket | flat | none | 14.5 | T1 |
| `Coupon_Knee_Thigh`, `Coupon_Knee_Shin` | any | test: knee MG90S, knee cross horn, cap, lead chamber | outer face down | none | 3.0, 5.6 | T1 |
| `Coupon_Snap_White`, `Coupon_Snap_Graphite` | any | test: one snap hook and catch, a dia 12 and a dia 14 cap seat | outer face down / flat | none | 2.3, 0.6 | T1 |

**Identical prints.** The front-left and rear-right thighs are the same shape turned round, and so are the
front-right and rear-left. The two left shins match, and so do the two right shins; all four wheels match, and
so do all the dia 12 caps. The files are separate only because each sits in its real place in the assembly.

## Print jobs (plates) and cost at the Deer Park maker space

One filament colour per plate, every plate fits the 223 x 220 x 205 bed with room to spare (Cura's
"Arrange all" places them), and every plate stays under 60 g so the band price applies. Both prices are shown:
the bands ($1 up to 10 g, $2 up to 20 g, $4 up to 40 g, $6 up to 60 g) and $1.10 per 10 g.

| Order | Plate | Filament | Parts | Grams | Band | $1.10 / 10 g |
|---:|---|---|---|---:|---:|---:|
| 1 | T1 test prints | any | Fit_Test_Coupon, both knee coupons, both snap coupons, 1 dia 12 + 1 dia 14 cap | 26.5 | $4.00 | $2.92 |
| 2 | B1 | black | 13 caps, 4 port doors and blanks, screw plugs, screen washers | 4.6 | $1.00 | $0.51 |
| 3 | G1 | graphite | tub + 2 bands | 56.6 | $6.00 | $6.23 |
| 4 | W1 | warm white | lid + 2 ears + tail root + tail | 53.7 | $6.00 | $5.91 |
| 5 | G2 | graphite | 2 side panels + battery door + clamp + collar | 54.6 | $6.00 | $6.01 |
| 6 | W2 | warm white | head front + muzzle | 47.2 | $6.00 | $5.19 |
| 7 | W3 | warm white | head back + 1 thigh outer | 38.3 | $4.00 | $4.21 |
| 8 | W4 | warm white | 4 shin outers + 3 thigh outers | 57.9 | $6.00 | $6.37 |
| 9 | G3 | graphite | 4 thigh covers + 3 wheels | 37.5 | $4.00 | $4.12 |
| 10 | G4 | graphite | 4 shin covers + 1 wheel | 35.3 | $4.00 | $3.88 |
| | **Robot (plates 2-10)** | | | **385.7** | **$43.00** | **$42.43** |
| | **With the test plate** | | | **412.2** | **$47.00** | **$45.35** |

Skirt and brim add a gram or two per plate: G1, W1 and W4 are close to 60 g, so one of them may land just over
and cost $6.60 at the per-10 g rate instead of $6. Print T1 first. If a fit is wrong, change the number in the
script (see "Before you print anything"), run it again and reprint T1 before anything else. Then print B1
(cheap, and the caps are needed early), then the body plates, then the legs.

## Numbers from this build

"v3 measured like v3.1" runs the v3 files through the same slicer model and balance check, so it is the fair
comparison. The v3 report's own figures used one FILL factor of 0.75 for every part, which is why they differ.

| | v3 report | v3 measured like v3.1 | **v3.1** |
|---|---:|---:|---:|
| Printed parts, solid | 613 g | 615.4 g | **550.7 g** |
| Printed parts, as printed (2 walls) | - | 393.2 g | **385.7 g** |
| Printed parts, as printed (3 walls) | 460 g (FILL guess) | 457.3 g | 422.6 g |
| Whole robot (bought parts + wiring 598 g) | 1058 g | 991 g | **983 g** |
| Clashes (289 bodies, printed and bought) | 2 | 0 | **0** |
| Centre of mass inside the 4 wheels | 49.0 mm | 48.6 mm | **48.8 mm** |
| Weight shift needed to lift a front foot (left / right) | -8.2 / -8.0 mm | -8.5 / -8.3 mm | **-8.4 / -8.2 mm** |
| Margin with a rear foot lifted (right / left) | +8.2 / +8.0 mm | +8.5 / +8.3 mm | **+8.4 / +8.2 mm** |

Every leg clearance sweep is exactly the v3 value (the legs did not change): knee pod vs belly 3.54 / 3.39 mm
(2.87 / 2.62 with the root fillet), paw vs desk 4.55 mm (band) and 5.01 mm (pod), paw vs thigh 14.6 mm, lead
corridors 3.48 mm (knee) and 2.79 mm (paw) for a 2.4 mm bundle. Every part is one piece in its exported STL,
fits the bed, and its STL matches the model in size and volume. All 56 assembly files sit at their modelled
positions.

**The stretch goal (robot 900 g, printed about 300 g) is not reachable without changing the approved look.** The
printed grams now sit in the outer skins, and 1.6 mm is the thinnest wall allowed. The five biggest shells (tub,
lid, head front, head back, side panels) are 192 g, half of the total, and most of that is their visible skin.
Getting to 300 g would need thinner visible shells (about 1.2 mm) or smaller parts, which is a design decision
for the owner.

## Screws (all M2 self-tapping, from the 500-piece kit, plus the servo bags)

Every length below was checked against the model: the screw reaches at least 2 mm into its pilot and stops
before the far side of the part.

| Where | Count | Screw | Note |
|---|---:|---|---|
| Hip MG90S tabs into the tub wall (from outside, under the side panels) | 8 | M2 x 6 | servo bag screws fit |
| Knee and wheel MG90S tabs into the leg outer halves | 16 | M2 x 6 | from the tab side into blind pilots |
| Tail MG90S tabs into the two ribs under the lid | 2 | M2 x 6 | driven up from inside |
| PCA9685 boards onto the upper two standoffs each | 4 | M2 x 6 | the lower standoffs are spacers only |
| Cross-horn arms into the **thighs** (hip horns) | 8 | **M2 x 4** | use horn holes 6.7-10 mm from the centre; a longer screw comes out through the thigh's face |
| Cross-horn arms into the **shins** (knee horns) | 8 | M2 x 6 | |
| Cross-horn arms into the **wheels** | 8 | M2 x 6 | use the outer horn holes (7.6 mm or more from the centre) |
| Cross-horn arms into the **tail root** | 2 | **M2 x 4** | the root is only 4.6 mm thick |
| Horn onto each spline (13 outputs) | 13 | the servo's own horn screw | then press the black cap in |
| Thigh and shin covers | 8 | M2 x 8 | thigh: from the outer face at the bottom of the knee disc (hidden by the shin); shin: from the outer face under the wheel |
| Lid to tub, through the chest and rump walls | 4 | M2 x 6 | hidden by the snap-in bands |
| Lid to collar, from inside the lid | 4 | M2 x 8 | fit before the lid goes on the tub |
| Head to collar, from inside the head | 4 | M2 x 8 | fit before the head back goes on |
| Muzzle to head, from inside the head | 4 | M2 x 8 | |
| Screen to the head front, through the 4 printed washers | 4 | M2 x 6 | |
| Ears, from inside the head | 2 | M2 x 8 | |
| Battery door to tub (heads under the black plugs) | 4 | M2 x 6 | v3.1 made the lugs 0.8 mm taller for this length |
| Battery clamp onto the door posts | 2 | M2 x 8 | |
| Touch pads: foil tab + wire clamped under the screw | 5 | **M2 x 4** | 4 under the lid, 1 under the head top; M2 x 6 would come through the top |
| Tail onto the tail root, from under the root | 1 | M2 x 8 | fit before the root goes onto the servo |
| **Total** | | **M2 x 4: 15, M2 x 6: 58, M2 x 8: 25** + 13 horn screws | the side panels, bands, head back, port doors, caps and plugs have no screws |

## Assembly order (the PDF guide will show each step)

The pictures `print_v3_1_png\Desk Buddy v3.1 - full assembly - section N (exploded, labelled).png` show each
section taken apart with every part named.

1. **Tub** (section 1). Push each hip MG90S through its slot in the tub wall from outside, lead first, tabs
   against the outside of the wall, and screw the tabs (2 x M2 x 6 each). Stand the two PCA9685 boards on their
   standoffs (2 x M2 x 6 each, top holes). Lay the protection board between its fences with the fuse holder on
   top, put the USB-C charger on its raised ledge with the socket in the rump opening, snap the KCD1 switch into
   the belly from outside, and stick the 5 VL53L0X boards to their inclines and wedges (foam tape).
2. **Battery door.** Holder between the fences, clamp over it (2 x M2 x 8). Screw the door to the belly
   (4 x M2 x 6) and press the 4 black plugs over the screw heads.
3. **Lid, not yet on the tub** (section 2). Fit the MPU6050, MPR121 and the perfboard hub in their fences (tape,
   and cable ties on the hub anchors), the side VL53L0X boards on their shelves, the tail MG90S under its ribs
   (2 x M2 x 6), and the 4 foil touch pads (M2 x 4). Screw the collar on from inside (4 x M2 x 8).
4. **Side panels.** Clip each panel on (4 snap hooks). Do this before the legs: the thigh cups hold the panels.
5. **Legs** (section 4) - see step 9. Their leads go through the slot in the side panel and down into the
   notch in the tub wall, then along the wall to the PCA9685.
6. **Close the body.** With every hip lead lying in its notch, put the lid on (its combs clamp the leads), screw
   it through the chest and rump walls (4 x M2 x 6) and snap the two bands over those screws.
7. **Tail.** Screw the cross horn into the tail root (2 x M2 x 4), fix the tail to the root (1 x M2 x 8 from
   below), push the root onto the tail servo's spline, horn screw, black cap.
8. **Head** (section 3). Screen into the head front (4 x M2 x 6 through the printed washers), mics into their
   rings, ears (1 x M2 x 8 each from inside), touch pad (M2 x 4), port doors and blanks pressed in. Muzzle: camera
   board on its rests, APDS-9960 on its shelf, then screw the muzzle on from inside the head (4 x M2 x 8). Screw
   the head to the collar from inside (4 x M2 x 8). Speaker in the head back's fences, then clip the head back on.
9. **Each leg** (section 4, the same for all four):
   1. Thigh outer half: cross horn into the hip pocket (2 x M2 x 4), knee MG90S tabs onto the knee end
      (2 x M2 x 6); the case points away from the body (forward on the front legs, backward on the rear legs).
   2. Leads: the knee lead leaves its pod at the end nearest the knee and runs up the channel; the wheel lead
      comes up the shin, through the window in the knee ring, half a turn round, and out through the small
      hole at 12 o'clock in the thigh face. Both run up the thigh channel into the hip cup at 6 o'clock.
   3. Thigh cover: slide its tongue into the window at the bottom of the hip cup, press until both hooks click,
      then 1 x M2 x 8 from the outer face at the bottom of the knee disc.
   4. Shin the same way (wheel MG90S 360 tabs 2 x M2 x 6, cross horn 2 x M2 x 6, cover M2 x 8 under the wheel).
   5. Wheel: cross horn in (2 x M2 x 6, outer holes), onto the wheel servo spline, horn screw, cap, then stretch
      the O-ring into the groove.
   6. Push each horn onto its spline, drive the horn screw through the 6 mm hole, press the cap in with its
      notch at the bottom.
10. Before powering up, move every joint through its whole range by hand and check no lead is pinched.

## Joint limits (for the firmware)

Angles are measured from the modelled pose (every leg straight down). **+ moves the foot forward** (toward the
head), **- moves it back**. The hip angle turns the thigh; the knee angle turns the shin relative to the thigh.
The firmware has to map these to each servo's own direction (the left and right legs are mirrored).

| Legs | Limit | Why |
|---|---|---|
| Front legs | none needed inside hip +/-30 x knee +/-50 | the paw pod stays at least 11.5 mm under the belly |
| Rear legs | **when the hip is above +25 deg, keep the knee at or below +45 deg** | at hip +30 / knee +50 the rear paw pod comes within 0.9 mm of the belly. It never touches, but the firmware should keep 2 mm. With this rule the gap never drops below 4.6 mm |

The exact table the rule comes from (`build_v3_1_report.txt`, 2 mm margin): rear legs hip +29: knee up to +49;
hip +30: knee up to +48; everything else unrestricted. The gait itself (shin tilt = hip + knee between -9.9 and
+19.8 deg) never gets near these poses. They only matter for tricks like sitting or folding a leg.

(The v3 report said "-1.6 mm" for this pose. That check used the whole paw outline, including the toe, which
sits at |x| 60-61 - outside the body, which ends at |x| 48.6 - so it could never hit the belly. Only the paw pod
passes under the body.)

## Numbers the model does not show

- **Tilt sign.** All paws point forward. This assumes gait.py's +19.8 deg shin limit means "toe up". If it is
  the other way round, set `PAW_DZ = -1` and run the script again.
- **Leads.** The wheel lead needs about 200 mm to the PCA9685 and the knee lead about 135 mm. Don't cut them
  shorter. Stock PVC leads flex at 2 coils per leg; silicone wire lasts longer.
- **Heat.** The knee and paw pods are closed PLA. Check a knee pod with a thermocouple before long walks
  (stop above 45 deg C).
- **Heat-set inserts** are a good upgrade for the covers you open often (battery door, lid).

## Decisions made for v3.1, and why

| Decision | Why |
|---|---|
| Grams come from slicing the exported STLs, not from one FILL factor | Thin shells print almost solid and thick slabs print at 50-60 %, so one factor was wrong both ways. The model was checked against hand calculations (within 2 %). |
| Hidden walls 1.6 mm (4 lines of a 0.4 nozzle) and 2 walls in the slicer | This is what brings the robot under 400 g without touching the outside. With 3 walls no interior change gets under about 420 g. 1.6 mm walls print solid with 2 walls, so nothing becomes a hollow sandwich. |
| Screen frame kept at 2.4 mm (a 0.8 mm plate inside the 1.6 mm face) | The glass seats where it did, and the approved 2.2 mm bevel round the window needs 2.4 mm to cut into. |
| Pads under every screw head that sits on a thin wall (collar and muzzle screws, ears) | Keeps 2.0 mm or more under each head. The front collar screws needed a notch in the head back's lip, because their heads sit where the lip slides in. |
| Knee and paw pods kept at the v3 1.8 mm | They are covers round the servo case (the servo is held by its tabs on the 5-10 mm outer halves). Thickening them would change the outside or squeeze the servo. They are not thinner than v3. |
| Snap detent pockets in the head front 0.4 mm deep (1.2 mm skin behind them) | The only place under 1.6 mm: a 5 x 2 mm recess the barb clicks into. The hook's beam and root are on the head back and unchanged. |
| Side panels kept exactly v3 (1.8 mm skin) | A 1.6 mm skin would save 2.8 g, but they sit just behind the centre of mass, and the balance margin mattered more. |
| Perfboard hub moved 9 mm rearward under the lid | Lightening the lid and tub (behind the centre of mass) had moved it 0.4 mm forward. The hub move takes back half of that for free. 16 mm would have hit the tail socket. |
| Tail cap peg 1.0 mm (v3 1.2) | Leaves 0.6 mm between the cap and the tail horn, so a horn up to 0.5 mm thicker than estimated still fits. The cap looks the same from outside. |
| Rear-leg joint limit in firmware instead of new geometry | Nothing touches (0.9 mm at the extreme pose), the gait never goes there, and changing the paw would change the approved look. |
| Battery door lugs 0.8 mm taller | So the door uses the same M2 x 6 as everything else. |
| Two ribs inside the head back | It is the widest thin flat panel (126 x 98 mm at 1.6 mm). |
| The script opens every part without a window when it builds the assembly | v3's build opened 56 part windows, ran SOLIDWORKS out of Windows GDI objects, and stopped. That is also why the last v3 run never finished. |

## Pictures in `print_v3_1_png\`

- one picture per part, `ALL PRINTED PARTS - sheet.png`
- `Desk Buddy v3.1 - full assembly - iso / front / side / back / top / under / inside (shells see-through).png`
- `... - section 1 Body / 2 Lid / 3 Head / 4 Leg (exploded).png` and the same with `(exploded, labelled)`: each
  label points at a pixel of its own part. The printed parts are moved apart and the bought parts stay where
  they are fitted, so you can see where each one goes.
- `label masks (...)\` holds the flat-colour pictures used to place the labels. Nothing to print; ignore it.

To rebuild everything: `python build_print_parts_v3_1.py` (about 50 minutes). To redo only the pictures:
`--sections` (section pictures) or `--assembly-only` (assembly and all its pictures, after restarting SOLIDWORKS).
