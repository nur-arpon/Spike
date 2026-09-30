// spike_raster.cpp -- see spike_raster.h.
#include "spike_raster.h"
#include <stdlib.h>
#include <string.h>

#if defined(ESP_PLATFORM)
#include <esp_heap_caps.h>
static void* allocHot(size_t n) {  // inner-loop buffers: internal SRAM
  void* p = heap_caps_malloc(n, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  return p ? p : malloc(n);
}
static void* allocBig(size_t n) {  // large tables: PSRAM when present
  void* p = heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  return p ? p : malloc(n);
}
#else
static void* allocHot(size_t n) { return malloc(n); }
static void* allocBig(size_t n) { return malloc(n); }
#endif

namespace spike {

const char* tagName(Tag t) {
  static const char* const names[] = {"face", "fur", "eye", "eye-icon", "brow", "nose", "nose-wrinkle",
                                      "philtrum", "mouth", "cheek", "whisker", "ear", "accessory",
                                      "accessory-glasses", "decal", "decal-battery", "dim", "particle"};
  int i = (int)t;
  return (i >= 0 && i < (int)Tag::Count) ? names[i] : "?";
}

// ================================================================================================
// Surfaces
// ================================================================================================
void Rgb888Surface::fillRow(int y, int x, int n, Rgb c, float alpha) {
  if (y < clipY0 || y >= clipY1 || n <= 0) return;
  uint8_t* p = px_ + ((size_t)y * width + x) * 3;
  int r = rgbR(c), g = rgbG(c), b = rgbB(c);
  if (alpha >= 0.9995f) {
    for (int i = 0; i < n; i++, p += 3) { p[0] = (uint8_t)r; p[1] = (uint8_t)g; p[2] = (uint8_t)b; }
    return;
  }
  for (int i = 0; i < n; i++, p += 3) {
    p[0] = (uint8_t)roundChannel(p[0] + (r - p[0]) * alpha);
    p[1] = (uint8_t)roundChannel(p[1] + (g - p[1]) * alpha);
    p[2] = (uint8_t)roundChannel(p[2] + (b - p[2]) * alpha);
  }
}

void Rgb888Surface::blendRow(int y, int x, int n, const float* cov, Rgb c, float alpha) {
  if (y < clipY0 || y >= clipY1 || n <= 0) return;
  uint8_t* p = px_ + ((size_t)y * width + x) * 3;
  int r = rgbR(c), g = rgbG(c), b = rgbB(c);
  for (int i = 0; i < n; i++, p += 3) {
    float a = cov[i] * alpha;
    p[0] = (uint8_t)roundChannel(p[0] + (r - p[0]) * a);
    p[1] = (uint8_t)roundChannel(p[1] + (g - p[1]) * a);
    p[2] = (uint8_t)roundChannel(p[2] + (b - p[2]) * a);
  }
}

// RGB565 blend in 8-bit-per-channel space with an 8-bit alpha: expand, mix, pack.
static inline uint16_t blend565(uint16_t d, int r, int g, int b, int a8) {
  int dr = (d >> 11) & 31, dg = (d >> 5) & 63, db = d & 31;
  dr = (dr << 3) | (dr >> 2);
  dg = (dg << 2) | (dg >> 4);
  db = (db << 3) | (db >> 2);
  dr += ((r - dr) * a8 + 128) >> 8;
  dg += ((g - dg) * a8 + 128) >> 8;
  db += ((b - db) * a8 + 128) >> 8;
  return (uint16_t)(((dr & 0xF8) << 8) | ((dg & 0xFC) << 3) | (db >> 3));
}

void Rgb565Surface::fillRow(int y, int x, int n, Rgb c, float alpha) {
  if (y < clipY0 || y >= clipY1 || n <= 0) return;
  uint16_t* p = px_ + (size_t)(y - originY_) * width + x;
  if (alpha >= 0.9995f) {
    uint16_t v = to565(c);
    for (int i = 0; i < n; i++) p[i] = v;
    return;
  }
  int a8 = (int)(alpha * 256.0f + 0.5f);
  int r = rgbR(c), g = rgbG(c), b = rgbB(c);
  for (int i = 0; i < n; i++) p[i] = blend565(p[i], r, g, b, a8);
}

void Rgb565Surface::blendRow(int y, int x, int n, const float* cov, Rgb c, float alpha) {
  if (y < clipY0 || y >= clipY1 || n <= 0) return;
  uint16_t* p = px_ + (size_t)(y - originY_) * width + x;
  int r = rgbR(c), g = rgbG(c), b = rgbB(c);
  float k = alpha * 256.0f;
  for (int i = 0; i < n; i++) p[i] = blend565(p[i], r, g, b, (int)(cov[i] * k + 0.5f));
}

// ================================================================================================
// Path
// ================================================================================================
void Path::begin() {
  if (open) end(false);
  if (nContours >= kMaxContours) { open = false; return; }
  start[nContours] = nPts;
  open = true;
}

void Path::add(float x, float y) {
  if (!open) return;
  if (nPts >= kMaxPts) { dropped++; return; }
  xy[2 * nPts] = x;
  xy[2 * nPts + 1] = y;
  nPts++;
}

void Path::end(bool forcePositive) {
  if (!open) return;
  open = false;
  int s = start[nContours], n = nPts - s;
  if (n < 3) { nPts = s; return; }
  if (forcePositive) {
    float area = 0;
    for (int i = 0; i < n; i++) {
      int j = (i + 1) % n;
      area += xy[2 * (s + i)] * xy[2 * (s + j) + 1] - xy[2 * (s + j)] * xy[2 * (s + i) + 1];
    }
    if (area < 0) {
      for (int i = 0, j = n - 1; i < j; i++, j--) {
        float tx = xy[2 * (s + i)], ty = xy[2 * (s + i) + 1];
        xy[2 * (s + i)] = xy[2 * (s + j)]; xy[2 * (s + i) + 1] = xy[2 * (s + j) + 1];
        xy[2 * (s + j)] = tx; xy[2 * (s + j) + 1] = ty;
      }
    }
  }
  nContours++;
  start[nContours] = nPts;
}

// ================================================================================================
// Raster
// ================================================================================================
Raster::Raster() {
  edges_ = (Edge*)allocBig(sizeof(Edge) * kMaxEdges);
  order_ = (int*)allocBig(sizeof(int) * kMaxEdges);
  active_ = (int*)allocBig(sizeof(int) * kMaxEdges);
  acc_ = (float*)allocHot(sizeof(float) * (kMaxW + 4));
  cov_ = (float*)allocHot(sizeof(float) * (kMaxW + 4));
  if (!edges_ || !order_ || !active_ || !acc_ || !cov_) {
    free(edges_); free(order_); free(active_); free(acc_); free(cov_);
    edges_ = nullptr; order_ = nullptr; active_ = nullptr; acc_ = nullptr; cov_ = nullptr;
  }
}

Raster::~Raster() { free(edges_); free(order_); free(active_); free(acc_); free(cov_); }

// Signed-area contribution of edge e to pixel row y (font-rs accumulation, restricted to one row).
// acc index = device x - bx0; x values are clamped to [0, wAcc].
void Raster::accumulate(const Edge& e, int y, int bx0, float wAcc) {
  float fy = (float)y;
  float ya = e.y0 > fy ? e.y0 : fy;
  float yb = e.y1 < fy + 1.0f ? e.y1 : fy + 1.0f;
  if (yb <= ya) return;
  float x = e.x0 + (ya - e.y0) * e.dxdy - (float)bx0;
  float xnext = e.x0 + (yb - e.y0) * e.dxdy - (float)bx0;
  if (x < 0) x = 0; else if (x > wAcc) x = wAcc;
  if (xnext < 0) xnext = 0; else if (xnext > wAcc) xnext = wAcc;
  float d = (yb - ya) * e.dir;
  float x0 = x < xnext ? x : xnext, x1 = x < xnext ? xnext : x;
  float x0floor = floorf(x0);
  int x0i = (int)x0floor;
  float x1ceil = ceilf(x1);
  int x1i = (int)x1ceil;
  float* a = acc_;
  if (x1i <= x0i + 1) {
    float xmf = 0.5f * (x + xnext) - x0floor;
    a[x0i] += d - d * xmf;
    a[x0i + 1] += d * xmf;
  } else {
    float s = 1.0f / (x1 - x0);
    float x0f = x0 - x0floor;
    float a0 = 0.5f * s * (1.0f - x0f) * (1.0f - x0f);
    float x1f = x1 - x1ceil + 1.0f;
    float am = 0.5f * s * x1f * x1f;
    a[x0i] += d * a0;
    if (x1i == x0i + 2) {
      a[x0i + 1] += d * (1.0f - a0 - am);
    } else {
      float a1 = s * (1.5f - x0f);
      a[x0i + 1] += d * (a1 - a0);
      float ds = d * s;
      for (int xi = x0i + 2; xi < x1i - 1; xi++) a[xi] += ds;
      float a2 = a1 + (float)(x1i - x0i - 3) * s;
      a[x1i - 1] += d * (1.0f - a2 - am);
    }
    a[x1i] += d * am;
  }
}

void Raster::fill(const Path& p, Rgb c, float alpha, Surface& s, RasterStats* st) {
  if (!ok() || p.nContours == 0) return;
  // --- edges + bounds ---
  int ne = 0;
  float minx = 1e30f, maxx = -1e30f, miny = 1e30f, maxy = -1e30f;
  for (int ci = 0; ci < p.nContours; ci++) {
    int s0 = p.start[ci], n = p.start[ci + 1] - s0;
    for (int i = 0; i < n; i++) {
      float x0 = p.xy[2 * (s0 + i)], y0 = p.xy[2 * (s0 + i) + 1];
      int j = (i + 1) % n;
      float x1 = p.xy[2 * (s0 + j)], y1 = p.xy[2 * (s0 + j) + 1];
      if (!(x0 == x0) || !(y0 == y0)) return;  // NaN guard: skip the whole primitive
      if (x0 < minx) minx = x0; if (x0 > maxx) maxx = x0;
      if (y0 < miny) miny = y0; if (y0 > maxy) maxy = y0;
      if (y0 == y1 || ne >= kMaxEdges) continue;
      Edge& e = edges_[ne++];
      if (y0 < y1) { e.x0 = x0; e.y0 = y0; e.x1 = x1; e.y1 = y1; e.dir = 1.0f; }
      else { e.x0 = x1; e.y0 = y1; e.x1 = x0; e.y1 = y0; e.dir = -1.0f; }
      e.dxdy = (e.x1 - e.x0) / (e.y1 - e.y0);
    }
  }
  if (ne == 0) return;
  int ry0 = (int)floorf(miny), ry1 = (int)ceilf(maxy);
  if (ry0 < s.clipY0) ry0 = s.clipY0;
  if (ry1 > s.clipY1) ry1 = s.clipY1;
  int bx0 = (int)floorf(minx), bx1 = (int)ceilf(maxx);
  if (bx0 < 0) bx0 = 0;
  if (bx1 > s.width) bx1 = s.width;
  if (ry0 >= ry1 || bx0 >= bx1) return;
  int wpx = bx1 - bx0;
  if (wpx > kMaxW) return;
  float wAcc = (float)wpx;

  // --- sort edges by top y (insertion sort on indices; edge counts are small) ---
  for (int i = 0; i < ne; i++) order_[i] = i;
  for (int i = 1; i < ne; i++) {
    int k = order_[i];
    float ky = edges_[k].y0;
    int j = i - 1;
    while (j >= 0 && edges_[order_[j]].y0 > ky) { order_[j + 1] = order_[j]; j--; }
    order_[j + 1] = k;
  }

  // Active edge list (indices into edges_), fed from order_ as rows advance.
  int next = 0, nActive = 0;
  int* active = active_;
  for (int y = ry0; y < ry1; y++) {
    float fy = (float)y;
    int w = 0;  // retire edges that end at or above this row's top
    for (int i = 0; i < nActive; i++)
      if (edges_[active[i]].y1 > fy) active[w++] = active[i];
    nActive = w;
    while (next < ne && edges_[order_[next]].y0 < fy + 1.0f) {  // edges starting before this row's bottom
      int k = order_[next++];
      if (edges_[k].y1 > fy) active[nActive++] = k;
    }
    if (nActive == 0) continue;
    memset(acc_, 0, sizeof(float) * (wpx + 3));
    for (int i = 0; i < nActive; i++) accumulate(edges_[active[i]], y, bx0, wAcc);
    if (st) { st->edgeRows += nActive; st->rows++; st->scanned += (uint32_t)wpx; }
    // prefix sum -> coverage runs
    float sum = 0;
    int runStart = -1, runKind = 0;  // 1 solid, 2 partial
    for (int i = 0; i <= wpx; i++) {
      int kind = 0;
      float cv = 0;
      if (i < wpx) {
        sum += acc_[i];
        cv = sum < 0 ? -sum : sum;
        if (cv > 1.0f) cv = 1.0f;
        kind = cv >= 0.9985f ? 1 : (cv > 0.001f ? 2 : 0);
      }
      if (kind != runKind) {
        if (runKind == 1) {
          s.fillRow(y, bx0 + runStart, i - runStart, c, alpha);
          if (st) st->pixelsSolid += (uint32_t)(i - runStart);
        } else if (runKind == 2) {
          s.blendRow(y, bx0 + runStart, i - runStart, cov_ + runStart, c, alpha);
          if (st) st->pixelsBlended += (uint32_t)(i - runStart);
        }
        runKind = kind;
        runStart = i;
      }
      if (kind == 2) cov_[i] = cv;
    }
  }
}

// ================================================================================================
// VectorGfx
// ================================================================================================
static inline bool skipAlpha(float a) { return !(a > 0.003f); }

VectorGfx::VectorGfx() {
  path_.xy = (float*)allocBig(sizeof(float) * 2 * Path::kMaxPts);
  path_.start = (int*)allocBig(sizeof(int) * (Path::kMaxContours + 1));
  strokeTmp_ = (float*)allocBig(sizeof(float) * 2 * 512);
  if (!path_.xy || !path_.start || !strokeTmp_) {
    free(path_.xy); free(path_.start); free(strokeTmp_);
    path_.xy = nullptr; path_.start = nullptr; strokeTmp_ = nullptr;
  }
}

VectorGfx::~VectorGfx() { free(path_.xy); free(path_.start); free(strokeTmp_); }

int VectorGfx::segsFor(float r) {
  // chord error r * (1 - cos(pi / n)) <= ~0.05 px  ->  n ~ 10 * sqrt(r)
  int n = (int)ceilf(10.0f * sqrtf(r > 0 ? r : 0));
  if (n < 8) n = 8;
  if (n > 128) n = 128;
  return n;
}

void VectorGfx::flush(Rgb c, float alpha) {
  if (path_.open) path_.end(false);
  stats.primitives++;
  stats.pathPoints += (uint32_t)path_.nPts;
  stats.dropped += (uint32_t)path_.dropped;
  if (surf_ && path_.nContours > 0) raster_.fill(path_, c, alpha > 1 ? 1 : alpha, *surf_, &stats);
  path_.clear();
  path_.dropped = 0;
}

void VectorGfx::addPolyDevice(const float* pts, int nPts) {
  path_.begin();
  for (int i = 0; i < nPts; i++) {
    float x, y;
    m_.apply(pts[2 * i], pts[2 * i + 1], &x, &y);
    path_.add(x, y);
  }
  path_.end(false);
}

void VectorGfx::addCircleDevice(float cx, float cy, float r) {
  int n = segsFor(r);
  path_.begin();
  for (int i = 0; i < n; i++) {
    float a = TAU_F * (float)i / (float)n;
    path_.add(cx + cosf(a) * r, cy + sinf(a) * r);
  }
  path_.end(true);
}

// Pie slice (device space) from angle a0 sweeping `sweep` radians, positively wound.
void VectorGfx::addWedgeDevice(float cx, float cy, float r, float a0, float sweep) {
  int n = (int)ceilf((float)segsFor(r) * fabsf(sweep) / TAU_F);
  if (n < 1) n = 1;
  path_.begin();
  path_.add(cx, cy);
  for (int i = 0; i <= n; i++) {
    float a = a0 + sweep * (float)i / (float)n;
    path_.add(cx + cosf(a) * r, cy + sinf(a) * r);
  }
  path_.end(true);
}

// Stroke a device-space polyline with round joins and round caps, as a union of positively wound
// pieces: one quad per segment, a pie slice on the OUTER side of every turn, half discs at the two ends.
// The pieces only overlap inside the stroke (never along its silhouette), so the coverage clamp gives
// canvas-accurate anti-aliased edges. A closed polyline (first point == last) gets a join, not caps.
void VectorGfx::strokeDevice(const float* d, int n, float hw, bool closed) {
  (void)closed;
  // drop zero-length segments
  static float q[2 * 512];
  int m = 0;
  for (int i = 0; i < n && m < 512; i++) {
    float x = d[2 * i], y = d[2 * i + 1];
    if (m > 0) {
      float dx = x - q[2 * m - 2], dy = y - q[2 * m - 1];
      if (dx * dx + dy * dy < 1e-8f) continue;
    }
    q[2 * m] = x; q[2 * m + 1] = y; m++;
  }
  if (m == 1) { addCircleDevice(q[0], q[1], hw); return; }
  bool isClosed = false;
  if (m > 2) {
    float dx = q[0] - q[2 * m - 2], dy = q[1] - q[2 * m - 1];
    if (dx * dx + dy * dy < 1e-4f) { isClosed = true; m--; q[2 * m] = q[0]; q[2 * m + 1] = q[1]; }
  }
  int nSeg = m - 1 + (isClosed ? 1 : 0);
  for (int i = 0; i < nSeg; i++) {
    float x0 = q[2 * i], y0 = q[2 * i + 1], x1 = q[2 * i + 2], y1 = q[2 * i + 3];
    float dx = x1 - x0, dy = y1 - y0, len = sqrtf(dx * dx + dy * dy);
    float nx = -dy / len * hw, ny = dx / len * hw;
    path_.begin();
    path_.add(x0 + nx, y0 + ny);
    path_.add(x1 + nx, y1 + ny);
    path_.add(x1 - nx, y1 - ny);
    path_.add(x0 - nx, y0 - ny);
    path_.end(true);
  }
  (void)nSeg;
  auto segAngle = [&](int i) {  // direction of segment i -> i+1 (indices wrap for closed)
    int j = (i + 1) % (isClosed ? m : m + 1);
    return atan2f(q[2 * j + 1] - q[2 * i + 1], q[2 * j] - q[2 * i]);
  };
  // joins
  int firstJ = isClosed ? 0 : 1, lastJ = m - 2;
  for (int v = firstJ; v <= (isClosed ? m - 1 : lastJ); v++) {
    int a = (v - 1 + m) % m;
    float ta = segAngle(isClosed ? a : v - 1), tb = segAngle(v);
    float turn = tb - ta;
    while (turn > PI_F) turn -= TAU_F;
    while (turn <= -PI_F) turn += TAU_F;
    if (fabsf(turn) < 1e-4f) continue;
    float start = turn > 0 ? ta - PI_F / 2 : ta + PI_F / 2;
    addWedgeDevice(q[2 * v], q[2 * v + 1], hw, start, turn);
  }
  if (!isClosed) {
    float t0 = segAngle(0), t1 = segAngle(m - 2);
    addWedgeDevice(q[0], q[1], hw, t0 + PI_F / 2, PI_F);            // start cap (behind the start)
    addWedgeDevice(q[2 * (m - 1)], q[2 * (m - 1) + 1], hw, t1 - PI_F / 2, PI_F);  // end cap
  }
}

void VectorGfx::rect(float x, float y, float w, float h, Rgb c, float alpha) {
  if (skipAlpha(alpha)) return;
  if (m_.axisAligned() && surf_) {
    // Fast path (the background and the dim overlay): exact box coverage, no edge accumulation.
    float x0, y0, x1, y1;
    m_.apply(x, y, &x0, &y0);
    m_.apply(x + w, y + h, &x1, &y1);
    if (x0 > x1) { float tt = x0; x0 = x1; x1 = tt; }
    if (y0 > y1) { float tt = y0; y0 = y1; y1 = tt; }
    if (x0 < 0) x0 = 0;
    if (y0 < (float)surf_->clipY0) y0 = (float)surf_->clipY0;
    if (x1 > (float)surf_->width) x1 = (float)surf_->width;
    if (y1 > (float)surf_->clipY1) y1 = (float)surf_->clipY1;
    stats.primitives++;
    if (x0 >= x1 || y0 >= y1) return;
    int ix0 = (int)floorf(x0), ix1 = (int)ceilf(x1), iy0 = (int)floorf(y0), iy1 = (int)ceilf(y1);
    int n = ix1 - ix0;
    static float cov[1024];
    if (n > 1024) return;
    for (int yy = iy0; yy < iy1; yy++) {
      float cy = fminf((float)yy + 1, y1) - fmaxf((float)yy, y0);
      bool fullRow = cy >= 0.9985f;
      int a = ix0, b = ix1;  // solid interior columns [a, b)
      if (x0 > (float)ix0) a = ix0 + 1;
      if (x1 < (float)ix1) b = ix1 - 1;
      if (fullRow && b > a) {
        if (a > ix0) { cov[0] = (float)a - x0; surf_->blendRow(yy, ix0, 1, cov, c, alpha); }
        surf_->fillRow(yy, a, b - a, c, alpha);
        if (b < ix1) { cov[0] = x1 - (float)b; surf_->blendRow(yy, b, 1, cov, c, alpha); }
        stats.pixelsSolid += (uint32_t)(b - a);
      } else {
        for (int xx = ix0; xx < ix1; xx++)
          cov[xx - ix0] = cy * (fminf((float)xx + 1, x1) - fmaxf((float)xx, x0));
        surf_->blendRow(yy, ix0, n, cov, c, alpha);
        stats.pixelsBlended += (uint32_t)n;
      }
    }
    return;
  }
  float pts[8] = {x, y, x + w, y, x + w, y + h, x, y + h};
  addPolyDevice(pts, 4);
  flush(c, alpha);
}

void VectorGfx::circle(float x, float y, float r, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !(r > 0.05f)) return;
  ellipse(x, y, r, r, 0, c, alpha);
}

void VectorGfx::ellipse(float x, float y, float rx, float ry, float rot, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !(rx > 0.05f) || !(ry > 0.05f)) return;
  float sc = m_.scaleFactor();
  int n = segsFor((rx > ry ? rx : ry) * sc);
  float cr = cosf(rot), sr = sinf(rot);
  path_.begin();
  for (int i = 0; i < n; i++) {
    float a = TAU_F * (float)i / (float)n;
    float lx = cosf(a) * rx, ly = sinf(a) * ry;
    float px = x + lx * cr - ly * sr, py = y + lx * sr + ly * cr, dx, dy;
    m_.apply(px, py, &dx, &dy);
    path_.add(dx, dy);
  }
  path_.end(false);
  flush(c, alpha);
}

void VectorGfx::rrect(float x, float y, float w, float h, float r, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !(w > 0.05f) || !(h > 0.05f)) return;
  if (r > w / 2) r = w / 2;
  if (r > h / 2) r = h / 2;
  if (r < 0) r = 0;
  float sc = m_.scaleFactor();
  int q = segsFor(r * sc) / 4;
  if (q < 2) q = 2;
  path_.begin();
  const float cxs[4] = {x + w - r, x + w - r, x + r, x + r};
  const float cys[4] = {y + r, y + h - r, y + h - r, y + r};
  const float a0s[4] = {-PI_F / 2, 0, PI_F / 2, PI_F};
  for (int k = 0; k < 4; k++) {
    for (int i = 0; i <= q; i++) {
      float a = a0s[k] + (PI_F / 2) * (float)i / (float)q;
      float dx, dy;
      m_.apply(cxs[k] + cosf(a) * r, cys[k] + sinf(a) * r, &dx, &dy);
      path_.add(dx, dy);
      if (r <= 0) break;
    }
  }
  path_.end(false);
  flush(c, alpha);
}

void VectorGfx::tri(float x0, float y0, float x1, float y1, float x2, float y2, Rgb c, float alpha) {
  if (skipAlpha(alpha)) return;
  float pts[6] = {x0, y0, x1, y1, x2, y2};
  addPolyDevice(pts, 3);
  flush(c, alpha);
}

void VectorGfx::poly(const float* pts, int nPts, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !pts || nPts < 3) return;
  addPolyDevice(pts, nPts);
  flush(c, alpha);
}

void VectorGfx::mpoly(const float* pts, int nPts, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !pts || nPts < 3) return;
  addPolyDevice(pts, nPts);
  flush(c, alpha);
}

void VectorGfx::line(float x0, float y0, float x1, float y1, float w, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !(w > 0.05f)) return;
  float pts[4] = {x0, y0, x1, y1};
  polyline(pts, 2, w, c, alpha);
}

void VectorGfx::polyline(const float* pts, int nPts, float w, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !pts || nPts < 2 || !(w > 0.05f)) return;
  if (nPts > 512) nPts = 512;
  for (int i = 0; i < nPts; i++) m_.apply(pts[2 * i], pts[2 * i + 1], &strokeTmp_[2 * i], &strokeTmp_[2 * i + 1]);
  float lw = w < 0.5f ? 0.5f : w;  // canvas: lineWidth = max(0.5, w) in user space
  strokeDevice(strokeTmp_, nPts, 0.5f * lw * m_.scaleFactor(), false);
  flush(c, alpha);
}

void VectorGfx::arc(float x, float y, float r, float a0, float a1, float w, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !(r > 0.05f) || !(w > 0.05f)) return;
  float span = a1 - a0;
  if (span > TAU_F) span = TAU_F;
  if (span < -TAU_F) span = -TAU_F;
  float sc = m_.scaleFactor();
  int n = (int)ceilf((float)segsFor(r * sc) * fabsf(span) / TAU_F);
  if (n < 2) n = 2;
  if (n > 511) n = 511;
  for (int i = 0; i <= n; i++) {
    float a = a0 + span * (float)i / (float)n;
    m_.apply(x + cosf(a) * r, y + sinf(a) * r, &strokeTmp_[2 * i], &strokeTmp_[2 * i + 1]);
  }
  float lw = w < 0.5f ? 0.5f : w;
  strokeDevice(strokeTmp_, n + 1, 0.5f * lw * sc, false);
  flush(c, alpha);
}

void VectorGfx::wedge(float x, float y, float r, float a0, float a1, Rgb c, float alpha) {
  if (skipAlpha(alpha) || !(r > 0.05f)) return;
  float span = a1 - a0;
  if (span > TAU_F) span = TAU_F;
  if (span < -TAU_F) span = -TAU_F;
  float sc = m_.scaleFactor();
  int n = (int)ceilf((float)segsFor(r * sc) * fabsf(span) / TAU_F);
  if (n < 2) n = 2;
  path_.begin();
  float dx, dy;
  m_.apply(x, y, &dx, &dy);
  path_.add(dx, dy);
  for (int i = 0; i <= n; i++) {
    float a = a0 + span * (float)i / (float)n;
    m_.apply(x + cosf(a) * r, y + sinf(a) * r, &dx, &dy);
    path_.add(dx, dy);
  }
  path_.end(false);
  flush(c, alpha);
}

// ================================================================================================
// RecordGfx
// ================================================================================================
void RecordGfx::note(uint8_t kind, const float* pts, int nPts, float alpha, float pad) {
  if (count >= kMax) { overflow++; return; }
  RecordEntry& e = log[count++];
  e.tag = tag_;
  e.kind = kind;
  e.alpha = alpha;
  e.finite = (alpha == alpha);
  float mnx = 1e30f, mny = 1e30f, mxx = -1e30f, mxy = -1e30f;
  for (int i = 0; i < nPts; i++) {
    float x, y;
    m_.apply(pts[2 * i], pts[2 * i + 1], &x, &y);
    if (!(x == x) || !(y == y) || fabsf(x) > 1e20f || fabsf(y) > 1e20f) e.finite = false;
    if (x < mnx) mnx = x; if (x > mxx) mxx = x;
    if (y < mny) mny = y; if (y > mxy) mxy = y;
  }
  pad *= m_.scaleFactor();
  e.x0 = mnx - pad; e.y0 = mny - pad; e.x1 = mxx + pad; e.y1 = mxy + pad;
}

void RecordGfx::rect(float x, float y, float w, float h, Rgb, float alpha) {
  if (skipAlpha(alpha)) return;
  float p[4] = {x, y, x + w, y + h};
  note(0, p, 2, alpha, 0);
}
void RecordGfx::circle(float x, float y, float r, Rgb, float alpha) {
  if (skipAlpha(alpha) || !(r > 0.05f)) return;
  float p[8] = {x - r, y - r, x + r, y + r, x - r, y + r, x + r, y - r};
  note(1, p, 4, alpha, 0);
}
void RecordGfx::ellipse(float x, float y, float rx, float ry, float rot, Rgb, float alpha) {
  if (skipAlpha(alpha) || !(rx > 0.05f) || !(ry > 0.05f)) return;
  float p[24];
  float cr = cosf(rot), sr = sinf(rot);
  for (int i = 0; i < 12; i++) {
    float a = TAU_F * i / 12.0f, lx = cosf(a) * rx, ly = sinf(a) * ry;
    p[2 * i] = x + lx * cr - ly * sr;
    p[2 * i + 1] = y + lx * sr + ly * cr;
  }
  note(2, p, 12, alpha, 0);
}
void RecordGfx::rrect(float x, float y, float w, float h, float, Rgb, float alpha) {
  if (skipAlpha(alpha) || !(w > 0.05f) || !(h > 0.05f)) return;
  float p[8] = {x, y, x + w, y + h, x, y + h, x + w, y};
  note(3, p, 4, alpha, 0);
}
void RecordGfx::tri(float x0, float y0, float x1, float y1, float x2, float y2, Rgb, float alpha) {
  if (skipAlpha(alpha)) return;
  float p[6] = {x0, y0, x1, y1, x2, y2};
  note(4, p, 3, alpha, 0);
}
void RecordGfx::poly(const float* pts, int nPts, Rgb, float alpha) {
  if (skipAlpha(alpha) || !pts || nPts < 3) return;
  note(5, pts, nPts, alpha, 0);
}
void RecordGfx::mpoly(const float* pts, int nPts, Rgb, float alpha) {
  if (skipAlpha(alpha) || !pts || nPts < 3) return;
  note(6, pts, nPts, alpha, 0);
}
void RecordGfx::line(float x0, float y0, float x1, float y1, float w, Rgb, float alpha) {
  if (skipAlpha(alpha) || !(w > 0.05f)) return;
  float p[4] = {x0, y0, x1, y1};
  note(7, p, 2, alpha, w / 2);
}
void RecordGfx::polyline(const float* pts, int nPts, float w, Rgb, float alpha) {
  if (skipAlpha(alpha) || !pts || nPts < 2 || !(w > 0.05f)) return;
  note(8, pts, nPts, alpha, w / 2);
}
void RecordGfx::arc(float x, float y, float r, float a0, float a1, float w, Rgb, float alpha) {
  if (skipAlpha(alpha) || !(r > 0.05f) || !(w > 0.05f)) return;
  float p[18];
  for (int i = 0; i <= 8; i++) {
    float a = a0 + (a1 - a0) * i / 8.0f;
    p[2 * i] = x + cosf(a) * r;
    p[2 * i + 1] = y + sinf(a) * r;
  }
  note(9, p, 9, alpha, w / 2);
}
void RecordGfx::wedge(float x, float y, float r, float a0, float a1, Rgb, float alpha) {
  if (skipAlpha(alpha) || !(r > 0.05f)) return;
  float p[20];
  p[0] = x; p[1] = y;
  for (int i = 0; i <= 8; i++) {
    float a = a0 + (a1 - a0) * i / 8.0f;
    p[2 * i + 2] = x + cosf(a) * r;
    p[2 * i + 3] = y + sinf(a) * r;
  }
  note(10, p, 10, alpha, 0);
}

}  // namespace spike
