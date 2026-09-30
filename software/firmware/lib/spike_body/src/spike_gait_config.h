// spike_gait_config.h -- EVERY tunable of Spike's walking, give-paw, balance calibration and the desk-edge
// laser threshold, in one place. Platform-free (compiled on the PC for the host tests too).
//
// Sources (the review's corrections win where the two differ):
//   cad/stability_max_research.md     the "tilt-step march" spec: keyframes, timings, IMU and abort rules
//   cad/stability_research_review.md  wheels PWM-OFF in leg phases, tilt first / tuck second, lift 0.8-1.0 s,
//                                     sag compensation in 0.5 deg steps both ways, lasers ignored for the
//                                     whole leg phase, desk-edge level reading ~94 mm (not 40-80)
//   cad/servo_load_check_v3_1_walk_options.md  rear-step walk and wheel-assisted march (the fallbacks)
// Angles in degrees, times in seconds, lengths in mm. Change values here, not in the code.
#pragma once
#include <stdint.h>

namespace spike {
namespace body {

// ---- desk-edge lasers: threshold from the level reading, tilt-compensated -------------------------
struct EdgeLaserConfig {
  float fallbackMm = 110;       // threshold until / unless a level calibration exists (the old fixed value)
  float marginMm = 25;          // threshold = expected reading for the current tilt + this
  float minBaselineMm = 40;     // a plausible level reading (review estimate: ~94 mm, laser ~85 mm up)
  float maxBaselineMm = 150;
  float maxSpreadMm = 8;        // one laser's samples must agree within this during the calibration
  float maxLevelTiltDeg = 4;    // |pitch| and |roll| (absolute, IMU) must be below this to calibrate
  float maxRateDps = 3;         // ... and the body still (gyro)
  float calSeconds = 1.0f;      // samples collected for the startup calibration
  // Geometry (review: laser on the 25 deg incline of the tub floor -> beam 65 deg below horizontal).
  // Fitted to the review's own estimates: level 94, nose-up 3.5 deg -> ~105, 8 deg -> ~120, 12 deg -> ~136.
  float beamDownDeg = 65;       // beam angle below the horizontal when the robot stands level
  float leverFrontMm = 111;     // nose-up raises the front edge lasers by lever * sin(pitch)
  float leverRearMm = 17;       // ... and lowers the rear one by this lever * sin(pitch)
  float lateralMm = 35;         // front edge lasers sit this far left / right of the centre line
  float maxCompDeg = 12;        // tilt used for the compensation is clamped to this
  float maxThresholdMm = 200;   // the compensated threshold never exceeds this
  uint8_t recheckReadings = 5;  // fresh clear readings on EVERY desk-edge laser before a gait glide
};

// ---- the gait ---------------------------------------------------------------------------------------
struct GaitConfig {
  // IMU tilt estimate (complementary filter; accelerometer only if the gyro is missing)
  float tiltTauS = 0.25f;
  float accOnlyTauS = 0.08f;

  // before any step
  float levelRefS = 0.5f;          // research rule 1: average the IMU in the stand at every walk start
  float settleMinS = 0.2f;         // F1
  float settleQuietS = 0.1f;       // roll and pitch rates under settleRateDps for this long
  float settleRateDps = 5;
  float settleTimeoutS = 2.5f;     // never quiet -> the walk stops (something is wrong)

  // front paw step (tilt-step march) -- review items 3 and 4
  float shiftS = 0.8f;             // F2: stand -> crossing (four paws)
  float shiftTolDeg = 1.5f;        // F2 gate: measured tilt within this of the crossing prediction
  float tiltS = 0.9f;              // F3: the three stance legs -> lift pose, lifted leg HELD at crossing angles
  float tuckStartProgress = 0.6f;  // tuck only after the tilt change has passed 60 % of its prediction
  float tuckS = 0.5f;              // then the lifted paw tucks up and back
  float tiltWaitS = 0.3f;          // tilt move done but no lift-off yet: wait this long, then lean in steps
  float holdS = 0.3f;              // F4
  float holdRateDps = 10;          // F4 gate before setting down
  float setDownS = 0.6f;           // F5
  float unshiftS = 0.6f;           // F6

  // closed-loop lean (review item 2): 0.5 deg steps BOTH ways until the tilt matches the prediction
  float leanStepDeg = 0.5f;
  float leanStepS = 0.25f;         // move time of one lean step
  float leanSettleS = 0.25f;       // wait after a step before judging again
  float leanTolDeg = 0.5f;         // |measured - predicted| tilt change along the predicted direction
  float leanTimeoutS = 2.0f;       // not reached in this long -> abort (paw down, level, stand)
  float leanMaxAdjDeg = 1.5f;      // most the loop may move the lean away from the step's starting trim
  // +1: an over-tilt (more tilt than predicted) is answered with LESS lean, as the review says. DAY-1 TEST
  // (FLASHING_CHECKLIST 5d, step 6) confirms the sign on the real robot; set -1 if the tilt moved the other way.
  float leanLoopSign = 1;

  // aborts (research rules 2 and 3, review item 7)
  float abortRateDps = 20;         // roll or pitch rate above this in any three-paw phase -> fast abort
  float dropBackDeg = 1.0f;        // tilt falls back toward the lifted paw by this much -> paw reloading
  float overTiltDeg = 3.0f;        // measured tilt this far beyond the prediction -> tipping trend
  float fastAbortS = 0.2f;         // fast abort: lifted leg straight back to its crossing angles

  // learning (research rule 5 as corrected by review item 2)
  float learnStepDeg = 0.5f;
  float trimCapDeg = 3.0f;         // beyond this the tilt-step is switched off until a new calibration
  uint8_t abortsBeforeFallback = 2;  // same paw aborts twice in a row -> rear-step walk for the rest

  // conditions (research rules 1 and 4)
  float maxDeskTiltDeg = 3.0f;     // desk tilt above this: no front-paw lifts (rear steps + glides only)
  float deskTrimStartDeg = 1.0f;   // 1..3 deg: add the matching lean trim
  float deskTrimGain = 1.25f;      // deg of lean per deg of harmful desk tilt (1.9 mm/deg vs 1.5 mm/deg)
  float minRestVolts = 7.4f;       // resting battery below this: no paw lifts (wheel-assisted march only)

  // rear paw step (R1-R3); no lean loop (a back lift is naturally stable, 12 mm margin, 0.10 kg.cm)
  float rearLiftS = 0.5f, rearHoldS = 0.3f, rearDownS = 0.4f;
  float rearTolDeg = 1.5f;         // calibration: measured tilt change within this of the prediction

  // glide between steps (four paws down only)
  float glideMm = 40;
  float glideS = 1.0f;
  float glideRampS = 0.25f;        // linear speed ramps: peak ~53 mm/s, ~0.21 m/s^2
  float glideSettleS = 0.2f;
  float wheelRearmS = 0.15f;       // wheels are switched back on one at a time (staggered power rule)
  float yawTrimMax = 0.10f;        // +-10 % left/right trim from the gyro to hold the heading
  float yawGainPerDeg = 0.02f;

  // wheel-assisted march (the last fallback): paws stay on the desk, the legs bob, the wheels roll
  float marchSpeed = 0.2f;         // wheel command (x 0.16 m/s = 32 mm/s)
  float marchStepMm = 40;          // distance per requested step
  float marchBobDeg = 5;           // crouch of the bobbing diagonal pair (foot stays under the hip)
  float marchPeriodS = 1.0f;
  float marchRampS = 0.3f;

  // give paw
  float pawReachS = 0.6f;          // lifted leg crossing angles -> paw pose, after the tilt has lifted it
  float pawHoldS = 1.5f;
  // The puppy-sit variant (paw 61 mm up, 12 deg nose-up) is unproven as a MOVE (review item 6) and its
  // back-left pod clears the desk by ~1.1 mm. OFF until the day-1 tests pass (FLASHING_CHECKLIST 5d).
  bool puppySitPaw = false;
  bool requireCalibration = true;  // no front-paw lift (march or paw) before the balance calibration passed

  // day-1 balance calibration
  float calLevelS = 1.0f;
  float calMaxMountDeg = 8;        // IMU reads more than this on a level desk: mounting is wrong -> fail
  float calStartTrimDeg = -1.0f;   // lean trims probed from here upward in leanStepDeg steps
  float calMarginTrimDeg = 0.5f;   // stored trim = the first trim that unloads the paw + this
  float calProbeWaitS = 0.5f;

  uint8_t maxSteps = 16;           // one request: at most this many steps
};

}  // namespace body
}  // namespace spike
