// spike_face_draw.h -- the PURE face renderer, a line-for-line port of face_v2/face_draw.js:
//   drawFace(G, state, recipe, t)
// Same inputs -> same pixels. No timers, no randomness, no heap. `t` (seconds) only drives cyclic
// effects (panting, tear wobble, sparkle, spiral, vein throb, sleep bubble, hungry lick/drool).
// Layout rules (owner's): eye centres at 45 % of the height, nose at 62 %, mouth + tongue inside
// 70-89.5 %, nothing joins the two eyes.
#pragma once
#include "spike_gfx.h"
#include "spike_params.h"
#include "spike_recipe.h"

namespace spike {

namespace layout {
static const float W = 480.0f, H = 272.0f, CX = 240.0f;
static const float eyeY = 0.45f * 272.0f;       // 122.4
static const float eyeDX = 96.0f;
static const float noseY = 0.62f * 272.0f;      // 168.64
static const float mouthY = 0.745f * 272.0f;    // 202.64
static const float mouthMaxY = 0.892f * 272.0f; // 242.62
static const float pivotY = 0.64f * 272.0f;     // 174.08
}  // namespace layout

// Eye opening outline (face_draw.js outlineFns) as two functions of local x.
struct EyeOutline {
  uint8_t shape;
  float a, b;
  float top(float x) const;
  float bot(float x) const;
};

// Everything about one eye this frame (face_draw.js eyeGeom). Edge functions are members.
struct EyeGeom {
  int side;
  float a, b, a0, b0, ex, ey, gx, gy, ix, iy, slant, C, curv;
  // internals used by the edge functions
  float yMeet, arcW, hap, hTop, hBot, Cb, lidT, lidB, lidTilt, lidSag, lidBulge;
  EyeOutline o;
  uint8_t shape;
  float arc(float x) const;
  float arcH(float x) const;
  float topEdge(float x) const;
  float botEdge(float x) const;
  float oTop(float x) const { return gy + o.top(x - gx); }
  float oBot(float x) const { return gy + o.bot(x - gx); }
  float visTop(float x) const { float u = oTop(x), v = topEdge(x); return u > v ? u : v; }
  float visBot(float x) const { float u = oBot(x), v = botEdge(x); return u < v ? u : v; }
};

struct EyeIconInfo { Icon name; float amt; };

struct NoseInfo { float x, y, w, h, bottom; };
struct NosePos { float x, y, sx, sy; };

struct MouthGeom {
  uint8_t style;
  float hwM, dipM, liftM, depthM, lwM;  // the MOUTH style constants
  float mx, my, hw, hwo, o, d, top0, tongueOut, hang;
  // lip() inputs
  float lift, dip, wob, smile, skew, t;
  float lip(float x) const;
  float bot(float x) const;
};

struct FaceResult {
  EyeGeom eyes[2];
  NoseInfo nose;
  MouthGeom mouth;
};

// The renderer. `out` (optional) receives the key geometry for hit tests and layout tests.
void drawFace(Gfx& G, const FaceState& p, const Recipe& r, float t, FaceResult* out = nullptr);

// Helpers exported for tests and the behaviour layer.
EyeGeom eyeGeom(const FaceState& p, const Recipe& r, int side);
EyeIconInfo eyeIcon(const FaceState& p, const Recipe& r);
NosePos nosePos(const FaceState& p, const Recipe& r);
MouthGeom mouthGeom(const FaceState& p, const Recipe& r, float t);
// Which part of the face is at screen (x, y): 0 nose, 1 head (upper half = pat), 2 face.
enum HitZone { HIT_NOSE = 0, HIT_HEAD = 1, HIT_FACE = 2 };
HitZone hitTest(const FaceState& p, const Recipe& r, float x, float y);

}  // namespace spike
