/// A spoken conversation with Gemini Live (away, the default when the laptop
/// can't be reached): microphone -> Live native audio -> Spike's voice, with
/// our safety layer watching both transcripts (live_guard.dart) and able to
/// cut Gemini off and speak our own line instead. DESIGN.md "Gemini Live".
///
/// Order of events for one owner turn, and where safety sits:
///  1. mic audio streams to Live (only while Spike is not talking: half duplex,
///     so his own voice can never be taken for the owner's).
///  2. inputTranscription pieces arrive -> guard.onInput: a crisis phrase or an
///     explicit request stops the turn at once (nothing of Gemini's plays) and
///     the brain speaks the crisis / deflection line.
///  3. Gemini's first audio arrives. It is HELD (not played) until the owner's
///     words for this turn have been screened: up to [transcriptWait] for the
///     transcript to show up, and, if soft risk words were heard, until the
///     classifier has answered (up to 4 s). Then it plays.
///  4. outputTranscription pieces -> guard.onOutput on the whole reply so far:
///     a broken rule stops playback within one audio piece and the brain says
///     the replacement line. Residual risk: the output transcript can trail the
///     audio slightly, so a few words may already have played (DESIGN.md).
///  5. After a crisis, Live ends for this conversation ([LiveTalkEnd.crisis]):
///     the caller switches to the phone brain's text path, whose every sentence
///     is checked BEFORE it is spoken (Gemini text + Gemini TTS).
library;

import 'dart:async';

import 'package:flutter/foundation.dart' show debugPrint;
import 'dart:typed_data';

import '../brain/safety.dart' as safety;
import '../voice/pcm_stream.dart';
import 'gemini_live.dart';
import 'live_guard.dart';

enum LiveTalkEnd { stopped, crisis, rateLimited, badKey, unavailable, network, noMic }

/// What the conversation asks of the phone brain (captions, face, scripted lines).
class LiveTalkHooks {
  const LiveTalkHooks({
    required this.crisis,
    required this.blocked,
    required this.replace,
    this.heard,
    this.said,
    this.state,
    this.classify,
  });

  /// Speak the crisis (or emergency) line; the brain logs the moment (no words).
  final Future<void> Function(String kind) crisis;

  /// Speak the deflection line for an explicit request.
  final Future<void> Function() blocked;

  /// Speak the replacement for a reply that broke a rule ('not_honest' -> the honest robot line).
  final Future<void> Function(String rule) replace;
  final void Function(String text)? heard; // the owner's words, once per turn
  final void Function(String sentence)? said; // Spike's words, a sentence at a time (captions)
  final void Function(String state)? state; // listening | thinking | speaking | idle
  final Future<safety.SafetyLevel> Function(String text)? classify;
}

typedef LiveOpener = Future<GeminiLiveSession> Function({String? resumeHandle});

class LiveTalk {
  LiveTalk({
    required this.open,
    required this.sink,
    required this.hooks,
    this.mic,
    this.guard,
    this.transcriptWait = const Duration(milliseconds: 700),
    this.classifyTimeout = const Duration(seconds: 4),
    this.echoTail = const Duration(milliseconds: 300),
  });

  final LiveOpener open;
  final PcmSink sink;
  final MicSource? mic;
  final LiveTalkHooks hooks;
  LiveGuard? guard;
  final Duration transcriptWait;
  final Duration classifyTimeout;
  final Duration echoTail;

  GeminiLiveSession? _s;
  StreamSubscription<LiveEvent>? _sub;
  StreamSubscription<Uint8List>? _micSub;
  final _done = Completer<LiveTalkEnd>();
  bool _stopping = false;

  // per turn
  bool _suppress = false; // this Gemini turn was stopped by safety: drop the rest of it
  bool _heardSent = false;
  bool _gateOpen = false;
  bool _gating = false;
  bool _sinkBegun = false;
  final List<Uint8List> _held = [];
  Future<void>? _intervention;
  bool _micOpen = false;

  Future<LiveTalkEnd> get done => _done.future;
  bool get running => _s != null && !_done.isCompleted;
  LiveGuard get _g => guard ??= LiveGuard();

  /// Connect and start listening. Returns false (and [done] says why) when Live can't start.
  /// Why the session could not open (never contains the key), for the preview screen.
  LiveError? error;

  Future<bool> start({bool listen = true}) async {
    try {
      _s = await open();
    } on LiveError catch (e) {
      error = e;
      _finish(_endFor(e));
      return false;
    }
    _sub = _s!.events.listen(_onEvent);
    if (listen && mic != null) {
      final stream = await mic!.start();
      if (stream == null) {
        await stop(LiveTalkEnd.noMic);
        return false;
      }
      _micSub = stream.listen((pcm) {
        if (_micOpen) _s?.sendAudio(pcm);
      });
      _openMic();
    }
    return true;
  }

  /// Say something typed (the preview screen's lines and question): a turn like any other.
  void sendText(String text) {
    _newTurn();
    final a = _g.onInput(text);
    _heardSent = true;
    if (!a.ok) {
      _intervene(a);
      return;
    }
    _closeMic();
    hooks.state?.call('thinking');
    _s?.sendText(text);
  }

  Future<void> stop([LiveTalkEnd why = LiveTalkEnd.stopped]) async {
    if (_stopping) return;
    _stopping = true;
    _micOpen = false;
    await _micSub?.cancel();
    await mic?.stop();
    await sink.stop();
    await _sub?.cancel();
    await _s?.close();
    hooks.state?.call('idle');
    _finish(why);
  }

  void _finish(LiveTalkEnd why) {
    if (!_done.isCompleted) _done.complete(why);
  }

  static LiveTalkEnd _endFor(LiveError e) => switch (e.kind) {
        LiveErrorKind.rateLimited => LiveTalkEnd.rateLimited,
        LiveErrorKind.badKey => LiveTalkEnd.badKey,
        LiveErrorKind.network => LiveTalkEnd.network,
        _ => LiveTalkEnd.unavailable,
      };

  void _openMic() {
    if (_stopping) return;
    if (mic == null) {
      hooks.state?.call('idle'); // text-only (preview): ready for the next line
      return;
    }
    _micOpen = true;
    hooks.state?.call('listening');
  }

  void _closeMic() => _micOpen = false;

  void _newTurn() {
    _g.newTurn();
    _suppress = false;
    _heardSent = false;
    _gateOpen = false;
    _gating = false;
    _sinkBegun = false;
    _held.clear();
  }

  // ---------------------------------------------------------------- events
  bool _turnFresh = true;

  void _onEvent(LiveEvent e) {
    if (_stopping) return;
    if (_turnFresh && (e is LiveInputText || e is LiveAudio || e is LiveOutputText)) {
      _turnFresh = false;
      if (e is! LiveAudio || _g.input.isEmpty) {
        if (!_heardSent) _newTurnKeepText();
      }
    }
    switch (e) {
      case LiveInputText():
        if (_suppress) {
          _g.onInput(e.text);
          return;
        }
        final a = _g.onInput(e.text);
        if (!a.ok) {
          _intervene(a);
        } else if (_sinkBegun && _g.needsCheck && hooks.classify != null) {
          // words that arrived after Gemini began: check them, cutting if needed
          unawaited(_classifyThen(() {}));
        }
      case LiveAudio():
        if (_suppress) return;
        _closeMic();
        if (_gateOpen) {
          _play(e.pcm);
        } else {
          _held.add(e.pcm);
          if (!_gating) unawaited(_gate());
        }
      case LiveOutputText():
        if (_suppress) return;
        final a = _g.onOutput(e.text);
        if (!a.ok) {
          _intervene(a);
          return;
        }
        if (_gateOpen) {
          for (final s in _g.takeSentences()) {
            hooks.said?.call(s);
          }
        }
      case LiveInterrupted():
        _held.clear();
        unawaited(sink.stop());
        _sinkBegun = false;
      case LiveTurnComplete():
        unawaited(_turnEnded());
      case LiveGoAway():
        unawaited(_reconnect());
      case LiveClosed():
        if (!_reconnecting) {
          final err = e.error;
          if (err != null) {
            error = err;
            debugPrint('gemini live: closed during the session: $err');
          }
          unawaited(stop(err == null ? LiveTalkEnd.stopped : _endFor(err)));
        }
      case LiveReady():
      case LiveResumeHandle():
        break;
    }
  }

  /// First words of a new owner turn: fresh guard state (the words themselves go to the guard next).
  void _newTurnKeepText() {
    _newTurn();
    hooks.state?.call('thinking');
  }

  /// Hold Gemini's first audio until the owner's words have been screened.
  Future<void> _gate() async {
    _gating = true;
    final deadline = DateTime.now().add(transcriptWait);
    while (_g.input.isEmpty && DateTime.now().isBefore(deadline) && !_suppress && !_stopping) {
      await Future<void>.delayed(const Duration(milliseconds: 50));
    }
    if (_suppress || _stopping) return;
    if (_g.needsCheck && hooks.classify != null) {
      await _classifyThen(() {});
      if (_suppress || _stopping) return;
    }
    _sendHeard();
    _gateOpen = true;
    for (final pcm in _held) {
      _play(pcm);
    }
    _held.clear();
    for (final s in _g.takeSentences()) {
      hooks.said?.call(s);
    }
  }

  Future<void> _classifyThen(void Function() then) async {
    final text = _g.input;
    safety.SafetyLevel level;
    try {
      level = await hooks.classify!(text).timeout(classifyTimeout, onTimeout: () => safety.SafetyLevel.none);
    } catch (_) {
      level = safety.SafetyLevel.none;
    }
    final a = _g.onClassified(level);
    if (!a.ok) _intervene(a);
    then();
  }

  void _sendHeard() {
    if (_heardSent) return;
    _heardSent = true;
    final t = _g.input;
    if (t.isNotEmpty) hooks.heard?.call(t);
  }

  void _play(Uint8List pcm) {
    if (!_sinkBegun) {
      _sinkBegun = true;
      hooks.state?.call('speaking');
      _beginning = sink.begin(liveOutRate);
    }
    final b = _beginning;
    if (b == null) {
      sink.feed(pcm);
    } else {
      _pendingFeed.add(pcm);
      if (_pendingFeed.length == 1) {
        b.then((_) {
          _beginning = null;
          if (!_suppress) {
            for (final p in _pendingFeed) {
              sink.feed(p);
            }
          }
          _pendingFeed.clear();
        });
      }
    }
  }

  Future<void>? _beginning;
  final List<Uint8List> _pendingFeed = [];

  Future<void> _turnEnded() async {
    _turnFresh = true;
    if (_intervention != null) {
      await _intervention;
    } else {
      _sendHeard();
      for (final s in _g.takeSentences(all: true)) {
        hooks.said?.call(s);
      }
      // a reply held at the gate is still let out, then played to its end
      while (_gating && !_gateOpen && !_suppress && !_stopping) {
        await Future<void>.delayed(const Duration(milliseconds: 50));
      }
      if (_sinkBegun) {
        await _beginning;
        await sink.end();
      }
    }
    if (_stopping) return;
    await Future<void>.delayed(echoTail);
    _intervention = null;
    _newTurn();
    _openMic();
  }

  /// Safety stepped in: silence Gemini at once, then speak our own line.
  void _intervene(GuardAction a) {
    _suppress = true;
    _closeMic();
    _held.clear();
    _pendingFeed.clear();
    _sendHeard();
    final f = () async {
      await sink.stop();
      _sinkBegun = false;
      switch (a.kind) {
        case GuardKind.crisis:
          await hooks.crisis(a.detail);
          await stop(LiveTalkEnd.crisis); // the rest of this conversation: the checked text path
        case GuardKind.blocked:
          await hooks.blocked();
        case GuardKind.replace:
          await hooks.replace(a.detail);
        case GuardKind.cap:
        case GuardKind.ok:
          break;
      }
    }();
    _intervention = f;
    unawaited(f.whenComplete(() {
      if (_turnFresh && !_stopping) {
        // Gemini's turn already ended: listen again now
        _intervention = null;
        _newTurn();
        _openMic();
      }
    }));
  }

  // ---------------------------------------------------------------- GoAway: same conversation, new connection
  bool _reconnecting = false;

  Future<void> _reconnect() async {
    if (_reconnecting || _stopping) return;
    _reconnecting = true;
    final old = _s;
    try {
      final next = await open(resumeHandle: old?.resumeHandle);
      await _sub?.cancel();
      _s = next;
      _sub = next.events.listen(_onEvent);
      await old?.close();
    } on LiveError catch (e) {
      _reconnecting = false;
      await stop(_endFor(e));
      return;
    }
    _reconnecting = false;
  }
}
