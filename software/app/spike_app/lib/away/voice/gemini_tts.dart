/// Gemini TTS: a sentence from the phone brain spoken in Spike's or Spicy's
/// chosen Google voice, steered with a natural-language style prompt.
///
/// Checked 30 Sep 2026 (ai.google.dev speech-generation): TTS now goes through
/// POST /v1beta/interactions (not generateContent):
///   {"model": "gemini-3.8-flash-tts",
///    "input": [{"type": "user_input", "content": [{"type": "text", "text": "...",
///               "annotations": [{"type": "speech_metadata", "style": "..."}]}]}],
///    "response_format": {"type": "audio"},
///    "generation_config": {"speech_config": [{"voice": "Puck"}]}}
/// and the answer's audio is steps[].content[] {type: "audio", data: base64},
/// a WAV at 24 kHz for a one-shot request. Both 3.8 TTS models are on the
/// free tier; Flash is tried first (better acting), Flash-Lite when Flash's
/// free quota is used up.
///
/// When every model is rate limited the voice rests for a while and throws, so
/// the voice chain quietly uses the next voice (Kokoro, then Android's). The
/// key goes in the header only; errors never contain it.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:http/http.dart' as http;

import '../ai/gemini_voices.dart';
import 'level_match.dart';
import 'speaker.dart';

const ttsModels = ['gemini-3.8-flash-tts', 'gemini-3.8-flash-lite-tts'];

class TtsError implements Exception {
  const TtsError(this.kind, [this.message = '']);
  final String kind; // rate_limited | bad_key | resting | network | other
  final String message;
  @override
  String toString() => 'TtsError($kind, $message)';
}

/// The request body (pure, tested).
Map<String, Object?> ttsBody(String model, String text, String voice, String style) => {
      'model': model,
      'input': [
        {
          'type': 'user_input',
          'content': [
            {
              'type': 'text',
              'text': text,
              'annotations': [
                {'type': 'speech_metadata', 'style': style}
              ],
            }
          ],
        }
      ],
      'response_format': {'type': 'audio'},
      'generation_config': {
        'speech_config': [
          {'voice': voice}
        ]
      },
    };

/// The audio in an interactions answer as WAV bytes (raw L16 24 kHz is wrapped), or null.
Uint8List? ttsAudio(Object? json) {
  String? data;
  void walk(Object? o) {
    if (o is Map) {
      if (o['type'] == 'audio' && o['data'] is String) data = o['data'] as String;
      for (final v in o.values) {
        walk(v);
      }
    } else if (o is List) {
      for (final v in o) {
        walk(v);
      }
    }
  }

  walk(json);
  if (data == null) return null;
  final bytes = base64Decode(data!);
  if (bytes.length > 12 && String.fromCharCodes(bytes.sublist(0, 4)) == 'RIFF') return bytes;
  return pcmToWav(bytes, 24000);
}

Uint8List pcmToWav(Uint8List pcm, int rate) {
  final n = pcm.length & ~1;
  final b = ByteData(44);
  void s(int o, String t) {
    for (var i = 0; i < 4; i++) {
      b.setUint8(o + i, t.codeUnitAt(i));
    }
  }

  s(0, 'RIFF');
  b.setUint32(4, 36 + n, Endian.little);
  s(8, 'WAVE');
  s(12, 'fmt ');
  b.setUint32(16, 16, Endian.little);
  b.setUint16(20, 1, Endian.little);
  b.setUint16(22, 1, Endian.little);
  b.setUint32(24, rate, Endian.little);
  b.setUint32(28, rate * 2, Endian.little);
  b.setUint16(32, 2, Endian.little);
  b.setUint16(34, 16, Endian.little);
  s(36, 'data');
  b.setUint32(40, n, Endian.little);
  return Uint8List.fromList([...b.buffer.asUint8List(), ...pcm.sublist(0, n)]);
}

/// Samples of a 16-bit mono WAV (walks the chunks; tolerates odd headers).
(Float32List, int) wavSamples(Uint8List wav) {
  final bd = ByteData.sublistView(wav);
  var rate = 24000;
  var off = 12;
  while (off + 8 <= wav.length) {
    final id = String.fromCharCodes(wav.sublist(off, off + 4));
    var size = bd.getUint32(off + 4, Endian.little);
    if (id == 'fmt ') rate = bd.getUint32(off + 12, Endian.little);
    if (id == 'data') {
      if (size == 0 || off + 8 + size > wav.length) size = wav.length - off - 8; // streamed WAVs
      final n = size ~/ 2;
      final out = Float32List(n);
      for (var i = 0; i < n; i++) {
        out[i] = bd.getInt16(off + 8 + i * 2, Endian.little) / 32768.0;
      }
      return (out, rate);
    }
    off += 8 + size + (size & 1);
  }
  return (Float32List(0), rate);
}

class GeminiTtsVoice implements SpikeVoice {
  GeminiTtsVoice({
    required String apiKey,
    required this.voiceFor,
    this.styleFor,
    http.Client? client,
    AudioPlayer? player,
    this.models = ttsModels,
    this.timeout = const Duration(seconds: 12),
    this.rest = const Duration(minutes: 15),
    this.baseUrl = 'https://generativelanguage.googleapis.com/v1beta',
    DateTime Function()? clock,
  })  : _key = apiKey.trim(),
        _client = client ?? http.Client(),
        _playerOrNull = player,
        _clock = clock ?? DateTime.now;

  final String _key;
  final String Function(String mode) voiceFor;
  final String Function(String mode, bool soft)? styleFor; // the owner's picked style (default: the character's)
  final http.Client _client;
  AudioPlayer? _playerOrNull;
  final List<String> models;
  final Duration timeout;
  final Duration rest;
  final String baseUrl;
  final DateTime Function() _clock;
  final Map<String, DateTime> _restUntil = {}; // per model, after a 429
  bool _badKey = false;

  AudioPlayer get _player => _playerOrNull ??= AudioPlayer();

  @override
  String get name => 'Gemini voice';

  /// False while every model is resting after a 429, or the key was refused.
  bool get available => !_badKey && models.any((m) => !_resting(m));
  bool _resting(String m) => _restUntil[m] != null && _clock().isBefore(_restUntil[m]!);

  /// Synthesise [text] as WAV bytes (tests and the preview screen use this directly).
  Future<Uint8List> synth(String text, {required String mode, bool soft = false, String? voice, String? style}) async {
    if (_key.isEmpty || _badKey) throw const TtsError('bad_key');
    TtsError? last;
    for (final model in models) {
      if (_resting(model)) {
        last ??= const TtsError('resting');
        continue;
      }
      final http.Response r;
      try {
        r = await _client
            .post(Uri.parse('$baseUrl/interactions'),
                headers: {'Content-Type': 'application/json', 'x-goog-api-key': _key},
                body: jsonEncode(ttsBody(model, text, voice ?? voiceFor(mode), style ?? styleFor?.call(mode, soft) ?? ttsStyle(mode, soft: soft))))
            .timeout(timeout);
      } on TimeoutException {
        throw const TtsError('network', 'timed out');
      } catch (e) {
        throw TtsError('network', e.runtimeType.toString());
      }
      if (r.statusCode == 200) {
        final wav = ttsAudio(jsonDecode(r.body));
        if (wav == null) throw const TtsError('other', 'no audio in the answer');
        return wav;
      }
      final low = r.body.toLowerCase();
      if (r.statusCode == 429 || low.contains('resource_exhausted')) {
        _restUntil[model] = _clock().add(rest);
        last = TtsError('rate_limited', 'HTTP ${r.statusCode}');
        continue;
      }
      if (r.statusCode == 401 || r.statusCode == 403 || (r.statusCode == 400 && low.contains('api key'))) {
        _badKey = true;
        throw TtsError('bad_key', 'HTTP ${r.statusCode}');
      }
      if (r.statusCode == 404) {
        _restUntil[model] = _clock().add(const Duration(days: 1)); // that model is gone
        last = const TtsError('other', 'HTTP 404');
        continue;
      }
      throw TtsError('other', 'HTTP ${r.statusCode}');
    }
    throw last ?? const TtsError('other', 'no TTS model');
  }

  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    final raw = await synth(text, mode: mode, soft: soft);
    final (heard, rate) = wavSamples(raw);
    final samples = levelMatch(heard, rate); // to the laptop voice's -21 dBFS (level_match.dart)
    final wav = wavBytes(samples, rate);
    final f = File('${Directory.systemTemp.path}/spike_gtts_${DateTime.now().microsecondsSinceEpoch}.wav');
    await f.writeAsBytes(wav, flush: true);
    return WavFileSpeech(_player, f,
        SpokenClip(durationMs: rate == 0 ? 0 : samples.length * 1000 ~/ rate, mouth: mouthEnvelope(samples, rate)));
  }

  @override
  Future<void> stop() async => _playerOrNull?.stop();

  void close() {
    _client.close();
    _playerOrNull?.dispose();
  }
}

/// A WAV file played once and deleted.
class WavFileSpeech implements PreparedSpeech {
  WavFileSpeech(this._player, this._file, this.clip);
  final AudioPlayer _player;
  final File _file;
  @override
  final SpokenClip clip;

  @override
  Future<void> play() async {
    final done = Completer<void>();
    final sub = _player.onPlayerStateChanged.listen((s) {
      if ((s == PlayerState.completed || s == PlayerState.stopped) && !done.isCompleted) done.complete();
    });
    try {
      await _player.play(DeviceFileSource(_file.path));
      await done.future.timeout(Duration(milliseconds: clip.durationMs + 3000), onTimeout: () {});
    } finally {
      await sub.cancel();
      if (await _file.exists()) await _file.delete();
    }
  }
}
