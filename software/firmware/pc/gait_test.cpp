// gait_test.cpp -- `face_pc gait`: host tests of the walking / give-paw / balance-calibration state machine
// and the desk-edge laser threshold, against a 3-D statics PLANT.
//
// The plant is a C++ port of cad/stability_scripts/spike_model.py (the research model the gait spec came
// from; the review's independent model matched it to 0.01 kg.cm): geometry and masses from
// cad/servo_load_check_v3_1.py, the body resting on the three paws whose plane leaves the fourth paw above
// the desk with the weight inside their triangle, the tyre touching the desk in its own plane. It is
// path-aware: the body stays on its current tripod while that is still valid, else rocks onto the valid
// tripod with the closest attitude (the model's own solve4 picks by gap, which is not path-aware).
// The plant turns the Controller's joint outputs into body pitch / roll (accelerometer + gyro), lifted-paw
// heights and desk-edge laser readings, so the firmware's closed loop runs against "physics".
#include "spike_body.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <algorithm>
#include <vector>

using namespace spike::body;

static int gfails = 0;
#define GCHECK(cond, ...) do { if (!(cond)) { gfails++; printf("  FAIL: "); printf(__VA_ARGS__); printf("\n"); } } while (0)

// ---- plant: port of spike_model.py -------------------------------------------------------------------
namespace plant {
struct V3 { double x, y, z; };
static V3 operator+(V3 a, V3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
static V3 operator-(V3 a, V3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
static V3 operator*(double s, V3 a) { return {s * a.x, s * a.y, s * a.z}; }
static double dot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static V3 cross(V3 a, V3 b) { return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x}; }
static V3 norm(V3 a) { double n = sqrt(dot(a, a)); return n > 1e-12 ? (1.0 / n) * a : a; }

// frame: x lateral (+ = robot's left), y up, z forward; mm, g
static const double HIP_Y = 18, L1 = 38, L2 = 45, TYRE_R = 16.3, CASE_OFF = 5.4;
static const double HIP_Z[4] = {66, 66, -52, -52};          // FL FR BL BR
static const double FOOT_X[4] = {81.2, -81.2, 81.2, -81.2};
static const double KNEE_DZ[4] = {1, 1, -1, -1};
static const double M_BODY = 714.6, M_THIGH = 16.7, M_KNEE_SV = 13.4, M_SHIN = 20.1, M_WHEEL_SV = 13.4, M_WHEEL = 3.5;
static const V3 COM_BODY = {0.27511895, 47.60187517, 20.62602855};
static const double D2R = 3.14159265358979 / 180;

struct LegPts { V3 axle; std::vector<std::pair<double, V3>> masses; };

static LegPts legPoints(int l, double hip, double knee) {
  double h = hip * D2R, t = (hip + knee) * D2R;
  double hy = HIP_Y, hz = HIP_Z[l];
  double ky = hy + L1 * -cos(h), kz = hz + L1 * sin(h);
  double ay = ky + L2 * -cos(t), az = kz + L2 * sin(t);
  LegPts p;
  p.axle = {FOOT_X[l], ay, az};
  double x = FOOT_X[l];
  p.masses.push_back({M_THIGH, {x, (hy + ky) / 2, (hz + kz) / 2}});
  p.masses.push_back({M_KNEE_SV, {x, ky + CASE_OFF * KNEE_DZ[l] * sin(h), kz + CASE_OFF * KNEE_DZ[l] * cos(h)}});
  p.masses.push_back({M_SHIN, {x, (ky + ay) / 2, (kz + az) / 2}});
  p.masses.push_back({M_WHEEL_SV, {x, ay + CASE_OFF * sin(t), az + CASE_OFF * cos(t)}});
  p.masses.push_back({M_WHEEL, {x, ay, az}});
  return p;
}

static V3 contact(V3 axle, V3 n) {
  V3 d = {0, -n.y, -n.z};  // -n without its x (lateral) part: the tyre touches in its own plane
  d = norm(d);
  return axle + TYRE_R * d;
}

struct Sol { bool ok; double margin, gap, pitch, roll; V3 n; };

static Sol solve(const double hip[4], const double knee[4], int lifted, double comShiftZ) {
  LegPts P[4];
  for (int l = 0; l < 4; l++) P[l] = legPoints(l, hip[l], knee[l]);
  int sup[3], k = 0;
  for (int l = 0; l < 4; l++) if (l != lifted) sup[k++] = l;
  V3 n = {0, 1, 0}, p0{};
  V3 cps[4];
  for (int it = 0; it < 3; it++) {
    for (int l = 0; l < 4; l++) cps[l] = contact(P[l].axle, n);
    p0 = cps[sup[0]];
    V3 nn = norm(cross(cps[sup[1]] - p0, cps[sup[2]] - p0));
    if (nn.y < 0) nn = -1.0 * nn;
    n = nn;
  }
  for (int l = 0; l < 4; l++) cps[l] = contact(P[l].axle, n);
  p0 = cps[sup[0]];
  double M = M_BODY;
  V3 com = M_BODY * (COM_BODY + V3{0, 0, comShiftZ});
  for (int l = 0; l < 4; l++)
    for (auto& m : P[l].masses) { M += m.first; com = com + m.first * m.second; }
  com = (1.0 / M) * com;
  V3 e1 = norm(cross(n, {0, 0, 1})), e2 = cross(e1, n);
  double h = dot(com - p0, n);
  V3 cp = com - h * n;
  double c2[2] = {dot(cp - p0, e1), dot(cp - p0, e2)};
  double q[3][2];
  for (int i = 0; i < 3; i++) { q[i][0] = dot(cps[sup[i]] - p0, e1); q[i][1] = dot(cps[sup[i]] - p0, e2); }
  double margin = 1e9;
  for (int i = 0; i < 3; i++) {
    const double *a = q[i], *b = q[(i + 1) % 3], *c = q[(i + 2) % 3];
    double ex = b[0] - a[0], ey = b[1] - a[1], ln = sqrt(ex * ex + ey * ey);
    double nx = -ey / ln, ny = ex / ln;
    if ((c[0] - a[0]) * nx + (c[1] - a[1]) * ny < 0) { nx = -nx; ny = -ny; }
    margin = std::min(margin, (c2[0] - a[0]) * nx + (c2[1] - a[1]) * ny);
  }
  Sol s;
  s.gap = dot(cps[lifted] - p0, n);
  s.margin = margin;
  s.ok = s.gap >= -0.3 && margin >= 0;
  s.pitch = atan2(n.z, n.y) / D2R;
  s.roll = atan2(-n.x, n.y) / D2R;
  s.n = n;
  return s;
}

struct Body {
  double comShiftZ = 0;   // + = weight further forward than the model
  int tripod = 2;         // the paw NOT on the desk in the current support (stand: any of the back ones)
  double pitch = 0, roll = 0, gap[4] = {0, 0, 0, 0};
  bool fell = false;
  Sol cur{};
  void step(const double hip[4], const double knee[4]) {
    Sol s[4];
    for (int l = 0; l < 4; l++) s[l] = solve(hip, knee, l, comShiftZ);
    if (!s[tripod].ok) {
      int best = -1;
      double bd = 1e9;
      for (int l = 0; l < 4; l++) {
        if (!s[l].ok) continue;
        double d = fabs(s[l].pitch - pitch) + fabs(s[l].roll - roll);
        if (d < bd) { bd = d; best = l; }
      }
      if (best < 0) { fell = true; return; }
      tripod = best;
    }
    cur = s[tripod];
    pitch = cur.pitch;
    roll = cur.roll;
    for (int l = 0; l < 4; l++) gap[l] = 0;
    gap[tripod] = std::max(0.0, cur.gap);
  }
  double maxGap() const { return std::max(std::max(gap[0], gap[1]), std::max(gap[2], gap[3])); }
};
}  // namespace plant

// Desk-edge laser reading at a body tilt relative to the desk (the review's geometry, see EdgeLaserConfig).
static float laserModel(float baseline, int i, float pitchDeg, float rollDeg) {
  const float R = 0.01745329f;
  float a0 = 65 * R, p = pitchDeg * R, r = rollDeg * R;
  float h = baseline * sinf(a0), a;
  if (i < 2) { h += 111 * sinf(p) - (i == 0 ? 35 : -35) * sinf(r); a = a0 - p; }
  else { h -= 17 * sinf(p); a = a0 + p; }
  return h / sinf(a);
}

// ---- simulation harness ----------------------------------------------------------------------------------
struct Sim {
  Controller c;
  plant::Body pl;
  BodyOutput o{};
  SafetyEvent ev[8];
  float t = 0;
  double dist = 0;
  float baseline[3] = {94, 94, 94};
  float edgeForce[3] = {-1, -1, -1};   // >= 0: this reading instead of the model
  float deskP = 0, deskR = 0;          // desk tilt (IMU sees it, lasers do not)
  float biasP = 0, biasR = 0;          // extra IMU tilt (disturbance injection)
  float volts = 7.9f, voltsFast = -1;
  float frontObstacle = 400;
  bool lifted = false;                 // pick-up: all lasers far + no weight
  bool falseEdgesInLegPhase = false;   // feed the review's nose-up false-edge readings (lasers in B_FL etc.)
  // sag test: extra IMU tilt along the predicted change = sagGain * (trim - sagTrue) while a front paw is up
  float sagGain = 0, sagTrue = 0, sagExtra = 0;
  float prevP = 0, prevR = 0;
  bool first = true;
  // invariants over the whole run
  int violWheelsWhileLifted = 0, violIgnoreWithWheels = 0, violEnvelope = 0, violAccel = 0, violRearm = 0;
  double maxGapFL = 0, maxGapFR = 0, maxGapBL = 0, maxGapBR = 0;
  float prevWheel = 0, lastArmT = -1;
  bool prevWheelOn[4] = {true, true, true, true};
  int edgeEvents = 0, gaitDone = 0, calEvents = 0;
  std::vector<GaitPhase> phases;

  Sim() { pl.tripod = 2; }

  SensorFrame frame() {
    SensorFrame f{};
    f.dt = 0.02f;
    float sp = (float)pl.pitch, sr = (float)pl.roll;
    float p = sp + deskP + biasP, r = sr + deskR + biasR;
    // sag injection
    if (sagGain != 0) {
      const GaitStatus& gs = c.gait.status();
      if ((gs.phase == GP_TILT || gs.phase == GP_HOLD) && (pl.gap[LEG_FL] > 5 || pl.gap[LEG_FR] > 5)) {
        float gap = (float)std::max(pl.gap[LEG_FL], pl.gap[LEG_FR]);
        float target = sagGain * (gs.trimNow - sagTrue) * std::min(1.0f, (gap - 5) / 25.0f);
        sagExtra += (target - sagExtra) * 0.02f / 0.15f;  // servo sag follows the load with a lag
      } else sagExtra += (0 - sagExtra) * 0.02f / 0.15f;
      float dp = 2.43f, dr = pl.gap[LEG_FR] > 5 ? 0.94f : -0.94f, dl = sqrtf(dp * dp + dr * dr);
      p += sagExtra * dp / dl;
      r += sagExtra * dr / dl;
    }
    const float R = 0.01745329f;
    float az = 1.0f / sqrtf(1 + tanf(p * R) * tanf(p * R) + tanf(r * R) * tanf(r * R));
    f.imuOk = true;
    f.az = az;
    f.ax = tanf(p * R) * az;
    f.ay = -tanf(r * R) * az;
    if (lifted) { f.az *= 0.3f; f.ax *= 0.3f; f.ay *= 0.3f; }
    f.gyroOk = true;
    if (first) { prevP = p; prevR = r; first = false; }
    f.gy = -(p - prevP) / 0.02f;
    f.gx = -(r - prevR) / 0.02f;
    f.gz = 0;
    prevP = p; prevR = r;
    for (int l = 0; l < LASER_COUNT; l++) { f.laserOk[l] = true; f.laserMm[l] = 400; }
    f.laserMm[LASER_FRONT] = frontObstacle;
    static const Laser E[3] = {EDGE_FL, EDGE_FR, EDGE_REAR};
    for (int i = 0; i < 3; i++) {
      float v = laserModel(baseline[i], i, sp, sr);
      if (falseEdgesInLegPhase && c.safety.ignoreEdges) v = 150;  // a certain "edge" if it were not ignored
      if (edgeForce[i] >= 0) v = edgeForce[i];
      if (lifted) v = 800;
      f.laserMm[E[i]] = v;
    }
    f.volts = volts;
    f.voltsFast = voltsFast;
    return f;
  }

  void step() {
    SensorFrame f = frame();
    int n = c.tick(f, &o, ev, 8);
    for (int i = 0; i < n; i++) {
      if (ev[i] == EV_EDGE_FL || ev[i] == EV_EDGE_FR || ev[i] == EV_EDGE_REAR) edgeEvents++;
      if (ev[i] == EV_GAIT_DONE) gaitDone++;
      if (ev[i] == EV_EDGE_CALIBRATED) calEvents++;
    }
    t += 0.02f;
    double hip[4], knee[4];
    static const Joint H[4] = {HIP_FL, HIP_FR, HIP_BL, HIP_BR}, K[4] = {KNEE_FL, KNEE_FR, KNEE_BL, KNEE_BR};
    for (int l = 0; l < 4; l++) {
      hip[l] = o.angle[H[l]];
      knee[l] = o.angle[K[l]];
      float h = (float)hip[l], k = (float)knee[l];
      if (limitLeg((Leg)l, &h, &k)) violEnvelope++;
    }
    pl.step(hip, knee);
    maxGapFL = std::max(maxGapFL, pl.gap[LEG_FL]);
    maxGapFR = std::max(maxGapFR, pl.gap[LEG_FR]);
    maxGapBL = std::max(maxGapBL, pl.gap[LEG_BL]);
    maxGapBR = std::max(maxGapBR, pl.gap[LEG_BR]);
    // invariants
    static const Joint W[4] = {WHEEL_FL, WHEEL_FR, WHEEL_BL, WHEEL_BR};
    bool anyWheelOn = false, anyMoving = false;
    for (int w = 0; w < 4; w++) {
      anyWheelOn |= o.enabled[W[w]];
      anyMoving |= o.enabled[W[w]] && fabsf(o.angle[W[w]]) > 1e-6f;
    }
    if (anyMoving && pl.maxGap() > 1.5) violWheelsWhileLifted++;  // glide only on four paws
    if (pl.maxGap() > 3.0 && anyWheelOn) violWheelsWhileLifted++;   // a paw clearly up: wheels PWM-off
    if (c.safety.ignoreEdges && anyWheelOn) violIgnoreWithWheels++;
    float wl = o.angle[WHEEL_FL];
    if (fabsf(wl - prevWheel) * 0.16f / 0.02f > 1.51f) violAccel++;
    prevWheel = wl;
    int newly = 0;
    for (int w = 0; w < 4; w++) { if (o.enabled[W[w]] && !prevWheelOn[w]) newly++; prevWheelOn[w] = o.enabled[W[w]]; }
    if (newly > 1) violRearm++;
    if (newly == 1) { if (lastArmT >= 0 && t - lastArmT < 0.139f && c.gait.active()) violRearm++; lastArmT = t; }
    if (!anyWheelOn) lastArmT = -1;
    if (pl.maxGap() < 1.0 && anyMoving) dist += 0.5 * (o.angle[WHEEL_FL] + o.angle[WHEEL_FR]) * 0.16 * 0.02 * 1000.0;
    if (phases.empty() || phases.back() != c.gait.status().phase) phases.push_back(c.gait.status().phase);
  }
  void run(float seconds) { for (int k = 0; k < (int)(seconds / 0.02f + 0.5f); k++) step(); }
  // until the gait is idle (or the time limit)
  bool runGait(float limit) {
    for (int k = 0; k < (int)(limit / 0.02f); k++) { step(); if (!c.gait.active() && k > 2) return true; if (pl.fell) return false; }
    return false;
  }
  void boot() { run(3.0f); }  // power-up stagger + the startup laser level measurement
  bool calibrate() {
    boot();
    if (!c.calibrateBalance()) return false;
    return runGait(120) && c.gait.status().result == GR_CAL_PASS;
  }
  bool sawPhase(GaitPhase p) const { return std::find(phases.begin(), phases.end(), p) != phases.end(); }
  int invariantViolations() const { return violWheelsWhileLifted + violIgnoreWithWheels + violEnvelope + violAccel + violRearm; }
};

static void reportInvariants(const Sim& s, const char* name) {
  GCHECK(!s.pl.fell, "%s: the plant tipped over", name);
  GCHECK(s.violWheelsWhileLifted == 0, "%s: wheels on / moving while a paw was up (%d ticks)", name, s.violWheelsWhileLifted);
  GCHECK(s.violIgnoreWithWheels == 0, "%s: desk-edge lasers ignored while a wheel was powered (%d)", name, s.violIgnoreWithWheels);
  GCHECK(s.violEnvelope == 0, "%s: joint output outside the envelope (%d)", name, s.violEnvelope);
  GCHECK(s.violAccel == 0, "%s: wheel speed change over 1.5 m/s^2 (%d)", name, s.violAccel);
  GCHECK(s.violRearm == 0, "%s: wheels switched on together / closer than 150 ms (%d)", name, s.violRearm);
}

// ---- the tests ----------------------------------------------------------------------------------------
int cmdGait() {
  gfails = 0;

  // 1. keyframes: inside the joint envelope for every trim; the plant reproduces the research tilts
  {
    static const GaitKey keys[] = {GK_CROSS, GK_LIFT, GK_PAW_STAND, GK_PAW_PUPPY, GK_REAR};
    for (GaitKey k : keys)
      for (int leg = 0; leg < 4; leg++)
        for (float tr = -3; tr <= 3.01f; tr += 0.5f) {
          Pose p = gaitPose(k, (Leg)leg, tr);
          for (int l = 0; l < 4; l++) {
            float h = p.hip[l], kk = p.knee[l];
            GCHECK(!limitLeg((Leg)l, &h, &kk), "%s leg %d trim %.1f outside the envelope", gaitKeyframe(k).name, l, tr);
          }
        }
    struct Case { GaitKey k; Leg leg; int lifted; double minGap; };
    static const Case cases[] = {{GK_LIFT, LEG_FL, LEG_FL, 35}, {GK_LIFT, LEG_FR, LEG_FR, 35}, {GK_REAR, LEG_BR, LEG_BR, 10},
                                 {GK_REAR, LEG_BL, LEG_BL, 10}, {GK_PAW_STAND, LEG_FL, LEG_FL, 35}, {GK_PAW_PUPPY, LEG_FR, LEG_FR, 50}};
    for (const Case& cs : cases) {
      Pose p = gaitPose(cs.k, cs.leg, 0);
      double hip[4], knee[4];
      for (int l = 0; l < 4; l++) { hip[l] = p.hip[l]; knee[l] = p.knee[l]; }
      plant::Sol s = plant::solve(hip, knee, cs.lifted, 0);
      float pp, pr;
      gaitPrediction(cs.k, cs.leg, &pp, &pr);
      GCHECK(s.ok && s.gap >= cs.minGap, "%s leg %d: plant rests with that paw %.1f mm up (margin %.1f)", gaitKeyframe(cs.k).name, cs.leg, s.gap, s.margin);
      GCHECK(fabs(s.pitch - pp) < 0.3 && fabs(s.roll - pr) < 0.3, "%s leg %d: plant tilt %.2f/%.2f vs prediction %.2f/%.2f",
             gaitKeyframe(cs.k).name, cs.leg, s.pitch, s.roll, pp, pr);
    }
    printf("keyframes: envelope ok for trims -3..+3; plant tilts match the research (lift +3.54/-2.76, rear -0.91/+0.68)\n");
  }

  // 2. desk-edge laser threshold: calibrated from the level reading, tilt-compensated, fallback 110
  {
    Safety s;
    GCHECK(fabsf(s.edgeThreshold(0) - 110) < 0.01f, "uncalibrated threshold %.1f (want the old 110)", s.edgeThreshold(0));
    SensorFrame f{};
    f.dt = 0.02f;
    f.imuOk = true; f.az = 1; f.gyroOk = true;
    for (int l = 0; l < LASER_COUNT; l++) { f.laserOk[l] = true; f.laserMm[l] = 400; }
    f.laserMm[EDGE_FL] = 94; f.laserMm[EDGE_FR] = 95; f.laserMm[EDGE_REAR] = 93;
    f.volts = 7.9f;
    SafetyEvent ev[8];
    s.standing = true;
    bool cal = false;
    for (int k = 0; k < 60; k++) { int n = s.tick(f, ev, 8); for (int i = 0; i < n; i++) cal |= ev[i] == EV_EDGE_CALIBRATED; }
    GCHECK(cal && s.edgeCal.done && s.edgeCal.fresh[0], "level calibration done after 1 s standing still");
    float lvl = s.edgeThreshold(0);
    GCHECK(fabsf(lvl - 119) < 1.0f, "level threshold %.1f (94 + 25)", lvl);
    GCHECK(!s.st.edge[0] && !s.st.edge[1] && !s.st.edge[2], "level desk: no edge");
    // the review's nose-up readings: 3.5 deg ~105 mm, 8 deg ~120, 12 deg ~136 -> not edges once compensated
    const float tilts[3] = {3.5f, 8, 12}, reads[3] = {105, 120, 136};
    for (int i = 0; i < 3; i++) {
      Safety t = s;
      SensorFrame g = f;
      float R = 0.01745329f;
      g.ax = sinf(tilts[i] * R); g.az = cosf(tilts[i] * R);
      g.laserMm[EDGE_FL] = g.laserMm[EDGE_FR] = reads[i];
      g.laserMm[EDGE_REAR] = laserModel(93, 2, tilts[i], 0);
      for (int k = 0; k < 40; k++) t.tick(g, ev, 8);
      GCHECK(!t.st.edge[0] && !t.st.edge[1] && !t.st.edge[2], "nose-up %.1f deg, %.0f mm read as an edge (threshold %.1f)",
             tilts[i], reads[i], t.edgeThreshold(0));
      printf("edge threshold at %4.1f deg nose-up: %.1f mm (level reading there ~%.0f mm; old fixed value 110)\n", tilts[i], t.edgeThreshold(0), reads[i]);
      // a REAL edge while tilted is still an edge
      g.laserMm[EDGE_FL] = 9999;
      bool e = false;
      for (int k = 0; k < 3; k++) { int n = t.tick(g, ev, 8); for (int j = 0; j < n; j++) e |= ev[j] == EV_EDGE_FL; }
      GCHECK(e && t.st.edge[0] && t.st.blockFwd, "real edge (no echo) while nose-up %.1f deg", tilts[i]);
      g.laserMm[EDGE_FL] = 400;  // the floor seen over a desk edge
      Safety u = t;
      for (int k = 0; k < 3; k++) u.tick(g, ev, 8);
      GCHECK(u.st.edge[0], "real edge (floor at 400 mm) while nose-up %.1f deg", tilts[i]);
    }
    { // level: real edge readings
      Safety t = s;
      SensorFrame g = f;
      g.laserMm[EDGE_FR] = 400;
      for (int k = 0; k < 3; k++) t.tick(g, ev, 8);
      GCHECK(t.st.edge[1] && t.st.blockFwd, "level: floor at 400 mm is an edge");
      g.laserMm[EDGE_FR] = 125;
      Safety u = s;
      for (int k = 0; k < 3; k++) u.tick(g, ev, 8);
      GCHECK(u.st.edge[1], "level: 125 mm (31 mm over the level reading) is an edge");
    }
    { // nose-down makes the front threshold tighter (never looser than level)
      Safety t = s;
      SensorFrame g = f;
      float R = 0.01745329f;
      g.ax = sinf(-4 * R); g.az = cosf(-4 * R);
      for (int k = 0; k < 40; k++) t.tick(g, ev, 8);
      GCHECK(t.edgeThreshold(0) < lvl - 5, "nose-down 4 deg: front threshold %.1f should be below the level %.1f", t.edgeThreshold(0), lvl);
      GCHECK(t.edgeThreshold(2) > lvl, "nose-down: the rear laser reads longer, threshold %.1f", t.edgeThreshold(2));
      // roll left side low: left laser lower, tighter
      g.ax = 0; g.ay = -sinf(5 * R); g.az = cosf(5 * R);
      for (int k = 0; k < 40; k++) t.tick(g, ev, 8);
      GCHECK(t.edgeThreshold(0) < t.edgeThreshold(1), "roll left-low: FL threshold %.1f < FR %.1f", t.edgeThreshold(0), t.edgeThreshold(1));
      g.ax = sinf(40 * R); g.ay = 0; g.az = cosf(40 * R);  // a silly tilt is clamped
      for (int k = 0; k < 40; k++) t.tick(g, ev, 8);
      GCHECK(t.edgeThreshold(0) <= s.cfg.laser.maxThresholdMm, "threshold capped (%.1f)", t.edgeThreshold(0));
    }
    // calibration refused: not level, moving, implausible, noisy, not standing
    struct Bad { const char* what; float ax; float gx; float mm; float noise; bool standing; };
    static const Bad bad[] = {{"tilted 6 deg", 0.105f, 0, 94, 0, true}, {"moving", 0, 10, 94, 0, true}, {"held in the air", 0, 0, 9999, 0, true},
                              {"too near", 0, 0, 30, 0, true}, {"noisy", 0, 0, 94, 12, true}, {"not standing", 0, 0, 94, 0, false}};
    for (const Bad& b : bad) {
      Safety t;
      t.standing = b.standing;
      SensorFrame g = f;
      g.ax = b.ax; g.az = sqrtf(1 - b.ax * b.ax); g.gx = b.gx;
      for (int k = 0; k < 100; k++) {
        float v = b.mm + ((k & 1) ? b.noise : 0);
        g.laserMm[EDGE_FL] = g.laserMm[EDGE_FR] = g.laserMm[EDGE_REAR] = v;
        t.tick(g, ev, 8);
      }
      GCHECK(!t.edgeCal.done && fabsf(t.edgeThreshold(0) - 110) < 0.01f, "calibration must be refused when %s", b.what);
    }
    { // stored baseline (NVS) is used until this boot's measurement; implausible stored values are not
      Safety t;
      float mm[3] = {90, 91, 92};
      bool ok[3] = {true, true, false};
      t.useStoredBaseline(mm, ok, 0, 0);
      GCHECK(fabsf(t.edgeThreshold(0) - 115) < 1 && fabsf(t.edgeThreshold(2) - 110) < 0.01f, "stored baseline used (%.1f / %.1f)",
             t.edgeThreshold(0), t.edgeThreshold(2));
      float junk[3] = {500, 10, 94};
      bool ok3[3] = {true, true, true};
      Safety u;
      u.useStoredBaseline(junk, ok3, 0, 0);
      GCHECK(fabsf(u.edgeThreshold(0) - 110) < 0.01f && fabsf(u.edgeThreshold(1) - 110) < 0.01f, "implausible stored baseline ignored");
    }
    // edge-ignore: readings skipped only while set; afterwards 5 fresh clear readings are needed
    {
      Safety t = s;
      SensorFrame g = f;
      t.ignoreEdges = true;
      g.laserMm[EDGE_FL] = 150;
      for (int k = 0; k < 20; k++) t.tick(g, ev, 8);
      GCHECK(!t.st.edge[0], "ignored during a leg phase");
      GCHECK(!t.edgeRecheckOk(), "no glide right after a leg phase");
      t.ignoreEdges = false;
      g.laserMm[EDGE_FL] = 94;
      for (int k = 0; k < 4; k++) t.tick(g, ev, 8);
      GCHECK(!t.edgeRecheckOk(), "4 readings are not enough");
      t.tick(g, ev, 8);
      GCHECK(t.edgeRecheckOk(), "5 fresh clear readings allow the glide");
      g.laserOk[EDGE_REAR] = false;
      t.tick(g, ev, 8);
      GCHECK(!t.edgeRecheckOk(), "a missing laser never allows a glide");
    }
  }

  // 3. day-1 balance calibration on the nominal robot
  GaitTrims nominal;
  {
    Sim s;
    bool ok = s.calibrate();
    const GaitTrims& tr = s.c.gait.trims;
    GCHECK(ok, "calibration passes on the nominal robot (%s: %s)", gaitResultName(s.c.gait.status().result), s.c.gait.status().why);
    GCHECK(tr.calibrated && tr.tiltOk[0] && tr.tiltOk[1] && tr.rearOk, "calibration flags");
    GCHECK(fabsf(tr.lean[0]) <= 1.01f && fabsf(tr.lean[1]) <= 1.01f, "nominal lean trims small (%.1f / %.1f)", tr.lean[0], tr.lean[1]);
    GCHECK(s.c.gait.trimsDirty(), "calibration marks the trims for saving");
    GCHECK(s.c.safety.edgeCal.done, "startup laser level measurement done");
    reportInvariants(s, "calibration");
    printf("calibration: %s, %.1f s\n", s.c.gait.status().why, s.t - 3.0f);
    nominal = tr;
  }
  {  // weight 4 mm further forward than the model: the probe needs more lean, still passes
    Sim s;
    s.pl.comShiftZ = 4;
    bool ok = s.calibrate();
    GCHECK(ok, "calibration with the weight 4 mm forward (%s)", s.c.gait.status().why);
    GCHECK(s.c.gait.trims.lean[0] > nominal.lean[0], "more lean found (%.1f vs %.1f)", s.c.gait.trims.lean[0], nominal.lean[0]);
    reportInvariants(s, "calibration +4 mm");
    printf("calibration, weight 4 mm forward: lean FL %+.1f FR %+.1f deg\n", s.c.gait.trims.lean[0], s.c.gait.trims.lean[1]);
  }
  {  // hopeless robot (weight 15 mm forward): fails, walks fall back
    Sim s;
    s.pl.comShiftZ = 15;
    s.calibrate();
    GCHECK(s.c.gait.status().result == GR_CAL_FAIL && !s.c.gait.trims.tiltOk[0], "calibration fails with the weight 15 mm forward");
    const char* why = nullptr;
    GCHECK(s.c.gait.choose(GAIT_AUTO, 0, 7.9f, &why) != GAIT_TILT_STEP, "tilt-step not chosen after a failed calibration");
    reportInvariants(s, "calibration +15 mm");
  }
  {  // IMU mounted crooked / desk not level
    Sim s;
    s.deskP = 10;
    s.boot();
    s.c.calibrateBalance();
    s.runGait(30);
    GCHECK(s.c.gait.status().result == GR_CAL_FAIL, "calibration refuses a 10 deg reading");
  }

  // 4. tilt-step march on the calibrated nominal robot
  {
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.falseEdgesInLegPhase = true;  // the review's nose-up false edges: must be ignored in leg phases
    GCHECK(s.c.walk(GAIT_AUTO, 1, 8), "walk accepted");
    bool done = s.runGait(90);
    const GaitStatus& g = s.c.gait.status();
    GCHECK(done && g.result == GR_DONE, "8-step tilt-step march done (%s, %s)", gaitResultName(g.result), g.why);
    GCHECK(g.style == GAIT_TILT_STEP, "auto chose the tilt-step (%s)", gaitStyleName(g.style));
    GCHECK(g.aborts == 0, "no aborts on the nominal robot (%d: %s)", g.aborts, g.why);
    GCHECK(s.maxGapFL > 30 && s.maxGapFR > 30, "front paws really lift (FL %.0f FR %.0f mm)", s.maxGapFL, s.maxGapFR);
    GCHECK(s.maxGapBL > 8 && s.maxGapBR > 8, "back paws really lift (BL %.0f BR %.0f mm)", s.maxGapBL, s.maxGapBR);
    GCHECK(s.dist > 250 && s.dist < 400, "8 glides move the robot ~320 mm (%.0f)", s.dist);
    GCHECK(s.edgeEvents == 0, "no desk-edge event from the nose-up readings (%d)", s.edgeEvents);
    GCHECK(s.sawPhase(GP_HOLD) && s.sawPhase(GP_REAR_HOLD) && s.sawPhase(GP_GLIDE), "phases seen");
    GCHECK(s.gaitDone == 1, "EV_GAIT_DONE once");
    reportInvariants(s, "tilt-step march");
    printf("tilt-step march: 8 steps in %.1f s, %.0f mm (%.1f mm/s); paws up FL %.0f FR %.0f BL %.0f BR %.0f mm\n", s.t - 3.0f,
           s.dist, s.dist / (s.t - 3.0f), s.maxGapFL, s.maxGapFR, s.maxGapBL, s.maxGapBR);
    // the robot ends standing with the wheels powered again
    s.run(1);
    GCHECK(s.o.enabled[WHEEL_FL] && s.o.enabled[WHEEL_BR] && s.pl.maxGap() < 1, "ends standing, wheels back on");
  }
  {  // backward
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, -1, 4);
    s.runGait(60);
    GCHECK(s.c.gait.status().result == GR_DONE && s.dist < -120, "backward march (%.0f mm)", s.dist);
    reportInvariants(s, "backward");
  }

  // 5. edges: seen before a glide -> no glide, safe stand; seen during a glide -> ramped stop
  {
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 8);
    // wait for the first paw step to be under way, then put the front-left laser over an edge
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_HOLD; k++) s.step();
    s.edgeForce[0] = 9999;
    double d0 = s.dist;
    s.runGait(30);
    GCHECK(s.c.gait.status().result == GR_EDGE, "edge before the glide ends the walk (%s: %s)", gaitResultName(s.c.gait.status().result), s.c.gait.status().why);
    GCHECK(fabs(s.dist - d0) < 0.5, "no wheel motion toward the edge (%.1f mm)", s.dist - d0);
    GCHECK(s.pl.maxGap() < 1 && s.edgeEvents > 0, "paws down, edge reported");
    reportInvariants(s, "edge before glide");
  }
  {
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 8);
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_GLIDE; k++) s.step();
    for (int k = 0; k < 20; k++) s.step();  // mid-glide
    s.edgeForce[1] = 9999;
    double d0 = s.dist;
    s.runGait(30);
    GCHECK(s.c.gait.status().result == GR_EDGE, "edge during a glide ends the walk");
    GCHECK(s.dist - d0 < 20, "stops within 20 mm of the edge warning (%.1f)", s.dist - d0);
    reportInvariants(s, "edge in glide");
  }
  {  // obstacle ahead: no glide at all
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.frontObstacle = 40;
    s.c.walk(GAIT_TILT_STEP, 1, 2);
    s.runGait(40);
    GCHECK(s.c.gait.status().result == GR_EDGE && fabs(s.dist) < 0.5, "obstacle: no glide (%s)", gaitResultName(s.c.gait.status().result));
    reportInvariants(s, "obstacle");
  }
  // 6. abort paths
  {  // weight 3 mm forward with the nominal trims: the tilt stalls, the closed loop leans in 0.5 deg steps
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.pl.comShiftZ = 3;
    s.c.walk(GAIT_TILT_STEP, 1, 8);
    if (getenv("GAIT_TRACE")) {
      for (int k = 0; k < 7500 && (s.c.gait.active() || k < 3); k++) {
        s.step();
        const GaitStatus& q = s.c.gait.status();
        if (k % 5 == 0 || q.phase == GP_ABORT)
          printf("t %6.2f %-12s paw %d prog %5.2f trim %4.1f p %5.2f r %5.2f rates %6.1f %6.1f tripod %d gap %.1f\n", s.t,
                 gaitPhaseName(q.phase), q.paw, q.progress, q.trimNow, q.pitch, q.roll, s.c.gait.pitchRate(), s.c.gait.rollRate(),
                 s.pl.tripod, s.pl.maxGap());
      }
    }
    s.runGait(150);
    const GaitStatus& g = s.c.gait.status();
    GCHECK(g.result == GR_DONE || g.result == GR_ABORTED, "walk with the weight 3 mm forward ends cleanly (%s)", gaitResultName(g.result));
    GCHECK(s.c.gait.trims.lean[0] > nominal.lean[0], "learned more lean for FL (%.1f -> %.1f)", nominal.lean[0], s.c.gait.trims.lean[0]);
    GCHECK(s.maxGapFL > 30, "FL still lifts after leaning (%.0f mm)", s.maxGapFL);
    reportInvariants(s, "weight 3 mm forward");
    printf("weight 3 mm forward: FL lean %.1f -> %.1f deg, %d abort(s), result %s (%s)\n", nominal.lean[0], s.c.gait.trims.lean[0],
           g.aborts, gaitResultName(g.result), g.why);
  }
  {  // weight 8 mm forward: no lift-off inside the lean limit -> graceful aborts, twice -> rear-step walk
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.pl.comShiftZ = 8;
    s.c.walk(GAIT_TILT_STEP, 1, 12);
    s.runGait(200);
    const GaitStatus& g = s.c.gait.status();
    GCHECK(g.aborts >= 2, "stalled lifts abort (%d)", g.aborts);
    GCHECK(g.style == GAIT_REAR_STEP || g.style == GAIT_MARCH, "falls back after two aborts of one paw (%s)", gaitStyleName(g.style));
    GCHECK(g.result == GR_DONE, "the walk still finishes (%s: %s)", gaitResultName(g.result), g.why);
    GCHECK(s.maxGapFL < 12, "FL never lifted high on a robot that cannot (%.1f mm)", s.maxGapFL);
    reportInvariants(s, "weight 8 mm forward");
    printf("weight 8 mm forward: %d aborts, fell back to %s (%s)\n", g.aborts, gaitStyleName(g.style), g.why);
  }
  {  // a tip trend while the paw is up (a shove): fast abort, paw down, walk ends
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 4);
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_HOLD; k++) s.step();
    for (int k = 0; k < 10; k++) { s.biasR -= 0.6f; s.step(); }  // 30 deg/s roll toward the lifted side
    s.runGait(20);
    GCHECK(s.c.gait.status().result == GR_ABORTED, "fast abort on a 30 deg/s roll (%s: %s)", gaitResultName(s.c.gait.status().result), s.c.gait.status().why);
    GCHECK(s.pl.maxGap() < 1, "paws down after the abort");
    reportInvariants(s, "tip abort");
  }
  {  // the paw reloads (body tilts back toward it by 1.5 deg, slowly): graceful abort, walk continues
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 2);
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_HOLD; k++) s.step();
    for (int k = 0; k < 15; k++) { s.biasP -= 0.1f; s.biasR += 0.05f; s.step(); }
    s.biasP = 0; s.biasR = 0;
    s.runGait(40);
    const GaitStatus& g = s.c.gait.status();
    GCHECK(g.aborts >= 1 && g.result == GR_DONE, "reloading paw: graceful abort, walk goes on (%d, %s, %s)", g.aborts, gaitResultName(g.result), g.why);
    reportInvariants(s, "reload abort");
  }

  // 7. sag: the real robot tilts 1 deg more than predicted at the nominal lean -> the loop removes lean
  {
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.sagGain = 1.0f;
    s.sagTrue = nominal.lean[0] - 1.0f;  // correct trim is 1 deg less lean
    s.c.walk(GAIT_TILT_STEP, 1, 1);
    float minTrim = 99;
    for (int k = 0; k < 5000 && s.c.gait.active(); k++) { s.step(); if (s.c.gait.status().phase == GP_HOLD) minTrim = std::min(minTrim, s.c.gait.status().trimNow); }
    GCHECK(s.c.gait.status().result == GR_DONE && s.c.gait.status().aborts == 0, "sag loop converges (%s)", s.c.gait.status().why);
    GCHECK(minTrim <= nominal.lean[0] - 0.49f, "lean reduced in the hold (%.1f -> %.1f)", nominal.lean[0], minTrim);
    GCHECK(s.c.gait.trims.lean[0] < nominal.lean[0], "learned less lean (%.1f)", s.c.gait.trims.lean[0]);
    reportInvariants(s, "sag loop");
    // wrong loop sign against this robot: never matches, times out, paw put down (graceful)
    Sim w;
    w.boot();
    w.c.gait.trims = nominal;
    w.c.gait.cfg.leanLoopSign = -1;
    w.sagGain = 1.0f;
    w.sagTrue = nominal.lean[0] - 1.0f;
    w.c.walk(GAIT_TILT_STEP, 1, 1);
    w.runGait(40);
    GCHECK(w.c.gait.status().aborts >= 1, "a lean that never matches aborts (%s)", w.c.gait.status().why);
    reportInvariants(w, "sag wrong sign");
  }

  // 8. conditions and fallbacks
  {
    Gait g;
    g.trims = nominal;
    const char* why = nullptr;
    GCHECK(g.choose(GAIT_AUTO, 0.5f, 7.9f, &why) == GAIT_TILT_STEP, "calibrated, level: tilt-step");
    GCHECK(g.choose(GAIT_AUTO, 4.0f, 7.9f, &why) == GAIT_REAR_STEP, "desk tilted 4 deg: rear-step (%s)", why);
    GCHECK(g.choose(GAIT_AUTO, 0, 7.3f, &why) == GAIT_MARCH, "battery 7.3 V: march (%s)", why);
    GCHECK(g.choose(GAIT_MARCH, 0, 7.9f, &why) == GAIT_MARCH, "march on request");
    Gait u;
    GCHECK(u.choose(GAIT_TILT_STEP, 0, 7.9f, &why) == GAIT_REAR_STEP, "uncalibrated: rear-step (%s)", why);
    u.trims.calibrated = true;
    GCHECK(u.choose(GAIT_REAR_STEP, 0, 7.9f, &why) == GAIT_MARCH, "rear lift failed calibration: march");
  }
  {  // desk tilted 4 deg nose-down: only back paws lift
    Sim s;
    s.deskP = -4;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_AUTO, 1, 4);
    s.runGait(60);
    GCHECK(s.c.gait.status().style == GAIT_REAR_STEP && s.maxGapFL < 1 && s.maxGapFR < 1 && s.maxGapBR > 8, "tilted desk: rear-step only");
    reportInvariants(s, "tilted desk");
  }
  {  // uncalibrated: rear-step walk; give paw refused
    Sim s;
    s.boot();
    s.c.walk(GAIT_AUTO, 1, 4);
    s.runGait(60);
    GCHECK(s.c.gait.status().style == GAIT_REAR_STEP && s.c.gait.status().result == GR_DONE && s.maxGapFL < 1, "uncalibrated: rear-step");
    GCHECK(s.maxGapBR > 8 && s.maxGapBL > 8, "rear-step lifts both back paws (%.0f / %.0f)", s.maxGapBR, s.maxGapBL);
    reportInvariants(s, "rear-step");
    s.c.givePaw(LEG_FL, false);
    s.runGait(10);
    GCHECK(s.c.gait.status().result == GR_REFUSED && s.maxGapFL < 1, "give paw refused before calibration (%s)", s.c.gait.status().why);
  }
  {  // low battery at rest: the march (paws stay down, wheels roll, lasers live)
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.volts = 7.3f;
    s.c.walk(GAIT_AUTO, 1, 4);
    bool ignored = false;
    for (int k = 0; k < 3000 && (s.c.gait.active() || k < 3); k++) { s.step(); ignored |= s.c.safety.ignoreEdges; }
    GCHECK(s.c.gait.status().style == GAIT_MARCH && s.c.gait.status().result == GR_DONE, "low battery: march (%s)", gaitStyleName(s.c.gait.status().style));
    GCHECK(s.pl.maxGap() < 1 && s.maxGapFL < 1.5 && s.maxGapBR < 1.5, "march keeps the paws on the desk (%.2f mm)", std::max(s.maxGapFL, s.maxGapBR));
    GCHECK(!ignored, "the march never ignores the desk-edge lasers");
    GCHECK(s.dist > 130 && s.dist < 190, "march covers ~160 mm (%.0f)", s.dist);
    reportInvariants(s, "march");
    // an edge during the march stops it
    Sim e;
    e.boot();
    e.c.walk(GAIT_MARCH, 1, 8);
    e.run(2.0f);
    e.edgeForce[0] = 9999;
    double d0 = e.dist;
    e.runGait(10);
    GCHECK(e.c.gait.status().result == GR_EDGE && e.dist - d0 < 20, "march stops at an edge (%.1f mm)", e.dist - d0);
  }

  // 9. low power in a lift: the paw is finished and put down (lifted leg first), then the walk ends
  {
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 4);
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_HOLD; k++) s.step();
    s.voltsFast = 7.1f;
    s.runGait(60);
    GCHECK(s.c.gait.status().result == GR_STOPPED && s.pl.maxGap() < 1, "low power: paw down, walk stopped (%s)", gaitResultName(s.c.gait.status().result));
    reportInvariants(s, "low power");
  }
  {  // pick-up while a paw is up: cancelled at once, wheels off/stopped
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 4);
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_HOLD; k++) s.step();
    s.lifted = true;
    s.run(1.0f);
    GCHECK(!s.c.gait.active() && s.c.gait.status().result == GR_CANCELLED, "pick-up cancels the walk");
    GCHECK(s.o.angle[WHEEL_FL] == 0 && s.o.angle[WHEEL_BR] == 0, "wheels stopped");
  }
  {  // stop request in the hold: paw put down normally
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 8);
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_HOLD; k++) s.step();
    s.c.stopAll();
    s.runGait(20);
    GCHECK(s.c.gait.status().result == GR_STOPPED && s.pl.maxGap() < 1, "stop: paw down, stand");
    // the joystick during a walk ends it too; a body sequence during a walk is refused
    Sim j;
    j.boot();
    j.c.gait.trims = nominal;
    j.c.walk(GAIT_TILT_STEP, 1, 8);
    j.run(1.0f);
    GCHECK(!j.c.play("zoomies"), "body sequences wait for the walk");
    j.c.setDrive(0.5f, 0.5f, 0.3f);
    j.runGait(20);
    GCHECK(j.c.gait.status().result == GR_STOPPED, "drive command ends the walk");
    reportInvariants(j, "joystick stop");
  }

  // 10. give paw (from the stand); puppy-sit variant off by default
  {
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    GCHECK(s.c.givePaw(LEG_FL, false), "give paw accepted");
    float upT = 0;
    for (int k = 0; k < 3000 && s.c.gait.active(); k++) { s.step(); if (s.pl.gap[LEG_FL] > 35) upT += 0.02f; }
    GCHECK(s.c.gait.status().result == GR_DONE, "give paw done (%s)", s.c.gait.status().why);
    GCHECK(s.maxGapFL > 38 && upT >= 1.4f, "paw offered: %.0f mm up for %.1f s", s.maxGapFL, upT);
    reportInvariants(s, "give paw");
    printf("give paw (stand): paw %.0f mm up for %.1f s\n", s.maxGapFL, upT);
    Sim r;
    r.boot();
    r.c.gait.trims = nominal;
    r.c.givePaw(LEG_FR, true);
    r.runGait(30);
    GCHECK(r.c.gait.status().result == GR_DONE && r.maxGapFR > 38 && r.maxGapFR < 50, "puppy-sit off: paw from the stand (%.0f mm, %s)", r.maxGapFR, r.c.gait.status().why);
    Sim q;
    q.boot();
    q.c.gait.trims = nominal;
    q.c.gait.cfg.puppySitPaw = true;
    q.c.givePaw(LEG_FL, true);
    q.runGait(30);
    GCHECK(q.c.gait.status().result == GR_DONE && q.maxGapFL > 50, "puppy-sit paw when enabled (%.0f mm)", q.maxGapFL);
    reportInvariants(q, "puppy paw");
  }

  // 10b. day-1 lift test: allowed before the calibration, holds the march's lift pose as long as asked
  {
    Sim s;
    s.boot();
    GCHECK(s.c.liftTest(LEG_FR, 5), "lift test accepted before calibration");
    float upT = 0;
    for (int k = 0; k < 3000 && s.c.gait.active(); k++) { s.step(); if (s.pl.gap[LEG_FR] > 35) upT += 0.02f; }
    GCHECK(s.c.gait.status().result == GR_DONE && upT >= 4.9f && s.maxGapFR < 50, "lift test: FR %.0f mm up for %.1f s", s.maxGapFR, upT);
    reportInvariants(s, "lift test");
  }

  // 11. brown-out dip during a step: the gait clock pauses with the frozen joints
  {
    Sim s;
    s.boot();
    s.c.gait.trims = nominal;
    s.c.walk(GAIT_TILT_STEP, 1, 1);
    for (int k = 0; k < 3000 && s.c.gait.status().phase != GP_TILT; k++) s.step();
    s.voltsFast = 6.4f;
    s.step();
    s.voltsFast = -1;
    s.runGait(40);
    reportInvariants(s, "dip");
  }

  printf("gait test: %s (%d failure%s)\n", gfails ? "FAILED" : "ok", gfails, gfails == 1 ? "" : "s");
  return gfails ? 1 : 0;
}
