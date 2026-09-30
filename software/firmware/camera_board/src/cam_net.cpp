// cam_net.cpp -- the camera board's brain link: WebSocket client, role "camera", PROTOCOL.md v1.3
// (hello within 5 s, pong to ping, 3 x heartbeat dead-link rule, 0.5..10 s backoff with jitter).
// The camera only sends `camera` frames; every other brain message is ignored (rule 2).
// The link goes to the laptop brain on the home Wi-Fi, or -- away from home (11.6, cam_away.cpp) -- to
// the phone brain on its hotspot, with the one-time hotspot token and "link":"hotspot" in the hello.
#include "cam.h"
#include <WiFi.h>
#include <ArduinoJson.h>
#include <esp_websocket_client.h>
#include <esp_heap_caps.h>
#include "spike_link_policy.h"

static esp_websocket_client_handle_t ws;
static SemaphoreHandle_t sendLock;
static volatile bool wsOpen = false, helloDone = false;
static uint32_t outId = 0;
static volatile uint32_t lastRxMs = 0;
static float heartbeatS = 5;
static char* rxBuf;
static size_t rxLen = 0;
static int backoff = 0;
static uint32_t nextConnectMs = 0, connectStartMs = 0, helloSentMs = 0;
static const size_t RXMAX = 8 * 1024;  // the camera never needs big inbound messages
static bool wsToHotspot = false;

bool netConnected() { return wsOpen && helloDone; }

bool netSend(const char* type, const char* fields) {
  if (!ws || !wsOpen) return false;
  if (!helloDone && strcmp(type, "hello") && strcmp(type, "pong")) return false;
  size_t flen = fields ? strlen(fields) : 0, cap = flen + 128;
  char* buf = (char*)heap_caps_malloc(cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!buf) return false;
  xSemaphoreTake(sendLock, portMAX_DELAY);
  outId = outId == 0xFFFFFFFFu ? 1 : outId + 1;
  int n = snprintf(buf, cap, "{\"v\":1,\"type\":\"%s\",\"id\":%lu,\"ts\":%lu%s%s}", type, (unsigned long)outId,
                   (unsigned long)millis(), flen ? "," : "", flen ? fields : "");
  int r = (n > 0 && (size_t)n < cap) ? esp_websocket_client_send_text(ws, buf, n, pdMS_TO_TICKS(2000)) : -1;
  xSemaphoreGive(sendLock);
  heap_caps_free(buf);
  return r >= 0;
}

static void sendHello() {
  char f[320];
  char tok[132];
  const char* id = cs.robotId[0] ? cs.robotId : deviceId();
  const AwayHotspot* h = wsToHotspot ? awayHotspot() : nullptr;
  const char* t = h ? h->token : cs.token;
  int n = snprintf(f, sizeof f, "\"role\":\"camera\",\"device_id\":\"%s\",\"fw\":\"%s\",\"caps\":[\"camera\"]", id, SPIKE_FW_VERSION);
  if (t[0] && spike::link::jsonEscape(t, tok, sizeof tok) && n > 0 && n < (int)sizeof f - 150)
    n += snprintf(f + n, sizeof f - n, ",\"token\":\"%s\"", tok);
  if (h && n > 0 && n < (int)sizeof f - 20) snprintf(f + n, sizeof f - n, ",\"link\":\"hotspot\"");
  helloSentMs = millis();
  netSend("hello", f);
}

static void handle(const char* text, size_t len) {
  JsonDocument doc;
  if (deserializeJson(doc, text, len)) return;
  long id = doc["id"] | 0L;
  if ((doc["v"] | -1) != 1) {
    char f[96];
    snprintf(f, sizeof f, "\"re\":%ld,\"code\":\"version_mismatch\",\"message\":\"robot speaks v1\"", id);
    netSend("error", f);
    return;
  }
  const char* type = doc["type"] | "";
  if (!strcmp(type, "hello")) {
    helloDone = true;
    backoff = 0;
    heartbeatS = doc["heartbeat_s"] | 5.0f;
    if (heartbeatS < 1) heartbeatS = 1;
    logf("net: brain hello, heartbeat %.1f s", heartbeatS);
  } else if (helloDone && !strcmp(type, "ping")) {
    char f[32];
    snprintf(f, sizeof f, "\"re\":%ld", id);
    netSend("pong", f);
  } else if (!strcmp(type, "error")) {
    logf("net: brain error %s: %s", doc["code"] | "?", doc["message"] | "");
  }
}

static void wsEvent(void*, esp_event_base_t, int32_t eventId, void* data) {
  esp_websocket_event_data_t* d = (esp_websocket_event_data_t*)data;
  if (eventId == WEBSOCKET_EVENT_CONNECTED) {
    helloDone = false;
    lastRxMs = millis();
    outId = 0;  // ids start at 1 on every connection
    helloSentMs = millis();
    wsOpen = true;
    logf("net: connected to the %s", wsToHotspot ? "phone brain on its hotspot" : "laptop brain");
    sendHello();
  } else if (eventId == WEBSOCKET_EVENT_DISCONNECTED || eventId == WEBSOCKET_EVENT_CLOSED) {
    wsOpen = false;
    helloDone = false;
  } else if (eventId == WEBSOCKET_EVENT_DATA) {
    lastRxMs = millis();
    if (d->op_code != 0x01 && d->op_code != 0x00) return;
    if (d->payload_offset == 0) rxLen = 0;
    if (rxLen + d->data_len > RXMAX) { rxLen = RXMAX + 1; return; }  // too big for us: ignore it
    memcpy(rxBuf + rxLen, d->data_ptr, d->data_len);
    rxLen += d->data_len;
    if (d->payload_offset + d->data_len >= d->payload_len && rxLen <= RXMAX) { handle(rxBuf, rxLen); rxLen = 0; }
  }
}

static void wsStop() {
  if (!ws) return;
  esp_websocket_client_stop(ws);
  esp_websocket_client_destroy(ws);
  ws = nullptr;
  wsOpen = false;
  helloDone = false;
}

static void wsStart(const AwayHotspot* h) {
  static char uri[96];
  if (h) {
    String gw = WiFi.gatewayIP().toString();
    snprintf(uri, sizeof uri, "ws://%s:%u/", h->host[0] ? h->host : gw.c_str(), h->port);
  } else {
    snprintf(uri, sizeof uri, "ws://%s:%u/", cs.host, cs.port);
  }
  wsToHotspot = h != nullptr;
  esp_websocket_client_config_t cfg = {};
  cfg.uri = uri;
  cfg.buffer_size = 4096;
  cfg.task_stack = 6144;
  cfg.disable_auto_reconnect = true;
  cfg.ping_interval_sec = 5;
  cfg.pingpong_timeout_sec = 20;
  ws = esp_websocket_client_init(&cfg);
  if (!ws) return;
  esp_websocket_register_events(ws, WEBSOCKET_EVENT_ANY, wsEvent, nullptr);
  esp_websocket_client_start(ws);
}

static uint32_t backoffMs() {
  float base = 0.5f * (float)(1 << (backoff < 5 ? backoff : 5));
  if (base > 10) base = 10;
  backoff++;
  return (uint32_t)(base * (0.8f + 0.4f * (esp_random() % 1000) / 1000.0f) * 1000);
}

void netBegin() {
  sendLock = xSemaphoreCreateMutex();
  rxBuf = (char*)heap_caps_malloc(RXMAX + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  WiFi.persistent(false);
  WiFi.setHostname(deviceId());
  if (!cs.ssid[0]) { logf("net: no Wi-Fi saved -- use the serial console or the setup portal"); return; }
  WiFi.mode(WIFI_STA);
  WiFi.begin(cs.ssid, cs.pass);
  WiFi.setSleep(false);
  logf("net: joining Wi-Fi '%s'", cs.ssid);
}

void netRestart() {
  wsStop();
  backoff = 0;
  nextConnectMs = millis();
}

void netLoop() {
  uint32_t now = millis();
  const AwayHotspot* h = awayHotspot();
  if (!h && (!cs.ssid[0] || !cs.host[0])) { if (ws) wsStop(); return; }
  if (WiFi.status() != WL_CONNECTED) { if (ws) wsStop(); return; }
  if (ws && wsToHotspot != (h != nullptr)) wsStop();  // the network changed under the link
  if (!ws) {
    if ((int32_t)(now - nextConnectMs) >= 0) { wsStart(h); connectStartMs = now; }
    return;
  }
  bool dead = false;
  // signed: the WebSocket task may stamp lastRxMs after `now` was read (unsigned would wrap and kill the link)
  if (wsOpen && helloDone && (int32_t)(millis() - lastRxMs) > (int32_t)(3 * heartbeatS * 1000)) dead = true;
  if (wsOpen && !helloDone && (int32_t)(millis() - helloSentMs) > 6000) dead = true;
  if (!wsOpen && now - connectStartMs > 6000) dead = true;
  if (dead) { wsStop(); nextConnectMs = now + backoffMs(); }
}
