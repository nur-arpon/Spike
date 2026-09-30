/*
 * gfx.js -- the tiny drawing abstraction every face pixel goes through.
 *
 * WHY: the face must port to the robot's ESP32-S3 screen (LovyanGFX on the
 * Guition JC4827W543). So the renderer may ONLY use primitives that library
 * also has. This file is the whole list:
 *
 *   rect      fillRect                      (background / theme dim)
 *   circle    fillSmoothCircle              (anti-aliased)
 *   ellipse   fillEllipse (axis-aligned; rotated ones become a 32-gon)
 *   rrect     fillSmoothRoundRect
 *   tri       fillTriangle
 *   poly      CONVEX polygon = triangle fan of fillTriangle
 *   mpoly     x-monotone "band" polygon = column strips of fillTriangle
 *   line      drawWideLine (thick line, round caps)
 *   polyline  a chain of drawWideLine segments
 *   arc       thick arc stroke = fillArc(x,y,r0,r1,a0,a1)
 *   wedge     filled pie slice = fillArc(x,y,0,r,a0,a1)
 *   alpha     every call takes an alpha; LovyanGFX blends with alpha too
 *
 * No clip(), no gradients, no shadowBlur, no filters. Anything that needs a
 * clipped shape (eyelids, a wobbling waterline, an iris peeking past the eye
 * edge) is clipped ANALYTICALLY with clipConvex() below, which is plain maths
 * the C++ port copies line for line.
 *
 * Transforms: save/restore/translate/rotate/scale are tracked here as a 2x3
 * matrix. On the ESP32 the same matrix is applied to points in software; the
 * whole-face head tilt can instead be done by drawing into a PSRAM sprite and
 * calling pushRotateZoomWithAA (see DESIGN.md).
 *
 * RECORD MODE (tests): create(ctx, {record:true}) also logs every primitive
 * with its device-space bounding box, the current feature tag and alpha, and
 * throws on NaN. ctx may be null in record mode (no pixels, just geometry).
 *
 * Classic script: attaches to window.Gfx, or module.exports in Node.
 */
(function (root) {
  'use strict';

  var TAU = Math.PI * 2;

  // ---------------------------------------------------------------------
  // Pure geometry helpers (exported; used by face_draw.js and tests)
  // ---------------------------------------------------------------------

  // Sutherland-Hodgman: clip polygon `subject` (flat [x0,y0,x1,y1,...]) by
  // a CONVEX polygon `clip` (flat, either winding). Returns a flat array
  // (possibly empty). Result is convex when subject is convex.
  function clipConvex(subject, clip) {
    var out = subject;
    var n = clip.length / 2;
    if (n < 3 || subject.length < 6) return [];
    // winding sign of the clip polygon
    var area = 0;
    for (var i = 0; i < n; i++) {
      var j = (i + 1) % n;
      area += clip[i * 2] * clip[j * 2 + 1] - clip[j * 2] * clip[i * 2 + 1];
    }
    var sgn = area >= 0 ? 1 : -1;
    for (var e = 0; e < n && out.length >= 6; e++) {
      var ax = clip[e * 2], ay = clip[e * 2 + 1];
      var f = (e + 1) % n;
      var bx = clip[f * 2], by = clip[f * 2 + 1];
      out = clipHalfPlane(out, ax, ay, bx, by, sgn);
    }
    return out.length >= 6 ? out : [];
  }

  // Keep the part of `poly` on the inside (left for sgn=+1) of line a->b.
  function clipHalfPlane(poly, ax, ay, bx, by, sgn) {
    var res = [];
    var m = poly.length / 2;
    if (m === 0) return res;
    function side(x, y) { return sgn * ((bx - ax) * (y - ay) - (by - ay) * (x - ax)); }
    var px = poly[(m - 1) * 2], py = poly[(m - 1) * 2 + 1];
    var ps = side(px, py);
    for (var i = 0; i < m; i++) {
      var cx = poly[i * 2], cy = poly[i * 2 + 1];
      var cs = side(cx, cy);
      if (cs >= 0) {
        if (ps < 0) { var k = ps / (ps - cs); res.push(px + (cx - px) * k, py + (cy - py) * k); }
        res.push(cx, cy);
      } else if (ps >= 0) {
        var k2 = ps / (ps - cs); res.push(px + (cx - px) * k2, py + (cy - py) * k2);
      }
      px = cx; py = cy; ps = cs;
    }
    return res;
  }

  // Keep the part of `poly` ABOVE (smaller y) the polyline `line` (flat,
  // x increasing). Correct for any convex poly when the polyline is a
  // concave function (sags down or is straight) -- true for all our lids.
  function clipAbove(poly, line) {
    var out = poly;
    for (var i = 0; i + 3 < line.length && out.length >= 6; i += 2) {
      // left of a->b where a->b runs toward -x means "above" for +x lines;
      // we pass points right-to-left so "left side" = smaller y.
      out = clipHalfPlane(out, line[i + 2], line[i + 3], line[i], line[i + 1], 1);
    }
    return out.length >= 6 ? out : [];
  }

  // Keep the part of `poly` BELOW (larger y) the polyline `line` (x
  // increasing). Correct when the polyline is a convex function (bulges up).
  function clipBelow(poly, line) {
    var out = poly;
    for (var i = 0; i + 3 < line.length && out.length >= 6; i += 2) {
      out = clipHalfPlane(out, line[i], line[i + 1], line[i + 2], line[i + 3], 1);
    }
    return out.length >= 6 ? out : [];
  }

  function ellipsePoly(cx, cy, rx, ry, n, rot) {
    n = n || 32;
    var c = Math.cos(rot || 0), s = Math.sin(rot || 0);
    var pts = [];
    for (var i = 0; i < n; i++) {
      var a = (i / n) * TAU;
      var x = Math.cos(a) * rx, y = Math.sin(a) * ry;
      pts.push(cx + x * c - y * s, cy + x * s + y * c);
    }
    return pts;
  }

  function isConvex(pts) {
    var n = pts.length / 2;
    if (n < 3) return false;
    var sign = 0;
    for (var i = 0; i < n; i++) {
      var ax = pts[i * 2], ay = pts[i * 2 + 1];
      var b = (i + 1) % n, c = (i + 2) % n;
      var bx = pts[b * 2], by = pts[b * 2 + 1];
      var cx = pts[c * 2], cy = pts[c * 2 + 1];
      var cr = (bx - ax) * (cy - by) - (by - ay) * (cx - bx);
      if (Math.abs(cr) < 1e-6) continue;
      var sg = cr > 0 ? 1 : -1;
      if (sign === 0) sign = sg; else if (sg !== sign) return false;
    }
    return true;
  }

  function pointInConvex(pts, x, y) {
    var n = pts.length / 2, sign = 0;
    for (var i = 0; i < n; i++) {
      var j = (i + 1) % n;
      var cr = (pts[j * 2] - pts[i * 2]) * (y - pts[i * 2 + 1]) - (pts[j * 2 + 1] - pts[i * 2 + 1]) * (x - pts[i * 2]);
      if (Math.abs(cr) < 1e-9) continue;
      var sg = cr > 0 ? 1 : -1;
      if (sign === 0) sign = sg; else if (sg !== sign) return false;
    }
    return true;
  }

  // ---------------------------------------------------------------------
  // Colour helpers (hex only, so the C++ port maps 1:1 to RGB565)
  // ---------------------------------------------------------------------
  function hexToRgb(h) {
    h = String(h || '#000000').replace('#', '');
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    var n = parseInt(h, 16);
    if (isNaN(n)) n = 0;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function rgbToHex(r, g, b) {
    function c(v) { v = Math.max(0, Math.min(255, Math.round(v))); return (v < 16 ? '0' : '') + v.toString(16); }
    return '#' + c(r) + c(g) + c(b);
  }
  // mix(a, b, t): t=0 -> a, t=1 -> b
  function mix(a, b, t) {
    var A = hexToRgb(a), B = hexToRgb(b);
    return rgbToHex(A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t, A[2] + (B[2] - A[2]) * t);
  }
  function shade(c, amt) { return amt < 0 ? mix(c, '#000000', -amt) : mix(c, '#FFFFFF', amt); }
  function luminance(c) { var A = hexToRgb(c); return (0.299 * A[0] + 0.587 * A[1] + 0.114 * A[2]) / 255; }

  // ---------------------------------------------------------------------
  // The drawing context wrapper
  // ---------------------------------------------------------------------
  function create(ctx, opts) {
    opts = opts || {};
    var record = !!opts.record;
    var m = [1, 0, 0, 1, 0, 0];          // a b c d e f  (x' = a x + c y + e)
    var stack = [];
    var curTag = 'face';
    var log = record ? [] : null;

    function tx(x, y) { return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]; }

    function note(kind, pts, color, alpha, extra) {
      if (!record) return;
      var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      for (var i = 0; i < pts.length; i += 2) {
        var p = tx(pts[i], pts[i + 1]);
        if (!isFinite(p[0]) || !isFinite(p[1])) {
          throw new Error('gfx: non-finite coordinate in ' + kind + ' (tag ' + curTag + ')');
        }
        if (p[0] < minX) minX = p[0]; if (p[0] > maxX) maxX = p[0];
        if (p[1] < minY) minY = p[1]; if (p[1] > maxY) maxY = p[1];
      }
      if (!isFinite(alpha)) throw new Error('gfx: non-finite alpha (tag ' + curTag + ')');
      var pad = (extra && extra.pad) || 0;
      var sc = Math.sqrt(Math.abs(m[0] * m[3] - m[1] * m[2]));
      pad *= sc;
      log.push({ kind: kind, tag: curTag, color: color, alpha: alpha,
        x0: minX - pad, y0: minY - pad, x1: maxX + pad, y1: maxY + pad,
        convex: extra && extra.convex });
    }

    function setFill(color, alpha) {
      if (!ctx) return;
      ctx.globalAlpha = alpha == null ? 1 : Math.max(0, Math.min(1, alpha));
      ctx.fillStyle = color;
    }
    function setStroke(color, w, alpha) {
      if (!ctx) return;
      ctx.globalAlpha = alpha == null ? 1 : Math.max(0, Math.min(1, alpha));
      ctx.strokeStyle = color;
      ctx.lineWidth = Math.max(0.5, w);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
    }
    function skip(alpha) { return alpha != null && alpha <= 0.003; }

    var G = {
      log: log,
      tag: function (t) { var prev = curTag; curTag = t; return prev; },
      getTag: function () { return curTag; },
      save: function () { stack.push(m.slice()); if (ctx) ctx.save(); },
      restore: function () { if (stack.length) m = stack.pop(); if (ctx) ctx.restore(); },
      translate: function (x, y) {
        m[4] += m[0] * x + m[2] * y; m[5] += m[1] * x + m[3] * y;
        if (ctx) ctx.translate(x, y);
      },
      rotate: function (r) {
        var c = Math.cos(r), s = Math.sin(r);
        var a = m[0], b = m[1], cc = m[2], d = m[3];
        m[0] = a * c + cc * s; m[1] = b * c + d * s;
        m[2] = -a * s + cc * c; m[3] = -b * s + d * c;
        if (ctx) ctx.rotate(r);
      },
      scale: function (sx, sy) {
        m[0] *= sx; m[1] *= sx; m[2] *= sy; m[3] *= sy;
        if (ctx) ctx.scale(sx, sy);
      },
      matrix: function () { return m.slice(); },
      toDevice: function (x, y) { return tx(x, y); },

      rect: function (x, y, w, h, color, alpha) {
        if (skip(alpha)) return;
        note('rect', [x, y, x + w, y + h], color, alpha == null ? 1 : alpha);
        if (ctx) { setFill(color, alpha); ctx.fillRect(x, y, w, h); }
      },
      circle: function (x, y, r, color, alpha) {
        if (skip(alpha) || !(r > 0.05)) return;
        note('circle', [x - r, y - r, x + r, y + r, x - r, y + r, x + r, y - r], color, alpha == null ? 1 : alpha);
        if (ctx) { setFill(color, alpha); ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill(); }
      },
      ellipse: function (x, y, rx, ry, rot, color, alpha) {
        if (skip(alpha) || !(rx > 0.05) || !(ry > 0.05)) return;
        note('ellipse', ellipsePoly(x, y, rx, ry, 12, rot), color, alpha == null ? 1 : alpha);
        if (ctx) { setFill(color, alpha); ctx.beginPath(); ctx.ellipse(x, y, rx, ry, rot || 0, 0, TAU); ctx.fill(); }
      },
      rrect: function (x, y, w, h, r, color, alpha) {
        if (skip(alpha) || !(w > 0.05) || !(h > 0.05)) return;
        r = Math.max(0, Math.min(r, w / 2, h / 2));
        note('rrect', [x, y, x + w, y + h, x, y + h, x + w, y], color, alpha == null ? 1 : alpha);
        if (!ctx) return;
        setFill(color, alpha);
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y); ctx.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
        ctx.lineTo(x + w, y + h - r); ctx.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
        ctx.lineTo(x + r, y + h); ctx.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
        ctx.lineTo(x, y + r); ctx.arc(x + r, y + r, r, Math.PI, Math.PI * 1.5);
        ctx.closePath(); ctx.fill();
      },
      tri: function (x0, y0, x1, y1, x2, y2, color, alpha) {
        if (skip(alpha)) return;
        note('tri', [x0, y0, x1, y1, x2, y2], color, alpha == null ? 1 : alpha);
        if (!ctx) return;
        setFill(color, alpha);
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.lineTo(x2, y2); ctx.closePath(); ctx.fill();
      },
      // CONVEX polygon only (portable as a triangle fan). Tests check this.
      poly: function (pts, color, alpha) {
        if (skip(alpha) || !pts || pts.length < 6) return;
        note('poly', pts, color, alpha == null ? 1 : alpha, { convex: record ? isConvex(pts) : true });
        if (!ctx) return;
        setFill(color, alpha);
        ctx.beginPath(); ctx.moveTo(pts[0], pts[1]);
        for (var i = 2; i < pts.length; i += 2) ctx.lineTo(pts[i], pts[i + 1]);
        ctx.closePath(); ctx.fill();
      },
      // X-MONOTONE polygon: a top chain left->right then a bottom chain
      // right->left (what face_draw's band() emits). Portable as column
      // strips: two fillTriangle per column. Used for eyelids, the open
      // mouth under a wavy lip, the tongue and the teary waterline.
      mpoly: function (pts, color, alpha) {
        if (skip(alpha) || !pts || pts.length < 6) return;
        note('mpoly', pts, color, alpha == null ? 1 : alpha);
        if (!ctx) return;
        setFill(color, alpha);
        ctx.beginPath(); ctx.moveTo(pts[0], pts[1]);
        for (var i = 2; i < pts.length; i += 2) ctx.lineTo(pts[i], pts[i + 1]);
        ctx.closePath(); ctx.fill();
      },
      line: function (x0, y0, x1, y1, w, color, alpha) {
        if (skip(alpha) || !(w > 0.05)) return;
        note('line', [x0, y0, x1, y1], color, alpha == null ? 1 : alpha, { pad: w / 2 });
        if (!ctx) return;
        setStroke(color, w, alpha);
        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
      },
      polyline: function (pts, w, color, alpha) {
        if (skip(alpha) || !pts || pts.length < 4 || !(w > 0.05)) return;
        note('polyline', pts, color, alpha == null ? 1 : alpha, { pad: w / 2 });
        if (!ctx) return;
        setStroke(color, w, alpha);
        ctx.beginPath(); ctx.moveTo(pts[0], pts[1]);
        for (var i = 2; i < pts.length; i += 2) ctx.lineTo(pts[i], pts[i + 1]);
        ctx.stroke();
      },
      arc: function (x, y, r, a0, a1, w, color, alpha) {
        if (skip(alpha) || !(r > 0.05) || !(w > 0.05)) return;
        var pts = [];
        for (var i = 0; i <= 8; i++) { var a = a0 + (a1 - a0) * i / 8; pts.push(x + Math.cos(a) * r, y + Math.sin(a) * r); }
        note('arc', pts, color, alpha == null ? 1 : alpha, { pad: w / 2 });
        if (!ctx) return;
        setStroke(color, w, alpha);
        ctx.beginPath(); ctx.arc(x, y, r, a0, a1, a1 < a0); ctx.stroke();
      },
      wedge: function (x, y, r, a0, a1, color, alpha) {
        if (skip(alpha) || !(r > 0.05)) return;
        var pts = [x, y];
        for (var i = 0; i <= 8; i++) { var a = a0 + (a1 - a0) * i / 8; pts.push(x + Math.cos(a) * r, y + Math.sin(a) * r); }
        note('wedge', pts, color, alpha == null ? 1 : alpha);
        if (!ctx) return;
        setFill(color, alpha);
        ctx.beginPath(); ctx.moveTo(x, y); ctx.arc(x, y, r, a0, a1, a1 < a0); ctx.closePath(); ctx.fill();
      }
    };
    return G;
  }

  var api = {
    create: create,
    clipConvex: clipConvex,
    clipHalfPlane: clipHalfPlane,
    clipAbove: clipAbove,
    clipBelow: clipBelow,
    ellipsePoly: ellipsePoly,
    isConvex: isConvex,
    pointInConvex: pointInConvex,
    hexToRgb: hexToRgb,
    rgbToHex: rgbToHex,
    mix: mix,
    shade: shade,
    luminance: luminance
  };
  root.Gfx = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
