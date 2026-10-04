import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';

import '../../core/haptics.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/client.dart';
import '../../protocol/names.dart';
import '../../state/link.dart';
import '../../state/pairing_sync.dart';
import '../../state/settings.dart';
import 'discovery.dart';
import 'nearby_robot.dart';
import 'pairing.dart';
import 'qr_sheet.dart';

/// Find Spike's brain on the Wi-Fi, scan his pairing QR, or type an address.
class ConnectScreen extends ConsumerStatefulWidget {
  const ConnectScreen({super.key});
  @override
  ConsumerState<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends ConsumerState<ConnectScreen> {
  final _host = TextEditingController();
  final _port = TextEditingController(text: '$defaultPort');
  final _token = TextEditingController();
  BrainEndpoint? _trying;
  bool _manualOpen = false;

  @override
  void initState() {
    super.initState();
    final ep = ref.read(settingsProvider).endpoint;
    if (ep != null) {
      _host.text = ep.host;
      _port.text = '${ep.port}';
      _token.text = ep.token ?? '';
    }
  }

  @override
  void dispose() {
    _host.dispose();
    _port.dispose();
    _token.dispose();
    super.dispose();
  }

  void _connect(BrainEndpoint ep) {
    FocusScope.of(context).unfocus();
    Haptics.confirm();
    setState(() => _trying = ep);
    ref.read(brainClientProvider).connect(ep);
  }

  void _connectManual() {
    final ep = parsePairing('${_host.text.trim()}:${_port.text.trim()}');
    if (ep == null) {
      Haptics.error();
      showToast(context, 'That address does not look right', icon: Icons.error_outline_rounded);
      return;
    }
    final t = _token.text.trim();
    _connect(BrainEndpoint(host: ep.host, port: ep.port, token: t.isEmpty ? null : t));
  }

  Future<void> _scan() async {
    final ep = await showQrSheet(context);
    if (ep != null && mounted) {
      _host.text = ep.host;
      _port.text = '${ep.port}';
      _token.text = ep.token ?? '';
      _connect(ep);
    }
  }

  void _skip() {
    ref.read(settingsProvider.notifier).update((s) => s.copyWith(onboarded: true));
    context.go('/home');
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final link = ref.watch(lanStatusProvider).value ?? const LinkStatus();
    final disc = ref.watch(discoveryProvider);
    final recent = ref.watch(settingsProvider.select((s) => s.recent));

    ref.listen(lanStatusProvider, (prev, next) {
      final s = next.value;
      if (s == null || _trying == null) return;
      if (s.isConnected && !(prev?.value?.isConnected ?? false)) {
        Haptics.success();
        ref.read(settingsProvider.notifier).rememberEndpoint(s.endpoint!);
        final router = GoRouter.of(context);
        Future.delayed(const Duration(milliseconds: 650), () {
          if (mounted) router.go('/home');
        });
      } else if (s.phase == LinkPhase.authFailed) {
        Haptics.error();
      }
    });

    final canPop = GoRouter.of(context).canPop();
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 40),
          children: [
            Row(children: [
              if (canPop)
                IconButton(onPressed: () => context.pop(), icon: const Icon(Icons.arrow_back_rounded))
              else
                const SizedBox(height: 48),
              const Spacer(),
              TextButton(onPressed: _skip, child: Text(canPop ? 'Done' : 'Explore first', style: TextStyle(color: p.muted))),
            ]),
            const SizedBox(height: 8),
            Center(child: _Logo(connected: link.isConnected, trying: _trying != null && link.isTrying)),
            const SizedBox(height: 22),
            Entrance(
              child: Text(link.isConnected ? 'Found him!' : "Let's find Spike",
                  textAlign: TextAlign.center, style: context.tt.headlineMedium),
            ),
            const SizedBox(height: 8),
            Entrance(
              index: 1,
              child: Text(
                'Spike\'s brain runs on your laptop. Keep the phone on the same Wi-Fi, or scan his pairing code (pair_phone on the laptop).',
                textAlign: TextAlign.center,
                style: context.tt.bodyMedium?.copyWith(color: p.muted),
              ),
            ),
            const SizedBox(height: 20),
            _StatusBanner(status: link, trying: _trying),
            const SizedBox(height: 18),
            Entrance(
              index: 2,
              child: Row(children: [
                Expanded(child: PillButton(label: 'Scan pairing code', icon: Icons.qr_code_scanner_rounded, filled: true, onTap: _scan)),
              ]),
            ),
            SectionHeader(
              'On this Wi-Fi',
              subtitle: disc.searching ? 'Looking for Spike...' : (disc.error ?? 'Search finished'),
              trailing: IconButton(
                onPressed: () {
                  Haptics.tap();
                  ref.read(discoveryProvider.notifier).start();
                },
                icon: disc.searching
                    ? SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.4, color: p.accent))
                    : const Icon(Icons.refresh_rounded),
              ),
            ),
            if (disc.found.isEmpty)
              _EmptyHint(searching: disc.searching)
            else
              for (final (i, ep) in disc.found.indexed)
                Entrance(
                  index: i,
                  child: EndpointTile(
                    ep: PairingSync.withKnownToken(ep, ref.watch(settingsProvider)),
                    icon: Icons.wifi_rounded,
                    onTap: () => _connect(PairingSync.withKnownToken(ep, ref.read(settingsProvider))),
                  ),
                ),
            if (recent.isNotEmpty) ...[
              const SectionHeader('Recent'),
              for (final (i, ep) in recent.indexed)
                Entrance(index: i, child: EndpointTile(ep: ep, icon: Icons.history_rounded, onTap: () => _connect(ep))),
            ],
            const SizedBox(height: 10),
            SpikeCard(
              padding: EdgeInsets.zero,
              child: Column(children: [
                ListTile(
                  contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 4),
                  leading: Icon(Icons.edit_rounded, color: p.accent),
                  title: Text('Type an address', style: context.tt.titleMedium),
                  subtitle: Text('For a laptop on another network, or USB (127.0.0.1)', style: context.tt.bodySmall),
                  trailing: AnimatedRotation(
                    turns: _manualOpen ? 0.5 : 0,
                    duration: const Duration(milliseconds: 400),
                    curve: Springs.curve,
                    child: const Icon(Icons.expand_more_rounded),
                  ),
                  onTap: () {
                    Haptics.tick();
                    setState(() => _manualOpen = !_manualOpen);
                  },
                ),
                AnimatedSize(
                  duration: const Duration(milliseconds: 420),
                  curve: Springs.smoothCurve,
                  child: _manualOpen
                      ? Padding(
                          padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                          child: Column(children: [
                            Row(children: [
                              Expanded(
                                flex: 5,
                                child: TextField(
                                  controller: _host,
                                  keyboardType: TextInputType.url,
                                  decoration: const InputDecoration(hintText: '192.168.1.20'),
                                ),
                              ),
                              const SizedBox(width: 10),
                              Expanded(
                                flex: 2,
                                child: TextField(
                                  controller: _port,
                                  keyboardType: TextInputType.number,
                                  decoration: const InputDecoration(hintText: '8765'),
                                ),
                              ),
                            ]),
                            const SizedBox(height: 10),
                            TextField(
                              controller: _token,
                              obscureText: true,
                              decoration: const InputDecoration(hintText: 'Pairing code (only if Spike asks)'),
                            ),
                            const SizedBox(height: 12),
                            Row(children: [
                              Expanded(child: PillButton(label: 'Connect', icon: Icons.link_rounded, onTap: _connectManual)),
                            ]),
                          ]),
                        )
                      : const SizedBox(width: double.infinity),
                ),
              ]),
            ),
            const SectionHeader('Away from home'),
            const NearbyRobotCard(),
          ],
        ),
      ),
    );
  }
}

class _Logo extends StatefulWidget {
  const _Logo({required this.connected, required this.trying});
  final bool connected;
  final bool trying;
  @override
  State<_Logo> createState() => _LogoState();
}

class _LogoState extends State<_Logo> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 2400))..repeat();
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return SizedBox(
      width: 190,
      height: 190,
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, child) => CustomPaint(
          painter: _RipplePainter(t: _c.value, color: widget.connected ? Brand.ok : p.accent, active: widget.trying || widget.connected),
          child: child,
        ),
        child: Center(
          child: AnimatedScale(
            scale: widget.connected ? 1.08 : 1,
            duration: const Duration(milliseconds: 600),
            curve: Springs.curve,
            child: Hero(tag: 'spike-logo', child: SvgPicture.asset('assets/icon/spike_icon.svg', width: 120, height: 120)),
          ),
        ),
      ),
    );
  }
}

class _RipplePainter extends CustomPainter {
  _RipplePainter({required this.t, required this.color, required this.active});
  final double t;
  final Color color;
  final bool active;
  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    for (var i = 0; i < 3; i++) {
      final k = ((t + i / 3) % 1.0);
      final r = 62 + k * 34;
      final a = (active ? 0.28 : 0.12) * (1 - k);
      canvas.drawCircle(c, r, Paint()..color = color.withValues(alpha: a));
    }
  }

  @override
  bool shouldRepaint(_RipplePainter o) => o.t != t || o.color != color || o.active != active;
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({required this.status, required this.trying});
  final LinkStatus status;
  final BrainEndpoint? trying;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    String? text;
    Color color = p.muted;
    IconData icon = Icons.info_outline_rounded;
    if (status.isConnected) {
      text = 'Connected to ${status.hello?.names['dog'] ?? 'Spike'}\'s brain at ${status.endpoint?.label}';
      color = Brand.ok;
      icon = Icons.check_circle_rounded;
    } else if (trying != null && status.phase == LinkPhase.authFailed) {
      text = 'Spike wants his pairing code. Scan it (pair_phone on the laptop), or plug this phone in by USB once.';
      color = Brand.tongue;
      icon = Icons.lock_rounded;
    } else if (trying != null && status.isTrying) {
      text = status.phase == LinkPhase.retrying
          ? '${status.error ?? 'No answer'} - trying again...'
          : 'Calling Spike at ${trying!.label}...';
      color = status.phase == LinkPhase.retrying ? Brand.warn : p.accent;
      icon = status.phase == LinkPhase.retrying ? Icons.wifi_off_rounded : Icons.wifi_tethering_rounded;
    }
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 350),
      switchInCurve: Springs.curve,
      transitionBuilder: (c, a) => FadeTransition(opacity: a, child: ScaleTransition(scale: Tween(begin: 0.94, end: 1.0).animate(a), child: c)),
      child: text == null
          ? const SizedBox.shrink()
          : Container(
              key: ValueKey(text),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(18)),
              child: Row(children: [
                Icon(icon, color: color),
                const SizedBox(width: 10),
                Expanded(child: Text(text, style: context.tt.bodyMedium?.copyWith(fontWeight: FontWeight.w600))),
              ]),
            ),
    );
  }
}

class EndpointTile extends StatelessWidget {
  const EndpointTile({super.key, required this.ep, required this.icon, required this.onTap});
  final BrainEndpoint ep;
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: SpikeCard(
        onTap: onTap,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(children: [
          Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(color: p.accent.withValues(alpha: 0.14), shape: BoxShape.circle),
            child: Icon(icon, color: p.accent),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(ep.name ?? 'Spike\'s brain', style: context.tt.titleMedium),
              Text('${ep.host}:${ep.port}${ep.token != null ? '  ·  paired' : ''}', style: context.tt.bodySmall),
            ]),
          ),
          Icon(Icons.chevron_right_rounded, color: p.muted),
        ]),
      ),
    );
  }
}

class _EmptyHint extends StatelessWidget {
  const _EmptyHint({required this.searching});
  final bool searching;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
        child: Text(
          searching
              ? 'Listening for Spike on the network. This takes a few seconds.'
              : 'Nothing found yet. Is the laptop on and on this Wi-Fi? You can also scan the pairing code (pair_phone.bat on the laptop) or type its address.',
          style: context.tt.bodySmall,
        ),
      );
}
