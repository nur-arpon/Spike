// link_test.cpp -- host tests for protocol v1.3 "away from home" (lib/spike_link) and the pairing
// passkey overlay (lib/spike_face/spike_passkey):
//
//   face_pc link <ble_vectors.txt>   BLE framing vs software/protocol/ble_frame_vectors.json (converted by
//                                    test/ble_vectors_to_txt.py), extra framing round trips, the
//                                    one-brain-at-a-time policy, hotspot_join checks, and the ESP-NOW
//                                    packet (round trip, wrong key, tamper, too long)
//   face_pc passkey <out.png> [passkey] [remaining 0..1]
//
// AES-256-GCM on the PC: Windows CNG (bcrypt.dll, part of Windows; nothing downloaded). It is a TEST-ONLY
// Aead: the boards use mbedTLS (lib/spike_link/src/spike_aead_mbedtls.cpp), which this build cannot
// compile. The CNG adapter is itself checked against the published GCM test case 16 (AES-256).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <bcrypt.h>
#pragma comment(lib, "bcrypt.lib")

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <string>
#include <vector>

#include "png_write.h"
#include "spike_ble_frames.h"
#include "spike_espnow_pkt.h"
#include "spike_link_policy.h"
#include "spike_passkey.h"
#include "spike_raster.h"

using namespace spike;

static int lfails = 0, lchecks = 0;
#define LCHECK(cond, ...)                          \
  do {                                             \
    lchecks++;                                     \
    if (!(cond)) {                                 \
      lfails++;                                    \
      printf("FAIL %s:%d: ", __FILE__, __LINE__);  \
      printf(__VA_ARGS__);                         \
      printf("\n");                                \
    }                                              \
  } while (0)

typedef std::vector<uint8_t> Bytes;

static Bytes unhex(const char* s) {
  Bytes b;
  if (!s || strcmp(s, "-") == 0) return b;
  size_t n = strlen(s) / 2;
  b.resize(n);
  if (!espnow::fromHex(s, b.data(), n)) b.clear();
  return b;
}

// ---- test-only AES-256-GCM through Windows CNG --------------------------------------------------
class BcryptAead : public espnow::Aead {
 public:
  bool seal(const uint8_t key[32], const uint8_t nonce[12], const uint8_t* aad, size_t aadLen, const uint8_t* pt,
            size_t len, uint8_t* ct, uint8_t tag[16]) override {
    return run(true, key, nonce, aad, aadLen, pt, len, ct, tag);
  }
  bool open(const uint8_t key[32], const uint8_t nonce[12], const uint8_t* aad, size_t aadLen, const uint8_t* ct,
            size_t len, const uint8_t tag[16], uint8_t* pt) override {
    return run(false, key, nonce, aad, aadLen, ct, len, pt, const_cast<uint8_t*>(tag));
  }

 private:
  static bool run(bool enc, const uint8_t* key, const uint8_t* nonce, const uint8_t* aad, size_t aadLen,
                  const uint8_t* in, size_t len, uint8_t* out, uint8_t* tag) {
    BCRYPT_ALG_HANDLE alg = nullptr;
    BCRYPT_KEY_HANDLE k = nullptr;
    bool ok = false;
    uint8_t dummy[1] = {0};
    if (BCRYPT_SUCCESS(BCryptOpenAlgorithmProvider(&alg, BCRYPT_AES_ALGORITHM, nullptr, 0)) &&
        BCRYPT_SUCCESS(BCryptSetProperty(alg, BCRYPT_CHAINING_MODE, (PUCHAR)BCRYPT_CHAIN_MODE_GCM,
                                         sizeof(BCRYPT_CHAIN_MODE_GCM), 0)) &&
        BCRYPT_SUCCESS(BCryptGenerateSymmetricKey(alg, &k, nullptr, 0, (PUCHAR)key, 32, 0))) {
      BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO info;
      BCRYPT_INIT_AUTH_MODE_INFO(info);
      info.pbNonce = (PUCHAR)nonce;
      info.cbNonce = 12;
      info.pbAuthData = (PUCHAR)aad;
      info.cbAuthData = (ULONG)aadLen;
      info.pbTag = tag;
      info.cbTag = 16;
      ULONG outLen = 0;
      NTSTATUS st = enc ? BCryptEncrypt(k, len ? (PUCHAR)in : dummy, (ULONG)len, &info, nullptr, 0, len ? out : dummy,
                                        (ULONG)len, &outLen, 0)
                        : BCryptDecrypt(k, len ? (PUCHAR)in : dummy, (ULONG)len, &info, nullptr, 0, len ? out : dummy,
                                        (ULONG)len, &outLen, 0);
      ok = BCRYPT_SUCCESS(st) && outLen == len;
    }
    if (k) BCryptDestroyKey(k);
    if (alg) BCryptCloseAlgorithmProvider(alg, 0);
    return ok;
  }
};

// ---- BLE framing ---------------------------------------------------------------------------------
static bool collectSink(void* ctx, const uint8_t* f, size_t n) {
  ((std::vector<Bytes>*)ctx)->push_back(Bytes(f, f + n));
  return true;
}
static bool stopAfterOne(void* ctx, const uint8_t*, size_t) { return ++*(int*)ctx < 1; }

static std::vector<uint8_t> gDecBuf(ble::kMaxMessage + 1);

static void testVectors(const char* path, int* nEnc, int* nDec) {
  FILE* f = fopen(path, "rb");
  LCHECK(f != nullptr, "cannot open %s (run test/ble_vectors_to_txt.py first)", path);
  if (!f) return;
  std::string text;
  char chunk[65536];
  size_t got;
  while ((got = fread(chunk, 1, sizeof chunk, f)) > 0) text.append(chunk, got);
  fclose(f);
  std::string name = "?";
  size_t pos = 0;
  while (pos < text.size()) {
    size_t eol = text.find('\n', pos);
    if (eol == std::string::npos) eol = text.size();
    std::string line = text.substr(pos, eol - pos);
    pos = eol + 1;
    if (line.empty()) continue;
    if (line[0] == '#') { name = line.size() > 2 ? line.substr(2) : ""; continue; }
    std::vector<char> buf(line.begin(), line.end());
    buf.push_back(0);
    std::vector<const char*> tok;
    for (char* t = strtok(buf.data(), " \r"); t; t = strtok(nullptr, " \r")) tok.push_back(t);
    size_t i = 0;
    auto next = [&]() -> const char* { return i < tok.size() ? tok[i++] : "-"; };
    const char* kind = next();
    if (!strcmp(kind, "E")) {
      int mtu = atoi(next()), start = atoi(next());
      Bytes msg = unhex(next());
      int nf = atoi(next());
      std::vector<Bytes> want;
      for (int k = 0; k < nf; k++) want.push_back(unhex(next()));
      ble::FrameEncoder e;
      e.setCounter((uint8_t)start);
      std::vector<Bytes> got2;
      int r = e.encode(msg.data(), msg.size(), (uint16_t)mtu, collectSink, &got2);
      LCHECK(r == nf, "encode '%s': %d frames, want %d", name.c_str(), r, nf);
      bool same = got2.size() == want.size();
      for (size_t k = 0; same && k < want.size(); k++) same = got2[k] == want[k];
      LCHECK(same, "encode '%s': frames differ from the vectors", name.c_str());
      (*nEnc)++;
    } else if (!strcmp(kind, "D")) {
      int nf = atoi(next());
      std::vector<Bytes> frames;
      for (int k = 0; k < nf; k++) frames.push_back(unhex(next()));
      int nm = atoi(next());
      std::vector<Bytes> want;
      for (int k = 0; k < nm; k++) want.push_back(unhex(next()));
      int dropped = atoi(next());
      bool tooBig = atoi(next()) != 0;
      ble::FrameDecoder d(gDecBuf.data());
      std::vector<Bytes> out;
      for (const Bytes& fr : frames) {
        const uint8_t* m;
        size_t ml;
        if (d.feed(fr.data(), fr.size(), &m, &ml)) out.push_back(Bytes(m, m + ml));
      }
      bool same = out.size() == want.size();
      for (size_t k = 0; same && k < want.size(); k++) same = out[k] == want[k];
      LCHECK(same, "decode '%s': %d messages out, want %d (or different bytes)", name.c_str(), (int)out.size(), nm);
      LCHECK((int)d.dropped() == dropped, "decode '%s': dropped %u, want %d", name.c_str(), d.dropped(), dropped);
      LCHECK(d.tooBig() == tooBig, "decode '%s': too_big %d, want %d", name.c_str(), d.tooBig(), tooBig);
      if (tooBig) LCHECK(d.tooBigEvents() == 1, "decode '%s': error too_big must be answered once", name.c_str());
      (*nDec)++;
    }
  }
}

static uint32_t rngState = 12345;
static uint32_t rnd() { rngState = rngState * 1664525u + 1013904223u; return rngState >> 8; }

static void testFramingExtra() {
  // round trips at every MTU class and many sizes, with the counter carried across messages
  const uint16_t mtus[] = {23, 24, 40, 185, 247, 517, 600};
  for (uint16_t mtu : mtus) {
    ble::FrameEncoder e;
    ble::FrameDecoder d(gDecBuf.data());
    e.setCounter((uint8_t)(rnd() & 63));
    const size_t sizes[] = {0, 1, 18, 19, 20, 181, 513, 514, 1000, 4096, ble::kMaxMessage - 1, ble::kMaxMessage};
    for (size_t sz : sizes) {
      Bytes msg(sz);
      for (auto& b : msg) b = (uint8_t)(32 + rnd() % 90);
      std::vector<Bytes> fr;
      int n = e.encode(msg.data(), msg.size(), mtu, collectSink, &fr);
      size_t per = ble::payloadSize(mtu);
      size_t wantN = sz == 0 ? 1 : (sz + per - 1) / per;
      LCHECK(n == (int)wantN, "mtu %u size %u: %d frames, want %u", mtu, (unsigned)sz, n, (unsigned)wantN);
      bool fits = true;
      for (auto& f : fr) fits &= f.size() <= (size_t)(mtu > ble::kMaxAttMtu ? ble::kMaxAttMtu : mtu) - 3;
      LCHECK(fits, "mtu %u: a frame is longer than ATT_MTU - 3", mtu);
      int msgs = 0;
      for (auto& f : fr) {
        const uint8_t* m;
        size_t ml;
        if (d.feed(f.data(), f.size(), &m, &ml)) {
          msgs++;
          LCHECK(ml == sz && (sz == 0 || memcmp(m, msg.data(), sz) == 0), "mtu %u size %u: round trip differs", mtu, (unsigned)sz);
          LCHECK(m[ml] == 0, "decoded message is NUL-terminated");
        }
      }
      LCHECK(msgs == 1, "mtu %u size %u: %d messages out", mtu, (unsigned)sz, msgs);
    }
    LCHECK(d.dropped() == 0, "mtu %u: nothing dropped", mtu);
  }
  // over 16 KiB: the encoder refuses and sends nothing, the counter does not move
  {
    ble::FrameEncoder e;
    Bytes big(ble::kMaxMessage + 1, 'x');
    std::vector<Bytes> fr;
    LCHECK(e.encode(big.data(), big.size(), 517, collectSink, &fr) == -1 && fr.empty() && e.counter() == 0,
           "a message over 16 KiB is refused");
  }
  // a sink that stops: -1, and the peer resynchronises on the next message
  {
    ble::FrameEncoder e;
    ble::FrameDecoder d(gDecBuf.data());
    Bytes msg(100, 'a');
    int calls = 0;
    LCHECK(e.encode(msg.data(), msg.size(), 23, stopAfterOne, &calls) == -1, "a stopped sink reports failure");
    std::vector<Bytes> fr;
    const char* next = "{\"v\":1,\"type\":\"ping\",\"id\":2}";
    e.encode((const uint8_t*)next, strlen(next), 23, collectSink, &fr);
    int got = 0;
    for (auto& f : fr) {
      const uint8_t* m;
      size_t ml;
      if (d.feed(f.data(), f.size(), &m, &ml)) got += ml == strlen(next);
    }
    LCHECK(got == 1, "after an aborted message the next one still arrives");
  }
  // a reset (new connection) forgets a half-built message and the expected counter
  {
    ble::FrameEncoder e;
    ble::FrameDecoder d(gDecBuf.data());
    Bytes msg(60, 'b');
    std::vector<Bytes> fr;
    e.encode(msg.data(), msg.size(), 23, collectSink, &fr);
    const uint8_t* m;
    size_t ml;
    d.feed(fr[0].data(), fr[0].size(), &m, &ml);
    d.reset();
    ble::FrameEncoder e2;  // the phone starts at 0 again
    std::vector<Bytes> fr2;
    e2.encode(msg.data(), msg.size(), 23, collectSink, &fr2);
    int got = 0;
    for (auto& f : fr2) got += d.feed(f.data(), f.size(), &m, &ml) ? 1 : 0;
    LCHECK(got == 1, "after reset the first message of the new connection arrives");
  }
}

// ---- one brain at a time (11.4), routing, hotspot_join checks (11.5) -----------------------------
static void testPolicy() {
  using namespace link;
  LinkView none, lan, ble, lanBle, hs, hsBle;
  lan.wsUp = true;
  ble.bleUp = true;
  lanBle.wsUp = true;
  lanBle.bleUp = true;
  hs.wsUp = true;
  hs.wsKind = WsKind::Hotspot;
  hsBle = hs;
  hsBle.bleUp = true;
  LCHECK(activeBrain(none) == Brain::None && !strcmp(brainName(activeBrain(none)), "none"), "no brain");
  LCHECK(activeBrain(lan) == Brain::Lan && !strcmp(brainName(Brain::Lan), "lan"), "laptop brain");
  LCHECK(activeBrain(ble) == Brain::Ble && !strcmp(brainName(Brain::Ble), "ble"), "phone over BLE");
  LCHECK(activeBrain(lanBle) == Brain::Lan, "the laptop brain wins over BLE");
  LCHECK(activeBrain(hsBle) == Brain::Hotspot && !strcmp(brainName(Brain::Hotspot), "hotspot"), "hotspot link preferred");

  // inbound: BLE while the laptop brain is followed
  LCHECK(classifyInbound(Link::Ble, "mood", true, lanBle) == Inbound::Busy, "mood over BLE while LAN -> busy");
  LCHECK(classifyInbound(Link::Ble, "drive", true, lanBle) == Inbound::Busy, "drive over BLE while LAN -> busy");
  LCHECK(classifyInbound(Link::Ble, "say", true, lanBle) == Inbound::Busy, "say over BLE while LAN -> busy");
  LCHECK(classifyInbound(Link::Ble, "ping", true, lanBle) == Inbound::Handle, "ping still answered");
  LCHECK(classifyInbound(Link::Ble, "hello", false, lanBle) == Inbound::Handle, "hello exchange still runs");
  LCHECK(classifyInbound(Link::Ble, "hotspot_join", true, lanBle) == Inbound::Handle, "hotspot_join still handled");
  LCHECK(classifyInbound(Link::Ble, "hotspot_leave", true, lanBle) == Inbound::Handle, "hotspot_leave still handled");
  LCHECK(classifyInbound(Link::Ble, "error", true, lanBle) == Inbound::Handle, "an error is never answered with busy");
  LCHECK(classifyInbound(Link::Ble, "robot_link_ack", true, lanBle) == Inbound::Handle, "robot_link_ack handled");
  // inbound: BLE is the brain
  LCHECK(classifyInbound(Link::Ble, "mood", true, ble) == Inbound::Handle, "BLE brain followed");
  LCHECK(classifyInbound(Link::Ble, "drive", true, ble) == Inbound::Handle, "BLE drive handled");
  LCHECK(classifyInbound(Link::Ble, "mood", false, ble) == Inbound::Ignore, "nothing before the phone's hello");
  LCHECK(classifyInbound(Link::Ble, "mood", true, hsBle) == Inbound::Handle, "same phone on BLE and hotspot");
  // inbound: WebSocket
  LCHECK(classifyInbound(Link::Ws, "hotspot_join", true, lan) == Inbound::BadLink, "hotspot_join refused on the WS");
  LCHECK(classifyInbound(Link::Ws, "hotspot_leave", true, hs) == Inbound::BadLink, "hotspot_leave refused on the WS");
  LCHECK(classifyInbound(Link::Ws, "mood", true, lanBle) == Inbound::Handle, "laptop brain handled");
  LCHECK(classifyInbound(Link::Ws, "mood", false, lan) == Inbound::Ignore, "WS: nothing before hello");
  LCHECK(classifyInbound(Link::Ws, "robot_link_ack", true, hs) == Inbound::Handle, "robot_link_ack on the hotspot");

  // outbound routing
  Link out = Link::Ble;
  LCHECK(routeOutbound("touch", lanBle, &out) && out == Link::Ws, "touch goes to the laptop while LAN");
  LCHECK(routeOutbound("touch", ble, &out) && out == Link::Ble, "touch goes over BLE to the phone brain");
  LCHECK(routeOutbound("say_state", hsBle, &out) && out == Link::Ws, "hotspot WS carries robot->brain when up");
  LCHECK(!routeOutbound("touch", none, &out), "no brain: dropped");
  LCHECK(routeOutbound("robot_link", lanBle, &out) && out == Link::Ble, "robot_link over BLE even while LAN");
  LCHECK(routeOutbound("hotspot_state", hsBle, &out) && out == Link::Ble, "hotspot_state over BLE");
  LCHECK(routeOutbound("hotspot_state", hs, &out) && out == Link::Ws, "hotspot_state on the hotspot without BLE");
  LCHECK(!routeOutbound("robot_link", lan, &out), "robot_link never to the laptop");
  LCHECK(!routeOutbound("audio", ble, &out), "mic audio never over BLE");
  LCHECK(!routeOutbound("camera", ble, &out), "camera never over BLE");
  LCHECK(micWanted(lan) && micWanted(lanBle) && !micWanted(ble) && !micWanted(hsBle), "mics only for the laptop brain");

  // hotspot_join checks
  HotspotJoin j;
  j.ssid = "AndroidShare_1234";
  j.pass = "correct horse";
  j.portIsInt = true;
  j.port = 8766;
  j.token = "9f2c0123456789abcdef";
  j.host = "";
  LCHECK(checkHotspotJoin(j) == nullptr, "a good hotspot_join passes");
  HotspotJoin b = j; b.ssid = nullptr; LCHECK(checkHotspotJoin(b), "ssid missing");
  b = j; b.ssid = ""; LCHECK(checkHotspotJoin(b), "empty ssid");
  b = j; b.ssid = "123456789012345678901234567890123"; LCHECK(checkHotspotJoin(b), "33-byte ssid");
  b = j; b.ssid = "12345678901234567890123456789012"; LCHECK(!checkHotspotJoin(b), "32-byte ssid ok");
  b = j; b.pass = "1234567"; LCHECK(checkHotspotJoin(b), "7-char pass");
  b = j; b.pass = "1234567890123456789012345678901234567890123456789012345678901234"; LCHECK(checkHotspotJoin(b), "64-char pass");
  b = j; b.pass = "pass\x01word"; LCHECK(checkHotspotJoin(b), "control char in pass");
  b = j; b.portIsInt = false; LCHECK(checkHotspotJoin(b), "port not an integer");
  b = j; b.port = 0; LCHECK(checkHotspotJoin(b), "port 0");
  b = j; b.port = 65536; LCHECK(checkHotspotJoin(b), "port 65536");
  b = j; b.token = "short"; LCHECK(checkHotspotJoin(b), "short token");
  b = j; b.token = "0123456789abcdef 123"; LCHECK(checkHotspotJoin(b), "space in token");
  b = j; b.token = nullptr; LCHECK(checkHotspotJoin(b), "token missing");
  b = j; b.host = "192.168.49.1"; LCHECK(!checkHotspotJoin(b), "IPv4 host ok");
  b = j; b.host = "phone.local"; LCHECK(!checkHotspotJoin(b), "host name ok");
  b = j; b.host = "fe80::1"; LCHECK(checkHotspotJoin(b), "IPv6 host refused");
  b = j; b.host = nullptr; LCHECK(!checkHotspotJoin(b), "host missing = gateway");
  LCHECK(!strcmp(hotspotFailReason(201), "not_found"), "no AP -> not_found");
  LCHECK(!strcmp(hotspotFailReason(15), "auth") && !strcmp(hotspotFailReason(202), "auth") &&
             !strcmp(hotspotFailReason(204), "auth"), "wrong password -> auth");
  LCHECK(!strcmp(hotspotFailReason(0), "timeout") && !strcmp(hotspotFailReason(200), "timeout"), "else timeout");
  char esc[64];
  LCHECK(jsonEscape("a\"b\\c\n", esc, sizeof esc) && !strcmp(esc, "a\\\"b\\\\c\\u000a"), "json escape: %s", esc);
  LCHECK(!jsonEscape("0123456789", esc, 5) && esc[0] == 0, "json escape reports no room");
  LCHECK(jsonEscape("", esc, 1) && esc[0] == 0, "json escape of an empty string");
}

// ---- ESP-NOW hand-over packet (11.6) ---------------------------------------------------------------
static void testEspNow() {
  BcryptAead aead;
  // 1. the CNG adapter against GCM test case 16 (AES-256, 96-bit IV, AAD, 60-byte plaintext)
  {
    Bytes key = unhex("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308");
    Bytes iv = unhex("cafebabefacedbaddecaf888");
    Bytes aad = unhex("feedfacedeadbeeffeedfacedeadbeefabaddad2");
    Bytes pt = unhex("d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39");
    Bytes wantCt = unhex("522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa8cb08e48590dbb3da7b08b1056828838c5f61e6393ba7a0abcc9f662");
    Bytes wantTag = unhex("76fc6ece0f4e1768cddf8853bb2d551b");
    Bytes ct(pt.size()), tag(16), back(pt.size());
    LCHECK(aead.seal(key.data(), iv.data(), aad.data(), aad.size(), pt.data(), pt.size(), ct.data(), tag.data()), "GCM seal runs");
    LCHECK(ct == wantCt && tag == wantTag, "AES-256-GCM matches the published test case 16");
    LCHECK(aead.open(key.data(), iv.data(), aad.data(), aad.size(), ct.data(), ct.size(), tag.data(), back.data()) && back == pt,
           "GCM open of test case 16");
  }
  uint8_t key[32], key2[32], nonce[12];
  for (int i = 0; i < 32; i++) { key[i] = (uint8_t)(i * 7 + 1); key2[i] = key[i]; }
  key2[31] ^= 1;
  for (int i = 0; i < 12; i++) nonce[i] = (uint8_t)(0xA0 + i);
  espnow::JoinInfo ji;
  ji.ssid = "AndroidShare_1234";
  ji.pass = "hunter2hunter2";
  ji.port = 8766;
  ji.token = "9f2c0123456789abcdef0123456789ab";
  ji.host = "";
  ji.sid = "0011223344556677";
  char pt[256];
  bool withSid = false;
  size_t n = espnow::buildJoinPlaintext(ji, pt, sizeof pt, &withSid);
  LCHECK(n > 0 && withSid, "a typical join fits with its session id");
  LCHECK(!strcmp(pt, "{\"ssid\":\"AndroidShare_1234\",\"pass\":\"hunter2hunter2\",\"port\":8766,\"token\":\"9f2c0123456789abcdef0123456789ab\",\"host\":\"\",\"sid\":\"0011223344556677\"}"),
         "join plaintext: %s", pt);
  uint8_t pkt[300];
  size_t len = espnow::seal(aead, key, espnow::KIND_JOIN, nonce, (const uint8_t*)pt, n, pkt, sizeof pkt);
  LCHECK(len == n + 33 && len <= 250, "packet length %u", (unsigned)len);
  LCHECK(!memcmp(pkt, "SPK1", 4) && pkt[4] == 1 && !memcmp(pkt + 5, nonce, 12), "header SPK1 | kind | nonce");
  uint8_t kind = 0, out[260];
  size_t outLen = 0;
  LCHECK(espnow::open(aead, key, pkt, len, &kind, out, sizeof out, &outLen) == espnow::OpenResult::Ok && kind == 1 &&
             outLen == n && !memcmp(out, pt, n) && out[n] == 0, "round trip kind 1");
  LCHECK(espnow::open(aead, key2, pkt, len, &kind, out, sizeof out, &outLen) == espnow::OpenResult::AuthFail, "wrong key rejected");
  // tamper: every region of the packet (kind byte, nonce, ciphertext, tag)
  const size_t spots[] = {4, 5, 16, 17, 17 + n / 2, len - 16, len - 1};
  for (size_t s : spots) {
    uint8_t t[300];
    memcpy(t, pkt, len);
    t[s] ^= (s == 4) ? 3 : 0x01;  // kind 1 -> 2 is still a valid kind: only the AAD catches it
    espnow::OpenResult r = espnow::open(aead, key, t, len, &kind, out, sizeof out, &outLen);
    LCHECK(r == espnow::OpenResult::AuthFail, "tamper at byte %u rejected (%s)", (unsigned)s, espnow::openResultName(r));
  }
  {
    uint8_t t[300];
    memcpy(t, pkt, len);
    t[0] = 'X';
    LCHECK(espnow::open(aead, key, t, len, &kind, out, sizeof out, &outLen) == espnow::OpenResult::BadMagic, "bad magic");
    t[0] = 'S';
    t[4] = 7;
    LCHECK(espnow::open(aead, key, t, len, &kind, out, sizeof out, &outLen) == espnow::OpenResult::BadKind, "bad kind");
    LCHECK(espnow::open(aead, key, pkt, len - 1, &kind, out, sizeof out, &outLen) == espnow::OpenResult::AuthFail, "truncated");
    LCHECK(espnow::open(aead, key, pkt, 32, &kind, out, sizeof out, &outLen) == espnow::OpenResult::TooShort, "too short");
  }
  // too long
  {
    uint8_t big[300] = {0};
    LCHECK(espnow::seal(aead, key, 1, nonce, big, 218, pkt, sizeof pkt) == 0, "a 218-byte plaintext is refused");
    LCHECK(espnow::seal(aead, key, 1, nonce, big, 217, pkt, sizeof pkt) == 250, "217 bytes make a 250-byte packet");
    memcpy(big, "SPK1\x01", 5);
    LCHECK(espnow::open(aead, key, big, 251, &kind, out, sizeof out, &outLen) == espnow::OpenResult::TooLong, "251 bytes refused");
    LCHECK(espnow::seal(aead, key, 3, nonce, big, 10, pkt, sizeof pkt) == 0, "unknown kind refused");
  }
  // kind 2
  {
    char lv[64];
    size_t ln = espnow::buildLeavePlaintext("0011223344556677", lv, sizeof lv);
    LCHECK(ln && !strcmp(lv, "{\"sid\":\"0011223344556677\"}"), "leave plaintext %s", lv);
    LCHECK(espnow::buildLeavePlaintext(nullptr, lv, sizeof lv) == 2 && !strcmp(lv, "{}"), "spec leave plaintext {}");
    len = espnow::seal(aead, key, espnow::KIND_LEAVE, nonce, (const uint8_t*)lv, 2, pkt, sizeof pkt);
    LCHECK(espnow::open(aead, key, pkt, len, &kind, out, sizeof out, &outLen) == espnow::OpenResult::Ok && kind == 2 &&
               !strcmp((char*)out, "{}"), "round trip kind 2");
  }
  // sizes: escaping, the sid falls away first, and the spec's worst case does not fit in 250 bytes
  {
    espnow::JoinInfo q = ji;
    q.ssid = "a\"b\\c";
    n = espnow::buildJoinPlaintext(q, pt, sizeof pt, &withSid);
    LCHECK(n && strstr(pt, "\"ssid\":\"a\\\"b\\\\c\""), "ssid escaped in the plaintext: %s", pt);
    q = ji;
    q.ssid = "12345678901234567890123456789012";
    q.pass = "123456789012345678901234567890123456789012345678901234567890123";
    q.token = "0123456789abcdef0123456789abcdef";
    n = espnow::buildJoinPlaintext(q, pt, sizeof pt, &withSid);
    LCHECK(n == 206 && withSid, "32 + 63 + a 32-char token still fits with the sid (%u)", (unsigned)n);
    q.token = "0123456789abcdef0123456789abcdef0123456789abcdef";
    n = espnow::buildJoinPlaintext(q, pt, sizeof pt, &withSid);
    LCHECK(n == 197 && !withSid, "with a 48-char token it fits only without the sid (%u)", (unsigned)n);
    q.token = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
    q.host = "192.168.100.100";
    n = espnow::buildJoinPlaintext(q, pt, sizeof pt, &withSid);
    LCHECK(n == 0, "the spec's largest join (32 + 63 + 64-char token) cannot fit in one ESP-NOW packet");
  }
  // link key hex
  {
    char hx[65];
    uint8_t back[32];
    espnow::toHex(key, 32, hx);
    LCHECK(strlen(hx) == 64 && espnow::fromHex(hx, back, 32) && !memcmp(back, key, 32), "link key hex round trip");
    LCHECK(!espnow::fromHex("00", back, 32) && !espnow::fromHex(std::string(64, 'g').c_str(), back, 32), "bad hex refused");
  }
}

int cmdLink(int argc, char** argv) {
  if (argc < 3) { printf("usage: face_pc link <ble_vectors.txt>\n"); return 2; }
  int nEnc = 0, nDec = 0;
  testVectors(argv[2], &nEnc, &nDec);
  LCHECK(nEnc >= 7 && nDec >= 6, "vector file has %d encode and %d decode cases", nEnc, nDec);
  testFramingExtra();
  testPolicy();
  testEspNow();
  printf("link test: %s (%d checks, %d failure%s; BLE vectors: %d encode + %d decode cases)\n", lfails ? "FAILED" : "ok",
         lchecks, lfails, lfails == 1 ? "" : "s", nEnc, nDec);
  return lfails ? 1 : 0;
}

int cmdPasskey(int argc, char** argv) {
  if (argc < 3) { printf("usage: face_pc passkey <out.png> [passkey] [remaining]\n"); return 2; }
  const int W = 480, H = 272;
  uint32_t pk = argc > 3 ? (uint32_t)strtoul(argv[3], nullptr, 10) : 482917;
  float rem = argc > 4 ? (float)atof(argv[4]) : 0.7f;
  std::vector<uint8_t> px((size_t)W * H * 3, 0);
  for (size_t i = 0; i < px.size(); i += 3) { px[i] = 0xF2; px[i + 1] = 0xC9; px[i + 2] = 0x8A; }  // a fur-coloured backdrop
  Rgb888Surface surf(px.data(), W, H);
  static VectorGfx G;
  if (!G.ok()) return 3;
  G.setSurface(&surf);
  drawPasskeyOverlay(G, pk, rem, (float)W, (float)H);
  if (!pngw::writeRgb(argv[2], px.data(), W, H)) { printf("cannot write %s\n", argv[2]); return 3; }
  printf("wrote %s (passkey %06u)\n", argv[2], (unsigned)pk);
  return 0;
}
