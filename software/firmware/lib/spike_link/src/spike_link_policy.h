// spike_link_policy.h -- PROTOCOL.md 11.4 / 11.5 decisions as pure functions (no Arduino, no I/O),
// so the host test (`face_pc link`) checks exactly the logic the screen board runs.
//
//  * one brain at a time: the home (laptop) WebSocket brain wins; while its hello is done, brain
//    messages that arrive over BLE are answered `error busy` (ping, the hello exchange,
//    hotspot_join / hotspot_leave and a few non-commands are still handled)
//  * robot -> brain messages go to ONE link: the WebSocket when its hello is done, else BLE
//  * hotspot_join / hotspot_leave are accepted over BLE only
//  * hotspot_join field checks and the Wi-Fi failure reasons of `hotspot_state`
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace spike {
namespace link {

enum class Link : uint8_t { Ws = 0, Ble = 1 };
enum class WsKind : uint8_t { Home = 0, Hotspot = 1 };      // where the WebSocket brain link points
enum class Brain : uint8_t { None = 0, Lan, Ble, Hotspot }; // whose commands the robot follows

// "Up" = the hello exchange on that link is complete (the brain's hello arrived).
struct LinkView {
  bool wsUp = false;
  WsKind wsKind = WsKind::Home;
  bool bleUp = false;
};

Brain activeBrain(const LinkView& v);
const char* brainName(Brain b);  // "none", "lan", "ble", "hotspot" (robot_link.brain, info.brain)

enum class Inbound : uint8_t {
  Handle,   // process it
  Busy,     // answer `error` code `busy` (another brain is followed) and drop it
  Ignore,   // drop silently (nothing but hello is expected before the brain's hello)
  BadLink,  // not allowed on this link: answer `error` code `bad_value`
};
// type: the message's `type`; linkHelloDone: the brain's hello already arrived on `from`.
Inbound classifyInbound(Link from, const char* type, bool linkHelloDone, const LinkView& v);

// Which link carries a robot -> brain message of this type. False = no link wants it (drop it).
// Replies (pong, error, hello) are NOT routed: they go back on the link they answer.
bool routeOutbound(const char* type, const LinkView& v, Link* out);

// Robot microphones stream only to the laptop brain: away, the phone listens (11.3).
bool micWanted(const LinkView& v);

// ---- hotspot_join (11.5) -------------------------------------------------------------------------
struct HotspotJoin {
  const char* ssid = nullptr;   // nullptr when the field is missing or not a string
  const char* pass = nullptr;
  const char* token = nullptr;
  const char* host = nullptr;   // "" = the Wi-Fi gateway
  bool portIsInt = false;
  long port = 0;
};
// Returns nullptr when valid, else a short reason for the log (the robot answers
// hotspot_state failed / reason bad_value).
const char* checkHotspotJoin(const HotspotJoin& j);

// hotspot_state.reason for a failed join, from the last Wi-Fi disconnect reason code the ESP32
// reported (esp_wifi `wifi_err_reason_t`, 0 = none seen) when the 20 s join timeout ran out.
const char* hotspotFailReason(int lastWifiReason);

// ---- small helpers ---------------------------------------------------------------------------------
// JSON string body escaping (no surrounding quotes): `"` `\` and control characters. Bytes >= 0x80
// pass through (the input came from a JSON message, so it is already UTF-8). Returns false (and
// out = "") when it does not fit; cap includes the NUL.
bool jsonEscape(const char* in, char* out, size_t cap);

}  // namespace link
}  // namespace spike
