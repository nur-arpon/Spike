/// Spike's voice on the phone while away (the robot has no audio link over
/// Bluetooth, so the phone speaks and the robot moves its mouth to it).
///
/// 1. Kokoro-82M on the phone (sherpa_onnx), the same voices the owner picked
///    for the laptop's Kokoro fallback: Spike = am_puck, Spicy = af_heart. The
///    voice pack (~380 MB) is downloaded only when the owner asks.
/// 2. Android's own text-to-speech (flutter_tts) otherwise, or if Kokoro fails.
///
/// Numbers the voice must say a certain way are spoken as the laptop does
/// ("000" -> "triple zero", default.toml say_as); captions keep "000".
library;

import 'dart:async';
import 'dart:io';
import 'dart:isolate';
import 'dart:math';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:sherpa_onnx/sherpa_onnx.dart' as sherpa;

import '../download/bundle.dart';
import '../download/downloads.dart' show hfTree;
import 'level_match.dart';

/// What was said, for the robot's mouth and the caption timing.
class SpokenClip {
  const SpokenClip({required this.durationMs, this.mouth, this.mouthHz = 50});
  final int durationMs;
  final List<int>? mouth; // 0..100 per 1/mouthHz s; null = babble
  final int mouthHz;
}

abstract class SpikeVoice {
  String get name;

  /// Prepare [text] (synthesise when the engine can) without playing it yet.
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false});
  Future<void> stop();
}

abstract class PreparedSpeech {
  SpokenClip get clip;

  /// Play it and complete when it has finished (or was stopped).
  Future<void> play();
}

// ------------------------------------------------------------------ Kokoro (sherpa_onnx)

const kokoroRepo = 'csukuangfj/kokoro-multi-lang-v1_0';
const kokoroApproxMb = 380;
const kokoroSid = {'dog': 18, 'cat': 3}; // am_puck (Spike), af_heart (Spicy): the owner's picks

/// The repo commit the voice pack is pinned to: the listing, sizes and hashes
/// never change under a download (a moving `main` could swap a file mid-way).
const kokoroRevision = 'f7b96bb6bef5c5da4d3aa4f4e0498fbbf62dc78b';

/// The 355 espeak-ng-data files as ONE download (sherpa-onnx's release of the
/// same data, 7.3 MB). Fetched one by one they are 355 requests, and Hugging
/// Face answered HTTP 429 (too many requests) on the S23 (log 30 Sep 08:31).
/// Checked 30 Sep: 353 of the 355 files are byte-identical to the pinned
/// Hugging Face ones; cmn_dict and ru_dict differ (the Kokoro repo's are newer)
/// and are fetched on their own, because every unpacked file is still checked
/// against its Hugging Face hash. If GitHub ever changes this file, its SHA-256
/// no longer matches and the pack quietly falls back to file-by-file.
const espeakArchive = BundleArchive(
  id: 'espeak',
  url: 'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/espeak-ng-data.tar.bz2',
  size: 7252012,
  sha256: '4135ccf82e1f40613491c0874d4945ae9e9c7840933d8e25a6f9e003d9ebf533',
  prefix: 'espeak-ng-data/',
);

class KokoroPack {
  KokoroPack(this.dir);
  final Directory dir;
  bool get installed => Bundle.isCompleteDir(dir);

  /// Where the file list is kept once fetched (beside the pack, so a resume
  /// after a restart needs no new listing).
  File get _listCache => File('${dir.parent.path}/${dir.uri.pathSegments.where((s) => s.isNotEmpty).last}.files.json');

  /// The files to fetch: model, voices, tokens, the US lexicon and
  /// espeak-ng-data, each once (the old two listings overlapped: every
  /// espeak file was fetched twice into the same .part file).
  static List<BundleFile> pickFiles(List<Map<String, dynamic>> tree) {
    const want = {'model.onnx', 'voices.bin', 'tokens.txt', 'lexicon-us-en.txt', 'LICENSE'};
    final byPath = <String, BundleFile>{};
    for (final e in tree) {
      if (e['type'] != 'file') continue;
      final p = e['path'] as String;
      if (want.contains(p) || p.startsWith('espeak-ng-data/')) {
        byPath[p] = BundleFile.fromHfTree(kokoroRepo, e, revision: kokoroRevision);
      }
    }
    if (!byPath.containsKey('model.onnx')) throw const HttpException('model.onnx not listed');
    return byPath.values.toList();
  }

  /// The pack as a download bundle; lists the files on Hugging Face the first time.
  Future<Bundle> bundle({http.Client? client, bool listIfMissing = true}) async {
    List<Map<String, dynamic>>? tree;
    try {
      if (await _listCache.exists()) {
        tree = (jsonDecode(await _listCache.readAsString()) as List<dynamic>).cast<Map<String, dynamic>>();
      }
    } catch (_) {
      tree = null;
    }
    if (tree == null) {
      if (!listIfMissing) throw const HttpException('no file list yet');
      tree = await hfTree(kokoroRepo, kokoroRevision, client: client);
      final files = pickFiles(tree); // validates before caching
      await _listCache.parent.create(recursive: true);
      await _listCache.writeAsString(jsonEncode([
        for (final e in tree)
          if (files.any((f) => f.path == e['path'])) e,
      ]));
    }
    return Bundle(
      id: 'spike_voice',
      root: dir.parent,
      folder: dir.uri.pathSegments.where((s) => s.isNotEmpty).last,
      files: pickFiles(tree),
      title: 'Spike\'s voice',
      archives: const [espeakArchive],
    );
  }

  Future<void> delete() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  }
}

/// The Kokoro engine lives in its own isolate: synthesis is a blocking native
/// call that would otherwise freeze the UI.
class KokoroVoice implements SpikeVoice {
  KokoroVoice(this.pack, this._player);
  final KokoroPack pack;
  final AudioPlayer _player;
  SendPort? _send;
  Isolate? _iso;
  final _replies = <int, Completer<(Float32List, int)>>{};
  int _next = 0;
  ReceivePort? _rx;

  @override
  String get name => 'Kokoro';

  Future<void> _start() async {
    if (_send != null) return;
    final rx = _rx = ReceivePort();
    final ready = Completer<SendPort>();
    rx.listen((msg) {
      if (msg is SendPort) {
        ready.complete(msg);
      } else if (msg is List && msg.length == 3) {
        final c = _replies.remove(msg[0] as int);
        final data = msg[1];
        if (data is TransferableTypedData) {
          c?.complete((data.materialize().asFloat32List(), msg[2] as int));
        } else {
          c?.completeError(StateError('kokoro: ${msg[1]}'));
        }
      }
    });
    _iso = await Isolate.spawn(_kokoroMain, [rx.sendPort, pack.dir.path]);
    _send = await ready.future.timeout(const Duration(seconds: 60));
  }

  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    await _start();
    final id = _next++;
    final c = _replies[id] = Completer<(Float32List, int)>();
    _send!.send([id, text, kokoroSid[mode] ?? 18, soft ? 0.92 : 1.0]);
    final (raw, rate) = await c.future.timeout(const Duration(seconds: 25));
    final samples = levelMatch(raw, rate); // to the laptop voice's -21 dBFS (level_match.dart)
    final wav = await _writeWav(samples, rate);
    return _KokoroSpeech(_player, wav, SpokenClip(durationMs: samples.length * 1000 ~/ rate, mouth: mouthEnvelope(samples, rate)));
  }

  static Future<File> _writeWav(Float32List samples, int rate) async {
    final f = File('${Directory.systemTemp.path}/spike_say_${DateTime.now().microsecondsSinceEpoch}.wav');
    await f.writeAsBytes(wavBytes(samples, rate), flush: true);
    return f;
  }

  @override
  Future<void> stop() => _player.stop();

  void dispose() {
    _iso?.kill(priority: Isolate.immediate);
    _rx?.close();
    _send = null;
  }
}

class _KokoroSpeech implements PreparedSpeech {
  _KokoroSpeech(this._player, this._file, this.clip);
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

void _kokoroMain(List<dynamic> args) {
  final reply = args[0] as SendPort;
  final dir = args[1] as String;
  final rx = ReceivePort();
  sherpa.OfflineTts? tts;
  reply.send(rx.sendPort);
  rx.listen((msg) {
    final m = msg as List;
    final id = m[0] as int;
    try {
      if (tts == null) {
        sherpa.initBindings();
        tts = sherpa.OfflineTts(sherpa.OfflineTtsConfig(
          model: sherpa.OfflineTtsModelConfig(
            kokoro: sherpa.OfflineTtsKokoroModelConfig(
              model: '$dir/model.onnx',
              voices: '$dir/voices.bin',
              tokens: '$dir/tokens.txt',
              dataDir: '$dir/espeak-ng-data',
              lexicon: '$dir/lexicon-us-en.txt',
              lang: 'en-us',
            ),
            numThreads: 2,
            debug: false,
          ),
          maxNumSenetences: 1,
        ));
      }
      final audio = tts!.generate(text: m[1] as String, sid: m[2] as int, speed: (m[3] as num).toDouble());
      reply.send([id, TransferableTypedData.fromList([audio.samples]), audio.sampleRate]);
    } catch (e) {
      reply.send([id, e.toString(), 0]);
    }
  });
}

/// 16-bit mono WAV.
Uint8List wavBytes(Float32List samples, int rate) {
  final n = samples.length;
  final b = ByteData(44 + n * 2);
  void s(int o, String t) {
    for (var i = 0; i < 4; i++) {
      b.setUint8(o + i, t.codeUnitAt(i));
    }
  }

  s(0, 'RIFF');
  b.setUint32(4, 36 + n * 2, Endian.little);
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
  b.setUint32(40, n * 2, Endian.little);
  for (var i = 0; i < n; i++) {
    b.setInt16(44 + i * 2, (samples[i].clamp(-1.0, 1.0) * 32767).round(), Endian.little);
  }
  return b.buffer.asUint8List();
}

/// Mouth-open envelope 0..100 at 50 Hz from the audio's loudness (PROTOCOL.md 5.4 `mouth`).
List<int> mouthEnvelope(Float32List samples, int rate, {int hz = 50}) {
  final win = max(1, rate ~/ hz);
  final rms = <double>[];
  for (var i = 0; i < samples.length; i += win) {
    var acc = 0.0;
    final end = min(samples.length, i + win);
    for (var j = i; j < end; j++) {
      acc += samples[j] * samples[j];
    }
    rms.add(sqrt(acc / (end - i)));
  }
  final peak = rms.fold<double>(0, max);
  if (peak <= 0) return List.filled(rms.length, 0);
  return [for (final r in rms) (min(1.0, r / (peak * 0.8)) * 100).round()];
}

// ------------------------------------------------------------------ Android text-to-speech

class AndroidVoice implements SpikeVoice {
  AndroidVoice() {
    _tts.awaitSpeakCompletion(true);
  }
  final FlutterTts _tts = FlutterTts();

  @override
  String get name => 'Android voice';

  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    await _tts.setVolume(androidTtsVolume); // no PCM to level-match: full media volume (level_match.dart)
    await _tts.setPitch(mode == 'cat' ? 1.25 : 1.1);
    await _tts.setSpeechRate(soft ? 0.45 : 0.5);
    // no audio to measure: ~ 2.6 words a second, a babble mouth on the robot
    final words = text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
    final ms = max(900, (words / 2.6 * 1000).round());
    return _AndroidSpeech(_tts, text, SpokenClip(durationMs: ms));
  }

  @override
  Future<void> stop() async {
    await _tts.stop();
  }
}

class _AndroidSpeech implements PreparedSpeech {
  _AndroidSpeech(this._tts, this._text, this.clip);
  final FlutterTts _tts;
  final String _text;
  @override
  final SpokenClip clip;
  @override
  Future<void> play() async {
    await _tts.speak(_text).timeout(Duration(milliseconds: clip.durationMs * 3 + 4000), onTimeout: () => null);
  }
}

/// Silent: the owner switched phone speech off (captions and the robot's mouth still work).
class SilentVoice implements SpikeVoice {
  @override
  String get name => 'Silent';
  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    final words = text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
    return _Silent(SpokenClip(durationMs: max(900, (words / 2.6 * 1000).round())));
  }

  @override
  Future<void> stop() async {}
}

class _Silent implements PreparedSpeech {
  _Silent(this.clip);
  @override
  final SpokenClip clip;
  @override
  Future<void> play() => Future.delayed(Duration(milliseconds: clip.durationMs));
}
