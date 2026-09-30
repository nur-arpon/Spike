// cam_away.cpp -- the camera board away from home (PROTOCOL.md v1.3, 11.6).
//
// The camera board has no Bluetooth link to the phone. When the phone brain takes Spike away, the
// screen board hands the phone's hotspot over ESP-NOW, sealed with the robot's link key (AES-256-GCM,
// lib/spike_link). This module:
//  * keeps the link key (`linkkey <64 hex>` once at the bench; NVS namespace "spikelink", so
//    `factory-reset` keeps it). Without a key the camera stays on the home Wi-Fi only.
//  * while there is no working brain link: after a 20 s grace it leaves the home Wi-Fi and listens on
//    channels 1..13 in turn (1.5 s each); after each full sweep it tries the home Wi-Fi again for 20 s
//    (so it still comes back to the laptop at home). Frames that do not decrypt are ignored.
//  * on a kind 1 (join): joins that hotspot (details in RAM only) and connects as role "camera" with the
//    one-time token to host-or-gateway:port. While it HAS a working brain link, kind 1 is ignored.
//  * kind 2 (leave, with the matching session id), or 60 s without its hotspot link: back home.
#include "cam.h"

#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#include "spike_aead_mbedtls.h"
#include "spike_espnow_pkt.h"
#include "spike_link_policy.h"

namespace en = spike::espnow;

static const uint32_t HOME_GRACE_MS = 20000, HOP_MS = 1500, HOTSPOT_DEAD_MS = 60000;
static const uint8_t CHANNELS = 13;

enum Mode : uint8_t { M_HOME, M_LISTEN, M_HOTSPOT };
static Mode mode = M_HOME;
static uint8_t key[en::kKeyLen];
static bool haveKey = false, espnowUp = false;
static AwayHotspot hs;  // RAM only
static uint32_t noLinkSinceMs = 0, hopAtMs = 0, hsLastGoodMs = 0;
static uint8_t hopCh = 0, hops = 0;

struct RxPkt {
  uint8_t len;
  uint8_t ch;
  uint8_t data[en::kMaxPacket];
};
static QueueHandle_t rxQ;

static void wipe(void* p, size_t n) {
  volatile uint8_t* v = (volatile uint8_t*)p;
  while (n--) *v++ = 0;
}

const AwayHotspot* awayHotspot() { return mode == M_HOTSPOT ? &hs : nullptr; }
bool awayLinkKeySet() { return haveKey; }
const char* awayModeName() { return mode == M_HOME ? "home" : (mode == M_LISTEN ? "listening for the phone's hotspot" : "phone's hotspot"); }

// ---- link key --------------------------------------------------------------------------------------------
static void loadKey() {
  Preferences p;
  p.begin("spikelink", true);
  haveKey = p.getBytesLength("key") == en::kKeyLen && p.getBytes("key", key, en::kKeyLen) == en::kKeyLen;
  p.end();
}

void awayLinkKeyCommand(const char* arg) {
  if (!arg || !arg[0]) {
    logf("linkkey: %s", haveKey ? "set -- the camera follows Spike to the phone's hotspot" : "NOT set -- camera stays on the home Wi-Fi");
    logf("  linkkey <64 hex digits>   store the key printed by the screen board's 'linkkey'");
    logf("  linkkey forget            remove it");
    return;
  }
  Preferences p;
  if (!strcmp(arg, "forget")) {
    p.begin("spikelink", false);
    p.remove("key");
    p.end();
    wipe(key, sizeof key);
    haveKey = false;
    logf("linkkey: removed; reboot to stop listening");
    return;
  }
  uint8_t k[en::kKeyLen];
  if (!en::fromHex(arg, k, sizeof k)) { logf("linkkey: needs exactly 64 hex digits (0-9, a-f)"); return; }
  p.begin("spikelink", false);
  bool ok = p.putBytes("key", k, sizeof k) == sizeof k;
  p.end();
  wipe(k, sizeof k);
  logf("linkkey: %s", ok ? "saved. Reboot the camera board to use it." : "could NOT be saved");
}

// ---- ESP-NOW receive (Wi-Fi task: copy only) ----------------------------------------------------------
static void onRecv(const uint8_t*, const uint8_t* data, int len) {
  if (len <= 0 || len > (int)en::kMaxPacket || !rxQ) return;
  RxPkt p;
  p.len = (uint8_t)len;
  uint8_t ch = 0;
  wifi_second_chan_t second;
  esp_wifi_get_channel(&ch, &second);
  p.ch = ch;
  memcpy(p.data, data, len);
  xQueueSend(rxQ, &p, 0);
}

static bool espnowBegin() {
  if (espnowUp) return true;
  if (WiFi.getMode() == WIFI_OFF) WiFi.mode(WIFI_STA);
  if (esp_now_init() != ESP_OK) { logf("away: ESP-NOW would not start"); return false; }
  esp_now_register_recv_cb(onRecv);
  espnowUp = true;
  return true;
}

// The station must be running for ESP-NOW and for channel hopping. Closing the setup portal on a board
// with no home Wi-Fi turns the radio off (softAPdisconnect), which also silences ESP-NOW: bring both back.
static void ensureRadio() {
  if (WiFi.getMode() & WIFI_MODE_STA) return;
  WiFi.mode(portalActive() ? WIFI_AP_STA : WIFI_STA);
  if (espnowUp) {
    esp_now_deinit();
    espnowUp = false;
  }
  espnowBegin();
}

// ---- modes -----------------------------------------------------------------------------------------------
static void goHome(const char* why) {
  logf("away: back to the home Wi-Fi (%s)", why);
  wipe(&hs, sizeof hs);
  mode = M_HOME;
  netRestart();
  WiFi.setAutoReconnect(true);
  WiFi.disconnect();
  if (cs.ssid[0]) WiFi.begin(cs.ssid, cs.pass);
  noLinkSinceMs = millis();
}

static void startListening() {
  logf("away: no brain link -- listening for the screen board on channels 1-%d", CHANNELS);
  mode = M_LISTEN;
  netRestart();
  ensureRadio();
  WiFi.setAutoReconnect(false);  // the station must stay idle so the channel can hop
  WiFi.disconnect();
  hopCh = 0;
  hops = 0;
  hopAtMs = millis() - HOP_MS;
}

static void joinHotspot(const AwayHotspot& h, uint8_t channel) {
  wipe(&hs, sizeof hs);
  hs = h;
  mode = M_HOTSPOT;
  hsLastGoodMs = millis();
  netRestart();
  ensureRadio();
  WiFi.setAutoReconnect(true);
  WiFi.disconnect();
  WiFi.begin(hs.ssid, hs.pass, channel);  // RAM only: WiFi.persistent(false)
  logf("away: joining the phone's hotspot '%s' (channel %u)", hs.ssid, channel);
}

static void onPacket(const RxPkt& p) {
  uint8_t kind = 0;
  char pt[en::kMaxPlaintext + 1];
  size_t n = 0;
  en::OpenResult r = en::open(en::mbedtlsAead(), key, p.data, p.len, &kind, (uint8_t*)pt, sizeof pt, &n);
  if (r != en::OpenResult::Ok) return;  // not ours, or not from this robot: ignored
  JsonDocument doc;
  bool parsed = !deserializeJson(doc, pt, n);
  wipe(pt, sizeof pt);
  if (!parsed || !doc.is<JsonObject>()) return;
  const char* sid = doc["sid"] | "";
  if (kind == en::KIND_LEAVE) {
    if (mode != M_HOTSPOT) return;
    if (hs.sid[0] && strcmp(sid, hs.sid) != 0) { logf("away: a 'leave' for another hotspot session -- ignored"); return; }
    goHome("the screen board left the hotspot");
    return;
  }
  // kind 1: only while there is no working brain link (11.6), and not again for the session we are on
  if (netConnected()) return;
  spike::link::HotspotJoin j;
  j.ssid = doc["ssid"].is<const char*>() ? doc["ssid"].as<const char*>() : nullptr;
  j.pass = doc["pass"].is<const char*>() ? doc["pass"].as<const char*>() : nullptr;
  j.token = doc["token"].is<const char*>() ? doc["token"].as<const char*>() : nullptr;
  j.host = doc["host"].is<const char*>() ? doc["host"].as<const char*>() : nullptr;
  j.portIsInt = doc["port"].is<long>();
  j.port = j.portIsInt ? doc["port"].as<long>() : 0;
  const char* why = spike::link::checkHotspotJoin(j);
  if (why) { logf("away: hand-over refused: %s", why); return; }
  if (mode == M_HOTSPOT && !strcmp(hs.ssid, j.ssid) && !strcmp(hs.sid, sid)) return;  // already joining it
  AwayHotspot h;
  memset(&h, 0, sizeof h);
  strncpy(h.ssid, j.ssid, sizeof h.ssid - 1);
  strncpy(h.pass, j.pass, sizeof h.pass - 1);
  strncpy(h.token, j.token, sizeof h.token - 1);
  strncpy(h.host, j.host ? j.host : "", sizeof h.host - 1);
  strncpy(h.sid, strlen(sid) == en::kSidLen ? sid : "", sizeof h.sid - 1);
  h.port = (uint16_t)j.port;
  joinHotspot(h, p.ch);
  wipe(&h, sizeof h);
}

void awayBegin() {
  loadKey();
  if (!haveKey) { logf("away: no link key -- the camera stays on the home Wi-Fi (bench step: linkkey)"); return; }
  rxQ = xQueueCreate(4, sizeof(RxPkt));
  if (!rxQ || !espnowBegin()) { haveKey = false; return; }
  noLinkSinceMs = millis();
  logf("away: link key set -- the camera follows Spike to the phone's hotspot");
}

void awayLoop() {
  if (!haveKey) return;
  RxPkt p;
  while (xQueueReceive(rxQ, &p, 0) == pdTRUE) onPacket(p);
  uint32_t now = millis();
  switch (mode) {
    case M_HOME:
      if (netConnected() || portalActive()) noLinkSinceMs = now;
      else if (now - noLinkSinceMs > HOME_GRACE_MS) startListening();
      break;
    case M_LISTEN:
      if (portalActive()) break;  // the setup AP pins the channel
      if (now - hopAtMs >= HOP_MS) {
        if (hops >= CHANNELS && cs.ssid[0]) { goHome("one sweep done, trying the home Wi-Fi again"); break; }
        hopCh = hopCh % CHANNELS + 1;
        esp_wifi_set_channel(hopCh, WIFI_SECOND_CHAN_NONE);
        hopAtMs = now;
        hops++;
      }
      break;
    case M_HOTSPOT:
      if (netConnected()) hsLastGoodMs = now;
      else if (now - hsLastGoodMs > HOTSPOT_DEAD_MS) goHome("no hotspot link for 60 s");
      break;
  }
}
