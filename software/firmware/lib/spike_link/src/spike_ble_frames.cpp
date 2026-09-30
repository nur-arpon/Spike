// spike_ble_frames.cpp -- see spike_ble_frames.h. Mirrors software/protocol/tools/ble_frames.py
// line by line; the vectors in software/protocol/ble_frame_vectors.json are the contract.
#include "spike_ble_frames.h"

#include <string.h>

namespace spike {
namespace ble {

int FrameEncoder::encode(const uint8_t* msg, size_t len, uint16_t attMtu, FrameSink sink, void* ctx) {
  if (len > kMaxMessage) return -1;
  const size_t size = payloadSize(attMtu);
  uint8_t frame[kMaxAttMtu];  // 1 header byte + at most kMaxAttMtu - 4 payload bytes
  const size_t pieces = len == 0 ? 1 : (len + size - 1) / size;
  int sent = 0;
  for (size_t i = 0; i < pieces; i++) {
    const size_t off = i * size;
    const size_t n = len == 0 ? 0 : (len - off < size ? len - off : size);
    uint8_t header = counter_ & kCounterMask;
    if (i == 0) header |= kStart;
    if (i == pieces - 1) header |= kEnd;
    frame[0] = header;
    if (n) memcpy(frame + 1, msg + off, n);
    counter_ = (uint8_t)((counter_ + 1) & kCounterMask);
    if (!sink(ctx, frame, n + 1)) return -1;
    sent++;
  }
  return sent;
}

void FrameDecoder::reset() {
  len_ = 0;
  open_ = false;
  skip_ = false;
  haveExpected_ = false;
  expected_ = 0;
}

bool FrameDecoder::feed(const uint8_t* frame, size_t len, const uint8_t** msg, size_t* msgLen) {
  if (!frame || len == 0 || !buf_) return false;
  const uint8_t header = frame[0];
  const uint8_t* payload = frame + 1;
  const size_t plen = len - 1;
  const uint8_t counter = header & kCounterMask;
  if (haveExpected_ && counter != expected_) {
    if (open_) dropped_++;  // frames were lost: drop the partial message
    open_ = false;
    len_ = 0;
    skip_ = false;
  }
  expected_ = (uint8_t)((counter + 1) & kCounterMask);
  haveExpected_ = true;
  if (header & kStart) {
    if (open_) dropped_++;  // a new message while one was open
    open_ = true;
    len_ = 0;
    skip_ = false;
  } else if (!open_) {
    return false;  // a continuation with nothing open: drop it
  }
  if (skip_) {
    if (header & kEnd) {
      open_ = false;
      skip_ = false;
    }
    return false;
  }
  if (len_ + plen > kMaxMessage) {  // ble_frames.py extends first, then compares: same outcome
    dropped_++;
    tooBig_ = true;
    tooBigEvents_++;
    skip_ = !(header & kEnd);
    open_ = skip_;  // ble_frames.py keeps an empty buffer while skipping, None otherwise
    len_ = 0;
    return false;
  }
  if (plen) memcpy(buf_ + len_, payload, plen);
  len_ += plen;
  if (header & kEnd) {
    buf_[len_] = 0;
    *msg = buf_;
    *msgLen = len_;
    open_ = false;
    len_ = 0;
    return true;
  }
  return false;
}

}  // namespace ble
}  // namespace spike
