// audio.cpp -- the speaker (NS4168 on I2S0) and the two mics (MS3625 on I2S1).
//
// Speaker: one 22.05 kHz mono timeline, mixed from
//   * the brain's speech (protocol 5.4): segments are queued back to back in a PSRAM ring in seq
//     order; playback may start on the first chunk; say_state started/finished/stopped go back;
//   * the built-in synth sounds (lib/spike_life spike_synth, the sounds.js port).
// The mouth follows the brain's envelope (say.mouth) or, if it sent none, the audio's own RMS.
// Mics: 16 kHz stereo I2S in, averaged to mono, sent as `audio` messages (protocol 6.7) in 40 ms
// chunks while the brain link is up -- except while Spike speaks and for 300 ms after (BOM 2e).
#include "app.h"
#include "config.h"
#include "spike_synth.h"
#include <driver/i2s.h>
#include <esp_heap_caps.h>
#include <mbedtls/base64.h>

using spike::Sound;

static spike::Synth synth(SPEAKER_RATE);
static QueueHandle_t soundQ;
struct SoundReq { uint8_t sound; float arg; };
static SemaphoreHandle_t lock;
static volatile float mouthLevel = -1;
static volatile bool speaking = false;
static volatile uint32_t lastSpeechMs = 0;
static volatile float volume = 0.6f;

// ---- speech ring + segments ----------------------------------------------------------------------
static const uint32_t RING = SPEAKER_RATE * 40;  // 40 s of speech (1.7 MB PSRAM)
static int16_t* ring;
static uint32_t readPos = 0;     // next sample to play (monotonic, wraps at 2^32 -- differences only)
static uint32_t reserveHead = 0; // end of the last reserved segment

struct Seg {
  char utt[24];
  int seq;
  uint32_t start, len, written;
  bool captionOnly, started, done;
  int srcRate;
  double srcPos;      // resampler: position in source samples of the next output sample
  int64_t srcCount;   // source samples received so far
  int16_t prev;
  int expectIndex;
  int mouthN, mouthHz;
  uint8_t mouth[1024];
  char mood[24];
  uint32_t underrunMs;
};
static const int MAXSEG = 12;
static Seg* segs;  // PSRAM
static int nSeg = 0;
static int16_t* decodeBuf;  // one say_audio chunk (<= 8192 samples)
static uint8_t* b64Buf;

static void reportState(const Seg& s, const char* state) {
  char f[96];
  snprintf(f, sizeof f, "\"utt\":\"%s\",\"seq\":%d,\"state\":\"%s\"", s.utt, s.seq, state);
  netSend("say_state", f);
}

static void ringWrite(uint32_t pos, const int16_t* src, uint32_t n) {
  for (uint32_t i = 0; i < n; i++) ring[(pos + i) % RING] = src[i];
}

void audioSay(const SayHeader& h) {
  if (!h.hasAudio && !h.hasText) return;  // end marker: nothing to play, nothing to report
  xSemaphoreTake(lock, portMAX_DELAY);
  // drop finished segments from the front
  int w = 0;
  for (int i = 0; i < nSeg; i++) if (!segs[i].done) segs[w++] = segs[i];
  nSeg = w;
  if (nSeg >= MAXSEG) { xSemaphoreGive(lock); logf("audio: segment queue full, dropping %s/%d", h.utt, h.seq); return; }
  Seg& s = segs[nSeg];
  memset(&s, 0, sizeof s);
  strncpy(s.utt, h.utt, sizeof s.utt - 1);
  s.seq = h.seq;
  s.captionOnly = !h.hasAudio;
  s.srcRate = h.hasAudio && h.rate > 0 ? h.rate : SPEAKER_RATE;
  uint32_t n = h.hasAudio ? (uint32_t)((int64_t)h.samples * SPEAKER_RATE / s.srcRate)
                          : (uint32_t)((int64_t)h.durationMs * SPEAKER_RATE / 1000);
  if (reserveHead - readPos + n > RING) { xSemaphoreGive(lock); logf("audio: ring full, dropping %s/%d", h.utt, h.seq); return; }
  if (nSeg == 0 && (int32_t)(readPos - reserveHead) > 0) reserveHead = readPos;
  s.start = reserveHead;
  s.len = n;
  reserveHead += n;
  s.mouthN = h.mouthN > (int)sizeof s.mouth ? (int)sizeof s.mouth : h.mouthN;
  s.mouthHz = h.mouthHz > 0 ? h.mouthHz : 50;
  memcpy(s.mouth, h.mouth, s.mouthN);
  strncpy(s.mood, h.mood, sizeof s.mood - 1);
  if (s.captionOnly) {  // silence on the timeline, so the caption keeps its place in seq order
    static const int16_t zeros[256] = {0};
    for (uint32_t o = 0; o < n; o += 256) ringWrite(s.start + o, zeros, (n - o) < 256 ? (n - o) : 256);
    s.written = n;
  }
  nSeg++;
  xSemaphoreGive(lock);
}

void audioSayChunk(const char* utt, int seq, int index, bool last, const char* b64, size_t b64len) {
  size_t outLen = 0;
  if (b64len > 24 * 1024) { logf("audio: chunk too big (%u)", (unsigned)b64len); return; }
  memcpy(b64Buf, b64, b64len);
  if (mbedtls_base64_decode((unsigned char*)decodeBuf, 8192 * 2, &outLen, b64Buf, b64len) != 0) {
    logf("audio: bad base64 in say_audio %s/%d", utt, seq);
    return;
  }
  int nIn = (int)(outLen / 2);
  xSemaphoreTake(lock, portMAX_DELAY);
  Seg* s = nullptr;
  for (int i = 0; i < nSeg; i++) if (!segs[i].done && segs[i].seq == seq && strcmp(segs[i].utt, utt) == 0) s = &segs[i];
  if (s && !s->captionOnly) {
    if (index != s->expectIndex) logf("audio: chunk %d of %s/%d out of order (expected %d)", index, utt, seq, s->expectIndex);
    s->expectIndex = index + 1;
    if (s->srcRate == SPEAKER_RATE) {
      uint32_t n = (uint32_t)nIn;
      if (s->written + n > s->len) n = s->len - s->written;
      ringWrite(s->start + s->written, decodeBuf, n);
      s->written += n;
    } else {  // linear resampling to the speaker rate, continuous across chunks
      double step = (double)s->srcRate / SPEAKER_RATE;
      int64_t base = s->srcCount;  // absolute index of decodeBuf[0]
      while (s->written < s->len) {
        double p = s->srcPos;
        int64_t i0 = (int64_t)floor(p);
        if (i0 + 1 >= base + nIn) break;
        float fr = (float)(p - (double)i0);
        int16_t a = i0 < base ? s->prev : decodeBuf[i0 - base];
        int16_t b = decodeBuf[i0 + 1 - base];
        int16_t v = (int16_t)(a + (b - a) * fr);
        ring[(s->start + s->written) % RING] = v;
        s->written++;
        s->srcPos += step;
      }
      s->srcCount += nIn;
      if (nIn > 0) s->prev = decodeBuf[nIn - 1];
    }
    if (last && s->written < s->len) {  // the brain sent fewer samples than announced: pad
      uint32_t missing = s->len - s->written;
      for (uint32_t i = 0; i < missing; i++) ring[(s->start + s->written + i) % RING] = 0;
      s->written = s->len;
    }
  }
  xSemaphoreGive(lock);
}

void audioStopSpeaking() {
  xSemaphoreTake(lock, portMAX_DELAY);
  for (int i = 0; i < nSeg; i++)
    if (!segs[i].done) { segs[i].done = true; reportState(segs[i], "stopped"); }
  nSeg = 0;
  readPos = reserveHead;
  speaking = false;
  mouthLevel = -1;
  lastSpeechMs = millis();
  xSemaphoreGive(lock);
}

float audioMouthLevel() { return mouthLevel; }
bool audioSpeaking() { return speaking; }
void audioSetVolume(float v) { volume = v < 0 ? 0 : (v > 1 ? 1 : v); }

void audioPlaySound(uint8_t sound, float arg) {
  SoundReq r{sound, arg};
  if (soundQ) xQueueSend(soundQ, &r, 0);
}

// Fill `out` (n mono samples) from the speech timeline. Returns the RMS of what was played.
static float pullSpeech(int16_t* out, int n) {
  memset(out, 0, n * 2);
  xSemaphoreTake(lock, portMAX_DELAY);
  Seg* cur = nullptr;
  for (int i = 0; i < nSeg; i++) if (!segs[i].done) { cur = &segs[i]; break; }
  float rms = 0;
  if (!cur) {
    if (speaking) { speaking = false; lastSpeechMs = millis(); }
    mouthLevel = -1;
    xSemaphoreGive(lock);
    return 0;
  }
  speaking = true;
  if ((int32_t)(readPos - cur->start) < 0) readPos = cur->start;
  uint32_t off = readPos - cur->start;
  uint32_t avail = cur->written - off;
  uint32_t take = avail < (uint32_t)n ? avail : (uint32_t)n;
  if (take > 0 && !cur->started) {
    cur->started = true;
    reportState(*cur, "started");
    Cmd c = makeCmd(C_SPEECH_START, 0, 0, 0, 0, cur->mood);
    postCmd(c);
  }
  if (take == 0 && cur->written < cur->len) {  // waiting for chunks (underrun)
    cur->underrunMs += (uint32_t)(n * 1000 / SPEAKER_RATE);
    if (cur->underrunMs > 4000) {  // give up on this segment
      logf("audio: %s/%d stalled, skipping", cur->utt, cur->seq);
      readPos = cur->start + cur->len;
      cur->done = true;
      reportState(*cur, "finished");
    }
  }
  double acc = 0;
  float v = volume;
  for (uint32_t i = 0; i < take; i++) {
    int16_t s = ring[(readPos + i) % RING];
    acc += (double)s * s;
    out[i] = (int16_t)(s * v);
  }
  readPos += take;
  if (take) rms = (float)sqrt(acc / take) / 32768.0f;
  // mouth: the brain's envelope, a babble for caption-only segments, or our own RMS
  float t = (float)(readPos - cur->start) / SPEAKER_RATE;
  if (cur->captionOnly) mouthLevel = 0.25f + 0.25f * sinf(t * 18);
  else if (cur->mouthN > 0) {
    int idx = (int)(t * cur->mouthHz);
    if (idx >= cur->mouthN) idx = cur->mouthN - 1;
    mouthLevel = cur->mouth[idx] / 100.0f;
  } else mouthLevel = rms * 4 > 1 ? 1 : rms * 4;
  if (readPos - cur->start >= cur->len && cur->written >= cur->len) {
    cur->done = true;
    reportState(*cur, "finished");
  }
  xSemaphoreGive(lock);
  return rms;
}

static void speakerTask(void*) {
  static int16_t mono[256];
  static int16_t stereo[512];
  for (;;) {
    SoundReq r;
    while (xQueueReceive(soundQ, &r, 0) == pdTRUE) synth.play((Sound)r.sound, r.arg);
    synth.setVolume(volume);
    pullSpeech(mono, 256);
    synth.render(mono, 256);
    for (int i = 0; i < 256; i++) { stereo[2 * i] = mono[i]; stereo[2 * i + 1] = mono[i]; }
    size_t wr = 0;
    i2s_write(I2S_NUM_0, stereo, sizeof stereo, &wr, portMAX_DELAY);  // paces the task
  }
}

// ---- mics ------------------------------------------------------------------------------------
static void micTask(void*) {
  const int frames = MIC_RATE * MIC_CHUNK_MS / 1000;  // 640
  int32_t* raw = (int32_t*)heap_caps_malloc(frames * 2 * 4, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
  int16_t* mono = (int16_t*)malloc(frames * 2);
  size_t b64cap = ((frames * 2 + 2) / 3) * 4 + 4;
  unsigned char* b64 = (unsigned char*)malloc(b64cap);
  char* fields = (char*)malloc(b64cap + 96);
  uint32_t seq = 0;
  if (!raw || !mono || !b64 || !fields) { logf("audio: mic buffers failed"); vTaskDelete(nullptr); }
  for (;;) {
    size_t got = 0;
    i2s_read(I2S_NUM_1, raw, frames * 2 * 4, &got, portMAX_DELAY);
    int n = (int)(got / 8);
    // MS3625: 24-bit samples left-justified in 32-bit slots; average left + right mics
    for (int i = 0; i < n; i++) {
      int32_t l = raw[2 * i] >> 14, rr = raw[2 * i + 1] >> 14;
      int32_t m = (l + rr) / 2;
      mono[i] = (int16_t)(m > 32767 ? 32767 : (m < -32768 ? -32768 : m));
    }
    bool muted = speaking || (millis() - lastSpeechMs < MIC_MUTE_TAIL_MS);
    if (!netWantsMic() || muted || n == 0) continue;
    size_t olen = 0;
    if (mbedtls_base64_encode(b64, b64cap, &olen, (const unsigned char*)mono, n * 2) != 0) continue;
    b64[olen] = 0;
    snprintf(fields, b64cap + 96, "\"seq\":%lu,\"rate\":%d,\"format\":\"pcm_s16le\",\"data\":\"%s\"", (unsigned long)++seq,
             MIC_RATE, (const char*)b64);
    netSend("audio", fields);
  }
}

void audioBegin() {
  lock = xSemaphoreCreateMutex();
  soundQ = xQueueCreate(16, sizeof(SoundReq));
  ring = (int16_t*)heap_caps_malloc(RING * 2, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  segs = (Seg*)heap_caps_malloc(sizeof(Seg) * MAXSEG, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  decodeBuf = (int16_t*)heap_caps_malloc(8192 * 2 + 16, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  b64Buf = (uint8_t*)heap_caps_malloc(24 * 1024 + 4, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!ring || !segs || !decodeBuf || !b64Buf) logf("audio: PSRAM buffers FAILED");
  volume = gSettings.volume;

  i2s_config_t tx = {};
  tx.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  tx.sample_rate = SPEAKER_RATE;
  tx.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  tx.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  tx.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  tx.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  tx.dma_buf_count = 6;
  tx.dma_buf_len = 256;
  tx.tx_desc_auto_clear = true;
  i2s_pin_config_t txp = {};
  txp.mck_io_num = I2S_PIN_NO_CHANGE;
  txp.bck_io_num = PIN_SPK_BCLK;
  txp.ws_io_num = PIN_SPK_LRCK;
  txp.data_out_num = PIN_SPK_DOUT;
  txp.data_in_num = I2S_PIN_NO_CHANGE;
  if (i2s_driver_install(I2S_NUM_0, &tx, 0, nullptr) != ESP_OK || i2s_set_pin(I2S_NUM_0, &txp) != ESP_OK)
    logf("audio: speaker I2S init failed");

  i2s_config_t rx = {};
  rx.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  rx.sample_rate = MIC_RATE;
  rx.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  rx.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  rx.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  rx.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  rx.dma_buf_count = 6;
  rx.dma_buf_len = 320;
  i2s_pin_config_t rxp = {};
  rxp.mck_io_num = I2S_PIN_NO_CHANGE;
  rxp.bck_io_num = PIN_MIC_SCK;
  rxp.ws_io_num = PIN_MIC_WS;
  rxp.data_out_num = I2S_PIN_NO_CHANGE;
  rxp.data_in_num = PIN_MIC_SD;
  if (i2s_driver_install(I2S_NUM_1, &rx, 0, nullptr) != ESP_OK || i2s_set_pin(I2S_NUM_1, &rxp) != ESP_OK)
    logf("audio: mic I2S init failed");

  xTaskCreatePinnedToCore(speakerTask, "speaker", 6144, nullptr, 6, nullptr, 0);
  xTaskCreatePinnedToCore(micTask, "mic", 6144, nullptr, 4, nullptr, 0);
  logf("audio: speaker I2S0 %d Hz (BCLK %d LRCK %d DOUT %d), mics I2S1 %d Hz (SCK %d WS %d SD %d)", SPEAKER_RATE,
       PIN_SPK_BCLK, PIN_SPK_LRCK, PIN_SPK_DOUT, MIC_RATE, PIN_MIC_SCK, PIN_MIC_WS, PIN_MIC_SD);
}
