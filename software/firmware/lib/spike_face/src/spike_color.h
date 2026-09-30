// spike_color.h -- colour helpers, a line-for-line port of gfx.js (hexToRgb, rgbToHex, mix, shade,
// luminance). Colours are 0xRRGGBB integers; JS passes "#RRGGBB" strings, and every JS helper rounds
// through a hex string, so these helpers round each channel exactly like rgbToHex (Math.round, clamp).
#pragma once
#include <stdint.h>
#include <math.h>

namespace spike {

typedef uint32_t Rgb;  // 0xRRGGBB

inline int rgbR(Rgb c) { return (int)((c >> 16) & 255); }
inline int rgbG(Rgb c) { return (int)((c >> 8) & 255); }
inline int rgbB(Rgb c) { return (int)(c & 255); }

// JS Math.round for the 0..255 range, then clamp (rgbToHex).
inline int roundChannel(float v) {
  int i = (int)floorf(v + 0.5f);
  return i < 0 ? 0 : (i > 255 ? 255 : i);
}
inline Rgb makeRgb(float r, float g, float b) {
  return ((Rgb)roundChannel(r) << 16) | ((Rgb)roundChannel(g) << 8) | (Rgb)roundChannel(b);
}

// mix(a, b, t): t = 0 -> a, t = 1 -> b
inline Rgb mix(Rgb a, Rgb b, float t) {
  return makeRgb(rgbR(a) + (rgbR(b) - rgbR(a)) * t, rgbG(a) + (rgbG(b) - rgbG(a)) * t,
                 rgbB(a) + (rgbB(b) - rgbB(a)) * t);
}
inline Rgb shade(Rgb c, float amt) { return amt < 0 ? mix(c, 0x000000, -amt) : mix(c, 0xFFFFFF, amt); }
inline float luminance(Rgb c) { return (0.299f * rgbR(c) + 0.587f * rgbG(c) + 0.114f * rgbB(c)) / 255.0f; }

// "#RRGGBB" / "RRGGBB" / "#RGB" -> Rgb. Returns false (and leaves *out) on a bad string.
inline bool parseHex(const char* s, Rgb* out) {
  if (!s) return false;
  if (*s == '#') s++;
  int n = 0;
  while (s[n]) n++;
  if (n != 6 && n != 3) return false;
  Rgb v = 0;
  for (int i = 0; i < n; i++) {
    char ch = s[i];
    int d;
    if (ch >= '0' && ch <= '9') d = ch - '0';
    else if (ch >= 'a' && ch <= 'f') d = ch - 'a' + 10;
    else if (ch >= 'A' && ch <= 'F') d = ch - 'A' + 10;
    else return false;
    if (n == 3) v = (v << 8) | (Rgb)(d * 17);
    else v = (v << 4) | (Rgb)d;
  }
  *out = v;
  return true;
}

// RGB565 helpers for the device frame buffer.
inline uint16_t to565(Rgb c) {
  return (uint16_t)(((rgbR(c) & 0xF8) << 8) | ((rgbG(c) & 0xFC) << 3) | (rgbB(c) >> 3));
}

}  // namespace spike
