# Spike's face, version 2

This folder is the new face for Spike, and for Spicy, his cat side. It runs in your web browser as a simulator of the robot's little screen. Everything works offline. There are no downloads and no internet calls, and every sound is made live by the browser.

Version 1 is still in the folder next to this one, called "face". Nothing in it was changed.

## How to open it

Double-click the file called index dot html. It opens in your browser. There is nothing to install.

## What is new in version 2

The face sits lower on the screen now, the way baby animals look. The eyes are just below the middle, and the nose and mouth are tucked in close underneath.

Nothing joins the two eyes any more. The line that looked like the rim of glasses is gone. There is a test that checks this every time.

The default face is your toy puppy. It has cream fur, a brown patch around one eye, big glossy dark eyes with two shiny highlights, a wet dark nose, a big smile with a red tongue, and floppy brown ears in the top corners.

Spicy has her own face. She is a calico cat, which is a nice touch, because calico cats are almost always girls. She has green cat eyes with eyelashes, a pink nose, a little "w" shaped mouth, whiskers and a pink bow. When she's calm she looks at you with half-closed, knowing eyes.

## Why it looks alive

Nothing on the face ever snaps. Every part moves like it is on a soft spring, so it overshoots a little and settles, the way a cartoon character moves.

When Spike blinks, his eyes squash shut and then stretch a little as they spring open. Sometimes he blinks twice.

His eyes make tiny darting movements all the time, and bigger glances now and then. The shiny spots in his eyes stay put as he looks around, like real reflections.

He breathes with a slow gentle bob. His ears flick now and then, and they swing when he tilts his head. He sniffs in little bursts of three, and his nose twitches when he's curious. Now and then he tilts his head at you.

When he is really happy, his cheeks push his eyes up into happy closed arcs. When he is sad, his eyes get watery with a wobbling waterline and extra sparkles.

## Touching the face

Click anywhere on the face to give him a head pat. His eyes close happily, his ears go flat, and little hearts pop up. If you pat too fast he gets dizzy. Spicy only puts up with a few pats before she gets cross and hisses.

Click his nose to boop it. He goes cross-eyed looking at his own nose, then giggles.

Move your mouse around and his eyes follow you. On the real robot the camera will do this.

## The panel on the right

The panel has four tabs.

Moods has one button for every mood. There are forty-three of them, from happy and sad to jealous, smug, awe and hungry. Each mood has its own little motion, so none of them is a still picture. "Play all moods" steps through every one.

Actions has the physical actions. They are wake up, fall asleep, nap, doze off, dream, trip, sneeze, hiccups, shiver, pant, happy dance, zoomies, head tilt, sniff around, beg, roll over and play bow. Each one also sends a body label, which the robot's legs and wheels will use later. You can see the label under the buttons while an action plays.

Life has the everyday things. You can say hi, get a greeting that suits the time of day, and try events like coming home, looking sad, being picked up, falling over, being ignored, talking, and a wake-up alarm with an "I'm up!" button. There is a battery slider too. Low battery makes him hungry. He gives you big pleading wet eyes, licks his lips, drools a little, his tummy rumbles, and a small battery blinks red above his head. On the Minimal and Night robot styles the battery shows in his eyes instead. Tick "Charging" and he eats happily until he's full. You can also play a song and he dances and sings along, or play rock, paper, scissors.

Face Studio is where you build your own pet face. It is explained next.

The buttons at the top switch between Spike and Spicy, turn the sound off, and show the face at its true size on the robot.

## The Face Studio

Every part of the face can be swapped. You can choose the fur colour and pattern, the eye style, shape and colour, eyelashes, eyebrows, nose, mouth, ears, cheeks and freckles, whiskers, and an accessory like a bow, bandana, glasses, a party hat or a flower.

Whatever you choose, the face still does every mood, every blink and every action. That is the most important rule of the Studio, and the tests check it with random faces.

There are nine ready-made faces to start from. They are Classic Pup, Spicy, Beagle, Husky, Minimal, Night, Anime Pup, Sticker Buddy and Midnight Tux. Minimal is white glowing eyes on black. Night is dim and warm for a dark bedroom.

"Roll the dice" makes a random face from colours that go well together.

There are three save slots, kept in this browser.

Each face also has a share code, a short line of letters starting with S P K 1. Copy it to share a face, and paste one in and press Load to use someone else's.

Spike and Spicy each keep their own face, so changing one doesn't change the other.

## Changing the names

The names and wake words live in one place, the file called config dot js. If you rename Spicy there, the whole page follows. That includes the buttons, the speech bubbles and the Face Studio.

## For the robot

The face only uses shapes the robot's screen library can draw: filled circles, ellipses, rounded rectangles, triangles, thick lines and arcs, with see-through blending. There are no blurs or glows. The eyelids aren't black bars. The eye is simply drawn only between the lid edges, so the lid you see is the real fur underneath.

The tool called export recipes writes every mood, face, preset and action into one data file for the robot's code.

## Checking it works

The automatic test is test slash smoke dot js. You run it with node, and at the moment it passes all of its twenty thousand checks. It draws every mood with every ready-made face and twenty random faces, for both Spike and Spicy. It also measures that the eyes, nose and mouth sit where you asked, checks that nothing is drawn between the eyes, and runs every event, action, the song and the battery.

A second check loads the real page without a browser and clicks through it. It is tools slash page check dot js, and it passes all forty-one checks. The page also fits narrow windows and phones now. The face shrinks to fit, and under about 900 pixels wide the controls move below the face.

The pictures of every face and every action are in the tools slash out folder.

## Not finished yet

The face hasn't been put on the real robot screen yet. The export file and the design notes are ready for that.

The speech lines are still a fixed list. Later they'll come from the laptop AI.

The battery slider is a test control. On the robot, the real battery reading will drive it.
