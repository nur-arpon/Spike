/*
 * face_host.js -- the Spike app's host for the face_v2 engine.
 *
 * The engine files (config.js ... music.js) are unchanged copies of
 * software/face_v2. This file replaces face_v2's page glue (app.js, studio.js,
 * brain_link.js) with a bridge to Flutter:
 *
 *   Flutter -> face : window.SpikeFace.<method>(...) via runJavaScript
 *   face -> Flutter : SpikeBridge.postMessage(JSON) (a JavaScriptChannel)
 *
 * Protocol messages the brain mirrors to the app (mood, action, event, sound,
 * look_at, set_mode, set_recipe, listening, say, stop_speaking, alarm, game)
 * are passed straight to SpikeFace.handle(msg), so the phone's face moves the
 * same way the robot's does. The phone never plays the brain's speech audio.
 */
(function (root) {
  'use strict';
  var W = SPIKE.screenWidth, H = SPIKE.screenHeight;
  var canvas = document.getElementById('face');
  var ctx = canvas.getContext('2d');
  var G = Gfx.create(ctx);

  function post(obj) {
    try { if (root.SpikeBridge && SpikeBridge.postMessage) SpikeBridge.postMessage(JSON.stringify(obj)); }
    catch (e) { /* Flutter side gone: ignore */ }
  }

  var H$ = {
    engine: null, recipes: { dog: null, cat: null }, sound: true, audioReady: false,
    sx: 1, sy: 1, lastParams: null, segs: [], lookAt: -10, listen: 'idle',
    lastMood: '', lastAction: '', interactive: true, paused: false
  };

  function copy(r) { return JSON.parse(JSON.stringify(r)); }
  function defaultFor(mode) {
    return copy(Recipe.PRESETS[mode === 'cat' ? SPIKE.catPreset : SPIKE.dogPreset] || Recipe.PRESETS.classic);
  }
  H$.recipes.dog = defaultFor('dog');
  H$.recipes.cat = defaultFor('cat');

  var engine = Behaviour.createBehaviour({
    onCaption: function (text) { post({ ev: 'caption', text: String(text) }); }
  });
  H$.engine = engine;
  Behaviour.setMood(engine, 'neutral', { snap: true });
  Sounds.setMuted(false);
  if (Sounds.setVolume) Sounds.setVolume(SPIKE.masterVolume);

  function ensureAudio() {
    if (H$.audioReady || !H$.sound) return;
    try { Sounds.initAudio(); H$.audioReady = true; } catch (e) { /* no WebAudio */ }
  }

  // ------------------------------------------------------------- layout
  function layout() {
    var dpr = root.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    var cssW = rect.width > 10 ? rect.width : W;
    var bw = Math.max(1, Math.round(cssW * dpr)), bh = Math.max(1, Math.round(cssW * H / W * dpr));
    if (canvas.width !== bw || canvas.height !== bh) { canvas.width = bw; canvas.height = bh; }
    H$.sx = bw / W; H$.sy = bh / H;
  }
  root.addEventListener('resize', layout);
  layout();

  function backColor(recipe) { return recipe.frame === 'head' ? recipe.bg : recipe.fur; }
  function paintBody() { document.body.style.background = backColor(H$.recipes[engine.mode]); }

  // ------------------------------------------------------------- touch
  var down = null;
  function toFace(ev) {
    var rect = canvas.getBoundingClientRect();
    return { x: (ev.clientX - rect.left) / rect.width * W, y: (ev.clientY - rect.top) / rect.height * H, rect: rect };
  }
  root.addEventListener('pointerdown', function (ev) {
    if (!H$.interactive) return;
    ensureAudio();
    down = { x: ev.clientX, y: ev.clientY, t: performance.now(), moved: false };
  });
  root.addEventListener('pointermove', function (ev) {
    if (!H$.interactive || !down) return;
    if (Math.abs(ev.clientX - down.x) + Math.abs(ev.clientY - down.y) > 14) down.moved = true;
    var rect = canvas.getBoundingClientRect();
    var cx = rect.left + rect.width / 2, cy = rect.top + rect.height * 0.45;
    var rad = Math.max(rect.width, rect.height) * 0.6;
    Behaviour.setLook(engine, (ev.clientX - cx) / rad, (ev.clientY - cy) / rad);
  });
  root.addEventListener('pointerup', function (ev) {
    if (!H$.interactive || !down) return;
    var d = down; down = null;
    var f = toFace(ev);
    if (d.moved) {                                   // a stroke across the face = a pat
      Behaviour.pat(engine);
      post({ ev: 'pat', gesture: 'pat' });
      return;
    }
    if (H$.lastParams && FaceDraw.hitTest(H$.lastParams, H$.recipes[engine.mode], f.x, f.y) === 'nose') {
      Behaviour.boop(engine);
      post({ ev: 'boop' });
    } else {
      Behaviour.pat(engine);
      post({ ev: 'pat', gesture: 'tap' });
    }
  });
  root.addEventListener('pointercancel', function () { down = null; });

  // ------------------------------------------------------------- comfort actions (protocol v1.1)
  // Same drawing as face_v2/brain_link.js, which owns them for the simulator.
  var COMFORT = {
    snuggle: function (e) {
      Behaviour.kick(e, { headSY: -0.9, headSX: 0.5, bob: 60 });
      Behaviour.override(e, { tilt: (e.rnd() < 0.5 ? -1 : 1) * 9, earBack: 0.6, blush: 0.6, happy: 0.35 }, 2.6);
      if (Sounds.playSigh) Sounds.playSigh();
      Extras.burst(e.particles, 'heart', 240, 56, 1, null, e.rnd);
    },
    slowWag: function (e) {
      [0, 0.75, 1.5].forEach(function (t, i) {
        Behaviour.after(e, t, function () { Behaviour.kick(e, { tilt: (i % 2 ? -1 : 1) * 70, earL: -60, earR: -60 }); });
      });
      Behaviour.override(e, { happy: 0.3, blush: 0.3 }, 2.4);
    }
  };

  // Body actions (protocol v1.4). Same drawing as face_v2/brain_link.js: the real robot
  // walks or offers a paw, but this page has no legs, so the phone-only Spike (no robot
  // connected) reacts with a happy face instead - the owner's rule is that the app only
  // does what the real robot can do, and now walk/paw are real.
  var BODY = {
    walk: function (e) {
      [0, 0.28, 0.56, 0.84].forEach(function (t, i) {
        Behaviour.after(e, t, function () { Behaviour.kick(e, { bob: 90, tilt: (i % 2 ? -1 : 1) * 14 }); });
      });
      Behaviour.override(e, { happy: 0.4 }, 1.3);
    },
    paw: function (e) {
      Behaviour.kick(e, { headSY: -0.6, headSX: 0.4, eyeSY: 0.5 });
      Behaviour.override(e, { tilt: (e.rnd() < 0.5 ? -1 : 1) * 6, happy: 0.45, blush: 0.2 }, 1.6);
    }
  };
  var EVENTS = { sayHi: 1, greetByTimeOfDay: 1, comeHome: 1, ownerLooksSad: 1, pickedUp: 1, fellOver: 1, ignoredNudge: 1 };
  var SOUND_FN = { yip: 'playYip', bark: 'playBark', whine: 'playWhine', sniff: 'playSniff', sigh: 'playSigh',
    snore: 'playSnore', giggle: 'playGiggle', meow: 'playMeow', purr: 'playPurr', hiss: 'playHiss', trill: 'playTrill',
    yawn: 'playYawn', sneeze: 'playSneeze', hiccup: 'playHiccup', growl: 'playStomachGrowl', munch: 'playMunch',
    pop: 'playPop', boop: 'playBoop', patSqueak: 'playPatSqueak' };

  function playAction(name) {
    if (COMFORT[name]) { COMFORT[name](engine); return true; }
    if (BODY[name]) { BODY[name](engine); return true; }
    if (Actions.ACTIONS[name]) { Actions.playAction(engine, name); return true; }
    return false;
  }

  function setMode(m) {
    m = m === 'cat' ? 'cat' : 'dog';
    if (engine.mode !== m) Behaviour.setMode(engine, m);
    paintBody();
  }

  // ------------------------------------------------------------- speech mouth (captions are native)
  function onSay(m) {
    if (!m.text && m.final && !m.audio) return;                 // end marker
    var now = performance.now() / 1000;
    var last = H$.segs.length ? H$.segs[H$.segs.length - 1].end : now;
    var start = Math.max(now, last), dur = Math.max(0.3, (m.duration_ms || 0) / 1000);
    H$.segs.push({ start: start, end: start + dur, text: String(m.text || ''),
      mouth: m.mouth && Array.isArray(m.mouth.values) ? m.mouth : null, mood: m.mood, moodDone: false });
  }
  function applyMouth(p) {
    if (!H$.segs.length) return;
    var t = performance.now() / 1000;
    H$.segs = H$.segs.filter(function (s) { return s.end > t; });
    for (var i = 0; i < H$.segs.length; i++) {
      var s = H$.segs[i];
      if (t < s.start) continue;
      if (s.mood && !s.moodDone && Moods.FACE[s.mood]) { s.moodDone = true; Behaviour.setMood(engine, s.mood); }
      var v;
      if (s.mouth && s.mouth.values.length) {
        var idx = Math.floor((t - s.start) * (s.mouth.rate_hz || 50));
        v = (s.mouth.values[Math.min(idx, s.mouth.values.length - 1)] || 0) / 100;
      } else v = 0.25 + 0.25 * Math.sin((t - s.start) * 18);
      p.open = Math.max(p.open || 0, Math.min(1, v * 0.62));
      p.mouthO = Math.max(p.mouthO || 0, Math.min(1, v * 0.28));
      return;
    }
  }

  function setListening(state) {
    H$.listen = state;
    if (state === 'wake' || state === 'listening') {
      Behaviour.kick(engine, { earL: -220, earR: -220, headSY: 0.8 });
      Behaviour.override(engine, { earPerk: 1 }, state === 'wake' ? 1.2 : 5);
      Behaviour.markInteraction(engine);
    } else if (state === 'thinking') {
      Behaviour.override(engine, { lookX: 0.45, lookY: -0.7, earPerk: 0.6 }, 1.6);
    } else if (state === 'idle' && engine.over && engine.over.earPerk) {
      delete engine.over.earPerk;
    }
  }

  var RPS_COUNT = { 3: 'Rock...', 2: 'Paper...', 1: 'Scissors...' };

  // A protocol message from the brain (already decoded by Flutter).
  function handle(m) {
    if (!m || typeof m !== 'object') return;
    switch (m.type) {
      case 'hello':
        if (m.names) { if (m.names.dog) SPIKE.dogName = String(m.names.dog); if (m.names.cat) SPIKE.catName = String(m.names.cat); }
        if (m.mode) setMode(m.mode);
        break;
      case 'mood': if (Moods.FACE[m.mood]) Behaviour.setMood(engine, m.mood); break;
      case 'action': playAction(m.action); break;
      case 'event': if (EVENTS[m.event] && Behaviour[m.event]) Behaviour[m.event](engine); break;
      case 'sound': if (H$.sound && SOUND_FN[m.sound] && Sounds[SOUND_FN[m.sound]]) Sounds[SOUND_FN[m.sound]](); break;
      case 'look_at':
        H$.lookAt = performance.now() / 1000;
        Behaviour.setLook(engine, Number(m.x) || 0, Number(m.y) || 0);
        break;
      case 'set_mode': setMode(m.mode); break;
      case 'set_recipe': {
        var r = m.code ? Recipe.fromCode(String(m.code)) : (m.recipe && typeof m.recipe === 'object' ? m.recipe : null);
        if (r) { H$.recipes[m.mode === 'cat' ? 'cat' : 'dog'] = Recipe.normalize(r); paintBody(); }
        break;
      }
      case 'listening': setListening(m.state); break;
      case 'say': onSay(m); break;
      case 'stop_speaking': H$.segs = []; break;
      case 'alarm':
        if (m.state === 'ringing') { if (!engine.alarmActive) Behaviour.alarmStart(engine); }
        else if (engine.alarmActive) {
          engine.alarmActive = false;
          Behaviour.markInteraction(engine);
          Behaviour.setMood(engine, m.state === 'snoozed' ? 'sleepy' : 'proud');
        }
        break;
      case 'game':
        if (m.game !== 'rps') break;
        if (m.phase === 'countdown' && RPS_COUNT[m.count]) Behaviour.showCaption(engine, RPS_COUNT[m.count], 0.9);
        else if (m.phase === 'shoot') Behaviour.showCaption(engine, 'SHOOT!', 1.2);
        else if (m.phase === 'start') Behaviour.setMood(engine, 'playful');
        else if (m.phase === 'reveal') Behaviour.rpsReact(engine, m.result === 'win' || m.result === 'lose' ? m.result : 'draw');
        break;
      default: break;
    }
  }

  // ------------------------------------------------------------- studio helpers
  function thumbData(recipe, mode, mood, w) {
    w = w || 240;
    var h = Math.round(w * H / W);
    var c = document.createElement('canvas');
    c.width = w; c.height = h;
    var cx = c.getContext('2d');
    cx.setTransform(w / W, 0, 0, w / W, 0, 0);
    FaceDraw.draw(Gfx.create(cx), Moods.getTarget(mood || 'neutral', mode), Recipe.normalize(recipe), 0.6);
    return c.toDataURL('image/png');
  }

  function catalog() {
    var presets = Recipe.PRESET_ORDER.map(function (id) {
      var r = Recipe.PRESETS[id], kind = Recipe.PRESET_KIND[id] === 'cat' ? 'cat' : 'dog';
      return { id: id, name: id === 'spicy' ? SPIKE.catName : r.name, kind: kind, recipe: r, code: Recipe.toCode(r) };
    });
    return {
      slots: Recipe.SLOTS, slotLabels: Recipe.SLOT_LABELS, optionLabels: Recipe.OPTION_LABELS,
      colors: Recipe.COLORS, colorLabels: Recipe.COLOR_LABELS,
      numbers: Recipe.NUMBERS, numberLabels: Recipe.NUMBER_LABELS,
      presets: presets,
      moods: Moods.MOODS.map(function (id) { return { id: id, label: Moods.LABELS[id] }; }),
      actions: Actions.ACTION_NAMES.map(function (id) { return { id: id, label: Actions.ACTION_LABELS[id] }; }),
      defaults: { dog: defaultFor('dog'), cat: defaultFor('cat') }
    };
  }

  // Every call from Flutter that wants an answer goes through call(); the
  // answer comes back as {ev:'result', id, ok, value}.
  var METHODS = {
    catalog: catalog,
    thumbs: function (a) {
      return (a.items || []).map(function (it) { return thumbData(it.recipe, it.mode || 'dog', it.mood, a.width); });
    },
    random: function () { return Recipe.randomRecipe(); },
    toCode: function (a) { return Recipe.toCode(Recipe.normalize(a.recipe)); },
    fromCode: function (a) { var r = Recipe.fromCode(String(a.code || '')); return r ? Recipe.normalize(r) : null; },
    normalize: function (a) { return Recipe.normalize(a.recipe); },
    state: function () {
      return { mood: engine.mood, mode: engine.mode, action: engine._action ? engine._action.name : null };
    }
  };

  var api = {
    handle: handle,
    call: function (id, method, args) {
      var out;
      try { out = { ev: 'result', id: id, ok: true, value: METHODS[method](args || {}) }; }
      catch (e) { out = { ev: 'result', id: id, ok: false, value: String(e && e.message || e) }; }
      post(out);
    },
    setMode: setMode,
    setRecipe: function (recipe, mode) {
      H$.recipes[mode === 'cat' ? 'cat' : 'dog'] = Recipe.normalize(recipe);
      paintBody();
    },
    setMood: function (id) { if (Moods.FACE[id]) { Behaviour.markInteraction(engine); Behaviour.setMood(engine, id, { force: true }); } },
    playAction: function (name) { ensureAudio(); return playAction(name); },
    event: function (name) { ensureAudio(); if (Behaviour[name]) Behaviour[name](engine); },
    pat: function () { ensureAudio(); Behaviour.pat(engine); },
    boop: function () { ensureAudio(); Behaviour.boop(engine); },
    look: function (x, y) { Behaviour.setLook(engine, x, y); },
    setSound: function (on) { H$.sound = !!on; Sounds.setMuted(!on); if (on) ensureAudio(); },
    setInteractive: function (on) { H$.interactive = !!on; },
    setPaused: function (on) { H$.paused = !!on; if (!on) { last = performance.now(); requestAnimationFrame(frame); } },
    setNames: function (dog, cat) { if (dog) SPIKE.dogName = String(dog); if (cat) SPIKE.catName = String(cat); },
    song: function () { ensureAudio(); if (!Music.isPlaying(engine)) Music.playSong(engine, { singAlong: true }); },
    battery: function (pct, charging) { Behaviour.setBattery(engine, Number(pct)); Behaviour.setCharging(engine, !!charging); }
  };
  root.SpikeFace = api;

  // ------------------------------------------------------------- loop
  var last = performance.now();
  function frame(now) {
    if (H$.paused) return;
    var dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    Behaviour.update(engine, dt);
    var recipe = H$.recipes[engine.mode];
    var p = Behaviour.getFaceParams(engine);
    applyMouth(p);
    H$.lastParams = p;
    ctx.setTransform(H$.sx, 0, 0, H$.sy, 0, 0);
    FaceDraw.draw(G, p, recipe, engine.time);
    Extras.draw(G, engine.particles, engine.time, { light: Gfx.luminance(backColor(recipe)) > 0.45 });
    var an = engine._action ? engine._action.name : '';
    if (H$.lastMood !== engine.mood || H$.lastAction !== an) {
      H$.lastMood = engine.mood; H$.lastAction = an;
      post({ ev: 'state', mood: engine.mood, moodLabel: Moods.LABELS[engine.mood] || engine.mood,
        action: an || null, mode: engine.mode });
    }
    requestAnimationFrame(frame);
  }
  paintBody();
  requestAnimationFrame(frame);
  post({ ev: 'ready' });
})(window);
