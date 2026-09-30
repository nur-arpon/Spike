// spike_espnow_pkt.h -- the robot-internal ESP-NOW hand-over packet of PROTOCOL.md 11.6 (v1.3).
//
//   "SPK1" (4) | kind (1) | nonce (12) | ciphertext (n) | tag (16)        at most 250 bytes
//   AES-256-GCM, key = the robot's 32-byte link key, AAD = the first 5 bytes, nonce random per message
//   kind 1 = hotspot join:  plaintext {"ssid":..,"pass":..,"port":..,"token":..,"host":..}
//   kind 2 = hotspot leave: plaintext {}
//
// Platform-free: the cipher is behind the Aead interface. The ESP32 boards use mbedTLS
// (spike_aead_mbedtls.cpp); the PC test uses Windows CNG (pc/aead_bcrypt.cpp).
//
// Firmware extension (additive, protocol rule 1 "unknown fields are ignored"): both plaintexts may
// carry "sid", a random 16-hex-digit hotspot session id. The camera board acts on a kind 2 only when
// its sid matches the kind 1 it joined with, so a recorded kind 2 from an older session cannot be
// replayed to knock the camera off a later hotspot (see OPEN_QUESTIONS / the v1.3 report).
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace spike {
namespace espnow {

constexpr size_t kMaxPacket = 250;   // ESP-NOW v1 payload limit (Arduino-ESP32 2.x = ESP-IDF 4.4)
constexpr size_t kMagicLen = 4;
constexpr size_t kHeaderLen = 5;     // magic + kind = the AAD
constexpr size_t kNonceLen = 12;
constexpr size_t kTagLen = 16;
constexpr size_t kKeyLen = 32;
constexpr size_t kOverhead = kHeaderLen + kNonceLen + kTagLen;   // 33
constexpr size_t kMaxPlaintext = kMaxPacket - kOverhead;         // 217
constexpr size_t kSidLen = 16;       // hex digits

enum : uint8_t { KIND_JOIN = 1, KIND_LEAVE = 2 };

class Aead {
 public:
  virtual ~Aead() {}
  // AES-256-GCM with a 12-byte nonce and a 16-byte tag. ct/pt may not overlap their inputs.
  virtual bool seal(const uint8_t key[kKeyLen], const uint8_t nonce[kNonceLen], const uint8_t* aad, size_t aadLen,
                    const uint8_t* pt, size_t len, uint8_t* ct, uint8_t tag[kTagLen]) = 0;
  // False when the tag does not verify (pt is then undefined and must not be used).
  virtual bool open(const uint8_t key[kKeyLen], const uint8_t nonce[kNonceLen], const uint8_t* aad, size_t aadLen,
                    const uint8_t* ct, size_t len, const uint8_t tag[kTagLen], uint8_t* pt) = 0;
};

// Builds a packet. Returns its length, or 0 (plaintext over 217 bytes, bad kind, cap too small, or
// the cipher failed).
size_t seal(Aead& aead, const uint8_t key[kKeyLen], uint8_t kind, const uint8_t nonce[kNonceLen],
            const uint8_t* pt, size_t len, uint8_t* out, size_t cap);

enum class OpenResult : uint8_t { Ok, TooShort, TooLong, BadMagic, BadKind, AuthFail, NoRoom };
const char* openResultName(OpenResult r);
// Checks and decrypts a received packet. On Ok, *kind and pt[0..*ptLen) hold the message and
// pt[*ptLen] = 0 (ptCap must be at least ciphertext length + 1).
OpenResult open(Aead& aead, const uint8_t key[kKeyLen], const uint8_t* pkt, size_t len, uint8_t* kind, uint8_t* pt,
                size_t ptCap, size_t* ptLen);

struct JoinInfo {
  const char* ssid = "";
  const char* pass = "";
  uint16_t port = 0;
  const char* token = "";
  const char* host = "";
  const char* sid = nullptr;  // optional session id (16 hex digits)
};
// The kind 1 plaintext as compact JSON. When it would be over 217 bytes with the sid, the sid is
// left out (*withSid = false); when it is still too long, returns 0 (the hotspot cannot be handed
// over: the camera board stays home). Otherwise returns the length.
size_t buildJoinPlaintext(const JoinInfo& j, char* out, size_t cap, bool* withSid);
// The kind 2 plaintext: {} or {"sid":".."}.
size_t buildLeavePlaintext(const char* sid, char* out, size_t cap);

// Hex helpers for the link key console commands (lower-case output; input either case).
void toHex(const uint8_t* in, size_t n, char* out);  // out gets 2n chars + NUL
bool fromHex(const char* in, uint8_t* out, size_t n); // exactly 2n hex chars

}  // namespace espnow
}  // namespace spike
