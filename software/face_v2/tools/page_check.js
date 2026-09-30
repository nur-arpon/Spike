/*
 * page_check.js -- DEV ONLY. Loads the real index.html in jsdom (no browser),
 * runs every classic script, backs <canvas> with @napi-rs/canvas, drives the
 * UI like a person would, and checks the page glue:
 *   - no script errors on load
 *   - every mood / action / event / studio control exists and works
 *   - button states follow the engine (pressed mood, playing action,
 *     "I'm up!" only during the alarm, song button while playing, etc.)
 *   - clicking the nose boops, clicking the forehead pats
 *   - Face Studio: presets, a slot change, dice, save + load slot, share code
 *   - storage blocked (throws) still works
 * Saves the page's own canvas to out/page_canvas_*.png.
 * Run:  node tools/page_check.js
 */
'use strict';
var path = require('path'), fs = require('fs');
var { JSDOM, VirtualConsole } = require('jsdom');
var napi = require('@napi-rs/canvas');

var ROOT = path.join(__dirname, '..');
var OUT = path.join(__dirname, 'out');
var errors = [], fails = 0, checks = 0;
function ok(c, m) { checks++; if (!c) { fails++; console.log('  FAIL: ' + m); } }

function run(opts) {
  var html = fs.readFileSync(path.join(ROOT, 'index.html'), 'utf8');
  var vc = new VirtualConsole();
  vc.on('jsdomError', function (e) { errors.push(e.message || String(e)); });
  vc.on('error', function (e) { errors.push(String(e)); });
  var rafQueue = [];
  var dom = new JSDOM(html, {
    url: 'file:///' + ROOT.replace(/\\/g, '/') + '/index.html',
    runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: false, virtualConsole: vc,
    beforeParse: function (win) {
      var canvases = new WeakMap();
      // like a browser: resizing the canvas gives a fresh, cleared backing store
      win.HTMLCanvasElement.prototype.getContext = function () {
        var el = this;
        function real() {
          var c = canvases.get(el);
          if (!c || c.width !== el.width || c.height !== el.height) { c = napi.createCanvas(el.width || 1, el.height || 1); canvases.set(el, c); }
          return c.getContext('2d');
        }
        return new Proxy({}, {
          get: function (_, k) { var r = real(), v = r[k]; return typeof v === 'function' ? v.bind(r) : v; },
          set: function (_, k, v) { real()[k] = v; return true; }
        });
      };
      Object.defineProperty(win.HTMLElement.prototype, 'clientWidth', { get: function () { return 1040; } });
      win.HTMLCanvasElement.prototype._napi = function () { return canvases.get(this); };
      win.requestAnimationFrame = function (fn) { rafQueue.push(fn); return rafQueue.length; };
      win.performance.now = (function () { var t = 0; return function () { return (t += 16.7); }; })();
      win.devicePixelRatio = 1;
      if (opts && opts.blockStorage) {
        Object.defineProperty(win, 'localStorage', { get: function () { throw new Error('storage blocked'); } });
      }
    }
  });
  return new Promise(function (resolve) {
    dom.window.addEventListener('load', function () { resolve({ dom: dom, win: dom.window, raf: rafQueue }); });
  });
}

function frames(env, n) {
  for (var i = 0; i < n; i++) {
    var q = env.raf.splice(0, env.raf.length);
    q.forEach(function (fn) { fn(env.win.performance.now()); });
  }
}
function click(win, el) {
  el.dispatchEvent(new win.PointerEvent ? new win.MouseEvent('pointerdown', { bubbles: true }) : null);
  el.click();
}
function savePng(env, name) {
  var c = env.win.document.getElementById('face-canvas')._napi();
  if (c) { fs.writeFileSync(path.join(OUT, name), c.toBuffer('image/png')); console.log('  wrote out/' + name); }
}

(async function main() {
  console.log('== load');
  var env = await run();
  var win = env.win, doc = win.document, $ = function (id) { return doc.getElementById(id); };
  frames(env, 5);
  ok(errors.length === 0, 'no script errors on load: ' + errors.join(' | '));
  ok(!!win.Behaviour && !!win.FaceDraw && !!win.Studio, 'all modules loaded');
  var moodButtons = doc.querySelectorAll('#mood-grid .btn');
  ok(moodButtons.length === win.Moods.MOODS.length, moodButtons.length + ' mood buttons');
  ok(doc.querySelectorAll('#action-grid .btn').length === win.Actions.ACTION_NAMES.length, 'action buttons');
  ok(doc.querySelectorAll('.preset').length === win.Recipe.PRESET_ORDER.length, 'preset thumbnails');
  ok($('mode-dog').textContent === win.SPIKE.dogName && $('mode-cat').textContent === win.SPIKE.catName, 'character names from config');
  savePng(env, 'page_canvas_start.png');

  console.log('== responsive layout (static: jsdom has no layout engine)');
  var cvEl = $('face-canvas');
  ok(cvEl.style.width === '' && cvEl.style.height === '', 'script leaves the canvas size to CSS');
  $('true-size').checked = true; $('true-size').dispatchEvent(new win.Event('change')); frames(env, 2);
  ok($('stage').classList.contains('true-size'), 'true-size mode on');
  $('true-size').checked = false; $('true-size').dispatchEvent(new win.Event('change')); frames(env, 2);
  ok(!$('stage').classList.contains('true-size'), 'true-size mode off');
  var css = fs.readFileSync(path.join(ROOT, 'styles.css'), 'utf8');
  ok(/@media \(max-width: 900px\)[^}]*grid-template-columns: minmax\(0, 1fr\)/.test(css), 'one column under 900 px');
  ok(/#face-canvas \{[^}]*width: 100%[^}]*aspect-ratio: 480 \/ 272/.test(css), 'canvas is fluid and keeps 480:272');
  ok(/\.stage\.true-size \.device-scroll \{[^}]*overflow-x: auto/.test(css), 'true size scrolls in its own box');
  // a fixed width wider than a 360 px window minus gutters (outside the
  // true-size rules) would force a sideways scroll
  var wide = [];
  css.replace(/([^{}]+)\{([^}]*)\}/g, function (all, sel, body) {
    if (/true-size/.test(sel)) return all;
    body.replace(/(?:^|[;\s])(min-width|width)\s*:\s*(\d+)px/g, function (m, prop, n) {
      if (+n > 336) wide.push(sel.trim() + ' ' + prop + ':' + n + 'px');
      return m;
    });
    return all;
  });
  ok(wide.length === 0, 'no fixed widths over 336 px: ' + wide.join(', '));

  console.log('== moods, demo, actions');
  var joyBtn = Array.prototype.find.call(moodButtons, function (b) { return b.textContent === 'Joy'; });
  joyBtn.click(); frames(env, 30);
  ok(joyBtn.getAttribute('aria-pressed') === 'true' && $('st-mood').textContent === 'Joy', 'mood button pressed + status');
  $('demo-btn').click(); frames(env, 3);
  ok($('demo-btn').getAttribute('aria-pressed') === 'true', 'demo on');
  $('demo-btn').click(); frames(env, 3);
  ok($('demo-btn').getAttribute('aria-pressed') === 'false', 'demo off');
  var sneeze = Array.prototype.find.call(doc.querySelectorAll('#action-grid .btn'), function (b) { return b.textContent === 'Sneeze'; });
  sneeze.click(); frames(env, 20);
  ok(sneeze.classList.contains('playing') && $('st-body').textContent === 'sneeze', 'action playing state + body label');
  frames(env, 200);
  ok(!sneeze.classList.contains('playing') && $('st-body').textContent === 'idle', 'action finished state');

  console.log('== life');
  ok($('imup-btn').disabled === true, "I'm up disabled without alarm");
  $('alarm-btn').click(); frames(env, 5);
  ok($('imup-btn').disabled === false && $('alarm-btn').disabled === true, 'alarm running states');
  $('imup-btn').click(); frames(env, 5);
  ok($('imup-btn').disabled === true && $('alarm-btn').disabled === false, 'alarm stopped states');
  $('play-song').click(); frames(env, 5);
  ok($('play-song').disabled === true && $('play-song').textContent === 'Playing...', 'song playing state');
  frames(env, 300);
  ok($('play-song').disabled === false, 'song finished state');
  $('battery').value = '10'; $('battery').dispatchEvent(new win.Event('input')); frames(env, 20);
  ok(/hungry/.test($('st-batt').textContent), 'low battery -> hungry status (' + $('st-batt').textContent + ')');
  savePng(env, 'page_canvas_hungry.png');
  $('charging').checked = true; $('charging').dispatchEvent(new win.Event('change')); frames(env, 800);
  ok($('charging').checked === false && $('battery').value === '100', 'charging fills and unticks');
  doc.querySelector('[data-rps="rock"]').click(); frames(env, 5);
  ok(/You: rock/.test($('rps-line').textContent), 'rps line');
  doc.querySelector('[data-event="comeHome"]').click(); frames(env, 20);
  ok($('bubble').classList.contains('show'), 'caption bubble shows');

  console.log('== touch: nose boop, head pat');
  var cv = $('face-canvas');
  cv.getBoundingClientRect = function () { return { left: 0, top: 0, width: 480, height: 272, right: 480, bottom: 272 }; };
  frames(env, 120);
  cv.dispatchEvent(new win.MouseEvent('pointerdown', { bubbles: true, clientX: 240, clientY: 0.62 * 272 }));
  frames(env, 10);
  ok($('st-body').textContent === 'boop', 'nose click = boop (' + $('st-body').textContent + ')');
  savePng(env, 'page_canvas_boop.png');
  frames(env, 150);
  cv.dispatchEvent(new win.MouseEvent('pointerdown', { bubbles: true, clientX: 240, clientY: 40 }));
  frames(env, 12);
  ok($('st-mood').textContent === 'Happy', 'forehead click = pat -> happy (' + $('st-mood').textContent + ')');
  savePng(env, 'page_canvas_pat.png');

  console.log('== Face Studio');
  $('mode-cat').click(); frames(env, 10);
  ok($('mode-cat').getAttribute('aria-pressed') === 'true' && /Spicy/.test($('st-wake').textContent), 'switch to cat');
  ok(doc.querySelector('.preset[data-preset="spicy"]').getAttribute('aria-pressed') === 'true', 'Spicy preset pressed');
  var earsSel = doc.querySelector('[data-slot="ears"]');
  earsSel.value = 'round'; earsSel.dispatchEvent(new win.Event('change')); frames(env, 5);
  ok(win.Studio.current('cat').ears === 'round' && doc.querySelector('.preset[aria-pressed="true"]') === null, 'slot change applied, no preset pressed');
  doc.querySelector('[data-save="1"]').click();
  ok(doc.querySelector('[data-load="1"]').disabled === false, 'save slot 2 filled');
  doc.querySelector('.preset[data-preset="tuxedo"]').click(); frames(env, 5);
  ok(win.Studio.current('cat').pattern === 'tux', 'preset applied');
  doc.querySelector('[data-load="1"]').click(); frames(env, 5);
  ok(win.Studio.current('cat').ears === 'round' && win.Studio.current('cat').pattern === 'calico', 'slot loaded back');
  $('dice-btn').click(); frames(env, 5);
  var diceCode = win.Recipe.toCode(win.Studio.current('cat'));
  ok($('share-code').value === diceCode, 'share code tracks the face');
  $('reset-btn').click(); frames(env, 5);
  $('share-code').value = diceCode; $('load-code').click(); frames(env, 5);
  ok(win.Recipe.toCode(win.Studio.current('cat')) === diceCode, 'share code import');
  $('share-code').value = 'nonsense'; $('load-code').click();
  ok($('studio-toast').classList.contains('err'), 'bad code shows an error');
  savePng(env, 'page_canvas_studio.png');
  $('mode-dog').click(); frames(env, 5);
  ok(win.Studio.current('dog').name === 'Classic Pup', 'dog keeps its own face');
  ok(errors.length === 0, 'no script errors while using the page: ' + errors.join(' | '));
  env.dom.window.close();

  console.log('== storage blocked');
  errors = [];
  var env2 = await run({ blockStorage: true });
  frames(env2, 5);
  env2.win.document.querySelector('[data-save="0"]').click();
  env2.win.document.getElementById('dice-btn').click();
  frames(env2, 5);
  ok(errors.length === 0, 'page works with storage blocked: ' + errors.join(' | '));
  env2.dom.window.close();

  console.log('\n' + (fails ? 'FAILED' : 'PASSED') + ': ' + (checks - fails) + '/' + checks + ' page checks');
  process.exit(fails ? 1 : 0);
})().catch(function (e) { console.error(e); process.exit(1); });
