/*
 * music.js -- "play a song": a short original synthesized melody
 * (Sounds.playMelody(), see sounds.js) with Spike dancing along --
 * bobbing, closing his eyes happily, and popping music-note particles --
 * plus an optional "sing along" mode where the mouth moves with the tune.
 *
 * Real playback later: swap Sounds.playMelody()'s body for Sounds.
 * playExternalTrack(), which already returns the same {start,dur,freq}
 * shape this file consumes, so the dance/lip-sync code below needs no
 * changes when that lands.
 */
(function (root) {
  'use strict';

  var isNode = typeof window === 'undefined';
  var Behaviour = root.Behaviour || (isNode ? require('./behaviour.js') : null);
  var Sounds = root.Sounds || (isNode ? require('./sounds.js') : null);
  var Extras = root.Extras || (isNode ? require('./extras.js') : null);

  var DANCE_BEAT = 6.5; // radians/sec -- purely a visual bob rate, not tied to tempo precisely

  function playSong(engine, opts) {
    opts = opts || {};
    var schedule = Sounds.playMelody();
    var duration = Sounds.getMelodyDuration();
    var t = Behaviour.nowSeconds();
    engine.dance = { schedule: schedule, startAt: t, duration: duration, singAlong: !!opts.singAlong, noteIndex: -1 };
    Behaviour.markInteraction(engine);
    Behaviour.setMood(engine, engine.mode === 'cat' ? 'delight' : 'joy');
    return duration;
  }

  function stopSong(engine) {
    engine.dance = null;
  }

  function isPlaying(engine) {
    return !!engine.dance;
  }

  function update(engine, dt, t) {
    var d = engine.dance;
    if (!d) return;
    var age = t - d.startAt;
    if (age >= d.duration) { engine.dance = null; return; }

    // pop a music note on each new beat of the schedule
    var idx = -1;
    for (var i = 0; i < d.schedule.length; i++) {
      if (age >= d.schedule[i].start) idx = i;
    }
    if (idx !== d.noteIndex) {
      d.noteIndex = idx;
      Extras.spawn(engine.particles, 'music', (idx % 2 === 0 ? -1 : 1) * 30, -80);
    }
  }

  function applyOverlay(engine, p, t) {
    var d = engine.dance;
    if (!d) return;
    var age = t - d.startAt;

    // bobbing dance move + a little squash/stretch on the beat
    p.bobOffset = (p.bobOffset || 0) + Math.sin(age * DANCE_BEAT) * 4;
    p.squashX = (p.squashX || 1) + Math.sin(age * DANCE_BEAT) * 0.04;
    p.squashY = (p.squashY || 1) - Math.sin(age * DANCE_BEAT) * 0.04;

    // eyes closing happily while the music plays
    p.topLidL = Math.max(p.topLidL || 0, 0.35);
    p.topLidR = Math.max(p.topLidR || 0, 0.35);

    if (d.singAlong) {
      var note = null;
      for (var i = 0; i < d.schedule.length; i++) {
        var seg = d.schedule[i];
        if (age >= seg.start && age <= seg.start + seg.dur) { note = seg; break; }
      }
      p.mouthOpen = Math.max(p.mouthOpen || 0, note ? 0.5 : 0.08);
    }
  }

  var api = { playSong: playSong, stopSong: stopSong, isPlaying: isPlaying, update: update, applyOverlay: applyOverlay };
  root.Music = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
