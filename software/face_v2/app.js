/*
 * app.js -- page glue: builds the control panel from the data tables (so
 * buttons can never drift out of sync with moods.js / actions.js), keeps
 * every button state honest each frame, maps clicks on the face to pats
 * and boops, and runs the render loop. Browser-only.
 */
(function () {
  'use strict';
  var W = SPIKE.screenWidth, H = SPIKE.screenHeight;
  var canvas = document.getElementById('face-canvas');
  var ctx = canvas.getContext('2d');
  var G = Gfx.create(ctx);
  var bubble = document.getElementById('bubble');
  function $(id) { return document.getElementById(id); }

  var engine = Behaviour.createBehaviour({
    onCaption: function (text) { bubble.textContent = text; bubble.classList.add('show'); }
  });
  Behaviour.setMood(engine, 'neutral', { snap: true });
  Sounds.setMuted(SPIKE.startMuted);
  if (Sounds.setVolume) Sounds.setVolume(SPIKE.masterVolume);

  var ui = { trueSize: false, audio: false, rps: { until: 0, choice: 'rock' }, lastMood: '', lastAction: '' };

  function ensureAudio() { if (!ui.audio) { Sounds.initAudio(); ui.audio = true; } }
  window.addEventListener('pointerdown', ensureAudio, { once: true });

  // ------------------------------------------------------------- canvas size
  // CSS decides how big the screen is (full width of its box, 480:272, or
  // exactly 480 x 272 in true-size mode). Here we only match the canvas's
  // backing store to that size, so it stays crisp and never forces the page
  // wider than the window. (v2.0 measured the stage to size the canvas, but
  // the stage was sized BY the canvas, so it never shrank.)
  var stageEl = document.getElementById('stage');
  ui.sx = 1; ui.sy = 1;
  function layout() {
    stageEl.classList.toggle('true-size', ui.trueSize);
    var dpr = window.devicePixelRatio || 1;
    var cssW = canvas.getBoundingClientRect().width;
    if (!(cssW > 10)) cssW = W;                       // not laid out yet (or a test DOM)
    var bw = Math.max(1, Math.round(cssW * dpr)), bh = Math.max(1, Math.round(cssW * H / W * dpr));
    if (canvas.width !== bw || canvas.height !== bh) { canvas.width = bw; canvas.height = bh; }
    ui.sx = bw / W; ui.sy = bh / H;
  }
  window.addEventListener('resize', layout);
  if (window.ResizeObserver) { try { new ResizeObserver(function () { layout(); }).observe(canvas); } catch (err) { /* resize event still works */ } }
  layout();

  // ------------------------------------------------------------- Studio
  Studio.init({ onChange: function () { /* drawn from Studio.current() every frame */ } });

  // ------------------------------------------------------------- tabs
  var tabs = document.querySelectorAll('[role="tab"]');
  Array.prototype.forEach.call(tabs, function (t) {
    t.addEventListener('click', function () {
      Array.prototype.forEach.call(tabs, function (x) { x.setAttribute('aria-selected', String(x === t)); });
      Array.prototype.forEach.call(document.querySelectorAll('.tabpane'), function (p) { p.hidden = p.dataset.pane !== t.dataset.tab; });
    });
  });

  // ------------------------------------------------------------- characters
  function refreshMode() {
    $('mode-dog').textContent = SPIKE.dogName;
    $('mode-cat').textContent = SPIKE.catName;
    $('mode-dog').setAttribute('aria-pressed', String(engine.mode === 'dog'));
    $('mode-cat').setAttribute('aria-pressed', String(engine.mode === 'cat'));
    $('brand-name').textContent = engine.mode === 'cat' ? SPIKE.catName : SPIKE.dogName;
    $('st-wake').textContent = (engine.mode === 'cat' ? SPIKE.catWakeWords : SPIKE.dogWakeWords).join(', ');
    Studio.setMode(engine.mode);
  }
  function setMode(m) { ensureAudio(); Behaviour.setMode(engine, m); refreshMode(); if (m === 'cat') Sounds.playMeow(); else Sounds.playYip(); }
  $('mode-dog').addEventListener('click', function () { if (engine.mode !== 'dog') setMode('dog'); });
  $('mode-cat').addEventListener('click', function () { if (engine.mode !== 'cat') setMode('cat'); });
  refreshMode();

  // ------------------------------------------------------------- moods
  var moodBtns = {};
  $('mood-count').textContent = Moods.MOODS.length + ' moods';
  Moods.MOODS.forEach(function (id) {
    var b = document.createElement('button');
    b.className = 'btn'; b.textContent = Moods.LABELS[id]; b.setAttribute('aria-pressed', 'false');
    b.addEventListener('click', function () {
      Behaviour.stopDemo(engine);
      if (window.Actions) Actions.stopAction(engine);
      Behaviour.markInteraction(engine);
      Behaviour.setMood(engine, id, { force: true });
    });
    moodBtns[id] = b;
    $('mood-grid').appendChild(b);
  });
  $('demo-btn').addEventListener('click', function () {
    if (engine.demoActive) Behaviour.stopDemo(engine); else { Actions.stopAction(engine); Behaviour.startDemo(engine); }
  });

  // ------------------------------------------------------------- actions
  var actionBtns = {};
  Actions.ACTION_NAMES.forEach(function (name) {
    var b = document.createElement('button');
    b.className = 'btn'; b.textContent = Actions.ACTION_LABELS[name];
    b.addEventListener('click', function () { ensureAudio(); Behaviour.stopDemo(engine); Actions.playAction(engine, name); });
    actionBtns[name] = b;
    $('action-grid').appendChild(b);
  });

  // ------------------------------------------------------------- life
  Array.prototype.forEach.call(document.querySelectorAll('[data-event]'), function (b) {
    b.addEventListener('click', function () {
      ensureAudio(); Behaviour.stopDemo(engine);
      var fn = Behaviour[b.dataset.event];
      if (fn) fn(engine);
    });
  });
  $('say-hi').addEventListener('click', function () { ensureAudio(); Behaviour.stopDemo(engine); Behaviour.sayHi(engine); });
  $('greet-time').addEventListener('click', function () { ensureAudio(); Behaviour.stopDemo(engine); Behaviour.greetByTimeOfDay(engine); });
  $('battery').addEventListener('input', function (ev) { Behaviour.setBattery(engine, Number(ev.target.value)); });
  $('charging').addEventListener('change', function (ev) { ensureAudio(); Behaviour.setCharging(engine, ev.target.checked); });
  $('play-song').addEventListener('click', function () {
    if (Music.isPlaying(engine)) return;
    ensureAudio(); Behaviour.stopDemo(engine);
    Music.playSong(engine, { singAlong: $('sing-along').checked });
  });
  $('mute').addEventListener('change', function (ev) { Sounds.setMuted(ev.target.checked); });
  $('true-size').addEventListener('change', function (ev) { ui.trueSize = ev.target.checked; layout(); });

  function playRPS(choice) {
    ensureAudio();
    var r = Games.playRound(engine.score, choice);
    Behaviour.rpsReact(engine, r.result);
    ui.rps.choice = r.computerChoice;
    ui.rps.until = engine.time + 1.6;
    var who = engine.mode === 'cat' ? SPIKE.catName : SPIKE.dogName;
    var verdict = r.result === 'win' ? 'You win!' : (r.result === 'lose' ? who + ' wins!' : 'Draw!');
    $('rps-line').textContent = 'You: ' + r.playerChoice + ' vs ' + who + ': ' + r.computerChoice + ' -- ' + verdict +
      '  (you ' + engine.score.wins + ', ' + who + ' ' + engine.score.losses + ', draws ' + engine.score.draws + ')';
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-rps]'), function (b) {
    b.addEventListener('click', function () { playRPS(b.dataset.rps); });
  });
  window.addEventListener('keydown', function (ev) {
    var tag = (document.activeElement && document.activeElement.tagName) || '';
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var k = ev.key.toLowerCase();
    if (k === 'r') playRPS('rock'); else if (k === 'p') playRPS('paper'); else if (k === 's') playRPS('scissors');
  });

  // ------------------------------------------------------------- the face
  var lastParams = Behaviour.getFaceParams(engine);
  canvas.addEventListener('pointerdown', function (ev) {
    ensureAudio(); Behaviour.stopDemo(engine);
    var rect = canvas.getBoundingClientRect();
    var x = (ev.clientX - rect.left) / rect.width * W, y = (ev.clientY - rect.top) / rect.height * H;
    if (FaceDraw.hitTest(lastParams, Studio.current(engine.mode), x, y) === 'nose') Behaviour.boop(engine);
    else Behaviour.pat(engine);
  });
  // the eyes follow the pointer (stand-in for the camera finding your face)
  window.addEventListener('pointermove', function (ev) {
    var rect = canvas.getBoundingClientRect();
    var cx = rect.left + rect.width / 2, cy = rect.top + rect.height * 0.45;
    var rad = Math.max(window.innerWidth, window.innerHeight) * 0.45;
    Behaviour.setLook(engine, (ev.clientX - cx) / rad, (ev.clientY - cy) / rad);
  });

  // ------------------------------------------------------------- loop
  var last = performance.now();
  function frame(now) {
    var dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    Behaviour.update(engine, dt);
    var recipe = Studio.current(engine.mode);
    var p = Behaviour.getFaceParams(engine);
    lastParams = p;
    if (window.BrainLink) BrainLink.applyOverlay(p);   // mouth while the laptop brain talks

    ctx.setTransform(ui.sx, 0, 0, ui.sy, 0, 0);
    FaceDraw.draw(G, p, recipe, engine.time);
    var back = recipe.frame === 'head' ? recipe.bg : recipe.fur;
    Extras.draw(G, engine.particles, engine.time, { light: Gfx.luminance(back) > 0.45 });
    if (engine.time < ui.rps.until) Games.drawHandIcon(G, ui.rps.choice, W - 44, 42, 34, '#FFFFFF', '#2E2320');

    syncUI();
    requestAnimationFrame(frame);
  }

  function syncUI() {
    if (!engine.caption) bubble.classList.remove('show');
    if (ui.lastMood !== engine.mood) {
      if (moodBtns[ui.lastMood]) moodBtns[ui.lastMood].setAttribute('aria-pressed', 'false');
      if (moodBtns[engine.mood]) moodBtns[engine.mood].setAttribute('aria-pressed', 'true');
      $('st-mood').textContent = Moods.LABELS[engine.mood];
      ui.lastMood = engine.mood;
    }
    var an = engine._action ? engine._action.name : '';
    if (ui.lastAction !== an) {
      if (actionBtns[ui.lastAction]) actionBtns[ui.lastAction].classList.remove('playing');
      if (actionBtns[an]) actionBtns[an].classList.add('playing');
      $('st-body').textContent = engine.actionLabel || 'idle';
      $('st-body-dot').style.background = engine.actionLabel ? '#22c55e' : '';
      $('action-meta').textContent = engine.actionLabel ? 'Body label sent to the legs: "' + engine.actionLabel + '"' : 'The body label appears here while an action plays.';
      ui.lastAction = an;
    }
    var demo = $('demo-btn');
    demo.setAttribute('aria-pressed', String(engine.demoActive));
    demo.textContent = engine.demoActive ? 'Stop the mood tour' : 'Play all moods';
    $('imup-btn').disabled = !engine.alarmActive;
    $('alarm-btn').disabled = engine.alarmActive;
    var song = $('play-song'), playing = Music.isPlaying(engine);
    song.disabled = playing; song.textContent = playing ? 'Playing...' : 'Play a song';
    var pct = Math.round(engine.battery);
    $('battery-readout').textContent = pct + '%';
    $('st-batt').textContent = pct + '%' + (engine.charging ? ' charging' : (engine.hungerLevel !== 'ok' ? ' hungry' : ''));
    if (document.activeElement !== $('battery')) $('battery').value = pct;
    if ($('charging').checked !== engine.charging) $('charging').checked = engine.charging;
  }
  requestAnimationFrame(frame);

  // Optional link to Spike's laptop brain (brain_link.js). It stays off
  // unless the page has ?brain=ws://... or its "Connect brain" button is used.
  if (window.BrainLink) BrainLink.init({ engine: engine, setMode: setMode, refreshMode: refreshMode,
    showRps: function (choice) { ui.rps.choice = choice; ui.rps.until = engine.time + 1.6; } });
})();
