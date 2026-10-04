import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/platform.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/messages.dart';
import '../../protocol/client.dart';
import '../../state/link.dart';
import '../connect/brain_needed.dart';
import '../../state/settings.dart';
import '../home/mode_switch.dart';
import '../../desktop/desktop_page.dart';
import 'memories_screen.dart';
import 'timers_state.dart';
import '../story/push_copy.dart';
import '../story/push_widgets.dart';

class LifeScreen extends ConsumerWidget {
  const LifeScreen({super.key});

  /// Alarms are kept by the computer's brain only. Paired but away from it: say so. Never paired (or
  /// still exploring): the one friendly ask (features/connect/brain_needed.dart) to link a computer.
  Future<bool> _ready(BuildContext context, WidgetRef ref) async {
    if (ref.read(brainClientProvider).away && ref.read(settingsProvider).endpoint != null) {
      Haptics.error();
      showToast(context, 'Alarms live on his home brain. Set them when you are home.', icon: Icons.home_rounded);
      return false;
    }
    if (!await ensureBrain(context, ref, reason: BrainReason.alarms) || !context.mounted) return false;
    if (ref.read(commandsProvider).connected) return true;
    Haptics.error();
    showToast(context, 'Spike is still waking up. Try again in a moment.', icon: Icons.hourglass_top_rounded);
    return false;
  }

  Future<void> _addAlarm(BuildContext context, WidgetRef ref) async {
    if (!await _ready(context, ref) || !context.mounted) return;
    final now = DateTime.now();
    final t = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: (now.hour + 1) % 24, minute: 0),
      helpText: 'Wake me up at',
    );
    if (t == null || !context.mounted) return;
    final at = nextAt(t.hour, t.minute, DateTime.now());
    final cmds = ref.read(commandsProvider);
    final sent = cmds.legacy ? cmds.say(alarmCommand(at, DateTime.now())) : cmds.setAlarm(at);
    if (sent) {
      Haptics.success();
      showToast(context, 'Alarm set for ${TimeOfDay.fromDateTime(at).format(context)} ${dayLabel(at, DateTime.now()).toLowerCase()}',
          icon: Icons.alarm_on_rounded);
    }
  }

  Future<void> _addReminder(BuildContext context, WidgetRef ref) async {
    if (!await _ready(context, ref) || !context.mounted) return;
    // desktop: a dialog in the middle of the window (a bottom sheet is a phone idiom)
    final r = AppPlatform.desktop
        ? await showDialog<(String, DateTime)>(
            context: context,
            builder: (_) => const Dialog(
              child: SizedBox(width: 460, child: Padding(padding: EdgeInsets.only(top: Space.x6), child: _ReminderSheet())),
            ),
          )
        : await showModalBottomSheet<(String, DateTime)>(
            context: context,
            useRootNavigator: true, // above the tab bar
            isScrollControlled: true,
            builder: (_) => const _ReminderSheet(),
          );
    if (r == null || !context.mounted) return;
    final cmds = ref.read(commandsProvider);
    final sent = cmds.legacy ? cmds.say(reminderCommand(r.$1, r.$2, DateTime.now())) : cmds.setReminder(r.$1, r.$2);
    if (sent) {
      Haptics.success();
      showToast(context, 'Reminder set', icon: Icons.notifications_active_rounded);
    }
  }

  /// Life on the desktop (DESIGN.md "Desktop > Proportions"): the alarms and reminders are the main
  /// pane (61.8 %): the list, then one-click quick sets for the most common ones, so an alarm is one
  /// click from the page; who is out and what he remembers (the full list with its forget buttons)
  /// share the side pane (38.2 %).
  Widget _desktop(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final settings = ref.watch(settingsProvider);
    final spike = ref.watch(spikeStateProvider);
    final timers = ref.watch(timersProvider);
    final connected = ref.watch(linkStatusProvider.select((s) => s.value?.isConnected ?? false));
    final name = settings.nameFor(spike.mode);
    Future<void> quick(bool alarm, Duration? inTime, TimeOfDay? at, String label) async {
      if (!await _ready(context, ref) || !context.mounted) return;
      final now = DateTime.now();
      final when = at != null ? nextAt(at.hour, at.minute, now) : now.add(inTime!);
      final cmds = ref.read(commandsProvider);
      final ok = alarm ? cmds.setAlarm(when) : cmds.setReminder(label, when);
      if (ok) {
        showToast(context, '${alarm ? 'Alarm' : 'Reminder'} set for ${TimeOfDay.fromDateTime(when).format(context)}',
            icon: Icons.check_rounded);
      }
    }

    return DesktopPage(
      title: 'Life with $name',
      trailing: Row(children: [
        PillButton(label: 'New alarm', icon: Icons.alarm_add_rounded, filled: true, onTap: () => _addAlarm(context, ref)),
        const SizedBox(width: Space.x3),
        PillButton(label: 'New reminder', icon: Icons.notification_add_rounded, onTap: () => _addReminder(context, ref)),
      ]),
      body: (context, room) {
        final m = context.metrics;
        final (main, side) = goldenSplit(room.maxWidth, m.gutter);
        return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          SizedBox(
            width: main,
            // the list, then the week filling exactly the room that is left (never less than 200 px: then it scrolls)
            child: CustomScrollView(slivers: [
              SliverList.list(children: [
              PaneTitle('Alarms and reminders', subtitle: '$name wakes you with yips, then barks, then jokes', first: true),
              if (timers.items.isEmpty)
                SpikeCard(
                  child: Row(children: [
                    Icon(Icons.nights_stay_rounded, color: p.muted),
                    const SizedBox(width: Space.x3),
                    Expanded(
                      child: Text(
                          connected && timers.synced
                              ? 'Nothing set. Pick one below, or just tell $name: "wake me up at seven".'
                              : 'Starting $name\'s brain...',
                          style: context.tt.bodyMedium),
                    ),
                  ]),
                )
              else
                for (final t in timers.items)
                  _TimerTile(
                    key: ValueKey(t.id),
                    t: t,
                    live: connected && timers.synced,
                    onCancel: () async {
                      if (!await _ready(context, ref)) return;
                      ref.read(commandsProvider).cancelTimer(t.id);
                    },
                  ),
              const PaneTitle('Quick set', subtitle: 'One click, and he keeps it'),
              // side by side from 560 px (each list's longest line, "Stand up and stretch in 1 h", fits one
              // line in 272); a narrower pane stacks them
              _QuickPair(
                side: main >= 560,
                wake: _QuickList(
                  icon: Icons.alarm_rounded,
                  title: 'Wake me up',
                  items: [
                    for (final (h, mi) in const [(6, 30), (7, 0), (7, 30), (8, 0)])
                      ('At ${TimeOfDay(hour: h, minute: mi).format(context)}',
                          () => quick(true, null, TimeOfDay(hour: h, minute: mi), 'Wake up')),
                  ],
                ),
                remind: _QuickList(
                  icon: Icons.notifications_active_rounded,
                  title: 'Remind me',
                  items: [
                    for (final (label, mins) in const [
                      ('Take a break', 25),
                      ('Drink some water', 30),
                      ('Stand up and stretch', 60),
                      ('Go to bed', 120),
                    ])
                      ('$label in ${mins < 60 ? '$mins min' : '${mins ~/ 60} h'}',
                          () => quick(false, Duration(minutes: mins), null, label.toLowerCase())),
                  ],
                ),
              ),
              ]),
              const SliverToBoxAdapter(child: PaneTitle('This week', subtitle: 'What rings when')),
              SliverFillRemaining(
                hasScrollBody: false,
                child: ConstrainedBox(constraints: const BoxConstraints(minHeight: 160), child: _Week(items: timers.items)),
              ),
            ]),
          ),
          SizedBox(width: m.gutter),
          SizedBox(
            width: side,
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              const PaneTitle('Who is out', first: true),
              ModeSwitch(
                mode: spike.mode,
                dogName: settings.dogName,
                catName: settings.catName,
                onChanged: (mo) {
                  ref.read(spikeStateProvider.notifier).localMode(mo);
                  ref.read(commandsProvider).setMode(mo, dogName: settings.dogName, catName: settings.catName);
                },
              ),
              PaneTitle('What $name remembers', subtitle: 'Kept on this computer; forget anything'),
              const Expanded(child: MemoriesScreen(embedded: true)),
            ]),
          ),
        ]);
      },
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (AppPlatform.desktop && context.isWide) return _desktop(context, ref);
    final p = context.sp;
    final settings = ref.watch(settingsProvider);
    final spike = ref.watch(spikeStateProvider);
    final timers = ref.watch(timersProvider);
    final away = ref.watch(linkStatusProvider.select((s) => s.value?.brain == BrainHost.phone && (s.value?.isConnected ?? false)));
    final connected = !away && ref.watch(linkStatusProvider.select((s) => s.value?.isConnected ?? false));
    final name = settings.nameFor(spike.mode);
    final bottom = MediaQuery.paddingOf(context).bottom + 100;

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: EdgeInsets.fromLTRB(20, 10, 20, bottom),
          children: [
            Text('Life with $name', style: context.tt.headlineSmall),
            const SectionHeader('Who is out', subtitle: 'Spike the pup or Spicy the cat'),
            ModeSwitch(
              mode: spike.mode,
              dogName: settings.dogName,
              catName: settings.catName,
              onChanged: (m) {
                Haptics.thud();
                ref.read(spikeStateProvider.notifier).localMode(m);
                ref.read(commandsProvider).setMode(m, dogName: settings.dogName, catName: settings.catName);
              },
            ),
            SectionHeader(
              'Alarms and reminders',
              subtitle: '$name wakes you with yips, then barks, then jokes',
            ),
            Row(children: [
              Expanded(child: PillButton(label: 'Alarm', icon: Icons.alarm_add_rounded, filled: true, onTap: () => _addAlarm(context, ref))),
              const SizedBox(width: 10),
              Expanded(child: PillButton(label: 'Reminder', icon: Icons.notification_add_rounded, onTap: () => _addReminder(context, ref))),
            ]),
            const SizedBox(height: 12),
            if (timers.items.isEmpty)
              SpikeCard(
                child: Row(children: [
                  Icon(Icons.nights_stay_rounded, color: p.muted),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      connected && timers.synced
                          ? 'Nothing set. You can also just tell $name: "wake me up at seven".'
                          : away
                              ? 'Alarms live on $name\'s home brain, so they ring even when your phone is off. Set them when you are home.'
                              : 'Connect $name to see his alarms. You can also just tell him: "wake me up at seven".',
                      style: context.tt.bodySmall,
                    ),
                  ),
                ]),
              )
            else ...[
              for (final (i, t) in timers.items.indexed)
                Entrance(
                  index: i,
                  key: ValueKey(t.id),
                  child: _TimerTile(
                    t: t,
                    live: connected && timers.synced,
                    onCancel: () async {
                      if (!await _ready(context, ref)) return;
                      Haptics.confirm();
                      ref.read(commandsProvider).cancelTimer(t.id);
                    },
                  ),
                ),
              if (!(connected && timers.synced))
                Padding(
                  padding: const EdgeInsets.only(left: 6, top: 2),
                  child: Text(away ? 'Last list from $name\'s home brain. It rings from there.' : 'Last list from $name. It updates when he is connected.',
                      style: context.tt.bodySmall),
                ),
            ],
            const SectionHeader('Memories and privacy'),
            SpikeCard(
              onTap: () => context.push('/memories'),
              child: Row(children: [
                Container(
                  width: 46,
                  height: 46,
                  decoration: BoxDecoration(color: Brand.tongue.withValues(alpha: 0.14), shape: BoxShape.circle),
                  child: const Icon(Icons.auto_stories_rounded, color: Brand.tongue),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('What $name remembers', style: context.tt.titleMedium),
                    Text('See it, add to it, or make him forget', style: context.tt.bodySmall),
                  ]),
                ),
                Icon(Icons.chevron_right_rounded, color: p.muted),
              ]),
            ),
            const SizedBox(height: 10),
            SpikeCard(
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Icon(Icons.lock_rounded, color: Brand.ok),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'Everything $name hears, sees and remembers stays on your laptop. Nothing goes to the cloud unless you turn it on there.',
                    style: context.tt.bodySmall?.copyWith(color: p.ink),
                  ),
                ),
              ]),
            ),
            if (pushVisible) ...[const SizedBox(height: 18), const RobotCard(tab: PushTab.life)],
          ],
        ),
      ),
    );
  }
}

/// The next seven days, one column each, with what rings on that day (daily ones every day).
class _Week extends StatelessWidget {
  const _Week({required this.items});
  final List<TimerItem> items;
  static const _days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    return SpikeCard(
      padding: const EdgeInsets.all(Space.x3),
      child: Stack(fit: StackFit.passthrough, children: [
      Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        for (var d = 0; d < 7; d++) ...[
          if (d > 0) VerticalDivider(width: Space.x3, color: p.line),
          Expanded(
            child: Builder(builder: (context) {
              final day = today.add(Duration(days: d));
              final on = [
                for (final t in items)
                  if (t.repeat == 'daily' || (t.dueAt.year == day.year && t.dueAt.month == day.month && t.dueAt.day == day.day)) t,
              ]..sort((a, b) => (a.dueAt.hour * 60 + a.dueAt.minute).compareTo(b.dueAt.hour * 60 + b.dueAt.minute));
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(d == 0 ? 'Today' : _days[day.weekday - 1],
                    style: context.tt.labelLarge?.copyWith(color: d == 0 ? p.accent : p.ink, fontWeight: FontWeight.w800)),
                Text('${day.day}', style: context.tt.bodySmall),
                const SizedBox(height: Space.x2),
                for (final t in on.take(4))
                  Padding(
                    padding: const EdgeInsets.only(bottom: Space.x1),
                    child: Text(
                      '${TimeOfDay.fromDateTime(t.dueAt).format(context)} ${t.kind == 'alarm' ? 'alarm' : t.label}',
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: context.tt.bodySmall?.copyWith(color: p.ink),
                    ),
                  ),
              ]);
            }),
          ),
        ],
      ]),
      // an empty week says so in its middle, not in a corner
      if (items.isEmpty)
        Positioned.fill(
          top: 48,
          child: Center(
            // on a plate of the card's colour, so the day lines stop at its edge instead of crossing the words
            child: DecoratedBox(
              decoration: BoxDecoration(color: p.card, borderRadius: BorderRadius.circular(Radii.control)),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.x4, vertical: Space.x2),
                child: Text('Nothing rings this week. What you set shows up here.',
                    textAlign: TextAlign.center, style: context.tt.bodyMedium?.copyWith(color: p.muted)),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

/// The two quick-set cards: side by side (equal heights), or stacked in a narrow pane.
class _QuickPair extends StatelessWidget {
  const _QuickPair({required this.side, required this.wake, required this.remind});
  final bool side;
  final Widget wake, remind;
  @override
  Widget build(BuildContext context) => side
      ? IntrinsicHeight(
          child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Expanded(child: wake),
            const SizedBox(width: Space.x4),
            Expanded(child: remind),
          ]),
        )
      : Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [wake, const SizedBox(height: Space.x4), remind]);
}

/// A quick-set card: four one-click rows (desktop Life).
class _QuickList extends StatelessWidget {
  const _QuickList({required this.icon, required this.title, required this.items});
  final IconData icon;
  final String title;
  final List<(String, VoidCallback)> items;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return SpikeCard(
      padding: const EdgeInsets.fromLTRB(Space.x4, Space.x4, Space.x2, Space.x2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(icon, color: p.accent, size: 20),
          const SizedBox(width: Space.x2),
          Text(title, style: context.tt.titleMedium),
        ]),
        const SizedBox(height: Space.x2),
        for (final (label, onTap) in items)
          Pressable(
            haptic: false,
            scale: 0.98,
            onTap: onTap,
            semanticLabel: label,
            child: SizedBox(
              height: 44,
              child: Row(children: [
                Expanded(child: Text(label, style: context.tt.bodyMedium)),
                Icon(Icons.add_circle_outline_rounded, color: p.accent, size: 20),
                const SizedBox(width: Space.x2),
              ]),
            ),
          ),
      ]),
    );
  }
}

class _TimerTile extends StatelessWidget {
  const _TimerTile({super.key, required this.t, required this.live, required this.onCancel});
  final TimerItem t;
  final bool live;
  final VoidCallback onCancel;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final now = DateTime.now();
    final tod = TimeOfDay.fromDateTime(t.dueAt).format(context);
    final ringing = t.state == 'ringing';
    final what = t.kind == 'alarm' ? (t.label.isEmpty || t.label == 'Wake up' ? 'Alarm' : t.label) : t.label;
    final when = t.repeat == 'daily' ? 'Every day' : dayLabel(t.dueAt, now);
    final snoozed = t.state == 'snoozed' ? ' · snoozed' : '';
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: SpikeCard(
        padding: const EdgeInsets.fromLTRB(18, 12, 8, 12),
        child: Row(children: [
          Icon(
            ringing ? Icons.alarm_on_rounded : (t.kind == 'alarm' ? Icons.alarm_rounded : Icons.notifications_active_rounded),
            color: ringing ? Brand.tongue : (live ? p.accent : p.muted),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(tod, style: context.tt.headlineSmall?.copyWith(color: live ? p.ink : p.muted, fontFeatures: const [FontFeature.tabularFigures()])),
              Text('$when · $what$snoozed', maxLines: 2, overflow: TextOverflow.ellipsis, style: context.tt.bodySmall),
            ]),
          ),
          if (live)
            IconButton(
              tooltip: ringing ? 'Stop' : 'Cancel',
              onPressed: onCancel,
              icon: Icon(ringing ? Icons.alarm_off_rounded : Icons.close_rounded, color: ringing ? Brand.tongue : p.muted),
            ),
        ]),
      ),
    );
  }
}

class _ReminderSheet extends StatefulWidget {
  const _ReminderSheet();
  @override
  State<_ReminderSheet> createState() => _ReminderSheetState();
}

class _ReminderSheetState extends State<_ReminderSheet> {
  final _what = TextEditingController();
  DateTime _at = DateTime.now().add(const Duration(minutes: 30));
  @override
  void dispose() {
    _what.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final inset = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + inset + MediaQuery.paddingOf(context).bottom),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('Remind me to...', style: context.tt.titleLarge),
        const SizedBox(height: 12),
        TextField(controller: _what, autofocus: true, textCapitalization: TextCapitalization.sentences, decoration: const InputDecoration(hintText: 'drink some water')),
        const SizedBox(height: 12),
        PillButton(
          label: 'At ${TimeOfDay.fromDateTime(_at).format(context)}${_at.day != DateTime.now().day ? ' tomorrow' : ''}',
          icon: Icons.schedule_rounded,
          onTap: () async {
            final t = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(_at));
            if (t == null) return;
            final now = DateTime.now();
            var at = DateTime(now.year, now.month, now.day, t.hour, t.minute);
            if (!at.isAfter(now)) at = at.add(const Duration(days: 1));
            setState(() => _at = at);
          },
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52), shape: const StadiumBorder()),
            onPressed: () {
              final w = _what.text.trim();
              if (w.isEmpty) {
                Haptics.error();
                return;
              }
              Navigator.pop(context, (w, _at));
            },
            child: const Text('Set reminder'),
          ),
        ),
      ]),
    );
  }
}
