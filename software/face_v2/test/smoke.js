/*
 * test/smoke.js -- run:  node test/smoke.js      (exit code 0 = pass)
 *
 * Checks, all against the REAL renderer in record mode (gfx.js logs every
 * primitive with its device-space bounding box and feature tag):
 *  1. every mood x every preset x 20 random recipes x dog/cat mode draws
 *     without throwing and without a single NaN coordinate
 *  2. face position rules (owner's hard rules), measured on the drawn shapes:
 *     eye centres 42-48 % of height, nose 60-65 %, mouth + tongue in 70-90 %
 *  3. nothing is drawn in the gap between the eyes at neutral (only fur),
 *     and nothing spans from one eye to the other
 *  4. portability: every G.poly is convex (a triangle fan on the ESP32)
 *  5. springs settle; blink overshoot really produces a stretch
 *  6. the behaviour engine runs every event, action, song and battery path
 *     for 2 seconds each, all values finite, every action finishes
 *  7. share codes round-trip; the nose hit-test finds the nose
 */
'use strict';
var path = require('path');
function req(rel) { return require(path.join(__dirname, '..', rel)); }
var SPIKE = req('config.js');
var Gfx = req('gfx.js');
var FP = req('params.js');
var Recipe = req('recipe.js');
var FaceDraw = req('face_draw.js');
var Moods = req('moods.js');
var Extras = req('extras.js');
req('sounds.js'); req('captions.js'); var Games = req('games.js');
var Behaviour = req('behaviour.js');
var Actions = req('actions.js');
var Music = req('music.js');

var W = 480, H = 272;
var fails = 0, checks = 0;
function ok(cond, msg) { checks++; if (!cond) { fails++; if (fails <= 40) console.log('  FAIL: ' + msg); } }
function section(s) { console.log('\n== ' + s); }

var rnd = Recipe.seeded(424242);
var RANDOM = [];
for (var i = 0; i < 20; i++) RANDOM.push(Recipe.randomRecipe(rnd));
var RECIPES = Recipe.PRESET_ORDER.map(function (id) { return { id: id, r: Recipe.PRESETS[id] }; })
  .concat(RANDOM.map(function (r, k) { return { id: 'random' + k, r: r }; }));

// Layout checks use the settled pose with whole-head motion removed (tilt,
// bob, sway are motion, not layout).
var STILL = { tilt: 0, bob: 0, shakeX: 0, headSX: 1, headSY: 1 };
function record(state, recipe, t) {
  var G = Gfx.create(null, { record: true });
  var geo = FaceDraw.draw(G, state, recipe, t == null ? 0.6 : t);
  return { log: G.log, geo: geo };
}
function bbox(log, tagTest) {
  var b = null;
  log.forEach(function (e) {
    if (!tagTest(e.tag)) return;
    if (!b) b = { x0: e.x0, y0: e.y0, x1: e.x1, y1: e.y1 };
    else { b.x0 = Math.min(b.x0, e.x0); b.y0 = Math.min(b.y0, e.y0); b.x1 = Math.max(b.x1, e.x1); b.y1 = Math.max(b.y1, e.y1); }
  });
  return b;
}

// ---------------------------------------------------------------------
section('1. every mood x every recipe x both modes draws cleanly');
var draws = 0, nonConvex = 0, t0 = Date.now();
RECIPES.forEach(function (rc) {
  ['dog', 'cat'].forEach(function (mode) {
    Moods.MOODS.forEach(function (m) {
      [0.37, 1.93].forEach(function (tt) {
        var st = FP.clampState(Moods.applyMotion(Moods.getTarget(m, mode), m, tt, 1));
        try {
          var res = record(st, rc.r, tt);
          draws++;
          res.log.forEach(function (e) { if (e.kind === 'poly' && e.convex === false) { nonConvex++; if (nonConvex < 4) console.log('  non-convex poly: ' + rc.id + ' ' + m + ' tag ' + e.tag); } });
        } catch (err) { ok(false, rc.id + ' / ' + mode + ' / ' + m + ': ' + err.message); }
      });
    });
  });
});
ok(draws === RECIPES.length * 2 * Moods.MOODS.length * 2, 'all draws completed (' + draws + ')');
console.log('  ' + draws + ' frames drawn (' + RECIPES.length + ' recipes x 2 modes x ' + Moods.MOODS.length + ' moods x 2 times) in ' + (Date.now() - t0) + ' ms');

section('4. portability: polygons are convex');
ok(nonConvex === 0, nonConvex + ' non-convex G.poly calls');
console.log('  non-convex polys: ' + nonConvex);

// ---------------------------------------------------------------------
section('2. face position rules');
var worst = { eye: [1, 0], nose: [1, 0], mouth: [1, 0] };
RECIPES.forEach(function (rc) {
  ['dog', 'cat'].forEach(function (mode) {
    Moods.MOODS.forEach(function (m) {
      var st = FP.merge(Moods.getTarget(m, mode), STILL);
      var res = record(st, rc.r);
      // eyes: the drawn eye geometry centre (icons replace the eye in place)
      res.geo.eyes.forEach(function (g) {
        var f = g.ey / H;
        worst.eye[0] = Math.min(worst.eye[0], f); worst.eye[1] = Math.max(worst.eye[1], f);
        ok(f >= 0.42 && f <= 0.48, rc.id + '/' + mode + '/' + m + ' eye centre at ' + (f * 100).toFixed(1) + '%');
      });
      var nb = bbox(res.log, function (tg) { return tg === 'nose'; });
      ok(!!nb, rc.id + ' has a nose');
      if (nb) {
        var nf = (nb.y0 + nb.y1) / 2 / H;
        worst.nose[0] = Math.min(worst.nose[0], nf); worst.nose[1] = Math.max(worst.nose[1], nf);
        ok(nf >= 0.60 && nf <= 0.65, rc.id + '/' + mode + '/' + m + ' nose centre at ' + (nf * 100).toFixed(1) + '%');
      }
      var mb = bbox(res.log, function (tg) { return tg === 'mouth'; });
      if (mb) {
        worst.mouth[0] = Math.min(worst.mouth[0], mb.y0 / H); worst.mouth[1] = Math.max(worst.mouth[1], mb.y1 / H);
        ok(mb.y0 >= 0.70 * H - 0.01 && mb.y1 <= 0.90 * H + 0.01,
          rc.id + '/' + mode + '/' + m + ' mouth spans ' + (mb.y0 / H * 100).toFixed(1) + '-' + (mb.y1 / H * 100).toFixed(1) + '%');
      }
    });
  });
});
console.log('  eye centres  ' + (worst.eye[0] * 100).toFixed(1) + '% .. ' + (worst.eye[1] * 100).toFixed(1) + '%   (rule 42-48)');
console.log('  nose centre  ' + (worst.nose[0] * 100).toFixed(1) + '% .. ' + (worst.nose[1] * 100).toFixed(1) + '%   (rule 60-65)');
console.log('  mouth+tongue ' + (worst.mouth[0] * 100).toFixed(1) + '% .. ' + (worst.mouth[1] * 100).toFixed(1) + '%   (rule 70-90)');

// ---------------------------------------------------------------------
section('2b. HUNGRY: begging face on fur, battery eyes only on glow styles');
var hungryFrames = 0, hWorst = [1, 0];
RECIPES.forEach(function (rc) {
  ['dog', 'cat'].forEach(function (mode) {
    var glow = rc.r.eyeStyle === 'glow';
    for (var tt = 0; tt < Moods.HUNGRY_CYCLE; tt += 0.1) {  // the whole lick / drool / rumble cycle
      var st = FP.merge(FP.clampState(Moods.applyMotion(Moods.getTarget('hungry', mode), 'hungry', tt, 1)), STILL);
      var res = record(st, rc.r, tt);
      hungryFrames++;
      var mb = bbox(res.log, function (tg) { return tg === 'mouth'; });
      if (mb) {
        hWorst[0] = Math.min(hWorst[0], mb.y0 / H); hWorst[1] = Math.max(hWorst[1], mb.y1 / H);
        ok(mb.y0 >= 0.70 * H - 0.01 && mb.y1 <= 0.90 * H + 0.01, rc.id + '/' + mode + ' hungry t=' + tt.toFixed(1) + ' mouth ' + (mb.y0 / H * 100).toFixed(1) + '-' + (mb.y1 / H * 100).toFixed(1) + '%');
      }
      if (Math.abs(tt - 0.6) < 0.05) {
        var icon = res.log.some(function (e) { return e.tag === 'eye-icon'; });
        var pop = res.log.some(function (e) { return e.tag === 'decal-battery'; });
        ok(glow ? (icon && !pop) : (!icon && pop), rc.id + '/' + mode + ' hungry: ' + (glow ? 'battery eyes' : 'pop-up battery, normal eyes') +
          ' (icon ' + icon + ', pop ' + pop + ')');
      }
    }
  });
});
console.log('  ' + hungryFrames + ' hungry frames across the 3.6 s cycle; mouth + lick + drool ' + (hWorst[0] * 100).toFixed(1) + '% .. ' + (hWorst[1] * 100).toFixed(1) + '%');

// ---------------------------------------------------------------------
section('3. nothing between the eyes at neutral');
var gapChecked = 0;
RECIPES.forEach(function (rc) {
  if (rc.r.accessory === 'glasses') return; // the one opt-in exception (see DESIGN.md)
  ['dog', 'cat'].forEach(function (mode) {
    var st = FP.merge(Moods.getTarget('neutral', mode), STILL);
    var res = record(st, rc.r);
    var L = res.geo.eyes[0], R = res.geo.eyes[1];
    // the eyes as actually drawn (outline ring, slant and lashes included)
    var eL = bbox(res.log, function (tg) { return false; }), eR = null;
    res.log.forEach(function (e) {
      if (e.tag !== 'eye') return;
      var left = (e.x0 + e.x1) / 2 < W / 2, b = left ? eL : eR;
      if (!b) { b = { x0: e.x0, x1: e.x1 }; if (left) eL = b; else eR = b; }
      b.x0 = Math.min(b.x0, e.x0); b.x1 = Math.max(b.x1, e.x1);
    });
    ok(eL.x1 < W / 2 - 20 && eR.x0 > W / 2 + 20, rc.id + '/' + mode + ': eyes stay clear of the midline');
    var gap = { x0: eL.x1 + 1, x1: eR.x0 - 1, y0: L.ey - L.b0, y1: L.ey + 0.3 * L.b0 };
    ok(gap.x1 - gap.x0 >= 40, rc.id + '/' + mode + ': eye gap is ' + (gap.x1 - gap.x0).toFixed(0) + ' px');
    res.log.forEach(function (e) {
      // fur/pattern and the global dim layer are the skin itself, not a feature
      if (e.tag === 'fur' || e.tag === 'face' || e.tag === 'dim') return;
      var hit = e.x1 > gap.x0 && e.x0 < gap.x1 && e.y1 > gap.y0 && e.y0 < gap.y1;
      ok(!hit, rc.id + '/' + mode + ': "' + e.tag + '" ' + e.kind + ' drawn in the eye gap');
      var spans = e.x0 < L.ex && e.x1 > R.ex && e.y1 > gap.y0 && e.y0 < gap.y1;
      ok(!spans, rc.id + '/' + mode + ': "' + e.tag + '" spans from eye to eye');
    });
    gapChecked++;
  });
});
console.log('  checked ' + gapChecked + ' neutral faces');

// ---------------------------------------------------------------------
section('5. springs: settle, and blinks squash & stretch');
var s = FP.createSprings({});
FP.setTarget(s, { smile: 1, tilt: 10, earL: 20 });
for (var k = 0; k < 600; k++) FP.step(s, 1 / 60);
ok(Math.abs(s.current.smile - 1) < 1e-3 && Math.abs(s.current.tilt - 10) < 1e-2, 'springs settle on target');
var peak = 0;
var s2 = FP.createSprings({}); FP.setTarget(s2, { tilt: 10 });
for (k = 0; k < 120; k++) { FP.step(s2, 1 / 60); peak = Math.max(peak, s2.current.tilt); }
ok(peak > 10.5, 'head tilt overshoots (peak ' + peak.toFixed(2) + ')');
var s3 = FP.createSprings({}); FP.setTarget(s3, { blinkL: 1 });
for (k = 0; k < 6; k++) FP.step(s3, 1 / 60);
FP.setTarget(s3, { blinkL: 0 });
var minBlink = 1;
for (k = 0; k < 60; k++) { FP.step(s3, 1 / 60); minBlink = Math.min(minBlink, s3.current.blinkL); }
ok(minBlink < -0.03, 'blink re-opens past open = stretch (min ' + minBlink.toFixed(3) + ')');
var gOpen = FaceDraw.eyeGeom(FP.merge({ blinkL: 0 }), Recipe.PRESETS.classic, -1);
var gStretch = FaceDraw.eyeGeom(FP.merge({ blinkL: minBlink }), Recipe.PRESETS.classic, -1);
var gSquash = FaceDraw.eyeGeom(FP.merge({ blinkL: 0.6 }), Recipe.PRESETS.classic, -1);
ok(gStretch.b > gOpen.b && gSquash.b < gOpen.b && gSquash.a > gOpen.a, 'eye is taller on the rebound, shorter + wider mid-blink');
console.log('  tilt overshoot peak ' + peak.toFixed(2) + ' / 10, blink rebound ' + minBlink.toFixed(3) + ', eye height open/stretch/squash ' +
  gOpen.b.toFixed(1) + '/' + gStretch.b.toFixed(1) + '/' + gSquash.b.toFixed(1));

// ---------------------------------------------------------------------
section('6. behaviour engine: events, actions, song, battery');
function finiteState(p, where) {
  for (var f in p) if (f !== 'icon' && !(typeof p[f] === 'number' && isFinite(p[f]))) { ok(false, where + ': ' + f + ' = ' + p[f]); return false; }
  return true;
}
function runFor(e, sec, where, recipe) {
  var G = Gfx.create(null, { record: true });
  for (var n = 0; n < Math.round(sec * 60); n++) {
    Behaviour.update(e, 1 / 60);
    var p = Behaviour.getFaceParams(e);
    if (!finiteState(p, where)) return;
    if (n % 10 === 0) {
      try { FaceDraw.draw(G, p, recipe, e.time); Extras.draw(G, e.particles, e.time, { light: true }); G.log.length = 0; }
      catch (err) { ok(false, where + ' draw: ' + err.message); return; }
    }
  }
}
var EVENTS = ['pat', 'boop', 'sayHi', 'greetByTimeOfDay', 'comeHome', 'ownerLooksSad', 'alarmStart', 'imUp',
  'pickedUp', 'fellOver', 'talk', 'ignoredNudge'];
['dog', 'cat'].forEach(function (mode) {
  var recipe = mode === 'cat' ? Recipe.PRESETS.spicy : Recipe.PRESETS.classic;
  EVENTS.forEach(function (ev) {
    var e = Behaviour.createBehaviour({ rnd: Recipe.seeded(9) });
    Behaviour.setMode(e, mode);
    Behaviour[ev](e);
    runFor(e, 2.5, mode + ' event ' + ev, recipe);
  });
  var pe = Behaviour.createBehaviour({ rnd: Recipe.seeded(3) });
  Behaviour.setMode(pe, mode);
  for (var q = 0; q < (mode === 'cat' ? 4 : 6); q++) { Behaviour.pat(pe); runFor(pe, 0.1, mode + ' rapid pats', recipe); }
  ok(pe.mood === (mode === 'cat' ? 'cuteAngry' : 'dizzy'), mode + ': rapid pats -> ' + pe.mood);
  ['win', 'lose', 'draw'].forEach(function (res) {
    var e = Behaviour.createBehaviour({ rnd: Recipe.seeded(4) }); Behaviour.setMode(e, mode);
    Behaviour.rpsReact(e, res); runFor(e, 1, mode + ' rps ' + res, recipe);
  });
  Actions.ACTION_NAMES.concat(['yawn', 'boop']).forEach(function (name) {
    var e = Behaviour.createBehaviour({ rnd: Recipe.seeded(5) });
    Behaviour.setMode(e, mode);
    ok(Actions.playAction(e, name), 'action ' + name + ' starts');
    ok(!!e.actionLabel, name + ' exposes a body label');
    var total = Actions.ACTIONS[name].steps.reduce(function (acc, st) { return acc + (st.hold || 0.5); }, 0);
    runFor(e, total + 0.3, mode + ' action ' + name, recipe);
    ok(e.actionLabel === null, mode + ' action ' + name + ' finished and cleared its label');
  });
  var se = Behaviour.createBehaviour({ rnd: Recipe.seeded(6) }); Behaviour.setMode(se, mode);
  var dur = Music.playSong(se, { singAlong: true });
  runFor(se, dur + 0.5, mode + ' song', recipe);
  ok(!Music.isPlaying(se), mode + ' song ends');
  var be = Behaviour.createBehaviour({ rnd: Recipe.seeded(8), battery: 12 }); Behaviour.setMode(be, mode);
  runFor(be, 1.5, mode + ' weak battery', recipe);
  ok(be.hungerLevel === 'weak', mode + ' low battery -> weak (' + be.hungerLevel + ')');
  Behaviour.setCharging(be, true); runFor(be, 12, mode + ' charging', recipe);
  ok(be.battery >= 99.9 && !be.charging, mode + ' charging fills up and stops');
  var ie = Behaviour.createBehaviour({ rnd: Recipe.seeded(11) }); Behaviour.setMode(ie, mode);
  runFor(ie, SPIKE.moodDrift * 4 + 5, mode + ' ignored', recipe);
  ok(ie.mood === 'sleeping', mode + ' ignored for long -> ' + ie.mood);
  var de = Behaviour.createBehaviour({ rnd: Recipe.seeded(12) }); Behaviour.setMode(de, mode);
  Behaviour.startDemo(de); runFor(de, Moods.MOODS.length * 2.4, mode + ' demo cycle', recipe);
});
console.log('  events, rapid pats, rps, ' + (Actions.ACTION_NAMES.length + 2) + ' actions, song, battery, drift, demo -- both modes');

// ---------------------------------------------------------------------
section('7. share codes, recipes, hit test, particles, RPS icon');
RECIPES.forEach(function (rc) {
  var code = Recipe.toCode(rc.r), back = Recipe.fromCode(code);
  ok(!!back, rc.id + ' code decodes');
  if (back) {
    Object.keys(Recipe.SLOTS).concat(Recipe.COLORS).forEach(function (k) { ok(back[k] === rc.r[k], rc.id + ' round-trip ' + k); });
    Object.keys(Recipe.NUMBERS).forEach(function (k) {
      var rg = Recipe.NUMBERS[k];
      ok(Math.abs(back[k] - rc.r[k]) <= (rg[1] - rg[0]) / 35 / 2 + 1e-9, rc.id + ' round-trip ' + k);
    });
  }
});
ok(Recipe.fromCode('garbage') === null && Recipe.fromCode('SPK1-zz-zz-zz') === null, 'bad codes rejected');
console.log('  example code (Classic Pup): ' + Recipe.toCode(Recipe.PRESETS.classic));
var np = FaceDraw.nosePos(FP.merge({}), Recipe.PRESETS.classic);
ok(FaceDraw.hitTest(FP.merge({}), Recipe.PRESETS.classic, np.x, np.y) === 'nose', 'tap on the nose = boop');
ok(FaceDraw.hitTest(FP.merge({}), Recipe.PRESETS.classic, 240, 40) === 'head', 'tap on the forehead = pat');
var sys = Extras.createSystem();
Object.keys(Extras.TYPES).forEach(function (ty) { Extras.burst(sys, ty, 240, 60, 2, null, rnd); });
var PG = Gfx.create(null, { record: true });
try { for (var f = 0; f < 60; f++) { Extras.update(sys, 1 / 30); Extras.draw(PG, sys, f / 30, { light: f % 2 === 0 }); } ok(true, 'particles'); }
catch (err) { ok(false, 'particles: ' + err.message); }
try { ['rock', 'paper', 'scissors'].forEach(function (c) { Games.drawHandIcon(PG, c, 420, 40, 30, '#FFFFFF'); }); ok(true, 'rps icons'); }
catch (err2) { ok(false, 'rps icon: ' + err2.message); }

console.log('\n' + (fails ? 'FAILED' : 'PASSED') + ': ' + (checks - fails) + '/' + checks + ' checks');
process.exit(fails ? 1 : 0);
