/// The phone's ear while away: Android's speech recognizer, asked to work on
/// the device (`onDevice: true`, Android's "prefer offline"). Push-to-talk in
/// the app and a head tap on the robot both start it. The words go to the
/// phone brain only (and, like everything the owner says, to the AI provider
/// the owner chose when a reply needs the language model).
library;

import 'dart:async';

import 'package:speech_to_text/speech_to_text.dart';

abstract class SpikeEar {
  /// Listen once; [onPartial] gets the words so far. Completes with the final
  /// words, or null if nothing was understood / permission was refused.
  Future<String?> listenOnce({void Function(String)? onPartial});
  Future<void> stop();
  bool get listening;
}

class AndroidEar implements SpikeEar {
  final SpeechToText _stt = SpeechToText();
  bool _ready = false;
  Completer<String?>? _done;
  String _last = '';

  @override
  bool get listening => _stt.isListening;

  void _onStatus(String s) {
    if (s == 'done' || s == 'notListening') _finish();
  }

  Future<bool> _init() async {
    if (!_ready) _ready = await _stt.initialize(onError: (e) => _finish(), onStatus: _onStatus);
    // one plugin instance is shared with the app's voice session (turn_ear.dart): take the listeners back
    _stt.errorListener = (e) => _finish();
    _stt.statusListener = _onStatus;
    return _ready;
  }

  void _finish() {
    final d = _done;
    if (d != null && !d.isCompleted) d.complete(_last.trim().isEmpty ? null : _last.trim());
  }

  @override
  Future<String?> listenOnce({void Function(String)? onPartial}) async {
    if (!await _init()) return null; // no recognizer, or the microphone permission was refused
    _last = '';
    final done = _done = Completer<String?>();
    await _stt.listen(
      onResult: (r) {
        _last = r.recognizedWords;
        onPartial?.call(_last);
        if (r.finalResult) _finish();
      },
      listenOptions: SpeechListenOptions(
        onDevice: true,
        partialResults: true,
        cancelOnError: true,
        listenMode: ListenMode.dictation,
        listenFor: const Duration(seconds: 15),
        pauseFor: const Duration(milliseconds: 1500),
      ),
    );
    return done.future.timeout(const Duration(seconds: 20), onTimeout: () {
      _stt.stop();
      return _last.trim().isEmpty ? null : _last.trim();
    });
  }

  @override
  Future<void> stop() async {
    await _stt.stop();
    _finish();
  }
}
