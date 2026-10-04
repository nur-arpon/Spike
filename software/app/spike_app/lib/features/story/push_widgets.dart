/// The pieces of the robot push (software/app/DESIGN.md "Robot push"): the render image, the main
/// button, the preview banner and the robot card. The sheets are in push_sheets.dart and the page in
/// story_screen.dart. All unsolicited pieces (banner, cards, sheets) are phone-only for now
/// ([pushVisible]); the story page itself works on every size.
library;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/haptics.dart';
import '../../core/motion.dart';
import '../../core/platform.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import 'push_copy.dart';
import 'push_state.dart';

/// The banner, cards and sheets show on the phone app (the Windows app gets them in its next update,
/// with a layout of its own).
bool get pushVisible => AppPlatform.phone;

void openStory(BuildContext context) {
  Haptics.tap();
  context.push('/story');
}

/// One of the bundled website renders (assets/robot/, about 40 KB each as webp).
/// [shot]: 'hero' (the whole robot, square), 'close' (head and chest, 4:3) or 'front' (4:3).
/// Light and dark pictures differ only in the backdrop, so the dark one follows the theme.
class RobotShot extends StatelessWidget {
  const RobotShot({super.key, this.shot = 'hero', this.fit = BoxFit.cover, this.alignment = Alignment.center, this.cacheWidth = 900});
  final String shot;
  final BoxFit fit;
  final Alignment alignment;
  final int cacheWidth;

  static const aspects = {'hero': 1.0, 'close': 4 / 3, 'front': 4 / 3};

  @override
  Widget build(BuildContext context) {
    final dark = context.isDark && shot != 'front';
    return Image.asset(
      'assets/robot/$shot${dark ? '-dark' : ''}.webp',
      fit: fit,
      alignment: alignment,
      cacheWidth: cacheWidth,
      filterQuality: FilterQuality.medium,
      excludeFromSemantics: true,
      errorBuilder: (_, _, _) => ColoredBox(color: Brand.cream, child: Icon(Icons.pets_rounded, color: context.sp.accent, size: 40)),
    );
  }
}

/// The picture panel: a render in rounded corners with a soft shadow.
class RobotPanel extends StatelessWidget {
  const RobotPanel({super.key, this.shot = 'close', this.radius = 28, this.child});
  final String shot;
  final double radius;
  final Widget? child;
  @override
  Widget build(BuildContext context) => Semantics(
        label: 'A render of Spike\'s robot body',
        image: true,
        child: Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(radius),
            boxShadow: [BoxShadow(color: context.sp.shadow.withValues(alpha: context.isDark ? 0.5 : 0.2), blurRadius: 30, offset: const Offset(0, 14))],
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(radius),
            child: AspectRatio(
              aspectRatio: RobotShot.aspects[shot] ?? 1,
              child: Stack(fit: StackFit.expand, children: [RobotShot(shot: shot), ?child]),
            ),
          ),
        ),
      );
}

/// The main button: "I want one - join the waitlist" (opens the Google Form in the browser) or, while
/// there is no form yet, "Follow the build" (the website's robot page).
class WaitlistButton extends ConsumerWidget {
  const WaitlistButton({super.key, this.showNote = true, this.dense = false});
  final bool showNote;
  final bool dense;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cta = ctaFor(ref.watch(waitlistUrlProvider));
    final p = context.sp;
    Future<void> open() async {
      Haptics.confirm();
      var ok = false;
      try {
        ok = await ref.read(urlOpenerProvider)(cta.uri);
      } catch (_) {}
      if (!ok && context.mounted) showToast(context, 'Open ${cta.uri} in your browser', icon: Icons.link_rounded);
    }

    return Column(mainAxisSize: MainAxisSize.min, children: [
      Pressable(
        onTap: open,
        semanticLabel: cta.label,
        child: Container(
          width: double.infinity,
          padding: EdgeInsets.symmetric(horizontal: 22, vertical: dense ? 14 : 18),
          decoration: BoxDecoration(
            gradient: LinearGradient(colors: [p.accent, Color.lerp(p.accent, Brand.tongue, 0.35)!]),
            borderRadius: BorderRadius.circular(100),
            boxShadow: [BoxShadow(color: p.accent.withValues(alpha: 0.45), blurRadius: 22, offset: const Offset(0, 8))],
          ),
          child: Row(mainAxisAlignment: MainAxisAlignment.center, mainAxisSize: MainAxisSize.min, children: [
            Icon(cta.waitlist ? Icons.favorite_rounded : Icons.explore_rounded, color: p.accentInk, size: 20),
            const SizedBox(width: 10),
            Flexible(
              child: Text(cta.label,
                  maxLines: 2,
                  textAlign: TextAlign.center,
                  overflow: TextOverflow.ellipsis,
                  style: context.tt.titleMedium?.copyWith(color: p.accentInk, fontWeight: FontWeight.w800)),
            ),
          ]),
        ),
      ),
      if (showNote) ...[
        const SizedBox(height: 8),
        Text(cta.note, textAlign: TextAlign.center, style: context.tt.bodySmall?.copyWith(color: p.muted)),
      ],
    ]);
  }
}

// ---------------------------------------------------------------- the banner on Home

/// "Preview: Spike's robot body is on the way": a dark chocolate card with a glow, near the top of Home.
class PreviewBanner extends StatelessWidget {
  const PreviewBanner({super.key});
  @override
  Widget build(BuildContext context) {
    if (!pushVisible) return const SizedBox.shrink();
    return Pressable(
      onTap: () => openStory(context),
      scale: 0.97,
      semanticLabel: bannerTitle,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(26),
          gradient: const LinearGradient(colors: [Color(0xFF5A3F2F), Brand.chocolate], begin: Alignment.topLeft, end: Alignment.bottomRight),
          border: Border.all(color: Brand.brown.withValues(alpha: 0.55)),
          boxShadow: [BoxShadow(color: Brand.caramel.withValues(alpha: context.isDark ? 0.25 : 0.32), blurRadius: 26, offset: const Offset(0, 10))],
        ),
        clipBehavior: Clip.antiAlias,
        child: Stack(children: [
          Positioned(
            right: -30,
            top: -40,
            child: Container(
              width: 140,
              height: 140,
              decoration: BoxDecoration(shape: BoxShape.circle, color: Brand.brown.withValues(alpha: 0.22)),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(10, 10, 14, 10),
            child: Row(children: [
              Container(
                width: 60,
                height: 60,
                decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: Brand.cream.withValues(alpha: 0.7), width: 2)),
                child: ClipOval(child: Container(color: Brand.cream, child: const RobotShot(shot: 'close', alignment: Alignment(0, -0.2), cacheWidth: 240))),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(bannerTitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: context.tt.titleSmall?.copyWith(color: Brand.cream, fontWeight: FontWeight.w800, height: 1.2)),
                  const SizedBox(height: 3),
                  Text(bannerLine,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: context.tt.bodySmall?.copyWith(color: Brand.cream.withValues(alpha: 0.78), height: 1.25)),
                ]),
              ),
              const SizedBox(width: 8),
              Container(
                width: 34,
                height: 34,
                decoration: const BoxDecoration(shape: BoxShape.circle, color: Brand.brown),
                child: const Icon(Icons.arrow_forward_rounded, color: Brand.chocolate, size: 20),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

// ---------------------------------------------------------------- the card on each tab

/// A compact robot card for the end of a tab (copy per tab in push_copy.dart). Tapping opens the story.
class RobotCard extends StatelessWidget {
  const RobotCard({super.key, required this.tab});
  final PushTab tab;
  @override
  Widget build(BuildContext context) {
    if (!pushVisible) return const SizedBox.shrink();
    final p = context.sp;
    final (title, line) = tabCards[tab]!;
    return SpikeCard(
      key: ValueKey('robotCard.${tab.name}'),
      onTap: () => openStory(context),
      padding: const EdgeInsets.all(12),
      gradient: LinearGradient(
        colors: context.isDark ? [const Color(0xFF3A2A1F), const Color(0xFF231A14)] : [Brand.cream, const Color(0xFFF8EBDA)],
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
      ),
      child: Row(children: [
        SizedBox(
          width: 88,
          height: 88,
          child: ClipRRect(borderRadius: BorderRadius.circular(20), child: const RobotShot(shot: 'hero', cacheWidth: 320)),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(cardOverline, style: context.tt.labelSmall?.copyWith(color: p.accent, fontWeight: FontWeight.w800, letterSpacing: 1.2)),
            const SizedBox(height: 2),
            Text(title, maxLines: 2, overflow: TextOverflow.ellipsis, style: context.tt.titleSmall?.copyWith(fontWeight: FontWeight.w800, height: 1.2)),
            const SizedBox(height: 2),
            Text(line, maxLines: 2, overflow: TextOverflow.ellipsis, style: context.tt.bodySmall?.copyWith(height: 1.25)),
          ]),
        ),
        Icon(Icons.chevron_right_rounded, color: p.muted),
      ]),
    );
  }
}
