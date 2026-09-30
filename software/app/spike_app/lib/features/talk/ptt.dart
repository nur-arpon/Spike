import 'dart:async';
import 'dart:math';
import 'dart:typed_data';

import 'package:record/record.dart';

/// The phone's microphone as Spike's ear at home (PROTOCOL.md 6.7): 16 kHz mono
/// pcm_s16le, streamed by the voice session (lib/state/voice.dart) to the laptop
/// brain in 40 ms `audio` chunks. Audio only ever goes to the brain on the
/// owner's own network (home Wi-Fi, or his Tailscale), never anywhere else.
///
/// (This file held the old press-and-hold controller; since 30 Sep the mic is
/// tap to start, tap to stop, and the session lives in a global provider.)
abstract class MicStream {
  /// Asks Android for the microphone the first time.
  Future<bool> hasPermission();
  Future<Stream<Uint8List>> start();
  Future<void> stop();
}

class RecordMic implements MicStream {
  static const rate = 16000;
  AudioRecorder? _rec;

  @override
  Future<bool> hasPermission() => (_rec ??= AudioRecorder()).hasPermission();

  @override
  Future<Stream<Uint8List>> start() => (_rec ??= AudioRecorder()).startStream(const RecordConfig(
        encoder: AudioEncoder.pcm16bits,
        sampleRate: rate,
        numChannels: 1,
        autoGain: true,
        echoCancel: true, // Spike's voice from the phone or the robot, cancelled where the phone can
        noiseSuppress: true,
      ));

  @override
  Future<void> stop() async {
    try {
      await _rec?.stop();
    } catch (_) {}
  }
}

/// Loudness of a pcm_s16le chunk, 0..1, for the waveform.
double pcmLevel(Uint8List data) {
  final bd = ByteData.sublistView(data);
  final n = data.lengthInBytes ~/ 2;
  if (n == 0) return 0;
  var sum = 0.0;
  for (var i = 0; i < n; i++) {
    final s = bd.getInt16(i * 2, Endian.little) / 32768.0;
    sum += s * s;
  }
  return (sqrt(sum / n) * 6).clamp(0.0, 1.0).toDouble();
}

/// Cuts a byte stream into fixed chunks (the protocol's 20..100 ms; we use 40 ms).
class PcmChunker {
  PcmChunker(this.chunkBytes);
  final int chunkBytes;
  final _buf = BytesBuilder(copy: false);

  /// Whole chunks ready to send; the remainder waits for the next call.
  List<Uint8List> add(Uint8List data) {
    _buf.add(data);
    final bytes = _buf.takeBytes();
    final out = <Uint8List>[];
    var off = 0;
    while (bytes.length - off >= chunkBytes) {
      out.add(Uint8List.sublistView(bytes, off, off + chunkBytes));
      off += chunkBytes;
    }
    if (off < bytes.length) _buf.add(Uint8List.sublistView(bytes, off));
    return out;
  }

  void clear() => _buf.clear();
}
