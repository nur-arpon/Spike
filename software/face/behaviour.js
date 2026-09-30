/*
 * behaviour.js -- the mood/behaviour engine and events.
 *
 * This is the piece that ties everything else together: it owns the
 * spring state (face_params.js), decides which preset (expressions.js)
 * is the current target, drives idle life-like motion (blinks, glances,
 * breathing, yawns, mood drift), reacts to events fired from the page
 * (pat, comeHome, ownerSad, alarm, pickedUp, fellOver, talk, RPS...),
 * and exposes one getFaceParams()/getExtras() pair per frame for app.js
 * to draw.
 *
 * Depends on (all loaded earlier via <script> tags, or require() in
 * Node): SPIKE (config.js), FaceParams, Expressions, Extras, Sounds,
 * Captions.
 */
(function (root) {
  'use strict';

  var isNode = typeof window === 'undefined';
  var SPIKE = root.SPIKE || (isNode ? require('./config.js') : null);
  var FaceParams = root.FaceParams || (isNode ? require('./face_params.js') : null);
  var Expressions = root.Expressions || (isNode ? require('./expressions.js') : null);
  var Extras = root.Extras || (isNode ? require('./extras.js') : null);
  var Sounds = root.Sounds || (isNode ? require('./sounds.js') : null);
  var Captions = root.Captions || (isNode ? require('./captions.js') : null);

  // Moods where the eyes should track the mouse/finger. Everything except
  // moods with strong scripted gaze (looking away sulking, eyes shut).
  var LOOK_FOLLOW_MOODS = {
    neutral: 1, happy: 1, excited: 1, love: 1, laughing: 1, playful: 1,
    caring: 1, bored: 1, scared: 1, surprised: 1, cuteAngry: 1, proud: 1,
    embarrassed: 1, begging: 1, cuddly: 1, wakeupAlarm: 1,
    joy: 1, delight: 1, anger: 1, frustration: 1, disgust: 1, hope: 1,
    confusion: 1, relief: 1, gratitude: 1, mischief: 1, determination: 1,
    nervousness: 1, awe: 1, smugness: 1, silliness: 1
  };

  var DRIFT_CHAIN = ['happy', 'bored', 'sulking', 'sleepy'];

  // -----------------------------------------------------------------------
  // Per-mood idle animation -- small continuous modulations layered on top
  // of the spring-settled pose so nothing (especially the new "human
  // emotions" presets) is ever a completely dead, static picture. Each
  // entry is {field, amp, freq (Hz), phase, kind: 'sin' | 'jitter'}.
  // 'jitter' sums two off-ratio sines for a less mechanically-regular
  // tremor (used for shivers/nerves/anger) than a single sine gives.
  // Values are in the same units as the field itself (px / degrees / 0..1).
  // -----------------------------------------------------------------------
  var MOOD_MOTION = {
    excited: [{ field: 'bobOffset', amp: 2, freq: 4, kind: 'sin' }],
    sleeping: [
      { field: 'lookX', amp: 0.12, freq: 0.7, kind: 'jitter' },
      { field: 'lookY', amp: 0.08, freq: 0.9, kind: 'jitter', phase: 1.7 }
    ],
    dizzy: [
      { field: 'faceTilt', amp: 22, freq: 0.9, kind: 'sin' },
      { field: 'lookX', amp: 0.6, freq: 0.9, kind: 'sin' },
      { field: 'lookY', amp: 0.3, freq: 1.8, kind: 'sin' }
    ],
    bored: [{ field: 'topLidL', amp: 0.1, freq: 0.25, kind: 'sin' }, { field: 'topLidR', amp: 0.1, freq: 0.25, kind: 'sin' }],
    sulking: [{ field: 'lookX', amp: 0.15, freq: 0.15, kind: 'sin', phase: 2 }],
    joy: [{ field: 'bobOffset', amp: 3, freq: 2.2, kind: 'sin' }],
    delight: [{ field: 'squashX', amp: 0.03, freq: 3.2, kind: 'sin' }, { field: 'squashY', amp: 0.03, freq: 3.2, kind: 'sin', phase: 3.14 }],
    anger: [{ field: 'faceTilt', amp: 1.5, freq: 9, kind: 'jitter' }],
    frustration: [{ field: 'faceTilt', amp: 4, freq: 1.5, kind: 'sin' }],
    disgust: [{ field: 'faceTilt', amp: 2, freq: 0.6, kind: 'sin' }],
    grief: [{ field: 'bobOffset', amp: 2, freq: 0.4, kind: 'sin' }],
    loneliness: [{ field: 'lookY', amp: 0.08, freq: 0.2, kind: 'sin' }],
    hope: [{ field: 'faceTilt', amp: 2, freq: 0.5, kind: 'sin' }, { field: 'bobOffset', amp: -1.5, freq: 0.5, kind: 'sin' }],
    shyness: [{ field: 'lookX', amp: 0.25, freq: 0.35, kind: 'sin', phase: 1 }],
    jealousy: [{ field: 'lookX', amp: 0.2, freq: 0.8, kind: 'sin' }],
    confusion: [{ field: 'faceTilt', amp: 8, freq: 0.5, kind: 'sin' }],
    suspicion: [{ field: 'lookX', amp: 0.18, freq: 0.18, kind: 'sin' }],
    relief: [{ field: 'breathScale', amp: 0.04, freq: 0.5, kind: 'sin' }],
    gratitude: [{ field: 'faceTilt', amp: 3, freq: 0.8, kind: 'sin' }],
    mischief: [{ field: 'smirkSide', amp: 0.15, freq: 1.2, kind: 'sin' }],
    determination: [{ field: 'bobOffset', amp: 0.8, freq: 2.5, kind: 'sin' }],
    nervousness: [{ field: 'faceTilt', amp: 2, freq: 10, kind: 'jitter' }, { field: 'bobOffset', amp: 1, freq: 11, kind: 'jitter', phase: 2 }],
    awe: [{ field: 'breathScale', amp: 0.03, freq: 0.3, kind: 'sin' }],
    smugness: [{ field: 'faceTilt', amp: 2, freq: 0.4, kind: 'sin' }],
    silliness: [{ field: 'faceTilt', amp: 6, freq: 2.5, kind: 'sin' }]
  };

  // Fields that must stay in a sane range even after motion + overlays are
  // added on top of them -- a final safety clamp, not a design choice.
  var CLAMP_RANGES = {
    topLidL: [0, 1], topLidR: [0, 1], bottomLidL: [0, 1], bottomLidR: [0, 1],
    blinkL: [0, 1], blinkR: [0, 1], breathScale: [0.75, 1.35], squashX: [0.55, 1.6],
    squashY: [0.55, 1.6], mouthOpen: [0, 1], slitPupil: [0, 1]
  };

  function applyMoodMotion(p, moodId, t, amplitudeScale) {
    var list = MOOD_MOTION[moodId];
    if (!list) return;
    var scale = amplitudeScale == null ? 1 : amplitudeScale;
    for (var i = 0; i < list.length; i++) {
      var m = list[i];
      var phase = m.phase || 0;
      var val;
      if (m.kind === 'jitter') {
        val = m.amp * (0.6 * Math.sin(t * m.freq * 6.2832 + phase) + 0.4 * Math.sin(t * m.freq * 2.4 * 6.2832 + phase * 1.3));
      } else {
        val = m.amp * Math.sin(t * m.freq * 6.2832 + phase);
      }
      p[m.field] = (p[m.field] || 0) + val * scale;
    }
  }

  function finalClamp(p) {
    for (var field in CLAMP_RANGES) {
      var range = CLAMP_RANGES[field];
      if (p[field] < range[0]) p[field] = range[0];
      else if (p[field] > range[1]) p[field] = range[1];
    }
    return p;
  }

  function nowSeconds() {
    return (typeof performance !== 'undefined' ? performance.now() : Date.now()) / 1000;
  }

  function createBehaviour(options) {
    options = options || {};
    var cfg = SPIKE;

    var engine = {
      mode: 'dog',                 // 'dog' | 'cat'
      mood: 'neutral',
      spring: FaceParams.createSpringState(Expressions.getPreset('neutral', 'dog')),
      particles: Extras.createSystem(),
      caption: null,               // { text, expiresAt }
      score: null,

      lastInteractionAt: nowSeconds(),
      driftStage: 0,
      driftTimerAt: nowSeconds(),

      // idle scheduling
      nextBlinkAt: nowSeconds() + randRange(cfg.idleBlinkMinMs, cfg.idleBlinkMaxMs) / 1000,
      nextGlanceAt: nowSeconds() + randRange(cfg.idleGlanceMinMs, cfg.idleGlanceMaxMs) / 1000,
      nextYawnAt: nowSeconds() + randRange(cfg.yawnChanceMs * 0.6, cfg.yawnChanceMs * 1.4) / 1000,
      blinkUntil: 0,
      glanceUntil: 0,
      glanceX: 0, glanceY: 0,

      // pointer / camera-tracking stand-in
      lookX: 0, lookY: 0,

      // transient overlays
      bounceStartAt: -1, bounceDurationS: 0, bounceAmp: 0,
      babbleSchedule: null, babbleStartAt: -1, babbleDurationS: 0,

      // pat tracking (rapid taps -> dizzy/funny-annoyed)
      patTimestamps: [],

      // alarm
      alarmActive: false, alarmLevel: 0, alarmNextAt: 0,

      // followup one-shots (e.g. "gentle joke" after comforting)
      pendingFollowup: null, // { atSeconds, mood, category }

      // demo cycling
      demoActive: false, demoIndex: 0, demoNextAt: 0,

      // battery / hunger ("hungry = low battery")
      battery: options.battery != null ? options.battery : 70,
      charging: false,
      hungerLevel: 'ok', // 'ok' | 'hungry' | 'weak'
      nextHungryPokeAt: 0,
      munchNextAt: 0,

      // current scripted physical-action label, read by actions.js and by
      // (eventually) the leg/wheel firmware -- null when idle
      actionLabel: null,

      // music / dance (used by music.js if it's loaded)
      dance: null,

      onCaption: options.onCaption || function () {}
    };

    engine.score = (root.Games ? root.Games.createGame() : { wins: 0, losses: 0, draws: 0, rounds: 0 });

    return engine;
  }

  function randRange(a, b) { return a + Math.random() * (b - a); }

  function markInteraction(engine) {
    engine.lastInteractionAt = nowSeconds();
    engine.driftStage = 0;
    engine.driftTimerAt = nowSeconds();
  }

  // Sets the mood and springs the face toward its preset. `opts.snap`
  // jumps instantly (used on first load / mode switch).
  function setMood(engine, moodId, opts) {
    opts = opts || {};
    if (!Expressions.PRESETS.hasOwnProperty(moodId)) moodId = 'neutral';
    engine.mood = moodId;
    var target = Expressions.getPreset(moodId, engine.mode);
    if (opts.snap) FaceParams.snapTo(engine.spring, target);
    else FaceParams.setTarget(engine.spring, target);
  }

  function setMode(engine, mode) {
    engine.mode = (mode === 'cat') ? 'cat' : 'dog';
    setMood(engine, engine.mood, {});
  }

  function showCaption(engine, text, holdSeconds) {
    engine.caption = { text: text, expiresAt: nowSeconds() + (holdSeconds || 3.2) };
    engine.onCaption(text);
  }

  function sayFromCategory(engine, category, holdSeconds) {
    var name = engine.mode === 'cat' ? SPIKE.catName : SPIKE.dogName;
    showCaption(engine, Captions.pickRendered(category, name), holdSeconds);
  }

  function triggerBounce(engine, durationS, amp) {
    engine.bounceStartAt = nowSeconds();
    engine.bounceDurationS = durationS;
    engine.bounceAmp = amp;
  }

  // Animation principle: "anticipation before the big move" -- nudge the
  // SPRING'S CURRENT VALUE (not its target) a little the wrong way just
  // before a big pose change. Because the spring still has the old target
  // for one tick, it visibly winds up, then the new setMood() call snaps
  // the target and the spring's own overshoot carries it past and back --
  // a tiny anticipation + overshoot for free, no extra animation code.
  function anticipate(engine, fieldDips) {
    for (var field in fieldDips) {
      if (engine.spring.current[field] !== undefined) {
        engine.spring.current[field] += fieldDips[field];
      }
    }
  }

  // -----------------------------------------------------------------------
  // Battery / hunger ("hungry = low battery")
  // -----------------------------------------------------------------------
  function setBattery(engine, v) {
    engine.battery = FaceParams.clamp(v, 0, 100);
  }

  function setCharging(engine, on) {
    on = !!on;
    if (on && !engine.charging) {
      markInteraction(engine);
      setMood(engine, engine.mode === 'cat' ? 'delight' : 'joy');
      showCaption(engine, Captions.pickRendered('full', engine.mode === 'cat' ? SPIKE.catName : SPIKE.dogName), 2.4);
    }
    engine.charging = on;
    if (!on) engine.munchNextAt = 0;
  }

  function updateBattery(engine, t, dt) {
    if (engine.charging) {
      engine.battery = Math.min(100, engine.battery + dt * 9);
      if (t >= engine.munchNextAt) {
        Sounds.playMunch();
        engine.munchNextAt = t + 0.32;
      }
      if (engine.battery >= 100) {
        engine.charging = false;
        Sounds.playSigh();
        showCaption(engine, Captions.pickRendered('full', engine.mode === 'cat' ? SPIKE.catName : SPIKE.dogName), 2.6);
        setMood(engine, 'cuddly');
      }
      engine.hungerLevel = 'ok';
      return;
    }

    var level = engine.battery < 15 ? 'weak' : (engine.battery < 30 ? 'hungry' : 'ok');
    var justDropped = level !== 'ok' && level !== engine.hungerLevel;
    engine.hungerLevel = level;

    if (level !== 'ok' && t >= engine.nextHungryPokeAt) {
      engine.nextHungryPokeAt = t + (justDropped ? 0 : 22);
      if (!engine.demoActive && !engine.alarmActive && !engine.actionLabel) {
        Sounds.playStomachGrowl();
        sayFromCategory(engine, 'hungry', 2.8);
        if (level === 'weak' && !LOOK_FOLLOW_MOODS[engine.mood]) {
          // weak: nudge toward sleepy if nothing more important is happening
          setMood(engine, 'sleepy');
        }
      }
    }
  }

  // fatigue: how much low battery should damp idle motion amplitude and
  // slow the blink/glance cadence -- 1 = full energy, down to ~0.35 when critical.
  function fatigueScale(engine) {
    if (engine.charging) return 1;
    if (engine.battery >= 30) return 1;
    return 0.35 + (engine.battery / 30) * 0.65;
  }

  // -----------------------------------------------------------------------
  // Say hi / time-of-day greetings
  // -----------------------------------------------------------------------
  function sayHi(engine) {
    markInteraction(engine);
    anticipate(engine, { bobOffset: 3, squashY: -0.04 });
    setMood(engine, engine.mode === 'cat' ? 'delight' : 'happy');
    triggerBounce(engine, 0.7, 7);
    if (engine.mode === 'cat') Sounds.playMeow(); else Sounds.playYip();
    showCaption(engine, 'Hi!', 1.6);
    engine.pendingFollowup = { atSeconds: nowSeconds() + 1.7, mood: engine.mood, category: 'greeting' };
  }

  function greetByTimeOfDay(engine) {
    markInteraction(engine);
    var hour = new Date().getHours();
    var category, mood;
    if (hour >= 5 && hour < 12) { category = 'greetMorning'; mood = 'joy'; }
    else if (hour >= 12 && hour < 17) { category = 'greetAfternoon'; mood = 'happy'; }
    else if (hour >= 17 && hour < 22) { category = 'greetEvening'; mood = 'caring'; }
    else { category = 'greetLateNight'; mood = 'sleepy'; }
    setMood(engine, mood);
    sayFromCategory(engine, category, 3);
  }

  // -----------------------------------------------------------------------
  // Events (called from app.js in response to buttons / canvas taps)
  // -----------------------------------------------------------------------

  function pat(engine) {
    markInteraction(engine);
    var t = nowSeconds();
    engine.patTimestamps.push(t);
    engine.patTimestamps = engine.patTimestamps.filter(function (ts) { return t - ts < 1.4; });

    if (engine.patTimestamps.length >= 5) {
      setMood(engine, 'dizzy');
      Extras.spawn(engine.particles, 'dizzyStar', 0, -70, { orbitR: 50 });
      sayFromCategory(engine, 'tease', 2.6);
      return;
    }

    if (engine.mode === 'cat' && engine.patTimestamps.length >= 3) {
      setMood(engine, 'cuteAngry');
      Sounds.playHiss();
      sayFromCategory(engine, 'catsass', 2.6);
      return;
    }

    setMood(engine, engine.mode === 'cat' ? 'love' : 'happy');
    Extras.spawnBurst(engine.particles, 'heart', 0, -60, 3);
    if (engine.mode === 'cat') Sounds.playPurr(1.0); else Sounds.playYip();
    sayFromCategory(engine, engine.mode === 'cat' ? 'catsass' : 'general', 2.4);
  }

  function comeHome(engine) {
    markInteraction(engine);
    setMood(engine, 'excited');
    triggerBounce(engine, 0.9, 10);
    Extras.spawnBurst(engine.particles, 'sparkle', 0, -40, 5);
    if (engine.mode === 'cat') { Sounds.playMeow(); }
    else { Sounds.playYip(); setTimeoutSafe(function () { Sounds.playBark(); }, 220); }
    showCaption(engine, "YOU'RE BACK!!", 3);
  }

  function ownerLooksSad(engine) {
    markInteraction(engine);
    setMood(engine, 'caring');
    sayFromCategory(engine, 'comfort', 4);
    engine.pendingFollowup = { atSeconds: nowSeconds() + 5.5, mood: engine.mode === 'cat' ? 'playful' : 'happy', category: 'selfdep' };
  }

  function alarmStart(engine) {
    engine.alarmActive = true;
    engine.alarmLevel = 0;
    engine.alarmNextAt = nowSeconds();
    setMood(engine, 'wakeupAlarm');
    triggerBounce(engine, 10000, 6);
  }

  function imUp(engine) {
    engine.alarmActive = false;
    engine.alarmLevel = 0;
    engine.bounceStartAt = -1;
    markInteraction(engine);
    setMood(engine, 'proud');
    sayFromCategory(engine, 'general', 2.6);
  }

  function pickedUp(engine) {
    markInteraction(engine);
    setMood(engine, 'cuddly');
    if (engine.mode === 'cat') Sounds.playPurr(1.6); else Sounds.playSigh();
    sayFromCategory(engine, 'comfort', 3);
  }

  function fellOver(engine) {
    markInteraction(engine);
    setMood(engine, 'scared');
    Sounds.playWhine();
    setTimeoutSafe(function () {
      setMood(engine, 'embarrassed');
      Extras.spawn(engine.particles, 'sweat', 26, -70);
      showCaption(engine, 'I meant to do that.', 2.8);
    }, 700);
  }

  function talk(engine) {
    markInteraction(engine);
    var name = engine.mode === 'cat' ? SPIKE.catName : SPIKE.dogName;
    var category = engine.mode === 'cat' ? 'catsass' : 'general';
    var line = Captions.pickRendered(category, name);
    var duration = Math.max(1.0, Math.min(2.6, line.length * 0.045));
    engine.babbleSchedule = Sounds.playBabble(duration);
    engine.babbleStartAt = nowSeconds();
    engine.babbleDurationS = duration;
    showCaption(engine, line, duration + 1.2);
  }

  function rpsReact(engine, result) {
    markInteraction(engine);
    if (result === 'win') {
      setMood(engine, 'sulking');
      sayFromCategory(engine, 'tease', 2.4);
      if (engine.mode === 'cat') Sounds.playHiss(); else Sounds.playWhine();
    } else if (result === 'lose') {
      setMood(engine, 'excited');
      Extras.spawnBurst(engine.particles, 'confetti', 0, -40, 6);
      sayFromCategory(engine, 'greeting', 2.4);
      if (engine.mode === 'cat') Sounds.playTrill(); else Sounds.playGiggle();
    } else {
      setMood(engine, 'curious');
      sayFromCategory(engine, 'general', 2);
    }
  }

  function ignoredNudge(engine) {
    // Manual trigger for the "Ignored for ages" button (also happens
    // automatically in update() if truly left alone).
    setMood(engine, 'sulking');
    sayFromCategory(engine, 'comfort', 2.6);
  }

  function setLook(engine, x, y) {
    engine.lookX = FaceParams.clamp(x, -1, 1);
    engine.lookY = FaceParams.clamp(y, -1, 1);
  }

  function startDemo(engine) {
    engine.demoActive = true;
    engine.demoIndex = 0;
    engine.demoNextAt = nowSeconds();
  }
  function stopDemo(engine) { engine.demoActive = false; }

  function setTimeoutSafe(fn, ms) {
    if (typeof setTimeout === 'function') setTimeout(fn, ms);
  }

  // -----------------------------------------------------------------------
  // Per-frame update. dt in seconds.
  // -----------------------------------------------------------------------
  function update(engine, dt) {
    var t = nowSeconds();

    // --- demo cycling -----------------------------------------------------
    if (engine.demoActive && t >= engine.demoNextAt) {
      var moods = Expressions.MOODS;
      setMood(engine, moods[engine.demoIndex % moods.length]);
      engine.demoIndex++;
      engine.demoNextAt = t + 2.2;
    }

    // --- pending one-shot followup (gentle joke after comfort) ------------
    if (engine.pendingFollowup && t >= engine.pendingFollowup.atSeconds) {
      var fu = engine.pendingFollowup;
      engine.pendingFollowup = null;
      if (!engine.demoActive && !engine.alarmActive) {
        setMood(engine, fu.mood);
        sayFromCategory(engine, fu.category, 2.6);
      }
    }

    // --- alarm escalation ---------------------------------------------------
    if (engine.alarmActive && t >= engine.alarmNextAt) {
      Sounds.playAlarmBark(engine.alarmLevel);
      sayFromCategory(engine, 'alarm', 2.2);
      engine.alarmLevel = Math.min(3, engine.alarmLevel + 1);
      engine.alarmNextAt = t + Math.max(1.4, 3.4 - engine.alarmLevel * 0.6);
    }

    // --- idle life-like motion (skipped while demo/alarm/an action owns
    // the mood -- a scripted action drives its own blinks/tilts) --------
    var fatigue = fatigueScale(engine);
    if (!engine.demoActive && !engine.actionLabel) {
      if (t >= engine.nextBlinkAt) {
        engine.blinkUntil = t + 0.14;
        if (Math.random() < SPIKE.doubleBlinkChance) {
          engine.nextBlinkAt = t + 0.32; // schedule the second half of a double blink soon
        } else {
          engine.nextBlinkAt = t + (randRange(SPIKE.idleBlinkMinMs, SPIKE.idleBlinkMaxMs) / fatigue) / 1000;
        }
      }
      if (t >= engine.nextGlanceAt) {
        engine.glanceUntil = t + 0.6;
        engine.glanceX = randRange(-1, 1) * 0.5;
        engine.glanceY = randRange(-1, 1) * 0.3;
        engine.nextGlanceAt = t + (randRange(SPIKE.idleGlanceMinMs, SPIKE.idleGlanceMaxMs) / fatigue) / 1000;
      }

      // mood drift: happy -> bored -> sulking -> sleepy the longer it's ignored
      var idleFor = t - engine.lastInteractionAt;
      if (idleFor > SPIKE.moodDriftMs / 1000 && t - engine.driftTimerAt > SPIKE.moodDriftMs / 1000) {
        engine.driftTimerAt = t;
        if (engine.driftStage < DRIFT_CHAIN.length - 1 &&
            (engine.mood === 'neutral' || DRIFT_CHAIN.indexOf(engine.mood) !== -1)) {
          engine.driftStage++;
          setMood(engine, DRIFT_CHAIN[engine.driftStage]);
        }
      }
    }

    updateBattery(engine, t, dt);

    // --- breathing bob is handled by the spring target itself; here we
    // just add a small continuous sine so it's alive even mid-spring ----
    var breathe = Math.sin(t * 1.6) * 1.5 * fatigue;

    FaceParams.stepSpring(engine.spring, dt);
    Extras.update(engine.particles, dt);

    if (engine.caption && t >= engine.caption.expiresAt) engine.caption = null;

    engine._breatheOffset = breathe;
    engine._fatigue = fatigue;
    engine._time = t;

    // scripted physical actions and music/dance live in their own files so
    // this one doesn't balloon -- both are optional (only hooked in if the
    // page loaded them).
    if (root.Actions) root.Actions.update(engine, dt, t);
    if (root.Music) root.Music.update(engine, dt, t);
  }

  // Builds the final params object for this frame: spring current values
  // plus transient overlays (blink, glance/look, bounce, babble lip-sync).
  function getFaceParams(engine) {
    var p = FaceParams.mergeParams(engine.spring.current);
    var t = engine._time || nowSeconds();

    // blink overlay (multiplies over the mood's own lid values)
    if (t < engine.blinkUntil) {
      p.blinkL = 1; p.blinkR = 1;
    }

    // look: mouse-follow for most moods, glances layered on top briefly
    var lookX = p.lookX, lookY = p.lookY;
    if (LOOK_FOLLOW_MOODS[engine.mood]) {
      lookX = engine.lookX * 0.8;
      lookY = engine.lookY * 0.6;
    }
    if (t < engine.glanceUntil) {
      lookX = engine.glanceX;
      lookY = engine.glanceY;
    }
    p.lookX = FaceParams.clamp(lookX, -1, 1);
    p.lookY = FaceParams.clamp(lookY, -1, 1);

    p.bobOffset = (p.bobOffset || 0) + (engine._breatheOffset || 0);

    // bounce overlay (comeHome / alarm): a decaying sine bump
    if (engine.bounceStartAt >= 0) {
      var age = t - engine.bounceStartAt;
      if (age < engine.bounceDurationS) {
        var decay = engine.bounceDurationS > 999 ? 1 : Math.max(0, 1 - age / engine.bounceDurationS);
        p.bobOffset += Math.sin(age * 9) * engine.bounceAmp * decay;
      } else if (engine.bounceDurationS < 999) {
        engine.bounceStartAt = -1;
      }
    }

    // babble lip-sync overlay for "Talk"
    if (engine.babbleSchedule && t < engine.babbleStartAt + engine.babbleDurationS) {
      var rel = t - engine.babbleStartAt;
      var open = 0;
      for (var i = 0; i < engine.babbleSchedule.length; i++) {
        var seg = engine.babbleSchedule[i];
        if (rel >= seg.start && rel <= seg.start + seg.dur) { open = 0.55; break; }
      }
      p.mouthOpen = Math.max(p.mouthOpen, open);
    }

    // per-mood idle animation -- damped by battery fatigue so a hungry/weak
    // Spike visibly has less spark, not just a different static face
    applyMoodMotion(p, engine.mood, t, engine._fatigue == null ? 1 : engine._fatigue);

    // munching overlay while charging ("eating happily")
    if (engine.charging) {
      var chompPhase = (t * 3.2) % 1;
      p.mouthOpen = Math.max(p.mouthOpen, chompPhase < 0.4 ? 0.35 : 0.05);
      p.mouthCurve = Math.max(p.mouthCurve, 0.3);
    }

    // scripted physical actions / music-dance overlays, if those modules
    // are loaded -- each may further adjust p (mouth, squash, tilt, bob...)
    if (root.Actions) root.Actions.applyOverlay(engine, p, t);
    if (root.Music) root.Music.applyOverlay(engine, p, t);

    return finalClamp(p);
  }

  var api = {
    createBehaviour: createBehaviour,
    setMood: setMood,
    setMode: setMode,
    setLook: setLook,
    update: update,
    getFaceParams: getFaceParams,
    // events
    pat: pat,
    comeHome: comeHome,
    ownerLooksSad: ownerLooksSad,
    alarmStart: alarmStart,
    imUp: imUp,
    pickedUp: pickedUp,
    fellOver: fellOver,
    talk: talk,
    rpsReact: rpsReact,
    ignoredNudge: ignoredNudge,
    startDemo: startDemo,
    stopDemo: stopDemo,
    showCaption: showCaption,
    sayHi: sayHi,
    greetByTimeOfDay: greetByTimeOfDay,
    setBattery: setBattery,
    setCharging: setCharging,
    // shared helpers exposed for actions.js / music.js to reuse
    sayFromCategory: sayFromCategory,
    triggerBounce: triggerBounce,
    markInteraction: markInteraction,
    anticipate: anticipate,
    finalClamp: finalClamp,
    nowSeconds: nowSeconds
  };

  root.Behaviour = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
