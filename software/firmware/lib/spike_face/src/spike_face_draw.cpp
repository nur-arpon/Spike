// spike_face_draw.cpp -- port of face_v2/face_draw.js. Keep it line-for-line with the JS: when the JS
// changes, change the same function here, then re-run the golden-image test (test/README.md).
#include "spike_face_draw.h"
#include <math.h>
#include <string.h>
#include <stdlib.h>

namespace spike {

using namespace layout;
static const float PI = PI_F, TAU = TAU_F, DEG = DEG_F;

struct ShapeDims { float a, b, slant; };
static const ShapeDims EYE_SHAPES[5] = {
    {36, 44, 0},   // oval
    {40, 40, 0},   // round
    {41, 33, 9},   // almond
    {37, 40, 0},   // soft
    {35, 41, -8},  // droop
};
static const ShapeDims& eyeShape(uint8_t s) { return EYE_SHAPES[s < 5 ? s : 0]; }

struct MouthStyle { float hw, dip, lift, depth, lw; };
static const MouthStyle MOUTH[3] = {
    {38, 10, 8, 32, 4.4f},  // pup
    {23, 7, 5, 20, 3.7f},   // omega
    {30, 0, 6, 25, 4.6f},   // simple
};

static inline float fmaxf2(float a, float b) { return a > b ? a : b; }
static inline float fminf2(float a, float b) { return a < b ? a : b; }
static inline float fmax3(float a, float b, float c) { return fmaxf2(a, fmaxf2(b, c)); }
static inline float sgnf(float v) { return v > 0 ? 1.0f : (v < 0 ? -1.0f : 0.0f); }

// ================================================================================================
// Geometry helpers
// ================================================================================================
typedef Pts<160> PBuf;

// Cosine-spaced samples across [x0, x1] (n + 1 values).
static void cosXs(float x0, float x1, int n, float* xs) {
  for (int i = 0; i <= n; i++) xs[i] = x0 + (x1 - x0) * (1.0f - cosf(PI * (float)i / (float)n)) / 2.0f;
}

// BAND: fill between two curves over sampled xs; each open run becomes one x-monotone polygon.
static void band(Gfx& G, const float* xs, const float* tops, const float* bots, int n, Rgb color, float alpha) {
  PBuf top, bot;
  bool run = false;
  auto flush = [&]() {
    if (run && top.n >= 2) {
      PBuf pts;
      for (int k = 0; k < top.n; k++) pts.push(top.x(k), top.y(k));
      for (int k = bot.n - 1; k >= 0; k--) pts.push(bot.x(k), bot.y(k));
      G.mpoly(pts.data(), pts.n, color, alpha);
    }
    run = false;
  };
  for (int i = 0; i < n; i++) {
    bool open = bots[i] - tops[i] > 0.01f;
    if (open) {
      if (!run) {
        run = true;
        top.clear();
        bot.clear();
        if (i > 0) {  // crossing into open: pointed start
          float d0 = bots[i - 1] - tops[i - 1], d1 = bots[i] - tops[i];
          float f = d0 / (d0 - d1);
          float xc = xs[i - 1] + (xs[i] - xs[i - 1]) * f, yc = tops[i - 1] + (tops[i] - tops[i - 1]) * f;
          top.push(xc, yc);
          bot.push(xc, yc);
        }
      }
      top.push(xs[i], tops[i]);
      bot.push(xs[i], bots[i]);
    } else if (run) {
      float e0 = bots[i - 1] - tops[i - 1], e1 = bots[i] - tops[i];
      float g = e0 / (e0 - e1);
      float xe = xs[i - 1] + (xs[i] - xs[i - 1]) * g, ye = tops[i - 1] + (tops[i] - tops[i - 1]) * g;
      top.push(xe, ye);
      bot.push(xe, ye);
      flush();
    }
  }
  flush();
}

// An ellipse drawn only inside the visible region vTop(x) .. vBot(x).
template <class FT, class FB>
static void clippedEllipse(Gfx& G, float cx, float cy, float rx, float ry, FT vTop, FB vBot, Rgb color,
                           float alpha, int n = 18) {
  if (!(rx > 0.2f) || !(ry > 0.2f)) return;
  float xs[130], tops[130], bots[130];
  if (n > 128) n = 128;
  cosXs(cx - rx, cx + rx, n, xs);
  bool inside = true;
  for (int i = 0; i <= n; i++) {
    float q = (xs[i] - cx) / rx, h = ry * sqrtf(fmaxf2(0.0f, 1.0f - q * q));
    float t0 = cy - h, b0 = cy + h, vt = vTop(xs[i]), vb = vBot(xs[i]);
    if (vt > t0 + 0.01f || vb < b0 - 0.01f) inside = false;
    tops[i] = fmaxf2(t0, vt);
    bots[i] = fminf2(b0, vb);
  }
  if (inside) G.ellipse(cx, cy, rx, ry, 0, color, alpha);
  else band(G, xs, tops, bots, n + 1, color, alpha);
}

// Convex hull (monotone chain) of a point list.
template <int N, int M>
static void hull(const Pts<N>& in, Pts<M>& out) {
  int n = in.n;
  static float P[2 * 512];
  if (n > 512) n = 512;
  for (int i = 0; i < n; i++) { P[2 * i] = in.x(i); P[2 * i + 1] = in.y(i); }
  // insertion sort by x then y
  for (int i = 1; i < n; i++) {
    float kx = P[2 * i], ky = P[2 * i + 1];
    int j = i - 1;
    while (j >= 0 && (P[2 * j] > kx || (P[2 * j] == kx && P[2 * j + 1] > ky))) {
      P[2 * j + 2] = P[2 * j]; P[2 * j + 3] = P[2 * j + 1];
      j--;
    }
    P[2 * j + 2] = kx; P[2 * j + 3] = ky;
  }
  auto cross = [](const float* o, const float* a, const float* b) {
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  };
  static int H[1030];
  int k = 0;
  for (int i = 0; i < n; i++) {
    while (k >= 2 && cross(&P[2 * H[k - 2]], &P[2 * H[k - 1]], &P[2 * i]) <= 0) k--;
    H[k++] = i;
  }
  for (int i = n - 2, t = k + 1; i >= 0; i--) {
    while (k >= t && cross(&P[2 * H[k - 2]], &P[2 * H[k - 1]], &P[2 * i]) <= 0) k--;
    H[k++] = i;
  }
  out.clear();
  for (int i = 0; i < k - 1; i++) out.push(P[2 * H[i]], P[2 * H[i] + 1]);
}

// Hull of several circles {x, y, r} = a smooth rounded convex shape.
struct Circ { float x, y, r; };
template <int M>
static void circleHull(const Circ* c, int nc, int seg, Pts<M>& out) {
  Pts<512> pts;
  for (int i = 0; i < nc; i++)
    for (int j = 0; j < seg; j++) {
      float a = (float)j / (float)seg * TAU;
      pts.push(c[i].x + cosf(a) * c[i].r, c[i].y + sinf(a) * c[i].r);
    }
  hull(pts, out);
}

template <int N>
static void xform(const Pts<N>& in, float dx, float dy, float rot, float sx, float sy, Pts<N>& out) {
  float c = cosf(rot), s = sinf(rot);
  out.clear();
  for (int i = 0; i < in.n; i++) {
    float x = in.x(i) * sx, y = in.y(i) * sy;
    out.push(dx + x * c - y * s, dy + x * s + y * c);
  }
}

// Heart from two circles and one convex polygon.
static void heart(Gfx& G, float x, float y, float s, Rgb color, float alpha) {
  G.circle(x - 0.5f * s, y - 0.25f * s, 0.56f * s, color, alpha);
  G.circle(x + 0.5f * s, y - 0.25f * s, 0.56f * s, color, alpha);
  float p[10] = {x - 1.03f * s, y - 0.08f * s, x + 1.03f * s, y - 0.08f * s, x + 0.35f * s, y + 0.72f * s,
                 x, y + 0.98f * s, x - 0.35f * s, y + 0.72f * s};
  G.poly(p, 5, color, alpha);
}

// 4- or 5-point star: a convex centre + one triangle per point.
static void star(Gfx& G, float x, float y, float ro, float ri, int points, float rot, Rgb color, float alpha) {
  float centre[20];
  for (int i = 0; i < points; i++) {
    float a0 = rot + ((float)i + 0.5f) / (float)points * TAU;
    centre[2 * i] = x + cosf(a0) * ri;
    centre[2 * i + 1] = y + sinf(a0) * ri;
  }
  G.poly(centre, points, color, alpha);
  for (int j = 0; j < points; j++) {
    float a = rot + (float)j / points * TAU, al = rot + ((float)j - 0.5f) / points * TAU,
          ar = rot + ((float)j + 0.5f) / points * TAU;
    G.tri(x + cosf(a) * ro, y + sinf(a) * ro, x + cosf(al) * ri, y + sinf(al) * ri, x + cosf(ar) * ri,
          y + sinf(ar) * ri, color, alpha);
  }
}

// Contrast guard: the skin a feature sits on is known from the recipe.
static Rgb eyeSkin(const Recipe& r, int side) {
  int ps = r.patternSide == SIDE_RIGHT ? 1 : -1;
  if ((r.pattern == PAT_PATCH || r.pattern == PAT_CALICO) && side == ps) return r.fur2;
  return r.fur;
}
static Rgb mouthSkin(const Recipe& r) {
  if (r.muzzle != MUZ_NONE) return r.muzzleColor;
  if (r.pattern == PAT_BLAZE || r.pattern == PAT_TUX) return r.fur2;
  return r.fur;
}
static bool lowContrast(Rgb a, Rgb b) { return fabsf(luminance(a) - luminance(b)) < 0.26f; }
static Rgb contrastOn(Rgb col, Rgb bg) {
  if (!lowContrast(col, bg)) return col;
  return luminance(bg) < 0.5f ? mix(col, 0xFFFFFF, 0.72f) : mix(col, 0x000000, 0.62f);
}

// Deterministic pseudo-random (hash). Double precision: the *43758 amplifies float error.
static float hashf(float n) {
  double x = sin((double)n * 127.1 + 311.7) * 43758.5453;
  return (float)(x - floor(x));
}

// ================================================================================================
// EYES
// ================================================================================================
float EyeOutline::top(float x) const {
  if (shape == SHAPE_ALMOND) {
    float q = x / a, u = fmaxf2(0.0f, 1.0f - q * q);
    return -b * powf(u, 0.7f);
  }
  return -bot(x);
}

float EyeOutline::bot(float x) const {
  if (shape == SHAPE_ALMOND) {
    float q = x / a, u = fmaxf2(0.0f, 1.0f - q * q);
    return b * 0.86f * powf(u, 0.92f);
  }
  if (shape == SHAPE_SOFT) {
    float q = fminf2(1.0f, fabsf(x / a));
    return b * powf(fmaxf2(0.0f, 1.0f - powf(q, 2.8f)), 1.0f / 2.8f);
  }
  float q = x / a;
  return b * sqrtf(fmaxf2(0.0f, 1.0f - q * q));
}

float EyeGeom::arc(float x) const {
  float q = fminf2(1.0f, fabsf(x) / arcW);
  return gy + yMeet - curv * b * 0.42f * (1.0f - powf(q, 1.5f));
}
float EyeGeom::arcH(float x) const {
  float q = fminf2(1.0f, fabsf(x) / arcW);
  return gy + b * 0.04f - b * 0.42f * (1.0f - powf(q, 1.5f));
}
float EyeGeom::topEdge(float x) const {
  float q = x / fmaxf2(a, 1.0f), xin = -(float)side * q;
  float base = gy + b * (-1.05f + 1.9f * lidT) + lidTilt * 0.55f * b * xin * (1.0f - hap) +
               lidSag * 0.32f * b * (1.0f - q * q);
  base = lerpf(base, arcH(x) - 0.4f, hTop);
  return lerpf(base, arc(x) - 0.4f, Cb);
}
float EyeGeom::botEdge(float x) const {
  float q = x / fmaxf2(a, 1.0f);
  float base = gy + b * (1.05f - 1.9f * lidB) - lidBulge * 0.34f * b * (1.0f - q * q);
  base = lerpf(base, arcH(x) + 0.4f, hBot);
  return lerpf(base, arc(x) + 0.4f, Cb);
}

EyeIconInfo eyeIcon(const FaceState& p, const Recipe& r) {
  if (r.eyeStyle == EYE_GLOW && p.batt > p.iconAmt) return {Icon::Battery, p.batt};
  return {p.icon, p.icon != Icon::None ? p.iconAmt : 0.0f};
}

EyeGeom eyeGeom(const FaceState& p, const Recipe& r, int side) {
  EyeGeom g;
  const ShapeDims& shp = eyeShape(r.eyeShape);
  float bl = side < 0 ? p.blinkL : p.blinkR;
  float sc = r.eyeSize * p.eyeScale * (side < 0 ? p.eyeScaleL : p.eyeScaleR);
  if (r.eyeStyle == EYE_GLOW) sc *= 1.08f;
  float body = 1.0f - clampf(eyeIcon(p, r).amt, 0.0f, 1.0f);
  g.side = side;
  g.a0 = shp.a * sc * p.eyeSX;
  g.b0 = shp.b * sc * p.eyeSY;
  g.a = g.a0 * (1.0f + 0.12f * bl) * body;
  g.b = g.b0 * (1.0f - 0.15f * bl) * body;
  float winkSide = p.wink * (float)side > 0 ? fabsf(p.wink) : 0.0f;
  g.ex = CX + (float)side * (eyeDX * r.eyeSpacing + p.eyeSpread);
  g.ey = eyeY + p.eyeDY - fmaxf2(p.happy, winkSide) * 3.0f;
  bool moves = (r.eyeStyle == EYE_GLOSS || r.eyeStyle == EYE_GLOW);
  float reach0 = r.eyeStyle == EYE_GLOW ? 9.0f : 5.0f, reach1 = r.eyeStyle == EYE_GLOW ? 6.0f : 4.0f;
  float crossX = p.cross * (float)(-side), crossY = p.cross;
  g.gx = moves ? (p.lookX * reach0 + crossX * 14.0f) : 0.0f;
  g.gy = moves ? (p.lookY * reach1 + crossY * 7.0f) : 0.0f;
  g.ix = moves ? 0.0f : (p.lookX * 0.34f * g.a + crossX * 0.45f * g.a);
  g.iy = moves ? 0.0f : (p.lookY * 0.24f * g.b + crossY * 0.28f * g.b);
  float blinkC = clampf(bl, 0.0f, 1.0f);
  float hap = fmaxf2(p.happy, winkSide);
  g.Cb = clampf(fmaxf2(blinkC, p.shut), 0.0f, 1.0f);
  g.C = clampf(fmaxf2(g.Cb, hap), 0.0f, 1.0f);
  float hw = hap / fmaxf2(1e-3f, fmax3(hap, p.shut, blinkC));
  hw = clampf(hw, 0.0f, 1.0f) * smoothstepf(0.0f, 0.6f, hap);
  g.curv = lerpf(-0.38f, 1.0f, hw);
  g.yMeet = g.b * lerpf(0.2f, 0.04f, hw);
  g.lidT = side < 0 ? p.lidTL : p.lidTR;
  g.lidB = side < 0 ? p.lidBL : p.lidBR;
  g.arcW = 0.96f * fmaxf2(g.a, 1.0f);
  g.hap = hap;
  g.hTop = hap * hap * hap;
  g.hBot = powf(hap, 0.8f);
  g.lidTilt = p.lidTilt;
  g.lidSag = p.lidSag;
  g.lidBulge = p.lidBulge;
  g.o.shape = r.eyeShape;
  g.o.a = g.a;
  g.o.b = g.b;
  g.shape = r.eyeShape;
  g.slant = -(float)side * shp.slant * DEG;
  return g;
}

static void eyeBand(Gfx& G, const EyeGeom& g, float grow, Rgb color, float alpha, int n = 28) {
  float xs[64], tops[64], bots[64];
  cosXs(g.gx - g.a - grow, g.gx + g.a + grow, n, xs);
  EyeOutline o{g.shape, g.a + grow, g.b + grow};
  for (int i = 0; i <= n; i++) {
    float x = xs[i];
    float ot = grow > 0 ? g.gy + o.top(x - g.gx) : g.oTop(x);
    float ob = grow > 0 ? g.gy + o.bot(x - g.gx) : g.oBot(x);
    tops[i] = fmaxf2(ot, g.topEdge(x) - grow);
    bots[i] = fminf2(ob, g.botEdge(x) + grow);
  }
  band(G, xs, tops, bots, n + 1, color, alpha);
}

// A thick line along the visible TOP edge of the eye, broken wherever the eye is closed.
static void topLiner(Gfx& G, const EyeGeom& g, float x0, float x1, float w, Rgb color, float alpha) {
  const int n = 14;
  PBuf run;
  for (int i = 0; i <= n; i++) {
    float x = x0 + (x1 - x0) * (float)i / (float)n, yt = g.visTop(x), yb = g.visBot(x);
    if (yb - yt > 0.8f) run.push(x, yt);
    else {
      if (run.n >= 2) G.polyline(run.data(), run.n, w, color, alpha);
      run.clear();
    }
  }
  if (run.n >= 2) G.polyline(run.data(), run.n, w, color, alpha);
}

static void drawLashes(Gfx& G, const EyeGeom& g, const Recipe& r, int side, Rgb color) {
  bool closedish = g.C > 0.85f;
  int n = r.lashes == LASH_FULL ? 3 : 2;
  float w = r.lashes == LASH_FULL ? 3.4f : 3.1f;
  static const float fullFx[3] = {0.52f, 0.74f, 0.93f}, flickFx[2] = {0.72f, 0.92f};
  float s = (float)side;
  for (int k = 0; k < n; k++) {
    float fx = r.lashes == LASH_FULL ? fullFx[k] : flickFx[k];
    float bx = s * g.a * fx, by;
    if (closedish) { bx = s * g.a * 0.9f; by = g.arc(bx); }
    else {
      by = g.visTop(bx);
      if (g.visBot(bx) - by < 1.0f) by = g.arc(bx);
    }
    float ang = -PI / 2 + s * (0.62f + 0.3f * (float)k + (closedish ? 0.5f : 0.0f));
    if (closedish && g.curv < 0) ang += s * 0.35f;
    float L = g.b0 * (0.24f + 0.03f * (float)k);
    float x1 = bx + cosf(ang) * L * 0.6f, y1 = by + sinf(ang) * L * 0.6f;
    float a2 = ang + s * 0.45f;
    float pts[6] = {bx, by, x1, y1, x1 + cosf(a2) * L * 0.5f, y1 + sinf(a2) * L * 0.5f};
    G.polyline(pts, 3, w, color, 1);
  }
  if (r.lashes == LASH_FULL && !closedish) {
    float ox = s * g.a * 0.92f, oy = g.visTop(ox);
    if (g.visBot(ox) - oy > 1.0f) {
      G.tri(ox, oy - 1.5f, ox + s * g.a * 0.34f, oy - g.b0 * 0.2f, ox + s * g.a * 0.06f, oy + 3.0f, color, 1);
      float lx = s * g.a * 0.7f, ly = g.visBot(lx);
      G.line(lx, ly + 1.0f, lx + s * 6.0f, ly + 7.0f, 2.6f, color, 0.9f);
    }
  }
}

static void drawEyeIcon(Gfx& G, const EyeIconInfo& icon, const Recipe& r, int side, float t, Rgb dark, Rgb skin) {
  const ShapeDims& shp = eyeShape(r.eyeShape);
  float s = fmaxf2(shp.a, shp.b) * r.eyeSize * 0.62f * clampf(icon.amt, 0.0f, 1.3f);
  switch (icon.name) {
    case Icon::Heart: {
      float beat = 1.0f + 0.09f * fmaxf2(0.0f, sinf(t * 8.5f));
      heart(G, 0, -0.08f * s, s * 0.98f * beat, 0xFF4D79, 1);
      G.ellipse(-0.42f * s, -0.52f * s, 0.2f * s, 0.14f * s, -0.5f, 0xFFFFFF, 0.85f);
      break;
    }
    case Icon::Star:
      star(G, 0, 0, s * 1.05f, s * 0.46f, 5, -PI / 2 + 0.12f * sinf(t * 3.0f), 0xFFD23F, 1);
      G.circle(-0.25f * s, -0.3f * s, 0.13f * s, 0xFFFFFF, 0.9f);
      break;
    case Icon::Spiral: {
      PBuf pts;
      float turns = 2.6f, rot = t * 7.0f * (float)(-side);
      for (int i = 0; i <= 44; i++) {
        float f = (float)i / 44.0f, a = rot + f * turns * TAU;
        pts.push(cosf(a) * f * s, sinf(a) * f * s);
      }
      G.polyline(pts.data(), pts.n, fmaxf2(3.5f, s * 0.14f), dark, 1);
      break;
    }
    case Icon::X: {
      float q = s * 0.62f, lw = fmaxf2(5.0f, s * 0.22f);
      G.line(-q, -q, q, q, lw, dark, 1);
      G.line(q, -q, -q, q, lw, dark, 1);
      break;
    }
    case Icon::Battery: {
      float bw = s * 2.1f, bh = s * 1.2f;
      G.rrect(-bw / 2, -bh / 2, bw, bh, s * 0.2f, dark, 1);
      G.rrect(-bw / 2 + s * 0.13f, -bh / 2 + s * 0.13f, bw - s * 0.26f, bh - s * 0.26f, s * 0.1f, skin, 1);
      G.rrect(bw / 2 - 1, -s * 0.2f, s * 0.16f, s * 0.4f, s * 0.06f, dark, 1);
      float blinkOn = 0.55f + 0.45f * sinf(t * 6.0f);
      G.rrect(-bw / 2 + s * 0.22f, -bh / 2 + s * 0.22f, (bw - s * 0.44f) * 0.22f, bh - s * 0.44f, s * 0.06f, 0xFF4B4B,
              blinkOn);
      break;
    }
    case Icon::Question: {
      float lw2 = fmaxf2(4.0f, s * 0.17f);
      G.arc(0, -0.28f * s, 0.34f * s, PI * 1.05f, PI * 2.3f, lw2, dark, 1);
      G.line(0.12f * s, 0.02f * s, 0, 0.28f * s, lw2, dark, 1);
      G.circle(0, 0.62f * s, lw2 * 0.62f, dark, 1);
      break;
    }
    default:
      break;
  }
}

static EyeGeom drawEye(Gfx& G, const FaceState& p, const Recipe& r, int side, float t) {
  EyeGeom g = eyeGeom(p, r, side);
  uint8_t style = r.eyeStyle;
  Rgb dark = r.eyeColor, white = 0xFFFFFF;
  float shineMul = p.shine * (0.85f + 0.15f * p.pupil) * (1.0f + 0.3f * p.tear);
  bool closed = g.C > 0.985f;
  float s = (float)side;
  auto vT = [&g](float x) { return g.visTop(x); };
  auto vB = [&g](float x) { return g.visBot(x); };

  G.save();
  G.translate(g.ex, g.ey);
  if (g.slant != 0.0f) G.rotate(g.slant);
  G.tag(Tag::Eye);

  if (!closed && g.a > 0.5f && g.b > 0.5f) {
    if (style == EYE_GLOW) {
      eyeBand(G, g, 6, dark, 0.13f);
      eyeBand(G, g, 0, dark, 1);
    } else if (style == EYE_GLOSS) {
      Rgb skin = eyeSkin(r, side);
      if (lowContrast(dark, skin)) eyeBand(G, g, 3, mix(skin, luminance(skin) < 0.5f ? 0xFFFFFF : 0x000000, 0.55f), 1);
      eyeBand(G, g, 0, dark, 1);
      clippedEllipse(G, g.gx * 0.4f, g.gy + 0.47f * g.b, 0.64f * g.a, 0.4f * g.b, vT, vB, mix(dark, r.irisColor, 0.6f), 0.95f);
      clippedEllipse(G, g.gx * 0.4f, g.gy + 0.56f * g.b, 0.42f * g.a, 0.24f * g.b, vT, vB, mix(dark, r.irisColor, 0.9f), 0.6f);
    } else {
      Rgb skin2 = eyeSkin(r, side);
      if (lowContrast(dark, skin2)) eyeBand(G, g, style == EYE_CAT ? 5.4f : 5.0f, mix(skin2, 0xFFFFFF, 0.55f), 1);
      eyeBand(G, g, style == EYE_CAT ? 3.2f : 2.8f, dark, 1);
      if (style == EYE_IRIS) {
        eyeBand(G, g, 0, 0xFFFDF9, 1);
        float rix = 0.7f * g.a, riy = 0.8f * g.b, icx = g.ix, icy = g.iy + 0.05f * g.b;
        clippedEllipse(G, icx, icy, rix, riy, vT, vB, shade(r.irisColor, -0.4f), 1);
        clippedEllipse(G, icx, icy, rix * 0.86f, riy * 0.88f, vT, vB, r.irisColor, 1);
        clippedEllipse(G, icx, icy + riy * 0.4f, rix * 0.64f, riy * 0.4f, vT, vB, mix(r.irisColor, 0xFFFFFF, 0.38f), 0.95f);
        clippedEllipse(G, icx, icy - riy * 0.58f, rix * 0.84f, riy * 0.34f, vT, vB, shade(r.irisColor, -0.3f), 0.55f);
        clippedEllipse(G, icx, icy + riy * 0.04f, rix * 0.4f * p.pupil, riy * 0.42f * p.pupil, vT, vB, dark, 1);
      } else {  // cat
        eyeBand(G, g, 0, r.irisColor, 1);
        clippedEllipse(G, 0, -0.66f * g.b, 0.98f * g.a, 0.46f * g.b, vT, vB, shade(r.irisColor, -0.28f), 0.6f);
        clippedEllipse(G, g.ix * 0.3f, 0.5f * g.b, 0.72f * g.a, 0.42f * g.b, vT, vB, mix(r.irisColor, 0xFFFFFF, 0.32f), 0.85f);
        float dil = clampf((p.pupil - 0.3f) / 1.1f, 0.0f, 1.0f);
        clippedEllipse(G, g.ix, g.iy, g.a * lerpf(0.1f, 0.5f, dil), g.b * lerpf(0.86f, 0.62f, dil), vT, vB, dark, 1);
      }
    }

    // --- teary waterline (wobbles) ---
    if (p.tear > 0.02f) {
      float tear = p.tear;
      auto wl = [&g, tear, t](float x) {
        return g.gy + g.b * lerpf(0.74f, 0.34f, tear) + 1.6f * sinf(x * 0.22f + t * 5.5f) +
               1.1f * sinf(x * 0.11f - t * 3.7f);
      };
      float xs[32], tops[32], bots[32];
      cosXs(g.gx - g.a, g.gx + g.a, 26, xs);
      for (int i = 0; i <= 26; i++) {
        tops[i] = fmaxf2(vT(xs[i]), wl(xs[i]));
        bots[i] = vB(xs[i]);
      }
      Rgb wc = style == EYE_GLOW ? 0xCFEFFF : (style == EYE_GLOSS ? mix(dark, 0x5FB4F0, 0.55f) : 0xA8DCFF);
      float wa = (style == EYE_GLOW ? 0.6f : (style == EYE_GLOSS ? 0.85f : 0.45f)) * tear;
      band(G, xs, tops, bots, 27, wc, wa);
      PBuf men;
      for (int j = 0; j <= 12; j++) {
        float mx = g.gx - g.a * 0.9f + g.a * 1.8f * (float)j / 12.0f, my = wl(mx);
        if (my > vT(mx) + 1 && my < vB(mx) - 1) men.push(mx, my);
        else if (men.n >= 2) { G.polyline(men.data(), men.n, 2, 0xE8F8FF, 0.9f * tear); men.clear(); }
        else men.clear();
      }
      if (men.n >= 2) G.polyline(men.data(), men.n, 2, 0xE8F8FF, 0.9f * tear);
      for (int k = 0; k < 3; k++) {
        float dx = g.gx + g.a * (-0.5f + 0.48f * (float)k), dy = wl(dx) + 3.0f;
        float rr = (1.8f + 1.2f * sinf(t * 7.0f + (float)k * 2.0f)) * tear + 0.3f;
        clippedEllipse(G, dx, dy, rr, rr, vT, vB, 0xFFFFFF, 0.9f * tear, 8);
      }
    }

    // --- highlights: reflections of one light, so they barely move ---
    if (style != EYE_GLOW) {
      float hx, hy, sz;
      if (style == EYE_GLOSS) { hx = g.gx * 0.45f; hy = g.gy * 0.45f; sz = g.a; }
      else { hx = g.ix * 0.5f; hy = g.iy * 0.5f; sz = (style == EYE_IRIS ? 0.7f : 0.8f) * g.a; }
      float hr1 = 0.3f * sz * shineMul, hr2 = 0.13f * sz * shineMul;
      clippedEllipse(G, hx + s * 0.34f * sz, hy - 0.42f * g.b, hr1, hr1 * 1.08f, vT, vB, white, 0.96f, 16);
      clippedEllipse(G, hx - s * 0.3f * sz, hy + 0.36f * g.b, hr2, hr2, vT, vB, white, 0.9f, 10);
      if (p.sparkle > 0.02f) {
        float spx = hx - s * 0.22f * sz, spy = hy - 0.55f * g.b;
        if (vB(spx) - vT(spx) > 6 && spy > vT(spx) && spy < vB(spx)) {
          star(G, spx, spy, 0.26f * sz * p.sparkle * (0.85f + 0.15f * sinf(t * 6.0f)), 0.07f * sz, 4, t * 0.8f, white,
               p.sparkle);
        }
        clippedEllipse(G, hx + s * 0.55f * sz, hy + 0.05f * g.b, 0.07f * sz * p.sparkle + 0.2f,
                       0.07f * sz * p.sparkle + 0.2f, vT, vB, white, p.sparkle, 8);
      }
    }

    // --- eyeliner along the lid edge (iris / cat) ---
    if (style == EYE_IRIS || style == EYE_CAT)
      topLiner(G, g, g.gx - g.a * 0.98f, g.gx + g.a * 0.98f, style == EYE_CAT ? 4.2f : 4.6f, dark, 1);
  }

  // --- closed eye arc: relaxed "u" when asleep, "^" when happy ---
  if (g.C > 0.8f && g.a > 0.5f) {
    float ca = smoothstepf(0.8f, 0.975f, g.C);
    float lw = style == EYE_GLOW ? fmaxf2(7.0f, g.a0 * 0.22f) : fmaxf2(6.0f, g.a0 * 0.19f);
    PBuf c;
    float x0 = -g.a * 0.94f, x1 = g.a * 0.94f;
    for (int i = 0; i <= 12; i++) { float x = x0 + (x1 - x0) * (float)i / 12.0f; c.push(x, g.arc(x)); }
    G.polyline(c.data(), c.n, lw, contrastOn(dark, eyeSkin(r, side)), ca);
  }

  // --- lashes: ride on the lid edge so they drop when blinking ---
  if (r.lashes != LASH_NONE && g.a > 0.5f)
    drawLashes(G, g, r, side, luminance(r.fur) < 0.3f ? mix(r.fur, 0xFFFFFF, 0.82f) : dark);

  // --- eye icons ---
  EyeIconInfo ic = eyeIcon(p, r);
  if (ic.amt > 0.01f && ic.name != Icon::None) {
    G.tag(Tag::EyeIcon);
    drawEyeIcon(G, ic, r, side, t, contrastOn(dark, eyeSkin(r, side)), eyeSkin(r, side));
    G.tag(Tag::Eye);
  }

  G.restore();
  return g;
}

static void drawBrows(Gfx& G, const FaceState& p, const Recipe& r, const EyeGeom& g, int side) {
  if (r.brows == BROW_NONE) return;
  G.tag(Tag::Brow);
  float bx = g.ex + (float)(-side) * 0.08f * g.a0;
  float by = g.ey - g.b0 - 13.0f - p.browY * 9.0f + p.happy * 2.0f;
  float rot = -(float)side * p.browTilt * 0.42f;
  Rgb c = contrastOn(r.browColor, eyeSkin(r, side));
  G.save();
  G.translate(bx, by);
  G.rotate(rot);
  if (r.brows == BROW_DOTS) G.ellipse(0, 0, 0.24f * g.a0, 0.16f * g.a0, 0, c, 1);
  else if (r.brows == BROW_ARCS) G.arc(0, 26, 29, -PI / 2 - 0.44f, -PI / 2 + 0.44f, 5, c, 1);
  else G.rrect(-0.45f * g.a0, -4.5f, 0.9f * g.a0, 9, 4.5f, c, 1);
  G.restore();
}

// ================================================================================================
// NOSE -- every style has one, and it always animates (sniff, twitch, scrunch, boop squash).
// ================================================================================================
typedef Pts<64> Shape;
struct Shapes {
  Shape nosePup, noseCat;
  Shape floppyOut, floppyIn, lopOut, lopIn, pointOut, pointIn, foldOut, foldFlap, bunnyOut, bunnyIn;
  PBuf headPoly, headOutline;
};
static void headPoly(float grow, PBuf& out);
static const Shapes& shapes() {
  static Shapes S;
  static bool ready = false;
  if (!ready) {
    { Circ c[] = {{-11, -5, 8.5f}, {11, -5, 8.5f}, {0, 7.5f, 7}}; circleHull(c, 3, 16, S.nosePup); }
    { Circ c[] = {{-6.5f, -3, 4.2f}, {6.5f, -3, 4.2f}, {0, 4.5f, 3.4f}}; circleHull(c, 3, 12, S.noseCat); }
    { Circ c[] = {{0, 4, 24}, {-10, 112, 52}}; circleHull(c, 2, 18, S.floppyOut); }
    { Circ c[] = {{-4, 60, 10}, {-12, 116, 30}}; circleHull(c, 2, 14, S.floppyIn); }
    { Circ c[] = {{0, 10, 21}, {-4, 140, 29}}; circleHull(c, 2, 14, S.lopOut); }
    { Circ c[] = {{-1, 34, 9}, {-4, 132, 18}}; circleHull(c, 2, 12, S.lopIn); }
    { Circ c[] = {{-54, 10, 10}, {54, 10, 10}, {0, -104, 12}}; circleHull(c, 3, 12, S.pointOut); }
    { Circ c[] = {{-27, -6, 4}, {27, -6, 4}, {0, -72, 5}}; circleHull(c, 3, 10, S.pointIn); }
    { Circ c[] = {{-42, 8, 9}, {42, 8, 9}, {0, -46, 11}}; circleHull(c, 3, 12, S.foldOut); }
    { Circ c[] = {{-28, -18, 6}, {28, -18, 6}, {0, 20, 7}}; circleHull(c, 3, 10, S.foldFlap); }
    { Circ c[] = {{0, 0, 22}, {0, -120, 26}}; circleHull(c, 2, 14, S.bunnyOut); }
    { Circ c[] = {{0, -10, 10}, {0, -112, 14}}; circleHull(c, 2, 12, S.bunnyIn); }
    headPoly(0, S.headPoly);
    headPoly(4, S.headOutline);
    ready = true;
  }
  return S;
}

static const float NOSE_SIZE[5][2] = {{39, 28}, {28, 21}, {21, 15}, {25, 22}, {42, 24}};  // pup button cat heart bean

NosePos nosePos(const FaceState& p, const Recipe& r) {
  (void)r;
  NosePos n;
  n.x = CX + p.noseDX + p.lookX * 3.0f;
  n.y = noseY + p.noseDY - p.scrunch * 3.0f;
  n.sx = p.noseSX * (1.0f + 0.1f * p.scrunch);
  n.sy = p.noseSY * (1.0f - 0.2f * p.scrunch);
  return n;
}

static NoseInfo drawNose(Gfx& G, const FaceState& p, const Recipe& r) {
  G.tag(Tag::Nose);
  NosePos n = nosePos(p, r);
  uint8_t style = r.nose < 5 ? r.nose : NOSE_PUP;
  Rgb col = contrastOn(r.noseColor, mouthSkin(r));
  float w = NOSE_SIZE[style][0] * n.sx, h = NOSE_SIZE[style][1] * n.sy;
  bool pink = luminance(col) > 0.45f;
  Rgb shineCol = 0xFFFFFF;
  float shineA = pink ? 0.55f : 0.5f;

  if (p.scrunch > 0.03f) {
    G.tag(Tag::NoseWrinkle);
    for (int k = 0; k < 3; k++) {
      float wy = n.y - h * 0.5f - 6.0f - (float)k * 5.5f, ww = 8.0f - (float)k * 1.5f;
      float pts[6] = {n.x - ww, wy + 2.2f, n.x, wy, n.x + ww, wy + 2.2f};
      G.polyline(pts, 3, 2.4f, r.lineColor, p.scrunch * 0.85f);
    }
    G.tag(Tag::Nose);
  }

  if (style == NOSE_PUP || style == NOSE_CAT) {
    Shape s;
    xform(style == NOSE_PUP ? shapes().nosePup : shapes().noseCat, n.x, n.y, 0, n.sx, n.sy, s);
    G.poly(s.data(), s.n, col, 1);
  } else if (style == NOSE_HEART) {
    heart(G, n.x, n.y - 1.5f * n.sy, 11.5f * n.sx, col, 1);
  } else {
    G.ellipse(n.x, n.y, w / 2, h / 2, 0, col, 1);
  }
  G.ellipse(n.x - w * 0.18f, n.y - h * 0.24f, w * 0.2f, h * 0.13f, -0.15f, shineCol, shineA);
  G.circle(n.x + w * 0.16f, n.y - h * 0.27f, fmaxf2(1.0f, w * 0.045f), shineCol, shineA * 0.9f);
  NoseInfo ni{n.x, n.y, w, h, n.y + h * (style == NOSE_HEART ? 0.42f : 0.5f)};
  return ni;
}

// ================================================================================================
// MOUTH -- lip line + open interior + tongue, all bands (no clip).
// ================================================================================================
float MouthGeom::lip(float x) const {
  float dx = x - mx, q = fminf2(1.0f, fabsf(dx) / fmaxf2(hw, 1.0f)), sg = dx >= 0 ? 1.0f : -1.0f;
  float L = clampf(lift + skew * 5.0f * sg, -12.0f, 8.0f);
  float y;
  if (style == MOUTH_SIMPLE) y = my + 2.0f + smile * 7.0f * (1.0f - q * q) - (L - lift * 1.0f) * q - lift * 0.35f * q * q;
  else y = my + dip * sinf(PI * q) - L * powf(q, 1.6f);
  if (wob > 0.01f) y += wob * 2.2f * sinf(t * 17.0f + dx * 0.16f) * (1.0f - q * 0.5f);
  return fmaxf2(y, my - 8.2f);  // hard rule: nothing of the mouth above 70 %
}

float MouthGeom::bot(float x) const {
  float q = (x - mx) / fmaxf2(hwo, 1.0f), f = powf(fmaxf2(0.0f, 1.0f - q * q), 0.55f), l = lip(x);
  return l + fmaxf2(0.0f, top0 + d - l) * f;
}

MouthGeom mouthGeom(const FaceState& p, const Recipe& r, float t) {
  MouthGeom m;
  m.style = r.mouth < 3 ? r.mouth : MOUTH_PUP;
  const MouthStyle& M = MOUTH[m.style];
  m.hwM = M.hw; m.dipM = M.dip; m.liftM = M.lift; m.depthM = M.depth; m.lwM = M.lw;
  m.mx = CX + p.lookX * 2.0f + p.noseDX * 0.3f;
  m.my = mouthY;
  m.hw = M.hw * p.mouthW * (1.0f - 0.55f * p.mouthO);
  float restOpen = r.mouthRest * clampf((p.smile + 0.1f) / 0.5f, 0.0f, 1.0f) * (1.0f - p.mouthO);
  m.o = clampf(p.open + restOpen, 0.0f, 1.0f);
  m.lift = p.smile * M.lift;
  m.dip = M.dip * clampf(0.45f + p.smile, 0.25f, 1.25f) * (1.0f - 0.7f * p.mouthO);
  m.wob = p.wobble;
  m.smile = p.smile;
  m.skew = p.skew;
  m.t = t;
  m.hwo = m.hw * (m.style == MOUTH_SIMPLE ? 0.86f : 0.9f);
  m.top0 = m.my + (m.style == MOUTH_SIMPLE ? 2.0f : m.dip * 0.55f);
  float maxD = M.depth * (1.0f + 0.25f * p.mouthO);
  m.d = m.o * maxD;
  m.tongueOut = clampf((p.tongue - 0.5f) * 2.0f, 0.0f, 1.0f);
  float room = mouthMaxY - m.top0 - 1.0f;
  m.hang = m.tongueOut * 16.0f + p.pant * 5.0f;
  if (m.d + m.hang > room) {
    float k = room / (m.d + m.hang);
    m.d *= k;
    m.hang *= k;
  }
  return m;
}

// HUNGRY lick + drool on one 3.6 s cycle.
static void drawLick(Gfx& G, const FaceState& p, const Recipe& r, float t, const MouthGeom& m, Rgb line) {
  const float P = 3.6f;
  float c = fmodf(fmodf(t, P) + P, P), L = p.lick;
  float minY = 0.705f * H + 1.0f, maxY = mouthMaxY - 1.0f;
  Shape s;
  if (c < 1.0f) {
    float k = c / 1.0f, env = sinf(k * PI) * L;
    if (env < 0.03f) return;
    float sx = lerpf(-0.7f, 0.7f, smoothstepf(0, 1, k));
    float tx = m.mx + sx * m.hw * 0.8f, ly = m.lip(tx);
    float rr = 4.5f + 3.5f * env;
    float up = fmaxf2(0.0f, fminf2(rr * 1.1f * env + 2.0f, ly - minY - (rr * 0.9f + 2.0f)));
    float cx2 = tx + sx * 3.0f, cy2 = ly - up;
    { Circ cc[] = {{tx, ly + 2, rr + 2}, {cx2, cy2, rr * 0.9f + 2}}; circleHull(cc, 2, 12, s); G.poly(s.data(), s.n, line, 1); }
    { Circ cc[] = {{tx, ly + 2, rr}, {cx2, cy2, rr * 0.9f}}; circleHull(cc, 2, 12, s); G.poly(s.data(), s.n, r.tongueColor, 1); }
    G.line(tx, ly + 1, (cx2 + tx) / 2, (cy2 + ly) / 2, 1.6f, shade(r.tongueColor, -0.28f), 0.8f);
    G.circle(cx2 - rr * 0.3f, cy2 - rr * 0.2f, rr * 0.22f, 0xFFFFFF, 0.35f);
  } else {
    float k2 = (c - 1.0f) / (P - 1.0f);
    float dx = m.mx + m.hw * 0.62f, base = m.lip(dx) + 1.0f;
    float len, dropY, rad, al = L;
    if (k2 < 0.7f) {
      float g = k2 / 0.7f;
      len = 2.0f + 13.0f * powf(g, 1.4f);
      rad = 3.2f + 2.8f * g;
      dropY = base + len + rad * 0.6f;
    } else {
      float f = (k2 - 0.7f) / 0.3f;
      len = 15.0f * (1.0f - f);
      rad = 6.0f * (1.0f - 0.3f * f);
      dropY = base + 18.0f + 16.0f * f * f;
      al = L * (1.0f - f);
    }
    dropY = fminf2(dropY, maxY - rad - 1.2f);
    if (len > 0.5f) { Circ cc[] = {{dx, base, 2.4f}, {dx, base + len, 1.6f}}; circleHull(cc, 2, 8, s); G.poly(s.data(), s.n, 0xBFE6FF, 0.95f * L); }
    G.circle(dx, dropY, rad + 1.2f, 0x7FC3EC, 0.9f * al);
    G.circle(dx, dropY, rad, 0xDDF4FF, al);
    G.circle(dx - rad * 0.35f, dropY - rad * 0.35f, fmaxf2(0.6f, rad * 0.3f), 0xFFFFFF, al);
  }
}

static MouthGeom drawMouth(Gfx& G, const FaceState& p, const Recipe& r, float t, const NoseInfo& nose) {
  MouthGeom m = mouthGeom(p, r, t);
  Rgb line = contrastOn(r.eyeStyle == EYE_GLOW ? r.eyeColor : r.lineColor, mouthSkin(r));
  float lw = m.lwM;

  if (m.style != MOUTH_SIMPLE) {
    G.tag(Tag::Philtrum);
    G.line(nose.x, nose.bottom - 2.0f, m.mx, m.lip(m.mx) + 0.5f, lw * 0.85f, line, 1);
  }
  G.tag(Tag::Mouth);

  if (m.o > 0.02f && m.d > 1.0f) {
    float xs[32], tops[32], bots[32];
    cosXs(m.mx - m.hwo - 2.0f, m.mx + m.hwo + 2.0f, 26, xs);
    for (int i = 0; i <= 26; i++) {
      float x = xs[i], lp = m.lip(x) - 0.5f, qq = (x - m.mx) / (m.hwo + 2.0f);
      tops[i] = lp;
      bots[i] = m.bot(x) + 2.6f * powf(fmaxf2(0.0f, 1.0f - qq * qq), 0.3f);
    }
    band(G, xs, tops, bots, 27, line, 1);  // outline
    float xs2[32], tops2[32], bots2[32];
    cosXs(m.mx - m.hwo, m.mx + m.hwo, 26, xs2);
    for (int j = 0; j <= 26; j++) { tops2[j] = m.lip(xs2[j]); bots2[j] = m.bot(xs2[j]); }
    Rgb inside = r.eyeStyle == EYE_GLOW ? 0x2A0E14 : 0x7A2630;
    band(G, xs2, tops2, bots2, 27, inside, 1);  // interior
    clippedEllipse(G, m.mx, m.top0 + 1.0f, m.hwo * 0.75f, m.d * 0.45f, [&m](float x) { return m.lip(x); },
                   [&m](float x) { return m.bot(x); }, 0x4E1520, 0.55f, 14);

    if (p.tongue > 0.04f && m.o > 0.08f) {
      float tw = m.hwo * lerpf(0.5f, 0.64f, clampf(p.tongue * 2.0f, 0.0f, 1.0f));
      float bounce = p.pant * 4.5f * fabsf(sinf(t * 8.5f));
      float tTop = m.top0 + m.d * lerpf(0.5f, 0.25f, m.tongueOut) + bounce * 0.4f;
      float tBot = m.top0 + m.d + m.hang * (m.tongueOut > 0 ? 1.0f : 0.0f) + bounce * (m.tongueOut > 0 ? 1.0f : 0.3f);
      tBot = fminf2(tBot, mouthMaxY - 0.5f);
      float tx = m.mx + p.skew * 3.0f;
      float xs3[24], t3[24], b3[24];
      cosXs(tx - tw, tx + tw, 20, xs3);
      for (int k2 = 0; k2 <= 20; k2++) {
        float xx = xs3[k2], q = (xx - tx) / tw;
        float tt = tTop + q * q * 4.0f;
        float tb = tTop + (tBot - tTop) * powf(fmaxf2(0.0f, 1.0f - q * q), 0.45f);
        t3[k2] = fmaxf2(tt, m.lip(xx));
        b3[k2] = m.tongueOut > 0.02f ? tb : fminf2(tb, m.bot(xx));
      }
      if (m.tongueOut > 0.02f) {
        float t4[24], b4[24];
        for (int k3 = 0; k3 <= 20; k3++) {
          t4[k3] = t3[k3];
          b4[k3] = b3[k3] > m.bot(xs3[k3]) ? b3[k3] + 2.0f : b3[k3];
        }
        band(G, xs3, t4, b4, 21, line, 1);
      }
      band(G, xs3, t3, b3, 21, r.tongueColor, 1);
      float gy0 = fmaxf2(tTop + 3.0f, m.lip(tx) + 3.0f), gy1 = tTop + (tBot - tTop) * 0.55f;
      if (gy1 > gy0 + 2.0f) G.line(tx, gy0, tx, gy1, 2, shade(r.tongueColor, -0.28f), 0.9f);
      G.ellipse(tx - tw * 0.38f, tTop + (tBot - tTop) * 0.34f, tw * 0.16f, fmaxf2(1.0f, (tBot - tTop) * 0.12f), -0.3f,
                0xFFFFFF, 0.3f);
    }
  }

  // lip line (the smile itself), cusp kept sharp for the "w" shapes
  {
    PBuf pts;
    const int n = 10;
    for (int a = 0; a <= n; a++) { float xa = m.mx - m.hw + m.hw * (float)a / n; pts.push(xa, m.lip(xa)); }
    for (int b = 1; b <= n; b++) { float xb = m.mx + m.hw * (float)b / n; pts.push(xb, m.lip(xb)); }
    G.polyline(pts.data(), pts.n, lw, line, 1);
  }
  float dimple = smoothstepf(0.45f, 0.9f, p.smile) * (1.0f - p.mouthO);
  if (dimple > 0.02f) {
    for (int s = -1; s <= 1; s += 2) {
      float cx = m.mx + (float)s * m.hw, cy = m.lip(cx);
      G.line(cx, cy, cx + (float)s * 4.5f, cy - 1.8f, lw * 0.8f, line, dimple);
    }
  }
  if (p.lick > 0.02f) drawLick(G, p, r, t, m, line);
  if (p.fang > 0.03f) {
    float fx = m.mx + m.hw * (m.style == MOUTH_OMEGA ? 0.55f : 0.42f), fy = m.lip(fx);
    G.tri(fx - 3.6f, fy + 0.5f, fx + 3.6f, m.lip(fx + 3.6f) + 0.5f, fx + 0.4f, fy + 8.5f * p.fang, 0xFFFFFF, 1);
  }
  return m;
}

// ================================================================================================
// CHEEKS, FRECKLES, WHISKERS
// ================================================================================================
static void drawCheeks(Gfx& G, const FaceState& p, const Recipe& r, const EyeGeom& gL, const EyeGeom& gR) {
  G.tag(Tag::Cheek);
  float al = clampf(r.blush + 0.7f * p.blush, 0.0f, 0.85f);
  if (luminance(r.fur) < 0.3f) al = clampf(al * 1.5f, 0.0f, 0.9f);
  const EyeGeom* eyes[2] = {&gL, &gR};
  for (int i = 0; i < 2; i++) {
    const EyeGeom& g = *eyes[i];
    float s = (float)g.side;
    float bx = g.ex + s * 0.52f * g.a0, by = g.ey + g.b0 * 1.02f + 5.0f;
    if (al > 0.01f) G.ellipse(bx, by, 0.64f * g.a0, 0.3f * g.a0, 0, r.blushColor, al);
    if (p.blushLines > 0.02f) {
      for (int k = 0; k < 3; k++) {
        float lx = bx - 11.0f + (float)k * 8.0f;
        G.line(lx - 3.0f, by + 5.0f, lx + 3.0f, by - 5.0f, 2.3f, shade(r.blushColor, -0.3f), p.blushLines);
      }
    }
    if (r.freckles == FRECK_YES) {
      Rgb fc = shade(r.fur, -0.35f);
      G.circle(bx - 7, by + 1, 2, fc, 0.8f);
      G.circle(bx + 1, by + 4, 2, fc, 0.8f);
      G.circle(bx + 8, by, 2, fc, 0.8f);
    }
  }
}

static void drawWhiskers(Gfx& G, const FaceState& p, const Recipe& r, float t) {
  if (r.whiskers == WHISK_NONE) return;
  G.tag(Tag::Whisker);
  const MouthStyle& m = MOUTH[r.mouth < 3 ? r.mouth : 0];
  float ox = fmaxf2(m.hw * p.mouthW + 12.0f, 36.0f);
  float len = r.whiskers == WHISK_LONG ? 70.0f : 44.0f;
  Rgb wc = contrastOn(r.whiskerColor, r.fur);
  float perk = p.smile * 0.08f - p.earBack * 0.08f + p.noseDY * 0.015f + 0.02f * sinf(t * 2.1f);
  for (int si = -1; si <= 1; si += 2) {
    float s = (float)si;
    for (int k = 0; k < 3; k++) {
      float x0 = CX + s * ox + p.lookX * 2.0f, y0 = mouthY - 9.0f + (float)(k - 1) * 8.0f;
      float L = len - fabsf((float)(k - 1)) * 9.0f;
      float ang = (float)(k - 1) * 0.2f - perk;
      float x2 = x0 + s * L * cosf(ang), y2 = y0 + L * sinf(ang);
      float xm = (x0 + x2) / 2, ym = (y0 + y2) / 2 - 2.5f;
      float pts[6] = {x0, y0, xm, ym, x2, y2};
      G.polyline(pts, 3, 2, wc, 0.9f);
    }
    for (int d = 0; d < 3; d++)
      G.circle(CX + s * (ox - 10.0f + (float)(d % 2) * 6.0f), mouthY - 12.0f + (float)d * 6.0f, 1.6f,
               shade(r.whiskerColor, -0.1f), 0.7f);
  }
}
// ================================================================================================
// FUR: head silhouette (sticker frame), patterns, muzzle
// ================================================================================================
static const float HEAD_CX = CX, HEAD_CY = 170, HEAD_RX = 180, HEAD_RY = 154, HEAD_N = 2.2f;

static void headPoly(float grow, PBuf& out) {
  out.clear();
  float rx = HEAD_RX + grow, ry = HEAD_RY + grow;
  for (int i = 0; i < 72; i++) {
    float a = (float)i / 72.0f * TAU, c = cosf(a), s = sinf(a);
    out.push(HEAD_CX + rx * sgnf(c) * powf(fabsf(c), 2.0f / HEAD_N), HEAD_CY + ry * sgnf(s) * powf(fabsf(s), 2.0f / HEAD_N));
  }
}

static const float SPOTS[8][5] = {{-178, 52, 17, 13, 0.3f}, {156, 36, 21, 15, -0.4f}, {196, 150, 15, 11, 0.2f},
                                  {-196, 172, 19, 14, -0.2f}, {112, 238, 13, 9, 0.5f}, {-58, 28, 11, 8, 0.1f},
                                  {-120, 246, 11, 8, 0}, {60, 14, 8, 6, 0.4f}};

static void drawPattern(Gfx& G, const FaceState& p, const Recipe& r, const EyeGeom& gL, const EyeGeom& gR, float headTop) {
  (void)p;
  uint8_t pat = r.pattern;
  Rgb c2 = r.fur2, c3 = r.fur3;
  float s = r.patternSide == SIDE_RIGHT ? 1.0f : -1.0f;
  const EyeGeom& g = s < 0 ? gL : gR;
  G.tag(Tag::Fur);
  if (pat == PAT_PATCH) {
    G.ellipse(g.ex + s * 5, g.ey - 4, g.a0 * 1.62f, g.b0 * 1.36f, s * 0.25f, c2, 1);
    G.ellipse(g.ex + s * 22, g.ey - 38, g.a0 * 1.08f, g.b0 * 0.8f, s * 0.5f, c2, 1);
    G.ellipse(g.ex - s * 12, g.ey + 20, g.a0 * 1.0f, g.b0 * 0.62f, -s * 0.3f, c2, 1);
  } else if (pat == PAT_SPOTS) {
    for (int i = 0; i < 8; i++) {
      const float* sp = SPOTS[i];
      G.ellipse(CX + sp[0] * -s, sp[1] + (headTop > 0 ? 8.0f : 0.0f), sp[2], sp[3], sp[4], c2, 1);
    }
  } else if (pat == PAT_TABBY) {
    const float xsT[3] = {-30, 0, 30}, ls[3] = {36, 50, 36};
    for (int k = 0; k < 3; k++) {
      float x = CX + xsT[k], y0 = headTop - 2;
      Shape h, o;
      Circ cc[] = {{0, 0, 6.5f}, {0, ls[k], 2}};
      circleHull(cc, 2, 10, h);
      xform(h, x, y0, xsT[k] * 0.006f, 1, 1, o);
      G.poly(o.data(), o.n, c2, 1);
    }
    for (int sd = -1; sd <= 1; sd += 2) {
      for (int j = 0; j < 2; j++) {
        float yy = 168.0f + (float)j * 22.0f;
        Shape h;
        Circ cc[] = {{CX + (float)sd * 236, yy, 6.5f}, {CX + (float)sd * 184, yy + 5.0f - (float)j * 2.0f, 2}};
        circleHull(cc, 2, 10, h);
        G.poly(h.data(), h.n, c2, 1);
      }
    }
  } else if (pat == PAT_CALICO) {
    G.ellipse(CX + s * 150, 24, 118, 84, -s * 0.3f, c2, 1);
    G.ellipse(CX + s * 196, 118, 60, 70, 0, c2, 1);
    G.ellipse(CX - s * 178, 8, 92, 56, s * 0.35f, c3, 1);
    G.ellipse(CX - s * 214, 70, 34, 40, 0, c3, 1);
  } else if (pat == PAT_BLAZE) {
    float pts[8] = {CX - 9, headTop - 4, CX + 9, headTop - 4, CX + 27, 150, CX - 27, 150};
    G.poly(pts, 4, c2, 1);
    G.ellipse(CX, 214, 94, 64, 0, c2, 1);
  } else if (pat == PAT_MASK) {
    G.ellipse(CX, -72, 330, 160, 0, c2, 1);
    G.tri(CX - 30, 60, CX + 30, 60, CX, 116, c2, 1);
    G.ellipse(gL.ex, gL.ey - gL.b0 - 11, 15, 9, 0.15f, r.fur, 1);
    G.ellipse(gR.ex, gR.ey - gR.b0 - 11, 15, 9, -0.15f, r.fur, 1);
  } else if (pat == PAT_TUX) {
    G.ellipse(CX, 268, 156, 104, 0, c2, 1);
    G.tri(CX - 34, 180, CX + 34, 180, CX, 108, c2, 1);
  }
}

static void drawMuzzle(Gfx& G, const Recipe& r) {
  if (r.muzzle == MUZ_NONE) return;
  G.tag(Tag::Fur);
  if (r.muzzle == MUZ_ROUND) G.ellipse(CX, mouthY - 4, 66, 48, 0, r.muzzleColor, 1);
  else {
    G.ellipse(CX - 31, mouthY + 1, 48, 37, 0, r.muzzleColor, 1);
    G.ellipse(CX + 31, mouthY + 1, 48, 37, 0, r.muzzleColor, 1);
  }
}

// ================================================================================================
// EARS (at the top corners; floppy ones swing like real flaps)
// ================================================================================================
static void earPoly(Gfx& G, const Shape& sh, float ax, float ay, float rot, float sx, float sy, Rgb c, float a) {
  Shape o;
  xform(sh, ax, ay, rot, sx, sy, o);
  G.poly(o.data(), o.n, c, a);
}

// front: true = only ears that hang in FRONT of a sticker head (floppy).
static void drawEars(Gfx& G, const FaceState& p, const Recipe& r, bool full, float t, bool front) {
  uint8_t st = r.ears;
  if (st == EARS_NONE) return;
  bool floppyish = st == EARS_FLOPPY;
  if (!full && (front ? !floppyish : floppyish)) return;
  G.tag(Tag::Ear);
  const Shapes& S = shapes();
  Rgb col = r.earColor, inn = r.earInner;
  float sway = sinf(t * 1.7f) * 1.2f;
  int calS = r.patternSide == SIDE_RIGHT ? 1 : -1;
  for (int si = -1; si <= 1; si += 2) {
    float s = (float)si;
    float flick = si < 0 ? p.earL : p.earR;
    if (r.pattern == PAT_CALICO) col = si == calS ? r.fur2 : r.fur3;
    float ax, ay, out, rot;
    if (st == EARS_FLOPPY || (st == EARS_BUNNY && full)) {
      bool lop = st == EARS_BUNNY;
      ax = CX + s * (full ? (lop ? 176.0f : 170.0f) : 166.0f);
      ay = full ? -30.0f : 42.0f;
      out = (lop ? 8.0f : (full ? 16.0f : 26.0f)) + 18.0f * p.earPerk + 22.0f * p.earBack + flick + sway;
      rot = -s * out * DEG;
      float fl = si < 0 ? 1.0f : -1.0f;
      earPoly(G, lop ? S.lopOut : S.floppyOut, ax, ay, rot, fl * 1.05f, 1.03f, shade(col, -0.2f), 1);
      earPoly(G, lop ? S.lopOut : S.floppyOut, ax, ay, rot, fl, 1, col, 1);
      earPoly(G, lop ? S.lopIn : S.floppyIn, ax, ay, rot, fl, 1, inn, lop ? 0.8f : 0.35f);
    } else if (st == EARS_POINTY || st == EARS_FOLD) {
      ax = CX + s * (full ? 164.0f : 132.0f);
      ay = full ? 46.0f : 62.0f;
      out = (full ? 12.0f : 24.0f) - 10.0f * p.earPerk + 40.0f * p.earBack + flick + sway;
      rot = s * out * DEG;
      if (st == EARS_POINTY) {
        earPoly(G, S.pointOut, ax, ay, rot, 1.07f, 1.05f, shade(col, -0.22f), 1);
        earPoly(G, S.pointOut, ax, ay, rot, 1, 1, col, 1);
        earPoly(G, S.pointIn, ax, ay, rot, 1, 1, inn, 0.95f);
      } else {
        earPoly(G, S.foldOut, ax, ay - 8, rot, 1.07f, 1.06f, shade(col, -0.22f), 1);
        earPoly(G, S.foldOut, ax, ay - 8, rot, 1, 1, col, 1);
        earPoly(G, S.foldFlap, ax, ay - 8, rot, 1, 1, shade(col, -0.16f), 1);
      }
    } else if (st == EARS_BUNNY) {
      ax = CX + s * 92;
      ay = 40;
      rot = s * (14.0f - 8.0f * p.earPerk + 30.0f * p.earBack + flick + sway) * DEG;
      earPoly(G, S.bunnyOut, ax, ay, rot, 1, 1, col, 1);
      earPoly(G, S.bunnyIn, ax, ay, rot, 1, 1, inn, 0.9f);
    } else {  // round / bear
      bool big = st == EARS_ROUND;
      float R = big ? 46.0f : 36.0f, lift = (p.earPerk * 4.0f - p.earBack * 8.0f) + flick * 0.3f;
      ax = CX + s * (big ? 168.0f : 150.0f);
      ay = (full ? (big ? 16.0f : 12.0f) : 48.0f) - lift;
      G.circle(ax, ay, R + 3, shade(col, -0.22f), 1);
      G.circle(ax, ay, R, col, 1);
      G.circle(ax - s * 3, ay + 5, R * 0.58f, inn, 0.9f);
    }
  }
}

// ================================================================================================
// ACCESSORIES (glasses are opt-in: the only thing allowed to bridge the eyes)
// ================================================================================================
static void drawAccessory(Gfx& G, const FaceState& p, const Recipe& r, const EyeGeom& gL, const EyeGeom& gR,
                          float headTop, float t) {
  (void)p;
  uint8_t acc = r.accessory;
  Rgb c = r.accColor;
  float s2 = r.patternSide == SIDE_LEFT ? 1.0f : -1.0f;
  if (acc == ACC_NONE) return;
  G.tag(Tag::Accessory);
  Shape sh;
  if (acc == ACC_BOW) {
    G.save();
    G.translate(CX + s2 * 120, (headTop > 0 ? 34.0f : 28.0f));
    G.rotate(s2 * 0.28f);
    { Circ cc[] = {{0, 0, 6}, {-27, -13, 11}, {-29, 13, 11}}; circleHull(cc, 3, 12, sh); G.poly(sh.data(), sh.n, c, 1); }
    { Circ cc[] = {{0, 0, 6}, {27, -13, 11}, {29, 13, 11}}; circleHull(cc, 3, 12, sh); G.poly(sh.data(), sh.n, c, 1); }
    G.ellipse(-20, -9, 6, 3.5f, -0.4f, 0xFFFFFF, 0.4f);
    G.ellipse(20, -9, 6, 3.5f, 0.4f, 0xFFFFFF, 0.4f);
    G.circle(0, 0, 8.5f, shade(c, -0.12f), 1);
    G.circle(-2, -2.5f, 2.5f, 0xFFFFFF, 0.45f);
    G.restore();
  } else if (acc == ACC_BANDANA) {
    float xs[25], tops[25], bots[25];
    for (int i = 0; i <= 24; i++) {
      float x = (float)i / 24.0f * W;
      xs[i] = x;
      tops[i] = headTop - 12;
      float q = (x - CX) / CX;
      bots[i] = headTop + 18 + 12 * (1 - q * q);
    }
    band(G, xs, tops, bots, 25, c, 1);
    for (int d = 0; d < 9; d++) {
      float dx = 40.0f + (float)d * 50.0f, q = (dx - CX) / CX;
      G.circle(dx, headTop + 14 + 6 * (1 - q * q), 3, 0xFFFFFF, 0.85f);
    }
    float kx = CX - s2 * 170, ky = headTop + 24;
    { Circ cc[] = {{kx, ky, 5}, {kx - s2 * 16, ky + 26, 7}}; circleHull(cc, 2, 10, sh); G.poly(sh.data(), sh.n, shade(c, -0.1f), 1); }
    { Circ cc[] = {{kx, ky, 5}, {kx - s2 * 30, ky + 14, 7}}; circleHull(cc, 2, 10, sh); G.poly(sh.data(), sh.n, shade(c, -0.1f), 1); }
    G.circle(kx, ky, 9, shade(c, -0.18f), 1);
  } else if (acc == ACC_GLASSES) {
    G.tag(Tag::AccessoryGlasses);
    const EyeGeom* eyes[2] = {&gL, &gR};
    for (int e = 0; e < 2; e++) {
      const EyeGeom& g = *eyes[e];
      float R = fmaxf2(g.a0, g.b0) * 1.2f;
      G.circle(g.ex, g.ey, R, 0xFFFFFF, 0.12f);
      G.arc(g.ex, g.ey, R, 0, TAU, 4.5f, 0x3A3A46, 1);
      G.line(g.ex + (float)g.side * R * 0.96f, g.ey - 6, g.ex + (float)g.side * (R + 20), g.ey - 12, 4, 0x3A3A46, 1);
    }
    float ix0 = gL.ex + fmaxf2(gL.a0, gL.b0) * 1.2f, ix1 = gR.ex - fmaxf2(gR.a0, gR.b0) * 1.2f;
    float pts[6] = {ix0, gL.ey - 8, CX, gL.ey - 16, ix1, gR.ey - 8};
    G.polyline(pts, 3, 4, 0x3A3A46, 1);
  } else if (acc == ACC_HAT) {
    G.save();
    G.translate(CX + s2 * 96, headTop + 56);
    G.rotate(s2 * 0.3f);
    G.tri(-29, 0, 29, 0, 0, -66, c, 1);
    float b1[8] = {-19.4f, -22, 19.4f, -22, 15, -32, -15, -32};
    G.poly(b1, 4, 0xFFFFFF, 0.75f);
    float b2[8] = {-8.8f, -46, 8.8f, -46, 4.4f, -56, -4.4f, -56};
    G.poly(b2, 4, 0xFFFFFF, 0.75f);
    G.rrect(-31, -4, 62, 8, 4, shade(c, -0.2f), 1);
    G.circle(0, -68, 8, 0xFFFFFF, 1);
    G.restore();
  } else if (acc == ACC_FLOWER) {
    float fx = CX + s2 * 132, fy = headTop + 40, rot = t * 0.2f;
    for (int k = 0; k < 5; k++) {
      float a = rot + (float)k / 5.0f * TAU;
      G.circle(fx + cosf(a) * 11, fy + sinf(a) * 11, 9.5f, c, 1);
    }
    G.circle(fx, fy, 7.5f, 0xFFD23F, 1);
    G.circle(fx - 2, fy - 2, 2.5f, 0xFFFFFF, 0.6f);
  }
}

// ================================================================================================
// DECALS: anger vein, sweat drop, gloom lines, low battery, sleep bubble, tear streams
// ================================================================================================
static void drawDecals(Gfx& G, const FaceState& p, const Recipe& r, const EyeGeom& gL, const EyeGeom& gR,
                       const NoseInfo& nose, float headTop, float t) {
  G.tag(Tag::Decal);
  if (p.cry > 0.02f) {
    const EyeGeom* eyes[2] = {&gL, &gR};
    for (int e = 0; e < 2; e++) {
      const EyeGeom& g = *eyes[e];
      float sd = (float)g.side;
      float sx = g.ex + sd * 0.5f * g.a0, sy = g.ey + 0.72f * g.b0;
      float len = 62.0f * p.cry;
      Shape sh;
      Circ cc[] = {{sx, sy, 4.5f}, {sx + sd * 5, sy + len, 7.5f}};
      circleHull(cc, 2, 12, sh);
      G.poly(sh.data(), sh.n, 0x8FD3FF, 0.75f * p.cry);
      for (int k = 0; k < 2; k++) {
        float f = fmodf(t * 1.3f + (float)k * 0.5f, 1.0f);
        G.circle(sx + sd * 5 * f, sy + len * f + 4, 4.5f, 0xCFEFFF, 0.9f * p.cry * (1 - f * 0.5f));
      }
    }
  }
  if (p.vein > 0.02f) {
    float vSide = (r.accessory == ACC_NONE || r.accessory == ACC_GLASSES) ? (r.patternSide == SIDE_LEFT ? 1.0f : -1.0f)
                                                                          : (r.patternSide == SIDE_LEFT ? -1.0f : 1.0f);
    float vx = CX + vSide * 118, vy = headTop + 54, vs = 1.5f * (1 + 0.14f * sinf(t * 9));
    for (int dx = -1; dx <= 1; dx += 2)
      for (int dy = -1; dy <= 1; dy += 2) {
        float fx = (float)dx, fy = (float)dy;
        float vp[6] = {vx + fx * 3 * vs, vy + fy * 11 * vs, vx + fx * 3.5f * vs, vy + fy * 3.5f * vs, vx + fx * 11 * vs,
                       vy + fy * 3 * vs};
        G.polyline(vp, 3, 7, 0xFFFFFF, 0.85f * p.vein);
        G.polyline(vp, 3, 3.8f, 0xE53935, p.vein);
      }
  }
  if (p.sweat > 0.02f) {
    float wx = CX + 150, wy = headTop + 52 + 9 * fmodf(t * 0.4f, 1.0f);
    G.circle(wx, wy, 11, 0xFFFFFF, 0.9f * p.sweat);
    G.tri(wx - 10, wy - 4, wx + 10, wy - 4, wx, wy - 27, 0xFFFFFF, 0.9f * p.sweat);
    G.circle(wx, wy, 9, 0x7CC8F8, p.sweat);
    G.tri(wx - 8.1f, wy - 4, wx + 8.1f, wy - 4, wx, wy - 23, 0x7CC8F8, p.sweat);
    G.ellipse(wx - 3.5f, wy + 1, 2.4f, 3.8f, 0, 0xFFFFFF, 0.85f * p.sweat);
  }
  if (p.gloom > 0.02f) {
    for (int j = 0; j < 5; j++) {
      float gx = CX - 84 + (float)j * 42, gl = 26 + 16 * hashf((float)(j + 3));
      G.line(gx, headTop + 4, gx, headTop + 4 + gl * p.gloom, 3, 0x7383B0, 0.55f * p.gloom);
    }
  }
  if (p.batt > 0.02f && r.eyeStyle != EYE_GLOW) {
    G.tag(Tag::DecalBattery);
    float bs = p.batt, bxc = CX, byc = headTop + (headTop > 0 ? 40.0f : 34.0f) + sinf(t * 3) * 2;
    float bw2 = 56 * bs, bh2 = 29 * bs, rad2 = 7 * bs;
    G.rrect(bxc - bw2 / 2 - 3, byc - bh2 / 2 - 3, bw2 + 6 + 5 * bs, bh2 + 6, rad2 + 3, 0xFFFFFF, 0.9f);
    bool redOn = sinf(t * 7) > -0.2f;
    Rgb shell = redOn ? 0xE53935 : 0x2E2320;
    G.rrect(bxc - bw2 / 2, byc - bh2 / 2, bw2, bh2, rad2, shell, 1);
    G.rrect(bxc + bw2 / 2 - 1, byc - 5 * bs, 5 * bs, 10 * bs, 2 * bs, shell, 1);
    G.rrect(bxc - bw2 / 2 + 3.5f * bs, byc - bh2 / 2 + 3.5f * bs, bw2 - 7 * bs, bh2 - 7 * bs, 3 * bs, 0xFFFFFF, 1);
    G.rrect(bxc - bw2 / 2 + 6 * bs, byc - bh2 / 2 + 6 * bs, (bw2 - 12 * bs) * 0.3f, bh2 - 12 * bs, 2 * bs, 0xFF3B3B,
            redOn ? 1.0f : 0.45f);
    G.tag(Tag::Decal);
  }
  if (p.bubble > 0.02f) {
    float rb = (5 + 11 * (0.5f + 0.5f * sinf(t * 1.6f))) * p.bubble;
    float bx = nose.x + 13 + rb * 0.7f, by = nose.y - 2 - rb * 0.3f;
    G.circle(bx, by, rb, 0xBFE6FF, 0.4f * p.bubble);
    G.arc(bx, by, rb, 0, TAU, 1.6f, 0xFFFFFF, 0.75f * p.bubble);
    G.circle(bx - rb * 0.35f, by - rb * 0.35f, fmaxf2(1.0f, rb * 0.18f), 0xFFFFFF, 0.9f * p.bubble);
  }
}

// ================================================================================================
// MAIN ENTRY
// ================================================================================================
void drawFace(Gfx& G, const FaceState& p, const Recipe& r, float t, FaceResult* out) {
  bool full = r.frame != FRAME_HEAD;
  G.resetTransform();
  G.tag(Tag::Fur);
  G.rect(0, 0, W, H, full ? r.fur : r.bg, 1);

  EyeGeom gL = eyeGeom(p, r, -1), gR = eyeGeom(p, r, 1);
  float headTop = full ? -6.0f : HEAD_CY - HEAD_RY;

  G.save();
  float px = CX, py = pivotY;
  G.translate(px + p.shakeX, py + p.bob);
  if (p.tilt != 0.0f) G.rotate(p.tilt * DEG);
  G.scale(p.headSX, p.headSY);
  G.translate(-px, -py);

  if (!full) {
    drawEars(G, p, r, false, t, false);
    G.tag(Tag::Fur);
    const Shapes& S = shapes();
    G.poly(S.headOutline.data(), S.headOutline.n, shade(r.fur, -0.3f), 1);
    G.poly(S.headPoly.data(), S.headPoly.n, r.fur, 1);
  }
  drawPattern(G, p, r, gL, gR, headTop);
  drawMuzzle(G, r);
  if (r.accessory == ACC_BANDANA) drawAccessory(G, p, r, gL, gR, headTop, t);
  drawEars(G, p, r, full, t, true);
  drawCheeks(G, p, r, gL, gR);
  drawWhiskers(G, p, r, t);
  EyeGeom eL = drawEye(G, p, r, -1, t);
  EyeGeom eR = drawEye(G, p, r, 1, t);
  drawBrows(G, p, r, eL, -1);
  drawBrows(G, p, r, eR, 1);
  NoseInfo nose = drawNose(G, p, r);
  MouthGeom mouth = drawMouth(G, p, r, t, nose);
  drawDecals(G, p, r, gL, gR, nose, headTop, t);
  if (r.accessory != ACC_BANDANA) drawAccessory(G, p, r, gL, gR, headTop, t);
  G.restore();

  float dim = clampf(r.dim + p.dim, 0.0f, 0.85f);
  if (dim > 0.003f) {
    G.tag(Tag::Dim);
    G.rect(0, 0, W, H, 0x000000, dim);
  }
  G.tag(Tag::Face);
  if (out) {
    out->eyes[0] = eL;
    out->eyes[1] = eR;
    out->nose = nose;
    out->mouth = mouth;
  }
}

HitZone hitTest(const FaceState& p, const Recipe& r, float x, float y) {
  NosePos n = nosePos(p, r);
  float dx = x - n.x, dy = y - (n.y + p.bob);
  if (dx * dx / (34.0f * 34.0f) + dy * dy / (26.0f * 26.0f) <= 1.0f) return HIT_NOSE;
  return y < H * 0.5f ? HIT_HEAD : HIT_FACE;
}


}  // namespace spike
