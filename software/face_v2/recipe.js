/*
 * recipe.js -- Face Studio recipes: the slot catalogue, the presets, the
 * dice (random face), validation and short share codes.
 *
 * A face is a small flat JSON RECIPE. Every feature is a SLOT with a fixed
 * list of options. The renderer (face_draw.js) reads the recipe for LOOKS
 * and the face state (params.js) for MOOD, so any recipe animates every
 * mood. The robot stores the recipe; the phone app / share codes move it.
 *
 * Classic script: window.Recipe, or module.exports in Node.
 */
(function (root) {
  'use strict';

  // ---------------------------------------------------------------------
  // The slot catalogue. Order matters: share codes store the index.
  // NEVER reorder or delete an option -- only append (codes must survive).
  // ---------------------------------------------------------------------
  var SLOTS = {
    frame:     ['full', 'head'],
    pattern:   ['plain', 'patch', 'spots', 'tabby', 'calico', 'blaze', 'mask', 'tux'],
    muzzle:    ['none', 'round', 'wide'],
    eyeStyle:  ['gloss', 'iris', 'cat', 'glow'],
    eyeShape:  ['oval', 'round', 'almond', 'soft', 'droop'],
    lashes:    ['none', 'flick', 'full'],
    brows:     ['none', 'dots', 'arcs', 'bold'],
    nose:      ['pup', 'button', 'cat', 'heart', 'bean'],
    mouth:     ['pup', 'omega', 'simple'],
    ears:      ['floppy', 'pointy', 'round', 'bear', 'bunny', 'fold', 'none'],
    whiskers:  ['none', 'short', 'long'],
    accessory: ['none', 'bow', 'bandana', 'glasses', 'hat', 'flower'],
    freckles:  ['no', 'yes'],
    patternSide: ['left', 'right']
  };

  // Human labels for the Studio UI.
  var SLOT_LABELS = {
    frame: 'Face frame', pattern: 'Fur pattern', muzzle: 'Muzzle', eyeStyle: 'Eye style',
    eyeShape: 'Eye shape', lashes: 'Eyelashes', brows: 'Eyebrows', nose: 'Nose', mouth: 'Mouth',
    ears: 'Ears', whiskers: 'Whiskers', accessory: 'Accessory', freckles: 'Freckles',
    patternSide: 'Pattern side'
  };
  var OPTION_LABELS = {
    full: 'Full screen', head: 'Sticker head', plain: 'Plain', patch: 'Eye patch', spots: 'Spots',
    tabby: 'Tabby stripes', calico: 'Calico', blaze: 'Beagle blaze', mask: 'Husky mask', tux: 'Tuxedo',
    none: 'None', round: 'Round', wide: 'Wide', gloss: 'Glossy', iris: 'Anime iris', cat: 'Cat',
    glow: 'Glow (robot)', oval: 'Oval', almond: 'Almond', soft: 'Soft square', droop: 'Puppy droop',
    flick: 'Flick', dots: 'Dots', arcs: 'Arcs', bold: 'Bold', pup: 'Puppy', button: 'Button',
    heart: 'Heart', bean: 'Bean', omega: 'Kitty ω', simple: 'Simple', floppy: 'Floppy', pointy: 'Pointy',
    bear: 'Bear', bunny: 'Bunny', fold: 'Folded', short: 'Short', long: 'Long', bow: 'Bow',
    bandana: 'Bandana', glasses: 'Glasses', hat: 'Party hat', flower: 'Flower', no: 'No', yes: 'Yes',
    left: 'Left', right: 'Right'
  };

  // Colour slots (hex). Order matters for share codes (append only).
  var COLORS = ['bg', 'fur', 'fur2', 'fur3', 'muzzleColor', 'eyeColor', 'irisColor', 'noseColor',
    'lineColor', 'tongueColor', 'earColor', 'earInner', 'blushColor', 'browColor', 'whiskerColor', 'accColor'];
  var COLOR_LABELS = {
    bg: 'Background', fur: 'Fur', fur2: 'Pattern colour', fur3: 'Third colour', muzzleColor: 'Muzzle',
    eyeColor: 'Eyes', irisColor: 'Iris', noseColor: 'Nose', lineColor: 'Mouth line',
    tongueColor: 'Tongue', earColor: 'Ears', earInner: 'Inner ear', blushColor: 'Blush',
    browColor: 'Brows', whiskerColor: 'Whiskers', accColor: 'Accessory'
  };

  // Number slots: [min, max]. Stored in codes as one base-36 digit (0..35).
  var NUMBERS = { eyeSize: [0.8, 1.25], eyeSpacing: [0.86, 1.14], mouthRest: [0, 0.6], blush: [0, 0.8], dim: [0, 0.6] };
  var NUMBER_LABELS = { eyeSize: 'Eye size', eyeSpacing: 'Eye spacing', mouthRest: 'Resting smile', blush: 'Blush', dim: 'Dim (night)' };

  // ---------------------------------------------------------------------
  // Base recipe = Classic Pup (the DEFAULT face, from the owner's photo).
  // ---------------------------------------------------------------------
  var BASE = {
    name: 'Classic Pup',
    frame: 'full', bg: '#BFE3F2',
    fur: '#F3DDBF', fur2: '#C98A5E', fur3: '#8A5A3C', pattern: 'patch', patternSide: 'left',
    muzzle: 'none', muzzleColor: '#FFF4E4',
    eyeStyle: 'gloss', eyeShape: 'oval', eyeColor: '#2E2320', irisColor: '#7A4B2A',
    eyeSize: 1.0, eyeSpacing: 1.0, lashes: 'none', brows: 'none', browColor: '#A8714D',
    nose: 'pup', noseColor: '#2E2320',
    mouth: 'pup', mouthRest: 0.55, lineColor: '#4A2E24', tongueColor: '#E0564F',
    ears: 'floppy', earColor: '#C98A5E', earInner: '#B07650',
    blush: 0.22, blushColor: '#FF8C8C', freckles: 'no',
    whiskers: 'none', whiskerColor: '#8A6A55',
    accessory: 'none', accColor: '#E84A5F',
    dim: 0
  };

  function withBase(over) {
    var r = {};
    for (var k in BASE) r[k] = BASE[k];
    for (var j in over) r[j] = over[j];
    return r;
  }

  // ---------------------------------------------------------------------
  // CONCEPT recipes (design exploration, see DESIGN.md). The winners became
  // Classic Pup / Spicy; the good runners-up stay as extra presets.
  // ---------------------------------------------------------------------
  var CONCEPTS = {
    pupA_plush: withBase({ name: 'Pup A: Plush Toy' }),
    pupB_sticker: withBase({
      name: 'Pup B: Sticker Buddy', frame: 'head', bg: '#BFE3F2',
      muzzle: 'round', muzzleColor: '#FFF7EE', eyeShape: 'round', eyeSize: 0.86, eyeSpacing: 1.08,
      brows: 'dots', browColor: '#B98159', nose: 'button', mouth: 'omega', mouthRest: 0.25,
      ears: 'floppy', blush: 0.45
    }),
    pupC_anime: withBase({
      name: 'Pup C: Anime Sparkle', fur: '#F6E4CB', eyeStyle: 'iris', eyeShape: 'oval', eyeSize: 1.1,
      irisColor: '#8B5A3C', eyeColor: '#3A2A24', lashes: 'none', brows: 'arcs', browColor: '#9A6444',
      nose: 'button', mouth: 'simple', mouthRest: 0.35, blush: 0.35, ears: 'floppy'
    }),
    catA_calico: withBase({
      name: 'Cat A: Calico Sass', fur: '#FBF3E8', fur2: '#E8964A', fur3: '#4A3B36', pattern: 'calico',
      eyeStyle: 'cat', eyeShape: 'almond', irisColor: '#8CCB5E', eyeColor: '#2A2226', eyeSize: 1.05,
      lashes: 'flick', nose: 'cat', noseColor: '#F28CA0', mouth: 'omega', mouthRest: 0.05,
      lineColor: '#5A3A3A', ears: 'pointy', earColor: '#E8964A', earInner: '#F6B3C0',
      whiskers: 'long', whiskerColor: '#9A8A80', accessory: 'bow', accColor: '#FF5C9A', blush: 0.3
    }),
    catB_kitten: withBase({
      name: 'Cat B: Kitten Plush', fur: '#DCD6D2', fur2: '#A99E97', pattern: 'tabby',
      eyeStyle: 'gloss', eyeShape: 'round', eyeSize: 1.02, lashes: 'flick',
      nose: 'heart', noseColor: '#F28CA0', mouth: 'omega', mouthRest: 0.05, lineColor: '#5A4A48',
      ears: 'pointy', earColor: '#DCD6D2', earInner: '#F6B3C0', whiskers: 'short',
      whiskerColor: '#8E8580', blush: 0.5
    }),
    catC_tuxedo: withBase({
      name: 'Cat C: Tuxedo Glam', fur: '#2F2C38', fur2: '#F4F0EC', pattern: 'tux',
      eyeStyle: 'cat', eyeShape: 'round', irisColor: '#D4E157', eyeColor: '#15121A', eyeSize: 1.12,
      lashes: 'full', nose: 'cat', noseColor: '#F59AB0', mouth: 'omega', mouthRest: 0.05,
      lineColor: '#3A2E36', ears: 'pointy', earColor: '#2F2C38', earInner: '#F2A3B8',
      whiskers: 'long', whiskerColor: '#F4F0EC', blush: 0.35, blushColor: '#FF7FA8',
      browColor: '#F4F0EC'
    })
  };

  // ---------------------------------------------------------------------
  // PRESETS (filled in after the concept pick -- see bottom of file).
  // ---------------------------------------------------------------------
  var PRESETS = {};
  var PRESET_ORDER = [];

  function addPreset(id, recipe) { PRESETS[id] = recipe; PRESET_ORDER.push(id); }

  // ---------------------------------------------------------------------
  // Validation: unknown / missing values fall back to Classic Pup's.
  // ---------------------------------------------------------------------
  var HEX = /^#[0-9a-fA-F]{6}$/;
  function normalize(r) {
    r = r || {};
    var out = {};
    for (var k in BASE) out[k] = BASE[k];
    for (var s in SLOTS) if (SLOTS[s].indexOf(r[s]) !== -1) out[s] = r[s];
    for (var i = 0; i < COLORS.length; i++) { var c = COLORS[i]; if (HEX.test(r[c] || '')) out[c] = r[c].toUpperCase(); }
    for (var n in NUMBERS) {
      var v = Number(r[n]);
      if (isFinite(v)) out[n] = Math.max(NUMBERS[n][0], Math.min(NUMBERS[n][1], v));
    }
    if (typeof r.name === 'string' && r.name.trim()) out.name = r.name.trim().slice(0, 40);
    return out;
  }

  // ---------------------------------------------------------------------
  // Share codes:  SPK1-<slots>-<numbers>-<colours>
  //   slots   : one base-36 digit per SLOTS key (in key order)
  //   numbers : one base-36 digit per NUMBERS key (quantised 0..35)
  //   colours : 6 hex digits per COLORS entry, concatenated
  // ---------------------------------------------------------------------
  var SLOT_KEYS = Object.keys(SLOTS);
  var NUM_KEYS = Object.keys(NUMBERS);

  function toCode(recipe) {
    var r = normalize(recipe);
    var s = '';
    for (var i = 0; i < SLOT_KEYS.length; i++) s += Math.max(0, SLOTS[SLOT_KEYS[i]].indexOf(r[SLOT_KEYS[i]])).toString(36);
    var n = '';
    for (var j = 0; j < NUM_KEYS.length; j++) {
      var rg = NUMBERS[NUM_KEYS[j]];
      n += Math.round((r[NUM_KEYS[j]] - rg[0]) / (rg[1] - rg[0]) * 35).toString(36);
    }
    var c = '';
    for (var k = 0; k < COLORS.length; k++) c += r[COLORS[k]].slice(1).toUpperCase();
    return 'SPK1-' + s + '-' + n + '-' + c;
  }

  // Returns a normalized recipe, or null if the code is not valid.
  function fromCode(code) {
    if (typeof code !== 'string') return null;
    var parts = code.trim().split('-');
    if (parts.length !== 4 || parts[0].toUpperCase() !== 'SPK1') return null;
    var s = parts[1].toLowerCase(), n = parts[2].toLowerCase(), c = parts[3];
    if (s.length < SLOT_KEYS.length || n.length < NUM_KEYS.length || c.length < COLORS.length * 6) return null;
    if (!/^[0-9a-z]+$/.test(s) || !/^[0-9a-z]+$/.test(n) || !/^[0-9a-fA-F]+$/.test(c)) return null;
    var r = { name: 'Shared face' };
    for (var i = 0; i < SLOT_KEYS.length; i++) {
      var opts = SLOTS[SLOT_KEYS[i]], idx = parseInt(s[i], 36);
      if (!(idx >= 0 && idx < opts.length)) return null;
      r[SLOT_KEYS[i]] = opts[idx];
    }
    for (var j = 0; j < NUM_KEYS.length; j++) {
      var rg = NUMBERS[NUM_KEYS[j]], q = parseInt(n[j], 36);
      if (!(q >= 0 && q <= 35)) return null;
      r[NUM_KEYS[j]] = rg[0] + (rg[1] - rg[0]) * q / 35;
    }
    for (var k = 0; k < COLORS.length; k++) r[COLORS[k]] = '#' + c.substr(k * 6, 6);
    return normalize(r);
  }

  // ---------------------------------------------------------------------
  // Dice: a random but HARMONIOUS face. Colours come from curated palettes
  // so random faces still look like a product, not a ransom note.
  // ---------------------------------------------------------------------
  var FUR_PALETTES = [
    // [fur, fur2, fur3, ears]
    ['#F3DDBF', '#C98A5E', '#8A5A3C', '#C98A5E'],
    ['#FFF6EC', '#E8964A', '#4A3B36', '#E8964A'],
    ['#E9D2B0', '#8B5E3C', '#FFF7EE', '#8B5E3C'],
    ['#DCD6D2', '#A99E97', '#6E6560', '#A99E97'],
    ['#F7E7D0', '#3D3431', '#FFFFFF', '#3D3431'],
    ['#FFE2C6', '#F29A5B', '#FFF6EC', '#F29A5B'],
    ['#EFE3F7', '#B8A0D6', '#7C62A8', '#B8A0D6'],
    ['#D9EEF7', '#8CC3DD', '#4F87A6', '#8CC3DD'],
    ['#2F2C38', '#F4F0EC', '#9A93A6', '#2F2C38'],
    ['#C9B8A6', '#6B5A4E', '#F2EAE0', '#6B5A4E']
  ];
  var EYE_COLORS = ['#2E2320', '#23272E', '#3B2A40', '#1F2A2A'];
  var IRIS_COLORS = ['#8B5A3C', '#7BC96F', '#5FB3E6', '#D4E157', '#B784E0', '#E6A04A'];
  var ACC_COLORS = ['#E84A5F', '#FF5C9A', '#4A90E2', '#FFC43D', '#57C785', '#9B6BDB'];
  var BG_COLORS = ['#BFE3F2', '#F7D9E3', '#E3F2C9', '#FBE7C2', '#D9D2F2'];

  function pick(list, rnd) { return list[Math.floor(rnd() * list.length) % list.length]; }

  function randomRecipe(rnd) {
    rnd = rnd || Math.random;
    var pal = pick(FUR_PALETTES, rnd);
    var cat = rnd() < 0.4;
    var r = {
      name: 'Dice face',
      frame: rnd() < 0.8 ? 'full' : 'head',
      bg: pick(BG_COLORS, rnd),
      fur: pal[0], fur2: pal[1], fur3: pal[2], earColor: pal[3],
      pattern: pick(SLOTS.pattern, rnd), patternSide: pick(SLOTS.patternSide, rnd),
      muzzle: pick(SLOTS.muzzle, rnd), muzzleColor: '#FFF6EC',
      eyeStyle: pick(['gloss', 'gloss', 'iris', 'cat', 'glow'], rnd),
      eyeShape: pick(SLOTS.eyeShape, rnd),
      eyeColor: pick(EYE_COLORS, rnd), irisColor: pick(IRIS_COLORS, rnd),
      eyeSize: 0.85 + rnd() * 0.35, eyeSpacing: 0.9 + rnd() * 0.2,
      lashes: cat ? pick(['flick', 'full'], rnd) : pick(['none', 'none', 'flick'], rnd),
      brows: pick(SLOTS.brows, rnd), browColor: pal[1],
      nose: cat ? pick(['cat', 'heart'], rnd) : pick(['pup', 'button', 'bean'], rnd),
      noseColor: cat ? '#F28CA0' : pick(EYE_COLORS, rnd),
      mouth: cat ? 'omega' : pick(['pup', 'pup', 'simple', 'omega'], rnd),
      mouthRest: rnd() * 0.45, lineColor: '#4A2E24', tongueColor: '#E0564F',
      ears: cat ? 'pointy' : pick(SLOTS.ears, rnd), earInner: '#F2A3B0',
      blush: 0.1 + rnd() * 0.5, blushColor: '#FF8C9A', freckles: rnd() < 0.2 ? 'yes' : 'no',
      whiskers: cat ? pick(['short', 'long'], rnd) : pick(['none', 'none', 'short'], rnd),
      whiskerColor: pal[2],
      accessory: pick(SLOTS.accessory, rnd), accColor: pick(ACC_COLORS, rnd),
      dim: 0
    };
    if (r.eyeStyle === 'glow') { r.fur = '#12151C'; r.eyeColor = pick(['#FFFFFF', '#7FE3FF', '#FFD27F'], rnd); r.pattern = 'plain'; r.muzzle = 'none'; }
    return normalize(r);
  }

  // Seeded RNG (mulberry32) so tests and contact sheets are repeatable.
  function seeded(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  // ---------------------------------------------------------------------
  // The presets (all plain recipes). 'kind' only groups them in the UI;
  // any recipe works for either character.
  // ---------------------------------------------------------------------
  var PRESET_KIND = {};
  function preset(id, kind, recipe) { addPreset(id, normalize(recipe)); PRESET_KIND[id] = kind; }

  preset('classic', 'dog', withBase({ name: 'Classic Pup' }));
  preset('spicy', 'cat', withBase(copyOf(CONCEPTS.catA_calico, { name: 'Spicy' })));
  preset('beagle', 'dog', withBase({
    name: 'Beagle', fur: '#C8874E', fur2: '#FFF7EE', pattern: 'blaze', eyeShape: 'droop',
    earColor: '#6E4326', earInner: '#5A361E', nose: 'bean', noseColor: '#2A201C', blush: 0.15,
    lineColor: '#3A2A22'
  }));
  preset('husky', 'dog', withBase({
    name: 'Husky', fur: '#F4F6F8', fur2: '#6B7280', pattern: 'mask', eyeStyle: 'iris', eyeShape: 'almond',
    irisColor: '#6EC6F2', eyeColor: '#1F2430', ears: 'pointy', earColor: '#6B7280', earInner: '#F2C4C4',
    nose: 'pup', noseColor: '#1F2430', lineColor: '#2E3440', blush: 0.18, eyeSize: 1.02
  }));
  preset('minimal', 'dog', withBase({
    name: 'Minimal', fur: '#0E1117', pattern: 'plain', eyeStyle: 'glow', eyeShape: 'soft',
    eyeColor: '#FFFFFF', nose: 'button', noseColor: '#D8DEE9', mouth: 'simple', mouthRest: 0.25,
    lineColor: '#FFFFFF', tongueColor: '#FF7A8A', ears: 'none', blush: 0.28, blushColor: '#FF6B8A'
  }));
  preset('night', 'dog', withBase({
    name: 'Night', fur: '#0B0D14', pattern: 'plain', eyeStyle: 'glow', eyeShape: 'soft',
    eyeColor: '#FFB86B', nose: 'button', noseColor: '#9A7654', mouth: 'simple', mouthRest: 0.15,
    lineColor: '#FFB86B', tongueColor: '#C8645A', ears: 'none', blush: 0.2, blushColor: '#C86A5A', dim: 0.35
  }));
  preset('anime', 'dog', withBase(copyOf(CONCEPTS.pupC_anime, {
    name: 'Anime Pup', browColor: '#6B4430', mouth: 'pup', mouthRest: 0.4, blush: 0.4
  })));
  preset('sticker', 'dog', withBase(copyOf(CONCEPTS.pupB_sticker, { name: 'Sticker Buddy' })));
  preset('tuxedo', 'cat', withBase(copyOf(CONCEPTS.catC_tuxedo, { name: 'Midnight Tux' })));

  function copyOf(src, over) {
    var o = {};
    for (var k in src) o[k] = src[k];
    for (var j in over) o[j] = over[j];
    return o;
  }

  var api = {
    PRESET_KIND: PRESET_KIND,
    SLOTS: SLOTS, SLOT_LABELS: SLOT_LABELS, OPTION_LABELS: OPTION_LABELS,
    COLORS: COLORS, COLOR_LABELS: COLOR_LABELS, NUMBERS: NUMBERS, NUMBER_LABELS: NUMBER_LABELS,
    BASE: BASE, CONCEPTS: CONCEPTS, PRESETS: PRESETS, PRESET_ORDER: PRESET_ORDER,
    withBase: withBase, addPreset: addPreset, normalize: normalize,
    toCode: toCode, fromCode: fromCode, randomRecipe: randomRecipe, seeded: seeded
  };
  root.Recipe = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
