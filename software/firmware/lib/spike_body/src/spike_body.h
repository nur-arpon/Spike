// spike_body.h -- Spike's body control core (platform-free, unit-tested on the PC).
//
//  * the joint model: 13 servos on two PCA9685 boards, channel map exactly as the assembly guide
//    (guide/src/data_wiring.py SERVO_CH / LASER_CH, guide/tools/servo_center): board A 0x40 (left
//    wall) = left legs + tail, board B 0x41 (right wall) = right legs + the 7 laser XSHUT lines.
//  * joint limits (cad/print_v3_1_README.md "Joint limits"): hip +-30, knee +-50, and on the REAR legs
//    "when the hip is above +25 deg, keep the knee at or below +45 deg". Angles: 0 = leg straight
//    down (modelled pose), + moves the foot FORWARD. Left/right mirroring is a per-servo direction.
//  * calibration (per servo: centre pulse, direction, pulse per degree; wheels: stop pulse, direction),
//    stored by the screen board in NVS.
//  * poses (stand, sit, lie down, play bow, lean left/right = "head tilt via the body", lean forward)
//    and slewed transitions, the tail wag, differential wheel drive.
//  * the motion sequences for every action label (actions.js `label` + the v1.1 comfort actions).
//  * the SAFETY monitor, which runs locally and never waits for Wi-Fi: desk-edge lasers stop the
//    wheels, obstacle lasers block driving into things, the IMU detects falls and pick-ups, the battery
//    warns at 7.0 V and parks + cuts the servos at 6.8 V, and a heartbeat supervisor parks everything
//    if the controller stalls. The desk-edge threshold is the level reading measured at startup + a margin,
//    tilt-compensated from the IMU (spike_gait_config.h EdgeLaserConfig); 110 mm until then.
//  * walking, give-paw and the day-1 balance calibration: spike_gait.h (the Controller runs the Gait and
//    keeps every safety layer above in the path; wheels PWM-off in leg phases).
#pragma once
#include <stdint.h>
#include "spike_gait_config.h"

namespace spike {
namespace body {

// ---- servos ---------------------------------------------------------------------------------
enum Joint : uint8_t {
  HIP_FL, KNEE_FL, WHEEL_FL, HIP_BL, KNEE_BL, WHEEL_BL, TAIL,
  HIP_FR, KNEE_FR, WHEEL_FR, HIP_BR, KNEE_BR, WHEEL_BR,
  JOINT_COUNT
};
enum Leg : uint8_t { LEG_FL, LEG_FR, LEG_BL, LEG_BR, LEG_COUNT };

struct ServoMap { const char* name; uint8_t board; uint8_t channel; bool wheel; };
extern const ServoMap kServoMap[JOINT_COUNT];  // guide table, board 0 = A (0x40), 1 = B (0x41)

enum Laser : uint8_t { LASER_FRONT, LASER_REAR, EDGE_FL, EDGE_FR, EDGE_REAR, LASER_SIDE_L, LASER_SIDE_R, LASER_COUNT };
struct LaserMap { const char* name; uint8_t xshutChannel; uint8_t address; };
extern const LaserMap kLaserMap[LASER_COUNT];  // XSHUT on board B ch 9..15, new I2C address each

static const uint8_t PCA_ADDR[2] = {0x40, 0x41};

struct ServoCal {
  int16_t centerUs;    // pulse at 0 deg (legs, tail) / stop pulse (wheels)
  int8_t dir;          // +1 / -1: sign from joint angle (+ = foot forward) to pulse
  float usPerDeg;      // MG90S: ~ 1000 us per 90 deg
  int16_t minUs, maxUs;
};
struct Calibration {
  uint16_t version;
  ServoCal servo[JOINT_COUNT];
  void setDefaults();
  bool valid() const;
};

// ---- joint limits ---------------------------------------------------------------------------
static const float HIP_MIN = -30, HIP_MAX = 30, KNEE_MIN = -50, KNEE_MAX = 50;
static const float TAIL_MIN = -45, TAIL_MAX = 45;
static const float REAR_HIP_RULE = 25, REAR_KNEE_CAP = 45;
// Clamp a leg's (hip, knee) in degrees into the safe envelope. Returns true if it changed anything.
bool limitLeg(Leg leg, float* hip, float* knee);

// ---- poses ----------------------------------------------------------------------------------
struct Pose {
  float hip[LEG_COUNT];   // FL FR BL BR, degrees
  float knee[LEG_COUNT];
  float tail;             // degrees, + = to the robot's left
};
enum PoseId : uint8_t { POSE_STAND, POSE_SIT, POSE_LIE, POSE_PLAY_BOW, POSE_LEAN_LEFT, POSE_LEAN_RIGHT,
                        POSE_LEAN_FORWARD, POSE_PARK, POSE_COUNT };
const Pose& pose(PoseId id);
const char* poseName(PoseId id);
Pose blend(const Pose& a, const Pose& b, float t);

// ---- motion sequences (action labels) -------------------------------------------------------
enum TailMode : uint8_t { TAIL_HOLD, TAIL_WAG, TAIL_SLOW_WAG, TAIL_DOWN, TAIL_UP };
enum Drive : uint8_t { DRIVE_NONE, DRIVE_SPIN, DRIVE_WIGGLE, DRIVE_BACK_OFF };
struct Keyframe {
  float t;          // seconds from the action start
  PoseId pose;
  float moveS;      // transition time to this pose
  TailMode tail;
  float tailHz, tailAmp;
  Drive drive;
  float driveSpeed; // 0..1
};
struct Sequence { const char* label; const Keyframe* keys; uint8_t n; float length; };
const Sequence* findSequence(const char* label);  // label from actions.js, or "snuggle" / "slowWag"
int sequenceCount();
const Sequence& sequenceAt(int i);

// ---- safety ---------------------------------------------------------------------------------
struct SafetyConfig {
  // desk-edge laser: farther than the threshold = no desk. The threshold is the level reading measured at
  // startup (robot standing still and level) + a margin, compensated for the body tilt (IMU); before that,
  // or if it never succeeds, the stored reading from the last good calibration, else 110 mm. See
  // spike_gait_config.h EdgeLaserConfig (review: the real level reading is ~94 mm, not 40-80).
  EdgeLaserConfig laser;
  float obstacleMm = 70;     // obstacle laser: nearer than this blocks driving that way
  uint8_t edgeConfirm = 2;   // consecutive readings before EDGE (lasers glitch)
  uint8_t clearConfirm = 5;  // consecutive readings before CLEAR
  float warnVolts = 7.0f, cutVolts = 6.8f, resumeVolts = 7.3f;
  float cutHoldS = 5.0f;     // below cutVolts this long (servo current sags the pack)
  float fallTiltDeg = 50;    // body tilt beyond this = fallen
  float pickupG = 0.35f;     // |a| deviation from 1 g (low-passed) for a pick-up
  float pickupHoldS = 0.4f;
  float heartbeatS = 0.3f;   // controller must tick at least this often
};

struct SensorFrame {           // one control tick's inputs
  float dt;                    // seconds since the previous tick
  float laserMm[LASER_COUNT];  // < 0 = no reading this tick (sensor missing / not ready)
  bool laserOk[LASER_COUNT];   // sensor present and initialised
  float ax, ay, az;            // accelerometer, g (x forward, y left, z up), valid if imuOk
  bool imuOk;
  bool gyroOk = false;         // gyro valid (MPU6050), deg/s about the body x / y / z axes
  float gx = 0, gy = 0, gz = 0;
  float volts;                 // battery, ~0.4 s average, < 0 = unknown (warn / cut decisions)
  float voltsFast = -1;        // battery, ~40 ms average, < 0 = use volts (brown-out response)
};

enum SafetyEvent : uint8_t {
  EV_NONE, EV_EDGE_FL, EV_EDGE_FR, EV_EDGE_REAR, EV_CLEAR_FL, EV_CLEAR_FR, EV_CLEAR_REAR,
  EV_PICKUP, EV_PUTDOWN, EV_FALL, EV_BATTERY_WARN, EV_BATTERY_CUT, EV_BATTERY_OK,
  EV_LOW_POWER, EV_POWER_OK,  // fast brown-out guard (Controller): moves limited below lowPowerVolts
  EV_EDGE_CALIBRATED,         // the desk-edge level readings were measured (save them: Safety::edgeCal)
  EV_GAIT_DONE                // a walk / give-paw / balance calibration ended (Controller::gait.status())
};

struct SafetyState {
  bool edge[3];              // FL FR REAR
  bool blockFwd, blockBack;  // wheel directions forbidden right now
  bool fallen, pickedUp;
  bool battWarn, battCut;
  float lowSince;
  float tiltDeg;
  float pitchDeg, rollDeg;   // body tilt from the accelerometer (+ nose up, + left side lower), low-passed
};

struct EdgeCalState {
  bool done;                 // every present desk-edge laser was measured this boot
  bool fresh[3];             // FL FR REAR measured this boot
  bool ok[3];                // a level reading (fresh or stored) is in use for this laser
  float baseline[3];         // level reading, mm
  float refPitch, refRoll;   // body tilt when it was measured (deg)
};

class Safety {
 public:
  SafetyConfig cfg;
  SafetyState st{};
  // Feed one tick; up to 8 events are written to ev (returns the count).
  int tick(const SensorFrame& f, SafetyEvent* ev, int maxEv);
  // Filter a wheel command (left/right speed -1..1, + = forward) through the current blocks.
  void filterDrive(float* left, float* right) const;
  bool legsAllowed() const { return !st.battCut && !st.fallen; }

  // Desk-edge threshold for edge laser i (0 FL, 1 FR, 2 REAR) at the current tilt.
  float edgeThreshold(int i) const;
  // The level readings from NVS (last good calibration): used until this boot's own measurement.
  void useStoredBaseline(const float mm[3], const bool ok[3], float refPitch, float refRoll);
  EdgeCalState edgeCal{};
  // Set by the Controller: true only while the wheels are PWM-off in a gait leg phase. The desk-edge
  // readings are then skipped (the body tilts nose-up; the wheels cannot move).
  bool ignoreEdges = false;
  // Set by the Controller: standing still in the plain stand (the startup level measurement waits for it).
  bool standing = false;
  // Every desk-edge laser present, not at an edge, and >= laser.recheckReadings clear readings since the
  // last leg phase: a gait glide may start.
  bool edgeRecheckOk() const;

 private:
  uint8_t edgeCount_[3] = {0, 0, 0}, clearCount_[3] = {0, 0, 0}, freshClear_[3] = {0, 0, 0};
  bool lastOk_[3] = {false, false, false};
  float pickupTimer_ = 0, calmTimer_ = 0, lowTimer_ = 0, gLp_ = 1;
  bool tiltInit_ = false;
  float calT_ = 0, calSum_[3] = {0, 0, 0}, calMin_[3] = {0, 0, 0}, calMax_[3] = {0, 0, 0};
  float calSumP_ = 0, calSumR_ = 0;
  int calN_[3] = {0, 0, 0}, calTiltN_ = 0;
  void calReset();
};

}  // namespace body
}  // namespace spike

#include "spike_gait.h"  // needs Pose / Leg / limitLeg above

namespace spike {
namespace body {

// ---- the body controller (platform-free part) ------------------------------------------------
struct BodyOutput {
  float angle[JOINT_COUNT];   // legs / tail in degrees (limited); wheels: speed -1..1
  bool enabled[JOINT_COUNT];  // false = PWM off (limp / stop)
};

// Motion limits from the servo load check (cad/servo_load_check_v3_1.md, 983 g robot, MG90S at 4.8 V).
struct MotionConfig {
  float wheelTopSpeed = 0.16f;   // m/s at wheel command 1.0 (report: top speed about 0.16 m/s)
  float maxAccel = 1.5f;         // m/s^2 for EVERY wheel speed change, stops included (hip 2.6 -> 0.68 kg.cm)
  float maxSpinSpeed = 0.4f;     // wheel command cap while turning in place (tyre scrub loads the hips)
  float spinBurstS = 0.5f;       // longest continuous turn in place ...
  float spinRestS = 0.4f;        // ... followed by at least this long without turning
  float tailMaxAmp = 30;         // deg: tail wag cap
  float tailMaxDegPerS = 565;    // MG90S no-load speed at 4.8 V: +-30 deg at 3 Hz; faster wags shrink
  float jointSlewDegPerS = 400;  // normal joint rate limit (below the servo's ~600 deg/s)
  float staggerS = 0.15f;        // power-up: one servo output switched on every 150 ms (no 7.6 A inrush)
  float lowPowerVolts = 7.2f;    // fast battery reading below this -> low-power motion (brown-out guard)
  float lowPowerExitVolts = 7.4f, lowPowerExitS = 2.0f;
  float lowPowerSlewDegPerS = 60;  // low power: slow joints, ONE leg moving at a time, no spins, half speed
  float dipVolts = 6.6f;         // a dip below this freezes every joint for dipHoldS (let the pack recover)
  float dipHoldS = 0.5f;
};

class Controller {
 public:
  Controller();
  Safety safety;
  Calibration cal;
  MotionConfig mcfg;
  // Start the motion for an action label (actions.js label, "snuggle", "slowWag"). False if unknown.
  bool play(const char* label);
  void setPose(PoseId id, float moveS);
  void setDrive(float left, float right, float seconds);  // explicit wheel command (future `move`)
  void stopAll();                                         // wheels stop, sequence stops, hold pose
  // Switch the servo outputs on again one at a time (boot, after OE was high, after a fall).
  void restartPowerUp();
  // One control tick (50 Hz). Fills out; events go to ev.
  int tick(const SensorFrame& f, BodyOutput* out, SafetyEvent* ev, int maxEv);
  // Pulse width for a joint from an angle (legs/tail) or speed (wheels), with limits + calibration.
  int pulseUs(int joint, float value) const;
  const char* activeLabel() const { return seq_ ? seq_->label : nullptr; }
  PoseId currentPose() const { return target_; }
  bool lowPower() const { return lowPower_; }
  float wheelLeft() const { return wheelL_; }
  float wheelRight() const { return wheelR_; }

  // ---- walking and give-paw (spike_gait.h). The gait owns the legs and wheels while it runs; every
  // safety layer above still applies (edge / obstacle filter, ramps, brown-out guard, limits, stagger).
  Gait gait;
  bool walk(GaitStyle style, int direction, int steps);
  bool givePaw(Leg paw, bool fromSit);
  bool calibrateBalance();
  bool liftTest(Leg paw, float seconds);  // day-1 test: one front paw up in the lift pose for `seconds`
  void stopGait() { gait.stop(); }
  const GaitOutput& gaitOutput() const { return gout_; }
  bool wheelsOffNow() const { return wheelsOffNow_; }  // wheels PWM-off this tick (gait leg phase)

 private:
  bool gaitAllowed(const char** why) const;
  GaitOutput gout_{};
  bool gaitWasActive_ = false, wheelsOffNow_ = false, poseReached_ = true;
  const Sequence* seq_ = nullptr;
  float seqT_ = 0;
  int key_ = -1;
  Pose from_{}, cur_{}, out_{};
  PoseId target_ = POSE_STAND;
  float moveT_ = 0, moveS_ = 0.001f;
  TailMode tail_ = TAIL_HOLD;
  float tailHz_ = 0, tailAmp_ = 0, tailPhase_ = 0;
  Drive drive_ = DRIVE_NONE;
  float driveSpeed_ = 0, driveT_ = 0;
  float manualL_ = 0, manualR_ = 0, manualS_ = 0;
  bool parked_ = false;
  float wheelL_ = 0, wheelR_ = 0;     // ramped wheel commands
  float spinT_ = 0, spinRest_ = 0;    // spin burst guard
  int enabledCount_ = 0;              // power-up stagger
  float staggerT_ = 0;
  bool wasLegsAllowed_ = true;
  bool lowPower_ = false;
  float lowPowerOkT_ = 0, dipHold_ = 0;
  float tailOut_ = 0;                 // slewed tail angle
};

}  // namespace body
}  // namespace spike
