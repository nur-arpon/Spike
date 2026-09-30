// touch.cpp -- GT911 capacitive touch (JC4827W543 "C" variant) on its own I2C bus (Wire1).
// A tiny register-level driver: reset sequence to select address 0x5D, then read the status register
// and the first touch point. Coordinates are mapped to the 480 x 272 face.
#include "app.h"
#include "config.h"
#include <Wire.h>

static uint8_t addr = 0;
static TwoWire& tw = Wire1;

static bool rd(uint16_t reg, uint8_t* buf, int n) {
  tw.beginTransmission(addr);
  tw.write(reg >> 8);
  tw.write(reg & 0xFF);
  if (tw.endTransmission(false) != 0) return false;
  if (tw.requestFrom((int)addr, n) != n) return false;
  for (int i = 0; i < n; i++) buf[i] = tw.read();
  return true;
}
static void wr(uint16_t reg, uint8_t v) {
  tw.beginTransmission(addr);
  tw.write(reg >> 8);
  tw.write(reg & 0xFF);
  tw.write(v);
  tw.endTransmission();
}

void touchBegin() {
  // GT911 address select: INT low while RST rises -> 0x5D
  pinMode(PIN_TP_RST, OUTPUT);
  pinMode(PIN_TP_INT, OUTPUT);
  digitalWrite(PIN_TP_INT, LOW);
  digitalWrite(PIN_TP_RST, LOW);
  delay(11);
  digitalWrite(PIN_TP_RST, HIGH);
  delay(6);
  pinMode(PIN_TP_INT, INPUT);
  delay(55);
  tw.begin(PIN_TP_SDA, PIN_TP_SCL, TP_I2C_HZ);
  for (uint8_t a : {(uint8_t)0x5D, (uint8_t)0x14}) {
    tw.beginTransmission(a);
    if (tw.endTransmission() == 0) { addr = a; break; }
  }
  if (!addr) { logf("touch: GT911 not found on SDA %d / SCL %d (check the board is the 'C' variant)", PIN_TP_SDA, PIN_TP_SCL); return; }
  uint8_t id[4] = {0};
  rd(0x8140, id, 4);
  logf("touch: GT911 at 0x%02X, product id %c%c%c%c", addr, id[0], id[1], id[2], id[3]);
}

TouchPoint touchRead() {
  TouchPoint p{false, false, 0, 0};
  if (!addr) return p;
  uint8_t st;
  if (!rd(0x814E, &st, 1)) return p;
  if (!(st & 0x80)) return p;  // no new data (fresh = false): keep the last state
  p.fresh = true;
  int n = st & 0x0F;
  if (n > 0) {
    uint8_t b[8];
    if (rd(0x8150, b, 8)) {
      int x = b[0] | (b[1] << 8), y = b[2] | (b[3] << 8);
      p.down = true;
      p.x = (int16_t)(x < 0 ? 0 : (x >= LCD_W ? LCD_W - 1 : x));
      p.y = (int16_t)(y < 0 ? 0 : (y >= LCD_H ? LCD_H - 1 : y));
    }
  }
  wr(0x814E, 0);
  return p;
}
