// body_hw.cpp -- the body task: every device on the P4 robot bus, the safety reflexes and the servos.
//
// 50 Hz, core 0, above the network in priority. Everything that keeps Spike on the desk runs HERE,
// locally, and never waits for Wi-Fi (lib/spike_body Safety + Controller do the deciding):
//   desk-edge lasers -> wheels stop the same tick; fall / pick-up from the lasers + MPU6050;
//   battery 7.0 V warn / 6.8 V park + servos off; joint limits on every pulse.
// Stall protection, two layers:
//   * an esp_timer supervisor pulls OE HIGH (all PCA9685 outputs off) if this task has not ticked
//     for BODY_STALL_MS; the lasers (XSHUT on board B) lose power with it, so they are re-initialised
//     before OE goes low again (guide OPEN_QUESTIONS A1);
//   * the task watchdog reboots the chip after WDT_TIMEOUT_S; during reset the 2.2 k pull-up holds
//     OE high, so the wheels stop.
#include "app.h"
#include "config.h"
#include "spike_body.h"
#include <Wire.h>
#include <Preferences.h>
#include <VL53L0X.h>
#include <esp_task_wdt.h>
#include <esp_timer.h>

using namespace spike::body;

static QueueHandle_t bodyQ;
static Controller ctl;
static bool pcaOk[2] = {false, false};
static bool imuOk = false, mprOk = false, apdsOk = false;
static VL53L0X lasers[LASER_COUNT];
static bool laserOk[LASER_COUNT];
static volatile uint32_t lastTickMs = 0;
static volatile bool stalled = false;
static volatile bool inhibit = false;
static volatile float vbat = -1;
static int16_t lastPulse[JOINT_COUNT];
static bool lastOn[JOINT_COUNT];
static bool listeningPause = false;
static bool i2cStarted = false;
static volatile float lastMm[LASER_COUNT];
static volatile float lastAx, lastAy, lastAz;
static volatile uint16_t lastPadBits;
static bool gaitDirty = false;

bool postBody(const BodyCmd& c) { return bodyQ && xQueueSend(bodyQ, &c, 0) == pdTRUE; }
float bodyBatteryVolts() { return vbat; }
void bodySetInhibit(bool on) { inhibit = on; if (on) digitalWrite(PIN_SERVO_OE, HIGH); }

// ---- I2C helpers ---------------------------------------------------------------------------------
static bool present(uint8_t a) { Wire.beginTransmission(a); return Wire.endTransmission() == 0; }
static void wr8(uint8_t a, uint8_t reg, uint8_t v) { Wire.beginTransmission(a); Wire.write(reg); Wire.write(v); Wire.endTransmission(); }
static bool rdN(uint8_t a, uint8_t reg, uint8_t* b, int n) {
  Wire.beginTransmission(a);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)a, n) != n) return false;
  for (int i = 0; i < n; i++) b[i] = Wire.read();
  return true;
}

// ---- PCA9685 (same init as guide/tools/servo_center) -------------------------------------------
static const uint8_t PRESCALE = 121;  // 25 MHz / (4096 * 122) = 50.0 Hz
static const float PERIOD_US = 4096.0f * (PRESCALE + 1) / 25.0f;

static void pcaInit(uint8_t a) {
  wr8(a, 0x00, 0x10);        // sleep (prescaler can only be set asleep)
  wr8(a, 0xFE, PRESCALE);
  wr8(a, 0x01, 0x04);        // totem-pole; outputs LOW while OE is high
  wr8(a, 0x00, 0x20);        // wake, auto-increment
  delay(2);
  wr8(a, 0x00, 0xA0);        // restart
  // every channel full OFF (limp) until the controller enables it
  Wire.beginTransmission(a);
  Wire.write(0xFA);          // ALL_LED_ON_L
  Wire.write(0); Wire.write(0); Wire.write(0); Wire.write(0x10);
  Wire.endTransmission();
}

static void pcaRaw(uint8_t a, uint8_t ch, uint16_t on, uint16_t off) {
  Wire.beginTransmission(a);
  Wire.write(0x06 + 4 * ch);
  Wire.write(on & 0xFF); Wire.write(on >> 8);
  Wire.write(off & 0xFF); Wire.write(off >> 8);
  Wire.endTransmission();
}
static void pcaPulse(uint8_t a, uint8_t ch, int us) {
  uint16_t ticks = (uint16_t)lroundf(us * 4096.0f / PERIOD_US);
  if (ticks > 4095) ticks = 4095;
  pcaRaw(a, ch, 0, ticks);
}
static void pcaDigital(uint8_t a, uint8_t ch, bool high) { if (high) pcaRaw(a, ch, 0x1000, 0); else pcaRaw(a, ch, 0, 0x1000); }

// ---- lasers: wake one at a time through XSHUT (board B ch 9..15) and give each its own address -----
static void lasersInit() {
  for (int l = 0; l < LASER_COUNT; l++) laserOk[l] = false;
  if (!pcaOk[1]) { logf("body: servo board B (0x41) missing -- lasers unavailable, desk edges treated as unsafe"); return; }
  for (int l = 0; l < LASER_COUNT; l++) pcaDigital(PCA_ADDR[1], kLaserMap[l].xshutChannel, false);
  delay(10);
  for (int l = 0; l < LASER_COUNT; l++) {
    pcaDigital(PCA_ADDR[1], kLaserMap[l].xshutChannel, true);
    delay(3);
    VL53L0X& s = lasers[l];
    s.setBus(&Wire);
    s.setAddress(0x29);  // library's idea of the address after a reset
    s.setTimeout(30);
    if (!s.init()) { logf("body: laser '%s' did not answer (XSHUT B%d)", kLaserMap[l].name, kLaserMap[l].xshutChannel); continue; }
    s.setAddress(kLaserMap[l].address);
    bool edge = (l == EDGE_FL || l == EDGE_FR || l == EDGE_REAR);
    s.setMeasurementTimingBudget(edge ? 20000 : 33000);
    s.startContinuous(0);
    laserOk[l] = true;
  }
  int ok = 0;
  for (int l = 0; l < LASER_COUNT; l++) ok += laserOk[l];
  logf("body: %d of %d lasers running", ok, LASER_COUNT);
}

// Non-blocking read: returns mm, or -1 if no new measurement.
static float laserRead(int l) {
  VL53L0X& s = lasers[l];
  uint8_t st = s.readReg(0x13);  // RESULT_INTERRUPT_STATUS
  if ((st & 0x07) == 0) return -1;
  uint16_t mm = s.readReg16Bit(0x14 + 10);
  s.writeReg(0x0B, 0x01);        // SYSTEM_INTERRUPT_CLEAR
  if (s.last_status != 0) { laserOk[l] = false; return -1; }
  return mm >= 8000 ? 9999.0f : (float)mm;  // 8190 / 8191 = nothing in range = far
}

// ---- MPU6050 / MPR121 / APDS-9960 ---------------------------------------------------------------
static void imuInit() {
  imuOk = present(ADDR_MPU6050);
  if (!imuOk) { logf("body: MPU6050 not found"); return; }
  uint8_t who = 0;
  rdN(ADDR_MPU6050, 0x75, &who, 1);
  wr8(ADDR_MPU6050, 0x6B, 0x01);  // wake, PLL
  wr8(ADDR_MPU6050, 0x1A, 0x03);  // DLPF 44 Hz
  wr8(ADDR_MPU6050, 0x1B, 0x00);  // gyro +-250 deg/s (131 LSB per deg/s)
  wr8(ADDR_MPU6050, 0x1C, 0x00);  // +-2 g
  logf("body: MPU6050 WHO_AM_I 0x%02X (clones may report another id; it is used anyway)", who);
}
static float gyroBias[3] = {0, 0, 0};
// Accelerometer (g) and gyro (deg/s, bias removed) in body axes (x forward, y left, z up). The GY-521
// sits flat under the lid; the mapping assumes its X arrow points to the head. Change here (both
// sensors together) if `gait imu` shows otherwise (FLASHING_CHECKLIST 5d step 2).
static bool imuRead(float* ax, float* ay, float* az, float* gx, float* gy, float* gz) {
  uint8_t b[14];
  if (!imuOk || !rdN(ADDR_MPU6050, 0x3B, b, 14)) return false;
  *ax = (int16_t)((b[0] << 8) | b[1]) / 16384.0f;
  *ay = (int16_t)((b[2] << 8) | b[3]) / 16384.0f;
  *az = (int16_t)((b[4] << 8) | b[5]) / 16384.0f;
  *gx = (int16_t)((b[8] << 8) | b[9]) / 131.0f - gyroBias[0];
  *gy = (int16_t)((b[10] << 8) | b[11]) / 131.0f - gyroBias[1];
  *gz = (int16_t)((b[12] << 8) | b[13]) / 131.0f - gyroBias[2];
  return true;
}
// Gyro bias at boot (the robot sits still while the servo outputs are still off); refined later while
// standing still (body task). Clone MPU6050 gyros are often a few deg/s off, which would upset the gait's
// "rates under 5 deg/s" gates and its tilt filter.
static void gyroBiasInit() {
  if (!imuOk) return;
  float s[3] = {0, 0, 0};
  int n = 0;
  for (int i = 0; i < 100; i++) {
    float ax, ay, az, g[3];
    if (imuRead(&ax, &ay, &az, &g[0], &g[1], &g[2])) { for (int k = 0; k < 3; k++) s[k] += g[k]; n++; }
    delay(5);
  }
  if (n < 50) return;
  for (int k = 0; k < 3; k++) gyroBias[k] = s[k] / n;
  logf("body: gyro bias %.2f %.2f %.2f deg/s", gyroBias[0], gyroBias[1], gyroBias[2]);
}

static void mprInit() {
  mprOk = present(ADDR_MPR121);
  if (!mprOk) { logf("body: MPR121 not found"); return; }
  wr8(ADDR_MPR121, 0x80, 0x63);  // soft reset
  delay(2);
  wr8(ADDR_MPR121, 0x5E, 0x00);  // stop mode while configuring
  for (int e = 0; e < 5; e++) {  // foil pads behind plastic: sensitive thresholds
    wr8(ADDR_MPR121, 0x41 + 2 * e, 8);  // touch
    wr8(ADDR_MPR121, 0x42 + 2 * e, 4);  // release
  }
  wr8(ADDR_MPR121, 0x5B, 0x01);  // debounce
  wr8(ADDR_MPR121, 0x5D, 0x04);  // filter config
  wr8(ADDR_MPR121, 0x7B, 0x0B);  // auto-config on
  wr8(ADDR_MPR121, 0x7D, 200);   // USL
  wr8(ADDR_MPR121, 0x7E, 130);   // LSL
  wr8(ADDR_MPR121, 0x7F, 180);   // target
  wr8(ADDR_MPR121, 0x5E, 0x85);  // run, electrodes 0..4, baseline tracking on
  logf("body: MPR121 touch pads E0..E4");
}

static void apdsInit() {
  apdsOk = present(ADDR_APDS9960);
  if (!apdsOk) { logf("body: APDS-9960 not found"); return; }
  uint8_t id = 0;
  rdN(ADDR_APDS9960, 0x92, &id, 1);
  wr8(ADDR_APDS9960, 0x80, 0x00);
  wr8(ADDR_APDS9960, 0x8E, 0x87);  // proximity pulse count / length
  wr8(ADDR_APDS9960, 0x8F, 0x0C);  // proximity gain 8x
  wr8(ADDR_APDS9960, 0x80, 0x05);  // power on + proximity enable
  logf("body: APDS-9960 id 0x%02X, proximity mode (hand near / wave)", id);
}

// ---- calibration in NVS ------------------------------------------------------------------------
static void calLoad() {
  Preferences p;
  p.begin("spikecal", true);
  Calibration c;
  size_t n = p.getBytes("cal", &c, sizeof c);
  p.end();
  if (n == sizeof c && c.valid()) { ctl.cal = c; logf("body: calibration loaded"); }
  else { ctl.cal.setDefaults(); logf("body: no calibration saved -- defaults (1500 us centres)"); }
}
static void calSave() {
  Preferences p;
  p.begin("spikecal", false);
  p.putBytes("cal", &ctl.cal, sizeof ctl.cal);
  p.end();
  logf("body: calibration saved");
}

// Gait trims (balance calibration, learned lean, desk-edge level readings) next to the servo calibration.
static void gaitLoad() {
  Preferences p;
  p.begin("spikecal", true);
  GaitTrims t;
  size_t n = p.getBytes("gait", &t, sizeof t);
  ctl.gait.cfg.puppySitPaw = p.getBool("puppy", false);
  ctl.gait.cfg.leanLoopSign = p.getChar("lsign", 1) < 0 ? -1.0f : 1.0f;
  p.end();
  if (n == sizeof t && t.valid()) {
    ctl.gait.trims = t;
    ctl.safety.useStoredBaseline(t.laserMm, t.laserOk, t.laserRefPitch, t.laserRefRoll);
    logf("body: balance %s (FL %s %+.1f, FR %s %+.1f, back %s); desk-edge level readings %s", t.calibrated ? "calibrated" : "NOT calibrated",
         t.tiltOk[0] ? "ok" : "off", t.lean[0], t.tiltOk[1] ? "ok" : "off", t.lean[1], t.rearOk ? "ok" : "off",
         (t.laserOk[0] || t.laserOk[1] || t.laserOk[2]) ? "stored" : "none yet");
  } else {
    ctl.gait.trims.setDefaults();
    logf("body: no balance calibration yet (gait cal) -- walks use the rear-step walk, give paw is off");
  }
}
static void gaitSave() {
  Preferences p;
  p.begin("spikecal", false);
  p.putBytes("gait", &ctl.gait.trims, sizeof ctl.gait.trims);
  p.putBool("puppy", ctl.gait.cfg.puppySitPaw);
  p.putChar("lsign", ctl.gait.cfg.leanLoopSign < 0 ? -1 : 1);
  p.end();
}

// Day-1 visibility: one log line each time a paw is up (measured vs predicted tilt, lean in use).
static void gaitPhaseLog() {
  static GaitPhase last = GP_IDLE;
  static float holdStart = 0;
  const GaitStatus& g = ctl.gait.status();
  if (g.phase == last) return;
  if (g.phase == GP_HOLD || g.phase == GP_REAR_HOLD) {
    const char* names[4] = {"front-left", "front-right", "back-left", "back-right"};
    logf("gait: %s paw up, tilt %+.1f / %+.1f deg from the stand, progress %.2f (1.00 = as predicted), lean %+.1f deg",
         g.paw >= 0 && g.paw < 4 ? names[g.paw] : "?", g.pitch, g.roll, g.progress, g.trimNow);
    holdStart = millis() / 1000.0f;
  } else if (last == GP_HOLD) {
    logf("gait: paw held %.1f s, lean now %+.1f deg, progress %.2f", millis() / 1000.0f - holdStart, g.trimNow, g.progress);
  }
  if (g.phase == GP_ABORT) logf("gait: ABORT -- %s", g.why);
  last = g.phase;
}

// ---- console (serial `servo ...`) ---------------------------------------------------------------
static volatile int testJoint = -1;
static volatile uint32_t testUntil = 0;

void bodyConsole(const char* line) {
  char cmd[16] = {0};
  int j = -1, v = 0;
  int n = sscanf(line, "%15s %d %d", cmd, &j, &v);
  if (n < 1 || !strcmp(cmd, "help")) {
    logf("servo show | servo center <joint> <us> | servo dir <joint> <1|-1> | servo test <joint>");
    logf("servo save | servo defaults | servo pose <stand|sit|lie|play-bow> | servo play <label> | servo off");
    logf("servo sensors   (one reading of every laser, the IMU, the touch pads and the battery)");
    logf("joints: 0 hip FL 1 knee FL 2 wheel FL 3 hip BL 4 knee BL 5 wheel BL 6 tail 7 hip FR 8 knee FR");
    logf("        9 wheel FR 10 hip BR 11 knee BR 12 wheel BR  (wheels: centre = the stop pulse)");
    return;
  }
  if (!strcmp(cmd, "sensors")) {
    for (int l = 0; l < LASER_COUNT; l++)
      logf("laser %-22s %s %6.0f mm", kLaserMap[l].name, laserOk[l] ? "ok     " : "MISSING", (float)lastMm[l]);
    const SafetyState& st = ctl.safety.st;
    logf("imu %s  a = %.2f %.2f %.2f g  tilt %.0f deg | edges FL %d FR %d REAR %d | picked up %d fallen %d",
         imuOk ? "ok" : "MISSING", (float)lastAx, (float)lastAy, (float)lastAz, st.tiltDeg, st.edge[0], st.edge[1], st.edge[2], st.pickedUp, st.fallen);
    logf("pads 0x%02X (E0 back-left E1 back-right E2 rump-left E3 rump-right E4 head) | battery %.2f V warn %d cut %d",
         (unsigned)lastPadBits, (float)vbat, st.battWarn, st.battCut);
    const EdgeCalState& ec = ctl.safety.edgeCal;
    logf("desk-edge thresholds FL %.0f FR %.0f REAR %.0f mm (level readings %s: %.0f %.0f %.0f mm) | pitch %+.1f roll %+.1f deg",
         ctl.safety.edgeThreshold(0), ctl.safety.edgeThreshold(1), ctl.safety.edgeThreshold(2),
         ec.done ? "measured this boot" : (ec.ok[0] || ec.ok[1] || ec.ok[2] ? "stored" : "none: 110 mm"), ec.baseline[0],
         ec.baseline[1], ec.baseline[2], st.pitchDeg, st.rollDeg);
    return;
  }
  if (!strcmp(cmd, "show")) {
    for (int i = 0; i < JOINT_COUNT; i++)
      logf("%2d %-18s board %c ch %2d  centre %d us  dir %+d", i, kServoMap[i].name, 'A' + kServoMap[i].board,
           kServoMap[i].channel, ctl.cal.servo[i].centerUs, ctl.cal.servo[i].dir);
  } else if (!strcmp(cmd, "center") && n == 3 && j >= 0 && j < JOINT_COUNT && v >= 1000 && v <= 2000) {
    ctl.cal.servo[j].centerUs = (int16_t)v;
    logf("%s centre %d us (servo save to keep)", kServoMap[j].name, v);
  } else if (!strcmp(cmd, "dir") && n == 3 && j >= 0 && j < JOINT_COUNT && (v == 1 || v == -1)) {
    ctl.cal.servo[j].dir = (int8_t)v;
    logf("%s direction %+d (servo save to keep)", kServoMap[j].name, v);
  } else if (!strcmp(cmd, "test") && n >= 2 && j >= 0 && j < JOINT_COUNT) {
    testJoint = j;
    testUntil = millis() + 2500;
    logf("testing %s: +15 deg (forward) for 1 s, then -15 deg", kServoMap[j].name);
  } else if (!strcmp(cmd, "save")) {
    BodyCmd c{B_CALIBRATE_SAVE, 0, ""};
    postBody(c);
  } else if (!strcmp(cmd, "defaults")) {
    ctl.cal.setDefaults();
    logf("calibration reset to defaults (servo save to keep)");
  } else if (!strcmp(cmd, "pose")) {
    char name[20] = {0};
    sscanf(line, "%*s %19s", name);
    for (int p = 0; p < POSE_COUNT; p++) if (!strcmp(poseName((PoseId)p), name)) {
      BodyCmd c{B_REST_POSE, (int16_t)p, ""};
      postBody(c);
    }
  } else if (!strcmp(cmd, "play")) {
    BodyCmd c{B_PLAY, 0, ""};
    sscanf(line, "%*s %19s", c.label);
    postBody(c);
  } else if (!strcmp(cmd, "off")) {
    bodySetInhibit(true);
    logf("servo outputs OFF (OE high). Reboot to turn them on again.");
  } else logf("servo: unknown command -- servo help");
}

// ---- console (serial `gait ...`) -------------------------------------------------------------------
void gaitConsole(const char* line) {
  char cmd[12] = {0}, a1[12] = {0}, a2[12] = {0}, a3[12] = {0};
  int n = sscanf(line, "%11s %11s %11s %11s", cmd, a1, a2, a3);
  if (n < 1 || !strcmp(cmd, "help")) {
    logf("gait cal                        day-1 balance calibration (robot standing on a LEVEL desk, clear space)");
    logf("gait walk [steps] [fwd|back] [auto|tilt|rear|march]   e.g. gait walk 4 fwd");
    logf("gait paw [left|right] [sit]     give a paw (from the stand; 'sit' only when gait puppy on)");
    logf("gait stop | gait show | gait imu | gait reset (forget trims) | gait puppy on|off");
    logf("gait lift [left|right] [seconds]   day-1 test: one front paw up in the walking pose (default 30 s)");
    logf("gait sign 1|-1                  direction of the closed-loop lean (FLASHING_CHECKLIST 5d step 8)");
    return;
  }
  const GaitStatus& g = ctl.gait.status();
  if (!strcmp(cmd, "show")) {
    const GaitTrims& t = ctl.gait.trims;
    logf("gait: %s, phase %s, style %s, step %d/%d, last result %s (%s)", ctl.gait.active() ? "RUNNING" : "idle",
         gaitPhaseName(g.phase), gaitStyleName(g.style), g.stepsDone, g.stepsWanted, gaitResultName(g.result), g.why);
    logf("balance %s: FL %s lean %+.1f (%u clean lifts), FR %s lean %+.1f (%u), back lifts %s, level ref %+.1f/%+.1f deg, puppy sit %s",
         t.calibrated ? "calibrated" : "NOT calibrated", t.tiltOk[0] ? "ok" : "off", t.lean[0], (unsigned)t.cleanLifts[0],
         t.tiltOk[1] ? "ok" : "off", t.lean[1], (unsigned)t.cleanLifts[1], t.rearOk ? "ok" : "off", t.levelPitch, t.levelRoll,
         ctl.gait.cfg.puppySitPaw ? "on" : "off");
    return;
  }
  if (!strcmp(cmd, "imu")) {  // day 1: nose up -> pitch +, left side down -> roll +
    logf("imu: pitch %+.2f roll %+.2f deg, rates %+.1f %+.1f deg/s (tilt nose-up: pitch must go +; left side down: roll +)",
         ctl.gait.pitchAbs(), ctl.gait.rollAbs(), ctl.gait.pitchRate(), ctl.gait.rollRate());
    return;
  }
  BodyCmd c{B_STOP, 0, "", 0, 0};
  if (!strcmp(cmd, "walk")) {
    c.type = B_WALK;
    c.a = 4;
    c.left = 1;
    c.right = GAIT_AUTO;
    const char* args[3] = {a1, a2, a3};
    for (int i = 0; i < 3; i++) {
      const char* s = args[i];
      if (!s[0]) continue;
      if (isdigit((unsigned char)s[0])) c.a = (int16_t)atoi(s);
      else if (!strcmp(s, "back")) c.left = -1;
      else if (!strcmp(s, "fwd")) c.left = 1;
      else if (!strcmp(s, "tilt")) c.right = GAIT_TILT_STEP;
      else if (!strcmp(s, "rear")) c.right = GAIT_REAR_STEP;
      else if (!strcmp(s, "march")) c.right = GAIT_MARCH;
    }
  } else if (!strcmp(cmd, "paw")) {
    c.type = B_PAW;
    c.a = !strcmp(a1, "right") ? 1 : 0;
    c.left = (!strcmp(a1, "sit") || !strcmp(a2, "sit")) ? 1 : 0;
  } else if (!strcmp(cmd, "cal")) {
    c.type = B_GAIT_CAL;
  } else if (!strcmp(cmd, "stop")) {
    c.type = B_STOP;
  } else if (!strcmp(cmd, "reset")) {
    c.type = B_GAIT_RESET;
  } else if (!strcmp(cmd, "puppy") && (!strcmp(a1, "on") || !strcmp(a1, "off"))) {
    c.type = B_GAIT_PUPPY;
    c.a = !strcmp(a1, "on");
  } else if (!strcmp(cmd, "lift")) {
    c.type = B_GAIT_LIFT;
    c.a = (!strcmp(a1, "right") || !strcmp(a2, "right")) ? 1 : 0;
    c.left = 30;
    if (isdigit((unsigned char)a1[0])) c.left = (int16_t)atoi(a1);
    if (isdigit((unsigned char)a2[0])) c.left = (int16_t)atoi(a2);
  } else if (!strcmp(cmd, "sign") && (!strcmp(a1, "1") || !strcmp(a1, "-1"))) {
    c.type = B_GAIT_SIGN;
    c.a = (int16_t)atoi(a1);
  } else {
    logf("gait: unknown command -- gait help");
    return;
  }
  if (!postBody(c)) logf("gait: body queue full, try again");
}

// ---- battery -------------------------------------------------------------------------------------
static float cellPercent(float v) {  // per-cell resting voltage -> % (Samsung 35E class, 2S)
  static const float V[] = {3.40f, 3.50f, 3.60f, 3.70f, 3.80f, 3.90f, 4.00f, 4.10f, 4.20f};
  static const float P[] = {0, 12, 25, 40, 55, 68, 80, 90, 100};
  if (v <= V[0]) return 0;
  for (int i = 1; i < 9; i++) if (v <= V[i]) return P[i - 1] + (P[i] - P[i - 1]) * (v - V[i - 1]) / (V[i] - V[i - 1]);
  return 100;
}

// ---- supervisor --------------------------------------------------------------------------------
static void supervisor(void*) {
  if (millis() - lastTickMs > BODY_STALL_MS && !stalled) {
    stalled = true;
    digitalWrite(PIN_SERVO_OE, HIGH);  // all servo outputs (and the lasers' XSHUT) off
  }
}

static void sendSafety(SafetyEvent e) {
  switch (e) {
    case EV_EDGE_FL: netSend("edge", "\"sensor\":\"front_left\",\"state\":\"edge\""); break;
    case EV_EDGE_FR: netSend("edge", "\"sensor\":\"front_right\",\"state\":\"edge\""); break;
    // one centred rear desk-edge laser (CAD v3.1); protocol v1.1 has rear_left / rear_right only
    case EV_EDGE_REAR:
      netSend("edge", "\"sensor\":\"rear_left\",\"state\":\"edge\"");
      netSend("edge", "\"sensor\":\"rear_right\",\"state\":\"edge\"");
      break;
    case EV_CLEAR_FL: netSend("edge", "\"sensor\":\"front_left\",\"state\":\"clear\""); break;
    case EV_CLEAR_FR: netSend("edge", "\"sensor\":\"front_right\",\"state\":\"clear\""); break;
    case EV_CLEAR_REAR:
      netSend("edge", "\"sensor\":\"rear_left\",\"state\":\"clear\"");
      netSend("edge", "\"sensor\":\"rear_right\",\"state\":\"clear\"");
      break;
    case EV_PICKUP: netSend("imu", "\"event\":\"pickup\""); break;
    case EV_PUTDOWN: netSend("imu", "\"event\":\"putdown\""); break;
    case EV_FALL: netSend("imu", "\"event\":\"fall\""); break;
    case EV_BATTERY_WARN: netSend("log", "\"level\":\"warn\",\"msg\":\"battery below 7.0 V\""); break;
    case EV_LOW_POWER: logf("body: battery dipped under 7.2 V -- slow moves, one leg at a time, no spins"); break;
    case EV_POWER_OK: logf("body: battery recovered -- normal moves"); break;
    case EV_BATTERY_CUT: netSend("log", "\"level\":\"error\",\"msg\":\"battery below 6.8 V: parked, servos off\""); break;
    case EV_EDGE_CALIBRATED: {
      const EdgeCalState& ec = ctl.safety.edgeCal;
      logf("body: desk-edge level readings FL %.0f FR %.0f REAR %.0f mm -> thresholds %.0f / %.0f / %.0f mm", ec.baseline[0],
           ec.baseline[1], ec.baseline[2], ctl.safety.edgeThreshold(0), ctl.safety.edgeThreshold(1), ctl.safety.edgeThreshold(2));
      break;
    }
    case EV_GAIT_DONE: {
      const GaitStatus& g = ctl.gait.status();
      char fl[140];
      snprintf(fl, sizeof fl, "\"level\":\"%s\",\"msg\":\"gait %s: %s%s%s\"",
               (g.result == GR_DONE || g.result == GR_CAL_PASS) ? "info" : "warn", gaitStyleName(g.style), gaitResultName(g.result),
               g.why[0] ? " - " : "", g.why);
      logf("body: gait %s, %s (%s), %d abort(s)", gaitStyleName(g.style), gaitResultName(g.result), g.why, g.aborts);
      netSend("log", fl);
      break;
    }
    default: break;
  }
  Cmd c = makeCmd(C_SAFETY, (int)e);
  postCmd(c);
}

static void writeOutputs(const BodyOutput& o) {
  for (int j = 0; j < JOINT_COUNT; j++) {
    const ServoMap& m = kServoMap[j];
    if (!pcaOk[m.board]) continue;
    bool on = o.enabled[j];
    float val = o.angle[j];
    if (testJoint == j && millis() < testUntil) { on = true; val = (millis() + 2500 - testUntil) < 1000 ? 15.0f : -15.0f; if (m.wheel) val /= 30.0f; }
    int us = ctl.pulseUs(j, val);
    if (on == lastOn[j] && (!on || us == lastPulse[j])) continue;  // only changed channels go on the bus
    if (on) pcaPulse(PCA_ADDR[m.board], m.channel, us);
    else pcaDigital(PCA_ADDR[m.board], m.channel, false);
    lastOn[j] = on;
    lastPulse[j] = (int16_t)us;
  }
}

static void bringUp() {
  // power sequencing: outputs stay off (OE high) until every channel holds a valid state; lasers
  // come up one by one; then OE low and the legs are enabled one joint at a time (inrush).
  digitalWrite(PIN_SERVO_OE, HIGH);
  for (int b = 0; b < 2; b++) {
    pcaOk[b] = present(PCA_ADDR[b]);
    if (pcaOk[b]) pcaInit(PCA_ADDR[b]);
    else logf("body: servo board %c (0x%02X) NOT FOUND", 'A' + b, PCA_ADDR[b]);
  }
  for (int j = 0; j < JOINT_COUNT; j++) { lastOn[j] = false; lastPulse[j] = 0; }
  if (inhibit) return;
  ctl.restartPowerUp();             // servo outputs come on one at a time, 150 ms apart (no 7.6 A inrush)
  digitalWrite(PIN_SERVO_OE, LOW);  // board B must be live for the XSHUT lines
  lasersInit();
}

static void bodyTask(void*) {
  esp_task_wdt_add(nullptr);
  bringUp();
  SensorFrame f{};
  uint32_t last = millis(), lastBattMsg = 0, lastPadPoll = 0;
  float lastPct = -10, vf = -1, vfast = -1;
  uint16_t lastPads = 0;
  int proxState = 0;
  uint32_t proxT0 = 0, waveCount = 0;
  TickType_t wake = xTaskGetTickCount();
  for (;;) {
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(1000 / BODY_HZ));
    esp_task_wdt_reset();
    uint32_t now = millis();
    lastTickMs = now;
    if (stalled && !inhibit) {  // recovered from a stall: lasers lost power with OE -> redo bring-up
      logf("body: controller stall recovered -- re-initialising servos and lasers");
      bringUp();
      stalled = false;
    }
    // commands
    BodyCmd bc;
    while (xQueueReceive(bodyQ, &bc, 0) == pdTRUE) {
      if (bc.type == B_PLAY) ctl.play(bc.label);
      else if (bc.type == B_REST_POSE && !ctl.activeLabel()) ctl.setPose((PoseId)bc.a, 1.2f);
      else if (bc.type == B_STOP) ctl.stopAll();
      else if (bc.type == B_LISTENING) {
        listeningPause = bc.a != 0;
        if (listeningPause) ctl.stopGait();  // BOM 2e: stop walking to listen (the paw goes down first)
      }
      else if (bc.type == B_CALIBRATE_SAVE) calSave();
      else if (bc.type == B_DRIVE) ctl.setDrive(bc.left / 1000.0f, bc.right / 1000.0f, bc.a / 1000.0f);  // v1.2 drive
      else if (bc.type == B_WALK) {
        GaitStyle s = bc.right >= 0 && bc.right < GAIT_STYLE_COUNT ? (GaitStyle)bc.right : GAIT_AUTO;
        if (ctl.walk(s, bc.left < 0 ? -1 : 1, bc.a)) logf("body: walk %d step(s) %s, style %s", bc.a, bc.left < 0 ? "back" : "forward", gaitStyleName(s));
        else logf("body: walk refused (%s)", ctl.gait.active() ? "busy" : "fallen, picked up, low power or battery cut");
      } else if (bc.type == B_PAW) {
        if (ctl.givePaw(bc.a ? LEG_FR : LEG_FL, bc.left != 0)) logf("body: give %s paw", bc.a ? "right" : "left");
        else logf("body: give paw refused (busy, fallen, picked up, low power or battery cut)");
      } else if (bc.type == B_GAIT_CAL) {
        if (ctl.calibrateBalance()) logf("body: balance calibration started -- keep the desk clear, about 25 s");
        else logf("body: balance calibration refused (busy, fallen, picked up, low power or battery cut)");
      } else if (bc.type == B_GAIT_RESET && !ctl.gait.active()) {
        float mm[3];
        bool ok[3];
        for (int i = 0; i < 3; i++) { mm[i] = ctl.gait.trims.laserMm[i]; ok[i] = ctl.gait.trims.laserOk[i]; }
        float rp = ctl.gait.trims.laserRefPitch, rr = ctl.gait.trims.laserRefRoll;
        ctl.gait.trims.setDefaults();
        for (int i = 0; i < 3; i++) { ctl.gait.trims.laserMm[i] = mm[i]; ctl.gait.trims.laserOk[i] = ok[i]; }
        ctl.gait.trims.laserRefPitch = rp;
        ctl.gait.trims.laserRefRoll = rr;
        gaitSave();
        logf("body: balance trims forgotten -- run gait cal again");
      } else if (bc.type == B_GAIT_PUPPY) {
        ctl.gait.cfg.puppySitPaw = bc.a != 0;
        gaitSave();
        logf("body: puppy-sit give paw %s", bc.a ? "ON (only after the day-1 tests passed!)" : "off");
      } else if (bc.type == B_GAIT_LIFT) {
        if (ctl.liftTest(bc.a ? LEG_FR : LEG_FL, bc.left)) logf("body: lift test, %s front paw, %d s -- hands ready", bc.a ? "right" : "left", bc.left);
        else logf("body: lift test refused (busy, fallen, picked up, low power or battery cut)");
      } else if (bc.type == B_GAIT_SIGN && !ctl.gait.active()) {
        ctl.gait.cfg.leanLoopSign = bc.a < 0 ? -1.0f : 1.0f;
        gaitSave();
        logf("body: closed-loop lean sign %+d", bc.a < 0 ? -1 : 1);
      }
    }
    // sensors
    f.dt = (now - last) / 1000.0f;
    last = now;
    // 100 kHz bus budget: desk-edge lasers every tick (safety), the others every second tick
    static uint32_t tickN = 0;
    tickN++;
    for (int l = 0; l < LASER_COUNT; l++) {
      bool edgeLaser = (l == EDGE_FL || l == EDGE_FR || l == EDGE_REAR);
      f.laserOk[l] = laserOk[l];
      f.laserMm[l] = (laserOk[l] && (edgeLaser || (tickN & 1))) ? laserRead(l) : -1;
      if (f.laserMm[l] >= 0) lastMm[l] = f.laserMm[l];
    }
    f.imuOk = imuRead(&f.ax, &f.ay, &f.az, &f.gx, &f.gy, &f.gz);
    f.gyroOk = f.imuOk;
    if (f.imuOk) {
      lastAx = f.ax; lastAy = f.ay; lastAz = f.az;
      // slow gyro bias tracking while standing still (tau ~10 s): the gait's rate gates stay honest
      if (ctl.safety.standing && fabsf(f.gx) < 2 && fabsf(f.gy) < 2 && fabsf(f.gz) < 2) {
        gyroBias[0] += f.gx * 0.002f; gyroBias[1] += f.gy * 0.002f; gyroBias[2] += f.gz * 0.002f;
      }
    }
    uint32_t mv = analogReadMilliVolts(PIN_VBAT);
    float v = mv / 1000.0f * VBAT_DIVIDER;
    vf = vf < 0 ? v : vf + (v - vf) * 0.05f;  // ~0.4 s low-pass at 50 Hz: warn / cut decisions
    vfast = vfast < 0 ? v : vfast + (v - vfast) * 0.5f;  // ~40 ms: the brown-out guard sees short dips
    f.volts = (mv > 100) ? vf : -1;           // < 0.1 V on the pin = divider not wired (USB bench power)
    f.voltsFast = (mv > 100) ? vfast : -1;
    vbat = f.volts;
    // control
    SafetyEvent ev[8];
    BodyOutput out;
    if (listeningPause) ctl.setDrive(0, 0, 0);  // BOM 2e: pause walking while it listens
    int nev = ctl.tick(f, &out, ev, 8);
    for (int i = 0; i < nev; i++) sendSafety(ev[i]);
    if (!inhibit && !stalled) writeOutputs(out);
    gaitPhaseLog();
    // NVS writes only while no gait runs (a flash write can stall this task for tens of ms)
    for (int i = 0; i < nev; i++)
      if (ev[i] == EV_EDGE_CALIBRATED) {
        GaitTrims& t = ctl.gait.trims;
        const EdgeCalState& ec = ctl.safety.edgeCal;
        bool changed = false;
        for (int k = 0; k < 3; k++)
          if (ec.fresh[k] && (!t.laserOk[k] || fabsf(t.laserMm[k] - ec.baseline[k]) > 2)) {
            t.laserOk[k] = true;
            t.laserMm[k] = ec.baseline[k];
            changed = true;
          }
        if (changed) { t.laserRefPitch = ec.refPitch; t.laserRefRoll = ec.refRoll; gaitDirty = true; }
      }
    if (ctl.gait.trimsDirty()) { gaitDirty = true; ctl.gait.clearTrimsDirty(); }
    if (gaitDirty && !ctl.gait.active()) { gaitSave(); gaitDirty = false; logf("body: balance trims saved"); }
    // touch pads (MPR121): back / rump = zone back, E4 = head
    if (mprOk && now - lastPadPoll >= 40) {
      lastPadPoll = now;
      uint8_t b[2];
      if (rdN(ADDR_MPR121, 0x00, b, 2)) {
        uint16_t pads = (b[0] | (b[1] << 8)) & 0x1F;
        uint16_t pressed = pads & ~lastPads, released = lastPads & ~pads;
        for (int e = 0; e < 5; e++) {
          if (pressed & (1 << e)) { Cmd c = makeCmd(C_TOUCH_PAD, e, 1); postCmd(c); }
          if (released & (1 << e)) { Cmd c = makeCmd(C_TOUCH_PAD, e, 0); postCmd(c); }
        }
        lastPads = pads;
        lastPadBits = pads;
      }
    }
    // hand near / wave (APDS-9960 proximity)
    if (apdsOk && (tickN & 1) == 0) {
      uint8_t pdata = 0;
      if (rdN(ADDR_APDS9960, 0x9C, &pdata, 1)) {
        bool near = pdata > 120;
        if (near && proxState == 0) {
          proxState = 1;
          if (now - proxT0 < 1500) waveCount++; else waveCount = 1;
          proxT0 = now;
          Cmd c = makeCmd(C_GESTURE, waveCount >= 2 ? 1 : 0);
          postCmd(c);
          if (waveCount >= 2) waveCount = 0;
        } else if (!near && pdata < 60) proxState = 0;
      }
    }
    // battery report (protocol 6.4: on >= 1 % change and every 60 s)
    if (f.volts > 0) {
      float pct = cellPercent(f.volts / 2);
      if (fabsf(pct - lastPct) >= 1 || now - lastBattMsg > 60000) {
        char fl[80];
        snprintf(fl, sizeof fl, "\"percent\":%d,\"volts\":%.2f,\"charging\":false", (int)lroundf(pct), f.volts);
        netSend("battery", fl);
        Cmd c = makeCmd(C_BATTERY, 0, 0, pct, f.volts);
        postCmd(c);
        lastPct = pct;
        lastBattMsg = now;
      }
    }
  }
}

void bodyBegin() {
  pinMode(PIN_SERVO_OE, OUTPUT);
  digitalWrite(PIN_SERVO_OE, HIGH);  // first thing at boot: every servo output off
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_VBAT, ADC_11db);
  bodyQ = xQueueCreate(16, sizeof(BodyCmd));
  calLoad();
  Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, ROBOT_I2C_HZ);
  i2cStarted = true;
  if (!present(PCA_ADDR[0]) && !present(PCA_ADDR[1])) {
    logf("body: no servo board on SDA %d / SCL %d -- trying the pins the other way round", PIN_I2C_SDA, PIN_I2C_SCL);
    Wire.end();
    Wire.begin(PIN_I2C_SCL, PIN_I2C_SDA, ROBOT_I2C_HZ);
    if (!present(PCA_ADDR[0]) && !present(PCA_ADDR[1])) {
      Wire.end();
      Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, ROBOT_I2C_HZ);
      logf("body: still no servo board -- the face runs; the body stays off");
    } else logf("body: robot bus found with SDA/SCL swapped (fix the wiring table or leave it)");
  }
  imuInit();
  gyroBiasInit();
  gaitLoad();
  mprInit();
  apdsInit();
  lastTickMs = millis();
  xTaskCreatePinnedToCore(bodyTask, "body", 6144, nullptr, 7, nullptr, 0);
  const esp_timer_create_args_t a = {supervisor, nullptr, ESP_TIMER_TASK, "bodysup", false};
  esp_timer_handle_t t;
  esp_timer_create(&a, &t);
  esp_timer_start_periodic(t, 50000);
}
