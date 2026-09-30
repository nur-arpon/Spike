// spike_passkey.h -- the BLE pairing passkey drawn big over the face (PROTOCOL.md 11.1, v1.3).
//
// The face renderer has no text font, so the six digits are seven-segment digits built from
// rounded rectangles through the normal Gfx (same anti-aliased rasteriser as the face). The face
// task draws it as the last layer while a pairing is pending; `face_pc passkey` renders it to PNG.
#pragma once
#include <stdint.h>

#include "spike_gfx.h"

namespace spike {

// passkey: 0..999999 (always shown with 6 digits, leading zeros included).
// remaining: 0..1 of the 60 s pairing window still left (drawn as a shrinking bar).
void drawPasskeyOverlay(Gfx& g, uint32_t passkey, float remaining, float screenW, float screenH);

// One seven-segment digit (0..9) in the box x, y, w, h with segment thickness t.
void drawSevenSegDigit(Gfx& g, int digit, float x, float y, float w, float h, float t, Rgb c);

}  // namespace spike
