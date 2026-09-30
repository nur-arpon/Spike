/*
 * actions.js -- physical action sequences: face + extras + sounds, each
 * tagged with an `actionLabel` string that the future leg/wheel firmware
 * can read (engine.actionLabel) to drive the actual body movement. This
 * screen simulator only has a face, so things like "tail-wag" or
 * "play-bow" are approximated with face motion (squash/tilt/bob) -- the
 * label is the contract the hardware side will act on later.
 *
 * A action is an ordered list of steps. Each step is a plain object:
 *   { mood, hold, sound, soundArgs, particle, caption, anticipate,
 *     overlay, set }
 * All fields are optional except `hold` (seconds). `overlay` values are
 * ADDED to that frame's params; `set` values REPLACE them outright.
 * Both accept either a plain number or a function(ageSeconds) -> number,
 * so a step can animate (a sneeze spike, a roll's tilt sweep) without any
 * new drawing code.
 *
 * Depends on Behaviour (for setMood/showCaption/sayFromCategory/
 * anticipate/nowSeconds) and Sounds/Extras, all loaded earlier.
 */
(function (root) {
  'use strict';

  var isNode = typeof window === 'undefined';
  var Behaviour = root.Behaviour || (isNode ? require('./behaviour.js') : null);
  var Sounds = root.Sounds || (isNode ? require('./sounds.js') : null);
  var Extras = root.Extras || (isNode ? require('./extras.js') : null);

  function jitter(amp, freq) {
    return function (age) {
      return amp * (0.6 * Math.sin(age * freq * 6.2832) + 0.4 * Math.sin(age * freq * 2.4 * 6.2832));
    };
  }
  function pulseOpenClose(peak, durS) {
    // ramps up then back down across the step's own duration
    return function (age) {
      var t = Math.max(0, Math.min(1, age / durS));
      return peak * Math.sin(t * Math.PI);
    };
  }

  // ---------------------------------------------------------------------
  // The action table.
  // ---------------------------------------------------------------------
  var ACTIONS = {
    wakeUp: [
      { mood: 'sleepy', hold: 0.7 },
      {
        mood: 'sleepy', hold: 0.9, sound: 'playYawn',
        overlay: { mouthOpen: pulseOpenClose(0.9, 0.9), squashY: pulseOpenClose(0.15, 0.9) }
      },
      {
        mood: 'neutral', hold: 0.5,
        overlay: { blinkL: function (a) { return Math.max(0, Math.sin(a * 10)) * 0.6; },
          blinkR: function (a) { return Math.max(0, Math.sin(a * 10 + 0.6)) * 0.6; } }
      },
      { mood: 'happy', hold: 0.7, sound: 'playYip', caption: { category: 'greeting' } }
    ],

    fallAsleep: [
      { mood: 'sleepy', hold: 1.1, sound: 'playSigh' },
      { mood: 'sleeping', hold: 1.6, sound: 'playSnore', caption: { category: 'sleepy' } }
    ],

    napping: [
      { mood: 'sleepy', hold: 1.0, sound: 'playSnore' },
      { mood: 'sleepy', hold: 0.35, overlay: { topLidL: pulseOpenClose(-0.35, 0.35), topLidR: pulseOpenClose(-0.35, 0.35) } },
      { mood: 'sleepy', hold: 1.1, sound: 'playSnore' },
      { mood: 'sleepy', hold: 0.3, overlay: { topLidL: pulseOpenClose(-0.3, 0.3), topLidR: pulseOpenClose(-0.3, 0.3) } },
      { mood: 'sleeping', hold: 1.4 }
    ],

    dozing: [
      { mood: 'sleepy', hold: 0.7 },
      { mood: 'sleepy', hold: 0.3, overlay: { topLidL: pulseOpenClose(-0.3, 0.3), topLidR: pulseOpenClose(-0.3, 0.3) } },
      { mood: 'sleepy', hold: 0.7 }
    ],

    deepSleepDreams: [
      { mood: 'sleeping', hold: 2.0, sound: 'playSnore', particle: { type: 'zzz', x: 42, y: -88 } },
      { mood: 'sleeping', hold: 2.0, sound: 'playWhine', particle: { type: 'zzz', x: 42, y: -88 }, caption: { category: 'sleepy' } },
      { mood: 'sleeping', hold: 2.0, sound: 'playSnore', particle: { type: 'zzz', x: 42, y: -88 } }
    ],

    tripBump: [
      { mood: 'surprised', hold: 0.35, anticipate: { squashY: -0.05 } },
      { mood: 'dizzy', hold: 1.1, sound: 'playWhine', particle: { type: 'dizzyStar', x: 0, y: -70, opts: { orbitR: 50 } } },
      { mood: 'embarrassed', hold: 1.6, particle: { type: 'sweat', x: 26, y: -70 }, caption: { category: 'trip' } }
    ],

    sneeze: [
      { mood: 'neutral', hold: 0.18, overlay: { topLidL: 0.15, topLidR: 0.15 } },
      {
        mood: 'surprised', hold: 0.24, sound: 'playSneeze', anticipate: { squashX: 0.05, squashY: -0.06 },
        overlay: { squashX: pulseOpenClose(-0.14, 0.24), squashY: pulseOpenClose(0.18, 0.24) }
      },
      { mood: 'neutral', hold: 0.4 }
    ],

    hiccup: [
      { hold: 0.45 },
      { hold: 0.15, sound: 'playHiccup', overlay: { squashY: pulseOpenClose(-0.12, 0.15) } },
      { hold: 0.5 },
      { hold: 0.15, sound: 'playHiccup', overlay: { squashY: pulseOpenClose(-0.12, 0.15) } },
      { hold: 0.6, sound: 'playHiccup', overlay: { squashY: pulseOpenClose(-0.12, 0.15) }, caption: { category: 'selfdep' } }
    ],

    shiver: [
      {
        hold: 1.6, sound: 'playShiverChatter', soundArgs: [1.5],
        caption: { text: 'B-b-brr, c-cold!' },
        overlay: { faceTilt: jitter(3, 11), bobOffset: jitter(1.5, 12) }
      }
    ],

    pant: [
      { hold: 1.6, sound: 'playPant', soundArgs: [1.5], set: { mouthOpen: 0.5, tongueOut: 0.7, pantSpeed: 7 } }
    ],

    tailWagDance: [
      {
        mood: 'excited', hold: 1.8, sound: 'playGiggle', particle: { type: 'heart', x: 0, y: -60, count: 3 },
        overlay: {
          bobOffset: function (a) { return Math.sin(a * 10) * 5; },
          squashX: function (a) { return Math.sin(a * 10) * 0.05; },
          squashY: function (a) { return -Math.sin(a * 10) * 0.05; }
        }
      }
    ],

    zoomies: [
      {
        mood: 'excited', hold: 2.0, sound: 'playBark', caption: { category: 'selfdep' },
        overlay: {
          faceTilt: function (a) { return Math.sin(a * 14) * 10; },
          bobOffset: function (a) { return Math.abs(Math.sin(a * 14)) * -3; }
        }
      }
    ],

    headTilt: [
      { mood: 'curious', hold: 1.4 }
    ],

    sniffAround: [
      { mood: 'curious', hold: 0.6, sound: 'playSniff' },
      { mood: 'curious', hold: 0.6, sound: 'playSniff', overlay: { lookX: function (a) { return Math.sin(a * 3) * 0.4; } } },
      { mood: 'curious', hold: 0.6, sound: 'playSniff' }
    ],

    beggingAction: [
      { mood: 'begging', hold: 1.8, sound: 'playWhine', caption: { category: 'tease' } }
    ],

    rollOver: [
      { mood: 'playful', hold: 0.3, anticipate: { squashY: -0.05 } },
      {
        mood: 'playful', hold: 1.0,
        overlay: { faceTilt: function (a) { return (a / 1.0) * 360; }, squashY: function (a) { return -0.15 * Math.sin(a / 1.0 * Math.PI); } }
      },
      { mood: 'cuddly', hold: 1.0, sound: 'playYip', caption: { category: 'tease' } }
    ],

    playBow: [
      { mood: 'playful', hold: 1.2, sound: 'playYip', caption: { text: 'Wanna play?' }, set: { faceTilt: 18, bobOffset: 6 } }
    ]
  };

  var ACTION_NAMES = Object.keys(ACTIONS);
  var ACTION_LABELS = {
    wakeUp: 'Wake up', fallAsleep: 'Fall asleep', napping: 'Napping', dozing: 'Dozing',
    deepSleepDreams: 'Deep sleep (dreams)', tripBump: 'Trip / bump', sneeze: 'Sneeze',
    hiccup: 'Hiccups', shiver: 'Shiver (cold)', pant: 'Pant (hot)',
    tailWagDance: 'Happy dance', zoomies: 'Zoomies', headTilt: 'Head tilt',
    sniffAround: 'Sniff around', beggingAction: 'Beg', rollOver: 'Roll over',
    playBow: 'Play-bow'
  };

  function spawnParticle(engine, p) {
    if (!p) return;
    if (p.count) Extras.spawnBurst(engine.particles, p.type, p.x, p.y, p.count, p.opts);
    else Extras.spawn(engine.particles, p.type, p.x, p.y, p.opts);
  }

  function runStep(engine, step, t) {
    if (step.mood) Behaviour.setMood(engine, step.mood);
    if (step.anticipate) Behaviour.anticipate(engine, step.anticipate);
    if (step.sound && Sounds[step.sound]) Sounds[step.sound].apply(null, step.soundArgs || []);
    spawnParticle(engine, step.particle);
    if (step.caption) {
      if (step.caption.text) Behaviour.showCaption(engine, step.caption.text, step.hold + 0.6);
      else Behaviour.sayFromCategory(engine, step.caption.category, step.hold + 0.6);
    }
  }

  function playAction(engine, name) {
    var steps = ACTIONS[name];
    if (!steps || !steps.length) return false;
    var t = Behaviour.nowSeconds();
    engine.actionLabel = name;
    engine._action = { name: name, steps: steps, index: 0, stepStartAt: t };
    runStep(engine, steps[0], t);
    return true;
  }

  function stopAction(engine) {
    engine._action = null;
    engine.actionLabel = null;
  }

  function update(engine, dt, t) {
    var a = engine._action;
    if (!a) return;
    var step = a.steps[a.index];
    if (t - a.stepStartAt >= (step.hold || 0.5)) {
      a.index++;
      if (a.index >= a.steps.length) {
        engine._action = null;
        engine.actionLabel = null;
        return;
      }
      a.stepStartAt = t;
      runStep(engine, a.steps[a.index], t);
    }
  }

  function applyOverlay(engine, p, t) {
    var a = engine._action;
    if (!a) return;
    var step = a.steps[a.index];
    var age = t - a.stepStartAt;
    if (step.overlay) {
      for (var field in step.overlay) {
        var ov = step.overlay[field];
        var val = typeof ov === 'function' ? ov(age) : ov;
        p[field] = (p[field] || 0) + val;
      }
    }
    if (step.set) {
      for (var field2 in step.set) {
        var sv = step.set[field2];
        p[field2] = typeof sv === 'function' ? sv(age) : sv;
      }
    }
  }

  var api = {
    ACTIONS: ACTIONS, ACTION_NAMES: ACTION_NAMES, ACTION_LABELS: ACTION_LABELS,
    playAction: playAction, stopAction: stopAction, update: update, applyOverlay: applyOverlay
  };

  root.Actions = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
