/// The voice session: tap the mic once and Spike keeps listening, on every
/// screen, until the same mic (or the pill's stop button) is tapped again
/// (owner decision 30 Sep, replacing press-and-hold).
///
///   off --tap--> starting --> listening <--> paused (Spike thinking / talking)
///                                 |   ^
///               link lost         v   | link back
///                               waiting
///   any --tap / app to background / mic refused / brain gone for good--> off
///
/// Home (laptop brain): the phone mic streams 40 ms pcm `audio` chunks (6.7),
/// each carrying `end_silence_ms` (the owner's "Wait before Spike answers"), so
/// the brain's VAD only ends a turn after that much silence. A head `touch` tap
/// re-opens the brain's listening whenever it goes idle. While the owner is quiet a silent
/// `keepalive` (protocol v1.6, 10.9) goes every 2 s to a brain that says it understands it, keeping
/// the model warm and the listening window open with no face flicker; an older brain gets nothing
/// (never a fake tap). Nothing is sent while Spike thinks or talks (the brain also mutes itself then).
/// Away (phone brain): Android's on-device recognizer, restarted seamlessly
/// and stitched into whole turns (turn_ear.dart); each turn goes to the phone
/// brain as heard speech, and the ear is closed while Spike talks.
/// No silent timeout: only the owner, the background, a refused mic, or a
/// brain lost for good (2 min of waiting, or pairing refused) stop it.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../away/voice/turn_ear.dart';
import '../core/haptics.dart';
import '../features/talk/ptt.dart';
import '../protocol/client.dart';
import '../protocol/messages.dart';
import 'hub.dart';
import 'link.dart';
import 'live_voice.dart';
import 'settings.dart';
import 'voice_out.dart';

enum VoicePhase { off, starting, listening, paused, waiting }

/// Why the session ended.
enum VoiceStop { user, background, permission, lost, unavailable }

@immutable
class VoiceState {
  const VoiceState({
    this.phase = VoicePhase.off,
    this.level = 0,
    this.caption,
    this.away = false,
    this.pausedFor,
    this.canInterrupt = false,
    this.notice,
    this.noticeSeq = 0,
  });
  final VoicePhase phase;

  /// Microphone loudness 0..1 for the waveform.
  final double level;

  /// What was just heard (shown briefly in the pill).
  final String? caption;

  /// Listening for the phone brain (Android's recognizer) rather than the laptop.
  final bool away;

  /// 'thinking' or 'speaking' while paused.
  final String? pausedFor;
  final bool canInterrupt;

  /// A message for the owner (why it stopped); [noticeSeq] changes with each one.
  final String? notice;
  final int noticeSeq;

  bool get on => phase != VoicePhase.off;
  bool get spikeTalking => phase == VoicePhase.paused && pausedFor == 'speaking';

  VoiceState copyWith({
    VoicePhase? phase,
    double? level,
    String? caption,
    bool clearCaption = false,
    bool? away,
    String? pausedFor,
    bool clearPausedFor = false,
    bool? canInterrupt,
  }) =>
      VoiceState(
        phase: phase ?? this.phase,
        level: level ?? this.level,
        caption: clearCaption ? null : (caption ?? this.caption),
        away: away ?? this.away,
        pausedFor: clearPausedFor ? null : (pausedFor ?? this.pausedFor),
        canInterrupt: canInterrupt ?? this.canInterrupt,
        notice: notice,
        noticeSeq: noticeSeq,
      );
}

/// What the session needs from whichever brain is live (the hub; a fake in tests).
abstract class VoiceLink {
  bool get away;
  bool get canInterrupt;
  bool sendAudio(AudioMsg m);

  /// Home: a head tap, the protocol's "listen now" (and "hush" while he talks).
  bool listenNow();

  /// Home: the silent keep-warm message (protocol v1.6, 10.9). False (and nothing is sent) when the
  /// brain is older, away, or not connected: never a fake head tap instead.
  bool keepAlive();

  /// Away: a whole spoken turn for the phone brain.
  void heard(String text);

  /// Home: a whole spoken turn, heard by the PHONE's recognizer, sent to the laptop brain as
  /// text (owner decision 30 Sep: the laptop's CPU Whisper misheard him). False if not sent.
  bool sendText(String text);

  /// Away: the face shows (or stops showing) that he is listening.
  void awayListening(bool on);

  /// Barge-in: stop Spike talking so the owner can speak.
  Future<void> interrupt();

  /// Words the brain heard (home: after its speech-to-text).
  Stream<String> get heardWords;
}

/// The silent keep-alive (protocol v1.6, 10.9) only goes to a laptop brain that says it understands it;
/// an older one would answer `unknown_type`, and a head tap instead would flicker the robot's face.
bool keepAliveSupported({required bool away, required bool legacy, required BrainHello? hello}) =>
    !away && !legacy && hello?.keepalive == true;

class HubVoiceLink implements VoiceLink {
  HubVoiceLink(this.hub);
  final SpikeHub hub;
  @override
  bool get away => hub.away;
  @override
  bool get canInterrupt => away ? hub.phone != null : !hub.legacyBrain;
  @override
  bool sendAudio(AudioMsg m) => hub.send(m);
  @override
  bool listenNow() => hub.send(const TouchMsg(zone: 'head', gesture: 'tap'));
  @override
  bool keepAlive() {
    if (!keepAliveSupported(away: hub.away, legacy: hub.legacyBrain, hello: hub.current.hello)) return false;
    return hub.send(const KeepaliveMsg());
  }

  @override
  void heard(String text) => hub.phone?.startTurn(text, 'phone_mic');
  @override
  bool sendText(String text) => hub.send(TextMsg(text: text));
  @override
  void awayListening(bool on) {
    final p = hub.phone;
    if (p == null || !hub.away) return;
    if (on && p.listeningState == 'idle') p.setListening('listening');
    if (!on && p.listeningState == 'listening') p.setListening('idle');
  }

  @override
  Future<void> interrupt() async {
    if (away) {
      await hub.phone?.hush();
    } else {
      listenNow(); // brain.py on_touch: a tap while he talks = "hush, listen"
    }
  }

  @override
  Stream<String> get heardWords =>
      hub.messages.where((m) => m is HeardMsg && !m.mine && m.via != 'typed').map((m) => (m as HeardMsg).text);
}

final micStreamProvider = Provider<MicStream>((ref) => RecordMic());
final turnEarProvider = Provider<TurnEar>((ref) => AndroidTurnEar());
final voiceLinkProvider = Provider<VoiceLink>((ref) => HubVoiceLink(ref.read(brainClientProvider)));

class VoiceController extends Notifier<VoiceState> {
  static const chunkBytes = RecordMic.rate * 2 * 40 ~/ 1000; // 40 ms
  /// Waiting for a lost brain this long = gone for good: the mic goes off.
  static Duration lostAfter = const Duration(minutes: 2);
  static const _rearmDelay = Duration(milliseconds: 350);
  static const _replyStartsWithin = Duration(seconds: 6);

  final _chunker = PcmChunker(chunkBytes);
  StreamSubscription<Uint8List>? _pcm;
  StreamSubscription<String>? _heardSub;
  AppLifecycleListener? _life;
  int _seq = 0;
  int _gen = 0; // bumps on every engage / disengage: stale loops and callbacks stop
  String? _engine; // 'homeEar' (phone recognizer -> text) | 'home' (mic stream, fallback) | 'away'
  bool _streamFallback = false; // the phone recognizer was unavailable this session: stream the mic

  /// Home: hear him with the phone's recognizer and send text (default). False = stream the mic to
  /// the laptop's Whisper as before v1.7 (tests of that path; it is also the automatic fallback).
  static bool phoneEarAtHome = true;

  /// Desktop: the built-in brain hears the computer's own microphone itself (its wake words too), so a
  /// session only keeps the brain's listening window open (head tap + silent keep-alive); no audio is
  /// streamed from the app. Set in main() on Windows (DESIGN.md "Desktop").
  static bool brainOwnMic = false;
  static Duration keepAliveEvery = const Duration(seconds: 2); // under the brain's 5 s listening window
  Timer? _rearm, _captionTimer, _lostTimer, _replyGuard, _keepAlive;
  Completer<void>? _idle;
  bool _awaitingReply = false, _sawBusy = false;
  String _words = ''; // away: heard in the current turn, not yet sent

  VoiceLink get _link => ref.read(voiceLinkProvider);
  LinkStatus get _status => ref.read(linkStatusProvider).value ?? const LinkStatus();
  // v1.5: while the laptop's voice plays through THIS phone, that counts as Spike talking too (voice_out.dart)
  String get _brainListening => ref.read(spikeSpeakingProvider) ? 'speaking' : ref.read(spikeStateProvider).listening;
  bool get _busy => const {'thinking', 'speaking'}.contains(_brainListening);
  int get _waitMs => (ref.read(settingsProvider).voiceWaitS * 1000).round();

  @override
  VoiceState build() {
    ref.listen<AsyncValue<LinkStatus>>(linkStatusProvider, (_, next) {
      final s = next.value;
      if (s != null) _onLink(s);
    });
    ref.listen<String>(spikeStateProvider.select((s) => s.listening), (_, l) => _onBrainListening(_brainListening));
    ref.listen<bool>(spikeSpeakingProvider, (_, _) => _onBrainListening(_brainListening));
    ref.listen<bool>(spikeStateProvider.select((s) => s.alarmRinging), (_, ringing) {
      if (!ringing && _engine == 'home' && _brainListening == 'idle') _scheduleRearm();
    });
    try {
      _life = AppLifecycleListener(onStateChange: onLifecycle);
    } catch (_) {} // no Flutter binding (plain unit tests)
    ref.onDispose(() {
      _gen++;
      _life?.dispose();
      _timersOff();
      _pcm?.cancel();
      _heardSub?.cancel();
    });
    return const VoiceState();
  }

  // ---------------------------------------------------------------- the owner's taps
  Future<void> toggle() => state.on ? stop() : start();

  Future<bool> start() async {
    if (state.on) return true;
    if (!_status.isConnected) {
      Haptics.error();
      _notice("Spike isn't connected. Connect him from Home.");
      return false;
    }
    if (brainOwnMic && !ref.read(settingsProvider).desktopMic) {
      _notice('The microphone is off for Spike. Switch it on in Settings > Spike on this computer.');
      return false;
    }
    unawaited(Haptics.voiceOn());
    state = state.copyWith(phase: VoicePhase.starting, level: 0, clearCaption: true, clearPausedFor: true);
    _heardSub ??= _link.heardWords.listen(_caption);
    return _engage();
  }

  Future<void> stop([VoiceStop why = VoiceStop.user]) async {
    if (!state.on) return;
    final words = _words.trim();
    final engine = _engine;
    await _disengage(closeTurn: why == VoiceStop.user);
    _streamFallback = false; // the next session tries the phone recognizer again
    // tapping off right after speaking: what the phone heard still goes to Spike
    if (why == VoiceStop.user && words.isNotEmpty) {
      if (engine == 'away') _link.heard(words);
      if (engine == 'homeEar') _link.sendText(words);
    }
    _timersOff();
    await _heardSub?.cancel();
    _heardSub = null;
    unawaited(Haptics.voiceOff());
    state = VoiceState(noticeSeq: state.noticeSeq);
    final msg = switch (why) {
      VoiceStop.user => null,
      VoiceStop.background => 'Stopped listening: Spike only listens while the app is open',
      VoiceStop.permission => 'Allow the microphone to talk to Spike',
      VoiceStop.lost => 'Lost touch with Spike, so the mic is off',
      VoiceStop.unavailable => "The phone's speech recognition isn't working right now",
    };
    if (msg != null) _notice(msg);
  }

  /// A tap on the pill while Spike talks: stop him and listen (when the brain can).
  Future<void> interrupt() async {
    if (!state.spikeTalking || !state.canInterrupt) return;
    Haptics.confirm();
    await _link.interrupt();
  }

  /// Privacy and Android's rules: the mic is never used from the background.
  void onLifecycle(AppLifecycleState s) {
    if (state.on && (s == AppLifecycleState.paused || s == AppLifecycleState.hidden || s == AppLifecycleState.detached)) {
      unawaited(stop(VoiceStop.background));
    }
  }

  // ---------------------------------------------------------------- engines
  Future<bool> _engage() async {
    final gen = ++_gen;
    final away = _link.away;
    state = state.copyWith(away: away, canInterrupt: _link.canInterrupt);
    if (away) {
      _engine = 'away';
      _pauseOrListen();
      unawaited(_earLoop(gen));
      return true;
    }
    if (brainOwnMic) {
      // desktop: the brain listens on this computer's microphone; keep its listening window open
      _engine = 'home';
      _pauseOrListen();
      _startKeepAlive();
      if (_brainListening == 'idle') _scheduleRearm(now: true);
      return true;
    }
    if (phoneEarAtHome && !_streamFallback) {
      // home: the phone's own recognizer hears him and the laptop gets the words (the laptop's
      // Whisper stream below is only the fallback when the phone recognizer is unavailable)
      _engine = 'homeEar';
      _pauseOrListen();
      _startKeepAlive();
      unawaited(_earLoop(gen));
      return true;
    }
    final mic = ref.read(micStreamProvider);
    try {
      if (!await mic.hasPermission()) {
        if (gen == _gen) await stop(VoiceStop.permission);
        return false;
      }
      if (gen != _gen) return false;
      final stream = await mic.start();
      if (gen != _gen) {
        await mic.stop();
        return false;
      }
      _engine = 'home';
      _chunker.clear();
      _pcm = stream.listen(_onPcm, onError: (Object _) {
        if (gen == _gen) unawaited(stop(VoiceStop.unavailable));
      });
      _pauseOrListen();
      _startKeepAlive();
      if (_brainListening == 'idle') _scheduleRearm(now: true);
      return true;
    } catch (_) {
      if (gen == _gen) await stop(VoiceStop.unavailable);
      return false;
    }
  }

  void _startKeepAlive() {
    _keepAlive?.cancel();
    _keepAlive = Timer.periodic(keepAliveEvery, (_) {
      if ((_engine == 'home' || _engine == 'homeEar') && state.phase == VoicePhase.listening) _link.keepAlive();
    });
  }

  Future<void> _disengage({bool closeTurn = false}) async {
    _gen++;
    _rearm?.cancel();
    _keepAlive?.cancel();
    _replyGuard?.cancel();
    _awaitingReply = false;
    _words = '';
    _resolveIdle();
    final e = _engine;
    _engine = null;
    if (e == 'home' && brainOwnMic) {
      // nothing was streamed: the brain's own microphone simply stops being kept open
    } else if (e == 'home') {
      await _pcm?.cancel();
      _pcm = null;
      await ref.read(micStreamProvider).stop();
      if (_status.isConnected && !_link.away) {
        // no end_silence_ms: the brain's own end of speech again; and when the owner
        // tapped off, a moment of silence so a sentence in progress is answered now
        for (var i = 0; i < (closeTurn ? 15 : 1); i++) {
          _send(Uint8List(chunkBytes), wait: false);
        }
      }
    } else if (e == 'away') {
      await ref.read(liveVoiceProvider.notifier).stop(); // Gemini Live, if it was the ear (live_voice.dart)
      await ref.read(turnEarProvider).cancel();
      _link.awayListening(false);
    } else if (e == 'homeEar') {
      await ref.read(turnEarProvider).cancel();
    }
  }

  void _pauseOrListen() {
    if (_busy || _awaitingReply) {
      state = state.copyWith(phase: VoicePhase.paused, pausedFor: _busy ? _brainListening : 'thinking', level: 0);
    } else {
      state = state.copyWith(phase: VoicePhase.listening, clearPausedFor: true);
    }
  }

  // ---- home: the phone mic streamed to the laptop brain
  void _onPcm(Uint8List data) {
    if (_engine != 'home') return;
    final chunks = _chunker.add(data);
    if (state.phase != VoicePhase.listening) return; // don't hear himself: nothing is sent while Spike thinks or talks
    state = state.copyWith(level: pcmLevel(data));
    for (final c in chunks) {
      _send(c);
    }
  }

  void _send(Uint8List pcm, {bool wait = true}) {
    _seq = (_seq + 1) & 0x7FFFFFFF;
    _link.sendAudio(AudioMsg(data: base64Encode(pcm), rate: RecordMic.rate, seq: _seq, endSilenceMs: wait ? _waitMs : null));
  }

  /// The brain went idle: open its listening again (a head tap), unless an alarm rings.
  void _scheduleRearm({bool now = false}) {
    _rearm?.cancel();
    _rearm = Timer(now ? Duration.zero : _rearmDelay, () {
      if (_engine != 'home' || state.phase != VoicePhase.listening) return;
      final sp = ref.read(spikeStateProvider);
      if (sp.listening != 'idle' || sp.alarmRinging) return;
      _link.listenNow();
    });
  }

  // ---- away: Android's recognizer, one whole turn at a time
  Future<void> _earLoop(int gen) async {
    // Gemini Live first when it may be used (owner decision 30 Sep, live_voice.dart): it hears,
    // answers and watches safety itself. Any end but the owner's own stop -> the recognizer below.
    final live = ref.read(liveVoiceProvider.notifier);
    final home = _engine == 'homeEar';
    if (!home && live.liveAvailable) {
      state = state.copyWith(phase: VoicePhase.listening, clearPausedFor: true);
      final end = await live.startConversation();
      if (gen != _gen || end == null) return;
    }
    final ear = ref.read(turnEarProvider);
    while (gen == _gen && (_engine == 'away' || _engine == 'homeEar')) {
      if (_busy || _awaitingReply) {
        await (_idle ??= Completer<void>()).future;
        continue;
      }
      state = state.copyWith(phase: VoicePhase.listening, clearPausedFor: true);
      if (!home) _link.awayListening(true);
      _words = '';
      final r = await ear.listenTurn(
        wait: Duration(milliseconds: _waitMs),
        onWords: (w) {
          if (gen != _gen) return;
          _words = w;
          _caption(w);
        },
        onLevel: (v) {
          if (gen == _gen && state.phase == VoicePhase.listening) state = state.copyWith(level: v);
        },
      );
      if (gen != _gen) return;
      switch (r.end) {
        case EarEnd.denied:
          unawaited(stop(VoiceStop.permission));
          return;
        case EarEnd.unavailable:
          if (home) {
            // no phone recognizer: the laptop's own speech-to-text hears the mic stream instead
            _streamFallback = true;
            unawaited(() async {
              await _disengage();
              if (!state.on) return;
              state = state.copyWith(phase: VoicePhase.starting);
              await _engage();
            }());
            return;
          }
          unawaited(stop(VoiceStop.unavailable));
          return;
        case EarEnd.cancelled:
          continue; // Spike began talking: wait for him, then listen again
        case EarEnd.words:
          _words = '';
          _awaitReply();
          if (home) {
            _link.sendText(r.text);
          } else {
            _link.heard(r.text);
          }
      }
    }
  }

  void _awaitReply() {
    _awaitingReply = true;
    _sawBusy = false;
    state = state.copyWith(phase: VoicePhase.paused, pausedFor: 'thinking', level: 0);
    _replyGuard?.cancel();
    _replyGuard = Timer(_replyStartsWithin, () {
      if (_awaitingReply && !_sawBusy) _replyDone(); // nothing to say: listen again
    });
  }

  void _replyDone() {
    _awaitingReply = false;
    _replyGuard?.cancel();
    if (_engine != null) state = state.copyWith(phase: VoicePhase.listening, clearPausedFor: true);
    _resolveIdle();
  }

  void _resolveIdle() {
    final c = _idle;
    _idle = null;
    if (c != null && !c.isCompleted) c.complete();
  }

  // ---------------------------------------------------------------- what the brain does
  void _onBrainListening(String l) {
    final busy = l == 'thinking' || l == 'speaking';
    if (busy && _awaitingReply) _sawBusy = true;
    if (_engine == null) return; // off, starting, or waiting for the link
    if (busy) {
      _rearm?.cancel();
      final talkingOnHisOwn = (_engine == 'away' || _engine == 'homeEar') && !_awaitingReply && state.phase == VoicePhase.listening;
      state = state.copyWith(phase: VoicePhase.paused, pausedFor: l, level: 0);
      if (talkingOnHisOwn) unawaited(ref.read(turnEarProvider).cancel()); // his voice must not be transcribed
      return;
    }
    if (_engine == 'away' || _engine == 'homeEar') {
      if (l != 'idle') return;
      if (_awaitingReply && !_sawBusy) return; // his reply has not started yet
      _replyDone();
      return;
    }
    state = state.copyWith(phase: VoicePhase.listening, clearPausedFor: true);
    if (l == 'idle') _scheduleRearm();
  }

  void _onLink(LinkStatus s) {
    if (!state.on) return;
    if (s.isConnected) {
      _lostTimer?.cancel();
      _lostTimer = null;
      final away = _link.away;
      final mismatch = _engine != null && (_engine == 'away') != away; // home <-> away switched under us
      if (state.phase == VoicePhase.waiting || mismatch) {
        unawaited(() async {
          await _disengage();
          if (!state.on) return;
          state = state.copyWith(phase: VoicePhase.starting);
          await _engage();
        }());
      }
      return;
    }
    if (s.phase == LinkPhase.authFailed || s.phase == LinkPhase.versionMismatch) {
      unawaited(stop(VoiceStop.lost));
      return;
    }
    if (state.phase != VoicePhase.waiting) {
      unawaited(_disengage());
      state = state.copyWith(phase: VoicePhase.waiting, level: 0, clearPausedFor: true);
      _lostTimer ??= Timer(lostAfter, () {
        if (state.phase == VoicePhase.waiting) unawaited(stop(VoiceStop.lost));
      });
    }
  }

  // ---------------------------------------------------------------- bits
  void _caption(String words) {
    final w = words.trim();
    if (w.isEmpty || !state.on) return;
    state = state.copyWith(caption: w.length > 80 ? '…${w.substring(w.length - 79)}' : w);
    _captionTimer?.cancel();
    _captionTimer = Timer(const Duration(seconds: 3), () {
      if (state.caption != null) state = state.copyWith(clearCaption: true);
    });
  }

  void _notice(String text) => state = VoiceState(
        phase: state.phase,
        level: state.level,
        caption: state.caption,
        away: state.away,
        pausedFor: state.pausedFor,
        canInterrupt: state.canInterrupt,
        notice: text,
        noticeSeq: state.noticeSeq + 1,
      );

  void _timersOff() {
    _rearm?.cancel();
    _keepAlive?.cancel();
    _captionTimer?.cancel();
    _lostTimer?.cancel();
    _replyGuard?.cancel();
    _lostTimer = null;
  }
}

final voiceProvider = NotifierProvider<VoiceController, VoiceState>(VoiceController.new);
