/* Spike website - the light field: a dusky fbm-noise "aurora" behind every page, a warm spotlight that follows the
   pointer, and a layer of fine dust that drifts on a curl-noise flow and is pushed and swirled by the cursor (or a
   finger). Raw WebGL, no library.
   The aurora is adapted from the "light field" in Nur's portfolio (NurIfranArpon-v2/assets/js/app.js); the dark mode
   matches its Spike page (#15100c page, #6b3f22 glow, #d9956a accent). Every colour and strength is a CSS variable
   in site.css (--field-*, --dust-*, per light/dark), re-read when the page switches mode.
   Rules it keeps:
   - alpha stays ON. An opaque full-screen canvas can be handed to the GPU as a video overlay, and some Windows GPUs
     then read its colours as YUV, which turned the whole page bright green on Nur's laptop. No 'low-power' either.
   - the page's CSS background stays behind the canvases, so a failed or missing WebGL still looks right.
   - text stays readable: a soft local scrim (a blurred mask of where the text is) fades the field back to the page
     colour behind words, so the effect stays strong everywhere else.
   - aurora at half resolution and ~30 fps; dust at full resolution (pixel ratio capped) with a CPU sim in typed
     arrays that drops particles if it ever costs more than about 1 ms. Both stop while the tab is hidden and while
     the full-screen 3D stage (<exploded-view mode="scroll">, data-pinned) covers the screen. Reduced motion: one
     still frame (redrawn only to keep the scrim under the text when you scroll), dust static, no cursor effect. */
(function () {
  "use strict";
  var cv = document.getElementById("field");
  if (!cv) return;
  var root = document.documentElement;
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var GLOPT = { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false };

  var gl = null;
  try { gl = cv.getContext("webgl", GLOPT); } catch (e) { gl = null; }
  if (!gl) { cv.setAttribute("data-off", ""); return; } // the CSS background shows instead

  /* ---------- colours and knobs, from site.css ---------- */
  // colours arrive as "#rrggbb" or "rgb()/rgba()"; both must parse, or the field draws garbage (it flashed green)
  var lastRGB = {};
  function rgb(s, key) {
    s = (s || "").trim();
    var v = null, m = /^rgba?\(([^)]+)\)/i.exec(s);
    if (m) { var p = m[1].split(/[\s,\/]+/).map(parseFloat); v = [p[0] / 255, p[1] / 255, p[2] / 255]; }
    else if (/^#?[0-9a-f]{6}$/i.test(s)) { s = s.replace("#", ""); v = [parseInt(s.substr(0, 2), 16) / 255, parseInt(s.substr(2, 2), 16) / 255, parseInt(s.substr(4, 2), 16) / 255]; }
    else if (/^#?[0-9a-f]{3}$/i.test(s)) { s = s.replace("#", ""); v = [0, 1, 2].map(function (i) { return parseInt(s[i] + s[i], 16) / 255; }); }
    if (!v || v.some(isNaN)) return lastRGB[key] || [0.984, 0.961, 0.925]; // last good colour, else the light cream page
    lastRGB[key] = v; return v;
  }
  function num(cs, name, dflt) { var v = parseFloat(cs.getPropertyValue(name)); return isNaN(v) ? dflt : v; }
  function readLook() {
    var cs = getComputedStyle(root);
    var bg = rgb(cs.getPropertyValue("--bg"), "bg");
    return {
      bg: bg,
      glow: rgb(cs.getPropertyValue("--field-glow"), "glow"),
      accent: rgb(cs.getPropertyValue("--field-accent") || cs.getPropertyValue("--accent"), "accent"),
      dustCol: rgb(cs.getPropertyValue("--dust-color"), "dust"),
      dark: 0.2126 * bg[0] + 0.7152 * bg[1] + 0.0722 * bg[2] < 0.5 ? 1 : 0,
      aurora: num(cs, "--field-aurora", 0.42),
      spot: num(cs, "--field-spot", 0.55),
      spotSize: num(cs, "--field-spot-size", 1),
      speed: num(cs, "--field-speed", 1),
      vignette: num(cs, "--field-vignette", 0.18),
      scrim: num(cs, "--field-scrim", 0.8),
      dustCount: num(cs, "--dust-count", 2600),
      dustSize: num(cs, "--dust-size", 1.6),
      dustOpacity: num(cs, "--dust-opacity", 0.3),
      dustPush: num(cs, "--dust-push", 1),
      dustRadius: num(cs, "--dust-radius", 140)
    };
  }
  var NUMS = ["dark", "aurora", "spot", "spotSize", "speed", "vignette", "scrim", "dustSize", "dustOpacity", "dustPush", "dustRadius", "dustCount"];
  var COLS = ["bg", "glow", "accent", "dustCol"];

  /* ---------- the scrim mask: where the text is, blurred, at 1/8 scale ---------- */
  var MS = 8, SOFT = 40, mask = document.createElement("canvas"), mctx = mask.getContext("2d");
  var texts = [], textBoxes = [], maskDirty = true, boxSig = -1;
  function opaqueAncestor(el) {
    for (var a = el; a && a !== document.body; a = a.parentElement) {
      var cs = getComputedStyle(a), m = /rgba?\(([^)]+)\)/.exec(cs.backgroundColor), al = 0;
      if (m) { var p = m[1].split(","); al = p.length > 3 ? parseFloat(p[3]) : 1; }
      if (al > 0.85 || cs.backgroundImage !== "none" || a.tagName === "EXPLODED-VIEW" || a.classList.contains("site-header")) return true;
    }
    return false;
  }
  function collectTexts() {
    var seen = new Map(), out = [];
    var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), n;
    while ((n = w.nextNode())) {
      var el = n.parentElement;
      if (!el || !n.textContent.trim()) continue;
      if (seen.has(el)) { if (seen.get(el)) out.push(n); continue; }
      if (/^(SCRIPT|STYLE|NOSCRIPT)$/.test(el.tagName) || el.closest(".sr-only,.skip")) { seen.set(el, false); continue; }
      var free = !opaqueAncestor(el); seen.set(el, free);
      if (free) out.push(n);
    }
    texts = out; measureTexts();
  }
  function measureTexts() {
    var r = document.createRange(), sy = window.scrollY, sx = window.scrollX;
    var boxes = [], sig = 0;
    for (var i = 0; i < texts.length; i++) {
      r.selectNodeContents(texts[i]);
      var b = r.getBoundingClientRect();
      if (b.width && b.height) { boxes.push([b.left + sx, b.top + sy, b.width, b.height]); sig += (b.left + sx) * 3 + (b.top + sy) * 7 + b.width * 11 + b.height * 13; }
    }
    textBoxes = boxes;
    if (sig !== boxSig) { boxSig = sig; maskDirty = true; }
  }
  function drawMask() {
    var W = Math.ceil(window.innerWidth / MS), H = Math.ceil(window.innerHeight / MS);
    if (mask.width !== W || mask.height !== H) { mask.width = W; mask.height = H; }
    mctx.setTransform(1, 0, 0, 1, 0, 0);
    mctx.clearRect(0, 0, W, H);
    // a wide, soft blur so the calmer patch behind words reads as part of the field, not as a box
    mctx.fillStyle = "#fff";
    if ("filter" in mctx) mctx.filter = "blur(" + (SOFT / MS).toFixed(1) + "px)";
    else { mctx.shadowColor = "#fff"; mctx.shadowBlur = SOFT / MS * 2; }
    var sy = window.scrollY, sx = window.scrollX, vh = window.innerHeight, pad = 22;
    for (var i = 0; i < textBoxes.length; i++) {
      var b = textBoxes[i], top = b[1] - sy;
      if (top > vh + 60 || top + b[3] < -60) continue;
      mctx.fillRect((b[0] - sx - pad) / MS, (top - pad * 0.7) / MS, (b[2] + pad * 2) / MS, (b[3] + pad * 1.4) / MS);
    }
    maskDirty = false;
    return true;
  }

  /* ---------- GL helpers ---------- */
  function program(g, vs, fs) {
    function sh(type, src) { var o = g.createShader(type); g.shaderSource(o, src); g.compileShader(o); return o; }
    var pr = g.createProgram(); g.attachShader(pr, sh(g.VERTEX_SHADER, vs)); g.attachShader(pr, sh(g.FRAGMENT_SHADER, fs)); g.linkProgram(pr);
    return g.getProgramParameter(pr, g.LINK_STATUS) ? pr : null;
  }
  function uniforms(g, pr, names) { var U = {}; names.forEach(function (k) { U[k] = g.getUniformLocation(pr, k); }); return U; }
  function maskTexture(g) {
    var t = g.createTexture(); g.bindTexture(g.TEXTURE_2D, t);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MIN_FILTER, g.LINEAR); g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MAG_FILTER, g.LINEAR);
    g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_S, g.CLAMP_TO_EDGE); g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_T, g.CLAMP_TO_EDGE);
    g.texImage2D(g.TEXTURE_2D, 0, g.RGBA, 1, 1, 0, g.RGBA, g.UNSIGNED_BYTE, new Uint8Array([0, 0, 0, 0]));
    return t;
  }
  function uploadMask(g, t) {
    g.bindTexture(g.TEXTURE_2D, t); g.pixelStorei(g.UNPACK_FLIP_Y_WEBGL, true);
    g.texImage2D(g.TEXTURE_2D, 0, g.RGBA, g.RGBA, g.UNSIGNED_BYTE, mask);
    g.pixelStorei(g.UNPACK_FLIP_Y_WEBGL, false);
  }

  /* ---------- the aurora (half resolution) ---------- */
  var NOISE = [
    "float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}",
    "float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}",
    "float fb(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}"
  ].join("\n");
  var aPr = program(gl, "attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}", [
    "precision mediump float;",
    "uniform vec2 r;uniform float t;uniform vec2 m;uniform vec3 c0;uniform vec3 c1;uniform vec3 c2;",
    "uniform float s;uniform float dk;uniform float au;uniform float sz;uniform float vg;uniform float sc;uniform sampler2D mk;",
    NOISE,
    "void main(){vec2 uv=gl_FragCoord.xy/r;vec2 q=uv;q.x*=r.x/r.y;float tt=t*.035;",
    "vec2 w=vec2(fb(q*1.3+vec2(tt,-tt*.6)),fb(q*1.3+vec2(-tt*.8,tt)+4.1));",
    "float f=fb(q*1.6+w*1.8+vec2(0.,tt*.5));",
    "vec2 mm=m;mm.x*=r.x/r.y;float d=distance(q,mm);float spot=exp(-d*d*5.5/(sz*sz))*s;",
    "float band=smoothstep(.35,.95,f)*(.55+.45*uv.y);",
    "vec3 col=mix(c0,c1,band*au);",
    // dark: the portfolio's added glow; light: a mix toward amber (an added glow on cream only clips to white)
    "col+=dk*(c2*spot*.35+c1*spot*.25);",
    "col=mix(col,mix(c1,c2,.55),(1.-dk)*spot*.6);",
    "float v=smoothstep(1.35,.25,distance(uv,vec2(.5,.62)));col*=mix(1.-vg,1.,v);",
    "float k=smoothstep(.04,.6,texture2D(mk,uv).a);col=mix(col,c0,k*sc);",
    "gl_FragColor=vec4(col,1.);}"
  ].join("\n"));
  if (!aPr) { cv.setAttribute("data-off", ""); return; }
  gl.useProgram(aPr);
  var aBuf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, aBuf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  var aLoc = gl.getAttribLocation(aPr, "p"); gl.enableVertexAttribArray(aLoc); gl.vertexAttribPointer(aLoc, 2, gl.FLOAT, false, 0, 0);
  var AU = uniforms(gl, aPr, ["r", "t", "m", "c0", "c1", "c2", "s", "dk", "au", "sz", "vg", "sc", "mk"]);
  var aTex = maskTexture(gl); gl.uniform1i(AU.mk, 0);

  /* ---------- the dust (full resolution, its own transparent canvas) ---------- */
  var dv = document.createElement("canvas"); dv.id = "dust"; dv.setAttribute("aria-hidden", "true");
  cv.parentNode.insertBefore(dv, cv.nextSibling);
  var dg = null;
  try { dg = dv.getContext("webgl", GLOPT); } catch (e) { dg = null; }
  var dPr = dg && program(dg, [
    "attribute vec2 a;attribute vec2 b;uniform vec2 vp;uniform float px;uniform float sz;varying float va;",
    "void main(){gl_Position=vec4(a.x/vp.x*2.-1.,1.-a.y/vp.y*2.,0.,1.);gl_PointSize=max(1.,sz*b.x*px);va=b.y;}"
  ].join("\n"), [
    "precision mediump float;uniform vec3 dc;uniform float op;uniform float sc;uniform vec2 rr;uniform sampler2D mk;varying float va;",
    "void main(){float d=length(gl_PointCoord-.5)*2.;float a=smoothstep(1.,.15,d);",
    "float k=smoothstep(.04,.6,texture2D(mk,gl_FragCoord.xy/rr).a);a*=va*op*(1.-k*sc*.9);",
    "gl_FragColor=vec4(dc*a,a);}"
  ].join("\n"));
  if (!dPr) { if (dv.parentNode) dv.parentNode.removeChild(dv); dg = null; }
  var DU, dTex, posBuf, metaBuf, aA, aB;
  if (dg) {
    dg.useProgram(dPr);
    DU = uniforms(dg, dPr, ["vp", "px", "sz", "dc", "op", "sc", "rr", "mk"]);
    dTex = maskTexture(dg); dg.uniform1i(DU.mk, 0);
    posBuf = dg.createBuffer(); metaBuf = dg.createBuffer();
    aA = dg.getAttribLocation(dPr, "a"); aB = dg.getAttribLocation(dPr, "b");
    dg.enable(dg.BLEND); dg.blendFunc(dg.ONE, dg.ONE_MINUS_SRC_ALPHA);
    dg.clearColor(0, 0, 0, 0);
  }

  /* particles: position, velocity (CSS px, px/s) in typed arrays */
  var N = 0, CAP = 0, PX, PY, VX, VY, POS, META;
  function seed(count) {
    count = Math.max(300, Math.min(4000, Math.round(count)));
    var W = window.innerWidth, H = window.innerHeight;
    CAP = count; N = count;
    PX = new Float32Array(count); PY = new Float32Array(count); VX = new Float32Array(count); VY = new Float32Array(count);
    POS = new Float32Array(count * 2); META = new Float32Array(count * 2);
    for (var i = 0; i < count; i++) {
      PX[i] = Math.random() * W; PY[i] = Math.random() * H;
      var big = Math.random(); META[i * 2] = 0.6 + big * big * 1.6; META[i * 2 + 1] = 0.35 + Math.random() * 0.65;
    }
    if (dg) { dg.bindBuffer(dg.ARRAY_BUFFER, metaBuf); dg.bufferData(dg.ARRAY_BUFFER, META, dg.STATIC_DRAW); dg.bindBuffer(dg.ARRAY_BUFFER, posBuf); dg.bufferData(dg.ARRAY_BUFFER, POS.byteLength, dg.DYNAMIC_DRAW); }
  }
  function wantedCount() { return look.dustCount * (window.innerWidth * window.innerHeight) / (1366 * 768); }

  /* ---------- the look: tween colours and knobs in plain numbers when the mode changes ---------- */
  var look = readLook(), from = look, to = look, tweenAt = 0, TWEEN = 700;
  function lerp(a, b, k) { return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k]; }
  function stepLook(now) {
    if (!tweenAt) return;
    var k = Math.min(1, (now - tweenAt) / TWEEN);
    if (k >= 1) { tweenAt = 0; look = to; return; }
    k = k * k * (3 - 2 * k);
    var o = {};
    COLS.forEach(function (c) { o[c] = lerp(from[c], to[c], k); });
    NUMS.forEach(function (c) { o[c] = from[c] + (to[c] - from[c]) * k; });
    look = o;
  }
  function relook() {
    from = look; to = readLook();
    if (reduce) { look = to; tweenAt = 0; } else tweenAt = performance.now();
    if (Math.abs(to.dustCount - from.dustCount) > 1) seed(wantedCount());
    collectSoon(); dirty = true; kick();
  }
  var mq = window.matchMedia("(prefers-color-scheme: dark)");
  if (mq.addEventListener) mq.addEventListener("change", relook); else if (mq.addListener) mq.addListener(relook);
  new MutationObserver(relook).observe(root, { attributes: true, attributeFilter: ["data-theme", "class"] });

  /* ---------- size ---------- */
  var aW = 0, aH = 0, dpr = 1;
  function size() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    var scale = dpr * (window.innerWidth >= 1024 ? 0.5 : 0.4);
    var w = Math.max(2, Math.round(window.innerWidth * scale)), h = Math.max(2, Math.round(window.innerHeight * scale));
    if (w !== aW || h !== aH) { aW = w; aH = h; cv.width = w; cv.height = h; gl.viewport(0, 0, w, h); }
    if (dg) {
      var dw = Math.round(window.innerWidth * dpr), dh = Math.round(window.innerHeight * dpr);
      if (dv.width !== dw || dv.height !== dh) { dv.width = dw; dv.height = dh; dg.viewport(0, 0, dw, dh); }
      if (!CAP || Math.abs(wantedCount() - CAP) / CAP > 0.35) seed(wantedCount());
    }
    maskDirty = true; measureTexts(); dirty = true; kick();
  }

  /* ---------- pointer and touch: position, and a smoothed velocity for the wake ---------- */
  var ptr = { on: false, x: 0, y: 0, vx: 0, vy: 0, t: 0 };
  var spotX = 0.22, spotY = 0.28, spotTX = spotX, spotTY = spotY; // with no pointer the glow rests low on the left, like the portfolio's dusk
  function feel(x, y, now) {
    if (ptr.on && ptr.t) {
      var dt = Math.max(8, now - ptr.t) / 1000;
      ptr.vx += ((x - ptr.x) / dt - ptr.vx) * 0.35; ptr.vy += ((y - ptr.y) / dt - ptr.vy) * 0.35;
    }
    ptr.on = true; ptr.x = x; ptr.y = y; ptr.t = now;
    spotTX = x / window.innerWidth; spotTY = 1 - y / window.innerHeight;
  }
  if (!reduce) {
    window.addEventListener("pointermove", function (e) { if (e.pointerType === "mouse" || e.pointerType === "pen") feel(e.clientX, e.clientY, performance.now()); }, { passive: true });
    document.addEventListener("pointerleave", function () { ptr.on = false; });
    window.addEventListener("blur", function () { ptr.on = false; });
    window.addEventListener("touchstart", function (e) { var t = e.touches[0]; if (t) { ptr.t = 0; feel(t.clientX, t.clientY, performance.now()); } }, { passive: true });
    window.addEventListener("touchmove", function (e) { var t = e.touches[0]; if (t) feel(t.clientX, t.clientY, performance.now()); }, { passive: true });
    window.addEventListener("touchend", function () { ptr.on = false; ptr.vx = ptr.vy = 0; }, { passive: true });
  }

  /* ---------- the dust sim: curl-noise flow, pushed and swirled by the pointer, easing back with inertia ---------- */
  var simMs = 0, simFrames = 0, flowT = 0;
  function simulate(dt) {
    var t0 = performance.now();
    var W = window.innerWidth, H = window.innerHeight, sp = look.speed;
    flowT += dt * sp;
    var ft = flowT, k1 = 1 / 260, k1y = 1 / 236, k2 = 1 / 170, A = 3000 * sp, rise = -5 * sp;
    var R = look.dustRadius, R2 = R * R, push = look.dustPush;
    var on = ptr.on, mx = ptr.x, my = ptr.y, pvx = ptr.vx, pvy = ptr.vy;
    var pspeed = Math.sqrt(pvx * pvx + pvy * pvy), energy = 0.25 + Math.min(pspeed / 900, 2.5);
    var relax = Math.min(1, dt * 1.1), damp = Math.max(0, 1 - dt * 0.6);
    var s1 = ft * 0.3, s2 = ft * 0.2, s3 = ft * 0.25;
    for (var i = 0; i < N; i++) {
      var x = PX[i], y = PY[i];
      var ax_ = x * k1 + s1, ay_ = y * k1y - s2, c_ = (x * 0.7 - y) * k2 + s3;
      var sa = Math.sin(ax_), ca = Math.cos(ax_), sb = Math.sin(ay_), cb = Math.cos(ay_), cc = Math.cos(c_) * 0.6;
      var dpx = k1 * ca * cb + cc * 0.7 * k2, dpy = -k1y * sa * sb - cc * k2;
      var fu = dpy * A, fv = -dpx * A + rise;
      var vx = VX[i], vy = VY[i];
      if (on) {
        var dx = x - mx, dy = y - my, d2 = dx * dx + dy * dy;
        if (d2 < R2 && d2 > 0.01) {
          var d = Math.sqrt(d2), f = 1 - d / R; f *= f;
          var pf = push * f * energy * 1400 * dt, nx = dx / d, ny = dy / d;
          var swirl = (pvx * dy - pvy * dx) > 0 ? 1 : -1;
          vx += nx * pf - ny * pf * 0.7 * swirl + pvx * f * push * 2.6 * dt;
          vy += ny * pf + nx * pf * 0.7 * swirl + pvy * f * push * 2.6 * dt;
        }
      }
      vx = (vx + (fu - vx) * relax) * damp + fu * (1 - damp);
      vy = (vy + (fv - vy) * relax) * damp + fv * (1 - damp);
      x += vx * dt; y += vy * dt;
      if (x < -20) x += W + 40; else if (x > W + 20) x -= W + 40;
      if (y < -20) y += H + 40; else if (y > H + 20) y -= H + 40;
      PX[i] = x; PY[i] = y; VX[i] = vx; VY[i] = vy;
    }
    // the pointer's own velocity fades when it stops, so a still cursor only parts the dust gently
    ptr.vx *= Math.max(0, 1 - dt * 4); ptr.vy *= Math.max(0, 1 - dt * 4);
    var ms = performance.now() - t0;
    simMs += (ms - simMs) * 0.05; simFrames++;
    // over budget: drop a fifth of the particles (never below 400)
    if (simFrames > 40 && simMs > 0.9 && N > 400) { N = Math.max(400, Math.round(N * 0.8)); simFrames = 0; }
  }
  function drawDust() {
    if (!dg) return;
    for (var i = 0; i < N; i++) { POS[i * 2] = PX[i]; POS[i * 2 + 1] = PY[i]; }
    dg.clear(dg.COLOR_BUFFER_BIT);
    dg.bindBuffer(dg.ARRAY_BUFFER, posBuf); dg.bufferSubData(dg.ARRAY_BUFFER, 0, POS.subarray(0, N * 2));
    dg.enableVertexAttribArray(aA); dg.vertexAttribPointer(aA, 2, dg.FLOAT, false, 0, 0);
    dg.bindBuffer(dg.ARRAY_BUFFER, metaBuf);
    dg.enableVertexAttribArray(aB); dg.vertexAttribPointer(aB, 2, dg.FLOAT, false, 0, 0);
    dg.uniform2f(DU.vp, window.innerWidth, window.innerHeight); dg.uniform1f(DU.px, dpr); dg.uniform1f(DU.sz, look.dustSize);
    dg.uniform3fv(DU.dc, look.dustCol); dg.uniform1f(DU.op, look.dustOpacity); dg.uniform1f(DU.sc, look.scrim);
    dg.uniform2f(DU.rr, dv.width, dv.height);
    dg.activeTexture(dg.TEXTURE0); dg.bindTexture(dg.TEXTURE_2D, dTex);
    dg.drawArrays(dg.POINTS, 0, N);
  }
  function drawAurora(now) {
    spotX += (spotTX - spotX) * 0.06; spotY += (spotTY - spotY) * 0.06;
    gl.uniform2f(AU.r, aW, aH);
    gl.uniform1f(AU.t, reduce ? 12 : auroraT);
    gl.uniform2f(AU.m, spotX, spotY);
    gl.uniform3fv(AU.c0, look.bg); gl.uniform3fv(AU.c1, look.glow); gl.uniform3fv(AU.c2, look.accent);
    gl.uniform1f(AU.s, look.spot * (fine ? 1 : 0.75)); gl.uniform1f(AU.dk, look.dark); gl.uniform1f(AU.au, look.aurora);
    gl.uniform1f(AU.sz, look.spotSize); gl.uniform1f(AU.vg, look.vignette); gl.uniform1f(AU.sc, look.scrim);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, aTex);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    window.__lightFieldFrames = (window.__lightFieldFrames || 0) + 1;
  }

  /* ---------- pause: hidden tab, or the full-screen 3D stage pinned over the screen ---------- */
  var stages = Array.prototype.slice.call(document.querySelectorAll('exploded-view[mode="scroll"]'));
  function covered() { for (var i = 0; i < stages.length; i++) if (stages[i].hasAttribute("data-pinned")) return true; return false; }
  var paused = false;
  function updatePause() {
    var p = document.hidden || covered();
    if (p === paused) return;
    paused = p; root.toggleAttribute("data-field-paused", p);
    if (!p) { last = 0; dirty = true; kick(); }
  }
  if (stages.length) {
    var mo = new MutationObserver(updatePause);
    stages.forEach(function (s) { mo.observe(s, { attributes: true, attributeFilter: ["data-pinned"] }); });
  }
  document.addEventListener("visibilitychange", updatePause);

  /* ---------- text boxes for the scrim: found once, re-measured on resize, fonts, content changes, and now and then ---------- */
  var collectTimer = 0;
  function collectSoon() { clearTimeout(collectTimer); collectTimer = setTimeout(function () { collectTexts(); kick(); }, 150); }
  new MutationObserver(function (list) {
    for (var i = 0; i < list.length; i++) { var t = list[i].target; if (t === cv || t === dv || (t.closest && t.closest("exploded-view"))) continue; collectSoon(); return; }
  }).observe(document.body, { childList: true, subtree: true, characterData: true });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(function () { measureTexts(); kick(); });
  setInterval(function () { if (!paused && !document.hidden) { measureTexts(); if (reduce) kick(); } }, 2000); // reveal animations and late images move text a little
  window.addEventListener("scroll", function () { maskDirty = true; if (reduce) { dirty = true; kick(); } }, { passive: true });

  /* ---------- the loop: dust every frame, aurora about 30 times a second (or at once when the scrim moves) ---------- */
  var raf = 0, last = 0, lastAurora = 0, auroraT = 0, dirty = true, STEP = 1000 / 30;
  function kick() { if (!raf && !paused) raf = requestAnimationFrame(frame); }
  function frame(now) {
    raf = 0;
    if (paused) return;
    var dt = last ? Math.min(0.05, (now - last) / 1000) : 0; last = now;
    stepLook(now);
    var scrimMoved = maskDirty;
    if (maskDirty) { drawMask(); uploadMask(gl, aTex); if (dg) uploadMask(dg, dTex); }
    if (reduce) {                                   // one still frame; redrawn only when the scrim or colours change
      if (dirty || scrimMoved) { drawAurora(now); drawDust(); dirty = false; }
      return;
    }
    auroraT += dt * look.speed;
    if (scrimMoved || dirty || now - lastAurora >= STEP - 2) { lastAurora = now; drawAurora(now); }
    if (dg) { simulate(dt); drawDust(); }
    dirty = false;
    raf = requestAnimationFrame(frame);
  }
  function lost(e) { e.preventDefault(); paused = true; cv.setAttribute("data-off", ""); }
  cv.addEventListener("webglcontextlost", lost);
  dv.addEventListener("webglcontextlost", lost);
  cv.addEventListener("webglcontextrestored", function () { location.reload(); });
  window.addEventListener("resize", size);

  window.__lightField = {
    probe: function (x, y, r) { var n = 0, s = 0, g = 0; for (var i = 0; i < N; i++) { var v = Math.hypot(VX[i], VY[i]); g += v; if (Math.hypot(PX[i] - x, PY[i] - y) < r) { n++; s += v; } } return { near: n, nearSpeed: n ? +(s / n).toFixed(1) : 0, meanSpeed: +(g / Math.max(1, N)).toFixed(1) }; },
    mask: function () { return mask.toDataURL(); }, stats: function () { return { particles: N, simMs: +simMs.toFixed(3), paused: paused, scrimBoxes: textBoxes.length }; } };
  collectTexts();
  size();
  if (!CAP) seed(wantedCount());
  updatePause();
  root.setAttribute("data-field", "on");
  kick();
})();
