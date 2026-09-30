// spike_recipe.cpp -- see spike_recipe.h.
#include "spike_recipe.h"
#include <math.h>
#include <string.h>
#include <stdio.h>

namespace spike {

const Recipe& baseRecipe() { return kPresets[0].recipe; }  // generator emits 'classic' first

const PresetDef* findPreset(const char* id) {
  if (!id) return nullptr;
  for (int i = 0; i < kNumPresets; i++)
    if (strcmp(kPresets[i].id, id) == 0) return &kPresets[i];
  return nullptr;
}

void clampNumbers(Recipe& r) {
  for (int i = 0; i < kNumNumbers; i++) {
    float v = r.number(i);
    if (!(v == v)) v = baseRecipe().number(i);
    if (v < kNumberRange[i][0]) v = kNumberRange[i][0];
    if (v > kNumberRange[i][1]) v = kNumberRange[i][1];
    r.number(i) = v;
  }
}

static char b36(int v) { return (char)(v < 10 ? '0' + v : 'a' + (v - 10)); }
static int fromB36(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'z') return c - 'a' + 10;
  if (c >= 'A' && c <= 'Z') return c - 'A' + 10;
  return -1;
}

void toCode(const Recipe& r, char* out, int outSize) {
  char buf[160];
  int n = 0;
  memcpy(buf, "SPK1-", 5);
  n = 5;
  for (int i = 0; i < kNumSlots; i++) buf[n++] = b36(r.slot(i) < kSlotOptionCount[i] ? r.slot(i) : 0);
  buf[n++] = '-';
  for (int i = 0; i < kNumNumbers; i++) {
    float lo = kNumberRange[i][0], hi = kNumberRange[i][1];
    int q = (int)floor((double)(r.number(i) - lo) / (double)(hi - lo) * 35.0 + 0.5);
    if (q < 0) q = 0;
    if (q > 35) q = 35;
    buf[n++] = b36(q);
  }
  buf[n++] = '-';
  for (int i = 0; i < kNumColors; i++) {
    snprintf(buf + n, sizeof(buf) - n, "%06X", (unsigned)(r.color(i) & 0xFFFFFF));
    n += 6;
  }
  buf[n] = 0;
  if (outSize > 0) {
    strncpy(out, buf, (size_t)outSize - 1);
    out[outSize - 1] = 0;
  }
}

bool fromCode(const char* code, Recipe* out) {
  if (!code) return false;
  while (*code == ' ' || *code == '\t' || *code == '\n' || *code == '\r') code++;
  if (!((code[0] == 'S' || code[0] == 's') && (code[1] == 'P' || code[1] == 'p') &&
        (code[2] == 'K' || code[2] == 'k') && code[3] == '1' && code[4] == '-'))
    return false;
  const char* s = code + 5;
  const char* d1 = strchr(s, '-');
  if (!d1) return false;
  const char* nb = d1 + 1;
  const char* d2 = strchr(nb, '-');
  if (!d2) return false;
  const char* c = d2 + 1;
  if (strchr(c, '-')) return false;  // exactly 4 parts
  int ls = (int)(d1 - s), ln = (int)(d2 - nb), lc = (int)strlen(c);
  while (lc > 0 && (c[lc - 1] == ' ' || c[lc - 1] == '\n' || c[lc - 1] == '\r' || c[lc - 1] == '\t')) lc--;
  if (ls < kNumSlots || ln < kNumNumbers || lc < kNumColors * 6) return false;
  for (int i = 0; i < ls; i++) if (fromB36(s[i]) < 0) return false;
  for (int i = 0; i < ln; i++) if (fromB36(nb[i]) < 0) return false;
  Recipe r = baseRecipe();
  strcpy(r.name, "Shared face");
  for (int i = 0; i < kNumSlots; i++) {
    int idx = fromB36(s[i]);
    if (idx < 0 || idx >= kSlotOptionCount[i]) return false;
    r.slot(i) = (uint8_t)idx;
  }
  for (int i = 0; i < kNumNumbers; i++) {
    int q = fromB36(nb[i]);
    if (q < 0 || q > 35) return false;
    r.number(i) = kNumberRange[i][0] + (kNumberRange[i][1] - kNumberRange[i][0]) * (float)q / 35.0f;
  }
  for (int i = 0; i < kNumColors; i++) {
    char hex[7];
    memcpy(hex, c + i * 6, 6);
    hex[6] = 0;
    Rgb v;
    if (!parseHex(hex, &v)) return false;
    r.color(i) = v;
  }
  clampNumbers(r);
  *out = r;
  return true;
}

int slotIndexByKey(const char* key) {
  for (int i = 0; i < kNumSlots; i++) if (key && strcmp(kSlotKeys[i], key) == 0) return i;
  return -1;
}
int slotOptionIndex(int slot, const char* option) {
  if (slot < 0 || slot >= kNumSlots || !option) return -1;
  for (int i = 0; i < kSlotOptionCount[slot]; i++)
    if (strcmp(kSlotOptions[slot][i], option) == 0) return i;
  return -1;
}
int colorIndexByKey(const char* key) {
  for (int i = 0; i < kNumColors; i++) if (key && strcmp(kColorKeys[i], key) == 0) return i;
  return -1;
}
int numberIndexByKey(const char* key) {
  for (int i = 0; i < kNumNumbers; i++) if (key && strcmp(kNumberKeys[i], key) == 0) return i;
  return -1;
}

}  // namespace spike
