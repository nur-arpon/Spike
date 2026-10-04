/// "Spike's story": the page behind the banner, the robot cards and Settings (software/app/DESIGN.md
/// "Robot push"). Who is building him, what he will do on a desk (only what the body really does,
/// from core/capabilities.dart), how the build is going, a note from the founder, and the main button.
///
/// Layout: a phone column up to 720 wide; from 900 wide (Windows) two designed panes: the picture,
/// the story and the button on the left, the details on the right. Nothing is stretched.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/brand.dart';
import '../../core/capabilities.dart';
import '../../core/layout.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import 'push_copy.dart';
import 'push_sheets.dart';
import 'push_widgets.dart';

/// The founder's note: assets/story/founder_note.txt, the ONE place to edit it.
final founderNoteProvider = FutureProvider<String>((ref) async => (await rootBundle.loadString('assets/story/founder_note.txt')).trim());

const _abilityIcons = <String, IconData>{
  'drive': Icons.sports_esports_rounded,
  'sit': Icons.airline_seat_recline_normal_rounded,
  'lieDown': Icons.bedtime_rounded,
  'playBow': Icons.pets_rounded,
  'headTilt': Icons.psychology_alt_rounded,
  'snuggle': Icons.favorite_rounded,
  'tailWagDance': Icons.music_note_rounded,
  'zoomies': Icons.autorenew_rounded,
  'backPaw': Icons.pan_tool_alt_rounded,
  'walk': Icons.directions_walk_rounded,
  'paw': Icons.front_hand_rounded,
};

class StoryScreen extends StatelessWidget {
  const StoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Scaffold(
      backgroundColor: p.bg,
      appBar: AppBar(
        backgroundColor: p.bg,
        scrolledUnderElevation: 0,
        title: const Text(storyTitle),
        leading: BackButton(onPressed: () => context.canPop() ? context.pop() : context.go('/home')),
      ),
      body: LayoutBuilder(builder: (context, c) {
        // the wide, two-pane design from the medium size class up (core/layout.dart)
        if (c.maxWidth >= Breakpoints.medium) return _Wide(width: c.maxWidth);
        return _Narrow(width: c.maxWidth);
      }),
    );
  }
}

class _Narrow extends StatelessWidget {
  const _Narrow({required this.width});
  final double width;
  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.paddingOf(context).bottom + 28;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: DesktopMetrics.readingMax),
        child: ListView(
          padding: EdgeInsets.fromLTRB(20, 4, 20, bottom),
          children: const [
            _Hero(),
            SizedBox(height: Space.x5),
            WaitlistButton(),
            _Beginning(),
            _Gallery(),
            _Things(),
            _Progress(),
            _Founder(),
            SizedBox(height: Space.x6),
            WaitlistButton(),
          ],
        ),
      ),
    );
  }
}

class _Wide extends StatelessWidget {
  const _Wide({required this.width});
  final double width;
  @override
  Widget build(BuildContext context) {
    final m = DesktopMetrics.of(Breakpoints.of(width));
    final (left, right) = goldenSplit(width - 2 * m.pagePad, m.gutter);
    // the picture pane takes the smaller share (38.2 %), the reading pane the larger (61.8 %), capped
    // at the reading column so lines stay readable on a large window
    final readW = right.clamp(0.0, DesktopMetrics.readingMax + Space.x16);
    final picW = left.clamp(0.0, 520.0);
    return Center(
      child: Padding(
        padding: EdgeInsets.fromLTRB(m.pagePad, Space.x2, m.pagePad, m.pagePad),
        child: Row(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            width: picW,
            child: ListView(children: const [
              RobotPanel(shot: 'hero', radius: Radii.card),
              SizedBox(height: Space.x5),
              WaitlistButton(),
              SizedBox(height: Space.x3),
            ]),
          ),
          SizedBox(width: m.gutter),
          SizedBox(
            width: readW,
            child: ListView(padding: const EdgeInsets.only(bottom: Space.x8), children: const [
              _Headline(),
              _Beginning(),
              _Things(),
              _Progress(),
              _Founder(),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _Headline extends StatelessWidget {
  const _Headline();
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(cardOverline, style: context.tt.labelMedium?.copyWith(color: context.sp.accent, fontWeight: FontWeight.w800, letterSpacing: 1.4)),
        const SizedBox(height: Space.x2),
        Text(storyHeadline, style: context.tt.headlineMedium?.copyWith(fontWeight: FontWeight.w800, height: 1.1)),
        const SizedBox(height: Space.x2),
        Text(storySub, style: context.tt.titleMedium?.copyWith(color: context.sp.muted, fontWeight: FontWeight.w500)),
      ]);
}

/// The big picture and the headline (the phone column).
class _Hero extends StatelessWidget {
  const _Hero();
  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const RobotPanel(shot: 'hero', radius: 32),
        const SizedBox(height: Space.x5),
        const _Headline(),
      ]);
}

class _Block extends StatelessWidget {
  const _Block({required this.title, this.subtitle, required this.child});
  final String title;
  final String? subtitle;
  final Widget child;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: Space.x8),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: context.tt.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
          if (subtitle != null) ...[const SizedBox(height: 2), Text(subtitle!, style: context.tt.bodySmall)],
          const SizedBox(height: Space.x3),
          child,
        ]),
      );
}

class _Beginning extends StatelessWidget {
  const _Beginning();
  @override
  Widget build(BuildContext context) => _Block(
        title: storyBeginTitle,
        child: Text(startupLine(AppBrand.publisherDisplayName, AppBrand.developerName),
            style: context.tt.bodyLarge?.copyWith(height: 1.45, color: context.sp.ink)),
      );
}

/// Three renders side by side (and the 3D viewer already in the app).
class _Gallery extends StatelessWidget {
  const _Gallery();
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: Space.x6),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          SizedBox(
            height: 150,
            child: Row(children: [
              for (final (i, s) in const ['close', 'front'].indexed) ...[
                if (i > 0) const SizedBox(width: Space.x3),
                Expanded(
                  child: ClipRRect(borderRadius: BorderRadius.circular(Radii.tile), child: RobotShot(shot: s, cacheWidth: 600)),
                ),
              ],
            ]),
          ),
          const SizedBox(height: Space.x3),
          PillButton(label: storyViewer, icon: Icons.view_in_ar_rounded, onTap: () => context.push('/viewer')),
        ]),
      );
}

class _Things extends StatelessWidget {
  const _Things();
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return _Block(
      title: storyThingsTitle,
      subtitle: storyThingsSub,
      child: Wrap(spacing: Space.x2, runSpacing: Space.x2, children: [
        for (final a in bodyAbilities)
          Container(
            key: ValueKey('ability.${a.action}'),
            padding: const EdgeInsets.fromLTRB(12, 9, 14, 9),
            decoration: BoxDecoration(
              color: a.inDevelopment ? Colors.transparent : p.card,
              borderRadius: BorderRadius.circular(100),
              border: Border.all(color: a.inDevelopment ? p.line : p.accent.withValues(alpha: 0.45), width: a.inDevelopment ? 1.5 : 1),
            ),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              Icon(_abilityIcons[a.action] ?? Icons.pets_rounded, size: 18, color: a.inDevelopment ? p.muted : p.accent),
              const SizedBox(width: 8),
              Flexible(child: Text(a.label, style: context.tt.labelLarge?.copyWith(color: a.inDevelopment ? p.muted : p.ink))),
              if (a.inDevelopment) ...[
                const SizedBox(width: 8),
                Text(storyInDevelopment, style: context.tt.labelSmall?.copyWith(color: p.accent, fontWeight: FontWeight.w800)),
              ],
            ]),
          ),
      ]),
    );
  }
}

class _Progress extends StatelessWidget {
  const _Progress();
  @override
  Widget build(BuildContext context) => const _Block(title: storyBuildTitle, child: BuildTimeline());
}

class _Founder extends ConsumerWidget {
  const _Founder();
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final note = ref.watch(founderNoteProvider).value;
    if (note == null || note.isEmpty) return const SizedBox.shrink();
    return _Block(
      title: storyFounderTitle,
      child: SpikeCard(
        key: const ValueKey('founderNote'),
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(Icons.format_quote_rounded, color: p.accent, size: 34),
          Text(note, style: context.tt.bodyLarge?.copyWith(height: 1.5)),
          const SizedBox(height: Space.x4),
          Row(children: [
            Container(
              width: 44,
              height: 44,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle),
              child: Text(AppBrand.developerName.characters.first, style: context.tt.titleLarge?.copyWith(color: p.accentInk, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: Space.x3),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(AppBrand.developerName, style: context.tt.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
                Text('Founder, ${AppBrand.publisherDisplayName}', style: context.tt.bodySmall),
              ]),
            ),
          ]),
        ]),
      ),
    );
  }
}
