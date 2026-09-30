import 'dart:math';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/away/voice/level_match.dart';

/// A sine "voice" at [dbfs] RMS, [seconds] long, with optional silence appended.
Float32List tone(double dbfs, {double seconds = 1, double silence = 0, int rate = 24000}) {
  final amp = pow(10, dbfs / 20) * sqrt2;
  final n = (seconds * rate).round(), s = (silence * rate).round();
  return Float32List.fromList([for (var i = 0; i < n + s; i++) i < n ? amp * sin(2 * pi * 220 * i / rate) : 0.0]);
}

Uint8List pcm16(Float32List x) {
  final b = ByteData(x.length * 2);
  for (var i = 0; i < x.length; i++) {
    b.setInt16(i * 2, (x[i] * 32767).round(), Endian.little);
  }
  return b.buffer.asUint8List();
}

void main() {
  test('a quiet clip is raised to -21 dBFS, a loud one lowered', () {
    for (final start in [-33.0, -27.0, -15.0, -12.0]) {
      final y = levelMatch(tone(start), 24000);
      expect(speechRmsDbfs(y, 24000)!, closeTo(-21, 0.6), reason: 'from $start');
    }
  });

  test('pauses do not count as quiet: silence around the voice does not change the result', () {
    final y = levelMatch(tone(-30, silence: 2), 24000);
    expect(speechRmsDbfs(y, 24000)!, closeTo(-21, 0.6));
  });

  test('gain is clamped: near-silence is not turned into a roar, and silence is untouched', () {
    expect(gainDbFor(-70), maxBoostDb);
    expect(gainDbFor(0), maxCutDb);
    expect(gainDbFor(-21), 0);
    final z = Float32List(4800);
    expect(identical(levelMatch(z, 24000), z), isTrue);
    final hiss = tone(-45); // above nothing to fix: boosted by at most maxBoostDb
    expect(speechRmsDbfs(levelMatch(hiss, 24000), 24000)!, lessThan(-45 + maxBoostDb + 0.6));
  });

  test('the limiter never passes its ceiling and is continuous and symmetric', () {
    expect(softLimit(0.5), 0.5);
    expect(softLimit(limiterKnee), limiterKnee);
    for (final x in [0.71, 0.9, 1.0, 2.0, 10.0]) {
      expect(softLimit(x), lessThanOrEqualTo(limiterCeiling));
      expect(softLimit(-x), -softLimit(x));
    }
    expect(softLimit(limiterKnee + 1e-6) - limiterKnee, lessThan(1e-4));
    var last = 0.0;
    for (var x = 0.0; x < 3; x += 0.01) {
      expect(softLimit(x), greaterThanOrEqualTo(last), reason: 'monotonic at $x');
      last = softLimit(x);
    }
  });

  test('a peaky clip after gain never clips (peaks limited under the ceiling)', () {
    final x = tone(-30);
    x[100] = 0.9; // a click that the +9 dB gain would push far over full scale
    final y = levelMatch(x, 24000);
    expect(y.reduce(max), lessThanOrEqualTo(limiterCeiling));
  });

  test('16-bit PCM bytes round trip to the same level', () {
    final y = levelMatchPcm16(pcm16(tone(-30)), 24000);
    expect(y.length, pcm16(tone(-30)).length);
    final bd = ByteData.sublistView(y);
    final f = Float32List.fromList([for (var i = 0; i < y.length ~/ 2; i++) bd.getInt16(i * 2, Endian.little) / 32768]);
    expect(speechRmsDbfs(f, 24000)!, closeTo(-21, 0.6));
  });

  test('the streaming leveler settles on -21 dBFS within a phrase, in small pieces, and resets', () {
    final l = StreamLeveler();
    final src = pcm16(tone(-30, seconds: 3));
    final out = BytesBuilder();
    for (var i = 0; i < src.length; i += 2400) {
      out.add(l.process(Uint8List.sublistView(src, i, min(src.length, i + 2400)))); // 50 ms pieces
    }
    final y = out.toBytes();
    final bd = ByteData.sublistView(y);
    final tail = Float32List.fromList([for (var i = y.length ~/ 2 - 24000; i < y.length ~/ 2; i++) bd.getInt16(i * 2, Endian.little) / 32768]);
    expect(speechRmsDbfs(tail, 24000)!, closeTo(-21, 0.8));
    expect(l.gainDb, closeTo(9, 0.8));
    l.reset();
    expect(l.gainDb, closeTo(0, 1e-9));
    // an odd trailing byte is carried through, not dropped
    expect(l.process(Uint8List.fromList([1, 2, 3])).length, 3);
  });

  test('Android TTS cannot be processed: its volume is the full media volume', () {
    expect(androidTtsVolume, 1.0);
  });
}
