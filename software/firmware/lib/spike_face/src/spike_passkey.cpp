// spike_passkey.cpp -- see spike_passkey.h.
#include "spike_passkey.h"

namespace spike {

// Segments a..g (bit 0 = a top, b upper right, c lower right, d bottom, e lower left, f upper left, g middle).
static const uint8_t kSeg[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};

void drawSevenSegDigit(Gfx& g, int digit, float x, float y, float w, float h, float t, Rgb c) {
  if (digit < 0 || digit > 9) return;
  const uint8_t m = kSeg[digit];
  const float r = t * 0.5f;
  const float gap = t * 0.18f;              // a hair of space between segments reads as "digital"
  const float hx = x + t * 0.5f + gap;      // horizontal segment start / length
  const float hw = w - t - 2 * gap;
  const float half = h * 0.5f;
  const float vh = half - t * 0.5f - 2 * gap;  // vertical segment length
  if (m & 0x01) g.rrect(hx, y, hw, t, r, c);                            // a
  if (m & 0x02) g.rrect(x + w - t, y + t * 0.5f + gap, t, vh, r, c);    // b
  if (m & 0x04) g.rrect(x + w - t, y + half + gap, t, vh, r, c);        // c
  if (m & 0x08) g.rrect(hx, y + h - t, hw, t, r, c);                    // d
  if (m & 0x10) g.rrect(x, y + half + gap, t, vh, r, c);                // e
  if (m & 0x20) g.rrect(x, y + t * 0.5f + gap, t, vh, r, c);            // f
  if (m & 0x40) g.rrect(hx, y + half - t * 0.5f, hw, t, r, c);          // g
}

void drawPasskeyOverlay(Gfx& g, uint32_t passkey, float remaining, float W, float H) {
  if (passkey > 999999) passkey %= 1000000;
  if (remaining < 0) remaining = 0;
  if (remaining > 1) remaining = 1;
  g.resetTransform();  // screen space (also resets the save stack; the face is already drawn)
  // a dark card over the face, so the digits read at arm's length in any light
  const float cardW = W * 0.92f, cardH = H * 0.74f;
  const float cx = (W - cardW) * 0.5f, cy = (H - cardH) * 0.5f;
  g.rrect(cx, cy, cardW, cardH, 26, 0x0E1420, 0.94f);
  // 6 digits in two groups of 3 (easier to read aloud and to type)
  const float dw = W * 0.112f, dh = H * 0.36f, t = dw * 0.22f;
  const float gap = dw * 0.26f, groupGap = dw * 0.62f;
  const float total = 6 * dw + 4 * gap + groupGap;
  float x = (W - total) * 0.5f;
  const float y = cy + cardH * 0.17f;
  uint32_t div = 100000;
  for (int i = 0; i < 6; i++) {
    int d = (int)((passkey / div) % 10);
    div /= 10;
    drawSevenSegDigit(g, d, x, y, dw, dh, t, 0xFFFFFF);
    x += dw + (i == 2 ? groupGap : gap);
  }
  // the time left to type it: a bar that shrinks over the 60 s pairing window
  const float barW = total, barH = t * 0.55f;
  const float bx = (W - barW) * 0.5f, by = y + dh + cardH * 0.13f;
  g.rrect(bx, by, barW, barH, barH * 0.5f, 0x2A3444, 1.0f);
  if (remaining > 0.01f) g.rrect(bx, by, barW * remaining, barH, barH * 0.5f, 0x5AC8FA, 1.0f);
}

}  // namespace spike
