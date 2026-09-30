/*
 * face_params.js -- the parametric face model + spring/tween interpolation.
 *
 * A "face" is a FLAT object of plain numbers (no nesting) so it can be
 * ported line-by-line to a C struct on the ESP32 later. Every field has a
 * default in FACE_DEFAULTS. Presets (expressions.js) only need to specify
 * the fields that differ from the default -- mergeParams() fills the rest.
 *
 * Interpolation is done with simple critically-damped-ish springs, one
 * per field, each with its own stiffness/damping so fast things (blink)
 * snap quickly while slow things (face tilt, look) drift smoothly. This
 * is what gives "anticipation before big moves" -- a spring overshoots
 * slightly before settling, which reads as alive rather than robotic.
 *
 * Classic script, no ES modules. Works in the browser (attaches to
 * window) and in plain Node for the smoke test (attaches to global /
 * module.exports).
 */
(function (root) {
  'use strict';

  // ---------------------------------------------------------------------
  // Small math helpers
  // ---------------------------------------------------------------------
  function clamp(v, lo, hi) {
    return v < lo ? lo : (v > hi ? hi : v);
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  // ---------------------------------------------------------------------
  // Default flat face. Units: pixels / degrees / 0..1 unless noted.
  // Coordinate origin for eye offsets is the eye's own resting slot;
  // (0,0) means centred in its default position.
  // ---------------------------------------------------------------------
  var FACE_DEFAULTS = {
    // --- eyes (shared shape applied to both, then offset per side) ------
    eyeW: 78,
    eyeH: 88,
    eyeRadius: 30,
    eyeGap: 46,          // distance between the inner edges of the eyes
    eyeYOffset: 0,        // shared vertical offset for both eyes
    eyeLXOffset: 0,        // extra per-eye offsets (curious/wink use these)
    eyeLYOffset: 0,
    eyeRXOffset: 0,
    eyeRYOffset: 0,
    eyeLScale: 1,         // per-eye size multiplier (curious = one eye bigger)
    eyeRScale: 1,

    // --- lids: 0 = fully open, 1 = fully covers the eye -------------------
    topLidL: 0,
    topLidR: 0,
    bottomLidL: 0,
    bottomLidR: 0,
    // slant in degrees, positive = outer corner up (angry), negative = down (sad)
    topLidAngleL: 0,
    topLidAngleR: 0,
    bottomLidAngleL: 0,
    bottomLidAngleR: 0,

    // --- pupils (0 = no pupil drawn i.e. plain white eye) -----------------
    pupilSize: 0.42,       // fraction of eye height
    pupilXOffset: 0,
    pupilYOffset: 0,
    slitPupil: 0,         // 0 = round pupil, 1 = fully slit (cat)
    highlightSize: 0.34,
    highlightOpacity: 0.9,

    // --- blink: 0 = open, 1 = closed (multiplies over topLid/bottomLid) --
    blinkL: 0,
    blinkR: 0,

    // --- squash & stretch, look, tilt -------------------------------------
    squashX: 1,
    squashY: 1,
    lookX: 0,             // -1..1, driven by mouse tracking
    lookY: 0,             // -1..1
    faceTilt: 0,          // degrees, whole-face rotation

    // --- mouth -------------------------------------------------------------
    mouthCurve: 0.15,       // -1 (frown) .. 1 (grin)
    mouthOpen: 0,         // 0..1
    mouthWidth: 70,
    mouthYOffset: 0,
    tongueOut: 0,         // 0..1
    pantSpeed: 0,         // 0 = not panting, >0 = pant animation speed
    mouthWobble: 0,         // 0..1 amount of wobble (sad quiver)
    catOmega: 0,         // 0..1 morph to cat "w" mouth shape
    smirkSide: 0,         // -1 (left corner up) .. 1 (right corner up)

    // --- extras baked into the face itself --------------------------------
    blushOpacity: 0,
    tearsOpacity: 0,
    eyelashesOpacity: 0,   // cat only
    whiskersOpacity: 0,   // cat only

    // --- idle motion ---------------------------------------------------
    bobOffset: 0,          // vertical breathing bob, px
    breathScale: 1,          // subtle whole-face scale for breathing

    // --- style-specific decorations (only drawn if the active style has
    // the matching feature flag -- see styles.js) ------------------------
    earAngleL: 22,          // degrees, droop angle for a floppy ear (0 = perked up)
    earAngleR: 22,
    noseWiggle: 0           // 0..1, small sniff jitter on the nose
  };

  // Per-field spring tuning: [stiffness, damping]. Higher stiffness =
  // faster; higher damping = less overshoot. Fields not listed use
  // DEFAULT_SPRING. Blink is intentionally very stiff+snappy.
  var DEFAULT_SPRING = [170, 18];
  var SPRING_TUNING = {
    blinkL: [420, 24],
    blinkR: [420, 24],
    topLidL: [420, 24],
    topLidR: [420, 24],
    bottomLidL: [420, 24],
    bottomLidR: [420, 24],
    lookX: [140, 14],
    lookY: [140, 14],
    faceTilt: [90, 13],
    squashX: [260, 14],   // snappy but with a touch of overshoot (bounce)
    squashY: [260, 14],
    bobOffset: [40, 10],
    breathScale: [40, 10]
  };

  function getDefaults() {
    // Return a fresh copy so callers can't mutate the shared template.
    var out = {};
    for (var k in FACE_DEFAULTS) out[k] = FACE_DEFAULTS[k];
    return out;
  }

  // Merge one or more override objects onto a copy of the defaults.
  // mergeParams(overrides) or mergeParams(base, overrides)
  function mergeParams() {
    var out = getDefaults();
    for (var i = 0; i < arguments.length; i++) {
      var src = arguments[i];
      if (!src) continue;
      for (var k in src) {
        if (Object.prototype.hasOwnProperty.call(src, k)) out[k] = src[k];
      }
    }
    return out;
  }

  // ---------------------------------------------------------------------
  // Spring state: holds current value + velocity per field, and the
  // current target. step() advances one physics tick (dt in seconds).
  // ---------------------------------------------------------------------
  function createSpringState(initial) {
    var current = initial ? mergeParams(initial) : getDefaults();
    var velocity = {};
    for (var k in current) velocity[k] = 0;
    return { current: current, velocity: velocity, target: mergeParams(current) };
  }

  function setTarget(state, targetParams) {
    // Any field missing from targetParams falls back to FACE_DEFAULTS,
    // so a preset only needs to name the fields it cares about.
    state.target = mergeParams(targetParams);
  }

  // Advance the spring simulation by dt seconds. Returns state.current
  // (same object, mutated in place) ready to hand to draw().
  function stepSpring(state, dt) {
    dt = clamp(dt, 0, 0.05); // guard against huge dt after a tab was hidden
    var cur = state.current, vel = state.velocity, tgt = state.target;
    for (var k in tgt) {
      var tuning = SPRING_TUNING[k] || DEFAULT_SPRING;
      var stiffness = tuning[0], damping = tuning[1];
      var x = cur[k] === undefined ? tgt[k] : cur[k];
      var v = vel[k] || 0;
      var displacement = x - tgt[k];
      var springForce = -stiffness * displacement;
      var dampingForce = -damping * v;
      var accel = springForce + dampingForce;
      v += accel * dt;
      x += v * dt;
      cur[k] = x;
      vel[k] = v;
    }
    return cur;
  }

  // Snap instantly to a target (used on first load / mode switch so we
  // don't spring in from zeroed defaults).
  function snapTo(state, targetParams) {
    setTarget(state, targetParams);
    for (var k in state.target) {
      state.current[k] = state.target[k];
      state.velocity[k] = 0;
    }
    return state.current;
  }

  var api = {
    FACE_DEFAULTS: FACE_DEFAULTS,
    clamp: clamp,
    lerp: lerp,
    getDefaults: getDefaults,
    mergeParams: mergeParams,
    createSpringState: createSpringState,
    setTarget: setTarget,
    stepSpring: stepSpring,
    snapTo: snapTo
  };

  root.FaceParams = api;

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }
})(typeof window !== 'undefined' ? window : global);
