/*
 * extras.js -- pop-up particles: hearts, Zzz, sparkles, sweat, tears, "?",
 * "!", anger steam, music notes, dizzy stars, confetti, sneeze puffs.
 *
 * Screen-space (480x272). Every particle POPS in with a little overshoot
 * (easeOutBack), lives, then fades. Drawn through gfx.js with the same
 * portable primitives as the face, so the ESP32 can show them too (with a
 * smaller particle budget: MAX below).
 *
 * Colours adapt to the fur: on cream fur, pale blue "Zzz" would vanish, so
 * light backgrounds get deeper colours with a white outline.
 */
(function (root) {
  'use strict';
  var TAU = Math.PI * 2;
  var MAX = 40; // hard cap (the ESP32 port should use ~16)

  var TYPES = {
    heart:     { life: 1.6, vy: -48, vx: 10, g: 0, spin: 0, size: 1 },
    zzz:       { life: 2.2, vy: -26, vx: 16, g: 0, spin: 0, size: 1 },
    sweat:     { life: 1.1, vy: 30, vx: 20, g: 90, spin: 0, size: 1 },
    sparkle:   { life: 0.95, vy: -14, vx: 0, g: 0, spin: 1.2, size: 1 },
    confetti:  { life: 1.8, vy: -110, vx: 60, g: 190, spin: 7, size: 1 },
    question:  { life: 1.5, vy: -14, vx: 0, g: 0, spin: 0, size: 1 },
    exclaim:   { life: 1.1, vy: -12, vx: 0, g: 0, spin: 0, size: 1 },
    steam:     { life: 1.1, vy: -30, vx: 22, g: 0, spin: 0, size: 1 },
    music:     { life: 1.7, vy: -38, vx: 14, g: 0, spin: 0, size: 1 },
    dizzyStar: { life: 2.6, vy: 0, vx: 0, g: 0, spin: 0, size: 1, orbit: true },
    tear:      { life: 1.2, vy: 40, vx: 0, g: 160, spin: 0, size: 1 },
    puff:      { life: 0.8, vy: 10, vx: 70, g: 0, spin: 0, size: 1 }
  };

  function createSystem() { return { list: [], seq: 0 }; }
  function clear(sys) { sys.list.length = 0; }

  function spawn(sys, type, x, y, opts, rnd) {
    rnd = rnd || Math.random;
    var d = TYPES[type] || TYPES.sparkle;
    opts = opts || {};
    if (sys.list.length >= MAX) sys.list.shift();
    sys.seq++;
    var dir = rnd() < 0.5 ? -1 : 1;
    sys.list.push({
      type: type, x: x, y: y,
      vx: (opts.vx != null ? opts.vx : d.vx * (0.6 + rnd() * 0.8) * dir),
      vy: (opts.vy != null ? opts.vy : d.vy * (0.8 + rnd() * 0.4)),
      g: d.g, age: -(opts.delay || 0), life: opts.life || d.life,
      rot: opts.rot != null ? opts.rot : (rnd() - 0.5) * 0.6, spin: d.spin * dir,
      scale: (opts.scale || 1) * (0.85 + rnd() * 0.3), seed: sys.seq * 1.618 + rnd() * 6,
      orbit: !!d.orbit, ox: x, oy: y, orbitR: opts.orbitR || 58, orbitSpeed: opts.orbitSpeed || 2.6,
      color: opts.color || null
    });
  }

  function burst(sys, type, x, y, count, opts, rnd) {
    rnd = rnd || Math.random;
    for (var i = 0; i < count; i++) {
      var a = (i / count) * TAU + rnd() * 0.5, sp = 40 + rnd() * 30;
      var o = { vx: Math.cos(a) * sp, vy: Math.sin(a) * sp * 0.6 - 25, delay: i * 0.04 };
      if (TYPES[type] && TYPES[type].orbit) o = { delay: 0 };
      for (var k in (opts || {})) o[k] = opts[k];
      spawn(sys, type, x + Math.cos(a) * 6, y + Math.sin(a) * 4, o, rnd);
      if (TYPES[type] && TYPES[type].orbit) sys.list[sys.list.length - 1].seed = i / count * TAU;
    }
  }

  function update(sys, dt) {
    var L = sys.list;
    for (var i = L.length - 1; i >= 0; i--) {
      var p = L[i];
      p.age += dt;
      if (p.age >= p.life) { L.splice(i, 1); continue; }
      if (p.age < 0 || p.orbit) continue;
      p.vy += p.g * dt;
      p.x += p.vx * dt; p.y += p.vy * dt;
      p.vx *= Math.pow(0.35, dt); // air drag
      p.rot += p.spin * dt;
    }
  }

  // easeOutBack pop-in, then fade the last 35% of life
  function popScale(age) { var e = Math.min(1, Math.max(0, age / 0.24)) - 1; return 1 + 2.7 * e * e * e + 1.7 * e * e; }
  function fade(p) { var f = p.age / p.life; return f < 0.65 ? 1 : Math.max(0, 1 - (f - 0.65) / 0.35); }

  // -------------------------------------------------------------------
  // Shapes (portable primitives only)
  // -------------------------------------------------------------------
  function heartShape(G, x, y, s, c, a) {
    G.circle(x - 0.5 * s, y - 0.25 * s, 0.56 * s, c, a);
    G.circle(x + 0.5 * s, y - 0.25 * s, 0.56 * s, c, a);
    G.poly([x - 1.03 * s, y - 0.08 * s, x + 1.03 * s, y - 0.08 * s, x + 0.35 * s, y + 0.72 * s, x, y + 0.98 * s, x - 0.35 * s, y + 0.72 * s], c, a);
  }
  function starShape(G, x, y, ro, ri, n, rot, c, a) {
    var ctr = [];
    for (var i = 0; i < n; i++) { var a0 = rot + (i + 0.5) / n * TAU; ctr.push(x + Math.cos(a0) * ri, y + Math.sin(a0) * ri); }
    G.poly(ctr, c, a);
    for (var j = 0; j < n; j++) {
      var ang = rot + j / n * TAU, al = rot + (j - 0.5) / n * TAU, ar = rot + (j + 0.5) / n * TAU;
      G.tri(x + Math.cos(ang) * ro, y + Math.sin(ang) * ro, x + Math.cos(al) * ri, y + Math.sin(al) * ri, x + Math.cos(ar) * ri, y + Math.sin(ar) * ri, c, a);
    }
  }
  function dropShape(G, x, y, s, c, a) {
    G.circle(x, y, 5 * s, c, a);
    G.tri(x - 4.6 * s, y - 2 * s, x + 4.6 * s, y - 2 * s, x, y - 12 * s, c, a);
  }

  function drawOne(G, p, t, light) {
    var s = p.scale * (p.orbit ? 1 : popScale(p.age)), a = fade(p);
    var x = p.x, y = p.y;
    var out = light ? '#FFFFFF' : null;
    switch (p.type) {
      case 'heart':
        x += Math.sin(p.age * 4 + p.seed) * 5;
        if (out) heartShape(G, x, y, 10.5 * s, out, 0.85 * a);
        heartShape(G, x, y, 8.5 * s, p.color || '#FF4D79', a);
        G.circle(x - 4.5 * s, y - 4 * s, 1.8 * s, '#FFFFFF', 0.7 * a);
        break;
      case 'zzz': {
        var zc = p.color || (light ? '#6C84F0' : '#BFD4FF'), w = 7 * s * (1 + p.age * 0.25), h = 7 * s * (1 + p.age * 0.25);
        var pts = [x - w, y - h, x + w, y - h, x - w, y + h, x + w, y + h];
        if (out) G.polyline(pts, 6 * s, out, 0.8 * a);
        G.polyline(pts, 3 * s, zc, a);
        break;
      }
      case 'sparkle': {
        var tw = 0.75 + 0.25 * Math.sin(p.age * 18 + p.seed);
        var sc = p.color || (light ? '#FFB020' : '#FFE98A');
        if (out) starShape(G, x, y, 11 * s * tw, 4 * s, 4, p.rot, out, 0.8 * a);
        starShape(G, x, y, 8.5 * s * tw, 2.6 * s, 4, p.rot, sc, a);
        G.circle(x, y, 1.6 * s, '#FFFFFF', a);
        break;
      }
      case 'dizzyStar': {
        var ang = p.seed + t * p.orbitSpeed;
        x = p.ox + Math.cos(ang) * p.orbitR; y = p.oy + Math.sin(ang) * p.orbitR * 0.32;
        var ds = p.scale * (0.8 + 0.2 * Math.sin(ang));
        if (out) starShape(G, x, y, 12 * ds, 6 * ds, 5, t * 3, out, 0.85 * a);
        starShape(G, x, y, 9.5 * ds, 4.2 * ds, 5, t * 3, p.color || '#FFC21F', a);
        break;
      }
      case 'sweat':
        if (out) dropShape(G, x, y, s * 1.3, out, 0.85 * a);
        dropShape(G, x, y, s, p.color || '#7CC8F8', a);
        break;
      case 'tear':
        dropShape(G, x, y, s * 0.9, p.color || '#7CC8F8', a);
        break;
      case 'question': {
        var qc = p.color || (light ? '#5B5FE8' : '#C9CCFF'), wob = Math.sin(p.age * 7) * 0.15, lw = 4.2 * s;
        G.save(); G.translate(x, y); G.rotate(wob);
        if (out) { G.arc(0, -7 * s, 7 * s, Math.PI * 1.05, Math.PI * 2.3, lw + 3.5, out, 0.85 * a); G.line(1.5 * s, -1 * s, 0, 5 * s, lw + 3.5, out, 0.85 * a); G.circle(0, 12 * s, lw * 0.6 + 1.8, out, 0.85 * a); }
        G.arc(0, -7 * s, 7 * s, Math.PI * 1.05, Math.PI * 2.3, lw, qc, a);
        G.line(1.5 * s, -1 * s, 0, 5 * s, lw, qc, a);
        G.circle(0, 12 * s, lw * 0.6, qc, a);
        G.restore();
        break;
      }
      case 'exclaim': {
        var ec = p.color || '#FF8A00';
        if (out) { G.rrect(x - 4.8 * s, y - 16.5 * s, 9.6 * s, 20 * s, 4.8 * s, out, 0.85 * a); G.circle(x, y + 9 * s, 5 * s, out, 0.85 * a); }
        G.rrect(x - 3 * s, y - 15 * s, 6 * s, 17 * s, 3 * s, ec, a);
        G.circle(x, y + 9 * s, 3.2 * s, ec, a);
        break;
      }
      case 'steam': {
        var grow = 1 + p.age * 1.4, stc = p.color || (light ? '#A7AFC2' : '#E6E9F0');
        G.circle(x, y, 6 * s * grow, stc, 0.9 * a);
        G.circle(x + 6 * s * grow, y - 3 * s, 4.6 * s * grow, stc, 0.9 * a);
        G.circle(x - 5 * s * grow, y - 2 * s, 4 * s * grow, stc, 0.9 * a);
        break;
      }
      case 'music': {
        var mc = p.color || '#8E6CFF';
        x += Math.sin(p.age * 5 + p.seed) * 4;
        if (out) { G.circle(x, y, 6.5 * s, out, 0.85 * a); G.rrect(x + 1.8 * s, y - 18 * s, 5.4 * s, 19 * s, 2, out, 0.85 * a); }
        G.circle(x, y, 4.6 * s, mc, a);
        G.rrect(x + 3 * s, y - 16.5 * s, 2.6 * s, 17 * s, 1, mc, a);
        G.tri(x + 5.6 * s, y - 16.5 * s, x + 12 * s, y - 12.5 * s, x + 5.6 * s, y - 9 * s, mc, a);
        break;
      }
      case 'confetti': {
        var cc = p.color || ['#FF5C77', '#FFC21F', '#4FC3F7', '#66D17A', '#B388FF'][Math.floor(p.seed * 7) % 5];
        G.save(); G.translate(x, y); G.rotate(p.rot);
        G.rrect(-3.5 * s, -6 * s, 7 * s, 12 * s, 1.5, cc, a);
        G.restore();
        break;
      }
      case 'puff': {
        var pg = 1 + p.age * 2.2;
        G.circle(x, y, 7 * s * pg, light ? '#FFFFFF' : '#DDE3EA', 0.8 * a);
        G.circle(x + 7 * s * pg, y + 2, 5 * s * pg, light ? '#FFFFFF' : '#DDE3EA', 0.7 * a);
        break;
      }
      default: break;
    }
  }

  // opts: { light: true when the fur behind is light }
  function draw(G, sys, t, opts) {
    var light = !!(opts && opts.light);
    var prev = G.tag('particle');
    for (var i = 0; i < sys.list.length; i++) {
      var p = sys.list[i];
      if (p.age < 0) continue;
      drawOne(G, p, t, light);
    }
    G.tag(prev);
  }

  var api = { TYPES: TYPES, MAX: MAX, createSystem: createSystem, clear: clear, spawn: spawn, burst: burst,
    update: update, draw: draw };
  root.Extras = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
