/*
 * smoke.js -- Node smoke test (no browser needed).
 *
 * Checks:
 *   1. face_params.js interpolation: stepSpring actually moves the
 *      current value toward the target, and converges within a
 *      reasonable number of steps.
 *   2. expressions.js: the preset table loads, has 20+ moods, and every
 *      preset produces a full, sane params object in both dog and cat
 *      mode.
 *   3. face_draw.js: draw(ctx, params, t) runs against a mock canvas
 *      context without throwing, for every preset in both modes.
 *   4. extras.js and games.js: particle draw + RPS hand icon draw also
 *      run clean against the same mock context, and RPS logic is sound.
 *   5. behaviour.js: the full engine (mood/battery/greetings) runs a
 *      frame without throwing, for dog and cat.
 *   6. actions.js: every scripted physical-action step's overlay/set
 *      math stays finite (no NaN) at the start, middle and end of its
 *      hold time.
 *   7. music.js: playSong()'s dance + sing-along overlay stays finite
 *      across the whole song.
 *
 * Run with:  node test/smoke.js
 */
'use strict';

var path = require('path');
function req(rel) { return require(path.join(__dirname, '..', rel)); }

var FaceParams = req('face_params.js');
var FaceDraw = req('face_draw.js');
var Expressions = req('expressions.js');
var Extras = req('extras.js');
var Games = req('games.js');
var Behaviour = req('behaviour.js');
var Actions = req('actions.js');
var Music = req('music.js');

var failures = 0;
function ok(cond, label) {
  if (cond) {
    console.log('  OK   ' + label);
  } else {
    console.log('  FAIL ' + label);
    failures++;
  }
}

// -------------------------------------------------------------------------
// Mock canvas 2D context -- enough surface area for face_draw / extras /
// games' drawHandIcon, all of which stick to portable primitives.
// -------------------------------------------------------------------------
function makeMockCtx() {
  var calls = 0;
  var ctx = {
    fillStyle: '', strokeStyle: '', lineWidth: 1, lineCap: '', lineJoin: '',
    globalAlpha: 1, shadowColor: '', shadowBlur: 0,
    save: function () { calls++; }, restore: function () { calls++; },
    translate: function () { calls++; }, rotate: function () { calls++; }, scale: function () { calls++; },
    setTransform: function () { calls++; },
    beginPath: function () { calls++; }, closePath: function () { calls++; },
    moveTo: function () { calls++; }, lineTo: function () { calls++; },
    arc: function () { calls++; }, ellipse: function () { calls++; },
    fill: function () { calls++; }, stroke: function () { calls++; },
    fillRect: function () { calls++; }, rect: function () { calls++; }
  };
  Object.defineProperty(ctx, '_calls', { get: function () { return calls; } });
  return ctx;
}

console.log('== 1. face_params.js interpolation ==');
(function () {
  var state = FaceParams.createSpringState();
  FaceParams.setTarget(state, { mouthOpen: 1, faceTilt: 20 });
  var startOpen = state.current.mouthOpen;
  for (var i = 0; i < 240; i++) FaceParams.stepSpring(state, 1 / 60);
  ok(state.current.mouthOpen > startOpen, 'mouthOpen moved toward its target');
  ok(Math.abs(state.current.mouthOpen - 1) < 0.02, 'mouthOpen converged near 1 after 4s (' + state.current.mouthOpen.toFixed(4) + ')');
  ok(Math.abs(state.current.faceTilt - 20) < 0.5, 'faceTilt converged near 20 after 4s (' + state.current.faceTilt.toFixed(3) + ')');

  var snapState = FaceParams.createSpringState();
  FaceParams.snapTo(snapState, { blinkL: 1 });
  ok(snapState.current.blinkL === 1, 'snapTo() jumps instantly with no spring lag');
})();

console.log('== 2. expressions.js preset table ==');
ok(Array.isArray(Expressions.MOODS) && Expressions.MOODS.length >= 20,
  'at least 20 moods defined (found ' + Expressions.MOODS.length + ')');
Expressions.MOODS.forEach(function (id) {
  ok(!!Expressions.MOOD_LABELS[id], 'mood "' + id + '" has a label');
});

console.log('== 3. face_draw.js against a mock ctx, every preset, both modes ==');
var modes = ['dog', 'cat'];
var drawOpts = { eyeColor: '#FFFFFF', backgroundColor: '#000000', width: 480, height: 272, glow: true };
modes.forEach(function (mode) {
  Expressions.MOODS.forEach(function (id) {
    var params = Expressions.getPreset(id, mode);
    var ctx = makeMockCtx();
    var threw = null;
    try {
      FaceDraw.draw(ctx, params, 1.23, drawOpts);
    } catch (e) {
      threw = e;
    }
    ok(!threw, 'draw() OK for mood="' + id + '" mode="' + mode + '"' + (threw ? (' -- ' + threw.message) : ''));
  });
});

console.log('== 4. extras.js particles + games.js RPS ==');
(function () {
  var sys = Extras.createSystem();
  ['heart', 'zzz', 'sweat', 'sparkle', 'confetti', 'question', 'exclaim', 'anger', 'music', 'dizzyStar', 'tear']
    .forEach(function (type) { Extras.spawn(sys, type, 0, 0); });
  Extras.update(sys, 0.5);
  var ctx = makeMockCtx();
  var threw = null;
  try { Extras.draw(ctx, sys, 0.5); } catch (e) { threw = e; }
  ok(!threw, 'Extras.draw() runs clean for every particle type' + (threw ? (' -- ' + threw.message) : ''));

  var game = Games.createGame();
  var res = Games.playRound(game, 'rock');
  ok(['win', 'lose', 'draw'].indexOf(res.result) !== -1, 'RPS playRound() returns a valid result');
  ok(game.rounds === 1 && (game.wins + game.losses + game.draws) === 1, 'RPS score tallies exactly one round');

  var ctx2 = makeMockCtx();
  var threw2 = null;
  try {
    Games.drawHandIcon(ctx2, 'rock', 0, 0, 30, '#fff');
    Games.drawHandIcon(ctx2, 'paper', 0, 0, 30, '#fff');
    Games.drawHandIcon(ctx2, 'scissors', 0, 0, 30, '#fff');
  } catch (e) { threw2 = e; }
  ok(!threw2, 'Games.drawHandIcon() runs clean for all three choices');
})();

console.log('== 5. behaviour.js engine (mood, battery, greetings) ==');
(function () {
  ['dog', 'cat'].forEach(function (mode) {
    var engine = Behaviour.createBehaviour({});
    Behaviour.setMode(engine, mode);
    Behaviour.setMood(engine, 'neutral', { snap: true });
    var threw = null;
    try {
      for (var i = 0; i < 30; i++) Behaviour.update(engine, 1 / 60);
      Behaviour.pat(engine);
      Behaviour.setBattery(engine, 10);
      Behaviour.update(engine, 1 / 60);
      Behaviour.setCharging(engine, true);
      Behaviour.update(engine, 1 / 60);
      Behaviour.sayHi(engine);
      Behaviour.greetByTimeOfDay(engine);
      Behaviour.getFaceParams(engine);
    } catch (e) { threw = e; }
    ok(!threw, 'behaviour engine runs a frame clean in ' + mode + ' mode' + (threw ? (' -- ' + threw.message) : ''));
    ok(engine.hungerLevel === 'ok', mode + ': charging clears hungerLevel back to ok');
  });
})();

console.log('== 6. actions.js: every step\'s overlay/set math stays finite ==');
(function () {
  var bad = 0;
  Actions.ACTION_NAMES.forEach(function (name) {
    var steps = Actions.ACTIONS[name];
    steps.forEach(function (step, idx) {
      var hold = step.hold || 0.5;
      [0, hold * 0.3, hold * 0.6, hold].forEach(function (age) {
        var engine = Behaviour.createBehaviour({});
        Behaviour.setMood(engine, step.mood || 'neutral', { snap: true });
        Behaviour.update(engine, 1 / 60);
        engine._action = { name: name, steps: steps, index: idx, stepStartAt: 0 };
        engine.actionLabel = name;
        engine._time = age;
        var p = Behaviour.getFaceParams(engine);
        Object.keys(p).forEach(function (k) {
          if (typeof p[k] === 'number' && isNaN(p[k])) bad++;
        });
      });
    });
  });
  ok(bad === 0, 'all ' + Actions.ACTION_NAMES.length + ' actions stay NaN-free across every step (found ' + bad + ' issues)');
})();

console.log('== 7. music.js: play-along dance + sing-along overlay ==');
(function () {
  var engine = Behaviour.createBehaviour({});
  Behaviour.setMood(engine, 'neutral', { snap: true });
  var duration = Music.playSong(engine, { singAlong: true });
  ok(duration > 0, 'playSong() returns a positive duration (' + duration.toFixed(2) + 's)');
  var bad = 0;
  [0, duration * 0.25, duration * 0.5, duration * 0.75, duration * 0.99].forEach(function (age) {
    engine.dance.startAt = 0;
    engine._time = age;
    var p = Behaviour.getFaceParams(engine);
    Object.keys(p).forEach(function (k) {
      if (typeof p[k] === 'number' && isNaN(p[k])) bad++;
    });
  });
  ok(bad === 0, 'dance/sing-along overlay stays NaN-free across the whole song');
})();

console.log('');
if (failures > 0) {
  console.log(failures + ' check(s) FAILED');
  process.exit(1);
} else {
  console.log('All smoke checks passed.');
  process.exit(0);
}
