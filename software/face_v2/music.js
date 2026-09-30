/*
 * music.js -- "play a song": an original synthesized melody (Sounds.
 * playMelody) with Spike dancing: a bob on every beat, a side-to-side head
 * sway, happy "^ ^" eyes that pop open on the high notes, music notes
 * popping out, and an optional sing-along mouth. Reused from v1, rebuilt on
 * the v2 face state and engine clock.
 *
 * Real playback later: Sounds.playExternalTrack() returns the same
 * {start,dur,freq} schedule shape, so this file does not change.
 */
(function (root) {
  'use strict';
  var isNode = typeof window === 'undefined';
  function dep(n, f) { return root[n] || (isNode ? require(f) : null); }
  var Behaviour = dep('Behaviour', './behaviour.js');
  var Sounds = dep('Sounds', './sounds.js');
  var Extras = dep('Extras', './extras.js');

  var FALLBACK = [523, 587, 659, 784, 659, 784, 880, 784, 659, 587, 523];
  var FALLBACK_DUR = [0.28, 0.28, 0.28, 0.42, 0.28, 0.28, 0.56, 0.28, 0.28, 0.28, 0.56];

  function fallbackSchedule() {
    var s = [], c = 0;
    for (var i = 0; i < FALLBACK.length; i++) { s.push({ start: c, dur: FALLBACK_DUR[i], freq: FALLBACK[i] }); c += FALLBACK_DUR[i]; }
    return s;
  }

  function playSong(e, opts) {
    opts = opts || {};
    var schedule = Sounds.playMelody() || fallbackSchedule();
    if (!schedule.length) schedule = fallbackSchedule();
    var last = schedule[schedule.length - 1];
    e.dance = { schedule: schedule, start: e.time, duration: last.start + last.dur + 0.3,
      singAlong: opts.singAlong !== false, noteIndex: -1 };
    Behaviour.markInteraction(e);
    Behaviour.setMood(e, e.mode === 'cat' ? 'delight' : 'joy');
    return e.dance.duration;
  }
  function stopSong(e) { e.dance = null; }
  function isPlaying(e) { return !!e.dance; }

  function noteAt(d, age) {
    for (var i = 0; i < d.schedule.length; i++) {
      var s = d.schedule[i];
      if (age >= s.start && age < s.start + s.dur) return i;
    }
    return -1;
  }

  function update(e) {
    var d = e.dance;
    if (!d) return;
    var age = e.time - d.start;
    if (age >= d.duration) { e.dance = null; Behaviour.setMood(e, 'happy'); return; }
    var idx = noteAt(d, age);
    if (idx !== -1 && idx !== d.noteIndex) {
      d.noteIndex = idx;
      Extras.spawn(e.particles, 'music', 240 + (idx % 2 === 0 ? -1 : 1) * (60 + (idx % 3) * 30), 60, null, e.rnd);
      Behaviour.kick(e, { bob: -70, headSY: 0.8 });   // a hop on every note
    }
  }

  function applyOverlay(e, p) {
    var d = e.dance;
    if (!d) return;
    var age = e.time - d.start;
    var idx = noteAt(d, age), note = idx >= 0 ? d.schedule[idx] : null;
    p.tilt += Math.sin(age * 4.4) * 7;           // sway side to side
    p.shakeX += Math.sin(age * 4.4) * 4;
    var high = note && note.freq >= 780;
    p.happy = Math.max(p.happy, high ? 0 : 0.85); // eyes pop open on the high notes
    if (d.singAlong) {
      if (note) {
        var q = (age - note.start) / note.dur;
        p.open = Math.max(p.open, 0.55 * Math.sin(Math.min(1, q * 1.3) * Math.PI) + 0.1);
        p.mouthO = Math.max(p.mouthO, high ? 0.5 : 0.2);
      } else p.open = Math.max(p.open, 0.08);
    }
  }

  var api = { playSong: playSong, stopSong: stopSong, isPlaying: isPlaying, update: update, applyOverlay: applyOverlay };
  root.Music = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
