// spike_extras.cpp -- see spike_extras.h. Port of face_v2/extras.js.
#include "spike_extras.h"
#include <math.h>
#include <string.h>

namespace spike {

struct TypeDef { double life; float vy, vx, g, spin, size; bool orbit; };
static const TypeDef TYPES[(int)Particle::Count] = {
    {1.6, -48, 10, 0, 0, 1, false},    // heart
    {2.2, -26, 16, 0, 0, 1, false},    // zzz
    {1.1, 30, 20, 90, 0, 1, false},    // sweat
    {0.95, -14, 0, 0, 1.2f, 1, false}, // sparkle
    {1.8, -110, 60, 190, 7, 1, false}, // confetti
    {1.5, -14, 0, 0, 0, 1, false},     // question
    {1.1, -12, 0, 0, 0, 1, false},     // exclaim
    {1.1, -30, 22, 0, 0, 1, false},    // steam
    {1.7, -38, 14, 0, 0, 1, false},    // music
    {2.6, 0, 0, 0, 0, 1, true},        // dizzyStar
    {1.2, 40, 0, 160, 0, 1, false},    // tear
    {0.8, 10, 70, 0, 0, 1, false},     // puff
};

void ParticleSystem::spawn(Particle type, float x, float y, const SpawnOpts* opts, Rng& rnd) {
  const TypeDef& d = TYPES[(int)type < (int)Particle::Count ? (int)type : (int)Particle::Sparkle];
  SpawnOpts none;
  if (!opts) opts = &none;
  if (count >= kMax) {  // drop the oldest (list.shift())
    memmove(&list[0], &list[1], sizeof(ParticleInst) * (kMax - 1));
    count--;
  }
  seq++;
  float dir = rnd.next() < 0.5f ? -1.0f : 1.0f;
  ParticleInst& p = list[count++];
  p.type = type;
  p.x = x;
  p.y = y;
  p.vx = opts->hasVx ? opts->vx : d.vx * (0.6f + rnd.next() * 0.8f) * dir;
  p.vy = opts->hasVy ? opts->vy : d.vy * (0.8f + rnd.next() * 0.4f);
  p.g = d.g;
  p.age = -opts->delay;
  p.life = opts->life > 0 ? opts->life : d.life;
  p.rot = opts->hasRot ? opts->rot : (rnd.next() - 0.5f) * 0.6f;
  p.spin = d.spin * dir;
  p.scale = (opts->scale > 0 ? opts->scale : 1.0f) * (0.85f + rnd.next() * 0.3f);
  p.seed = (float)seq * 1.618f + rnd.next() * 6.0f;
  p.orbit = d.orbit;
  p.ox = x;
  p.oy = y;
  p.orbitR = 58;
  p.orbitSpeed = 2.6f;
  p.hasColor = false;
  p.color = 0;
}

void ParticleSystem::burst(Particle type, float x, float y, int n, Rng& rnd) {
  bool orbit = TYPES[(int)type].orbit;
  for (int i = 0; i < n; i++) {
    float a = ((float)i / (float)n) * TAU_F + rnd.next() * 0.5f, sp = 40.0f + rnd.next() * 30.0f;
    SpawnOpts o;
    if (!orbit) {
      o.hasVx = true; o.vx = cosf(a) * sp;
      o.hasVy = true; o.vy = sinf(a) * sp * 0.6f - 25.0f;
      o.delay = (double)i * 0.04;
    }
    spawn(type, x + cosf(a) * 6.0f, y + sinf(a) * 4.0f, &o, rnd);
    if (orbit) list[count - 1].seed = (float)i / (float)n * TAU_F;
  }
}

void ParticleSystem::update(double dt) {
  for (int i = count - 1; i >= 0; i--) {
    ParticleInst& p = list[i];
    p.age += dt;
    if (p.age >= p.life) {
      memmove(&list[i], &list[i + 1], sizeof(ParticleInst) * (count - i - 1));
      count--;
      continue;
    }
    if (p.age < 0 || p.orbit) continue;
    float fdt = (float)dt;
    p.vy += p.g * fdt;
    p.x += p.vx * fdt;
    p.y += p.vy * fdt;
    p.vx *= powf(0.35f, fdt);
    p.rot += p.spin * fdt;
  }
}

static float popScale(double age) {
  float e = fminf(1.0f, fmaxf(0.0f, (float)age / 0.24f)) - 1.0f;
  return 1.0f + 2.7f * e * e * e + 1.7f * e * e;
}
static float fade(const ParticleInst& p) {
  float f = (float)(p.age / p.life);
  return f < 0.65f ? 1.0f : fmaxf(0.0f, 1.0f - (f - 0.65f) / 0.35f);
}

static void heartShape(Gfx& G, float x, float y, float s, Rgb c, float a) {
  G.circle(x - 0.5f * s, y - 0.25f * s, 0.56f * s, c, a);
  G.circle(x + 0.5f * s, y - 0.25f * s, 0.56f * s, c, a);
  float p[10] = {x - 1.03f * s, y - 0.08f * s, x + 1.03f * s, y - 0.08f * s, x + 0.35f * s, y + 0.72f * s,
                 x, y + 0.98f * s, x - 0.35f * s, y + 0.72f * s};
  G.poly(p, 5, c, a);
}
static void starShape(Gfx& G, float x, float y, float ro, float ri, int n, float rot, Rgb c, float a) {
  float ctr[20];
  for (int i = 0; i < n; i++) {
    float a0 = rot + ((float)i + 0.5f) / (float)n * TAU_F;
    ctr[2 * i] = x + cosf(a0) * ri;
    ctr[2 * i + 1] = y + sinf(a0) * ri;
  }
  G.poly(ctr, n, c, a);
  for (int j = 0; j < n; j++) {
    float ang = rot + (float)j / n * TAU_F, al = rot + ((float)j - 0.5f) / n * TAU_F, ar = rot + ((float)j + 0.5f) / n * TAU_F;
    G.tri(x + cosf(ang) * ro, y + sinf(ang) * ro, x + cosf(al) * ri, y + sinf(al) * ri, x + cosf(ar) * ri,
          y + sinf(ar) * ri, c, a);
  }
}
static void dropShape(Gfx& G, float x, float y, float s, Rgb c, float a) {
  G.circle(x, y, 5 * s, c, a);
  G.tri(x - 4.6f * s, y - 2 * s, x + 4.6f * s, y - 2 * s, x, y - 12 * s, c, a);
}

static void drawOne(Gfx& G, const ParticleInst& p, float t, bool light) {
  float s = p.scale * (p.orbit ? 1.0f : popScale(p.age)), a = fade(p);
  float x = p.x, y = p.y;
  bool out = light;
  const Rgb W = 0xFFFFFF;
  switch (p.type) {
    case Particle::Heart:
      x += sinf((float)p.age * 4 + p.seed) * 5;
      if (out) heartShape(G, x, y, 10.5f * s, W, 0.85f * a);
      heartShape(G, x, y, 8.5f * s, p.hasColor ? p.color : 0xFF4D79, a);
      G.circle(x - 4.5f * s, y - 4 * s, 1.8f * s, W, 0.7f * a);
      break;
    case Particle::Zzz: {
      Rgb zc = p.hasColor ? p.color : (light ? 0x6C84F0 : 0xBFD4FF);
      float w = 7 * s * (1 + (float)p.age * 0.25f), h = w;
      float pts[8] = {x - w, y - h, x + w, y - h, x - w, y + h, x + w, y + h};
      if (out) G.polyline(pts, 4, 6 * s, W, 0.8f * a);
      G.polyline(pts, 4, 3 * s, zc, a);
      break;
    }
    case Particle::Sparkle: {
      float tw = 0.75f + 0.25f * sinf((float)p.age * 18 + p.seed);
      Rgb sc = p.hasColor ? p.color : (light ? 0xFFB020 : 0xFFE98A);
      if (out) starShape(G, x, y, 11 * s * tw, 4 * s, 4, p.rot, W, 0.8f * a);
      starShape(G, x, y, 8.5f * s * tw, 2.6f * s, 4, p.rot, sc, a);
      G.circle(x, y, 1.6f * s, W, a);
      break;
    }
    case Particle::DizzyStar: {
      float ang = p.seed + t * p.orbitSpeed;
      x = p.ox + cosf(ang) * p.orbitR;
      y = p.oy + sinf(ang) * p.orbitR * 0.32f;
      float ds = p.scale * (0.8f + 0.2f * sinf(ang));
      if (out) starShape(G, x, y, 12 * ds, 6 * ds, 5, t * 3, W, 0.85f * a);
      starShape(G, x, y, 9.5f * ds, 4.2f * ds, 5, t * 3, p.hasColor ? p.color : 0xFFC21F, a);
      break;
    }
    case Particle::Sweat:
      if (out) dropShape(G, x, y, s * 1.3f, W, 0.85f * a);
      dropShape(G, x, y, s, p.hasColor ? p.color : 0x7CC8F8, a);
      break;
    case Particle::Tear:
      dropShape(G, x, y, s * 0.9f, p.hasColor ? p.color : 0x7CC8F8, a);
      break;
    case Particle::Question: {
      Rgb qc = p.hasColor ? p.color : (light ? 0x5B5FE8 : 0xC9CCFF);
      float wob = sinf((float)p.age * 7) * 0.15f, lw = 4.2f * s;
      G.save();
      G.translate(x, y);
      G.rotate(wob);
      if (out) {
        G.arc(0, -7 * s, 7 * s, PI_F * 1.05f, PI_F * 2.3f, lw + 3.5f, W, 0.85f * a);
        G.line(1.5f * s, -1 * s, 0, 5 * s, lw + 3.5f, W, 0.85f * a);
        G.circle(0, 12 * s, lw * 0.6f + 1.8f, W, 0.85f * a);
      }
      G.arc(0, -7 * s, 7 * s, PI_F * 1.05f, PI_F * 2.3f, lw, qc, a);
      G.line(1.5f * s, -1 * s, 0, 5 * s, lw, qc, a);
      G.circle(0, 12 * s, lw * 0.6f, qc, a);
      G.restore();
      break;
    }
    case Particle::Exclaim: {
      Rgb ec = p.hasColor ? p.color : 0xFF8A00;
      if (out) {
        G.rrect(x - 4.8f * s, y - 16.5f * s, 9.6f * s, 20 * s, 4.8f * s, W, 0.85f * a);
        G.circle(x, y + 9 * s, 5 * s, W, 0.85f * a);
      }
      G.rrect(x - 3 * s, y - 15 * s, 6 * s, 17 * s, 3 * s, ec, a);
      G.circle(x, y + 9 * s, 3.2f * s, ec, a);
      break;
    }
    case Particle::Steam: {
      float grow = 1 + (float)p.age * 1.4f;
      Rgb stc = p.hasColor ? p.color : (light ? 0xA7AFC2 : 0xE6E9F0);
      G.circle(x, y, 6 * s * grow, stc, 0.9f * a);
      G.circle(x + 6 * s * grow, y - 3 * s, 4.6f * s * grow, stc, 0.9f * a);
      G.circle(x - 5 * s * grow, y - 2 * s, 4 * s * grow, stc, 0.9f * a);
      break;
    }
    case Particle::Music: {
      Rgb mc = p.hasColor ? p.color : 0x8E6CFF;
      x += sinf((float)p.age * 5 + p.seed) * 4;
      if (out) {
        G.circle(x, y, 6.5f * s, W, 0.85f * a);
        G.rrect(x + 1.8f * s, y - 18 * s, 5.4f * s, 19 * s, 2, W, 0.85f * a);
      }
      G.circle(x, y, 4.6f * s, mc, a);
      G.rrect(x + 3 * s, y - 16.5f * s, 2.6f * s, 17 * s, 1, mc, a);
      G.tri(x + 5.6f * s, y - 16.5f * s, x + 12 * s, y - 12.5f * s, x + 5.6f * s, y - 9 * s, mc, a);
      break;
    }
    case Particle::Confetti: {
      static const Rgb pal[5] = {0xFF5C77, 0xFFC21F, 0x4FC3F7, 0x66D17A, 0xB388FF};
      Rgb cc = p.hasColor ? p.color : pal[((int)floorf(p.seed * 7)) % 5];
      G.save();
      G.translate(x, y);
      G.rotate(p.rot);
      G.rrect(-3.5f * s, -6 * s, 7 * s, 12 * s, 1.5f, cc, a);
      G.restore();
      break;
    }
    case Particle::Puff: {
      float pg = 1 + (float)p.age * 2.2f;
      G.circle(x, y, 7 * s * pg, light ? W : 0xDDE3EA, 0.8f * a);
      G.circle(x + 7 * s * pg, y + 2, 5 * s * pg, light ? W : 0xDDE3EA, 0.7f * a);
      break;
    }
    default:
      break;
  }
}

void ParticleSystem::draw(Gfx& G, float t, bool lightFur) const {
  Tag prev = G.tag(Tag::Particle);
  for (int i = 0; i < count; i++) {
    if (list[i].age < 0) continue;
    drawOne(G, list[i], t, lightFur);
  }
  G.tag(prev);
}

}  // namespace spike
