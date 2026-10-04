# Desk Buddy - print model v3.2 (1 Oct 2026)

v3.2 is v3.1 with the face, camera and colour decisions of 29 Sep - 1 Oct built in, plus the walking fixes
the stability reviews asked for. Everything is made and checked by `build_print_parts_v3_2.py` (SolidWorks,
driven from Python, helpers in `swlib_v3_2.py`); the raw numbers are in `build_v3_2_report.txt`. v1, v2, v3
and v3.1 files are untouched. For everything not listed here (servo measurements to take, screws, joint
limits, assembly order) the v3.1 README still applies - `print_v3_1_README.md`.

| Folder / file | What is in it |
|---|---|
| `print_v3_2\` | SolidWorks files only: 56 robot parts, 5 test prints, the bought-parts model, `Desk Buddy v3.2 - full assembly.SLDASM` |
| `print_v3_2_stl\` | one STL per printed part (each checked after export: size, volume, 1 piece, fits the 223 x 220 x 205 bed) |
| `print_v3_2_png\` | a picture of every part; iso / front / side / top / back / under / inside; tuft close-ups (front, 3/4, side); head "section" (shells see-through, side and 3/4); 4 exploded + labelled section pictures |
| `build_v3_2_report.txt` | every check with its numbers |

## What changed from v3.1

1. **One face.** The muzzle, its port door and blank, and the 4 face screws are gone. The screen draws the nose
   and mouth. The face below the screen is plain 1.6 mm shell (no holes, no pads).
2. **Forehead camera under a tuft (owner decision 1 Oct; style "Plush" from 3D preview v7.1).** The OV5640 lens
   sits centred on the brow, 5.8 mm above the screen glass, behind a 6.2 mm hole (0.6 mm chamfer) just under **Spike's signature cowlick**: a caramel `Tuft` of 5 short, plump, rounded locks that grow from one
   thin base, all lean toward the robot's left and sweep back. It is 15.5 mm tall (10.6 mm above the head top;
   the ears are 34 mm) and 25.6 mm wide, 0.9 g. Nothing of the tuft enters a 70 deg cone above the lens.
   - The tuft's thin base sits on a small flat 45 deg seat (x +-11.2) cut 0.4 mm into the head's top-front round,
     located by 2 dia 2 pins in 2 holes and **glued** (CA or 2-part epoxy). A screw could not get enough thread
     in 1 g of plush locks, and the screw lands showed below the tuft - so no screws here.
   - The module sits between two guides inside the head front (a dot of glue fixes it), its lens 1.0 mm behind
     the wall, so the barrel clears the head's top round and only a dark dot shows. Beyond the seat the tuft's
     underside follows the head's round exactly.
   - **Colour:** print it in caramel. The preview's cream-to-caramel gradient cannot be printed on a single-
     nozzle printer. (Plush or Flick, and the final colour, are still open; v3.2 is built as Plush.)
   - **Print:** on its flat base (the seat face) on the bed; the locks rise at 50 deg or less, so at most the
     curled tips want a touch of tree support. Locks are 2.2 mm or thicker everywhere.
   - The ears are the plain v3.1 ears (no sensors, no inner triangles).
3. **Camera board inside the head.** The ESP32-S3 CAM board stands upright behind the screen in two rails
   (head front, floor to roof); two posts on the head back press its top against the rails when the head back
   clips on. Its USB-C end points down; flash it with the head back off. **No pin headers on this board.**
   The flex runs from the module's top edge back under the roof and down into the board's connector
   (16.5 mm of path, so the flex must be about **19 mm or longer** from the module edge - measure yours).
   Mounted this way the image is upside down: the camera firmware must set `vflip` and `hmirror`.
4. **Gesture sensor (APDS-9960) moved to the chest.** Inside the tuft it needed a 31 x 35 mm slab (the board is
   21 x 15.5 mm), which made the tuft a lump, not a cowlick. It now sits in a pocket in the chest wall behind
   the chest band, at x +24 (robot's left), looking forward through a 10 x 8 window identical to the obstacle
   laser's. A blank twin window on the right keeps the band symmetric (three matching windows). In front of the
   chip there is a 0.6 mm skin with a 5 x 3.4 mm slot, so the window shows plain wall + a small dark slot. Hands
   waving 5-20 cm in front of Spike are in its field; the desk is below it. Its lead now stays inside the body.
5. **Collar tag.** A 22 x 21 mm cream tag hangs from a peg on the collar front (keyhole: lift, hook over the peg
   head, let it drop). The face has a 17 x 16 x 0.6 mm recess for the logo sticker or a printed insert.
   Decorative only; its bottom is 2.75 mm above the chest laser window.
6. **Paw pods clear the desk in the tilt poses.** Two changes:
   - a 3.5 x 45 deg chamfer on each paw pod's inboard lower edge (the lead gap behind it is filled so the wall
     stays 1.6 mm, 0.6 mm clear of the wheel servo's case corner);
   - a **bigger tyre with the same O-ring**: the wheel groove is r 15.5 (was 13.9), so the 26 x 2.4 O-ring is
     stretched 19 % (was 7 %; O-ring drive belts run at 10-25 %) and the tyre radius is 17.7 (was 16.3). The
     wheels are 33.9 mm across (were 30.7). This lifts the whole robot 1.4 mm. Why both: the chamfer alone gains
     only ~0.1-0.5 mm, because the wheel servo's case corner (with its minimum wall) is what meets the desk.
     Details in "Clearances".
7. **Desk-edge lasers look 15 deg ahead of straight down** (was 25). A level desk now reads about 90 mm (was 95)
   and 99 mm at the gait's +3.5 deg nose-up (was 106), so the 110 mm edge alarm is no longer 4-5 mm away. The
   edge spot is still 21 mm ahead of the front wheels (glide stopping distance ~8 mm).
8. **Rump ballast pockets.** Two closed pockets in the tub floor under the rear hip servos, closed by flush
   caramel `Ballast_Cover_Left/Right` (press fit, pry notch) in the belly. **Coins do not fit anywhere at the
   rump:** the largest free round is 16 mm (AU 5c is 19.4, $2 is 20.5, 20c is 28.65). Each pocket takes a steel
   slug 24 x 7.5 x 15.8 mm = 22.3 g (cut from 25 x 8 mm flat bar, or stack 3 x 2.5 mm plates), 44.6 g for both.
   Lead shot or fishing sinkers also work (~30 g per pocket).
9. **Caramel Pup colours** as SolidWorks appearances (see "Filament colours").
10. Smaller items: the head touch pad moved 4.7 mm back (z 53.3) so the camera flex passes in front of it; the
    centre top snap hook of the head back moved to x -12 (it was under the new touch-pad boss).

## Files to ignore
`Tuft_Mask (...)` files in `print_v3_2\`, `print_v3_2_stl\` and `print_v3_2_png\` are left over from an earlier
v3.2 tuft design (a separate dark mask part). The final design has no mask; they are not in the assembly. Do not
print them (files are never deleted here - remove them yourself if you like).

## Filament colours (Caramel Pup) and slicer settings
Slicer settings are exactly the v3.1 ones (2 walls, 0.8 top/bottom, 15 % gyroid, 0.2 mm layers) - see the v3.1
README. **Robot total 381.7 g as printed** (v3.1: 385.7 g; the muzzle went, the tuft, tag and ballast covers came).

| Colour | Hex | Parts |
|---|---|---|
| cream | #F1DEC2 | Torso_Lid, Head_Front, Head_Back, Tail_Root, Collar_Tag |
| caramel | #B97A4F | Torso_Bottom, Side_Panel x2, Battery_Door, Battery_Clamp, Ballast_Cover x2, every Thigh/Shin outer half and cover, Wheel x4, Ear x2, Tuft, Tail |
| band brown | #A56A43 | Band_Chest, Band_Rump, Collar |
| cocoa | #4A3326 | the 13 hub caps, Port_Door_Head, Port_Blank_Head, Screw_Plugs, Screen_Washers (hidden - any dark filament) |

Ask Deer Park which cream / caramel / brown / dark-brown PLA they stock before the first print; the tuft is one
flat colour (caramel), not the preview's gradient.

## Print jobs and cost (Deer Park bands: $1 <= 10 g, $2 <= 20 g, $4 <= 40 g, $6 <= 60 g; or $1.10 per 10 g)
| Plate | Filament | Parts | g | Band | per 10 g |
|---|---|---|---:|---:|---:|
| T1 (first) | any | Fit_Test_Coupon, Coupon_Knee_Thigh, Coupon_Knee_Shin, Coupon_Snap_White, Coupon_Snap_Graphite | 26.3 | $4 | $2.89 |
| C1 | caramel | Torso_Bottom, Ballast_Cover x2, Battery_Clamp, Tail, Tuft | 55.1 | $6 | $6.06 |
| C2 | caramel | Side_Panel x2, Battery_Door, Ear x2 | 45.9 | $6 | $5.05 |
| C3 | caramel | Thigh outer x4, Thigh cover x4 | 58.0 | $6 | $6.38 |
| C4 | caramel | Shin outer x4, Wheel x4 | 50.0 | $6 | $5.50 |
| C5 | caramel | Shin cover x4 | 32.0 | $4 | $3.52 |
| K1 | cream | Torso_Lid, Tail_Root, Collar_Tag | 48.6 | $6 | $5.35 |
| K2 | cream | Head_Front | 37.9 | $4 | $4.17 |
| K3 | cream | Head_Back | 31.4 | $4 | $3.45 |
| B1 | band brown | Collar, Band_Chest, Band_Rump | 19.0 | $2 | $2.09 |
| D1 | cocoa | 13 caps, 2 port door/blank, screw plugs, screen washers | 3.8 | $1 | $0.42 |
| **Robot** | | 56 files | **381.7** | **$45** | **$41.99** |

New print notes: `Tuft` - flat base (its 45 deg seat face) on the bed; at most a touch of tree support under
the curled tips. `Collar_Tag` - back face down. `Ballast_Cover` - outer (lip) face down. The wheels are now
dia 33.9 (fit-test the groove on the `Fit_Test_Coupon` first: the O-ring should need a firm stretch and sit
without twisting).

## Checks (from `build_v3_2_report.txt`, all on the EXPORTED files)
- 61 printed parts (56 robot + 5 test prints) built, 1 piece each in the model and in the STL, STL size and volume = model, all fit the bed.
- **0 clashes** over 297 bodies (printed vs printed, printed vs bought, bought vs bought).
- Assembly: 57 of 57 files at their modelled positions.

## Mass and centre of mass
| | total | CoM x / y (height above desk) / z | on 4 wheels | lift front L / R | lift rear R / L |
|---|---:|---|---:|---:|---:|
| v3.1 | 983 g | +0.2 / 25.5 (107) / +17.2 | 48.8 mm | -8.4 / -8.2 | +8.4 / +8.2 |
| v3.2 without ballast | 981 g | +0.3 / 26.5 (109) / +15.8 | 50.2 mm | -7.3 / -7.0 | +7.3 / +7.0 |
| **v3.2 with 2 slugs (44.6 g)** | **1025 g** | +0.3 / 25.6 (108) / **+12.4** | **53.6 mm** | **-4.5 / -4.2** | +4.5 / +4.2 |

The head change alone moves the weight 1.4 mm back; the slugs another 3.4 mm (4.8 mm total, the stability
research asked for ~5). The body sits 1.4 mm higher (bigger tyres).

## Servo loads and stability (re-run; outputs in `v3_2_servo_load_check_output.txt`, `v3_2_stability_check_output.txt`)
- `servo_load_check_v3_2.py`: worst case is still the instant wheel stop (skid), hip 1.71 kg.cm static (v3.1
  1.74). Spin-in-place hip load +8 % (heavier robot), wheel torque 0.196 kg.cm (11 % of stall, was 9 %).
- Lift poses re-optimised for each robot (`stability_scripts/reopt_v3_2.py`, the research's optimiser):

  | worst joint, kg.cm | v3.1 | v3.2 no ballast | v3.2 with ballast |
  |---|---:|---:|---:|
  | front paw lifted 12 mm (gait), margin 8 | 0.33 | 0.30 | **0.26** |
  | give paw (30 mm up, axle 12 ahead), margin 8 | 0.39 | 0.35 | **0.32** |
  | crossing (four paws, weight over the diagonal) | 0.43 | 0.37 | **0.20** |

  **The firmware keyframes must be re-tuned for v3.2**: the research's v3.1 angles on the v3.2 robot lean too
  far back (give-paw from a puppy sit then peaks at 0.79 kg.cm). The IMU learning rule does this, or use the
  angles in `v3_2_stability_check_output.txt`.

## Clearances
- Leg sweeps (report): knee pods vs belly 2.62-3.54 mm (as v3.1); paw band / pod vs desk over the gait 5.95 /
  6.41 mm (v3.1 4.55 / 5.01); lead corridors unchanged; the rear-leg joint limit is unchanged (hip >= +29 ->
  knee <= +48).
- Paw pods vs the desk in the tilt poses (`stability_scripts/pod_clearance_v3_2.py`, real pod shape, every paw):

  | pose | v3.1 | v3.2 (research angles) | v3.2 re-optimised |
  |---|---:|---:|---:|
  | give paw from stand (8 mm) | 1.6 | 3.1 | **4.7** |
  | give paw from puppy sit (6 mm) | 1.2 | 2.7 | - |
  | curious tilt | 2.2 | 3.7 | - |
  | sniff (back paw up) | 1.4 | 2.9 | - |
  | gait B_FL / crossing | 4.5 / 4.6 | 5.9 / 6.0 | 5.4 / 5.3 |

  The target >= 3 mm is met for the give-paw from the stand (demo this first) and every re-optimised pose;
  the puppy-sit and sniff poses at their old v3.1 angles are 2.7-2.9 mm.
- **Research pose that cannot work:** the "Sit (8 deg)" row (rear knees -48) puts the rear paw pods 6 mm into the
  desk in both v3.1 and v3.2. Keep the firmware sit.

## Open decisions
1. Tuft style Plush (built) or Flick, and its colour (caramel built; a gradient is not printable).
2. The bigger tyre (O-ring stretch 7 -> 19 %). If you would rather not stretch the O-ring that much, set
   `OR_GROOVE_R = 13.9` back in the script: the paws then clear the desk by 1.7-2.5 mm in the give-paw poses.
3. Ballast: buy / cut 2 steel slugs 24 x 7.5 x 15.8 mm (or fill with lead shot). Coins do not fit. Try the tape
   test first (day-1 test 3).
4. Measure the delivered OV5640 flex (needs >= 19 mm from the module edge) and the APDS-9960 chip position
   (assumed centred on the 21 x 15.5 board; the chest window allows +-3 mm).
