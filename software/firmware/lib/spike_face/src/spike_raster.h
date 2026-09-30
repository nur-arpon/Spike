// spike_raster.h -- the anti-aliased coverage rasteriser and the VectorGfx backend.
//
// Why a rasteriser of our own instead of LovyanGFX / Arduino_GFX shape calls:
//  * the face needs alpha on every primitive (blush, tears, glow halos, fades). Arduino_GFX has no
//    alpha blending at all, and LovyanGFX's smooth/alpha calls each use their own AA model, so the
//    device would never match the golden images drawn by the browser canvas.
//  * one rasteriser for BOTH the PC build (RGB888 -> PNG) and the ESP32-S3 (RGB565 frame in PSRAM)
//    means the golden-image test checks the pixels the robot will actually show.
// The display library (Arduino_GFX, NV3041A over QSPI) is only used to push finished frames.
//
// Algorithm: exact-area coverage accumulation (the "font-rs" signed-area method), one pixel row at a
// time over the shape's bounding box, active-edge list, non-zero union clamp (coverage = min(1,|w|)).
// Every primitive is turned into device-space polygons first (curves tessellated to <= ~0.05 px error).
#pragma once
#include <stdint.h>
#include "spike_gfx.h"

namespace spike {

// ------------------------------------------------------------------------------------------------
// Surfaces: where coverage rows land.
// ------------------------------------------------------------------------------------------------
class Surface {
 public:
  virtual ~Surface() {}
  int width = 0, height = 0;   // device size in pixels
  int clipY0 = 0, clipY1 = 0;  // drawable rows [clipY0, clipY1) (strip rendering)
  // Solid run (coverage 1): n pixels from (x, y).
  virtual void fillRow(int y, int x, int n, Rgb c, float alpha) = 0;
  // Partial coverage run: cov[i] in (0, 1).
  virtual void blendRow(int y, int x, int n, const float* cov, Rgb c, float alpha) = 0;
};

// 24-bit RGB, row-major, for the PC build and PNG output.
class Rgb888Surface : public Surface {
 public:
  Rgb888Surface(uint8_t* pixels, int w, int h) : px_(pixels) {
    width = w; height = h; clipY0 = 0; clipY1 = h;
  }
  void fillRow(int y, int x, int n, Rgb c, float alpha) override;
  void blendRow(int y, int x, int n, const float* cov, Rgb c, float alpha) override;
  uint8_t* pixels() { return px_; }

 private:
  uint8_t* px_;
};

// 16-bit RGB565 for the device. `originY` lets a buffer hold only rows [originY, originY + rows)
// (strip rendering); the full-frame PSRAM buffer uses originY = 0, rows = height.
class Rgb565Surface : public Surface {
 public:
  Rgb565Surface(uint16_t* pixels, int w, int h, int originY = 0, int rows = -1)
      : px_(pixels), originY_(originY) {
    width = w; height = h;
    clipY0 = originY;
    clipY1 = rows < 0 ? h : originY + rows;
  }
  void setBuffer(uint16_t* pixels) { px_ = pixels; }
  void fillRow(int y, int x, int n, Rgb c, float alpha) override;
  void blendRow(int y, int x, int n, const float* cov, Rgb c, float alpha) override;
  uint16_t* pixels() { return px_; }

 private:
  uint16_t* px_;
  int originY_;
};

// ------------------------------------------------------------------------------------------------
// Path: device-space contours (closed polygons).
// ------------------------------------------------------------------------------------------------
struct Path {
  static const int kMaxPts = 4096;
  static const int kMaxContours = 512;
  float* xy = nullptr;        // 2 * kMaxPts
  int* start = nullptr;       // kMaxContours + 1
  int nPts = 0, nContours = 0;
  int dropped = 0;            // points that did not fit (should stay 0; tests check it)
  bool open = false;

  void clear() { nPts = 0; nContours = 0; open = false; }
  void begin();
  void add(float x, float y);
  // Close the current contour. forcePositive: reverse it if its signed area is negative, so that
  // several overlapping contours (a stroke = quads + round joins) union instead of cancelling.
  void end(bool forcePositive);
};

struct RasterStats {
  uint32_t primitives = 0;
  uint32_t pathPoints = 0;
  uint32_t edgeRows = 0;       // edge x row-slab contributions (the rasteriser's inner loop)
  uint32_t rows = 0;           // rows scanned
  uint32_t scanned = 0;        // accumulator cells cleared + prefix-summed (bbox width x rows)
  uint32_t pixelsSolid = 0;    // pixels written with coverage 1
  uint32_t pixelsBlended = 0;  // pixels with partial coverage
  uint32_t dropped = 0;        // path points dropped (capacity)
  void reset() { *this = RasterStats(); }
};

class Raster {
 public:
  Raster();
  ~Raster();
  bool ok() const { return edges_ != nullptr && acc_ != nullptr; }
  void fill(const Path& p, Rgb c, float alpha, Surface& s, RasterStats* st);

 private:
  struct Edge { float x0, y0, x1, y1, dxdy, dir; };
  static const int kMaxEdges = 4096;
  static const int kMaxW = 1024;
  Edge* edges_;
  int* order_;
  int* active_;
  float* acc_;   // kMaxW + 4
  float* cov_;   // kMaxW + 4
  void accumulate(const Edge& e, int y, int bx0, float wAcc);
};

// ------------------------------------------------------------------------------------------------
// VectorGfx: the Gfx backend that tessellates and rasterises into a Surface.
// ------------------------------------------------------------------------------------------------
class VectorGfx : public Gfx {
 public:
  VectorGfx();
  ~VectorGfx() override;
  bool ok() const { return path_.xy != nullptr && raster_.ok(); }
  void setSurface(Surface* s) { surf_ = s; }
  RasterStats stats;

  void rect(float x, float y, float w, float h, Rgb c, float alpha = 1) override;
  void circle(float x, float y, float r, Rgb c, float alpha = 1) override;
  void ellipse(float x, float y, float rx, float ry, float rot, Rgb c, float alpha = 1) override;
  void rrect(float x, float y, float w, float h, float r, Rgb c, float alpha = 1) override;
  void tri(float x0, float y0, float x1, float y1, float x2, float y2, Rgb c, float alpha = 1) override;
  void poly(const float* pts, int nPts, Rgb c, float alpha = 1) override;
  void mpoly(const float* pts, int nPts, Rgb c, float alpha = 1) override;
  void line(float x0, float y0, float x1, float y1, float w, Rgb c, float alpha = 1) override;
  void polyline(const float* pts, int nPts, float w, Rgb c, float alpha = 1) override;
  void arc(float x, float y, float r, float a0, float a1, float w, Rgb c, float alpha = 1) override;
  void wedge(float x, float y, float r, float a0, float a1, Rgb c, float alpha = 1) override;

 private:
  Surface* surf_ = nullptr;
  Path path_;
  Raster raster_;
  float* strokeTmp_ = nullptr;  // device-space copy of polyline points
  void flush(Rgb c, float alpha);
  void addPolyDevice(const float* pts, int nPts);  // user-space points -> one contour
  void strokeDevice(const float* dpts, int nPts, float halfW, bool closed);
  void addCircleDevice(float cx, float cy, float r);
  void addWedgeDevice(float cx, float cy, float r, float a0, float sweep);
  static int segsFor(float rDevice);
};

// ------------------------------------------------------------------------------------------------
// RecordGfx: no pixels; counts primitives per tag and keeps the device-space bounds of each.
// ------------------------------------------------------------------------------------------------
struct RecordEntry {
  Tag tag;
  uint8_t kind;  // 0 rect 1 circle 2 ellipse 3 rrect 4 tri 5 poly 6 mpoly 7 line 8 polyline 9 arc 10 wedge
  float x0, y0, x1, y1;
  float alpha;
  bool finite;
};

class RecordGfx : public Gfx {
 public:
  static const int kMax = 400;
  RecordEntry log[kMax];
  int count = 0;
  int overflow = 0;
  void clear() { count = 0; overflow = 0; }
  void rect(float x, float y, float w, float h, Rgb c, float alpha = 1) override;
  void circle(float x, float y, float r, Rgb c, float alpha = 1) override;
  void ellipse(float x, float y, float rx, float ry, float rot, Rgb c, float alpha = 1) override;
  void rrect(float x, float y, float w, float h, float r, Rgb c, float alpha = 1) override;
  void tri(float x0, float y0, float x1, float y1, float x2, float y2, Rgb c, float alpha = 1) override;
  void poly(const float* pts, int nPts, Rgb c, float alpha = 1) override;
  void mpoly(const float* pts, int nPts, Rgb c, float alpha = 1) override;
  void line(float x0, float y0, float x1, float y1, float w, Rgb c, float alpha = 1) override;
  void polyline(const float* pts, int nPts, float w, Rgb c, float alpha = 1) override;
  void arc(float x, float y, float r, float a0, float a1, float w, Rgb c, float alpha = 1) override;
  void wedge(float x, float y, float r, float a0, float a1, Rgb c, float alpha = 1) override;

 private:
  void note(uint8_t kind, const float* pts, int nPts, float alpha, float pad);
};

}  // namespace spike
