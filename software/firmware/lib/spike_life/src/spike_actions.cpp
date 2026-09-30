// spike_actions.cpp -- the actions.js table, step for step. Keep it in sync with face_v2/actions.js
// (test/life_trace compares a seeded run of both engines).
#include "spike_actions.h"
#include <math.h>

namespace spike {

float Overlay::eval(float a) const {
  const float TAU = 6.2832f;
  switch (kind) {
    case OV_CONST: return p0;
    case OV_JITTER: return p0 * (0.6f * sinf(a * p1 * TAU) + 0.4f * sinf(a * p1 * 2.37f * TAU));
    case OV_DECAY: return p0 * sinf(a * p1 * TAU) * fmaxf(0.0f, 1.0f - a / p2);
    case OV_BLINKS: return ((a >= p0 && a < p0 + 0.08f) || (a >= p1 && a < p1 + 0.08f)) ? 1.0f : 0.0f;
    case OV_SIN: return p0 * sinf(a * p1 + p2);
    case OV_NEG_ABS_SIN: return -fabsf(sinf(a * p1)) * p0;
    case OV_ROLL: {
      float f = fminf(1.0f, a / p0);
      return 360.0f * (f < 0.5f ? 2 * f * f : 1 - powf(-2 * f + 2, 2) / 2);
    }
  }
  return 0;
}

static StepDef St() { return StepDef(); }

static ActionDef A(const char* name, const char* label, bool restore) {
  ActionDef a;
  a.name = name;
  a.label = label;
  a.restore = restore;
  a.nSteps = 0;
  return a;
}
static void add(ActionDef& a, const StepDef& s) { if (a.nSteps < 8) a.steps[a.nSteps++] = s; }

static int build(ActionDef* T) {
  int n = 0;
  using P = Particle;
  {  // wakeUp
    ActionDef a = A("wakeUp", "wake-up", false);
    add(a, St().M("sleeping").H(0.6).NoIdle());
    add(a, St().H(1.3).Snd(Sound::Yawn).NoIdle().O(F_shut, 0.85f).O(F_mouthO, 1).O(F_open, 0.95f).O(F_headSY, 1.12f)
               .O(F_headSX, 0.93f).O(F_tilt, -7).O(F_earPerk, 1).O(F_smile, 0.2f));
    add(a, St().M("sleepy").H(0.45).O(F_headSY, 0.95f).O(F_headSX, 1.04f));
    add(a, St().M("neutral").H(0.5).S(F_blinkL, OV_BLINKS, 0.05f, 0.28f).S(F_blinkR, OV_BLINKS, 0.05f, 0.28f));
    add(a, St().H(0.4).A(F_shakeX, OV_DECAY, 6, 7, 0.4f).A(F_tilt, OV_DECAY, 5, 7, 0.4f).K(F_earL, 300).K(F_earR, -300));
    add(a, St().M("happy").H(0.9).Snd(Sound::Yip).SndCat(Sound::Meow).Cap("greeting").P(P::Sparkle, 240, 50, 4)
               .K(F_bob, -140).K(F_headSY, 1.4f));
    T[n++] = a;
  }
  {  // fallAsleep
    ActionDef a = A("fallAsleep", "fall-asleep", false);
    add(a, St().M("sleepy").H(1.0).Snd(Sound::Sigh));
    add(a, St().M("sleepy").H(1.0).NoIdle().O(F_lidTL, 0.82f).O(F_lidTR, 0.82f).O(F_tilt, 13).O(F_bob, 6));
    add(a, St().H(0.35).NoIdle().O(F_lidTL, 0.25f).O(F_lidTR, 0.25f).O(F_tilt, 1).O(F_bob, -1).O(F_eyeScale, 1.08f).K(F_headSY, 1.2f));
    add(a, St().M("sleepy").H(1.0).NoIdle().O(F_lidTL, 0.86f).O(F_lidTR, 0.86f).O(F_tilt, 10).O(F_bob, 4));
    add(a, St().M("sleeping").H(1.8).Snd(Sound::Snore).Cap("sleepy").P(P::Zzz, 330, 70, 1));
    T[n++] = a;
  }
  {  // napping
    ActionDef a = A("napping", "nap", false);
    add(a, St().M("sleeping").H(1.6).Snd(Sound::Snore).P(P::Zzz, 330, 70, 1));
    add(a, St().M("sleeping").H(0.7).K(F_earL, 260).O(F_smile, 0.6f));
    add(a, St().M("sleeping").H(1.4).Snd(Sound::Snore).P(P::Zzz, 330, 70, 1));
    T[n++] = a;
  }
  {  // dozing
    ActionDef a = A("dozing", "doze", false);
    add(a, St().M("sleepy").H(0.6));
    add(a, St().H(0.9).NoIdle().O(F_tilt, 14).O(F_bob, 7).O(F_lidTL, 0.92f).O(F_lidTR, 0.92f));
    add(a, St().H(0.35).NoIdle().O(F_tilt, 0).O(F_bob, -2).O(F_lidTL, 0.15f).O(F_lidTR, 0.15f).O(F_eyeScale, 1.1f)
               .O(F_browY, 0.8f).K(F_headSY, 1.5f).K(F_earL, -200).K(F_earR, -200));
    add(a, St().M("sleepy").H(0.7));
    add(a, St().H(1.0).NoIdle().O(F_tilt, -12).O(F_bob, 7).O(F_lidTL, 0.92f).O(F_lidTR, 0.92f));
    add(a, St().H(0.35).NoIdle().O(F_tilt, 0).O(F_bob, -2).O(F_lidTL, 0.15f).O(F_lidTR, 0.15f).O(F_eyeScale, 1.1f).K(F_headSY, 1.5f));
    add(a, St().M("sleepy").H(0.8).Text("I'm awake. Totally awake."));
    T[n++] = a;
  }
  {  // deepSleepDreams
    ActionDef a = A("deepSleepDreams", "dream", false);
    add(a, St().M("sleeping").H(2.0).Snd(Sound::Snore).P(P::Zzz, 330, 70, 1));
    add(a, St().M("sleeping").H(1.8).Snd(Sound::Whine).Cap("sleepy").P(P::Heart, 330, 70, 1).O(F_smile, 0.8f).O(F_blush, 0.5f)
               .A(F_earL, OV_JITTER, 10, 3).A(F_earR, OV_JITTER, 10, 3.3f).A(F_noseDY, OV_JITTER, 1.2f, 5));
    add(a, St().M("sleeping").H(2.0).Snd(Sound::Snore).P(P::Zzz, 330, 70, 1));
    T[n++] = a;
  }
  {  // tripBump
    ActionDef a = A("tripBump", "trip", false);
    add(a, St().H(0.25).NoIdle().O(F_eyeScale, 1.22f).O(F_mouthO, 1).O(F_open, 0.55f).O(F_browY, 1.1f).K(F_headSY, -1.8f));
    add(a, St().H(0.22).NoIdle().O(F_tilt, -22).O(F_bob, 10).OIcon(Icon::X).O(F_iconAmt, 1).K(F_bob, 90));
    add(a, St().M("dizzy").H(1.3).Snd(Sound::Whine).P(P::DizzyStar, 240, 40, 3).O(F_tilt, -8));
    add(a, St().M("embarrassed").H(1.6).Cap("trip"));
    T[n++] = a;
  }
  {  // sneeze
    ActionDef a = A("sneeze", "sneeze", true);
    add(a, St().H(0.5).NoIdle().O(F_scrunch, 0.6f).O(F_lidTL, 0.3f).O(F_lidTR, 0.3f).O(F_mouthO, 0.5f).O(F_open, 0.25f)
               .A(F_noseDY, OV_JITTER, 1.5f, 9));
    add(a, St().H(0.45).NoIdle().O(F_scrunch, 1).O(F_lidTL, 0.6f).O(F_lidTR, 0.6f).O(F_mouthO, 0.85f).O(F_open, 0.6f)
               .O(F_tilt, -8).O(F_bob, -6).O(F_headSY, 1.09f));
    add(a, St().H(0.3).NoIdle().Snd(Sound::Sneeze).O(F_shut, 1).O(F_scrunch, 0.2f).O(F_mouthO, 0).O(F_open, 0.45f)
               .O(F_smile, 0.3f).O(F_tilt, 6).O(F_bob, 7).O(F_headSY, 0.86f).O(F_headSX, 1.1f).K(F_headSY, -2.5f).K(F_bob, 150)
               .P(P::Puff, 268, 178, 3));
    add(a, St().H(0.5).NoIdle().O(F_shut, 0.25f).A(F_shakeX, OV_DECAY, 7, 8, 0.5f).A(F_tilt, OV_DECAY, 4, 8, 0.5f)
               .K(F_earL, 300).K(F_earR, -300));
    add(a, St().H(0.7).Text("Bless me!").O(F_happy, 0.8f).O(F_smile, 0.8f));
    T[n++] = a;
  }
  {  // hiccup
    ActionDef a = A("hiccup", "hiccup", true);
    StepDef hic = St().H(0.4).Snd(Sound::Hiccup).K(F_headSY, 2.4f).K(F_bob, -110).O(F_eyeScale, 1.14f).O(F_mouthO, 0.7f).O(F_open, 0.25f);
    add(a, St().H(0.45));
    add(a, hic);
    add(a, St().H(0.45));
    add(a, hic);
    add(a, St().H(0.4));
    StepDef last = hic;
    last.H(0.9).O(F_blush, 0.6f).Cap("selfdep");
    add(a, last);
    T[n++] = a;
  }
  {  // shiver
    ActionDef a = A("shiver", "shiver", true);
    add(a, St().H(1.9).Snd(Sound::ShiverChatter, 1.8f).Text("B-b-brr, c-cold!").O(F_lidTilt, -0.4f).O(F_earBack, 0.7f)
               .O(F_smile, -0.2f).O(F_wobble, 1).O(F_blush, 0.45f).O(F_mouthW, 0.7f).O(F_eyeDY, 2)
               .A(F_shakeX, OV_JITTER, 2.6f, 13).A(F_tilt, OV_JITTER, 1.5f, 11));
    T[n++] = a;
  }
  {  // pant
    ActionDef a = A("pant", "pant", true);
    add(a, St().H(2.3).Snd(Sound::Pant, 2.1f).O(F_open, 0.75f).O(F_tongue, 1).O(F_pant, 1).O(F_smile, 0.85f).O(F_lidTL, 0.18f)
               .O(F_lidTR, 0.18f).O(F_sweat, 0.7f).A(F_bob, OV_SIN, 1.4f, 17, 0));
    T[n++] = a;
  }
  {  // tailWagDance
    ActionDef a = A("tailWagDance", "happy-dance", false);
    add(a, St().M("joy").H(1.2).Snd(Sound::Giggle).SndCat(Sound::Trill).P(P::Music, 240, 50, 2)
               .A(F_tilt, OV_SIN, 9, 9, 0).A(F_bob, OV_NEG_ABS_SIN, 6, 9).A(F_shakeX, OV_SIN, 7, 9, 0));
    add(a, St().M("joy").H(1.2).P(P::Heart, 240, 50, 2)
               .A(F_tilt, OV_SIN, 9, 9, 0).A(F_bob, OV_NEG_ABS_SIN, 6, 9).A(F_shakeX, OV_SIN, 7, 9, 0));
    T[n++] = a;
  }
  {  // zoomies
    ActionDef a = A("zoomies", "zoomies", false);
    add(a, St().M("excited").H(2.3).Snd(Sound::Bark).SndCat(Sound::Trill).Cap("selfdep").O(F_pant, 1).O(F_tongue, 1)
               .O(F_open, 0.8f).P(P::Confetti, 240, 70, 6)
               .A(F_shakeX, OV_SIN, 10, 12, 0).A(F_tilt, OV_SIN, 14, 12, 0).A(F_lookX, OV_SIN, 1, 12, 1));
    T[n++] = a;
  }
  {  // headTilt
    ActionDef a = A("headTilt", "head-tilt", true);
    add(a, St().M("curious").H(1.3).O(F_tilt, 18).K(F_earL, -220).Text("Hm?"));
    add(a, St().M("curious").H(1.1).O(F_tilt, -12).K(F_earR, 220));
    T[n++] = a;
  }
  {  // sniffAround
    ActionDef a = A("sniffAround", "sniff", true);
    add(a, St().M("curious").H(0.9).Sniff(3).O(F_lookX, -0.85f).O(F_lookY, 0.6f).O(F_tilt, -7));
    add(a, St().M("curious").H(0.9).Sniff(3).O(F_lookX, 0.85f).O(F_lookY, 0.6f).O(F_tilt, 7));
    add(a, St().M("curious").H(0.9).Sniff(2).O(F_lookX, 0).O(F_lookY, -0.2f).O(F_eyeScale, 1.1f).O(F_browY, 0.9f)
               .P(P::Exclaim, 300, 40, 1));
    T[n++] = a;
  }
  {  // beggingAction
    ActionDef a = A("beggingAction", "beg", false);
    add(a, St().M("begging").H(2.3).Snd(Sound::Whine).Cap("tease").A(F_tilt, OV_SIN, 4, 2.5f, 0));
    T[n++] = a;
  }
  {  // rollOver
    ActionDef a = A("rollOver", "roll-over", false);
    add(a, St().M("playful").H(0.3).K(F_headSY, -1.2f).O(F_headSY, 0.95f));
    add(a, St().H(1.0).NoIdle().O(F_happy, 1).O(F_open, 0.5f).O(F_tongue, 0.85f).S(F_tilt, OV_ROLL, 1.0f));
    add(a, St().M("cuddly").H(1.0).Snd(Sound::Yip).SndCat(Sound::Meow).Cap("tease").K(F_headSY, 1.2f));
    T[n++] = a;
  }
  {  // playBow
    ActionDef a = A("playBow", "play-bow", false);
    add(a, St().M("playful").H(1.2).Snd(Sound::Yip).Text("Wanna play?").O(F_bob, 12).O(F_headSY, 0.92f).O(F_headSX, 1.06f)
               .O(F_earPerk, 1.2f).O(F_lookY, -0.5f).O(F_tilt, 0));
    add(a, St().M("excited").H(0.9).K(F_bob, -220).K(F_headSY, 2));
    T[n++] = a;
  }
  {  // yawn
    ActionDef a = A("yawn", "yawn", true);
    add(a, St().H(1.4).Snd(Sound::Yawn).O(F_mouthO, 1).O(F_open, 1).O(F_shut, 0.75f).O(F_tilt, -5).O(F_headSY, 1.08f)
               .O(F_earPerk, -0.3f));
    add(a, St().H(0.4).O(F_shut, 0.3f));
    T[n++] = a;
  }
  {  // boop
    ActionDef a = A("boop", "boop", true);
    add(a, St().H(0.6).NoIdle().Snd(Sound::Boop).K(F_noseSY, -10).K(F_noseSX, 7).K(F_headSY, -1.3f).K(F_earL, -200)
               .K(F_earR, -200).O(F_cross, 1).O(F_mouthO, 0.75f).O(F_open, 0.35f).O(F_eyeScale, 1.12f).O(F_browY, 0.9f)
               .O(F_earPerk, 1).OIcon(Icon::None).O(F_iconAmt, 0));
    add(a, St().M("laughing").H(1.5).Snd(Sound::Giggle).SndCat(Sound::Trill).Cap("boop", "catboop").P(P::Heart, 240, 56, 3)
               .O(F_blush, 0.9f));
    T[n++] = a;
  }
  return n;
}

const ActionDef* actionTable(int* count) {
  static ActionDef T[20];
  static int n = build(T);
  if (count) *count = n;
  return T;
}

}  // namespace spike
