/*
 * js_cases.js -- golden-image test, JS side.
 *
 * Builds the test cases from face_v2 ITSELF (presets x key moods, every mood for Spike and Spicy, dice
 * recipes, and frames sampled from the real behaviour engine: blinks, boop, pat, sneeze, roll-over,
 * hungry lick, particles...), then
 *   - renders each case with the JS renderer (face_draw.js + extras.js on @napi-rs/canvas, exactly as
 *     face_v2/tools does) to test/out/raw/js/<name>.rgb (480 x 272 RGB8)
 *   - writes test/out/cases.txt: the exact face state, recipe, t and particles of every case, which the
 *     C++ build (pc/face_pc.exe cases) renders with the shared C++ core.
 * test/compare.py then diffs the two and writes the side-by-side diff sheets.
 *
 * Only READS software/face_v2. Run: node software/firmware/test/js_cases.js
 */
'use strict';
var path = require('path'), fs = require('fs');
var FACE = path.join(__dirname, '..', '..', 'face_v2');
var { createCanvas } = require(path.join(FACE, 'tools', 'node_modules', '@napi-rs', 'canvas'));
function req(f) { return require(path.join(FACE, f)); }
var Gfx = req('gfx.js');
var FP = req('params.js');
var Recipe = req('recipe.js');
var FaceDraw = req('face_draw.js');
var Moods = req('moods.js');
var Extras = req('extras.js');
req('config.js'); req('sounds.js'); req('captions.js'); req('games.js');
var Behaviour = req('behaviour.js');
var Actions = req('actions.js');
req('music.js');

var OUT = path.join(__dirname, 'out');
var RAW = path.join(OUT, 'raw', 'js');
fs.mkdirSync(RAW, { recursive: true });
var W = 480, H = 272;
var SLOT_KEYS = Object.keys(Recipe.SLOTS), NUM_KEYS = Object.keys(Recipe.NUMBERS);
var KEY_MOODS = ['neutral', 'joy', 'happy', 'sad', 'love', 'sleepy', 'surprised', 'anger', 'playful', 'grief', 'hungry'];

var cases = [];
function add(name, state, recipe, t, moodId, cat, particles, light) {
  cases.push({ name: name, state: state, recipe: recipe, t: t, moodIdx: moodId ? Moods.MOODS.indexOf(moodId) : -1,
    cat: !!cat, particles: particles || [], light: !!light });
}

// 1. every preset x the key moods (the presets sheet)
Recipe.PRESET_ORDER.forEach(function (id) {
  var rec = Recipe.PRESETS[id], mode = Recipe.PRESET_KIND[id];
  KEY_MOODS.forEach(function (m) { add('preset_' + id + '_' + m, Moods.getTarget(m, mode), rec, 0.6, m, mode === 'cat'); });
});
// 2. every mood, Spike (dog) and Spicy (cat), with the mood's motion applied (the moods sheets)
Moods.MOODS.forEach(function (m) {
  add('spike_' + m, FP.clampState(Moods.applyMotion(Moods.getTarget(m, 'dog'), m, 0.35, 1)), Recipe.PRESETS.classic, 0.6);
  add('spicy_' + m, FP.clampState(Moods.applyMotion(Moods.getTarget(m, 'cat'), m, 0.35, 1)), Recipe.PRESETS.spicy, 0.6);
});
// 3. dice recipes (Studio robustness): every slot option shows up somewhere
(function () {
  var rnd = Recipe.seeded(20260928);
  var moods = ['neutral', 'joy', 'sad', 'anger'];
  for (var r = 0; r < 14; r++) {
    var rec = Recipe.randomRecipe(rnd);
    moods.forEach(function (m) { add('dice' + r + '_' + m, Moods.getTarget(m, 'dog'), rec, 0.6, m, false); });
  }
  // the opt-in accessories and rare slots, forced
  ['glasses', 'hat', 'bandana', 'flower', 'bow'].forEach(function (acc, i) {
    var rec = Recipe.normalize(Object.assign({}, Recipe.PRESETS.classic, { accessory: acc, brows: ['arcs', 'bold', 'dots', 'arcs', 'bold'][i],
      ears: ['round', 'bear', 'bunny', 'fold', 'pointy'][i], freckles: 'yes', muzzle: ['round', 'wide', 'round', 'wide', 'none'][i],
      pattern: ['spots', 'tabby', 'mask', 'blaze', 'tux'][i], frame: i % 2 ? 'head' : 'full', lashes: ['full', 'flick', 'none', 'full', 'flick'][i] }));
    add('slots_' + acc, Moods.getTarget(['love', 'cuteAngry', 'scared', 'confusion', 'dizzy'][i], 'dog'), rec, 0.9 + i * 0.37, null, false);
  });
})();
// 4. frames from the real behaviour engine (motion: squash & stretch, overshoot, kicks, particles)
function engine(mode) {
  var e = Behaviour.createBehaviour({ rnd: Recipe.seeded(7) });
  if (mode) Behaviour.setMode(e, mode);
  Behaviour.setMood(e, 'neutral', { snap: true });
  e.nextBlink = e.nextGlance = e.nextEarFlick = e.nextSniff = e.nextIdleTilt = 999;
  for (var i = 0; i < 30; i++) Behaviour.update(e, 1 / 60);
  return e;
}
function advance(e, sec) { var n = Math.round(sec * 120); for (var i = 0; i < n; i++) Behaviour.update(e, 1 / 120); }
function snapParticles(e) {
  return e.particles.list.map(function (p) {
    return [p.type, p.x, p.y, p.age, p.life, p.rot, p.scale, p.seed, p.orbit ? 1 : 0, p.ox, p.oy, p.orbitR, p.orbitSpeed];
  });
}
var STRIPS = [
  ['blink', null, 'classic', function (e) { e.blinkUntil = e.time + 0.085; }, [0.03, 0.06, 0.1, 0.16]],
  ['joy', null, 'classic', function (e) { Behaviour.setMood(e, 'joy'); }, [0.1, 0.3, 0.9]],
  ['boop', null, 'classic', function (e) { Behaviour.boop(e); }, [0.1, 0.3, 0.8, 1.2]],
  ['pat', null, 'classic', function (e) { Behaviour.pat(e); }, [0.08, 0.25, 0.6]],
  ['sneeze', null, 'classic', function (e) { Actions.playAction(e, 'sneeze'); }, [0.6, 1.0, 1.3]],
  ['rollover', null, 'classic', function (e) { Actions.playAction(e, 'rollOver'); }, [0.5, 0.8]],
  ['zoomies', null, 'beagle', function (e) { Actions.playAction(e, 'zoomies'); }, [0.3, 1.0]],
  ['hungry', null, 'classic', function (e) { Behaviour.setMood(e, 'hungry'); }, [0.513, 1.1, 2.0, 2.6, 3.3]],
  ['sleeping', null, 'husky', function (e) { Behaviour.setMood(e, 'sleeping'); }, [1.0, 2.5]],
  ['trip', null, 'anime', function (e) { Actions.playAction(e, 'tripBump'); }, [0.3, 0.8]],
  ['catpat', 'cat', 'spicy', function (e) { Behaviour.pat(e); }, [0.2, 0.5]],
  ['catwake', 'cat', 'tuxedo', function (e) { Actions.playAction(e, 'wakeUp'); }, [1.2, 3.5]],
  ['minimal', null, 'minimal', function (e) { Behaviour.setMood(e, 'hungry'); }, [0.6, 1.5]],
  ['night', null, 'night', function (e) { Actions.playAction(e, 'hiccup'); }, [0.6]],
  ['sticker', null, 'sticker', function (e) { Actions.playAction(e, 'tailWagDance'); }, [0.4, 1.4]]
];
STRIPS.forEach(function (s) {
  var e = engine(s[1]);
  s[3](e);
  var t0 = e.time, rec = Recipe.PRESETS[s[2]];
  var back = rec.frame === 'head' ? rec.bg : rec.fur;
  s[4].forEach(function (at) {
    advance(e, at - (e.time - t0));
    add('motion_' + s[0] + '_' + Math.round(at * 1000), Behaviour.getFaceParams(e), rec, e.time, null, false,
      snapParticles(e), Gfx.luminance(back) > 0.45);
  });
});

// ---- render (JS) + write cases.txt --------------------------------------------------------------
var cv = createCanvas(W, H), ctx = cv.getContext('2d');
var lines = ['# name t moodIdx cat slots(' + SLOT_KEYS.length + ') colours(16) numbers(5) icon fields(' + FP.FIELDS.length +
  ') light nParticles [type x y age life rot scale seed orbit ox oy orbitR orbitSpeed]*'];
cases.forEach(function (c) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1;
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  var G = Gfx.create(ctx);
  FaceDraw.draw(G, c.state, c.recipe, c.t);
  if (c.particles.length) {
    var sys = { list: c.particles.map(function (q) {
      return { type: q[0], x: q[1], y: q[2], age: q[3], life: q[4], rot: q[5], scale: q[6], seed: q[7], orbit: !!q[8],
        ox: q[9], oy: q[10], orbitR: q[11], orbitSpeed: q[12], color: null };
    }) };
    Extras.draw(G, sys, c.t, { light: c.light });
  }
  var img = ctx.getImageData(0, 0, W, H).data, rgb = Buffer.alloc(W * H * 3);
  for (var i = 0, j = 0; i < img.length; i += 4, j += 3) { rgb[j] = img[i]; rgb[j + 1] = img[i + 1]; rgb[j + 2] = img[i + 2]; }
  fs.writeFileSync(path.join(RAW, c.name + '.rgb'), rgb);

  var r = c.recipe, st = c.state;
  var f = [c.name, c.t, c.moodIdx, c.cat ? 1 : 0];
  SLOT_KEYS.forEach(function (k) { f.push(Recipe.SLOTS[k].indexOf(r[k])); });
  Recipe.COLORS.forEach(function (k) { f.push(r[k].replace('#', '')); });
  NUM_KEYS.forEach(function (k) { f.push(r[k]); });
  f.push(st.icon ? st.icon : '-');
  FP.FIELDS.forEach(function (k) { f.push(st[k]); });
  f.push(c.light ? 1 : 0, c.particles.length);
  c.particles.forEach(function (q) { f.push.apply(f, q); });
  lines.push(f.join(' '));
});
fs.writeFileSync(path.join(OUT, 'cases.txt'), lines.join('\n') + '\n');
console.log('js: rendered ' + cases.length + ' cases -> ' + RAW + ' and cases.txt');
