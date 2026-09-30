// handover.cpp -- the robot's link key and the ESP-NOW hand-over of the phone's hotspot to the camera
// board (PROTOCOL.md v1.3, 11.6).
//
// Link key: 32 random bytes made on the first boot (hardware RNG, after the radio is on) and kept in
// NVS namespace "spikelink" -- NOT in "spike", so `factory-reset` does not break the pairing between
// the two boards. `linkkey` on the console prints it; the camera board gets it once at the bench with
// `linkkey <64 hex>`.
//
// Hand-over: after joining the hotspot the screen board broadcasts, once a second on the hotspot's
// channel, "SPK1" | 1 | nonce | AES-256-GCM({ssid, pass, port, token, host, sid}) | tag -- until the
// phone confirms the camera is online (robot_link_ack camera:true) or for 120 s. Leaving the hotspot
// sends kind 2 ({"sid"}) three times. The packet format lives in lib/spike_link (host-tested).
#include "app.h"

#include <Preferences.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_random.h>
#include <esp_wifi.h>

#include "spike_aead_mbedtls.h"
#include "spike_espnow_pkt.h"

namespace en = spike::espnow;

static uint8_t linkKey[en::kKeyLen];
static bool haveKey = false;

static bool allZero(const uint8_t* p, size_t n) {
  uint8_t acc = 0;
  for (size_t i = 0; i < n; i++) acc |= p[i];
  return acc == 0;
}

void linkKeyEnsure() {
  Preferences p;
  p.begin("spikelink", false);
  if (p.getBytesLength("key") == en::kKeyLen && p.getBytes("key", linkKey, en::kKeyLen) == en::kKeyLen && !allZero(linkKey, en::kKeyLen)) {
    haveKey = true;
  } else {
    do esp_fill_random(linkKey, en::kKeyLen); while (allZero(linkKey, en::kKeyLen));
    haveKey = p.putBytes("key", linkKey, en::kKeyLen) == en::kKeyLen;
    logf("linkkey: made this robot's link key%s -- type 'linkkey' and copy it to the camera board once",
         haveKey ? "" : " (but could NOT save it)");
  }
  p.end();
}

void linkKeyPrint() {
  if (!haveKey) { logf("linkkey: none (NVS problem?)"); return; }
  char hex[2 * en::kKeyLen + 1];
  en::toHex(linkKey, en::kKeyLen, hex);
  logf("linkkey %s", hex);
  logf("On the CAMERA board's console type exactly the line above (it is secret: keep it off photos and chats).");
}

// ---- hand-over (loop task; handoverCameraAck may come from any task) ----------------------------------
static const uint8_t kBroadcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static const uint32_t SEND_EVERY_MS = 1000, GIVE_UP_MS = 120000;
static bool espnowUp = false, active = false;
static volatile bool ackPending = false, cameraOnline = false;
static uint32_t startMs = 0, lastSendMs = 0;
static char plain[en::kMaxPlaintext + 1];
static size_t plainLen = 0;
static char sid[en::kSidLen + 1];

static void wipePlain() {
  volatile char* v = plain;
  for (size_t i = 0; i < sizeof plain; i++) v[i] = 0;
  plainLen = 0;
}

static bool espnowBegin() {
  if (espnowUp) return true;
  if (esp_now_init() != ESP_OK) { logf("handover: ESP-NOW would not start"); return false; }
  esp_now_peer_info_t peer;
  memset(&peer, 0, sizeof peer);
  memcpy(peer.peer_addr, kBroadcast, 6);
  peer.channel = 0;  // the channel the station is on: the hotspot's
  peer.ifidx = WIFI_IF_STA;
  peer.encrypt = false;  // broadcast; the payload is AES-256-GCM sealed with the link key
  if (esp_now_add_peer(&peer) != ESP_OK) { esp_now_deinit(); logf("handover: ESP-NOW peer failed"); return false; }
  espnowUp = true;
  return true;
}

static void espnowEnd() {
  if (!espnowUp) return;
  esp_now_deinit();
  espnowUp = false;
}

static bool sendKind(uint8_t kind, const char* pt, size_t n) {
  uint8_t nonce[en::kNonceLen];
  esp_fill_random(nonce, sizeof nonce);  // random per message (radio on: true RNG)
  uint8_t pkt[en::kMaxPacket];
  size_t len = en::seal(en::mbedtlsAead(), linkKey, kind, nonce, (const uint8_t*)pt, n, pkt, sizeof pkt);
  if (!len) return false;
  return esp_now_send(kBroadcast, pkt, len) == ESP_OK;
}

void handoverStart(const char* ssid, const char* pass, uint16_t port, const char* token, const char* host, const char* sidHex) {
  active = false;
  cameraOnline = false;
  ackPending = false;
  wipePlain();
  sid[0] = 0;
  if (!haveKey) { logf("handover: no link key -- the camera board stays on the home Wi-Fi"); return; }
  en::JoinInfo j;
  j.ssid = ssid;
  j.pass = pass;
  j.port = port;
  j.token = token;
  j.host = host;
  j.sid = sidHex;
  bool withSid = false;
  plainLen = en::buildJoinPlaintext(j, plain, sizeof plain, &withSid);
  if (!plainLen) {
    logf("handover: the hotspot details are too long for one ESP-NOW packet -- the camera board stays home (OPEN_QUESTIONS F-1)");
    return;
  }
  if (withSid) strncpy(sid, sidHex, sizeof sid - 1);
  if (!espnowBegin()) { wipePlain(); return; }
  active = true;
  startMs = millis();
  lastSendMs = startMs - SEND_EVERY_MS;  // first packet now
  logf("handover: telling the camera board about the hotspot (ESP-NOW, channel %d)", WiFi.channel());
}

void handoverLoop() {
  if (ackPending) {
    ackPending = false;
    cameraOnline = true;
    if (active) {
      active = false;
      wipePlain();
      logf("handover: the phone confirms the camera board is on its hotspot");
    }
  }
  if (!active) return;
  uint32_t now = millis();
  if (now - startMs > GIVE_UP_MS) {
    active = false;
    wipePlain();
    logf("handover: no camera confirmation after 120 s -- stopped (the camera board goes home by itself)");
    return;
  }
  if (now - lastSendMs >= SEND_EVERY_MS) {
    lastSendMs = now;
    if (!sendKind(en::KIND_JOIN, plain, plainLen)) logf("handover: ESP-NOW send failed");
  }
}

void handoverCameraAck() { ackPending = true; }
bool handoverCameraOnline() { return cameraOnline; }

void handoverStop(bool sendLeave) {
  const bool wasActive = active;
  active = false;
  wipePlain();
  if (sendLeave && haveKey && (espnowUp || espnowBegin())) {
    char lv[40];
    size_t n = en::buildLeavePlaintext(sid[0] ? sid : nullptr, lv, sizeof lv);
    for (int i = 0; i < 3 && n; i++) {
      sendKind(en::KIND_LEAVE, lv, n);
      delay(30);
    }
    logf("handover: told the camera board to go home");
  } else if (wasActive) {
    logf("handover: stopped");
  }
  cameraOnline = false;
  ackPending = false;
  sid[0] = 0;
  espnowEnd();
}
