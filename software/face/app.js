/*
 * app.js -- page glue. Wires the DOM controls to Behaviour/Games/Sounds
 * and runs the requestAnimationFrame render loop. Browser-only (uses
 * window/document directly), so it is NOT loaded by the Node smoke test.
 */
(function () {
  'use strict';

  var canvas = document.getElementById('face-canvas');
  var ctx = canvas.getContext('2d');
  var wrap = document.getElementById('canvas-wrap');
  var captionEl = document.getElementById('caption-bubble');

  var W = SPIKE.screenWidth, H = SPIKE.screenHeight;
  var CENTER_X = W / 2, CENTER_Y = H / 2;

  var engine = Behaviour.createBehaviour({
    onCaption: function (text) {
      captionEl.textContent = text;
      captionEl.classList.add('visible');
    }
  });
  Behaviour.setMood(engine, 'neutral', { snap: true });
  Sounds.setMuted(SPIKE.startMuted);

  var state = {
    eyeColor: SPIKE.eyeColor,
    glow: true,
    trueSize: false,
    audioStarted: false,
    rps: { showUntil: 0, choice: 'rock' }
  };

  var startTime = performanceNow();

  function performanceNow() {
    return (typeof performance !== 'undefined' ? performance.now() : Date.now()) / 1000;
  }

  // -----------------------------------------------------------------------
  // Canvas backing-store sizing: keep a crisp 1:1 (or Nx) pixel mapping
  // instead of letting the browser blur-scale a 480x272 buffer.
  // -----------------------------------------------------------------------
  function layoutCanvas() {
    var dpr = window.devicePixelRatio || 1;
    var scale;
    if (state.trueSize) {
      scale = 1;
    } else {
      var available = Math.min(wrap.parentElement.clientWidth, 720);
      scale = Math.max(1, Math.min(2.2, available / W));
    }
    var cssW = Math.round(W * scale);
    var cssH = Math.round(H * scale);
    canvas.style.width = cssW + 'px';
    canvas.style.height = cssH + 'px';
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    canvas._renderScale = (cssW / W) * dpr;
  }

  window.addEventListener('resize', layoutCanvas);
  layoutCanvas();

  // -----------------------------------------------------------------------
  // Mood buttons (built from the preset table so the list can't drift out
  // of sync with expressions.js)
  // -----------------------------------------------------------------------
  var moodGrid = document.getElementById('mood-grid');
  Expressions.MOODS.forEach(function (moodId) {
    var b = document.createElement('button');
    b.textContent = Expressions.MOOD_LABELS[moodId];
    b.addEventListener('click', function () {
      Behaviour.stopDemo(engine);
      Behaviour.setMood(engine, moodId);
    });
    moodGrid.appendChild(b);
  });

  document.getElementById('demo-btn').addEventListener('click', function () {
    if (engine.demoActive) { Behaviour.stopDemo(engine); this.textContent = 'Demo: cycle all moods'; }
    else { Behaviour.startDemo(engine); this.textContent = 'Stop demo'; }
  });

  // -----------------------------------------------------------------------
  // Physical action buttons (built from actions.js so the list can't drift
  // out of sync either). Clicking one plays the whole scripted sequence.
  // -----------------------------------------------------------------------
  var actionGrid = document.getElementById('action-grid');
  Actions.ACTION_NAMES.forEach(function (name) {
    var b = document.createElement('button');
    b.textContent = Actions.ACTION_LABELS[name] || name;
    b.addEventListener('click', function () {
      ensureAudio();
      Behaviour.stopDemo(engine);
      Actions.playAction(engine, name);
    });
    actionGrid.appendChild(b);
  });

  // -----------------------------------------------------------------------
  // Mode toggle (dog / cat) -- labels pull wake words straight from config.
  // -----------------------------------------------------------------------
  var dogBtn = document.getElementById('mode-dog-btn');
  var catBtn = document.getElementById('mode-cat-btn');
  function refreshModeUI() {
    dogBtn.textContent = SPIKE.dogName;
    catBtn.textContent = SPIKE.catName;
    dogBtn.setAttribute('aria-pressed', String(engine.mode === 'dog'));
    catBtn.setAttribute('aria-pressed', String(engine.mode === 'cat'));
    var words = engine.mode === 'cat' ? SPIKE.catWakeWords : SPIKE.dogWakeWords;
    document.getElementById('wake-words-line').textContent = 'Wake words: ' + words.join(', ');
  }
  dogBtn.addEventListener('click', function () { Behaviour.setMode(engine, 'dog'); refreshModeUI(); });
  catBtn.addEventListener('click', function () { Behaviour.setMode(engine, 'cat'); refreshModeUI(); });
  refreshModeUI();

  // -----------------------------------------------------------------------
  // Event buttons
  // -----------------------------------------------------------------------
  var EVENT_FNS = {
    comeHome: Behaviour.comeHome,
    ownerSad: Behaviour.ownerLooksSad,
    alarmStart: Behaviour.alarmStart,
    imUp: Behaviour.imUp,
    pickedUp: Behaviour.pickedUp,
    fellOver: Behaviour.fellOver,
    talk: Behaviour.talk,
    ignoredNudge: Behaviour.ignoredNudge
  };
  Array.prototype.forEach.call(document.querySelectorAll('[data-event]'), function (btn) {
    btn.addEventListener('click', function () {
      ensureAudio();
      var fn = EVENT_FNS[btn.getAttribute('data-event')];
      if (fn) fn(engine);
    });
  });

  // -----------------------------------------------------------------------
  // Rock / Paper / Scissors
  // -----------------------------------------------------------------------
  var rpsLine = document.getElementById('rps-line');
  function playRPS(choice) {
    ensureAudio();
    var outcome = Games.playRound(engine.score, choice);
    Behaviour.rpsReact(engine, outcome.result);
    state.rps.choice = outcome.computerChoice;
    state.rps.showUntil = performanceNow() + 1.4;
    var verb = outcome.result === 'win' ? 'You win!' : (outcome.result === 'lose' ? 'You lose!' : 'Draw!');
    rpsLine.textContent = 'You: ' + outcome.playerChoice + ' vs ' + SPIKE.dogName + ': ' + outcome.computerChoice +
      ' -- ' + verb + '  (W ' + engine.score.wins + ' / L ' + engine.score.losses + ' / D ' + engine.score.draws + ')';
  }
  Array.prototype.forEach.call(document.querySelectorAll('[data-rps]'), function (btn) {
    btn.addEventListener('click', function () { playRPS(btn.getAttribute('data-rps')); });
  });
  window.addEventListener('keydown', function (e) {
    if (e.key === 'r' || e.key === 'R') playRPS('rock');
    else if (e.key === 'p' || e.key === 'P') playRPS('paper');
    else if (e.key === 's' || e.key === 'S') playRPS('scissors');
  });

  // -----------------------------------------------------------------------
  // Stage controls: true size, mute, glow, eye colour
  // -----------------------------------------------------------------------
  document.getElementById('true-size-toggle').addEventListener('change', function (e) {
    state.trueSize = e.target.checked;
    layoutCanvas();
  });
  document.getElementById('mute-toggle').addEventListener('change', function (e) {
    Sounds.setMuted(e.target.checked);
  });
  document.getElementById('glow-toggle').addEventListener('change', function (e) {
    state.glow = e.target.checked;
  });
  document.getElementById('eye-color').addEventListener('input', function (e) {
    state.eyeColor = e.target.value;
  });

  // -----------------------------------------------------------------------
  // Say hi / greetings
  // -----------------------------------------------------------------------
  document.getElementById('say-hi-btn').addEventListener('click', function () {
    ensureAudio();
    Behaviour.stopDemo(engine);
    Behaviour.sayHi(engine);
  });
  document.getElementById('greet-time-btn').addEventListener('click', function () {
    ensureAudio();
    Behaviour.stopDemo(engine);
    Behaviour.greetByTimeOfDay(engine);
  });

  // -----------------------------------------------------------------------
  // Battery / hunger
  // -----------------------------------------------------------------------
  var batterySlider = document.getElementById('battery-slider');
  var batteryReadout = document.getElementById('battery-readout');
  var chargingToggle = document.getElementById('charging-toggle');
  batterySlider.addEventListener('input', function (e) {
    Behaviour.setBattery(engine, Number(e.target.value));
  });
  chargingToggle.addEventListener('change', function (e) {
    ensureAudio();
    Behaviour.setCharging(engine, e.target.checked);
  });

  // -----------------------------------------------------------------------
  // Music: play a song, dance, optionally sing along (lip-sync)
  // -----------------------------------------------------------------------
  var singAlongToggle = document.getElementById('sing-along-toggle');
  document.getElementById('play-song-btn').addEventListener('click', function () {
    ensureAudio();
    Behaviour.stopDemo(engine);
    Music.playSong(engine, { singAlong: singAlongToggle.checked });
  });

  function ensureAudio() {
    if (!state.audioStarted) { Sounds.initAudio(); state.audioStarted = true; }
  }
  window.addEventListener('pointerdown', ensureAudio, { once: true });

  // -----------------------------------------------------------------------
  // Canvas interaction: tap top half = pat on the head. Eyes follow the
  // pointer anywhere on the page (stand-in for camera face tracking).
  // -----------------------------------------------------------------------
  canvas.addEventListener('pointerdown', function (e) {
    ensureAudio();
    var rect = canvas.getBoundingClientRect();
    var yFrac = (e.clientY - rect.top) / rect.height;
    if (yFrac < 0.5) Behaviour.pat(engine);
  });

  window.addEventListener('pointermove', function (e) {
    var rect = canvas.getBoundingClientRect();
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var radius = Math.max(window.innerWidth, window.innerHeight) * 0.6;
    var nx = (e.clientX - cx) / radius;
    var ny = (e.clientY - cy) / radius;
    Behaviour.setLook(engine, nx, ny);
  });

  // -----------------------------------------------------------------------
  // Render loop
  // -----------------------------------------------------------------------
  var lastT = performanceNow();
  function frame() {
    var now = performanceNow();
    var dt = Math.min(0.05, now - lastT);
    lastT = now;
    var elapsed = now - startTime;

    Behaviour.update(engine, dt);

    ctx.save();
    var rs = canvas._renderScale || 1;
    ctx.setTransform(rs, 0, 0, rs, 0, 0);

    var params = Behaviour.getFaceParams(engine);
    FaceDraw.draw(ctx, params, elapsed, {
      eyeColor: state.eyeColor,
      backgroundColor: SPIKE.backgroundColor,
      width: W, height: H,
      glow: state.glow
    });

    ctx.save();
    ctx.translate(CENTER_X, CENTER_Y);
    Extras.draw(ctx, engine.particles, elapsed);
    if (now < state.rps.showUntil) {
      Games.drawHandIcon(ctx, state.rps.choice, W / 2 - 60, -H / 2 + 30, 34, state.eyeColor);
    }
    ctx.restore();

    ctx.restore();

    if (engine.caption && captionEl.classList.contains('visible') === false) {
      captionEl.classList.add('visible');
    } else if (!engine.caption) {
      captionEl.classList.remove('visible');
    }

    // alarm's "I'm up" button only makes sense while the alarm is ringing
    document.getElementById('im-up-btn').style.opacity = engine.alarmActive ? '1' : '0.5';

    // battery readout follows the engine (charging auto-fills it, hunger
    // drains it in a real deployment) rather than only the slider
    var batteryPct = Math.round(engine.battery);
    batteryReadout.textContent = batteryPct + '%' + (engine.charging ? ' (charging)' : '');
    if (document.activeElement !== batterySlider) batterySlider.value = batteryPct;
    if (!engine.charging && chargingToggle.checked) chargingToggle.checked = false;

    // physical-action readout -- this is the label future leg/wheel
    // firmware would key off of; shown here just so it's visible.
    var labelEl = document.getElementById('action-label-line');
    labelEl.textContent = engine.actionLabel ? ('Action: ' + engine.actionLabel) : '';

    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
