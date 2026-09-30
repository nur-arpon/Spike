/*
 * export_recipes.js -- exports everything the C++ (ESP32-S3 / LovyanGFX)
 * port needs as data, so the firmware never re-types a number by hand:
 *   out/face_v2_export.json
 *     layout      eye/nose/mouth anchors, eye shapes, mouth styles
 *     params      the face-state fields: default, range, spring [k, d]
 *     moods       every mood: face (dog), face (cat), motion, extras, follow flag, caption group
 *     slots       the Face Studio slot catalogue (index order = share-code order)
 *     presets     every preset recipe + its share code
 *     actions     every physical action: body label + step list (functions -> "fn")
 * Run:  node tools/export_recipes.js
 */
'use strict';
var path = require('path'), fs = require('fs');
function req(rel) { return require(path.join(__dirname, '..', rel)); }
var SPIKE = req('config.js');
var FP = req('params.js');
var Recipe = req('recipe.js');
var FaceDraw = req('face_draw.js');
var Moods = req('moods.js');
req('gfx.js'); req('extras.js'); req('sounds.js'); req('captions.js'); req('games.js');
req('behaviour.js');
var Actions = req('actions.js');

function plain(v) {
  if (typeof v === 'function') return 'fn';
  if (Array.isArray(v)) return v.map(plain);
  if (v && typeof v === 'object') { var o = {}; for (var k in v) o[k] = plain(v[k]); return o; }
  return v;
}

var params = {};
FP.FIELDS.forEach(function (f) {
  params[f] = { default: FP.DEFAULTS[f], range: FP.RANGES[f], spring: FP.TUNE[FP.GROUP[f] || 'shape'], group: FP.GROUP[f] };
});

var moods = {};
Moods.MOODS.forEach(function (id) {
  moods[id] = {
    label: Moods.LABELS[id], captionGroup: Moods.GROUP[id],
    face: Moods.FACE[id], faceCat: Moods.getFace(id, 'cat'),
    motion: Moods.MOTION[id] || [], extras: Moods.EXTRAS[id] || null, followsLook: Moods.followsLook(id)
  };
});

var presets = {};
Recipe.PRESET_ORDER.forEach(function (id) {
  presets[id] = { kind: Recipe.PRESET_KIND[id], code: Recipe.toCode(Recipe.PRESETS[id]), recipe: Recipe.PRESETS[id] };
});

var actions = {};
Object.keys(Actions.ACTIONS).forEach(function (id) {
  var a = Actions.ACTIONS[id];
  actions[id] = { label: a.label, restore: !!a.restore, title: Actions.ACTION_LABELS[id], steps: plain(a.steps) };
});

var out = {
  version: 2, generated: new Date().toISOString().slice(0, 10),
  screen: { width: SPIKE.screenWidth, height: SPIKE.screenHeight },
  names: { dog: SPIKE.dogName, cat: SPIKE.catName, dogWakeWords: SPIKE.dogWakeWords, catWakeWords: SPIKE.catWakeWords },
  layout: { anchors: FaceDraw.LAYOUT, eyeShapes: FaceDraw.EYE_SHAPES, mouthStyles: FaceDraw.MOUTH },
  params: params,
  moods: moods, moodOrder: Moods.MOODS,
  slots: { enums: Recipe.SLOTS, colors: Recipe.COLORS, numbers: Recipe.NUMBERS },
  presets: presets, presetOrder: Recipe.PRESET_ORDER,
  actions: actions, actionOrder: Actions.ACTION_NAMES
};
var dir = path.join(__dirname, 'out');
fs.mkdirSync(dir, { recursive: true });
var file = path.join(dir, 'face_v2_export.json');
fs.writeFileSync(file, JSON.stringify(out, null, 1));
console.log('wrote', file, Math.round(fs.statSync(file).size / 1024) + ' KB:',
  Object.keys(moods).length, 'moods,', Object.keys(presets).length, 'presets,', Object.keys(actions).length, 'actions,',
  FP.FIELDS.length, 'face fields');
