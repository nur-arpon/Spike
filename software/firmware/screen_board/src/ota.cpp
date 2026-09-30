// ota.cpp -- wireless firmware updates (BOM audit 2d: "build wireless updates in from day one").
// ArduinoOTA on the "Minimal SPIFFS with OTA" partition table (two 1.9 MB app slots): the new image
// goes to the idle slot and only becomes active after it was written and verified completely, so a
// failed update leaves the old firmware running. Disabled until an update password is set (no
// default passwords): serial `otapass <password>` or the setup portal.
// Before the flash is written the servos are switched off (OE high) so nothing moves mid-update.
#include "app.h"
#include "config.h"
#include <ArduinoOTA.h>
#include <WiFi.h>

static bool started = false;

void otaReconfigure() {
  if (started || !gSettings.otaPass[0]) return;
  if (!netOnHomeWifi()) return;  // wireless updates on the home Wi-Fi only, never on the phone's hotspot
  ArduinoOTA.setHostname(deviceId());
  ArduinoOTA.setPassword(gSettings.otaPass);
  ArduinoOTA.onStart([]() {
    bodySetInhibit(true);  // every servo output off during the update (OE high)
    audioStopSpeaking();
    logf("ota: update started -- servos off");
  });
  ArduinoOTA.onEnd([]() { logf("ota: update written, restarting"); });
  ArduinoOTA.onError([](ota_error_t e) { logf("ota: update failed (%d); the old firmware stays", (int)e); });
  ArduinoOTA.begin();
  started = true;
  logf("ota: ready as %s.local", deviceId());
}

void otaBegin() {}

void otaLoop() {
  if (!started) { otaReconfigure(); return; }
  if (!netOnHomeWifi()) return;  // (v1.3) on the phone's hotspot no update is accepted
  ArduinoOTA.handle();
}
