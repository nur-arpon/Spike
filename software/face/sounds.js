/*
 * sounds.js -- synthesized puppy (and kitty) sounds via WebAudio.
 *
 * No audio files anywhere -- every sound is oscillators/noise + envelopes,
 * built at runtime. The AudioContext is created lazily on the FIRST call
 * into this module that happens after a user gesture (app.js calls
 * Sounds.initAudio() from the page's first click, per browser autoplay
 * rules). In Node (the smoke test) `AudioContext` does not exist, so every
 * public function checks getCtx() for null and silently no-ops instead of
 * throwing -- this file is safe to require() even with no audio backend.
 *
 * This file is NOT meant to be ported to the ESP32 as-is (the board will
 * likely use a small onboard buzzer/DAC + a simpler tone library) but the
 * envelope shapes and timings documented here are the reference design.
 */
(function (root) {
  'use strict';

  var ctx = null;
  var masterGain = null;
  var muted = false;
  var volume = 0.6;

  function hasWebAudio() {
    return typeof window !== 'undefined' &&
      (typeof window.AudioContext === 'function' || typeof window.webkitAudioContext === 'function');
  }

  function getCtx() {
    if (!hasWebAudio()) return null;
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
      masterGain = ctx.createGain();
      masterGain.gain.value = volume;
      masterGain.connect(ctx.destination);
    }
    return ctx;
  }

  // Call from a real user gesture (click/touch) to satisfy autoplay policy.
  function initAudio() {
    var c = getCtx();
    if (c && c.state === 'suspended') c.resume();
    return !!c;
  }

  function setMuted(v) { muted = !!v; }
  function isMuted() { return muted; }
  function setVolume(v) { volume = Math.max(0, Math.min(1, v)); if (masterGain) masterGain.gain.value = volume; }

  // -----------------------------------------------------------------------
  // Low-level building blocks
  // -----------------------------------------------------------------------

  // A single oscillator with a frequency ramp and an amplitude envelope.
  // freqFrom/freqTo in Hz, over `duration` seconds, with a short attack and
  // release so nothing clicks.
  function tone(opts) {
    var c = getCtx();
    if (!c || muted) return;
    var t0 = c.currentTime + (opts.delay || 0);
    var osc = c.createOscillator();
    osc.type = opts.type || 'sine';
    osc.frequency.setValueAtTime(opts.freqFrom, t0);
    osc.frequency.exponentialRampToValueAtTime(Math.max(1, opts.freqTo || opts.freqFrom), t0 + opts.duration);

    var gain = c.createGain();
    var peak = (opts.gain != null ? opts.gain : 0.5);
    var attack = opts.attack != null ? opts.attack : 0.012;
    var release = opts.release != null ? opts.release : opts.duration * 0.4;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(peak, t0 + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + opts.duration + release);

    var node = osc;
    if (opts.filterFreq) {
      var filt = c.createBiquadFilter();
      filt.type = opts.filterType || 'lowpass';
      filt.frequency.value = opts.filterFreq;
      node.connect(filt);
      node = filt;
    }
    node.connect(gain);
    gain.connect(masterGain);
    osc.start(t0);
    osc.stop(t0 + opts.duration + release + 0.05);
  }

  // A burst of filtered white noise -- used for pant/sniff/hiss/sigh.
  function noiseBurst(opts) {
    var c = getCtx();
    if (!c || muted) return;
    var t0 = c.currentTime + (opts.delay || 0);
    var dur = opts.duration || 0.2;
    var buf = c.createBuffer(1, Math.ceil(c.sampleRate * dur), c.sampleRate);
    var data = buf.getChannelData(0);
    for (var i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;

    var src = c.createBufferSource();
    src.buffer = buf;

    var filt = c.createBiquadFilter();
    filt.type = opts.filterType || 'bandpass';
    filt.frequency.value = opts.filterFreq || 2500;
    filt.Q.value = opts.q || 0.9;

    var gain = c.createGain();
    var peak = opts.gain != null ? opts.gain : 0.35;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(peak, t0 + (opts.attack || 0.02));
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);

    src.connect(filt);
    filt.connect(gain);
    gain.connect(masterGain);
    src.start(t0);
    src.stop(t0 + dur + 0.05);
  }

  // Slow amplitude tremolo on a sustained low tone -- used for snore/purr.
  function tremoloTone(opts) {
    var c = getCtx();
    if (!c || muted) return;
    var t0 = c.currentTime + (opts.delay || 0);
    var dur = opts.duration;
    var osc = c.createOscillator();
    osc.type = opts.type || 'sine';
    osc.frequency.setValueAtTime(opts.freq, t0);

    var lfo = c.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = opts.lfoRate || 27;
    var lfoGain = c.createGain();
    lfoGain.gain.value = opts.lfoDepth != null ? opts.lfoDepth : 0.25;

    var gain = c.createGain();
    var peak = opts.gain != null ? opts.gain : 0.3;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(peak, t0 + 0.08);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);

    lfo.connect(lfoGain);
    lfoGain.connect(gain.gain);
    osc.connect(gain);
    gain.connect(masterGain);

    osc.start(t0); lfo.start(t0);
    osc.stop(t0 + dur + 0.05); lfo.stop(t0 + dur + 0.05);
  }

  // -----------------------------------------------------------------------
  // Dog sounds
  // -----------------------------------------------------------------------
  function playYip() {
    tone({ type: 'triangle', freqFrom: 950, freqTo: 620, duration: 0.11, gain: 0.5 });
  }

  function playBarkOnce(delay, pitch) {
    tone({ type: 'sawtooth', freqFrom: pitch || 320, freqTo: (pitch || 320) * 0.55, duration: 0.14, gain: 0.55, filterFreq: 2200, delay: delay || 0 });
  }

  function playBark() {
    playBarkOnce(0, 300);
    playBarkOnce(0.18, 320);
  }

  function playWhine() {
    tone({ type: 'sine', freqFrom: 480, freqTo: 720, duration: 0.35, gain: 0.28, release: 0.2 });
    tone({ type: 'sine', freqFrom: 720, freqTo: 420, duration: 0.35, gain: 0.24, delay: 0.32, release: 0.25 });
  }

  function playSniff() {
    noiseBurst({ duration: 0.14, filterFreq: 3200, q: 1.2, gain: 0.25, attack: 0.01 });
    noiseBurst({ duration: 0.1, filterFreq: 3600, q: 1.2, gain: 0.2, delay: 0.16 });
  }

  function playSigh() {
    noiseBurst({ duration: 0.55, filterFreq: 600, filterType: 'lowpass', gain: 0.22, attack: 0.08 });
    tone({ type: 'sine', freqFrom: 220, freqTo: 140, duration: 0.55, gain: 0.18, attack: 0.08 });
  }

  function playSnore() {
    tremoloTone({ type: 'triangle', freq: 105, duration: 0.7, lfoRate: 22, gain: 0.22 });
    noiseBurst({ duration: 0.18, filterFreq: 900, gain: 0.15, delay: 0.68 });
  }

  // Repeated quick breathy bursts -- call once, it schedules `count` bursts.
  function playPant(seconds) {
    seconds = seconds || 1.2;
    var interval = 0.22;
    var count = Math.max(1, Math.round(seconds / interval));
    for (var i = 0; i < count; i++) {
      noiseBurst({ duration: 0.1, filterFreq: 1500, q: 0.7, gain: 0.18, delay: i * interval });
    }
  }

  function playGiggle() {
    var notes = [520, 600, 560, 660, 700];
    for (var i = 0; i < notes.length; i++) {
      tone({ type: 'triangle', freqFrom: notes[i], freqTo: notes[i] * 1.08, duration: 0.09, gain: 0.3, delay: i * 0.09 });
    }
  }

  // level: 0..3, escalating urgency for the alarm event.
  function playAlarmBark(level) {
    level = Math.max(0, Math.min(3, level || 0));
    var count = 2 + level;
    var gap = 0.32 - level * 0.06;
    var pitch = 300 + level * 30;
    for (var i = 0; i < count; i++) {
      playBarkOnce(i * gap, pitch);
    }
  }

  // -----------------------------------------------------------------------
  // Cat sounds
  // -----------------------------------------------------------------------
  function playMeow() {
    var c = getCtx();
    if (!c || muted) return;
    var t0 = c.currentTime;
    var osc = c.createOscillator();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(380, t0);
    osc.frequency.exponentialRampToValueAtTime(680, t0 + 0.16);
    osc.frequency.exponentialRampToValueAtTime(340, t0 + 0.42);

    var filt = c.createBiquadFilter();
    filt.type = 'bandpass'; filt.frequency.value = 900; filt.Q.value = 1.4;

    var gain = c.createGain();
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.32, t0 + 0.05);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.46);

    osc.connect(filt); filt.connect(gain); gain.connect(masterGain);
    osc.start(t0); osc.stop(t0 + 0.5);
  }

  function playPurr(seconds) {
    tremoloTone({ type: 'triangle', freq: 90, duration: seconds || 1.2, lfoRate: 26, lfoDepth: 0.3, gain: 0.22 });
  }

  function playHiss() {
    noiseBurst({ duration: 0.32, filterFreq: 4500, filterType: 'highpass', q: 0.6, gain: 0.28, attack: 0.005 });
  }

  function playTrill() {
    var c = getCtx();
    if (!c || muted) return;
    var t0 = c.currentTime;
    var osc = c.createOscillator();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(650, t0);
    var lfo = c.createOscillator();
    lfo.type = 'sine'; lfo.frequency.value = 22;
    var lfoGain = c.createGain(); lfoGain.gain.value = 60;
    lfo.connect(lfoGain); lfoGain.connect(osc.frequency);

    var gain = c.createGain();
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.28, t0 + 0.03);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.32);

    osc.connect(gain); gain.connect(masterGain);
    osc.start(t0); lfo.start(t0);
    osc.stop(t0 + 0.35); lfo.stop(t0 + 0.35);
  }

  // -----------------------------------------------------------------------
  // Babble for the "Talk" lip-sync caption -- returns a schedule of
  // {start, dur} vowel-blips (seconds, relative to now) that app.js/
  // behaviour.js replays into mouthOpen so the mouth moves with the sound.
  // -----------------------------------------------------------------------
  function playBabble(durationSeconds) {
    durationSeconds = durationSeconds || 1.4;
    var schedule = [];
    var tCursor = 0;
    while (tCursor < durationSeconds) {
      var dur = 0.08 + Math.random() * 0.09;
      var pitch = 260 + Math.random() * 180;
      tone({ type: 'sine', freqFrom: pitch, freqTo: pitch * 0.85, duration: dur, gain: 0.16, delay: tCursor, attack: 0.01, release: 0.03 });
      schedule.push({ start: tCursor, dur: dur });
      tCursor += dur + 0.03 + Math.random() * 0.03;
    }
    return schedule;
  }

  // -----------------------------------------------------------------------
  // Physical-action sounds (sneeze, hiccup, shiver, yawn, stomach growl,
  // munch) -- used by actions.js's scripted sequences.
  // -----------------------------------------------------------------------
  function playYawn() {
    tone({ type: 'sine', freqFrom: 300, freqTo: 140, duration: 0.9, gain: 0.22, attack: 0.15, release: 0.3 });
    noiseBurst({ duration: 0.7, filterFreq: 500, filterType: 'lowpass', gain: 0.12, attack: 0.2 });
  }

  function playSneeze() {
    noiseBurst({ duration: 0.08, filterFreq: 5500, q: 0.8, gain: 0.08, attack: 0.02 }); // the "in-breath"
    noiseBurst({ duration: 0.12, filterFreq: 3200, q: 0.7, gain: 0.42, attack: 0.004, delay: 0.1 }); // "-CHOO"
    tone({ type: 'triangle', freqFrom: 520, freqTo: 210, duration: 0.16, gain: 0.22, delay: 0.11, attack: 0.005 });
  }

  function playHiccup() {
    tone({ type: 'square', freqFrom: 640, freqTo: 900, duration: 0.06, gain: 0.3, attack: 0.004, release: 0.03 });
  }

  // Quick chattery noise bursts -- call once, it schedules the whole shiver.
  function playShiverChatter(seconds) {
    seconds = seconds || 1.0;
    var interval = 0.09;
    var count = Math.max(1, Math.round(seconds / interval));
    for (var i = 0; i < count; i++) {
      noiseBurst({ duration: 0.045, filterFreq: 2400, q: 1.4, gain: 0.16, delay: i * interval });
    }
  }

  function playStomachGrowl() {
    tone({ type: 'sawtooth', freqFrom: 95, freqTo: 65, duration: 0.7, gain: 0.14, filterFreq: 300, filterType: 'lowpass', attack: 0.05 });
    noiseBurst({ duration: 0.6, filterFreq: 220, filterType: 'lowpass', gain: 0.18, attack: 0.08 });
  }

  // One chomp -- behaviour/actions call this on a short interval for munching.
  function playMunch() {
    noiseBurst({ duration: 0.07, filterFreq: 900, filterType: 'lowpass', gain: 0.2, attack: 0.005 });
    tone({ type: 'sine', freqFrom: 190, freqTo: 120, duration: 0.08, gain: 0.22, attack: 0.005 });
  }

  // -----------------------------------------------------------------------
  // Music -- a short, cheerful, ORIGINAL melody (not from any existing
  // song). Pentatonic so it can't help but sound upbeat and friendly.
  // playMelody() schedules every note as a `tone()` call and returns a
  // {start, dur, freq} schedule (seconds, relative to now) so behaviour.js
  // can drive the dance bob and the "sing along" mouth from the same
  // clock the audio is using.
  // -----------------------------------------------------------------------
  var MELODY = [
    { freq: 523.25, dur: 0.28 }, { freq: 587.33, dur: 0.28 }, { freq: 659.25, dur: 0.28 },
    { freq: 783.99, dur: 0.42 }, { freq: 659.25, dur: 0.28 }, { freq: 783.99, dur: 0.28 },
    { freq: 880.00, dur: 0.56 }, { freq: 783.99, dur: 0.28 }, { freq: 659.25, dur: 0.28 },
    { freq: 587.33, dur: 0.28 }, { freq: 523.25, dur: 0.56 }
  ];

  function playMelody() {
    var schedule = [];
    var cursor = 0;
    for (var i = 0; i < MELODY.length; i++) {
      var note = MELODY[i];
      tone({
        type: 'triangle', freqFrom: note.freq, freqTo: note.freq,
        duration: note.dur * 0.9, gain: 0.26, delay: cursor,
        attack: 0.008, release: note.dur * 0.3
      });
      schedule.push({ start: cursor, dur: note.dur, freq: note.freq });
      cursor += note.dur;
    }
    return schedule;
  }

  function getMelodyDuration() {
    return MELODY.reduce(function (sum, n) { return sum + n.dur; }, 0);
  }

  // Hook for real audio/voice playback later (e.g. streamed from the
  // laptop AI). Deliberately a no-op today -- this build never loads
  // audio over the network. Swap the body for an <audio>/decoded-buffer
  // player once that exists, and it slots into the same dance/lip-sync
  // scheduling that playMelody()/playBabble() already provide.
  function playExternalTrack(sourceUrlOrBuffer) {
    if (typeof console !== 'undefined') {
      console.warn('Sounds.playExternalTrack() is a placeholder -- synth playback only for now.', sourceUrlOrBuffer);
    }
    return null;
  }

  var api = {
    initAudio: initAudio, setMuted: setMuted, isMuted: isMuted, setVolume: setVolume,
    playYip: playYip, playBark: playBark, playWhine: playWhine, playSniff: playSniff,
    playSigh: playSigh, playSnore: playSnore, playPant: playPant, playGiggle: playGiggle,
    playAlarmBark: playAlarmBark,
    playMeow: playMeow, playPurr: playPurr, playHiss: playHiss, playTrill: playTrill,
    playBabble: playBabble,
    playYawn: playYawn, playSneeze: playSneeze, playHiccup: playHiccup,
    playShiverChatter: playShiverChatter, playStomachGrowl: playStomachGrowl, playMunch: playMunch,
    playMelody: playMelody, getMelodyDuration: getMelodyDuration, playExternalTrack: playExternalTrack
  };

  root.Sounds = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
