// cam_main.cpp -- Spike's camera board: OV5640 JPEG frames to the brain (protocol 6.8).
//   * frame size, frame rate and JPEG quality are settings (serial `cam ...`), default 320 x 240 at 5 fps
//   * never more than 10 fps, never a JPEG over 46 KiB (it raises the compression and drops that frame)
//   * frames exist only in memory; nothing is stored (privacy, protocol 6.8)
//   * setup like the screen board: serial console `help`, or the "Spike-Cam-Setup-xxxxxx" portal
//   * wireless updates (ArduinoOTA) once an update password is set (home Wi-Fi only)
//   * away from home it follows Spike to the phone's hotspot (cam_away.cpp, protocol v1.3 11.6)
#include "cam.h"
#include <esp_camera.h>
#include <esp_task_wdt.h>
#include <esp_mac.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ArduinoOTA.h>
#include <mbedtls/base64.h>
#include <esp_heap_caps.h>

#if ARDUINO_USB_MODE && !ARDUINO_USB_CDC_ON_BOOT
#include <HWCDC.h>
extern HWCDC USBSerial;
#define HAVE_USB 1
#endif

CamSettings cs;
static bool camOk = false;
static char* b64;           // base64 of one frame + the JSON fields
static size_t b64Cap;
static uint32_t seq = 0, sentFrames = 0, dropped = 0, lastStat = 0;

void logf(const char* fmt, ...) {
  char buf[256];
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(buf, sizeof buf - 2, fmt, ap);
  va_end(ap);
  if (n < 0) return;
  if (n > (int)sizeof buf - 3) n = sizeof buf - 3;
  buf[n++] = '\r';
  buf[n++] = '\n';
  Serial.write((const uint8_t*)buf, n);
#ifdef HAVE_USB
  if (USBSerial) USBSerial.write((const uint8_t*)buf, n);
#endif
}

const char* deviceId() {
  static char id[24] = {0};
  if (!id[0]) {
    uint8_t mac[6];
    esp_efuse_mac_get_default(mac);
    snprintf(id, sizeof id, "spikecam-%02x%02x%02x", mac[3], mac[4], mac[5]);
  }
  return id;
}

// ---- settings --------------------------------------------------------------------------------
static Preferences prefs;
static void getStr(const char* k, char* o, size_t n) { String s = prefs.getString(k, ""); strncpy(o, s.c_str(), n - 1); o[n - 1] = 0; }
void settingsLoad() {
  prefs.begin("spikecam", true);
  getStr("ssid", cs.ssid, sizeof cs.ssid);
  getStr("pass", cs.pass, sizeof cs.pass);
  getStr("host", cs.host, sizeof cs.host);
  getStr("token", cs.token, sizeof cs.token);
  getStr("ota", cs.otaPass, sizeof cs.otaPass);
  getStr("robot", cs.robotId, sizeof cs.robotId);
  cs.port = prefs.getUShort("port", BRAIN_DEFAULT_PORT);
  cs.frameSize = prefs.getUChar("size", FRAMESIZE_QVGA);
  cs.fps = prefs.getUChar("fps", 5);
  cs.quality = prefs.getUChar("q", 12);
  cs.vflip = prefs.getBool("vflip", false);
  cs.hmirror = prefs.getBool("hmirror", false);
  prefs.end();
  if (cs.fps < 1 || cs.fps > 10) cs.fps = 5;
  if (cs.quality < 6 || cs.quality > 40) cs.quality = 12;
  if (cs.frameSize < FRAMESIZE_QQVGA || cs.frameSize > FRAMESIZE_VGA) cs.frameSize = FRAMESIZE_QVGA;
}
void settingsSave() {
  prefs.begin("spikecam", false);
  prefs.putString("ssid", cs.ssid);
  prefs.putString("pass", cs.pass);
  prefs.putString("host", cs.host);
  prefs.putString("token", cs.token);
  prefs.putString("ota", cs.otaPass);
  prefs.putString("robot", cs.robotId);
  prefs.putUShort("port", cs.port);
  prefs.putUChar("size", cs.frameSize);
  prefs.putUChar("fps", cs.fps);
  prefs.putUChar("q", cs.quality);
  prefs.putBool("vflip", cs.vflip);
  prefs.putBool("hmirror", cs.hmirror);
  prefs.end();
}

// ---- camera ----------------------------------------------------------------------------------
static bool cameraBegin() {
  camera_config_t c = {};
  c.pin_pwdn = CAM_PIN_PWDN; c.pin_reset = CAM_PIN_RESET; c.pin_xclk = CAM_PIN_XCLK;
  c.pin_sccb_sda = CAM_PIN_SIOD; c.pin_sccb_scl = CAM_PIN_SIOC;
  c.pin_d7 = CAM_PIN_D7; c.pin_d6 = CAM_PIN_D6; c.pin_d5 = CAM_PIN_D5; c.pin_d4 = CAM_PIN_D4;
  c.pin_d3 = CAM_PIN_D3; c.pin_d2 = CAM_PIN_D2; c.pin_d1 = CAM_PIN_D1; c.pin_d0 = CAM_PIN_D0;
  c.pin_vsync = CAM_PIN_VSYNC; c.pin_href = CAM_PIN_HREF; c.pin_pclk = CAM_PIN_PCLK;
  c.xclk_freq_hz = 20000000;
  c.ledc_timer = LEDC_TIMER_0;
  c.ledc_channel = LEDC_CHANNEL_0;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = (framesize_t)cs.frameSize;
  c.jpeg_quality = cs.quality;
  c.fb_count = 2;
  c.fb_location = CAMERA_FB_IN_PSRAM;
  c.grab_mode = CAMERA_GRAB_LATEST;  // always the newest frame, never a stale queue
  esp_err_t e = esp_camera_init(&c);
  if (e != ESP_OK) { logf("camera: init failed 0x%x -- check the pin map in cam.h against the seller's sheet", e); return false; }
  sensor_t* s = esp_camera_sensor_get();
  // Cheap copies can report the wrong chip id (BOM 2e): log it, but carry on.
  logf("camera: sensor PID 0x%04X (OV5640 = 0x5640), %s", s ? s->id.PID : 0, s && s->id.PID == OV5640_PID ? "OV5640" : "not an OV5640 id");
  if (s) { s->set_vflip(s, cs.vflip); s->set_hmirror(s, cs.hmirror); }
  return true;
}

static void sendFrame() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) { dropped++; return; }
  if (fb->len > JPEG_MAX_BYTES) {  // too big for the protocol: compress harder from the next frame
    esp_camera_fb_return(fb);
    dropped++;
    sensor_t* s = esp_camera_sensor_get();
    if (s && cs.quality < 40) { cs.quality += 2; s->set_quality(s, cs.quality); logf("camera: frame over 46 KiB, JPEG quality -> %d", cs.quality); }
    return;
  }
  const size_t head = 96;
  size_t olen = 0;
  if (mbedtls_base64_encode((unsigned char*)b64 + head, b64Cap - head - 4, &olen, fb->buf, fb->len) != 0) {
    esp_camera_fb_return(fb);
    dropped++;
    return;
  }
  int w = fb->width, h = fb->height;
  esp_camera_fb_return(fb);
  b64[head + olen] = 0;
  char pre[head];
  int pn = snprintf(pre, sizeof pre, "\"seq\":%lu,\"format\":\"jpeg\",\"width\":%d,\"height\":%d,\"data\":\"", (unsigned long)++seq, w, h);
  char* start = b64 + head - pn;
  memcpy(start, pre, pn);
  b64[head + olen] = '"';
  b64[head + olen + 1] = 0;
  if (netSend("camera", start)) sentFrames++; else dropped++;
}

// ---- console + setup portal ----------------------------------------------------------------
static WebServer* web;
static DNSServer* dns;
static bool portal = false;
static uint32_t portalStart = 0, bootMs = 0;
static bool triedPortal = false;

bool portalActive() { return portal; }

static void page() {
  String h = F("<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'><title>Spike camera setup</title>"
               "<style>body{font-family:sans-serif;max-width:420px;margin:20px auto;padding:0 12px}label{display:block;margin-top:12px}"
               "input{width:100%;padding:8px;font-size:16px}button{margin-top:18px;padding:10px 20px;font-size:16px}</style></head><body>"
               "<h2>Spike camera setup</h2><form method=post action=/save>");
  h += "<label>Home Wi-Fi name (2.4 GHz)<input name=ssid value=\"" + String(cs.ssid) + "\"></label>";
  h += F("<label>Wi-Fi password<input name=pass type=password></label>");
  h += "<label>Laptop brain address (IP)<input name=host value=\"" + String(cs.host) + "\"></label>";
  h += "<label>Brain port<input name=port value=\"" + String(cs.port) + "\"></label>";
  h += F("<label>Pairing token<input name=token type=password></label>");
  h += "<label>Robot id (the screen board's device id, e.g. spike-1a2b3c)<input name=robot value=\"" + String(cs.robotId) + "\"></label>";
  h += F("<label>Update password (optional)<input name=ota type=password></label><button>Save and restart</button></form></body></html>");
  web->send(200, "text/html", h);
}

static void save() {
  auto cp = [](const char* n, char* o, size_t sz, bool keep) { String v = web->arg(n); if (keep && !v.length()) return; strncpy(o, v.c_str(), sz - 1); o[sz - 1] = 0; };
  cp("ssid", cs.ssid, sizeof cs.ssid, false);
  cp("pass", cs.pass, sizeof cs.pass, true);
  cp("host", cs.host, sizeof cs.host, false);
  cp("token", cs.token, sizeof cs.token, true);
  cp("robot", cs.robotId, sizeof cs.robotId, false);
  cp("ota", cs.otaPass, sizeof cs.otaPass, true);
  int p = web->arg("port").toInt();
  cs.port = p > 0 && p < 65536 ? p : BRAIN_DEFAULT_PORT;
  settingsSave();
  web->send(200, "text/html", F("<html><body><h2>Saved. The camera restarts now.</h2></body></html>"));
  delay(800);
  ESP.restart();
}

static void startPortal() {
  if (portal) return;
  char ap[40];
  snprintf(ap, sizeof ap, "Spike-Cam-Setup-%s", deviceId() + 9);
  WiFi.mode(cs.ssid[0] ? WIFI_AP_STA : WIFI_AP);
  WiFi.softAP(ap);
  dns = new DNSServer();
  dns->start(53, "*", WiFi.softAPIP());
  web = new WebServer(80);
  web->on("/", HTTP_GET, page);
  web->on("/save", HTTP_POST, save);
  web->onNotFound(page);
  web->begin();
  portal = true;
  portalStart = millis();
  logf("setup: portal open -- join '%s' and open http://%s", ap, WiFi.softAPIP().toString().c_str());
}

static void command(char* line) {
  char* a[5] = {0};
  int n = 0;
  for (char* p = line; *p && n < 5;) {
    while (*p == ' ') p++;
    if (!*p) break;
    if (*p == '"') { a[n++] = ++p; while (*p && *p != '"') p++; }
    else { a[n++] = p; while (*p && *p != ' ') p++; }
    if (*p) *p++ = 0;
  }
  if (!n) return;
  if (!strcmp(a[0], "help")) {
    logf("status | wifi \"<name>\" \"<password>\" | brain <ip> [port] | token <t> | robot <screen-board-id>");
    logf("cam <qqvga|qvga|vga> <fps 1-10> <quality 6-40> | flip <0|1> <0|1> | otapass <p> | setup | reboot | factory-reset");
    logf("linkkey <64 hex> (from the screen board's 'linkkey') | linkkey | linkkey forget");
  } else if (!strcmp(a[0], "status")) {
    logf("%s fw %s | Wi-Fi '%s' %s | brain %s:%u %s | robot id %s | camera %s, %d fps, q %d | sent %lu dropped %lu", deviceId(),
         SPIKE_FW_VERSION, cs.ssid, WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "not connected", cs.host,
         cs.port, netConnected() ? "linked" : "not linked", cs.robotId[0] ? cs.robotId : "(own id)", camOk ? "ok" : "FAILED",
         cs.fps, cs.quality, (unsigned long)sentFrames, (unsigned long)dropped);
    logf("away: %s | link key %s", awayModeName(), awayLinkKeySet() ? "set" : "not set");
  } else if (!strcmp(a[0], "linkkey")) {
    awayLinkKeyCommand(n >= 2 ? a[1] : "");
  } else if (!strcmp(a[0], "wifi") && n >= 2) { strncpy(cs.ssid, a[1], sizeof cs.ssid - 1); strncpy(cs.pass, n >= 3 ? a[2] : "", sizeof cs.pass - 1); settingsSave(); logf("saved; reboot to use it"); }
  else if (!strcmp(a[0], "brain") && n >= 2) { strncpy(cs.host, a[1], sizeof cs.host - 1); cs.port = n >= 3 ? atoi(a[2]) : BRAIN_DEFAULT_PORT; settingsSave(); logf("saved; reboot to use it"); }
  else if (!strcmp(a[0], "token") && n >= 2) { strncpy(cs.token, a[1], sizeof cs.token - 1); settingsSave(); logf("saved"); }
  else if (!strcmp(a[0], "robot") && n >= 2) { strncpy(cs.robotId, a[1], sizeof cs.robotId - 1); settingsSave(); logf("saved; reboot to use it"); }
  else if (!strcmp(a[0], "otapass") && n >= 2) { strncpy(cs.otaPass, a[1], sizeof cs.otaPass - 1); settingsSave(); logf("saved; reboot to enable updates"); }
  else if (!strcmp(a[0], "cam") && n >= 4) {
    cs.frameSize = !strcmp(a[1], "vga") ? FRAMESIZE_VGA : (!strcmp(a[1], "qqvga") ? FRAMESIZE_QQVGA : FRAMESIZE_QVGA);
    int f = atoi(a[2]), q = atoi(a[3]);
    cs.fps = f < 1 ? 1 : (f > 10 ? 10 : f);
    cs.quality = q < 6 ? 6 : (q > 40 ? 40 : q);
    settingsSave();
    logf("saved camera %s %d fps quality %d; reboot to use it", a[1], cs.fps, cs.quality);
  } else if (!strcmp(a[0], "flip") && n >= 3) { cs.vflip = atoi(a[1]); cs.hmirror = atoi(a[2]); settingsSave(); logf("saved; reboot to use it"); }
  else if (!strcmp(a[0], "setup")) startPortal();
  else if (!strcmp(a[0], "reboot")) ESP.restart();
  else if (!strcmp(a[0], "factory-reset")) { prefs.begin("spikecam", false); prefs.clear(); prefs.end(); ESP.restart(); }
  else logf("unknown command -- type help");
}

static char lineBuf[200];
static int lineLen = 0;
static void feed(int ch) {
  if (ch == '\r' || ch == '\n') { if (lineLen) { lineBuf[lineLen] = 0; command(lineBuf); lineLen = 0; } }
  else if (lineLen < (int)sizeof lineBuf - 1) lineBuf[lineLen++] = (char)ch;
}

static bool otaStarted = false;
static void otaLoop() {
  if (awayHotspot()) return;  // no wireless updates on the phone's hotspot
  if (!otaStarted) {
    if (!cs.otaPass[0] || WiFi.status() != WL_CONNECTED) return;
    ArduinoOTA.setHostname(deviceId());
    ArduinoOTA.setPassword(cs.otaPass);
    ArduinoOTA.begin();
    otaStarted = true;
    logf("ota: ready as %s.local", deviceId());
  }
  ArduinoOTA.handle();
}

void setup() {
  Serial.begin(115200);
  delay(200);
  logf("\nSpike camera board firmware %s", SPIKE_FW_VERSION);
  esp_task_wdt_init(8, true);
  esp_task_wdt_add(nullptr);
  settingsLoad();
  if (!psramFound()) logf("WARNING: no PSRAM -- the camera needs it (board settings: OPI PSRAM)");
  b64Cap = (JPEG_MAX_BYTES + 2) / 3 * 4 + 256;
  b64 = (char*)heap_caps_malloc(b64Cap, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  camOk = cameraBegin();
  netBegin();
  awayBegin();
  bootMs = millis();
  if (!cs.ssid[0] || !cs.host[0]) { startPortal(); triedPortal = true; }
  logf("device %s ready -- type help", deviceId());
}

void loop() {
  esp_task_wdt_reset();
  while (Serial.available()) feed(Serial.read());
#ifdef HAVE_USB
  while (USBSerial.available()) feed(USBSerial.read());
#endif
  awayLoop();
  netLoop();
  otaLoop();
  // The setup portal opens by itself when the home Wi-Fi fails -- but not once a link key is set: then
  // the camera is set up, and away from home it must be free to hop channels for the hand-over.
  if (!triedPortal && !awayLinkKeySet() && WiFi.status() != WL_CONNECTED && millis() - bootMs > 60000) { startPortal(); triedPortal = true; }
  if (portal) {
    dns->processNextRequest();
    web->handleClient();
    if (millis() - portalStart > 15UL * 60 * 1000) { web->stop(); dns->stop(); WiFi.softAPdisconnect(true); portal = false; }
  }
  static uint32_t nextFrame = 0;
  uint32_t now = millis();
  if (camOk && netConnected() && (int32_t)(now - nextFrame) >= 0) {
    nextFrame = now + 1000 / cs.fps;
    sendFrame();
  }
  if (now - lastStat > 30000) {
    lastStat = now;
    if (netConnected()) logf("camera: %lu frames sent, %lu dropped", (unsigned long)sentFrames, (unsigned long)dropped);
  }
  delay(2);
}
