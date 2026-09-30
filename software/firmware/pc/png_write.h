// png_write.h -- a minimal, dependency-free PNG writer (RGB8, "stored" deflate blocks).
// Used instead of stb_image_write so the PC build needs no download; the files are standard PNGs
// (just not compressed). The golden-image tooling compresses its sheets with Pillow.
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

namespace pngw {

inline uint32_t crc32(const uint8_t* d, size_t n, uint32_t crc = 0) {
  static uint32_t table[256];
  static bool ready = false;
  if (!ready) {
    for (uint32_t i = 0; i < 256; i++) {
      uint32_t c = i;
      for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      table[i] = c;
    }
    ready = true;
  }
  crc = ~crc;
  for (size_t i = 0; i < n; i++) crc = table[(crc ^ d[i]) & 255] ^ (crc >> 8);
  return ~crc;
}

inline void put32(uint8_t* p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }

inline void chunk(FILE* f, const char* type, const uint8_t* data, uint32_t len) {
  uint8_t hdr[8];
  put32(hdr, len);
  memcpy(hdr + 4, type, 4);
  fwrite(hdr, 1, 8, f);
  if (len) fwrite(data, 1, len, f);
  uint32_t c = crc32((const uint8_t*)type, 4);
  c = crc32(data, len, c);
  uint8_t cb[4];
  put32(cb, c);
  fwrite(cb, 1, 4, f);
}

// Writes w x h RGB8 pixels (row-major) to path. Returns false on I/O error.
inline bool writeRgb(const char* path, const uint8_t* rgb, int w, int h) {
  FILE* f = fopen(path, "wb");
  if (!f) return false;
  static const uint8_t sig[8] = {137, 80, 78, 71, 13, 10, 26, 10};
  fwrite(sig, 1, 8, f);
  uint8_t ihdr[13];
  put32(ihdr, (uint32_t)w);
  put32(ihdr + 4, (uint32_t)h);
  ihdr[8] = 8; ihdr[9] = 2; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  chunk(f, "IHDR", ihdr, 13);
  // raw scanlines with filter byte 0
  size_t rowLen = (size_t)w * 3 + 1, rawLen = rowLen * (size_t)h;
  uint8_t* raw = (uint8_t*)malloc(rawLen);
  if (!raw) { fclose(f); return false; }
  for (int y = 0; y < h; y++) {
    raw[y * rowLen] = 0;
    memcpy(raw + y * rowLen + 1, rgb + (size_t)y * w * 3, (size_t)w * 3);
  }
  // zlib stream: header, stored blocks (<= 65535 bytes), adler32
  size_t nBlocks = (rawLen + 65534) / 65535;
  size_t zLen = 2 + rawLen + nBlocks * 5 + 4;
  uint8_t* z = (uint8_t*)malloc(zLen);
  if (!z) { free(raw); fclose(f); return false; }
  size_t o = 0;
  z[o++] = 0x78; z[o++] = 0x01;
  uint32_t a = 1, b = 0;
  for (size_t i = 0; i < rawLen; i++) { a = (a + raw[i]) % 65521; b = (b + a) % 65521; }
  for (size_t pos = 0; pos < rawLen; pos += 65535) {
    size_t n = rawLen - pos < 65535 ? rawLen - pos : 65535;
    z[o++] = (pos + n >= rawLen) ? 1 : 0;
    z[o++] = (uint8_t)(n & 255); z[o++] = (uint8_t)(n >> 8);
    z[o++] = (uint8_t)(~n & 255); z[o++] = (uint8_t)((~n >> 8) & 255);
    memcpy(z + o, raw + pos, n);
    o += n;
  }
  put32(z + o, (b << 16) | a);
  o += 4;
  chunk(f, "IDAT", z, (uint32_t)o);
  chunk(f, "IEND", nullptr, 0);
  free(z);
  free(raw);
  return fclose(f) == 0;
}

}  // namespace pngw
