// spike_ble_frames.h -- the BLE framing of PROTOCOL.md 11.2 (v1.3). Platform-free (PC tests + ESP32).
//
// One protocol message (a UTF-8 JSON object) travels as one or more frames; a frame is one write to
// `rx` or one notification on `tx`:
//     byte 0   header: bit 7 START, bit 6 END, bits 5..0 frame counter (0..63, per direction)
//     byte 1.. the next piece of the message
// The C++ codec reproduces software/protocol/tools/ble_frames.py (the reference) exactly, including
// its `dropped` / `too_big` bookkeeping; `face_pc link` replays ble_frame_vectors.json against it.
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace spike {
namespace ble {

constexpr uint8_t kStart = 0x80;
constexpr uint8_t kEnd = 0x40;
constexpr uint8_t kCounterMask = 0x3F;
constexpr size_t kMaxMessage = 16 * 1024;  // a longer message is dropped by the receiver
constexpr uint16_t kMinAttMtu = 23;
constexpr uint16_t kMaxAttMtu = 517;       // the largest ATT_MTU BLE allows; the encoder clamps to it

// Message bytes per frame for a negotiated ATT MTU (ATT header 3, our header 1), at least 1.
inline size_t payloadSize(uint16_t attMtu) {
  if (attMtu > kMaxAttMtu) attMtu = kMaxAttMtu;
  return attMtu > 4 ? (size_t)attMtu - 4 : 1;
}

// Receives each frame the encoder makes. Return false to stop (the rest of the message is not sent;
// the frame counter has still advanced for the frames already made, which the peer's decoder
// treats as lost frames -- it drops the partial message and resynchronises on the next START).
typedef bool (*FrameSink)(void* ctx, const uint8_t* frame, size_t len);

// Cuts messages into frames. One encoder per direction per connection.
class FrameEncoder {
 public:
  void reset() { counter_ = 0; }
  void setCounter(uint8_t c) { counter_ = c & kCounterMask; }
  uint8_t counter() const { return counter_; }
  // Returns the number of frames handed to the sink, or -1 when the message is over 16 KiB (nothing
  // is sent) or the sink stopped early.
  int encode(const uint8_t* msg, size_t len, uint16_t attMtu, FrameSink sink, void* ctx);

 private:
  uint8_t counter_ = 0;
};

// Rebuilds messages from frames into a caller-owned buffer of at least kMaxMessage + 1 bytes (the
// finished message is NUL-terminated for the JSON parser). feed() returns true when a message is
// complete; it stays valid until the next feed().
class FrameDecoder {
 public:
  explicit FrameDecoder(uint8_t* buf = nullptr) : buf_(buf) {}
  void setBuffer(uint8_t* buf) { buf_ = buf; }
  // Forget the message being built and the expected counter (a new connection). The statistics
  // below are kept; clearStats() zeroes them.
  void reset();
  void clearStats() { dropped_ = 0; tooBig_ = false; tooBigEvents_ = 0; }
  bool feed(const uint8_t* frame, size_t len, const uint8_t** msg, size_t* msgLen);

  // Messages thrown away (lost frames, a restart, or too big), as ble_frames.py `dropped`.
  uint32_t dropped() const { return dropped_; }
  // Set once any message was too big (ble_frames.py `too_big`).
  bool tooBig() const { return tooBig_; }
  // How many over-long messages were seen: the receiver answers `error too_big` once per event.
  uint32_t tooBigEvents() const { return tooBigEvents_; }

 private:
  uint8_t* buf_;
  size_t len_ = 0;
  bool open_ = false;     // a message is being built (ble_frames.py: buf is not None)
  bool skip_ = false;     // skipping the rest of an over-long message
  bool haveExpected_ = false;
  uint8_t expected_ = 0;
  uint32_t dropped_ = 0;
  bool tooBig_ = false;
  uint32_t tooBigEvents_ = 0;
};

}  // namespace ble
}  // namespace spike
