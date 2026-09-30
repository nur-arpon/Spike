// spike_gait.h -- Spike's walking and give-paw (platform-free, host-tested). INCLUDE "spike_body.h", not
// this file directly: spike_body.h pulls it in after the pose and safety types it needs.
//
// Three walks, one give-paw and a day-1 balance calibration, all built on the same step engine:
//  * TILT-STEP MARCH (cad/stability_max_research.md "Question 3", corrected by
//    cad/stability_research_review.md): glide 40 mm on four paws, then lift one paw with the wheels
//    PWM-OFF: shift to the four-paw crossing, tilt the body with the three stance legs (the lifted leg held
//    at its crossing angles), tuck the paw only once the IMU shows the weight has crossed, hold (closed-loop
//    lean in 0.5 deg steps both ways), set down, unshift. Order FL, BR, FR, BL.
//  * REAR-STEP WALK (fallback 1): glides + back-paw lifts only (naturally stable, 12 mm, 0.10 kg.cm).
//  * WHEEL-ASSISTED MARCH (fallback 2): the wheels roll slowly while the legs bob in diagonal pairs with the
//    paws kept on the desk; the desk-edge lasers stay active the whole time.
//  * GIVE PAW from a stand (a front paw raised 43 mm and reaching forward); the puppy-sit variant exists
//    behind GaitConfig::puppySitPaw (off).
//  * BALANCE CALIBRATION: IMU level check, then for each front paw a lean probe from -1 deg upward in
//    0.5 deg steps until the stance tilt unloads the paw; then both back-paw lifts are checked.
// Safety invariants (the Controller enforces them too): the wheels are PWM-off in every leg phase and a
// leg phase starts only with the wheels at rest; the desk-edge lasers are ignored only while the wheels are
// off; every glide needs 5 fresh clear readings from every desk-edge laser; any unexpected tilt, tilt
// rate or reloading paw puts the paw down, levels and stands.
#pragma once
#include <stdint.h>
#include "spike_gait_config.h"

namespace spike {
namespace body {

enum GaitStyle : uint8_t { GAIT_AUTO, GAIT_TILT_STEP, GAIT_REAR_STEP, GAIT_MARCH, GAIT_STYLE_COUNT };
const char* gaitStyleName(GaitStyle s);

enum GaitPhase : uint8_t {
  GP_IDLE, GP_LEVEL, GP_ARM, GP_GLIDE, GP_GLIDE_SETTLE, GP_SETTLE, GP_SHIFT, GP_TILT, GP_HOLD, GP_SETDOWN,
  GP_UNSHIFT, GP_REAR_LIFT, GP_REAR_HOLD, GP_REAR_DOWN, GP_MARCH, GP_ABORT, GP_FINISH, GP_PHASE_COUNT
};
const char* gaitPhaseName(GaitPhase p);

enum GaitResult : uint8_t {
  GR_NONE, GR_DONE, GR_STOPPED, GR_EDGE, GR_ABORTED, GR_REFUSED, GR_CANCELLED, GR_CAL_PASS, GR_CAL_FAIL
};
const char* gaitResultName(GaitResult r);

// Stored in NVS next to the servo calibration (screen board, "spikecal"/"gait").
struct GaitTrims {
  uint16_t version;
  bool calibrated;           // the balance calibration ran to the end
  bool tiltOk[2];            // front paw FL / FR may lift (calibration passed, trims inside the cap)
  bool rearOk;               // both back-paw lifts matched the prediction
  float levelPitch, levelRoll;  // IMU reading on the known-level calibration desk (mounting offset)
  float lean[2];             // learned lean trim per front paw FL / FR, deg (stance hips +t, crouch knee +2t)
  uint16_t cleanLifts[2];
  bool laserOk[3];           // desk-edge level readings from the last good calibration (fallback)
  float laserMm[3];
  float laserRefPitch, laserRefRoll;  // body tilt when those readings were taken
  void setDefaults();
  bool valid() const;
};

// Keyframe poses (research tables, front-left / back-right versions; the others are mirror images).
enum GaitKey : uint8_t { GK_STAND, GK_CROSS, GK_LIFT, GK_PAW_STAND, GK_PAW_PUPPY, GK_REAR, GK_COUNT };
struct GaitKeyframe { const char* name; Pose pose; float pitch, roll; };  // predicted IMU tilt from the stand
const GaitKeyframe& gaitKeyframe(GaitKey k);
// The keyframe for paw `leg` (front keys: LEG_FL / LEG_FR; rear key: LEG_BL / LEG_BR), with the lean
// trim applied (front keys only: the two stance-diagonal hips + t, the crouching rear knee + 2 t).
Pose gaitPose(GaitKey k, Leg leg, float trim);
void gaitPrediction(GaitKey k, Leg leg, float* pitch, float* roll);
Pose mirrorPose(const Pose& p);

// What the Controller tells the gait every tick.
struct GaitInput {
  float dt;
  bool imuOk;
  float ax, ay, az;          // g, body axes (x forward, y left, z up)
  bool gyroOk;
  float gx, gy, gz;          // deg/s about x / y / z
  bool wheelsStopped;        // the Controller's ramped wheel speed is 0 (a leg phase may begin)
  bool poseReached;          // the joint outputs have caught up with the gait's pose (slew, low power)
  bool frozen;               // brown-out dip: joints frozen, the gait clock pauses
  bool lowPower;
  bool legsAllowed;          // not fallen, not battery-cut
  bool pickedUp;
  bool outputsReady;         // power-up stagger finished
  bool edgeRecheckOk;        // every desk-edge laser has >= 5 fresh clear readings since the last leg phase
  bool blockFwd, blockBack;  // Safety's wheel blocks (edges, obstacles)
  float restVolts;           // slow battery reading, < 0 = unknown
  float wheelTopSpeed;       // m/s at wheel command 1.0 (MotionConfig)
};

struct GaitOutput {
  bool active;
  Pose pose;
  bool wheelsOff;            // PWM full-off on all four wheels (not the stop pulse)
  bool ignoreEdges;          // leg phase: Safety skips desk-edge readings (wheels are off)
  float wheelL, wheelR;      // glide / march command (-1..1), before the Controller's safety filter
  int8_t wheelsArmed;        // wheels switched on so far during a staggered re-arm (0..4), 4 = all
  int8_t priorityLeg;        // low power: this leg moves first (the lifted one), -1 = none
};

struct GaitStatus {          // for logs, the console and the tests
  GaitPhase phase;
  GaitStyle style;
  int8_t paw;                // leg being stepped, -1 = none
  uint8_t stepsDone, stepsWanted;
  float progress;            // tilt progress of the current front step (0 at the crossing, 1 at the prediction)
  float trimNow;             // lean trim in use for the current step
  float pitch, roll;         // tilt relative to the walk-start reference
  float deskTilt;            // |reference - stored level|
  uint8_t aborts;            // this request
  uint8_t consecutiveAborts[4];
  GaitResult result;         // last finished request
  char why[48];              // reason of the last abort / refusal / fallback
};

class Gait {
 public:
  GaitConfig cfg;
  GaitTrims trims;
  Gait();

  // Requests. They return false (and say why in status().why) when refused outright.
  bool walk(GaitStyle style, int direction, int steps);   // direction +1 forward, -1 backward
  bool givePaw(Leg paw, bool fromSit);                    // paw LEG_FL / LEG_FR
  // Day-1 test (research test 5b): one front paw up in the march's tucked lift pose, held `seconds`
  // (<= 60), with every abort rule active. Allowed before the calibration (supervised bench test).
  bool liftTest(Leg paw, float seconds);
  bool calibrate();
  void setStartPose(const Pose& p);                       // where the legs are now (call before a request)
  void stop();                                          // graceful: paw down, level, stand
  void cancel();                                          // at once, no motion (fall, pick-up, battery cut)

  // Which walk to use: the requested style if its conditions hold, else the fallback (tilt-step ->
  // rear-step -> march). Why lands in *why (may be null).
  GaitStyle choose(GaitStyle wanted, float deskTiltDeg, float restVolts, const char** why) const;

  void tick(const GaitInput& in, GaitOutput* out);
  bool active() const { return phase_ != GP_IDLE; }
  const GaitStatus& status() const { return st_; }
  bool trimsDirty() const { return dirty_; }
  void clearTrimsDirty() { dirty_ = false; }
  // Tilt estimate (absolute, deg), kept warm every tick even when idle.
  float pitchAbs() const { return pitch_; }
  float rollAbs() const { return roll_; }
  float pitchRate() const { return pitchRate_; }
  float rollRate() const { return rollRate_; }

 private:
  enum Req : uint8_t { REQ_NONE, REQ_WALK, REQ_PAW, REQ_CAL };
  enum Item : uint8_t { IT_GLIDE, IT_FRONT, IT_REAR, IT_PAW, IT_PROBE, IT_MARCH };
  struct LegMove { float h0, k0, h1, k1, t, T; };

  void estimate(const GaitInput& in);
  void setMove(int leg, float h, float k, float T);
  void moveAll(const Pose& to, float T);
  void moveStance(const Pose& to, float T);   // every leg but the stepping one
  bool movesDone() const;
  Pose commanded() const;
  void beginRequest(Req r);
  void nextItem();
  void startItem();
  void enter(GaitPhase p);
  void finish(GaitResult r, const char* why);
  void abortStep(bool fast, bool stalled, const char* why);
  void stepComplete();
  void abortComplete();
  void learnAfterStep(bool aborted, bool stalled);
  void countAbort();
  void calNext();
  float deskTrimFor(int paw) const;
  void fallBack(const char* why);
  float frontProgress() const;
  float pathError() const;
  bool tipTrend(float rate, bool frontStep) const;
  void setWhy(const char* w);
  bool blocked(const GaitInput& in) const { return dir_ > 0 ? in.blockFwd : in.blockBack; }

  GaitPhase phase_ = GP_IDLE;
  Req req_ = REQ_NONE;
  GaitStyle style_ = GAIT_AUTO;
  int dir_ = 1;
  int stepsWanted_ = 0, stepsDone_ = 0;
  Item item_ = IT_GLIDE;
  int paw_ = -1;                 // leg of the current step
  int pawIdx_ = 0;               // index into the paw order
  bool nextIsGlide_ = true;
  bool pawFromSit_ = false;
  bool stopReq_ = false;
  bool dirty_ = false;

  LegMove mv_[LEG_COUNT];
  float t_ = 0;                  // time in the current phase
  float sub_ = 0;                // sub-timer (lean steps, settle windows)
  int subState_ = 0;

  // tilt estimate
  bool haveTilt_ = false;
  float pitch_ = 0, roll_ = 0, pitchRate_ = 0, rollRate_ = 0, yawDeg_ = 0;
  float prevAccP_ = 0, prevAccR_ = 0;
  // walk reference and step bookkeeping
  float refP_ = 0, refR_ = 0, refSumP_ = 0, refSumR_ = 0;
  int refN_ = 0;
  float cP_ = 0, cR_ = 0;        // measured tilt at the crossing (relative)
  float dP_ = 0, dR_ = 0;        // predicted change crossing -> lift pose
  float predCP_ = 0, predCR_ = 0;
  float progMax_ = 0;
  bool tucked_ = false;
  float trimStart_ = 0, trim_ = 0, deskTrim_ = 0;
  float leanT_ = 0;
  GaitKey liftKey_ = GK_LIFT;
  bool abortFast_ = false, abortStalled_ = false;
  int abortStage_ = 0;
  GaitResult pending_ = GR_DONE;
  float restVolts_ = -1, deskP_ = 0, deskR_ = 0, yaw0_ = 0;
  bool rearMatch_ = false, deskKnown_ = false;
  bool liftTest_ = false;
  float holdOverride_ = 0;
  // glide
  float glideV_ = 0, glideCruise_ = 0;
  int armed_ = 0;
  // march
  float marchT_ = 0, marchDur_ = 0;
  // calibration
  int calStage_ = 0;
  float calTrim_ = 0;
  bool calFound_ = false;
  bool calFrontOk_[2] = {false, false};
  bool calRearOk_[2] = {false, false};
  float calLean_[2] = {0, 0};
  float lastProbeProgress_ = 0;
  GaitStatus st_{};
};

}  // namespace body
}  // namespace spike
