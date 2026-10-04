import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/capabilities.dart';
import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/platform.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/messages.dart';
import '../../state/hub.dart';
import '../../state/away.dart';
import '../../state/brain_ready.dart';
import '../connect/brain_needed.dart';
import '../../state/link.dart';
import '../settings/away_settings.dart' show hotspotProblem;
import '../../state/settings.dart';
import '../../desktop/desktop_page.dart';
import '../story/push_copy.dart';
import '../story/push_sheets.dart';
import '../story/push_widgets.dart';
import 'joystick.dart';

/// A trick button: the face_v2 action it plays (protocol v1.2 `action`).
/// Every trick is a real, distinct action (the brain's voice words mapped
/// "sit" and "bow" to the same playBow; the legs will add a real sit later).
typedef Trick = ({String id, String label, IconData icon});

/// Every trick the face can draw (kept for the future).
const allTricks = <Trick>[
  (id: 'playBow', label: 'Bow', icon: Icons.pets_rounded),
  (id: 'zoomies', label: 'Zoomies', icon: Icons.autorenew_rounded),
  (id: 'beggingAction', label: 'Beg', icon: Icons.back_hand_rounded),
  (id: 'rollOver', label: 'Roll over', icon: Icons.rotate_right_rounded),
  (id: 'headTilt', label: 'Head tilt', icon: Icons.psychology_alt_rounded),
  (id: 'tailWagDance', label: 'Wag dance', icon: Icons.music_note_rounded),
  (id: 'sniffAround', label: 'Sniff', icon: Icons.search_rounded),
  (id: 'sneeze', label: 'Sneeze', icon: Icons.air_rounded),
  // v1.4 body actions (PROTOCOL.md 5.2): real motion on the robot, a face reaction otherwise.
  (id: 'walk', label: 'Walk', icon: Icons.directions_walk_rounded),
  (id: 'paw', label: 'Give paw', icon: Icons.front_hand_rounded),
  (id: 'snuggle', label: 'Snuggle', icon: Icons.favorite_rounded),
  (id: 'slowWag', label: 'Slow wag', icon: Icons.spa_rounded),
];

/// What the Play tab shows: only tricks the real body can do (core/capabilities.dart).
final tricks = availableOnly<Trick>(allTricks, (t) => t.id);

const _comfort = {'snuggle', 'slowWag'};

List<List<T>> _rows<T>(List<T> items, int n) =>
    [for (var i = 0; i < items.length; i += n) items.sublist(i, i + n > items.length ? items.length : i + n)];

class RemoteScreen extends ConsumerStatefulWidget {
  const RemoteScreen({super.key});
  @override
  ConsumerState<RemoteScreen> createState() => _RemoteScreenState();
}

class _RemoteScreenState extends ConsumerState<RemoteScreen> with WidgetsBindingObserver {
  String? _busy;
  Timer? _busyTimer;
  double _jx = 0, _jy = 0;

  /// While the stick is held the last position is re-sent 20 times a second,
  /// so the robot's dead man's switch (300 ms) never trips on a steady thumb.
  Timer? _driveTimer;
  static const _driveEvery = Duration(milliseconds: 50);
  static const _ttlMs = 300;

  /// Kept from initState: dispose must still be able to send the final stop.
  late final SpikeCommands _cmds;

  @override
  void initState() {
    super.initState();
    _cmds = ref.read(commandsProvider);
    if (AppPlatform.desktop) {
      HardwareKeyboard.instance.addHandler(_onKey);
      WidgetsBinding.instance.addObserver(this);
    }
  }

  @override
  void dispose() {
    if (AppPlatform.desktop) {
      HardwareKeyboard.instance.removeHandler(_onKey);
      WidgetsBinding.instance.removeObserver(this);
    }
    _busyTimer?.cancel();
    _stopDrive(rebuild: false); // leaving the tab mid-drive stops the wheels at once
    super.dispose();
  }

  bool _asking = false;

  /// No brain yet: the one friendly ask (features/connect/brain_needed.dart). One sheet at a time.
  Future<bool> _brainReady() async {
    if (brainReadyNow(ref)) return true;
    if (_asking) return false;
    _asking = true;
    final ok = await ensureBrain(context, ref, reason: BrainReason.play);
    _asking = false;
    return ok;
  }

  Future<void> _trick(Trick t) async {
    if (!await _brainReady() || !mounted) return;
    final cmds = ref.read(commandsProvider);
    if (!cmds.connected) {
      Haptics.error();
      showToast(context, 'Spike is still waking up. Try again in a moment.', icon: Icons.hourglass_top_rounded);
      return;
    }
    Haptics.confirm();
    if (t.id == 'walk') {
      cmds.action(t.id, direction: 'forward', steps: 4);   // a short walk by default (PROTOCOL.md 5.2)
    } else {
      cmds.action(t.id);
    }
    // first trick ever: a short "imagine this on your desk" (features/story/), once
    maybePeek(context, ref, t.id == 'tailWagDance' || t.id == 'slowWag' ? PeekFeature.wag : PeekFeature.trick);
    setState(() => _busy = t.id);
    _busyTimer?.cancel();
    _busyTimer = Timer(const Duration(milliseconds: 2400), () {
      if (mounted) setState(() => _busy = null);
    });
  }

  /// After the thumb lifts the knob springs home and keeps reporting positions:
  /// those must never drive the wheels again.
  bool _springingHome = false;

  void _stick(double x, double y) {
    final centred = x.abs() <= 0.02 && y.abs() <= 0.02;
    if (!centred && !brainReadyNow(ref)) {
      // steering needs a brain: ask once, and ignore this drag until the stick is let go
      _springingHome = true;
      _brainReady();
      return;
    }
    if (_springingHome) {
      if (centred) _springingHome = false;
      return;
    }
    if (centred) x = y = 0;
    if ((x - _jx).abs() > 0.02 || (y - _jy).abs() > 0.02 || (centred && (_jx != 0 || _jy != 0))) {
      setState(() {
        _jx = x;
        _jy = y;
      });
    }
    if (_driveTimer == null && (x.abs() > 0.02 || y.abs() > 0.02)) {
      _sendDrive();
      _driveTimer = Timer.periodic(_driveEvery, (_) => _sendDrive());
    }
  }

  void _sendDrive() {
    if (_cmds.connected && !_cmds.legacy) _cmds.drive(_jx, _jy, ttlMs: _ttlMs);
  }

  void _stopDrive({bool rebuild = true}) {
    final was = _driveTimer != null;
    _driveTimer?.cancel();
    _driveTimer = null;
    if (was && _cmds.connected && !_cmds.legacy) _cmds.drive(0, 0, ttlMs: _ttlMs);
    _springingHome = rebuild; // only a real release is followed by the spring animation
    _jx = _jy = 0;
    if (rebuild && mounted) setState(() {});
  }

  // ---------------------------------------------------------------- desktop: drive with the keyboard
  /// Arrow keys or W A S D, held = drive (the same 20 Hz stream and dead man's switch as the stick).
  final Set<LogicalKeyboardKey> _keys = {};
  static final _keyMap = <LogicalKeyboardKey, (double, double)>{
    LogicalKeyboardKey.arrowUp: (0, 1), LogicalKeyboardKey.keyW: (0, 1),
    LogicalKeyboardKey.arrowDown: (0, -1), LogicalKeyboardKey.keyS: (0, -1),
    LogicalKeyboardKey.arrowLeft: (-1, 0), LogicalKeyboardKey.keyA: (-1, 0),
    LogicalKeyboardKey.arrowRight: (1, 0), LogicalKeyboardKey.keyD: (1, 0),
  };

  bool _onKey(KeyEvent e) {
    if (!mounted || !AppPlatform.desktop || !TickerMode.valuesOf(context).enabled) return false; // another tab is showing
    if (FocusManager.instance.primaryFocus?.context?.widget is EditableText) return false;
    if (!_keyMap.containsKey(e.logicalKey)) return false;
    if (e is KeyDownEvent) _keys.add(e.logicalKey);
    if (e is KeyUpEvent) _keys.remove(e.logicalKey);
    var x = 0.0, y = 0.0;
    for (final k in _keys) {
      x += _keyMap[k]!.$1;
      y += _keyMap[k]!.$2;
    }
    x = x.clamp(-1, 1) * 0.6; // keys drive at 60 %: a desk is small
    y = y.clamp(-1, 1) * 0.6;
    if (x == 0 && y == 0) {
      _stopDrive();
      _springingHome = false;
    } else {
      _stick(x, y);
    }
    return true;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed && _keys.isNotEmpty) {
      _keys.clear(); // the window lost the keyboard mid-drive: stop now, never keep driving
      _stopDrive();
    }
  }

  @override
  Widget build(BuildContext context) {
    if (AppPlatform.desktop && context.isWide) return _desktop(context);
    final p = context.sp;
    final spike = ref.watch(spikeStateProvider);
    final name = ref.watch(settingsProvider.select((s) => s.nameFor(spike.mode)));
    final connected = ref.watch(linkStatusProvider.select((s) => s.value?.isConnected ?? false));
    final canDrive = connected && spike.robotOnline && spike.robotDrive;
    final bottom = MediaQuery.paddingOf(context).bottom + 100;
    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: ListView(
          padding: EdgeInsets.fromLTRB(20, 10, 20, bottom),
          children: [
            Text('Play with $name', style: context.tt.headlineSmall),
            const SectionHeader('Tricks', subtitle: 'He shows off, then tells you about it'),
            for (final row in _rows(tricks.where((t) => !_comfort.contains(t.id)).toList(), 4))
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(children: [
                  for (final (i, t) in row.indexed) ...[
                    if (i > 0) const SizedBox(width: 8),
                    Expanded(
                      child: Entrance(
                        index: tricks.indexOf(t),
                        child: ActionTile(icon: t.icon, label: t.label, busy: _busy == t.id, onTap: () => _trick(t)),
                      ),
                    ),
                  ],
                ]),
              ),
            const SectionHeader('Comfort', subtitle: 'Gentle and slow, for the harder days'),
            Row(children: [
              for (final (i, t) in tricks.where((t) => _comfort.contains(t.id)).indexed) ...[
                if (i > 0) const SizedBox(width: 10),
                Expanded(
                  child: Entrance(
                    index: 8 + i,
                    child: _ComfortTile(trick: t, busy: _busy == t.id, onTap: () => _trick(t)),
                  ),
                ),
              ],
            ]),
            const SectionHeader('Eyes', subtitle: 'What Spike sees'),
            const _CameraCard(),
            SectionHeader('Drive', subtitle: canDrive ? 'Hold and steer. Let go and he stops.' : 'Wheels answer when the robot is here'),
            SpikeCard(
              child: Column(children: [
                Row(children: [
                  Icon(Icons.shield_rounded, color: Brand.ok, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text('Desk-edge stops are always on inside $name. The app can never turn them off.',
                        style: context.tt.bodySmall?.copyWith(color: p.ink, fontWeight: FontWeight.w600)),
                  ),
                ]),
                const SizedBox(height: 18),
                SpringJoystick(
                    onChanged: _stick,
                    onStart: () => _springingHome = false,
                    // the first drive ever: the peek comes once the thumb is lifted, never mid-drag
                    onRelease: () {
                      _stopDrive();
                      maybePeek(context, ref, PeekFeature.drive);
                    }),
                const SizedBox(height: 12),
                Text(
                  _jx == 0 && _jy == 0
                      ? 'Drag to steer'
                      : '${_jy >= 0 ? 'Forward' : 'Back'} ${(_jy.abs() * 100).round()}%  ·  ${_jx >= 0 ? 'Right' : 'Left'} ${(_jx.abs() * 100).round()}%',
                  style: context.tt.labelLarge?.copyWith(color: p.muted, fontFeatures: const [FontFeature.tabularFigures()]),
                ),
                const SizedBox(height: 4),
                Text(
                  !connected
                      ? 'Connect $name first.'
                      : canDrive
                          ? 'He stops by himself if this phone goes quiet for a third of a second.'
                          : spike.simulatorOnly
                              ? 'Only the face simulator is connected: it has no wheels, so nothing moves.'
                              : 'Robot not connected: nothing moves.',
                  textAlign: TextAlign.center,
                  style: context.tt.bodySmall,
                ),
              ]),
            ),
            if (pushVisible) ...[const SizedBox(height: 18), const RobotCard(tab: PushTab.play)],
          ],
        ),
      ),
    );
  }
}

/// Play on the desktop (DESIGN.md "Desktop > Proportions"):
///  * the tricks are one row across the page (8 tiles of 132..168 x 88 fit a 1366 window), first
///    because they are what people come here for;
///  * below: his eyes (the camera, at its true 4:3, as tall as the page allows, never more than
///    61.8 % of the width) on the right, and on the left the drive pad (arrow keys first, the
///    stick for the mouse) with the gentle comfort actions. Nothing scrolls at 1366 x 768.
extension _PlayDesktop on _RemoteScreenState {
  Widget _desktop(BuildContext context) {
    final p = context.sp;
    final spike = ref.watch(spikeStateProvider);
    final name = ref.watch(settingsProvider.select((s) => s.nameFor(spike.mode)));
    final connected = ref.watch(linkStatusProvider.select((s) => s.value?.isConnected ?? false));
    final canDrive = connected && spike.robotOnline && spike.robotDrive;
    final showy = tricks.where((t) => !_comfort.contains(t.id)).toList();
    final comfort = tricks.where((t) => _comfort.contains(t.id)).toList();
    return DesktopPage(
      title: 'Play with $name',
      body: (context, room) {
        final m = context.metrics;
        const tileMin = 132.0, tileMax = 168.0;
        final perRow = ((room.maxWidth + Space.x3) / (tileMin + Space.x3)).floor().clamp(1, showy.length);
        final rows = (showy.length / perRow).ceil();
        // one row fills the page edge to edge; wrapped rows keep the tile width steady
        final tileW = rows == 1
            ? (room.maxWidth - (showy.length - 1) * Space.x3) / showy.length
            : ((room.maxWidth - (perRow - 1) * Space.x3) / perRow).clamp(tileMin, tileMax);
        final tricksH = PaneTitle.height + rows * DesktopMetrics.actionTile + (rows - 1) * Space.x3;
        final lowerH = room.maxHeight - tricksH - Space.x8;
        // the camera: as tall as the lower band allows, never wider than the golden main share
        final camH0 = lowerH - PaneTitle.height;
        final camW = math.min(camH0 * Ratios.camera, goldenSplit(room.maxWidth, m.gutter).$1).clamp(320.0, 1600.0);
        final leftW = room.maxWidth - m.gutter - camW;
        // drive title + card padding + Comfort title (with its air) + a comfort tile = 60 + 40 + 92 + 60
        final stick = (camH0 + PaneTitle.height - 252).clamp(152.0, 232.0);
        return SingleChildScrollView(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const PaneTitle('Tricks', subtitle: 'He shows off, then tells you about it', first: true),
            Wrap(spacing: Space.x3, runSpacing: Space.x3, children: [
              for (final t in showy)
                SizedBox(width: tileW, child: DeskTile(icon: t.icon, label: t.label, busy: _busy == t.id, onTap: () => _trick(t))),
            ]),
            const SizedBox(height: Space.x8),
            SizedBox(
              // both columns exactly as tall as the camera column, so their bottoms line up
              height: math.max(PaneTitle.height + camW / Ratios.camera, 392),
              child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              SizedBox(
                width: leftW,
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  PaneTitle('Drive', subtitle: canDrive ? 'Hold an arrow key, or drag the stick' : 'The wheels answer when the robot is here', first: true),
                  // the stick grows with the height the column has (152..232); the card hugs it, and any
                  // spare height stays under Comfort as air rather than an empty card
                  SpikeCard(
                    padding: const EdgeInsets.all(Space.x5),
                    child: Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
                      SpringJoystick(size: stick, onChanged: _stick, onStart: () => _springingHome = false, onRelease: _stopDrive),
                      const SizedBox(width: Space.x6),
                      Expanded(
                        child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                          const _Keys(),
                          const SizedBox(height: Space.x4),
                          Row(children: [
                            const Icon(Icons.shield_rounded, color: Brand.ok, size: 18),
                            const SizedBox(width: Space.x2),
                            Expanded(child: Text('Desk-edge stops are always on', style: context.tt.titleSmall)),
                          ]),
                          Text(
                            _jx == 0 && _jy == 0
                                ? (canDrive
                                    ? 'Let go and he stops.'
                                    : (spike.simulatorOnly ? 'Only the face simulator is here: no wheels.' : 'Robot not connected: nothing moves.'))
                                : '${_jy >= 0 ? 'Forward' : 'Back'} ${(_jy.abs() * 100).round()}%  ·  ${_jx >= 0 ? 'Right' : 'Left'} ${(_jx.abs() * 100).round()}%',
                            style: context.tt.bodySmall?.copyWith(color: p.muted, fontFeatures: const [FontFeature.tabularFigures()]),
                          ),
                        ]),
                      ),
                    ]),
                  ),
                  const PaneTitle('Comfort', subtitle: 'Gentle and slow, for the harder days'),
                  Row(children: [
                    for (final (i, t) in comfort.indexed) ...[
                      if (i > 0) const SizedBox(width: Space.x3),
                      Expanded(child: _ComfortTile(trick: t, busy: _busy == t.id, onTap: () => _trick(t))),
                    ],
                  ]),
                ]),
              ),
              SizedBox(width: m.gutter),
              SizedBox(
                width: camW,
                child: const Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  PaneTitle('Eyes', subtitle: 'What he sees, live. Never saved.', first: true),
                  _CameraCard(),
                ]),
              ),
            ]),
            ),
          ]),
        );
      },
    );
  }
}

/// The arrow-key cluster, drawn as keys (a hint that the keyboard drives).
class _Keys extends StatelessWidget {
  const _Keys();
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    Widget key(IconData i) => Container(
          width: 32,
          height: 32,
          margin: const EdgeInsets.all(2),
          decoration: BoxDecoration(color: p.cardHi, borderRadius: BorderRadius.circular(8), border: Border.all(color: p.line)),
          child: Icon(i, size: 18, color: p.muted),
        );
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(padding: const EdgeInsets.only(left: 36), child: key(Icons.keyboard_arrow_up_rounded)),
      Row(mainAxisSize: MainAxisSize.min, children: [
        key(Icons.keyboard_arrow_left_rounded),
        key(Icons.keyboard_arrow_down_rounded),
        key(Icons.keyboard_arrow_right_rounded),
      ]),
    ]);
  }
}

class _ComfortTile extends StatelessWidget {
  const _ComfortTile({required this.trick, required this.busy, required this.onTap});
  final Trick trick;
  final bool busy;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Pressable(
      onTap: onTap,
      scale: 0.94,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Springs.curve,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Brand.tongue.withValues(alpha: busy ? 0.32 : 0.16), Brand.tongue.withValues(alpha: busy ? 0.18 : 0.06)],
          ),
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: busy ? Brand.tongue : p.line),
        ),
        child: Row(children: [
          Icon(trick.icon, color: Brand.tongue, size: 26),
          const SizedBox(width: 10),
          Expanded(child: Text(trick.label, style: context.tt.titleMedium)),
        ]),
      ),
    );
  }
}

/// Live view from the robot's camera (v1.2 camera_subscribe). Subscribes while
/// this card is on screen and the robot has a camera; frames are shown and
/// dropped, never stored.
class _CameraCard extends ConsumerStatefulWidget {
  const _CameraCard();
  @override
  ConsumerState<_CameraCard> createState() => _CameraCardState();
}

class _CameraCardState extends ConsumerState<_CameraCard> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
  bool _subscribed = false;
  SpikeHub? _client;

  @override
  void dispose() {
    _c.dispose();
    if (_subscribed && (_client?.current.isConnected ?? false)) {
      _client!.send(const CameraUnsubscribeMsg());
    }
    super.dispose();
  }

  void _sync(bool want) {
    if (want && !_subscribed) {
      _subscribed = ref.read(commandsProvider).watchCamera(8);
    } else if (!want && _subscribed) {
      ref.read(commandsProvider).stopCamera();
      _subscribed = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    _client = ref.watch(brainClientProvider);
    final spike = ref.watch(spikeStateProvider);
    final connected = ref.watch(linkStatusProvider.select((s) => s.value?.isConnected ?? false));
    final away = ref.watch(awayProvider);
    // away (v1.3): asking for the camera is what brings the phone's hotspot up, so ask as soon as the robot is here
    final want = connected && spike.robotOnline && (spike.robotCamera || away.away) && !ref.read(commandsProvider).legacy;
    // the brain forgets subscriptions when the link drops: subscribe again after a reconnect
    ref.listen(linkStatusProvider.select((s) => s.value?.isConnected ?? false), (_, now) {
      if (!now) _subscribed = false;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _sync(want);
    });
    final frame = want ? ref.watch(cameraFramesProvider).value : null;
    String title;
    String body;
    if (!connected) {
      title = "Spike's eye view";
      body = 'Connect Spike to see through his eyes.';
    } else if (!spike.robotOnline) {
      title = 'Robot not connected';
      body = spike.simulatorOnly
          ? 'Only the face simulator is connected. The live view comes from the robot\'s own camera.'
          : 'Turn the robot on: his camera view appears here.';
    } else if (away.away && !spike.robotCamera) {
      (title, body) = switch (away.hotspot) {
        HotspotConn.failed => ('Camera needs Wi-Fi', hotspotProblem(away.hotspotReason)),
        HotspotConn.up => ('Waiting for his eyes…', 'Spike is on the hotspot; his camera is joining.'),
        _ => ('Opening his eyes…', 'The phone is making a hotspot for his camera.'),
      };
    } else if (!spike.robotCamera) {
      title = 'No camera on this robot';
      body = 'The robot is connected, but it has no camera board.';
    } else {
      title = 'Waiting for his eyes…';
      body = 'The picture appears in a moment.';
    }
    return ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: AspectRatio(
        aspectRatio: 4 / 3,
        child: frame != null
            ? Stack(fit: StackFit.expand, children: [
                Image.memory(frame, fit: BoxFit.cover, gaplessPlayback: true, filterQuality: FilterQuality.medium),
                const Positioned(left: 14, top: 14, child: _Rec(live: true)),
              ])
            : AnimatedBuilder(
                animation: _c,
                builder: (_, child) => DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment(-1 + 2 * _c.value, -1),
                      end: Alignment(1 + 2 * _c.value, 1),
                      colors: const [Color(0xFF2A1E17), Color(0xFF3B2A1F), Color(0xFF2A1E17)],
                    ),
                  ),
                  child: child,
                ),
                child: Stack(children: [
                  const Positioned(left: 14, top: 14, child: _Rec(live: false)),
                  Center(
                    child: Column(mainAxisSize: MainAxisSize.min, children: [
                      Icon(spike.robotOnline ? Icons.videocam_rounded : Icons.videocam_off_rounded,
                          color: Brand.cream.withValues(alpha: 0.8), size: 40),
                      const SizedBox(height: 10),
                      Text(title, style: context.tt.titleMedium?.copyWith(color: Brand.cream)),
                      const SizedBox(height: 4),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 28),
                        child: Text(body,
                            textAlign: TextAlign.center, style: context.tt.bodySmall?.copyWith(color: Brand.cream.withValues(alpha: 0.7))),
                      ),
                    ]),
                  ),
                ]),
              ),
      ),
    );
  }
}

class _Rec extends StatelessWidget {
  const _Rec({required this.live});
  final bool live;
  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        decoration: BoxDecoration(color: Colors.black.withValues(alpha: 0.35), borderRadius: BorderRadius.circular(20)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: live ? Brand.tongue : Brand.cream.withValues(alpha: 0.5), shape: BoxShape.circle)),
          const SizedBox(width: 6),
          Text(live ? 'LIVE' : 'NO SIGNAL',
              style: context.tt.labelSmall?.copyWith(color: Brand.cream, letterSpacing: 1.2, fontWeight: FontWeight.w800)),
        ]),
      );
}
