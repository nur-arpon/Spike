/*
 * behaviour.js -- the brain: mood engine, idle life, events, battery hunger,
 * greetings. Reused from v1's design (same event names, caption logic and
 * mood drift) and rebuilt for the v2 face state.
 *
 * WHERE THE CUTENESS LIVES (motion):
 *  - every field is a damped spring (params.js), so mood changes overshoot
 *    and settle; each change also gets a squash/stretch "accent" kick
 *  - blinks: the lids snap shut and spring open; the blink spring overshoots
 *    past open, which the renderer turns into a STRETCH (squash & stretch);
 *    double blinks; a blink often rides on a big glance, like real eyes
 *  - micro-saccades every ~0.4-1 s and bigger glances every few seconds
 *  - breathing bob, ear flicks (spring impulses on a very bouncy spring),
 *    ears that swing when the head tilts (follow-through from tilt velocity)
 *  - nose sniffs in bursts of three, nose twitches when curious
 *  - idle head tilts, yawns when sleepy, mood drift when ignored
 *
 * The engine keeps its OWN clock (engine.time, advanced by update(dt)) and
 * its own scheduler, instead of setTimeout, so tests are deterministic and
 * the C++ port is a straight loop.
 *
 * Depends on: SPIKE, FaceParams, Moods, Extras, Sounds, Captions (+ Actions,
 * Music, Games if loaded).
 */
(function (root) {
  'use strict';

  var isNode = typeof window === 'undefined';
  function dep(name, file) { return root[name] || (isNode ? require(file) : null); }
  var SPIKE = dep('SPIKE', './config.js');
  var FP = dep('FaceParams', './params.js');
  var Moods = dep('Moods', './moods.js');
  var Extras = dep('Extras', './extras.js');
  var Sounds = dep('Sounds', './sounds.js');
  var Captions = dep('Captions', './captions.js');

  function Actions() { return root.Actions || null; }
  function Music() { return root.Music || null; }

  var DRIFT_CHAIN = ['bored', 'loneliness', 'sleepy', 'sleeping'];
  var POSITIVE = { happy: 1, excited: 1, love: 1, laughing: 1, playful: 1, joy: 1, delight: 1, proud: 1,
    wakeupAlarm: 1, awe: 1, hope: 1, gratitude: 1, surprised: 1, silliness: 1 };
  var NEGATIVE = { sad: 1, grief: 1, loneliness: 1, sulking: 1, sleepy: 1, bored: 1, hungry: 1, scared: 1 };
  var NO_IDLE_TILT = { sleeping: 1, dizzy: 1, grief: 1, scared: 1 };

  function rr(e, a, b) { return a + e.rnd() * (b - a); }

  // -------------------------------------------------------------------
  // Construction
  // -------------------------------------------------------------------
  function createBehaviour(opts) {
    opts = opts || {};
    var e = {
      time: 0,
      rnd: opts.rnd || Math.random,
      mode: 'dog',
      mood: 'neutral', moodSince: 0, prevMood: 'neutral',
      springs: FP.createSprings(Moods.getTarget('neutral', 'dog')),
      over: {},              // event overrides of spring targets: field -> {v, until}
      particles: Extras.createSystem(),
      caption: null,
      onCaption: opts.onCaption || function () {},
      queue: [],             // own scheduler: [{at, fn}]

      // idle life
      blinkUntil: -1, blinkSide: 0, nextBlink: 1.2,
      sacX: 0, sacY: 0, nextSaccade: 0.5,
      glanceX: 0, glanceY: 0, glanceUntil: -1, nextGlance: 3,
      nextEarFlick: 2.5, nextSniff: 6, sniffStart: -10, sniffCount: 0,
      twitchDX: 0, twitchUntil: -1, nextTwitch: 1,
      nextIdleTilt: 7, nextYawn: 30, extrasAt: 0,

      // pointer / camera stand-in
      lookX: 0, lookY: 0, lookSeenAt: -100,

      lastInteraction: 0, driftStage: -1, driftAt: 0,
      patTimes: [],
      babble: null,
      alarmActive: false, alarmLevel: 0, alarmNextAt: 0,
      demoActive: false, demoIndex: 0, demoNextAt: 0,

      battery: opts.battery != null ? opts.battery : 80,
      charging: false, hungerLevel: 'ok', nextHungryPokeAt: 0, munchNextAt: 0,

      actionLabel: null, _action: null,
      dance: null,
      energy: 1
    };
    e.score = root.Games ? root.Games.createGame() : { wins: 0, losses: 0, draws: 0, rounds: 0 };
    return e;
  }

  function now(e) { return e.time; }
  function after(e, seconds, fn) { e.queue.push({ at: e.time + seconds, fn: fn }); }
  function markInteraction(e) { e.lastInteraction = e.time; e.driftStage = -1; e.driftAt = e.time; }
  function name(e) { return e.mode === 'cat' ? SPIKE.catName : SPIKE.dogName; }

  // Override some spring TARGETS for a while (they still animate, so they
  // overshoot and settle like everything else).
  function override(e, fields, seconds) {
    var until = seconds == null ? Infinity : e.time + seconds;
    for (var k in fields) e.over[k] = { v: fields[k], until: until };
  }
  function clearOverrides(e) { e.over = {}; }
  function kick(e, fields) { for (var k in fields) FP.kick(e.springs, k, fields[k]); }

  // -------------------------------------------------------------------
  // Mood
  // -------------------------------------------------------------------
  function setMood(e, id, opts) {
    opts = opts || {};
    if (!Moods.FACE[id]) id = 'neutral';
    if (id === e.mood && !opts.force && !opts.snap) return;
    e.prevMood = e.mood;
    e.mood = id;
    e.moodSince = e.time;
    var target = Moods.getTarget(id, e.mode);
    if (opts.snap) { FP.snap(e.springs, target); return; }
    // expression-change accent: a stretch for happy things, a squash for
    // heavy ones; the springs overshoot it into a little bounce
    if (POSITIVE[id]) kick(e, { headSY: 0.9, headSX: -0.5, eyeSY: 0.8 });
    else if (NEGATIVE[id]) kick(e, { headSY: -0.5, headSX: 0.3 });
    else kick(e, { headSY: 0.35, eyeSY: 0.4 });
    var ex = Moods.EXTRAS[id];
    if (ex && ex.enter) {
      for (var i = 0; i < ex.enter.length; i++) {
        var s = ex.enter[i];
        Extras.burst(e.particles, s[0], s[1], s[2], s[3] || 1, null, e.rnd);
      }
    }
    e.extrasAt = e.time + 0.4;
  }

  function setMode(e, mode) {
    e.mode = mode === 'cat' ? 'cat' : 'dog';
    setMood(e, e.mood, { force: true });
    kick(e, { headSY: 1.2, headSX: -0.8 });
  }

  function showCaption(e, text, hold) {
    e.caption = { text: text, until: e.time + (hold || 3.2) };
    e.onCaption(text);
  }
  function say(e, category, hold) { showCaption(e, Captions.pickRendered(category, name(e)), hold); }

  function setLook(e, x, y) {
    e.lookX = FP.clamp(x, -1, 1);
    e.lookY = FP.clamp(y, -1, 1);
    e.lookSeenAt = e.time;
  }

  // -------------------------------------------------------------------
  // Touch: head pat (head pad) and nose boop
  // -------------------------------------------------------------------
  function pat(e) {
    markInteraction(e);
    var t = e.time;
    e.patTimes.push(t);
    e.patTimes = e.patTimes.filter(function (x) { return t - x < 1.6; });
    // every pat squashes the head a little and the ears go flat, like a
    // real dog leaning into a hand
    kick(e, { headSY: -1.6, headSX: 0.9, earL: 160, earR: 160 });
    override(e, { earBack: 0.5, happy: 1, blush: 0.7 }, 0.9);

    if (e.patTimes.length >= 6) {
      e.patTimes = [];
      setMood(e, 'dizzy');
      say(e, 'tease', 2.6);
      after(e, 2.4, function () { if (e.mood === 'dizzy') setMood(e, 'embarrassed'); });
      return;
    }
    if (e.mode === 'cat' && e.patTimes.length >= 4) {
      e.patTimes = [];
      clearOverrides(e);
      setMood(e, 'cuteAngry');
      Sounds.playHiss();
      say(e, 'catsass', 2.6);
      return;
    }
    setMood(e, e.mode === 'cat' ? 'cuddly' : 'happy');
    Extras.burst(e.particles, 'heart', 240, 44, 2 + Math.floor(e.rnd() * 2), null, e.rnd);
    if (e.mode === 'cat') Sounds.playPurr(1.2); else Sounds.playPatSqueak();
    if (e.rnd() < 0.4) say(e, e.mode === 'cat' ? 'catsass' : 'pat', 2.2);
  }

  // Tap on the nose: cross-eyed "boop!", then a giggle. Scripted in
  // actions.js (label 'boop') so the body can react too.
  function boop(e) {
    markInteraction(e);
    var A = Actions();
    if (A) A.playAction(e, 'boop');
  }

  // A burst of n sniffs (nose bobs + flares in time with the sound).
  function sniff(e, n) {
    e.sniffStart = e.time;
    e.sniffCount = n || 3;
    Sounds.playSniffs(e.sniffCount);
  }

  // -------------------------------------------------------------------
  // Greetings and life events (kept from v1, rebuilt on the new face)
  // -------------------------------------------------------------------
  function sayHi(e) {
    markInteraction(e);
    setMood(e, e.mode === 'cat' ? 'delight' : 'happy');
    kick(e, { bob: -120, headSY: 1.4, earL: -150, earR: -150 });
    if (e.mode === 'cat') Sounds.playMeow(); else Sounds.playYip();
    showCaption(e, 'Hi!', 1.6);
    after(e, 1.7, function () { say(e, 'greeting', 2.6); });
  }

  function greetByTimeOfDay(e, hourOverride) {
    markInteraction(e);
    var hour = hourOverride != null ? hourOverride : new Date().getHours();
    var cat, mood;
    if (hour >= 5 && hour < 12) { cat = 'greetMorning'; mood = 'joy'; }
    else if (hour >= 12 && hour < 17) { cat = 'greetAfternoon'; mood = 'happy'; }
    else if (hour >= 17 && hour < 22) { cat = 'greetEvening'; mood = 'caring'; }
    else { cat = 'greetLateNight'; mood = 'sleepy'; }
    setMood(e, mood);
    say(e, cat, 3);
  }

  function comeHome(e) {
    markInteraction(e);
    setMood(e, 'excited');
    kick(e, { bob: -160, headSY: 1.8, earL: -220, earR: -220 });
    after(e, 0.45, function () { kick(e, { bob: -140, headSY: 1.4 }); });
    after(e, 0.9, function () { kick(e, { bob: -100, headSY: 1.0 }); });
    Extras.burst(e.particles, 'confetti', 240, 60, 10, null, e.rnd);
    Extras.burst(e.particles, 'heart', 240, 50, 3, null, e.rnd);
    if (e.mode === 'cat') { Sounds.playTrill(); }
    else { Sounds.playYip(); after(e, 0.22, function () { Sounds.playBark(); }); }
    showCaption(e, "YOU'RE BACK!!", 3);
  }

  // Gentle and caring first; a small joke only after a pause.
  function ownerLooksSad(e) {
    markInteraction(e);
    setMood(e, 'caring');
    Sounds.playWhine();
    say(e, 'comfort', 4);
    after(e, 5.5, function () {
      if (e.demoActive || e.alarmActive) return;
      setMood(e, e.mode === 'cat' ? 'playful' : 'happy');
      say(e, 'selfdep', 3);
    });
  }

  function alarmStart(e) {
    e.alarmActive = true;
    e.alarmLevel = 0;
    e.alarmNextAt = e.time;
    setMood(e, 'wakeupAlarm');
  }
  function imUp(e) {
    if (!e.alarmActive) return;
    e.alarmActive = false;
    markInteraction(e);
    setMood(e, 'proud');
    Extras.burst(e.particles, 'sparkle', 240, 50, 5, null, e.rnd);
    say(e, 'general', 2.6);
  }

  function pickedUp(e) {
    markInteraction(e);
    setMood(e, 'cuddly');
    if (e.mode === 'cat') Sounds.playPurr(1.8); else Sounds.playSigh();
    say(e, 'comfort', 3);
  }

  function fellOver(e) {
    markInteraction(e);
    setMood(e, 'scared');
    kick(e, { tilt: -220, bob: 140, headSY: -2 });
    Sounds.playWhine();
    after(e, 0.8, function () {
      setMood(e, 'embarrassed');
      showCaption(e, 'I meant to do that.', 2.8);
    });
  }

  function talk(e, line) {
    markInteraction(e);
    line = line || Captions.pickRendered(e.mode === 'cat' ? 'catsass' : 'general', name(e));
    var dur = Math.max(1.0, Math.min(2.8, line.length * 0.045));
    e.babble = { schedule: Sounds.playBabble(dur) || fakeBabble(dur, e), start: e.time, dur: dur };
    showCaption(e, line, dur + 1.2);
  }
  function fakeBabble(dur, e) { // Node / muted: still animate the mouth
    var s = [], c = 0;
    while (c < dur) { var d = 0.08 + e.rnd() * 0.09; s.push({ start: c, dur: d }); c += d + 0.04; }
    return s;
  }

  function rpsReact(e, result) {
    markInteraction(e);
    if (result === 'win') {       // the person won
      setMood(e, 'sulking');
      say(e, 'tease', 2.4);
      if (e.mode === 'cat') Sounds.playHiss(); else Sounds.playWhine();
    } else if (result === 'lose') {
      setMood(e, 'excited');
      Extras.burst(e.particles, 'confetti', 240, 60, 8, null, e.rnd);
      say(e, 'greeting', 2.4);
      if (e.mode === 'cat') Sounds.playTrill(); else Sounds.playGiggle();
    } else {
      setMood(e, 'curious');
      say(e, 'general', 2);
    }
  }

  function ignoredNudge(e) {
    setMood(e, 'sulking');
    say(e, 'comfort', 2.6);
  }

  function startDemo(e) { e.demoActive = true; e.demoIndex = 0; e.demoNextAt = e.time; }
  function stopDemo(e) { e.demoActive = false; }

  // -------------------------------------------------------------------
  // Battery / hunger ("hungry = low battery"): battery eyes, stomach
  // growls, dramatic lines; munching happily while charging.
  // -------------------------------------------------------------------
  function setBattery(e, v) { e.battery = FP.clamp(v, 0, 100); }
  function setCharging(e, on) {
    on = !!on;
    if (on && !e.charging) {
      markInteraction(e);
      setMood(e, e.mode === 'cat' ? 'delight' : 'joy');
      say(e, 'full', 2.4);
    }
    e.charging = on;
  }
  function updateBattery(e) {
    var t = e.time;
    if (e.charging) {
      e.battery = Math.min(100, e.battery + e._dt * 9);
      if (t >= e.munchNextAt) { Sounds.playMunch(); e.munchNextAt = t + 0.32; }
      if (e.battery >= 100) {
        e.charging = false;
        Sounds.playSigh();
        say(e, 'full', 2.6);
        setMood(e, 'cuddly');
      }
      e.hungerLevel = 'ok';
      return;
    }
    var level = e.battery < SPIKE.weakBelow ? 'weak' : (e.battery < SPIKE.hungryBelow ? 'hungry' : 'ok');
    var dropped = level !== 'ok' && level !== e.hungerLevel;
    e.hungerLevel = level;
    if (level !== 'ok' && t >= e.nextHungryPokeAt) {
      e.nextHungryPokeAt = t + (dropped ? 0.1 : 22);
      if (!e.demoActive && !e.alarmActive && !e.actionLabel) {
        setMood(e, 'hungry');
        say(e, 'hungry', 2.8);
        // the growl lands on the face's tummy-rumble wobble (same 3.6 s cycle)
        var cyc = Moods.HUNGRY_CYCLE, toRumble = ((2.2 - (e.time % cyc)) % cyc + cyc) % cyc;
        after(e, toRumble, function () { if (e.mood === 'hungry') Sounds.playStomachGrowl(); });
        after(e, 6.5, function () {
          if (e.mood === 'hungry') setMood(e, level === 'weak' ? 'sleepy' : 'sad');
        });
      }
    }
  }
  function energyOf(e) {
    if (e.charging || e.battery >= SPIKE.hungryBelow) return 1;
    return 0.35 + (e.battery / SPIKE.hungryBelow) * 0.65;
  }

  // -------------------------------------------------------------------
  // Idle life
  // -------------------------------------------------------------------
  function present(e) { return e.time - e.lookSeenAt < 3; }

  function idle(e, t, allowed) {
    var cur = e.springs.current;
    var asleep = e.mood === 'sleeping' || cur.shut > 0.6;

    // blinks (+ double blinks); slower when the battery is low
    if (t >= e.nextBlink) {
      if (allowed && !asleep && cur.happy < 0.5) {
        e.blinkUntil = t + 0.085; e.blinkSide = 0;
        e.nextBlink = e.rnd() < SPIKE.doubleBlinkChance ? t + 0.3 : t + rr(e, SPIKE.blinkMin, SPIKE.blinkMax) / e.energy;
      } else e.nextBlink = t + 1;
    }
    // micro-saccades: tiny quick eye jumps so the gaze is never frozen
    if (t >= e.nextSaccade) {
      e.sacX = (e.rnd() - 0.5) * 0.14; e.sacY = (e.rnd() - 0.5) * 0.1;
      e.nextSaccade = t + rr(e, SPIKE.saccadeMin, SPIKE.saccadeMax);
    }
    // bigger glances; a blink often rides along with a big eye move
    if (t >= e.nextGlance) {
      if (allowed && !asleep && (!present(e) || e.rnd() < 0.3)) {
        e.glanceX = (e.rnd() - 0.5) * 1.5; e.glanceY = (e.rnd() - 0.5) * 0.7;
        e.glanceUntil = t + rr(e, 0.5, 1.3);
        if (e.rnd() < 0.35 && cur.happy < 0.5) e.blinkUntil = t + 0.085;
      }
      e.nextGlance = t + rr(e, SPIKE.glanceMin, SPIKE.glanceMax) / e.energy;
    }
    // ear flicks: an impulse on a very bouncy spring
    if (t >= e.nextEarFlick) {
      if (allowed) {
        var v = (e.mode === 'cat' ? 420 : 400) * (0.75 + e.rnd() * 0.5) * (asleep ? 0.45 : 1) * (e.rnd() < 0.6 ? -1 : 1);
        FP.kick(e.springs, e.rnd() < 0.5 ? 'earL' : 'earR', v);
        if (e.rnd() < 0.25) FP.kick(e.springs, e.rnd() < 0.5 ? 'earL' : 'earR', v * 0.8);
      }
      e.nextEarFlick = t + rr(e, SPIKE.earFlickMin, SPIKE.earFlickMax) * (e.mode === 'cat' ? 0.7 : 1);
    }
    // sniffs (more often when curious) and nose twitches
    if (t >= e.nextSniff) {
      if (allowed && !asleep && !NEGATIVE[e.mood]) sniff(e, 2 + Math.floor(e.rnd() * 2));
      e.nextSniff = t + (e.mood === 'curious' ? rr(e, 2.5, 4.5) : rr(e, SPIKE.sniffMin, SPIKE.sniffMax));
    }
    if (e.mood === 'curious' && t >= e.nextTwitch) {
      e.twitchDX = (e.rnd() < 0.5 ? -1 : 1) * rr(e, 1.5, 3);
      e.twitchUntil = t + 0.12;
      e.nextTwitch = t + rr(e, 0.5, 1.4);
    }
    // the "huh?" head tilt a dog gives you when you're there
    if (t >= e.nextIdleTilt) {
      if (allowed && !NO_IDLE_TILT[e.mood] && present(e)) {
        var dir = e.rnd() < 0.5 ? -1 : 1;
        override(e, { tilt: dir * rr(e, 7, 12) }, rr(e, 1.1, 2.0));
        FP.kick(e.springs, dir < 0 ? 'earL' : 'earR', -150);
      }
      e.nextIdleTilt = t + rr(e, 6, 12);
    }
    // yawns when sleepy
    if (e.mood === 'sleepy' && allowed && t >= e.nextYawn && Actions()) {
      Actions().playAction(e, 'yawn', { auto: true });
      e.nextYawn = t + rr(e, 9, 16);
    } else if (e.mood !== 'sleepy') e.nextYawn = Math.max(e.nextYawn, t + 3);

    // ignored for a while: bored -> lonely -> sleepy -> asleep
    if (allowed && !e.demoActive && !e.alarmActive && !e.dance &&
        t - e.lastInteraction > SPIKE.moodDrift && t - e.driftAt > SPIKE.moodDrift) {
      e.driftAt = t;
      if (e.driftStage < DRIFT_CHAIN.length - 1 &&
          (e.mood === 'neutral' || e.mood === 'happy' || DRIFT_CHAIN.indexOf(e.mood) !== -1)) {
        e.driftStage++;
        setMood(e, DRIFT_CHAIN[e.driftStage]);
      }
    }
  }

  // -------------------------------------------------------------------
  // Per-frame update. dt in seconds.
  // -------------------------------------------------------------------
  function update(e, dt) {
    dt = FP.clamp(dt || 0, 0, 0.1);
    e._dt = dt;
    e.time += dt;
    var t = e.time;

    if (e.queue.length) {
      var due = [];
      e.queue = e.queue.filter(function (q) { if (q.at <= t) { due.push(q); return false; } return true; });
      for (var i = 0; i < due.length; i++) due[i].fn();
    }
    if (e.demoActive && t >= e.demoNextAt) {
      setMood(e, Moods.MOODS[e.demoIndex % Moods.MOODS.length], { force: true });
      e.demoIndex++;
      e.demoNextAt = t + 2.4;
    }
    if (e.alarmActive && t >= e.alarmNextAt) {
      Sounds.playAlarmBark(e.alarmLevel);
      say(e, 'alarm', 2.2);
      kick(e, { bob: -120 - 30 * e.alarmLevel, headSY: 1.4 });
      e.alarmLevel = Math.min(3, e.alarmLevel + 1);
      e.alarmNextAt = t + Math.max(1.4, 3.4 - e.alarmLevel * 0.6);
    }

    e.energy = energyOf(e);
    var step = e._action ? e._action.steps[e._action.index] : null;
    var idleAllowed = !(step && step.idle === false) && !e.demoActive;
    idle(e, t, idleAllowed);
    updateBattery(e);

    var ex = Moods.EXTRAS[e.mood];
    if (ex && ex.every && t >= e.extrasAt) {
      var ev = ex.every;
      Extras.spawn(e.particles, ev[1], ev[2] + (e.rnd() - 0.5) * 2 * (ev[4] || 0), ev[3] + (e.rnd() - 0.5) * 16, null, e.rnd);
      e.extrasAt = t + ev[0] * rr(e, 0.8, 1.2);
    }

    if (Actions()) Actions().update(e, dt);
    if (Music()) Music().update(e, dt);

    // ---- spring targets: mood -> gaze -> blink -> action -> events ----
    var tg = Moods.getTarget(e.mood, e.mode);
    var follow = Moods.followsLook(e.mood);
    var gx = tg.lookX, gy = tg.lookY;
    if (follow && present(e) && t >= e.glanceUntil) { gx = e.lookX * 0.95; gy = e.lookY * 0.8; }
    else if (follow && t < e.glanceUntil) { gx = e.glanceX; gy = e.glanceY; }
    tg.lookX = gx + e.sacX; tg.lookY = gy + e.sacY;
    if (t < e.blinkUntil) { tg.blinkL = 1; tg.blinkR = 1; }
    if (e._actionOver) for (var k in e._actionOver) if (k in tg) tg[k] = e._actionOver[k];
    for (var f in e.over) {
      if (e.over[f].until < t) delete e.over[f];
      else if (f in tg) tg[f] = e.over[f].v;
    }
    // a heart/star/battery shrinks away before its icon is dropped
    var cur = e.springs.current;
    if (!tg.icon && cur.icon && cur.iconAmt > 0.03) tg.icon = cur.icon;
    e.springs.target = tg;
    cur.icon = tg.icon;
    FP.step(e.springs, dt);

    Extras.update(e.particles, dt);
    if (e.caption && t >= e.caption.until) e.caption = null;
  }

  // -------------------------------------------------------------------
  // The face state to draw this frame: springs + overlays.
  // -------------------------------------------------------------------
  function getFaceParams(e) {
    var p = FP.copy(e.springs.current), t = e.time, en = e.energy;

    // breathing (a slow bob and a hint of chest-rise stretch)
    var br = Math.sin(t * 6.283185 / SPIKE.breathPeriod);
    p.bob += br * 1.6 * en;
    p.headSY += br * 0.006 * en;
    p.headSX -= br * 0.003 * en;

    Moods.applyMotion(p, e.mood, t, en);

    // follow-through: floppy ears lag behind head tilt and bounce
    var tv = e.springs.velocity.tilt, bv = e.springs.velocity.bob;
    var sw = FP.clamp(tv * 0.22, -24, 24), bw = FP.clamp(bv * 0.12, -14, 14);
    p.earL += -sw + bw;
    p.earR += sw + bw;

    // sniff burst: the nose bobs and flares in 0.14 s beats
    var sa = t - e.sniffStart, win = 0.14;
    if (sa >= 0 && sa < e.sniffCount * win) {
      var fr = (sa % win) / win, pulse = fr < 0.6 ? Math.sin(fr / 0.6 * Math.PI) : 0;
      p.noseDY -= 3.6 * pulse; p.noseSX += 0.13 * pulse; p.noseSY -= 0.07 * pulse;
    }
    if (t < e.twitchUntil) p.noseDX += e.twitchDX;

    // talking: lip-sync from the babble schedule
    if (e.babble) {
      var rel = t - e.babble.start;
      if (rel > e.babble.dur) e.babble = null;
      else {
        for (var i = 0; i < e.babble.schedule.length; i++) {
          var s = e.babble.schedule[i];
          if (rel >= s.start && rel <= s.start + s.dur) {
            var q = (rel - s.start) / s.dur;
            p.open = Math.max(p.open, 0.5 * Math.sin(q * Math.PI));
            p.mouthO = Math.max(p.mouthO, 0.25 * Math.sin(q * Math.PI));
            break;
          }
        }
      }
    }
    // charging = eating happily
    if (e.charging) {
      var ph = (t * 3.2) % 1;
      p.open = Math.max(p.open, ph < 0.4 ? 0.45 : 0.06);
      p.smile = Math.max(p.smile, 0.5);
    }

    if (Actions()) Actions().applyOverlay(e, p, t);
    if (Music()) Music().applyOverlay(e, p, t);
    return FP.clampState(p);
  }

  var api = {
    createBehaviour: createBehaviour, update: update, getFaceParams: getFaceParams,
    setMood: setMood, setMode: setMode, setLook: setLook,
    // touch + events
    pat: pat, boop: boop, sniff: sniff, sayHi: sayHi, greetByTimeOfDay: greetByTimeOfDay,
    comeHome: comeHome, ownerLooksSad: ownerLooksSad, alarmStart: alarmStart, imUp: imUp,
    pickedUp: pickedUp, fellOver: fellOver, talk: talk, rpsReact: rpsReact, ignoredNudge: ignoredNudge,
    startDemo: startDemo, stopDemo: stopDemo, setBattery: setBattery, setCharging: setCharging,
    // helpers for actions.js / music.js
    say: say, showCaption: showCaption, markInteraction: markInteraction, override: override,
    clearOverrides: clearOverrides, kick: kick, after: after, now: now
  };
  root.Behaviour = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
