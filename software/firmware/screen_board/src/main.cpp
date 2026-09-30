// main.cpp -- Spike's screen board: boot, the face task, and the glue between the modules.
//
// The face task (core 1) owns Spike's life (lib/spike_life) and the face renderer (lib/spike_face):
// every frame it applies the queued commands (brain, touch, body, audio), steps the behaviour engine,
// draws the face into the PSRAM back buffer and hands it to the panel. It reports mood / action
// changes to the brain and tells the body which motion to play.
#include <Arduino.h>
#include <esp_task_wdt.h>
#include <esp_heap_caps.h>
#include <time.h>
#include "app.h"
#include "config.h"
#include "spike_face_draw.h"
#include "spike_raster.h"
#include "spike_life.h"
#include "spike_body.h"
#include "spike_passkey.h"

using namespace spike;

static QueueHandle_t cmdQ;

bool postCmd(const Cmd& c) { return cmdQ && xQueueSend(cmdQ, &c, 0) == pdTRUE; }

Cmd makeCmd(uint8_t type, int a, int b, float x, float y, const char* s) {
  Cmd c;
  c.type = type;
  c.a = (int16_t)a;
  c.b = (int16_t)b;
  c.x = x;
  c.y = y;
  c.s[0] = 0;
  if (s) { strncpy(c.s, s, sizeof c.s - 1); c.s[sizeof c.s - 1] = 0; }
  return c;
}

void bodySetInhibit(bool on);

// ---- Life hooks: sounds to the speaker, captions to the log ----------------------------------------
struct Hooks : LifeHooks {
  void playSound(Sound s, float arg) override { audioPlaySound((uint8_t)s, arg); }
  void caption(const char* text, bool literal, float) override {
    if (literal) logf("face: \"%s\"", text);
  }
};

// ---- face task state -----------------------------------------------------------------------------
static Hooks hooks;
static Life* life;
static Recipe recipes[2];  // [0] dog, [1] cat
static uint32_t lookAtMs = 0;
struct TouchState { bool down; int16_t x0, y0, x, y; uint32_t t0; HitZone zone; bool held, moved; uint32_t lastPat; };
static TouchState ts{};
static uint32_t padDown[5];
static bool padHeld[5];

static void loadRecipes() {
  recipes[0] = findPreset("classic")->recipe;
  recipes[1] = findPreset("spicy")->recipe;
  Recipe r;
  if (gSettings.recipeDog[0] && fromCode(gSettings.recipeDog, &r)) recipes[0] = r;
  if (gSettings.recipeCat[0] && fromCode(gSettings.recipeCat, &r)) recipes[1] = r;
}

static void sendTouch(const char* zone, const char* gesture) {
  char f[64];
  snprintf(f, sizeof f, "\"zone\":\"%s\",\"gesture\":\"%s\"", zone, gesture);
  netSend("touch", f);
}

static int hourNow() {
  time_t now = time(nullptr);
  if (now < 1700000000) return 12;  // clock not set yet (no Wi-Fi): assume the afternoon
  struct tm t;
  localtime_r(&now, &t);
  return t.tm_hour;
}

static void applyCmd(const Cmd& c) {
  Life& L = *life;
  switch (c.type) {
    case C_MOOD: {
      int m = moodIndex(c.s);
      if (m >= 0) { L.setMood(m); if (c.x > 0) L.setMoodHold(c.x); }
      break;
    }
    case C_ACTION:
      if (L.comfort(c.s)) { BodyCmd b{B_PLAY, 0, ""}; strncpy(b.label, c.s, sizeof b.label - 1); postBody(b); }
      else L.playAction(c.s);
      break;
    case C_EVENT:
      if (!strcmp(c.s, "sayHi")) L.sayHi();
      else if (!strcmp(c.s, "greetByTimeOfDay")) L.greetByTimeOfDay(hourNow());
      else if (!strcmp(c.s, "comeHome")) L.comeHome();
      else if (!strcmp(c.s, "ownerLooksSad")) L.ownerLooksSad();
      else if (!strcmp(c.s, "pickedUp")) L.pickedUp();
      else if (!strcmp(c.s, "fellOver")) L.fellOver();
      else if (!strcmp(c.s, "ignoredNudge")) L.ignoredNudge();
      break;
    case C_SOUND: {
      bool ok;
      Sound s = soundFromProtocolName(c.s, &ok);
      if (ok) audioPlaySound((uint8_t)s, 0);
      break;
    }
    case C_LOOK: L.setLook(c.x, c.y); lookAtMs = millis(); break;
    case C_MODE:
      if ((c.a != 0) != L.cat()) {
        L.setMode(c.a != 0);
        gSettings.cat = c.a != 0;
        settingsSave();
      }
      break;
    case C_RECIPE_CODE: {
      Recipe r;
      if (fromCode(c.s, &r)) {
        recipes[c.a ? 1 : 0] = r;
        strncpy(c.a ? gSettings.recipeCat : gSettings.recipeDog, c.s, sizeof gSettings.recipeDog - 1);
        settingsSave();
      }
      break;
    }
    case C_LISTEN: L.setListening((Listen)c.a); break;
    case C_ALARM: L.alarm((AlarmState)c.a, c.b); break;
    case C_GAME:
      if (c.a == 0) L.gameStart();
      else if (c.a == 3) L.rpsReact(c.b);
      break;
    case C_BATTERY: L.setBattery(c.x); break;
    case C_SAFETY:
      switch ((body::SafetyEvent)c.a) {
        case body::EV_EDGE_FL: case body::EV_EDGE_FR: case body::EV_EDGE_REAR: L.edgeFear(); break;
        case body::EV_PICKUP: L.pickedUp(); break;
        case body::EV_FALL: L.fellOver(); break;
        default: break;
      }
      break;
    case C_SPEECH_START: {
      int m = moodIndex(c.s);
      if (m >= 0) L.setMood(m);
      L.markInteraction();
      break;
    }
    case C_TOUCH_PAD: {
      int e = c.a;
      if (e < 0 || e > 4) break;
      const char* zone = e == PAD_HEAD ? "head" : "back";
      if (c.b) {
        padDown[e] = millis();
        padHeld[e] = false;
        L.pat();
        sendTouch(zone, e == PAD_HEAD ? "tap" : "pat");
      } else if (padHeld[e]) sendTouch(zone, "release");
      break;
    }
    case C_GESTURE: if (c.a) L.handWave(); else L.handNear(); break;
    case C_BRAIN_UP: break;
    case C_BRAIN_DOWN: break;
    case C_HELLO_NAMES: logf("face: names from the brain: %s", c.s); break;
    default: break;
  }
}

// Screen touch: nose -> boop, anywhere else -> pat (as the face_v2 page), strokes pat again,
// a long press sends hold/release, and the eyes follow the finger.
static void handleTouch(const FaceState& p, const Recipe& r) {
  TouchPoint tp = touchRead();
  uint32_t now = millis();
  if (tp.fresh) {
    if (tp.down && !ts.down) {
      ts = TouchState{true, tp.x, tp.y, tp.x, tp.y, now, hitTest(p, r, tp.x, tp.y), false, false, now};
      if (ts.zone == HIT_NOSE) { life->boop(); sendTouch("nose", "tap"); }
      else { life->pat(); sendTouch(ts.zone == HIT_HEAD ? "head" : "chin", "tap"); }
    } else if (tp.down && ts.down) {
      ts.x = tp.x; ts.y = tp.y;
      int dx = ts.x - ts.x0, dy = ts.y - ts.y0;
      if (!ts.moved && dx * dx + dy * dy > 30 * 30) ts.moved = true;
      if (ts.moved && ts.zone != HIT_NOSE && now - ts.lastPat > 450) {
        ts.lastPat = now;
        life->pat();
        sendTouch(ts.y < LCD_H / 2 ? "head" : "chin", "pat");
      }
    } else if (!tp.down && ts.down) {
      if (ts.held) sendTouch(ts.zone == HIT_NOSE ? "nose" : (ts.zone == HIT_HEAD ? "head" : "chin"), "release");
      ts.down = false;
    }
  }
  if (ts.down) {
    if (!ts.held && !ts.moved && now - ts.t0 > 1000) {
      ts.held = true;
      sendTouch(ts.zone == HIT_NOSE ? "nose" : (ts.zone == HIT_HEAD ? "head" : "chin"), "hold");
    }
    if (now - lookAtMs > 1500) life->setLook((ts.x - 240) / 240.0f, (ts.y - 122) / 150.0f);  // the camera wins
  }
  for (int e = 0; e < 5; e++)  // touch-pad holds
    if (padDown[e] && !padHeld[e] && now - padDown[e] > 1000) {
      padHeld[e] = true;
      sendTouch(e == PAD_HEAD ? "head" : "back", "hold");
    }
}

static body::PoseId restPoseFor(int mood) {
  if (mood == moodIndex("sleeping")) return body::POSE_LIE;
  if (mood == moodIndex("sleepy") || mood == moodIndex("begging") || mood == moodIndex("hungry")) return body::POSE_SIT;
  return body::POSE_STAND;
}

static void faceTask(void*) {
  esp_task_wdt_add(nullptr);
  life = new Life(&hooks, esp_random());
  loadRecipes();
  if (gSettings.cat) life->setMode(true);
  life->setMood(0, false, true);
  VectorGfx* G = new VectorGfx();
  if (!G->ok()) logf("face: renderer allocation FAILED");
  Rgb565Surface surf(displayBackBuffer(), LCD_W, LCD_H);
  G->setSurface(&surf);

  uint32_t lastSerial = 0xFFFFFFFF, lastMoodSent = 0;
  const char* lastAction = nullptr;
  int lastMood = -1;
  uint32_t statFrames = 0, statT0 = millis();
  uint64_t renderSum = 0;
  uint32_t renderMax = 0;
  TickType_t wake = xTaskGetTickCount();
  int64_t prevUs = esp_timer_get_time();
  for (;;) {
    esp_task_wdt_reset();
    Cmd c;
    int budget = 24;
    while (budget-- > 0 && xQueueReceive(cmdQ, &c, 0) == pdTRUE) applyCmd(c);

    int64_t nowUs = esp_timer_get_time();
    double dt = (nowUs - prevUs) / 1e6;
    prevUs = nowUs;
    life->setSpeechLevel(audioMouthLevel());
    life->update(dt);

    // body + brain bookkeeping
    const char* act = life->actionName();
    if (act != lastAction) {
      if (act) { BodyCmd b{B_PLAY, 0, ""}; strncpy(b.label, life->actionLabel(), sizeof b.label - 1); postBody(b); }
      lastAction = act;
    }
    if (life->mood() != lastMood) {
      lastMood = life->mood();
      BodyCmd b{B_REST_POSE, (int16_t)restPoseFor(lastMood), ""};
      postBody(b);
    }
    if (life->stateSerial() != lastSerial && millis() - lastMoodSent > 100) {
      lastSerial = life->stateSerial();
      lastMoodSent = millis();
      char f[128];
      snprintf(f, sizeof f, "\"mood\":\"%s\",\"mode\":\"%s\",\"action\":%s%s%s", mood(life->mood()).id,
               life->cat() ? "cat" : "dog", act ? "\"" : "", act ? act : "null", act ? "\"" : "");
      netSend("mood_state", f);
    }

    const Recipe& r = recipes[life->cat() ? 1 : 0];
    FaceState p = life->faceParams();
    handleTouch(p, r);

    uint32_t t0 = micros();
    surf.setBuffer(displayBackBuffer());
    drawFace(*G, p, r, life->drawTime());
    Rgb back = r.frame == FRAME_HEAD ? r.bg : r.fur;
    life->particles().draw(*G, life->drawTime(), luminance(back) > 0.45f);
    uint32_t passkey;
    float passkeyLeft;
    if (blePasskey(&passkey, &passkeyLeft)) drawPasskeyOverlay(*G, passkey, passkeyLeft, LCD_W, LCD_H);  // BLE pairing (11.1)
    uint32_t renderUs = micros() - t0;
    displayPresent();

    renderSum += renderUs;
    if (renderUs > renderMax) renderMax = renderUs;
    statFrames++;
    if (millis() - statT0 >= 10000) {
      float secs = (millis() - statT0) / 1000.0f;
      logf("face: %.1f fps, render %.1f ms avg / %.1f ms max, mood %s, free heap %u / PSRAM %u", statFrames / secs,
           renderSum / 1000.0f / statFrames, renderMax / 1000.0f, mood(life->mood()).id, (unsigned)ESP.getFreeHeap(),
           (unsigned)ESP.getFreePsram());
      statFrames = 0;
      renderSum = 0;
      renderMax = 0;
      statT0 = millis();
    }
    vTaskDelayUntil(&wake, pdMS_TO_TICKS(1000 / FACE_FPS_TARGET));  // no catch-up bursts after a slow frame
    if ((int32_t)(xTaskGetTickCount() - wake) > 0) wake = xTaskGetTickCount();
  }
}

void setup() {
  Serial.begin(115200);
  delay(200);
  logf("\nSpike screen board firmware %s (%s)", SPIKE_FW_VERSION, __DATE__);
  esp_task_wdt_init(WDT_TIMEOUT_S, true);
  esp_task_wdt_add(nullptr);  // the Arduino loop task
  settingsLoad();
  if (!psramFound()) logf("WARNING: no PSRAM -- check the board settings (OPI PSRAM)");
  cmdQ = xQueueCreate(32, sizeof(Cmd));
  bodyBegin();                 // first: OE high, servos safe, before anything slow
  displayBegin();
  touchBegin();
  audioBegin();
  configTzTime("AEST-10AEDT,M10.1.0,M4.1.0/3", "pool.ntp.org");  // Melbourne; used only for greetings
  netBegin();
  provisionBegin();
  otaBegin();
  xTaskCreatePinnedToCore(faceTask, "face", 12288, nullptr, 5, nullptr, 1);
  logf("device %s ready", deviceId());
}

void loop() {
  esp_task_wdt_reset();
  netLoop();
  provisionLoop();
  otaLoop();
  delay(5);
}
