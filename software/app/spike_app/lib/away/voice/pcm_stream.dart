/// Streamed audio in and out for Gemini Live, behind two small interfaces so
/// the Live logic is tested without a speaker or a microphone.
///
/// Out: flutter_soloud's buffer stream (the package the laptop-voice agent
/// added for gapless PCM/Opus playback). Gemini sends 16-bit PCM at 24 kHz in
/// small pieces; they are fed straight in, so Spike starts talking as soon as
/// the first quarter second has arrived.
/// In: the `record` package, 16-bit PCM 16 kHz mono with the phone's echo
/// cancelling on (Spike's own voice must not come back in as the owner's).
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_soloud/flutter_soloud.dart';
import 'package:record/record.dart';

import 'level_match.dart';
import 'soloud_output.dart';

abstract class PcmSink {
  /// A new utterance at [rate] Hz (any previous one is cut).
  Future<void> begin(int rate);
  void feed(Uint8List pcm);

  /// No more data: completes once everything fed has been heard.
  Future<void> end();

  /// Cut now and drop whatever is buffered.
  Future<void> stop();
  bool get playing;

  /// Loudness 0..1 of the last piece fed (for the robot's mouth / the UI).
  double get level;
}

abstract class MicSource {
  /// 16 kHz mono s16le pieces, or null when the microphone is not allowed.
  Future<Stream<Uint8List>?> start();
  Future<void> stop();
}

double pcmLevel(Uint8List pcm) {
  final bd = ByteData.sublistView(pcm);
  final n = pcm.lengthInBytes ~/ 2;
  if (n == 0) return 0;
  var peak = 0;
  for (var i = 0; i < n; i += 8) {
    final s = bd.getInt16(i * 2, Endian.little).abs();
    if (s > peak) peak = s;
  }
  return (peak / 20000).clamp(0.0, 1.0).toDouble();
}

class SoloudPcmSink implements PcmSink {
  AudioSource? _src;
  SoundHandle? _handle;
  int _bytes = 0;
  int _rate = 24000;
  DateTime? _startedAt;
  double _level = 0;
  Uint8List _odd = Uint8List(0); // a half sample left over from the previous piece
  final _leveler = StreamLeveler(); // Gemini Live's voice to the laptop voice's -21 dBFS (level_match.dart)

  @override
  bool get playing => _src != null;
  @override
  double get level => _level;

  /// The one SoLoud engine, started the way the laptop voice starts it (soloud_output.dart).
  static Future<void> _ensure() async {
    await SoloudOutput.instance();
    if (!SoLoud.instance.isInitialized) await SoLoud.instance.init(channels: Channels.mono, sampleRate: 48000, bufferSize: 1024);
  }

  @override
  Future<void> begin(int rate) async {
    await stop();
    await _ensure();
    _rate = rate;
    _bytes = 0;
    _odd = Uint8List(0);
    _leveler.reset();
    _src = SoLoud.instance.setBufferStream(
      sampleRate: rate,
      channels: Channels.mono,
      format: BufferType.s16le,
      bufferingType: BufferingType.released,
      bufferingTimeNeeds: 0.25,
      maxBufferSizeDuration: const Duration(minutes: 3),
    );
  }

  @override
  void feed(Uint8List pcm) {
    final src = _src;
    if (src == null || pcm.isEmpty) return;
    var data = pcm;
    if (_odd.isNotEmpty) data = Uint8List.fromList([..._odd, ...pcm]);
    final even = data.length & ~1;
    _odd = even < data.length ? Uint8List.sublistView(data, even) : Uint8List(0);
    if (even == 0) return;
    final chunk = _leveler.process(Uint8List.sublistView(data, 0, even));
    _level = pcmLevel(chunk);
    SoLoud.instance.addAudioDataStream(src, chunk);
    _bytes += even;
    if (_handle == null) {
      _handle = SoLoud.instance.play(src);
      _startedAt = DateTime.now();
    }
  }

  @override
  Future<void> end() async {
    final src = _src, h = _handle;
    if (src == null) return;
    SoLoud.instance.setDataIsEnded(src);
    if (h != null) {
      final total = Duration(milliseconds: _bytes * 1000 ~/ (_rate * 2));
      final deadline = (_startedAt ?? DateTime.now()).add(total + const Duration(seconds: 3));
      while (identical(_src, src) && SoLoud.instance.getIsValidVoiceHandle(h) && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 80));
      }
    }
    if (identical(_src, src)) await stop();
  }

  @override
  Future<void> stop() async {
    final src = _src, h = _handle;
    _src = null;
    _handle = null;
    _level = 0;
    if (!SoLoud.instance.isInitialized) return;
    try {
      if (h != null) await SoLoud.instance.stop(h);
    } catch (_) {}
    try {
      if (src != null) await SoLoud.instance.disposeSource(src);
    } catch (_) {}
  }
}

class RecordMic implements MicSource {
  AudioRecorder? _rec;

  @override
  Future<Stream<Uint8List>?> start() async {
    final rec = _rec ??= AudioRecorder();
    if (!await rec.hasPermission()) return null;
    return rec.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
      autoGain: true,
      echoCancel: true,
      noiseSuppress: true,
    ));
  }

  @override
  Future<void> stop() async {
    try {
      await _rec?.stop();
    } catch (_) {}
  }

  Future<void> dispose() async {
    await stop();
    await _rec?.dispose();
    _rec = null;
  }
}
