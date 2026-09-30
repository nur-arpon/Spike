/// DEBUG builds only: a Gemini Live / TTS check that a developer can start on
/// a real phone without touching it, by creating an empty file named
/// `selftest.live` in the app's own files folder
/// (`adb shell run-as com.spikebuddy.spike_app touch files/selftest.live`).
/// It runs the app's own Live and TTS code with the owner's saved key and
/// writes what Google answered to the log (`gemini selftest: ...`). The key is
/// never logged (only [cleanReason] text). Nothing is played out loud: the
/// sink check feeds silence.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../voice/gemini_tts.dart';
import '../voice/pcm_stream.dart';
import 'gemini_live.dart';

void _log(String m) => debugPrint('gemini selftest: $m');

/// Starts watching for the trigger file (debug builds only).
void watchLiveSelfTest(Future<String?> Function() readKey, {Future<String> Function(PcmSink sink)? preview}) {
  if (!kDebugMode || Platform.environment.containsKey('FLUTTER_TEST')) return;
  var running = false;
  Timer.periodic(const Duration(seconds: 3), (_) async {
    if (running) return;
    try {
      final f = File('${(await getApplicationSupportDirectory()).path}/selftest.live');
      if (!await f.exists()) return;
      await f.delete();
      running = true;
      await runLiveSelfTest(await readKey());
      if (preview != null) {
        final sink = CountingSink();
        final how = await preview(sink).timeout(const Duration(seconds: 90), onTimeout: () => 'timed out');
        _log('preview path: $how; heard ${sink.bytes} bytes in ${sink.pieces} pieces, ${sink.begins} utterances');
      }
    } catch (e) {
      _log('failed: ${cleanReason(e)}');
    } finally {
      running = false;
    }
  });
}

Future<void> runLiveSelfTest(String? key) async {
  if (key == null || key.trim().isEmpty) {
    _log('no key saved');
    return;
  }
  _log('start (key length ${key.trim().length})');
  // 1. TTS, each model
  for (final m in ttsModels) {
    final t = GeminiTtsVoice(apiKey: key, voiceFor: (_) => 'Fenrir', models: [m]);
    try {
      final wav = await t.synth('Hi, it is me, Spike!', mode: 'dog');
      _log('tts $m: ok, ${wav.length} bytes');
    } on TtsError catch (e) {
      _log('tts $m: ${e.kind} ${cleanReason(e.message)}');
    } catch (e) {
      _log('tts $m: ${cleanReason(e)}');
    } finally {
      t.close();
    }
  }
  // 2. Live, each model: connect, one text turn, count what comes back
  for (final m in liveModels) {
    final GeminiLiveSession s;
    try {
      s = await GeminiLiveSession.connect(
          apiKey: key,
          config: const LiveConfig(voice: 'Fenrir', systemInstruction: 'You are Spike, a cheerful robot puppy. Answer in one short sentence.'),
          models: [m]);
    } on LiveError catch (e) {
      _log('live $m: ${e.kind.name} ${e.message}');
      continue;
    } catch (e) {
      _log('live $m: ${cleanReason(e)}');
      continue;
    }
    var audio = 0, frames = 0;
    final said = StringBuffer();
    final done = Completer<String>();
    final sub = s.events.listen((e) {
      switch (e) {
        case LiveAudio():
          audio += e.pcm.length;
          frames++;
        case LiveOutputText():
          said.write(e.text);
        case LiveTurnComplete():
          if (!done.isCompleted) done.complete('turn complete');
        case LiveClosed():
          if (!done.isCompleted) done.complete('closed ${e.error ?? ''}');
        default:
          break;
      }
    });
    s.sendText('Say hello to me in five words.');
    final how = await done.future.timeout(const Duration(seconds: 20), onTimeout: () => 'no answer in 20 s');
    await sub.cancel();
    await s.close();
    _log('live $m: ready; $how; audio $audio bytes in $frames pieces; said "${cleanReason(said)}"');
  }
  // 3. the player the preview uses (silence only: nothing audible)
  final sink = SoloudPcmSink();
  try {
    await sink.begin(liveOutRate);
    sink.feed(Uint8List(liveOutRate)); // 0.5 s of silence
    await sink.end().timeout(const Duration(seconds: 5));
    _log('pcm sink: ok');
  } catch (e) {
    _log('pcm sink: ${cleanReason(e)}');
  }
  _log('done');
}

/// A sink that only counts (the preview path, silently).
class CountingSink implements PcmSink {
  int bytes = 0, pieces = 0, begins = 0;
  bool _playing = false;
  @override
  Future<void> begin(int rate) async {
    begins++;
    _playing = true;
  }

  @override
  void feed(Uint8List pcm) {
    bytes += pcm.length;
    pieces++;
  }

  @override
  Future<void> end() async => _playing = false;
  @override
  Future<void> stop() async => _playing = false;
  @override
  bool get playing => _playing;
  @override
  double get level => 0;
}
