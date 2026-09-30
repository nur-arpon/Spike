/*
 * render_actions.js -- DEV ONLY. Filmstrips of MOTION, sampled from the real
 * behaviour engine (same code as the page), so squash & stretch, overshoot,
 * boops, pats and every physical action can be checked frame by frame.
 *   out/motion_basics.png   blink, mood-change overshoot, boop, pat, ear flick, sniff
 *   out/actions_all.png     every physical action (Classic Pup)
 *   out/actions_spicy.png   a few actions in cat mode (Spicy)
 * Run: node tools/render_actions.js
 */
'use strict';
var path = require('path');
var fs = require('fs');
var { createCanvas } = require('@napi-rs/canvas');
function req(rel) { return require(path.join(__dirname, '..', rel)); }
var Gfx = req('gfx.js');
var Recipe = req('recipe.js');
var FaceDraw = req('face_draw.js');
var Extras = req('extras.js');
req('config.js'); req('params.js'); req('moods.js'); req('sounds.js'); req('captions.js'); req('games.js');
var Behaviour = req('behaviour.js');
var Actions = req('actions.js');
req('music.js');

var OUT = path.join(__dirname, 'out');
var W = 480, H = 272, CW = 200, CH = 113, PAD = 6, LW = 118;

function engine(mode) {
  var e = Behaviour.createBehaviour({ rnd: Recipe.seeded(7) });
  if (mode) Behaviour.setMode(e, mode);
  Behaviour.setMood(e, 'neutral', { snap: true });
  e.nextBlink = e.nextGlance = e.nextEarFlick = e.nextSniff = e.nextIdleTilt = 999; // quiet idle for clean strips
  for (var i = 0; i < 30; i++) Behaviour.update(e, 1 / 60);
  return e;
}
function advance(e, sec) { var n = Math.round(sec * 120); for (var i = 0; i < n; i++) Behaviour.update(e, 1 / 120); }

function cell(ctx, x, y, e, recipe, label) {
  ctx.save(); ctx.translate(x, y); ctx.scale(CW / W, CH / H);
  ctx.beginPath(); ctx.rect(0, 0, W, H); ctx.clip();
  var G = Gfx.create(ctx);
  FaceDraw.draw(G, Behaviour.getFaceParams(e), recipe, e.time);
  Extras.draw(G, e.particles, e.time, { light: true });
  ctx.restore();
  ctx.fillStyle = '#9aa3ad'; ctx.font = '10px sans-serif'; ctx.fillText(label, x + 2, y + CH + 11);
}

// rows: [{title, frames: n, dt, setup(e), recipe, mode}]
function strip(file, rows, cols) {
  var cv = createCanvas(LW + cols * (CW + PAD), rows.length * (CH + 18 + PAD) + PAD);
  var ctx = cv.getContext('2d');
  ctx.fillStyle = '#1b1e24'; ctx.fillRect(0, 0, cv.width, cv.height);
  rows.forEach(function (r, ri) {
    var y = PAD + ri * (CH + 18 + PAD);
    ctx.fillStyle = '#fff'; ctx.font = '12px sans-serif'; ctx.fillText(r.title, 6, y + CH / 2);
    var e = engine(r.mode);
    r.setup(e);
    var t0 = e.time;
    for (var c = 0; c < cols; c++) {
      cell(ctx, LW + c * (CW + PAD), y, e, r.recipe || Recipe.PRESETS.classic, '+' + Math.round((e.time - t0) * 1000) + 'ms');
      advance(e, r.dt);
    }
  });
  var f = path.join(OUT, file);
  fs.writeFileSync(f, cv.toBuffer('image/png'));
  console.log('wrote', f, cv.width + 'x' + cv.height);
}

strip('motion_basics.png', [
  { title: 'blink (squash\n& stretch)', dt: 0.025, setup: function (e) { e.blinkUntil = e.time + 0.085; } },
  { title: 'neutral -> joy', dt: 0.05, setup: function (e) { Behaviour.setMood(e, 'joy'); } },
  { title: 'joy -> sad', dt: 0.07, setup: function (e) { Behaviour.setMood(e, 'joy', { snap: true }); Behaviour.setMood(e, 'sad'); } },
  { title: 'nose boop', dt: 0.14, setup: function (e) { Behaviour.boop(e); } },
  { title: 'head pat', dt: 0.08, setup: function (e) { Behaviour.pat(e); } },
  { title: 'ear flick', dt: 0.05, setup: function (e) { Behaviour.kick(e, { earL: -420 }); } },
  { title: 'sniff x3', dt: 0.035, setup: function (e) { Behaviour.sniff(e, 3); } },
  { title: 'idle head tilt', dt: 0.1, setup: function (e) { Behaviour.override(e, { tilt: 11 }, 0.8); } }
], 10);

var names = Actions.ACTION_NAMES;
strip('actions_all.png', names.map(function (n) {
  var total = Actions.ACTIONS[n].steps.reduce(function (s, st) { return s + (st.hold || 0.5); }, 0);
  return { title: Actions.ACTION_LABELS[n], dt: total / 9, setup: function (e) { Actions.playAction(e, n); } };
}), 10);

strip('actions_spicy.png', ['boop', 'sneeze', 'rollOver', 'wakeUp', 'headTilt'].map(function (n) {
  var total = Actions.ACTIONS[n].steps.reduce(function (s, st) { return s + (st.hold || 0.5); }, 0);
  return { title: 'Spicy: ' + Actions.ACTION_LABELS[n], dt: total / 9, mode: 'cat', recipe: Recipe.PRESETS.spicy,
    setup: function (e) { Actions.playAction(e, n); } };
}), 10);
