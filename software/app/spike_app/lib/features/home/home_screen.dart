import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';

import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/platform.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/client.dart';
import '../../protocol/names.dart';
import '../../away/ai/offline_brain.dart';
import '../../state/away.dart';
import '../../state/brain_ready.dart';
import '../connect/brain_needed.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import '../face/face_view.dart';
import '../story/push_copy.dart';
import '../story/push_sheets.dart';
import '../story/push_widgets.dart';
import 'home_desktop.dart';
import 'mode_switch.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});
  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  final _face = FaceController();
  bool _toldOffline = false;

  @override
  void dispose() {
    _face.dispose();
    super.dispose();
  }

  bool get _connected => ref.read(brainClientProvider).current.isConnected;

  void _offlineNote() {
    // exploring with no brain yet: the face answering by itself is plain to see, and anything that needs
    // his brain asks for it (features/connect/brain_needed.dart), so no extra note then
    if (_connected || _toldOffline || !brainReadyNow(ref)) return;
    _toldOffline = true;
    showToast(context, 'Spike isn\'t connected, so only the phone face reacts', icon: Icons.wifi_off_rounded);
  }

  Future<void> _quick(String what) async {
    final cmds = ref.read(commandsProvider);
    switch (what) {
      case 'pat':
        Haptics.purr();
        _face.pat();
        cmds.pat();
      case 'boop':
        Haptics.confirm();
        _face.boop();
        cmds.boop();
      case 'treat':
        Haptics.success();
        // the body cannot beg (core/capabilities.dart): a happy wag and a delighted face instead
        _face.setMood('delight');
        _face.playAction('tailWagDance');
        // the face reacted by itself; the spoken treat needs his brain
        if (!await ensureBrain(context, ref, reason: BrainReason.talk) || !mounted) return;
        if (_connected) cmds.action('tailWagDance', quiet: true);
        cmds.say('here is a treat for you, good ${ref.read(spikeStateProvider).mode == 'cat' ? 'girl' : 'boy'}');
        if (mounted) maybePeek(context, ref, PeekFeature.wag); // first time only, ever (features/story/)
      case 'play':
        Haptics.confirm();
        if (!_connected) _face.playAction('playBow');
        if (!await ensureBrain(context, ref, reason: BrainReason.talk) || !mounted) return;
        cmds.say("let's play rock paper scissors");
      case 'sleep':
        Haptics.confirm();
        if (!_connected) _face.playAction('fallAsleep');
        cmds.sleep(); // v1.2 action fallAsleep (words on an older brain)
        maybePeek(context, ref, PeekFeature.sleep); // first time only, ever (features/story/)
    }
    _offlineNote();
  }

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 5) return 'Up late';
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    if (h < 22) return 'Good evening';
    return 'Good night';
  }

  @override
  Widget build(BuildContext context) {
    // the desktop from the medium size class up: its own composition (home_desktop.dart)
    if (AppPlatform.desktop && context.isWide) return HomeDesktop(face: _face, onQuick: _quick, greeting: _greeting());
    final p = context.sp;
    final link = ref.watch(linkStatusProvider).value ?? const LinkStatus();
    final spike = ref.watch(spikeStateProvider);
    final settings = ref.watch(settingsProvider);
    final away = ref.watch(awayProvider);
    final name = settings.nameFor(spike.mode);
    final bottom = MediaQuery.paddingOf(context).bottom + 96;

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: CustomScrollView(
          slivers: [
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 10, 12, 0),
              sliver: SliverToBoxAdapter(
                child: Row(children: [
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(_greeting(), style: context.tt.bodyMedium?.copyWith(color: p.muted, fontWeight: FontWeight.w600)),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 380),
                        transitionBuilder: (c, a) => FadeTransition(
                            opacity: a,
                            child: SlideTransition(position: Tween(begin: const Offset(0, 0.3), end: Offset.zero).animate(a), child: c)),
                        child: Text(name, key: ValueKey(name), style: context.tt.displaySmall),
                      ),
                    ]),
                  ),
                  _RoundIcon(icon: Icons.view_in_ar_rounded, label: '3D view', onTap: () => context.push('/viewer')),
                  const SizedBox(width: 6),
                  _RoundIcon(icon: Icons.tune_rounded, label: 'Settings', onTap: () => context.push('/settings')),
                ]),
              ),
            ),
            // the robot preview banner (features/story/): a classy line near the top, opens the story
            if (pushVisible)
              const SliverPadding(
                padding: EdgeInsets.fromLTRB(20, 12, 20, 0),
                sliver: SliverToBoxAdapter(child: PreviewBanner()),
              ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
              sliver: SliverToBoxAdapter(
                child: Wrap(spacing: 8, runSpacing: 8, children: [
                  LinkPill(status: link),
                  StatusPill(label: moodLabel(spike.mood), icon: Icons.mood_rounded),
                  if (away.away) _AwayRobotPill(away: away, name: name, robotPaired: settings.robotId != null),
                  if (link.isConnected && spike.robotOnline)
                    StatusPill(
                      label: spike.battery == null ? 'Battery -' : '${spike.battery!.round()}%${spike.charging ? ' charging' : ''}',
                      icon: spike.charging ? Icons.battery_charging_full_rounded : batteryIcon(spike.battery),
                    )
                  else if (link.isConnected && !away.away)
                    StatusPill(
                      label: spike.simulatorOnly ? 'Simulator' : 'Robot not connected',
                      icon: spike.simulatorOnly ? Icons.computer_rounded : Icons.link_off_rounded,
                    ),
                  if (link.isConnected && spike.llm == 'warming')
                    StatusPill(label: "Waking $name's brain\u2026", dot: Brand.warn, pulse: true),
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
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
              sliver: SliverToBoxAdapter(
                child: FaceCard(face: _face, caption: spike.caption, alarm: spike.alarmRinging),
              ),
            ),
            if (spike.alarmRinging)
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
                sliver: SliverToBoxAdapter(child: AlarmBar(label: spike.alarmLabel)),
              ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
              sliver: SliverToBoxAdapter(
                child: Row(children: [
                  for (final (i, q) in const [
                    (Icons.back_hand_rounded, 'Pat', 'pat'),
                    (Icons.touch_app_rounded, 'Boop', 'boop'),
                    (Icons.cookie_rounded, 'Treat', 'treat'),
                    (Icons.sports_baseball_rounded, 'Play', 'play'),
                    (Icons.bedtime_rounded, 'Sleep', 'sleep'),
                  ].indexed) ...[
                    if (i > 0) const SizedBox(width: 8),
                    Expanded(child: Entrance(index: i, child: ActionTile(icon: q.$1, label: q.$2, onTap: () => _quick(q.$3)))),
                  ],
                ]),
              ),
            ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
              sliver: SliverToBoxAdapter(
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
              ),
            ),
            // exploring with no brain yet: one gentle card that opens the same ask the first brain-needing action does
            if (!AppPlatform.desktop && !ref.watch(brainReadyProvider))
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                sliver: SliverToBoxAdapter(
                  child: SpikeCard(
                    onTap: () => ensureBrain(context, ref),
                    child: Row(children: [
                      Icon(Icons.auto_awesome_rounded, color: p.accent, size: 30), // a sparkle: the old head-with-"?" read like an error
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('Give $name his brain', style: context.tt.titleMedium),
                          Text('A free Gemini key, or the code on your computer', style: context.tt.bodySmall),
                        ]),
                      ),
                      Icon(Icons.chevron_right_rounded, color: p.muted),
                    ]),
                  ),
                ),
              )
            else if (away.away && (settings.robotId == null || (!away.hasKey && ref.watch(offlineStatusProvider).value?.state != OfflineState.installed)))
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                sliver: SliverToBoxAdapter(
                  child: SpikeCard(
                    onTap: () => context.push(settings.robotId == null ? '/connect' : '/settings'),
                    child: Row(children: [
                      Icon(settings.robotId == null ? Icons.bluetooth_searching_rounded : Icons.psychology_rounded, color: p.accent, size: 30),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(settings.robotId == null ? 'Bring along' : 'Give his thinking brain',
                              style: context.tt.titleMedium),
                          Text(
                              settings.robotId == null
                                  ? 'Pair the robot over Bluetooth for when you are out'
                                  : 'Paste a free Gemini key, or download the offline brain',
                              style: context.tt.bodySmall),
                        ]),
                      ),
                      Icon(Icons.chevron_right_rounded, color: p.muted),
                    ]),
                  ),
                ),
              ),
            if (!link.isConnected)
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 0),
                sliver: SliverToBoxAdapter(
                  child: SpikeCard(
                    onTap: () => context.push('/connect'),
                    child: Row(children: [
                      Icon(Icons.wifi_find_rounded, color: p.accent, size: 30),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(link.isTrying ? 'Reconnecting to $name...' : 'Connect to $name', style: context.tt.titleMedium),
                          Text(link.isTrying ? (link.error ?? 'Trying again') : 'Find his brain on your Wi-Fi',
                              style: context.tt.bodySmall),
                        ]),
                      ),
                      Icon(Icons.chevron_right_rounded, color: p.muted),
                    ]),
                  ),
                ),
              ),
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(20, 14, 20, 0),
              sliver: SliverToBoxAdapter(
                child: SpikeCard(
                  onTap: () => context.push('/viewer'),
                  gradient: LinearGradient(
                    colors: context.isDark ? [const Color(0xFF3A2A1F), const Color(0xFF231A14)] : [Brand.cream, const Color(0xFFF8EBDA)],
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                  ),
                  child: Row(children: [
                    Hero(tag: 'spike-logo', child: SvgPicture.asset('assets/icon/spike_icon.svg', width: 56, height: 56)),
                    const SizedBox(width: 16),
                    Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('Meet $name in 3D', style: context.tt.titleMedium),
                        Text('Spin him around, try colours and screen states', style: context.tt.bodySmall),
                      ]),
                    ),
                    Icon(Icons.view_in_ar_rounded, color: p.accent),
                  ]),
                ),
              ),
            ),
            if (pushVisible)
              const SliverPadding(
                padding: EdgeInsets.fromLTRB(20, 14, 20, 0),
                sliver: SliverToBoxAdapter(child: RobotCard(tab: PushTab.home)),
              ),
            SliverToBoxAdapter(child: SizedBox(height: bottom)),
          ],
        ),
      ),
    );
  }
}

IconData batteryIcon(double? pct) => switch (pct) {
      null => Icons.battery_unknown_rounded,
      < 15 => Icons.battery_alert_rounded,
      < 40 => Icons.battery_2_bar_rounded,
      < 75 => Icons.battery_4_bar_rounded,
      _ => Icons.battery_full_rounded,
    };

class _RoundIcon extends StatelessWidget {
  const _RoundIcon({required this.icon, required this.label, required this.onTap});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => Pressable(
        onTap: onTap,
        semanticLabel: label,
        scale: 0.85,
        child: Container(
          width: 46,
          height: 46,
          decoration: BoxDecoration(color: context.sp.card, shape: BoxShape.circle, border: Border.all(color: context.sp.line)),
          child: Icon(icon, color: context.sp.ink, size: 22),
        ),
      );
}

class LinkPill extends ConsumerWidget {
  const LinkPill({super.key, required this.status});
  final LinkStatus status;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // exploring: nothing is linked and no key is saved yet (onboarding v2)
    if (!ref.watch(brainReadyProvider)) {
      return StatusPill(label: 'Exploring', icon: Icons.explore_rounded, dot: context.sp.muted);
    }
    if (status.brain == BrainHost.phone && status.isConnected) {
      return const StatusPill(label: 'Away · phone brain', icon: Icons.smartphone_rounded, dot: Brand.ok);
    }
    final (label, color, pulse) = switch (status.phase) {
      // home Wi-Fi, or the laptop's Tailscale address from any other network (PROTOCOL.md 10.7)
      // desktop: its own brain on this computer (no network, so no round-trip time to show)
      LinkPhase.connected when AppPlatform.desktop => ('Brain on this computer', Brand.ok, false),
      LinkPhase.connected => ('${status.routeLabel}${status.rttMs != null ? ' · ${status.rttMs} ms' : ''}', Brand.ok, false),
      LinkPhase.connecting || LinkPhase.handshaking => ('Connecting', Brand.warn, true),
      LinkPhase.retrying => ('Reconnecting', Brand.warn, true),
      LinkPhase.authFailed => ('Needs pairing', Brand.tongue, false),
      LinkPhase.versionMismatch => ('Update needed', Brand.tongue, false),
      LinkPhase.idle => ('Offline', context.sp.muted, false),
    };
    return StatusPill(label: label, dot: color, pulse: pulse);
  }
}

/// Away from home: how the robot is linked to the phone brain.
class _AwayRobotPill extends StatelessWidget {
  const _AwayRobotPill({required this.away, required this.name, required this.robotPaired});
  final AwayState away;
  final String name;
  final bool robotPaired;
  @override
  Widget build(BuildContext context) {
    if (!robotPaired) return const StatusPill(label: 'Robot not paired', icon: Icons.bluetooth_disabled_rounded);
    final (label, icon, pulse) = switch (away.robot) {
      RobotConn.connected => (
          away.hotspot == HotspotConn.up ? 'Robot · Bluetooth + hotspot' : 'Robot · Bluetooth',
          Icons.bluetooth_connected_rounded,
          false
        ),
      RobotConn.needsPermission => ('Bluetooth permission needed', Icons.bluetooth_disabled_rounded, false),
      RobotConn.bluetoothOff => ('Bluetooth is off', Icons.bluetooth_disabled_rounded, false),
      RobotConn.connecting || RobotConn.pairing => ('Reaching …', Icons.bluetooth_searching_rounded, true),
      _ => ('Looking for …', Icons.bluetooth_searching_rounded, true),
    };
    return StatusPill(label: label, icon: icon, pulse: pulse);
  }
}

class FaceCard extends StatelessWidget {
  const FaceCard({super.key, required this.face, required this.caption, required this.alarm});
  final FaceController face;
  final String? caption;
  final bool alarm;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(34),
        color: Brand.chocolate,
        boxShadow: [BoxShadow(color: p.shadow.withValues(alpha: context.isDark ? 0.6 : 0.22), blurRadius: 36, offset: const Offset(0, 16))],
      ),
      padding: const EdgeInsets.all(10),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(26),
        child: AspectRatio(
          aspectRatio: 480 / 272,
          child: Stack(fit: StackFit.expand, children: [
            FaceView(controller: face),
            Positioned(
              left: 12,
              right: 12,
              top: 10,
              child: IgnorePointer(child: _Bubble(text: caption)),
            ),
          ]),
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.text});
  final String? text;
  @override
  Widget build(BuildContext context) {
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 420),
      switchInCurve: Springs.curve,
      switchOutCurve: Curves.easeIn,
      transitionBuilder: (c, a) => FadeTransition(
        opacity: a,
        child: ScaleTransition(scale: Tween(begin: 0.8, end: 1.0).animate(a), alignment: Alignment.topCenter, child: c),
      ),
      child: text == null
          ? const SizedBox.shrink()
          : Align(
              key: ValueKey(text),
              alignment: Alignment.topCenter,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.94),
                  borderRadius: BorderRadius.circular(18),
                  boxShadow: const [BoxShadow(color: Color(0x33000000), blurRadius: 12, offset: Offset(0, 4))],
                ),
                child: Text(text!,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Brand.chocolate, fontWeight: FontWeight.w700, fontSize: 14, height: 1.25)),
              ),
            ),
    );
  }
}

class AlarmBar extends ConsumerWidget {
  const AlarmBar({super.key, required this.label});
  final String? label;
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cmds = ref.read(commandsProvider);
    return SpikeCard(
      color: Brand.tongue.withValues(alpha: 0.14),
      child: Row(children: [
        const Icon(Icons.alarm_rounded, color: Brand.tongue),
        const SizedBox(width: 12),
        Expanded(child: Text(label ?? 'Alarm', style: context.tt.titleMedium)),
        PillButton(label: 'Snooze', dense: true, onTap: cmds.alarmSnooze),
        const SizedBox(width: 8),
        PillButton(label: "I'm up", dense: true, filled: true, color: Brand.tongue, onTap: () {
          Haptics.success();
          cmds.alarmStop();
        }),
      ]),
    );
  }
}
