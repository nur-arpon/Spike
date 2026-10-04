/// Spike's voice on the phone while away (the robot has no audio link over
/// Bluetooth, so the phone speaks and the robot moves its mouth to it).
///
/// 1. Kokoro-82M on the phone, ONLY once the owner installed the optional
///    add-on (kokoro_addon.dart): the APK carries no sherpa-onnx native code
///    (it links GPL-3.0 espeak-ng); the phone fetches the official libraries
///    from the sherpa-onnx release and the voice files (~380 MB) from their
///    upstream pages, only when asked. Same voices as the laptop's Kokoro:
///    Spike = am_puck, Spicy = af_heart.
/// 2. Android's own text-to-speech (flutter_tts) otherwise, or if Kokoro fails.
///
/// Numbers the voice must say a certain way are spoken as the laptop does
/// ("000" -> "triple zero", default.toml say_as); captions keep "000".
library;

import 'dart:async';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

import '../../core/platform.dart';
import 'kokoro_addon.dart';
import 'kokoro_voice_addon.dart';
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

// ------------------------------------------------------------------ Kokoro (an optional add-on the owner installs)

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

  /// The voice files are all here (the engine is separate: [engine]).
  bool get installed => Bundle.isCompleteDir(dir);

  /// The add-on's engine (sherpa-onnx libraries), beside the voice files: `<app support>/kokoro_engine`.
  KokoroEngineFiles get engine => KokoroEngineFiles(Directory('${dir.parent.path}/kokoro_engine'));

  /// Kokoro can speak: voice files AND the engine, proven to load.
  bool get ready => installed && engine.ready;

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

/// A Kokoro voice on the phone. The engine's native code (sherpa-onnx) is NOT in the app: it
/// links espeak-ng (GPL-3.0), which cannot ship under Spike's all-rights-reserved licence. The
/// owner installs it as an add-on from the upstream release (kokoro_addon.dart).
abstract class KokoroVoice implements SpikeVoice {
  void dispose();
}

typedef KokoroEngine = KokoroVoice Function(KokoroPack pack, AudioPlayer player);

/// The Kokoro engine: the add-on one (opens the owner-installed libraries by path). It is only
/// ever used once [KokoroPack.ready]. Tests swap it for a fake.
KokoroEngine? kokoroEngine = AddonKokoroVoice.new;

/// Null = the real platform; tests set true to show the add-on card on their host.
bool? debugKokoroAddonSupported;

/// The add-on exists for Android phones only (the libraries fetched are Android arm64 ones).
bool get kokoroAddonSupported =>
    debugKokoroAddonSupported ?? (AppPlatform.onDeviceAiPack && Platform.isAndroid);

/// The Settings card "Offline backup voice (Kokoro)" and the Kokoro step of the voice chain are
/// hidden, not deleted, while this is false.
bool get kokoroVoiceAvailable => kokoroAddonSupported && kokoroEngine != null;

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
