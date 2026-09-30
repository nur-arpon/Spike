// spike_espnow_pkt.cpp -- see spike_espnow_pkt.h (PROTOCOL.md 11.6).
#include "spike_espnow_pkt.h"

#include <stdio.h>
#include <string.h>

#include "spike_link_policy.h"

namespace spike {
namespace espnow {

static const uint8_t kMagic[kMagicLen] = {'S', 'P', 'K', '1'};

size_t seal(Aead& aead, const uint8_t key[kKeyLen], uint8_t kind, const uint8_t nonce[kNonceLen],
            const uint8_t* pt, size_t len, uint8_t* out, size_t cap) {
  if (kind != KIND_JOIN && kind != KIND_LEAVE) return 0;
  if (len > kMaxPlaintext) return 0;
  const size_t total = kOverhead + len;
  if (!out || cap < total) return 0;
  memcpy(out, kMagic, kMagicLen);
  out[kMagicLen] = kind;
  memcpy(out + kHeaderLen, nonce, kNonceLen);
  uint8_t* ct = out + kHeaderLen + kNonceLen;
  uint8_t* tag = ct + len;
  if (!aead.seal(key, nonce, out, kHeaderLen, pt, len, ct, tag)) return 0;
  return total;
}

const char* openResultName(OpenResult r) {
  switch (r) {
    case OpenResult::Ok: return "ok";
    case OpenResult::TooShort: return "too short";
    case OpenResult::TooLong: return "too long";
    case OpenResult::BadMagic: return "not SPK1";
    case OpenResult::BadKind: return "unknown kind";
    case OpenResult::AuthFail: return "does not decrypt";
    case OpenResult::NoRoom: return "no room";
  }
  return "?";
}

OpenResult open(Aead& aead, const uint8_t key[kKeyLen], const uint8_t* pkt, size_t len, uint8_t* kind, uint8_t* pt,
                size_t ptCap, size_t* ptLen) {
  if (!pkt || len < kOverhead) return OpenResult::TooShort;
  if (len > kMaxPacket) return OpenResult::TooLong;
  if (memcmp(pkt, kMagic, kMagicLen) != 0) return OpenResult::BadMagic;
  const uint8_t k = pkt[kMagicLen];
  if (k != KIND_JOIN && k != KIND_LEAVE) return OpenResult::BadKind;
  const size_t n = len - kOverhead;
  if (!pt || ptCap < n + 1) return OpenResult::NoRoom;
  const uint8_t* nonce = pkt + kHeaderLen;
  const uint8_t* ct = nonce + kNonceLen;
  const uint8_t* tag = ct + n;
  if (!aead.open(key, nonce, pkt, kHeaderLen, ct, n, tag, pt)) {
    memset(pt, 0, n + 1);  // never hand out unauthenticated plaintext
    return OpenResult::AuthFail;
  }
  pt[n] = 0;
  *kind = k;
  *ptLen = n;
  return OpenResult::Ok;
}

static size_t buildJoin(const JoinInfo& j, bool sid, char* out, size_t cap) {
  char ssid[32 * 6 + 1], pass[63 * 6 + 1], token[64 * 6 + 1], host[64 * 6 + 1];
  if (!link::jsonEscape(j.ssid, ssid, sizeof ssid) || !link::jsonEscape(j.pass, pass, sizeof pass) ||
      !link::jsonEscape(j.token, token, sizeof token) || !link::jsonEscape(j.host, host, sizeof host))
    return 0;
  char tmp[512];  // anything longer is over the 217-byte limit anyway
  int n;
  if (sid && j.sid)
    n = snprintf(tmp, sizeof tmp, "{\"ssid\":\"%s\",\"pass\":\"%s\",\"port\":%u,\"token\":\"%s\",\"host\":\"%s\",\"sid\":\"%s\"}",
                 ssid, pass, (unsigned)j.port, token, host, j.sid);
  else
    n = snprintf(tmp, sizeof tmp, "{\"ssid\":\"%s\",\"pass\":\"%s\",\"port\":%u,\"token\":\"%s\",\"host\":\"%s\"}", ssid,
                 pass, (unsigned)j.port, token, host);
  if (n <= 0 || (size_t)n >= sizeof tmp || (size_t)n > kMaxPlaintext || (size_t)n + 1 > cap) return 0;
  memcpy(out, tmp, (size_t)n + 1);
  return (size_t)n;
}

size_t buildJoinPlaintext(const JoinInfo& j, char* out, size_t cap, bool* withSid) {
  if (withSid) *withSid = false;
  if (!out || cap == 0) return 0;
  out[0] = 0;
  if (j.sid && strlen(j.sid) == kSidLen) {
    size_t n = buildJoin(j, true, out, cap);
    if (n) {
      if (withSid) *withSid = true;
      return n;
    }
  }
  return buildJoin(j, false, out, cap);
}

size_t buildLeavePlaintext(const char* sid, char* out, size_t cap) {
  int n = (sid && strlen(sid) == kSidLen) ? snprintf(out, cap, "{\"sid\":\"%s\"}", sid) : snprintf(out, cap, "{}");
  return (n > 0 && (size_t)n < cap) ? (size_t)n : 0;
}

void toHex(const uint8_t* in, size_t n, char* out) {
  static const char* d = "0123456789abcdef";
  for (size_t i = 0; i < n; i++) {
    out[2 * i] = d[in[i] >> 4];
    out[2 * i + 1] = d[in[i] & 15];
  }
  out[2 * n] = 0;
}

static int hexVal(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

bool fromHex(const char* in, uint8_t* out, size_t n) {
  if (!in || strlen(in) != 2 * n) return false;
  for (size_t i = 0; i < n; i++) {
    int h = hexVal(in[2 * i]), l = hexVal(in[2 * i + 1]);
    if (h < 0 || l < 0) return false;
    out[i] = (uint8_t)(h << 4 | l);
  }
  return true;
}

}  // namespace espnow
}  // namespace spike
