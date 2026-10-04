/// Kokoro-82M on the phone, through the OPTIONAL add-on the owner installs himself
/// (kokoro_addon.dart): the sherpa-onnx native libraries are NOT in the APK; they are opened by
/// absolute path from the app's files folder with the vendored Apache-2.0 Dart bindings
/// (third_party/sherpa_onnx_ffi). The engine is the one from the 1.0.1 development builds
/// (optional/kokoro_sherpa/kokoro_voice_sherpa.dart), with only the library loading changed.
library;

import 'dart:async';
import 'dart:io';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:audioplayers/audioplayers.dart';
import 'package:sherpa_onnx_ffi/sherpa_onnx_ffi.dart' as sherpa;

import 'level_match.dart';
import 'speaker.dart';

/// The Kokoro engine lives in its own isolate: synthesis is a blocking native
/// call that would otherwise freeze the UI.
class AddonKokoroVoice implements KokoroVoice {
  AddonKokoroVoice(this.pack, this._player);
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
    _iso = await Isolate.spawn(_kokoroMain, [rx.sendPort, pack.dir.path, pack.engine.dir.path]);
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

  @override
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
  final engineDir = args[2] as String;
  final rx = ReceivePort();
  sherpa.OfflineTts? tts;
  reply.send(rx.sendPort);
  rx.listen((msg) {
    final m = msg as List;
    final id = m[0] as int;
    try {
      if (tts == null) {
        sherpa.loadSherpaOnnx(engineDir); // by absolute path: nothing of sherpa-onnx is in the APK
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
