/*
 * captions.js -- the caption bank. 40+ short lines, grouped so
 * behaviour.js can pick one that matches the moment.
 *
 * Lines use the token {{name}} instead of a hard-coded "Spike"/"Spicy" --
 * render(line, mode) below swaps it for config.js's current dogName /
 * catName, so renaming either character never touches this file.
 *
 * Later these come from the laptop AI; this bank is the offline fallback
 * and the format the AI-generated lines should match (short, one or two
 * sentences, in character).
 */
(function (root) {
  'use strict';

  var CAPTIONS = {
    // Self-deprecating: bumping into things, tiny legs, low battery, jokes
    // about itself -- always affectionate, never actually sad about it.
    selfdep: [
      "Did you see that? I meant to walk into the table. Bold move, really.",
      "My legs are very small. I am doing my best. It's a lot of best.",
      "Battery at 12%. This is my dramatic death scene. ...Still here.",
      "I zoomed across the whole floor just now. Took four seconds. Athlete.",
      "I tripped over nothing. Nothing! I lost to nothing.",
      "Running at full speed, which is, uh, a determined walk.",
      "I'm not stuck under the couch, I'm doing a bit.",
      "Give me a second, I'm recalculating how to be cool about that."
    ],

    // Comforting first, gentle -- for sad/caring/sulking/cuddly moments.
    comfort: [
      "Hey. I'm right here, okay? Take your time.",
      "You don't have to talk. I'll just sit with you.",
      "That sounds heavy. I've got you.",
      "Bad day, huh. Bad days don't get the last word around here.",
      "I'm not going anywhere. Promise.",
      "Whatever it is, we'll figure it out together.",
      "You're allowed to feel like this. I'm still proud of you.",
      "Come here. Virtual head-on-your-lap, deployed."
    ],

    // Greeting / owner comes home / excited.
    greeting: [
      "YOU'RE BACK!! Okay okay okay hi hi hi!",
      "I heard the door and did a whole lap of the desk.",
      "Best part of my day, right here, right now.",
      "I was NOT staring at the door the entire time. Was too.",
      "You're home! Everything is instantly better.",
      "I saved up three whole stories for you. Ready? Go."
    ],

    // Teasing / playful, always affectionate.
    tease: [
      "Oh you want to play? That's adorable. I'm going to win.",
      "Was that your best trick? I've seen better from a houseplant.",
      "You blinked first. That's basically a rule now.",
      "I let you win that one. Definitely. On purpose.",
      "One more pat and I'm legally a puddle.",
      "Careful, I bite. Softly. Mostly for effect.",
      "I'm cute AND dangerous. Okay, mostly cute."
    ],

    // Sleepy / sleeping.
    sleepy: [
      "Five more minutes. Or four hundred.",
      "My eyes are doing the slow blink thing. It's happening.",
      "Sleep mode engaging in three... two...",
      "Dreaming about chasing something. Winning, obviously.",
      "Shh. Recharging my personality.",
      "If I stop moving it's because I'm asleep, not broken."
    ],

    // Alarm / wake-up, escalating urgency but still warm.
    alarm: [
      "Rise and shine! The day is out there being a day!",
      "I will keep barking. I have nowhere else to be.",
      "Okay this is the polite alarm. A LESS polite one is coming.",
      "Up up up! I made that sound extra enthusiastic just for you.",
      "Last warning before I start doing my most annoying trick.",
      "You up? You up. I can see you not being up."
    ],

    // Cat-sass -- Spicy specifically: ignores commands, then does them
    // anyway, pretend-bites after too many pats.
    catsass: [
      "I heard you. I am choosing to finish this nap first.",
      "Fine. FINE. I'll do the thing. Slowly. On my terms.",
      "That's my third warning pat. Next one gets a nibble.",
      "I don't do tricks. I do favours. Rare ones.",
      "You're lucky you're cute. That's the only reason I moved.",
      "Ordering me around? Bold. I respect it. Still not doing it fast.",
      "I pretend not to care. It's very convincing. I care a lot."
    ],

    // General idle chatter -- neutral/happy/curious/bored moments, and a
    // catch-all for the "human emotions" moods that don't need their own
    // dedicated bank (joy, hope, confusion, awe, and so on).
    general: [
      "Just vibing. Robot-dog things.",
      "What'cha doing? Genuinely curious, not just being nosy.",
      "I could nap or cause mischief. Fifty-fifty, honestly.",
      "Status report: good. Legs: small. Mood: fine.",
      "I've been staring at that spot for ten minutes. No regrets.",
      "Tell me something. Anything. I'm all ears. Metaphorically.",
      "Huh. Didn't expect that. In a good way, I think.",
      "I don't know what's happening but I'm feeling a lot about it.",
      "That was oddly beautiful. Robot-dog moment of the day.",
      "Wait, come back, I had a whole feeling about that."
    ],

    // Battery running low -- dramatic, self-deprecating, still funny.
    hungry: [
      "I'm wasting away over here… dramatically… very dramatically.",
      "Battery's low. Emotional damage is high.",
      "Feed me or watch me fade artistically into the carpet.",
      "This is my final form. Weak. Hungry. Still handsome.",
      "My tummy is doing the low-battery beep. That's a real sound it makes. Probably.",
      "I could power a small emotion right now. That's about it."
    ],

    // Charging finished -- happy and full.
    full: [
      "Ahh. Ten out of ten meal. Chef's kiss.",
      "Fully charged and deeply content. Don't talk to me for a second.",
      "That's the good stuff. Running at 100% smugness now too."
    ],

    // Time-of-day greetings.
    greetMorning: [
      "Morning! I've been up for ages. Okay, ninety seconds.",
      "Good morning! Today has so much potential. Statistically."
    ],
    greetAfternoon: [
      "Afternoon! How's the day treating you so far?",
      "Hey, it's afternoon already? Time flies when you're this cute."
    ],
    greetEvening: [
      "Evening! Prime couch-and-chill hours have begun.",
      "Good evening. My favourite shift: winding-down o'clock."
    ],
    greetLateNight: [
      "...why are you still up?",
      "It's very late. I'm not judging. I am absolutely judging.",
      "Late night club, population: us two."
    ],

    // "I'm fine!" beat after tripping/bumping into something.
    trip: [
      "I'm fine!",
      "That was intentional. Advanced maneuver, actually.",
      "Nailed it. ...Ish."
    ]
  };

  function pick(category) {
    var list = CAPTIONS[category] || CAPTIONS.general;
    return list[Math.floor(Math.random() * list.length)];
  }

  function render(line, name) {
    return line.replace(/\{\{name\}\}/g, name);
  }

  function pickRendered(category, name) {
    return render(pick(category), name);
  }

  var api = { CAPTIONS: CAPTIONS, pick: pick, render: render, pickRendered: pickRendered };
  root.Captions = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
