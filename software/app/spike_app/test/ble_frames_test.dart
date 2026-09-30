// BLE framing (PROTOCOL.md 11.2) against the shared vectors that the firmware
// and the fake robot replay too (software/protocol/ble_frame_vectors.json).
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/away/transport/ble_frames.dart';

String hex(List<int> b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();
Uint8List unhex(String s) =>
    Uint8List.fromList([for (var i = 0; i < s.length; i += 2) int.parse(s.substring(i, i + 2), radix: 16)]);

void main() {
  final file = File('../../protocol/ble_frame_vectors.json');
  final vectors = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;

  test('the vectors file is the v1.3 one', () {
    expect(vectors['max_message'], bleMaxMessage);
    expect((vectors['encode'] as List).length, greaterThanOrEqualTo(7));
    expect((vectors['decode'] as List).length, greaterThanOrEqualTo(6));
  });

  for (final c in (vectors['encode'] as List).cast<Map<String, dynamic>>()) {
    test('encode: ${c['name']}', () {
      final e = BleFrameEncoder()..counter = c['start_counter'] as int;
      final frames = e.encode(utf8.encode(c['message'] as String), c['att_mtu'] as int);
      expect(frames.map(hex).toList(), c['frames']);
      // and it decodes back
      final d = BleFrameDecoder();
      Uint8List? out;
      for (final f in frames) {
        out = d.feed(f) ?? out;
      }
      expect(utf8.decode(out!), c['message']);
    });
  }

  for (final c in (vectors['decode'] as List).cast<Map<String, dynamic>>()) {
    test('decode: ${c['name']}', () {
      final d = BleFrameDecoder();
      final got = <String>[];
      for (final f in (c['frames'] as List).cast<String>()) {
        final m = d.feed(unhex(f));
        if (m != null) got.add(utf8.decode(m));
      }
      expect(got, c['messages']);
      expect(d.dropped, c['dropped']);
      expect(d.tooBig, c['too_big']);
    });
  }

  test('the encoder refuses a message over 16 KiB', () {
    expect(() => BleFrameEncoder().encode(List.filled(bleMaxMessage + 1, 65), 517), throwsArgumentError);
  });

  test('payload size follows the MTU, never below one byte', () {
    expect(blePayloadSize(23), 19);
    expect(blePayloadSize(517), 513);
    expect(blePayloadSize(3), 1);
  });
}
