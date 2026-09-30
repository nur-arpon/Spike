// provision.cpp -- how Spike learns the home Wi-Fi, the brain's address and the pairing token.
//
// Two paths (both write the same NVS settings):
//  1. Serial console (USB cable, 115200 baud): type `help`. Always available.
//  2. Setup portal: when no Wi-Fi is saved, or the saved one fails for 60 s after boot, Spike opens
//     an open access point "Spike-Setup-xxxxxx" for 15 minutes. Join it with a phone; the page opens
//     by itself (captive portal) or browse to http://192.168.4.1 . Fill in the form, press Save.
// The portal never starts while Spike is connected, and it closes after 15 minutes.
#include "app.h"
#include "config.h"
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>

void bodyConsole(const char* line);  // body_hw.cpp: servo calibration commands
void otaReconfigure();

static WebServer* web;
static DNSServer* dns;
static bool portal = false;
static uint32_t portalStart = 0;
static uint32_t bootMs = 0;
static bool triedPortal = false;

bool provisionPortalActive() { return portal; }
static void stopPortal();
void provisionStopPortal() { stopPortal(); }

static String esc(const char* s) {
  String o;
  for (; *s; s++) {
    if (*s == '<') o += "&lt;"; else if (*s == '>') o += "&gt;"; else if (*s == '"') o += "&quot;"; else if (*s == '&') o += "&amp;";
    else o += *s;
  }
  return o;
}

static void page() {
  String h = F("<!doctype html><html><head><meta name=viewport content='width=device-width,initial-scale=1'>"
               "<title>Spike setup</title><style>body{font-family:sans-serif;max-width:420px;margin:20px auto;padding:0 12px}"
               "label{display:block;margin-top:12px}input{width:100%;padding:8px;font-size:16px}"
               "button{margin-top:18px;padding:10px 20px;font-size:16px}</style></head><body><h2>Spike setup</h2>"
               "<form method=post action=/save>");
  h += "<label>Home Wi-Fi name (2.4 GHz)<input name=ssid value=\"" + esc(gSettings.ssid) + "\"></label>";
  h += F("<label>Wi-Fi password<input name=pass type=password></label>");
  h += "<label>Laptop brain address (IP)<input name=host value=\"" + esc(gSettings.host) + "\"></label>";
  h += "<label>Brain port<input name=port value=\"" + String(gSettings.port) + "\"></label>";
  h += F("<label>Pairing token (from the brain's .env SPIKE_TOKEN)<input name=token type=password></label>"
         "<label>Update password (for wireless updates, optional)<input name=ota type=password></label>"
         "<button>Save and restart</button></form><p>Device ");
  h += deviceId();
  h += F("</p></body></html>");
  web->send(200, "text/html", h);
}

static void copyArg(const char* name, char* out, size_t n, bool keepIfEmpty) {
  String v = web->arg(name);
  if (keepIfEmpty && v.length() == 0) return;
  strncpy(out, v.c_str(), n - 1);
  out[n - 1] = 0;
}

static void save() {
  copyArg("ssid", gSettings.ssid, sizeof gSettings.ssid, false);
  copyArg("pass", gSettings.pass, sizeof gSettings.pass, true);
  copyArg("host", gSettings.host, sizeof gSettings.host, false);
  int port = web->arg("port").toInt();
  gSettings.port = port > 0 && port < 65536 ? (uint16_t)port : BRAIN_DEFAULT_PORT;
  copyArg("token", gSettings.token, sizeof gSettings.token, true);
  copyArg("ota", gSettings.otaPass, sizeof gSettings.otaPass, true);
  settingsSave();
  web->send(200, "text/html", F("<html><body><h2>Saved. Spike restarts now.</h2></body></html>"));
  logf("setup: saved Wi-Fi '%s', brain %s:%u -- restarting", gSettings.ssid, gSettings.host, gSettings.port);
  delay(800);
  ESP.restart();
}

static void startPortal() {
  if (portal) return;
  char ap[40];
  snprintf(ap, sizeof ap, SETUP_AP_PREFIX "%s", deviceId() + 6);
  WiFi.mode(gSettings.ssid[0] ? WIFI_AP_STA : WIFI_AP);
  WiFi.softAP(ap);
  dns = new DNSServer();
  dns->start(53, "*", WiFi.softAPIP());
  web = new WebServer(80);
  web->on("/", HTTP_GET, page);
  web->on("/save", HTTP_POST, save);
  web->onNotFound(page);  // captive portal: every URL shows the form
  web->begin();
  portal = true;
  portalStart = millis();
  logf("setup: portal open -- join Wi-Fi '%s' and open http://%s", ap, WiFi.softAPIP().toString().c_str());
}

static void stopPortal() {
  if (!portal) return;
  web->stop();
  dns->stop();
  delete web;
  delete dns;
  web = nullptr;
  dns = nullptr;
  WiFi.softAPdisconnect(true);
  if (gSettings.ssid[0]) WiFi.mode(WIFI_STA);
  portal = false;
  logf("setup: portal closed");
}

// ---- serial console ------------------------------------------------------------------------------
static int tokenize(char* s, char** argv, int maxArgs) {  // splits on spaces, "quoted words" allowed
  int n = 0;
  while (*s && n < maxArgs) {
    while (*s == ' ') s++;
    if (!*s) break;
    if (*s == '"') {
      argv[n++] = ++s;
      while (*s && *s != '"') s++;
    } else {
      argv[n++] = s;
      while (*s && *s != ' ') s++;
    }
    if (*s) *s++ = 0;
  }
  return n;
}

static void help() {
  logf("Spike console. Commands:");
  logf("  status                         what Spike knows (Wi-Fi, brain, battery)");
  logf("  wifi \"<name>\" \"<password>\"     save the home Wi-Fi (2.4 GHz)");
  logf("  brain <laptop-ip> [port]       save the brain address (default port %d)", BRAIN_DEFAULT_PORT);
  logf("  token <pairing-token>          save the brain's pairing token (SPIKE_TOKEN)");
  logf("  otapass <password>             enable wireless updates with this password");
  logf("  volume <0..1>                  speaker volume");
  logf("  setup                          open the setup portal now");
  logf("  ble                            Bluetooth: the phone link and the paired phones");
  logf("  ble forget                     forget every paired phone (they pair again with the passkey)");
  logf("  linkkey                        print this robot's link key (copy it to the camera board once)");
  logf("  servo ...                      servo calibration (type: servo help)");
  logf("  gait ...                       walking, give paw, balance calibration (type: gait help)");
  logf("  reboot | factory-reset");
}

static void command(char* line) {
  char* argv[6];
  int n = tokenize(line, argv, 6);
  if (n == 0) return;
  const char* c = argv[0];
  if (!strcmp(c, "help")) help();
  else if (!strcmp(c, "status")) {
    logf("device %s fw %s | Wi-Fi '%s' %s %s | brain %s:%u %s | battery %.2f V | portal %s", deviceId(), SPIKE_FW_VERSION,
         gSettings.ssid, WiFi.status() == WL_CONNECTED ? "connected" : "not connected",
         WiFi.status() == WL_CONNECTED ? WiFi.localIP().toString().c_str() : "", gSettings.host, gSettings.port,
         netConnected() ? "linked" : "not linked", bodyBatteryVolts(), portal ? "open" : "closed");
    netConsoleStatus();
  } else if (!strcmp(c, "wifi") && n >= 2) {
    strncpy(gSettings.ssid, argv[1], sizeof gSettings.ssid - 1);
    strncpy(gSettings.pass, n >= 3 ? argv[2] : "", sizeof gSettings.pass - 1);
    settingsSave();
    logf("saved Wi-Fi '%s'. Type reboot to use it.", gSettings.ssid);
  } else if (!strcmp(c, "brain") && n >= 2) {
    strncpy(gSettings.host, argv[1], sizeof gSettings.host - 1);
    gSettings.port = n >= 3 ? (uint16_t)atoi(argv[2]) : BRAIN_DEFAULT_PORT;
    settingsSave();
    logf("saved brain %s:%u. Type reboot to use it.", gSettings.host, gSettings.port);
  } else if (!strcmp(c, "token") && n >= 2) {
    strncpy(gSettings.token, argv[1], sizeof gSettings.token - 1);
    settingsSave();
    logf("saved the pairing token.");
  } else if (!strcmp(c, "otapass") && n >= 2) {
    strncpy(gSettings.otaPass, argv[1], sizeof gSettings.otaPass - 1);
    settingsSave();
    otaReconfigure();
    logf("wireless updates enabled.");
  } else if (!strcmp(c, "volume") && n >= 2) {
    float v = atof(argv[1]);
    gSettings.volume = v < 0 ? 0 : (v > 1 ? 1 : v);
    settingsSave();
    audioSetVolume(gSettings.volume);
    logf("volume %.2f", gSettings.volume);
  } else if (!strcmp(c, "setup")) startPortal();
  else if (!strcmp(c, "reboot")) ESP.restart();
  else if (!strcmp(c, "factory-reset")) {
    settingsFactoryReset();
    bleForgetAll();  // a new owner starts with no paired phones (the link key between the boards stays)
    logf("settings erased. Rebooting.");
    delay(300);
    ESP.restart();
  } else if (!strcmp(c, "ble")) bleConsole(n >= 2 ? argv[1] : "");
  else if (!strcmp(c, "linkkey")) linkKeyPrint();
  else if (!strcmp(c, "servo") || !strcmp(c, "gait")) {
    char rest[160] = {0};
    for (int i = 1; i < n; i++) { strncat(rest, argv[i], sizeof rest - strlen(rest) - 2); strcat(rest, " "); }
    if (c[0] == 's') bodyConsole(rest); else gaitConsole(rest);
  } else logf("unknown command '%s' -- type help", c);
}

static char lineBuf[200];
static int lineLen = 0;

static void feed(int ch) {
  if (ch == '\r' || ch == '\n') {
    if (lineLen) { lineBuf[lineLen] = 0; command(lineBuf); lineLen = 0; }
  } else if (lineLen < (int)sizeof lineBuf - 1) lineBuf[lineLen++] = (char)ch;
}

#if ARDUINO_USB_MODE && !ARDUINO_USB_CDC_ON_BOOT
#include <HWCDC.h>
extern HWCDC USBSerial;
#define HAVE_USB_CONSOLE 1
#endif

void provisionBegin() {
  bootMs = millis();
  if (!gSettings.ssid[0] || !gSettings.host[0]) { startPortal(); triedPortal = true; }
  logf("console: type help (115200 baud)");
}

void provisionLoop() {
  while (Serial.available()) feed(Serial.read());
#ifdef HAVE_USB_CONSOLE
  while (USBSerial.available()) feed(USBSerial.read());
#endif
  if (!triedPortal && gSettings.ssid[0] && WiFi.status() != WL_CONNECTED && millis() - bootMs > 60000) {
    logf("setup: Wi-Fi '%s' not reachable after 60 s", gSettings.ssid);
    startPortal();
    triedPortal = true;
  }
  if (portal) {
    dns->processNextRequest();
    web->handleClient();
    if (millis() - portalStart > 15UL * 60 * 1000) stopPortal();
  }
}
