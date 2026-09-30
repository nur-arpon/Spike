// spike_life.h -- Spike's life on the robot: the behaviour engine (port of face_v2/behaviour.js), the
// scripted physical actions (actions.js), the comfort actions and brain-link reactions (brain_link.js).
//
// It runs WITHOUT the laptop: moods, idle life (blinks, saccades, glances, ear flicks, sniffs, idle
// tilts, yawns), mood drift when ignored, pats and boops, pick-ups and falls, battery hunger. The
// laptop brain, when connected, only adds commands on top (mood, action, event, look_at, say...).
//
// Platform-free (no Arduino): sounds go out through LifeHooks, time comes in through update(dt).
// The engine keeps its own clock and scheduler (never wall-clock timers), so a seeded run is
// deterministic and replays the JS engine (test/life_trace).
#pragma once
#include <stdint.h>
#include "spike_params.h"
#include "spike_moods.h"
#include "spike_extras.h"

namespace spike {

// Built-in synthesized sounds (protocol 5.8 names first, then the action-only ones).
enum class Sound : uint8_t {
  Yip, Bark, Whine, Sniff, Sigh, Snore, Giggle, Meow, Purr, Hiss, Trill, Yawn, Sneeze, Hiccup, Growl, Munch, Pop,
  Boop, PatSqueak,                        // protocol names end here
  Sniffs, Pant, ShiverChatter, AlarmBark,  // actions / behaviour only
  Count
};
Sound soundFromProtocolName(const char* s, bool* ok);
const char* soundName(Sound s);

struct LifeHooks {
  virtual ~LifeHooks() {}
  // arg: sniff count, purr / pant / shiver seconds, alarm level (0 when unused)
  virtual void playSound(Sound s, float arg) { (void)s; (void)arg; }
  // A caption the face would show (category from captions.js, or literal text). The robot has no
  // speech bubble by default; the screen board may log it.
  virtual void caption(const char* textOrCategory, bool literal, float holdS) { (void)textOrCategory; (void)literal; (void)holdS; }
};

struct LifeConfig {  // face_v2/config.js
  float blinkMin = 2.2f, blinkMax = 6.0f, doubleBlinkChance = 0.16f;
  float saccadeMin = 0.35f, saccadeMax = 1.1f, glanceMin = 2.2f, glanceMax = 6.0f;
  float earFlickMin = 3.5f, earFlickMax = 9.0f, sniffMin = 7.0f, sniffMax = 16.0f;
  float moodDrift = 20.0f, breathPeriod = 3.4f;
  float hungryBelow = 30.0f, weakBelow = 15.0f;
};

enum class Listen : uint8_t { Idle, Wake, Listening, Thinking, Speaking };
enum class AlarmState : uint8_t { Ringing, Snoozed, Stopped };

// One entry of the engine's own scheduler (behaviour.js after()).
struct LifeEvent {
  double at;
  uint8_t kind;
  uint8_t n;          // number of kicks / small int arg
  int16_t a;          // small int arg (mood index, level, sound)
  uint8_t kf[4];      // kick fields
  float kv[4];        // kick values
};

class Life {
 public:
  explicit Life(LifeHooks* hooks = nullptr, uint32_t seed = 1);
  LifeConfig cfg;

  // ---- time -----------------------------------------------------------------------------------
  void update(double dt);                 // behaviour.js update(e, dt) (double: the clock must not drift)
  FaceState faceParams();                 // behaviour.js getFaceParams(e) (+ speech mouth overlay)
  double time() const { return time_; }
  float drawTime() const;                 // time wrapped to 720 s for float-precise cyclic effects
  const ParticleSystem& particles() const { return particles_; }

  // ---- state ----------------------------------------------------------------------------------
  int mood() const { return mood_; }
  bool cat() const { return cat_; }
  const char* actionLabel() const;        // body label of the running action, or nullptr
  const char* actionName() const;         // actions.js key, or nullptr
  int actionStep() const;                 // step index (-1 if none)
  float actionStepAge() const;
  uint32_t stateSerial() const { return serial_; }  // bumps on mood / mode / action change
  float energy() const { return energy_; }
  float battery() const { return battery_; }
  bool alarmActive() const { return alarmActive_; }

  // ---- inputs (behaviour.js API) ----------------------------------------------------------------
  void setMood(int idx, bool force = false, bool snap = false);
  void setMode(bool cat);
  void setLook(float x, float y);
  void pat();
  void boop();
  void sniff(int n);
  void sayHi();
  void greetByTimeOfDay(int hour);
  void comeHome();
  void ownerLooksSad();
  void alarmStart();
  void imUp();
  void pickedUp();
  void fellOver();
  void ignoredNudge();
  // Firmware additions (not in behaviour.js; the brief asks for them): the desk-edge fright and
  // a hand waved at the gesture sensor.
  void edgeFear();
  void handWave();
  void handNear();
  void rpsReact(int result);              // +1 owner won, -1 owner lost, 0 draw
  void setBattery(float percent) { battery_ = clampf(percent, 0, 100); }
  void setCharging(bool on);
  void markInteraction();
  void override(int field, float v, double seconds);  // seconds < 0 = forever
  void clearOverride(int field);
  void kick(int field, float v) { springs_.kick(field, v); }

  // ---- actions.js + comfort actions -------------------------------------------------------------
  bool playAction(const char* name, bool autoStarted = false);
  bool playActionIndex(int idx, bool autoStarted = false);
  void stopAction();
  static int actionIndex(const char* name);
  bool comfort(const char* name);         // snuggle, slowWag

  // ---- brain link (brain_link.js reactions) -----------------------------------------------------
  void setListening(Listen s);
  void alarm(AlarmState s, int level);
  void gameStart() { setMood(moodIndex("playful")); }
  // Mouth-open envelope while the robot speaks (0..1), or < 0 when silent.
  void setSpeechLevel(float v) { speech_ = v; }
  void setMoodHold(float seconds) { holdUntil_ = time_ + seconds; }

 private:
  friend struct ActionRunner;
  LifeHooks* hooks_;
  LifeHooks nullHooks_;
  Rng rnd_;
  double time_ = 0;
  float dt_ = 0;
  bool cat_ = false;
  int mood_ = 0, prevMood_ = 0;
  double moodSince_ = 0;
  Springs springs_;
  ParticleSystem particles_;
  // overrides of spring targets
  bool overOn_[F_COUNT];
  float overV_[F_COUNT];
  double overUntil_[F_COUNT];
  // scheduler
  static const int kMaxEvents = 24;
  LifeEvent events_[kMaxEvents];
  int nEvents_ = 0;
  // idle life
  double blinkUntil_ = -1, nextBlink_ = 1.2;
  float sacX_ = 0, sacY_ = 0;
  double nextSaccade_ = 0.5;
  float glanceX_ = 0, glanceY_ = 0;
  double glanceUntil_ = -1, nextGlance_ = 3, nextEarFlick_ = 2.5, nextSniff_ = 6, sniffStart_ = -10;
  int sniffCount_ = 0;
  float twitchDX_ = 0;
  double twitchUntil_ = -1, nextTwitch_ = 1, nextIdleTilt_ = 7, nextYawn_ = 30, extrasAt_ = 0;
  float lookX_ = 0, lookY_ = 0;
  double lookSeenAt_ = -100;
  double lastInteraction_ = 0, driftAt_ = 0;
  int driftStage_ = -1;
  double patTimes_[8];
  int nPat_ = 0;
  bool alarmActive_ = false;
  int alarmLevel_ = 0;
  double alarmNextAt_ = 0;
  float battery_ = 80;
  bool charging_ = false;
  int hungerLevel_ = 0;  // 0 ok, 1 hungry, 2 weak
  double nextHungryPokeAt_ = 0, munchNextAt_ = 0;
  float energy_ = 1;
  float speech_ = -1;
  double holdUntil_ = 0;
  uint32_t serial_ = 0;
  // action runner
  int action_ = -1, actionIdx_ = 0, actionPrevMood_ = 0;
  bool actionRestore_ = false;
  double actionStepAt_ = 0;

  float rr(float a, float b) { return a + rnd_.next() * (b - a); }
  bool present() const { return time_ - lookSeenAt_ < 3; }
  void after(double seconds, const LifeEvent& ev);
  void runEvent(const LifeEvent& ev);
  void idle(double t, bool allowed);
  void updateBattery();
  void updateAction();
  void runStep();
  void applyActionOverlay(FaceState& p);
  void sound(Sound s, float arg = 0) { hooks_->playSound(s, arg); }
  void say(const char* category, float hold) { hooks_->caption(category, false, hold); }
  void showCaption(const char* text, float hold) { hooks_->caption(text, true, hold); }
  void kickList(const uint8_t* f, const float* v, int n) { for (int i = 0; i < n; i++) springs_.kick(f[i], v[i]); }
};

}  // namespace spike
