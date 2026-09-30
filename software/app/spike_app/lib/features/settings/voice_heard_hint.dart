import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../away/voice/laptop_voice.dart';
import '../../state/voice_out.dart';

/// The subtitle of "Spike talks on this phone": what the switch does, and (quietly)
/// which voice was heard last - the laptop's real voice, or the phone's own (v1.5).
class VoiceHeardHint extends ConsumerWidget {
  const VoiceHeardHint({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final last = switch (ref.watch(voiceHeardProvider)) {
      VoiceHeard.laptop => ' · laptop voice',
      VoiceHeard.phone => ' · phone voice',
      null => '',
    };
    return Text('He answers here when you talk from this phone$last');
  }
}
