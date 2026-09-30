/// Continuous listening away from home (the app's tap-to-talk voice session).
///
/// Android's SpeechRecognizer ends a session on its own after a short pause
/// (Samsung and Google recognizers often ignore the silence-length extras),
/// so one spoken turn can span several recognizer sessions. [TurnStitcher]
/// joins them and only calls the turn finished after the owner's full wait
/// ("Wait before Spike answers", 3 s by default) with no new words.
///
/// The recognizer is Android's on-device one (`onDevice: true`, API 31+
/// `createOnDeviceSpeechRecognizer` inside speech_to_text 7.5). The plugin has
/// no way to switch off the start/stop chime; the on-device recognizer does not
/// play the Google app's chime, which is why it is used. Muting the phone's
/// sound streams around each restart was rejected: it changes system volume
/// and would swallow Spike's own voice and notifications (DESIGN.md).
library;

import 'dart:async';
import 'dart:math';

import 'package:speech_to_text/speech_recognition_error.dart';
import 'package:speech_to_text/speech_to_text.dart';

/// How a turn ended.
enum EarEnd { words, cancelled, denied, unavailable }

class EarTurn {
  const EarTurn(this.end, [this.text = '']);
  final EarEnd end;
  final String text;
}

/// Listens for one whole spoken turn (the owner talks, then is quiet for [wait]).
abstract class TurnEar {
  Future<EarTurn> listenTurn({
    required Duration wait,
    void Function(String words)? onWords,
    void Function(double level)? onLevel,
  });

  /// Stop listening now and drop what was heard (Spike started talking, or the owner stopped).
  Future<void> cancel();
}

/// Joins recognizer sessions into one turn. Pure, so it is unit tested.
class TurnStitcher {
  TurnStitcher({required this.wait, DateTime Function()? clock}) : _clock = clock ?? DateTime.now;
  final Duration wait;
  final DateTime Function() _clock;
  String _done = '';
  String _live = '';
  DateTime? _lastWords;

  /// The running session's words so far (each session starts from empty).
  void partial(String words) {
    final w = words.trim();
    if (w == _live) return;
    _live = w;
    if (w.isNotEmpty) _lastWords = _clock();
  }

  /// The recognizer ended a session (a pause, its own time limit, no match).
  void sessionEnded() {
    if (_live.isEmpty) return;
    _done = _join(_done, _live);
    _live = '';
  }

  String get text => _join(_done, _live);
  bool get heardAnything => text.isNotEmpty;

  /// The owner said something and has now been quiet for the whole wait.
  bool complete([DateTime? now]) =>
      heardAnything && _lastWords != null && (now ?? _clock()).difference(_lastWords!) >= wait;

  static String _join(String a, String b) => a.isEmpty ? b : (b.isEmpty ? a : '$a $b');
}

/// speech_to_text rms dB (about -2 quiet .. 10 loud) as 0..1 for the pill's waveform.
double levelFromDb(double db) => ((db + 2) / 12).clamp(0.0, 1.0).toDouble();

class AndroidTurnEar implements TurnEar {
  final SpeechToText _stt = SpeechToText(); // a singleton inside the plugin (shared with AndroidEar)
  bool _ready = false;
  Completer<void>? _session;
  Completer<EarTurn>? _turn;
  String? _error;

  static const _deniedErrors = {'error_permission', 'error_insufficient_permissions'};
  static const _busyErrors = {'error_busy', 'error_recognizer_busy', 'error_client', 'error_server_disconnected'};

  void _onStatus(String s) {
    if (s == SpeechToText.doneStatus || s == SpeechToText.notListeningStatus) _endSession();
  }

  void _onError(SpeechRecognitionError e) {
    _error = e.errorMsg;
    _endSession();
  }

  void _endSession() {
    final s = _session;
    if (s != null && !s.isCompleted) s.complete();
  }

  Future<bool> _init() async {
    if (!_ready) _ready = await _stt.initialize(onError: _onError, onStatus: _onStatus);
    // the plugin keeps one set of listeners: take them back from AndroidEar every turn
    _stt.errorListener = _onError;
    _stt.statusListener = _onStatus;
    return _ready;
  }

  @override
  Future<EarTurn> listenTurn({required Duration wait, void Function(String)? onWords, void Function(double)? onLevel}) async {
    try {
      if (!await _init()) return const EarTurn(EarEnd.denied); // no recognizer, or the permission was refused
    } catch (_) {
      return const EarTurn(EarEnd.unavailable);
    }
    final turn = _turn = Completer<EarTurn>();
    final st = TurnStitcher(wait: wait);
    final tick = Timer.periodic(const Duration(milliseconds: 150), (_) {
      if (st.complete() && !turn.isCompleted) turn.complete(EarTurn(EarEnd.words, st.text));
    });
    var quickFails = 0;
    try {
      while (!turn.isCompleted) {
        final session = _session = Completer<void>();
        _error = null;
        final started = DateTime.now();
        try {
          await _stt.listen(
            onResult: (r) {
              st.partial(r.recognizedWords);
              onWords?.call(st.text);
              if (r.finalResult) _endSession();
            },
            onSoundLevelChange: onLevel == null ? null : (db) => onLevel(levelFromDb(db)),
            listenOptions: SpeechListenOptions(
              onDevice: true,
              partialResults: true,
              cancelOnError: false,
              listenMode: ListenMode.dictation,
              pauseFor: wait,
              listenFor: const Duration(seconds: 60),
            ),
          );
        } catch (_) {
          _error = 'error_client';
          _endSession();
        }
        await Future.any([session.future, turn.future]);
        st.sessionEnded();
        if (turn.isCompleted) break;
        final err = _error;
        if (err != null && _deniedErrors.contains(err)) {
          turn.complete(const EarTurn(EarEnd.denied));
          break;
        }
        if (st.complete()) {
          turn.complete(EarTurn(EarEnd.words, st.text));
          break;
        }
        // restart at once; back off only when the recognizer keeps failing straight away
        final quick = DateTime.now().difference(started) < const Duration(milliseconds: 400);
        quickFails = quick ? quickFails + 1 : 0;
        if (quickFails >= 8) {
          turn.complete(const EarTurn(EarEnd.unavailable));
          break;
        }
        final busy = err != null && _busyErrors.contains(err);
        if (busy || quick) await Future<void>.delayed(Duration(milliseconds: min(2000, 150 * (1 << min(quickFails, 4)))));
      }
    } finally {
      tick.cancel();
      if (_stt.isListening) {
        try {
          await _stt.cancel();
        } catch (_) {}
      }
    }
    return turn.future;
  }

  @override
  Future<void> cancel() async {
    final t = _turn;
    if (t != null && !t.isCompleted) t.complete(const EarTurn(EarEnd.cancelled));
    _endSession();
    try {
      await _stt.cancel();
    } catch (_) {}
  }
}
