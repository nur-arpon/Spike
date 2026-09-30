/*
 * actions.js -- scripted PHYSICAL ACTIONS: face + pop-ups + sounds, each
 * tagged with an actionLabel (engine.actionLabel) that the robot's leg and
 * wheel firmware reads to move the body. Reused from v1's design, rebuilt
 * for the v2 face state and given real anticipation / follow-through.
 *
 * A step:  { hold (s), mood, sound, soundCat, soundArgs, particle, caption,
 *            over, kick, add, set, sniff, idle }
 *   over  spring-TARGET overrides for the step (they animate + overshoot)
 *   kick  spring impulses at the step start (hops, flinches, hiccups)
 *   add   overlay ADDED each frame: number or fn(age) -> number
 *   set   overlay that REPLACES a field each frame: number or fn(age)
 *   sniff n sniffs at the step start
 *   idle  false = no idle blinks/glances during the step
 * An action with restore:true returns to the mood it interrupted.
 */
(function (root) {
  'use strict';
  var isNode = typeof window === 'undefined';
  function dep(n, f) { return root[n] || (isNode ? require(f) : null); }
  var Behaviour = dep('Behaviour', './behaviour.js');
  var Sounds = dep('Sounds', './sounds.js');
  var Extras = dep('Extras', './extras.js');

  function jitter(amp, freq) {
    return function (a) { return amp * (0.6 * Math.sin(a * freq * 6.2832) + 0.4 * Math.sin(a * freq * 2.37 * 6.2832)); };
  }
  function pulse(peak, dur) { return function (a) { return peak * Math.sin(Math.min(1, Math.max(0, a / dur)) * Math.PI); }; }
  function decayShake(amp, freq, dur) { return function (a) { return amp * Math.sin(a * freq * 6.2832) * Math.max(0, 1 - a / dur); }; }
  // blink pulses at the given start times (0.08 s each)
  function blinks(times) {
    return function (a) { for (var i = 0; i < times.length; i++) if (a >= times[i] && a < times[i] + 0.08) return 1; return 0; };
  }

  var ACTIONS = {
    wakeUp: { label: 'wake-up', steps: [
      { mood: 'sleeping', hold: 0.6, idle: false },
      { hold: 1.3, sound: 'playYawn', idle: false,
        over: { shut: 0.85, mouthO: 1, open: 0.95, headSY: 1.12, headSX: 0.93, tilt: -7, earPerk: 1, smile: 0.2 } },
      { mood: 'sleepy', hold: 0.45, over: { headSY: 0.95, headSX: 1.04 } },
      { mood: 'neutral', hold: 0.5, set: { blinkL: blinks([0.05, 0.28]), blinkR: blinks([0.05, 0.28]) } },
      { hold: 0.4, add: { shakeX: decayShake(6, 7, 0.4), tilt: decayShake(5, 7, 0.4) }, kick: { earL: 300, earR: -300 } },
      { mood: 'happy', hold: 0.9, sound: 'playYip', soundCat: 'playMeow', caption: { category: 'greeting' },
        particle: ['sparkle', 240, 50, 4], kick: { bob: -140, headSY: 1.4 } }
    ] },

    fallAsleep: { label: 'fall-asleep', steps: [
      { mood: 'sleepy', hold: 1.0, sound: 'playSigh' },
      { mood: 'sleepy', hold: 1.0, idle: false, over: { lidTL: 0.82, lidTR: 0.82, tilt: 13, bob: 6 } },
      { hold: 0.35, idle: false, over: { lidTL: 0.25, lidTR: 0.25, tilt: 1, bob: -1, eyeScale: 1.08 }, kick: { headSY: 1.2 } },
      { mood: 'sleepy', hold: 1.0, idle: false, over: { lidTL: 0.86, lidTR: 0.86, tilt: 10, bob: 4 } },
      { mood: 'sleeping', hold: 1.8, sound: 'playSnore', caption: { category: 'sleepy' }, particle: ['zzz', 330, 70, 1] }
    ] },

    napping: { label: 'nap', steps: [
      { mood: 'sleeping', hold: 1.6, sound: 'playSnore', particle: ['zzz', 330, 70, 1] },
      { mood: 'sleeping', hold: 0.7, kick: { earL: 260 }, over: { smile: 0.6 } },
      { mood: 'sleeping', hold: 1.4, sound: 'playSnore', particle: ['zzz', 330, 70, 1] }
    ] },

    dozing: { label: 'doze', steps: [
      { mood: 'sleepy', hold: 0.6 },
      { hold: 0.9, idle: false, over: { tilt: 14, bob: 7, lidTL: 0.92, lidTR: 0.92 } },
      { hold: 0.35, idle: false, over: { tilt: 0, bob: -2, lidTL: 0.15, lidTR: 0.15, eyeScale: 1.1, browY: 0.8 }, kick: { headSY: 1.5, earL: -200, earR: -200 } },
      { mood: 'sleepy', hold: 0.7 },
      { hold: 1.0, idle: false, over: { tilt: -12, bob: 7, lidTL: 0.92, lidTR: 0.92 } },
      { hold: 0.35, idle: false, over: { tilt: 0, bob: -2, lidTL: 0.15, lidTR: 0.15, eyeScale: 1.1 }, kick: { headSY: 1.5 } },
      { mood: 'sleepy', hold: 0.8, caption: { text: "I'm awake. Totally awake." } }
    ] },

    deepSleepDreams: { label: 'dream', steps: [
      { mood: 'sleeping', hold: 2.0, sound: 'playSnore', particle: ['zzz', 330, 70, 1] },
      { mood: 'sleeping', hold: 1.8, sound: 'playWhine', caption: { category: 'sleepy' }, particle: ['heart', 330, 70, 1],
        over: { smile: 0.8, blush: 0.5 }, add: { earL: jitter(10, 3), earR: jitter(10, 3.3), noseDY: jitter(1.2, 5) } },
      { mood: 'sleeping', hold: 2.0, sound: 'playSnore', particle: ['zzz', 330, 70, 1] }
    ] },

    tripBump: { label: 'trip', steps: [
      { hold: 0.25, idle: false, over: { eyeScale: 1.22, mouthO: 1, open: 0.55, browY: 1.1 }, kick: { headSY: -1.8 } },
      { hold: 0.22, idle: false, over: { tilt: -22, bob: 10, icon: 'x', iconAmt: 1 }, kick: { bob: 90 } },
      { mood: 'dizzy', hold: 1.3, sound: 'playWhine', particle: ['dizzyStar', 240, 40, 3], over: { tilt: -8 } },
      { mood: 'embarrassed', hold: 1.6, caption: { category: 'trip' } }
    ] },

    sneeze: { label: 'sneeze', restore: true, steps: [
      { hold: 0.5, idle: false, over: { scrunch: 0.6, lidTL: 0.3, lidTR: 0.3, mouthO: 0.5, open: 0.25 },
        add: { noseDY: jitter(1.5, 9) } },
      { hold: 0.45, idle: false, over: { scrunch: 1, lidTL: 0.6, lidTR: 0.6, mouthO: 0.85, open: 0.6, tilt: -8, bob: -6, headSY: 1.09 } },
      { hold: 0.3, idle: false, sound: 'playSneeze',
        over: { shut: 1, scrunch: 0.2, mouthO: 0, open: 0.45, smile: 0.3, tilt: 6, bob: 7, headSY: 0.86, headSX: 1.1 },
        kick: { headSY: -2.5, bob: 150 }, particle: ['puff', 268, 178, 3] },
      { hold: 0.5, idle: false, over: { shut: 0.25 }, add: { shakeX: decayShake(7, 8, 0.5), tilt: decayShake(4, 8, 0.5) }, kick: { earL: 300, earR: -300 } },
      { hold: 0.7, caption: { text: 'Bless me!' }, over: { happy: 0.8, smile: 0.8 } }
    ] },

    hiccup: { label: 'hiccup', restore: true, steps: [
      { hold: 0.45 },
      { hold: 0.4, sound: 'playHiccup', kick: { headSY: 2.4, bob: -110 }, over: { eyeScale: 1.14, mouthO: 0.7, open: 0.25 } },
      { hold: 0.45 },
      { hold: 0.4, sound: 'playHiccup', kick: { headSY: 2.4, bob: -110 }, over: { eyeScale: 1.14, mouthO: 0.7, open: 0.25 } },
      { hold: 0.4 },
      { hold: 0.9, sound: 'playHiccup', kick: { headSY: 2.4, bob: -110 }, over: { eyeScale: 1.14, mouthO: 0.7, open: 0.25, blush: 0.6 },
        caption: { category: 'selfdep' } }
    ] },

    shiver: { label: 'shiver', restore: true, steps: [
      { hold: 1.9, sound: 'playShiverChatter', soundArgs: [1.8], caption: { text: 'B-b-brr, c-cold!' },
        over: { lidTilt: -0.4, earBack: 0.7, smile: -0.2, wobble: 1, blush: 0.45, mouthW: 0.7, eyeDY: 2 },
        add: { shakeX: jitter(2.6, 13), tilt: jitter(1.5, 11) } }
    ] },

    pant: { label: 'pant', restore: true, steps: [
      { hold: 2.3, sound: 'playPant', soundArgs: [2.1],
        over: { open: 0.75, tongue: 1, pant: 1, smile: 0.85, lidTL: 0.18, lidTR: 0.18, sweat: 0.7 },
        add: { bob: function (a) { return Math.sin(a * 17) * 1.4; } } }
    ] },

    tailWagDance: { label: 'happy-dance', steps: [
      { mood: 'joy', hold: 1.2, sound: 'playGiggle', soundCat: 'playTrill', particle: ['music', 240, 50, 2],
        add: { tilt: function (a) { return Math.sin(a * 9) * 9; }, bob: function (a) { return -Math.abs(Math.sin(a * 9)) * 6; },
          shakeX: function (a) { return Math.sin(a * 9) * 7; } } },
      { mood: 'joy', hold: 1.2, particle: ['heart', 240, 50, 2],
        add: { tilt: function (a) { return Math.sin(a * 9) * 9; }, bob: function (a) { return -Math.abs(Math.sin(a * 9)) * 6; },
          shakeX: function (a) { return Math.sin(a * 9) * 7; } } }
    ] },

    zoomies: { label: 'zoomies', steps: [
      { mood: 'excited', hold: 2.3, sound: 'playBark', soundCat: 'playTrill', caption: { category: 'selfdep' },
        over: { pant: 1, tongue: 1, open: 0.8 }, particle: ['confetti', 240, 70, 6],
        add: { shakeX: function (a) { return Math.sin(a * 12) * 10; }, tilt: function (a) { return Math.sin(a * 12) * 14; },
          lookX: function (a) { return Math.sin(a * 12 + 1); } } }
    ] },

    headTilt: { label: 'head-tilt', restore: true, steps: [
      { mood: 'curious', hold: 1.3, over: { tilt: 18 }, kick: { earL: -220 }, caption: { text: 'Hm?' } },
      { mood: 'curious', hold: 1.1, over: { tilt: -12 }, kick: { earR: 220 } }
    ] },

    sniffAround: { label: 'sniff', restore: true, steps: [
      { mood: 'curious', hold: 0.9, sniff: 3, over: { lookX: -0.85, lookY: 0.6, tilt: -7 } },
      { mood: 'curious', hold: 0.9, sniff: 3, over: { lookX: 0.85, lookY: 0.6, tilt: 7 } },
      { mood: 'curious', hold: 0.9, sniff: 2, over: { lookX: 0, lookY: -0.2, eyeScale: 1.1, browY: 0.9 },
        particle: ['exclaim', 300, 40, 1] }
    ] },

    beggingAction: { label: 'beg', steps: [
      { mood: 'begging', hold: 2.3, sound: 'playWhine', caption: { category: 'tease' },
        add: { tilt: function (a) { return Math.sin(a * 2.5) * 4; } } }
    ] },

    rollOver: { label: 'roll-over', steps: [
      { mood: 'playful', hold: 0.3, kick: { headSY: -1.2 }, over: { headSY: 0.95 } },
      { hold: 1.0, idle: false, over: { happy: 1, open: 0.5, tongue: 0.85 },
        set: { tilt: function (a) { var f = Math.min(1, a / 1.0); return 360 * (f < 0.5 ? 2 * f * f : 1 - Math.pow(-2 * f + 2, 2) / 2); } } },
      { mood: 'cuddly', hold: 1.0, sound: 'playYip', soundCat: 'playMeow', caption: { category: 'tease' }, kick: { headSY: 1.2 } }
    ] },

    playBow: { label: 'play-bow', steps: [
      { mood: 'playful', hold: 1.2, sound: 'playYip', caption: { text: 'Wanna play?' },
        over: { bob: 12, headSY: 0.92, headSX: 1.06, earPerk: 1.2, lookY: -0.5, tilt: 0 } },
      { mood: 'excited', hold: 0.9, kick: { bob: -220, headSY: 2 } }
    ] },

    // --- face-only helpers (still labelled so the body can join in) ------
    yawn: { label: 'yawn', restore: true, steps: [
      { hold: 1.4, sound: 'playYawn', over: { mouthO: 1, open: 1, shut: 0.75, tilt: -5, headSY: 1.08, earPerk: -0.3 } },
      { hold: 0.4, over: { shut: 0.3 } }
    ] },

    boop: { label: 'boop', restore: true, steps: [
      { hold: 0.6, idle: false, sound: 'playBoop',
        kick: { noseSY: -10, noseSX: 7, headSY: -1.3, earL: -200, earR: -200 },
        over: { cross: 1, mouthO: 0.75, open: 0.35, eyeScale: 1.12, browY: 0.9, earPerk: 1, icon: '', iconAmt: 0 } },
      { mood: 'laughing', hold: 1.5, sound: 'playGiggle', soundCat: 'playTrill',
        caption: { category: 'boop', catCategory: 'catboop' }, particle: ['heart', 240, 56, 3], over: { blush: 0.9 } }
    ] }
  };

  var ACTION_NAMES = ['wakeUp', 'fallAsleep', 'napping', 'dozing', 'deepSleepDreams', 'tripBump', 'sneeze',
    'hiccup', 'shiver', 'pant', 'tailWagDance', 'zoomies', 'headTilt', 'sniffAround', 'beggingAction',
    'rollOver', 'playBow'];
  var ACTION_LABELS = {
    wakeUp: 'Wake up', fallAsleep: 'Fall asleep', napping: 'Nap', dozing: 'Doze off',
    deepSleepDreams: 'Dream', tripBump: 'Trip', sneeze: 'Sneeze', hiccup: 'Hiccups',
    shiver: 'Shiver (cold)', pant: 'Pant (hot)', tailWagDance: 'Happy dance', zoomies: 'Zoomies',
    headTilt: 'Head tilt', sniffAround: 'Sniff around', beggingAction: 'Beg', rollOver: 'Roll over',
    playBow: 'Play bow', yawn: 'Yawn', boop: 'Boop'
  };

  function runStep(e, step) {
    if (step.mood) Behaviour.setMood(e, step.mood);
    if (step.kick) Behaviour.kick(e, step.kick);
    var snd = (e.mode === 'cat' && step.soundCat) ? step.soundCat : step.sound;
    if (snd && Sounds[snd]) Sounds[snd].apply(null, step.soundArgs || []);
    if (step.sniff) Behaviour.sniff(e, step.sniff);
    if (step.particle) Extras.burst(e.particles, step.particle[0], step.particle[1], step.particle[2], step.particle[3] || 1, null, e.rnd);
    if (step.caption) {
      if (step.caption.text) Behaviour.showCaption(e, step.caption.text, step.hold + 0.8);
      else Behaviour.say(e, (e.mode === 'cat' && step.caption.catCategory) || step.caption.category, step.hold + 1.2);
    }
    e._actionOver = step.over || null;
  }

  // opts.auto = started by idle life (a yawn), not by the person, so it
  // must not count as attention (otherwise an ignored Spike never sleeps)
  function playAction(e, name, opts) {
    var a = ACTIONS[name];
    if (!a) return false;
    var prev = e._action ? e._action.prevMood : e.mood;
    if (!(opts && opts.auto)) Behaviour.markInteraction(e);
    e.actionLabel = a.label;
    e._action = { name: name, steps: a.steps, index: 0, stepAt: e.time, restore: !!a.restore, prevMood: prev };
    runStep(e, a.steps[0]);
    return true;
  }

  function stopAction(e) {
    e._action = null; e._actionOver = null; e.actionLabel = null;
  }

  function update(e) {
    var a = e._action;
    if (!a) return;
    var step = a.steps[a.index];
    if (e.time - a.stepAt >= (step.hold || 0.5)) {
      a.index++;
      if (a.index >= a.steps.length) {
        var back = a.restore ? a.prevMood : null;
        stopAction(e);
        if (back) Behaviour.setMood(e, back);
        return;
      }
      a.stepAt = e.time;
      runStep(e, a.steps[a.index]);
    }
  }

  function applyOverlay(e, p) {
    var a = e._action;
    if (!a) return;
    var step = a.steps[a.index], age = e.time - a.stepAt, k;
    if (step.add) for (k in step.add) { var v = step.add[k]; p[k] = (p[k] || 0) + (typeof v === 'function' ? v(age) : v); }
    if (step.set) for (k in step.set) { var s = step.set[k]; p[k] = typeof s === 'function' ? s(age) : s; }
  }

  var api = { ACTIONS: ACTIONS, ACTION_NAMES: ACTION_NAMES, ACTION_LABELS: ACTION_LABELS,
    playAction: playAction, stopAction: stopAction, update: update, applyOverlay: applyOverlay };
  root.Actions = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
