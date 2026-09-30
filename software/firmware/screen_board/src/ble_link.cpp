// ble_link.cpp -- the phone's Bluetooth LE link (PROTOCOL.md v1.3, 11.1 to 11.3), NimBLE-Arduino 2.x.
//
//  GATT service "Spike link" c0de5b1e-0001-...: rx (write / write without response, encrypted +
//  authenticated), tx (notify), info (open read, <= 180 bytes of JSON). Advertises whenever no phone is
//  connected (service UUID in the advertisement, "Spike-xxxxxx" in the scan response); one central.
//
//  Security (DESIGN.md "v1.3 away mode"): LE Secure Connections ONLY (NimBLE's sm_sc_only refuses
//  legacy pairing and short keys), MITM, bonding, IO capability DisplayOnly: a random 6-digit passkey
//  per pairing is drawn big on the face (spike_passkey) for 60 s. At most 4 bonds; a new bond when
//  full replaces the least recently USED one (every authenticated reconnect moves the bond to the
//  young end of NimBLE's store). Nothing is sent to, or accepted from, a phone until its link is
//  encrypted + authenticated with a 16-byte SC key -- checked here in the application as well, because
//  NimBLE applies CCCD permissions to every CCCD at once (see OPEN_QUESTIONS F-2).
//
//  Threads: NimBLE's host task only runs the callbacks below, which copy frames / events into one
//  queue. The "blelink" task owns the framing codec: it rebuilds messages and hands them to the
//  shared brain handler (net.cpp), and it frames + notifies everything the robot sends, so callers
//  such as the body task never wait on the radio.
#include "app.h"
#include "config.h"

#include <NimBLEDevice.h>
#include <esp_heap_caps.h>
#include <esp_random.h>

#include "nimble/nimble/host/include/host/ble_gatt.h"
#include "nimble/nimble/host/include/host/ble_hs.h"
#include "nimble/nimble/host/include/host/ble_hs_mbuf.h"
#include "nimble/nimble/host/include/host/ble_store.h"
#include "spike_ble_frames.h"

#define SPIKE_SVC_UUID "c0de5b1e-0001-4a3c-9e5f-5370696b6500"
#define SPIKE_RX_UUID "c0de5b1e-0002-4a3c-9e5f-5370696b6500"
#define SPIKE_TX_UUID "c0de5b1e-0003-4a3c-9e5f-5370696b6500"
#define SPIKE_INFO_UUID "c0de5b1e-0004-4a3c-9e5f-5370696b6500"

static const uint32_t PAIRING_WINDOW_MS = 60000;   // passkey on screen; an unauthenticated link is dropped after
static const int TX_QUEUE_DEPTH = 48;
static const uint32_t NOTIFY_RETRY_MS = 10, NOTIFY_GIVE_UP_MS = 1500;

static NimBLEServer* server;
static NimBLECharacteristic *rxChr, *txChr, *infoChr;
static char advName[16];

// ---- state shared between the NimBLE host task, the blelink task and the loop -----------------------
static volatile uint16_t connHandle = BLE_HS_CONN_HANDLE_NONE;
static volatile bool authed = false;       // encrypted + authenticated + bonded + SC, 16-byte key
static volatile bool subscribed = false;   // tx notifications on
static volatile bool session = false;      // (blelink task) the protocol session runs: hello was sent
static volatile uint16_t attMtu = 23;
static volatile uint32_t connectedAtMs = 0;
static volatile uint32_t gen = 1;          // session generation: stale queued messages are dropped
static volatile bool passkeyOn = false;
static volatile uint32_t passkeyValue = 0, passkeyAtMs = 0;

enum EvType : uint8_t { EV_CONNECT, EV_DISCONNECT, EV_SESSION_START, EV_SESSION_END, EV_RX, EV_TX };
struct Ev {
  uint8_t type;
  uint16_t len;
  uint32_t gen;
  uint8_t* data;  // EV_RX / EV_TX: a heap copy (PSRAM), freed by the blelink task
};
static QueueHandle_t evQ;

// blelink task only
static spike::ble::FrameEncoder enc;
static spike::ble::FrameDecoder dec;
static uint32_t tooBigSeen = 0;

static bool olderThan(uint32_t t, uint32_t ms) { return (int32_t)(millis() - t) > (int32_t)ms; }  // t may be newer

static uint8_t* copyOf(const uint8_t* p, size_t n) {
  uint8_t* c = (uint8_t*)heap_caps_malloc(n ? n : 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!c) c = (uint8_t*)malloc(n ? n : 1);
  if (c && n) memcpy(c, p, n);
  return c;
}

static bool post(uint8_t type, const uint8_t* data = nullptr, size_t len = 0, TickType_t wait = 0) {
  Ev e{type, (uint16_t)len, gen, nullptr};
  if (data) {
    e.data = copyOf(data, len);
    if (!e.data) return false;
  }
  if (xQueueSend(evQ, &e, wait) != pdTRUE) {
    if (e.data) {
      memset(e.data, 0, len);  // may be a frame of a hotspot_join
      heap_caps_free(e.data);
    }
    return false;
  }
  return true;
}

// The link is good enough for Spike's data: SC pairing (sm_sc_only), MITM, bonded, full-size key.
static bool linkSecure(uint16_t h) {
  if (h == BLE_HS_CONN_HANDLE_NONE) return false;
  ble_gap_conn_desc d;
  if (ble_gap_conn_find(h, &d) != 0) return false;
  return d.sec_state.encrypted && d.sec_state.authenticated && d.sec_state.bonded && d.sec_state.key_size == 16;
}

// Least-recently-used bonds: NimBLE replaces the OLDEST entry of its store when a 5th phone bonds.
// Deleting and re-writing a bond's records moves it to the young end, so "oldest" = least recently used.
// Runs in the host task (the store is only touched there). Also refuses a non-SC bond, belt and braces.
static bool touchBond(const ble_addr_t* peerId) {
  ble_store_key_sec key;
  memset(&key, 0, sizeof key);
  key.peer_addr = *peerId;
  ble_store_value_sec ours, theirs;
  bool haveOurs = ble_store_read_our_sec(&key, &ours) == 0;
  bool haveTheirs = ble_store_read_peer_sec(&key, &theirs) == 0;
  if (!haveOurs) return true;  // nothing stored (yet): nothing to refresh
  if (!ours.sc || !ours.authenticated) return false;
  ble_store_delete_our_sec(&key);
  if (haveTheirs) ble_store_delete_peer_sec(&key);
  ble_store_write_our_sec(&ours);
  if (haveTheirs) ble_store_write_peer_sec(&theirs);
  return true;
}

static void startSessionIfReady() {
  if (authed && subscribed) post(EV_SESSION_START, nullptr, 0, pdMS_TO_TICKS(100));
}

// ---- NimBLE callbacks (host task) --------------------------------------------------------------------
class ServerCb : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer* s, NimBLEConnInfo& ci) override {
    if (connHandle != BLE_HS_CONN_HANDLE_NONE) {  // one phone at a time
      s->disconnect(ci.getConnHandle());
      return;
    }
    connHandle = ci.getConnHandle();
    authed = false;
    subscribed = false;
    attMtu = ci.getMTU();
    connectedAtMs = millis();
    post(EV_CONNECT, nullptr, 0, pdMS_TO_TICKS(100));
    ble_gattc_exchange_mtu(ci.getConnHandle(), nullptr, nullptr);  // ask for our 517 as well
    s->setDataLen(ci.getConnHandle(), 251);
    logf("ble: phone connected (%s)", ci.getAddress().toString().c_str());
  }
  void onDisconnect(NimBLEServer*, NimBLEConnInfo& ci, int reason) override {
    if (ci.getConnHandle() != connHandle) return;
    connHandle = BLE_HS_CONN_HANDLE_NONE;
    authed = false;
    subscribed = false;
    passkeyOn = false;
    gen++;
    post(EV_DISCONNECT, nullptr, 0, pdMS_TO_TICKS(100));
    logf("ble: phone disconnected (reason 0x%x); advertising again", reason);
  }
  void onMTUChange(uint16_t mtu, NimBLEConnInfo& ci) override {
    if (ci.getConnHandle() == connHandle) attMtu = mtu;
  }
  uint32_t onPassKeyDisplay() override {
    // a fresh uniform 6-digit passkey per pairing (rejection sampling: no modulo bias)
    uint32_t r;
    do r = esp_random(); while (r >= 4294000000u);
    passkeyValue = r % 1000000u;
    passkeyAtMs = millis();
    passkeyOn = true;
    logf("ble: a phone is pairing -- the passkey is on Spike's screen");
    return passkeyValue;
  }
  void onAuthenticationComplete(NimBLEConnInfo& ci) override {
    passkeyOn = false;
    if (ci.getConnHandle() != connHandle) return;
    bool ok = ci.isEncrypted() && ci.isAuthenticated() && ci.isBonded() && ci.getSecKeySize() == 16;
    if (ok) ok = touchBond(ci.getIdAddress().getBase());
    if (!ok) {
      logf("ble: pairing failed or not secure enough (enc %d, mitm %d, bond %d, key %d) -- disconnecting", ci.isEncrypted(),
           ci.isAuthenticated(), ci.isBonded(), ci.getSecKeySize());
      if (ci.isBonded()) NimBLEDevice::deleteBond(ci.getIdAddress());
      server->disconnect(ci.getConnHandle());
      return;
    }
    authed = true;
    logf("ble: phone authenticated (bonded, LE Secure Connections)");
    startSessionIfReady();
  }
};

class RxCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo& ci) override {
    if (ci.getConnHandle() != connHandle || !authed) return;  // the stack already demands MITM encryption
    const NimBLEAttValue& v = c->getValue();
    if (v.size() == 0 || v.size() > spike::ble::kMaxAttMtu) return;
    if (!post(EV_RX, v.data(), v.size(), 0)) {
      // queue full: this frame is lost; the decoder sees the counter gap and drops that message only
    }
  }
};

class TxCb : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic*, NimBLEConnInfo& ci, uint16_t subValue) override {
    if (ci.getConnHandle() != connHandle) return;
    bool on = (subValue & 1) != 0;
    if (on == subscribed) return;
    subscribed = on;
    if (!on) {
      gen++;
      post(EV_SESSION_END, nullptr, 0, pdMS_TO_TICKS(100));
      return;
    }
    if (!authed) {
      // Not paired yet (or not re-encrypted): ask the phone to secure the link. Nothing is sent before.
      NimBLEDevice::startSecurity(ci.getConnHandle());
      return;
    }
    startSessionIfReady();
  }
};

class InfoCb : public NimBLECharacteristicCallbacks {
  void onRead(NimBLECharacteristic* c, NimBLEConnInfo&) override {
    char j[180];
    snprintf(j, sizeof j, "{\"pv\":\"1.3\",\"fw\":\"%s\",\"device_id\":\"%s\",\"brain\":\"%s\"}", SPIKE_FW_VERSION, deviceId(),
             netBrainName());
    c->setValue((const uint8_t*)j, strlen(j));
  }
};

static ServerCb serverCb;
static RxCb rxCb;
static TxCb txCb;
static InfoCb infoCb;

// ---- blelink task: framing in and out ----------------------------------------------------------------
struct NotifyCtx {
  uint16_t conn;
  uint32_t gen;
};

// One frame = one notification. When NimBLE is out of buffers the frame is retried (this task only;
// no caller waits); a link that stays jammed for 1.5 s gives up the message, which the phone's decoder
// then sees as lost frames and drops cleanly.
static bool notifySink(void* ctxp, const uint8_t* f, size_t n) {
  NotifyCtx* ctx = (NotifyCtx*)ctxp;
  uint32_t t0 = millis();
  for (;;) {
    if (ctx->gen != gen || connHandle != ctx->conn) return false;
    os_mbuf* om = ble_hs_mbuf_from_flat(f, (uint16_t)n);
    if (om) {
      int rc = ble_gattc_notify_custom(ctx->conn, txChr->getHandle(), om);  // consumes om
      if (rc == 0) return true;
      if (rc != BLE_HS_ENOMEM && rc != BLE_HS_EBUSY) return false;
    }
    if (olderThan(t0, NOTIFY_GIVE_UP_MS)) return false;
    vTaskDelay(pdMS_TO_TICKS(NOTIFY_RETRY_MS));
  }
}

static void sendFramed(const uint8_t* msg, size_t len) {
  NotifyCtx ctx{connHandle, gen};
  if (enc.encode(msg, len, attMtu, notifySink, &ctx) < 0)
    logf("ble: a %u-byte message could not be sent (link jammed, gone, or over 16 KiB)", (unsigned)len);
}

static void linkTask(void*) {
  for (;;) {
    Ev e;
    if (xQueueReceive(evQ, &e, portMAX_DELAY) != pdTRUE) continue;
    switch (e.type) {
      case EV_CONNECT:
        dec.reset();  // the phone's counter starts at 0 on its first write after connecting
        tooBigSeen = dec.tooBigEvents();
        break;
      case EV_DISCONNECT:
      case EV_SESSION_END:
        if (session) {
          session = false;
          netBleSessionEnd();
        }
        break;
      case EV_SESSION_START:
        if (e.gen != gen || session || !authed || !subscribed) break;
        enc.reset();  // the robot's counter starts at 0 when the phone subscribes to tx
        session = true;
        netBleSessionStart();  // queues our hello
        break;
      case EV_RX:
        if (session && e.gen == gen && linkSecure(connHandle)) {
          const uint8_t* m;
          size_t ml;
          if (dec.feed(e.data, e.len, &m, &ml)) netHandleMessage(LINK_BLE, (char*)m, ml);
          if (dec.tooBigEvents() != tooBigSeen) {
            tooBigSeen = dec.tooBigEvents();
            netBleTooBig();
          }
        }
        break;
      case EV_TX:
        if (session && e.gen == gen && linkSecure(connHandle)) sendFramed(e.data, e.len);
        break;
    }
    if (e.data) {
      if (e.type == EV_RX) {  // a frame of hotspot_join carries the hotspot password: zero it before freeing
        volatile uint8_t* v = e.data;
        for (uint16_t i = 0; i < e.len; i++) v[i] = 0;
      }
      heap_caps_free(e.data);
    }
  }
}

// ---- API -----------------------------------------------------------------------------------------------
bool bleQueueMessage(const char* json, size_t len) {
  if (!evQ || !session || len > spike::ble::kMaxMessage) return false;
  return post(EV_TX, (const uint8_t*)json, len, 0);  // never blocks the caller (the body task sends too)
}

bool bleConnected() { return connHandle != BLE_HS_CONN_HANDLE_NONE && authed; }

bool blePasskey(uint32_t* pk, float* remaining) {
  if (!passkeyOn) return false;
  int32_t age = (int32_t)(millis() - passkeyAtMs);
  if (age < 0) age = 0;  // stamped by the host task just now
  if (age >= (int32_t)PAIRING_WINDOW_MS) return false;
  *pk = passkeyValue;
  *remaining = 1.0f - (float)age / PAIRING_WINDOW_MS;
  return true;
}

void bleDisconnect(const char* why) {
  uint16_t h = connHandle;
  if (h == BLE_HS_CONN_HANDLE_NONE || !server) return;
  logf("ble: closing the phone link: %s", why);
  server->disconnect(h);
}

void bleForgetAll() {
  if (!server) return;
  bleDisconnect("forgetting every paired phone");
  bool ok = NimBLEDevice::deleteAllBonds();
  logf("ble: %s", ok ? "all pairings forgotten -- phones must pair again (passkey on the screen)" : "could not delete the pairings");
}

void bleConsole(const char* args) {
  while (*args == ' ') args++;
  if (!strncmp(args, "forget", 6)) { bleForgetAll(); return; }
  if (!server) { logf("ble: not started"); return; }
  uint16_t h = connHandle;
  if (h != BLE_HS_CONN_HANDLE_NONE) {
    NimBLEConnInfo ci = server->getPeerInfoByHandle(h);
    logf("ble: %s | phone %s | %s | tx %s | session %s | ATT MTU %u | brain %s", advName, ci.getAddress().toString().c_str(),
         authed ? "paired + encrypted (SC, MITM)" : (passkeyOn ? "pairing (passkey on screen)" : "not paired"),
         subscribed ? "subscribed" : "off", session ? "running" : "off", (unsigned)attMtu, netBrainName());
  } else {
    logf("ble: %s | no phone connected | advertising %s", advName, NimBLEDevice::getAdvertising()->isAdvertising() ? "yes" : "no");
  }
  int n = NimBLEDevice::getNumBonds();
  logf("ble: %d of %d paired phones (least recently used first):", n, CONFIG_BT_NIMBLE_MAX_BONDS);
  for (int i = 0; i < n; i++) logf("  %d  %s", i + 1, NimBLEDevice::getBondedAddress(i).toString().c_str());
  logf("ble: 'ble forget' forgets them all");
}

void bleLoop() {
  // the passkey overlay and an unauthenticated connection both end with the 60 s pairing window
  uint16_t h = connHandle;
  if (passkeyOn && olderThan(passkeyAtMs, PAIRING_WINDOW_MS)) passkeyOn = false;
  if (h != BLE_HS_CONN_HANDLE_NONE && !authed && olderThan(connectedAtMs, PAIRING_WINDOW_MS + 2000))
    bleDisconnect("not paired within 60 s");
}

void bleBegin() {
  snprintf(advName, sizeof advName, "Spike-%s", deviceId() + 6);  // the last 6 of device_id
  evQ = xQueueCreate(TX_QUEUE_DEPTH, sizeof(Ev));
  uint8_t* rxBuf = (uint8_t*)heap_caps_malloc(spike::ble::kMaxMessage + 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!evQ || !rxBuf) {
    logf("ble: out of memory -- Bluetooth off");
    return;
  }
  dec.setBuffer(rxBuf);
  if (!NimBLEDevice::init(advName)) {
    logf("ble: NimBLE init failed -- Bluetooth off");
    return;
  }
  NimBLEDevice::setMTU(spike::ble::kMaxAttMtu);
  NimBLEDevice::setSecurityAuth(true /* bonding */, true /* MITM */, true /* LE Secure Connections */);
  NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
  ble_hs_cfg.sm_sc_only = 1;  // refuse legacy pairing and keys under 16 bytes (NimBLE ble_sm.c)

  server = NimBLEDevice::createServer();
  server->setCallbacks(&serverCb, false);
  server->advertiseOnDisconnect(true);
  NimBLEService* svc = server->createService(SPIKE_SVC_UUID);
  rxChr = svc->createCharacteristic(SPIKE_RX_UUID, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR |
                                                       NIMBLE_PROPERTY::WRITE_ENC | NIMBLE_PROPERTY::WRITE_AUTHEN,
                                    spike::ble::kMaxAttMtu);
  txChr = svc->createCharacteristic(SPIKE_TX_UUID, NIMBLE_PROPERTY::NOTIFY, spike::ble::kMaxAttMtu);
  infoChr = svc->createCharacteristic(SPIKE_INFO_UUID, NIMBLE_PROPERTY::READ, 180);
  rxChr->setCallbacks(&rxCb);
  txChr->setCallbacks(&txCb);
  infoChr->setCallbacks(&infoCb);
  infoChr->setValue("{}");
  server->start();

  NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
  NimBLEAdvertisementData ad, sr;
  ad.setFlags(BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP);
  ad.setCompleteServices(NimBLEUUID(SPIKE_SVC_UUID));
  sr.setName(advName);
  adv->setAdvertisementData(ad);
  adv->setScanResponseData(sr);
  adv->enableScanResponse(true);
  xTaskCreatePinnedToCore(linkTask, "blelink", 8192, nullptr, 4, nullptr, 0);
  bool ok = NimBLEDevice::startAdvertising();
  logf("ble: advertising as %s (%s), %d paired phone(s)", advName, ok ? "on" : "FAILED", NimBLEDevice::getNumBonds());
}
