/// Desktop layout pieces (software/app/DESIGN.md "Desktop"): the centred page frame, and the "Phone and robot" page (pairing QR + typed address, reaching Spike from
/// anywhere with Tailscale, and first-time robot Wi-Fi setup).
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/brand.dart';
import '../core/haptics.dart';
import '../core/layout.dart';
import '../core/platform.dart';
import '../core/theme.dart';
import '../core/widgets.dart';
import '../features/connect/pairing.dart';
import '../protocol/client.dart';
import '../state/link.dart';
import '../state/pairing_sync.dart';
import '../state/settings.dart';
import 'desktop_page.dart';
import 'robot_setup_dialog.dart';

// ---------------------------------------------------------------- frame

/// On a wide window, the page is centred at a comfortable width (the phone layouts stay readable
/// and nothing stretches edge to edge). On a phone it is the page itself.
class DesktopFrame extends StatelessWidget {
  const DesktopFrame({super.key, required this.child, this.maxWidth = 1080});
  final Widget child;
  final double maxWidth;

  @override
  Widget build(BuildContext context) {
    if (!AppPlatform.desktop) return child;
    return ColoredBox(
      color: context.sp.bg,
      child: Center(child: ConstrainedBox(constraints: BoxConstraints(maxWidth: maxWidth), child: child)),
    );
  }
}

// ---------------------------------------------------------------- phone and robot

Future<void> openLink(String url) async {
  try {
    await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
  } catch (_) {}
}

class PhoneAndRobotScreen extends ConsumerWidget {
  const PhoneAndRobotScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pairing = ref.watch(lastPairingProvider);
    final link = ref.watch(linkStatusProvider).value ?? const LinkStatus();
    final spike = ref.watch(spikeStateProvider);
    final ep = pairing != null && pairing.lan ? parsePairing(pairing.url) : null;
    final name = ref.watch(settingsProvider.select((s) => s.dogName));
    final phone = <Widget>[
      PaneTitle('Your phone', subtitle: 'Pair the ${AppBrand.productName} app on your phone with this computer', first: true),
      _PairCard(url: pairing?.lan == true ? pairing!.url : null, ep: ep, connected: link.isConnected),
      const SizedBox(height: Space.x4),
      _AnywhereCard(ep: ep),
      const SizedBox(height: Space.x4),
      const _NetworkHelpCard(),
    ];
    List<Widget> robotPane({required bool first}) => [
      PaneTitle('Your robot', subtitle: '$name\'s body joins your home Wi-Fi once, then finds it here', first: first),
      SpikeCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Icon(spike.robotOnline ? Icons.smart_toy_rounded : Icons.smart_toy_outlined,
                color: spike.robotOnline ? Brand.ok : context.sp.muted),
            const SizedBox(width: Space.x3),
            Expanded(
              child: Text(spike.robotOnline ? 'The robot is connected' : 'No robot connected right now', style: context.tt.titleMedium),
            ),
            if (spike.robotOnline) const StatusPill(label: 'Online', dot: Brand.ok),
          ]),
          const SizedBox(height: Space.x2),
          Text(
              'A new robot (or one that cannot find its Wi-Fi) opens its own setup Wi-Fi for 15 minutes. '
              'This computer can give it your home Wi-Fi and its own address, so it connects here.',
              style: context.tt.bodySmall),
          const SizedBox(height: Space.x4),
          Wrap(spacing: Space.x2, runSpacing: Space.x2, children: [
            PillButton(
              label: 'Set up a robot',
              icon: Icons.wifi_tethering_rounded,
              filled: true,
              onTap: ep == null ? null : () => showDialog<void>(context: context, builder: (_) => RobotSetupDialog(brain: ep)),
            ),
          ]),
          if (ep == null)
            Padding(
              padding: const EdgeInsets.only(top: Space.x2),
              child: Text('Needs this computer on your home Wi-Fi first.', style: context.tt.bodySmall),
            ),
        ]),
      ),
      const SizedBox(height: Space.x4),
      const _RobotHelpCard(),
    ];
    return DesktopPage(
      title: 'Phone and robot',
      body: (context, room) {
        final m = context.metrics;
        if (room.maxWidth < 1100) {
          return Align(
            alignment: Alignment.topLeft,
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: DesktopMetrics.readingMax + Space.x16),
              child: ListView(padding: EdgeInsets.zero, children: [...phone, ...robotPane(first: false)]),
            ),
          );
        }
        // the phone is what people do here first (61.8 %); the robot is set up once (38.2 %)
        final (main, side) = goldenSplit(room.maxWidth, m.gutter);
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: main, child: ListView(padding: EdgeInsets.zero, children: phone)),
          SizedBox(width: m.gutter),
          SizedBox(width: side, child: ListView(padding: EdgeInsets.zero, children: robotPane(first: true))),
        ]);
      },
    );
  }
}
class _PairCard extends StatefulWidget {
  const _PairCard({required this.url, required this.ep, required this.connected});
  final String? url;
  final BrainEndpoint? ep;
  final bool connected;
  @override
  State<_PairCard> createState() => _PairCardState();
}

class _PairCardState extends State<_PairCard> {
  bool _showCode = false;

  void _copy(String what, String text) {
    Clipboard.setData(ClipboardData(text: text));
    Haptics.confirm();
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(SnackBar(content: Text('$what copied')));
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final url = widget.url;
    final ep = widget.ep;
    if (url == null || ep == null) {
      return SpikeCard(
        child: Row(children: [
          if (!widget.connected) ...[
            SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2.5, color: p.accent)),
            const SizedBox(width: 14),
          ] else ...[
            Icon(Icons.wifi_off_rounded, color: p.muted),
            const SizedBox(width: 14),
          ],
          Expanded(
            child: Text(
                widget.connected
                    ? 'This computer is not on a network right now. Connect it to your home Wi-Fi to pair a phone.'
                    : 'Starting Spike\'s brain...',
                style: context.tt.bodyMedium),
          ),
        ]),
      );
    }
    return SpikeCard(
      child: LayoutBuilder(builder: (context, c) {
        final qr = Container(
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22)),
          child: QrImageView(
            data: url,
            size: 208,
            padding: EdgeInsets.zero,
            backgroundColor: Colors.white,
            eyeStyle: const QrEyeStyle(eyeShape: QrEyeShape.square, color: Brand.chocolate),
            dataModuleStyle: const QrDataModuleStyle(dataModuleShape: QrDataModuleShape.square, color: Brand.chocolate),
            semanticsLabel: 'Pairing code for the phone app',
          ),
        );
        final steps = Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Scan it with your phone', style: context.tt.titleMedium),
          const SizedBox(height: 8),
          for (final (i, t) in [
            'Open the ${AppBrand.productName} app on your phone.',
            'Go to Connect, then Scan the pairing code.',
            'Point the phone at this code.',
          ].indexed)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                CircleAvatar(radius: 11, backgroundColor: p.accent, child: Text('${i + 1}', style: context.tt.labelSmall?.copyWith(color: p.accentInk))),
                const SizedBox(width: 10),
                Expanded(child: Text(t, style: context.tt.bodyMedium)),
              ]),
            ),
          const SizedBox(height: 10),
          Text('On the same Wi-Fi the app also finds Spike by itself. Or type these in the app:',
              style: context.tt.bodySmall),
          const SizedBox(height: 8),
          _Field(label: 'Address', value: ep.host, onCopy: () => _copy('Address', ep.host)),
          _Field(label: 'Port', value: '${ep.port}', onCopy: () => _copy('Port', '${ep.port}')),
          if (ep.token != null)
            _Field(
              label: 'Pairing code',
              value: _showCode ? ep.token! : '•' * 12,
              onCopy: () => _copy('Pairing code', ep.token!),
              trailing: IconButton(
                tooltip: _showCode ? 'Hide' : 'Show',
                icon: Icon(_showCode ? Icons.visibility_off_rounded : Icons.visibility_rounded, size: 20),
                onPressed: () => setState(() => _showCode = !_showCode),
              ),
            ),
        ]);
        if (c.maxWidth < 560) {
          return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [Center(child: qr), const SizedBox(height: 16), steps]);
        }
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [qr, const SizedBox(width: 24), Expanded(child: steps)]);
      }),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.label, required this.value, required this.onCopy, this.trailing});
  final String label;
  final String value;
  final VoidCallback onCopy;
  final Widget? trailing;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 2),
        child: Row(children: [
          SizedBox(width: 110, child: Text(label, style: context.tt.bodySmall)),
          Expanded(child: SelectableText(value, style: context.tt.titleSmall?.copyWith(fontFeatures: const [FontFeature.tabularFigures()]))),
          ?trailing,
          IconButton(tooltip: 'Copy', icon: const Icon(Icons.copy_rounded, size: 18), onPressed: onCopy),
        ]),
      );
}

class _AnywhereCard extends StatelessWidget {
  const _AnywhereCard({required this.ep});
  final BrainEndpoint? ep;
  @override
  Widget build(BuildContext context) {
    final on = ep?.alt.isNotEmpty ?? false;
    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.public_rounded, color: on ? Brand.ok : context.sp.accent),
          const SizedBox(width: 12),
          Expanded(child: Text('Reach Spike from anywhere', style: context.tt.titleMedium)),
          if (on) const StatusPill(label: 'Tailscale on', dot: Brand.ok),
        ]),
        const SizedBox(height: 8),
        Text(
            on
                ? 'Tailscale is running here (${ep!.alt.first}). Your phone reaches Spike from any network when Tailscale '
                    'runs on it too, signed in to the same account. Pair (or pair again) after installing it on the phone.'
                : 'Away from home your phone can still talk to Spike on this computer through Tailscale, a free private '
                    'network: install it on this computer and on your phone, sign in to the same account on both, then '
                    'pair the phone again here. Nothing is opened to the internet.',
            style: context.tt.bodySmall),
        if (!on) ...[
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            PillButton(label: 'Get Tailscale', icon: Icons.open_in_new_rounded, onTap: () => openLink('https://tailscale.com/download')),
          ]),
        ],
      ]),
    );
  }
}

class _RobotHelpCard extends StatelessWidget {
  const _RobotHelpCard();
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    const steps = [
      (Icons.wifi_rounded, 'The robot needs a 2.4 GHz Wi-Fi (most home routers have one).'),
      (Icons.router_rounded, 'The robot and this computer must be on the same Wi-Fi.'),
      (Icons.shield_outlined, 'Windows must treat that Wi-Fi as a Private network.'),
      (Icons.restart_alt_rounded, 'Still nothing? Switch the robot off and on: its setup Wi-Fi opens again for 15 minutes.'),
    ];
    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.help_outline_rounded, color: p.accent),
          const SizedBox(width: Space.x3),
          Expanded(child: Text('If the robot doesn\'t connect', style: context.tt.titleMedium)),
        ]),
        const SizedBox(height: Space.x2),
        for (final (icon, text) in steps)
          Padding(
            padding: const EdgeInsets.only(top: Space.x2),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(icon, size: 18, color: p.muted),
              const SizedBox(width: Space.x3),
              Expanded(child: Text(text, style: context.tt.bodySmall)),
            ]),
          ),
      ]),
    );
  }
}

class _NetworkHelpCard extends StatelessWidget {
  const _NetworkHelpCard();
  @override
  Widget build(BuildContext context) => SpikeCard(
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Row(children: [
            Icon(Icons.help_outline_rounded, color: context.sp.accent),
            const SizedBox(width: 12),
            Expanded(child: Text('If the phone can\'t find Spike', style: context.tt.titleMedium)),
          ]),
          const SizedBox(height: 8),
          Text(
              'Both must be on the same Wi-Fi, and Windows must treat this Wi-Fi as a Private network (Settings > '
              'Network & internet > Wi-Fi > your network > Private). ${AppBrand.productName} only accepts connections '
              'on Private networks, and only from devices that have the pairing code.',
              style: context.tt.bodySmall),
          const SizedBox(height: 12),
          Wrap(spacing: 8, runSpacing: 8, children: [
            PillButton(label: 'Open Wi-Fi settings', icon: Icons.settings_ethernet_rounded, onTap: () => openLink('ms-settings:network-wifi')),
          ]),
        ]),
      );
}

/// The Wi-Fi this computer is on now (read-only: `netsh wlan show interfaces`), or ''.
Future<String> currentWifiName() async {
  if (!Platform.isWindows) return '';
  try {
    final r = await Process.run('netsh', ['wlan', 'show', 'interfaces']).timeout(const Duration(seconds: 4));
    final m = RegExp(r'^\s*SSID\s*:\s*(.+)$', multiLine: true).firstMatch('${r.stdout}');
    return m?.group(1)?.trim() ?? '';
  } catch (_) {
    return '';
  }
}
