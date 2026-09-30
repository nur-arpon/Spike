/// Home on the desktop (software/app/DESIGN.md "Desktop > Proportions", "Natural use").
///
/// The page is where the owner says hi: Spike's face is the hero, the conversation sits next to it
/// with its box ready (just type, or press Space), and the five quick actions are one row under
/// the face. Compositions per size class (core/layout.dart):
///
///   medium / expanded   hero | conversation   at the golden split (61.8 : 38.2); under the hero,
///                       when the height allows it, "Coming up" and "Meet Spike in 3D"
///   large, room >= 1924 hero (the face's own width, at most 2x native) | conversation (a reading
///                       column, at most 720 + padding) | "Today" (everything else, >= 320);
///                       a narrower large room (a 1920 window) keeps the golden two panes
///
/// The face is always exactly 480:272 and is sized by whichever runs out first: the hero's width,
/// the height left after the header and the action row, or 2x its native size.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';

import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/nav.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/client.dart';
import '../../protocol/messages.dart';
import '../../protocol/names.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import '../face/face_view.dart';
import '../life/timers_state.dart';
import '../talk/chat_panel.dart';
import 'home_screen.dart' show AlarmBar, FaceCard, LinkPill, batteryIcon;
import 'mode_switch.dart';

const _quick = [
  (Icons.back_hand_rounded, 'Pat', 'pat'),
  (Icons.touch_app_rounded, 'Boop', 'boop'),
  (Icons.cookie_rounded, 'Treat', 'treat'),
  (Icons.sports_baseball_rounded, 'Play', 'play'),
  (Icons.bedtime_rounded, 'Sleep', 'sleep'),
];

/// Heights that the page is built from (all on the 8-pt grid).
const double _header = 56; // greeting (20) + name (36)
const double _modeSwitch = 60; // the Spike | Spicy switch's own height
const double _extrasMin = 112; // below this, the cards under the hero are not shown (a two-line card is 104)

class HomeDesktop extends ConsumerWidget {
  const HomeDesktop({super.key, required this.face, required this.onQuick, required this.greeting});
  final FaceController face;
  final void Function(String what) onQuick;
  final String greeting;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final m = context.metrics;
    final spike = ref.watch(spikeStateProvider);
    final settings = ref.watch(settingsProvider);
    final name = settings.nameFor(spike.mode);
    return Scaffold(
      body: Padding(
        padding: EdgeInsets.all(m.pagePad),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          SizedBox(height: _header, child: _Header(greeting: greeting, name: name)),
          const SizedBox(height: Space.x6),
          Expanded(
            child: LayoutBuilder(builder: (context, c) {
              // three panes only when the face can be full size AND the conversation keeps a real reading width;
              // a 1920 window is still two panes at the golden split (a bigger face, a 590 px conversation)
              if (m.cls == SizeClass.large && c.maxWidth >= _threePaneMin(m)) return _large(context, c, m);
              final (main, side) = goldenSplit(c.maxWidth, m.gutter);
              return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                SizedBox(width: main, child: _Hero(face: face, onQuick: onQuick, height: c.maxHeight, extras: true)),
                SizedBox(width: m.gutter),
                SizedBox(width: side, child: const ChatPanel()),
              ]);
            }),
          ),
        ]),
      ),
    );
  }

  /// The narrowest room for three panes: the full-size face card, a 560 conversation, the Today column.
  static double _threePaneMin(DesktopMetrics m) => DesktopMetrics.faceMax + 20 + m.gutter + 560 + m.gutter + DesktopMetrics.statusColumn;

  Widget _large(BuildContext context, BoxConstraints c, DesktopMetrics m) {
    // the hero is exactly as wide as its face; the conversation is a reading column; the rest is Today
    final fixed = _Hero.fixedHeight;
    final faceW = faceSize(math.min(DesktopMetrics.faceMax, c.maxWidth * 0.5), c.maxHeight - fixed).width;
    final chatW = math.min(DesktopMetrics.readingMax + 2 * Space.x5, c.maxWidth - faceW - DesktopMetrics.statusColumn - 2 * m.gutter);
    return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      SizedBox(width: faceW, child: _Hero(face: face, onQuick: onQuick, height: c.maxHeight, extras: true, robotCard: true)),
      SizedBox(width: m.gutter),
      SizedBox(width: chatW, child: const ChatPanel()),
      SizedBox(width: m.gutter),
      const Expanded(child: _Today()),
    ]);
  }
}

class _Header extends ConsumerWidget {
  const _Header({required this.greeting, required this.name});
  final String greeting;
  final String name;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final link = ref.watch(linkStatusProvider).value ?? const LinkStatus();
    final spike = ref.watch(spikeStateProvider);
    return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
      Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(greeting, style: context.tt.bodyMedium?.copyWith(color: p.muted, fontWeight: FontWeight.w600)),
        Text(name, style: context.tt.headlineMedium?.copyWith(fontWeight: FontWeight.w800, height: 1.1)),
      ]),
      const SizedBox(width: Space.x6),
      Expanded(
        child: Wrap(spacing: Space.x2, runSpacing: Space.x2, alignment: WrapAlignment.end, children: [
          LinkPill(status: link),
          StatusPill(label: moodLabel(spike.mood), icon: Icons.mood_rounded),
          if (link.isConnected && spike.robotOnline)
            StatusPill(
              label: spike.battery == null ? 'Robot connected' : '${spike.battery!.round()}%${spike.charging ? ' charging' : ''}',
              icon: spike.charging ? Icons.battery_charging_full_rounded : batteryIcon(spike.battery),
            ),
          if (spike.listening != 'idle')
            StatusPill(
              label: switch (spike.listening) {
                'listening' || 'wake' => 'Listening',
                'thinking' => 'Thinking',
                _ => 'Talking',
              },
              dot: p.accent,
              pulse: true,
            ),
        ]),
      ),
      const SizedBox(width: Space.x3),
      Tooltip(
        message: 'Spike in 3D',
        child: IconButton.filledTonal(
          onPressed: () => context.push('/viewer'),
          icon: const Icon(Icons.view_in_ar_rounded),
        ),
      ),
    ]);
  }
}

/// The face, the quick actions and the Spike | Spicy switch, sized from the height left.
class _Hero extends ConsumerWidget {
  const _Hero({required this.face, required this.onQuick, required this.height, required this.extras, this.robotCard = false});
  final FaceController face;
  final void Function(String) onQuick;
  final double height;
  final bool extras;

  /// Large windows: the extras row shows the robot next to Coming up (3D moves to the Today pane).
  final bool robotCard;

  /// Everything in the hero column except the face (its gaps on the 8-pt grid).
  static const double fixedHeight = Space.x4 + DesktopMetrics.actionTile + Space.x4 + _modeSwitch + 2 * 10; // + the face card's frame

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final spike = ref.watch(spikeStateProvider);
    final settings = ref.watch(settingsProvider);
    return LayoutBuilder(builder: (context, c) {
      final alarm = spike.alarmRinging ? 88.0 + Space.x4 : 0.0;
      final fs = faceSize(c.maxWidth - 20, height - fixedHeight - alarm);
      final left = height - fixedHeight - alarm - fs.height;
      // the character's controls stay together (face, actions, Spike | Spicy), then the day's cards when
      // there is room; the column is read top down and any spare height stays below it as air (a gap in
      // the middle of the column read as a hole in the 2400 x 1300 screenshots)
      final showExtras = extras && left >= _extrasMin + Space.x6;
      final switcher = SizedBox(
        width: fs.width + 20,
        child: ModeSwitch(
          mode: spike.mode,
          dogName: settings.dogName,
          catName: settings.catName,
          onChanged: (m) {
            Haptics.thud();
            ref.read(spikeStateProvider.notifier).localMode(m);
            ref.read(commandsProvider).setMode(m, dogName: settings.dogName, catName: settings.catName);
          },
        ),
      );
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: fs.width + 20, child: FaceCard(face: face, caption: spike.caption, alarm: spike.alarmRinging)),
        if (spike.alarmRinging) ...[
          const SizedBox(height: Space.x4),
          SizedBox(width: fs.width + 20, child: AlarmBar(label: spike.alarmLabel)),
        ],
        const SizedBox(height: Space.x4),
        SizedBox(
          width: fs.width + 20,
          height: DesktopMetrics.actionTile,
          child: Row(children: [
            for (final (i, q) in _quick.indexed) ...[
              if (i > 0) const SizedBox(width: Space.x2),
              Expanded(child: DeskTile(icon: q.$1, label: q.$2, onTap: () => onQuick(q.$3))),
            ],
          ]),
        ),
        if (showExtras) ...[
          const SizedBox(height: Space.x4),
          switcher,
          const SizedBox(height: Space.x6),
          SizedBox(
            width: fs.width + 20,
            child: IntrinsicHeight(
              child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                const Expanded(child: _ComingUp()),
                const SizedBox(width: Space.x4),
                Expanded(child: robotCard ? const _RobotCard() : const _Meet3D()),
              ]),
            ),
          ),
        ] else ...[
          const SizedBox(height: Space.x4),
          switcher,
        ],
      ]);
    });
  }
}

/// Large windows: the third pane.
class _Today extends StatelessWidget {
  const _Today();
  @override
  Widget build(BuildContext context) => ListView(padding: EdgeInsets.zero, children: const [
        _Meet3D(),
        SizedBox(height: Space.x4),
        _MemoriesCard(),
        SizedBox(height: Space.x4),
        _PhoneCard(),
      ]);
}

class _ComingUp extends ConsumerWidget {
  const _ComingUp();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final timers = ref.watch(timersProvider);
    final now = DateTime.now();
    final next = timers.items.take(3).toList();
    return SpikeCard(
      onTap: () => StatefulNavigationShell.maybeOf(context)?.goBranch(4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.alarm_rounded, color: p.accent, size: 22),
          const SizedBox(width: Space.x2),
          Expanded(child: Text('Coming up', style: context.tt.titleMedium)),
          Icon(Icons.chevron_right_rounded, color: p.muted),
        ]),
        const SizedBox(height: Space.x2),
        if (next.isEmpty)
          Text('No alarms or reminders. Tell him "wake me up at seven", or set one in Life.', style: context.tt.bodySmall)
        else
          for (final TimerItem t in next)
            Padding(
              padding: const EdgeInsets.only(top: Space.x1),
              child: Row(children: [
                SizedBox(
                  width: 72,
                  child: Text(TimeOfDay.fromDateTime(t.dueAt).format(context),
                      style: context.tt.titleSmall?.copyWith(fontFeatures: const [FontFeature.tabularFigures()])),
                ),
                Expanded(
                  child: Text(
                      '${t.repeat == 'daily' ? 'Every day' : dayLabel(t.dueAt, now)} · ${t.kind == 'alarm' ? 'Alarm' : t.label}',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: context.tt.bodySmall),
                ),
              ]),
            ),
      ]),
    );
  }
}

class _Meet3D extends ConsumerWidget {
  const _Meet3D();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final name = ref.watch(settingsProvider.select((s) => s.dogName));
    return SpikeCard(
      onTap: () => context.push('/viewer'),
      gradient: LinearGradient(
        colors: context.isDark ? [const Color(0xFF3A2A1F), const Color(0xFF231A14)] : [Brand.cream, const Color(0xFFF8EBDA)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      child: Row(children: [
        SvgPicture.asset('assets/icon/spike_icon.svg', width: 48, height: 48),
        const SizedBox(width: Space.x4),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Meet $name in 3D', style: context.tt.titleMedium),
            Text('Turn him around, try colours and screen states', style: context.tt.bodySmall),
          ]),
        ),
      ]),
    );
  }
}

class _RobotCard extends ConsumerWidget {
  const _RobotCard();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final spike = ref.watch(spikeStateProvider);
    return SpikeCard(
      onTap: () => openPage(context, '/phone'),
      child: Row(children: [
        Icon(spike.robotOnline ? Icons.smart_toy_rounded : Icons.smart_toy_outlined, color: spike.robotOnline ? Brand.ok : p.muted),
        const SizedBox(width: Space.x3),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(spike.robotOnline ? 'The robot is here' : 'No robot connected', style: context.tt.titleMedium),
            Text(
                spike.robotOnline
                    ? '${spike.battery == null ? 'Battery unknown' : 'Battery ${spike.battery!.round()}%'}${spike.robotCamera ? ' · camera on' : ''}'
                    : 'Set one up, or pair your phone',
                style: context.tt.bodySmall),
          ]),
        ),
        Icon(Icons.chevron_right_rounded, color: p.muted),
      ]),
    );
  }
}

class _MemoriesCard extends ConsumerWidget {
  const _MemoriesCard();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final mem = ref.watch(memoryProvider);
    final name = ref.watch(settingsProvider.select((s) => s.dogName));
    final n = mem.total ?? mem.items.length;
    return SpikeCard(
      onTap: () => openPage(context, '/memories'),
      child: Row(children: [
        const Icon(Icons.auto_stories_rounded, color: Brand.tongue),
        const SizedBox(width: Space.x3),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('What $name remembers', style: context.tt.titleMedium),
            Text(mem.synced ? (n == 0 ? 'Nothing yet. Tell him about your day.' : '$n ${n == 1 ? 'thing' : 'things'} about you') : 'Kept on this computer',
                style: context.tt.bodySmall),
          ]),
        ),
        Icon(Icons.chevron_right_rounded, color: p.muted),
      ]),
    );
  }
}

class _PhoneCard extends ConsumerWidget {
  const _PhoneCard();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    return SpikeCard(
      onTap: () => openPage(context, '/phone'),
      child: Row(children: [
        Icon(Icons.phonelink_rounded, color: p.accent),
        const SizedBox(width: Space.x3),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Your phone', style: context.tt.titleMedium),
            Text('Pair it to talk to Spike from the sofa, or from anywhere', style: context.tt.bodySmall),
          ]),
        ),
        Icon(Icons.chevron_right_rounded, color: p.muted),
      ]),
    );
  }
}
