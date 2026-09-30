/*
 * face_draw.js -- the PURE face renderer:  draw(G, state, recipe, t, opts)
 *
 *   G       a Gfx wrapper (gfx.js) -- the only way pixels are made
 *   state   the face state (params.js): the MOOD, as plain numbers
 *   recipe  the Face Studio recipe (recipe.js): the LOOK
 *   t       seconds, only for cyclic motion (panting, tear wobble, sparkle)
 *
 * Same inputs -> same pixels. No DOM, no timers, no randomness (anything
 * "random", like spot positions, is a fixed table). That is what lets the
 * smoke test draw every mood x every recipe, and the ESP32 port copy it.
 *
 * LAYOUT (owner's hard rules, 480x272):
 *   eye centres at 45% of the height (rule: 42-48%)
 *   nose centre at 62%               (rule: 60-65%)
 *   mouth + tongue inside 70-89.5%   (rule: 70-90%)
 *   NOTHING joins the two eyes (no brow bridge, lid band or bar).
 *
 * EYELIDS: the eye is drawn only between its two lid edges, computed
 * analytically per column (a "band"), so the lid IS the skin underneath --
 * cream fur, the brown eye patch, a husky mask, whatever the recipe put
 * there. No black bars, no clip(), fully portable.
 *
 * Draw order: fur -> head transform (tilt/bob/squash) -> pattern -> muzzle
 * -> ears -> cheeks -> whiskers -> eyes -> brows -> nose -> mouth ->
 * decals -> accessories -> dim.
 */
(function (root) {
  'use strict';

  var isNode = typeof window === 'undefined';
  var Gfx = root.Gfx || (isNode ? require('./gfx.js') : null);
  var FP = root.FaceParams || (isNode ? require('./params.js') : null);
  var RecipeLib = root.Recipe || (isNode ? require('./recipe.js') : null);

  var W = 480, H = 272, CX = W / 2;
  var PI = Math.PI, TAU = PI * 2, DEG = PI / 180;

  var LAYOUT = {
    eyeY: 0.45 * H,     // 122.4
    eyeDX: 96,          // centre -> eye centre at spacing 1
    noseY: 0.62 * H,    // 168.6
    mouthY: 0.745 * H,  // 202.6 : top-centre of the mouth (bottom of the philtrum)
    mouthMaxY: 0.892 * H, // 242.6 : nothing of the mouth/tongue goes below this
    pivotY: 0.64 * H    // head tilt / squash pivot (between nose and eyes)
  };

  // Eye half-sizes (a = half width, b = half height) per shape at size 1,
  // and the slant (deg, + = outer corner up).
  var EYE_SHAPES = {
    oval:   { a: 36, b: 44, slant: 0 },
    round:  { a: 40, b: 40, slant: 0 },
    almond: { a: 41, b: 33, slant: 9 },
    soft:   { a: 37, b: 40, slant: 0 },
    droop:  { a: 35, b: 41, slant: -8 }
  };

  var clamp = FP.clamp, lerp = FP.lerp, smoothstep = FP.smoothstep;
  var mix = Gfx.mix, shade = Gfx.shade;

  // -------------------------------------------------------------------
  // Geometry helpers
  // -------------------------------------------------------------------

  // Cosine-spaced samples across [x0, x1]: dense near the ends, where round
  // shapes are steep, so bands look smooth with few columns.
  function cosXs(x0, x1, n) {
    var xs = [];
    for (var i = 0; i <= n; i++) xs.push(x0 + (x1 - x0) * (1 - Math.cos(PI * i / n)) / 2);
    return xs;
  }

  // BAND: fill between two curves over sampled xs. Columns where top >= bot
  // are closed; each open run becomes one x-monotone polygon (on the ESP32:
  // two fillTriangle per column). This single primitive gives us eyelids,
  // an open mouth under a wavy lip, a tongue inside the mouth and a
  // wobbling waterline -- all without clip().
  function band(G, xs, tops, bots, color, alpha) {
    var n = xs.length, run = null;
    function flush() {
      if (run && run.top.length >= 4) {
        var pts = run.top.slice();
        for (var k = run.bot.length - 2; k >= 0; k -= 2) pts.push(run.bot[k], run.bot[k + 1]);
        G.mpoly(pts, color, alpha);
      }
      run = null;
    }
    for (var i = 0; i < n; i++) {
      var open = bots[i] - tops[i] > 0.01;
      if (open) {
        if (!run) {
          run = { top: [], bot: [] };
          if (i > 0) { // crossing into open: pointed start
            var d0 = bots[i - 1] - tops[i - 1], d1 = bots[i] - tops[i];
            var f = d0 / (d0 - d1);
            var xc = xs[i - 1] + (xs[i] - xs[i - 1]) * f, yc = tops[i - 1] + (tops[i] - tops[i - 1]) * f;
            run.top.push(xc, yc); run.bot.push(xc, yc);
          }
        }
        run.top.push(xs[i], tops[i]); run.bot.push(xs[i], bots[i]);
      } else if (run) {
        var e0 = bots[i - 1] - tops[i - 1], e1 = bots[i] - tops[i];
        var g = e0 / (e0 - e1);
        var xe = xs[i - 1] + (xs[i] - xs[i - 1]) * g, ye = tops[i - 1] + (tops[i] - tops[i - 1]) * g;
        run.top.push(xe, ye); run.bot.push(xe, ye);
        flush();
      }
    }
    flush();
  }

  // An ellipse drawn only inside a visible region given by functions
  // vTop(x), vBot(x) (e.g. an iris inside the eyelids).
  function clippedEllipse(G, cx, cy, rx, ry, vTop, vBot, color, alpha, n) {
    if (!(rx > 0.2) || !(ry > 0.2)) return;
    var xs = cosXs(cx - rx, cx + rx, n || 18), tops = [], bots = [], inside = true;
    for (var i = 0; i < xs.length; i++) {
      var q = (xs[i] - cx) / rx, h = ry * Math.sqrt(Math.max(0, 1 - q * q));
      var t0 = cy - h, b0 = cy + h, vt = vTop(xs[i]), vb = vBot(xs[i]);
      if (vt > t0 + 0.01 || vb < b0 - 0.01) inside = false;
      tops.push(Math.max(t0, vt)); bots.push(Math.min(b0, vb));
    }
    if (inside) G.ellipse(cx, cy, rx, ry, 0, color, alpha);
    else band(G, xs, tops, bots, color, alpha);
  }

  // Convex hull (monotone chain) of a flat point list -> flat convex polygon.
  function hull(pts) {
    var P = [];
    for (var i = 0; i < pts.length; i += 2) P.push([pts[i], pts[i + 1]]);
    P.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; });
    function cross(o, a, b) { return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]); }
    var lo = [], up = [], k;
    for (k = 0; k < P.length; k++) { while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], P[k]) <= 0) lo.pop(); lo.push(P[k]); }
    for (k = P.length - 1; k >= 0; k--) { while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], P[k]) <= 0) up.pop(); up.push(P[k]); }
    lo.pop(); up.pop();
    var out = [], all = lo.concat(up);
    for (k = 0; k < all.length; k++) out.push(all[k][0], all[k][1]);
    return out;
  }

  // Hull of several circles [[x,y,r],...] = smooth rounded convex shape
  // (rounded triangles, teardrops, capsules).
  function circleHull(circles, seg) {
    seg = seg || 14;
    var pts = [];
    for (var i = 0; i < circles.length; i++) {
      var c = circles[i];
      for (var j = 0; j < seg; j++) { var a = j / seg * TAU; pts.push(c[0] + Math.cos(a) * c[2], c[1] + Math.sin(a) * c[2]); }
    }
    return hull(pts);
  }

  function xform(pts, dx, dy, rot, sx, sy) {
    var c = Math.cos(rot || 0), s = Math.sin(rot || 0), out = [];
    sx = sx == null ? 1 : sx; sy = sy == null ? sx : sy;
    for (var i = 0; i < pts.length; i += 2) {
      var x = pts[i] * sx, y = pts[i + 1] * sy;
      out.push(dx + x * c - y * s, dy + x * s + y * c);
    }
    return out;
  }

  // Heart built from two circles and one convex polygon (portable).
  function heart(G, x, y, s, color, alpha) {
    G.circle(x - 0.5 * s, y - 0.25 * s, 0.56 * s, color, alpha);
    G.circle(x + 0.5 * s, y - 0.25 * s, 0.56 * s, color, alpha);
    G.poly([x - 1.03 * s, y - 0.08 * s, x + 1.03 * s, y - 0.08 * s, x + 0.35 * s, y + 0.72 * s, x, y + 0.98 * s, x - 0.35 * s, y + 0.72 * s], color, alpha);
  }

  // 4- or 5-point star: a convex centre + one triangle per point.
  function star(G, x, y, ro, ri, points, rot, color, alpha) {
    var centre = [];
    for (var i = 0; i < points; i++) {
      var a0 = rot + (i + 0.5) / points * TAU;
      centre.push(x + Math.cos(a0) * ri, y + Math.sin(a0) * ri);
    }
    G.poly(centre, color, alpha);
    for (var j = 0; j < points; j++) {
      var a = rot + j / points * TAU, al = rot + (j - 0.5) / points * TAU, ar = rot + (j + 0.5) / points * TAU;
      G.tri(x + Math.cos(a) * ro, y + Math.sin(a) * ro, x + Math.cos(al) * ri, y + Math.sin(al) * ri,
        x + Math.cos(ar) * ri, y + Math.sin(ar) * ri, color, alpha);
    }
  }

  // Sample a curve fn(x) into a flat polyline over [x0, x1].
  function curve(fn, x0, x1, n) {
    var pts = [];
    for (var i = 0; i <= n; i++) { var x = x0 + (x1 - x0) * i / n; pts.push(x, fn(x)); }
    return pts;
  }

  // -------------------------------------------------------------------
  // Contrast guard (Face Studio: ANY combination must stay readable).
  // The skin a feature sits on is known from the recipe, so a feature whose
  // colour would vanish into it is pushed lighter or darker.
  // -------------------------------------------------------------------
  function eyeSkin(r, side) {
    var ps = r.patternSide === 'right' ? 1 : -1;
    if ((r.pattern === 'patch' || r.pattern === 'calico') && side === ps) return r.fur2;
    return r.fur;
  }
  function mouthSkin(r) {
    if (r.muzzle !== 'none') return r.muzzleColor;
    if (r.pattern === 'blaze' || r.pattern === 'tux') return r.fur2;
    return r.fur;
  }
  function lowContrast(a, b) { return Math.abs(Gfx.luminance(a) - Gfx.luminance(b)) < 0.26; }
  function contrastOn(col, bg) {
    if (!lowContrast(col, bg)) return col;
    return Gfx.luminance(bg) < 0.5 ? mix(col, '#FFFFFF', 0.72) : mix(col, '#000000', 0.62);
  }

  // Deterministic pseudo-random (hash) so "random" details never flicker.
  function hash(n) { var x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }

  // ===================================================================
  // EYES
  // ===================================================================

  // Eye opening outline as two functions of x (local coords, centred).
  function outlineFns(shape, a, b) {
    var f;
    if (shape === 'almond') {
      return {
        top: function (x) { var q = x / a, u = Math.max(0, 1 - q * q); return -b * Math.pow(u, 0.7); },
        bot: function (x) { var q = x / a, u = Math.max(0, 1 - q * q); return b * 0.86 * Math.pow(u, 0.92); }
      };
    }
    if (shape === 'soft') {
      f = function (x) { var q = Math.min(1, Math.abs(x / a)); return b * Math.pow(Math.max(0, 1 - Math.pow(q, 2.8)), 1 / 2.8); };
    } else {
      f = function (x) { var q = x / a; return b * Math.sqrt(Math.max(0, 1 - q * q)); };
    }
    return { top: function (x) { return -f(x); }, bot: f };
  }

  // Which icon (if any) replaces the eye. Low battery shows a battery IN
  // the eyes only for glow (robot) styles; fur styles get a pop-up instead.
  function eyeIcon(p, r) {
    if (r.eyeStyle === 'glow' && p.batt > p.iconAmt) return { name: 'battery', amt: p.batt };
    return { name: p.icon, amt: p.icon ? p.iconAmt : 0 };
  }

  // Everything about one eye's geometry this frame. Exported for tests.
  function eyeGeom(p, r, side) {
    var shp = EYE_SHAPES[r.eyeShape] || EYE_SHAPES.oval;
    var bl = side < 0 ? p.blinkL : p.blinkR;
    var sc = r.eyeSize * p.eyeScale * (side < 0 ? p.eyeScaleL : p.eyeScaleR);
    if (r.eyeStyle === 'glow') sc *= 1.08;
    var body = 1 - clamp(eyeIcon(p, r).amt, 0, 1);
    var a0 = shp.a * sc * p.eyeSX, b0 = shp.b * sc * p.eyeSY;
    var a = a0 * (1 + 0.12 * bl) * body;
    var b = b0 * (1 - 0.15 * bl) * body;
    var ex = CX + side * (LAYOUT.eyeDX * r.eyeSpacing + p.eyeSpread);
    var ey = LAYOUT.eyeY + p.eyeDY - Math.max(p.happy, p.wink * side > 0 ? Math.abs(p.wink) : 0) * 3;
    var moves = (r.eyeStyle === 'gloss' || r.eyeStyle === 'glow');
    var reach = r.eyeStyle === 'glow' ? [9, 6] : [5, 4];
    var crossX = p.cross * (-side), crossY = p.cross;
    // cross-eyed (boop!): each eye swings hard toward the nose and down
    var gx = moves ? (p.lookX * reach[0] + crossX * 14) : 0;
    var gy = moves ? (p.lookY * reach[1] + crossY * 7) : 0;
    var ix = moves ? 0 : (p.lookX * 0.34 * a + crossX * 0.45 * a);
    var iy = moves ? 0 : (p.lookY * 0.24 * b + crossY * 0.28 * b);

    var blinkC = clamp(bl, 0, 1);
    // happy "^" on both eyes, or a one-eyed wink (wink -1 = viewer's left eye)
    var hap = Math.max(p.happy, p.wink * side > 0 ? Math.abs(p.wink) : 0);
    var Cb = clamp(Math.max(blinkC, p.shut), 0, 1);   // blink / asleep: both lids meet
    var C = clamp(Math.max(Cb, hap), 0, 1);
    var hw = hap / Math.max(1e-3, Math.max(hap, p.shut, blinkC));
    hw = clamp(hw, 0, 1) * smoothstep(0, 0.6, hap);
    var curv = lerp(-0.38, 1.0, hw);
    var yMeet = b * lerp(0.2, 0.04, hw);
    var lidT = side < 0 ? p.lidTL : p.lidTR, lidB = side < 0 ? p.lidBL : p.lidBR;
    var arcW = 0.96 * Math.max(a, 1);
    // lids follow the eyeball up and down (gy), like real eyelids do
    function arc(x) { var q = Math.min(1, Math.abs(x) / arcW); return gy + yMeet - curv * b * 0.42 * (1 - Math.pow(q, 1.5)); }
    // Happy squint: the CHEEKS push the bottom lid up into a half-moon, and
    // the top lid only drops at the very end, so the eye melts into "^".
    // (Lowering the top lid first reads as annoyed -- checked on a strip.)
    function arcH(x) { var q = Math.min(1, Math.abs(x) / arcW); return gy + b * 0.04 - b * 0.42 * (1 - Math.pow(q, 1.5)); }
    var hTop = hap * hap * hap, hBot = Math.pow(hap, 0.8);
    function topEdge(x) {
      var q = x / Math.max(a, 1), xin = -side * q;
      var base = gy + b * (-1.05 + 1.9 * lidT) + p.lidTilt * 0.55 * b * xin * (1 - hap) + p.lidSag * 0.32 * b * (1 - q * q);
      base = lerp(base, arcH(x) - 0.4, hTop);
      return lerp(base, arc(x) - 0.4, Cb);
    }
    function botEdge(x) {
      var q = x / Math.max(a, 1);
      var base = gy + b * (1.05 - 1.9 * lidB) - p.lidBulge * 0.34 * b * (1 - q * q);
      base = lerp(base, arcH(x) + 0.4, hBot);
      return lerp(base, arc(x) + 0.4, Cb);
    }
    var o = outlineFns(r.eyeShape, a, b);
    function oTop(x) { return gy + o.top(x - gx); }
    function oBot(x) { return gy + o.bot(x - gx); }
    return {
      side: side, a: a, b: b, a0: a0, b0: b0, ex: ex, ey: ey, gx: gx, gy: gy, ix: ix, iy: iy,
      slant: -side * shp.slant * DEG, C: C, curv: curv, arc: arc, topEdge: topEdge, botEdge: botEdge,
      oTop: oTop, oBot: oBot,
      visTop: function (x) { return Math.max(oTop(x), topEdge(x)); },
      visBot: function (x) { return Math.min(oBot(x), botEdge(x)); }
    };
  }

  function eyeBand(G, g, grow, color, alpha, n) {
    var xs = cosXs(g.gx - g.a - grow, g.gx + g.a + grow, n || 28), tops = [], bots = [];
    var o = grow > 0 ? outlineFns(g.shape, g.a + grow, g.b + grow) : null;
    for (var i = 0; i < xs.length; i++) {
      var x = xs[i];
      var ot = o ? g.gy + o.top(x - g.gx) : g.oTop(x), ob = o ? g.gy + o.bot(x - g.gx) : g.oBot(x);
      tops.push(Math.max(ot, g.topEdge(x) - grow));
      bots.push(Math.min(ob, g.botEdge(x) + grow));
    }
    band(G, xs, tops, bots, color, alpha);
  }

  // A thick line along the visible TOP edge of the eye (eyeliner / lid rim),
  // broken wherever the eye is closed.
  function topLiner(G, g, x0, x1, w, color, alpha) {
    var n = 14, run = [];
    for (var i = 0; i <= n; i++) {
      var x = x0 + (x1 - x0) * i / n, yt = g.visTop(x), yb = g.visBot(x);
      if (yb - yt > 0.8) run.push(x, yt);
      else { if (run.length >= 4) G.polyline(run, w, color, alpha); run = []; }
    }
    if (run.length >= 4) G.polyline(run, w, color, alpha);
  }

  function drawEye(G, p, r, side, t) {
    var g = eyeGeom(p, r, side);
    g.shape = r.eyeShape;
    var style = r.eyeStyle;
    var dark = r.eyeColor, white = '#FFFFFF';
    var shineMul = p.shine * (0.85 + 0.15 * p.pupil) * (1 + 0.3 * p.tear);
    var closed = g.C > 0.985;

    G.save();
    G.translate(g.ex, g.ey);
    if (g.slant) G.rotate(g.slant);
    G.tag('eye');

    if (!closed && g.a > 0.5 && g.b > 0.5) {
      var vT = g.visTop, vB = g.visBot;
      if (style === 'glow') {
        eyeBand(G, g, 6, dark, 0.13);
        eyeBand(G, g, 0, dark, 1);
      } else if (style === 'gloss') {
        var skin = eyeSkin(r, side);
        if (lowContrast(dark, skin)) eyeBand(G, g, 3, mix(skin, Gfx.luminance(skin) < 0.5 ? '#FFFFFF' : '#000000', 0.55), 1);
        eyeBand(G, g, 0, dark, 1);
        clippedEllipse(G, g.gx * 0.4, g.gy + 0.47 * g.b, 0.64 * g.a, 0.4 * g.b, vT, vB, mix(dark, r.irisColor, 0.6), 0.95);
        clippedEllipse(G, g.gx * 0.4, g.gy + 0.56 * g.b, 0.42 * g.a, 0.24 * g.b, vT, vB, mix(dark, r.irisColor, 0.9), 0.6);
      } else {
        // iris / cat: dark outline ring (also becomes the lid liner), then the eye
        var skin2 = eyeSkin(r, side);
        if (lowContrast(dark, skin2)) eyeBand(G, g, style === 'cat' ? 5.4 : 5, mix(skin2, '#FFFFFF', 0.55), 1);
        eyeBand(G, g, style === 'cat' ? 3.2 : 2.8, dark, 1);
        if (style === 'iris') {
          eyeBand(G, g, 0, '#FFFDF9', 1);
          var rix = 0.7 * g.a, riy = 0.8 * g.b, icx = g.ix, icy = g.iy + 0.05 * g.b;
          clippedEllipse(G, icx, icy, rix, riy, vT, vB, shade(r.irisColor, -0.4), 1);
          clippedEllipse(G, icx, icy, rix * 0.86, riy * 0.88, vT, vB, r.irisColor, 1);
          clippedEllipse(G, icx, icy + riy * 0.4, rix * 0.64, riy * 0.4, vT, vB, mix(r.irisColor, '#FFFFFF', 0.38), 0.95);
          clippedEllipse(G, icx, icy - riy * 0.58, rix * 0.84, riy * 0.34, vT, vB, shade(r.irisColor, -0.3), 0.55);
          clippedEllipse(G, icx, icy + riy * 0.04, rix * 0.4 * p.pupil, riy * 0.42 * p.pupil, vT, vB, dark, 1);
        } else { // cat
          eyeBand(G, g, 0, r.irisColor, 1);
          clippedEllipse(G, 0, -0.66 * g.b, 0.98 * g.a, 0.46 * g.b, vT, vB, shade(r.irisColor, -0.28), 0.6);
          clippedEllipse(G, g.ix * 0.3, 0.5 * g.b, 0.72 * g.a, 0.42 * g.b, vT, vB, mix(r.irisColor, '#FFFFFF', 0.32), 0.85);
          var dil = clamp((p.pupil - 0.3) / 1.1, 0, 1);
          clippedEllipse(G, g.ix, g.iy, g.a * lerp(0.1, 0.5, dil), g.b * lerp(0.86, 0.62, dil), vT, vB, dark, 1);
        }
      }

      // --- teary waterline (wobbles) -----------------------------------
      if (p.tear > 0.02) {
        var wl = function (x) { return g.gy + g.b * lerp(0.74, 0.34, p.tear) + 1.6 * Math.sin(x * 0.22 + t * 5.5) + 1.1 * Math.sin(x * 0.11 - t * 3.7); };
        var xs = cosXs(g.gx - g.a, g.gx + g.a, 26), tops = [], bots = [];
        for (var i = 0; i < xs.length; i++) { tops.push(Math.max(vT(xs[i]), wl(xs[i]))); bots.push(vB(xs[i])); }
        band(G, xs, tops, bots, style === 'glow' ? '#CFEFFF' : (style === 'gloss' ? mix(dark, '#5FB4F0', 0.55) : '#A8DCFF'), (style === 'glow' ? 0.6 : (style === 'gloss' ? 0.85 : 0.45)) * p.tear);
        var men = [];
        for (var j = 0; j <= 12; j++) {
          var mx = g.gx - g.a * 0.9 + g.a * 1.8 * j / 12, my = wl(mx);
          if (my > vT(mx) + 1 && my < vB(mx) - 1) men.push(mx, my);
          else if (men.length >= 4) { G.polyline(men, 2, '#E8F8FF', 0.9 * p.tear); men = []; } else men = [];
        }
        if (men.length >= 4) G.polyline(men, 2, '#E8F8FF', 0.9 * p.tear);
        for (var k = 0; k < 3; k++) {
          var dx = g.gx + g.a * (-0.5 + 0.48 * k), dy = wl(dx) + 3;
          clippedEllipse(G, dx, dy, (1.8 + 1.2 * Math.sin(t * 7 + k * 2)) * p.tear + 0.3, (1.8 + 1.2 * Math.sin(t * 7 + k * 2)) * p.tear + 0.3, vT, vB, '#FFFFFF', 0.9 * p.tear, 8);
        }
      }

      // --- highlights: reflections of one light, so they barely move ----
      if (style !== 'glow') {
        var hx, hy, sz;
        if (style === 'gloss') { hx = g.gx * 0.45; hy = g.gy * 0.45; sz = g.a; }
        else { hx = g.ix * 0.5; hy = g.iy * 0.5; sz = (style === 'iris' ? 0.7 : 0.8) * g.a; }
        var hr1 = 0.3 * sz * shineMul, hr2 = 0.13 * sz * shineMul;
        clippedEllipse(G, hx + side * 0.34 * sz, hy - 0.42 * g.b, hr1, hr1 * 1.08, vT, vB, white, 0.96, 16);
        clippedEllipse(G, hx - side * 0.3 * sz, hy + 0.36 * g.b, hr2, hr2, vT, vB, white, 0.9, 10);
        if (p.sparkle > 0.02) {
          var spx = hx - side * 0.22 * sz, spy = hy - 0.55 * g.b;
          if (vB(spx) - vT(spx) > 6 && spy > vT(spx) && spy < vB(spx)) {
            star(G, spx, spy, 0.26 * sz * p.sparkle * (0.85 + 0.15 * Math.sin(t * 6)), 0.07 * sz, 4, t * 0.8, white, p.sparkle);
          }
          clippedEllipse(G, hx + side * 0.55 * sz, hy + 0.05 * g.b, 0.07 * sz * p.sparkle + 0.2, 0.07 * sz * p.sparkle + 0.2, vT, vB, white, p.sparkle, 8);
        }
      }

      // --- eyeliner along the lid edge (iris / cat) ---------------------
      if (style === 'iris' || style === 'cat') {
        topLiner(G, g, g.gx - g.a * 0.98, g.gx + g.a * 0.98, style === 'cat' ? 4.2 : 4.6, dark, 1);
      }
    }

    // --- closed eye arc: relaxed "u" when asleep, "^" when happy ----------
    if (g.C > 0.8 && g.a > 0.5) {
      var ca = smoothstep(0.8, 0.975, g.C);
      var lw = style === 'glow' ? Math.max(7, g.a0 * 0.22) : Math.max(6, g.a0 * 0.19);
      G.polyline(curve(g.arc, -g.a * 0.94, g.a * 0.94, 12), lw, contrastOn(dark, eyeSkin(r, side)), ca);
    }

    // --- lashes: ride on the lid edge so they drop when blinking ---------
    if (r.lashes !== 'none' && g.a > 0.5) drawLashes(G, g, r, side, Gfx.luminance(r.fur) < 0.3 ? mix(r.fur, '#FFFFFF', 0.82) : dark);

    // --- eye icons (heart, star, spiral, x, battery, ?) -------------------
    var ic = eyeIcon(p, r);
    if (ic.amt > 0.01 && ic.name) {
      G.tag('eye-icon');
      drawEyeIcon(G, ic, r, side, t, contrastOn(dark, eyeSkin(r, side)), eyeSkin(r, side));
      G.tag('eye');
    }

    G.restore();
    return g;
  }

  function drawLashes(G, g, r, side, color) {
    var closedish = g.C > 0.85;
    var n = r.lashes === 'full' ? 3 : 2;
    var w = r.lashes === 'full' ? 3.4 : 3.1;
    for (var k = 0; k < n; k++) {
      var fx = r.lashes === 'full' ? [0.52, 0.74, 0.93][k] : [0.72, 0.92][k];
      var bx = side * g.a * fx, by;
      if (closedish) { bx = side * g.a * 0.9; by = g.arc(bx); }
      else {
        by = g.visTop(bx);
        if (g.visBot(bx) - by < 1) by = g.arc(bx);
      }
      var ang = -PI / 2 + side * (0.62 + 0.3 * k + (closedish ? 0.5 : 0));
      if (closedish && g.curv < 0) ang += side * 0.35;
      var L = g.b0 * (0.24 + 0.03 * k);
      var x1 = bx + Math.cos(ang) * L * 0.6, y1 = by + Math.sin(ang) * L * 0.6;
      var a2 = ang + side * 0.45;
      G.polyline([bx, by, x1, y1, x1 + Math.cos(a2) * L * 0.5, y1 + Math.sin(a2) * L * 0.5], w, color, 1);
    }
    if (r.lashes === 'full' && !closedish) {
      // little wing at the outer corner + one lower lash
      var ox = side * g.a * 0.92, oy = g.visTop(ox);
      if (g.visBot(ox) - oy > 1) {
        G.tri(ox, oy - 1.5, ox + side * g.a * 0.34, oy - g.b0 * 0.2, ox + side * g.a * 0.06, oy + 3, color, 1);
        var lx = side * g.a * 0.7, ly = g.visBot(lx);
        G.line(lx, ly + 1, lx + side * 6, ly + 7, 2.6, color, 0.9);
      }
    }
  }

  function drawEyeIcon(G, icon, r, side, t, dark, skin) {
    var shp = EYE_SHAPES[r.eyeShape] || EYE_SHAPES.oval;
    var s = Math.max(shp.a, shp.b) * r.eyeSize * 0.62 * clamp(icon.amt, 0, 1.3);
    var ic = icon.name;
    if (ic === 'heart') {
      var beat = 1 + 0.09 * Math.max(0, Math.sin(t * 8.5)) ;
      heart(G, 0, -0.08 * s, s * 0.98 * beat, '#FF4D79', 1);
      G.ellipse(-0.42 * s, -0.52 * s, 0.2 * s, 0.14 * s, -0.5, '#FFFFFF', 0.85);
    } else if (ic === 'star') {
      star(G, 0, 0, s * 1.05, s * 0.46, 5, -PI / 2 + 0.12 * Math.sin(t * 3), '#FFD23F', 1);
      G.circle(-0.25 * s, -0.3 * s, 0.13 * s, '#FFFFFF', 0.9);
    } else if (ic === 'spiral') {
      var pts = [], turns = 2.6, rot = t * 7 * -side;
      for (var i = 0; i <= 44; i++) { var f = i / 44, a = rot + f * turns * TAU; pts.push(Math.cos(a) * f * s, Math.sin(a) * f * s); }
      G.polyline(pts, Math.max(3.5, s * 0.14), dark, 1);
    } else if (ic === 'x') {
      var q = s * 0.62, lw = Math.max(5, s * 0.22);
      G.line(-q, -q, q, q, lw, dark, 1); G.line(q, -q, -q, q, lw, dark, 1);
    } else if (ic === 'battery') {
      var bw = s * 2.1, bh = s * 1.2;
      G.rrect(-bw / 2, -bh / 2, bw, bh, s * 0.2, dark, 1);
      G.rrect(-bw / 2 + s * 0.13, -bh / 2 + s * 0.13, bw - s * 0.26, bh - s * 0.26, s * 0.1, skin || '#FFFFFF', 1);
      G.rrect(bw / 2 - 1, -s * 0.2, s * 0.16, s * 0.4, s * 0.06, dark, 1);
      var blinkOn = 0.55 + 0.45 * Math.sin(t * 6);
      G.rrect(-bw / 2 + s * 0.22, -bh / 2 + s * 0.22, (bw - s * 0.44) * 0.22, bh - s * 0.44, s * 0.06, '#FF4B4B', blinkOn);
    } else if (ic === 'question') {
      var lw2 = Math.max(4, s * 0.17);
      G.arc(0, -0.28 * s, 0.34 * s, PI * 1.05, PI * 2.3, lw2, dark, 1);
      G.line(0.12 * s, 0.02 * s, 0, 0.28 * s, lw2, dark, 1);
      G.circle(0, 0.62 * s, lw2 * 0.62, dark, 1);
    }
  }

  function drawBrows(G, p, r, g, side) {
    if (r.brows === 'none') return;
    G.tag('brow');
    var bx = g.ex + (-side) * 0.08 * g.a0;
    var by = g.ey - g.b0 - 13 - p.browY * 9 + p.happy * 2;
    var rot = -side * p.browTilt * 0.42;
    var c = contrastOn(r.browColor, eyeSkin(r, side));
    G.save(); G.translate(bx, by); G.rotate(rot);
    if (r.brows === 'dots') {
      G.ellipse(0, 0, 0.24 * g.a0, 0.16 * g.a0, 0, c, 1);
    } else if (r.brows === 'arcs') {
      G.arc(0, 26, 29, -PI / 2 - 0.44, -PI / 2 + 0.44, 5, c, 1);
    } else {
      G.rrect(-0.45 * g.a0, -4.5, 0.9 * g.a0, 9, 4.5, c, 1);
    }
    G.restore();
  }

  // ===================================================================
  // NOSE -- every style has one, and it always animates (sniff, twitch,
  // scrunch, boop squash). Shapes are cached unit polygons.
  // ===================================================================
  var NOSE_POLYS = {
    pup: circleHull([[-11, -5, 8.5], [11, -5, 8.5], [0, 7.5, 7]], 16),
    cat: circleHull([[-6.5, -3, 4.2], [6.5, -3, 4.2], [0, 4.5, 3.4]], 12)
  };
  var NOSE_SIZE = { pup: [39, 28], cat: [21, 15], button: [28, 21], bean: [42, 24], heart: [25, 22] };

  function nosePos(p, r) {
    var sc = r.nose === 'pup' ? 1 : 1;
    return {
      x: CX + p.noseDX + p.lookX * 3,
      y: LAYOUT.noseY + p.noseDY - p.scrunch * 3,
      sx: p.noseSX * (1 + 0.1 * p.scrunch) * sc,
      sy: p.noseSY * (1 - 0.2 * p.scrunch) * sc
    };
  }

  function drawNose(G, p, r) {
    G.tag('nose');
    var n = nosePos(p, r), style = r.nose, col = contrastOn(r.noseColor, mouthSkin(r));
    var sz = NOSE_SIZE[style] || NOSE_SIZE.pup;
    var w = sz[0] * n.sx, h = sz[1] * n.sy;
    var pink = Gfx.luminance(col) > 0.45;
    var shineCol = pink ? '#FFFFFF' : '#FFFFFF', shineA = pink ? 0.55 : 0.5;

    // scrunch wrinkles (disgust, pre-sneeze): short arcs ABOVE the nose only
    if (p.scrunch > 0.03) {
      G.tag('nose-wrinkle');
      for (var k = 0; k < 3; k++) {
        var wy = n.y - h * 0.5 - 6 - k * 5.5, ww = 8 - k * 1.5;
        G.polyline([n.x - ww, wy + 2.2, n.x, wy, n.x + ww, wy + 2.2], 2.4, r.lineColor, p.scrunch * 0.85);
      }
      G.tag('nose');
    }

    if (style === 'pup' || style === 'cat') {
      G.poly(xform(NOSE_POLYS[style], n.x, n.y, 0, n.sx, n.sy), col, 1);
    } else if (style === 'heart') {
      heart(G, n.x, n.y - 1.5 * n.sy, 11.5 * n.sx, col, 1);
    } else {
      G.ellipse(n.x, n.y, w / 2, h / 2, 0, col, 1);
    }
    // wet shine: a soft highlight + a tiny dot
    G.ellipse(n.x - w * 0.18, n.y - h * 0.24, w * 0.2, h * 0.13, -0.15, shineCol, shineA);
    G.circle(n.x + w * 0.16, n.y - h * 0.27, Math.max(1, w * 0.045), shineCol, shineA * 0.9);
    return { x: n.x, y: n.y, w: w, h: h, bottom: n.y + h * (style === 'heart' ? 0.42 : 0.5) };
  }

  // ===================================================================
  // MOUTH -- lip line + open interior + tongue, all bands (no clip).
  // ===================================================================
  var MOUTH = {
    pup:    { hw: 38, dip: 10, lift: 8, depth: 32, lw: 4.4 },
    omega:  { hw: 23, dip: 7, lift: 5, depth: 20, lw: 3.7 },
    simple: { hw: 30, dip: 0,   lift: 6, depth: 25, lw: 4.6 }
  };

  function mouthGeom(p, r, t) {
    var style = MOUTH[r.mouth] ? r.mouth : 'pup';
    var M = MOUTH[style];
    var mx = CX + p.lookX * 2 + p.noseDX * 0.3, my = LAYOUT.mouthY;
    var hw = M.hw * p.mouthW * (1 - 0.55 * p.mouthO);
    var restOpen = r.mouthRest * clamp((p.smile + 0.1) / 0.5, 0, 1) * (1 - p.mouthO);
    var o = clamp(p.open + restOpen, 0, 1);
    var lift = p.smile * M.lift;
    var dip = M.dip * clamp(0.45 + p.smile, 0.25, 1.25) * (1 - 0.7 * p.mouthO);
    var wob = p.wobble;
    function lip(x) {
      var dx = x - mx, q = Math.min(1, Math.abs(dx) / Math.max(hw, 1)), sg = dx >= 0 ? 1 : -1;
      var L = clamp(lift + p.skew * 5 * sg, -12, 8);
      var y;
      if (style === 'simple') y = my + 2 + p.smile * 7 * (1 - q * q) - (L - lift * 1) * q - lift * 0.35 * q * q;
      else y = my + dip * Math.sin(PI * q) - L * Math.pow(q, 1.6);
      if (wob > 0.01) y += wob * 2.2 * Math.sin(t * 17 + dx * 0.16) * (1 - q * 0.5);
      return Math.max(y, my - 8.2);   // hard rule: nothing of the mouth above 70 %
    }
    var hwo = hw * (style === 'simple' ? 0.86 : 0.9);
    var top0 = my + (style === 'simple' ? 2 : dip * 0.55);
    var maxD = M.depth * (1 + 0.25 * p.mouthO);
    var d = o * maxD;
    var tongueOut = clamp((p.tongue - 0.5) * 2, 0, 1);
    // keep everything above the 90% line
    var room = LAYOUT.mouthMaxY - top0 - 1;
    var hang = tongueOut * 16 + p.pant * 5;
    if (d + hang > room) { var k = room / (d + hang); d *= k; hang *= k; }
    // bottom of the opening: meets the lip at the corners, deepest in the middle
    function bot(x) {
      var q = (x - mx) / Math.max(hwo, 1), f = Math.pow(Math.max(0, 1 - q * q), 0.55), l = lip(x);
      return l + Math.max(0, top0 + d - l) * f;
    }
    return { style: style, M: M, mx: mx, my: my, hw: hw, hwo: hwo, o: o, d: d, top0: top0, lip: lip, bot: bot,
      tongueOut: tongueOut, hang: hang };
  }

  function drawMouth(G, p, r, t, nose) {
    var m = mouthGeom(p, r, t);
    var line = contrastOn(r.eyeStyle === 'glow' ? r.eyeColor : r.lineColor, mouthSkin(r));
    var lw = m.M.lw;

    // philtrum: nose -> centre of the lip (pup + omega mouths)
    if (m.style !== 'simple') {
      G.tag('philtrum');
      G.line(nose.x, nose.bottom - 2, m.mx, m.lip(m.mx) + 0.5, lw * 0.85, line, 1);
    }
    G.tag('mouth');

    if (m.o > 0.02 && m.d > 1) {
      var xs = cosXs(m.mx - m.hwo - 2, m.mx + m.hwo + 2, 26), tops = [], bots = [], tops2 = [], bots2 = [];
      for (var i = 0; i < xs.length; i++) {
        var x = xs[i], lp = m.lip(x) - 0.5, qq = (x - m.mx) / (m.hwo + 2);
        tops.push(lp); bots.push(m.bot(x) + 2.6 * Math.pow(Math.max(0, 1 - qq * qq), 0.3));
      }
      band(G, xs, tops, bots, line, 1);                    // outline
      var xs2 = cosXs(m.mx - m.hwo, m.mx + m.hwo, 26);
      for (var j = 0; j < xs2.length; j++) { tops2.push(m.lip(xs2[j])); bots2.push(m.bot(xs2[j])); }
      var inside = r.eyeStyle === 'glow' ? '#2A0E14' : '#7A2630';
      band(G, xs2, tops2, bots2, inside, 1);                // interior
      // back-of-mouth shadow for depth
      clippedEllipse(G, m.mx, m.top0 + 1, m.hwo * 0.75, m.d * 0.45,
        function (x) { return m.lip(x); }, function (x) { return m.bot(x); }, '#4E1520', 0.55, 14);

      // tongue: rests in the mouth, hangs out when tongue > 0.5, bounces when panting
      if (p.tongue > 0.04 && m.o > 0.08) {
        var tw = m.hwo * lerp(0.5, 0.64, clamp(p.tongue * 2, 0, 1));
        var bounce = p.pant * 4.5 * Math.abs(Math.sin(t * 8.5));
        var tTop = m.top0 + m.d * lerp(0.5, 0.25, m.tongueOut) + bounce * 0.4;
        var tBot = m.top0 + m.d + m.hang * (m.tongueOut > 0 ? 1 : 0) + bounce * (m.tongueOut > 0 ? 1 : 0.3);
        tBot = Math.min(tBot, LAYOUT.mouthMaxY - 0.5);
        var tx = m.mx + p.skew * 3;
        var xs3 = cosXs(tx - tw, tx + tw, 20), t3 = [], b3 = [];
        for (var k2 = 0; k2 < xs3.length; k2++) {
          var xx = xs3[k2], q = (xx - tx) / tw;
          var tt = tTop + q * q * 4;
          var tb = tTop + (tBot - tTop) * Math.pow(Math.max(0, 1 - q * q), 0.45);
          t3.push(Math.max(tt, m.lip(xx)));
          b3.push(m.tongueOut > 0.02 ? tb : Math.min(tb, m.bot(xx)));
        }
        if (m.tongueOut > 0.02) {
          // hanging tongue gets its own outline so it reads over the fur
          var t4 = [], b4 = [];
          for (var k3 = 0; k3 < xs3.length; k3++) { t4.push(t3[k3]); b4.push(b3[k3] > m.bot(xs3[k3]) ? b3[k3] + 2 : b3[k3]); }
          band(G, xs3, t4, b4, line, 1);
        }
        band(G, xs3, t3, b3, r.tongueColor, 1);
        var gy0 = Math.max(tTop + 3, m.lip(tx) + 3), gy1 = tTop + (tBot - tTop) * 0.55;
        if (gy1 > gy0 + 2) G.line(tx, gy0, tx, gy1, 2, shade(r.tongueColor, -0.28), 0.9);
        G.ellipse(tx - tw * 0.38, tTop + (tBot - tTop) * 0.34, tw * 0.16, Math.max(1, (tBot - tTop) * 0.12), -0.3, '#FFFFFF', 0.3);
      }
    }

    // lip line (the smile itself), cusp kept sharp for the "w" shapes
    var half = [];
    var n = 10, pts = [];
    for (var a = 0; a <= n; a++) { var xa = m.mx - m.hw + m.hw * a / n; pts.push(xa, m.lip(xa)); }
    for (var b = 1; b <= n; b++) { var xb = m.mx + m.hw * b / n; pts.push(xb, m.lip(xb)); }
    G.polyline(pts, lw, line, 1);
    // dimples at the corners on a big smile
    var dimple = smoothstep(0.45, 0.9, p.smile) * (1 - p.mouthO);
    if (dimple > 0.02) {
      for (var s = -1; s <= 1; s += 2) {
        var cx = m.mx + s * m.hw, cy = m.lip(cx);
        G.line(cx, cy, cx + s * 4.5, cy - 1.8, lw * 0.8, line, dimple);
      }
    }
    if (p.lick > 0.02) drawLick(G, p, r, t, m, line);
    // one cute fang
    if (p.fang > 0.03) {
      var fx = m.mx + m.hw * (m.style === 'omega' ? 0.55 : 0.42), fy = m.lip(fx);
      G.tri(fx - 3.6, fy + 0.5, fx + 3.6, m.lip(fx + 3.6) + 0.5, fx + 0.4, fy + 8.5 * p.fang, '#FFFFFF', 1);
    }
    return m;
  }

  // HUNGRY: on one cycle (Moods.HUNGRY_CYCLE = 3.6 s) the tongue sweeps
  // across the upper lip, then a drool drop forms at the mouth corner,
  // stretches and drips (the tummy rumble lands during the drool). Clamped
  // to the 70-90 % mouth band like the rest of the mouth.
  function drawLick(G, p, r, t, m, line) {
    var P = 3.6, c = ((t % P) + P) % P, L = p.lick;
    var minY = 0.705 * H + 1, maxY = LAYOUT.mouthMaxY - 1;
    if (c < 1.0) {
      var k = c / 1.0, env = Math.sin(k * PI) * L;
      if (env < 0.03) return;
      var sx = lerp(-0.7, 0.7, smoothstep(0, 1, k));
      var tx = m.mx + sx * m.hw * 0.8, ly = m.lip(tx);
      var rr = 4.5 + 3.5 * env;
      var up = Math.max(0, Math.min(rr * 1.1 * env + 2, ly - minY - (rr * 0.9 + 2)));
      var cx2 = tx + sx * 3, cy2 = ly - up;
      G.poly(circleHull([[tx, ly + 2, rr + 2], [cx2, cy2, rr * 0.9 + 2]], 12), line, 1);
      G.poly(circleHull([[tx, ly + 2, rr], [cx2, cy2, rr * 0.9]], 12), r.tongueColor, 1);
      G.line(tx, ly + 1, (cx2 + tx) / 2, (cy2 + ly) / 2, 1.6, shade(r.tongueColor, -0.28), 0.8);
      G.circle(cx2 - rr * 0.3, cy2 - rr * 0.2, rr * 0.22, '#FFFFFF', 0.35);
    } else {
      var k2 = (c - 1.0) / (P - 1.0);
      var dx = m.mx + m.hw * 0.62, base = m.lip(dx) + 1;
      var len, dropY, rad, al = L;
      if (k2 < 0.7) { var g = k2 / 0.7; len = 2 + 13 * Math.pow(g, 1.4); rad = 3.2 + 2.8 * g; dropY = base + len + rad * 0.6; }
      else { var f = (k2 - 0.7) / 0.3; len = 15 * (1 - f); rad = 6 * (1 - 0.3 * f); dropY = base + 18 + 16 * f * f; al = L * (1 - f); }
      dropY = Math.min(dropY, maxY - rad - 1.2);
      if (len > 0.5) G.poly(circleHull([[dx, base, 2.4], [dx, base + len, 1.6]], 8), '#BFE6FF', 0.95 * L);
      G.circle(dx, dropY, rad + 1.2, '#7FC3EC', 0.9 * al);
      G.circle(dx, dropY, rad, '#DDF4FF', al);
      G.circle(dx - rad * 0.35, dropY - rad * 0.35, Math.max(0.6, rad * 0.3), '#FFFFFF', al);
    }
  }

  // ===================================================================
  // CHEEKS (blush under-outside the eyes), FRECKLES, WHISKERS
  // ===================================================================
  function drawCheeks(G, p, r, gL, gR) {
    G.tag('cheek');
    var al = clamp(r.blush + 0.7 * p.blush, 0, 0.85);
    if (Gfx.luminance(r.fur) < 0.3) al = clamp(al * 1.5, 0, 0.9);
    var eyes = [gL, gR];
    for (var i = 0; i < 2; i++) {
      var g = eyes[i], s = g.side;
      var bx = g.ex + s * 0.52 * g.a0, by = g.ey + g.b0 * 1.02 + 5;
      if (al > 0.01) G.ellipse(bx, by, 0.64 * g.a0, 0.3 * g.a0, 0, r.blushColor, al);
      if (p.blushLines > 0.02) {
        for (var k = 0; k < 3; k++) {
          var lx = bx - 11 + k * 8;
          G.line(lx - 3, by + 5, lx + 3, by - 5, 2.3, shade(r.blushColor, -0.3), p.blushLines);
        }
      }
      if (r.freckles === 'yes') {
        var fc = shade(r.fur, -0.35);
        G.circle(bx - 7, by + 1, 2, fc, 0.8); G.circle(bx + 1, by + 4, 2, fc, 0.8); G.circle(bx + 8, by, 2, fc, 0.8);
      }
    }
  }

  function drawWhiskers(G, p, r, t) {
    if (r.whiskers === 'none') return;
    G.tag('whisker');
    var m = MOUTH[r.mouth] || MOUTH.pup;
    var ox = Math.max(m.hw * p.mouthW + 12, 36);
    var len = r.whiskers === 'long' ? 70 : 44;
    var wc = contrastOn(r.whiskerColor, r.fur);
    var perk = p.smile * 0.08 - p.earBack * 0.08 + p.noseDY * 0.015 + 0.02 * Math.sin(t * 2.1);
    for (var s = -1; s <= 1; s += 2) {
      for (var k = 0; k < 3; k++) {
        var x0 = CX + s * ox + p.lookX * 2, y0 = LAYOUT.mouthY - 9 + (k - 1) * 8;
        var L = len - Math.abs(k - 1) * 9;
        var ang = (k - 1) * 0.2 - perk;
        var x2 = x0 + s * L * Math.cos(ang), y2 = y0 + L * Math.sin(ang);
        var xm = (x0 + x2) / 2, ym = (y0 + y2) / 2 - 2.5;
        G.polyline([x0, y0, xm, ym, x2, y2], 2, wc, 0.9);
      }
      for (var d = 0; d < 3; d++) G.circle(CX + s * (ox - 10 + (d % 2) * 6), LAYOUT.mouthY - 12 + d * 6, 1.6, shade(r.whiskerColor, -0.1), 0.7);
    }
  }

  // ===================================================================
  // FUR: head silhouette (sticker frame), patterns, muzzle
  // ===================================================================
  var HEAD = { cx: CX, cy: 170, rx: 180, ry: 154, n: 2.2 };
  function headPoly(grow) {
    var pts = [], rx = HEAD.rx + grow, ry = HEAD.ry + grow;
    for (var i = 0; i < 72; i++) {
      var a = i / 72 * TAU, c = Math.cos(a), s = Math.sin(a);
      pts.push(HEAD.cx + rx * Math.sign(c) * Math.pow(Math.abs(c), 2 / HEAD.n),
        HEAD.cy + ry * Math.sign(s) * Math.pow(Math.abs(s), 2 / HEAD.n));
    }
    return pts;
  }
  var HEAD_POLY = headPoly(0), HEAD_OUTLINE = headPoly(4);

  var SPOTS = [[-178, 52, 17, 13, 0.3], [156, 36, 21, 15, -0.4], [196, 150, 15, 11, 0.2], [-196, 172, 19, 14, -0.2],
    [112, 238, 13, 9, 0.5], [-58, 28, 11, 8, 0.1], [-120, 246, 11, 8, 0], [60, 14, 8, 6, 0.4]];

  function drawPattern(G, p, r, gL, gR, headTop) {
    var pat = r.pattern, c2 = r.fur2, c3 = r.fur3;
    var s = r.patternSide === 'right' ? 1 : -1;
    var g = s < 0 ? gL : gR, o = s < 0 ? gR : gL;
    G.tag('fur');
    if (pat === 'patch') {
      G.ellipse(g.ex + s * 5, g.ey - 4, g.a0 * 1.62, g.b0 * 1.36, s * 0.25, c2, 1);
      G.ellipse(g.ex + s * 22, g.ey - 38, g.a0 * 1.08, g.b0 * 0.8, s * 0.5, c2, 1);
      G.ellipse(g.ex - s * 12, g.ey + 20, g.a0 * 1.0, g.b0 * 0.62, -s * 0.3, c2, 1);
    } else if (pat === 'spots') {
      for (var i = 0; i < SPOTS.length; i++) {
        var sp = SPOTS[i];
        G.ellipse(CX + sp[0] * -s, sp[1] + (headTop > 0 ? 8 : 0), sp[2], sp[3], sp[4], c2, 1);
      }
    } else if (pat === 'tabby') {
      var xsT = [-30, 0, 30], ls = [36, 50, 36];
      for (var k = 0; k < 3; k++) {
        var x = CX + xsT[k], y0 = headTop - 2;
        G.poly(xform(circleHull([[0, 0, 6.5], [0, ls[k], 2]], 10), x, y0, xsT[k] * 0.006, 1), c2, 1);
      }
      for (var sd = -1; sd <= 1; sd += 2) {
        for (var j = 0; j < 2; j++) {
          var yy = 168 + j * 22;
          G.poly(circleHull([[CX + sd * 236, yy, 6.5], [CX + sd * 184, yy + 5 - j * 2, 2]], 10), c2, 1);
        }
      }
    } else if (pat === 'calico') {
      G.ellipse(CX + s * 150, 24, 118, 84, -s * 0.3, c2, 1);
      G.ellipse(CX + s * 196, 118, 60, 70, 0, c2, 1);
      G.ellipse(CX - s * 178, 8, 92, 56, s * 0.35, c3, 1);
      G.ellipse(CX - s * 214, 70, 34, 40, 0, c3, 1);
    } else if (pat === 'blaze') {
      G.poly([CX - 9, headTop - 4, CX + 9, headTop - 4, CX + 27, 150, CX - 27, 150], c2, 1);
      G.ellipse(CX, 214, 94, 64, 0, c2, 1);
    } else if (pat === 'mask') {
      G.ellipse(CX, -72, 330, 160, 0, c2, 1);
      G.tri(CX - 30, 60, CX + 30, 60, CX, 116, c2, 1);
      G.ellipse(gL.ex, gL.ey - gL.b0 - 11, 15, 9, 0.15, r.fur, 1);
      G.ellipse(gR.ex, gR.ey - gR.b0 - 11, 15, 9, -0.15, r.fur, 1);
    } else if (pat === 'tux') {
      G.ellipse(CX, 268, 156, 104, 0, c2, 1);
      G.tri(CX - 34, 180, CX + 34, 180, CX, 108, c2, 1);
    }
  }

  function drawMuzzle(G, r) {
    if (r.muzzle === 'none') return;
    G.tag('fur');
    if (r.muzzle === 'round') G.ellipse(CX, LAYOUT.mouthY - 4, 66, 48, 0, r.muzzleColor, 1);
    else { G.ellipse(CX - 31, LAYOUT.mouthY + 1, 48, 37, 0, r.muzzleColor, 1); G.ellipse(CX + 31, LAYOUT.mouthY + 1, 48, 37, 0, r.muzzleColor, 1); }
  }

  // ===================================================================
  // EARS (at the top corners; floppy ones swing like real flaps)
  // ===================================================================
  var EAR_SHAPES = {
    floppyOut: circleHull([[0, 4, 24], [-10, 112, 52]], 18),
    floppyIn:  circleHull([[-4, 60, 10], [-12, 116, 30]], 14),
    lopOut:    circleHull([[0, 10, 21], [-4, 140, 29]], 14),
    lopIn:     circleHull([[-1, 34, 9], [-4, 132, 18]], 12),
    pointOut:  circleHull([[-54, 10, 10], [54, 10, 10], [0, -104, 12]], 12),
    pointIn:   circleHull([[-27, -6, 4], [27, -6, 4], [0, -72, 5]], 10),
    foldOut:   circleHull([[-42, 8, 9], [42, 8, 9], [0, -46, 11]], 12),
    foldFlap:  circleHull([[-28, -18, 6], [28, -18, 6], [0, 20, 7]], 10),
    bunnyOut:  circleHull([[0, 0, 22], [0, -120, 26]], 14),
    bunnyIn:   circleHull([[0, -10, 10], [0, -112, 14]], 12)
  };

  // front: true = only ears that hang in FRONT of a sticker head (floppy).
  function drawEars(G, p, r, full, t, front) {
    var st = r.ears;
    if (st === 'none') return;
    var floppyish = st === 'floppy';
    if (!full && (front ? !floppyish : floppyish)) return;
    G.tag('ear');
    var col = r.earColor, inn = r.earInner, sway = Math.sin(t * 1.7) * 1.2;
    var calS = r.patternSide === 'right' ? 1 : -1;
    for (var s = -1; s <= 1; s += 2) {
      var flick = s < 0 ? p.earL : p.earR;
      if (r.pattern === 'calico') col = s === calS ? r.fur2 : r.fur3;
      var ax, ay, out, rot;
      if (st === 'floppy' || (st === 'bunny' && full)) {
        var lop = st === 'bunny';
        ax = CX + s * (full ? (lop ? 176 : 170) : 166); ay = full ? -30 : 42;
        out = (lop ? 8 : (full ? 16 : 26)) + 18 * p.earPerk + 22 * p.earBack + flick + sway;
        rot = -s * out * DEG;
        G.poly(xform(EAR_SHAPES[lop ? 'lopOut' : 'floppyOut'], ax, ay, rot, (s < 0 ? 1 : -1) * 1.05, 1.03), shade(col, -0.2), 1);
        G.poly(xform(EAR_SHAPES[lop ? 'lopOut' : 'floppyOut'], ax, ay, rot, s < 0 ? 1 : -1, 1), col, 1);
        G.poly(xform(EAR_SHAPES[lop ? 'lopIn' : 'floppyIn'], ax, ay, rot, s < 0 ? 1 : -1, 1), inn, lop ? 0.8 : 0.35);
      } else if (st === 'pointy' || st === 'fold') {
        ax = CX + s * (full ? 164 : 132); ay = full ? 46 : 62;
        out = (full ? 12 : 24) - 10 * p.earPerk + 40 * p.earBack + flick + sway;
        rot = s * out * DEG;
        if (st === 'pointy') {
          G.poly(xform(EAR_SHAPES.pointOut, ax, ay, rot, 1.07, 1.05), shade(col, -0.22), 1);
          G.poly(xform(EAR_SHAPES.pointOut, ax, ay, rot, 1, 1), col, 1);
          G.poly(xform(EAR_SHAPES.pointIn, ax, ay, rot, 1, 1), inn, 0.95);
        } else {
          G.poly(xform(EAR_SHAPES.foldOut, ax, ay - 8, rot, 1.07, 1.06), shade(col, -0.22), 1);
          G.poly(xform(EAR_SHAPES.foldOut, ax, ay - 8, rot, 1, 1), col, 1);
          G.poly(xform(EAR_SHAPES.foldFlap, ax, ay - 8, rot, 1, 1), shade(col, -0.16), 1);
        }
      } else if (st === 'bunny') {
        ax = CX + s * 92; ay = 40;
        rot = s * (14 - 8 * p.earPerk + 30 * p.earBack + flick + sway) * DEG;
        G.poly(xform(EAR_SHAPES.bunnyOut, ax, ay, rot, 1, 1), col, 1);
        G.poly(xform(EAR_SHAPES.bunnyIn, ax, ay, rot, 1, 1), inn, 0.9);
      } else { // round / bear
        var big = st === 'round';
        var R = big ? 46 : 36, lift = (p.earPerk * 4 - p.earBack * 8) + flick * 0.3;
        ax = CX + s * (big ? 168 : 150); ay = (full ? (big ? 16 : 12) : 48) - lift;
        G.circle(ax, ay, R + 3, shade(col, -0.22), 1);
        G.circle(ax, ay, R, col, 1);
        G.circle(ax - s * 3, ay + 5, R * 0.58, inn, 0.9);
      }
    }
  }

  // ===================================================================
  // ACCESSORIES (glasses are opt-in: the only thing allowed to bridge
  // the eyes, because the owner picks it on purpose)
  // ===================================================================
  function drawAccessory(G, p, r, gL, gR, headTop, t) {
    var acc = r.accessory, c = r.accColor;
    var s2 = r.patternSide === 'left' ? 1 : -1;
    if (acc === 'none') return;
    G.tag('accessory');
    if (acc === 'bow') {
      G.save(); G.translate(CX + s2 * 120, (headTop > 0 ? 34 : 28)); G.rotate(s2 * 0.28);
      G.poly(circleHull([[0, 0, 6], [-27, -13, 11], [-29, 13, 11]], 12), c, 1);
      G.poly(circleHull([[0, 0, 6], [27, -13, 11], [29, 13, 11]], 12), c, 1);
      G.ellipse(-20, -9, 6, 3.5, -0.4, '#FFFFFF', 0.4); G.ellipse(20, -9, 6, 3.5, 0.4, '#FFFFFF', 0.4);
      G.circle(0, 0, 8.5, shade(c, -0.12), 1);
      G.circle(-2, -2.5, 2.5, '#FFFFFF', 0.45);
      G.restore();
    } else if (acc === 'bandana') {
      var xs = [], tops = [], bots = [];
      for (var i = 0; i <= 24; i++) { var x = i / 24 * W; xs.push(x); tops.push(headTop - 12); bots.push(headTop + 18 + 12 * (1 - Math.pow((x - CX) / CX, 2))); }
      band(G, xs, tops, bots, c, 1);
      for (var d = 0; d < 9; d++) G.circle(40 + d * 50, headTop + 14 + 6 * (1 - Math.pow((40 + d * 50 - CX) / CX, 2)), 3, '#FFFFFF', 0.85);
      var kx = CX - s2 * 170, ky = headTop + 24;
      G.poly(circleHull([[kx, ky, 5], [kx - s2 * 16, ky + 26, 7]], 10), shade(c, -0.1), 1);
      G.poly(circleHull([[kx, ky, 5], [kx - s2 * 30, ky + 14, 7]], 10), shade(c, -0.1), 1);
      G.circle(kx, ky, 9, shade(c, -0.18), 1);
    } else if (acc === 'glasses') {
      G.tag('accessory-glasses');
      var eyes = [gL, gR];
      for (var e = 0; e < 2; e++) {
        var g = eyes[e], R = Math.max(g.a0, g.b0) * 1.2;
        G.circle(g.ex, g.ey, R, '#FFFFFF', 0.12);
        G.arc(g.ex, g.ey, R, 0, TAU, 4.5, '#3A3A46', 1);
        G.line(g.ex + g.side * R * 0.96, g.ey - 6, g.ex + g.side * (R + 20), g.ey - 12, 4, '#3A3A46', 1);
      }
      var ix0 = gL.ex + Math.max(gL.a0, gL.b0) * 1.2, ix1 = gR.ex - Math.max(gR.a0, gR.b0) * 1.2;
      G.polyline([ix0, gL.ey - 8, CX, gL.ey - 16, ix1, gR.ey - 8], 4, '#3A3A46', 1);
    } else if (acc === 'hat') {
      G.save(); G.translate(CX + s2 * 96, headTop + 56); G.rotate(s2 * 0.3);
      G.tri(-29, 0, 29, 0, 0, -66, c, 1);
      G.poly([-19.4, -22, 19.4, -22, 15, -32, -15, -32], '#FFFFFF', 0.75);
      G.poly([-8.8, -46, 8.8, -46, 4.4, -56, -4.4, -56], '#FFFFFF', 0.75);
      G.rrect(-31, -4, 62, 8, 4, shade(c, -0.2), 1);
      G.circle(0, -68, 8, '#FFFFFF', 1);
      G.restore();
    } else if (acc === 'flower') {
      var fx = CX + s2 * 132, fy = headTop + 40, rot = t * 0.2;
      for (var k = 0; k < 5; k++) { var a = rot + k / 5 * TAU; G.circle(fx + Math.cos(a) * 11, fy + Math.sin(a) * 11, 9.5, c, 1); }
      G.circle(fx, fy, 7.5, '#FFD23F', 1);
      G.circle(fx - 2, fy - 2, 2.5, '#FFFFFF', 0.6);
    }
  }

  // ===================================================================
  // DECALS: anger vein, sweat drop, gloom lines, sleep bubble, tear streams
  // ===================================================================
  function drawDecals(G, p, r, gL, gR, nose, headTop, t) {
    G.tag('decal');
    if (p.cry > 0.02) {
      var eyes = [gL, gR];
      for (var e = 0; e < 2; e++) {
        var g = eyes[e], sx = g.ex + g.side * 0.5 * g.a0, sy = g.ey + 0.72 * g.b0;
        var len = 62 * p.cry;
        G.poly(circleHull([[sx, sy, 4.5], [sx + g.side * 5, sy + len, 7.5]], 12), '#8FD3FF', 0.75 * p.cry);
        for (var k = 0; k < 2; k++) {
          var f = (t * 1.3 + k * 0.5) % 1;
          G.circle(sx + g.side * 5 * f, sy + len * f + 4, 4.5, '#CFEFFF', 0.9 * p.cry * (1 - f * 0.5));
        }
      }
    }
    if (p.vein > 0.02) {
      var vSide = (r.accessory === 'none' || r.accessory === 'glasses') ? (r.patternSide === 'left' ? 1 : -1) : (r.patternSide === 'left' ? -1 : 1);
      var vx = CX + vSide * 118, vy = headTop + 54, vs = 1.5 * (1 + 0.14 * Math.sin(t * 9));
      for (var dx = -1; dx <= 1; dx += 2) for (var dy = -1; dy <= 1; dy += 2) {
        var vp = [vx + dx * 3 * vs, vy + dy * 11 * vs, vx + dx * 3.5 * vs, vy + dy * 3.5 * vs, vx + dx * 11 * vs, vy + dy * 3 * vs];
        G.polyline(vp, 7, '#FFFFFF', 0.85 * p.vein);
        G.polyline(vp, 3.8, '#E53935', p.vein);
      }
    }
    if (p.sweat > 0.02) {
      var wx = CX + 150, wy = headTop + 52 + 9 * ((t * 0.4) % 1);
      G.circle(wx, wy, 11, '#FFFFFF', 0.9 * p.sweat);
      G.tri(wx - 10, wy - 4, wx + 10, wy - 4, wx, wy - 27, '#FFFFFF', 0.9 * p.sweat);
      G.circle(wx, wy, 9, '#7CC8F8', p.sweat);
      G.tri(wx - 8.1, wy - 4, wx + 8.1, wy - 4, wx, wy - 23, '#7CC8F8', p.sweat);
      G.ellipse(wx - 3.5, wy + 1, 2.4, 3.8, 0, '#FFFFFF', 0.85 * p.sweat);
    }
    if (p.gloom > 0.02) {
      for (var j = 0; j < 5; j++) {
        var gx = CX - 84 + j * 42, gl = 26 + 16 * hash(j + 3);
        G.line(gx, headTop + 4, gx, headTop + 4 + gl * p.gloom, 3, '#7383B0', 0.55 * p.gloom);
      }
    }
    // low battery pop-up above the head (fur styles; glow styles show it in the eyes)
    if (p.batt > 0.02 && r.eyeStyle !== 'glow') {
      G.tag('decal-battery');
      var bs = p.batt, bxc = CX, byc = headTop + (headTop > 0 ? 40 : 34) + Math.sin(t * 3) * 2;
      var bw2 = 56 * bs, bh2 = 29 * bs, rad2 = 7 * bs;
      G.rrect(bxc - bw2 / 2 - 3, byc - bh2 / 2 - 3, bw2 + 6 + 5 * bs, bh2 + 6, rad2 + 3, '#FFFFFF', 0.9);
      // the whole battery blinks red (low!), with one red bar left
      var redOn = Math.sin(t * 7) > -0.2;
      var shell = redOn ? '#E53935' : '#2E2320';
      G.rrect(bxc - bw2 / 2, byc - bh2 / 2, bw2, bh2, rad2, shell, 1);
      G.rrect(bxc + bw2 / 2 - 1, byc - 5 * bs, 5 * bs, 10 * bs, 2 * bs, shell, 1);
      G.rrect(bxc - bw2 / 2 + 3.5 * bs, byc - bh2 / 2 + 3.5 * bs, bw2 - 7 * bs, bh2 - 7 * bs, 3 * bs, '#FFFFFF', 1);
      G.rrect(bxc - bw2 / 2 + 6 * bs, byc - bh2 / 2 + 6 * bs, (bw2 - 12 * bs) * 0.3, bh2 - 12 * bs, 2 * bs, '#FF3B3B', redOn ? 1 : 0.45);
      G.tag('decal');
    }
    if (p.bubble > 0.02) {
      var rb = (5 + 11 * (0.5 + 0.5 * Math.sin(t * 1.6))) * p.bubble;
      var bx = nose.x + 13 + rb * 0.7, by = nose.y - 2 - rb * 0.3;
      G.circle(bx, by, rb, '#BFE6FF', 0.4 * p.bubble);
      G.arc(bx, by, rb, 0, TAU, 1.6, '#FFFFFF', 0.75 * p.bubble);
      G.circle(bx - rb * 0.35, by - rb * 0.35, Math.max(1, rb * 0.18), '#FFFFFF', 0.9 * p.bubble);
    }
  }

  // ===================================================================
  // MAIN ENTRY
  // ===================================================================
  // draw(target, state, recipe, t, opts)
  //   target: a Gfx wrapper, or a raw CanvasRenderingContext2D (wrapped here)
  //   returns the key geometry (eye/nose/mouth) for hit-testing and tests.
  function draw(target, state, recipe, t, opts) {
    opts = opts || {};
    var G = (target && target.mpoly) ? target : Gfx.create(target);
    var r = recipe || RecipeLib.BASE;
    var p = state;
    t = t || 0;
    var full = r.frame !== 'head';

    G.tag('fur');
    G.rect(0, 0, W, H, full ? r.fur : r.bg, 1);

    var gL = eyeGeom(p, r, -1), gR = eyeGeom(p, r, 1);
    var headTop = full ? -6 : HEAD.cy - HEAD.ry;

    G.save();
    var px = CX, py = LAYOUT.pivotY;
    G.translate(px + p.shakeX, py + p.bob);
    if (p.tilt) G.rotate(p.tilt * DEG);
    G.scale(p.headSX, p.headSY);
    G.translate(-px, -py);

    if (!full) {
      drawEars(G, p, r, false, t, false);
      G.tag('fur');
      G.poly(HEAD_OUTLINE, shade(r.fur, -0.3), 1);
      G.poly(HEAD_POLY, r.fur, 1);
    }
    drawPattern(G, p, r, gL, gR, headTop);
    drawMuzzle(G, r);
    if (r.accessory === 'bandana') drawAccessory(G, p, r, gL, gR, headTop, t);
    drawEars(G, p, r, full, t, true);
    drawCheeks(G, p, r, gL, gR);
    drawWhiskers(G, p, r, t);
    var eL = drawEye(G, p, r, -1, t);
    var eR = drawEye(G, p, r, 1, t);
    drawBrows(G, p, r, eL, -1);
    drawBrows(G, p, r, eR, 1);
    var nose = drawNose(G, p, r);
    var mouth = drawMouth(G, p, r, t, nose);
    drawDecals(G, p, r, gL, gR, nose, headTop, t);
    if (r.accessory !== 'bandana') drawAccessory(G, p, r, gL, gR, headTop, t);
    G.restore();

    var dim = clamp(r.dim + p.dim, 0, 0.85);
    if (dim > 0.003) { G.tag('dim'); G.rect(0, 0, W, H, '#000000', dim); }
    G.tag('face');
    return { eyes: [eL, eR], nose: nose, mouth: mouth };
  }

  // Hit-test helper for the page: which part of the face is at screen (x,y)?
  // Returns 'nose', 'head' (upper half = pat) or 'face'.
  function hitTest(state, recipe, x, y) {
    var p = state, r = recipe || RecipeLib.BASE;
    var n = nosePos(p, r);
    var dx = x - n.x, dy = y - (n.y + p.bob);
    if (dx * dx / (34 * 34) + dy * dy / (26 * 26) <= 1) return 'nose';
    return y < H * 0.5 ? 'head' : 'face';
  }

  var api = {
    W: W, H: H, LAYOUT: LAYOUT, EYE_SHAPES: EYE_SHAPES, MOUTH: MOUTH,
    draw: draw, hitTest: hitTest, eyeGeom: eyeGeom, mouthGeom: mouthGeom, nosePos: nosePos, eyeIcon: eyeIcon,
    helpers: { band: band, clippedEllipse: clippedEllipse, circleHull: circleHull, hull: hull, heart: heart, star: star, cosXs: cosXs }
  };
  root.FaceDraw = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
