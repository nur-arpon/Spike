// face_pc.cpp -- the PC backend of the shared face core: renders faces to PNG / raw RGB with the SAME
// rasteriser the ESP32-S3 uses, runs the table self-test, and measures the frame cost.
//
//   face_pc selftest
//   face_pc png <preset> <mood> <dog|cat> <t> <out.png>
//   face_pc cases <cases.txt> <outdir> [repeat]   (golden-image test input written by test/js_cases.js)
//   face_pc link <ble_vectors.txt>                 (protocol v1.3 link tests: pc/link_test.cpp)
//   face_pc passkey <out.png> [passkey] [remaining] (the BLE pairing passkey overlay)
//
// Build: pc/build.bat (MSVC) -- see DESIGN.md "PC build".
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <chrono>
#include <string>
#include <vector>
#include <algorithm>

#include "spike_face_draw.h"
#include "spike_moods.h"
#include "spike_raster.h"
#include "spike_recipe.h"
#include "spike_extras.h"
#include "png_write.h"
#include "spike_life.h"
#include "spike_synth.h"
#include "spike_actions.h"
#include "spike_body.h"

using namespace spike;

static const int W = 480, H = 272;

static int fails = 0;
#define CHECK(cond, ...)                         \
  do {                                           \
    if (!(cond)) {                               \
      fails++;                                   \
      printf("FAIL %s:%d: ", __FILE__, __LINE__); \
      printf(__VA_ARGS__);                       \
      printf("\n");                              \
    }                                            \
  } while (0)

static int selftest() {
  // slot enums must match the generated option names (append-only catalogue)
  CHECK(strcmp(kSlotOptions[1][PAT_CALICO], "calico") == 0, "pattern enum");
  CHECK(strcmp(kSlotOptions[1][PAT_TUX], "tux") == 0, "pattern enum tux");
  CHECK(strcmp(kSlotOptions[3][EYE_GLOW], "glow") == 0, "eyeStyle enum");
  CHECK(strcmp(kSlotOptions[4][SHAPE_DROOP], "droop") == 0, "eyeShape enum");
  CHECK(strcmp(kSlotOptions[5][LASH_FULL], "full") == 0, "lashes enum");
  CHECK(strcmp(kSlotOptions[6][BROW_BOLD], "bold") == 0, "brows enum");
  CHECK(strcmp(kSlotOptions[7][NOSE_BEAN], "bean") == 0, "nose enum");
  CHECK(strcmp(kSlotOptions[8][MOUTH_SIMPLE], "simple") == 0, "mouth enum");
  CHECK(strcmp(kSlotOptions[9][EARS_NONE], "none") == 0, "ears enum");
  CHECK(strcmp(kSlotOptions[9][EARS_FOLD], "fold") == 0, "ears enum fold");
  CHECK(strcmp(kSlotOptions[10][WHISK_LONG], "long") == 0, "whiskers enum");
  CHECK(strcmp(kSlotOptions[11][ACC_FLOWER], "flower") == 0, "accessory enum");
  CHECK(strcmp(kSlotOptions[13][SIDE_RIGHT], "right") == 0, "patternSide enum");
  CHECK(kSlotOptionCount[0] == 2 && kSlotOptionCount[9] == 7, "slot counts");
  // share codes round-trip and match recipe.js toCode() byte for byte
  for (int i = 0; i < kNumPresets; i++) {
    char code[160];
    toCode(kPresets[i].recipe, code, sizeof code);
    CHECK(strcmp(code, kPresets[i].code) == 0, "toCode(%s) = %s, JS %s", kPresets[i].id, code, kPresets[i].code);
    Recipe back;
    CHECK(fromCode(kPresets[i].code, &back), "fromCode(%s)", kPresets[i].id);
    char code2[160];
    toCode(back, code2, sizeof code2);
    CHECK(strcmp(code2, kPresets[i].code) == 0, "round trip %s", kPresets[i].id);
  }
  Recipe junk;
  CHECK(!fromCode("SPK1-zz-00-00", &junk), "bad code accepted");
  CHECK(!fromCode("hello", &junk), "bad code accepted 2");
  CHECK(moodIndex("neutral") == 0 && moodIndex("hungry") == kNumMoods - 1 && moodIndex("nope") == -1, "mood index");
  CHECK(kNumMoods == 43, "43 moods");
  // springs: a step to 10 on the head group overshoots to ~11.95 (DESIGN.md 4)
  {
    Springs s;
    FaceState a = faceDefaults();
    s.init(a);
    FaceState b = a;
    b.tilt = 10;
    s.setTarget(b);
    float peak = 0;
    for (int i = 0; i < 300; i++) { s.step(1.0f / 60.0f); if (s.current.tilt > peak) peak = s.current.tilt; }
    CHECK(fabsf(peak - 11.95f) < 0.08f, "tilt overshoot %.3f (expected 11.95)", peak);
  }
  // raster sanity: a full-screen rect covers every pixel exactly once
  {
    std::vector<uint8_t> px((size_t)W * H * 3, 0);
    Rgb888Surface surf(px.data(), W, H);
    VectorGfx G;
    CHECK(G.ok(), "VectorGfx alloc");
    G.setSurface(&surf);
    G.rect(0, 0, W, H, 0x336699, 1);
    bool allOk = true;
    for (size_t i = 0; i < px.size(); i += 3)
      if (px[i] != 0x33 || px[i + 1] != 0x66 || px[i + 2] != 0x99) { allOk = false; break; }
    CHECK(allOk, "full rect");
    // a circle's covered area ~ pi r^2
    std::fill(px.begin(), px.end(), 0);
    G.circle(240, 136, 50, 0xFFFFFF, 1);
    double sum = 0;
    for (size_t i = 0; i < px.size(); i += 3) sum += px[i] / 255.0;
    CHECK(fabs(sum - 3.14159265 * 2500) < 20, "circle area %.1f", sum);
    // a stroked polyline with overlapping joints must not double-blend (union)
    std::fill(px.begin(), px.end(), 0);
    float pl[8] = {100, 100, 200, 100, 200, 110, 100, 110};
    G.polyline(pl, 4, 12, 0xFFFFFF, 0.5f);
    int maxv = 0;
    for (size_t i = 0; i < px.size(); i += 3) if (px[i] > maxv) maxv = px[i];
    CHECK(maxv <= 129, "stroke union max %d (alpha 0.5 -> 128)", maxv);
  }
  // the DEVICE surface (RGB565, the ESP32 frame buffer) gives the same face as the RGB888 PC surface
  {
    std::vector<uint8_t> px((size_t)W * H * 3, 0);
    std::vector<uint16_t> px565((size_t)W * H, 0);
    Rgb888Surface s888(px.data(), W, H);
    Rgb565Surface s565(px565.data(), W, H);
    static VectorGfx G;
    FaceState p = moodTarget(moodIndex("joy"), false);
    G.setSurface(&s888);
    drawFace(G, p, findPreset("classic")->recipe, 0.6f);
    G.setSurface(&s565);
    drawFace(G, p, findPreset("classic")->recipe, 0.6f);
    double sum = 0;
    int mx = 0;
    for (int i = 0; i < W * H; i++) {
      uint16_t v = px565[i];
      int r = ((v >> 11) & 31) * 255 / 31, g = ((v >> 5) & 63) * 255 / 63, b = (v & 31) * 255 / 31;
      int d = abs(r - px[3 * i]);
      d = std::max(d, abs(g - px[3 * i + 1]));
      d = std::max(d, abs(b - px[3 * i + 2]));
      sum += d;
      mx = std::max(mx, d);
    }
    CHECK(sum / (W * H) < 4.0 && mx <= 16, "RGB565 device path vs RGB888: mean %.2f max %d", sum / (W * H), mx);
    printf("rgb565 device path vs rgb888: mean %.2f max %d levels\n", sum / (W * H), mx);
    // strip rendering (a clip window) paints exactly the same rows as the full frame
    std::vector<uint16_t> strip((size_t)W * 34, 0);
    Rgb565Surface sStrip(strip.data(), W, H, 102, 34);
    G.setSurface(&sStrip);
    drawFace(G, p, findPreset("classic")->recipe, 0.6f);
    CHECK(memcmp(strip.data(), px565.data() + (size_t)102 * W, strip.size() * 2) == 0, "strip render == full frame rows");
  }
  printf("selftest: %s (%d failure%s)\n", fails ? "FAILED" : "ok", fails, fails == 1 ? "" : "s");
  return fails ? 1 : 0;
}

static bool renderToRgb(const FaceState& p, const Recipe& r, float t, std::vector<uint8_t>& px, RasterStats* st,
                        const ParticleSystem* ps = nullptr, bool light = false) {
  px.assign((size_t)W * H * 3, 0);
  Rgb888Surface surf(px.data(), W, H);
  static VectorGfx G;
  if (!G.ok()) return false;
  G.setSurface(&surf);
  G.stats.reset();
  drawFace(G, p, r, t);
  if (ps && ps->count) ps->draw(G, t, light);
  if (st) *st = G.stats;
  return true;
}

static int cmdPng(int argc, char** argv) {
  if (argc < 7) { printf("usage: face_pc png <preset> <mood> <dog|cat> <t> <out.png>\n"); return 2; }
  const PresetDef* pd = findPreset(argv[2]);
  int mi = moodIndex(argv[3]);
  if (!pd || mi < 0) { printf("unknown preset or mood\n"); return 2; }
  bool cat = strcmp(argv[4], "cat") == 0;
  FaceState p = moodTarget(mi, cat);
  std::vector<uint8_t> px;
  if (!renderToRgb(p, pd->recipe, (float)atof(argv[5]), px, nullptr)) return 3;
  if (!pngw::writeRgb(argv[6], px.data(), W, H)) { printf("cannot write %s\n", argv[6]); return 3; }
  printf("wrote %s\n", argv[6]);
  return 0;
}

// ---- golden-image cases ---------------------------------------------------------------------
struct Case {
  std::string name;
  float t;
  int moodIdx;
  bool cat;
  Recipe r;
  FaceState p;
  bool light = false;
  ParticleSystem ps;
};

static bool parseCase(char* line, Case& c) {
  char* tok = strtok(line, " \t\r\n");
  if (!tok || tok[0] == '#') return false;
  c.name = tok;
  auto next = [&]() { return strtok(nullptr, " \t\r\n"); };
  char* s;
  if (!(s = next())) return false; c.t = (float)atof(s);
  if (!(s = next())) return false; c.moodIdx = atoi(s);
  if (!(s = next())) return false; c.cat = atoi(s) != 0;
  c.r = baseRecipe();
  strcpy(c.r.name, "case");
  for (int i = 0; i < kNumSlots; i++) { if (!(s = next())) return false; c.r.slot(i) = (uint8_t)atoi(s); }
  for (int i = 0; i < kNumColors; i++) { if (!(s = next())) return false; Rgb v; if (!parseHex(s, &v)) return false; c.r.color(i) = v; }
  for (int i = 0; i < kNumNumbers; i++) { if (!(s = next())) return false; c.r.number(i) = (float)atof(s); }
  if (!(s = next())) return false;
  c.p = faceDefaults();
  c.p.icon = strcmp(s, "-") == 0 ? Icon::None : iconFromName(s);
  for (int i = 0; i < F_COUNT; i++) { if (!(s = next())) return false; c.p[i] = (float)atof(s); }
  c.ps.clear();
  if (!(s = next())) return true;  // older files: no particle columns
  c.light = atoi(s) != 0;
  if (!(s = next())) return false;
  int np = atoi(s);
  for (int k = 0; k < np; k++) {
    float v[13];
    char* ty = next();
    if (!ty) return false;
    for (int j = 1; j < 13; j++) { if (!(s = next())) return false; v[j] = (float)atof(s); }
    if (c.ps.count >= ParticleSystem::kMax) continue;
    ParticleInst& q = c.ps.list[c.ps.count++];
    memset(&q, 0, sizeof q);
    q.type = particleFromName(ty);
    q.x = v[1]; q.y = v[2]; q.age = v[3]; q.life = v[4]; q.rot = v[5]; q.scale = v[6]; q.seed = v[7];
    q.orbit = v[8] != 0; q.ox = v[9]; q.oy = v[10]; q.orbitR = v[11]; q.orbitSpeed = v[12];
  }
  return true;
}

static int cmdCases(int argc, char** argv) {
  if (argc < 4) { printf("usage: face_pc cases <cases.txt> <outdir> [repeat]\n"); return 2; }
  int repeat = argc > 4 ? atoi(argv[4]) : 5;
  if (repeat < 1) repeat = 1;
  FILE* f = fopen(argv[2], "r");
  if (!f) { printf("cannot open %s\n", argv[2]); return 2; }
  std::string outdir = argv[3];
  std::string statsPath = outdir + "/stats.csv";
  FILE* sf = fopen(statsPath.c_str(), "w");
  if (sf) fprintf(sf, "name,ms,primitives,path_points,edge_rows,rows,scanned,px_solid,px_blend,dropped\n");
  static char line[1 << 17];
  int n = 0, targetMismatch = 0;
  double msMax = 0, msSum = 0;
  RasterStats worst;
  uint64_t sumScan = 0, sumPts = 0; uint32_t maxScan = 0, maxPts = 0;
  uint64_t sumBlend = 0, sumSolid = 0, sumEdgeRows = 0, sumPrims = 0;
  uint32_t maxBlend = 0, maxSolid = 0, maxEdgeRows = 0, maxPrims = 0;
  std::vector<uint8_t> px;
  static Case c;
  while (fgets(line, sizeof line, f)) {
    if (!parseCase(line, c)) continue;
    if (c.moodIdx >= 0) {  // the generated mood table must give exactly the JS target
      FaceState mine = moodTarget(c.moodIdx, c.cat);
      for (int i = 0; i < F_COUNT; i++)
        if (fabsf(mine[i] - c.p[i]) > 1e-4f) {
          if (targetMismatch < 20) printf("target mismatch %s field %s: C++ %g JS %g\n", c.name.c_str(), kFields[i].name, mine[i], c.p[i]);
          targetMismatch++;
        }
      if (mine.icon != c.p.icon) { targetMismatch++; printf("icon mismatch %s\n", c.name.c_str()); }
    }
    RasterStats st;
    auto t0 = std::chrono::high_resolution_clock::now();
    for (int k = 0; k < repeat; k++) renderToRgb(c.p, c.r, c.t, px, &st, &c.ps, c.light);
    auto t1 = std::chrono::high_resolution_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count() / repeat;
    msSum += ms;
    if (ms > msMax) msMax = ms;
    sumScan += st.scanned; sumPts += st.pathPoints; if (st.scanned > maxScan) maxScan = st.scanned; if (st.pathPoints > maxPts) maxPts = st.pathPoints;
    sumBlend += st.pixelsBlended; sumSolid += st.pixelsSolid; sumEdgeRows += st.edgeRows; sumPrims += st.primitives;
    if (st.pixelsBlended > maxBlend) maxBlend = st.pixelsBlended;
    if (st.pixelsSolid > maxSolid) maxSolid = st.pixelsSolid;
    if (st.edgeRows > maxEdgeRows) maxEdgeRows = st.edgeRows;
    if (st.primitives > maxPrims) maxPrims = st.primitives;
    if (st.dropped) printf("WARNING %s dropped %u path points\n", c.name.c_str(), st.dropped);
    if (sf) fprintf(sf, "%s,%.3f,%u,%u,%u,%u,%u,%u,%u,%u\n", c.name.c_str(), ms, st.primitives, st.pathPoints, st.edgeRows,
                    st.rows, st.scanned, st.pixelsSolid, st.pixelsBlended, st.dropped);
    std::string path = outdir + "/" + c.name + ".rgb";
    FILE* o = fopen(path.c_str(), "wb");
    if (o) { fwrite(px.data(), 1, px.size(), o); fclose(o); }
    n++;
  }
  fclose(f);
  if (sf) fclose(sf);
  if (n == 0) { printf("no cases\n"); return 2; }
  printf("rendered %d cases; mood-target mismatches: %d\n", n, targetMismatch);
  printf("frame cost on this PC: mean %.3f ms, max %.3f ms\n", msSum / n, msMax);
  printf("per frame: primitives mean %.1f max %u | solid px mean %.0f max %u | blended px mean %.0f max %u | "
         "edge-rows mean %.0f max %u\n",
         (double)sumPrims / n, maxPrims, (double)sumSolid / n, maxSolid, (double)sumBlend / n, maxBlend,
         (double)sumEdgeRows / n, maxEdgeRows);
  printf("per frame: scanned cells mean %.0f max %u | path points mean %.0f max %u\n", (double)sumScan / n, maxScan,
         (double)sumPts / n, maxPts);
  return targetMismatch ? 1 : 0;
}


// ---- behaviour trace (test/life_trace.js) -----------------------------------------------------
static int cmdLife(int argc, char** argv) {
  if (argc < 4) { printf("usage: face_pc life <life_script.txt> <out.txt>\n"); return 2; }
  FILE* f = fopen(argv[2], "r");
  if (!f) { printf("cannot open %s\n", argv[2]); return 2; }
  struct Cmd { double t; char text[96]; };
  std::vector<Cmd> script;
  char line[256];
  while (fgets(line, sizeof line, f)) {
    Cmd c;
    int off = 0;
    if (sscanf(line, "%lf %n", &c.t, &off) < 1) continue;
    strncpy(c.text, line + off, sizeof c.text - 1);
    c.text[sizeof c.text - 1] = 0;
    c.text[strcspn(c.text, "\r\n")] = 0;
    script.push_back(c);
  }
  fclose(f);
  Life e(nullptr, 7);
  FILE* o = fopen(argv[3], "w");
  if (!o) return 3;
  const double DT = 1.0 / 60.0;
  size_t si = 0;
  int n = (int)lround(90.0 / (1.0 / 60.0));
  for (int i = 1; i <= n; i++) {
    while (si < script.size() && script[si].t <= e.time() + 1e-9) {
      char a[32] = {0}, b[32] = {0}, c3[32] = {0};
      sscanf(script[si].text, "%31s %31s %31s", a, b, c3);
      if (!strcmp(a, "look")) e.setLook((float)atof(b), (float)atof(c3));
      else if (!strcmp(a, "pat")) e.pat();
      else if (!strcmp(a, "boop")) e.boop();
      else if (!strcmp(a, "mood")) e.setMood(moodIndex(b));
      else if (!strcmp(a, "action")) e.playAction(b);
      else if (!strcmp(a, "mode")) e.setMode(!strcmp(b, "cat"));
      else if (!strcmp(a, "battery")) e.setBattery((float)atof(b));
      else if (!strcmp(a, "comfort")) e.comfort(b);
      else if (!strcmp(a, "listening")) e.setListening(!strcmp(b, "wake") ? Listen::Wake : !strcmp(b, "listening") ? Listen::Listening
                                                       : !strcmp(b, "thinking") ? Listen::Thinking : Listen::Idle);
      else if (!strcmp(a, "alarm")) e.alarm(!strcmp(b, "ringing") ? AlarmState::Ringing : !strcmp(b, "snoozed") ? AlarmState::Snoozed : AlarmState::Stopped, atoi(c3));
      else if (!strcmp(a, "event")) {
        if (!strcmp(b, "comeHome")) e.comeHome();
        else if (!strcmp(b, "fellOver")) e.fellOver();
        else if (!strcmp(b, "ownerLooksSad")) e.ownerLooksSad();
        else if (!strcmp(b, "sayHi")) e.sayHi();
        else if (!strcmp(b, "pickedUp")) e.pickedUp();
        else if (!strcmp(b, "ignoredNudge")) e.ignoredNudge();
      }
      si++;
    }
    e.update(DT);
    if (i % 6 == 0) {
      FaceState p = e.faceParams();
      fprintf(o, "%.4f %d %d %s", e.time(), e.mood(), e.particles().count, p.icon == Icon::None ? "-" : iconName(p.icon));
      for (int k = 0; k < F_COUNT; k++) fprintf(o, " %.5f", p[k]);
      fprintf(o, "\n");
    }
  }
  fclose(o);
  printf("life: wrote %s\n", argv[3]);
  return 0;
}

// ---- synth: every built-in sound to a WAV (listen to them) + sanity numbers ---------------------
static void writeWav(const char* path, const int16_t* pcm, int n, int rate) {
  FILE* f = fopen(path, "wb");
  if (!f) return;
  auto u32 = [&](uint32_t v) { fwrite(&v, 4, 1, f); };
  auto u16 = [&](uint16_t v) { fwrite(&v, 2, 1, f); };
  fwrite("RIFF", 1, 4, f); u32(36 + n * 2); fwrite("WAVEfmt ", 1, 8, f); u32(16); u16(1); u16(1); u32(rate);
  u32(rate * 2); u16(2); u16(16); fwrite("data", 1, 4, f); u32(n * 2); fwrite(pcm, 2, n, f);
  fclose(f);
}

static int cmdSounds(int argc, char** argv) {
  const char* dir = argc > 2 ? argv[2] : ".";
  const int rate = 22050;
  int bad = 0;
  for (int si = 0; si < (int)Sound::Count; si++) {
    Synth syn(rate);
    syn.play((Sound)si, si == (int)Sound::Sniffs ? 3.0f : (si == (int)Sound::AlarmBark ? 2.0f : 0.0f));
    std::vector<int16_t> pcm;
    int16_t buf[256];
    int guard = 0;
    while (syn.busy() && guard++ < 1000) {
      memset(buf, 0, sizeof buf);
      syn.render(buf, 256);
      pcm.insert(pcm.end(), buf, buf + 256);
    }
    int peak = 0;
    for (int16_t v : pcm) peak = abs(v) > peak ? abs(v) : peak;
    bool ok = !pcm.empty() && peak > 300 && guard < 1000;
    if (!ok) bad++;
    printf("%-10s %5.2f s  peak %5d %s\n", soundName((Sound)si), pcm.size() / (double)rate, peak, ok ? "" : "  <-- CHECK");
    std::string path = std::string(dir) + "/sound_" + soundName((Sound)si) + ".wav";
    writeWav(path.c_str(), pcm.data(), (int)pcm.size(), rate);
  }
  printf("sounds: %s\n", bad ? "SOME SILENT OR ENDLESS" : "all produce audio and end");
  return bad ? 1 : 0;
}

// ---- body: limits, sequences, safety reflexes ---------------------------------------------------
static int cmdBody() {
  using namespace spike::body;
  fails = 0;
  // joint limits (CAD v3.1 README)
  { float h = 30, k = 50; limitLeg(LEG_BL, &h, &k); CHECK(h == 30 && k == 45, "rear rule: %g %g", h, k); }
  { float h = 25, k = 50; limitLeg(LEG_BR, &h, &k); CHECK(k == 50, "rear rule starts ABOVE +25: %g", k); }
  { float h = 30, k = 50; limitLeg(LEG_FL, &h, &k); CHECK(k == 50, "front legs free in +-30 x +-50"); }
  { float h = 99, k = -99; limitLeg(LEG_FR, &h, &k); CHECK(h == 30 && k == -50, "range clamp"); }
  // every action label (actions.js) and the two comfort actions have a motion sequence
  int na;
  const ActionDef* T = actionTable(&na);
  for (int i = 0; i < na; i++) CHECK(findSequence(T[i].label) != nullptr, "no body sequence for label %s", T[i].label);
  CHECK(findSequence("snuggle") && findSequence("slowWag"), "comfort sequences");
  // every sequence stays inside the limits and the pulse range, on a clear desk
  SensorFrame clear{};
  clear.dt = 0.02f;
  for (int l = 0; l < LASER_COUNT; l++) { clear.laserOk[l] = true; clear.laserMm[l] = 55; }
  clear.laserMm[LASER_FRONT] = clear.laserMm[LASER_REAR] = 400;
  clear.imuOk = true; clear.ax = 0; clear.ay = 0; clear.az = 1; clear.volts = 7.8f;
  SafetyEvent ev[8];
  for (int si = 0; si < sequenceCount(); si++) {
    Controller c;
    BodyOutput o;
    c.play(sequenceAt(si).label);
    for (int k = 0; k < 400; k++) {
      c.tick(clear, &o, ev, 8);
      for (int l = 0; l < 4; l++) {
        static const Joint H[4] = {HIP_FL, HIP_FR, HIP_BL, HIP_BR}, K[4] = {KNEE_FL, KNEE_FR, KNEE_BL, KNEE_BR};
        float h = o.angle[H[l]], kk = o.angle[K[l]];
        CHECK(!limitLeg((Leg)l, &h, &kk), "%s leaves the joint envelope", sequenceAt(si).label);
      }
      for (int j = 0; j < JOINT_COUNT; j++) {
        int us = c.pulseUs(j, o.angle[j]);
        CHECK(us >= 600 && us <= 2400, "%s pulse %d", sequenceAt(si).label, us);
      }
    }
  }
  // desk edge (servo load check): every stop is RAMPED at 1.5 m/s^2. From top speed (0.16 m/s) the robot
  // must still stop well inside the 30-40 mm the desk-edge lasers look ahead of the wheels (BOM 2c.5).
  {
    Controller c;
    BodyOutput o;
    c.setDrive(1, 1, 30);
    for (int k = 0; k < 150; k++) c.tick(clear, &o, ev, 8);  // reach full speed
    CHECK(o.angle[WHEEL_FL] > 0.99f, "reaches full speed on a clear desk (%.2f)", o.angle[WHEEL_FL]);
    SensorFrame e = clear;
    e.laserMm[EDGE_FL] = 400;
    double dist = 0;
    float prevL = o.angle[WHEEL_FL], maxStep = 0;
    bool sawEvent = false;
    int ticks = 0;
    for (; ticks < 100; ticks++) {
      int n = c.tick(e, &o, ev, 8);
      for (int i = 0; i < n; i++) sawEvent |= ev[i] == EV_EDGE_FL;
      dist += 0.5 * (prevL + o.angle[WHEEL_FL]) * c.mcfg.wheelTopSpeed * 0.02 * 1000.0;  // mm
      maxStep = std::max(maxStep, fabsf(o.angle[WHEEL_FL] - prevL));
      prevL = o.angle[WHEEL_FL];
      if (o.angle[WHEEL_FL] <= 0 && o.angle[WHEEL_FR] <= 0) break;
    }
    CHECK(sawEvent, "EV_EDGE_FL seen");
    CHECK(o.angle[WHEEL_FL] == 0 && o.angle[WHEEL_FR] == 0 && o.angle[WHEEL_BL] == 0, "wheels stopped at the edge");
    float decel = maxStep * c.mcfg.wheelTopSpeed / 0.02f;
    CHECK(decel <= 1.5f + 0.01f, "edge stop deceleration %.2f m/s^2 (limit 1.5)", decel);
    CHECK(dist <= 20.0, "stopping distance from top speed %.1f mm (lasers look 30-40 mm ahead)", dist);
    printf("edge stop from 0.16 m/s: %.1f mm in %d ticks (2-reading confirm + 1.5 m/s^2 ramp)\n", dist, ticks + 1);
    // the zoomies spin also ramps down and never restarts toward the edge
    Controller z;
    z.play("zoomies");
    for (int k = 0; k < 3; k++) z.tick(clear, &o, ev, 8);
    CHECK(o.angle[WHEEL_FL] != 0, "zoomies drives on a clear desk");
    for (int k = 0; k < 20; k++) z.tick(e, &o, ev, 8);
    CHECK(o.angle[WHEEL_FL] == 0 && o.angle[WHEEL_FR] == 0, "playful drive stops completely near an edge");
    // backing away from the edge is allowed, driving toward it is not
    c.setDrive(-0.5f, -0.5f, 1);
    for (int k = 0; k < 5; k++) c.tick(e, &o, ev, 8);
    CHECK(o.angle[WHEEL_FL] < 0, "backing away from a front edge is allowed");
    c.setDrive(0.5f, 0.5f, 1);
    for (int k = 0; k < 10; k++) c.tick(e, &o, ev, 8);
    CHECK(o.angle[WHEEL_FL] <= 0, "driving toward the edge is blocked");
  }
  // every wheel speed change, in every sequence and a manual start / stop, respects 1.5 m/s^2
  {
    float worst = 0;
    for (int si = 0; si < sequenceCount(); si++) {
      Controller c;
      BodyOutput o;
      c.play(sequenceAt(si).label);
      float pl = 0, pr = 0;
      for (int k = 0; k < 300; k++) {
        c.tick(clear, &o, ev, 8);
        worst = std::max(worst, std::max(fabsf(o.angle[WHEEL_FL] - pl), fabsf(o.angle[WHEEL_FR] - pr)));
        pl = o.angle[WHEEL_FL];
        pr = o.angle[WHEEL_FR];
      }
    }
    Controller c;
    BodyOutput o;
    float pl = 0;
    c.setDrive(1, 1, 1);
    for (int k = 0; k < 100; k++) { c.tick(clear, &o, ev, 8); worst = std::max(worst, fabsf(o.angle[WHEEL_FL] - pl)); pl = o.angle[WHEEL_FL]; }
    CHECK(worst * 0.16f / 0.02f <= 1.51f, "wheel acceleration %.2f m/s^2 > 1.5", worst * 0.16f / 0.02f);
  }
  // spins: turning in place only in bursts of <= 0.5 s followed by >= 0.4 s rest, at <= 0.4 command
  {
    for (const char* lab : {"zoomies", "happy-dance"}) {
      Controller c;
      BodyOutput o;
      c.play(lab);
      float run = 0, rest = 1, maxRun = 0, minRestAfterRun = 9, maxCmd = 0, total = 0;
      bool inRun = false;
      for (int k = 0; k < 200; k++) {
        c.tick(clear, &o, ev, 8);
        float L = o.angle[WHEEL_FL], R = o.angle[WHEEL_FR];
        bool turn = (L > 0.02f && R < -0.02f) || (L < -0.02f && R > 0.02f);
        maxCmd = std::max(maxCmd, std::max(fabsf(L), fabsf(R)));
        if (turn) { if (!inRun && run == 0 && rest < minRestAfterRun && total > 0) minRestAfterRun = rest; run += 0.02f; total += 0.02f; inRun = true; rest = 0; }
        else { if (inRun) maxRun = std::max(maxRun, run); run = 0; inRun = false; rest += 0.02f; }
      }
      if (inRun) maxRun = std::max(maxRun, run);
      CHECK(maxRun <= 0.52f, "%s turns for %.2f s in one go (limit 0.5)", lab, maxRun);
      CHECK(minRestAfterRun >= 0.38f || minRestAfterRun == 9, "%s rests only %.2f s between turns", lab, minRestAfterRun);
      CHECK(maxCmd <= 0.401f, "%s turn speed %.2f (limit 0.4)", lab, maxCmd);
      CHECK(total <= 1.3f, "%s turns %.2f s in total", lab, total);
    }
    Controller c;  // a long manual spin is cut into bursts too
    BodyOutput o;
    c.setDrive(1, -1, 3);
    float run = 0, maxRun = 0;
    for (int k = 0; k < 150; k++) {
      c.tick(clear, &o, ev, 8);
      bool turn = o.angle[WHEEL_FL] > 0.02f && o.angle[WHEEL_FR] < -0.02f;
      run = turn ? run + 0.02f : 0;
      maxRun = std::max(maxRun, run);
      CHECK(fabsf(o.angle[WHEEL_FL]) <= 0.401f, "manual spin speed capped");
    }
    CHECK(maxRun <= 0.52f, "manual spin burst %.2f s", maxRun);
  }
  // tail: every wag inside +-30 deg and the servo's 565 deg/s
  {
    float maxA = 0, maxRate = 0;
    for (int si = 0; si < sequenceCount(); si++) {
      Controller c;
      BodyOutput o;
      c.play(sequenceAt(si).label);
      float prev = 0;
      for (int k = 0; k < 300; k++) {
        c.tick(clear, &o, ev, 8);
        maxA = std::max(maxA, fabsf(o.angle[TAIL]));
        if (k) maxRate = std::max(maxRate, fabsf(o.angle[TAIL] - prev) / 0.02f);
        prev = o.angle[TAIL];
      }
    }
    CHECK(maxA <= 30.01f, "tail swings %.1f deg (cap 30)", maxA);
    CHECK(maxRate <= 600, "tail speed %.0f deg/s (servo ~600)", maxRate);
    printf("tail: max %.1f deg, max %.0f deg/s\n", maxA, maxRate);
  }
  // poses from the servo load check
  {
    CHECK(pose(POSE_PLAY_BOW).hip[0] <= 20 && pose(POSE_PLAY_BOW).knee[0] >= -40, "soft play bow 20 / -40");
    CHECK(fabsf(pose(POSE_LIE).knee[0]) <= 24 && fabsf(pose(POSE_LIE).knee[2]) <= 24, "shallow lie (knees <= 24)");
    for (int l = 0; l < LEG_COUNT; l++) CHECK(pose(POSE_PARK).hip[l] == 0 && pose(POSE_PARK).knee[l] == 0, "park = straight legs");
  }
  // power-up stagger: at most one output switches on per 150 ms, legs first; again after a fall
  {
    Controller c;
    BodyOutput o;
    bool prev[JOINT_COUNT] = {false};
    float lastOnT = -1, minGap = 9, t = 0;
    int firstOn = -1;
    auto run = [&](const SensorFrame& fr, int ticks) {
      for (int k = 0; k < ticks; k++) {
        c.tick(fr, &o, ev, 8);
        t += 0.02f;
        int newly = 0;
        for (int j = 0; j < JOINT_COUNT; j++) {
          if (o.enabled[j] && !prev[j]) { newly++; if (firstOn < 0) firstOn = j; }
          prev[j] = o.enabled[j];
        }
        CHECK(newly <= 1, "%d outputs switched on in one tick", newly);
        if (newly) { if (lastOnT >= 0) minGap = std::min(minGap, t - lastOnT); lastOnT = t; }
      }
    };
    run(clear, 120);
    int on = 0;
    for (int j = 0; j < JOINT_COUNT; j++) on += o.enabled[j];
    CHECK(on == JOINT_COUNT, "all %d outputs on after the stagger (%d)", JOINT_COUNT, on);
    CHECK(minGap >= 0.139f, "outputs switched on %.3f s apart (>= 0.15)", minGap);
    CHECK(firstOn == HIP_FL, "a leg servo switches on first");
    SensorFrame tilt = clear;
    tilt.ay = 0.866f; tilt.az = 0.5f;
    run(tilt, 10);  // fall: legs limp
    lastOnT = -1; minGap = 9;
    run(clear, 120);  // stood up again: staggered again
    CHECK(minGap >= 0.139f, "after a fall, outputs switched on %.3f s apart", minGap);
  }
  // brown-out guard: below 7.2 V (fast reading) only one leg moves at a time, slowly; no spins; a dip
  // below 6.6 V freezes the joints
  {
    Controller c;
    BodyOutput o;
    SensorFrame lo = clear;
    lo.voltsFast = 7.1f;
    bool sawLow = false;
    for (int k = 0; k < 100; k++) { int n = c.tick(lo, &o, ev, 8); for (int i = 0; i < n; i++) sawLow |= ev[i] == EV_LOW_POWER; }
    CHECK(sawLow && c.lowPower(), "low-power mode below 7.2 V");
    c.setPose(POSE_LIE, 0.3f);
    float prevA[JOINT_COUNT];
    for (int j = 0; j < JOINT_COUNT; j++) prevA[j] = o.angle[j];
    int maxLegs = 0;
    float maxRate = 0;
    for (int k = 0; k < 200; k++) {
      c.tick(lo, &o, ev, 8);
      int moving = 0;
      static const Joint H[4] = {HIP_FL, HIP_FR, HIP_BL, HIP_BR}, K[4] = {KNEE_FL, KNEE_FR, KNEE_BL, KNEE_BR};
      for (int l = 0; l < 4; l++) {
        float dh = fabsf(o.angle[H[l]] - prevA[H[l]]), dk = fabsf(o.angle[K[l]] - prevA[K[l]]);
        if (dh > 1e-3f || dk > 1e-3f) moving++;
        maxRate = std::max(maxRate, std::max(dh, dk) / 0.02f);
      }
      maxLegs = std::max(maxLegs, moving);
      for (int j = 0; j < JOINT_COUNT; j++) prevA[j] = o.angle[j];
    }
    CHECK(maxLegs <= 1, "%d legs moved at once in low power", maxLegs);
    CHECK(maxRate <= 60.5f, "low-power joint speed %.0f deg/s (limit 60)", maxRate);
    CHECK(fabsf(o.angle[KNEE_BR] - pose(POSE_LIE).knee[3]) < 0.1f, "low power still reaches the pose");
    c.play("zoomies");
    for (int k = 0; k < 50; k++) { c.tick(lo, &o, ev, 8); CHECK(o.angle[WHEEL_FL] == 0, "no spin in low power"); }
    // a dip freezes the joints
    Controller d;
    for (int k = 0; k < 150; k++) d.tick(clear, &o, ev, 8);
    d.setPose(POSE_SIT, 0.2f);
    SensorFrame dip = clear;
    dip.voltsFast = 6.4f;
    d.tick(dip, &o, ev, 8);
    float h0 = o.angle[HIP_BL];
    for (int k = 0; k < 20; k++) d.tick(dip, &o, ev, 8);
    CHECK(fabsf(o.angle[HIP_BL] - h0) < 1e-3f, "joints frozen during a 6.4 V dip");
    bool sawOk = false;
    for (int k = 0; k < 200; k++) { int n = d.tick(clear, &o, ev, 8); for (int i = 0; i < n; i++) sawOk |= ev[i] == EV_POWER_OK; }
    CHECK(sawOk && !d.lowPower(), "normal power again after 2 s above 7.4 V");
  }
  // a missing desk-edge sensor is treated as an edge (fail-safe)
  {
    Controller c;
    BodyOutput o;
    SensorFrame m = clear;
    m.laserOk[EDGE_REAR] = false;
    for (int k = 0; k < 3; k++) c.tick(m, &o, ev, 8);
    c.setDrive(-0.5f, -0.5f, 1);
    c.tick(m, &o, ev, 8);
    CHECK(o.angle[WHEEL_BL] == 0, "missing rear edge sensor must block reversing");
  }
  // obstacle ahead blocks forward only
  {
    Controller c;
    BodyOutput o;
    SensorFrame m = clear;
    m.laserMm[LASER_FRONT] = 40;
    c.setDrive(0.5f, 0.5f, 1);
    c.tick(m, &o, ev, 8);
    CHECK(o.angle[WHEEL_FL] == 0, "front obstacle blocks forward");
  }
  // pick-up: all desk-edge lasers lose the desk -> EV_PICKUP within 0.5 s, wheels stop; put down again
  {
    Controller c;
    BodyOutput o;
    SensorFrame up = clear;
    up.laserMm[EDGE_FL] = up.laserMm[EDGE_FR] = up.laserMm[EDGE_REAR] = 800;
    bool pick = false, down = false;
    for (int k = 0; k < 25; k++) { int n = c.tick(up, &o, ev, 8); for (int i = 0; i < n; i++) pick |= ev[i] == EV_PICKUP; }
    CHECK(pick, "pick-up detected");
    for (int k = 0; k < 60; k++) { int n = c.tick(clear, &o, ev, 8); for (int i = 0; i < n; i++) down |= ev[i] == EV_PUTDOWN; }
    CHECK(down, "put-down detected");
  }
  // fall: 60 deg tilt -> EV_FALL, legs go limp
  {
    Controller c;
    BodyOutput o;
    SensorFrame t = clear;
    t.ax = 0; t.ay = 0.866f; t.az = 0.5f;
    bool fell = false;
    for (int k = 0; k < 5; k++) { int n = c.tick(t, &o, ev, 8); for (int i = 0; i < n; i++) fell |= ev[i] == EV_FALL; }
    CHECK(fell, "fall detected");
    CHECK(!o.enabled[HIP_FL] && !o.enabled[KNEE_BR], "legs limp after a fall");
  }
  // battery: 6.95 V warns only; 6.7 V for 5 s parks, then all servo outputs switch off
  {
    Controller c;
    BodyOutput o;
    SensorFrame b = clear;
    b.volts = 6.95f;
    bool warn = false, cut = false;
    for (int k = 0; k < 100; k++) { int n = c.tick(b, &o, ev, 8); for (int i = 0; i < n; i++) { warn |= ev[i] == EV_BATTERY_WARN; cut |= ev[i] == EV_BATTERY_CUT; } }
    CHECK(warn && !cut, "7.0 V warning only");
    b.volts = 6.7f;
    for (int k = 0; k < 240; k++) { int n = c.tick(b, &o, ev, 8); for (int i = 0; i < n; i++) cut |= ev[i] == EV_BATTERY_CUT; }
    CHECK(!cut, "no cut before 5 s below 6.8 V");
    for (int k = 0; k < 20; k++) { int n = c.tick(b, &o, ev, 8); for (int i = 0; i < n; i++) cut |= ev[i] == EV_BATTERY_CUT; }
    CHECK(cut, "cut after 5 s below 6.8 V");
    CHECK(o.enabled[HIP_FL], "legs still powered while parking");
    for (int k = 0; k < 80; k++) c.tick(b, &o, ev, 8);
    bool anyOn = false;
    for (int j = 0; j < JOINT_COUNT; j++) anyOn |= o.enabled[j];
    CHECK(!anyOn, "every servo output off after the park");
    CHECK(fabsf(o.angle[HIP_FL] - pose(POSE_PARK).hip[0]) < 0.5f, "parked in the park pose");
    b.volts = 8.0f;
    for (int k = 0; k < 100; k++) c.tick(b, &o, ev, 8);
    anyOn = false;
    for (int j = 0; j < JOINT_COUNT; j++) anyOn |= o.enabled[j];
    CHECK(!anyOn, "the cut latches until reboot");
  }
  // calibration defaults are valid, and the channel map matches the guide
  { Calibration cal; cal.setDefaults(); CHECK(cal.valid(), "default calibration"); }
  CHECK(kServoMap[TAIL].board == 0 && kServoMap[TAIL].channel == 8, "tail on A ch 8");
  CHECK(kServoMap[WHEEL_BR].board == 1 && kServoMap[WHEEL_BR].channel == 6, "BR wheel on B ch 6");
  CHECK(kLaserMap[EDGE_REAR].xshutChannel == 13 && kLaserMap[LASER_SIDE_R].xshutChannel == 15, "laser XSHUT map");
  printf("body test: %s (%d failure%s)\n", fails ? "FAILED" : "ok", fails, fails == 1 ? "" : "s");
  return fails ? 1 : 0;
}

int cmdLink(int argc, char** argv);     // link_test.cpp
int cmdPasskey(int argc, char** argv);  // link_test.cpp
int cmdGait();                          // gait_test.cpp

int main(int argc, char** argv) {
  if (argc < 2) {
    printf("face_pc selftest | png ... | cases ...\n");
    return 2;
  }
  if (strcmp(argv[1], "selftest") == 0) return selftest();
  if (strcmp(argv[1], "png") == 0) return cmdPng(argc, argv);
  if (strcmp(argv[1], "cases") == 0) return cmdCases(argc, argv);
  if (strcmp(argv[1], "life") == 0) return cmdLife(argc, argv);
  if (strcmp(argv[1], "sounds") == 0) return cmdSounds(argc, argv);
  if (strcmp(argv[1], "body") == 0) return cmdBody();
  if (strcmp(argv[1], "gait") == 0) return cmdGait();
  if (strcmp(argv[1], "link") == 0) return cmdLink(argc, argv);
  if (strcmp(argv[1], "passkey") == 0) return cmdPasskey(argc, argv);
  printf("unknown command %s\n", argv[1]);
  return 2;
}
