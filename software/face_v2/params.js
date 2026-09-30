/*
 * params.js -- the parametric FACE STATE and its spring physics.
 *
 * The face state is a FLAT object of plain numbers (plus one string, `icon`)
 * so it ports line-for-line to a C struct. Every mood in moods.js is a
 * partial list of these fields; every Face Studio slot in face_draw.js reads
 * the SAME fields, which is why any recipe animates every mood.
 *
 * Units: px are in the 480x272 screen space, angles in degrees, everything
 * else 0..1 (or -1..1 where noted).
 *
 * Springs: each field is a damped spring toward its target. Tuning is per
 * field GROUP: blinks are fast with a little overshoot (the overshoot past 0
 * is what makes the eye STRETCH as it re-opens), ears are very bouncy
 * (floppy), the head tilt overshoots then settles, decals fade slowly.
 * kick(field, velocity) gives a spring an impulse -- used for ear flicks,
 * boops, hiccups and bounces, so they wobble back naturally.
 */
(function (root) {
  'use strict';

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function smoothstep(e0, e1, x) { var t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); }

  // -------------------------------------------------------------------
  // The default (neutral) face state. Comments give the range.
  // -------------------------------------------------------------------
  var DEFAULTS = {
    // --- gaze ------------------------------------------------------
    lookX: 0,        // -1..1 (screen left..right)
    lookY: 0,        // -1..1 (up..down)
    cross: 0,        // 0..1 cross-eyed (boop!)

    // --- eye size / squash & stretch ---------------------------------
    eyeScale: 1,     // both eyes
    eyeScaleL: 1,    // viewer's-left eye extra scale (curious = one bigger)
    eyeScaleR: 1,
    eyeSX: 1,        // eye squash & stretch (x)
    eyeSY: 1,        //                       (y)
    eyeDY: 0,        // px, both eyes move down (+) / up (-)
    eyeSpread: 0,    // px, eyes push apart (+) / together (-)

    // --- lids (skin-coloured masks clipped to each eye) -------------
    lidTL: 0,        // 0..1 top lid droop, left eye
    lidTR: 0,        // 0..1 top lid droop, right eye
    lidBL: 0,        // 0..1 bottom lid rise, left eye
    lidBR: 0,        // 0..1 bottom lid rise, right eye
    lidTilt: 0,      // -1..1  + = inner corners DOWN (angry), - = inner UP (sad/worried)
    lidSag: 0,       // 0..1 top-lid edge sags in the middle (sleepy, soft)
    lidBulge: 0,     // 0..1 bottom-lid edge bulges up (smiling cheeks)
    blinkL: 0,       // 0..1 blink overlay (spring; overshoots <0 = stretch)
    blinkR: 0,
    shut: 0,         // 0..1 eyes closed and relaxed (sleep, content)
    happy: 0,        // 0..1 closed happy "^ ^" eyes
    wink: 0,         // -1..1 one happy closed eye (-1 = viewer's left)

    // --- eye interior -----------------------------------------------
    pupil: 1,        // pupil dilation 0.3 (slit) .. 1.6 (huge)
    shine: 1,        // highlight size multiplier
    sparkle: 0,      // 0..1 extra star glints (joy, awe, love)
    tear: 0,         // 0..1 teary: waterline + extra highlights
    cry: 0,          // 0..1 streaming tears down the cheeks
    iconAmt: 0,      // 0..1 how much the eye is replaced by `icon`

    // --- brows (float above each eye, never joined) -------------------
    browY: 0,        // -1..1 raise
    browTilt: 0,     // -1..1 + = inner ends down (cross), - = inner up (worried)

    // --- nose --------------------------------------------------------
    noseDX: 0, noseDY: 0,  // px
    noseSX: 1, noseSY: 1,  // squash
    scrunch: 0,      // 0..1 nose scrunch + wrinkles (disgust, pre-sneeze)

    // --- mouth -------------------------------------------------------
    smile: 0.3,      // -1 frown .. 1 grin
    open: 0,         // 0..1
    mouthW: 1,       // width multiplier
    mouthO: 0,       // 0..1 round "o" (surprise, awe)
    tongue: 0,       // 0..1 tongue visible/out
    pant: 0,         // 0..1 panting tongue bounce
    wobble: 0,       // 0..1 quivering lip
    skew: 0,         // -1..1 smirk (+ lifts the viewer's-right corner)
    fang: 0,         // 0..1 one cute fang

    // --- cheeks & decals ------------------------------------------
    blush: 0,        // 0..1 extra blush on top of the recipe's base blush
    blushLines: 0,   // 0..1 embarrassed hatch lines on the cheeks
    vein: 0,         // 0..1 anger mark on the forehead
    sweat: 0,        // 0..1 big nervous sweat drop at the temple
    gloom: 0,        // 0..1 gloomy lines on the forehead
    bubble: 0,       // 0..1 sleep bubble from the nose
    batt: 0,         // 0..1 low battery: a blinking battery pops up above the head
                     //      (glow/robot styles show it IN the eyes instead)
    lick: 0,         // 0..1 hungry lip-lick + drool drop cycle (timed by t)

    // --- ears --------------------------------------------------------
    earPerk: 0,      // -1 droop .. 1 perked
    earBack: 0,      // 0..1 flattened (angry/scared)
    earL: 0,         // deg, extra rotation (flicks, swing) left ear
    earR: 0,         // deg, right ear

    // --- whole head --------------------------------------------------
    tilt: 0,         // deg, whole-face rotation (+ = clockwise)
    bob: 0,          // px, whole face down (+) / up (-)
    headSX: 1,       // whole-face squash & stretch (pivot at the chin)
    headSY: 1,
    shakeX: 0,       // px sideways offset (shiver, no-no)

    // --- global --------------------------------------------------
    dim: 0           // 0..1 extra dimming (sleep / night)
  };

  // Non-spring fields (discrete).
  var DISCRETE = { icon: '' };  // '', 'heart', 'star', 'spiral', 'x', 'battery', 'question', 'money'

  // Spring tuning groups: [stiffness, damping].
  // Damping ratio = d / (2*sqrt(k)); < 1 overshoots.
  var TUNE = {
    fast:   [900, 36],  // blinks, lids  (zeta 0.6)
    gaze:   [520, 36],  // saccades      (zeta 0.79)
    eye:    [260, 14],  // eye squash    (zeta 0.43 -> bouncy)
    shape:  [210, 17],  // mouth, brows  (zeta 0.59)
    happy:  [320, 24],  //               (zeta 0.67)
    head:   [120, 10],  // tilt, bob     (zeta 0.46 -> overshoot)
    ear:    [150, 6],   // ears          (zeta 0.24 -> floppy)
    nose:   [700, 22],  // nose          (zeta 0.42)
    decal:  [60, 14],   // blush, tears  (zeta 0.9, slow fade)
    slow:   [40, 12]
  };
  var GROUP = {
    lookX: 'gaze', lookY: 'gaze', cross: 'happy',
    eyeScale: 'eye', eyeScaleL: 'eye', eyeScaleR: 'eye', eyeSX: 'eye', eyeSY: 'eye', eyeDY: 'shape', eyeSpread: 'shape',
    lidTL: 'fast', lidTR: 'fast', lidBL: 'fast', lidBR: 'fast', lidTilt: 'shape', lidSag: 'shape', lidBulge: 'shape',
    blinkL: 'fast', blinkR: 'fast', shut: 'happy', happy: 'happy', wink: 'happy',
    pupil: 'shape', shine: 'shape', sparkle: 'decal', tear: 'decal', cry: 'decal', iconAmt: 'eye',
    browY: 'shape', browTilt: 'shape',
    noseDX: 'nose', noseDY: 'nose', noseSX: 'nose', noseSY: 'nose', scrunch: 'shape',
    smile: 'shape', open: 'shape', mouthW: 'shape', mouthO: 'shape', tongue: 'shape', pant: 'decal',
    wobble: 'decal', skew: 'shape', fang: 'shape',
    blush: 'decal', blushLines: 'decal', vein: 'decal', sweat: 'decal', gloom: 'decal', bubble: 'decal',
    batt: 'eye', lick: 'decal',
    earPerk: 'ear', earBack: 'ear', earL: 'ear', earR: 'ear',
    tilt: 'head', bob: 'head', headSX: 'eye', headSY: 'eye', shakeX: 'nose',
    dim: 'slow'
  };

  // Final safety ranges (applied after motion overlays are added).
  var RANGES = {
    lookX: [-1.2, 1.2], lookY: [-1.2, 1.2], cross: [0, 1],
    eyeScale: [0.4, 1.6], eyeScaleL: [0.4, 1.6], eyeScaleR: [0.4, 1.6], eyeSX: [0.5, 1.6], eyeSY: [0.4, 1.6],
    eyeDY: [-14, 14], eyeSpread: [-14, 14],
    lidTL: [0, 1], lidTR: [0, 1], lidBL: [0, 1], lidBR: [0, 1], lidTilt: [-1.2, 1.2], lidSag: [0, 1], lidBulge: [0, 1],
    blinkL: [-0.6, 1], blinkR: [-0.6, 1], shut: [0, 1], happy: [0, 1], wink: [-1, 1],
    pupil: [0.2, 1.8], shine: [0, 2], sparkle: [0, 1], tear: [0, 1], cry: [0, 1], iconAmt: [0, 1.3],
    browY: [-1.5, 1.5], browTilt: [-1.2, 1.2],
    noseDX: [-10, 10], noseDY: [-10, 10], noseSX: [0.6, 1.5], noseSY: [0.6, 1.5], scrunch: [0, 1],
    smile: [-1.2, 1.2], open: [0, 1], mouthW: [0.4, 1.5], mouthO: [0, 1], tongue: [0, 1], pant: [0, 1],
    wobble: [0, 1], skew: [-1, 1], fang: [0, 1],
    blush: [0, 1], blushLines: [0, 1], vein: [0, 1], sweat: [0, 1], gloom: [0, 1], bubble: [0, 1],
    batt: [0, 1.3], lick: [0, 1],
    earPerk: [-1.5, 1.5], earBack: [0, 1], earL: [-60, 60], earR: [-60, 60],
    tilt: [-370, 370], bob: [-24, 24], headSX: [0.7, 1.35], headSY: [0.7, 1.35], shakeX: [-12, 12],
    dim: [0, 0.85]
  };

  var FIELDS = Object.keys(DEFAULTS);

  function defaults() {
    var o = {};
    for (var i = 0; i < FIELDS.length; i++) o[FIELDS[i]] = DEFAULTS[FIELDS[i]];
    o.icon = DISCRETE.icon;
    return o;
  }

  // merge(a, b, ...) onto a fresh copy of the defaults (later wins).
  function merge() {
    var o = defaults();
    for (var i = 0; i < arguments.length; i++) {
      var src = arguments[i];
      if (!src) continue;
      for (var k in src) if (Object.prototype.hasOwnProperty.call(src, k) && (k in o)) o[k] = src[k];
    }
    return o;
  }

  function clampState(p) {
    for (var k in RANGES) {
      var r = RANGES[k], v = p[k];
      if (typeof v !== 'number' || v !== v) { p[k] = DEFAULTS[k]; continue; }
      if (v < r[0]) p[k] = r[0]; else if (v > r[1]) p[k] = r[1];
    }
    return p;
  }

  // -------------------------------------------------------------------
  // Spring state
  // -------------------------------------------------------------------
  function createSprings(initial) {
    var cur = merge(initial);
    var vel = {};
    for (var i = 0; i < FIELDS.length; i++) vel[FIELDS[i]] = 0;
    return { current: cur, velocity: vel, target: merge(cur) };
  }

  function setTarget(s, target) {
    s.target = merge(target);
    s.current.icon = s.target.icon; // discrete: switch now, iconAmt springs
  }

  // Set just some target fields, keeping the rest.
  function setTargetFields(s, fields) {
    for (var k in fields) if (k in s.target) s.target[k] = fields[k];
    if ('icon' in fields) s.current.icon = fields.icon;
  }

  function kick(s, field, velocity) {
    if (field in s.velocity) s.velocity[field] += velocity;
  }

  // Semi-implicit Euler, sub-stepped so the stiff blink springs stay stable.
  function step(s, dt) {
    dt = clamp(dt, 0, 0.1);
    var sub = Math.max(1, Math.ceil(dt / (1 / 240)));
    var h = dt / sub;
    var cur = s.current, vel = s.velocity, tgt = s.target;
    for (var n = 0; n < sub; n++) {
      for (var i = 0; i < FIELDS.length; i++) {
        var k = FIELDS[i];
        var tn = TUNE[GROUP[k] || 'shape'];
        var v = vel[k] + (-tn[0] * (cur[k] - tgt[k]) - tn[1] * vel[k]) * h;
        vel[k] = v;
        cur[k] += v * h;
      }
    }
    return cur;
  }

  function snap(s, target) {
    setTarget(s, target);
    for (var i = 0; i < FIELDS.length; i++) {
      s.current[FIELDS[i]] = s.target[FIELDS[i]];
      s.velocity[FIELDS[i]] = 0;
    }
    return s.current;
  }

  function copy(p) { var o = {}; for (var k in p) o[k] = p[k]; return o; }

  var api = {
    DEFAULTS: DEFAULTS, FIELDS: FIELDS, RANGES: RANGES, TUNE: TUNE, GROUP: GROUP,
    clamp: clamp, lerp: lerp, smoothstep: smoothstep,
    defaults: defaults, merge: merge, clampState: clampState, copy: copy,
    createSprings: createSprings, setTarget: setTarget, setTargetFields: setTargetFields,
    kick: kick, step: step, snap: snap
  };
  root.FaceParams = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
