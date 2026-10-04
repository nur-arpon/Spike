/// Spike's voice chain away from home (owner decision 30 Sep 2026):
///   1. the laptop's voice (Chatterbox, streamed from the laptop) - slot kept
///      for the laptop-voice work; null until it lands
///   2. Gemini natural voice (Gemini TTS with the owner's key and voice pick)
///   3. Kokoro on the phone (only once the owner installed the optional add-on: kokoro_addon.dart)
///   4. Android's text-to-speech, the last resort
/// Each sentence goes to the first voice that can make it; a voice that fails
/// (no network, free quota used up, not installed) is skipped quietly for that
/// sentence, so Spike never shows or says an error about his voice.
library;

import 'speaker.dart';

class VoiceChain implements SpikeVoice {
  VoiceChain(this.voices) : assert(voices.isNotEmpty);

  /// Build the chain in the owner's order from whatever is available right now.
  factory VoiceChain.ordered({SpikeVoice? laptop, SpikeVoice? gemini, SpikeVoice? kokoro, required SpikeVoice android}) =>
      VoiceChain([?laptop, ?gemini, ?kokoro, android]);

  final List<SpikeVoice> voices;

  /// The voice that made the last sentence (for the settings screen).
  String? lastUsed;

  @override
  String get name => voices.first.name;

  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    Object? last;
    for (final v in voices) {
      try {
        final p = await v.prepare(text, mode: mode, soft: soft);
        lastUsed = v.name;
        return p;
      } catch (e) {
        last = e;
      }
    }
    throw last ?? StateError('no voice');
  }

  @override
  Future<void> stop() async {
    for (final v in voices) {
      try {
        await v.stop();
      } catch (_) {}
    }
  }
}
