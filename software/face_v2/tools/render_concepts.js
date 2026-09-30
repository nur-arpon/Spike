/*
 * render_concepts.js -- DEV ONLY. Design exploration contact sheets.
 * One sheet per concept direction (big neutral + thumbnails at "desk
 * distance" + the key moods), plus an overview of all concepts.
 *
 * Run:  node tools/render_concepts.js      -> tools/out/concepts/*.png
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

var OUT = path.join(__dirname, 'out', 'concepts');
fs.mkdirSync(OUT, { recursive: true });
var W = 480, H = 272;
var SHEET_MOODS = ['neutral', 'happy', 'joy', 'sad', 'love', 'sleepy', 'surprised', 'anger'];

function drawFace(ctx, x, y, scale, recipe, mood, mode, t, extra) {
  ctx.save();
  ctx.translate(x, y);
  ctx.scale(scale, scale);
  ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip(); // sheet framing only (not part of the face)
  var st = FP.merge(Moods.getTarget(mood, mode), extra || {});
  FaceDraw.draw(Gfx.create(ctx), st, recipe, t == null ? 0.6 : t);
  ctx.restore();
}

function label(ctx, text, x, y, size, color) {
  ctx.fillStyle = color || '#c9ced6';
  ctx.font = (size || 13) + 'px sans-serif';
  ctx.fillText(text, x, y);
}

function conceptSheet(id, recipe, mode) {
  var cw = 240, ch = 136, pad = 12, cols = 4;
  var width = pad + cols * (cw + pad);
  var heroH = H;
  var height = 40 + heroH + pad + 2 * (ch + 22) + pad;
  var cv = createCanvas(width, height), ctx = cv.getContext('2d');
  ctx.fillStyle = '#1b1e24'; ctx.fillRect(0, 0, width, height);
  label(ctx, recipe.name + '  (' + mode + ')', pad, 26, 18, '#ffffff');
  drawFace(ctx, pad, 40, 1, recipe, 'neutral', mode);
  // desk-distance thumbnails (120 px wide)
  var tx = pad + W + pad * 2;
  label(ctx, 'at 120 px (desk distance):', tx, 56, 12);
  var th = ['neutral', 'joy', 'sad', 'love', 'anger', 'sleepy'];
  for (var i = 0; i < th.length; i++) {
    var col = i % 2, row = Math.floor(i / 2);
    drawFace(ctx, tx + col * 132, 66 + row * 78, 0.25, recipe, th[i], mode);
  }
  for (var m = 0; m < SHEET_MOODS.length; m++) {
    var c = m % cols, r = Math.floor(m / cols);
    var x = pad + c * (cw + pad), y = 40 + heroH + pad + r * (ch + 22);
    drawFace(ctx, x, y, 0.5, recipe, SHEET_MOODS[m], mode);
    label(ctx, SHEET_MOODS[m], x + 2, y + ch + 15, 12);
  }
  var file = path.join(OUT, id + '.png');
  fs.writeFileSync(file, cv.toBuffer('image/png'));
  console.log('wrote', file);
}

function overview(list) {
  var cw = 160, ch = 91, pad = 8, lw = 150;
  var width = lw + SHEET_MOODS.length * (cw + pad) + pad;
  var height = 30 + list.length * (ch + pad) + pad;
  var cv = createCanvas(width, height), ctx = cv.getContext('2d');
  ctx.fillStyle = '#1b1e24'; ctx.fillRect(0, 0, width, height);
  for (var m = 0; m < SHEET_MOODS.length; m++) label(ctx, SHEET_MOODS[m], lw + m * (cw + pad) + 4, 20, 12);
  list.forEach(function (it, i) {
    var y = 30 + i * (ch + pad);
    label(ctx, it.recipe.name.split(':')[0], 8, y + ch / 2, 13, '#ffffff');
    label(ctx, (it.recipe.name.split(':')[1] || '').trim(), 8, y + ch / 2 + 16, 11);
    for (var m2 = 0; m2 < SHEET_MOODS.length; m2++) drawFace(ctx, lw + m2 * (cw + pad), y, cw / W, it.recipe, SHEET_MOODS[m2], it.mode);
  });
  var file = path.join(OUT, 'overview.png');
  fs.writeFileSync(file, cv.toBuffer('image/png'));
  console.log('wrote', file);
}

var list = [];
Object.keys(Recipe.CONCEPTS).forEach(function (id) {
  var mode = id.indexOf('cat') === 0 ? 'cat' : 'dog';
  var rec = Recipe.normalize(Recipe.CONCEPTS[id]);
  rec.name = Recipe.CONCEPTS[id].name;
  var only = process.argv[2];
  if (!only || id.indexOf(only) !== -1) conceptSheet(id, rec, mode);
  list.push({ recipe: rec, mode: mode });
});
overview(list);
