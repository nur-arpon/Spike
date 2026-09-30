/*
 * brain_link.js -- opt-in link from this simulator to Spike's laptop brain
 * (software/laptop/spike_brain). While connected, THIS PAGE IS THE ROBOT:
 * the brain sends moods, actions, speech (audio + captions + mouth timing),
 * gaze, alarms and games; the page sends back pats, boops, pick-ups, the
 * battery slider, its mood and typed chat.
 *
 * Wire format: software/protocol/PROTOCOL.md (v1). Keep them in step.
 *
 * Off by default. It only connects when the page is opened with
 *   index.html?brain=ws://127.0.0.1:8765   (always 127.0.0.1, not "localhost": a
 *   browser may resolve localhost to ::1, where another program can listen)
 * or when the "Connect brain" button is pressed. With neither, it does
 * nothing at all (no sockets, no timers).
 *
 * Hooks it needs from app.js: BrainLink.init(api) once the page is built,
 * and BrainLink.applyOverlay(params) each frame (mouth movement while
 * speaking). Everything else goes through the public face modules.
 */
(function (root) {
  'use strict';

  var PROTO = 1, FW = '2.0.0';
  var DEFAULT_URL = 'ws://127.0.0.1:8765';
  var CAPS = ['face', 'speaker', 'touch', 'imu', 'battery', 'text'];
  var EVENTS = { sayHi: 1, greetByTimeOfDay: 1, comeHome: 1, ownerLooksSad: 1, pickedUp: 1, fellOver: 1, ignoredNudge: 1 };
  var SOUND_FN = { yip: 'playYip', bark: 'playBark', whine: 'playWhine', sniff: 'playSniff', sigh: 'playSigh',
    snore: 'playSnore', giggle: 'playGiggle', meow: 'playMeow', purr: 'playPurr', hiss: 'playHiss', trill: 'playTrill',
    yawn: 'playYawn', sneeze: 'playSneeze', hiccup: 'playHiccup', growl: 'playStomachGrowl', munch: 'playMunch',
    pop: 'playPop', boop: 'playBoop', patSqueak: 'playPatSqueak' };
  var RPS_COUNT = { 3: 'Rock...', 2: 'Paper...', 1: 'Scissors...' };

  // Comfort actions (PROTOCOL.md 5.2, v1.1). They are not in actions.js, so the
  // link draws them from the face's own springs: gentle, slow, never bouncy.
  var COMFORT = {
    // lean in toward the owner: head dips and tilts, eyes soften, ears relax, a small sigh
    snuggle: function (e) {
      Behaviour.kick(e, { headSY: -0.9, headSX: 0.5, bob: 60 });
      Behaviour.override(e, { tilt: (e.rnd() < 0.5 ? -1 : 1) * 9, earBack: 0.6, blush: 0.6, happy: 0.35 }, 2.6);
      if (root.Sounds && Sounds.playSigh) Sounds.playSigh();
      if (root.Extras) Extras.burst(e.particles, 'heart', 240, 56, 1, null, e.rnd);
    },
    // a slow, contented tail wag: three soft side-to-side sways
    slowWag: function (e) {
      [0, 0.75, 1.5].forEach(function (t, i) {
        Behaviour.after(e, t, function () { Behaviour.kick(e, { tilt: (i % 2 ? -1 : 1) * 70, earL: -60, earR: -60 }); });
      });
      Behaviour.override(e, { happy: 0.3, blush: 0.3 }, 2.4);
    }
  };

  // Body actions (PROTOCOL.md 5.2, v1.4). Also not in actions.js: the real robot walks or
  // offers a paw, but this page has no legs to draw, so a happy face reaction stands in
  // (the owner's rule is that the app only does what the real robot can do; now it can).
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

  var L = {
    app: null, engine: null, orig: {},
    ws: null, url: '', want: false, state: 'off', outId: 0, backoff: 0, retryTimer: null, lastRx: 0,
    fromBrain: false,                  // true while applying a brain command (so wrappers don't echo it)
    ctx: null, playhead: 0, pending: {}, segs: [], sources: [],
    listen: 'idle', lookAt: -10, lastMoodSent: '', lastModeSent: '', lastBattery: null,
    ui: {}
  };

  function $(id) { return document.getElementById(id); }
  function nowS() { return L.ctx ? L.ctx.currentTime : performance.now() / 1000; }

  // ------------------------------------------------------------------ socket
  function send(type, fields) {
    if (!L.ws || L.ws.readyState !== 1) return false;
    var msg = { v: PROTO, type: type, id: ++L.outId, ts: Math.round(performance.now()) };
    for (var k in fields) if (Object.prototype.hasOwnProperty.call(fields, k)) msg[k] = fields[k];
    try { L.ws.send(JSON.stringify(msg)); return true; } catch (e) { return false; }
  }

  function connect(url) {
    L.url = url || L.url || DEFAULT_URL;
    L.want = true;
    try { root.localStorage.setItem('spike.brain.url', L.url); } catch (e) { /* storage blocked */ }
    open();
  }

  function open() {
    if (!L.want || typeof root.WebSocket !== 'function') return;
    clearTimeout(L.retryTimer);
    setState('connecting');
    var ws;
    try { ws = new root.WebSocket(L.url); } catch (e) { retry(); return; }
    L.ws = ws;
    L.outId = 0;
    ws.onopen = function () {
      L.lastRx = Date.now();
      send('hello', { role: 'simulator', device_id: deviceId(), fw: FW, caps: CAPS });
    };
    ws.onmessage = function (ev) {
      L.lastRx = Date.now();
      var msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      if (!msg || typeof msg !== 'object' || msg.v !== PROTO || typeof msg.type !== 'string') return;
      try { handle(msg); } catch (e) { if (root.console) console.warn('brain_link: ' + msg.type + ' failed', e); }
    };
    ws.onclose = function () {
      if (L.ws === ws) L.ws = null;
      stopSpeech(false);
      if (L.want) retry(); else setState('off');
    };
    ws.onerror = function () { /* onclose follows */ };
  }

  function retry() {
    setState('connecting');
    // 0.5, 1, 2, 4, 8, 10 s (+-20 % jitter) -- PROTOCOL.md section 3
    var base = Math.min(10, 0.5 * Math.pow(2, L.backoff++));
    L.retryTimer = setTimeout(open, base * (0.8 + Math.random() * 0.4) * 1000);
  }

  function disconnect() {
    L.want = false;
    clearTimeout(L.retryTimer);
    if (L.ws) { try { L.ws.close(1000, 'bye'); } catch (e) { /* already closed */ } }
    L.ws = null;
    stopSpeech(false);
    setState('off');
  }

  function deviceId() {
    try {
      var id = root.localStorage.getItem('spike.sim.id');
      if (!id) { id = 'sim-' + Math.random().toString(16).slice(2, 8); root.localStorage.setItem('spike.sim.id', id); }
      return id;
    } catch (e) { return 'sim-' + Math.random().toString(16).slice(2, 8); }
  }

  // ------------------------------------------------------------------ brain -> face
  function asBrain(fn) { L.fromBrain = true; try { return fn(); } finally { L.fromBrain = false; } }

  function handle(m) {
    var e = L.engine;
    switch (m.type) {
      case 'hello':
        L.backoff = 0;
        setState('on');
        applyNames(m);
        if (m.mode && m.mode !== e.mode) asBrain(function () { L.app.setMode(m.mode); });
        reportMood(true);
        break;
      case 'ping': send('pong', { re: m.id }); break;
      case 'mood':
        if (root.Moods && Moods.FACE[m.mood]) {
          Behaviour.stopDemo(e);
          asBrain(function () { Behaviour.setMood(e, m.mood); });
        }
        break;
      case 'action':
        if (COMFORT[m.action]) asBrain(function () { COMFORT[m.action](e); });
        else if (BODY[m.action]) asBrain(function () { BODY[m.action](e); });
        else if (root.Actions && Actions.ACTIONS[m.action]) asBrain(function () { Actions.playAction(e, m.action); });
        break;
      case 'event':
        if (EVENTS[m.event] && L.orig[m.event]) asBrain(function () { L.orig[m.event](e); });
        break;
      case 'sound':
        if (SOUND_FN[m.sound] && root.Sounds && Sounds[SOUND_FN[m.sound]]) Sounds[SOUND_FN[m.sound]]();
        break;
      case 'look_at':
        L.lookAt = performance.now() / 1000;
        L.orig.setLook(e, Number(m.x) || 0, Number(m.y) || 0);
        break;
      case 'set_mode':
        if ((m.mode === 'dog' || m.mode === 'cat') && m.mode !== e.mode) asBrain(function () { L.app.setMode(m.mode); });
        break;
      case 'set_recipe': applyRecipe(m); break;
      case 'listening': setListening(m.state); break;
      case 'say': onSay(m); break;
      case 'say_audio': onSayAudio(m); break;
      case 'stop_speaking': stopSpeech(true); break;
      case 'alarm': onAlarm(m); break;
      case 'game': onGame(m); break;
      case 'error': if (root.console) console.warn('brain says: ' + m.code + ' ' + (m.message || '')); break;
      default: break;                    // unknown types are ignored (protocol rule 2)
    }
  }

  function applyNames(m) {
    if (m.names) {
      if (m.names.dog) SPIKE.dogName = String(m.names.dog);
      if (m.names.cat) SPIKE.catName = String(m.names.cat);
    }
    if (m.wake_words) {
      if (Array.isArray(m.wake_words.dog)) SPIKE.dogWakeWords = m.wake_words.dog.map(String);
      if (Array.isArray(m.wake_words.cat)) SPIKE.catWakeWords = m.wake_words.cat.map(String);
    }
    if (L.app.refreshMode) L.app.refreshMode();
    if (root.Studio && Studio.refreshNames) Studio.refreshNames();
    if (L.ui.input) L.ui.input.placeholder = 'Type to ' + (L.engine.mode === 'cat' ? SPIKE.catName : SPIKE.dogName) + '...';
  }

  function applyRecipe(m) {
    if (!root.Studio || !root.Recipe) return;
    var mode = m.mode === 'cat' ? 'cat' : 'dog';
    var r = m.code ? Recipe.fromCode(String(m.code)) : (m.recipe && typeof m.recipe === 'object' ? m.recipe : null);
    if (!r) return;
    Studio.recipes[mode] = Recipe.normalize(r);
    Studio.setMode(Studio.mode);
  }

  function setListening(state) {
    var e = L.engine;
    L.listen = state;
    if (state === 'wake' || state === 'listening') {
      Behaviour.kick(e, { earL: -220, earR: -220, headSY: 0.8 });
      Behaviour.override(e, { earPerk: 1 }, state === 'wake' ? 1.2 : 5);
      Behaviour.markInteraction(e);
    } else if (state === 'thinking') {
      Behaviour.override(e, { lookX: 0.45, lookY: -0.7, earPerk: 0.6 }, 1.6);
    } else if (state === 'idle') {
      var over = e.over || {};
      if (over.earPerk) delete over.earPerk;
    }
    updatePill();
  }

  function onAlarm(m) {
    var e = L.engine;
    asBrain(function () {
      if (m.state === 'ringing') {
        if (!e.alarmActive) Behaviour.alarmStart(e);
        if (typeof m.level === 'number') e.alarmLevel = Math.max(e.alarmLevel, Math.min(3, m.level));
      } else if (e.alarmActive) {
        e.alarmActive = false;
        Behaviour.markInteraction(e);
        Behaviour.setMood(e, m.state === 'snoozed' ? 'sleepy' : 'proud');
      }
    });
  }

  function onGame(m) {
    if (m.game !== 'rps') return;
    var e = L.engine;
    if (m.phase === 'countdown' && RPS_COUNT[m.count]) Behaviour.showCaption(e, RPS_COUNT[m.count], 0.9);
    else if (m.phase === 'shoot') Behaviour.showCaption(e, 'SHOOT!', 1.2);
    else if (m.phase === 'start') Behaviour.setMood(e, 'playful');
    else if (m.phase === 'reveal') {
      if (L.app.showRps && m.robot) L.app.showRps(m.robot);
      asBrain(function () { Behaviour.rpsReact(e, m.result === 'win' || m.result === 'lose' ? m.result : 'draw'); });
      var line = $('rps-line'), who = e.mode === 'cat' ? SPIKE.catName : SPIKE.dogName, sc = m.score || {};
      if (line) line.textContent = 'You: ' + (m.owner || '?') + ' vs ' + who + ': ' + (m.robot || '?') + '  (you ' +
        (sc.owner || 0) + ', ' + who + ' ' + (sc.robot || 0) + ', draws ' + (sc.draws || 0) + ')';
    }
  }

  // ------------------------------------------------------------------ speech
  // A segment is one sentence: header ('say') + audio chunks ('say_audio').
  // Segments play back to back on one timeline (the AudioContext clock, or
  // performance.now() when there is no audio, e.g. muted tests), so the
  // mouth envelope and the captions line up with the sound.
  function audioCtx() {
    if (L.ctx) return L.ctx;
    var AC = root.AudioContext || root.webkitAudioContext;
    if (!AC) return null;
    try { L.ctx = new AC(); } catch (e) { L.ctx = null; }
    return L.ctx;
  }

  function onSay(m) {
    var key = m.utt + '/' + m.seq;
    if (!m.text && m.final && !m.audio) return;          // end marker: nothing to play, nothing to report
    var seg = { utt: m.utt, seq: m.seq, text: String(m.text || ''), mood: m.mood, dur: Math.max(0, (m.duration_ms || 0) / 1000),
      mouth: m.mouth && Array.isArray(m.mouth.values) ? m.mouth : null, audio: m.audio, chunks: [], need: 0 };
    if (m.audio && m.audio.chunks > 0) { seg.need = m.audio.chunks; L.pending[key] = seg; }
    else schedule(seg, null);                              // caption (or caption + mouth) only
  }

  function onSayAudio(m) {
    var key = m.utt + '/' + m.seq, seg = L.pending[key];
    if (!seg) return;
    seg.chunks[m.index] = m.data;
    if (m.last || seg.chunks.filter(Boolean).length >= seg.need) {
      delete L.pending[key];
      schedule(seg, decode(seg));
    }
  }

  function decode(seg) {
    var parts = seg.chunks.map(function (b64) {
      var bin = root.atob(b64 || ''), n = bin.length >> 1, out = new Float32Array(n);
      for (var i = 0; i < n; i++) {
        var v = bin.charCodeAt(2 * i) | (bin.charCodeAt(2 * i + 1) << 8);
        out[i] = (v >= 32768 ? v - 65536 : v) / 32768;
      }
      return out;
    });
    var total = parts.reduce(function (s, p) { return s + p.length; }, 0), pcm = new Float32Array(total), off = 0;
    parts.forEach(function (p) { pcm.set(p, off); off += p.length; });
    return pcm;
  }

  function schedule(seg, pcm) {
    var ctx = pcm ? audioCtx() : L.ctx, rate = seg.audio ? seg.audio.rate : 0;
    if (pcm && rate) seg.dur = pcm.length / rate;
    var t = nowS(), start = Math.max(t + 0.03, L.playhead);
    if (pcm && ctx && !(root.Sounds && Sounds.isMuted && Sounds.isMuted())) {
      if (ctx.state === 'suspended') { ctx.resume(); showTapHint(true); }
      var buf = ctx.createBuffer(1, pcm.length, rate);
      buf.copyToChannel ? buf.copyToChannel(pcm, 0) : buf.getChannelData(0).set(pcm);
      var src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(start);
      L.sources.push(src);
      src.onended = function () { L.sources = L.sources.filter(function (s) { return s !== src; }); };
    }
    seg.start = start;
    seg.end = start + seg.dur;
    L.playhead = seg.end;
    L.segs.push(seg);
    var wait = Math.max(0, (start - t) * 1000);
    seg.t1 = setTimeout(function () { segStarted(seg); }, wait);
    seg.t2 = setTimeout(function () { segFinished(seg, 'finished'); }, wait + seg.dur * 1000);
  }

  function segStarted(seg) {
    var e = L.engine;
    if (seg.mood && root.Moods && Moods.FACE[seg.mood]) asBrain(function () { Behaviour.setMood(e, seg.mood); });
    if (seg.text) Behaviour.showCaption(e, seg.text, seg.dur + 0.8);
    Behaviour.markInteraction(e);
    send('say_state', { utt: seg.utt, seq: seg.seq, state: 'started' });
  }

  function segFinished(seg, state) {
    if (seg.done) return;
    seg.done = true;
    clearTimeout(seg.t1); clearTimeout(seg.t2);
    L.segs = L.segs.filter(function (s) { return s !== seg; });
    send('say_state', { utt: seg.utt, seq: seg.seq, state: state });
  }

  function stopSpeech(report) {
    L.sources.forEach(function (s) { try { s.stop(); } catch (e) { /* already stopped */ } });
    L.sources = [];
    L.pending = {};
    L.segs.slice().forEach(function (seg) {
      if (report) segFinished(seg, 'stopped');
      else { seg.done = true; clearTimeout(seg.t1); clearTimeout(seg.t2); }
    });
    L.segs = [];
    L.playhead = 0;
  }

  // Mouth from the brain's loudness envelope (0..100 at rate_hz), per frame.
  function applyOverlay(p) {
    if (!L.segs.length) return;
    var t = nowS();
    for (var i = 0; i < L.segs.length; i++) {
      var s = L.segs[i];
      if (t < s.start || t > s.end) continue;
      var v = 0;
      if (s.mouth && s.mouth.values.length) {
        var idx = Math.floor((t - s.start) * (s.mouth.rate_hz || 50));
        v = (s.mouth.values[Math.min(idx, s.mouth.values.length - 1)] || 0) / 100;
      } else if (s.text) {
        v = 0.25 + 0.25 * Math.sin((t - s.start) * 18);      // caption-only: gentle babble
      }
      p.open = Math.max(p.open || 0, Math.min(1, v * 0.62));
      p.mouthO = Math.max(p.mouthO || 0, Math.min(1, v * 0.28));
      return;
    }
  }

  // ------------------------------------------------------------------ face -> brain
  function wrap(name, fn) {
    var original = Behaviour[name];
    if (typeof original !== 'function') return;
    L.orig[name] = original;
    Behaviour[name] = function () {
      var r = original.apply(this, arguments);
      if (!L.fromBrain) { try { fn.apply(null, arguments); } catch (e) { /* never break the page */ } }
      return r;
    };
  }

  function installWrappers() {
    wrap('pat', function () { send('touch', { zone: 'head', gesture: 'tap' }); });
    wrap('boop', function () { send('touch', { zone: 'nose', gesture: 'tap' }); });
    wrap('pickedUp', function () { send('imu', { event: 'pickup' }); });
    wrap('fellOver', function () { send('imu', { event: 'fall' }); });
    wrap('imUp', function () { send('alarm_ack', { action: 'stop' }); });
    wrap('setBattery', function () { reportBattery(); });
    wrap('setCharging', function () { reportBattery(true); });
    wrap('setMode', function () { reportMood(true); });
    ['sayHi', 'greetByTimeOfDay', 'comeHome', 'ownerLooksSad', 'ignoredNudge', 'alarmStart', 'rpsReact', 'setMood']
      .forEach(function (n) { if (!L.orig[n]) L.orig[n] = Behaviour[n]; });
    // the camera (brain look_at) wins over the mouse for a moment
    var setLook = Behaviour.setLook;
    L.orig.setLook = setLook;
    Behaviour.setLook = function (e, x, y) {
      if (L.state === 'on' && performance.now() / 1000 - L.lookAt < 1.5) return;
      return setLook(e, x, y);
    };
  }

  function reportBattery(force) {
    var e = L.engine, pct = Math.round(e.battery);
    var key = pct + (e.charging ? 'c' : '');
    if (!force && key === L.lastBattery) return;
    L.lastBattery = key;
    send('battery', { percent: pct, charging: !!e.charging });
  }

  function reportMood(force) {
    var e = L.engine;
    if (!force && e.mood === L.lastMoodSent && e.mode === L.lastModeSent) return;
    if (send('mood_state', { mood: e.mood, mode: e.mode, action: e._action ? e._action.name : null })) {
      L.lastMoodSent = e.mood; L.lastModeSent = e.mode;
    }
  }

  // ------------------------------------------------------------------ UI
  var CSS = '' +
    '.brain-btn{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);background:var(--panel);' +
    'border-radius:999px;padding:6px 13px;font-size:13px;font-weight:600;color:var(--ink-2);cursor:pointer;white-space:nowrap}' +
    '.brain-btn:hover{color:var(--ink)}.brain-btn .dot{width:8px;height:8px;border-radius:50%;background:#9ca3af;flex:none}' +
    '.brain-btn[data-state=connecting] .dot{background:#f59e0b}.brain-btn[data-state=on] .dot{background:#22c55e}' +
    '.brain-chat{display:flex;gap:8px;width:min(480px,100%);margin:0 auto}.brain-chat[hidden]{display:none}' +
    '.brain-chat input{flex:1 1 auto;min-width:0;border:1px solid var(--line);border-radius:999px;padding:8px 14px;' +
    'background:var(--panel)}.brain-chat input:focus{outline:2px solid var(--focus);outline-offset:1px}' +
    '.brain-chat button{flex:none;border:0;border-radius:999px;padding:8px 16px;background:var(--accent);' +
    'color:var(--accent-ink);font-weight:600;cursor:pointer;white-space:nowrap}' +
    '.brain-hint{font-size:12px;color:var(--ink-2);text-align:center}.brain-hint[hidden]{display:none}' +
    '#brain-pill[hidden]{display:none}';   /* .pill sets display, which would beat [hidden] */

  function buildUI() {
    var style = document.createElement('style');
    style.textContent = CSS;
    document.head.appendChild(style);

    var btn = document.createElement('button');
    btn.className = 'brain-btn';
    btn.id = 'brain-btn';
    btn.type = 'button';
    btn.innerHTML = '<span class="dot"></span><span class="lbl">Connect brain</span>';
    btn.addEventListener('click', function () { if (L.want) disconnect(); else connect(L.url || storedUrl()); });
    var bar = document.querySelector('.topbar');
    if (bar) bar.insertBefore(btn, bar.querySelector('.toggle'));

    var pill = document.createElement('span');
    pill.className = 'pill';
    pill.id = 'brain-pill';
    pill.hidden = true;
    pill.innerHTML = '<span class="dot"></span>Brain <b>idle</b>';
    var status = document.querySelector('.status');
    if (status) status.appendChild(pill);

    var form = document.createElement('form');
    form.className = 'brain-chat';
    form.id = 'brain-chat';
    form.hidden = true;
    form.innerHTML = '<input id="brain-input" autocomplete="off" maxlength="300" aria-label="Type a message">' +
      '<button type="submit">Send</button>';
    form.addEventListener('submit', function (ev) {
      ev.preventDefault();
      var text = L.ui.input.value.trim();
      if (!text) return;
      if (send('text', { text: text })) L.ui.input.value = '';
    });
    var hint = document.createElement('div');
    hint.className = 'brain-hint';
    hint.id = 'brain-hint';
    hint.hidden = true;
    hint.textContent = 'Click anywhere so ' + SPIKE.dogName + ' can talk out loud.';
    var stage = $('stage');
    if (stage) {
      var anchor = stage.querySelector('.hint');
      stage.insertBefore(form, anchor);
      stage.insertBefore(hint, anchor);
    }
    L.ui = { btn: btn, pill: pill, form: form, input: $('brain-input'), hint: hint };
    L.ui.input.placeholder = 'Type to ' + SPIKE.dogName + '...';
    root.addEventListener('pointerdown', function () {
      if (L.ctx && L.ctx.state === 'suspended') L.ctx.resume();
      showTapHint(false);
    });
  }

  function showTapHint(on) { if (L.ui.hint) L.ui.hint.hidden = !on; }

  function setState(s) {
    L.state = s;
    if (!L.ui.btn) return;
    L.ui.btn.dataset.state = s;
    L.ui.btn.querySelector('.lbl').textContent = s === 'on' ? 'Brain connected' : s === 'connecting' ? 'Connecting...' : 'Connect brain';
    L.ui.btn.title = s === 'off' ? 'Connect to the laptop brain at ' + (L.url || storedUrl()) : L.url;
    L.ui.btn.setAttribute('aria-pressed', String(s !== 'off'));
    L.ui.form.hidden = s !== 'on';
    L.ui.pill.hidden = s !== 'on';
    updatePill();
  }

  function updatePill() {
    if (!L.ui.pill) return;
    L.ui.pill.querySelector('b').textContent = L.listen;
    L.ui.pill.classList.toggle('live', L.listen !== 'idle');
  }

  function storedUrl() {
    var u;
    try { u = root.localStorage.getItem('spike.brain.url'); } catch (e) { u = null; }
    return (u || DEFAULT_URL).replace('//localhost:', '//127.0.0.1:');   // older saved URLs
  }

  function urlParam() {
    try {
      var q = new root.URLSearchParams(root.location.search).get('brain');
      if (!q) return null;
      return /^wss?:\/\//i.test(q) ? q : (q === '1' || q === 'true' ? DEFAULT_URL : 'ws://' + q);
    } catch (e) { return null; }
  }

  // ------------------------------------------------------------------ init
  function init(app) {
    if (L.app) return;
    L.app = app;
    L.engine = app.engine;
    installWrappers();
    buildUI();
    setState('off');
    setInterval(function () {
      if (L.state !== 'on') return;
      reportMood(false);
      reportBattery(false);
      // PROTOCOL.md 3.4: dead after 3 x heartbeat (5 s) of silence
      if (L.ws && Date.now() - L.lastRx > 15000) { try { L.ws.close(); } catch (e) { /* ignore */ } }
    }, 250);
    var u = urlParam();
    if (u) connect(u);
  }

  root.BrainLink = {
    init: init, applyOverlay: applyOverlay, connect: connect, disconnect: disconnect,
    state: function () { return L.state; }, _internal: L
  };
})(typeof window !== 'undefined' ? window : this);
