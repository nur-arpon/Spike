// spike_extras.h -- pop-up particles (port of face_v2/extras.js): hearts, Zzz, sparkles, sweat, tears,
// "?", "!", anger steam, music notes, dizzy stars, confetti, sneeze puffs. Screen space (480 x 272),
// easeOutBack pop-in, fade over the last 35 % of life, colours adapt to light or dark fur.
#pragma once
#include <stdint.h>
#include "spike_gfx.h"
#include "spike_moods.h"

namespace spike {

// mulberry32, bit-exact with recipe.js seeded(): the behaviour engine and the particles draw from it,
// so a seeded C++ run replays a seeded JS run.
struct Rng {
  uint32_t a;
  explicit Rng(uint32_t seed = 1) : a(seed) {}
  float next() {
    a += 0x6D2B79F5u;
    uint32_t t = a;
    t = (t ^ (t >> 15)) * (t | 1u);
    t ^= t + (t ^ (t >> 7)) * (t | 61u);
    return (float)((double)(t ^ (t >> 14)) / 4294967296.0);
  }
  double nextD() {
    a += 0x6D2B79F5u;
    uint32_t t = a;
    t = (t ^ (t >> 15)) * (t | 1u);
    t ^= t + (t ^ (t >> 7)) * (t | 61u);
    return (double)(t ^ (t >> 14)) / 4294967296.0;
  }
};

struct SpawnOpts {
  bool hasVx = false, hasVy = false, hasRot = false;
  float vx = 0, vy = 0, rot = 0, scale = 1;
  double delay = 0, life = 0;
};

struct ParticleInst {
  Particle type;
  float x, y, vx, vy, g, rot, spin, scale, seed, ox, oy, orbitR, orbitSpeed;
  double age, life;  // double: expiry lands on frame boundaries (lives like 1.6 s), keep JS parity
  bool orbit;
  bool hasColor;
  Rgb color;
};

class ParticleSystem {
 public:
  static const int kMax = 24;  // extras.js uses 40 in the browser and says the ESP32 should use ~16-24
  ParticleInst list[kMax];
  int count = 0;
  uint32_t seq = 0;
  void clear() { count = 0; }
  void spawn(Particle type, float x, float y, const SpawnOpts* opts, Rng& rnd);
  void burst(Particle type, float x, float y, int count, Rng& rnd);
  void update(double dt);
  void draw(Gfx& G, float t, bool lightFur) const;
};

}  // namespace spike
