/*
 * render_sheet.js -- DEV ONLY. Renders every mood (both modes) and a
 * few action sequences to PNG contact sheets in tools/out/, using the
 * exact same pure face_draw.js / behaviour.js / actions.js code the
 * browser uses, so what we look at here is what the page will show.
 *
 * Not loaded by index.html -- this whole `tools/` folder (including its
 * node_modules) is a dev-only helper.
 *
 * Run:  node tools/render_sheet.js
 */
'use strict';
var path = require('path');
var fs = require('fs');
var { createCanvas } = require('@napi-rs/canvas');

function req(rel) { return require(path.join(__dirname, '..', rel)); }
var FaceDraw = req('face_draw.js');
var Expressions = req('expressions.js');
var Behaviour = req('behaviour.js');
var Actions = req('actions.js');

var OUT_DIR = path.join(__dirname, 'out');
if (!fs.existsSync(OUT_DIR)) fs.mkdirSync(OUT_DIR);

var W = 480, H = 272;
var CELL_W = 210, CELL_H = 175, LABEL_H = 22;
var COLS = 6;

var DRAW_OPTS = { eyeColor: '#FFFFFF', backgroundColor: '#000000', width: W, height: H, glow: true };

function drawCell(ctx, col, row, params, label, opts) {
  var x0 = col * CELL_W, y0 = row * CELL_H;
  ctx.save();
  ctx.translate(x0, y0);

  // cell background + border so faces don't visually run together
  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, CELL_W, CELL_H);
  ctx.strokeStyle = '#2a2a2a';
  ctx.lineWidth = 1;
  ctx.strokeRect(0.5, 0.5, CELL_W - 1, CELL_H - 1);

  var faceAreaH = CELL_H - LABEL_H;
  var scale = Math.min(CELL_W / W, faceAreaH / H) * 0.94;
  ctx.save();
  ctx.translate((CELL_W - W * scale) / 2, (faceAreaH - H * scale) / 2);
  ctx.scale(scale, scale);
  FaceDraw.draw(ctx, params, (opts && opts.t != null) ? opts.t : 0.6, DRAW_OPTS);
  ctx.restore();

  ctx.fillStyle = '#cccccc';
  ctx.font = '11px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText(label, CELL_W / 2, CELL_H - 7);
  ctx.restore();
}

function renderMoodSheet(mode, filename) {
  var moods = Expressions.MOODS;
  var rows = Math.ceil(moods.length / COLS);
  var canvas = createCanvas(COLS * CELL_W, rows * CELL_H);
  var ctx = canvas.getContext('2d');
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  moods.forEach(function (moodId, i) {
    var params = Expressions.getPreset(moodId, mode);
    var col = i % COLS, row = Math.floor(i / COLS);
    drawCell(ctx, col, row, params, moodId, { t: 0.6 });
  });

  var outPath = path.join(OUT_DIR, filename);
  fs.writeFileSync(outPath, canvas.toBuffer('image/png'));
  console.log('wrote', outPath, canvas.width + 'x' + canvas.height);
}

// -----------------------------------------------------------------------
// Action sequences: sample N frames spread proportionally across every
// step's hold time, using the real engine + actions runtime.
// -----------------------------------------------------------------------
function sampleActionFrames(actionName, frameCount) {
  var steps = Actions.ACTIONS[actionName];
  var totalHold = steps.reduce(function (s, st) { return s + (st.hold || 0.5); }, 0);
  var frames = [];
  for (var i = 0; i < frameCount; i++) {
    var globalAge = (i / (frameCount - 1)) * totalHold * 0.999;
    var acc = 0, stepIndex = 0, localAge = 0;
    for (var s = 0; s < steps.length; s++) {
      var hold = steps[s].hold || 0.5;
      if (globalAge < acc + hold) { stepIndex = s; localAge = globalAge - acc; break; }
      acc += hold;
      stepIndex = s;
      localAge = hold;
    }
    var engine = Behaviour.createBehaviour({});
    Behaviour.setMood(engine, steps[0].mood || 'neutral', { snap: true });
    // re-apply every step's mood up to stepIndex so the spring target is
    // the right one, then let it settle so cells don't show a mid-spring
    // blend between two unrelated moods
    for (var m = 0; m <= stepIndex; m++) {
      if (steps[m].mood) Behaviour.setMood(engine, steps[m].mood, { snap: m < stepIndex });
    }
    for (var k = 0; k < 90; k++) Behaviour.update(engine, 1 / 60);
    engine._action = { name: actionName, steps: steps, index: stepIndex, stepStartAt: 0 };
    engine.actionLabel = actionName;
    engine._time = localAge;
    frames.push({ params: Behaviour.getFaceParams(engine), label: actionName + ' @' + globalAge.toFixed(2) + 's' });
  }
  return frames;
}

function renderActionSheet(actionNames, framesEach, filename) {
  var cells = [];
  actionNames.forEach(function (name) {
    sampleActionFrames(name, framesEach).forEach(function (f) { cells.push(f); });
  });
  var rows = Math.ceil(cells.length / COLS);
  var canvas = createCanvas(COLS * CELL_W, rows * CELL_H);
  var ctx = canvas.getContext('2d');
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  cells.forEach(function (cell, i) {
    var col = i % COLS, row = Math.floor(i / COLS);
    drawCell(ctx, col, row, cell.params, cell.label, { t: 0.6 });
  });
  var outPath = path.join(OUT_DIR, filename);
  fs.writeFileSync(outPath, canvas.toBuffer('image/png'));
  console.log('wrote', outPath, canvas.width + 'x' + canvas.height);
}

renderMoodSheet('dog', 'moods_dog.png');
renderMoodSheet('cat', 'moods_cat.png');
renderActionSheet(['tripBump', 'wakeUp', 'tailWagDance'], 5, 'actions_sample.png');
