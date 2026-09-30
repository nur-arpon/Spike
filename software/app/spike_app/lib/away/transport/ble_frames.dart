/// BLE framing of PROTOCOL.md 11.2 (v1.3): one JSON message = one or more
/// frames, each a 1-byte header + a piece of the UTF-8 bytes.
///
///     header: bit 7 START, bit 6 END, bits 5..0 frame counter (0..63)
///
/// The same rules are implemented by the screen board (C++) and the fake robot
/// (Python, `protocol/tools/ble_frames.py`); all three replay
/// `protocol/ble_frame_vectors.json` in their tests.
library;

import 'dart:typed_data';

const int bleFrameStart = 0x80;
const int bleFrameEnd = 0x40;
const int bleFrameCounterMask = 0x3F;

/// Largest message allowed over BLE (bigger ones go over the hotspot).
const int bleMaxMessage = 16 * 1024;

/// Bytes of message per frame for a negotiated ATT MTU (ATT header 3 + our header 1).
int blePayloadSize(int attMtu) => attMtu - 4 < 1 ? 1 : attMtu - 4;

class BleFrameEncoder {
  int counter = 0;

  void reset() => counter = 0;

  /// Frames for [message]. Throws [ArgumentError] over [bleMaxMessage].
  List<Uint8List> encode(List<int> message, int attMtu) {
    if (message.length > bleMaxMessage) throw ArgumentError('message over 16 KiB');
    final size = blePayloadSize(attMtu);
    final n = message.isEmpty ? 1 : (message.length + size - 1) ~/ size;
    final out = <Uint8List>[];
    for (var i = 0; i < n; i++) {
      final start = i * size;
      final end = start + size > message.length ? message.length : start + size;
      final f = Uint8List(1 + end - start);
      var h = counter & bleFrameCounterMask;
      if (i == 0) h |= bleFrameStart;
      if (i == n - 1) h |= bleFrameEnd;
      f[0] = h;
      f.setRange(1, f.length, message, start);
      out.add(f);
      counter = (counter + 1) & bleFrameCounterMask;
    }
    return out;
  }
}

class BleFrameDecoder {
  int? _expected;
  BytesBuilder? _buf;
  bool _skip = false;

  /// Messages thrown away (lost frames, a restart, or too big).
  int dropped = 0;

  /// Set once a message over [bleMaxMessage] arrived (answer `error too_big` once).
  bool tooBig = false;

  void reset() {
    _expected = null;
    _buf = null;
    _skip = false;
  }

  /// Feed one frame; returns a finished message's bytes, or null.
  Uint8List? feed(List<int> frame) {
    if (frame.isEmpty) return null;
    final header = frame[0];
    final counter = header & bleFrameCounterMask;
    if (_expected != null && counter != _expected) {
      if (_buf != null) dropped++; // frames were lost: drop the partial message
      _buf = null;
      _skip = false;
    }
    _expected = (counter + 1) & bleFrameCounterMask;
    if (header & bleFrameStart != 0) {
      if (_buf != null) dropped++; // a new message while one was open
      _buf = BytesBuilder(copy: false);
      _skip = false;
    } else if (_buf == null) {
      return null; // a continuation with nothing open
    }
    final end = header & bleFrameEnd != 0;
    if (_skip) {
      if (end) {
        _buf = null;
        _skip = false;
      }
      return null;
    }
    _buf!.add(Uint8List.fromList(frame.sublist(1)));
    if (_buf!.length > bleMaxMessage) {
      dropped++;
      tooBig = true;
      _skip = !end;
      _buf = _skip ? BytesBuilder(copy: false) : null;
      return null;
    }
    if (end) {
      final msg = _buf!.takeBytes();
      _buf = null;
      return msg;
    }
    return null;
  }
}
