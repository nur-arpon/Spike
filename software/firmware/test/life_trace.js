/*
 * life_trace.js -- behaviour-engine equivalence test, JS side.
 *
 * Runs face_v2's REAL behaviour engine (behaviour.js + actions.js, seeded mulberry32) through a
 * scripted 90-second life (pats, boops, moods, actions, looks, events, cat mode, low battery,
 * comfort actions, listening and alarm reactions), sampling the drawn face state 10 times a second.
 * Writes test/out/life_script.txt (the inputs) and test/out/life_js.txt (the trace). The C++ engine
 * (pc/face_pc.exe life) replays the same script; compare with `node test/life_trace.js compare`.
 */
'use strict';
var path = require('path'), fs = require('fs');
var FACE = path.join(__dirname, '..', '..', 'face_v2');
function req(f) { return require(path.join(FACE, f)); }
var FP = req('params.js');
var Recipe = req('recipe.js');
var Moods = req('moods.js');
req('config.js'); req('gfx.js'); req('extras.js'); req('sounds.js'); req('captions.js'); req('games.js');
var Behaviour = req('behaviour.js');
var Actions = req('actions.js');

var OUT = path.join(__dirname, 'out');
fs.mkdirSync(OUT, { recursive: true });

// time (s) -> command. Commands mirror what the robot's own inputs and the brain do.
var SCRIPT = [
  [0.5, 'look 0.3 -0.2'], [1.0, 'pat'], [1.5, 'look 0.35 -0.1'], [2.2, 'boop'], [4.0, 'mood joy'],
  [5.5, 'action sneeze'], [8.0, 'look -0.6 0.4'], [8.4, 'look -0.5 0.3'], [9.0, 'action tailWagDance'],
  [12.0, 'event comeHome'], [15.0, 'mood sad'], [16.0, 'comfort snuggle'], [18.0, 'comfort slowWag'],
  [20.0, 'listening listening'], [22.0, 'listening thinking'], [24.0, 'listening idle'],
  [25.0, 'action rollOver'], [28.0, 'mode cat'], [28.5, 'pat'], [28.9, 'pat'], [29.3, 'pat'], [29.7, 'pat'],
  [31.0, 'action headTilt'], [34.0, 'mode dog'], [35.0, 'battery 25'], [44.0, 'battery 80'],
  [45.0, 'event fellOver'], [48.0, 'alarm ringing 1'], [53.0, 'alarm stopped 0'], [54.0, 'event ownerLooksSad'],
  [61.0, 'action zoomies'], [64.0, 'event sayHi'], [66.0, 'mood sleepy'], [75.0, 'action wakeUp'], [80.0, 'event pickedUp']
];
var DURATION = 90, DT = 1 / 60, EVERY = 6;

function comfort(e, name) {  // brain_link.js COMFORT (same code)
  if (name === 'snuggle') {
    Behaviour.kick(e, { headSY: -0.9, headSX: 0.5, bob: 60 });
    Behaviour.override(e, { tilt: (e.rnd() < 0.5 ? -1 : 1) * 9, earBack: 0.6, blush: 0.6, happy: 0.35 }, 2.6);
    req('extras.js').burst(e.particles, 'heart', 240, 56, 1, null, e.rnd);
  } else if (name === 'slowWag') {
    [0, 0.75, 1.5].forEach(function (t, i) {
      Behaviour.after(e, t, function () { Behaviour.kick(e, { tilt: (i % 2 ? -1 : 1) * 70, earL: -60, earR: -60 }); });
    });
    Behaviour.override(e, { happy: 0.3, blush: 0.3 }, 2.4);
  }
}
function listening(e, state) {  // brain_link.js setListening
  if (state === 'wake' || state === 'listening') {
    Behaviour.kick(e, { earL: -220, earR: -220, headSY: 0.8 });
    Behaviour.override(e, { earPerk: 1 }, state === 'wake' ? 1.2 : 5);
    Behaviour.markInteraction(e);
  } else if (state === 'thinking') {
    Behaviour.override(e, { lookX: 0.45, lookY: -0.7, earPerk: 0.6 }, 1.6);
  } else if (state === 'idle') {
    if (e.over.earPerk) delete e.over.earPerk;
  }
}
function alarm(e, state, level) {  // brain_link.js onAlarm
  if (state === 'ringing') {
    if (!e.alarmActive) Behaviour.alarmStart(e);
    e.alarmLevel = Math.max(e.alarmLevel, Math.min(3, level));
  } else if (e.alarmActive) {
    e.alarmActive = false;
    Behaviour.markInteraction(e);
    Behaviour.setMood(e, state === 'snoozed' ? 'sleepy' : 'proud');
  }
}

function apply(e, cmd) {
  var a = cmd.split(' ');
  switch (a[0]) {
    case 'look': Behaviour.setLook(e, +a[1], +a[2]); break;
    case 'pat': Behaviour.pat(e); break;
    case 'boop': Behaviour.boop(e); break;
    case 'mood': Behaviour.setMood(e, a[1]); break;
    case 'action': Actions.playAction(e, a[1]); break;
    case 'event': Behaviour[a[1]](e); break;
    case 'mode': Behaviour.setMode(e, a[1]); break;
    case 'battery': Behaviour.setBattery(e, +a[1]); break;
    case 'comfort': comfort(e, a[1]); break;
    case 'listening': listening(e, a[1]); break;
    case 'alarm': alarm(e, a[1], +a[2]); break;
    default: throw new Error('bad command ' + cmd);
  }
}

function run() {
  var e = Behaviour.createBehaviour({ rnd: Recipe.seeded(7) });
  var lines = [], si = 0, n = Math.round(DURATION / DT);
  for (var i = 1; i <= n; i++) {
    while (si < SCRIPT.length && SCRIPT[si][0] <= e.time + 1e-9) apply(e, SCRIPT[si++][1]);
    Behaviour.update(e, DT);
    if (i % EVERY === 0) {
      var p = Behaviour.getFaceParams(e);
      lines.push([e.time.toFixed(4), Moods.MOODS.indexOf(e.mood), e.particles.list.length, p.icon || '-']
        .concat(FP.FIELDS.map(function (f) { return +p[f].toFixed(5); })).join(' '));
    }
  }
  fs.writeFileSync(path.join(OUT, 'life_script.txt'), SCRIPT.map(function (s) { return s[0] + ' ' + s[1]; }).join('\n') + '\n');
  fs.writeFileSync(path.join(OUT, 'life_js.txt'), lines.join('\n') + '\n');
  console.log('life_trace: JS trace ' + lines.length + ' samples');
}

function compare() {
  var a = fs.readFileSync(path.join(OUT, 'life_js.txt'), 'utf8').trim().split('\n');
  var b = fs.readFileSync(path.join(OUT, 'life_cpp.txt'), 'utf8').trim().split('\n');
  if (a.length !== b.length) console.log('sample count differs: JS ' + a.length + ' C++ ' + b.length);
  var n = Math.min(a.length, b.length), moodDiff = 0, firstMood = -1, worst = {}, partDiff = 0, iconDiff = 0;
  // Tolerances: fields are floats in C++ (doubles in JS); angles in degrees, px, and 0..1 levels.
  for (var i = 0; i < n; i++) {
    var x = a[i].split(' '), y = b[i].split(' ');
    if (x[1] !== y[1]) { moodDiff++; if (firstMood < 0) firstMood = i; }
    if (x[2] !== y[2]) partDiff++;
    if (x[3] !== y[3]) iconDiff++;
    FP.FIELDS.forEach(function (f, k) {
      var d = Math.abs(+x[4 + k] - +y[4 + k]);
      if (!worst[f] || d > worst[f].d) worst[f] = { d: d, t: x[0] };
    });
  }
  var bad = FP.FIELDS.filter(function (f) { var r = FP.RANGES[f]; return worst[f].d > 0.01 * (r[1] - r[0]) + 1e-3; });
  var rep = ['behaviour trace: JS behaviour.js vs C++ spike_life, ' + n + ' samples over ' + DURATION + ' s',
    'mood differs in ' + moodDiff + ' samples' + (firstMood >= 0 ? ' (first at t=' + a[firstMood].split(' ')[0] + ')' : ''),
    'particle count differs in ' + partDiff + ' samples, icon differs in ' + iconDiff,
    'fields over 1 % of their range: ' + (bad.length ? bad.map(function (f) { return f + ' ' + worst[f].d.toFixed(4) + ' @' + worst[f].t; }).join(', ') : 'none'),
    'largest field differences: ' + Object.keys(worst).sort(function (p, q) { return worst[q].d - worst[p].d; }).slice(0, 6)
      .map(function (f) { return f + ' ' + worst[f].d.toFixed(5); }).join(', '),
    'VERDICT: ' + (moodDiff === 0 && partDiff === 0 && iconDiff === 0 && bad.length === 0 ? 'PASS' : 'FAIL')];
  fs.writeFileSync(path.join(OUT, 'life_report.txt'), rep.join('\n') + '\n');
  console.log(rep.join('\n'));
  process.exitCode = rep[rep.length - 1].indexOf('PASS') > 0 ? 0 : 1;
}

if (process.argv[2] === 'compare') compare(); else run();
