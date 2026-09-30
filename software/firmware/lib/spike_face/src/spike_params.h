// spike_params.h -- the parametric FACE STATE and its spring physics (port of face_v2/params.js).
//
// The face state is a flat struct of floats (plus the discrete `icon`). The field list, defaults,
// safety ranges and spring tuning come from face_v2 itself through tools/gen_tables.js, which writes
// spike_fields.inc -- nothing here is re-typed by hand.
#pragma once
#include <stdint.h>
#include "spike_fields.inc"  // SPIKE_FIELDS(X): X(name, default, lo, hi, k, d)

namespace spike {

enum Field : uint8_t {
#define SPIKE_X_ENUM(n, def, lo, hi, k, d) F_##n,
  SPIKE_FIELDS(SPIKE_X_ENUM)
#undef SPIKE_X_ENUM
  F_COUNT
};

// Eye icons (params.js DISCRETE.icon). Order is internal only.
enum class Icon : uint8_t { None, Heart, Star, Spiral, X, Battery, Question, Money };
Icon iconFromName(const char* s);
const char* iconName(Icon i);

struct FaceState {
#define SPIKE_X_MEMBER(n, def, lo, hi, k, d) float n;
  SPIKE_FIELDS(SPIKE_X_MEMBER)
#undef SPIKE_X_MEMBER
  Icon icon;
  // Field access by index (the members above are consecutive floats).
  float& operator[](int i) { return reinterpret_cast<float*>(this)[i]; }
  float operator[](int i) const { return reinterpret_cast<const float*>(this)[i]; }
};

struct FieldInfo {
  const char* name;
  float def, lo, hi;  // default and final safety range
  float k, d;         // spring stiffness and damping
};
extern const FieldInfo kFields[F_COUNT];
int fieldIndex(const char* name);  // -1 if unknown

inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }
inline float lerpf(float a, float b, float t) { return a + (b - a) * t; }
inline float smoothstepf(float e0, float e1, float x) {
  float t = clampf((x - e0) / (e1 - e0), 0.0f, 1.0f);
  return t * t * (3.0f - 2.0f * t);
}

FaceState faceDefaults();
void clampState(FaceState& p);  // params.js clampState (NaN -> default)

// Damped springs, one per field (semi-implicit Euler, sub-stepped at 240 Hz).
struct Springs {
  FaceState current;
  FaceState target;
  float velocity[F_COUNT];
  void init(const FaceState& initial);
  void setTarget(const FaceState& t) { target = t; current.icon = t.icon; }
  void kick(int field, float v) { if (field >= 0 && field < F_COUNT) velocity[field] += v; }
  void step(float dt);
  void snap(const FaceState& t);
};

}  // namespace spike
