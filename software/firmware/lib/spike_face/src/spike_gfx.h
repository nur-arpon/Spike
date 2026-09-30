// spike_gfx.h -- the small abstract drawing interface every face pixel goes through.
//
// It is the C++ twin of face_v2/gfx.js and has exactly the same primitives:
//   rect, circle, ellipse (optionally rotated), rrect, tri, poly (convex), mpoly (x-monotone band),
//   line (thick, round caps), polyline (round joins/caps), arc (thick stroke), wedge (pie slice)
// Every call takes an alpha. Transforms (save/restore/translate/rotate/scale) are a 2x3 matrix kept here,
// in the base class, so every backend sees the same device-space geometry.
//
// Backends:
//   VectorGfx (spike_raster.h)  anti-aliased coverage rasteriser into a Surface. The SAME code runs on
//                               the PC (RGB888 -> PNG) and on the ESP32-S3 (RGB565 PSRAM frame).
//   RecordGfx (spike_raster.h)  counts primitives and device-space bounds (tests, frame budget).
#pragma once
#include <stdint.h>
#include <math.h>
#include "spike_color.h"

namespace spike {

static const float PI_F = 3.14159265358979f;
static const float TAU_F = 6.28318530717959f;
static const float DEG_F = 0.0174532925199433f;

enum class Tag : uint8_t {
  Face, Fur, Eye, EyeIcon, Brow, Nose, NoseWrinkle, Philtrum, Mouth, Cheek, Whisker, Ear,
  Accessory, AccessoryGlasses, Decal, DecalBattery, Dim, Particle, Count
};
const char* tagName(Tag t);

struct Mat2x3 {
  float a, b, c, d, e, f;  // x' = a x + c y + e ; y' = b x + d y + f   (same as gfx.js)
  void apply(float x, float y, float* ox, float* oy) const {
    *ox = a * x + c * y + e;
    *oy = b * x + d * y + f;
  }
  float scaleFactor() const { return sqrtf(fabsf(a * d - b * c)); }
  bool axisAligned() const { return fabsf(b) < 1e-6f && fabsf(c) < 1e-6f; }
};

// A fixed-capacity point list (flat x,y pairs). The renderer builds every shape in one of these on the
// stack; it never touches the heap. Points past the capacity are dropped (and counted).
template <int N>
struct Pts {
  float v[2 * N];
  int n = 0;  // number of points
  void clear() { n = 0; }
  void push(float x, float y) {
    if (n < N) { v[2 * n] = x; v[2 * n + 1] = y; n++; }
  }
  float x(int i) const { return v[2 * i]; }
  float y(int i) const { return v[2 * i + 1]; }
  const float* data() const { return v; }
};

class Gfx {
 public:
  Gfx() { resetTransform(); }
  virtual ~Gfx() {}

  // --- transform (gfx.js save/restore/translate/rotate/scale) ---------------------------------
  void resetTransform() {
    m_ = Mat2x3{1, 0, 0, 1, 0, 0};
    depth_ = 0;
  }
  void save() {
    if (depth_ < kStack) stack_[depth_] = m_;
    depth_++;
  }
  void restore() {
    if (depth_ > 0) {
      depth_--;
      if (depth_ < kStack) m_ = stack_[depth_];
    }
  }
  void translate(float x, float y) {
    m_.e += m_.a * x + m_.c * y;
    m_.f += m_.b * x + m_.d * y;
  }
  void rotate(float r) {
    float cs = cosf(r), sn = sinf(r);
    float a = m_.a, b = m_.b, c = m_.c, d = m_.d;
    m_.a = a * cs + c * sn;
    m_.b = b * cs + d * sn;
    m_.c = -a * sn + c * cs;
    m_.d = -b * sn + d * cs;
  }
  void scale(float sx, float sy) {
    m_.a *= sx; m_.b *= sx;
    m_.c *= sy; m_.d *= sy;
  }
  const Mat2x3& matrix() const { return m_; }
  void toDevice(float x, float y, float* ox, float* oy) const { m_.apply(x, y, ox, oy); }

  Tag tag(Tag t) { Tag p = tag_; tag_ = t; return p; }
  Tag getTag() const { return tag_; }

  // --- primitives (gfx.js) ---------------------------------------------------------------------
  // Point arrays are flat x,y pairs; nPts is the number of POINTS.
  virtual void rect(float x, float y, float w, float h, Rgb c, float alpha = 1) = 0;
  virtual void circle(float x, float y, float r, Rgb c, float alpha = 1) = 0;
  virtual void ellipse(float x, float y, float rx, float ry, float rot, Rgb c, float alpha = 1) = 0;
  virtual void rrect(float x, float y, float w, float h, float r, Rgb c, float alpha = 1) = 0;
  virtual void tri(float x0, float y0, float x1, float y1, float x2, float y2, Rgb c, float alpha = 1) = 0;
  virtual void poly(const float* pts, int nPts, Rgb c, float alpha = 1) = 0;   // convex
  virtual void mpoly(const float* pts, int nPts, Rgb c, float alpha = 1) = 0;  // x-monotone band
  virtual void line(float x0, float y0, float x1, float y1, float w, Rgb c, float alpha = 1) = 0;
  virtual void polyline(const float* pts, int nPts, float w, Rgb c, float alpha = 1) = 0;
  virtual void arc(float x, float y, float r, float a0, float a1, float w, Rgb c, float alpha = 1) = 0;
  virtual void wedge(float x, float y, float r, float a0, float a1, Rgb c, float alpha = 1) = 0;

 protected:
  static const int kStack = 16;
  Mat2x3 m_;
  Mat2x3 stack_[kStack];
  int depth_ = 0;
  Tag tag_ = Tag::Face;
};

}  // namespace spike
