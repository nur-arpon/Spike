// spike_synth.cpp -- see spike_synth.h. Every sound below is sounds.js's recipe (same waves, ramps,
// gains, filters, delays). WebAudio's exponentialRampToValueAtTime is reproduced exactly; its
// band-limited oscillators are naive here (fine for these short, mostly low sounds).
#include "spike_synth.h"
#include <math.h>
#include <string.h>

namespace spike {

Synth::Voice* Synth::add() {
  if (n_ >= kMax) return nullptr;
  Voice& v = v_[n_++];
  memset(&v, 0, sizeof v);
  v.filt = F_NONE;
  return &v;
}

void Synth::setFilter(Voice& v, uint8_t type, float freq, float q) {
  v.filt = type;
  if (type == F_NONE) return;
  const float PI = 3.14159265f;
  float w0 = 2 * PI * freq / (float)rate_;
  if (w0 > PI * 0.98f) w0 = PI * 0.98f;
  float cs = cosf(w0), al = sinf(w0) / (2 * (q > 0.05f ? q : 0.05f));
  float b0, b1, b2, a0, a1, a2;
  if (type == F_LOW) { b0 = (1 - cs) / 2; b1 = 1 - cs; b2 = (1 - cs) / 2; }
  else if (type == F_HIGH) { b0 = (1 + cs) / 2; b1 = -(1 + cs); b2 = (1 + cs) / 2; }
  else { b0 = al; b1 = 0; b2 = -al; }  // band-pass, 0 dB peak
  a0 = 1 + al; a1 = -2 * cs; a2 = 1 - al;
  v.b0 = b0 / a0; v.b1 = b1 / a0; v.b2 = b2 / a0; v.a1 = a1 / a0; v.a2 = a2 / a0;
}

void Synth::tone(uint8_t wave, float from, float to, float dur, float gain, float delay, float attack, float release,
                 uint8_t filt, float filtFreq) {
  Voice* v = add();
  if (!v) return;
  if (release < 0) release = dur * 0.4f;
  v->wave = wave;
  v->env = 0;
  v->start = (int32_t)(delay * rate_);
  v->len = (int32_t)((dur + release + 0.05f) * rate_);
  v->f0 = from;
  v->f1 = to > 1 ? to : 1;
  v->fdur = dur;
  v->peak = gain;
  v->attack = attack;
  v->end = dur + release;
  if (filt != F_NONE) setFilter(*v, filt, filtFreq, 0.707f);
}

void Synth::noise(float dur, float filtFreq, float q, float gain, float delay, float attack, uint8_t filt) {
  Voice* v = add();
  if (!v) return;
  v->wave = NOISE;
  v->env = 0;
  v->start = (int32_t)(delay * rate_);
  v->len = (int32_t)((dur + 0.05f) * rate_);
  v->peak = gain;
  v->attack = attack;
  v->end = dur;
  setFilter(*v, filt, filtFreq, filt == F_BAND ? q : 0.707f);
}

void Synth::tremolo(uint8_t wave, float freq, float dur, float lfoRate, float lfoDepth, float gain, float delay) {
  Voice* v = add();
  if (!v) return;
  v->wave = wave;
  v->env = 1;
  v->start = (int32_t)(delay * rate_);
  v->len = (int32_t)((dur + 0.05f) * rate_);
  v->f0 = v->f1 = freq;
  v->fdur = dur;
  v->peak = gain;
  v->attack = 0.08f;
  v->end = dur;
  v->lfoRate = lfoRate;
  v->lfoDepth = lfoDepth;
}

void Synth::barkOnce(float delay, float pitch) {
  tone(SAW, pitch, pitch * 0.55f, 0.14f, 0.55f, delay, 0.012f, -1, F_LOW, 2200);
}

void Synth::play(Sound s, float arg) {
  switch (s) {
    case Sound::Yip: tone(TRIANGLE, 950, 620, 0.11f, 0.5f); break;
    case Sound::Bark: barkOnce(0, 300); barkOnce(0.18f, 320); break;
    case Sound::Whine:
      tone(SINE, 480, 720, 0.35f, 0.28f, 0, 0.012f, 0.2f);
      tone(SINE, 720, 420, 0.35f, 0.24f, 0.32f, 0.012f, 0.25f);
      break;
    case Sound::Sniff:
      noise(0.14f, 3200, 1.2f, 0.25f, 0, 0.01f);
      noise(0.1f, 3600, 1.2f, 0.2f, 0.16f);
      break;
    case Sound::Sniffs: {
      int n = arg > 0 ? (int)arg : 3;
      for (int i = 0; i < n; i++) noise(0.07f, 3000.0f + i * 250.0f, 1.3f, 0.2f, i * 0.14f, 0.008f);
      break;
    }
    case Sound::Sigh:
      noise(0.55f, 600, 0.9f, 0.22f, 0, 0.08f, F_LOW);
      tone(SINE, 220, 140, 0.55f, 0.18f, 0, 0.08f);
      break;
    case Sound::Snore:
      tremolo(TRIANGLE, 105, 0.7f, 22, 0.25f, 0.22f);
      noise(0.18f, 900, 0.9f, 0.15f, 0.68f);
      break;
    case Sound::Pant: {
      float sec = arg > 0 ? arg : 1.2f;
      int count = (int)floorf(sec / 0.22f + 0.5f);
      if (count < 1) count = 1;
      for (int i = 0; i < count; i++) noise(0.1f, 1500, 0.7f, 0.18f, i * 0.22f);
      break;
    }
    case Sound::Giggle: {
      static const float notes[5] = {520, 600, 560, 660, 700};
      for (int i = 0; i < 5; i++) tone(TRIANGLE, notes[i], notes[i] * 1.08f, 0.09f, 0.3f, i * 0.09f);
      break;
    }
    case Sound::AlarmBark: {
      int level = (int)arg;
      if (level < 0) level = 0;
      if (level > 3) level = 3;
      int count = 2 + level;
      float gap = 0.32f - level * 0.06f, pitch = 300.0f + level * 30.0f;
      for (int i = 0; i < count; i++) barkOnce(i * gap, pitch);
      break;
    }
    case Sound::Meow: {
      Voice* v = add();
      if (!v) break;
      v->wave = SAW; v->env = 2; v->start = 0; v->len = (int32_t)(0.5f * rate_);
      v->peak = 0.32f; v->attack = 0.05f; v->end = 0.46f;
      setFilter(*v, F_BAND, 900, 1.4f);
      break;
    }
    case Sound::Purr: tremolo(TRIANGLE, 90, arg > 0 ? arg : 1.2f, 26, 0.3f, 0.22f); break;
    case Sound::Hiss: noise(0.32f, 4500, 0.6f, 0.28f, 0, 0.005f, F_HIGH); break;
    case Sound::Trill: {
      Voice* v = add();
      if (!v) break;
      v->wave = SINE; v->env = 3; v->start = 0; v->len = (int32_t)(0.35f * rate_);
      v->f0 = v->f1 = 650; v->peak = 0.28f; v->attack = 0.03f; v->end = 0.32f;
      v->lfoRate = 22; v->lfoDepth = 60;
      break;
    }
    case Sound::Yawn:
      tone(SINE, 300, 140, 0.9f, 0.22f, 0, 0.15f, 0.3f);
      noise(0.7f, 500, 0.9f, 0.12f, 0, 0.2f, F_LOW);
      break;
    case Sound::Sneeze:
      noise(0.08f, 5500, 0.8f, 0.08f, 0, 0.02f);
      noise(0.12f, 3200, 0.7f, 0.42f, 0.1f, 0.004f);
      tone(TRIANGLE, 520, 210, 0.16f, 0.22f, 0.11f, 0.005f);
      break;
    case Sound::Hiccup: tone(SQUARE, 640, 900, 0.06f, 0.3f, 0, 0.004f, 0.03f); break;
    case Sound::ShiverChatter: {
      float sec = arg > 0 ? arg : 1.0f;
      int count = (int)floorf(sec / 0.09f + 0.5f);
      if (count < 1) count = 1;
      for (int i = 0; i < count; i++) noise(0.045f, 2400, 1.4f, 0.16f, i * 0.09f);
      break;
    }
    case Sound::Growl:
      tone(SAW, 95, 65, 0.7f, 0.14f, 0, 0.05f, -1, F_LOW, 300);
      noise(0.6f, 220, 0.9f, 0.18f, 0, 0.08f, F_LOW);
      break;
    case Sound::Munch:
      noise(0.07f, 900, 0.9f, 0.2f, 0, 0.005f, F_LOW);
      tone(SINE, 190, 120, 0.08f, 0.22f, 0, 0.005f);
      break;
    case Sound::Pop: tone(SINE, 900 + rnd01() * 300, 1600, 0.04f, 0.07f, 0, 0.002f, 0.02f); break;
    case Sound::Boop:
      tone(SINE, 720, 1500, 0.07f, 0.34f, 0, 0.004f, 0.03f);
      tone(SINE, 1500, 1050, 0.09f, 0.26f, 0.07f, 0.004f, 0.05f);
      break;
    case Sound::PatSqueak: tone(TRIANGLE, 820, 1180, 0.08f, 0.22f, 0, 0.006f, 0.04f); break;
    default: break;
  }
}

// WebAudio exponential ramps: 0.0001 -> peak over [0, attack], peak -> 0.0001 over [attack, end].
static inline float expEnv(float t, float peak, float attack, float end) {
  const float lo = 0.0001f;
  if (t < 0) return 0;
  if (t < attack) return lo * powf(peak / lo, t / attack);
  if (t < end) return peak * powf(lo / peak, (t - attack) / (end - attack));
  return 0;
}

void Synth::render(int16_t* out, int n) {
  if (n_ == 0) return;
  const float TAU = 6.28318531f;
  float inv = 1.0f / (float)rate_;
  float gain = volume_ * 32767.0f;
  for (int vi = 0; vi < n_; vi++) {
    Voice& v = v_[vi];
    for (int i = 0; i < n; i++) {
      int32_t k = v.pos - v.start;
      v.pos++;
      if (k < 0) continue;
      if (k >= v.len) break;
      float t = (float)k * inv;
      float f;
      if (v.env == 2) {  // meow: 380 -> 680 by 0.16 s, -> 340 by 0.42 s
        f = t < 0.16f ? 380.0f * powf(680.0f / 380.0f, t / 0.16f)
                      : (t < 0.42f ? 680.0f * powf(340.0f / 680.0f, (t - 0.16f) / 0.26f) : 340.0f);
      } else if (v.env == 3) {  // trill: FM vibrato
        f = v.f0 + v.lfoDepth * sinf(TAU * v.lfoRate * t);
      } else {
        f = t < v.fdur ? v.f0 * powf(v.f1 / v.f0, t / v.fdur) : v.f1;
      }
      float s;
      if (v.wave == NOISE) s = rnd01() * 2 - 1;
      else {
        v.phase += f * inv;
        v.phase -= floorf(v.phase);
        float ph = v.phase;
        switch (v.wave) {
          case SINE: s = sinf(TAU * ph); break;
          case TRIANGLE: s = 1 - 4 * fabsf(ph - 0.5f); s = -s; break;
          case SAW: s = 2 * ph - 1; break;
          default: s = ph < 0.5f ? 1.0f : -1.0f; break;
        }
      }
      if (v.filt != F_NONE) {  // transposed direct form II
        float y = v.b0 * s + v.z1;
        v.z1 = v.b1 * s - v.a1 * y + v.z2;
        v.z2 = v.b2 * s - v.a2 * y;
        s = y;
      }
      float g;
      if (v.env == 1) {  // tremolo: 0.0001 -> peak at 0.08, -> 0.0001 at end, + LFO on the gain
        g = expEnv(t, v.peak, v.attack, v.end) + v.lfoDepth * sinf(TAU * v.lfoRate * t);  // lfoGain adds to gain
      } else {
        g = expEnv(t, v.peak, v.attack, v.end);
      }
      int32_t o = out[i] + (int32_t)(s * g * gain);
      out[i] = (int16_t)(o > 32767 ? 32767 : (o < -32768 ? -32768 : o));
    }
  }
  // retire finished voices
  int w = 0;
  for (int vi = 0; vi < n_; vi++)
    if (v_[vi].pos - v_[vi].start < v_[vi].len) v_[w++] = v_[vi];
  n_ = w;
}

}  // namespace spike
