// spike_actions.h -- the scripted physical actions (port of face_v2/actions.js): face + pop-ups +
// sounds, each tagged with the body label the leg/wheel code reads.
#pragma once
#include <stdint.h>
#include "spike_life.h"

namespace spike {

// Per-frame overlay functions of `add` / `set` (actions.js jitter, decayShake, blinks and the inline ones).
enum OverlayKind : uint8_t { OV_CONST, OV_JITTER, OV_DECAY, OV_BLINKS, OV_SIN, OV_NEG_ABS_SIN, OV_ROLL };
struct Overlay {
  uint8_t field, kind;
  float p0, p1, p2;
  float eval(float age) const;
};

struct StepDef {
  double hold = 0.5;
  const char* mood = nullptr;
  bool hasSound = false, hasSoundCat = false;
  Sound sound = Sound::Yip, soundCat = Sound::Yip;
  float soundArg = 0;
  uint8_t sniff = 0;
  bool hasParticle = false;
  Particle particle = Particle::Sparkle;
  float px = 0, py = 0;
  uint8_t pcount = 1;
  const char* capCategory = nullptr;
  const char* capCatCategory = nullptr;
  const char* capText = nullptr;
  bool idle = true;
  FieldValue over[12];
  uint8_t nOver = 0;
  bool overIcon = false;
  Icon icon = Icon::None;
  uint8_t kf[5];
  float kv[5];
  uint8_t nKick = 0;
  Overlay add[3];
  uint8_t nAdd = 0;
  Overlay set[2];
  uint8_t nSet = 0;

  // builder helpers (tables are written like actions.js)
  StepDef& M(const char* m) { mood = m; return *this; }
  StepDef& H(double h) { hold = h; return *this; }
  StepDef& Snd(Sound s, float arg = 0) { hasSound = true; sound = s; soundArg = arg; return *this; }
  StepDef& SndCat(Sound s) { hasSoundCat = true; soundCat = s; return *this; }
  StepDef& Sniff(int n) { sniff = (uint8_t)n; return *this; }
  StepDef& P(Particle t, float x, float y, int n) { hasParticle = true; particle = t; px = x; py = y; pcount = (uint8_t)n; return *this; }
  StepDef& Cap(const char* cat, const char* catCat = nullptr) { capCategory = cat; capCatCategory = catCat; return *this; }
  StepDef& Text(const char* t) { capText = t; return *this; }
  StepDef& NoIdle() { idle = false; return *this; }
  StepDef& O(int f, float v) { if (nOver < 12) over[nOver++] = FieldValue{(uint8_t)f, v}; return *this; }
  StepDef& OIcon(Icon i) { overIcon = true; icon = i; return *this; }
  StepDef& K(int f, float v) { if (nKick < 5) { kf[nKick] = (uint8_t)f; kv[nKick] = v; nKick++; } return *this; }
  StepDef& A(int f, uint8_t kind, float a, float b = 0, float c = 0) { if (nAdd < 3) add[nAdd++] = Overlay{(uint8_t)f, kind, a, b, c}; return *this; }
  StepDef& S(int f, uint8_t kind, float a, float b = 0, float c = 0) { if (nSet < 2) set[nSet++] = Overlay{(uint8_t)f, kind, a, b, c}; return *this; }
};

struct ActionDef {
  const char* name;
  const char* label;  // body label (actions.js `label`)
  bool restore;
  StepDef steps[8];
  uint8_t nSteps;
};

const ActionDef* actionTable(int* count);  // all 19 actions.js entries

}  // namespace spike
