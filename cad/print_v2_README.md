# Desk Buddy - print model v2

Built by `build_print_parts_v2.py` (SolidWorks 2025). All parts share one coordinate frame, so the
assembly `print_v2\Desk Buddy v2 - full assembly.SLDASM` needs no mates and every clash is checked
body-against-body (report: `build_v2_report.txt`).

| Folder | What is in it |
|---|---|
| `print_v2\` | SolidWorks only: 23 printed parts, the bought-parts model, the assembly |
| `print_v2_stl\` | one STL per printed part (each checked against the model after export) |
| `print_v2_png\` | a picture of every part, 4 views of the assembly, and a sheet of all parts |

## Step 1 - print the Fit_Test_Coupon first (about 20 g, about an hour)

It has one of every critical fit. When the parts arrive, try each one:

1. **MG90S servo** drops into the slot with a little play, and its bag screws bite into the two slotted holes.
2. **KCD1 rocker switch** snaps into the rectangle and holds.
3. **Screen boss**: an M2 x 6 screw goes into the small post and grips.
4. **Clearance hole + counterbore**: an M2 screw slides through and its head sits flush.
5. **Horn pocket**: a double-arm servo horn drops into the pocket flush, and two small screws bite into the slots.
6. **O-ring groove**: a 22 mm O-ring stretches into the groove and stands a little proud of the rim.
7. **Laser and gesture windows**: hold the VL53L0X and APDS-9960 boards behind them. The sensor chip must show through.

If a fit is wrong, change the number in the MEASURE table at the top of the script, run it again, and
print the coupon again. Only then print everything else.

## Step 2 - measure these with the caliper when the parts arrive

Everything else was checked against published drawings. These were not published, so the model uses a
safe guess:

| Number in the script | Guess | What to measure |
|---|---|---|
| `SV_UNDER` | 21.0 | MG90S: case bottom to the underside of the mounting tabs |
| `SV_SPLINE` | 14.4 | MG90S: tab underside to the top of the output spline |
| `SV_TAB_T` | 2.8 | MG90S tab thickness |
| `SV_HOLES` | 28.15 | MG90S: centre-to-centre of the two tab holes (the model already allows +/-0.45) |
| `HORN_OUT`, `HORN_T`, `HORN_W`, `HORN_REACH`, `CROSS_REACH` | 1.0 / 1.8 / 6.6 / 17.5 / 11.5 | the horns in the servo bag: how far the arm face sits above the spline, arm thickness, arm width at the hub, centre-to-tip |
| `SCREEN_STACK` | 4.5 | Guition screen: front of the glass to the front of the circuit board |
| `OR_CS` | 2.4 | O-ring thickness (the 22 mm one from the Syneco kit) |
| camera board | 57 x 28 | ESP32-S3 CAM board: length, width, and which face the USB-C ports are on |
| speaker | 28 x 31 x 15 | the speaker box (the fences allow up to 30.6 x 33.6) |
| VL53L0X | small 10.5 x 13.8 or big 25 x 12 | which size arrived, and where the sensor chip is on it |

## Screws

Servo bags: 2 mounting screws + 1 horn screw per servo, 13 servos. From the M2 kit:

| Where | Count | Size |
|---|---|---|
| PCA9685 boards to the standoffs | 8 | M2 x 6 |
| Screen to the head | 4 | M2 x 6 |
| Lid to torso (front and back walls) | 4 | M2 x 8 |
| Neck to lid, neck to head | 8 | M2 x 8 |
| Head back cover (side walls) | 4 | M2 x 6 |
| Muzzle to head | 4 | M2 x 6 |
| Battery clamp | 2 | M2 x 8 |
| Horns to the printed legs, wheels and tail (if the servo bags have no small horn screws) | 26 | M2 x 6 (twist them through the horn holes) |

## Notes the model does not show

- **Hip swing:** keep each hip within about 30 degrees either way in software. At about 36 degrees the knee
  servo touches the bottom edge of the torso.
- **Wires:** the knee and wheel servo leads go up the leg and into the torso through the two floor slots
  beside each hip. Leave a loop of slack at each joint.
- **Capacitors on the hub board:** lay the 1000 uF capacitors on their side. There is 13 mm under the
  hub board.
- **KCD1 switch wires:** solder them and bend them sideways. There is about 8 mm above the terminals.
