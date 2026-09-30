/*
 * brain_link_check.js -- loads the REAL face_v2 page in jsdom (no browser),
 * with ?brain=ws://127.0.0.1:<port>, lets brain_link.js talk to a real
 * Python protocol server (started by tests/test_sim_link.py), acts like a
 * person (pat the face, boop the nose, type a message, move the battery
 * slider, switch to the cat), and prints one JSON summary line of what
 * the face did. The Python side checks both ends.
 *
 * Usage: node brain_link_check.js <port> [seconds]
 * Needs jsdom + @napi-rs/canvas from software/face_v2/tools/node_modules.
 */
'use strict';
var path = require('path'), fs = require('fs');
var FACE = path.resolve(__dirname, '..', '..', '..', '..', 'face_v2');
var NM = path.join(FACE, 'tools', 'node_modules');
var { JSDOM, VirtualConsole } = require(path.join(NM, 'jsdom'));
var napi = require(path.join(NM, '@napi-rs', 'canvas'));

var port = Number(process.argv[2]);
var seconds = Number(process.argv[3] || 9);
var errors = [];
var summary = { errors: errors, states: [], captions: [], maxMouth: 0, moods: [], modeSeen: [] };

var html = fs.readFileSync(path.join(FACE, 'index.html'), 'utf8');
var vc = new VirtualConsole();
vc.on('jsdomError', function (e) { errors.push(String(e.message || e)); });
vc.on('error', function (e) { errors.push(String(e)); });
var raf = [];
var dom = new JSDOM(html, {
  url: 'file:///' + FACE.replace(/\\/g, '/') + '/index.html?brain=ws://127.0.0.1:' + port,
  runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: false, virtualConsole: vc,
  beforeParse: function (win) {
    var canvases = new WeakMap();
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
    win.requestAnimationFrame = function (fn) { raf.push(fn); return raf.length; };
    win.devicePixelRatio = 1;
  }
});
var win = dom.window;

function pump() {
  var q = raf.splice(0, raf.length);
  q.forEach(function (fn) { try { fn(win.performance.now()); } catch (e) { errors.push('frame: ' + e.message); } });
}

win.addEventListener('load', function () {
  var doc = win.document, L = win.BrainLink._internal;
  win.console.warn = function () { errors.push('warn: ' + Array.prototype.join.call(arguments, ' ')); };
  var bubble = doc.getElementById('bubble');
  var lastCaption = '';
  // hook the per-frame overlay to measure the mouth while speech plays
  var apply = win.BrainLink.applyOverlay;
  win.BrainLink.applyOverlay = function (p) {
    apply(p);
    if (L.segs.length && p.open > summary.maxMouth) summary.maxMouth = p.open;
  };
  var frameTimer = setInterval(function () {
    pump();
    var e = L.engine;
    if (summary.moods[summary.moods.length - 1] !== e.mood) summary.moods.push(e.mood);
    if (summary.modeSeen[summary.modeSeen.length - 1] !== e.mode) summary.modeSeen.push(e.mode);
    if (summary.states[summary.states.length - 1] !== L.state) summary.states.push(L.state);
    if (bubble.textContent && bubble.textContent !== lastCaption) { lastCaption = bubble.textContent; summary.captions.push(lastCaption); }
  }, 16);

  function when(cond, fn, timeoutMs) {
    var t0 = Date.now();
    var iv = setInterval(function () {
      if (cond()) { clearInterval(iv); fn(); } else if (Date.now() - t0 > (timeoutMs || 6000)) { clearInterval(iv); fn(); }
    }, 30);
  }

  when(function () { return L.state === 'on'; }, function () {
    summary.connectedButton = doc.getElementById('brain-btn').textContent;
    summary.chatVisible = !doc.getElementById('brain-chat').hidden;
    var canvas = doc.getElementById('face-canvas');
    // 1 s in: pat the head (forehead) -> touch head
    setTimeout(function () {
      canvas.getBoundingClientRect = function () { return { left: 0, top: 0, width: 480, height: 272, right: 480, bottom: 272 }; };
      canvas.dispatchEvent(new win.MouseEvent('pointerdown', { bubbles: true, clientX: 240, clientY: 40 }));
    }, 1000);
    // type to the brain
    setTimeout(function () {
      var input = doc.getElementById('brain-input');
      input.value = 'hello from the simulator';
      doc.getElementById('brain-chat').dispatchEvent(new win.Event('submit', { bubbles: true, cancelable: true }));
      summary.inputClearedAfterSend = input.value === '';
    }, 1500);
    // battery slider to 20 %
    setTimeout(function () {
      var b = doc.getElementById('battery');
      b.value = '20';
      b.dispatchEvent(new win.Event('input', { bubbles: true }));
    }, 2000);
    // "Picked up" event button -> imu pickup
    setTimeout(function () {
      var btn = doc.querySelector('[data-event="pickedUp"]');
      if (btn) btn.click();
    }, 2500);
  });

  setTimeout(function () {
    clearInterval(frameTimer);
    var e = L.engine;
    summary.finalMood = e.mood;
    summary.finalMode = e.mode;
    summary.dogName = win.SPIKE.dogName;
    summary.catName = win.SPIKE.catName;
    summary.modeButtonDog = doc.getElementById('mode-dog').textContent;
    summary.rpsLine = doc.getElementById('rps-line').textContent;
    summary.alarmActive = e.alarmActive;
    summary.pill = doc.getElementById('brain-pill').textContent;
    process.stdout.write(JSON.stringify(summary) + '\n');
    try { win.BrainLink.disconnect(); } catch (err) { /* ignore */ }
    setTimeout(function () { process.exit(0); }, 100);
  }, seconds * 1000);
});
