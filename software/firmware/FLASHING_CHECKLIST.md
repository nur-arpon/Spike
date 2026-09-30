# Flashing checklist (tick as you go)

Commands are for a Windows terminal (PowerShell or cmd). `PIO` below means:

    D:\Claude-Projects\RobotCompanion\software\laptop\.venv\Scripts\pio.exe

Replace `COM5` with the port Windows gives the board (Device Manager > Ports, or `PIO device list`).

## Before any USB cable goes in
- [ ] The board's 5 V lead from the hub is UNPLUGGED (guide rule 6).
- [ ] The cable is data-capable (the phone test from the BOM audit 2a.6).
- [ ] Host tests still pass on the laptop: `sh software/firmware/test/run_tests.sh` in Git Bash ends with
      `protocol check: PASS`.

## 1. Screen board - factory backup (once, first day)
- [ ] `D:\Claude-Projects\RobotCompanion\software\laptop\.venv\Scripts\python.exe %USERPROFILE%\.platformio\packages\tool-esptoolpy\esptool.py --chip esp32s3 --port COM5 --baud 460800 read_flash 0 0x400000 guition_factory_backup.bin`
- [ ] The file is 4,194,304 bytes. Keep it (restore: `write_flash 0 guition_factory_backup.bin`).
- [ ] If the port does not appear: hold BOOT, tap RESET, release BOOT, try again.

## 2. Screen board - flash on the bench
- [ ] `cd D:\Claude-Projects\RobotCompanion\software\firmware\screen_board`
- [ ] `PIO run` ends with `SUCCESS` (RAM about 42 %, Flash about 77 %).
- [ ] `PIO run -t upload --upload-port COM5` ends with `Hard resetting`.
- [ ] Face appears within 2 s (Classic Pup), blinks, looks around.
- [ ] Touch the nose: cross-eyed, squeaky boop, giggle, hearts.
- [ ] Touch elsewhere: squish, hearts, pat squeak. Six fast pats: dizzy.
- [ ] Speaker plays the sounds (if silent: OPEN_QUESTIONS B6, swap BCLK/LRCK).
- [ ] `PIO device monitor` shows `display:`, `touch: GT911 at 0x5D`, `audio:` lines.
- [ ] Write down the `face: .. fps, render .. ms avg / .. ms max` line: ______ fps, ______ ms, ______ ms.
- [ ] Bench only: `body: servo board A (0x40) NOT FOUND` is expected without the harness.

## 3. Screen board - Wi-Fi and brain
- [ ] Windows: home Wi-Fi set to Private; firewall allows TCP 8765; router 2.4 GHz band on.
- [ ] Setup: join `Spike-Setup-xxxxxx`, fill the page (Wi-Fi, laptop IP, port 8765, SPIKE_TOKEN, update
      password), Save. Or in the monitor:
      `wifi "Home Network" "password"`, `brain 192.168.1.20`, `token <SPIKE_TOKEN>`, `otapass <pw>`, `reboot`.
- [ ] Start the brain (`software\laptop\run_spike.bat`).
- [ ] Monitor: `net: connected to ws://...` then `net: brain hello`.
- [ ] Note the device id from the boot line `device spike-xxxxxx ready`: ______________.
- [ ] Say "Spike": ears perk (listening); he answers and his mouth moves with the voice.
- [ ] While he talks, the mic stream pauses (brain log: no audio from the robot until 300 ms after).

## 4. Camera board
- [ ] 5 V lead unplugged, USB in.
- [ ] `cd D:\Claude-Projects\RobotCompanion\software\firmware\camera_board`
- [ ] `PIO run -t upload --upload-port COM6`
- [ ] Monitor: `camera: sensor PID 0x5640 ... OV5640` (another id on a cheap copy is logged, not fatal).
- [ ] Setup (`Spike-Cam-Setup-xxxxxx` or monitor): Wi-Fi, `brain <laptop-ip>`, `token ...`,
      `robot spike-xxxxxx` (the screen board's id), `reboot`.
- [ ] Monitor every 30 s: `camera: N frames sent, 0 dropped`. The brain sees you (Spike's eyes follow you).
- [ ] If the picture is upside down: `flip 1 0` (or `flip 0 1`), `reboot`.

## 5. Body (after guide chapter 4, robot propped on a block)
- [ ] Guide servo sketch done: horns fitted at centre, trims and wheel stop points in the calibration table.
- [ ] Flash the Spike firmware again (step 2 upload command).
- [ ] Boot log: servo board A and B found, `7 of 7 lasers running`, MPU6050, MPR121, APDS-9960.
- [ ] Outputs switch on one by one, 150 ms apart, legs first (about 2 s in total). Nothing buzzes against a stop.
- [ ] `servo show`, then for every joint `servo center <n> <us>` from the table (wheels: the stop point).
- [ ] For every leg joint `servo test <n>`: the foot moves FORWARD first. If not: `servo dir <n> -1` (or 1).
- [ ] `servo save`. Reboot and check `body: calibration loaded`.
- [ ] `servo sensors` on the desk: desk-edge lasers about 80-110 mm (the review estimates ~94 mm), IMU about
      0 0 1 g, battery about 7.4-8.4 V. Write down the three desk-edge readings: FL ____ FR ____ REAR ____ mm.
- [ ] Stand Spike still on the desk for 2 s, then `servo sensors` again: the `desk-edge thresholds` line says
      `measured this boot` and each threshold is about the reading + 25 mm. (If it says `none: 110 mm`, he was
      not standing still and level; wait, try again. The boot log line `desk-edge level readings ...` shows it too.)
- [ ] Nose over the desk edge: that front laser jumps far past its threshold, Spike looks scared, the wheels
      would not drive forward. Same for the rear laser backing up.
- [ ] Lift the robot: `imu pickup` in the brain log, cuddly face. Put it down: `putdown`.
- [ ] Pat the head pad and the back pads: happy face, `touch head` / `touch back` in the brain log.
- [ ] Wave a hand in front of the muzzle twice: Spike says hi.
- [ ] `servo pose sit`, `servo pose lie` (shallow crouch), `servo pose play-bow`, `servo pose stand`: smooth,
      balanced, no leg hits the belly.
- [ ] `servo play happy-dance` (still on the block): tail wags (at most +-30 deg), wheels wiggle once for
      half a second. `servo play zoomies`: two half-second spins with a pause between.
- [ ] `servo off`: every servo goes limp (OE high). Reboot to restore.

## 5b. Servo load tests (cad/servo_load_check_v3_1.md, day 1)
- [ ] **Torque pass line for walking (review):** spare MG90S, powered, holding centre, a stick on the horn,
      weights hung **25 mm** from the shaft. Test 3 of the 10 servos.
      - Hold **330 g for 10 s** (that is 0.8 kg.cm, the walk's worst moment): it must not droop more than about
        2 degrees (a pen mark on the horn and the case shows it). Servo 1 ____ servo 2 ____ servo 3 ____.
      - Hold **260 g for 60 s**: same droop limit, and it must stay cool enough to hold.
      - Stall: it must lift **450 g** from 30 degrees below horizontal (1.1 kg.cm).
      - If they fail: do the 60 g coin ballast test (5d step 12) before buying anything.
- [ ] **1.1 kg.cm test:** hang 450 g on the spare MG90S horn, 25 mm from the shaft, for 5 minutes (powered,
      holding centre). Hot or buzzing = walking would need MG92B servos. Result: ______________.
- [ ] **Pod temperature:** thermometer in a front knee pod after 10 min in `servo pose lie`, then after 10 min
      in `servo pose stand`. Stop above 45 deg C. Lie: ______ deg C, stand: ______ deg C.
- [ ] **Stop test:** on the desk, away from the edge, `servo play zoomies` / a drive, then watch the front hips
      as the wheels stop: with the firmware's 1.5 m/s^2 ramp they must NOT visibly give. (The old sudden stop
      yanked them back a few degrees.)
- [ ] **Start-up dip:** watch the monitor while switching on: the outputs come on one by one (about 2 s).
      There must be no `battery dipped under 7.2 V` line at start-up, and `servo sensors` right after must
      show the battery above 7 V. If a dip line appears, note the battery voltage: ______ V.

## 5c. Away mode (firmware 0.2.0, protocol v1.3) - one-time bench step + first pairing
- [ ] Both boards run 0.2.0 (the boot line says `firmware 0.2.0`). First screen-board boot prints
      `linkkey: made this robot's link key` and `ble: advertising as Spike-xxxxxx (on)`.
- [ ] Screen board monitor: `linkkey` -> copy the whole `linkkey <64 hex>` line (keep it private).
- [ ] Camera board monitor: paste that line -> `linkkey: saved`. `reboot`. The boot log says
      `away: link key set`. (`status` on the camera shows `link key set`.)
- [ ] Phone app: find `Spike-xxxxxx`, pair. Six big digits appear on Spike's face with a shrinking blue bar;
      type them on the phone within 60 s. Monitor: `ble: phone authenticated (bonded, LE Secure Connections)`,
      then `net: phone subscribed over BLE -- saying hello` and `phone brain over BLE hello`.
- [ ] Wrong digits on purpose once: pairing fails, the digits disappear, the monitor says `pairing failed`.
- [ ] `ble` lists the phone; `status` prints the `links:` line. With the laptop brain running, the phone gets
      `busy` (the app should say the laptop is in charge).
- [ ] Laptop brain off, phone app as the brain: pat Spike's head -> the phone reacts; drive with the joystick on
      the desk (edge lasers still stop him at the edge: try it slowly).
- [ ] Phone hotspot on (2.4 GHz; iPhone: Maximise Compatibility): the app sends it -> monitor `joining the
      phone's hotspot`, `on the phone's hotspot`, `handover: telling the camera board`; the camera monitor
      says `away: joining the phone's hotspot` and `connected to the phone brain`; the app shows the camera.
- [ ] Hotspot off in the app -> both boards say `back to the home Wi-Fi`.
- [ ] Write down the `free heap / PSRAM` numbers from the 10 s face log with BLE + Wi-Fi both up: ______ / ______.

## 5d. Walking and give-paw, day 1 (cad/stability_max_research.md + the review)
Do these in order, on a hard, clear desk at least 30 cm from any edge, with a hand ready to catch him. Every
command goes into the monitor. If anything looks wrong, type `gait stop` (paw goes down gently) or
`servo off` (everything limp at once). Stop and let the servos cool if a pod feels hot to hold.
- [ ] **1. 5b torque pass line done** (330 g for 10 s). Result copied here: ______________.
- [ ] **2. IMU direction.** Spike standing. Type `gait imu`: pitch and roll both near 0 (write them down:
      ____ / ____). Lift his **nose** about 2 cm with a finger and type `gait imu` again: pitch must be
      **larger** (more +). Put him down, lift his **right** side 2 cm (so the left side is lower): roll must be **larger** (more +). If either
      goes the wrong way, stop: the IMU axes in `body_hw.cpp imuRead` must be fixed first.
- [ ] **3. Kitchen-scale balance point.** Front paws on the kitchen scale, back paws on a book of the same
      height. Scale reading ______ g, whole robot ______ g. (The model says the front carries about 45 %.)
- [ ] **4. Wheels hold with the power off.** Spike standing, a hand lightly on his back. Type `servo off`
      (all outputs off, like the walk does to the wheels). Tie a thread to one paw, run it forward over the edge of a book
      and hang 50 g on it (it pulls the paw the way its wheel rolls): the paw must **not roll**. Try all four. Also nudge him gently:
      no leg may fold (the legs are unpowered too; that is research test 6). Reboot afterwards.
      Rolls or folds: ______________ (if a wheel rolls, stop before walking).
- [ ] **5. Level desk.** Put a phone spirit-level app on the desk where he will stand: under 1 degree.
- [ ] **6. Balance calibration.** Spike standing on that spot. Type `gait cal`. He shifts his weight
      forward-and-sideways several times, tries to lift each front paw a little, then lifts each back paw
      (about 25 s). Wait for `body: gait ..., calibration passed` (or `calibration failed`) and write it down:
      FL lean ______ FR lean ______ back ______. `gait show` repeats it. Failed? Do step 12, then again.
- [ ] **7. Front-paw lift, held 30 s.** `gait lift left 30`. The log prints `gait: front-left paw up, tilt
      +x / -y deg`. **Expected: about +3.5 / -2.8** (pitch / roll), progress near 1.00. Pass: the paw is about
      4 cm up, stays up the whole 30 s without rocking, and comes down gently. Tilt ____ / ____, paw up
      ____ cm. Then `gait lift right 30`: expected about **+3.5 / +2.8**. Tilt ____ / ____.
      - While the left paw is up: slide a 1.5 mm card (two playing cards) under the **back-left** paw pod's
        inner edge. It must pass. (Right paw: the back-right pod.) Pass / fail: ______.
      - Three-paw balance check: while the left paw is up, stack coins on the front-left corner of the head
        until the paw touches down. About 90 g = the planned 8 mm margin. Coins needed: ______ g.
      - Feel the front-right and back-left hip servos afterwards: warm is fine, too hot to hold is not.
- [ ] **8. Lean direction.** Watch the `gait: paw held ..., lean now ...` lines in step 7 and in a short walk
      (`gait walk 4`). If most front lifts end with `ABORT -- lift tilt not matched in time`, type
      `gait sign -1` and repeat step 7. If that is worse, `gait sign 1` again. Sign used: ____.
- [ ] **9. Back-paw lift.** `gait walk 2 rear` (glide, back-right paw, glide, back-left paw). Each back paw rises about 1.2 cm, quietly;
      a back lift costs almost nothing, so any buzzing means the servo centre calibration is off.
- [ ] **10. First walk.** `gait walk 4`. He glides forward 4 cm, stops, lifts the front-left paw, glides,
      lifts the back-right, and so on (about 20 s). The log ends `body: gait tilt-step, done`. Then `gait walk 4 back`.
      Write down anything odd: ______________.
- [ ] **11. Desk edge while walking.** Point him at the edge from about 12 cm away: `gait walk 8`. He must
      stop **before** the edge, with all four paws down, and log `body: gait ..., edge`. Do it slowly the first time
      with a hand beside the edge. Stopped ____ cm from the edge.
- [ ] **12. 60 g rump ballast (only if steps 6/7 struggle or the torque test was weak).** Tape five
      Australian 20-cent coins (about 56 g) on top of the rump. `gait cal` again: the lean numbers should go
      **down**, and step 7 should look steadier. With coins: FL lean ____ FR lean ____. Record it: this
      decides the v3.2 ballast pocket.
- [ ] **13. 10-minute heat test.** Thermometer tip taped inside a front pod. Repeat `gait walk 16` for
      10 minutes (each one about 80 s). **Stop above 45 deg C.** Pod temperature after 10 min: ____ deg C.
- [ ] **14. Give paw.** `gait paw left`: he leans, raises the left paw about 4 cm, reaching forward, for 1.5 s.
      Then `gait paw right`. The card test from step 7 again under the opposite back pod (in this pose the
      clearance is only about 1 mm: if the card does not pass, report it -- the pod edge needs the chamfer).
- [ ] **15. Puppy-sit paw (ONLY after steps 7, 13 and 14 passed).** `gait puppy on`, then `gait paw left sit`
      with a hand ready. Card test under the back-left pod. Anything wrong: `gait puppy off` (it stays off
      until switched on again). Result: ______________.

## 6. Wireless update (optional)
- [ ] `set SPIKE_OTA_PASSWORD=<pw>` (cmd) or `$env:SPIKE_OTA_PASSWORD="<pw>"` (PowerShell)
- [ ] `PIO run -e ota -t upload --upload-port <robot-ip>`; servos switch off during the update.
