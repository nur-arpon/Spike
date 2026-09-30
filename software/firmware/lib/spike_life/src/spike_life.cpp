// spike_life.cpp -- see spike_life.h. Port of face_v2/behaviour.js (+ the action runner of actions.js
// and the comfort actions / listening / alarm reactions of brain_link.js). The ORDER of every rnd()
// call follows the JS exactly, so a seeded run replays the JS engine (test/life_trace.js).
#include "spike_life.h"
#include "spike_actions.h"
#include <math.h>
#include <string.h>
#include <initializer_list>
#include <utility>

namespace spike {

// ------------------------------------------------------------------------------------------------
static const char* const kSoundNames[] = {"yip", "bark", "whine", "sniff", "sigh", "snore", "giggle", "meow",
                                          "purr", "hiss", "trill", "yawn", "sneeze", "hiccup", "growl", "munch",
                                          "pop", "boop", "patSqueak", "sniffs", "pant", "shiver", "alarmBark"};

Sound soundFromProtocolName(const char* s, bool* ok) {
  if (s)
    for (int i = 0; i <= (int)Sound::PatSqueak; i++)
      if (strcmp(kSoundNames[i], s) == 0) { if (ok) *ok = true; return (Sound)i; }
  if (ok) *ok = false;
  return Sound::Yip;
}
const char* soundName(Sound s) { return (int)s < (int)Sound::Count ? kSoundNames[(int)s] : "?"; }

// scheduler event kinds
enum : uint8_t {
  EV_KICK, EV_CAPTION_CAT, EV_SOUND, EV_PAT_DIZZY_END, EV_SAD_FOLLOWUP, EV_FELL_FOLLOWUP, EV_HUNGRY_GROWL,
  EV_HUNGRY_END, EV_WAG, EV_EDGE_RELIEF
};

static int M(const char* id) { return moodIndex(id); }

static bool isPositive(int m) {
  static const char* const P[] = {"happy", "excited", "love", "laughing", "playful", "joy", "delight", "proud",
                                  "wakeupAlarm", "awe", "hope", "gratitude", "surprised", "silliness"};
  for (const char* p : P) if (M(p) == m) return true;
  return false;
}
static bool isNegative(int m) {
  static const char* const N[] = {"sad", "grief", "loneliness", "sulking", "sleepy", "bored", "hungry", "scared"};
  for (const char* p : N) if (M(p) == m) return true;
  return false;
}
static bool noIdleTilt(int m) {
  return m == M("sleeping") || m == M("dizzy") || m == M("grief") || m == M("scared");
}

// ------------------------------------------------------------------------------------------------
Life::Life(LifeHooks* hooks, uint32_t seed) : hooks_(hooks ? hooks : &nullHooks_), rnd_(seed) {
  springs_.init(moodTarget(0, false));
  for (int i = 0; i < F_COUNT; i++) { overOn_[i] = false; overV_[i] = 0; overUntil_[i] = 0; }
}

float Life::drawTime() const { return (float)fmod(time_, 720.0); }

void Life::markInteraction() {
  lastInteraction_ = time_;
  driftStage_ = -1;
  driftAt_ = time_;
}

void Life::override(int field, float v, double seconds) {
  if (field < 0 || field >= F_COUNT) return;
  overOn_[field] = true;
  overV_[field] = v;
  overUntil_[field] = seconds < 0 ? 1e30 : time_ + seconds;
}
void Life::clearOverride(int field) { if (field >= 0 && field < F_COUNT) overOn_[field] = false; }

void Life::after(double seconds, const LifeEvent& ev) {
  if (nEvents_ >= kMaxEvents) return;
  events_[nEvents_] = ev;
  events_[nEvents_].at = time_ + seconds;
  nEvents_++;
}

static LifeEvent evKick(std::initializer_list<std::pair<int, float>> k) {
  LifeEvent e{};
  e.kind = EV_KICK;
  for (auto& p : k) if (e.n < 4) { e.kf[e.n] = (uint8_t)p.first; e.kv[e.n] = p.second; e.n++; }
  return e;
}
static LifeEvent ev(uint8_t kind, int a = 0) { LifeEvent e{}; e.kind = kind; e.a = (int16_t)a; return e; }

// ------------------------------------------------------------------------------------------------
// Mood
// ------------------------------------------------------------------------------------------------
void Life::setMood(int id, bool force, bool snap) {
  if (id < 0 || id >= kNumMoods) id = 0;
  if (id == mood_ && !force && !snap) return;
  prevMood_ = mood_;
  mood_ = id;
  moodSince_ = time_;
  serial_++;
  FaceState target = moodTarget(id, cat_);
  if (snap) { springs_.snap(target); return; }
  if (isPositive(id)) { springs_.kick(F_headSY, 0.9f); springs_.kick(F_headSX, -0.5f); springs_.kick(F_eyeSY, 0.8f); }
  else if (isNegative(id)) { springs_.kick(F_headSY, -0.5f); springs_.kick(F_headSX, 0.3f); }
  else { springs_.kick(F_headSY, 0.35f); springs_.kick(F_eyeSY, 0.4f); }
  const ExtrasDef& ex = spike::mood(id).extras;
  for (int i = 0; i < ex.nEnter; i++)
    particles_.burst(ex.enter[i].type, ex.enter[i].x, ex.enter[i].y, ex.enter[i].count ? ex.enter[i].count : 1, rnd_);
  extrasAt_ = time_ + 0.4;
}

void Life::setMode(bool cat) {
  cat_ = cat;
  setMood(mood_, true);
  springs_.kick(F_headSY, 1.2f);
  springs_.kick(F_headSX, -0.8f);
  serial_++;
}

void Life::setLook(float x, float y) {
  lookX_ = clampf(x, -1, 1);
  lookY_ = clampf(y, -1, 1);
  lookSeenAt_ = time_;
}

// ------------------------------------------------------------------------------------------------
// Touch
// ------------------------------------------------------------------------------------------------
void Life::pat() {
  markInteraction();
  double t = time_;
  if (nPat_ < 8) patTimes_[nPat_++] = t;
  int w = 0;
  for (int i = 0; i < nPat_; i++) if (t - patTimes_[i] < 1.6) patTimes_[w++] = patTimes_[i];
  nPat_ = w;
  springs_.kick(F_headSY, -1.6f); springs_.kick(F_headSX, 0.9f); springs_.kick(F_earL, 160); springs_.kick(F_earR, 160);
  override(F_earBack, 0.5f, 0.9);
  override(F_happy, 1, 0.9);
  override(F_blush, 0.7f, 0.9);
  if (nPat_ >= 6) {
    nPat_ = 0;
    setMood(M("dizzy"));
    say("tease", 2.6f);
    after(2.4, ev(EV_PAT_DIZZY_END));
    return;
  }
  if (cat_ && nPat_ >= 4) {
    nPat_ = 0;
    for (int i = 0; i < F_COUNT; i++) overOn_[i] = false;
    setMood(M("cuteAngry"));
    sound(Sound::Hiss);
    say("catsass", 2.6f);
    return;
  }
  setMood(cat_ ? M("cuddly") : M("happy"));
  particles_.burst(Particle::Heart, 240, 44, 2 + (int)floorf(rnd_.next() * 2), rnd_);
  if (cat_) sound(Sound::Purr, 1.2f); else sound(Sound::PatSqueak);
  if (rnd_.next() < 0.4f) say(cat_ ? "catsass" : "pat", 2.2f);
}

void Life::boop() {
  markInteraction();
  playAction("boop");
}

void Life::sniff(int n) {
  sniffStart_ = time_;
  sniffCount_ = n ? n : 3;
  sound(Sound::Sniffs, (float)sniffCount_);
}

// ------------------------------------------------------------------------------------------------
// Greetings and life events
// ------------------------------------------------------------------------------------------------
void Life::sayHi() {
  markInteraction();
  setMood(cat_ ? M("delight") : M("happy"));
  springs_.kick(F_bob, -120); springs_.kick(F_headSY, 1.4f); springs_.kick(F_earL, -150); springs_.kick(F_earR, -150);
  sound(cat_ ? Sound::Meow : Sound::Yip);
  showCaption("Hi!", 1.6f);
  after(1.7, ev(EV_CAPTION_CAT, 0));
}

void Life::greetByTimeOfDay(int hour) {
  markInteraction();
  const char* cat;
  const char* m;
  if (hour >= 5 && hour < 12) { cat = "greetMorning"; m = "joy"; }
  else if (hour >= 12 && hour < 17) { cat = "greetAfternoon"; m = "happy"; }
  else if (hour >= 17 && hour < 22) { cat = "greetEvening"; m = "caring"; }
  else { cat = "greetLateNight"; m = "sleepy"; }
  setMood(M(m));
  say(cat, 3);
}

void Life::comeHome() {
  markInteraction();
  setMood(M("excited"));
  springs_.kick(F_bob, -160); springs_.kick(F_headSY, 1.8f); springs_.kick(F_earL, -220); springs_.kick(F_earR, -220);
  after(0.45, evKick({{F_bob, -140}, {F_headSY, 1.4f}}));
  after(0.9, evKick({{F_bob, -100}, {F_headSY, 1.0f}}));
  particles_.burst(Particle::Confetti, 240, 60, 10, rnd_);
  particles_.burst(Particle::Heart, 240, 50, 3, rnd_);
  if (cat_) sound(Sound::Trill);
  else { sound(Sound::Yip); after(0.22, ev(EV_SOUND, (int)Sound::Bark)); }
  showCaption("YOU'RE BACK!!", 3);
}

void Life::ownerLooksSad() {
  markInteraction();
  setMood(M("caring"));
  sound(Sound::Whine);
  say("comfort", 4);
  after(5.5, ev(EV_SAD_FOLLOWUP));
}

void Life::alarmStart() {
  alarmActive_ = true;
  alarmLevel_ = 0;
  alarmNextAt_ = time_;
  setMood(M("wakeupAlarm"));
}

void Life::imUp() {
  if (!alarmActive_) return;
  alarmActive_ = false;
  markInteraction();
  setMood(M("proud"));
  particles_.burst(Particle::Sparkle, 240, 50, 5, rnd_);
  say("general", 2.6f);
}

void Life::pickedUp() {
  markInteraction();
  setMood(M("cuddly"));
  if (cat_) sound(Sound::Purr, 1.8f); else sound(Sound::Sigh);
  say("comfort", 3);
}

void Life::fellOver() {
  markInteraction();
  setMood(M("scared"));
  springs_.kick(F_tilt, -220); springs_.kick(F_bob, 140); springs_.kick(F_headSY, -2);
  sound(Sound::Whine);
  after(0.8, ev(EV_FELL_FOLLOWUP));
}

void Life::ignoredNudge() {
  setMood(M("sulking"));
  say("comfort", 2.6f);
}

// The wheels already stopped (body safety reflex); the face shows the fright, then relief.
void Life::edgeFear() {
  markInteraction();
  if (mood_ != M("scared")) setMood(M("scared"));
  springs_.kick(F_bob, 90); springs_.kick(F_headSY, -1.2f); springs_.kick(F_earL, 200); springs_.kick(F_earR, 200);
  sound(Sound::Whine);
  after(1.8, ev(EV_EDGE_RELIEF));
}

void Life::handWave() {
  markInteraction();
  sayHi();
}

void Life::handNear() {
  markInteraction();
  if (mood_ == 0 || mood_ == M("bored") || mood_ == M("loneliness")) setMood(M("curious"));
  setLook(0, -0.6f);
}

void Life::rpsReact(int result) {
  markInteraction();
  if (result > 0) {
    setMood(M("sulking"));
    say("tease", 2.4f);
    sound(cat_ ? Sound::Hiss : Sound::Whine);
  } else if (result < 0) {
    setMood(M("excited"));
    particles_.burst(Particle::Confetti, 240, 60, 8, rnd_);
    say("greeting", 2.4f);
    sound(cat_ ? Sound::Trill : Sound::Giggle);
  } else {
    setMood(M("curious"));
    say("general", 2);
  }
}

void Life::setCharging(bool on) {
  if (on && !charging_) {
    markInteraction();
    setMood(cat_ ? M("delight") : M("joy"));
    say("full", 2.4f);
  }
  charging_ = on;
}

// ------------------------------------------------------------------------------------------------
// Scheduler events
// ------------------------------------------------------------------------------------------------
void Life::runEvent(const LifeEvent& e) {
  switch (e.kind) {
    case EV_KICK: kickList(e.kf, e.kv, e.n); break;
    case EV_CAPTION_CAT: say("greeting", 2.6f); break;
    case EV_SOUND: sound((Sound)e.a); break;
    case EV_PAT_DIZZY_END: if (mood_ == M("dizzy")) setMood(M("embarrassed")); break;
    case EV_SAD_FOLLOWUP:
      if (alarmActive_) return;
      setMood(cat_ ? M("playful") : M("happy"));
      say("selfdep", 3);
      break;
    case EV_FELL_FOLLOWUP:
      setMood(M("embarrassed"));
      showCaption("I meant to do that.", 2.8f);
      break;
    case EV_HUNGRY_GROWL: if (mood_ == M("hungry")) sound(Sound::Growl); break;
    case EV_HUNGRY_END: if (mood_ == M("hungry")) setMood(e.a == 2 ? M("sleepy") : M("sad")); break;
    case EV_EDGE_RELIEF: if (mood_ == M("scared")) setMood(M("relief")); break;
    case EV_WAG:
      springs_.kick(F_tilt, (e.a % 2 ? -1.0f : 1.0f) * 70);
      springs_.kick(F_earL, -60);
      springs_.kick(F_earR, -60);
      break;
  }
}

// ------------------------------------------------------------------------------------------------
// Battery / hunger
// ------------------------------------------------------------------------------------------------
void Life::updateBattery() {
  double t = time_;
  if (charging_) {
    // On the robot the charge level comes from the battery ADC (setBattery), not a simulation.
    if (t >= munchNextAt_) { sound(Sound::Munch); munchNextAt_ = t + 0.32; }
    hungerLevel_ = 0;
    return;
  }
  int level = battery_ < cfg.weakBelow ? 2 : (battery_ < cfg.hungryBelow ? 1 : 0);
  bool dropped = level != 0 && level != hungerLevel_;
  hungerLevel_ = level;
  if (level != 0 && t >= nextHungryPokeAt_) {
    nextHungryPokeAt_ = t + (dropped ? 0.1 : 22);
    if (!alarmActive_ && action_ < 0) {
      setMood(M("hungry"));
      say("hungry", 2.8f);
      double cyc = HUNGRY_CYCLE, toRumble = fmod(fmod(2.2 - fmod(time_, cyc), cyc) + cyc, cyc);
      after(toRumble, ev(EV_HUNGRY_GROWL));
      after(6.5, ev(EV_HUNGRY_END, level));
    }
  }
}

// ------------------------------------------------------------------------------------------------
// Idle life
// ------------------------------------------------------------------------------------------------
void Life::idle(double t, bool allowed) {
  const FaceState& cur = springs_.current;
  bool asleep = mood_ == M("sleeping") || cur.shut > 0.6f;

  if (t >= nextBlink_) {
    if (allowed && !asleep && cur.happy < 0.5f) {
      blinkUntil_ = t + 0.085;
      nextBlink_ = rnd_.next() < cfg.doubleBlinkChance ? t + 0.3 : t + rr(cfg.blinkMin, cfg.blinkMax) / energy_;
    } else nextBlink_ = t + 1;
  }
  if (t >= nextSaccade_) {
    sacX_ = (rnd_.next() - 0.5f) * 0.14f;
    sacY_ = (rnd_.next() - 0.5f) * 0.1f;
    nextSaccade_ = t + rr(cfg.saccadeMin, cfg.saccadeMax);
  }
  if (t >= nextGlance_) {
    if (allowed && !asleep && (!present() || rnd_.next() < 0.3f)) {
      glanceX_ = (rnd_.next() - 0.5f) * 1.5f;
      glanceY_ = (rnd_.next() - 0.5f) * 0.7f;
      glanceUntil_ = t + rr(0.5f, 1.3f);
      if (rnd_.next() < 0.35f && cur.happy < 0.5f) blinkUntil_ = t + 0.085;
    }
    nextGlance_ = t + rr(cfg.glanceMin, cfg.glanceMax) / energy_;
  }
  if (t >= nextEarFlick_) {
    if (allowed) {
      float r1 = rnd_.next();
      float r2 = rnd_.next();
      float v = (cat_ ? 420.0f : 400.0f) * (0.75f + r1 * 0.5f) * (asleep ? 0.45f : 1.0f) * (r2 < 0.6f ? -1.0f : 1.0f);
      springs_.kick(rnd_.next() < 0.5f ? F_earL : F_earR, v);
      if (rnd_.next() < 0.25f) springs_.kick(rnd_.next() < 0.5f ? F_earL : F_earR, v * 0.8f);
    }
    nextEarFlick_ = t + rr(cfg.earFlickMin, cfg.earFlickMax) * (cat_ ? 0.7f : 1.0f);
  }
  if (t >= nextSniff_) {
    if (allowed && !asleep && !isNegative(mood_)) sniff(2 + (int)floorf(rnd_.next() * 2));
    nextSniff_ = t + (mood_ == M("curious") ? rr(2.5f, 4.5f) : rr(cfg.sniffMin, cfg.sniffMax));
  }
  if (mood_ == M("curious") && t >= nextTwitch_) {
    float s = rnd_.next() < 0.5f ? -1.0f : 1.0f;
    twitchDX_ = s * rr(1.5f, 3);
    twitchUntil_ = t + 0.12;
    nextTwitch_ = t + rr(0.5f, 1.4f);
  }
  if (t >= nextIdleTilt_) {
    if (allowed && !noIdleTilt(mood_) && present()) {
      float dir = rnd_.next() < 0.5f ? -1.0f : 1.0f;
      float amt = rr(7, 12);
      double dur = rr(1.1f, 2.0f);
      override(F_tilt, dir * amt, dur);
      springs_.kick(dir < 0 ? F_earL : F_earR, -150);
    }
    nextIdleTilt_ = t + rr(6, 12);
  }
  if (mood_ == M("sleepy") && allowed && t >= nextYawn_) {
    playAction("yawn", true);
    nextYawn_ = t + rr(9, 16);
  } else if (mood_ != M("sleepy")) {
    nextYawn_ = nextYawn_ > t + 3 ? nextYawn_ : t + 3;
  }
  // ignored for a while: bored -> lonely -> sleepy -> asleep
  static const char* const DRIFT[] = {"bored", "loneliness", "sleepy", "sleeping"};
  if (allowed && !alarmActive_ && t >= holdUntil_ && t - lastInteraction_ > cfg.moodDrift && t - driftAt_ > cfg.moodDrift) {
    driftAt_ = t;
    bool inChain = false;
    for (const char* d : DRIFT) if (M(d) == mood_) inChain = true;
    if (driftStage_ < 3 && (mood_ == 0 || mood_ == M("happy") || inChain)) {
      driftStage_++;
      setMood(M(DRIFT[driftStage_]));
    }
  }
}

// ------------------------------------------------------------------------------------------------
// Per-frame update
// ------------------------------------------------------------------------------------------------
void Life::update(double dtIn) {
  double dtd = dtIn < 0 ? 0 : (dtIn > 0.1 ? 0.1 : dtIn);
  float dt = (float)dtd;
  dt_ = dt;
  time_ += dtd;
  double t = time_;

  if (nEvents_) {  // due events run in insertion order; new ones wait for the next frame
    LifeEvent due[kMaxEvents];
    int nd = 0, w = 0;
    for (int i = 0; i < nEvents_; i++) {
      if (events_[i].at <= t) due[nd++] = events_[i];
      else events_[w++] = events_[i];
    }
    nEvents_ = w;
    for (int i = 0; i < nd; i++) runEvent(due[i]);
  }
  if (alarmActive_ && t >= alarmNextAt_) {
    sound(Sound::AlarmBark, (float)alarmLevel_);
    say("alarm", 2.2f);
    springs_.kick(F_bob, -120.0f - 30.0f * alarmLevel_);
    springs_.kick(F_headSY, 1.4f);
    alarmLevel_ = alarmLevel_ + 1 > 3 ? 3 : alarmLevel_ + 1;
    alarmNextAt_ = t + fmax(1.4, 3.4 - alarmLevel_ * 0.6);
  }

  energy_ = (charging_ || battery_ >= cfg.hungryBelow) ? 1.0f : 0.35f + (battery_ / cfg.hungryBelow) * 0.65f;
  bool idleAllowed = true;
  if (action_ >= 0) {
    int n;
    const ActionDef* T = actionTable(&n);
    if (!T[action_].steps[actionIdx_].idle) idleAllowed = false;
  }
  idle(t, idleAllowed);
  updateBattery();

  const ExtrasDef& ex = spike::mood(mood_).extras;
  if (ex.hasEvery && t >= extrasAt_) {
    float r1 = rnd_.next();
    float r2 = rnd_.next();
    particles_.spawn(ex.everyType, ex.x + (r1 - 0.5f) * 2 * ex.spreadX, ex.y + (r2 - 0.5f) * 16, nullptr, rnd_);
    extrasAt_ = t + ex.everyS * rr(0.8f, 1.2f);
  }

  updateAction();

  // spring targets: mood -> gaze -> blink -> action -> events
  FaceState tg = moodTarget(mood_, cat_);
  bool follow = spike::mood(mood_).followsLook;
  float gx = tg.lookX, gy = tg.lookY;
  if (follow && present() && t >= glanceUntil_) { gx = lookX_ * 0.95f; gy = lookY_ * 0.8f; }
  else if (follow && t < glanceUntil_) { gx = glanceX_; gy = glanceY_; }
  tg.lookX = gx + sacX_;
  tg.lookY = gy + sacY_;
  if (t < blinkUntil_) { tg.blinkL = 1; tg.blinkR = 1; }
  if (action_ >= 0) {
    int n;
    const StepDef& st = actionTable(&n)[action_].steps[actionIdx_];
    for (int i = 0; i < st.nOver; i++) tg[st.over[i].field] = st.over[i].value;
    if (st.overIcon) tg.icon = st.icon;
  }
  for (int f = 0; f < F_COUNT; f++) {
    if (!overOn_[f]) continue;
    if (overUntil_[f] < t) overOn_[f] = false;
    else tg[f] = overV_[f];
  }
  FaceState& cur = springs_.current;
  if (tg.icon == Icon::None && cur.icon != Icon::None && cur.iconAmt > 0.03f) tg.icon = cur.icon;
  springs_.target = tg;
  cur.icon = tg.icon;
  springs_.step(dt);

  particles_.update(dtd);
}

// ------------------------------------------------------------------------------------------------
// The face state to draw this frame: springs + overlays.
// ------------------------------------------------------------------------------------------------
FaceState Life::faceParams() {
  FaceState p = springs_.current;
  float t = (float)time_, en = energy_;
  float tw = drawTime();
  float br = sinf(tw * 6.283185f / cfg.breathPeriod);
  p.bob += br * 1.6f * en;
  p.headSY += br * 0.006f * en;
  p.headSX -= br * 0.003f * en;

  applyMotion(p, mood_, tw, en);

  float tv = springs_.velocity[F_tilt], bv = springs_.velocity[F_bob];
  float sw = clampf(tv * 0.22f, -24, 24), bw = clampf(bv * 0.12f, -14, 14);
  p.earL += -sw + bw;
  p.earR += sw + bw;

  float sa = (float)(time_ - sniffStart_), win = 0.14f;
  if (sa >= 0 && sa < sniffCount_ * win) {
    float fr = fmodf(sa, win) / win, pulse = fr < 0.6f ? sinf(fr / 0.6f * 3.14159265f) : 0.0f;
    p.noseDY -= 3.6f * pulse;
    p.noseSX += 0.13f * pulse;
    p.noseSY -= 0.07f * pulse;
  }
  if (time_ < twitchUntil_) p.noseDX += twitchDX_;
  (void)t;
  if (charging_) {
    float ph = fmodf(tw * 3.2f, 1.0f);
    p.open = fmaxf(p.open, ph < 0.4f ? 0.45f : 0.06f);
    p.smile = fmaxf(p.smile, 0.5f);
  }
  applyActionOverlay(p);
  clampState(p);
  // speech mouth (brain_link.js applyOverlay, applied after the clamp like the page does)
  if (speech_ >= 0) {
    p.open = fmaxf(p.open, fminf(1.0f, speech_ * 0.62f));
    p.mouthO = fmaxf(p.mouthO, fminf(1.0f, speech_ * 0.28f));
  }
  return p;
}

// ------------------------------------------------------------------------------------------------
// Actions (actions.js runner)
// ------------------------------------------------------------------------------------------------
int Life::actionIndex(const char* name) {
  int n;
  const ActionDef* T = actionTable(&n);
  if (!name) return -1;
  for (int i = 0; i < n; i++) if (strcmp(T[i].name, name) == 0) return i;
  return -1;
}

bool Life::playAction(const char* name, bool autoStarted) { return playActionIndex(actionIndex(name), autoStarted); }

bool Life::playActionIndex(int idx, bool autoStarted) {
  int n;
  const ActionDef* T = actionTable(&n);
  if (idx < 0 || idx >= n) return false;
  int prev = action_ >= 0 ? actionPrevMood_ : mood_;
  if (!autoStarted) markInteraction();
  action_ = idx;
  actionIdx_ = 0;
  actionStepAt_ = time_;
  actionRestore_ = T[idx].restore;
  actionPrevMood_ = prev;
  serial_++;
  runStep();
  return true;
}

void Life::stopAction() {
  if (action_ >= 0) serial_++;
  action_ = -1;
}

void Life::runStep() {
  int n;
  const StepDef& s = actionTable(&n)[action_].steps[actionIdx_];
  if (s.mood) setMood(M(s.mood));
  kickList(s.kf, s.kv, s.nKick);
  if (cat_ && s.hasSoundCat) sound(s.soundCat, s.soundArg);
  else if (s.hasSound) sound(s.sound, s.soundArg);
  if (s.sniff) sniff(s.sniff);
  if (s.hasParticle) particles_.burst(s.particle, s.px, s.py, s.pcount ? s.pcount : 1, rnd_);
  if (s.capText) showCaption(s.capText, (float)s.hold + 0.8f);
  else if (s.capCategory) say((cat_ && s.capCatCategory) ? s.capCatCategory : s.capCategory, (float)s.hold + 1.2f);
}

void Life::updateAction() {
  if (action_ < 0) return;
  int n;
  const ActionDef& a = actionTable(&n)[action_];
  const StepDef& step = a.steps[actionIdx_];
  if (time_ - actionStepAt_ >= (step.hold > 0 ? step.hold : 0.5)) {
    actionIdx_++;
    if (actionIdx_ >= a.nSteps) {
      int back = actionRestore_ ? actionPrevMood_ : -1;
      stopAction();
      if (back >= 0) setMood(back);
      return;
    }
    actionStepAt_ = time_;
    runStep();
  }
}

void Life::applyActionOverlay(FaceState& p) {
  if (action_ < 0) return;
  int n;
  const StepDef& s = actionTable(&n)[action_].steps[actionIdx_];
  float age = (float)(time_ - actionStepAt_);
  for (int i = 0; i < s.nAdd; i++) p[s.add[i].field] += s.add[i].eval(age);
  for (int i = 0; i < s.nSet; i++) p[s.set[i].field] = s.set[i].eval(age);
}

const char* Life::actionLabel() const {
  if (action_ < 0) return nullptr;
  int n;
  return actionTable(&n)[action_].label;
}
const char* Life::actionName() const {
  if (action_ < 0) return nullptr;
  int n;
  return actionTable(&n)[action_].name;
}
int Life::actionStep() const { return action_ < 0 ? -1 : actionIdx_; }
float Life::actionStepAge() const { return action_ < 0 ? 0.0f : (float)(time_ - actionStepAt_); }

// ------------------------------------------------------------------------------------------------
// Comfort actions + brain link (brain_link.js)
// ------------------------------------------------------------------------------------------------
bool Life::comfort(const char* name) {
  if (!name) return false;
  if (strcmp(name, "snuggle") == 0) {
    springs_.kick(F_headSY, -0.9f); springs_.kick(F_headSX, 0.5f); springs_.kick(F_bob, 60);
    float s = rnd_.next() < 0.5f ? -1.0f : 1.0f;
    override(F_tilt, s * 9, 2.6);
    override(F_earBack, 0.6f, 2.6);
    override(F_blush, 0.6f, 2.6);
    override(F_happy, 0.35f, 2.6);
    sound(Sound::Sigh);
    particles_.burst(Particle::Heart, 240, 56, 1, rnd_);
    serial_++;
    return true;
  }
  if (strcmp(name, "slowWag") == 0) {
    after(0, ev(EV_WAG, 0));
    after(0.75, ev(EV_WAG, 1));
    after(1.5, ev(EV_WAG, 2));
    override(F_happy, 0.3f, 2.4);
    override(F_blush, 0.3f, 2.4);
    serial_++;
    return true;
  }
  return false;
}

void Life::setListening(Listen s) {
  if (s == Listen::Wake || s == Listen::Listening) {
    springs_.kick(F_earL, -220); springs_.kick(F_earR, -220); springs_.kick(F_headSY, 0.8f);
    override(F_earPerk, 1, s == Listen::Wake ? 1.2f : 5.0f);
    markInteraction();
  } else if (s == Listen::Thinking) {
    override(F_lookX, 0.45f, 1.6);
    override(F_lookY, -0.7f, 1.6);
    override(F_earPerk, 0.6f, 1.6);
  } else if (s == Listen::Idle) {
    clearOverride(F_earPerk);
  }
}

void Life::alarm(AlarmState s, int level) {
  if (s == AlarmState::Ringing) {
    if (!alarmActive_) alarmStart();
    if (level >= 0) { int l = level > 3 ? 3 : level; if (l > alarmLevel_) alarmLevel_ = l; }
  } else if (alarmActive_) {
    alarmActive_ = false;
    markInteraction();
    setMood(s == AlarmState::Snoozed ? M("sleepy") : M("proud"));
  }
}

}  // namespace spike
