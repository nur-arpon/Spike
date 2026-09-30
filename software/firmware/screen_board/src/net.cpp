// net.cpp -- Wi-Fi and the brain links, implementing software/protocol/PROTOCOL.md v1.3 exactly.
//
// Two links carry the same protocol (sections 3 to 6):
//  * LINK_WS: a WebSocket CLIENT -- of the laptop brain on the home Wi-Fi (as in v1.1/v1.2: hello within
//    5 s, nothing before the brain's hello, pong to ping, 3 x heartbeat dead-link rule, 0.5/1/2/4/8/10 s
//    reconnect with +-20 % jitter, text frames of one JSON object, unknown types and fields ignored,
//    v != 1 -> error version_mismatch), or of the phone brain over the phone's hotspot (11.5).
//  * LINK_BLE: the phone brain over Bluetooth LE (ble_link.cpp does the GATT + framing, 11.1-11.3).
// One brain at a time (11.4, lib/spike_link/src/spike_link_policy.*): the laptop brain wins; while its
// hello is done, brain messages over BLE are answered `error busy`. Robot -> brain messages go to one
// link: the WebSocket when its hello is done, else BLE. One shared handler serves both links.
// The robot never depends on any link: every reflex and the whole face life run without them.
#include "app.h"
#include "config.h"
#include <WiFi.h>
#include <ArduinoJson.h>
#include <esp_websocket_client.h>
#include <esp_heap_caps.h>
#include <esp_random.h>
#include "spike_recipe.h"
#include "spike_link_policy.h"
#include "spike_body.h"  // GaitStyle for the v1.4 walk action

using spike::link::Brain;
using spike::link::Inbound;
using spike::link::Link;
using spike::link::LinkView;
using spike::link::WsKind;

// ---- per-link protocol state ---------------------------------------------------------------------------
struct LinkState {
  volatile bool open;        // WS: the socket is connected; BLE: an authenticated phone subscribed to tx
  volatile bool helloDone;   // the brain's hello arrived on this link
  uint32_t outId;            // envelope id counter (under sendLock)
  volatile uint32_t lastRxMs;
  volatile float heartbeatS;
  volatile uint32_t helloSentMs;
};
static LinkState L[2];
static SemaphoreHandle_t sendLock[2];
static SemaphoreHandle_t handleLock;  // the handler runs on the WS task AND the blelink task

// ---- WebSocket client ----------------------------------------------------------------------------------
static esp_websocket_client_handle_t ws;
static volatile bool wsClosing = false;
static volatile bool wsToHotspot = false;  // this WS client points at the phone on its hotspot
static char* rxBuf;                         // reassembly of fragmented frames
static size_t rxLen = 0;
static bool rxOverflow = false;
static int backoff = 0;
static uint32_t nextConnectMs = 0, connectStartMs = 0;

// ---- Wi-Fi: the saved home network, or the phone's hotspot (details in RAM only, 11.5) -----------------
enum WifiMode : uint8_t { WM_HOME, WM_HS_JOINING, WM_HS_JOINED };
static volatile WifiMode wm = WM_HOME;
struct Hotspot {
  char ssid[33];
  char pass[64];
  char token[65];
  char host[64];
  uint16_t port;
  char sid[17];  // random session id for the ESP-NOW hand-over (see spike_espnow_pkt.h)
};
static Hotspot hs;      // the hotspot in use (loop task); wiped when leaving
static Hotspot hsReq;   // a join request from the handler, under hsMux
static portMUX_TYPE hsMux = portMUX_INITIALIZER_UNLOCKED;
static volatile bool hsJoinReq = false, hsLeaveReq = false;
static uint32_t hsJoinStartMs = 0, hsLastGoodMs = 0;
static volatile int lastWifiReason = 0;
static bool homeWifiStarted = false;
static const uint32_t HOTSPOT_JOIN_TIMEOUT_MS = 20000, HOTSPOT_DEAD_MS = 60000, BLE_HELLO_TIMEOUT_MS = 10000;

static void wipe(void* p, size_t n) {  // clear secrets so the compiler cannot drop it
  volatile uint8_t* v = (volatile uint8_t*)p;
  while (n--) *v++ = 0;
}

// "more than ms since t", safe when another task stamped t after the caller read the clock (a plain
// unsigned now - t would wrap to ~49 days and declare a healthy link dead)
static bool olderThan(uint32_t t, uint32_t ms) { return (int32_t)(millis() - t) > (int32_t)ms; }

static LinkView view() {
  LinkView v;
  v.wsUp = L[LINK_WS].open && L[LINK_WS].helloDone;
  v.wsKind = wsToHotspot ? WsKind::Hotspot : WsKind::Home;
  v.bleUp = L[LINK_BLE].open && L[LINK_BLE].helloDone;
  return v;
}

bool netConnected() { return spike::link::activeBrain(view()) != Brain::None; }
bool netWantsMic() { return spike::link::micWanted(view()); }
const char* netBrainName() { return spike::link::brainName(spike::link::activeBrain(view())); }
bool netOnHomeWifi() { return wm == WM_HOME && WiFi.status() == WL_CONNECTED; }

// ---- robot -> brain ------------------------------------------------------------------------------------
bool netSendOn(LinkId link, const char* type, const char* fields) {
  LinkState& s = L[link];
  if (!s.open) return false;
  if (!s.helloDone && strcmp(type, "hello") != 0 && strcmp(type, "pong") != 0) return false;  // protocol 3.2
  size_t flen = fields ? strlen(fields) : 0;
  size_t cap = flen + 128;
  char stackBuf[512];
  char* buf = cap <= sizeof stackBuf ? stackBuf : (char*)heap_caps_malloc(cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!buf) return false;
  bool ok = false;
  xSemaphoreTake(sendLock[link], portMAX_DELAY);
  if (link == LINK_WS ? (ws && !wsClosing) : true) {
    uint32_t id = s.outId = (s.outId == 0xFFFFFFFFu) ? 1 : s.outId + 1;
    int n = snprintf(buf, cap, "{\"v\":1,\"type\":\"%s\",\"id\":%lu,\"ts\":%lu%s%s}", type, (unsigned long)id,
                     (unsigned long)millis(), flen ? "," : "", flen ? fields : "");
    if (n > 0 && (size_t)n < cap)
      ok = link == LINK_WS ? esp_websocket_client_send_text(ws, buf, n, pdMS_TO_TICKS(1000)) >= 0 : bleQueueMessage(buf, n);
  }
  xSemaphoreGive(sendLock[link]);
  if (buf != stackBuf) heap_caps_free(buf);
  return ok;
}

bool netSend(const char* type, const char* fields) {
  Link out;
  if (!spike::link::routeOutbound(type, view(), &out)) return false;
  return netSendOn(out == Link::Ws ? LINK_WS : LINK_BLE, type, fields);
}

static void sendError(LinkId link, long re, const char* code, const char* msg) {
  char f[160];
  snprintf(f, sizeof f, "\"re\":%ld,\"code\":\"%s\",\"message\":\"%s\"", re, code, msg);
  netSendOn(link, "error", f);
}

// hello on the WebSocket: the laptop (as before), or the phone over its hotspot (one-time token, link)
static void sendHelloWs() {
  char f[320];
  char tok[132];
  const bool hot = wsToHotspot;
  int n = snprintf(f, sizeof f,
                   "\"role\":\"face\",\"device_id\":\"%s\",\"fw\":\"%s\","
                   "\"caps\":[\"face\",\"speaker\",\"mic\",\"touch\",\"imu\",\"edge\",\"battery\",\"drive\"],"
                   "\"audio_out\":{\"rates\":[%d,16000],\"format\":\"pcm_s16le\"}",
                   deviceId(), SPIKE_FW_VERSION, SPEAKER_RATE);
  const char* t = hot ? hs.token : gSettings.token;
  if (t[0] && spike::link::jsonEscape(t, tok, sizeof tok) && n > 0 && n < (int)sizeof f - 150)
    n += snprintf(f + n, sizeof f - n, ",\"token\":\"%s\"", tok);
  if (hot && n > 0 && n < (int)sizeof f - 20) snprintf(f + n, sizeof f - n, ",\"link\":\"hotspot\"");
  netSendOn(LINK_WS, "hello", f);
  L[LINK_WS].helloSentMs = millis();
}

// hello over BLE (11.3): role face, the same caps, "link":"ble", no token (the bond authenticates)
static void sendHelloBle() {
  char f[256];
  snprintf(f, sizeof f,
           "\"role\":\"face\",\"device_id\":\"%s\",\"fw\":\"%s\","
           "\"caps\":[\"face\",\"speaker\",\"mic\",\"touch\",\"imu\",\"edge\",\"battery\",\"drive\"],\"link\":\"ble\"",
           deviceId(), SPIKE_FW_VERSION);
  netSendOn(LINK_BLE, "hello", f);
  L[LINK_BLE].helloSentMs = millis();
}

static void post(uint8_t t, int a = 0, int b = 0, float x = 0, float y = 0, const char* s = nullptr) {
  Cmd c = makeCmd(t, a, b, x, y, s);
  if (!postCmd(c)) logf("net: face queue full, dropped command %d", t);
}

static volatile bool robotLinkDirty = true;  // send robot_link again at the next loop

// ---- brain -> robot (one handler for both links) ----------------------------------------------------
static void handleHello(LinkId from, JsonDocument& doc) {
  LinkState& s = L[from];
  s.helloDone = true;
  if (from == LINK_WS) backoff = 0;
  float hb = doc["heartbeat_s"] | 5.0f;
  s.heartbeatS = hb < 1 ? 1 : hb;
  const bool laptopFollowed = from == LINK_BLE && view().wsUp && !wsToHotspot;
  const char* linkName = from == LINK_BLE ? "phone brain over BLE" : (wsToHotspot ? "phone brain over the hotspot" : "brain");
  logf("net: %s hello: server %s %s, heartbeat %.1f s%s", linkName, doc["server"] | "?", doc["version"] | "?",
       (float)s.heartbeatS, laptopFollowed ? " (the laptop brain is in charge: this phone gets busy for now)" : "");
  robotLinkDirty = true;
  if (laptopFollowed) return;  // the laptop brain's mode and names stay
  const char* mode = doc["mode"] | "";
  if (!strcmp(mode, "dog") || !strcmp(mode, "cat")) post(C_MODE, !strcmp(mode, "cat"));
  const char* dn = doc["names"]["dog"] | "";
  const char* cn = doc["names"]["cat"] | "";
  char names[132];
  snprintf(names, sizeof names, "%s|%s", dn, cn);
  post(C_HELLO_NAMES, 0, 0, 0, 0, names);
  post(C_BRAIN_UP);
}

// hotspot_join (11.5, BLE only): check every field, then hand it to the loop task (Wi-Fi calls live there)
static void handleHotspotJoin(JsonDocument& doc) {
  spike::link::HotspotJoin j;
  j.ssid = doc["ssid"].is<const char*>() ? doc["ssid"].as<const char*>() : nullptr;
  j.pass = doc["pass"].is<const char*>() ? doc["pass"].as<const char*>() : nullptr;
  j.token = doc["token"].is<const char*>() ? doc["token"].as<const char*>() : nullptr;
  j.host = doc["host"].is<const char*>() ? doc["host"].as<const char*>() : nullptr;
  j.portIsInt = doc["port"].is<long>();
  j.port = j.portIsInt ? doc["port"].as<long>() : 0;
  const char* why = spike::link::checkHotspotJoin(j);
  if (why) {
    logf("net: hotspot_join refused: %s", why);
    netSend("hotspot_state", "\"state\":\"failed\",\"reason\":\"bad_value\"");
    return;
  }
  portENTER_CRITICAL(&hsMux);
  memset(&hsReq, 0, sizeof hsReq);
  strncpy(hsReq.ssid, j.ssid, sizeof hsReq.ssid - 1);
  strncpy(hsReq.pass, j.pass, sizeof hsReq.pass - 1);
  strncpy(hsReq.token, j.token, sizeof hsReq.token - 1);
  strncpy(hsReq.host, j.host ? j.host : "", sizeof hsReq.host - 1);
  hsReq.port = (uint16_t)j.port;
  hsLeaveReq = false;
  hsJoinReq = true;
  portEXIT_CRITICAL(&hsMux);
}

static void handleLocked(LinkId from, char* text, size_t len) {
  JsonDocument doc;
  DeserializationError e = deserializeJson(doc, text, len);
  if (e) { sendError(from, 0, "bad_json", e.c_str()); return; }
  if (!doc.is<JsonObject>()) return;
  long id = doc["id"] | 0L;
  int v = doc["v"] | -1;
  const char* type = doc["type"] | "";
  if (v != 1) { sendError(from, id, "version_mismatch", "robot speaks v1"); return; }

  switch (spike::link::classifyInbound(from == LINK_BLE ? Link::Ble : Link::Ws, type, L[from].helloDone, view())) {
    case Inbound::Ignore: return;  // nothing but hello is expected before the brain's hello
    case Inbound::Busy: sendError(from, id, "busy", "Spike follows the laptop brain right now"); return;
    case Inbound::BadLink: sendError(from, id, "bad_value", "hotspot messages are accepted over Bluetooth only"); return;
    case Inbound::Handle: break;
  }

  if (!strcmp(type, "hello")) {
    handleHello(from, doc);
  } else if (!strcmp(type, "ping")) {
    char f[32];
    snprintf(f, sizeof f, "\"re\":%ld", id);
    netSendOn(from, "pong", f);
  } else if (!strcmp(type, "mood")) {
    post(C_MOOD, 0, 0, doc["hold_s"] | 0.0f, 0, doc["mood"] | "");
  } else if (!strcmp(type, "action")) {
    const char* act = doc["action"] | "";
    if (!strcmp(act, "walk")) {
      // protocol v1.4 body action: {"action":"walk","direction":"forward"|"back","steps":1..16,
      // "style":"auto"|"tiltStep"|"rearStep"|"march"}; the body task picks a fallback when needed
      const char* d = doc["direction"] | "forward";
      const char* st = doc["style"] | "auto";
      int steps = doc["steps"] | 4;
      int16_t style = !strcmp(st, "tiltStep") ? spike::body::GAIT_TILT_STEP
                    : !strcmp(st, "rearStep") ? spike::body::GAIT_REAR_STEP
                    : !strcmp(st, "march") ? spike::body::GAIT_MARCH : spike::body::GAIT_AUTO;
      BodyCmd b{B_WALK, (int16_t)(steps < 1 ? 1 : (steps > 16 ? 16 : steps)), "", (int16_t)(!strcmp(d, "back") ? -1 : 1), style};
      postBody(b);
    } else if (!strcmp(act, "paw")) {
      // v1.4: {"action":"paw","side":"left"|"right","from":"stand"|"sit"} (sit only if enabled on the robot)
      BodyCmd b{B_PAW, (int16_t)!strcmp(doc["side"] | "left", "right"), "", (int16_t)!strcmp(doc["from"] | "stand", "sit"), 0};
      postBody(b);
      post(C_ACTION, 0, 0, 0, 0, "boop");  // the face's happy "boop" look while the paw is offered
    } else post(C_ACTION, 0, 0, 0, 0, act);
  } else if (!strcmp(type, "event")) {
    post(C_EVENT, 0, 0, 0, 0, doc["event"] | "");
  } else if (!strcmp(type, "sound")) {
    post(C_SOUND, 0, 0, 0, 0, doc["sound"] | "");
  } else if (!strcmp(type, "look_at")) {
    post(C_LOOK, 0, 0, doc["x"] | 0.0f, doc["y"] | 0.0f);
  } else if (!strcmp(type, "set_mode")) {
    const char* m = doc["mode"] | "";
    if (!strcmp(m, "dog") || !strcmp(m, "cat")) post(C_MODE, !strcmp(m, "cat"));
  } else if (!strcmp(type, "set_recipe")) {
    bool cat = !strcmp(doc["mode"] | "dog", "cat");
    const char* code = doc["code"] | (const char*)nullptr;
    spike::Recipe r;
    bool ok = false;
    if (code) ok = spike::fromCode(code, &r);
    else if (doc["recipe"].is<JsonObject>()) {  // a face_v2 recipe object: normalise like recipe.js
      JsonObject o = doc["recipe"];
      r = spike::baseRecipe();
      for (int i = 0; i < spike::kNumSlots; i++) {
        int idx = spike::slotOptionIndex(i, o[spike::kSlotKeys[i]] | "");
        if (idx >= 0) r.slot(i) = (uint8_t)idx;
      }
      for (int i = 0; i < spike::kNumColors; i++) {
        spike::Rgb c;
        if (spike::parseHex(o[spike::kColorKeys[i]] | "", &c)) r.color(i) = c;
      }
      for (int i = 0; i < spike::kNumNumbers; i++)
        if (o[spike::kNumberKeys[i]].is<float>()) r.number(i) = o[spike::kNumberKeys[i]].as<float>();
      spike::clampNumbers(r);
      ok = true;
    }
    if (ok) {
      char c2[132];
      spike::toCode(r, c2, sizeof c2);
      post(C_RECIPE_CODE, cat, 0, 0, 0, c2);
    } else sendError(from, id, "bad_value", "set_recipe: bad code or recipe");
  } else if (!strcmp(type, "listening")) {
    static const char* const S[] = {"idle", "wake", "listening", "thinking", "speaking"};
    const char* st = doc["state"] | "";
    for (int i = 0; i < 5; i++) if (!strcmp(st, S[i])) {
      post(C_LISTEN, i);
      BodyCmd b{B_LISTENING, (int16_t)(i == 2), ""};
      postBody(b);
    }
  } else if (!strcmp(type, "say")) {
    static SayHeader h;  // guarded by handleLock
    memset(&h, 0, sizeof h);
    strncpy(h.utt, doc["utt"] | "", sizeof h.utt - 1);
    h.seq = doc["seq"] | 0;
    h.final = doc["final"] | false;
    const char* text2 = doc["text"] | "";
    h.hasText = text2[0] != 0;
    h.durationMs = doc["duration_ms"] | 0;
    strncpy(h.mood, doc["mood"] | "", sizeof h.mood - 1);
    JsonVariant a = doc["audio"];
    if (a.is<JsonObject>()) {
      h.hasAudio = true;
      h.rate = a["rate"] | SPEAKER_RATE;
      h.samples = a["samples"] | 0;
      h.chunks = a["chunks"] | 0;
      if (strcmp(a["format"] | "pcm_s16le", "pcm_s16le") != 0 || (a["channels"] | 1) != 1) {
        sendError(from, id, "bad_value", "say: only pcm_s16le mono");
        h.hasAudio = false;
      }
    }
    JsonVariant m = doc["mouth"];
    if (m.is<JsonObject>()) {
      h.mouthHz = m["rate_hz"] | 50;
      JsonArray vals = m["values"];
      for (JsonVariant x : vals) {
        if (h.mouthN >= (int)sizeof h.mouth) break;
        int q = x | 0;
        h.mouth[h.mouthN++] = (uint8_t)(q < 0 ? 0 : (q > 100 ? 100 : q));
      }
    }
    audioSay(h);
  } else if (!strcmp(type, "say_audio")) {
    const char* data = doc["data"] | "";
    audioSayChunk(doc["utt"] | "", doc["seq"] | 0, doc["index"] | 0, doc["last"] | false, data, strlen(data));
  } else if (!strcmp(type, "stop_speaking")) {
    audioStopSpeaking();
  } else if (!strcmp(type, "alarm")) {
    static const char* const S[] = {"ringing", "snoozed", "stopped"};
    const char* st = doc["state"] | "";
    for (int i = 0; i < 3; i++) if (!strcmp(st, S[i])) post(C_ALARM, i, doc["level"] | -1);
  } else if (!strcmp(type, "game")) {
    if (strcmp(doc["game"] | "", "rps") != 0) return;
    static const char* const P[] = {"start", "countdown", "shoot", "reveal", "end"};
    const char* ph = doc["phase"] | "";
    const char* res = doc["result"] | "draw";
    int r = !strcmp(res, "win") ? 1 : (!strcmp(res, "lose") ? -1 : 0);
    for (int i = 0; i < 5; i++) if (!strcmp(ph, P[i])) post(C_GAME, i, r);
  } else if (!strcmp(type, "drive")) {
    // protocol v1.2 section 10.3: the phone's joystick (via the laptop brain, or from the phone brain
    // over BLE / the hotspot -- the same B_DRIVE path for every link). Arcade mix; ttl = dead man's
    // switch (Controller::setDrive stops the wheels when it runs out). The safety filter in the body
    // task (desk edges, obstacles, pick-up, low battery) still applies to every command.
    float x = doc["x"] | 0.0f, y = doc["y"] | 0.0f;
    int ttl = doc["ttl_ms"] | 300;
    if (ttl < 100) ttl = 100;
    if (ttl > 1000) ttl = 1000;
    float l = y + x, r = y - x;
    l = l < -1 ? -1 : (l > 1 ? 1 : l);
    r = r < -1 ? -1 : (r > 1 ? 1 : r);
    BodyCmd b{B_DRIVE, (int16_t)ttl, "", (int16_t)lroundf(l * 1000), (int16_t)lroundf(r * 1000)};
    postBody(b);
  } else if (!strcmp(type, "set_display")) {
    // protocol v1.2 section 10.2: the owner's "show captions on Spike's screen" switch. This board
    // does not draw caption bubbles yet (captions go to the log), so the choice is only recorded
    // for the renderer that will; the brain re-sends it on every connect, so nothing is stored.
    static bool showCaptions = true;
    if (doc["captions"].is<bool>()) showCaptions = doc["captions"].as<bool>();
    logf("net: captions on screen %s", showCaptions ? "on" : "off");
  } else if (!strcmp(type, "hotspot_join")) {
    handleHotspotJoin(doc);  // v1.3 11.5; the policy already refused it on the WebSocket
  } else if (!strcmp(type, "hotspot_leave")) {
    hsJoinReq = false;
    hsLeaveReq = true;
  } else if (!strcmp(type, "robot_link_ack")) {
    if (doc["camera"] | false) handoverCameraAck();  // v1.3 11.6: the camera board reached the phone
  } else if (!strcmp(type, "error")) {
    logf("net: brain error %s: %s", doc["code"] | "?", doc["message"] | "");
  }
  // unknown types: ignored (protocol rule 2)
}

void netHandleMessage(LinkId from, char* text, size_t len) {
  L[from].lastRxMs = millis();
  xSemaphoreTake(handleLock, portMAX_DELAY);
  handleLocked(from, text, len);
  wipe(text, len);  // it may have carried hotspot details or a token: do not leave them in the buffer
  xSemaphoreGive(handleLock);
}

// ---- the WebSocket link ----------------------------------------------------------------------------------
static void wsEvent(void*, esp_event_base_t, int32_t eventId, void* data) {
  esp_websocket_event_data_t* d = (esp_websocket_event_data_t*)data;
  switch (eventId) {
    case WEBSOCKET_EVENT_CONNECTED:
      L[LINK_WS].helloDone = false;
      L[LINK_WS].lastRxMs = millis();
      L[LINK_WS].outId = 0;  // ids start at 1 on every connection (section 2)
      L[LINK_WS].helloSentMs = millis();
      L[LINK_WS].open = true;
      rxLen = 0;
      logf("net: connected to the %s", wsToHotspot ? "phone brain on its hotspot" : "laptop brain");
      sendHelloWs();
      break;
    case WEBSOCKET_EVENT_DISCONNECTED:
    case WEBSOCKET_EVENT_CLOSED:
      if (L[LINK_WS].open) logf("net: brain link closed");
      L[LINK_WS].open = false;
      L[LINK_WS].helloDone = false;
      robotLinkDirty = true;
      post(C_BRAIN_DOWN);
      break;
    case WEBSOCKET_EVENT_DATA: {
      L[LINK_WS].lastRxMs = millis();
      if (d->op_code == 0x08 || d->op_code == 0x09 || d->op_code == 0x0A) break;  // close / ping / pong frames
      if (d->op_code == 0x02) break;  // binary frames are ignored in v1
      if (d->payload_offset == 0) { rxLen = 0; rxOverflow = false; }
      if (d->payload_len > WS_MAX_MESSAGE || rxLen + d->data_len > WS_MAX_MESSAGE) {
        if (!rxOverflow) sendError(LINK_WS, 0, "too_big", "message over 64 KiB");
        rxOverflow = true;
        break;
      }
      memcpy(rxBuf + rxLen, d->data_ptr, d->data_len);
      rxLen += d->data_len;
      if (!rxOverflow && d->payload_offset + d->data_len >= d->payload_len && rxLen > 0) {
        rxBuf[rxLen] = 0;
        netHandleMessage(LINK_WS, rxBuf, rxLen);
        rxLen = 0;
      }
      break;
    }
    default:
      break;
  }
}

static void wsStop() {
  if (!ws) return;
  // no sender may be inside esp_websocket_client_send_text() while the client is destroyed
  xSemaphoreTake(sendLock[LINK_WS], portMAX_DELAY);
  wsClosing = true;
  xSemaphoreGive(sendLock[LINK_WS]);
  esp_websocket_client_stop(ws);
  esp_websocket_client_destroy(ws);
  ws = nullptr;
  L[LINK_WS].open = false;
  L[LINK_WS].helloDone = false;
  wsClosing = false;
  robotLinkDirty = true;
}

static void wsStart(bool toHotspot) {
  static char uri[96];
  if (toHotspot) {
    String gw = WiFi.gatewayIP().toString();
    snprintf(uri, sizeof uri, "ws://%s:%u/", hs.host[0] ? hs.host : gw.c_str(), hs.port);
  } else {
    snprintf(uri, sizeof uri, "ws://%s:%u/", gSettings.host, gSettings.port);
  }
  wsToHotspot = toHotspot;
  esp_websocket_client_config_t cfg = {};
  cfg.uri = uri;
  cfg.buffer_size = 8192;
  cfg.task_stack = 8192;
  cfg.task_prio = 5;
  cfg.disable_auto_reconnect = true;   // our own backoff (protocol 3.5)
  cfg.ping_interval_sec = 5;
  cfg.pingpong_timeout_sec = 20;
  ws = esp_websocket_client_init(&cfg);
  if (!ws) { logf("net: websocket init failed"); return; }
  esp_websocket_register_events(ws, WEBSOCKET_EVENT_ANY, wsEvent, nullptr);
  esp_websocket_client_start(ws);
}

// Reconnect with 0.5, 1, 2, 4, 8, 10 s (+-20 % jitter), reset after a successful hello.
static uint32_t backoffMs() {
  float base = 0.5f * (float)(1 << (backoff < 5 ? backoff : 5));
  if (base > 10) base = 10;
  backoff++;
  float j = 0.8f + 0.4f * (float)(esp_random() % 1000) / 1000.0f;
  return (uint32_t)(base * j * 1000);
}

// ---- the BLE session (called from the blelink task) ------------------------------------------------
void netBleSessionStart() {
  LinkState& s = L[LINK_BLE];
  s.helloDone = false;
  s.heartbeatS = 5;
  s.lastRxMs = millis();
  xSemaphoreTake(sendLock[LINK_BLE], portMAX_DELAY);
  s.outId = 0;  // ids start at 1 on every connection
  xSemaphoreGive(sendLock[LINK_BLE]);
  s.helloSentMs = millis();
  s.open = true;
  logf("net: phone subscribed over BLE -- saying hello");
  sendHelloBle();  // section 3 exactly as on a WebSocket (11.3)
}

void netBleSessionEnd() {
  bool wasBrain = spike::link::activeBrain(view()) == Brain::Ble;
  L[LINK_BLE].open = false;
  L[LINK_BLE].helloDone = false;
  robotLinkDirty = true;
  if (wasBrain) post(C_BRAIN_DOWN);
  logf("net: BLE session ended");
}

void netBleTooBig() { sendError(LINK_BLE, 0, "too_big", "message over 16 KiB (BLE)"); }

// ---- the phone's hotspot (11.5) ------------------------------------------------------------------------
static void onWifiDisconnected(WiFiEvent_t, WiFiEventInfo_t info) {
  int r = info.wifi_sta_disconnected.reason;
  if (r != WIFI_REASON_ASSOC_LEAVE) lastWifiReason = r;  // 8 = we left on purpose
}

static void startHomeWifi() {
  homeWifiStarted = false;
  if (!gSettings.ssid[0]) return;
  WiFi.mode(provisionPortalActive() ? WIFI_AP_STA : WIFI_STA);
  WiFi.setSleep(true);  // modem sleep is REQUIRED while Bluetooth runs (ESP-IDF coexistence aborts otherwise)
  WiFi.begin(gSettings.ssid, gSettings.pass);
  homeWifiStarted = true;
  logf("net: joining Wi-Fi '%s'", gSettings.ssid);
}

static void returnHome(const char* why) {
  logf("net: back to the home Wi-Fi (%s)", why);
  handoverStop(wm == WM_HS_JOINED);  // tell the camera board to go home too (on the hotspot's channel)
  wsStop();
  wipe(&hs, sizeof hs);
  wm = WM_HOME;
  WiFi.disconnect();
  startHomeWifi();
  backoff = 0;
  nextConnectMs = millis();
  robotLinkDirty = true;
}

static void startHotspotJoin() {
  const bool wasJoined = wm == WM_HS_JOINED;
  handoverStop(wasJoined);  // an older hotspot session ends first (kind 2 while still on its channel)
  wsStop();
  wipe(&hs, sizeof hs);
  portENTER_CRITICAL(&hsMux);
  hs = hsReq;
  wipe(&hsReq, sizeof hsReq);
  hsJoinReq = false;
  portEXIT_CRITICAL(&hsMux);
  uint8_t sid[8];
  esp_fill_random(sid, sizeof sid);
  for (int i = 0; i < 8; i++) snprintf(hs.sid + 2 * i, 3, "%02x", sid[i]);
  provisionStopPortal();  // the owner's phone is here: no open setup access point next to the hotspot
  WiFi.disconnect();
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(true);
  lastWifiReason = 0;
  WiFi.begin(hs.ssid, hs.pass);  // WiFi.persistent(false): the ESP-IDF keeps it in RAM only, never in flash
  wm = WM_HS_JOINING;
  hsJoinStartMs = millis();
  robotLinkDirty = true;
  logf("net: joining the phone's hotspot '%s'", hs.ssid);
  netSend("hotspot_state", "\"state\":\"joining\"");
}

static void hotspotLoop(uint32_t now) {
  if (hsLeaveReq) {
    hsLeaveReq = false;
    netSend("hotspot_state", "\"state\":\"left\"");
    if (wm != WM_HOME) returnHome("the phone left");
    return;
  }
  if (hsJoinReq) { startHotspotJoin(); return; }
  if (wm == WM_HS_JOINING) {
    if (WiFi.status() == WL_CONNECTED) {
      wm = WM_HS_JOINED;
      hsLastGoodMs = now;
      backoff = 0;
      nextConnectMs = now;
      char f[64];
      snprintf(f, sizeof f, "\"state\":\"joined\",\"ip\":\"%s\"", WiFi.localIP().toString().c_str());
      netSend("hotspot_state", f);
      logf("net: on the phone's hotspot (channel %d), brain link next", WiFi.channel());
      handoverStart(hs.ssid, hs.pass, hs.port, hs.token, hs.host, hs.sid);
      robotLinkDirty = true;
    } else if (now - hsJoinStartMs > HOTSPOT_JOIN_TIMEOUT_MS) {
      const char* reason = spike::link::hotspotFailReason(lastWifiReason);
      char f[64];
      snprintf(f, sizeof f, "\"state\":\"failed\",\"reason\":\"%s\"", reason);
      netSend("hotspot_state", f);
      returnHome(reason);
    }
  } else if (wm == WM_HS_JOINED) {
    if (L[LINK_WS].open && L[LINK_WS].helloDone && wsToHotspot) hsLastGoodMs = now;
    if (now - hsLastGoodMs > HOTSPOT_DEAD_MS && !bleConnected()) returnHome("hotspot link dead for 60 s and no phone on BLE");
  }
}

// ---- robot_link (11.4): over BLE on connect and whenever it changes ----------------------------------
static void robotLinkLoop(uint32_t now) {
  static char last[160];
  static uint32_t lastCheck = 0;
  if (!L[LINK_BLE].open || !L[LINK_BLE].helloDone) { last[0] = 0; return; }  // after the phone's hello
  if (!robotLinkDirty && now - lastCheck < 250) return;
  lastCheck = now;
  bool up = WiFi.status() == WL_CONNECTED;
  const char* wifi = !up ? "off" : (wm == WM_HOME ? "home" : (wm == WM_HS_JOINED ? "hotspot" : "off"));
  char f[160];
  snprintf(f, sizeof f, "\"brain\":\"%s\",\"wifi\":\"%s\",\"ip\":\"%s\",\"camera\":%s", netBrainName(), wifi,
           up ? WiFi.localIP().toString().c_str() : "", handoverCameraOnline() ? "true" : "false");
  if (!robotLinkDirty && !strcmp(f, last)) return;
  if (netSendOn(LINK_BLE, "robot_link", f)) {
    strcpy(last, f);
    robotLinkDirty = false;
  }
}

// ---- setup and loop -------------------------------------------------------------------------------------
void netBegin() {
  sendLock[LINK_WS] = xSemaphoreCreateMutex();
  sendLock[LINK_BLE] = xSemaphoreCreateMutex();
  handleLock = xSemaphoreCreateMutex();
  rxBuf = (char*)heap_caps_malloc(WS_MAX_MESSAGE + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  WiFi.persistent(false);  // nothing Wi-Fi goes to flash through the ESP-IDF (our own NVS has the home Wi-Fi)
  WiFi.setHostname(deviceId());
  WiFi.onEvent(onWifiDisconnected, ARDUINO_EVENT_WIFI_STA_DISCONNECTED);
  bleBegin();       // the phone link (advertises whenever no phone is connected)
  linkKeyEnsure();  // after the radio is on, so the hardware RNG is fully seeded
  if (gSettings.ssid[0]) startHomeWifi();
  else logf("net: no Wi-Fi saved -- Spike runs on his own; setup portal, serial console and the phone (BLE) are available");
}

void netLoop() {
  uint32_t now = millis();
  bleLoop();
  hotspotLoop(now);
  handoverLoop();
  robotLinkLoop(now);

  // BLE dead-link rules (section 3 over BLE, 11.3): the phone (central) reconnects, Spike keeps advertising
  LinkState& b = L[LINK_BLE];
  if (b.open && b.helloDone && olderThan(b.lastRxMs, (uint32_t)(3 * b.heartbeatS * 1000))) bleDisconnect("no message for 3 heartbeats");
  else if (b.open && !b.helloDone && olderThan(b.helloSentMs, BLE_HELLO_TIMEOUT_MS)) bleDisconnect("no hello from the phone brain");

  // the WebSocket: the laptop on the home Wi-Fi, or the phone on its hotspot
  const bool toHotspot = wm == WM_HS_JOINED;
  if (wm == WM_HS_JOINING) return;
  if (!toHotspot && (!homeWifiStarted || !gSettings.host[0])) return;
  if (WiFi.status() != WL_CONNECTED) {
    if (ws) wsStop();
    return;
  }
  if (ws && wsToHotspot != toHotspot) wsStop();  // the network changed under the link
  if (!ws) {
    if ((int32_t)(now - nextConnectMs) >= 0) {
      logf("net: Wi-Fi up (%s), connecting to the %s", WiFi.localIP().toString().c_str(), toHotspot ? "phone brain" : "laptop brain");
      wsStart(toHotspot);
      connectStartMs = now;
    }
    return;
  }
  LinkState& w = L[LINK_WS];
  bool dead = false;
  if (w.open && w.helloDone && olderThan(w.lastRxMs, (uint32_t)(3 * w.heartbeatS * 1000))) { logf("net: no message for 3 heartbeats"); dead = true; }
  if (w.open && !w.helloDone && olderThan(w.helloSentMs, 6000)) { logf("net: no hello reply"); dead = true; }
  if (!w.open && now - connectStartMs > 6000) dead = true;  // the connect attempt failed or the link dropped
  if (dead) {
    wsStop();
    nextConnectMs = now + backoffMs();
  }
}

void netConsoleStatus() {
  const char* mode = wm == WM_HOME ? "home" : (wm == WM_HS_JOINING ? "joining the phone's hotspot" : "phone's hotspot");
  logf("links: brain %s | Wi-Fi %s %s | WebSocket %s | BLE %s | camera on hotspot %s", netBrainName(), mode,
       WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "(not joined)",
       L[LINK_WS].open ? (L[LINK_WS].helloDone ? "linked" : "saying hello") : "down",
       L[LINK_BLE].open ? (L[LINK_BLE].helloDone ? "phone brain linked" : "saying hello") : (bleConnected() ? "paired, not subscribed" : "no phone"),
       handoverCameraOnline() ? "yes" : "no");
}
