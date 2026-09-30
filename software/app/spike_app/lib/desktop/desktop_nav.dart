/// The desktop navigation (software/app/DESIGN.md "Desktop"): a rail on medium windows, a sidebar
/// with names, shortcuts and a live status card on expanded and large ones. It sits on the window's
/// own background (the title bar is painted the same colour, desktop_window.dart), so the chrome
/// reads as one surface and the pages' cards float on it.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../core/brand.dart';
import '../core/layout.dart';
import '../core/nav.dart';
import '../core/motion.dart';
import '../core/theme.dart';
import '../protocol/client.dart' show LinkStatus;
import '../state/link.dart';
import '../state/settings.dart';
import 'brain_sidecar.dart';
import 'desktop_state.dart';
import 'mini_window.dart';

class DesktopNav extends ConsumerWidget {
  const DesktopNav({super.key, required this.index, required this.items, required this.onTap});
  final int index;
  /// (icon, label, shell branch): the desktop's own sections (app.dart desktopSections).
  final List<(IconData, String, int)> items;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final m = context.metrics;
    final ext = m.navExtended;
    Widget row(IconData icon, String label, bool selected, VoidCallback go, {String? keys}) => _NavRow(
          icon: icon,
          label: label,
          selected: selected,
          extended: ext,
          keys: keys,
          onTap: go,
        );
    return Container(
      width: m.navWidth,
      decoration: BoxDecoration(color: p.bg, border: Border(right: BorderSide(color: p.line))),
      padding: EdgeInsets.symmetric(horizontal: ext ? Space.x4 : Space.x2, vertical: Space.x4),
      child: Column(crossAxisAlignment: ext ? CrossAxisAlignment.stretch : CrossAxisAlignment.center, children: [
        // the brand: the logo, and its name when there is room
        Padding(
          padding: EdgeInsets.fromLTRB(ext ? Space.x2 : 0, Space.x1, 0, Space.x6),
          child: Row(mainAxisAlignment: ext ? MainAxisAlignment.start : MainAxisAlignment.center, children: [
            SvgPicture.asset('assets/icon/spike_icon.svg', width: 40, height: 40, semanticsLabel: AppBrand.productName),
            if (ext) ...[
              const SizedBox(width: Space.x3),
              Text(AppBrand.productName, style: context.tt.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            ],
          ]),
        ),
        for (var i = 0; i < items.length; i++)
          row(items[i].$1, items[i].$2, items[i].$3 == index, () => onTap(items[i].$3), keys: 'Ctrl+${i + 1}'),
        const Spacer(),
        if (ext) const _StatusCard() else const _StatusDot(),
        const SizedBox(height: Space.x3),
        row(Icons.picture_in_picture_alt_rounded, 'Mini window', false, () => ref.read(miniWindowProvider.notifier).enter(MediaQuery.sizeOf(context)),
            keys: 'Ctrl+M'),
        row(Icons.phonelink_rounded, 'Phone and robot', index == 6, () => openPage(context, '/phone')),
        row(Icons.settings_rounded, 'Settings', index == 5, () => openPage(context, '/settings'), keys: 'Ctrl+,'),
      ]),
    );
  }
}

class _NavRow extends StatelessWidget {
  const _NavRow({required this.icon, required this.label, required this.selected, required this.extended, required this.onTap, this.keys});
  final IconData icon;
  final String label;
  final bool selected;
  final bool extended;
  final VoidCallback onTap;
  final String? keys;

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final color = selected ? p.accent : p.ink.withValues(alpha: 0.78);
    final bg = selected ? p.accent.withValues(alpha: context.isDark ? 0.22 : 0.13) : Colors.transparent;
    final Widget body = extended
        // sidebar: a 44 px row (icon 22 | 12 | label 15 semibold | shortcut 12 muted)
        ? AnimatedContainer(
            duration: const Duration(milliseconds: 280),
            curve: Springs.smoothCurve,
            height: 44,
            padding: const EdgeInsets.symmetric(horizontal: Space.x3),
            decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(Radii.control)),
            child: Row(children: [
              Icon(icon, size: 22, color: color),
              const SizedBox(width: Space.x3),
              Expanded(
                child: Text(label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: context.tt.bodyLarge?.copyWith(fontSize: 15, color: selected ? p.ink : color, fontWeight: selected ? FontWeight.w800 : FontWeight.w600)),
              ),
              if (keys != null) Text(keys!, style: context.tt.labelSmall?.copyWith(color: p.muted)),
            ]),
          )
        // rail: a 72 x 60 target (icon 24 over a 12 px label)
        : AnimatedContainer(
            duration: const Duration(milliseconds: 280),
            curve: Springs.smoothCurve,
            width: 72,
            height: 60,
            decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(Radii.tile)),
            child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(icon, size: 24, color: color),
              const SizedBox(height: Space.x1),
              Text(label.split(' ').first,
                  style: context.tt.labelSmall?.copyWith(color: color, fontWeight: selected ? FontWeight.w800 : FontWeight.w600)),
            ]),
          );
    final item = Pressable(haptic: false, scale: 0.96, semanticLabel: label, onTap: onTap, child: body);
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.x1),
      child: extended || keys == null
          ? item
          : Tooltip(message: '$label  ($keys)', waitDuration: const Duration(milliseconds: 500), child: item),
    );
  }
}

(Color, String, String) _brainLine(BrainSidecarState b, LinkStatus link) => switch (b.run) {
      BrainRun.running when link.isConnected => (Brand.ok, 'Brain running', 'On this computer'),
      BrainRun.running || BrainRun.starting || BrainRun.restarting => (Brand.warn, 'Brain starting', 'A few seconds'),
      BrainRun.stopped => (const Color(0xFF8A7B70), 'Brain stopped', ''),
      _ => (Brand.tongue, 'Brain problem', 'See Settings'),
    };

/// Expanded/large: what matters at a glance, always in the same place: the brain, the robot,
/// and whether Spike has his AI key.
class _StatusCard extends ConsumerWidget {
  const _StatusCard();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final d = ref.watch(desktopProvider);
    final link = ref.watch(linkStatusProvider).value ?? const LinkStatus();
    final spike = ref.watch(spikeStateProvider);
    final name = ref.watch(settingsProvider.select((s) => s.dogName));
    final (bc, bt, _) = _brainLine(d.brain, link);
    final robot = spike.robotOnline
        ? (Brand.ok, spike.battery == null ? 'Robot connected' : 'Robot · ${spike.battery!.round()}%${spike.charging ? ' charging' : ''}')
        : (p.muted, 'No robot connected');
    final ai = d.hasKey ? (Brand.ok, 'Gemini ready') : (Brand.warn, 'Add a Gemini key');
    Widget line(Color c, String t, {VoidCallback? onTap}) {
      final w = Padding(
        padding: const EdgeInsets.symmetric(vertical: Space.x1),
        child: Row(children: [
          Container(width: 8, height: 8, decoration: BoxDecoration(color: c, shape: BoxShape.circle)),
          const SizedBox(width: Space.x3),
          Expanded(child: Text(t, maxLines: 1, overflow: TextOverflow.ellipsis, style: context.tt.bodyMedium)),
        ]),
      );
      return onTap == null ? w : Pressable(haptic: false, scale: 0.98, onTap: onTap, child: w);
    }

    return Container(
      padding: const EdgeInsets.all(Space.x4),
      decoration: BoxDecoration(color: p.card, borderRadius: BorderRadius.circular(Radii.tile), border: Border.all(color: p.line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(name, style: context.tt.labelLarge?.copyWith(color: p.muted, fontWeight: FontWeight.w700)),
        const SizedBox(height: Space.x2),
        line(bc, bt),
        line(robot.$1, robot.$2, onTap: () => openPage(context, '/phone')),
        line(ai.$1, ai.$2, onTap: d.hasKey ? null : () => openPage(context, '/settings')),
      ]),
    );
  }
}

/// Medium: the brain state as one dot; its tooltip holds the whole status card (brain, robot, Gemini).
class _StatusDot extends ConsumerWidget {
  const _StatusDot();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final d = ref.watch(desktopProvider);
    final link = ref.watch(linkStatusProvider).value ?? const LinkStatus();
    final spike = ref.watch(spikeStateProvider);
    final (c, t, sub) = _brainLine(d.brain, link);
    final robot = spike.robotOnline
        ? (spike.battery == null ? 'Robot connected' : 'Robot connected · ${spike.battery!.round()}%')
        : 'No robot connected';
    return Tooltip(
      message: '${sub.isEmpty ? t : '$t · $sub'}\n$robot\n${d.hasKey ? 'Gemini ready' : 'Add a Gemini key'}',
      child: Semantics(label: t, child: Container(width: 10, height: 10, decoration: BoxDecoration(color: c, shape: BoxShape.circle))),
    );
  }
}
