// spike_gait.cpp -- see spike_gait.h. Numbers: cad/stability_max_research.md, corrected by
// cad/stability_research_review.md; tunables: spike_gait_config.h.
#include "spike_body.h"
#include <math.h>
#include <string.h>
#include <stdio.h>

namespace spike {
namespace body {

static inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }
static inline float smooth(float u) { u = clampf(u, 0, 1); return u * u * (3 - 2 * u); }
static const float RAD = 0.01745329252f;

const char* gaitStyleName(GaitStyle s) {
  static const char* const N[] = {"auto", "tilt-step", "rear-step", "march"};
  return s < GAIT_STYLE_COUNT ? N[s] : "?";
}
const char* gaitPhaseName(GaitPhase p) {
  static const char* const N[] = {"idle", "level", "arm", "glide", "glide-settle", "settle", "shift", "tilt",
                                  "hold", "set-down", "unshift", "rear-lift", "rear-hold", "rear-down", "march",
                                  "abort", "finish"};
  return p < GP_PHASE_COUNT ? N[p] : "?";
}
const char* gaitResultName(GaitResult r) {
  static const char* const N[] = {"none", "done", "stopped", "edge", "aborted", "refused", "cancelled",
                                  "calibration passed", "calibration failed"};
  return r <= GR_CAL_FAIL ? N[r] : "?";
}

// ---- keyframes (FL FR BL BR; hip / knee deg; + = foot forward). Predicted tilt from the stand: pitch
// (+ nose up) / roll (+ left side lower). Front keys lift the FRONT-LEFT paw, the rear key the BACK-RIGHT.
// Re-checked with cad/stability_scripts/spike_model.py (29 Sep): crossing +1.11/-1.82 (four paws),
// lift +3.54/-2.76 (FL 42 mm up, margin 8.1), paw-stand +9.79/-7.73 (43 mm), puppy +12.07/-8.78
// (61 mm), rear -0.91/+0.68 (BR 12.6 mm up, margin 12.0). The tilt of a lift pose is set by the three
// stance legs alone, so "tilt first" (lifted leg still at crossing angles) reaches the same tilt.
static const GaitKeyframe KEYS[GK_COUNT] = {
    {"stand", {{0, 0, 0, 0}, {0, 0, 0, 0}, 0}, 0, 0},
    {"crossing", {{4.2f, 28.2f, 20.2f, -19.0f}, {3.4f, -39.6f, -25.4f, 47.9f}, 0}, 1.11f, -1.82f},
    {"lift", {{-29.8f, 12.6f, 3.0f, -18.9f}, {-47.6f, -10.3f, 5.3f, 49.3f}, 0}, 3.54f, -2.76f},
    {"paw-stand", {{6.8f, 10.1f, -5.2f, -0.3f}, {43.5f, -23.2f, 4.4f, 49.6f}, 0}, 9.79f, -7.73f},
    {"paw-puppy", {{25.8f, -10.0f, -0.7f, 0.8f}, {33.0f, 7.3f, -9.5f, 49.8f}, 0}, 12.07f, -8.78f},
    {"rear", {{13.2f, 0.3f, 0.1f, 7.0f}, {-24.8f, -1.0f, -2.0f, 33.9f}, 0}, -0.91f, 0.68f},
};

const GaitKeyframe& gaitKeyframe(GaitKey k) { return KEYS[k < GK_COUNT ? k : GK_STAND]; }

Pose mirrorPose(const Pose& p) {
  Pose m = p;
  m.hip[LEG_FL] = p.hip[LEG_FR]; m.hip[LEG_FR] = p.hip[LEG_FL];
  m.hip[LEG_BL] = p.hip[LEG_BR]; m.hip[LEG_BR] = p.hip[LEG_BL];
  m.knee[LEG_FL] = p.knee[LEG_FR]; m.knee[LEG_FR] = p.knee[LEG_FL];
  m.knee[LEG_BL] = p.knee[LEG_BR]; m.knee[LEG_BR] = p.knee[LEG_BL];
  m.tail = -p.tail;
  return m;
}

static bool isFrontKey(GaitKey k) { return k == GK_CROSS || k == GK_LIFT || k == GK_PAW_STAND || k == GK_PAW_PUPPY; }

Pose gaitPose(GaitKey k, Leg leg, float trim) {
  Pose p = gaitKeyframe(k).pose;
  if (isFrontKey(k)) {
    // research rule 5: lean = the stance-diagonal hips (FR, BL for a front-left lift) +t, feet forward,
    // and the crouching back-right knee +2t (stops at the +50 limit)
    p.hip[LEG_FR] += trim;
    p.hip[LEG_BL] += trim;
    p.knee[LEG_BR] += 2 * trim;
    for (int l = 0; l < LEG_COUNT; l++) limitLeg((Leg)l, &p.hip[l], &p.knee[l]);
    if (leg == LEG_FR) p = mirrorPose(p);
  } else if (k == GK_REAR) {
    if (leg == LEG_BL) p = mirrorPose(p);
  }
  return p;
}

void gaitPrediction(GaitKey k, Leg leg, float* pitch, float* roll) {
  const GaitKeyframe& g = gaitKeyframe(k);
  bool mirrored = (isFrontKey(k) && leg == LEG_FR) || (k == GK_REAR && leg == LEG_BL);
  *pitch = g.pitch;
  *roll = mirrored ? -g.roll : g.roll;
}

// ---- trims ----------------------------------------------------------------------------------------
void GaitTrims::setDefaults() {
  memset(this, 0, sizeof *this);
  version = 1;
}

bool GaitTrims::valid() const {
  if (version != 1) return false;
  for (int i = 0; i < 2; i++)
    if (!(lean[i] >= -3.01f && lean[i] <= 3.01f)) return false;
  if (!(fabsf(levelPitch) <= 15 && fabsf(levelRoll) <= 15)) return false;
  for (int i = 0; i < 3; i++)
    if (laserOk[i] && !(laserMm[i] > 20 && laserMm[i] < 300)) return false;
  return true;
}

// ---- the gait ---------------------------------------------------------------------------------------
Gait::Gait() {
  trims.setDefaults();
  for (int l = 0; l < LEG_COUNT; l++) mv_[l] = LegMove{0, 0, 0, 0, 1, 1};
  st_.paw = -1;
}

void Gait::setWhy(const char* w) {
  strncpy(st_.why, w ? w : "", sizeof st_.why - 1);
  st_.why[sizeof st_.why - 1] = 0;
}

GaitStyle Gait::choose(GaitStyle wanted, float deskTiltDeg, float restVolts, const char** why) const {
  const char* w = "";
  bool lowBatt = restVolts > 0 && restVolts < cfg.minRestVolts;
  bool frontCal = trims.calibrated && trims.tiltOk[0] && trims.tiltOk[1];
  bool tiltAllowed = (frontCal || !cfg.requireCalibration) && deskTiltDeg <= cfg.maxDeskTiltDeg && !lowBatt;
  // a back lift is naturally stable (12 mm, 0.10 kg.cm): allowed before any calibration, but not after a
  // calibration that found it does not behave as predicted
  bool rearAllowed = (trims.rearOk || !trims.calibrated) && !lowBatt;
  GaitStyle s = wanted;
  if (s == GAIT_AUTO || s == GAIT_TILT_STEP) {
    if (tiltAllowed) s = GAIT_TILT_STEP;
    else {
      w = lowBatt ? "battery below 7.4 V" : (deskTiltDeg > cfg.maxDeskTiltDeg ? "desk tilted over 3 deg"
          : (!trims.calibrated ? "balance not calibrated" : "front paw calibration failed"));
      s = rearAllowed ? GAIT_REAR_STEP : GAIT_MARCH;
    }
  } else if (s == GAIT_REAR_STEP && !rearAllowed) {
    w = lowBatt ? "battery below 7.4 V" : "back-paw lift failed calibration";
    s = GAIT_MARCH;
  }
  if (s >= GAIT_STYLE_COUNT) s = GAIT_MARCH;
  if (why) *why = w;
  return s;
}

bool Gait::walk(GaitStyle style, int direction, int steps) {
  if (active()) { setWhy("busy"); return false; }
  style_ = style < GAIT_STYLE_COUNT ? style : GAIT_AUTO;
  dir_ = direction < 0 ? -1 : 1;
  stepsWanted_ = steps < 1 ? 1 : (steps > cfg.maxSteps ? cfg.maxSteps : steps);
  beginRequest(REQ_WALK);
  return true;
}

bool Gait::givePaw(Leg paw, bool fromSit) {
  if (active()) { setWhy("busy"); return false; }
  paw_ = paw == LEG_FR ? LEG_FR : LEG_FL;
  pawFromSit_ = fromSit;
  stepsWanted_ = 1;
  beginRequest(REQ_PAW);
  return true;
}

bool Gait::liftTest(Leg paw, float seconds) {
  if (!givePaw(paw, false)) return false;
  liftTest_ = true;
  holdOverride_ = seconds < 0.3f ? 0.3f : (seconds > 60 ? 60 : seconds);
  return true;
}

bool Gait::calibrate() {
  if (active()) { setWhy("busy"); return false; }
  stepsWanted_ = 4;
  beginRequest(REQ_CAL);
  return true;
}

void Gait::beginRequest(Req r) {
  req_ = r;
  phase_ = GP_LEVEL;
  t_ = sub_ = 0;
  subState_ = 0;
  stepsDone_ = 0;
  pawIdx_ = 0;
  nextIsGlide_ = true;
  stopReq_ = false;
  refSumP_ = refSumR_ = 0;
  refN_ = 0;
  armed_ = 0;
  calStage_ = 0;
  st_.aborts = 0;
  for (int l = 0; l < LEG_COUNT; l++) st_.consecutiveAborts[l] = 0;
  st_.result = GR_NONE;
  pending_ = GR_DONE;
  st_.progress = 0;
  liftTest_ = false;
  holdOverride_ = 0;
  setWhy("");
  moveAll(pose(POSE_STAND), 0.8f);  // from wherever the Controller left the legs (setStartPose)
}

void Gait::stop() {
  if (!active()) return;
  stopReq_ = true;
  if (pending_ == GR_DONE) pending_ = GR_STOPPED;
}

void Gait::cancel() {
  if (!active()) return;
  phase_ = GP_IDLE;
  req_ = REQ_NONE;
  st_.result = GR_CANCELLED;
  setWhy("cancelled (fall, pick-up or battery cut)");
}

// ---- per-leg moves ------------------------------------------------------------------------------------
Pose Gait::commanded() const {
  Pose p{};
  for (int l = 0; l < LEG_COUNT; l++) {
    const LegMove& m = mv_[l];
    float u = smooth(m.T > 0 ? m.t / m.T : 1);
    p.hip[l] = m.h0 + (m.h1 - m.h0) * u;
    p.knee[l] = m.k0 + (m.k1 - m.k0) * u;
  }
  p.tail = 0;  // research rule 8: tail held during the steps
  return p;
}

void Gait::setMove(int l, float h, float k, float T) {
  Pose c = commanded();
  mv_[l] = LegMove{c.hip[l], c.knee[l], h, k, 0, T > 0.001f ? T : 0.001f};
}

void Gait::moveAll(const Pose& to, float T) {
  Pose c = commanded();
  for (int l = 0; l < LEG_COUNT; l++) mv_[l] = LegMove{c.hip[l], c.knee[l], to.hip[l], to.knee[l], 0, T > 0.001f ? T : 0.001f};
}

bool Gait::movesDone() const {
  for (int l = 0; l < LEG_COUNT; l++) if (mv_[l].t < mv_[l].T) return false;
  return true;
}

// ---- tilt estimate: complementary filter (gyro + accelerometer), accelerometer-only fallback ---------
void Gait::estimate(const GaitInput& in) {
  float dt = in.dt > 0 ? in.dt : 0.02f;
  if (!in.imuOk) return;
  float accP = atan2f(in.ax, in.az) / RAD;
  float accR = atan2f(-in.ay, in.az) / RAD;
  if (!haveTilt_) {
    pitch_ = accP; roll_ = accR; haveTilt_ = true;
    prevAccP_ = accP; prevAccR_ = accR;
    return;
  }
  if (in.gyroOk) {
    // body axes: + gy = nose DOWN, + gx = left side UP (right-hand rule, x forward, y left, z up)
    pitchRate_ = -in.gy;
    rollRate_ = -in.gx;
    pitch_ += pitchRate_ * dt;
    roll_ += rollRate_ * dt;
    float a = clampf(dt / cfg.tiltTauS, 0, 1);
    pitch_ += (accP - pitch_) * a;
    roll_ += (accR - roll_) * a;
    yawDeg_ += in.gz * dt;
  } else {
    float a = clampf(dt / cfg.accOnlyTauS, 0, 1);
    float p0 = pitch_, r0 = roll_;
    pitch_ += (accP - pitch_) * a;
    roll_ += (accR - roll_) * a;
    pitchRate_ = (pitch_ - p0) / dt;
    rollRate_ = (roll_ - r0) / dt;
  }
}

// Progress of a front step along the predicted tilt change (0 = the crossing as measured, 1 = predicted).
float Gait::frontProgress() const {
  float d2 = dP_ * dP_ + dR_ * dR_;
  if (d2 < 1e-6f) return 0;
  float vp = (pitch_ - refP_) - cP_, vr = (roll_ - refR_) - cR_;
  return (vp * dP_ + vr * dR_) / d2;
}

// Distance (deg) of the measured tilt from the predicted path: beyond its end, or sideways off it.
float Gait::pathError() const {
  float dl = sqrtf(dP_ * dP_ + dR_ * dR_);
  if (dl < 1e-3f) return 0;
  float vp = (pitch_ - refP_) - cP_, vr = (roll_ - refR_) - cR_;
  float along = (vp * dP_ + vr * dR_) / dl;
  float perp = fabsf(vp * dR_ - vr * dP_) / dl;
  float beyond = along - dl;
  return beyond > perp ? beyond : perp;
}

bool Gait::tipTrend(float rate, bool) const {
  return rate > cfg.abortRateDps || pathError() > cfg.overTiltDeg;
}

// ---- step engine ------------------------------------------------------------------------------------
static const int8_t TILT_ORDER[4] = {LEG_FL, LEG_BR, LEG_FR, LEG_BL};  // research: FL, BR, FR, BL
static const int8_t REAR_ORDER[2] = {LEG_BR, LEG_BL};

void Gait::setStartPose(const Pose& p) {
  for (int l = 0; l < LEG_COUNT; l++) mv_[l] = LegMove{p.hip[l], p.knee[l], p.hip[l], p.knee[l], 1, 1};
}

void Gait::moveStance(const Pose& to, float T) {
  Pose c = commanded();
  for (int l = 0; l < LEG_COUNT; l++) {
    if (l == paw_) continue;
    mv_[l] = LegMove{c.hip[l], c.knee[l], to.hip[l], to.knee[l], 0, T > 0.001f ? T : 0.001f};
  }
}

// Research rule 1: 1..3 deg of desk tilt that moves the weight toward the lifted paw -> add that much lean.
float Gait::deskTrimFor(int paw) const {
  if (!deskKnown_) return 0;
  float tilt = sqrtf(deskP_ * deskP_ + deskR_ * deskR_);
  if (tilt < cfg.deskTrimStartDeg) return 0;
  // weight runs downhill: toward the front-left corner when nose-down (pitch -) and left-low (roll +)
  float hurt = (paw == LEG_FR ? (-deskP_ - deskR_) : (-deskP_ + deskR_)) * 0.70710678f;
  return hurt > 0 ? hurt * cfg.deskTrimGain : 0;
}

void Gait::fallBack(const char* why) {
  const char* w2 = nullptr;
  GaitStyle s = style_ == GAIT_TILT_STEP ? choose(GAIT_REAR_STEP, 0, restVolts_, &w2) : GAIT_MARCH;
  style_ = s;
  pawIdx_ = -1;  // the caller's pawIdx_++ starts the new order at its first paw
  setWhy(why);
}

void Gait::nextItem() {
  if (req_ != REQ_WALK) return;
  if (stopReq_ || stepsDone_ >= stepsWanted_) { finish(pending_, nullptr); return; }
  if (style_ == GAIT_MARCH) { item_ = IT_MARCH; startItem(); return; }
  if (nextIsGlide_) { nextIsGlide_ = false; item_ = IT_GLIDE; startItem(); return; }
  if (restVolts_ > 0 && restVolts_ < cfg.minRestVolts) {  // research rule 4
    style_ = GAIT_MARCH;
    setWhy("battery below 7.4 V: wheel-assisted march");
    item_ = IT_MARCH;
    startItem();
    return;
  }
  if (pawIdx_ < 0) pawIdx_ = 0;
  paw_ = style_ == GAIT_TILT_STEP ? TILT_ORDER[pawIdx_ % 4] : REAR_ORDER[pawIdx_ % 2];
  item_ = (paw_ == LEG_FL || paw_ == LEG_FR) ? IT_FRONT : IT_REAR;
  nextIsGlide_ = true;
  startItem();
}

void Gait::startItem() {
  if (item_ == IT_GLIDE || item_ == IT_MARCH) { armed_ = 0; enter(GP_ARM); return; }
  int side = paw_ == LEG_FR ? 1 : 0;
  if (item_ == IT_FRONT || item_ == IT_PAW)
    trimStart_ = clampf(trims.lean[side] + deskTrimFor(paw_), -cfg.trimCapDeg, cfg.trimCapDeg);
  else if (item_ == IT_PROBE) trimStart_ = calTrim_;
  else trimStart_ = 0;
  trim_ = trimStart_;
  liftKey_ = item_ == IT_PAW && !liftTest_ ? ((pawFromSit_ && cfg.puppySitPaw) ? GK_PAW_PUPPY : GK_PAW_STAND) : GK_LIFT;
  calFound_ = false;
  rearMatch_ = false;
  enter(GP_SETTLE);
}

void Gait::enter(GaitPhase p) {
  phase_ = p;
  t_ = sub_ = 0;
  subState_ = 0;
  switch (p) {
    case GP_SETTLE: moveAll(pose(POSE_STAND), 0.4f); break;
    case GP_SHIFT: moveAll(gaitPose(GK_CROSS, (Leg)paw_, trim_), cfg.shiftS); break;
    case GP_TILT: {
      float cp, cr, lp, lr;
      gaitPrediction(GK_CROSS, (Leg)paw_, &cp, &cr);
      gaitPrediction(liftKey_, (Leg)paw_, &lp, &lr);
      cP_ = pitch_ - refP_;  // review item 7: work with the tilt CHANGE from the crossing as measured
      cR_ = roll_ - refR_;
      dP_ = lp - cp;
      dR_ = lr - cr;
      progMax_ = 0;
      tucked_ = false;
      leanT_ = 0;
      // review item 3: tilt first -- the three stance legs go to the lift pose, the lifted leg stays
      moveStance(gaitPose(liftKey_, (Leg)paw_, trim_), cfg.tiltS);
      break;
    }
    case GP_HOLD: leanT_ = 0; break;
    case GP_SETDOWN: moveAll(gaitPose(GK_CROSS, (Leg)paw_, trim_), cfg.setDownS); break;
    case GP_UNSHIFT: moveAll(pose(POSE_STAND), cfg.unshiftS); break;
    case GP_REAR_LIFT:
      cP_ = pitch_ - refP_;
      cR_ = roll_ - refR_;
      gaitPrediction(GK_REAR, (Leg)paw_, &dP_, &dR_);
      moveAll(gaitPose(GK_REAR, (Leg)paw_, 0), cfg.rearLiftS);
      break;
    case GP_REAR_DOWN: moveAll(pose(POSE_STAND), cfg.rearDownS); break;
    case GP_GLIDE: case GP_MARCH: yaw0_ = yawDeg_; break;
    case GP_FINISH: moveAll(pose(POSE_STAND), 0.6f); break;
    default: break;
  }
}

void Gait::finish(GaitResult r, const char* why) {
  pending_ = r;
  if (why) setWhy(why);
  enter(GP_FINISH);
}

void Gait::abortStep(bool fast, bool stalled, const char* why) {
  st_.aborts++;
  setWhy(why);
  abortFast_ = fast;
  abortStalled_ = stalled;
  bool rear = item_ == IT_REAR;
  phase_ = GP_ABORT;
  t_ = sub_ = 0;
  if (fast) {  // research rule 3: the lifted leg straight back to its crossing (rear: stand) angles
    abortStage_ = 0;
    Pose base = rear ? pose(POSE_STAND) : gaitPose(GK_CROSS, (Leg)paw_, trim_);
    Pose c = commanded();
    for (int l = 0; l < LEG_COUNT; l++) mv_[l] = LegMove{c.hip[l], c.knee[l], c.hip[l], c.knee[l], 1, 1};
    setMove(paw_, base.hip[paw_], base.knee[paw_], cfg.fastAbortS);
  } else {
    abortStage_ = 1;
    if (rear) moveAll(pose(POSE_STAND), cfg.rearDownS);
    else moveAll(gaitPose(GK_CROSS, (Leg)paw_, trim_), cfg.setDownS);
  }
}

void Gait::countAbort() {
  if (paw_ < 0) return;
  if (st_.consecutiveAborts[paw_] < 255) st_.consecutiveAborts[paw_]++;
  if (st_.consecutiveAborts[paw_] >= cfg.abortsBeforeFallback) {
    if (style_ == GAIT_TILT_STEP) fallBack("a front paw aborted twice: rear-step walk");
    else if (style_ == GAIT_REAR_STEP) fallBack("a back paw aborted twice: wheel-assisted march");
  }
}

void Gait::learnAfterStep(bool aborted, bool stalled) {
  int side = paw_ == LEG_FR ? 1 : 0;
  float& L = trims.lean[side];
  if (aborted) {
    if (stalled) L += cfg.learnStepDeg;  // the weight did not cross: lean more next time
  } else {
    if (trims.cleanLifts[side] < 65535) trims.cleanLifts[side]++;
    // review item 2: the learned trim follows the closed loop both ways, 0.5 deg at a time
    float adj = trim_ - trimStart_;
    if (adj >= cfg.learnStepDeg - 1e-3f) L += cfg.learnStepDeg;
    else if (adj <= -cfg.learnStepDeg + 1e-3f) L -= cfg.learnStepDeg;
  }
  if (fabsf(L) > cfg.trimCapDeg + 1e-3f) {  // research rule 5: beyond the cap, stop and report
    L = clampf(L, -cfg.trimCapDeg, cfg.trimCapDeg);
    trims.tiltOk[side] = false;
    if (style_ == GAIT_TILT_STEP) fallBack("lean trim past 3 deg: tilt-step off, recalibrate");
  }
  dirty_ = true;
}

void Gait::stepComplete() {
  switch (item_) {
    case IT_PROBE: calNext(); return;
    case IT_PAW: finish(GR_DONE, nullptr); return;
    case IT_FRONT:
      learnAfterStep(false, false);
      st_.consecutiveAborts[paw_] = 0;
      break;
    case IT_REAR:
      if (req_ == REQ_CAL) { calRearOk_[paw_ == LEG_BR ? 0 : 1] = rearMatch_; calNext(); return; }
      st_.consecutiveAborts[paw_] = 0;
      break;
    default: break;
  }
  stepsDone_++;
  pawIdx_++;
  nextItem();
}

void Gait::abortComplete() {
  switch (item_) {
    case IT_PROBE:
      if (abortFast_) { finish(GR_CAL_FAIL, nullptr); return; }
      calFound_ = false;
      calNext();
      return;
    case IT_PAW: finish(GR_ABORTED, nullptr); return;
    case IT_REAR:
      if (req_ == REQ_CAL) {
        calRearOk_[paw_ == LEG_BR ? 0 : 1] = false;
        if (abortFast_) finish(GR_CAL_FAIL, nullptr); else calNext();
        return;
      }
      countAbort();
      break;
    case IT_FRONT:
      learnAfterStep(true, abortStalled_);
      countAbort();
      break;
    default: break;
  }
  if (abortFast_) { finish(GR_ABORTED, nullptr); return; }  // a tip / rate abort ends the walk
  stepsDone_++;
  pawIdx_++;
  nextItem();
}

// Calibration order: probe FL (lean from -1 deg upward), probe FR, back-right lift, back-left lift.
void Gait::calNext() {
  if (calStage_ <= 1) {
    int side = calStage_;
    if (calFound_) {
      calFrontOk_[side] = true;
      calLean_[side] = clampf(calTrim_ + cfg.calMarginTrimDeg, -cfg.trimCapDeg, cfg.trimCapDeg);
      calStage_++;
    } else {
      calTrim_ += cfg.leanStepDeg;
      if (calTrim_ > cfg.trimCapDeg + 1e-3f) { calFrontOk_[side] = false; calStage_++; }
    }
    if (calStage_ != side) calTrim_ = cfg.calStartTrimDeg;
  } else {
    calStage_++;
  }
  calFound_ = false;
  if (calStage_ <= 1) { paw_ = calStage_ == 0 ? LEG_FL : LEG_FR; item_ = IT_PROBE; startItem(); return; }
  if (calStage_ <= 3) { paw_ = calStage_ == 2 ? LEG_BR : LEG_BL; item_ = IT_REAR; startItem(); return; }
  trims.calibrated = true;
  for (int i = 0; i < 2; i++) {
    trims.tiltOk[i] = calFrontOk_[i];
    trims.lean[i] = calFrontOk_[i] ? calLean_[i] : 0;
    trims.cleanLifts[i] = 0;
  }
  trims.rearOk = calRearOk_[0] && calRearOk_[1];
  dirty_ = true;
  bool pass = calFrontOk_[0] && calFrontOk_[1] && trims.rearOk;
  char w[48];
  if (pass) snprintf(w, sizeof w, "balance ok: lean FL %+.1f FR %+.1f deg", calLean_[0], calLean_[1]);
  else snprintf(w, sizeof w, "FL %s FR %s back %s", calFrontOk_[0] ? "ok" : "FAIL", calFrontOk_[1] ? "ok" : "FAIL",
                trims.rearOk ? "ok" : "FAIL");
  finish(pass ? GR_CAL_PASS : GR_CAL_FAIL, w);
}

// ---- one control tick --------------------------------------------------------------------------------
void Gait::tick(const GaitInput& in, GaitOutput* out) {
  estimate(in);
  float dt = in.dt > 0 ? (in.dt > 0.1f ? 0.1f : in.dt) : 0.02f;
  restVolts_ = in.restVolts;
  out->active = false;
  out->wheelsOff = false;
  out->ignoreEdges = false;
  out->wheelL = out->wheelR = 0;
  out->wheelsArmed = 4;
  out->priorityLeg = -1;
  if (phase_ != GP_IDLE && (!in.legsAllowed || in.pickedUp)) cancel();
  if (phase_ == GP_IDLE) {
    out->pose = commanded();
    st_.phase = GP_IDLE;
    st_.paw = -1;
    return;
  }
  out->active = true;
  if (in.lowPower && !stopReq_) {  // research rule 4: finish the current paw, then stand
    stopReq_ = true;
    if (pending_ == GR_DONE) pending_ = GR_STOPPED;
    setWhy("battery dip: low-power mode, walk ends");
  }
  if (!in.frozen) {  // brown-out dip: the joints are frozen, so is the gait's clock
    t_ += dt;
    sub_ += dt;
    leanT_ += dt;
    for (int l = 0; l < LEG_COUNT; l++)
      if (mv_[l].t < mv_[l].T) { mv_[l].t += dt; if (mv_[l].t > mv_[l].T) mv_[l].t = mv_[l].T; }
  }
  float relP = pitch_ - refP_, relR = roll_ - refR_;
  float rate = fmaxf(fabsf(pitchRate_), fabsf(rollRate_));
  bool ready = movesDone() && in.poseReached;
  float dl = sqrtf(dP_ * dP_ + dR_ * dR_);
  float top = in.wheelTopSpeed > 0.01f ? in.wheelTopSpeed : 0.16f;
  bool legPhase = false, wheelsOff = false;
  float wl = 0, wr = 0;

  switch (phase_) {
    case GP_LEVEL: {
      wheelsOff = in.wheelsStopped;
      if (subState_ == 0) {
        if (ready && in.wheelsStopped && in.outputsReady && t_ >= 0.3f) {
          subState_ = 1;
          sub_ = 0;
          refSumP_ = refSumR_ = 0;
          refN_ = 0;
        } else if (t_ > 5.0f) finish(req_ == REQ_CAL ? GR_CAL_FAIL : GR_STOPPED, "legs or wheels never settled");
        break;
      }
      if (!in.imuOk || !haveTilt_) {
        if (req_ == REQ_WALK) {
          style_ = GAIT_MARCH;
          setWhy("no IMU: wheel-assisted march only");
          deskKnown_ = false;
          nextItem();
        } else finish(req_ == REQ_CAL ? GR_CAL_FAIL : GR_REFUSED, "no IMU");
        break;
      }
      if (rate > cfg.settleRateDps) {  // not still: start the average again
        sub_ = 0;
        refSumP_ = refSumR_ = 0;
        refN_ = 0;
        if (t_ > 0.3f + cfg.settleTimeoutS + 1.0f) finish(req_ == REQ_CAL ? GR_CAL_FAIL : GR_STOPPED, "could not hold still");
        break;
      }
      refSumP_ += pitch_;
      refSumR_ += roll_;
      refN_++;
      if (sub_ < (req_ == REQ_CAL ? cfg.calLevelS : cfg.levelRefS)) break;
      refP_ = refSumP_ / refN_;
      refR_ = refSumR_ / refN_;
      if (req_ == REQ_CAL) {
        if (fabsf(refP_) > cfg.calMaxMountDeg || fabsf(refR_) > cfg.calMaxMountDeg) {
          finish(GR_CAL_FAIL, "IMU over 8 deg on the level desk: check its mounting");
          break;
        }
        trims.levelPitch = refP_;
        trims.levelRoll = refR_;
        deskP_ = deskR_ = 0;
        deskKnown_ = true;
        st_.deskTilt = 0;
        calStage_ = 0;
        calTrim_ = cfg.calStartTrimDeg;
        calFound_ = false;
        calFrontOk_[0] = calFrontOk_[1] = false;
        calRearOk_[0] = calRearOk_[1] = false;
        paw_ = LEG_FL;
        item_ = IT_PROBE;
        startItem();
        break;
      }
      deskKnown_ = trims.calibrated;
      deskP_ = refP_ - (deskKnown_ ? trims.levelPitch : 0);
      deskR_ = refR_ - (deskKnown_ ? trims.levelRoll : 0);
      st_.deskTilt = sqrtf(deskP_ * deskP_ + deskR_ * deskR_);
      if (req_ == REQ_WALK) {
        const char* w = nullptr;
        style_ = choose(style_, st_.deskTilt, in.restVolts, &w);
        if (w && *w) setWhy(w);
        nextIsGlide_ = true;
        pawIdx_ = 0;
        nextItem();
      } else {
        int side = paw_ == LEG_FR ? 1 : 0;
        if (cfg.requireCalibration && !liftTest_ && !(trims.calibrated && trims.tiltOk[side]))
          finish(GR_REFUSED, "give paw needs the balance calibration");
        else if (st_.deskTilt > cfg.maxDeskTiltDeg) finish(GR_REFUSED, "desk tilted over 3 deg");
        else if (in.restVolts > 0 && in.restVolts < cfg.minRestVolts) finish(GR_REFUSED, "battery below 7.4 V");
        else {
          if (pawFromSit_ && !cfg.puppySitPaw) setWhy("puppy-sit paw is off: paw from the stand");
          item_ = IT_PAW;
          startItem();
        }
      }
      break;
    }

    case GP_ARM:  // wheels back on one at a time at the stop pulse, then the fresh desk-edge re-check
      if (armed_ < 4 && sub_ >= cfg.wheelRearmS) { armed_++; sub_ = 0; }
      if (armed_ < 4) break;
      if (blocked(in)) { finish(GR_EDGE, "desk edge or obstacle ahead: no glide"); break; }
      if (!in.edgeRecheckOk) {
        if (t_ > 4 * cfg.wheelRearmS + 0.6f) finish(GR_EDGE, "desk-edge lasers not clear: no glide");
        break;
      }
      enter(item_ == IT_MARCH ? GP_MARCH : GP_GLIDE);
      break;

    case GP_GLIDE: {  // four paws down: roll glideMm with linear speed ramps, heading held by the gyro
      if (blocked(in)) {
        pending_ = GR_EDGE;
        stopReq_ = true;
        setWhy("desk edge or obstacle during the glide");
        enter(GP_GLIDE_SETTLE);
        break;
      }
      if (stopReq_ || t_ >= cfg.glideS) { enter(GP_GLIDE_SETTLE); break; }
      float vmax = cfg.glideMm / 1000.0f / (cfg.glideS - cfg.glideRampS);
      float v = vmax;
      if (t_ < cfg.glideRampS) v = vmax * t_ / cfg.glideRampS;
      else if (t_ > cfg.glideS - cfg.glideRampS) v = vmax * (cfg.glideS - t_) / cfg.glideRampS;
      float cmd = dir_ * v / top;
      float k = clampf((yawDeg_ - yaw0_) * cfg.yawGainPerDeg, -cfg.yawTrimMax, cfg.yawTrimMax);
      wl = cmd + fabsf(cmd) * k;
      wr = cmd - fabsf(cmd) * k;
      break;
    }

    case GP_GLIDE_SETTLE:  // command 0; the Controller ramps the wheels down; then the next item
      if (in.wheelsStopped && t_ >= cfg.glideSettleS) nextItem();
      break;

    case GP_SETTLE:  // F1: four paws, wheels stopped then PWM-off, rates quiet
      if (!in.wheelsStopped) { t_ = 0; sub_ = 0; break; }  // never a leg phase with rolling wheels
      wheelsOff = true;
      if (stopReq_) { finish(req_ == REQ_WALK ? pending_ : GR_STOPPED, nullptr); break; }
      if (rate >= cfg.settleRateDps) sub_ = 0;
      if (ready && t_ >= cfg.settleMinS && sub_ >= cfg.settleQuietS) enter(item_ == IT_REAR ? GP_REAR_LIFT : GP_SHIFT);
      else if (t_ > cfg.settleTimeoutS) finish(req_ == REQ_CAL ? GR_CAL_FAIL : GR_STOPPED, "could not settle before a step");
      break;

    case GP_SHIFT: {  // F2: stand -> four-paw crossing
      legPhase = true;
      if (rate > cfg.abortRateDps) { abortStep(false, false, "tilt rate during the weight shift"); break; }
      if (!ready) break;
      if (subState_ == 0) { subState_ = 1; sub_ = 0; }
      if (sub_ < 0.2f) break;
      float cp, cr;
      gaitPrediction(GK_CROSS, (Leg)paw_, &cp, &cr);
      float e = sqrtf((relP - cp) * (relP - cp) + (relR - cr) * (relR - cr));
      if (e > cfg.shiftTolDeg) {
        char w[48];
        snprintf(w, sizeof w, "crossing tilt %.1f deg off the prediction", e);
        abortStep(false, false, w);
        break;
      }
      enter(GP_TILT);
      break;
    }

    case GP_TILT: {  // F3: tilt first, tuck second (review item 3)
      legPhase = true;
      float prog = frontProgress();
      st_.progress = prog;
      if (tipTrend(rate, true)) {
        abortStep(true, false, rate > cfg.abortRateDps ? "tilt rate over 20 deg/s" : "tilt beyond the prediction");
        break;
      }
      if (!tucked_) {
        if (prog >= cfg.tuckStartProgress) {  // the weight has crossed: the paw is already off the desk
          if (item_ == IT_PROBE) { calFound_ = true; lastProbeProgress_ = prog; enter(GP_SETDOWN); break; }
          tucked_ = true;
          progMax_ = prog;
          Pose lp = gaitPose(liftKey_, (Leg)paw_, trim_);
          setMove(paw_, lp.hip[paw_], lp.knee[paw_], item_ == IT_PAW ? cfg.pawReachS : cfg.tuckS);
          break;
        }
        if (!movesDone() || !in.poseReached) { sub_ = 0; break; }
        if (item_ == IT_PROBE) {
          if (sub_ >= cfg.calProbeWaitS) { lastProbeProgress_ = prog; calFound_ = false; enter(GP_SETDOWN); }
          break;
        }
        // No lift-off yet: the body has rocked onto the other diagonal (the weight is short of the line).
        // Leaning more from HERE would need extra lean to rock it back (the tilt moves the weight's
        // projection ~2 mm per deg), so: back to the four-paw crossing with 0.5 deg more lean, and tilt
        // again -- the same move the calibration probe makes. Up to leanMaxAdjDeg, then abort.
        if (subState_ == 0) {  // judging: the stance move is done; give the body tiltWaitS to settle
          if (sub_ < cfg.tiltWaitS) break;
          if (trim_ + cfg.leanStepDeg > trimStart_ + cfg.leanMaxAdjDeg + 1e-3f || trim_ + cfg.leanStepDeg > cfg.trimCapDeg + 1e-3f) {
            abortStep(false, true, "no lift-off within the lean limit");
            break;
          }
          // first back to the crossing at the SAME lean: every paw down again, nothing to rock over
          moveStance(gaitPose(GK_CROSS, (Leg)paw_, trim_), cfg.shiftS * 0.75f);
          subState_ = 1;
          break;
        }
        if (subState_ == 1) {  // on four paws: add the lean here, where crossing the line is gentle
          trim_ += cfg.leanStepDeg;
          moveStance(gaitPose(GK_CROSS, (Leg)paw_, trim_), cfg.leanStepS);
          subState_ = 2;
          break;
        }
        if (subState_ == 2) {  // tilt again
          moveStance(gaitPose(liftKey_, (Leg)paw_, trim_), cfg.tiltS);
          subState_ = 0;
          sub_ = 0;
        }
        break;
      }
      if (prog > progMax_) progMax_ = prog;
      if (dl > 1e-3f && prog < progMax_ - cfg.dropBackDeg / dl) { abortStep(false, false, "paw taking weight again"); break; }
      if (ready) enter(GP_HOLD);
      break;
    }

    case GP_HOLD: {  // F4: paw up; closed-loop lean both ways until the tilt matches (sag, review item 2)
      legPhase = true;
      float prog = frontProgress();
      st_.progress = prog;
      if (tipTrend(rate, true)) {
        abortStep(true, false, rate > cfg.abortRateDps ? "tilt rate over 20 deg/s" : "tilt beyond the prediction");
        break;
      }
      if (prog > progMax_) progMax_ = prog;
      if (dl > 1e-3f && prog < progMax_ - cfg.dropBackDeg / dl) { abortStep(false, false, "paw taking weight again"); break; }
      if (stopReq_) { enter(GP_SETDOWN); break; }
      if (!movesDone() || !in.poseReached) { sub_ = 0; break; }
      float e = (prog - 1) * dl;  // deg along the predicted change; + = more tilt than predicted
      if (fabsf(e) <= cfg.leanTolDeg) {
        float holdT = item_ == IT_PAW ? (holdOverride_ > 0 ? holdOverride_ : cfg.pawHoldS) : cfg.holdS;
        if (t_ >= holdT && rate < cfg.holdRateDps) enter(GP_SETDOWN);
        break;
      }
      if (sub_ < cfg.leanSettleS) break;
      if (leanT_ > cfg.leanTimeoutS) { abortStep(false, false, "lift tilt not matched in time"); break; }
      float step = -cfg.leanLoopSign * (e > 0 ? 1.0f : -1.0f) * cfg.leanStepDeg;
      float lo = fmaxf(trimStart_ - cfg.leanMaxAdjDeg, -cfg.trimCapDeg);
      float hi = fminf(trimStart_ + cfg.leanMaxAdjDeg, cfg.trimCapDeg);
      float nt = clampf(trim_ + step, lo, hi);
      if (fabsf(nt - trim_) > 1e-4f) { trim_ = nt; moveStance(gaitPose(liftKey_, (Leg)paw_, trim_), cfg.leanStepS); }
      sub_ = 0;
      break;
    }

    case GP_SETDOWN:  // F5: back to the crossing (four paws)
      legPhase = true;
      if (ready) enter(GP_UNSHIFT);
      break;

    case GP_UNSHIFT:  // F6: back to the stand
      legPhase = true;
      if (ready) stepComplete();
      break;

    case GP_REAR_LIFT:
    case GP_REAR_HOLD: {  // R1 / R2: a back paw up 12 mm (no lean loop: 12 mm of margin)
      legPhase = true;
      float prog = dl > 1e-3f ? ((relP - cP_) * dP_ + (relR - cR_) * dR_) / (dl * dl) : 0;
      st_.progress = prog;
      if (tipTrend(rate, false)) { abortStep(true, false, "back lift: tilt rate or tip trend"); break; }
      if (dl > 1e-3f && prog * dl < -cfg.dropBackDeg) { abortStep(false, false, "back lift tilting the wrong way"); break; }
      if (phase_ == GP_REAR_LIFT) { if (ready) enter(GP_REAR_HOLD); break; }
      if (stopReq_ || t_ >= cfg.rearHoldS) {
        float ep = relP - cP_ - dP_, er = relR - cR_ - dR_;
        rearMatch_ = sqrtf(ep * ep + er * er) <= cfg.rearTolDeg;
        enter(GP_REAR_DOWN);
      }
      break;
    }

    case GP_REAR_DOWN:  // R3
      legPhase = true;
      if (ready) stepComplete();
      break;

    case GP_ABORT:  // paw down (fast: lifted leg first), level, stand
      legPhase = true;
      if (!ready) break;
      if (abortStage_ == 0) {
        abortStage_ = 1;
        if (item_ == IT_REAR) moveAll(pose(POSE_STAND), cfg.rearDownS);
        else moveAll(gaitPose(GK_CROSS, (Leg)paw_, trim_), cfg.setDownS);
      } else if (abortStage_ == 1 && item_ != IT_REAR) {
        abortStage_ = 2;
        moveAll(pose(POSE_STAND), cfg.unshiftS);
      } else abortComplete();
      break;

    case GP_MARCH: {  // fallback 2: paws stay on the desk and bob; the wheels roll; lasers stay live
      float speed = cfg.marchSpeed * top;
      int remaining = stepsWanted_ - stepsDone_;
      float total = remaining * cfg.marchStepMm / 1000.0f / (speed > 1e-3f ? speed : 1e-3f) + cfg.marchRampS;
      if (blocked(in)) {
        pending_ = GR_EDGE;
        setWhy("desk edge or obstacle: march stopped");
        stopReq_ = true;
        stepsDone_ = stepsWanted_;
        enter(GP_GLIDE_SETTLE);
        break;
      }
      if (stopReq_ || t_ >= total) { stepsDone_ = stepsWanted_; enter(GP_GLIDE_SETTLE); break; }
      float v = cfg.marchSpeed;
      if (t_ < cfg.marchRampS) v *= t_ / cfg.marchRampS;
      else if (t_ > total - cfg.marchRampS) v *= (total - t_) / cfg.marchRampS;
      float cmd = dir_ * v;
      float k = clampf((yawDeg_ - yaw0_) * cfg.yawGainPerDeg, -cfg.yawTrimMax, cfg.yawTrimMax);
      wl = cmd + fabsf(cmd) * k;
      wr = cmd - fabsf(cmd) * k;
      float a = in.lowPower ? 0 : cfg.marchBobDeg;
      float s = sinf(6.2831853f * t_ / cfg.marchPeriodS);
      float aA = a * fmaxf(0, s), aB = a * fmaxf(0, -s);
      Pose p = pose(POSE_STAND);  // front: hip +a / knee -2a, rear: hip -a / knee +2a (foot under the hip)
      p.hip[LEG_FL] = aA;  p.knee[LEG_FL] = -2 * aA;
      p.hip[LEG_BR] = -aA; p.knee[LEG_BR] = 2 * aA;
      p.hip[LEG_FR] = aB;  p.knee[LEG_FR] = -2 * aB;
      p.hip[LEG_BL] = -aB; p.knee[LEG_BL] = 2 * aB;
      setStartPose(p);
      break;
    }

    case GP_FINISH:  // stand, wheels stopped, wheels back on one at a time, then idle
      if (!in.wheelsStopped) { armed_ = 4; break; }
      if (armed_ < 4 && sub_ >= cfg.wheelRearmS) { armed_++; sub_ = 0; }
      if (ready && armed_ >= 4) {
        phase_ = GP_IDLE;
        req_ = REQ_NONE;
        st_.result = pending_;
      }
      break;

    default: break;
  }

  if (legPhase) wheelsOff = true;
  if (wheelsOff) armed_ = 0;
  out->wheelsOff = wheelsOff;
  out->ignoreEdges = legPhase;
  out->wheelsArmed = wheelsOff ? 0 : ((phase_ == GP_ARM || phase_ == GP_FINISH) ? armed_ : 4);
  out->wheelL = wheelsOff ? 0 : wl;
  out->wheelR = wheelsOff ? 0 : wr;
  out->priorityLeg = legPhase ? (int8_t)paw_ : -1;
  out->pose = commanded();
  st_.phase = phase_;
  st_.style = style_;
  st_.paw = (int8_t)(legPhase ? paw_ : -1);
  st_.stepsDone = (uint8_t)stepsDone_;
  st_.stepsWanted = (uint8_t)stepsWanted_;
  st_.trimNow = trim_;
  st_.pitch = relP;
  st_.roll = relR;
}

}  // namespace body
}  // namespace spike
