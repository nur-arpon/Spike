// app.h -- the shared plumbing between the screen board's tasks.
//
//  core 1  "face"   Life (behaviour engine) + renderer + touch; owns every Life call
//  core 0  "push"   sends finished frames to the panel
//  core 0  "body"   50 Hz: sensors, safety reflexes, servos (highest priority after Wi-Fi)
//  core 0  "audio"  I2S out (speech + synth) and I2S in (mics)
//  core 0  websocket client task (esp_websocket_client) -> parses brain messages into commands
//  core 0  "blelink" BLE frames in/out (ble_link.cpp) -> the same brain message handler
//  core 0  NimBLE host task (library): GATT, pairing; only copies frames into the blelink queue
// Tasks talk through FreeRTOS queues of small POD commands; nothing shares Life.
#pragma once
#include <Arduino.h>
#include <stdarg.h>

// ---- logging to the UART and the native USB port ------------------------------------------------
void logf(const char* fmt, ...);

// ---- commands into the face task -----------------------------------------------------------------
enum CmdType : uint8_t {
  C_MOOD, C_ACTION, C_EVENT, C_SOUND, C_LOOK, C_MODE, C_RECIPE_CODE, C_LISTEN, C_ALARM, C_GAME,
  C_BATTERY, C_SAFETY, C_SPEECH_START, C_TOUCH_PAD, C_GESTURE, C_BRAIN_UP, C_BRAIN_DOWN, C_HELLO_NAMES
};
struct Cmd {
  uint8_t type;
  int16_t a, b;
  float x, y;
  char s[132];
};
bool postCmd(const Cmd& c);                       // non-blocking; false if the queue is full
Cmd makeCmd(uint8_t type, int a = 0, int b = 0, float x = 0, float y = 0, const char* s = nullptr);

// ---- commands into the body task ----------------------------------------------------------------
enum BodyCmdType : uint8_t { B_PLAY, B_REST_POSE, B_STOP, B_LISTENING, B_CALIBRATE_SAVE, B_DRIVE,
                             B_WALK, B_PAW, B_GAIT_CAL, B_GAIT_RESET, B_GAIT_PUPPY, B_GAIT_LIFT, B_GAIT_SIGN };
// B_GAIT_LIFT (day-1 test): a = 0 left / 1 right front paw, left = hold seconds. B_GAIT_SIGN: a = +1 / -1,
// the closed-loop lean direction (GaitConfig::leanLoopSign, saved).
// B_DRIVE (protocol v1.2 `drive`): a = ttl in ms, left/right = wheel commands x1000 (-1000..1000).
// B_WALK (protocol v1.4 `action` walk): a = steps, left = direction (+1 / -1), right = spike::body::GaitStyle.
// B_PAW (v1.4 `action` paw): a = 0 left / 1 right paw, left = 1 from the puppy sit (only if enabled).
// B_GAIT_CAL: the day-1 balance calibration. B_GAIT_RESET: forget the learned lean trims (keeps calibration
// off -> recalibrate). B_GAIT_PUPPY: a = 1 / 0 enables / disables the puppy-sit give-paw (saved).
struct BodyCmd { uint8_t type; int16_t a; char label[20]; int16_t left, right; };
bool postBody(const BodyCmd& c);

// ---- protocol out (thread-safe) ------------------------------------------------------------------
// Two brain links (PROTOCOL.md v1.3 section 11): the WebSocket (home laptop, or the phone over its
// hotspot) and BLE (the phone). One brain at a time: see lib/spike_link/src/spike_link_policy.h.
enum LinkId : uint8_t { LINK_WS = 0, LINK_BLE = 1 };
// fields: the JSON members after the envelope, e.g. "\"zone\":\"head\",\"gesture\":\"tap\"" (may be "").
// netSend: to the brain the robot follows (the WebSocket when its hello is done, else BLE).
bool netSend(const char* type, const char* fields);
// netSendOn: on one link (replies, hello, robot_link). Nothing but hello/pong before that link's hello.
bool netSendOn(LinkId link, const char* type, const char* fields);
bool netConnected();                              // some brain is followed
void netBegin();
void netLoop();                                   // called from loop(): Wi-Fi, hotspot, links, hand-over
bool netWantsMic();                               // only the laptop brain gets the mics (11.3)
void netHandleMessage(LinkId from, char* text, size_t len);  // brain -> robot, shared by both links
const char* netBrainName();                       // "lan" / "ble" / "hotspot" / "none" (safe from any task)
bool netOnHomeWifi();                             // joined the saved home Wi-Fi (not the phone's hotspot)
void netConsoleStatus();                          // console `status` line for the links
// BLE session hooks, called by ble_link.cpp from its link task
void netBleSessionStart();                        // an authenticated phone subscribed to tx: send hello
void netBleSessionEnd();
void netBleTooBig();                              // a message over 16 KiB was dropped: error too_big once

// ---- BLE link (ble_link.cpp): NimBLE GATT server, LE Secure Connections, framing (11.1-11.3) -----
void bleBegin();
void bleLoop();                                   // pairing timeout, passkey overlay timeout
bool bleQueueMessage(const char* json, size_t len);  // copied; framed + notified by the BLE task
bool bleConnected();                              // an authenticated (SC, MITM, bonded) phone is connected
bool blePasskey(uint32_t* passkey, float* remaining);  // a pairing passkey to show on the face
void bleDisconnect(const char* why);
void bleConsole(const char* args);                // `ble` status, `ble forget`
void bleForgetAll();                              // delete every bond (also on factory-reset)

// ---- ESP-NOW hand-over of the hotspot to the camera board + the link key (handover.cpp, 11.6) ----
void linkKeyEnsure();                             // make the 32-byte link key on first boot (NVS)
void linkKeyPrint();                              // console `linkkey`
void handoverStart(const char* ssid, const char* pass, uint16_t port, const char* token, const char* host,
                   const char* sidHex);          // send kind 1 every second (<= 120 s, until the ack)
void handoverStop(bool sendLeave);                // kind 2 (when asked) and stop
void handoverLoop();
void handoverCameraAck();                         // robot_link_ack camera:true (any task)
bool handoverCameraOnline();

// ---- settings (NVS) -------------------------------------------------------------------------------
struct Settings {
  char ssid[33];
  char pass[65];
  char host[64];
  uint16_t port;
  char token[65];
  char otaPass[33];
  float volume;
  bool cat;
  char recipeDog[132];
  char recipeCat[132];
};
extern Settings gSettings;
void settingsLoad();
void settingsSave();
void settingsFactoryReset();
const char* deviceId();                           // "spike-xxxxxx" from the eFuse MAC

// ---- modules --------------------------------------------------------------------------------------
void displayBegin();
uint16_t* displayBackBuffer();                    // PSRAM RGB565 frame to render into
void displayPresent();                            // hand the back buffer to the push task, swap
void displayBacklight(uint8_t level);

void touchBegin();
struct TouchPoint { bool fresh; bool down; int16_t x, y; };  // fresh = new data this read
TouchPoint touchRead();

void audioBegin();
void audioPlaySound(uint8_t sound, float arg);    // spike::Sound
void audioSetVolume(float v);
// speech from the brain (protocol 5.4 / 5.5)
struct SayHeader {
  char utt[24];
  int seq;
  bool final;
  bool hasAudio;
  int rate, samples, chunks;
  int durationMs;
  char mood[24];
  uint8_t mouth[1024];
  int mouthN, mouthHz;
  bool hasText;
};
void audioSay(const SayHeader& h);
void audioSayChunk(const char* utt, int seq, int index, bool last, const char* b64, size_t b64len);
void audioStopSpeaking();
float audioMouthLevel();                          // current speech mouth 0..1, or < 0 when silent
bool audioSpeaking();

void bodyBegin();
float bodyBatteryVolts();
void bodySetInhibit(bool on);                     // OE high and stay off (OTA, `servo off`)
void bodyConsole(const char* line);
void gaitConsole(const char* line);               // `gait ...`: walk, paw, balance calibration (body_hw.cpp)

void provisionBegin();
void provisionLoop();                             // serial console (always) + setup portal (when active)
bool provisionPortalActive();
void provisionStopPortal();                       // (loop task) the phone took over: close the open AP

void otaBegin();
void otaLoop();
