import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import '../../state/voice.dart';

/// Where the pill floats: just above the bottom nav bar (which is 68 tall, 10 up).
const voicePillHeight = 52.0;
double voicePillBottom(BuildContext context) => MediaQuery.paddingOf(context).bottom + 88;

/// The room a screen's own bottom controls leave for the pill while the mic is on.
const voicePillRoom = voicePillHeight + 10;

/// Wraps the whole app (MaterialApp.builder): while the mic is on, the voice
/// pill floats above every screen, the nav bar and sheets, and the mic's
/// notices (why it stopped) show as toasts.
class VoiceOverlay extends ConsumerWidget {
  const VoiceOverlay({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(voiceProvider.select((v) => v.noticeSeq), (prev, next) {
      final text = ref.read(voiceProvider).notice;
      if (prev != next && text != null) showToast(context, text, icon: Icons.mic_off_rounded);
    });
    final on = ref.watch(voiceProvider.select((v) => v.on));
    toastLift = on ? voicePillRoom : 0;
    return Stack(children: [
      child,
      Positioned(
        left: 16,
        right: 16,
        bottom: voicePillBottom(context),
        child: Center(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 460),
            reverseDuration: const Duration(milliseconds: 220),
            transitionBuilder: (c, a) {
              // the spring may overshoot 1: fine for position and scale, never for opacity
              final spring = CurvedAnimation(parent: a, curve: Springs.curve, reverseCurve: Curves.easeInCubic);
              return FadeTransition(
                opacity: CurvedAnimation(parent: a, curve: const Interval(0, 0.5)),
                child: SlideTransition(
                  position: Tween(begin: const Offset(0, 0.6), end: Offset.zero).animate(spring),
                  child: ScaleTransition(scale: Tween(begin: 0.8, end: 1.0).animate(spring), child: c),
                ),
              );
            },
            child: on ? const VoicePill(key: ValueKey('voicePill')) : const SizedBox.shrink(key: ValueKey('noPill')),
          ),
        ),
      ),
    ]);
  }
}

/// "Spike is listening": a live waveform, what he heard, and a stop button.
/// A tap on the pill while he talks interrupts him (when the brain can).
class VoicePill extends ConsumerStatefulWidget {
  const VoicePill({super.key});
  @override
  ConsumerState<VoicePill> createState() => _VoicePillState();
}

class _VoicePillState extends ConsumerState<VoicePill> with SingleTickerProviderStateMixin {
  late final AnimationController _wave = AnimationController(vsync: this, duration: const Duration(milliseconds: 1300))..repeat();

  @override
  void dispose() {
    _wave.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final v = ref.watch(voiceProvider);
    final mode = ref.watch(spikeStateProvider.select((s) => s.mode));
    final name = ref.watch(settingsProvider.select((s) => s.nameFor(mode)));
    final live = v.phase == VoicePhase.listening;
    final label = switch (v.phase) {
      VoicePhase.waiting => 'Waiting for $name…',
      VoicePhase.starting => 'Starting the mic…',
      VoicePhase.paused when v.pausedFor == 'speaking' => '$name is talking',
      VoicePhase.paused => '$name is thinking…',
      _ => v.caption ?? 'Listening…',
    };
    final hint = v.spikeTalking && v.canInterrupt ? 'Tap to cut in' : (v.phase == VoicePhase.waiting ? 'The mic stays on' : null);
    final width = min(MediaQuery.sizeOf(context).width - 32, 380.0);
    return Material(
      type: MaterialType.transparency,
      child: Semantics(
        container: true,
        liveRegion: true,
        label: 'Voice: $label',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: v.spikeTalking && v.canInterrupt ? () => ref.read(voiceProvider.notifier).interrupt() : null,
          child: Container(
            width: width,
            height: voicePillHeight,
            padding: const EdgeInsets.fromLTRB(6, 6, 6, 6),
            decoration: BoxDecoration(
              color: p.card.withValues(alpha: context.isDark ? 0.97 : 0.98),
              borderRadius: BorderRadius.circular(voicePillHeight / 2),
              border: Border.all(color: live ? Brand.tongue.withValues(alpha: 0.55) : p.line),
              boxShadow: [BoxShadow(color: p.shadow.withValues(alpha: context.isDark ? 0.5 : 0.18), blurRadius: 24, offset: const Offset(0, 8))],
            ),
            child: Row(children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: (live ? Brand.tongue : p.muted).withValues(alpha: context.isDark ? 0.22 : 0.13),
                  shape: BoxShape.circle,
                ),
                child: AnimatedBuilder(
                  animation: _wave,
                  builder: (_, _) => CustomPaint(
                    painter: _WavePainter(t: _wave.value, level: v.level, live: live, color: live ? Brand.tongue : p.muted),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 220),
                  layoutBuilder: (cur, prev) => Stack(alignment: Alignment.centerLeft, children: [...prev, ?cur]),
                  child: Column(
                    key: ValueKey('$label|$hint'),
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: context.tt.labelLarge?.copyWith(
                          color: v.caption != null && live ? p.ink : p.muted,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      if (hint != null)
                        Text(hint, maxLines: 1, overflow: TextOverflow.ellipsis,
                            style: context.tt.labelSmall?.copyWith(color: Brand.tongue, fontWeight: FontWeight.w700)),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Pressable(
                key: const ValueKey('voicePillStop'),
                haptic: false, // the stop has its own haptic (Haptics.voiceOff)
                scale: 0.86,
                semanticLabel: 'Stop listening',
                onTap: () => ref.read(voiceProvider.notifier).stop(),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: const BoxDecoration(color: Brand.tongue, shape: BoxShape.circle),
                  child: const Icon(Icons.stop_rounded, color: Colors.white, size: 22),
                ),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}

/// Five rounded bars that breathe with the microphone level.
class _WavePainter extends CustomPainter {
  _WavePainter({required this.t, required this.level, required this.live, required this.color});
  final double t;
  final double level;
  final bool live;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..strokeCap = StrokeCap.round
      ..strokeWidth = 3.2;
    const n = 5;
    const gap = 5.2;
    final x0 = size.width / 2 - gap * (n - 1) / 2;
    final amp = live ? 0.28 + 0.72 * level : 0.12;
    for (var i = 0; i < n; i++) {
      final wobble = 0.55 + 0.45 * sin(2 * pi * (t + i * 0.19));
      final centre = 1 - (i - 2).abs() * 0.18; // the middle bar is the tallest
      final h = 4 + 16 * amp * wobble * centre;
      final x = x0 + i * gap;
      canvas.drawLine(Offset(x, size.height / 2 - h / 2), Offset(x, size.height / 2 + h / 2), paint);
    }
  }

  @override
  bool shouldRepaint(_WavePainter old) => old.t != t || old.level != level || old.live != live || old.color != color;
}
