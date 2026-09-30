// spike_moods.h -- the mood table (port of face_v2/moods.js). The data (face poses for dog AND cat,
// motion, pop-up extras, gaze-follow flags) is generated from moods.js by tools/gen_tables.js, with
// Spicy's catify() already applied, so the firmware never re-implements or re-types the table.
#pragma once
#include <stdint.h>
#include "spike_params.h"

namespace spike {

enum class Particle : uint8_t { Heart, Zzz, Sweat, Sparkle, Confetti, Question, Exclaim, Steam, Music, DizzyStar,
                                Tear, Puff, Count };
Particle particleFromName(const char* s);

enum MotionKind : uint8_t { MOTION_SIN, MOTION_JITTER, MOTION_HOP, MOTION_RUMBLE };

struct FieldValue { uint8_t field; float value; };
struct MotionDef { uint8_t field; float amp, freq; uint8_t kind; float phase; };
struct ExtraEnter { Particle type; float x, y; uint8_t count; };
struct ExtrasDef {
  const ExtraEnter* enter; uint8_t nEnter;
  bool hasEvery; float everyS; Particle everyType; float x, y, spreadX;
};

struct MoodDef {
  const char* id;
  const char* label;
  const FieldValue* dog; uint8_t nDog; Icon dogIcon;
  const FieldValue* cat; uint8_t nCat; Icon catIcon;
  const MotionDef* motion; uint8_t nMotion;
  ExtrasDef extras;
  bool followsLook;
};

extern const MoodDef kMoods[];
extern const int kNumMoods;
static const float HUNGRY_CYCLE = 3.6f;

int moodIndex(const char* id);          // -1 if unknown
const MoodDef& mood(int idx);           // idx out of range -> neutral
// Full target face state for a mood (params defaults + the mood's partial pose).
FaceState moodTarget(int idx, bool cat);
float motionValue(const MotionDef& m, float t);
void applyMotion(FaceState& p, int idx, float t, float energy);

}  // namespace spike
