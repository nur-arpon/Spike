// cam.h -- camera board shared declarations.
#pragma once
#include <Arduino.h>

// OV5640 pins: the seller's map for the "ESP32-S3 N16R8 CAM" board family (Freenove ESP32-S3-WROOM
// CAM layout, identical to Espressif's ESP32-S3-EYE map). NOT the AI-Thinker ESP32-CAM map (BOM 2e).
// If the camera does not start, compare with the seller's pin sheet and change only these lines.
#define CAM_PIN_PWDN -1
#define CAM_PIN_RESET -1
#define CAM_PIN_XCLK 15
#define CAM_PIN_SIOD 4
#define CAM_PIN_SIOC 5
#define CAM_PIN_D7 16
#define CAM_PIN_D6 17
#define CAM_PIN_D5 18
#define CAM_PIN_D4 12
#define CAM_PIN_D3 10
#define CAM_PIN_D2 8
#define CAM_PIN_D1 9
#define CAM_PIN_D0 11
#define CAM_PIN_VSYNC 6
#define CAM_PIN_HREF 7
#define CAM_PIN_PCLK 13

#define BRAIN_DEFAULT_PORT 8765
#define JPEG_MAX_BYTES (46 * 1024)  // protocol: <= 48 KiB JPEG, and the base64 message must stay <= 64 KiB

struct CamSettings {
  char ssid[33], pass[65], host[64], token[65], otaPass[33], robotId[24];
  uint16_t port;
  uint8_t frameSize;   // framesize_t: QQVGA 1 .. VGA 8 (default QVGA 5 = 320 x 240)
  uint8_t fps;         // 1..10
  uint8_t quality;     // JPEG quality 6 (best) .. 40
  bool vflip, hmirror;
};
extern CamSettings cs;

void logf(const char* fmt, ...);
void settingsLoad();
void settingsSave();
const char* deviceId();

bool netSend(const char* type, const char* fields);
bool netConnected();
void netBegin();
void netLoop();
void netRestart();                 // drop the brain link now (the network changes); reconnects by itself
bool portalActive();

// ---- away from home (cam_away.cpp, PROTOCOL.md v1.3 section 11.6) ----
struct AwayHotspot {               // the phone's hotspot, from the screen board over ESP-NOW (RAM only)
  char ssid[33], pass[64], token[65], host[64], sid[17];
  uint16_t port;
};
void awayBegin();
void awayLoop();
const AwayHotspot* awayHotspot();  // non-null while the camera uses the phone's hotspot
bool awayLinkKeySet();
void awayLinkKeyCommand(const char* arg);  // console `linkkey [<64 hex> | forget]`
const char* awayModeName();
