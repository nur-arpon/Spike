// Desk Buddy v3.1 - servo centre + bench-test sketch
// ---------------------------------------------------------------------------------
// Runs on the Guition screen board (ESP32-S3), which drives both PCA9685 servo boards.
// On power-up it centres every leg and tail servo at 90 degrees (a 1500 us pulse) and
// holds them there, so the horns can be fitted straight. The wheel servos (360) get the
// same 1500 us pulse, which is "stop".
//
// Serial Monitor at 115200 baud. Type a letter and press Enter:
//   h        help
//   c        centre every servo again (1500 us)
//   s        scan the I2C bus and name what answers
//   n        next servo: select it and wiggle it so you can see which one it is
//   t        sweep the selected servo 60..120 degrees and back to 90
//   + / -    trim the selected servo by 10 us (find each wheel servo's stop point)
//   l        test the 7 laser sensors one by one (XSHUT lines on servo board B)
//   v        read the battery voltage (10k / 4.7k divider on IO5)
//   o        outputs off (OE high): every servo goes limp, the wheels stop
//
// Pin plan (shopping/BOM_Audit_2026-09-26.md, section 2d):
//   I2C on connector P4: IO17 and IO18 (the sketch tries both orders)
//   PCA9685 OE on IO14, with a 2.2 kOhm pull-up to 3.3 V (high = all outputs off)
//   battery sense on IO5
// ---------------------------------------------------------------------------------
#include <Arduino.h>
#include <Wire.h>

static const int PIN_A = 17, PIN_B = 18;   // P4 connector (SDA/SCL order is checked at boot)
static const int PIN_OE = 14;              // PCA9685 OE, both boards
static const int PIN_VBAT = 5;             // battery divider 10k (top) / 4.7k (bottom)

static const uint8_t PCA_ADDR[2] = {0x40, 0x41};   // A = left wall (no pads), B = right wall (A0 bridged)
static const float PCA_OSC_HZ = 25000000.0f;       // PCA9685 internal oscillator (nominal)
static const uint8_t PRESCALE = 121;               // 25 MHz / (4096 * 122) = 50.0 Hz

struct ServoCh { const char *name; uint8_t board; uint8_t ch; bool wheel; int us; };
// Channel map - the same table is printed in the guide (Wiring, "Servo channels").
static ServoCh SERVOS[] = {
  {"hip front-left",    0, 0, false, 1500}, {"knee front-left",   0, 1, false, 1500},
  {"wheel front-left",  0, 2, true,  1500}, {"hip back-left",     0, 4, false, 1500},
  {"knee back-left",    0, 5, false, 1500}, {"wheel back-left",   0, 6, true,  1500},
  {"tail",              0, 8, false, 1500},
  {"hip front-right",   1, 0, false, 1500}, {"knee front-right",  1, 1, false, 1500},
  {"wheel front-right", 1, 2, true,  1500}, {"hip back-right",    1, 4, false, 1500},
  {"knee back-right",   1, 5, false, 1500}, {"wheel back-right",  1, 6, true,  1500},
};
static const int N_SERVOS = sizeof(SERVOS) / sizeof(SERVOS[0]);

struct Laser { const char *name; uint8_t ch; };      // XSHUT lines on board B
static const Laser LASERS[] = {
  {"front obstacle (chest)", 9}, {"rear obstacle (rump)", 10}, {"desk-edge front-left", 11},
  {"desk-edge front-right", 12}, {"desk-edge rear", 13}, {"side left", 14}, {"side right", 15},
};

static bool boardOk[2] = {false, false};
static int sel = -1;

static bool present(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

static void writeReg(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(val);
  Wire.endTransmission();
}

static void pcaInit(uint8_t addr) {
  writeReg(addr, 0x00, 0x10);          // MODE1: sleep (needed to set the prescaler)
  writeReg(addr, 0xFE, PRESCALE);      // 50 Hz
  writeReg(addr, 0x01, 0x04);          // MODE2: totem-pole outputs; outputs LOW while OE is high
  writeReg(addr, 0x00, 0x20);          // MODE1: wake, register auto-increment, all-call off
  delay(2);
  writeReg(addr, 0x00, 0xA0);          // restart PWM
}

static void pcaRaw(uint8_t addr, uint8_t ch, uint16_t on, uint16_t off) {
  Wire.beginTransmission(addr);
  Wire.write(0x06 + 4 * ch);
  Wire.write(on & 0xFF); Wire.write(on >> 8);
  Wire.write(off & 0xFF); Wire.write(off >> 8);
  Wire.endTransmission();
}

static void pcaMicros(uint8_t addr, uint8_t ch, int us) {
  const float periodUs = 4096.0f * (PRESCALE + 1) / (PCA_OSC_HZ / 1000000.0f);
  uint16_t ticks = (uint16_t)constrain(lroundf(us * 4096.0f / periodUs), 0, 4095);
  pcaRaw(addr, ch, 0, ticks);
}

static void pcaDigital(uint8_t addr, uint8_t ch, bool high) {
  if (high) pcaRaw(addr, ch, 0x1000, 0);   // full on
  else      pcaRaw(addr, ch, 0, 0x1000);   // full off
}

static void setServo(int i, int us) {
  SERVOS[i].us = constrain(us, 500, 2500);
  if (boardOk[SERVOS[i].board]) pcaMicros(PCA_ADDR[SERVOS[i].board], SERVOS[i].ch, SERVOS[i].us);
}

static const char *deviceName(uint8_t a) {
  switch (a) {
    case 0x29: return "VL53L0X laser (only one should answer here at a time)";
    case 0x39: return "APDS-9960 gesture sensor";
    case 0x40: return "PCA9685 servo board A (left)";
    case 0x41: return "PCA9685 servo board B (right, A0 bridged)";
    case 0x5A: return "MPR121 touch board";
    case 0x68: return "MPU6050 motion sensor";
    case 0x69: return "MPU6050 (AD0 high)";
    case 0x70: return "PCA9685 all-call address (normal, ignore)";
    default:   return "unknown";
  }
}

static int scan(bool print) {
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    if (present(a)) {
      n++;
      if (print) Serial.printf("  0x%02X  %s\n", a, deviceName(a));
    }
  }
  if (print) Serial.printf("  %d device(s) found\n", n);
  return n;
}

static void centreAll() {
  for (int i = 0; i < N_SERVOS; i++) setServo(i, 1500);
  Serial.println("All servos at 1500 us (90 degrees; wheel servos: stop).");
}

static void help() {
  Serial.println("\nCommands: h help | c centre all | s scan I2C | n next servo (wiggle) | t sweep selected");
  Serial.println("          + / - trim selected 10 us | l test lasers | v battery volts | o outputs off");
}

static void sweep(int i) {
  Serial.printf("Sweeping %s 60..120 degrees\n", SERVOS[i].name);
  for (int us = 1500; us <= 1833; us += 10) { setServo(i, us); delay(15); }
  for (int us = 1833; us >= 1167; us -= 10) { setServo(i, us); delay(15); }
  for (int us = 1167; us <= 1500; us += 10) { setServo(i, us); delay(15); }
  setServo(i, 1500);
}

static void testLasers() {
  if (!boardOk[1]) { Serial.println("Servo board B (0x41) not found - the laser XSHUT lines are on it."); return; }
  for (auto &l : LASERS) pcaDigital(PCA_ADDR[1], l.ch, false);   // all lasers in standby
  delay(20);
  for (auto &l : LASERS) {
    pcaDigital(PCA_ADDR[1], l.ch, true);
    delay(15);
    Serial.printf("  %-24s (B ch %2d): %s\n", l.name, l.ch, present(0x29) ? "OK, answers at 0x29" : "NO ANSWER");
    pcaDigital(PCA_ADDR[1], l.ch, false);
    delay(5);
  }
}

static void readBattery() {
  uint32_t mv = 0;
  for (int k = 0; k < 16; k++) mv += analogReadMilliVolts(PIN_VBAT);
  float v = (mv / 16.0f) / 1000.0f * (10.0f + 4.7f) / 4.7f;
  Serial.printf("Battery: %.2f V  (full 8.4 V, warn 7.0 V, stop 6.8 V)\n", v);
}

void setup() {
  pinMode(PIN_OE, OUTPUT);
  digitalWrite(PIN_OE, HIGH);            // outputs off until the pulses are set
  Serial.begin(115200);
  delay(1500);
  Serial.println("\nDesk Buddy v3.1 - servo centre + bench test");

  // Try SDA=17/SCL=18 first, then the other way round.
  int sda = PIN_A, scl = PIN_B;
  for (int attempt = 0; attempt < 2; attempt++) {
    Wire.begin(sda, scl, 100000);
    if (present(PCA_ADDR[0]) || present(PCA_ADDR[1])) break;
    Wire.end();
    int t = sda; sda = scl; scl = t;
    if (attempt == 1) Wire.begin(sda, scl, 100000);
  }
  Serial.printf("I2C on SDA=IO%d, SCL=IO%d\n", sda, scl);
  scan(true);

  for (int b = 0; b < 2; b++) {
    boardOk[b] = present(PCA_ADDR[b]);
    if (boardOk[b]) pcaInit(PCA_ADDR[b]);
    Serial.printf("Servo board %c (0x%02X): %s\n", 'A' + b, PCA_ADDR[b], boardOk[b] ? "found" : "NOT FOUND");
  }
  if (boardOk[1]) for (auto &l : LASERS) pcaDigital(PCA_ADDR[1], l.ch, false);
  centreAll();
  digitalWrite(PIN_OE, LOW);             // outputs on
  help();
}

void loop() {
  if (!Serial.available()) { delay(10); return; }
  char c = Serial.read();
  switch (c) {
    case 'h': help(); break;
    case 'c': digitalWrite(PIN_OE, LOW); centreAll(); break;
    case 's': scan(true); break;
    case 'n':
      sel = (sel + 1) % N_SERVOS;
      Serial.printf("Selected %d: %s (board %c, channel %d)\n", sel, SERVOS[sel].name, 'A' + SERVOS[sel].board, SERVOS[sel].ch);
      if (!SERVOS[sel].wheel) {
        for (int k = 0; k < 2; k++) { setServo(sel, 1300); delay(300); setServo(sel, 1700); delay(300); }
        setServo(sel, 1500);
      } else {
        setServo(sel, 1600); delay(800); setServo(sel, 1500);
      }
      break;
    case 't': if (sel >= 0) sweep(sel); else Serial.println("Press n first to select a servo."); break;
    case '+': case '-':
      if (sel < 0) { Serial.println("Press n first to select a servo."); break; }
      setServo(sel, SERVOS[sel].us + (c == '+' ? 10 : -10));
      Serial.printf("%s: %d us - write this down if it is a wheel servo's stop point\n", SERVOS[sel].name, SERVOS[sel].us);
      break;
    case 'l': testLasers(); break;
    case 'v': readBattery(); break;
    case 'o': digitalWrite(PIN_OE, HIGH); Serial.println("Outputs off: servos limp, wheels stopped. Press c to turn them on."); break;
    default: break;
  }
}
