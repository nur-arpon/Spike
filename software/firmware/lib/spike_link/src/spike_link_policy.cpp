// spike_link_policy.cpp -- see spike_link_policy.h (PROTOCOL.md 11.4 / 11.5).
#include "spike_link_policy.h"

#include <stdio.h>
#include <string.h>

namespace spike {
namespace link {

static bool is(const char* a, const char* b) { return a && strcmp(a, b) == 0; }

Brain activeBrain(const LinkView& v) {
  if (v.wsUp) return v.wsKind == WsKind::Home ? Brain::Lan : Brain::Hotspot;
  if (v.bleUp) return Brain::Ble;
  return Brain::None;
}

const char* brainName(Brain b) {
  switch (b) {
    case Brain::Lan: return "lan";
    case Brain::Ble: return "ble";
    case Brain::Hotspot: return "hotspot";
    default: return "none";
  }
}

Inbound classifyInbound(Link from, const char* type, bool linkHelloDone, const LinkView& v) {
  if (!type) return Inbound::Ignore;
  if (is(type, "hello")) return Inbound::Handle;   // the hello exchange always runs (3.2, 11.4)
  if (!linkHelloDone) return Inbound::Ignore;       // nothing but hello before the brain's hello
  const bool hotspotCmd = is(type, "hotspot_join") || is(type, "hotspot_leave");
  if (hotspotCmd) return from == Link::Ble ? Inbound::Handle : Inbound::BadLink;  // BLE only (11.5)
  if (from == Link::Ble && v.wsUp && v.wsKind == WsKind::Home) {
    // The laptop brain is followed. Still handled: the heartbeat, and messages that are not
    // commands (answers and errors must never be answered with an error, or two sides could
    // bounce errors forever; robot_link_ack only reports the camera board).
    if (is(type, "ping") || is(type, "pong") || is(type, "error") || is(type, "robot_link_ack")) return Inbound::Handle;
    return Inbound::Busy;
  }
  return Inbound::Handle;
}

bool routeOutbound(const char* type, const LinkView& v, Link* out) {
  if (is(type, "hotspot_state") || is(type, "robot_link")) {  // for the phone (11.7): BLE, else the hotspot
    if (v.bleUp) { *out = Link::Ble; return true; }
    if (v.wsUp && v.wsKind == WsKind::Hotspot) { *out = Link::Ws; return true; }
    return false;
  }
  const Brain b = activeBrain(v);
  if (b == Brain::Lan || b == Brain::Hotspot) { *out = Link::Ws; return true; }
  if (b == Brain::Ble) {
    if (is(type, "audio") || is(type, "camera") || is(type, "say_audio")) return false;  // never over BLE (11.2)
    *out = Link::Ble;
    return true;
  }
  return false;
}

bool micWanted(const LinkView& v) { return activeBrain(v) == Brain::Lan; }

// ---- hotspot_join ----------------------------------------------------------------------------------
static bool allIn(const char* s, unsigned char lo, unsigned char hi) {
  for (; *s; s++)
    if ((unsigned char)*s < lo || (unsigned char)*s > hi) return false;
  return true;
}

static bool hostChars(const char* s) {
  for (; *s; s++) {
    char c = *s;
    bool ok = (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '.' || c == '-';
    if (!ok) return false;
  }
  return true;
}

const char* checkHotspotJoin(const HotspotJoin& j) {
  if (!j.ssid) return "ssid missing";
  size_t n = strlen(j.ssid);
  if (n < 1 || n > 32) return "ssid must be 1..32 bytes";
  if (!j.pass) return "pass missing";
  n = strlen(j.pass);
  if (n < 8 || n > 63) return "pass must be 8..63 characters";
  if (!allIn(j.pass, 0x20, 0x7E)) return "pass must be printable ASCII (WPA2 passphrase)";
  if (!j.portIsInt) return "port missing or not an integer";
  if (j.port < 1 || j.port > 65535) return "port out of range";
  if (!j.token) return "token missing";
  n = strlen(j.token);
  if (n < 16 || n > 64) return "token must be 16..64 characters";
  if (!allIn(j.token, 0x21, 0x7E)) return "token must be printable ASCII without spaces";
  if (j.host) {
    n = strlen(j.host);
    if (n > 63) return "host too long";
    if (!hostChars(j.host)) return "host must be an IPv4 address or a host name";
  }
  return nullptr;
}

const char* hotspotFailReason(int r) {
  switch (r) {
    case 201:  // WIFI_REASON_NO_AP_FOUND (also a 5 GHz-only hotspot: the ESP32-S3 is 2.4 GHz only)
      return "not_found";
    case 14:   // MIC_FAILURE
    case 15:   // 4WAY_HANDSHAKE_TIMEOUT (the usual wrong-password symptom)
    case 16:   // GROUP_KEY_UPDATE_TIMEOUT
    case 17:   // IE_IN_4WAY_DIFFERS
    case 23:   // 802_1X_AUTH_FAILED
    case 202:  // AUTH_FAIL
    case 204:  // HANDSHAKE_TIMEOUT
      return "auth";
    default:
      return "timeout";
  }
}

bool jsonEscape(const char* in, char* out, size_t cap) {
  if (!out || cap == 0) return false;
  size_t o = 0;
  for (const unsigned char* p = (const unsigned char*)(in ? in : ""); *p; p++) {
    char tmp[8];
    size_t k;
    if (*p == '"' || *p == '\\') { tmp[0] = '\\'; tmp[1] = (char)*p; k = 2; }
    else if (*p < 0x20) { snprintf(tmp, sizeof tmp, "\\u%04x", *p); k = 6; }
    else { tmp[0] = (char)*p; k = 1; }
    if (o + k + 1 > cap) { out[0] = 0; return false; }
    memcpy(out + o, tmp, k);
    o += k;
  }
  out[o] = 0;
  return true;
}

}  // namespace link
}  // namespace spike
