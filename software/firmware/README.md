# Spike's firmware: how to put it on the robot

This page is written to be read aloud. It tells you how to load Spike's software onto the two boards
when they arrive, one step at a time, and what you should see after each step.

## What is in this folder

There are two programs. The first one goes on the screen board, the big Guition board with the 4.3 inch
screen. It draws Spike's face, runs his whole personality, plays his sounds, listens with the two
microphones, talks to the laptop, and drives all thirteen servos and every sensor. The second program goes
on the small camera board in the muzzle. It only sends pictures to the laptop.

Spike does not need the laptop to be alive. Without it he still blinks, looks around, gets bored and falls
asleep, loves head pats, giggles when you boop his nose, gets scared at the desk edge, and gets hungry
when his battery is low. The laptop adds talking, seeing you, alarms and games.

## Before you start

You need the laptop, one data-capable USB-C cable, and this project folder. The build tool is already
installed inside the laptop brain's Python environment, so you do not need to install anything else.

Every command below is typed into a Windows terminal. Wherever a command starts with pio, type the full
path instead: D colon, backslash, Claude-Projects, backslash, RobotCompanion, backslash, software,
backslash, laptop, backslash, dot venv, backslash, Scripts, backslash, pio dot exe. It is easier to copy it
from FLASHING_CHECKLIST.md, which has every command written out.

Always unplug the 5 volt lead from the board before you plug the USB cable into it. Two power sources on
one board can damage the board or the laptop's USB port. This is rule six in the assembly guide.

## Step 1: back up the screen board's factory program

Do this once, the day the screen board arrives, before you flash anything. It lets you put the seller's
demo back if you ever need to. The checklist has the exact esptool command. It reads the whole 4 megabyte
flash into a file called guition factory backup dot bin. Keep that file.

## Step 2: flash the screen board on the desk

Plug the screen board into the laptop with the USB cable. Nothing else needs to be connected for this step.
Open a terminal in the folder software, firmware, screen board, and run pio run, then pio run with the
option minus t upload. The first build takes a few minutes. When it finishes, the board restarts by itself.

What you should see: Spike's face appears within about two seconds. It is the Classic Pup face: cream fur,
a brown patch around one eye, big glossy eyes. He blinks, his eyes dart around, and his ears twitch.
If you touch his nose he goes cross-eyed and giggles. If you touch anywhere else he gets a happy squish and
little hearts pop up.

Now open the monitor with pio device monitor. You should see lines that start with display, touch and
audio, and every ten seconds a line that starts with face, which tells you the frame rate. Please write
down the frame rate and the render time from that line. They tell us whether the face is fast enough.
On the bench, without the robot's body attached, the body lines will say that no servo board was found.
That is expected.

If the screen stays black, check the monitor for a line saying PSRAM allocation failed. If the face shows
but touching does nothing, the monitor will say GT911 not found, and the touch pins need checking. Both
are listed in OPEN_QUESTIONS.md.

## Step 3: tell Spike about your Wi-Fi and the laptop

The first time Spike starts without any saved Wi-Fi, he opens his own setup Wi-Fi network called Spike
Setup, followed by six letters and numbers. Join it with your phone. A setup page opens by itself. If it
does not, open a browser and go to 192.168.4.1. Type your home Wi-Fi name, your Wi-Fi password, the
laptop's IP address, and the pairing token from the brain's settings file, the value called SPIKE TOKEN.
You can also set an update password there. Press Save. Spike restarts and joins your Wi-Fi.

You can do the same thing by typing into the monitor instead. Type help to see the commands. For example,
type wifi, then your network name in quotes, then your password in quotes. Then type brain followed by
the laptop's IP address, then token followed by the pairing token, then reboot.

Remember that the laptop's Wi-Fi must be set to Private in Windows, the firewall must allow the brain's
port, which is 8765, and the router's 2.4 gigahertz band must be on.

What you should see: start the brain on the laptop. Within a few seconds the monitor says brain hello,
and the brain's window shows that a face client connected. Say "Spike" and he should perk his ears.

## Step 4: flash the camera board

Unplug the camera board's 5 volt lead, plug it into the laptop, and run the same two commands in the
folder software, firmware, camera board. Then set it up the same way as the screen board: its setup
network is called Spike Cam Setup. One extra setting matters here. Type robot, followed by the screen
board's device id. The screen board prints its id at startup, and it looks like spike, dash, and six
letters and numbers. This tells the laptop that both boards belong to the same dog.

What you should see: the camera's monitor says camera sensor PID 5640, which means the OV5640 camera
answered. Once it is linked, every thirty seconds it reports how many frames it sent. If it says camera
init failed, the camera pins need checking against the seller's pin sheet. That is item eight in
OPEN_QUESTIONS.md.

## Step 5: the body, after the wiring chapter of the guide

Do this only after chapter 4 of the assembly guide, with the robot propped on a block so the legs and
wheels are in the air. The guide's servo test sketch is used first, to centre the servos and find each
wheel's stop point. Write every number into the guide's calibration table.

Then flash the Spike firmware again. At startup the monitor lists each servo board, each of the seven
lasers, the motion sensor and the touch board. The servos come on one at a time, about a sixth of a second
apart, legs first, so the power supply is never asked for a big surge.

Now type your calibration numbers in. Type servo show to see all thirteen joints and their numbers. For
each joint, type servo center, the joint number, and the pulse from your table. Then type servo test and
the joint number. The joint should move its foot forward, toward the head, for one second. If it moves
backward instead, type servo dir, the joint number, and minus one. When everything is right, type servo
save. The numbers are kept even when the power is off.

Type servo sensors to see one reading from every laser, the motion sensor, the touch pads and the battery.
On the desk the three desk-edge lasers should read roughly 80 to 110 millimetres (about 94 is expected).
Spike measures this level reading by himself when he stands still for a second after starting, and his
"this is an edge" limit becomes that reading plus 25 millimetres. Hold the nose out over the edge of the
desk: the front ones should jump far above that limit, and Spike should look scared and whine.

Walking and giving a paw come after that. Type gait help to see the commands, and follow section 5d of
FLASHING_CHECKLIST.md step by step: first the balance calibration (gait cal), then one paw held up
(gait lift left 30), then a short walk (gait walk 4), then give paw (gait paw left).

## Step 6: away from home, with your phone as Spike's brain

Firmware version 0.2.0 lets your phone be Spike's brain when the laptop is not around. The phone talks to
the screen board over Bluetooth, and when the camera or heavy traffic is needed, the phone makes a Wi-Fi
hotspot and both boards join it. At home the laptop always wins: while the laptop is connected, Spike
politely tells the phone he is busy, and the phone app switches to talking to the laptop.

First, a one-time bench step, so that the camera board can follow Spike onto the phone's hotspot. Plug the
screen board into the laptop, open the monitor, and type linkkey. Spike prints a line that starts with the
word linkkey, followed by sixty-four letters and numbers. That is the robot's own secret key, made on its
first start. Copy that whole line. Then plug in the camera board, open its monitor, paste the line and
press enter. The camera board says the key is saved. Restart the camera board. You only ever do this once
per robot, and a factory reset does not remove it. Keep that line private: do not put it in a photo or a
chat. If you ever need to, typing linkkey forget on the camera board removes it.

Second, pairing your phone. In the Spike app, look for Spike nearby. He shows up as Spike, a dash, and six
letters and numbers. When you pair, Spike shows six big digits on his face with a blue bar that shrinks,
and your phone asks you to type a code. Type the six digits within one minute. If you are too slow, just
try again: Spike makes a new code every time. Only someone who can see Spike's face can pair, and your
phone stays paired after that, so next time it connects by itself. Spike remembers up to four phones; a
fifth one replaces the phone that was used longest ago.

To see the Bluetooth state, type ble in the screen board's monitor. It shows whether a phone is connected,
whether it is paired, and the list of paired phones. Typing ble forget removes every paired phone, and so
does a factory reset. Typing status now also prints a links line: which brain Spike follows, which Wi-Fi he
is on, and whether the camera reached the phone's hotspot.

A few things to know. The phone's hotspot must be on the 2.4 gigahertz band, because the boards have no 5
gigahertz radio. On iPhones, turn on Maximise Compatibility in the Personal Hotspot settings. The robot
never saves the hotspot name or password; after a restart he goes back to your home Wi-Fi. While he is on
the phone's hotspot, wireless updates are switched off. Away from home the phone listens and speaks for
Spike, so his own microphones rest and his mouth moves to the phone's voice.

## What keeps Spike safe

All of this runs on the robot itself and never waits for the laptop. If a desk-edge laser loses the desk,
the wheels slow to a stop within about a tenth of a second, gently enough not to yank the legs, and
from full speed he stops in about 12 millimetres. If the robot is picked up or falls over, the wheels stop
and the legs relax. At 7.0 volts Spike warns that his battery is low, and at 6.8 volts he lies down and
switches all his servos off until you charge him and switch him on again. If the software ever freezes,
a supervisor switches the servo outputs off within a third of a second, and the watchdog restarts the
board within three seconds. While it restarts, the 2.2 kilohm resistor holds the servo boards off.

## Wireless updates

Once you have set an update password, you do not need the USB cable any more. Set the password in an
environment variable called SPIKE OTA PASSWORD, then run pio run with the option minus e ota, the option
minus t upload, and the option upload port followed by the robot's IP address. The servos switch off
during an update. If an update fails halfway, the old firmware keeps running.

## If something goes wrong

The monitor always tells you what the robot sees. Type status for Wi-Fi, laptop and battery, and servo
sensors for the body. Type factory reset to erase all the settings and start again with the setup network.
OPEN_QUESTIONS.md lists everything the firmware had to guess before the parts arrived, and how to check
each one on the first day.
