// spike_body.cpp -- see spike_body.h.
#include "spike_body.h"
#include <math.h>
#include <string.h>

namespace spike {
namespace body {

// Guide wiring table (guide/src/data_wiring.py SERVO_CH) -- the owner wires exactly this.
const ServoMap kServoMap[JOINT_COUNT] = {
    {"hip front-left", 0, 0, false},   {"knee front-left", 0, 1, false},  {"wheel front-left", 0, 2, true},
    {"hip back-left", 0, 4, false},    {"knee back-left", 0, 5, false},   {"wheel back-left", 0, 6, true},
    {"tail", 0, 8, false},
    {"hip front-right", 1, 0, false},  {"knee front-right", 1, 1, false}, {"wheel front-right", 1, 2, true},
    {"hip back-right", 1, 4, false},   {"knee back-right", 1, 5, false},  {"wheel back-right", 1, 6, true},
};

// guide LASER_CH: XSHUT on servo board B channels 9..15. Each gets its own address at boot.
const LaserMap kLaserMap[LASER_COUNT] = {
    {"front obstacle", 9, 0x30},  {"rear obstacle", 10, 0x31}, {"desk edge front-left", 11, 0x32},
    {"desk edge front-right", 12, 0x33}, {"desk edge rear", 13, 0x34}, {"side left", 14, 0x35},
    {"side right", 15, 0x36},
};

void Calibration::setDefaults() {
  version = 1;
  for (int j = 0; j < JOINT_COUNT; j++) {
    ServoCal& c = servo[j];
    bool right = kServoMap[j].board == 1;
    c.centerUs = 1500;
    // Mirrored legs: a servo on the right wall turns the other way for "foot forward". Verify each
    // with the servo test on day 1 and flip `dir` in the calibration if a joint moves backwards.
    c.dir = right ? -1 : 1;
    c.usPerDeg = kServoMap[j].wheel ? 300.0f : 1000.0f / 90.0f;  // wheels: us at full speed
    c.minUs = 600;
    c.maxUs = 2400;
  }
}

bool Calibration::valid() const {
  if (version != 1) return false;
  for (int j = 0; j < JOINT_COUNT; j++) {
    const ServoCal& c = servo[j];
    if (c.centerUs < 1000 || c.centerUs > 2000 || (c.dir != 1 && c.dir != -1)) return false;
    if (!(c.usPerDeg > 1 && c.usPerDeg < 600) || c.minUs < 400 || c.maxUs > 2600 || c.minUs >= c.maxUs) return false;
  }
  return true;
}

static inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

bool limitLeg(Leg leg, float* hip, float* knee) {
  float h0 = *hip, k0 = *knee;
  if (!(*hip == *hip)) *hip = 0;
  if (!(*knee == *knee)) *knee = 0;
  *hip = clampf(*hip, HIP_MIN, HIP_MAX);
  *knee = clampf(*knee, KNEE_MIN, KNEE_MAX);
  // CAD v3.1: rear paw pod comes within 0.9 mm of the belly at hip +30 / knee +50; keep 2 mm.
  if ((leg == LEG_BL || leg == LEG_BR) && *hip > REAR_HIP_RULE && *knee > REAR_KNEE_CAP) *knee = REAR_KNEE_CAP;
  return *hip != h0 || *knee != k0;
}

// ---- poses: FL FR BL BR. A "crouch" is hip +a / knee -2a (front) or hip -a / knee +2a (rear): the
// foot stays under the hip while the body lowers. Loads from cad/servo_load_check_v3_1.md (983 g):
//   stand ~0.01 kg.cm, sit rear knees 0.43, lean 0.33 -- all inside the 0.63 kg.cm all-day hold limit.
//   lie: the old deep lie (hip 25 / knee -50) held the knees at 0.51 kg.cm for whole naps; it is now the
//        report's shallow sleepy lie (hip 12 / knee -24), which roughly halves the knee load.
//   play bow: 20 / -40 instead of 25 / -50 (front knees 0.65 -> ~0.53 kg.cm, inside the hold limit).
//   park (battery cut, before the servos go off): straight legs, which cost almost nothing to hold.
// First guesses for the look; tune on the real robot.
static const Pose POSES[POSE_COUNT] = {
    /* stand      */ {{0, 0, 0, 0}, {0, 0, 0, 0}, 0},
    /* sit        */ {{-4, -4, -25, -25}, {0, 0, 50, 50}, 0},
    /* lie        */ {{12, 12, -12, -12}, {-24, -24, 24, 24}, 0},
    /* play bow   */ {{20, 20, 0, 0}, {-40, -40, 0, 0}, 15},
    /* lean left  */ {{14, 0, -14, 0}, {-28, 0, 28, 0}, 0},
    /* lean right */ {{0, 14, 0, -14}, {0, -28, 0, 28}, 0},
    /* lean fwd   */ {{14, 14, 0, 0}, {-28, -28, 0, 0}, 0},
    /* park       */ {{0, 0, 0, 0}, {0, 0, 0, 0}, 0},
};
static const char* const POSE_NAMES[POSE_COUNT] = {"stand", "sit", "lie", "play-bow", "lean-left", "lean-right",
                                                   "lean-forward", "park"};

const Pose& pose(PoseId id) { return POSES[id < POSE_COUNT ? id : POSE_STAND]; }
const char* poseName(PoseId id) { return POSE_NAMES[id < POSE_COUNT ? id : 0]; }

Pose blend(const Pose& a, const Pose& b, float t) {
  Pose p;
  for (int i = 0; i < LEG_COUNT; i++) {
    p.hip[i] = a.hip[i] + (b.hip[i] - a.hip[i]) * t;
    p.knee[i] = a.knee[i] + (b.knee[i] - a.knee[i]) * t;
  }
  p.tail = a.tail + (b.tail - a.tail) * t;
  return p;
}

// ---- motion sequences, timed to the steps of face_v2/actions.js -----------------------------
#define K(t, pose, mv, tail, hz, amp, drv, spd) {t, pose, mv, tail, hz, amp, drv, spd}
static const Keyframe SEQ_WAKE[] = {
    K(0, POSE_LIE, 0.6f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(1.9f, POSE_STAND, 0.9f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0),
    K(3.25f, POSE_STAND, 0.2f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0)};
static const Keyframe SEQ_SLEEP[] = {
    K(0, POSE_SIT, 1.0f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(2.35f, POSE_LIE, 1.5f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_NAP[] = {
    K(0, POSE_LIE, 0.8f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(1.6f, POSE_LIE, 0.3f, TAIL_SLOW_WAG, 0.8f, 10, DRIVE_NONE, 0),
    K(2.3f, POSE_LIE, 0.3f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_DOZE[] = {
    K(0, POSE_SIT, 0.6f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(0.6f, POSE_LEAN_FORWARD, 0.9f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0),
    K(1.5f, POSE_SIT, 0.15f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(2.55f, POSE_LEAN_FORWARD, 1.0f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0),
    K(3.55f, POSE_SIT, 0.15f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_DREAM[] = {
    K(0, POSE_LIE, 0.8f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(2.0f, POSE_LIE, 0.3f, TAIL_SLOW_WAG, 1.2f, 12, DRIVE_NONE, 0),
    K(3.8f, POSE_LIE, 0.3f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_TRIP[] = {
    K(0, POSE_STAND, 0.2f, TAIL_UP, 0, 0, DRIVE_NONE, 0), K(0.25f, POSE_LEAN_LEFT, 0.15f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0),
    K(0.47f, POSE_STAND, 0.6f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_SNEEZE[] = {
    K(0, POSE_STAND, 0.3f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0), K(0.95f, POSE_LEAN_FORWARD, 0.1f, TAIL_UP, 0, 0, DRIVE_NONE, 0),
    K(1.25f, POSE_STAND, 0.3f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_HICCUP[] = {
    K(0.45f, POSE_LEAN_FORWARD, 0.08f, TAIL_UP, 0, 0, DRIVE_NONE, 0), K(0.6f, POSE_STAND, 0.2f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0),
    K(1.3f, POSE_LEAN_FORWARD, 0.08f, TAIL_UP, 0, 0, DRIVE_NONE, 0), K(1.45f, POSE_STAND, 0.2f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0),
    K(2.15f, POSE_LEAN_FORWARD, 0.08f, TAIL_UP, 0, 0, DRIVE_NONE, 0), K(2.3f, POSE_STAND, 0.2f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_SHIVER[] = {
    K(0, POSE_LEAN_LEFT, 0.08f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(0.12f, POSE_LEAN_RIGHT, 0.1f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0),
    K(0.26f, POSE_LEAN_LEFT, 0.1f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(0.40f, POSE_LEAN_RIGHT, 0.1f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0),
    K(0.54f, POSE_LEAN_LEFT, 0.1f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(0.68f, POSE_LEAN_RIGHT, 0.1f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0),
    K(0.82f, POSE_STAND, 0.3f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_PANT[] = {K(0, POSE_SIT, 0.6f, TAIL_SLOW_WAG, 1.0f, 15, DRIVE_NONE, 0)};
// Turning in place scrubs the tyres and loads every hip with ~1 kg.cm (servo load check): the spins are
// short bursts (<= 0.5 s) with rests, at a reduced turn speed. The Controller enforces the same limits.
static const Keyframe SEQ_DANCE[] = {
    K(0, POSE_STAND, 0.3f, TAIL_WAG, 3.0f, 30, DRIVE_WIGGLE, 0.35f), K(0.5f, POSE_STAND, 0.3f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0),
    K(1.2f, POSE_PLAY_BOW, 0.3f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0), K(1.8f, POSE_STAND, 0.3f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0)};
static const Keyframe SEQ_ZOOMIES[] = {
    K(0, POSE_STAND, 0.2f, TAIL_WAG, 4.0f, 22, DRIVE_SPIN, 0.4f), K(0.5f, POSE_STAND, 0.2f, TAIL_WAG, 4.0f, 22, DRIVE_NONE, 0),
    K(0.9f, POSE_STAND, 0.2f, TAIL_WAG, 4.0f, 22, DRIVE_SPIN, 0.4f), K(1.4f, POSE_STAND, 0.3f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0)};
static const Keyframe SEQ_HEAD_TILT[] = {
    K(0, POSE_LEAN_LEFT, 0.4f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0), K(1.3f, POSE_LEAN_RIGHT, 0.5f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_SNIFF[] = {
    K(0, POSE_LEAN_FORWARD, 0.4f, TAIL_SLOW_WAG, 1.5f, 10, DRIVE_NONE, 0), K(0.9f, POSE_LEAN_LEFT, 0.4f, TAIL_SLOW_WAG, 1.5f, 10, DRIVE_NONE, 0),
    K(1.8f, POSE_STAND, 0.4f, TAIL_UP, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_BEG[] = {K(0, POSE_SIT, 0.6f, TAIL_SLOW_WAG, 1.2f, 20, DRIVE_NONE, 0)};
static const Keyframe SEQ_ROLL[] = {
    K(0, POSE_STAND, 0.2f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0), K(0.3f, POSE_LIE, 0.5f, TAIL_WAG, 2.5f, 25, DRIVE_NONE, 0),
    K(1.3f, POSE_STAND, 0.6f, TAIL_WAG, 2.5f, 25, DRIVE_NONE, 0)};
static const Keyframe SEQ_BOW[] = {
    K(0, POSE_PLAY_BOW, 0.4f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0), K(1.2f, POSE_STAND, 0.3f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0)};
static const Keyframe SEQ_YAWN[] = {
    K(0, POSE_LEAN_FORWARD, 0.6f, TAIL_DOWN, 0, 0, DRIVE_NONE, 0), K(1.4f, POSE_STAND, 0.4f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_BOOP[] = {
    K(0, POSE_SIT, 0.15f, TAIL_UP, 0, 0, DRIVE_NONE, 0), K(0.6f, POSE_STAND, 0.4f, TAIL_WAG, 3.0f, 30, DRIVE_NONE, 0)};
static const Keyframe SEQ_SNUGGLE[] = {
    K(0, POSE_LEAN_FORWARD, 1.0f, TAIL_SLOW_WAG, 0.6f, 15, DRIVE_NONE, 0), K(2.6f, POSE_STAND, 1.0f, TAIL_HOLD, 0, 0, DRIVE_NONE, 0)};
static const Keyframe SEQ_SLOW_WAG[] = {K(0, POSE_STAND, 0.5f, TAIL_SLOW_WAG, 0.67f, 30, DRIVE_NONE, 0)};
#undef K

#define S(label, arr, len) {label, arr, (uint8_t)(sizeof(arr) / sizeof(arr[0])), len}
static const Sequence SEQS[] = {
    S("wake-up", SEQ_WAKE, 4.15f), S("fall-asleep", SEQ_SLEEP, 5.15f), S("nap", SEQ_NAP, 3.7f),
    S("doze", SEQ_DOZE, 4.7f), S("dream", SEQ_DREAM, 5.8f), S("trip", SEQ_TRIP, 3.37f),
    S("sneeze", SEQ_SNEEZE, 2.45f), S("hiccup", SEQ_HICCUP, 3.0f), S("shiver", SEQ_SHIVER, 1.9f),
    S("pant", SEQ_PANT, 2.3f), S("happy-dance", SEQ_DANCE, 2.4f), S("zoomies", SEQ_ZOOMIES, 2.3f),
    S("head-tilt", SEQ_HEAD_TILT, 2.4f), S("sniff", SEQ_SNIFF, 2.7f), S("beg", SEQ_BEG, 2.3f),
    S("roll-over", SEQ_ROLL, 2.3f), S("play-bow", SEQ_BOW, 2.1f), S("yawn", SEQ_YAWN, 1.8f),
    S("boop", SEQ_BOOP, 2.1f), S("snuggle", SEQ_SNUGGLE, 3.6f), S("slowWag", SEQ_SLOW_WAG, 2.25f),
};
#undef S

const Sequence* findSequence(const char* label) {
  if (!label) return nullptr;
  for (const Sequence& s : SEQS) if (strcmp(s.label, label) == 0) return &s;
  return nullptr;
}
int sequenceCount() { return (int)(sizeof(SEQS) / sizeof(SEQS[0])); }
const Sequence& sequenceAt(int i) { return SEQS[i]; }

// ---- safety ---------------------------------------------------------------------------------
int Safety::tick(const SensorFrame& f, SafetyEvent* ev, int maxEv) {
  int n = 0;
  auto emit = [&](SafetyEvent e) { if (n < maxEv) ev[n++] = e; };
  float dt = f.dt > 0 ? f.dt : 0.02f;

  static const Laser EDGE_LASER[3] = {EDGE_FL, EDGE_FR, EDGE_REAR};
  static const SafetyEvent ON[3] = {EV_EDGE_FL, EV_EDGE_FR, EV_EDGE_REAR};
  static const SafetyEvent OFF[3] = {EV_CLEAR_FL, EV_CLEAR_FR, EV_CLEAR_REAR};

  // body tilt (edge-threshold compensation, startup level check)
  if (f.imuOk) {
    float p = atan2f(f.ax, f.az) * 57.29578f, r = atan2f(-f.ay, f.az) * 57.29578f;
    if (!tiltInit_) { st.pitchDeg = p; st.rollDeg = r; tiltInit_ = true; }
    else {
      float a = clampf(dt / 0.1f, 0, 1);
      st.pitchDeg += (p - st.pitchDeg) * a;
      st.rollDeg += (r - st.rollDeg) * a;
    }
  }

  // startup level measurement of the desk-edge lasers: standing still and level for laser.calSeconds,
  // every present laser steady and plausible -> threshold = that reading (tilt-compensated) + margin
  if (!edgeCal.done) {
    const EdgeLaserConfig& L = cfg.laser;
    bool still = f.imuOk && tiltInit_ && fabsf(st.pitchDeg) < L.maxLevelTiltDeg && fabsf(st.rollDeg) < L.maxLevelTiltDeg &&
                 (!f.gyroOk || (fabsf(f.gx) < L.maxRateDps && fabsf(f.gy) < L.maxRateDps && fabsf(f.gz) < L.maxRateDps)) &&
                 standing && !ignoreEdges && !st.pickedUp && !st.fallen;
    if (!still) calReset();
    else {
      calT_ += dt;
      calSumP_ += st.pitchDeg;
      calSumR_ += st.rollDeg;
      calTiltN_++;
      for (int i = 0; i < 3; i++) {
        Laser l = EDGE_LASER[i];
        if (!f.laserOk[l] || f.laserMm[l] < 0) continue;
        float v = f.laserMm[l];
        if (calN_[i] == 0) calMin_[i] = calMax_[i] = v;
        if (v < calMin_[i]) calMin_[i] = v;
        if (v > calMax_[i]) calMax_[i] = v;
        calSum_[i] += v;
        calN_[i]++;
      }
      if (calT_ >= L.calSeconds) {
        bool all = true, any = false, okNow[3] = {false, false, false};
        float mean[3] = {0, 0, 0};
        for (int i = 0; i < 3; i++) {
          if (!f.laserOk[EDGE_LASER[i]]) continue;  // missing: an edge anyway (fail-safe)
          mean[i] = calN_[i] ? calSum_[i] / calN_[i] : 0;
          okNow[i] = calN_[i] >= 5 && calMax_[i] - calMin_[i] <= L.maxSpreadMm && mean[i] >= L.minBaselineMm &&
                     mean[i] <= L.maxBaselineMm;
          if (okNow[i]) any = true; else all = false;
        }
        if (all && any) {
          for (int i = 0; i < 3; i++) if (okNow[i]) { edgeCal.fresh[i] = edgeCal.ok[i] = true; edgeCal.baseline[i] = mean[i]; }
          edgeCal.refPitch = calSumP_ / calTiltN_;
          edgeCal.refRoll = calSumR_ / calTiltN_;
          edgeCal.done = true;
          emit(EV_EDGE_CALIBRATED);
        }
        calReset();
      }
    }
  }

  // desk edges (fail-safe: a missing desk-edge sensor counts as an edge). Skipped while a gait leg phase
  // has the wheels PWM-off (the Controller only sets ignoreEdges then); every glide needs fresh readings.
  for (int i = 0; i < 3; i++) {
    Laser l = EDGE_LASER[i];
    lastOk_[i] = f.laserOk[l];
    if (ignoreEdges) { freshClear_[i] = 0; continue; }
    bool far;
    if (!f.laserOk[l]) far = true;
    else if (f.laserMm[l] < 0) continue;  // no new reading this tick
    else far = f.laserMm[l] > edgeThreshold(i);
    if (far) {
      clearCount_[i] = 0;
      freshClear_[i] = 0;
      if (edgeCount_[i] < 255) edgeCount_[i]++;
      if (!st.edge[i] && edgeCount_[i] >= cfg.edgeConfirm) { st.edge[i] = true; emit(ON[i]); }
    } else {
      edgeCount_[i] = 0;
      if (clearCount_[i] < 255) clearCount_[i]++;
      if (freshClear_[i] < 255) freshClear_[i]++;
      if (st.edge[i] && clearCount_[i] >= cfg.clearConfirm) { st.edge[i] = false; emit(OFF[i]); }
    }
  }

  // pick-up: every desk-edge laser sees "no desk" at once (lifted), or a sustained g change
  bool allFar = st.edge[0] && st.edge[1] && st.edge[2] && f.laserOk[EDGE_FL] && f.laserOk[EDGE_FR] && f.laserOk[EDGE_REAR];
  bool gOff = false;
  if (f.imuOk) {
    float g = sqrtf(f.ax * f.ax + f.ay * f.ay + f.az * f.az);
    gLp_ += (g - gLp_) * clampf(dt / 0.15f, 0, 1);
    gOff = fabsf(gLp_ - 1.0f) > cfg.pickupG;
    float c = g > 0.2f ? clampf(f.az / g, -1, 1) : 1;
    st.tiltDeg = acosf(c) * 57.29578f;
    if (!st.fallen && st.tiltDeg > cfg.fallTiltDeg && !st.pickedUp) { st.fallen = true; emit(EV_FALL); }
    else if (st.fallen && st.tiltDeg < 30) st.fallen = false;
  }
  if (!st.pickedUp) {
    pickupTimer_ = (allFar || gOff) ? pickupTimer_ + dt : 0;
    if (pickupTimer_ >= cfg.pickupHoldS) { st.pickedUp = true; calmTimer_ = 0; emit(EV_PICKUP); }
  } else {
    calmTimer_ = (!allFar && !gOff) ? calmTimer_ + dt : 0;
    if (calmTimer_ >= 0.6f) { st.pickedUp = false; pickupTimer_ = 0; emit(EV_PUTDOWN); }
  }

  // battery: warn at 7.0 V, park + cut at 6.8 V held for cutHoldS (servo current sags the pack);
  // the cut latches until reboot (the pack needs charging).
  if (f.volts > 0) {
    if (!st.battWarn && f.volts < cfg.warnVolts) { st.battWarn = true; emit(EV_BATTERY_WARN); }
    else if (st.battWarn && !st.battCut && f.volts > cfg.resumeVolts) { st.battWarn = false; emit(EV_BATTERY_OK); }
    lowTimer_ = f.volts < cfg.cutVolts ? lowTimer_ + dt : 0;
    if (!st.battCut && lowTimer_ >= cfg.cutHoldS) { st.battCut = true; emit(EV_BATTERY_CUT); }
    st.lowSince = lowTimer_;
  }

  bool frontObst = f.laserOk[LASER_FRONT] && f.laserMm[LASER_FRONT] >= 0 && f.laserMm[LASER_FRONT] < cfg.obstacleMm;
  bool rearObst = f.laserOk[LASER_REAR] && f.laserMm[LASER_REAR] >= 0 && f.laserMm[LASER_REAR] < cfg.obstacleMm;
  bool stop = st.fallen || st.pickedUp || st.battCut;
  st.blockFwd = stop || st.edge[0] || st.edge[1] || frontObst;
  st.blockBack = stop || st.edge[2] || rearObst;
  return n;
}

void Safety::filterDrive(float* left, float* right) const {
  if (st.blockFwd) { if (*left > 0) *left = 0; if (*right > 0) *right = 0; }
  if (st.blockBack) { if (*left < 0) *left = 0; if (*right < 0) *right = 0; }
}

void Safety::calReset() {
  calT_ = 0;
  calSumP_ = calSumR_ = 0;
  calTiltN_ = 0;
  for (int i = 0; i < 3; i++) { calSum_[i] = 0; calN_[i] = 0; }
}

void Safety::useStoredBaseline(const float mm[3], const bool ok[3], float refPitch, float refRoll) {
  if (edgeCal.done) return;  // this boot's own measurement wins
  const EdgeLaserConfig& L = cfg.laser;
  for (int i = 0; i < 3; i++) {
    edgeCal.ok[i] = ok[i] && mm[i] >= L.minBaselineMm && mm[i] <= L.maxBaselineMm;
    edgeCal.fresh[i] = false;
    edgeCal.baseline[i] = mm[i];
  }
  edgeCal.refPitch = refPitch;
  edgeCal.refRoll = refRoll;
}

// Expected level reading at the current tilt (review geometry: laser ~85 mm up, beam 65 deg down; nose-up
// raises the front lasers and flattens their beams) + the margin. Without a level reading: 110 mm.
float Safety::edgeThreshold(int i) const {
  const EdgeLaserConfig& L = cfg.laser;
  if (i < 0 || i > 2 || !edgeCal.ok[i]) return L.fallbackMm;
  const float RAD = 0.01745329252f;
  float p = tiltInit_ ? clampf(st.pitchDeg - edgeCal.refPitch, -L.maxCompDeg, L.maxCompDeg) * RAD : 0;
  float r = tiltInit_ ? clampf(st.rollDeg - edgeCal.refRoll, -L.maxCompDeg, L.maxCompDeg) * RAD : 0;
  float a0 = L.beamDownDeg * RAD;
  float h = edgeCal.baseline[i] * sinf(a0), a;
  if (i < 2) {
    float lat = i == 0 ? L.lateralMm : -L.lateralMm;  // + roll = left side lower
    h += L.leverFrontMm * sinf(p) - lat * sinf(r);
    a = a0 - p;
  } else {
    h -= L.leverRearMm * sinf(p);
    a = a0 + p;
  }
  a = clampf(a, 20 * RAD, 89 * RAD);
  float th = h / sinf(a) + L.marginMm;
  return th > L.maxThresholdMm ? L.maxThresholdMm : th;
}

bool Safety::edgeRecheckOk() const {
  for (int i = 0; i < 3; i++)
    if (!lastOk_[i] || st.edge[i] || freshClear_[i] < cfg.laser.recheckReadings) return false;
  return true;
}

// ---- controller -----------------------------------------------------------------------------
Controller::Controller() {
  cal.setDefaults();
  cur_ = pose(POSE_STAND);
  from_ = cur_;
  out_ = cur_;
  restartPowerUp();
}

bool Controller::play(const char* label) {
  const Sequence* s = findSequence(label);
  if (!s || gait.active()) return false;  // a walk / give-paw owns the legs until it ends (face still plays)
  seq_ = s;
  seqT_ = 0;
  key_ = -1;
  return true;
}

void Controller::setPose(PoseId id, float moveS) {
  if (gait.active()) return;
  from_ = cur_;
  target_ = id;
  moveT_ = 0;
  moveS_ = moveS > 0.001f ? moveS : 0.001f;
}

void Controller::setDrive(float left, float right, float seconds) {
  if (gait.active()) {  // the joystick during a walk: end the walk gracefully (paw down), then drive
    if (left != 0 || right != 0) gait.stop();
    return;
  }
  manualL_ = clampf(left, -1, 1);
  manualR_ = clampf(right, -1, 1);
  manualS_ = seconds;
}

void Controller::stopAll() {
  seq_ = nullptr;
  drive_ = DRIVE_NONE;
  manualS_ = 0;
  tail_ = TAIL_HOLD;
  gait.stop();  // graceful: a lifted paw is put down first
}

bool Controller::gaitAllowed(const char** why) const {
  const char* w = nullptr;
  if (safety.st.battCut) w = "battery cut";
  else if (safety.st.fallen) w = "fallen over";
  else if (safety.st.pickedUp) w = "picked up";
  else if (lowPower_) w = "low-power mode (battery dip)";
  else if (gait.active()) w = "busy";
  if (why) *why = w;
  return w == nullptr;
}

bool Controller::walk(GaitStyle style, int direction, int steps) {
  if (!gaitAllowed(nullptr)) return false;
  seq_ = nullptr;
  drive_ = DRIVE_NONE;
  manualS_ = 0;
  gait.setStartPose(out_);
  return gait.walk(style, direction, steps);
}

bool Controller::givePaw(Leg paw, bool fromSit) {
  if (!gaitAllowed(nullptr)) return false;
  seq_ = nullptr;
  drive_ = DRIVE_NONE;
  manualS_ = 0;
  gait.setStartPose(out_);
  return gait.givePaw(paw, fromSit);
}

bool Controller::liftTest(Leg paw, float seconds) {
  if (!gaitAllowed(nullptr)) return false;
  seq_ = nullptr;
  drive_ = DRIVE_NONE;
  manualS_ = 0;
  gait.setStartPose(out_);
  return gait.liftTest(paw, seconds);
}

bool Controller::calibrateBalance() {
  if (!gaitAllowed(nullptr)) return false;
  seq_ = nullptr;
  drive_ = DRIVE_NONE;
  manualS_ = 0;
  gait.setStartPose(out_);
  return gait.calibrate();
}

int Controller::pulseUs(int j, float v) const {
  const ServoCal& c = cal.servo[j];
  float us;
  if (kServoMap[j].wheel) us = c.centerUs + c.dir * clampf(v, -1, 1) * c.usPerDeg;
  else us = c.centerUs + c.dir * v * c.usPerDeg;
  int u = (int)lroundf(us);
  return u < c.minUs ? c.minUs : (u > c.maxUs ? c.maxUs : u);
}

void Controller::restartPowerUp() {
  enabledCount_ = 0;
  staggerT_ = 0;
}

// Power-up order: legs first (hips, knees), then the tail, then the wheels (they hold the stop pulse).
static const Joint POWER_ORDER[JOINT_COUNT] = {HIP_FL, HIP_FR, HIP_BL, HIP_BR, KNEE_FL, KNEE_FR, KNEE_BL, KNEE_BR,
                                               TAIL, WHEEL_FL, WHEEL_FR, WHEEL_BL, WHEEL_BR};

static float approach(float cur, float target, float maxStep) {
  float d = target - cur;
  if (d > maxStep) return cur + maxStep;
  if (d < -maxStep) return cur - maxStep;
  return target;
}

int Controller::tick(const SensorFrame& f, BodyOutput* out, SafetyEvent* ev, int maxEv) {
  float dt = f.dt > 0 ? (f.dt > 0.1f ? 0.1f : f.dt) : 0.02f;
  int n = safety.tick(f, ev, maxEv);
  for (int i = 0; i < n; i++) {
    if (ev[i] == EV_BATTERY_CUT) { gait.cancel(); stopAll(); setPose(POSE_PARK, 1.0f); parked_ = true; }
    if (ev[i] == EV_FALL || ev[i] == EV_PICKUP) { gait.cancel(); seq_ = nullptr; drive_ = DRIVE_NONE; manualS_ = 0; }
  }
  auto emit = [&](SafetyEvent e) { if (n < maxEv) ev[n++] = e; };

  // ---- brown-out guard: react to the FAST battery reading (servo current spikes sag the pack) ----
  float vf = f.voltsFast > 0 ? f.voltsFast : f.volts;
  if (vf > 0) {
    if (!lowPower_ && vf < mcfg.lowPowerVolts) { lowPower_ = true; lowPowerOkT_ = 0; emit(EV_LOW_POWER); }
    else if (lowPower_) {
      lowPowerOkT_ = vf > mcfg.lowPowerExitVolts ? lowPowerOkT_ + dt : 0;
      if (lowPowerOkT_ >= mcfg.lowPowerExitS) { lowPower_ = false; emit(EV_POWER_OK); }
    }
    if (vf < mcfg.dipVolts) dipHold_ = mcfg.dipHoldS;
  }
  if (dipHold_ > 0) dipHold_ -= dt;

  // ---- sequence keyframes ----
  if (seq_) {
    seqT_ += dt;
    while (key_ + 1 < seq_->n && seqT_ >= seq_->keys[key_ + 1].t) {
      key_++;
      const Keyframe& k = seq_->keys[key_];
      setPose(k.pose, k.moveS);
      tail_ = k.tail;
      tailHz_ = k.tailHz;
      tailAmp_ = k.tailAmp;
      drive_ = k.drive;
      driveSpeed_ = k.driveSpeed;
      driveT_ = 0;
    }
    if (seqT_ >= seq_->length) {
      seq_ = nullptr;
      drive_ = DRIVE_NONE;
      if (tail_ == TAIL_WAG || tail_ == TAIL_SLOW_WAG) tail_ = TAIL_HOLD;
    }
  }

  // ---- walking / give-paw: the gait owns legs and wheels while it runs (spike_gait.h) ----
  {
    GaitInput gi{};
    gi.dt = dt;
    gi.imuOk = f.imuOk;
    gi.ax = f.ax; gi.ay = f.ay; gi.az = f.az;
    gi.gyroOk = f.imuOk && f.gyroOk;
    gi.gx = f.gx; gi.gy = f.gy; gi.gz = f.gz;
    gi.wheelsStopped = wheelL_ == 0 && wheelR_ == 0;
    gi.poseReached = poseReached_;
    gi.frozen = dipHold_ > 0;
    gi.lowPower = lowPower_;
    gi.legsAllowed = safety.legsAllowed();
    gi.pickedUp = safety.st.pickedUp;
    gi.outputsReady = enabledCount_ >= JOINT_COUNT;
    gi.edgeRecheckOk = safety.edgeRecheckOk();
    gi.blockFwd = safety.st.blockFwd;
    gi.blockBack = safety.st.blockBack;
    gi.restVolts = f.volts;
    gi.wheelTopSpeed = mcfg.wheelTopSpeed;
    gait.tick(gi, &gout_);
    if (gaitWasActive_ && !gait.active()) {  // ended: hold the stand from wherever the legs are
      from_ = cur_;
      target_ = POSE_STAND;
      moveT_ = 0;
      moveS_ = 0.8f;
      emit(EV_GAIT_DONE);
    }
    gaitWasActive_ = gait.active();
  }
  // Safety invariants, whatever the gait asks: wheels go PWM-off only once they have stopped, and the
  // desk-edge lasers are ignored only while the wheels are off.
  bool gaitOn = gout_.active;
  wheelsOffNow_ = gaitOn && gout_.wheelsOff && wheelL_ == 0 && wheelR_ == 0;
  safety.ignoreEdges = wheelsOffNow_ && gout_.ignoreEdges;

  // ---- pose interpolation (smoothstep), then per-joint slew limits ----
  if (gaitOn) {
    cur_ = gout_.pose;
    tail_ = TAIL_HOLD;
  } else {
    moveT_ += dt;
    float u = clampf(moveT_ / moveS_, 0, 1);
    u = u * u * (3 - 2 * u);
    cur_ = blend(from_, pose(target_), u);
  }
  if (dipHold_ <= 0) {
    if (!lowPower_) {
      float step = mcfg.jointSlewDegPerS * dt;
      for (int l = 0; l < LEG_COUNT; l++) {
        out_.hip[l] = approach(out_.hip[l], cur_.hip[l], step);
        out_.knee[l] = approach(out_.knee[l], cur_.knee[l], step);
      }
    } else {  // low power: slow, and only ONE leg moving at a time (the lifted paw's leg first, then in order)
      float step = mcfg.lowPowerSlewDegPerS * dt;
      int order[LEG_COUNT], no = 0;
      if (gaitOn && gout_.priorityLeg >= 0 && gout_.priorityLeg < LEG_COUNT) order[no++] = gout_.priorityLeg;
      for (int l = 0; l < LEG_COUNT; l++) if (no == 0 || order[0] != l) order[no++] = l;
      for (int i = 0; i < LEG_COUNT; i++) {
        int l = order[i];
        if (fabsf(out_.hip[l] - cur_.hip[l]) < 0.01f && fabsf(out_.knee[l] - cur_.knee[l]) < 0.01f) continue;
        out_.hip[l] = approach(out_.hip[l], cur_.hip[l], step);
        out_.knee[l] = approach(out_.knee[l], cur_.knee[l], step);
        break;
      }
    }
  }
  {
    float worst = 0;
    for (int l = 0; l < LEG_COUNT; l++)
      worst = fmaxf(worst, fmaxf(fabsf(out_.hip[l] - cur_.hip[l]), fabsf(out_.knee[l] - cur_.knee[l])));
    poseReached_ = worst < 0.5f;
  }
  safety.standing = !gaitOn && !seq_ && target_ == POSE_STAND && moveT_ >= moveS_ && poseReached_ &&
                    wheelL_ == 0 && wheelR_ == 0 && manualS_ <= 0;

  // ---- tail: wag amplitude capped by the servo's speed (2 pi f A <= tailMaxDegPerS) and tailMaxAmp ----
  float tail = cur_.tail;
  // The tail servo shaft is vertical (CAD: it hangs from a rib, shaft up), so the tail only swings side
  // to side: DOWN / UP hold the centre (kept as separate modes for a future tilting tail).
  if (tail_ == TAIL_DOWN || tail_ == TAIL_UP) tail = 0;
  if (tail_ == TAIL_WAG || tail_ == TAIL_SLOW_WAG) {
    float amp = tailAmp_;
    if (tailHz_ > 0) {
      float speedCap = mcfg.tailMaxDegPerS / (6.2831853f * tailHz_);
      if (amp > speedCap) amp = speedCap;
    }
    if (amp > mcfg.tailMaxAmp) amp = mcfg.tailMaxAmp;
    if (lowPower_) amp *= 0.5f;
    tailPhase_ += dt * tailHz_ * 6.2831853f;
    if (tailPhase_ > 6.2831853f) tailPhase_ -= 6.2831853f;
    tail = amp * sinf(tailPhase_);  // centred wag (the pose's tail offset is only used when holding)
  }
  tail = clampf(tail, -mcfg.tailMaxAmp, mcfg.tailMaxAmp);
  tailOut_ = approach(tailOut_, tail, mcfg.tailMaxDegPerS * dt);  // never faster than the servo can go
  tail = tailOut_;

  // ---- wheels: target, spin guard, safety filter, then the 1.5 m/s^2 ramp ----
  float left = 0, right = 0;
  bool anyBlock = safety.st.blockFwd || safety.st.blockBack;
  if (gaitOn) {  // glide / march command; the filter, low-power clamp and ramp below still apply
    left = gout_.wheelL;
    right = gout_.wheelR;
  } else if (manualS_ > 0) {
    manualS_ -= dt;
    left = manualL_;
    right = manualR_;
  } else if (drive_ != DRIVE_NONE && !anyBlock && !lowPower_) {  // playful drives only on a clear desk
    driveT_ += dt;
    float sp = driveSpeed_ < mcfg.maxSpinSpeed ? driveSpeed_ : mcfg.maxSpinSpeed;
    if (drive_ == DRIVE_SPIN) { left = sp; right = -sp; }
    else if (drive_ == DRIVE_WIGGLE) { float s = sinf(driveT_ * 6.2831853f * 2.0f) > 0 ? 1.0f : -1.0f; left = s * sp; right = -s * sp; }
  }
  bool turning = (left > 0.02f && right < -0.02f) || (left < -0.02f && right > 0.02f);
  if (turning) {  // turning in place scrubs the tyres sideways: 1 kg.cm on every hip -> short bursts only
    float cap = mcfg.maxSpinSpeed;
    left = clampf(left, -cap, cap);
    right = clampf(right, -cap, cap);
    if (spinRest_ > 0 || lowPower_) { left = 0; right = 0; }
  }
  if (lowPower_) { left = clampf(left, -0.5f, 0.5f); right = clampf(right, -0.5f, 0.5f); }
  safety.filterDrive(&left, &right);
  bool wheelsTurning = (wheelL_ > 0.02f && wheelR_ < -0.02f) || (wheelL_ < -0.02f && wheelR_ > 0.02f);
  if (wheelsTurning) {
    spinT_ += dt;
    // stop early enough that the ramp-down still ends inside the burst
    float rampDown = fmaxf(fabsf(wheelL_), fabsf(wheelR_)) * mcfg.wheelTopSpeed / mcfg.maxAccel;
    if (spinT_ + rampDown + dt >= mcfg.spinBurstS) { spinRest_ = mcfg.spinRestS + rampDown; spinT_ = 0; }
  } else {
    spinT_ = 0;
  }
  if (spinRest_ > 0) {
    spinRest_ -= dt;
    if (turning) { left = 0; right = 0; }
  }
  // Every change of wheel speed is ramped at maxAccel -- stops at a desk edge included (report: the
  // sudden stop yanks the front hips with 2.6 kg.cm; the ramp costs ~8 mm of stopping distance). Only
  // with no grip on the desk (picked up, fallen, battery cut) do the wheels stop at once.
  bool noGrip = safety.st.pickedUp || safety.st.fallen || safety.st.battCut;
  if (noGrip) { wheelL_ = 0; wheelR_ = 0; }
  else {
    float dv = mcfg.maxAccel / mcfg.wheelTopSpeed * dt;  // command units per tick (0.1875 at 50 Hz)
    wheelL_ = approach(wheelL_, left, dv);
    wheelR_ = approach(wheelR_, right, dv);
  }

  // ---- power-up stagger: one output every staggerS (boot, after OE high, after a fall) ----
  bool legsAllowed = safety.legsAllowed();
  if (legsAllowed && !wasLegsAllowed_ && !safety.st.battCut) restartPowerUp();
  wasLegsAllowed_ = legsAllowed;
  staggerT_ += dt;
  while (enabledCount_ < JOINT_COUNT && staggerT_ >= mcfg.staggerS) { staggerT_ -= mcfg.staggerS; enabledCount_++; }
  if (enabledCount_ >= JOINT_COUNT) staggerT_ = 0;

  // ---- outputs ----
  static const Joint HIP[LEG_COUNT] = {HIP_FL, HIP_FR, HIP_BL, HIP_BR};
  static const Joint KNEE[LEG_COUNT] = {KNEE_FL, KNEE_FR, KNEE_BL, KNEE_BR};
  static const Joint WHEEL[LEG_COUNT] = {WHEEL_FL, WHEEL_FR, WHEEL_BL, WHEEL_BR};
  bool legsOn = legsAllowed || (parked_ && moveT_ < moveS_ + 0.2f && !safety.st.fallen);
  for (int l = 0; l < LEG_COUNT; l++) {
    float h = out_.hip[l], k = out_.knee[l];
    limitLeg((Leg)l, &h, &k);
    out->angle[HIP[l]] = h;
    out->angle[KNEE[l]] = k;
    out->enabled[HIP[l]] = legsOn;
    out->enabled[KNEE[l]] = legsOn;
    bool leftSide = (l == LEG_FL || l == LEG_BL);
    out->angle[WHEEL[l]] = leftSide ? wheelL_ : wheelR_;
    // enabled wheel at speed 0 = the stop pulse. In a gait leg phase the wheels are PWM full-off instead
    // (review item 1: a creeping "stop" pulse can push a loaded paw; an unpowered gearbox cannot), and they
    // are switched back on one at a time before a glide.
    bool wheelOn = !safety.st.battCut;
    if (wheelsOffNow_) wheelOn = false;
    else if (gaitOn && !gout_.wheelsOff && l >= gout_.wheelsArmed) wheelOn = false;
    out->enabled[WHEEL[l]] = wheelOn;
  }
  out->angle[TAIL] = clampf(tail, TAIL_MIN, TAIL_MAX);
  out->enabled[TAIL] = legsOn;
  for (int k = enabledCount_; k < JOINT_COUNT; k++) out->enabled[POWER_ORDER[k]] = false;
  return n;
}

}  // namespace body
}  // namespace spike
