/*
 * face_draw.js -- PURE draw(ctx, params, t, opts) function.
 *
 * No globals are mutated, no timers, no DOM access beyond the ctx that is
 * handed in. Everything needed to render one frame comes in through the
 * three arguments, so this function can be called from a requestAnimationFrame
 * loop, from a mock context in a test, or (once translated) from an ESP32
 * loop() that owns an LovyanGFX/Arduino_GFX canvas.
 *
 * PORTING NOTES (read this before translating to C++):
 *  - Only rounded rects, ellipses/circles, arcs, straight lines, triangles
 *    and polygons are used. Every "polygon" here is a quad or triangle
 *    built from moveTo/lineTo/closePath+fill, which maps directly to two
 *    fillTriangle() calls in LovyanGFX/Arduino_GFX.
 *  - ctx.ellipse(x,y,rx,ry,rot,start,end) maps to drawEllipse/fillEllipse.
 *  - ctx.arc(x,y,r,start,end) maps to drawArc/fillArc (LovyanGFX has both).
 *  - Colors are passed as CSS hex strings on the web; on the ESP32 side
 *    swap in a small hex->RGB565 helper and keep every color name here.
 *  - Angles in this file are RADIANS for canvas calls, DEGREES in params
 *    (topLidAngleL etc.) -- converted once near the top of each block.
 *  - t is seconds elapsed (float), used only for idle animation (wobble,
 *    panting, tear drip) -- never for state, so calling draw() twice with
 *    the same (ctx, params, t) always paints the same pixels.
 */
(function (root) {
  'use strict';

  var DEG2RAD = Math.PI / 180;

  // -----------------------------------------------------------------------
  // Small path helpers (all portable to fillTriangle/fillArc on ESP32)
  // -----------------------------------------------------------------------

  // Filled rounded rect, built from lines + 4 corner arcs (no arcTo, no
  // native roundRect -- keeps this translatable 1:1 to fillRoundRect()).
  function fillRoundRect(ctx, x, y, w, h, r) {
    r = Math.max(0, Math.min(r, Math.min(w, h) / 2));
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
    ctx.lineTo(x + w, y + h - r);
    ctx.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
    ctx.lineTo(x + r, y + h);
    ctx.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
    ctx.lineTo(x, y + r);
    ctx.arc(x + r, y + r, r, Math.PI, Math.PI * 1.5);
    ctx.closePath();
    ctx.fill();
  }

  // Filled quad from 4 points -- on ESP32 this is fillTriangle() x2.
  function fillQuad(ctx, x0, y0, x1, y1, x2, y2, x3, y3) {
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.lineTo(x3, y3);
    ctx.closePath();
    ctx.fill();
  }

  function fillTri(ctx, x0, y0, x1, y1, x2, y2) {
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.closePath();
    ctx.fill();
  }

  function fillCircle(ctx, x, y, r) {
    ctx.beginPath();
    ctx.arc(x, y, Math.max(0, r), 0, Math.PI * 2);
    ctx.fill();
  }

  // -----------------------------------------------------------------------
  // Eye (base shape + lids + pupil + highlight), drawn for one side.
  // side = -1 for left eye, +1 for right eye.
  // -----------------------------------------------------------------------
  function drawEye(ctx, params, t, side, eyeColor) {
    var p = params;
    var scale = side < 0 ? p.eyeLScale : p.eyeRScale;
    var xOff = side < 0 ? p.eyeLXOffset : p.eyeRXOffset;
    var yOff = side < 0 ? p.eyeLYOffset : p.eyeRYOffset;
    var blink = side < 0 ? p.blinkL : p.blinkR;
    var topLid = side < 0 ? p.topLidL : p.topLidR;
    var bottomLid = side < 0 ? p.bottomLidL : p.bottomLidR;
    var topAngle = (side < 0 ? p.topLidAngleL : p.topLidAngleR) * DEG2RAD;
    var bottomAngle = (side < 0 ? p.bottomLidAngleL : p.bottomLidAngleR) * DEG2RAD;

    var w = p.eyeW * scale * p.squashX;
    var h = p.eyeH * scale * p.squashY;
    var cx = side * (p.eyeGap / 2 + w / 2) + xOff;
    var cy = p.eyeYOffset + yOff;
    var x = cx - w / 2;
    var y = cy - h / 2;
    var r = Math.min(p.eyeRadius, Math.min(w, h) / 2);

    // --- base eye shape --------------------------------------------------
    ctx.fillStyle = eyeColor;
    fillRoundRect(ctx, x, y, w, h, r);

    // --- pupil + highlight (drawn before lids so lids can cover them) ----
    var pupilSize = p.pupilSize;
    if (pupilSize > 0.001) {
      var lookPxX = p.lookX * (w / 2 - w * pupilSize * 0.5) * 0.6;
      var lookPxY = p.lookY * (h / 2 - h * pupilSize * 0.5) * 0.6;
      var pupilCx = cx + p.pupilXOffset + lookPxX;
      var pupilCy = cy + p.pupilYOffset + lookPxY;
      var pupilR = (h * pupilSize) / 2;
      var pupilRx = pupilR * (1 - p.slitPupil * 0.72); // slit narrows horizontally
      ctx.fillStyle = '#111111';
      ctx.beginPath();
      ctx.ellipse(pupilCx, pupilCy, Math.max(1, pupilRx), pupilR, 0, 0, Math.PI * 2);
      ctx.fill();

      if (p.highlightOpacity > 0.001) {
        var hlR = pupilR * p.highlightSize;
        ctx.globalAlpha = p.highlightOpacity;
        ctx.fillStyle = '#FFFFFF';
        fillCircle(ctx, pupilCx - pupilRx * 0.35, pupilCy - pupilR * 0.4, hlR);
        ctx.globalAlpha = 1;
      }
    }

    // --- eyelashes (cat only, drawn from the outer-top corner) -----------
    if (p.eyelashesOpacity > 0.001) {
      ctx.globalAlpha = p.eyelashesOpacity;
      ctx.strokeStyle = '#111111';
      ctx.lineWidth = 3;
      var lashBaseX = cx + side * (w / 2 - 4);
      var lashBaseY = y + 2;
      for (var i = 0; i < 3; i++) {
        var spread = (i - 1) * 7;
        ctx.beginPath();
        ctx.moveTo(lashBaseX + spread * 0.3, lashBaseY);
        ctx.lineTo(lashBaseX + spread + side * 10, lashBaseY - 10 - i * 2);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    // --- lids: black trapezoids covering the eye from top / bottom ------
    var topFrac = Math.max(topLid, blink);
    var bottomFrac = Math.max(bottomLid, blink);
    ctx.fillStyle = p.backgroundColor || '#000000';

    if (topFrac > 0.001) {
      var topDepth = h * topFrac;
      var slantL = Math.tan(topAngle) * (w / 2);
      // trapezoid: covers full width, from above the eye down to topDepth,
      // with the bottom edge slanted by topAngle (outer corner per `side`).
      var by0 = y + topDepth - side * slantL; // outer corner
      var by1 = y + topDepth + side * slantL; // inner corner
      fillQuad(ctx,
        x - 2, y - 2,
        x + w + 2, y - 2,
        side < 0 ? x + w + 2 : x + w + 2, side < 0 ? by1 : by0,
        side < 0 ? x - 2 : x - 2, side < 0 ? by0 : by1
      );
    }
    if (bottomFrac > 0.001) {
      var botDepth = h * bottomFrac;
      var slantB = Math.tan(bottomAngle) * (w / 2);
      var byBase = y + h;
      var by0b = byBase - botDepth - side * slantB;
      var by1b = byBase - botDepth + side * slantB;
      fillQuad(ctx,
        x - 2, y + h + 2,
        x + w + 2, y + h + 2,
        side < 0 ? x + w + 2 : x + w + 2, side < 0 ? by1b : by0b,
        side < 0 ? x - 2 : x - 2, side < 0 ? by0b : by1b
      );
    }
  }

  // -----------------------------------------------------------------------
  // Mouth: a stroked polyline for a closed mouth, or a filled open shape.
  // Blends toward a cat "omega" (w) shape as catOmega -> 1.
  // -----------------------------------------------------------------------
  function drawMouth(ctx, params, t, eyeColor) {
    var p = params;
    var cx = 0, cy = p.mouthYOffset;
    var halfW = p.mouthWidth / 2;
    var wobble = p.mouthWobble > 0.001 ? Math.sin(t * 14) * 3 * p.mouthWobble : 0;
    var smirk = p.smirkSide; // -1..1, shifts one corner up

    if (p.mouthOpen < 0.05) {
      // --- closed / smiling mouth: 7 sampled points across a parabola ---
      var N = 6;
      var pts = [];
      for (var i = 0; i <= N; i++) {
        var tx = (i / N) * 2 - 1; // -1..1
        var x = cx + tx * halfW;
        var baseCurve = p.mouthCurve * (1 - tx * tx) * 26;
        // cat omega: three little humps instead of one smooth curve
        var omega = Math.sin(tx * Math.PI * 1.5 + Math.PI / 2) * 10 - 6;
        var y = cy - lerpNum(baseCurve, omega, p.catOmega);
        // smirk lifts the right corner (tx>0) or left corner (tx<0)
        y -= smirk * tx * 12;
        y += wobble * (1 - Math.abs(tx));
        pts.push([x, y]);
      }
      ctx.strokeStyle = eyeColor;
      ctx.lineWidth = 5;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (var j = 1; j < pts.length; j++) ctx.lineTo(pts[j][0], pts[j][1]);
      ctx.stroke();
    } else {
      // --- open mouth: filled rounded shape + optional tongue ------------
      var openH = 14 + p.mouthOpen * 46;
      var mw = halfW * (1 - Math.abs(smirk) * 0.15);
      ctx.fillStyle = '#3A0E10';
      fillRoundRect(ctx, cx - mw, cy - openH * 0.15, mw * 2, openH, Math.min(18, openH / 2));

      if (p.tongueOut > 0.001) {
        var pantBob = p.pantSpeed > 0.001 ? Math.abs(Math.sin(t * p.pantSpeed)) : 1;
        var tongueH = openH * 0.55 * p.tongueOut * (0.6 + 0.4 * pantBob);
        var tongueW = mw * 0.6;
        var tongueCy = cy - openH * 0.15 + openH - tongueH * 0.4;
        ctx.fillStyle = '#FF7A8A';
        fillRoundRect(ctx, cx - tongueW / 2, tongueCy, tongueW, tongueH, tongueW / 2.2);
      }
    }
  }

  function lerpNum(a, b, t) { return a + (b - a) * t; }

  // -----------------------------------------------------------------------
  // Blush / tears
  // -----------------------------------------------------------------------
  function drawBlush(ctx, params) {
    if (params.blushOpacity < 0.001) return;
    var p = params;
    ctx.globalAlpha = p.blushOpacity;
    ctx.fillStyle = '#FF6B81';
    var bx = p.eyeGap / 2 + p.eyeW * 0.55;
    var by = p.eyeYOffset + p.eyeH * 0.55;
    fillCircle(ctx, -bx, by, 16);
    fillCircle(ctx, bx, by, 16);
    ctx.globalAlpha = 1;
  }

  function drawTears(ctx, params, t) {
    if (params.tearsOpacity < 0.001) return;
    var p = params;
    var drip = (t * 40) % 30; // falling motion, loops every 30px
    ctx.globalAlpha = p.tearsOpacity;
    ctx.fillStyle = '#7FD8FF';
    [-1, 1].forEach(function (side) {
      var tx = side * (p.eyeGap / 2 + p.eyeW * 0.3);
      var ty = p.eyeYOffset + p.eyeH * 0.55 + drip;
      fillCircle(ctx, tx, ty, 5);
      fillTri(ctx, tx - 5, ty, tx + 5, ty, tx, ty - 9);
    });
    ctx.globalAlpha = 1;
  }

  function drawWhiskers(ctx, params) {
    if (params.whiskersOpacity < 0.001) return;
    var p = params;
    ctx.globalAlpha = params.whiskersOpacity;
    ctx.strokeStyle = '#DDDDDD';
    ctx.lineWidth = 2;
    var originY = p.mouthYOffset - 6;
    [-1, 1].forEach(function (side) {
      for (var i = 0; i < 3; i++) {
        var oy = originY + (i - 1) * 10;
        var len = 46 - Math.abs(i - 1) * 8;
        ctx.beginPath();
        ctx.moveTo(side * 30, oy);
        ctx.lineTo(side * (30 + len), oy + (i - 1) * 6);
        ctx.stroke();
      }
    });
    ctx.globalAlpha = 1;
  }

  // -----------------------------------------------------------------------
  // Main entry point.
  // opts: { eyeColor, backgroundColor, glow (bool, browser-only extra) }
  // -----------------------------------------------------------------------
  function draw(ctx, params, t, opts) {
    opts = opts || {};
    var eyeColor = opts.eyeColor || '#FFFFFF';
    var bg = opts.backgroundColor || '#000000';
    var w = opts.width || 480;
    var h = opts.height || 272;
    var p = params;
    p.backgroundColor = bg; // stashed so drawEye's lids match the page bg

    ctx.save();
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    var cx = w / 2;
    var cy = h / 2 + (p.bobOffset || 0);

    ctx.translate(cx, cy);
    ctx.rotate((p.faceTilt || 0) * DEG2RAD);
    var breath = p.breathScale || 1;
    ctx.scale(breath, breath);

    if (opts.glow) {
      ctx.shadowColor = eyeColor;
      ctx.shadowBlur = 18;
    }

    drawEye(ctx, p, t, -1, eyeColor);
    drawEye(ctx, p, t, 1, eyeColor);

    if (opts.glow) { ctx.shadowBlur = 0; }

    drawWhiskers(ctx, p);
    drawBlush(ctx, p);
    drawTears(ctx, p, t);
    drawMouth(ctx, p, t, eyeColor);

    ctx.restore();
  }

  var api = { draw: draw, fillRoundRect: fillRoundRect, fillQuad: fillQuad, fillTri: fillTri, fillCircle: fillCircle };

  root.FaceDraw = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : global);
