/*
 * expressions.js -- the preset mood table.
 *
 * Each preset is a PARTIAL params object: only the fields that differ
 * from FACE_DEFAULTS (face_params.js) need to be listed. behaviour.js
 * calls getPreset(moodId, mode) to get the full merged target params for
 * FaceParams.setTarget().
 *
 * Dog presets are the source of truth. Cat mode is produced by catify(),
 * which layers cat-specific traits (slit pupils, eyelashes, whiskers, the
 * omega mouth, a slightly smug half-lidded default) on top of the SAME
 * mood preset, so every mood works for both characters without doubling
 * the table.
 *
 * expressions.json (sibling file) is generated FROM this file's data by
 * tools/export_expressions.js, for the future ESP32 port.
 */
(function (root) {
  'use strict';

  var FP = root.FaceParams || (typeof require === 'function' ? require('./face_params.js') : null);

  // Order here also drives the mood-button order and the demo cycle.
  // The first 22 are the original preset table; everything from 'joy'
  // onward is the "all the human ones" expansion -- each still gets its
  // own little idle animation, see MOOD_MOTION in behaviour.js.
  var MOODS = [
    'neutral', 'happy', 'excited', 'love', 'laughing', 'playful', 'curious',
    'sad', 'caring', 'sleepy', 'sleeping', 'bored', 'sulking', 'scared',
    'surprised', 'cuteAngry', 'dizzy', 'proud', 'embarrassed', 'begging',
    'cuddly', 'wakeupAlarm',
    'joy', 'delight', 'anger', 'frustration', 'disgust', 'grief',
    'loneliness', 'hope', 'shyness', 'jealousy', 'confusion', 'suspicion',
    'relief', 'gratitude', 'mischief', 'determination', 'nervousness',
    'awe', 'smugness', 'silliness'
  ];

  var MOOD_LABELS = {
    neutral: 'Neutral', happy: 'Happy', excited: 'Excited', love: 'Love',
    laughing: 'Laughing', playful: 'Playful / Teasing', curious: 'Curious',
    sad: 'Sad', caring: 'Caring / Comforting', sleepy: 'Sleepy',
    sleeping: 'Sleeping / Dreaming', bored: 'Bored', sulking: 'Sulking / Jealous',
    scared: 'Scared / Fright', surprised: 'Surprised', cuteAngry: 'Cute-Angry',
    dizzy: 'Dizzy', proud: 'Proud', embarrassed: 'Embarrassed / Shame',
    begging: 'Begging', cuddly: 'Cuddly', wakeupAlarm: 'Wake-Up Alarm',
    joy: 'Joy', delight: 'Delight', anger: 'Anger', frustration: 'Frustration',
    disgust: 'Disgust ("ew")', grief: 'Grief (lite)', loneliness: 'Loneliness',
    hope: 'Hope', shyness: 'Shyness', jealousy: 'Jealousy', confusion: 'Confusion',
    suspicion: 'Suspicion', relief: 'Relief', gratitude: 'Gratitude',
    mischief: 'Mischief', determination: 'Determination', nervousness: 'Nervousness',
    awe: 'Awe / Wonder', smugness: 'Smugness', silliness: 'Silliness'
  };

  // Caption-bank grouping used by behaviour.js to pick a matching line.
  var MOOD_GROUP = {
    neutral: 'general', happy: 'general', excited: 'greeting', love: 'general',
    laughing: 'tease', playful: 'tease', curious: 'general', sad: 'comfort',
    caring: 'comfort', sleepy: 'sleepy', sleeping: 'sleepy', bored: 'general',
    sulking: 'comfort', scared: 'general', surprised: 'general',
    cuteAngry: 'tease', dizzy: 'selfdep', proud: 'selfdep',
    embarrassed: 'selfdep', begging: 'tease', cuddly: 'comfort',
    wakeupAlarm: 'alarm',
    joy: 'general', delight: 'general', anger: 'general', frustration: 'general',
    disgust: 'general', grief: 'comfort', loneliness: 'comfort', hope: 'general',
    shyness: 'general', jealousy: 'tease', confusion: 'general', suspicion: 'tease',
    relief: 'general', gratitude: 'general', mischief: 'tease',
    determination: 'general', nervousness: 'general', awe: 'general',
    smugness: 'tease', silliness: 'tease'
  };

  var PRESETS = {
    neutral: {},

    happy: {
      mouthCurve: 0.55, mouthOpen: 0.12, topLidL: 0.08, topLidR: 0.08,
      squashX: 0.97, squashY: 1.05, blushOpacity: 0.15
    },

    excited: {
      mouthCurve: 0.7, mouthOpen: 0.35, eyeLScale: 1.1, eyeRScale: 1.1,
      squashX: 0.9, squashY: 1.15, bobOffset: -4, breathScale: 1.05
    },

    love: {
      pupilSize: 0.5, eyeLScale: 1.05, eyeRScale: 1.05, mouthCurve: 0.6,
      mouthOpen: 0.15, blushOpacity: 0.5, highlightSize: 0.5, highlightOpacity: 1
    },

    laughing: {
      mouthOpen: 0.6, mouthCurve: 0.8, topLidL: 0.55, topLidR: 0.55,
      squashX: 1.12, squashY: 0.85, bobOffset: -2
    },

    playful: {
      smirkSide: 0.5, blinkL: 1, mouthCurve: 0.5, eyeRScale: 1.05
    },

    curious: {
      faceTilt: 12, eyeRScale: 1.25, lookX: 0.2, mouthCurve: 0.1, mouthOpen: 0.05
    },

    sad: {
      mouthCurve: -0.6, topLidL: 0.35, topLidR: 0.35, bottomLidL: 0.1,
      bottomLidR: 0.1, eyeYOffset: 4, mouthWobble: 0.4, faceTilt: -4
    },

    caring: {
      mouthCurve: 0.35, mouthOpen: 0.05, topLidL: 0.15, topLidR: 0.15,
      eyeYOffset: 2, pupilSize: 0.46, breathScale: 1.02
    },

    sleepy: {
      topLidL: 0.55, topLidR: 0.55, mouthOpen: 0.05, mouthCurve: 0.05,
      bobOffset: 2, breathScale: 0.98, faceTilt: 6
    },

    sleeping: {
      topLidL: 0.92, topLidR: 0.92, mouthOpen: 0.08, mouthCurve: 0.1,
      bobOffset: 3, breathScale: 0.97
    },

    bored: {
      topLidL: 0.3, topLidR: 0.3, mouthCurve: -0.1, lookX: 0.3, faceTilt: -3
    },

    sulking: {
      mouthCurve: -0.4, topLidL: 0.25, topLidR: 0.25, faceTilt: -8,
      lookX: -0.4, lookY: 0.1
    },

    scared: {
      eyeLScale: 1.3, eyeRScale: 1.3, bottomLidL: 0.15, bottomLidR: 0.15,
      mouthOpen: 0.3, mouthCurve: -0.3, squashX: 0.85, squashY: 1.2, bobOffset: -3
    },

    surprised: {
      eyeLScale: 1.25, eyeRScale: 1.25, mouthOpen: 0.45, mouthCurve: 0.1,
      squashX: 0.92, squashY: 1.15
    },

    cuteAngry: {
      topLidL: 0.18, topLidR: 0.18, topLidAngleL: 16, topLidAngleR: -16,
      mouthOpen: 0.15, mouthCurve: -0.2, blushOpacity: 0.2,
      squashX: 1.05, squashY: 0.95
    },

    dizzy: {
      topLidL: 0.1, topLidR: 0.1, eyeLScale: 0.9, eyeRScale: 0.9,
      mouthOpen: 0.2, mouthCurve: -0.1, squashX: 1.1, squashY: 0.9
    },

    proud: {
      mouthCurve: 0.5, mouthOpen: 0.08, topLidL: 0.05, topLidR: 0.05,
      bobOffset: -2, breathScale: 1.03, squashX: 0.98, squashY: 1.05, smirkSide: 0.15
    },

    embarrassed: {
      mouthCurve: 0.25, mouthOpen: 0.15, mouthWobble: 0.2, topLidL: 0.2,
      topLidR: 0.2, blushOpacity: 0.6, faceTilt: 5, smirkSide: 0.3
    },

    begging: {
      pupilSize: 0.58, eyeLScale: 1.15, eyeRScale: 1.15, highlightSize: 0.55,
      highlightOpacity: 1, topLidL: 0.05, topLidR: 0.05, bottomLidL: 0.05,
      bottomLidR: 0.05, mouthCurve: 0.1, mouthOpen: 0.05, faceTilt: -6
    },

    cuddly: {
      topLidL: 0.45, topLidR: 0.45, mouthCurve: 0.4, mouthOpen: 0.05,
      breathScale: 1.04, bobOffset: 2, faceTilt: 3, blushOpacity: 0.2
    },

    wakeupAlarm: {
      eyeLScale: 1.2, eyeRScale: 1.2, mouthOpen: 0.35, mouthCurve: 0.3,
      squashX: 0.85, squashY: 1.2
    },

    // ---- the "all the human ones" expansion -----------------------------
    // Base poses only -- each also gets a small continuous idle animation
    // from MOOD_MOTION in behaviour.js, so none of these are a dead pose.

    joy: {
      mouthCurve: 0.65, mouthOpen: 0.2, topLidL: 0.05, topLidR: 0.05,
      squashX: 0.95, squashY: 1.08, blushOpacity: 0.2, breathScale: 1.03
    },

    delight: {
      eyeLScale: 1.1, eyeRScale: 1.1, mouthCurve: 0.5, mouthOpen: 0.25,
      highlightSize: 0.5, highlightOpacity: 1, blushOpacity: 0.3
    },

    anger: {
      topLidL: 0.2, topLidR: 0.2, topLidAngleL: 20, topLidAngleR: -20,
      eyeLScale: 0.95, eyeRScale: 0.95, mouthCurve: -0.35, mouthOpen: 0.1,
      squashX: 1.06, squashY: 0.96
    },

    frustration: {
      topLidL: 0.3, topLidR: 0.3, mouthCurve: -0.25, mouthOpen: 0.08,
      mouthWobble: 0.3, faceTilt: -2
    },

    disgust: {
      topLidL: 0.35, topLidR: 0.35, mouthCurve: -0.3, mouthOpen: 0.15,
      mouthWidth: 54, squashX: 0.92, squashY: 1.05, faceTilt: -6, tongueOut: 0.15
    },

    grief: {
      topLidL: 0.5, topLidR: 0.5, bottomLidL: 0.2, bottomLidR: 0.2,
      mouthCurve: -0.5, mouthWobble: 0.3, tearsOpacity: 0.5, faceTilt: -6, bobOffset: 3
    },

    loneliness: {
      topLidL: 0.3, topLidR: 0.3, mouthCurve: -0.2, lookX: -0.3, lookY: 0.2,
      faceTilt: -5, breathScale: 0.99
    },

    hope: {
      eyeLScale: 1.08, eyeRScale: 1.08, mouthCurve: 0.3, mouthOpen: 0.1,
      topLidL: 0.05, topLidR: 0.05, highlightSize: 0.45, highlightOpacity: 1,
      faceTilt: 4, pupilYOffset: -3
    },

    shyness: {
      topLidL: 0.4, topLidR: 0.4, blushOpacity: 0.5, mouthCurve: 0.2,
      smirkSide: 0.1, lookX: -0.3, faceTilt: 6
    },

    jealousy: {
      topLidL: 0.25, topLidR: 0.25, mouthCurve: -0.3, lookX: -0.5,
      faceTilt: -6, smirkSide: -0.2
    },

    confusion: {
      faceTilt: 14, eyeLScale: 1.15, eyeRScale: 0.95, mouthCurve: -0.05,
      mouthOpen: 0.1, lookX: 0.1
    },

    suspicion: {
      topLidL: 0.35, topLidR: 0.35, topLidAngleL: -10, topLidAngleR: 10,
      lookX: 0.35, faceTilt: -3, mouthCurve: -0.1
    },

    relief: {
      topLidL: 0.15, topLidR: 0.15, mouthCurve: 0.4, mouthOpen: 0.2,
      breathScale: 1.06, bobOffset: 2, squashY: 1.05
    },

    gratitude: {
      topLidL: 0.1, topLidR: 0.1, mouthCurve: 0.45, blushOpacity: 0.25,
      eyeYOffset: 1, faceTilt: 3, highlightOpacity: 1
    },

    mischief: {
      smirkSide: 0.5, topLidL: 0.15, topLidR: 0.15, mouthCurve: 0.35,
      eyeLScale: 1.05, lookX: 0.2
    },

    determination: {
      topLidL: 0.1, topLidR: 0.1, mouthCurve: 0.1, mouthWidth: 80,
      eyeLScale: 1.05, eyeRScale: 1.05, squashX: 0.97, squashY: 1.03
    },

    nervousness: {
      topLidL: 0.2, topLidR: 0.2, mouthWobble: 0.5, mouthCurve: -0.05,
      blushOpacity: 0.15, bobOffset: 1
    },

    awe: {
      eyeLScale: 1.2, eyeRScale: 1.2, mouthOpen: 0.3, mouthCurve: 0.1,
      highlightSize: 0.55, highlightOpacity: 1, faceTilt: -2
    },

    smugness: {
      smirkSide: 0.5, topLidL: 0.3, topLidR: 0.3, mouthCurve: 0.3,
      faceTilt: 5, eyeLScale: 0.95, eyeRScale: 0.95
    },

    silliness: {
      squashX: 1.15, squashY: 0.85, mouthOpen: 0.4, mouthCurve: 0.6,
      tongueOut: 0.6, eyeLScale: 1.1, eyeRScale: 0.9, faceTilt: 10
    }
  };

  // Moods where wide-open, alert eyes matter more than the cat's usual
  // smug half-lidded default -- catify() skips the extra lid-narrowing here.
  var CAT_ALERT_MOODS = {
    scared: 1, surprised: 1, wakeupAlarm: 1, curious: 1, dizzy: 1,
    anger: 1, awe: 1, delight: 1
  };

  function catify(baseParams, moodId) {
    var out = FP.mergeParams(baseParams);
    out.slitPupil = 0.8;
    out.eyelashesOpacity = 0.85;
    out.whiskersOpacity = 0.9;
    out.catOmega = out.mouthOpen < 0.05 ? (out.mouthCurve >= 0.05 ? 0.55 : 0.2) : 0;
    if (!CAT_ALERT_MOODS[moodId]) {
      out.topLidL = Math.min(1, out.topLidL + 0.10);
      out.topLidR = Math.min(1, out.topLidR + 0.10);
      out.smirkSide = FP.clamp((out.smirkSide || 0) + 0.18, -1, 1);
    }
    return out;
  }

  // Returns FULL merged params (defaults + preset [+ cat overlay]).
  function getPreset(moodId, mode) {
    var preset = PRESETS[moodId] || {};
    var merged = FP.mergeParams(preset);
    if (mode === 'cat') merged = catify(merged, moodId);
    return merged;
  }

  var api = {
    MOODS: MOODS,
    MOOD_LABELS: MOOD_LABELS,
    MOOD_GROUP: MOOD_GROUP,
    PRESETS: PRESETS,
    catify: catify,
    getPreset: getPreset
  };

  root.Expressions = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
