# Desk Buddy guide - wiring data.
# Sources: shopping/BOM_Audit_2026-09-26.md 2d (rules, pin plan, fuse position, OE resistor, battery
# divider), shopping/DeskBuddy_Parts_List.html (what each part does), cad/print_v3_1_README.md and
# cad/build_print_parts_v3_1.py (where each board sits, which wall each PCA9685 stands on).
# Anything the sources do not settle is listed in guide/OPEN_QUESTIONS.md.

# Wire colour key: (colour name, CSS colour, what it carries)
WIRE_KEY = [
    ('red, thick (7.5 A)', '#d62828', 'battery + after the fuse, switched battery, 5 V to the servo boards'),
    ('black, thick (7.5 A)', '#222222', 'battery - and power ground'),
    ('red (Dupont)', '#e63946', '5 V to the screen board and camera board'),
    ('black (Dupont)', '#333333', 'every signal ground'),
    ('orange', '#f4a261', '3.3 V to the sensors and the servo boards\' logic'),
    ('blue', '#1d6fd8', 'I2C data (SDA)'),
    ('yellow', '#e9c46a', 'I2C clock (SCL)'),
    ('green', '#2a9d8f', 'wheel stop (servo boards\' OE)'),
    ('white', '#bbbbbb', 'battery level (to IO5)'),
    ('purple', '#7b2cbf', 'laser on/off (XSHUT)'),
    ('grey', '#8d99ae', 'touch pads'),
    ('brown', '#8b5a2b', 'microphone lines (mark each one with tape)'),
]

# Connection table: (id, from, to, wire, length, note)
POWER = [
    ('P1', 'Cell holder, black lead (-)', 'Protection board B-', "holder's own lead", 'as supplied', 'long enough for the door to sit beside the robot'),
    ('P2', 'Metal link between the two cells', 'Protection board BM (middle)', 'thin red or white, soldered', '10 cm', 'the "middle wire" - solder it with the cells OUT'),
    ('P3', 'Cell holder, red lead (+)', 'Protection board B+', "holder's own lead", 'as supplied', 'connect last (negative, middle, positive)'),
    ('P4', 'Protection board P+', 'Fuse holder, lead 1', 'red, thick', '5 cm', '7.5 A blade fuse fitted'),
    ('P5', 'Fuse holder, lead 2', 'USB-C charger BAT+ (OUT+)', 'red, thick', '8 cm', 'the fuse protects the charger too'),
    ('P6', 'Fuse holder, lead 2 (same joint as P5)', 'Power switch (KCD1) terminal 1', 'red, thick', '12 cm', ''),
    ('P7', 'Protection board P-', 'USB-C charger BAT- (OUT-)', 'black, thick', '8 cm', ''),
    ('P8', 'Protection board P-', 'Hub GND pad', 'black, thick', '25 cm', 'slack so the lid lifts off'),
    ('P9', 'Power switch (KCD1) terminal 2', 'Hub BATT-SW pad', 'red, thick', '25 cm', 'slack so the lid lifts off'),
    ('P10', 'Hub BATT-SW / GND', 'Mini560 #1 (servos) IN+ / IN-, Mini560 #2 (boards) IN+ / IN-', 'red / black, thick', 'on the hub', '7.4 V in'),
    ('P11', 'Mini560 #1 OUT+ / OUT-', 'PCA9685 A and B, green V+ / GND screw terminal', 'red / black, thick', '20 cm each', '5 V servo power only'),
    ('P12', '1000 uF capacitor #1', 'Across Mini560 #1 OUT (+ leg to OUT+)', 'capacitor legs', 'on the hub', 'the stripe marks the - leg'),
    ('P13', 'Mini560 #2 OUT+ / OUT-', 'Screen board port P1: 5 V / GND only', 'red / black (MX1.25 plug)', '30 cm', 'through the collar; P1 only, never BAT'),
    ('P14', 'Mini560 #2 OUT+ / OUT-', 'Camera board 5V / GND pins', 'red / black (Dupont)', '30 cm', 'through the collar'),
    ('P15', '1000 uF capacitor #2', 'Across Mini560 #2 OUT (+ leg to OUT+)', 'capacitor legs', 'on the hub', ''),
]

SIGNAL = [
    ('S1', 'Screen board port P4: 3.3 V, GND, IO17, IO18', 'Hub 3V3, GND, SDA, SCL rails', 'orange, black, blue, yellow (MX1.25 plug)', '30 cm', 'through the collar; IO17 = SDA, IO18 = SCL (the servo sketch checks)'),
    ('S2', 'Hub 3V3 / GND / SDA / SCL', 'PCA9685 A and B: VCC, GND, SDA, SCL', 'orange, black, blue, yellow', '20 cm each', 'VCC is 3.3 V logic - NOT 5 V'),
    ('S3', 'Hub 3V3 / GND / SDA / SCL', 'MPU6050 (VCC, GND, SDA, SCL)', 'orange, black, blue, yellow', '10 cm', 'under the lid'),
    ('S4', 'Hub 3V3 / GND / SDA / SCL', 'MPR121 (3.3V, GND, SDA, SCL)', 'orange, black, blue, yellow', '10 cm', 'under the lid'),
    ('S5', 'Hub 3V3 / GND / SDA / SCL', '7 laser sensors (VIN, GND, SDA, SCL)', 'orange, black, blue, yellow', '10-25 cm', '2 in the lid, 5 in the tub'),
    ('S6', 'Hub 3V3 / GND / SDA / SCL', 'APDS-9960 gesture sensor (VCC, GND, SDA, SCL)', 'orange, black, blue, yellow', '30 cm', 'through the collar to the muzzle'),
    ('S7', 'Screen board IO14', 'Hub OE pad -> PCA9685 A OE and B OE', 'green', '30 cm', '2.2 kOhm from the OE pad to 3V3 (wheel stop)'),
    ('S8', 'Hub BATT-SW -> 10 kOhm -> VBAT pad -> 4.7 kOhm -> GND', 'Screen board IO5 from the VBAT pad', 'white', '30 cm', 'reads the battery; after the switch, so it never drains the pack when off'),
    ('S9', 'PCA9685 B channels 9-15 (PWM pin)', 'XSHUT pin of each laser (see the laser table)', 'purple', '10-25 cm', 'turns the lasers on one at a time at boot'),
    ('S10', 'MPR121 E0, E1, E2, E3, E4', 'Foil pads: back-left, back-right, rump-left, rump-right, head', 'grey', '5-30 cm', 'the wire is clamped under the pad screw'),
    ('S11', 'Screen board port P3: IO6, IO7, IO15', 'Both mics: SCK (IO6), WS (IO7), SD (IO15); 3.3 V and GND', 'brown (MX1.25 plug)', '10 cm', 'both mics share all three lines'),
    ('S12', 'Left mic L/R pin', 'GND (right mic L/R pin to 3.3 V)', 'black / orange', '3 cm', 'tells the two mics apart'),
    ('S13', 'Speaker (1.25 mm plug)', 'Screen board "Speak" port', "speaker's own lead", 'as supplied', 'never connect a speaker wire to ground'),
    ('S14', '13 servo leads', 'PCA9685 headers (see the servo table); brown wire on the GND row', "servo's own lead", 'do not cut', 'wheel lead needs about 200 mm, knee lead about 135 mm'),
]

# Servo channels: (servo, board, channel, lead route)
SERVO_CH = [
    ('Hip, front-left', 'A (left wall, 0x40)', 0, 'straight through the left tub wall'),
    ('Knee, front-left', 'A', 1, 'front-left leg, through the side-panel slot'),
    ('Wheel, front-left (360)', 'A', 2, 'front-left leg, through the side-panel slot'),
    ('Hip, back-left', 'A', 4, 'straight through the left tub wall'),
    ('Knee, back-left', 'A', 5, 'back-left leg, through the side-panel slot'),
    ('Wheel, back-left (360)', 'A', 6, 'back-left leg, through the side-panel slot'),
    ('Tail', 'A', 8, 'down from the lid'),
    ('Hip, front-right', 'B (right wall, 0x41)', 0, 'straight through the right tub wall'),
    ('Knee, front-right', 'B', 1, 'front-right leg, through the side-panel slot'),
    ('Wheel, front-right (360)', 'B', 2, 'front-right leg, through the side-panel slot'),
    ('Hip, back-right', 'B', 4, 'straight through the right tub wall'),
    ('Knee, back-right', 'B', 5, 'back-right leg, through the side-panel slot'),
    ('Wheel, back-right (360)', 'B', 6, 'back-right leg, through the side-panel slot'),
]

# Lasers: (sensor, where, board B channel for XSHUT)
LASER_CH = [
    ('Front obstacle', 'behind the chest band window', 9),
    ('Rear obstacle', 'behind the rump band window', 10),
    ('Desk edge, front-left', 'tub floor incline, left of the switch', 11),
    ('Desk edge, front-right', 'tub floor incline, right of the switch', 12),
    ('Desk edge, rear', 'tub floor incline at the rump, centred', 13),
    ('Side, left', 'shelf under the lid, left wall', 14),
    ('Side, right', 'shelf under the lid, right wall', 15),
]

# Rules - BOM audit 2d, in plain words. Each is a full sentence (read aloud by text-to-speech).
RULES = [
    ('Never use the screen board\'s BAT port.',
     'That port is for one 3.7 V cell, and the 7.4 V pack would destroy the board. Feed 5 V into port P1, using only its 5 V and GND wires. Check each wire against the printed labels with the multimeter first.'),
    ('Sensors get 3.3 V only.',
     'Every sensor, and the logic pin (VCC) of each servo board, runs on 3.3 V. Only the green V+ screw terminal of the servo boards gets 5 V. Before you connect any module, measure its SDA and SCL pins: they must read 3.3 V or less.'),
    ('Build the battery pack in this order.',
     'Take the cells out of the holder. Solder a short wire to the metal link between the two cell positions: this is the middle wire the protection board needs. Check that the two cells are within 0.05 V of each other. Connect negative first, then the middle wire, then positive. Plug the charger in once to wake the protection board up.'),
    ('The fuse comes straight after the protection board.',
     'It sits before both the charger and the switch, so a short anywhere in the robot blows the fuse instead of cooking a wire.'),
    ('Charge with the robot switched off.',
     'Use a 5 V, 2 A phone charger and a USB-A to USB-C cable. This charger cannot run the robot while it charges.'),
    ('Unplug the 5 V leads before you plug in the laptop.',
     'Before you connect a USB cable to the screen board or the camera board, unplug that board\'s 5 V lead from the hub. Two power sources on one board can damage it or the laptop port.'),
    ('Wheel stop.',
     'The servo boards\' OE pin goes to IO14, with the 2.2 kOhm resistor to 3.3 V. Do not use 10 kOhm, and never use IO46. The firmware turns on the watchdog, which restarts the board if the code freezes; while it restarts, OE is pulled high and every wheel stops. Run the first tests with the robot propped on a block.'),
    ('Battery limits in the code.',
     'The firmware warns at 7.0 V, and at 6.8 V it parks the robot and switches the servos off.'),
    ('Speaker.',
     'It plugs into the "Speak" port. Never connect either speaker wire to ground.'),
    ('Servo setup.',
     'Centre each leg servo before you fit its horn. Each wheel servo\'s stop point is found in software.'),
]

# ---------------------------------------------------------------------------------------------------------
# FIRMWARE PIN AND CHANNEL MAP - every pin / address / channel decision in one table.
# The same table is printed as Appendix 9.4 "Firmware pin and channel map" and copied into
# guide/OPEN_QUESTIONS.md section D. tools/servo_center/src/main.cpp uses exactly these values.
# (what, value, note)
PINMAP = [
    ('Brain', 'Guition JC4827W543C screen board (ESP32-S3)', 'drives both servo boards and every sensor'),
    ('I2C SDA', 'IO17 (port P4)', 'P4 order not confirmed; the servo sketch also tries SDA=IO18/SCL=IO17'),
    ('I2C SCL', 'IO18 (port P4)', '100 kHz; one bus, star-wired at the hub'),
    ('Wheel stop / servo enable', 'IO14 -> OE of PCA9685 A and B', 'LOW = outputs on; 2.2 kOhm pull-up to 3.3 V, so reset/crash = all servos off. Never IO46'),
    ('Battery voltage', 'IO5', 'divider 10 kOhm (top) / 4.7 kOhm (bottom) after the switch: V_bat = V_pin x 14.7 / 4.7; warn 7.0 V, park + servos off 6.8 V'),
    ('Microphones (I2S, both mics)', 'SCK IO6, WS IO7, SD IO15 (port P3)', 'left mic L/R pin to GND (left channel), right mic L/R pin to 3.3 V (right channel)'),
    ('Speaker', 'screen board "Speak" port (built-in amp)', 'no GPIO wiring'),
    ('Screen board power', 'port P1: 5 V and GND only', 'from Mini560 #2; never the BAT port'),
    ('PCA9685 A', 'I2C 0x40, left tub wall', 'no address pads bridged; 50 Hz'),
    ('PCA9685 B', 'I2C 0x41, right tub wall', 'A0 pad bridged; 50 Hz'),
    ('PCA9685 all-call', '0x70', 'default; ignore (the sketch turns all-call off)'),
    ('Servo A ch 0 / 1 / 2', 'hip / knee / wheel, FRONT-LEFT', 'wheel = MG90S 360 (continuous)'),
    ('Servo A ch 4 / 5 / 6', 'hip / knee / wheel, BACK-LEFT', ''),
    ('Servo A ch 8', 'tail', 'A ch 3, 7, 9-15 unused'),
    ('Servo B ch 0 / 1 / 2', 'hip / knee / wheel, FRONT-RIGHT', ''),
    ('Servo B ch 4 / 5 / 6', 'hip / knee / wheel, BACK-RIGHT', 'B ch 3, 7, 8 unused'),
    ('Laser XSHUT on B ch 9-15', '9 front obstacle (chest), 10 rear obstacle (rump), 11 desk-edge front-left, 12 desk-edge front-right, 13 desk-edge rear, 14 side left, 15 side right',
     'PCA9685 full-on = XSHUT high; all start at 0x29; wake one at a time and re-address. OE high also pulls these LOW: re-init the lasers after any OE-high event'),
    ('MPU6050', 'I2C 0x68', 'under the lid; INT not wired'),
    ('MPR121', 'I2C 0x5A', 'E0 back-left, E1 back-right, E2 rump-left, E3 rump-right, E4 head; E5-E11 unused; IRQ not wired (poll)'),
    ('APDS-9960', 'I2C 0x39', 'in the muzzle; INT not wired'),
    ('Camera board', 'ESP32-S3 CAM + OV5640, own firmware', '5 V + GND from Mini560 #2 only; talks to the laptop over Wi-Fi'),
    ('Servo pulses', '1500 us = centre (90 deg) / wheel stop nominal', 'per-servo trims and wheel stop points from the calibration table (guide 7.8)'),
    ('Joint sign', '+ = foot forward (toward the head)', 'left and right legs mirrored; back legs: hip above +25 deg -> knee at most +45 deg'),
]
