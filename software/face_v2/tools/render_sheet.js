/*
 * render_sheet.js -- DEV ONLY. Contact sheets drawn with the exact same
 * pure renderer the page uses:
 *   out/presets_key_moods.png   every preset x the key moods
 *   out/moods_spike.png         every mood, Classic Pup, dog mode
 *   out/moods_spicy.png         every mood, Spicy, cat mode
 *   out/actions_*.png           frames sampled from the real behaviour engine
 *   out/random_recipes.png      dice faces x a few moods (Studio robustness)
 *
 * Run:  node tools/render_sheet.js [presets|moods|actions|random]
 */
'use strict';
var path = require('path');
var fs = require('fs');
var { createCanvas } = require('@napi-rs/canvas');
function req(rel) { return require(path.join(__dirname, '..', rel)); }
var Gfx = req('gfx.js');
var FP = req('params.js');
var Recipe = req('recipe.js');
var FaceDraw = req('face_draw.js');
var Moods = req('moods.js');

var OUT = path.join(__dirname, 'out');
fs.mkdirSync(OUT, { recursive: true });
var W = 480, H = 272;
var KEY_MOODS = ['neutral', 'joy', 'happy', 'sad', 'love', 'sleepy', 'surprised', 'anger', 'playful', 'grief', 'hungry'];

function face(ctx, x, y, scale, recipe, state, t) {
  ctx.save();
  ctx.translate(x, y); ctx.scale(scale, scale);
  ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();  // sheet framing only
  FaceDraw.draw(Gfx.create(ctx), state, recipe, t == null ? 0.6 : t);
  ctx.restore();
}
function text(ctx, s, x, y, size, color) {
  ctx.fillStyle = color || '#c9ced6'; ctx.font = (size || 12) + 'px sans-serif'; ctx.fillText(s, x, y);
}
function save(cv, name) {
  var f = path.join(OUT, name);
  fs.writeFileSync(f, cv.toBuffer('image/png'));
  console.log('wrote', f, cv.width + 'x' + cv.height);
}

function presetsSheet() {
  var cw = 144, ch = 82, pad = 6, lw = 110;
  var ids = Recipe.PRESET_ORDER;
  var cv = createCanvas(lw + KEY_MOODS.length * (cw + pad) + pad, 26 + ids.length * (ch + pad) + pad);
  var ctx = cv.getContext('2d');
  ctx.fillStyle = '#1b1e24'; ctx.fillRect(0, 0, cv.width, cv.height);
  KEY_MOODS.forEach(function (m, i) { text(ctx, m, lw + i * (cw + pad) + 3, 18, 11); });
  ids.forEach(function (id, row) {
    var rec = Recipe.PRESETS[id], mode = Recipe.PRESET_KIND[id] === 'cat' ? 'cat' : 'dog';
    var y = 26 + row * (ch + pad);
    text(ctx, rec.name, 6, y + ch / 2, 12, '#fff');
    text(ctx, mode, 6, y + ch / 2 + 15, 10);
    KEY_MOODS.forEach(function (m, i) { face(ctx, lw + i * (cw + pad), y, cw / W, rec, Moods.getTarget(m, mode)); });
  });
  save(cv, 'presets_key_moods.png');
}

function moodsSheet(presetId, mode, file) {
  var cw = 240, ch = 136, pad = 8, cols = 6, lh = 16;
  var list = Moods.MOODS, rows = Math.ceil(list.length / cols);
  var cv = createCanvas(pad + cols * (cw + pad), 30 + rows * (ch + lh + pad));
  var ctx = cv.getContext('2d');
  ctx.fillStyle = '#1b1e24'; ctx.fillRect(0, 0, cv.width, cv.height);
  var rec = Recipe.PRESETS[presetId];
  text(ctx, rec.name + ' -- all ' + list.length + ' moods (' + mode + ' mode)', pad, 20, 14, '#fff');
  list.forEach(function (m, i) {
    var x = pad + (i % cols) * (cw + pad), y = 30 + Math.floor(i / cols) * (ch + lh + pad);
    var st = Moods.applyMotion(Moods.getTarget(m, mode), m, 0.35, 1);
    face(ctx, x, y, cw / W, rec, FP.clampState(st), 0.6);
    text(ctx, Moods.LABELS[m], x + 2, y + ch + 12, 11);
  });
  save(cv, file);
}

function randomSheet() {
  var rnd = Recipe.seeded(20260928);
  var moods = ['neutral', 'joy', 'sad', 'love', 'anger', 'sleeping', 'surprised'];
  var n = 12, cw = 160, ch = 91, pad = 6;
  var cv = createCanvas(pad + moods.length * (cw + pad), 24 + n * (ch + pad));
  var ctx = cv.getContext('2d');
  ctx.fillStyle = '#1b1e24'; ctx.fillRect(0, 0, cv.width, cv.height);
  moods.forEach(function (m, i) { text(ctx, m, pad + i * (cw + pad) + 3, 16, 11); });
  for (var r = 0; r < n; r++) {
    var rec = Recipe.randomRecipe(rnd);
    moods.forEach(function (m, i) { face(ctx, pad + i * (cw + pad), 24 + r * (ch + pad), cw / W, rec, Moods.getTarget(m, 'dog')); });
  }
  save(cv, 'random_recipes.png');
}

var which = process.argv[2];
if (!which || which === 'presets') presetsSheet();
if (!which || which === 'moods') { moodsSheet('classic', 'dog', 'moods_spike.png'); moodsSheet('spicy', 'cat', 'moods_spicy.png'); }
if (!which || which === 'random') randomSheet();
if ((!which || which === 'actions') && fs.existsSync(path.join(__dirname, 'render_actions.js'))) require('./render_actions.js');
