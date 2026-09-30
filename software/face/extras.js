/*
 * extras.js -- pop-up particles (hearts, Zzz, sweat drop, sparkles,
 * confetti, ?, !, anger mark, music notes, dizzy stars, tear drops).
 *
 * A "system" is a plain array of particle objects owned by the caller
 * (app.js). spawn() adds one, update(dt) ages and moves them all, draw()
 * paints them. Everything is built from the same portable primitives as
 * face_draw.js (circles, triangles, quads, arcs, lines) so this can be
 * ported to the ESP32 too, just with a much smaller particle budget.
 *
 * Classic script; also loadable from Node for the smoke test (draw() is
 * exercised there against a mock ctx).
 */
(function (root) {
  'use strict';

  var TWO_PI = Math.PI * 2;

  // Default lifetime (seconds) and rise speed (px/s) per particle type.
  var TYPE_DEFAULTS = {
    heart: { life: 1.4, vy: -55, vx: 0, gravity: 0, spin: 0 },
    zzz: { life: 1.8, vy: -30, vx: 18, gravity: 0, spin: 0 },
    sweat: { life: 1.1, vy: 40, vx: 0, gravity: 60, spin: 0 },
    sparkle: { life: 0.9, vy: -20, vx: 0, gravity: 0, spin: 0 },
    confetti: { life: 1.6, vy: -80, vx: 0, gravity: 160, spin: 6 },
    question: { life: 1.3, vy: -45, vx: 0, gravity: 0, spin: 0 },
    exclaim: { life: 1.1, vy: -50, vx: 0, gravity: 0, spin: 0 },
    anger: { life: 1.0, vy: -10, vx: 0, gravity: 0, spin: 0 },
    music: { life: 1.5, vy: -40, vx: 12, gravity: 0, spin: 0 },
    dizzyStar: { life: 999, vy: 0, vx: 0, gravity: 0, spin: 0, orbit: true },
    tear: { life: 1.2, vy: 70, vx: 0, gravity: 90, spin: 0 }
  };

  function createSystem() { return { particles: [] }; }

  function clear(sys) { sys.particles.length = 0; }

  function spawn(sys, type, x, y, opts) {
    var def = TYPE_DEFAULTS[type] || TYPE_DEFAULTS.sparkle;
    opts = opts || {};
    sys.particles.push({
      type: type,
      x: x, y: y,
      vx: (def.vx || 0) * (0.7 + Math.random() * 0.6) * (Math.random() < 0.5 ? -1 : 1) + (opts.vx || 0),
      vy: def.vy + (opts.vy || 0),
      gravity: def.gravity || 0,
      age: 0,
      life: opts.life || def.life,
      spin: (def.spin || 0) * (Math.random() < 0.5 ? -1 : 1),
      rotation: opts.rotation || Math.random() * TWO_PI,
      scale: opts.scale || (0.85 + Math.random() * 0.3),
      color: opts.color || null,
      seed: Math.random() * 1000,
      orbit: !!def.orbit,
      orbitR: opts.orbitR || 46,
      orbitSpeed: opts.orbitSpeed || 2.2,
      orbitCx: x, orbitCy: y
    });
  }

  function spawnBurst(sys, type, x, y, count, opts) {
    for (var i = 0; i < count; i++) {
      var angle = (i / count) * TWO_PI;
      var spread = 30;
      spawn(sys, type, x + Math.cos(angle) * 4, y + Math.sin(angle) * 4, Object.assign(
        { vx: Math.cos(angle) * spread, vy: Math.sin(angle) * spread - 20 }, opts || {}
      ));
    }
  }

  function update(sys, dt) {
    var list = sys.particles;
    for (var i = list.length - 1; i >= 0; i--) {
      var p = list[i];
      p.age += dt;
      if (p.age >= p.life) { list.splice(i, 1); continue; }
      if (!p.orbit) {
        p.vy += p.gravity * dt;
        p.x += p.vx * dt;
        p.y += p.vy * dt;
        p.rotation += p.spin * dt;
      }
    }
  }

  // -----------------------------------------------------------------------
  // Shape helpers (mirrors face_draw.js's style so both translate the same
  // way to LovyanGFX/Arduino_GFX primitives).
  // -----------------------------------------------------------------------
  function fillCircle(ctx, x, y, r) {
    ctx.beginPath(); ctx.arc(x, y, Math.max(0, r), 0, TWO_PI); ctx.fill();
  }
  function fillTri(ctx, x0, y0, x1, y1, x2, y2) {
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.lineTo(x2, y2); ctx.closePath(); ctx.fill();
  }
  function fillQuad(ctx, x0, y0, x1, y1, x2, y2, x3, y3) {
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.lineTo(x2, y2); ctx.lineTo(x3, y3); ctx.closePath(); ctx.fill();
  }
  function fillStar(ctx, cx, cy, outerR, innerR, points, rotation) {
    ctx.beginPath();
    for (var i = 0; i < points * 2; i++) {
      var r = (i % 2 === 0) ? outerR : innerR;
      var a = rotation + (i / (points * 2)) * TWO_PI;
      var x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.closePath(); ctx.fill();
  }
  function strokeLine(ctx, x0, y0, x1, y1, width, color) {
    ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
  }

  function drawHeart(ctx, x, y, s, color) {
    ctx.fillStyle = color;
    var r = 8 * s;
    fillCircle(ctx, x - r * 0.55, y, r * 0.6);
    fillCircle(ctx, x + r * 0.55, y, r * 0.6);
    fillTri(ctx, x - r * 1.1, y + r * 0.15, x + r * 1.1, y + r * 0.15, x, y + r * 1.6);
  }

  function drawZigzagLetter(ctx, x, y, s, color) {
    // A single "Z" as a stroked zigzag -- 3 line segments.
    ctx.strokeStyle = color; ctx.lineWidth = 2.5 * s; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    var w = 9 * s, h = 10 * s;
    ctx.beginPath();
    ctx.moveTo(x - w, y - h); ctx.lineTo(x + w, y - h);
    ctx.lineTo(x - w, y + h); ctx.lineTo(x + w, y + h);
    ctx.stroke();
  }

  function drawSweat(ctx, x, y, s, color) {
    ctx.fillStyle = color;
    fillCircle(ctx, x, y, 5 * s);
    fillTri(ctx, x - 5 * s, y, x + 5 * s, y, x, y - 9 * s);
  }

  function drawTear(ctx, x, y, s, color) {
    ctx.fillStyle = color;
    fillCircle(ctx, x, y, 5 * s);
    fillTri(ctx, x - 5 * s, y, x + 5 * s, y, x, y - 9 * s);
  }

  function drawSparkle(ctx, x, y, s, rotation, color) {
    ctx.fillStyle = color;
    fillStar(ctx, x, y, 7 * s, 2.5 * s, 4, rotation);
  }

  function drawConfetti(ctx, x, y, s, rotation, color) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(rotation);
    ctx.fillStyle = color;
    ctx.fillRect(-4 * s, -6 * s, 8 * s, 12 * s);
    ctx.restore();
  }

  function drawQuestion(ctx, x, y, s, color) {
    ctx.strokeStyle = color; ctx.lineWidth = 3 * s; ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(x, y - 6 * s, 6 * s, Math.PI * 1.1, Math.PI * 2.35);
    ctx.lineTo(x, y + 2 * s);
    ctx.stroke();
    ctx.fillStyle = color;
    fillCircle(ctx, x, y + 10 * s, 2 * s);
  }

  function drawExclaim(ctx, x, y, s, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x - 2 * s, y - 12 * s, 4 * s, 14 * s);
    fillCircle(ctx, x, y + 6 * s, 2.2 * s);
  }

  function drawAnger(ctx, x, y, s, rotation, color) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(rotation);
    ctx.strokeStyle = color; ctx.lineWidth = 3 * s; ctx.lineCap = 'round';
    var arm = 8 * s;
    ctx.beginPath(); ctx.moveTo(-arm, -arm); ctx.lineTo(arm, arm); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(arm, -arm); ctx.lineTo(-arm, arm); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, -arm * 1.3); ctx.lineTo(0, arm * 1.3); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(-arm * 1.3, 0); ctx.lineTo(arm * 1.3, 0); ctx.stroke();
    ctx.restore();
  }

  function drawMusicNote(ctx, x, y, s, color) {
    ctx.fillStyle = color;
    fillCircle(ctx, x, y, 4 * s);
    ctx.fillRect(x + 3.5 * s, y - 16 * s, 2 * s, 17 * s);
    fillTri(ctx, x + 5.5 * s, y - 16 * s, x + 11 * s, y - 13 * s, x + 5.5 * s, y - 9 * s);
  }

  function draw(ctx, sys, t) {
    var list = sys.particles;
    for (var i = 0; i < list.length; i++) {
      var p = list[i];
      var lifeFrac = p.age / p.life;
      var alpha = p.orbit ? 1 : Math.max(0, 1 - Math.pow(lifeFrac, 2));
      ctx.globalAlpha = alpha;

      var x = p.x, y = p.y;
      if (p.orbit) {
        var a = p.seed + t * p.orbitSpeed;
        x = p.orbitCx + Math.cos(a) * p.orbitR;
        y = p.orbitCy + Math.sin(a) * p.orbitR * 0.5;
      }

      switch (p.type) {
        case 'heart': drawHeart(ctx, x, y, p.scale, p.color || '#FF5C77'); break;
        case 'zzz': drawZigzagLetter(ctx, x, y, p.scale * (1 - lifeFrac * 0.3), p.color || '#BFE3FF'); break;
        case 'sweat': drawSweat(ctx, x, y, p.scale, p.color || '#7FD8FF'); break;
        case 'sparkle': drawSparkle(ctx, x, y, p.scale, p.rotation, p.color || '#FFE98A'); break;
        case 'confetti': drawConfetti(ctx, x, y, p.scale, p.rotation, p.color || confettiColor(p.seed)); break;
        case 'question': drawQuestion(ctx, x, y, p.scale, p.color || '#FFFFFF'); break;
        case 'exclaim': drawExclaim(ctx, x, y, p.scale, p.color || '#FFD23F'); break;
        case 'anger': drawAnger(ctx, x, y, p.scale, p.rotation, p.color || '#FF4444'); break;
        case 'music': drawMusicNote(ctx, x, y, p.scale, p.color || '#B388FF'); break;
        case 'dizzyStar': drawSparkle(ctx, x, y, p.scale, t * 3, p.color || '#FFE98A'); break;
        case 'tear': drawTear(ctx, x, y, p.scale, p.color || '#7FD8FF'); break;
        default: break;
      }
      ctx.globalAlpha = 1;
    }
  }

  function confettiColor(seed) {
    var colors = ['#FF5C77', '#FFD23F', '#59D9FF', '#8CFF8C', '#B388FF'];
    return colors[Math.floor(seed) % colors.length];
  }

  var api = { createSystem: createSystem, clear: clear, spawn: spawn, spawnBurst: spawnBurst, update: update, draw: draw };
  root.Extras = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
