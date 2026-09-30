// settings.cpp -- NVS settings (Preferences) and logging.
#include "app.h"
#include "config.h"
#include <Preferences.h>
#include <esp_mac.h>

#if ARDUINO_USB_MODE && !ARDUINO_USB_CDC_ON_BOOT
#include <HWCDC.h>
extern HWCDC USBSerial;
#define HAVE_USB_LOG 1
#endif

static SemaphoreHandle_t logLock;

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
  buf[n] = 0;
  if (!logLock) logLock = xSemaphoreCreateMutex();
  if (logLock) xSemaphoreTake(logLock, pdMS_TO_TICKS(50));
  Serial.write((const uint8_t*)buf, n);
#ifdef HAVE_USB_LOG
  if (USBSerial) USBSerial.write((const uint8_t*)buf, n);
#endif
  if (logLock) xSemaphoreGive(logLock);
}

Settings gSettings;
static Preferences prefs;

static void getStr(const char* key, char* out, size_t n, const char* def) {
  String s = prefs.getString(key, def);
  strncpy(out, s.c_str(), n - 1);
  out[n - 1] = 0;
}

void settingsLoad() {
  prefs.begin("spike", true);
  getStr("ssid", gSettings.ssid, sizeof gSettings.ssid, "");
  getStr("pass", gSettings.pass, sizeof gSettings.pass, "");
  getStr("host", gSettings.host, sizeof gSettings.host, "");
  gSettings.port = prefs.getUShort("port", BRAIN_DEFAULT_PORT);
  getStr("token", gSettings.token, sizeof gSettings.token, "");
  getStr("ota", gSettings.otaPass, sizeof gSettings.otaPass, "");
  gSettings.volume = prefs.getFloat("vol", 0.6f);
  gSettings.cat = prefs.getBool("cat", false);
  getStr("rdog", gSettings.recipeDog, sizeof gSettings.recipeDog, "");
  getStr("rcat", gSettings.recipeCat, sizeof gSettings.recipeCat, "");
  prefs.end();
  if (!(gSettings.volume >= 0 && gSettings.volume <= 1)) gSettings.volume = 0.6f;
}

void settingsSave() {
  prefs.begin("spike", false);
  prefs.putString("ssid", gSettings.ssid);
  prefs.putString("pass", gSettings.pass);
  prefs.putString("host", gSettings.host);
  prefs.putUShort("port", gSettings.port);
  prefs.putString("token", gSettings.token);
  prefs.putString("ota", gSettings.otaPass);
  prefs.putFloat("vol", gSettings.volume);
  prefs.putBool("cat", gSettings.cat);
  prefs.putString("rdog", gSettings.recipeDog);
  prefs.putString("rcat", gSettings.recipeCat);
  prefs.end();
}

void settingsFactoryReset() {
  prefs.begin("spike", false);
  prefs.clear();
  prefs.end();
  settingsLoad();
}

const char* deviceId() {
  static char id[20] = {0};
  if (!id[0]) {
    uint8_t mac[6];
    esp_efuse_mac_get_default(mac);
    snprintf(id, sizeof id, "spike-%02x%02x%02x", mac[3], mac[4], mac[5]);
  }
  return id;
}
