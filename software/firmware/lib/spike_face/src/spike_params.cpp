// spike_params.cpp -- see spike_params.h.
#include "spike_params.h"
#include <math.h>
#include <string.h>

namespace spike {

const FieldInfo kFields[F_COUNT] = {
#define SPIKE_X_INFO(n, def, lo, hi, k, d) {#n, (float)(def), (float)(lo), (float)(hi), (float)(k), (float)(d)},
    SPIKE_FIELDS(SPIKE_X_INFO)
#undef SPIKE_X_INFO
};

static_assert(sizeof(FaceState) >= sizeof(float) * F_COUNT, "FaceState layout");

int fieldIndex(const char* name) {
  if (!name) return -1;
  for (int i = 0; i < F_COUNT; i++)
    if (strcmp(kFields[i].name, name) == 0) return i;
  return -1;
}

static const char* const kIconNames[] = {"", "heart", "star", "spiral", "x", "battery", "question", "money"};

Icon iconFromName(const char* s) {
  if (!s) return Icon::None;
  for (int i = 1; i < 8; i++)
    if (strcmp(kIconNames[i], s) == 0) return (Icon)i;
  return Icon::None;
}
const char* iconName(Icon i) { return kIconNames[(int)i & 7]; }

FaceState faceDefaults() {
  FaceState p;
  for (int i = 0; i < F_COUNT; i++) p[i] = kFields[i].def;
  p.icon = Icon::None;
  return p;
}

void clampState(FaceState& p) {
  for (int i = 0; i < F_COUNT; i++) {
    float v = p[i];
    if (!(v == v)) { p[i] = kFields[i].def; continue; }
    if (v < kFields[i].lo) p[i] = kFields[i].lo;
    else if (v > kFields[i].hi) p[i] = kFields[i].hi;
  }
}

void Springs::init(const FaceState& initial) {
  current = initial;
  target = initial;
  for (int i = 0; i < F_COUNT; i++) velocity[i] = 0;
}

void Springs::step(float dt) {
  dt = clampf(dt, 0.0f, 0.1f);
  int sub = (int)ceilf(dt * 240.0f - 1e-4f);  // JS: ceil(dt / (1/240)); epsilon absorbs float noise
  if (sub < 1) sub = 1;
  float h = dt / (float)sub;
  for (int n = 0; n < sub; n++) {
    for (int i = 0; i < F_COUNT; i++) {
      float v = velocity[i] + (-kFields[i].k * (current[i] - target[i]) - kFields[i].d * velocity[i]) * h;
      velocity[i] = v;
      current[i] += v * h;
    }
  }
}

void Springs::snap(const FaceState& t) {
  setTarget(t);
  for (int i = 0; i < F_COUNT; i++) {
    current[i] = target[i];
    velocity[i] = 0;
  }
}

}  // namespace spike
