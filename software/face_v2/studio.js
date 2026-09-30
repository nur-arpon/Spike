/*
 * studio.js -- the Face Studio panel: build your own pet face.
 *
 * Each character (Spike / Spicy) has its own current recipe. Presets are
 * plain recipes (recipe.js); the Studio edits one slot at a time, rolls the
 * dice, keeps 3 save slots in localStorage (every access wrapped in
 * try/catch: private windows and blocked storage just mean "no saving"),
 * and exports / imports a short share code.
 *
 * Browser-only (DOM). Not loaded by the Node tests; the recipe logic it
 * relies on (normalize, codes, dice) is tested there.
 */
(function (root) {
  'use strict';
  var KEY = 'spike.faceStudio.v2';
  var SLOT_ORDER = ['frame', 'pattern', 'patternSide', 'muzzle', 'eyeStyle', 'eyeShape', 'lashes', 'brows',
    'nose', 'mouth', 'ears', 'whiskers', 'accessory', 'freckles'];

  var S = {
    mode: 'dog',
    recipes: { dog: null, cat: null },
    slots: [null, null, null],
    onChange: function () {}
  };

  function copy(r) { return JSON.parse(JSON.stringify(r)); }
  function defaultFor(mode) { return copy(Recipe.PRESETS[mode === 'cat' ? SPIKE.catPreset : SPIKE.dogPreset] || Recipe.PRESETS.classic); }
  function $(id) { return document.getElementById(id); }

  // ---------------------------------------------------------------- storage
  function load() {
    try {
      var raw = root.localStorage && root.localStorage.getItem(KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      if (d.dog) S.recipes.dog = Recipe.normalize(d.dog);
      if (d.cat) S.recipes.cat = Recipe.normalize(d.cat);
      if (Array.isArray(d.slots)) S.slots = [0, 1, 2].map(function (i) {
        var s = d.slots[i];
        return s && s.recipe ? { recipe: Recipe.normalize(s.recipe), when: String(s.when || '') } : null;
      });
    } catch (e) { /* storage blocked or corrupt: start fresh */ }
  }
  function save() {
    try { root.localStorage.setItem(KEY, JSON.stringify({ dog: S.recipes.dog, cat: S.recipes.cat, slots: S.slots })); }
    catch (e) { /* no storage available: editing still works for this visit */ }
  }

  function current() { return S.recipes[S.mode]; }
  function setCurrent(r, why) {
    S.recipes[S.mode] = Recipe.normalize(r);
    save();
    refresh();
    S.onChange(S.recipes[S.mode], why);
  }

  // ---------------------------------------------------------------- toast
  var toastTimer = null;
  function toast(msg, isErr) {
    var el = $('studio-toast');
    el.textContent = msg;
    el.className = 'toast' + (isErr ? ' err' : '');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.textContent = ''; }, 2600);
  }

  // ---------------------------------------------------------------- UI
  function thumb(canvas, recipe, mode) {
    var dpr = root.devicePixelRatio || 1, w = 150, h = Math.round(w * 272 / 480);
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr * w / 480, 0, 0, dpr * w / 480, 0, 0);
    FaceDraw.draw(Gfx.create(ctx), Moods.getTarget('neutral', mode), recipe, 0.6);
  }

  function buildPresets() {
    var grid = $('preset-grid');
    grid.innerHTML = '';
    Recipe.PRESET_ORDER.forEach(function (id) {
      var r = Recipe.PRESETS[id];
      var b = document.createElement('button');
      b.className = 'preset';
      b.setAttribute('aria-pressed', 'false');
      b.dataset.preset = id;
      b.title = r.name;
      var cv = document.createElement('canvas');
      var label = document.createElement('span');
      label.textContent = id === 'spicy' ? SPIKE.catName : r.name;
      b.appendChild(cv); b.appendChild(label);
      thumb(cv, r, Recipe.PRESET_KIND[id] === 'cat' ? 'cat' : 'dog');
      b.addEventListener('click', function () { setCurrent(copy(r), 'preset'); });
      grid.appendChild(b);
    });
  }

  function field(labelText, control) {
    var f = document.createElement('div'); f.className = 'field';
    var l = document.createElement('label'); l.textContent = labelText;
    var id = 'f-' + Math.random().toString(36).slice(2, 8);
    control.id = id; l.htmlFor = id;
    f.appendChild(l); f.appendChild(control);
    return f;
  }

  function buildControls() {
    var slotBox = $('slot-fields'); slotBox.innerHTML = '';
    SLOT_ORDER.forEach(function (k) {
      var sel = document.createElement('select');
      sel.dataset.slot = k;
      Recipe.SLOTS[k].forEach(function (opt) {
        var o = document.createElement('option'); o.value = opt; o.textContent = Recipe.OPTION_LABELS[opt] || opt;
        sel.appendChild(o);
      });
      sel.addEventListener('change', function () { var r = copy(current()); r[k] = sel.value; r.name = 'My face'; setCurrent(r, 'slot'); });
      slotBox.appendChild(field(Recipe.SLOT_LABELS[k], sel));
    });

    var colBox = $('color-fields'); colBox.innerHTML = '';
    Recipe.COLORS.forEach(function (k) {
      var w = document.createElement('label'); w.className = 'swatch';
      var inp = document.createElement('input'); inp.type = 'color'; inp.dataset.color = k;
      inp.addEventListener('input', function () { var r = copy(current()); r[k] = inp.value; r.name = 'My face'; setCurrent(r, 'color'); });
      w.appendChild(inp);
      w.appendChild(document.createTextNode(Recipe.COLOR_LABELS[k]));
      colBox.appendChild(w);
    });

    var numBox = $('number-fields'); numBox.innerHTML = '';
    Object.keys(Recipe.NUMBERS).forEach(function (k) {
      var rg = Recipe.NUMBERS[k];
      var row = document.createElement('div'); row.className = 'row';
      var lab = document.createElement('label'); lab.textContent = Recipe.NUMBER_LABELS[k];
      var inp = document.createElement('input'); inp.type = 'range'; inp.min = rg[0]; inp.max = rg[1];
      inp.step = ((rg[1] - rg[0]) / 35).toFixed(4); inp.dataset.number = k;
      var id = 'n-' + k; inp.id = id; lab.htmlFor = id;
      var out = document.createElement('span'); out.className = 'readout'; out.dataset.readout = k;
      inp.addEventListener('input', function () { var r = copy(current()); r[k] = Number(inp.value); r.name = 'My face'; setCurrent(r, 'number'); });
      row.appendChild(lab); row.appendChild(inp); row.appendChild(out);
      numBox.appendChild(row);
    });

    var slotsBox = $('save-slots'); slotsBox.innerHTML = '';
    [0, 1, 2].forEach(function (i) {
      var d = document.createElement('div'); d.className = 'saveslot';
      var sv = document.createElement('button'); sv.className = 'btn'; sv.textContent = 'Save ' + (i + 1); sv.dataset.save = i;
      var ld = document.createElement('button'); ld.className = 'btn primary'; ld.textContent = 'Load ' + (i + 1); ld.dataset.load = i;
      var note = document.createElement('small'); note.dataset.note = i;
      sv.addEventListener('click', function () {
        S.slots[i] = { recipe: copy(current()), when: new Date().toLocaleString() };
        save(); refresh(); toast('Saved to slot ' + (i + 1) + '.');
      });
      ld.addEventListener('click', function () {
        if (!S.slots[i]) return;
        setCurrent(copy(S.slots[i].recipe), 'load'); toast('Loaded slot ' + (i + 1) + '.');
      });
      d.appendChild(sv); d.appendChild(ld); d.appendChild(note);
      slotsBox.appendChild(d);
    });

    $('dice-btn').addEventListener('click', function () { setCurrent(Recipe.randomRecipe(), 'dice'); });
    $('reset-btn').addEventListener('click', function () { setCurrent(defaultFor(S.mode), 'reset'); toast('Back to the default face.'); });
    $('copy-code').addEventListener('click', function () {
      var el = $('share-code'), code = Recipe.toCode(current());
      el.value = code;
      function fallback() { el.focus(); el.select(); try { document.execCommand('copy'); toast('Copied.'); } catch (e) { toast('Select the code and copy it.', true); } }
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(code).then(function () { toast('Copied.'); }, fallback);
        else fallback();
      } catch (e2) { fallback(); }
    });
    $('load-code').addEventListener('click', function () {
      var r = Recipe.fromCode($('share-code').value);
      if (!r) { toast("That code doesn't look right. It starts with SPK1-.", true); return; }
      setCurrent(r, 'code'); toast('Face loaded from the code.');
    });
  }

  function refresh() {
    var r = current();
    var code = Recipe.toCode(r);
    $('studio-for').textContent = 'for ' + (S.mode === 'cat' ? SPIKE.catName : SPIKE.dogName);
    Array.prototype.forEach.call(document.querySelectorAll('.preset'), function (b) {
      b.setAttribute('aria-pressed', String(Recipe.toCode(Recipe.PRESETS[b.dataset.preset]) === code));
    });
    Array.prototype.forEach.call(document.querySelectorAll('[data-slot]'), function (s) { s.value = r[s.dataset.slot]; });
    Array.prototype.forEach.call(document.querySelectorAll('[data-color]'), function (c) { c.value = r[c.dataset.color].toLowerCase(); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-number]'), function (n) {
      n.value = r[n.dataset.number];
      var out = document.querySelector('[data-readout="' + n.dataset.number + '"]');
      if (out) out.textContent = Math.round((r[n.dataset.number] - Recipe.NUMBERS[n.dataset.number][0]) /
        (Recipe.NUMBERS[n.dataset.number][1] - Recipe.NUMBERS[n.dataset.number][0]) * 100) + '%';
    });
    [0, 1, 2].forEach(function (i) {
      var ld = document.querySelector('[data-load="' + i + '"]'), note = document.querySelector('[data-note="' + i + '"]');
      ld.disabled = !S.slots[i];
      note.textContent = S.slots[i] ? S.slots[i].recipe.name : 'empty';
      note.title = S.slots[i] ? S.slots[i].when : '';
    });
    if (document.activeElement !== $('share-code')) $('share-code').value = code;
  }

  S.init = function (opts) {
    S.onChange = opts.onChange || S.onChange;
    S.recipes.dog = defaultFor('dog');
    S.recipes.cat = defaultFor('cat');
    load();
    buildPresets();
    buildControls();
    refresh();
  };
  S.setMode = function (mode) { S.mode = mode === 'cat' ? 'cat' : 'dog'; refresh(); };
  S.current = function (mode) { return S.recipes[mode || S.mode]; };
  S.refreshNames = function () { buildPresets(); refresh(); };

  root.Studio = S;
})(window);
