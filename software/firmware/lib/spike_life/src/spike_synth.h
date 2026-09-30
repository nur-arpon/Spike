// spike_synth.h -- the built-in synthesized sounds (port of face_v2/sounds.js): oscillators and filtered
// noise with WebAudio-style exponential envelopes, mixed into 16-bit mono PCM. No audio files.
// Platform-free: the screen board calls render() from its I2S task.
#pragma once
#include <stdint.h>
#include "spike_life.h"

namespace spike {

class Synth {
 public:
  explicit Synth(int sampleRate = 22050) : rate_(sampleRate) {}
  void setRate(int r) { rate_ = r; }
  int rate() const { return rate_; }
  void setVolume(float v) { volume_ = v < 0 ? 0 : (v > 1 ? 1 : v); }
  float volume() const { return volume_; }
  void play(Sound s, float arg = 0);   // schedules the sound's voices (sounds.js play*)
  void stopAll() { n_ = 0; }
  bool busy() const { return n_ > 0; }
  // Adds (mixes) n samples into out (saturating). Call with out pre-filled (speech) or zeroed.
  void render(int16_t* out, int n);

 private:
  enum Wave : uint8_t { SINE, TRIANGLE, SAW, SQUARE, NOISE };
  enum Filt : uint8_t { F_NONE, F_LOW, F_BAND, F_HIGH };
  struct Voice {
    uint8_t wave, filt, env;  // env 0: exp attack/decay (tone/noise), 1: tremolo, 2: meow, 3: trill
    int32_t start, len;       // samples from "now" / total length
    float f0, f1, fdur;       // frequency ramp f0 -> f1 over fdur seconds
    float peak, attack, end;  // envelope: 0.0001 -> peak at attack, -> 0.0001 at end (seconds)
    float lfoRate, lfoDepth;
    float phase, lfoPhase;
    // biquad
    float b0, b1, b2, a1, a2, z1, z2;
    int32_t pos;
  };
  static const int kMax = 32;
  Voice v_[kMax];
  int n_ = 0;
  int rate_;
  float volume_ = 0.6f;
  uint32_t noise_ = 0x12345678u;
  float rnd01() { noise_ ^= noise_ << 13; noise_ ^= noise_ >> 17; noise_ ^= noise_ << 5; return (float)(noise_ >> 8) / 16777216.0f; }
  Voice* add();
  void setFilter(Voice& v, uint8_t type, float freq, float q);
  void tone(uint8_t wave, float from, float to, float dur, float gain, float delay = 0, float attack = 0.012f,
            float release = -1, uint8_t filt = F_NONE, float filtFreq = 0);
  void noise(float dur, float filtFreq, float q, float gain, float delay = 0, float attack = 0.02f, uint8_t filt = F_BAND);
  void tremolo(uint8_t wave, float freq, float dur, float lfoRate, float lfoDepth, float gain, float delay = 0);
  void barkOnce(float delay, float pitch);
};

}  // namespace spike
