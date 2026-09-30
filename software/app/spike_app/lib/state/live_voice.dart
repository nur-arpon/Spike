/// Gemini Live for the app: the away conversation (the default voice when the
/// laptop can't be reached) and the "Hear Spike's voices" preview.
///
/// For the continuous-listening session (tap-to-toggle, lib/away/voice/
/// turn_ear.dart): when [GeminiLiveController.liveAvailable] is true, call
/// [GeminiLiveController.startConversation] instead of listening with the
/// recognizer; when it returns anything but null (no key, free quota used up,
/// no network, a crisis this conversation...), carry on with the recognizer +
/// phone brain as before. Spike never shows the reason as an error.
library;

import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../away/ai/gemini.dart';
import '../away/ai/gemini_live.dart';
import '../away/ai/gemini_voices.dart';
import '../away/ai/key_store.dart';
import '../away/ai/live_talk.dart';
import '../away/brain/persona.dart';
import '../away/brain/phone_brain.dart';
import '../away/brain/reply.dart' show parseReply;
import '../away/brain/safety.dart' as safety;
import '../away/voice/gemini_tts.dart';
import '../away/voice/pcm_stream.dart';
import '../away/voice/speaker.dart';
import '../away/voice/voice_chain.dart';
import 'away.dart';
import 'link.dart';
import 'settings.dart';

enum LivePhase { idle, connecting, live }

@immutable
class LiveVoiceState {
  const LiveVoiceState({this.phase = LivePhase.idle, this.talkState = 'idle', this.lastEnd, this.said = '', this.detail});
  final LivePhase phase;
  final String talkState; // listening | thinking | speaking | idle
  final LiveTalkEnd? lastEnd;
  final String said; // Spike's last words (preview screen)
  final String? detail; // why Live could not start, in a short safe form (preview screen)
  LiveVoiceState copyWith({LivePhase? phase, String? talkState, LiveTalkEnd? lastEnd, String? said}) => LiveVoiceState(
      phase: phase ?? this.phase, talkState: talkState ?? this.talkState, lastEnd: lastEnd ?? this.lastEnd, said: said ?? this.said);
}

class GeminiLiveController extends Notifier<LiveVoiceState> {
  LiveTalk? _talk;
  final _sink = SoloudPcmSink();
  RecordMic? _mic;
  DateTime? _restUntil; // after the free quota ran out
  Persona? _dog, _cat;
  BrainSettings? _settings;
  final _rng = Random();

  @override
  LiveVoiceState build() {
    ref.onDispose(() {
      unawaited(_talk?.stop());
      unawaited(_mic?.dispose());
    });
    return const LiveVoiceState();
  }

  GeminiVoicePicks get picks => ref.read(awayProvider.notifier).voicePicks;
  PhoneBrain? get _brain => ref.read(brainClientProvider).away ? ref.read(brainClientProvider).phone : null;

  /// Live may be used right now: a key, the owner's switch on, quota not resting, no crisis this conversation.
  bool get liveAvailable {
    try {
      final b = _brain;
      return b != null &&
          ref.read(awayProvider).hasKey &&
          picks.liveOn &&
          (_restUntil == null || DateTime.now().isAfter(_restUntil!)) &&
          !b.inCrisis;
    } catch (_) {
      return false; // anything missing: the recognizer path, as before
    }
  }

  Future<void> _load() async {
    _dog ??= Persona.fromToml(await rootBundle.loadString('assets/brain/spike.toml'));
    _cat ??= Persona.fromToml(await rootBundle.loadString('assets/brain/spicy.toml'));
    _settings ??= BrainSettings.fromToml(await rootBundle.loadString('assets/brain/default.toml'));
  }

  Future<String?> _key() => ref.read(secretStoreProvider).read(aiKeyName('gemini'));

  /// The away conversation through Live. Null while it runs to its end normally;
  /// otherwise why it could not (the caller falls back to the recognizer path).
  Future<LiveTalkEnd?> startConversation() async {
    final b = _brain;
    if (b == null || !liveAvailable) return LiveTalkEnd.unavailable;
    return _run(mode: b.mode, style: picks.styleFor(b.mode), brain: b, listen: true);
  }

  /// The preview: a Live session with no microphone; [lines] are said one after another.
  Future<LiveTalkEnd?> preview(String mode, VoiceStyle style, List<String> lines, {PcmSink? sink}) =>
      _run(mode: mode, style: style, brain: null, listen: false, lines: lines, sink: sink);

  /// Talk live on the preview screen with any voice (standalone when the laptop is the brain).
  Future<LiveTalkEnd?> previewTalk(String mode, VoiceStyle style) =>
      _run(mode: mode, style: style, brain: _brain, listen: true);

  Future<void> stop() async => _talk?.stop();

  Future<LiveTalkEnd?> _run(
      {required String mode,
      required VoiceStyle style,
      PhoneBrain? brain,
      required bool listen,
      List<String> lines = const [],
      PcmSink? sink}) async {
    final voice = style.voice;
    await _talk?.stop();
    await _load();
    final key = await _key();
    if (key == null || key.isEmpty) return LiveTalkEnd.badKey;
    final persona = mode == 'cat' ? _cat! : _dog!;
    final settings = _settings!;
    final owner = brain?.memory.ownerName();
    final sys = liveSystemInstruction(persona, owner, settings.helpline(),
        soft: brain?.supportKind != null, robotAway: brain == null || !brain.robots.online, style: style);
    final silenceMs = (ref.read(settingsProvider).voiceWaitS * 1000).round();
    final classifier = GeminiProvider(apiKey: key);
    final tts = GeminiTtsVoice(apiKey: key, voiceFor: (_) => voice, styleFor: (m, soft) => ttsStyle(m, soft: soft, style: style));
    final standalone = VoiceChain.ordered(gemini: tts, android: AndroidVoice());

    Future<void> speakLine(String lineKey, [Map<String, String> fmt = const {}]) async {
      if (brain != null) {
        await brain.sayLine(lineKey, fmt);
        return;
      }
      final text = parseReply(persona.line(lineKey, _rng, fmt)).text;
      state = state.copyWith(said: text);
      final spoken = sayAs(text, settings.sayAs());
      final p = await standalone.prepare(spoken, mode: mode, soft: lineKey == 'crisis' || lineKey == 'emergency');
      await p.play();
    }

    final hooks = LiveTalkHooks(
      crisis: (kind) async {
        if (brain != null) {
          await brain.crisis(kind);
        } else {
          await speakLine(kind == 'emergency' ? 'emergency' : 'crisis', settings.helpline());
        }
      },
      blocked: () => speakLine('unsafe_replacement'),
      replace: (rule) => speakLine(rule == 'not_honest' ? 'honest_robot' : 'unsafe_replacement'),
      heard: (t) => brain?.liveHeard(t),
      said: (s) {
        brain?.liveSaid(s);
        state = state.copyWith(said: state.talkState == 'speaking' && state.said.isNotEmpty ? '${state.said} $s' : s);
      },
      state: (s) {
        brain?.setListening(s == 'listening' ? 'idle' : s); // the brain's word for "ready to hear you"
        state = state.copyWith(talkState: s, said: s == 'thinking' ? '' : null);
      },
      classify: (text) async {
        final raw = await classifier.completeJson(safety.classifierSystem, text, safety.classifierSchema,
            maxTokens: 20, timeout: const Duration(seconds: 4));
        return safety.parseClassifier(raw);
      },
    );

    final talk = _talk = LiveTalk(
      open: ({String? resumeHandle}) => GeminiLiveSession.connect(
        apiKey: key,
        // affective off: on the S23 with the owner's key (30 Sep, self-test log) Google closes 1007
        // 'Unknown name "enableAffectiveDialog" at setup' on gemini-3.8-live: asking costs a round trip
        config: LiveConfig(voice: voice, systemInstruction: sys, silenceMs: silenceMs, resumeHandle: resumeHandle, affective: false),
      ),
      sink: sink ?? _sink,
      mic: listen ? (_mic ??= RecordMic()) : null,
      hooks: hooks,
    );
    state = state.copyWith(phase: LivePhase.connecting, said: '');
    final ok = await talk.start(listen: listen);
    if (ok) {
      state = state.copyWith(phase: LivePhase.live);
      if (lines.isNotEmpty) unawaited(_sayLines(talk, lines));
    }
    final end = await talk.done;
    classifier.close();
    tts.close();
    if (end == LiveTalkEnd.rateLimited) _restUntil = DateTime.now().add(const Duration(minutes: 30));
    if (identical(_talk, talk)) _talk = null;
    state = LiveVoiceState(lastEnd: end, said: state.said, detail: talk.error?.message);
    return end == LiveTalkEnd.stopped ? null : end;
  }

  /// Preview: each line in turn ("say exactly this, in character"), then the question.
  Future<void> _sayLines(LiveTalk talk, List<String> lines) async {
    for (final line in lines) {
      if (!talk.running) return;
      talk.sendText(line.endsWith('?') ? line : 'Say exactly this line, in character, and nothing else: "$line"');
      // wait for the turn to be spoken and the talk to be listening/idle again
      await Future<void>.delayed(const Duration(milliseconds: 600));
      final deadline = DateTime.now().add(const Duration(seconds: 25));
      while (talk.running && state.talkState != 'listening' && state.talkState != 'idle' && DateTime.now().isBefore(deadline)) {
        await Future<void>.delayed(const Duration(milliseconds: 150));
      }
      await Future<void>.delayed(const Duration(milliseconds: 500));
    }
    await talk.stop();
  }
}

final liveVoiceProvider = NotifierProvider<GeminiLiveController, LiveVoiceState>(GeminiLiveController.new);
