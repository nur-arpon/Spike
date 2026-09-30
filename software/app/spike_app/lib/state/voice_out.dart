/// Spike's voice coming out of this phone while the LAPTOP is the brain
/// (protocol v1.5, PROTOCOL.md 10.8; owner decision "laptop voice first").
///
/// - [laptopVoiceProvider]: the player (away/voice/laptop_voice.dart) fed by
///   the laptop link only. It plays the audio of replies to conversations that
///   came from this phone, falls back to the phone's own voice (Kokoro if the
///   pack is downloaded, else Android's) sentence by sentence, and reports
///   say_state back to the brain.
/// - [spikeSpeakingProvider]: true while Spike talks through this phone (plus
///   a 300 ms tail). The voice session (voice.dart) pauses the mic on it, next
///   to the brain's own `listening: speaking`.
/// - [voiceHeardProvider]: laptop or phone voice, the last one heard (a tiny
///   hint in Settings only).
/// - [nowSayingProvider]: each segment as it STARTS playing, so the phone's
///   face moves its mouth in time with the sound (face_view.dart).
///
/// Away from home the phone brain speaks with its own voice as before (away.dart).
library;

import 'dart:async';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../away/voice/gemini_tts.dart';
import '../away/voice/laptop_voice.dart';
import '../away/voice/soloud_output.dart';
import '../away/voice/speaker.dart';
import '../away/voice/voice_chain.dart';
import '../protocol/messages.dart';
import 'away.dart';
import 'link.dart';
import 'settings.dart';

final laptopVoiceProvider = Provider<LaptopVoicePlayer>((ref) {
  final hub = ref.watch(brainClientProvider);
  KokoroVoice? kokoro;
  AndroidVoice? android;
  AudioPlayer? player;

  Future<SpikeVoice> phoneVoice() async {
    android ??= AndroidVoice();
    unawaited(Future.microtask(() => ref.read(voiceSourceProvider.notifier).refresh())); // Gemini may have run out
    // owner order 30 Sep: laptop voice -> Gemini natural voice (with a key) -> Kokoro -> Android (voice_chain.dart)
    final gemini = ref.read(awayProvider.notifier).geminiVoice;
    try {
      final pack = await ref.read(awayProvider.notifier).voicePack();
      if (pack.installed) {
        player ??= AudioPlayer();
        kokoro ??= KokoroVoice(pack, player!);
        return gemini == null ? _KokoroThenAndroid(kokoro!, android!) : VoiceChain([gemini, kokoro!, android!]);
      }
      kokoro?.dispose();
      kokoro = null;
    } catch (_) {}
    return gemini == null ? android! : VoiceChain([gemini, android!]);
  }

  final p = LaptopVoicePlayer(
    output: SoloudOutput.instance,
    phoneVoice: phoneVoice,
    report: (utt, seq, state) => hub.lan.send(SayStateMsg(utt: utt, seq: seq, state: state)),
    mode: () => ref.read(spikeStateProvider).mode,
    enabled: () => ref.read(settingsProvider).phoneSpeaks,
  );
  final msgs = hub.lan.messages.listen(p.onMessage);
  final status = hub.lan.status.listen((s) {
    if (!s.isConnected) p.onLinkLost();
  });
  ref.onDispose(() {
    msgs.cancel();
    status.cancel();
    unawaited(p.dispose());
    kokoro?.dispose();
    unawaited(player?.dispose());
  });
  return p;
});

class SpikeSpeaking extends Notifier<bool> {
  @override
  bool build() {
    final p = ref.watch(laptopVoiceProvider);
    final sub = p.speaking.listen((v) => state = v);
    ref.onDispose(sub.cancel);
    return p.isSpeaking;
  }
}

/// True while Spike is talking through this phone's speaker (pause the mic).
final spikeSpeakingProvider = NotifierProvider<SpikeSpeaking, bool>(SpikeSpeaking.new);

class VoiceHeardNotifier extends Notifier<VoiceHeard?> {
  @override
  VoiceHeard? build() {
    final p = ref.watch(laptopVoiceProvider);
    final sub = p.heard.listen((v) => state = v);
    ref.onDispose(sub.cancel);
    return p.lastHeard;
  }
}

/// Which voice the owner last heard on this phone (null = none yet).
final voiceHeardProvider = NotifierProvider<VoiceHeardNotifier, VoiceHeard?>(VoiceHeardNotifier.new);

/// Segments as they start playing on this phone (for the face's mouth).
final nowSayingProvider = Provider<Stream<SayMsg>>((ref) => ref.watch(laptopVoiceProvider).nowSaying);

/// Who voices the replies this phone plays at home (protocol v1.7, PROTOCOL.md 10.10; owner
/// decision 30 Sep "Gemini voice first, at home too"):
///  - "phone": a Gemini key, Gemini TTS not resting, "Use the laptop voice instead" off, phone
///    voice on. The brain then sends each sentence as text only (`play: true`, `audio: null`, no
///    synthesis on the laptop) and [LaptopVoicePlayer] speaks it with [phoneVoice]: Gemini TTS
///    (the picked style) -> Kokoro -> Android. Safety: the brain checked every sentence before
///    sending it (the same text path as its own voice).
///  - "laptop": the brain's own voice (v1.5 behaviour).
/// When Gemini's free quota runs out mid-reply, that sentence falls to Kokoro/Android and the
/// next replies come in the laptop's voice (the source is re-checked after every sentence).
class VoiceSourceNotifier extends Notifier<String> {
  String? _sent; // what the connected brain was last told

  @override
  String build() {
    final hub = ref.read(brainClientProvider);
    final sub = hub.lan.status.listen((s) {
      if (s.isConnected) {
        _sent = null; // a new connection: tell this brain again
        refresh();
      }
    });
    ref.listen(awayProvider.select((a) => a.hasKey), (_, _) => refresh());
    ref.listen(settingsProvider.select((s) => s.phoneSpeaks), (_, _) => refresh());
    ref.onDispose(sub.cancel);
    Future.microtask(refresh);
    return _want();
  }

  String _want() {
    try {
      final away = ref.read(awayProvider.notifier);
      final g = away.geminiVoice;
      final ok = g is GeminiTtsVoice && g.available;
      return ok && ref.read(settingsProvider).phoneSpeaks && !away.voicePicks.laptopFirst ? 'phone' : 'laptop';
    } catch (_) {
      return 'laptop';
    }
  }

  /// Re-check and tell the laptop brain when it changed (only a v1.7 brain that says it understands).
  void refresh() {
    final want = _want();
    if (state != want) state = want;
    final lan = ref.read(brainClientProvider).lan;
    final cur = lan.current;
    if (!cur.isConnected || cur.hello?.voiceSource != true || _sent == want) return;
    if (lan.send(VoiceSourceMsg(voice: want))) _sent = want;
  }
}

final voiceSourceProvider = NotifierProvider<VoiceSourceNotifier, String>(VoiceSourceNotifier.new);

/// Kokoro first; if it fails for a sentence, Android's voice says it.
class _KokoroThenAndroid implements SpikeVoice {
  _KokoroThenAndroid(this.a, this.b);
  final SpikeVoice a, b;
  @override
  String get name => a.name;
  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    try {
      return await a.prepare(text, mode: mode, soft: soft);
    } catch (_) {
      return b.prepare(text, mode: mode, soft: soft);
    }
  }

  @override
  Future<void> stop() async {
    await a.stop();
    await b.stop();
  }
}
