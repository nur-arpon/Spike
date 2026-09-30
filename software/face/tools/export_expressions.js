/*
 * export_expressions.js -- regenerates ../expressions.json from
 * ../expressions.js and ../face_params.js so the two never drift apart.
 *
 * Run after editing any mood preset:
 *   node tools/export_expressions.js
 */
'use strict';
var fs = require('fs');
var path = require('path');

var FP = require(path.join(__dirname, '..', 'face_params.js'));
var EX = require(path.join(__dirname, '..', 'expressions.js'));

var out = {
  _comment: 'Generated from expressions.js -- do not hand-edit, run tools/export_expressions.js instead. ' +
    'Screen is the Guition JC4827W543, 480x272. faceDefaults is the baseline every preset merges onto; ' +
    'each preset only lists the fields that differ from it. Cat mode is produced at runtime by the ' +
    'catify() rule in expressions.js (slitPupil, eyelashesOpacity, whiskersOpacity, catOmega, plus a ' +
    'smug lid/smirk nudge outside catAlertMoods) -- it is intentionally not duplicated in this file.',
  screen: { width: 480, height: 272 },
  moods: EX.MOODS,
  moodLabels: EX.MOOD_LABELS,
  moodGroup: EX.MOOD_GROUP,
  catAlertMoods: ['scared', 'surprised', 'wakeupAlarm', 'curious', 'dizzy'],
  faceDefaults: FP.FACE_DEFAULTS,
  presets: EX.PRESETS
};

var target = path.join(__dirname, '..', 'expressions.json');
fs.writeFileSync(target, JSON.stringify(out, null, 2) + '\n');
console.log('Wrote ' + target + ' (' + EX.MOODS.length + ' moods)');
