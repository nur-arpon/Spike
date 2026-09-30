// spike_recipe.h -- Face Studio recipes (port of face_v2/recipe.js): the slot catalogue, the presets
// and the SPK1 share codes. Slot option order is PERMANENT (share codes store the index); the enums
// below mirror recipe.js SLOTS and a unit test checks them against the generated name table.
#pragma once
#include <stdint.h>
#include "spike_color.h"

namespace spike {

enum Frame : uint8_t { FRAME_FULL, FRAME_HEAD };
enum Pattern : uint8_t { PAT_PLAIN, PAT_PATCH, PAT_SPOTS, PAT_TABBY, PAT_CALICO, PAT_BLAZE, PAT_MASK, PAT_TUX };
enum Muzzle : uint8_t { MUZ_NONE, MUZ_ROUND, MUZ_WIDE };
enum EyeStyle : uint8_t { EYE_GLOSS, EYE_IRIS, EYE_CAT, EYE_GLOW };
enum EyeShape : uint8_t { SHAPE_OVAL, SHAPE_ROUND, SHAPE_ALMOND, SHAPE_SOFT, SHAPE_DROOP };
enum Lashes : uint8_t { LASH_NONE, LASH_FLICK, LASH_FULL };
enum Brows : uint8_t { BROW_NONE, BROW_DOTS, BROW_ARCS, BROW_BOLD };
enum Nose : uint8_t { NOSE_PUP, NOSE_BUTTON, NOSE_CAT, NOSE_HEART, NOSE_BEAN };
enum Mouth : uint8_t { MOUTH_PUP, MOUTH_OMEGA, MOUTH_SIMPLE };
enum Ears : uint8_t { EARS_FLOPPY, EARS_POINTY, EARS_ROUND, EARS_BEAR, EARS_BUNNY, EARS_FOLD, EARS_NONE };
enum Whiskers : uint8_t { WHISK_NONE, WHISK_SHORT, WHISK_LONG };
enum Accessory : uint8_t { ACC_NONE, ACC_BOW, ACC_BANDANA, ACC_GLASSES, ACC_HAT, ACC_FLOWER };
enum Freckles : uint8_t { FRECK_NO, FRECK_YES };
enum Side : uint8_t { SIDE_LEFT, SIDE_RIGHT };

static const int kNumSlots = 14;    // frame .. patternSide (share-code order)
static const int kNumColors = 16;   // bg .. accColor (share-code order)
static const int kNumNumbers = 5;   // eyeSize eyeSpacing mouthRest blush dim

struct Recipe {
  char name[41];
  // slots, in share-code order
  uint8_t frame, pattern, muzzle, eyeStyle, eyeShape, lashes, brows, nose, mouth, ears, whiskers, accessory,
      freckles, patternSide;
  // colours, in share-code order
  Rgb bg, fur, fur2, fur3, muzzleColor, eyeColor, irisColor, noseColor, lineColor, tongueColor, earColor,
      earInner, blushColor, browColor, whiskerColor, accColor;
  // numbers, in share-code order
  float eyeSize, eyeSpacing, mouthRest, blush, dim;

  uint8_t& slot(int i) { return (&frame)[i]; }
  uint8_t slot(int i) const { return (&frame)[i]; }
  Rgb& color(int i) { return (&bg)[i]; }
  Rgb color(int i) const { return (&bg)[i]; }
  float& number(int i) { return (&eyeSize)[i]; }
  float number(int i) const { return (&eyeSize)[i]; }
};

// Generated from recipe.js (spike_tables_gen.cpp).
extern const char* const kSlotKeys[kNumSlots];
extern const char* const* const kSlotOptions[kNumSlots];
extern const uint8_t kSlotOptionCount[kNumSlots];
extern const char* const kColorKeys[kNumColors];
extern const char* const kNumberKeys[kNumNumbers];
extern const float kNumberRange[kNumNumbers][2];

struct PresetDef {
  const char* id;
  bool cat;  // PRESET_KIND == 'cat'
  Recipe recipe;
  const char* code;  // SPK1 share code, as recipe.js toCode() makes it (test oracle)
};
extern const PresetDef kPresets[];
extern const int kNumPresets;

const Recipe& baseRecipe();              // Classic Pup (recipe.js BASE)
const PresetDef* findPreset(const char* id);
void clampNumbers(Recipe& r);            // numbers into their ranges (normalize)

// Share codes: SPK1-<slots>-<numbers>-<colours>. toCode writes into out (>= 128 chars).
void toCode(const Recipe& r, char* out, int outSize);
bool fromCode(const char* code, Recipe* out);  // false if invalid (out untouched)

// Slot helpers for JSON recipes (set_recipe with a recipe object): option name -> index, or -1.
int slotIndexByKey(const char* key);
int slotOptionIndex(int slot, const char* option);
int colorIndexByKey(const char* key);
int numberIndexByKey(const char* key);

}  // namespace spike
