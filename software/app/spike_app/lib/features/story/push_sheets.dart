/// The two sheets of the robot push, and the build progress they and the story page share.
///
///  * "Imagine this on your desk": the FIRST time someone uses something the body will do (a trick, a
///    wag, the drive stick, sleep), one short sheet, once per feature, ever ([maybePeek]).
///  * The 3-day reminder: on app open, when three days have passed ([ReminderHost]).
///
/// Both are bottom sheets that swipe away, appear after the thing the person tapped has already
/// happened, never during a drag, and never stack on each other. In-app only: no notifications, no
/// permissions. Phone-only for now (push_widgets.dart [pushVisible]).
library;

import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/haptics.dart';
import '../../core/theme.dart';
import 'push_copy.dart';
import 'push_state.dart';
import 'push_widgets.dart';

// ---------------------------------------------------------------- build progress

typedef BuildStep = ({String title, String text, String state});

/// The five build steps: a bundled copy of docs/data/site.json "robotBuild" (assets/story/robot_build.json,
/// no network). To update it, copy the new "robotBuild" list over; states are done / now / next.
final buildStepsProvider = FutureProvider<List<BuildStep>>((ref) async {
  final j = jsonDecode(await rootBundle.loadString('assets/story/robot_build.json')) as Map<String, dynamic>;
  return [
    for (final s in (j['robotBuild'] as List).cast<Map<String, dynamic>>())
      (title: s['title'] as String, text: s['text'] as String, state: s['state'] as String),
  ];
});

/// The full timeline (the story page).
class BuildTimeline extends ConsumerWidget {
  const BuildTimeline({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final steps = ref.watch(buildStepsProvider).value ?? const <BuildStep>[];
    final p = context.sp;
    return Column(children: [
      for (final (i, s) in steps.indexed)
        IntrinsicHeight(
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            SizedBox(
              width: 36,
              child: Column(children: [
                _Dot(state: s.state),
                if (i < steps.length - 1)
                  Expanded(child: Container(width: 2, margin: const EdgeInsets.symmetric(vertical: 3), color: s.state == 'done' ? p.accent : p.line)),
              ]),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Flexible(child: Text(s.title, style: context.tt.titleSmall?.copyWith(fontWeight: FontWeight.w800))),
                    if (s.state == 'now') ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(100)),
                        child: Text('Happening now', style: context.tt.labelSmall?.copyWith(color: p.accentInk, fontWeight: FontWeight.w800)),
                      ),
                    ],
                  ]),
                  const SizedBox(height: 2),
                  Text(s.text, style: context.tt.bodySmall?.copyWith(color: s.state == 'next' ? p.muted : p.ink, height: 1.3)),
                ]),
              ),
            ),
          ]),
        ),
    ]);
  }
}

class _Dot extends StatelessWidget {
  const _Dot({required this.state});
  final String state;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return switch (state) {
      'done' => Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle),
          child: Icon(Icons.check_rounded, size: 18, color: p.accentInk),
        ),
      'now' => Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: p.accent, width: 3), color: p.accent.withValues(alpha: 0.18)),
          child: Center(child: Container(width: 10, height: 10, decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle))),
        ),
      _ => Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: p.line, width: 2)),
        ),
    };
  }
}

/// Five segments and the current step in a line (the reminder).
class BuildMini extends ConsumerWidget {
  const BuildMini({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final steps = ref.watch(buildStepsProvider).value ?? const <BuildStep>[];
    if (steps.isEmpty) return const SizedBox(height: 56);
    final p = context.sp;
    var now = steps.indexWhere((s) => s.state == 'now');
    if (now < 0) now = steps.lastIndexWhere((s) => s.state == 'done') + 1;
    now = now.clamp(0, steps.length - 1);
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        for (final (i, s) in steps.indexed) ...[
          if (i > 0) const SizedBox(width: 5),
          Expanded(
            child: Container(
              height: 8,
              decoration: BoxDecoration(
                borderRadius: BorderRadius.circular(100),
                color: s.state == 'done' ? p.accent : (s.state == 'now' ? p.accent.withValues(alpha: 0.5) : p.line),
              ),
            ),
          ),
        ],
      ]),
      const SizedBox(height: 10),
      Text('Step ${now + 1} of ${steps.length}: ${steps[now].title}', style: context.tt.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
      const SizedBox(height: 2),
      Text(steps[now].text, style: context.tt.bodySmall?.copyWith(height: 1.3)),
    ]);
  }
}

// ---------------------------------------------------------------- sheets

// the context that has a sheet open right now (one at a time); a stale one (its screen is gone) does not count
BuildContext? _sheetFor;

/// Tests: forget a sheet whose screen was torn down without closing it.
@visibleForTesting
void resetPushSheets() => _sheetFor = null;

Future<void> _showSheet(BuildContext context, Widget Function(BuildContext) builder) async {
  if (_sheetFor?.mounted ?? false) return;
  _sheetFor = context;
  try {
    await showModalBottomSheet<void>(
      context: context,
      useRootNavigator: true, // above the tab bar
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (c) => SingleChildScrollView(child: builder(c)),
    );
  } finally {
    _sheetFor = null; // one sheet at a time, so this is always the one that just closed
  }
}

/// Call right AFTER something the body will do has happened. Shows the peek the first time for that
/// feature and never again (the flag is saved before the sheet appears, so even a swipe-away counts).
/// Never blocks: the sheet comes up a moment later and swipes away.
void maybePeek(BuildContext context, WidgetRef ref, PeekFeature feature) {
  if (!pushVisible) return;
  if (!ref.read(pushProvider.notifier).takePeek(feature)) return;
  Future<void>.delayed(const Duration(milliseconds: 700), () {
    if (context.mounted) _showSheet(context, (_) => PeekPanel(feature: feature));
  });
}

class PeekPanel extends StatelessWidget {
  const PeekPanel({super.key, required this.feature});
  final PeekFeature feature;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        RobotPanel(
          shot: 'close',
          child: Align(
            alignment: Alignment.topLeft,
            child: Padding(padding: const EdgeInsets.all(12), child: _Overline(cardOverline, onImage: true)),
          ),
        ),
        const SizedBox(height: 18),
        Text(peekHeadline, style: context.tt.headlineSmall?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Text(peekLines[feature]!, style: context.tt.bodyLarge?.copyWith(color: p.ink, height: 1.35)),
        const SizedBox(height: 18),
        const WaitlistButton(dense: true),
        const SizedBox(height: 4),
        Wrap(alignment: WrapAlignment.center, children: [
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text(laterLabel)),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              openStory(context);
            },
            child: const Text(storyLink),
          ),
        ]),
      ]),
    );
  }
}

class _Overline extends StatelessWidget {
  const _Overline(this.text, {this.onImage = false});
  final String text;
  final bool onImage;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(color: Brand.chocolate.withValues(alpha: 0.85), borderRadius: BorderRadius.circular(100)),
        child: Text(text, style: context.tt.labelSmall?.copyWith(color: Brand.cream, fontWeight: FontWeight.w800, letterSpacing: 1.2)),
      );
}

/// On app open: the 3-day reminder (build progress and the main button). Wrap the phone's app shell in
/// this. Once per app launch it asks [PushNotifier.takeReminder] (the clock is in local preferences).
class ReminderHost extends ConsumerStatefulWidget {
  const ReminderHost({super.key, required this.child, this.delay = const Duration(milliseconds: 2500)});
  final Widget child;
  final Duration delay;
  @override
  ConsumerState<ReminderHost> createState() => _ReminderHostState();
}

class _ReminderHostState extends ConsumerState<ReminderHost> {
  @override
  void initState() {
    super.initState();
    if (!pushVisible) return;
    // decided right after the first frame (state may not change while the tree builds); on the very first
    // open this only starts the clock. Shown a moment later, after the app has settled.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !ref.read(pushProvider.notifier).takeReminder()) return;
      ref.read(buildStepsProvider); // start reading the steps now, so the sheet opens complete
      Future<void>.delayed(widget.delay, () {
        if (mounted) _showSheet(context, (_) => const ReminderPanel());
      });
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

class ReminderPanel extends StatelessWidget {
  const ReminderPanel({super.key});
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          SizedBox(
            width: 84,
            height: 84,
            child: ClipRRect(borderRadius: BorderRadius.circular(22), child: const RobotShot(shot: 'hero', cacheWidth: 320)),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const _Overline(cardOverline),
              const SizedBox(height: 8),
              Text(reminderTitle, style: context.tt.titleMedium?.copyWith(fontWeight: FontWeight.w800, height: 1.2)),
              Text(reminderLine, style: context.tt.bodySmall),
            ]),
          ),
        ]),
        const SizedBox(height: 18),
        const BuildMini(),
        const SizedBox(height: 20),
        const WaitlistButton(dense: true),
        const SizedBox(height: 4),
        Wrap(alignment: WrapAlignment.center, children: [
          TextButton(
            onPressed: () {
              Haptics.tick();
              Navigator.of(context).pop();
            },
            child: const Text(laterLabel),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(context).pop();
              openStory(context);
            },
            child: const Text(storyLink),
          ),
        ]),
      ]),
    );
  }
}
