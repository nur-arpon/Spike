/*
 * moods.js -- the mood table: every emotion as a partial FACE STATE
 * (params.js fields), plus its idle motion, its pop-up extras, whether the
 * eyes follow you, its caption group, and Spicy's cat variations.
 *
 * Rule of thumb used for every pose: it must read from across a desk at
 * 120 px wide. So each mood pushes the WHOLE face (eyes + lids + mouth +
 * ears + tilt + a decal), never just one feature.
 *
 * Exported as JSON for the C++ port by tools/export_recipes.js.
 */
(function (root) {
  'use strict';
  var isNode = typeof window === 'undefined';
  var FP = root.FaceParams || (isNode ? require('./params.js') : null);

  // Order drives the button grid and the demo cycle.
  var MOODS = [
    'neutral', 'happy', 'excited', 'love', 'laughing', 'playful', 'curious',
    'sad', 'caring', 'sleepy', 'sleeping', 'bored', 'sulking', 'scared',
    'surprised', 'cuteAngry', 'dizzy', 'proud', 'embarrassed', 'begging',
    'cuddly', 'wakeupAlarm',
    'joy', 'delight', 'anger', 'frustration', 'disgust', 'grief',
    'loneliness', 'hope', 'shyness', 'jealousy', 'confusion', 'suspicion',
    'relief', 'gratitude', 'mischief', 'determination', 'nervousness',
    'awe', 'smugness', 'silliness', 'hungry'
  ];

  var LABELS = {
    neutral: 'Neutral', happy: 'Happy', excited: 'Excited', love: 'Love',
    laughing: 'Laughing', playful: 'Playful', curious: 'Curious',
    sad: 'Sad', caring: 'Caring', sleepy: 'Sleepy', sleeping: 'Sleeping',
    bored: 'Bored', sulking: 'Sulking', scared: 'Scared', surprised: 'Surprised',
    cuteAngry: 'Cute-angry', dizzy: 'Dizzy', proud: 'Proud', embarrassed: 'Embarrassed',
    begging: 'Begging', cuddly: 'Cuddly', wakeupAlarm: 'Wake-up alarm',
    joy: 'Joy', delight: 'Delight', anger: 'Anger', frustration: 'Frustration',
    disgust: 'Disgust', grief: 'Grief', loneliness: 'Lonely', hope: 'Hope',
    shyness: 'Shy', jealousy: 'Jealous', confusion: 'Confused', suspicion: 'Suspicious',
    relief: 'Relief', gratitude: 'Grateful', mischief: 'Mischief',
    determination: 'Determined', nervousness: 'Nervous', awe: 'Awe',
    smugness: 'Smug', silliness: 'Silly', hungry: 'Hungry (low battery)'
  };

  // Caption bank category per mood (captions.js).
  var GROUP = {
    neutral: 'general', happy: 'general', excited: 'greeting', love: 'general',
    laughing: 'tease', playful: 'tease', curious: 'general', sad: 'comfort',
    caring: 'comfort', sleepy: 'sleepy', sleeping: 'sleepy', bored: 'general',
    sulking: 'comfort', scared: 'general', surprised: 'general',
    cuteAngry: 'tease', dizzy: 'selfdep', proud: 'selfdep',
    embarrassed: 'selfdep', begging: 'tease', cuddly: 'comfort',
    wakeupAlarm: 'alarm', joy: 'general', delight: 'general', anger: 'general',
    frustration: 'general', disgust: 'general', grief: 'comfort', loneliness: 'comfort',
    hope: 'general', shyness: 'general', jealousy: 'tease', confusion: 'general',
    suspicion: 'tease', relief: 'general', gratitude: 'general', mischief: 'tease',
    determination: 'general', nervousness: 'general', awe: 'general',
    smugness: 'tease', silliness: 'tease', hungry: 'hungry'
  };

  // ---------------------------------------------------------------------
  // FACE: partial face states (anything missing = params.js default).
  // ---------------------------------------------------------------------
  var FACE = {
    neutral: { smile: 0.4, tongue: 0.4 },

    happy: { smile: 0.85, open: 0.3, tongue: 0.45, lidBL: 0.14, lidBR: 0.14, lidBulge: 0.5,
      sparkle: 0.35, blush: 0.3, earPerk: 0.45, browY: 0.35, bob: -2 },

    excited: { smile: 1, open: 0.7, tongue: 0.8, pant: 0.7, eyeScale: 1.1, pupil: 1.3, sparkle: 0.8,
      shine: 1.2, earPerk: 1.1, browY: 0.8, headSY: 1.05, headSX: 0.97, bob: -4, blush: 0.3 },

    love: { icon: 'heart', iconAmt: 1, smile: 0.85, open: 0.28, tongue: 0.4, blush: 0.85, tilt: 5,
      earPerk: 0.3, browY: 0.3 },

    laughing: { happy: 1, smile: 1.1, open: 0.85, tongue: 0.5, tear: 0.25, blush: 0.5, earPerk: 0.6,
      headSX: 1.04, headSY: 0.97, browY: 0.6 },

    playful: { wink: -1, smile: 0.9, open: 0.45, tongue: 0.85, skew: 0.3, earPerk: 0.5, tilt: -7,
      browY: 0.35, blush: 0.25, sparkle: 0.3 },

    curious: { tilt: 13, eyeScaleR: 1.14, eyeScaleL: 0.97, browY: 0.6, smile: 0.2, mouthO: 0.4,
      open: 0.2, earPerk: 0.7, earL: -10, pupil: 1.15 },

    sad: { smile: -0.6, lidTL: 0.2, lidTR: 0.2, lidTilt: -0.75, eyeDY: 3, eyeScale: 1.05, pupil: 1.25,
      shine: 1.3, tear: 0.5, earPerk: -1, browY: 0.25, browTilt: -0.9, tilt: -4, mouthW: 0.8, wobble: 0.3 },

    caring: { smile: 0.5, lidTL: 0.16, lidTR: 0.16, lidBulge: 0.35, lidBL: 0.1, lidBR: 0.1, lidTilt: -0.3,
      pupil: 1.2, shine: 1.15, tilt: 6, blush: 0.35, browTilt: -0.4, browY: 0.2, earPerk: -0.2 },

    sleepy: { lidTL: 0.56, lidTR: 0.56, lidSag: 0.45, smile: 0.12, eyeDY: 2, earPerk: -0.7, tilt: 6,
      bob: 2, mouthW: 0.82, browY: -0.2 },

    sleeping: { shut: 1, smile: 0.12, bubble: 1, earPerk: -0.9, tilt: 8, bob: 3, dim: 0.12,
      mouthW: 0.8, browY: -0.3 },

    bored: { lidTL: 0.42, lidTR: 0.42, lidTilt: 0.1, smile: -0.05, lookX: 0.55, lookY: -0.35,
      tilt: -4, earPerk: -0.5, mouthW: 0.8, skew: -0.3 },

    sulking: { lidTL: 0.3, lidTR: 0.3, lidTilt: 0.25, smile: -0.45, mouthW: 0.62, skew: -0.2,
      lookX: -0.7, lookY: 0.25, tilt: -8, earPerk: -0.8, blush: 0.35, browTilt: 0.4 },

    scared: { eyeScale: 1.18, pupil: 0.55, shine: 0.85, lidBL: 0.08, lidBR: 0.08, lidTilt: -0.45,
      mouthO: 0.5, open: 0.4, smile: -0.4, wobble: 0.7, earBack: 1, earPerk: -0.5, sweat: 1,
      browTilt: -0.9, browY: 0.8, headSX: 0.95, headSY: 1.03, gloom: 0.3 },

    surprised: { eyeScale: 1.16, eyeSY: 1.07, pupil: 0.85, mouthO: 1, open: 0.6, smile: 0.1,
      browY: 1.1, earPerk: 1.1, shine: 1.1, headSY: 1.04 },

    cuteAngry: { lidTL: 0.15, lidTR: 0.15, lidTilt: 0.6, smile: -0.35, open: 0.32, mouthW: 0.55,
      fang: 1, blush: 0.65, vein: 0.8, browTilt: 0.8, earBack: 0.4, headSX: 1.05, headSY: 0.96,
      eyeScale: 1.05 },

    dizzy: { icon: 'spiral', iconAmt: 1, smile: -0.1, open: 0.35, tongue: 0.75, mouthW: 0.8,
      skew: 0.35, earPerk: -0.3 },

    proud: { happy: 1, smile: 0.8, open: 0.2, tongue: 0.3, tilt: -5, bob: -3, headSY: 1.04,
      earPerk: 0.7, browY: 0.5, blush: 0.2 },

    embarrassed: { lidTL: 0.15, lidTR: 0.15, lidTilt: -0.4, smile: 0.25, wobble: 0.35, mouthW: 0.7,
      blush: 1, blushLines: 1, sweat: 0.8, lookX: -0.5, lookY: 0.4, tilt: 6, earPerk: -0.4, browTilt: -0.6 },

    begging: { eyeScale: 1.14, pupil: 1.55, shine: 1.5, sparkle: 0.6, tear: 0.35, lidTilt: -0.55,
      lidTL: 0.05, lidTR: 0.05, smile: 0.1, mouthO: 0.3, open: 0.15, tilt: -9, earPerk: -0.6,
      browTilt: -1, browY: 0.7, headSY: 1.02 },

    cuddly: { lidTL: 0.5, lidTR: 0.5, lidSag: 0.3, lidBulge: 0.5, lidBL: 0.2, lidBR: 0.2, smile: 0.7,
      blush: 0.6, tilt: 7, earPerk: -0.3, bob: 2 },

    wakeupAlarm: { eyeScale: 1.15, pupil: 1.1, sparkle: 0.5, smile: 0.85, open: 0.75, tongue: 0.6,
      earPerk: 1.2, browY: 1, headSY: 1.06, bob: -3 },

    joy: { happy: 1, smile: 1, open: 0.55, tongue: 0.55, blush: 0.45, earPerk: 0.7, browY: 0.5,
      bob: -3, headSY: 1.03 },

    delight: { icon: 'star', iconAmt: 1, smile: 0.95, open: 0.45, tongue: 0.5, blush: 0.4,
      earPerk: 0.8, browY: 0.7, headSY: 1.03 },

    anger: { lidTL: 0.18, lidTR: 0.18, lidTilt: 0.85, lidBL: 0.1, lidBR: 0.1, smile: -0.5, open: 0.28,
      mouthW: 0.62, fang: 0.8, vein: 1, browTilt: 1, browY: -0.6, earBack: 0.85, eyeScale: 0.96,
      headSX: 1.03, headSY: 0.98, scrunch: 0.35 },

    frustration: { lidTL: 0.3, lidTR: 0.3, lidTilt: 0.5, smile: -0.4, wobble: 0.45, open: 0.12,
      mouthW: 0.8, scrunch: 0.45, vein: 0.5, earBack: 0.5, browTilt: 0.7 },

    disgust: { lidTL: 0.35, lidTR: 0.28, lidTilt: 0.2, lidBL: 0.25, lidBR: 0.25, smile: -0.5, skew: -0.5,
      open: 0.3, tongue: 0.75, mouthW: 0.7, scrunch: 1, gloom: 0.6, tilt: -8, lookX: 0.55,
      earBack: 0.4, browTilt: 0.5 },

    grief: { lidTL: 0.3, lidTR: 0.3, lidTilt: -0.9, tear: 0.9, cry: 1, smile: -0.8, open: 0.3,
      mouthW: 0.7, wobble: 0.6, earPerk: -1.2, tilt: -5, bob: 4, gloom: 0.8, browTilt: -1,
      eyeDY: 4, shine: 1.2 },

    loneliness: { lidTL: 0.25, lidTR: 0.25, lidTilt: -0.6, tear: 0.4, smile: -0.35, mouthW: 0.7,
      lookX: -0.6, lookY: 0.5, tilt: -6, earPerk: -1, gloom: 0.3, pupil: 1.2, browTilt: -0.7 },

    hope: { eyeScale: 1.08, pupil: 1.35, shine: 1.35, sparkle: 0.6, lidTilt: -0.3, smile: 0.35,
      mouthO: 0.25, open: 0.15, lookY: -0.55, tilt: 5, earPerk: 0.5, browY: 0.6, browTilt: -0.4 },

    shyness: { lidTL: 0.25, lidTR: 0.25, lidBulge: 0.4, lidBL: 0.12, lidBR: 0.12, smile: 0.35,
      mouthW: 0.6, blush: 0.9, blushLines: 0.6, lookX: -0.6, lookY: 0.45, tilt: 7, earPerk: -0.5,
      browTilt: -0.4 },

    jealousy: { lidTL: 0.4, lidTR: 0.4, lidTilt: 0.35, smile: -0.35, skew: -0.4, mouthW: 0.7,
      lookX: -0.85, tilt: -6, earBack: 0.3, browTilt: 0.5, blush: 0.2 },

    confusion: { tilt: 15, eyeScaleL: 1.12, eyeScaleR: 0.9, lidTR: 0.22, smile: -0.1, skew: -0.4,
      mouthW: 0.7, earL: -14, earR: 8, browY: 0.4 },

    suspicion: { lidTL: 0.45, lidTR: 0.3, lidTilt: 0.35, lidBL: 0.2, lidBR: 0.2, smile: -0.1,
      skew: 0.35, mouthW: 0.6, lookX: 0.6, tilt: -4, earBack: 0.2, browTilt: 0.3 },

    relief: { shut: 0.85, smile: 0.55, open: 0.2, mouthO: 0.3, tilt: -3, earPerk: -0.2, bob: 2,
      blush: 0.2, sweat: 0.5 },

    gratitude: { happy: 1, smile: 0.8, open: 0.2, tongue: 0.3, blush: 0.5, tilt: 4, earPerk: 0.2,
      tear: 0.3 },

    mischief: { lidTL: 0.3, lidTR: 0.3, lidTilt: 0.35, lidBulge: 0.5, lidBL: 0.15, lidBR: 0.15,
      smile: 0.7, skew: 0.6, fang: 1, lookX: 0.45, tilt: 6, earPerk: 0.4, browTilt: 0.5, blush: 0.2 },

    determination: { lidTL: 0.18, lidTR: 0.18, lidTilt: 0.45, smile: 0.1, mouthW: 0.8, earPerk: 0.8,
      browTilt: 0.6, browY: -0.3, sparkle: 0.6, headSY: 1.03, pupil: 1.1 },

    nervousness: { lidTilt: -0.4, eyeScale: 1.05, pupil: 0.8, smile: 0.1, wobble: 0.7, mouthW: 0.8,
      sweat: 1, blush: 0.2, lookX: 0.3, earBack: 0.5, browTilt: -0.7 },

    awe: { eyeScale: 1.2, pupil: 1.5, shine: 1.4, sparkle: 1, mouthO: 0.9, open: 0.5, smile: 0.2,
      browY: 1, earPerk: 0.8, lookY: -0.4, headSY: 1.03 },

    smugness: { lidTL: 0.42, lidTR: 0.42, lidBulge: 0.4, lidBL: 0.12, lidBR: 0.12, smile: 0.55,
      skew: 0.55, mouthW: 0.8, tilt: -6, earPerk: 0.3, browTilt: 0.2, browY: 0.3 },

    silliness: { eyeScaleL: 1.15, eyeScaleR: 0.85, cross: 0.6, smile: 0.9, open: 0.6, tongue: 1,
      skew: 0.4, tilt: 10, earPerk: 0.6, headSX: 1.05 },

    // HUNGRY = low battery: a begging puppy. Big pleading wet eyes, a lip
    // lick then a drool drop, a tummy-rumble wobble, and a blinking battery
    // popping up above the head. Glow (robot) styles show the battery IN the
    // eyes instead -- face_draw.js decides that from the recipe.
    hungry: { batt: 1, lick: 1, eyeScale: 1.14, pupil: 1.55, shine: 1.5, sparkle: 0.45, tear: 0.45,
      lidTilt: -0.55, lidTL: 0.04, lidTR: 0.04, browTilt: -1, browY: 0.7, smile: 0.05, open: 0.12,
      mouthW: 0.8, tilt: -7, earPerk: -0.6, headSY: 1.02 }
  };

  // ---------------------------------------------------------------------
  // MOTION: small continuous animation per mood, ADDED on top of the
  // spring-settled pose so no mood is ever a dead picture.
  // [field, amplitude, frequency Hz, kind, phase]
  //   sin    = plain sine
  //   jitter = two off-ratio sines (tremble; less mechanical)
  //   hop    = |sin| (little hops: joy, laughing, alarm)
  //   rumble = a short shake burst once per HUNGRY_CYCLE (tummy rumble),
  //            timed to fall after the lick and during the drool
  // ---------------------------------------------------------------------
  var MOTION = {
    happy: [['tilt', 2, 0.45, 'sin']],
    excited: [['bob', -4, 3.2, 'hop'], ['earL', 6, 3.2, 'sin'], ['earR', 6, 3.2, 'sin', 1.2], ['headSY', 0.025, 3.2, 'sin']],
    love: [['tilt', 3, 0.5, 'sin'], ['bob', 1.2, 1.1, 'sin'], ['iconAmt', 0.06, 1.6, 'sin']],
    laughing: [['bob', -3, 5.5, 'hop'], ['tilt', 3, 1.8, 'sin'], ['open', 0.12, 5.5, 'sin']],
    playful: [['tilt', 4, 0.9, 'sin'], ['earR', 8, 1.8, 'sin']],
    curious: [['tilt', 2.5, 0.4, 'sin']],
    sad: [['bob', 1, 0.3, 'sin'], ['wobble', 0.15, 0.6, 'sin']],
    caring: [['tilt', 2.5, 0.35, 'sin']],
    sleepy: [['lidTL', 0.1, 0.22, 'sin'], ['lidTR', 0.1, 0.22, 'sin'], ['tilt', 3, 0.15, 'sin'], ['bob', 2, 0.15, 'sin']],
    sleeping: [['bob', 2.2, 0.22, 'sin'], ['earL', 3, 0.22, 'sin'], ['headSY', 0.012, 0.22, 'sin']],
    bored: [['lidTL', 0.08, 0.2, 'sin'], ['lidTR', 0.08, 0.2, 'sin'], ['lookX', 0.2, 0.12, 'sin']],
    sulking: [['lookX', 0.12, 0.15, 'sin'], ['tilt', 1.5, 0.2, 'sin']],
    scared: [['shakeX', 1.6, 11, 'jitter'], ['tilt', 1.2, 9, 'jitter', 1]],
    cuteAngry: [['bob', -2.5, 3, 'hop'], ['shakeX', 0.8, 9, 'jitter']],
    dizzy: [['tilt', 12, 0.8, 'sin'], ['bob', 2, 1.6, 'sin'], ['lookX', 0.4, 0.8, 'sin']],
    proud: [['bob', -1, 0.6, 'sin']],
    embarrassed: [['lookX', 0.15, 0.5, 'sin'], ['tilt', 2, 0.6, 'sin']],
    begging: [['tilt', 3, 0.45, 'sin'], ['bob', 1.2, 0.9, 'sin']],
    cuddly: [['tilt', 2.5, 0.25, 'sin'], ['bob', 1.5, 0.25, 'sin']],
    wakeupAlarm: [['bob', -5, 3.6, 'hop'], ['tilt', 5, 1.8, 'sin'], ['earL', 10, 3.6, 'sin'], ['earR', 10, 3.6, 'sin', 1.5]],
    joy: [['bob', -3.5, 2.2, 'hop'], ['tilt', 3, 1.1, 'sin']],
    delight: [['bob', -2.5, 2.6, 'hop'], ['iconAmt', 0.08, 2.6, 'sin']],
    anger: [['shakeX', 1, 8, 'jitter'], ['tilt', 1.2, 7, 'jitter', 2]],
    frustration: [['tilt', 4, 1.5, 'sin'], ['shakeX', 1.5, 1.5, 'sin', 1.57]],
    disgust: [['tilt', 2, 0.6, 'sin'], ['scrunch', 0.1, 1.5, 'sin']],
    grief: [['bob', 2.5, 1.6, 'jitter'], ['wobble', 0.2, 1, 'sin']],
    loneliness: [['lookY', 0.08, 0.2, 'sin'], ['tilt', 1.5, 0.2, 'sin']],
    hope: [['tilt', 2, 0.5, 'sin'], ['bob', -1.5, 0.5, 'sin']],
    shyness: [['lookX', 0.2, 0.35, 'sin', 1], ['tilt', 2, 0.35, 'sin']],
    jealousy: [['lookX', 0.12, 0.8, 'sin']],
    confusion: [['tilt', 6, 0.5, 'sin']],
    suspicion: [['lookX', 0.25, 0.18, 'sin']],
    relief: [['bob', 1.5, 0.4, 'sin'], ['headSY', 0.02, 0.4, 'sin']],
    gratitude: [['tilt', 3, 0.7, 'sin']],
    mischief: [['skew', 0.12, 1.2, 'sin'], ['tilt', 2, 0.6, 'sin']],
    determination: [['bob', 0.8, 2.5, 'sin']],
    nervousness: [['shakeX', 1.2, 10, 'jitter'], ['lookX', 0.35, 0.9, 'sin'], ['bob', 0.8, 11, 'jitter', 2]],
    awe: [['headSY', 0.02, 0.3, 'sin'], ['sparkle', 0.2, 1.3, 'sin']],
    smugness: [['tilt', 2, 0.4, 'sin']],
    silliness: [['tilt', 7, 2.2, 'sin'], ['cross', 0.2, 1.1, 'sin']],
    hungry: [['shakeX', 1.8, 13, 'rumble'], ['headSY', 0.03, 13, 'rumble', 1.3], ['bob', 1.2, 13, 'rumble', 0.6],
      ['tilt', 2.5, 0.35, 'sin']]
  };

  var HUNGRY_CYCLE = 3.6; // s; face_draw.js times the lick + drool on the same cycle
  function motionValue(m, t) {
    var w = t * m[2] * 6.283185, ph = m[4] || 0;
    if (m[3] === 'rumble') {
      var c = t % HUNGRY_CYCLE;
      var env = (c >= 2.2 && c < 2.9) ? Math.sin((c - 2.2) / 0.7 * Math.PI) : 0;
      return m[1] * env * Math.sin(w + ph);
    }
    if (m[3] === 'jitter') return m[1] * (0.6 * Math.sin(w + ph) + 0.4 * Math.sin(w * 2.37 + ph * 1.3));
    if (m[3] === 'hop') return m[1] * Math.abs(Math.sin(w * 0.5 + ph));
    return m[1] * Math.sin(w + ph);
  }

  // Adds the mood's motion to a face state in place. `energy` (0..1) damps
  // it (low battery = less spark).
  function applyMotion(p, id, t, energy) {
    var list = MOTION[id];
    if (!list) return p;
    var e = energy == null ? 1 : energy;
    for (var i = 0; i < list.length; i++) {
      var m = list[i];
      if (m[0] in p) p[m[0]] += motionValue(m, t) * e;
    }
    return p;
  }

  // ---------------------------------------------------------------------
  // EXTRAS: pop-ups (extras.js) in screen coords.
  //   enter: [[type, x, y, count]]      once, when the mood starts
  //   every: [seconds, type, x, y, spreadX]  repeating while it lasts
  // ---------------------------------------------------------------------
  var EXTRAS = {
    excited: { enter: [['sparkle', 240, 60, 5]], every: [1.0, 'sparkle', 240, 50, 170] },
    love: { every: [1.1, 'heart', 240, 70, 150] },
    laughing: { every: [1.4, 'sparkle', 240, 60, 170] },
    sleeping: { every: [1.8, 'zzz', 330, 70, 0] },
    surprised: { enter: [['exclaim', 240, 38, 1]] },
    scared: { enter: [['exclaim', 300, 38, 1]] },
    dizzy: { enter: [['dizzyStar', 240, 40, 3]] },
    confusion: { enter: [['question', 300, 40, 1]], every: [2.6, 'question', 300, 40, 30] },
    joy: { every: [0.9, 'sparkle', 240, 60, 190] },
    delight: { every: [0.8, 'sparkle', 240, 60, 190] },
    awe: { every: [1.2, 'sparkle', 240, 50, 190] },
    proud: { every: [1.3, 'sparkle', 240, 40, 170] },
    hope: { every: [2.0, 'sparkle', 240, 40, 130] },
    cuddly: { every: [2.4, 'heart', 240, 80, 130] },
    caring: { every: [3.0, 'heart', 240, 80, 130] },
    gratitude: { every: [1.8, 'heart', 240, 80, 150] },
    wakeupAlarm: { every: [0.7, 'exclaim', 240, 40, 180] },
    anger: { every: [1.6, 'steam', 240, 36, 170] },
    frustration: { every: [2.2, 'steam', 240, 36, 170] },
    cuteAngry: { every: [1.9, 'steam', 240, 36, 170] }
  };

  // Moods whose eyes follow the person (camera / mouse). The rest have a
  // scripted gaze (sulking looks away, shy looks down, sleeping is shut).
  var NO_FOLLOW = { sleeping: 1, sleepy: 1, bored: 1, sulking: 1, embarrassed: 1, dizzy: 1,
    loneliness: 1, shyness: 1, jealousy: 1, suspicion: 1, disgust: 1, silliness: 1, hope: 1, relief: 1 };
  function followsLook(id) { return !NO_FOLLOW[id]; }

  // ---------------------------------------------------------------------
  // SPICY (cat mode). Same table, layered with cat body language:
  //  - calm moods: half-lids and a knowing smirk (her default sass)
  //  - calm moods: slit pupils; excited / scared / love: big round pupils
  //  - cats don't pant; the tongue only shows for a deliberate "bleh"
  //  - angry ears go flat ("airplane ears")
  // plus a few moods that a cat does differently.
  // ---------------------------------------------------------------------
  var CAT_ALERT = { scared: 1, surprised: 1, wakeupAlarm: 1, curious: 1, dizzy: 1, anger: 1, awe: 1,
    delight: 1, excited: 1, love: 1, joy: 1, laughing: 1, hope: 1, begging: 1, cuteAngry: 1, hungry: 1 };
  var CAT_FACE = {
    happy: { lidTL: 0.42, lidTR: 0.42, lidBulge: 0.55, lidBL: 0.16, lidBR: 0.16, smile: 0.7, open: 0.08 },
    playful: { wink: -1, smile: 0.7, open: 0.3, tongue: 0.9, skew: 0.5 },
    cuteAngry: { open: 0.65, fang: 1, earBack: 1, lidTilt: 0.8, smile: -0.4, mouthW: 0.7 },
    anger: { earBack: 1, open: 0.55 },
    sulking: { lookX: -0.95, tilt: -10, lidTL: 0.5, lidTR: 0.5 },
    smugness: { lidTL: 0.55, lidTR: 0.55, skew: 0.7 },
    mischief: { skew: 0.8 },
    cuddly: { shut: 0.9, smile: 0.7 }
  };

  function catify(face, id) {
    var o = FP.copy(face);
    var extra = CAT_FACE[id];
    if (extra) for (var k in extra) o[k] = extra[k];
    if (!CAT_ALERT[id]) {
      o.lidTL = Math.min(1, (o.lidTL || 0) + 0.12);
      o.lidTR = Math.min(1, (o.lidTR || 0) + 0.12);
      o.skew = FP.clamp((o.skew || 0) + 0.18, -1, 1);
    }
    var pu = o.pupil == null ? 1 : o.pupil;
    o.pupil = CAT_ALERT[id] ? pu * 1.25 : pu * 0.5;
    var tg = o.tongue || 0;
    o.tongue = tg >= 0.75 ? tg : tg * 0.3;
    o.pant = 0;
    if (o.earBack) o.earBack = Math.min(1.2, o.earBack * 1.2);
    return o;
  }

  function getFace(id, mode) {
    var f = FACE[id] || FACE.neutral;
    return mode === 'cat' ? catify(f, id) : f;
  }

  // Full target face state for a mood.
  function getTarget(id, mode) { return FP.merge(getFace(id, mode)); }

  var api = {
    MOODS: MOODS, LABELS: LABELS, GROUP: GROUP, FACE: FACE, MOTION: MOTION, EXTRAS: EXTRAS,
    CAT_FACE: CAT_FACE, CAT_ALERT: CAT_ALERT, NO_FOLLOW: NO_FOLLOW,
    catify: catify, getFace: getFace, getTarget: getTarget, applyMotion: applyMotion,
    motionValue: motionValue, followsLook: followsLook, HUNGRY_CYCLE: HUNGRY_CYCLE
  };
  root.Moods = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
