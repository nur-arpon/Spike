/// Settings that exist only on the desktop (software/app/DESIGN.md "Desktop"): the built-in brain,
/// Start with Windows, the computer's microphone, the Gemini key and voice, the phone and robot.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';


import '../core/haptics.dart';
import '../core/nav.dart';
import '../core/theme.dart';
import '../core/widgets.dart';
import '../features/settings/away_settings.dart' show GeminiKeyCard;
import '../protocol/client.dart' show LinkStatus;
import '../features/settings/voice_preview_screen.dart' show VoicePreviewScreen;
import '../state/away.dart';
import '../state/link.dart';
import '../state/settings.dart';
import 'brain_sidecar.dart';
import 'desktop_channel.dart';
import 'desktop_state.dart';

class DesktopSettings extends ConsumerWidget {
  const DesktopSettings({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final d = ref.watch(desktopProvider);
    final s = ref.watch(settingsProvider);
    final link = ref.watch(linkStatusProvider).value ?? const LinkStatus();
    final p = context.sp;
    final ctl = ref.read(desktopProvider.notifier);
    final (IconData icon, Color color, String title, String sub) = switch (d.brain.run) {
      BrainRun.running when link.isConnected => (
          Icons.check_circle_rounded,
          Brand.ok,
          'Spike\'s brain is running',
          'On this computer${d.brain.port == null ? '' : ', port ${d.brain.port}'}${d.hasKey ? '' : '. Add a Gemini key below so he can really chat.'}'
        ),
      BrainRun.running || BrainRun.starting => (Icons.hourglass_top_rounded, Brand.warn, 'Starting Spike\'s brain', 'A few seconds...'),
      BrainRun.restarting => (Icons.restart_alt_rounded, Brand.warn, 'Restarting Spike\'s brain', d.brain.detail ?? ''),
      BrainRun.missing => (Icons.error_outline_rounded, Brand.tongue, 'Spike\'s brain is missing', 'Reinstall the app from the Microsoft Store.'),
      BrainRun.failed => (Icons.error_outline_rounded, Brand.tongue, 'Spike\'s brain stopped', d.brain.detail ?? 'Try again.'),
      BrainRun.stopped => (Icons.pause_circle_outline_rounded, p.muted, 'Spike\'s brain is stopped', ''),
    };
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      const SectionHeader('Spike on this computer', subtitle: 'His brain runs here; your phone and the robot connect to it', first: true),
      SpikeCard(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Column(children: [
          ListTile(
            leading: Icon(icon, color: color),
            title: Text(title),
            subtitle: sub.isEmpty ? null : Text(sub),
            trailing: d.brain.run == BrainRun.failed
                ? TextButton(onPressed: () => unawaited(ctl.retryBrain()), child: const Text('Try again'))
                : null,
          ),
          Divider(height: 1, color: p.line),
          SwitchListTile(
            title: const Text('Start with Windows'),
            subtitle: Text(d.startWithWindows.note ?? 'Spike waits quietly by the clock after you sign in'),
            value: d.startWithWindows.isOn,
            onChanged: d.startWithWindows.canChange
                ? (v) {
                    Haptics.tick();
                    unawaited(ctl.setStartWithWindows(v));
                  }
                : null,
          ),
          SwitchListTile(
            title: const Text('Listen on this computer\'s microphone'),
            subtitle: Text(s.desktopMic
                ? 'He hears his name (${_wake(ref)}) and your voice. Speech is turned into words on this computer.'
                : 'Off: talk to him by typing, or from your phone.'),
            value: s.desktopMic,
            onChanged: (v) {
              Haptics.tick();
              unawaited(ctl.setMic(v));
            },
          ),
          Divider(height: 1, color: p.line),
          ListTile(
            leading: Icon(Icons.phonelink_rounded, color: p.accent),
            title: const Text('Phone and robot'),
            subtitle: const Text('Pair your phone, reach Spike from anywhere, set up a robot'),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => openPage(context, '/phone'),
          ),
        ]),
      ),
      const SectionHeader('Spike\'s AI', subtitle: 'Gemini, with your own free key'),
      GeminiKeyCard(
        onChanged: ctl.keyChanged,
        savedText: 'Saved. Spike thinks and talks with Gemini now.',
        whereKept: 'Windows\' protected storage for your account',
      ),
    ]);
  }
}

String _wake(WidgetRef ref) {
  final w = ref.watch(spikeStateProvider.select((s) => s.wakeWords));
  final dog = w['dog'] ?? const ['Spike'];
  return dog.take(2).join(', ');
}

/// Settings > Voice on the desktop: the top of the right column (choosing his voice is an everyday task,
/// so it is in view at 1366 x 768 without scrolling).
class DesktopVoiceCard extends ConsumerWidget {
  const DesktopVoiceCard({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(desktopProvider); // picks can change from the brain (another device picked one)
    final hasKey = ref.watch(awayProvider.select((a) => a.hasKey));
    final picks = ref.read(awayProvider.notifier).voicePicks;
    final s = ref.watch(settingsProvider);
    String label(String mode) {
      final st = picks.styleFor(mode);
      return '${s.nameFor(mode)}: ${st.label} (${st.voice})';
    }

    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.graphic_eq_rounded, color: hasKey ? Brand.ok : context.sp.accent),
          const SizedBox(width: 10),
          Expanded(child: Text('Gemini natural voice', style: context.tt.titleMedium)),
          if (hasKey) const StatusPill(label: 'Ready', dot: Brand.ok),
        ]),
        const SizedBox(height: 6),
        Text(
            hasKey
                ? '${label('dog')}. ${label('cat')}. Without internet, or when the free quota is used up, he uses '
                    'Windows\' own voice until Gemini is back.'
                : 'With a Gemini key Spike gets a natural voice. Until then he speaks with Windows\' own voice.',
            style: context.tt.bodySmall),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          PillButton(
            label: 'Choose voices',
            icon: Icons.record_voice_over_rounded,
            onTap: () => Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const VoicePreviewScreen())),
          ),
        ]),
      ]),
    );
  }
}
