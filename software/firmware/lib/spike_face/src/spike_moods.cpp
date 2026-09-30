// spike_moods.cpp -- see spike_moods.h. The tables live in spike_tables_gen.cpp.
#include "spike_moods.h"
#include <math.h>
#include <string.h>

namespace spike {

static const char* const kParticleNames[] = {"heart", "zzz", "sweat", "sparkle", "confetti", "question",
                                             "exclaim", "steam", "music", "dizzyStar", "tear", "puff"};

Particle particleFromName(const char* s) {
  if (s)
    for (int i = 0; i < (int)Particle::Count; i++)
      if (strcmp(kParticleNames[i], s) == 0) return (Particle)i;
  return Particle::Sparkle;  // extras.js: unknown type draws as a sparkle
}

int moodIndex(const char* id) {
  if (!id) return -1;
  for (int i = 0; i < kNumMoods; i++)
    if (strcmp(kMoods[i].id, id) == 0) return i;
  return -1;
}

const MoodDef& mood(int idx) { return (idx >= 0 && idx < kNumMoods) ? kMoods[idx] : kMoods[0]; }

FaceState moodTarget(int idx, bool cat) {
  const MoodDef& m = mood(idx);
  FaceState p = faceDefaults();
  const FieldValue* fv = cat ? m.cat : m.dog;
  int n = cat ? m.nCat : m.nDog;
  for (int i = 0; i < n; i++) p[fv[i].field] = fv[i].value;
  p.icon = cat ? m.catIcon : m.dogIcon;
  return p;
}

float motionValue(const MotionDef& m, float t) {
  float w = t * m.freq * 6.283185f, ph = m.phase;
  if (m.kind == MOTION_RUMBLE) {
    float c = fmodf(t, HUNGRY_CYCLE);
    float env = (c >= 2.2f && c < 2.9f) ? sinf((c - 2.2f) / 0.7f * 3.14159265f) : 0.0f;
    return m.amp * env * sinf(w + ph);
  }
  if (m.kind == MOTION_JITTER) return m.amp * (0.6f * sinf(w + ph) + 0.4f * sinf(w * 2.37f + ph * 1.3f));
  if (m.kind == MOTION_HOP) return m.amp * fabsf(sinf(w * 0.5f + ph));
  return m.amp * sinf(w + ph);
}

void applyMotion(FaceState& p, int idx, float t, float energy) {
  const MoodDef& m = mood(idx);
  for (int i = 0; i < m.nMotion; i++) p[m.motion[i].field] += motionValue(m.motion[i], t) * energy;
}

}  // namespace spike
