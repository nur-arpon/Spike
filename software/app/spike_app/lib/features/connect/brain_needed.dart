/// "Spike needs his brain": the one friendly ask (onboarding v2, 4 Oct 2026).
///
/// The app opens straight into exploring, with no setup screen. When the owner does something that
/// needs Spike's brain (talk to him, memories, alarms, tricks, driving), the screen calls
/// [ensureBrain]. If a brain is ready it returns true at once; otherwise this sheet (a dialog on a
/// wide window) offers two clear ways to give him one:
///   1. a free Gemini key, pasted here (shape checked only: no network call, no quota spent);
///   2. scanning the pairing code on the owner's computer.
/// "More ways" opens the older same-Wi-Fi list and the type-an-address form. After success the
/// caller carries on with what the owner was doing; dismissing returns to exploring.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../away/ai/key_store.dart';
import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/motion.dart';
import '../../core/platform.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/client.dart';
import '../../protocol/names.dart' show defaultPort;
import '../../state/away.dart';
import '../../state/brain_ready.dart';
import '../../state/link.dart';
import '../../state/pairing_sync.dart';
import '../../state/settings.dart';
import 'connect_screen.dart' show EndpointTile;
import 'discovery.dart';
import 'pairing.dart';
import 'qr_sheet.dart';

const geminiKeyPage = 'https://aistudio.google.com/apikey';

/// What the owner was trying to do: it shapes the first line of the ask.
enum BrainReason {
  talk('To talk with Spike, he needs a brain to think with.'),
  remember('Spike keeps his memories in his brain, so he needs one first.'),
  // alarms are kept by the computer's brain only (the phone's own brain has none), so a Gemini key would not help
  alarms("Alarms and reminders are kept by Spike's brain on your computer, so link him to it first.", computerOnly: true),
  play('To do tricks and drive, Spike needs a brain to tell his body what to do.'),
  general('Spike needs a brain for this.');

  const BrainReason(this.line, {this.computerOnly = false});
  final String line;

  /// Only the computer's brain can do this: the Gemini key is not offered.
  final bool computerOnly;
}

/// True when a brain is ready (now, or after the owner gave Spike one in the sheet); false when the
/// owner dismissed it and is back to exploring. Never shown on the desktop (built-in brain).
Future<bool> ensureBrain(BuildContext context, WidgetRef ref, {BrainReason reason = BrainReason.general}) async {
  if (reason.computerOnly ? computerBrainReadyNow(ref) : brainReadyNow(ref)) return true;
  Haptics.tap();
  final wide = context.isWide || AppPlatform.desktop;
  final ok = wide
      ? await showDialog<bool>(
          context: context,
          useRootNavigator: true,
          builder: (_) => Dialog(
            clipBehavior: Clip.antiAlias,
            insetPadding: const EdgeInsets.all(Space.x6),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.card)),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: SingleChildScrollView(child: BrainNeededPanel(reason: reason)),
            ),
          ),
        )
      : await showModalBottomSheet<bool>(
          context: context,
          useRootNavigator: true, // above the tab bar
          isScrollControlled: true,
          useSafeArea: true,
          showDragHandle: true,
          builder: (_) => SingleChildScrollView(child: BrainNeededPanel(reason: reason)),
        );
  return ok == true;
}

class BrainNeededPanel extends ConsumerStatefulWidget {
  const BrainNeededPanel({super.key, this.reason = BrainReason.general});
  final BrainReason reason;
  @override
  ConsumerState<BrainNeededPanel> createState() => _BrainNeededPanelState();
}

class _BrainNeededPanelState extends ConsumerState<BrainNeededPanel> {
  final _key = TextEditingController();
  final _host = TextEditingController();
  final _port = TextEditingController(text: '$defaultPort');
  String? _problem;
  String? _note; // a plain-English progress / failure line for the computer link
  bool _busy = false;
  bool _done = false;
  bool _more = false;
  bool _address = false;

  @override
  void dispose() {
    _key.dispose();
    _host.dispose();
    _port.dispose();
    super.dispose();
  }

  void _finish() {
    Haptics.success();
    setState(() {
      _done = true;
      _busy = false;
    });
    Future.delayed(const Duration(milliseconds: 650), () {
      if (mounted) Navigator.of(context).pop(true);
    });
  }

  Future<void> _paste() async {
    final d = await Clipboard.getData(Clipboard.kTextPlain);
    if (d?.text != null && mounted) setState(() => _key.text = tidyKey(d!.text!));
  }

  Future<void> _openKeyPage() async {
    try {
      await launchUrl(Uri.parse(geminiKeyPage), mode: LaunchMode.externalApplication);
    } catch (_) {
      if (mounted) showToast(context, 'Open $geminiKeyPage in your browser', icon: Icons.link_rounded);
    }
  }

  /// Shape check only (away/ai/key_store.dart keyProblem), then keep it in the secure keystore.
  Future<void> _useKey() async {
    final key = tidyKey(_key.text);
    final problem = keyProblem('gemini', key);
    if (problem != null) {
      Haptics.error();
      setState(() => _problem = problem);
      return;
    }
    setState(() {
      _problem = null;
      _busy = true;
    });
    final refused = await ref.read(awayProvider.notifier).saveKey(key);
    if (!mounted) return;
    if (refused != null) {
      Haptics.error();
      setState(() {
        _problem = refused;
        _busy = false;
      });
      return;
    }
    _finish();
  }

  Future<void> _scan() async {
    final ep = await showQrSheet(context);
    if (ep != null && mounted) await _useComputer(ep);
  }

  /// Call the computer and wait (a few seconds) for it to answer.
  Future<void> _useComputer(BrainEndpoint ep) async {
    FocusScope.of(context).unfocus();
    final hub = ref.read(brainClientProvider);
    final before = ref.read(settingsProvider).endpoint;
    setState(() {
      _busy = true;
      _note = 'Calling your computer...';
    });
    final answer = Completer<LinkStatus?>();
    final sub = hub.lan.status.listen((s) {
      if ((s.isConnected || s.phase == LinkPhase.authFailed) && !answer.isCompleted) answer.complete(s);
    });
    hub.connect(ep);
    final s = await answer.future.timeout(const Duration(seconds: 15), onTimeout: () => null);
    await sub.cancel();
    if (!mounted) return;
    if (s != null && s.isConnected) {
      ref.read(settingsProvider.notifier).rememberEndpoint(s.endpoint ?? ep);
      _finish();
      return;
    }
    // give the earlier link back (or stop calling a wrong address)
    if (before != null) {
      hub.connect(before);
    } else {
      unawaited(hub.disconnect());
    }
    Haptics.error();
    setState(() {
      _busy = false;
      _note = s != null
          ? 'That code did not work. Show a fresh pairing code on your computer and scan it again.'
          : 'Spike could not reach your computer. Check it is on and on the same Wi-Fi.';
    });
  }

  void _useAddress() {
    final ep = parsePairing('${_host.text.trim()}:${_port.text.trim()}');
    if (ep == null) {
      Haptics.error();
      setState(() => _note = 'That address does not look right.');
      return;
    }
    _useComputer(ep);
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    return AnimatedPadding(
      duration: const Duration(milliseconds: 200),
      padding: EdgeInsets.fromLTRB(Space.x6, Space.x2, Space.x6, Space.x6 + bottom),
      child: AnimatedSwitcher(
        duration: const Duration(milliseconds: 350),
        switchInCurve: Springs.curve,
        child: _done ? _success(context) : _ask(context, p),
      ),
    );
  }

  Widget _ask(BuildContext context, SpikePalette p) {
    return Column(
      key: const ValueKey('ask'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Entrance(
          child: Row(children: [
            Container(
              width: 44,
              height: 44,
              decoration: BoxDecoration(color: p.accent.withValues(alpha: 0.14), shape: BoxShape.circle),
              child: Icon(Icons.psychology_alt_rounded, color: p.accent, size: 26),
            ),
            const SizedBox(width: Space.x3),
            Expanded(child: Text('Spike needs his brain', style: context.tt.titleLarge)),
            // always in reach, even when the sheet is taller than a small screen
            IconButton(
              tooltip: 'Keep exploring',
              onPressed: () => Navigator.of(context).pop(false),
              icon: Icon(Icons.close_rounded, color: p.muted),
            ),
          ]),
        ),
        const SizedBox(height: Space.x3),
        Entrance(
          index: 1,
          child: Text(
            widget.reason.line,
            style: context.tt.bodyMedium?.copyWith(color: p.muted),
          ),
        ),
        const SizedBox(height: Space.x4),
        if (!widget.reason.computerOnly) Entrance(index: 2, child: _keyCard(context)),
        if (AppPlatform.qrScanner) ...[
          SizedBox(height: widget.reason.computerOnly ? 0 : Space.x3),
          Entrance(index: 3, child: _scanCard(context)),
        ],
        if (_note != null)
          Padding(
            padding: const EdgeInsets.only(top: Space.x3),
            child: Text(_note!, key: const Key('brain_note'), style: context.tt.bodySmall?.copyWith(color: _busy ? p.muted : Brand.tongue)),
          ),
        const SizedBox(height: Space.x2),
        Align(
          alignment: Alignment.center,
          child: TextButton(
            onPressed: () {
              Haptics.tick();
              setState(() => _more = !_more);
            },
            child: Text(_more ? 'Fewer ways' : 'More ways'),
          ),
        ),
        AnimatedSize(
          duration: const Duration(milliseconds: 380),
          curve: Springs.smoothCurve,
          alignment: Alignment.topCenter,
          child: _more ? _moreWays(context) : const SizedBox(width: double.infinity),
        ),
      ],
    );
  }

  Widget _success(BuildContext context) {
    final p = context.sp;
    return Padding(
      key: const ValueKey('done'),
      padding: const EdgeInsets.symmetric(vertical: Space.x8),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        const Icon(Icons.check_circle_rounded, color: Brand.ok, size: 56),
        const SizedBox(height: Space.x3),
        Text('Spike has his brain', style: context.tt.titleLarge),
        const SizedBox(height: Space.x1),
        Text('Picking up where you left off...', style: context.tt.bodyMedium?.copyWith(color: p.muted)),
      ]),
    );
  }

  Widget _scanCard(BuildContext context) {
    final p = context.sp;
    return SpikeCard(
      padding: const EdgeInsets.all(Space.x4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.qr_code_scanner_rounded, color: p.accent),
          const SizedBox(width: Space.x3),
          Expanded(child: Text('Scan the code on your computer', style: context.tt.titleMedium)),
        ]),
        const SizedBox(height: Space.x1),
        Text('Open Spike on your computer and show its code.', style: context.tt.bodySmall),
        const SizedBox(height: Space.x3),
        PillButton(label: 'Scan the code', icon: Icons.qr_code_scanner_rounded, onTap: _busy ? null : _scan),
      ]),
    );
  }

  Widget _keyCard(BuildContext context) {
    final p = context.sp;
    return SpikeCard(
      padding: const EdgeInsets.all(Space.x4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Icon(Icons.key_rounded, color: p.accent),
          const SizedBox(width: Space.x3),
          Expanded(child: Text('Use a free Gemini key', style: context.tt.titleMedium)),
        ]),
        const SizedBox(height: Space.x1),
        Text("Free from Google. It stays on this phone, in its secure storage.", style: context.tt.bodySmall),
        const SizedBox(height: Space.x3),
        TextField(
          key: const Key('brain_key_field'),
          controller: _key,
          enabled: !_busy,
          autocorrect: false,
          enableSuggestions: false,
          obscureText: true,
          onChanged: (_) {
            if (_problem != null) setState(() => _problem = null);
          },
          onSubmitted: (_) => _useKey(),
          decoration: InputDecoration(
            hintText: 'Paste your key here',
            errorText: _problem,
            suffixIcon: IconButton(tooltip: 'Paste', onPressed: _busy ? null : _paste, icon: const Icon(Icons.content_paste_rounded)),
          ),
        ),
        const SizedBox(height: Space.x3),
        Wrap(alignment: WrapAlignment.spaceBetween, crossAxisAlignment: WrapCrossAlignment.center, runSpacing: Space.x2, children: [
          TextButton.icon(
            onPressed: _openKeyPage,
            icon: const Icon(Icons.open_in_new_rounded, size: 18),
            label: const Text('Get a free key'),
          ),
          PillButton(
            label: _busy && _note == null ? 'Saving...' : 'Use this key',
            icon: Icons.check_rounded,
            filled: true,
            onTap: _busy ? null : _useKey,
          ),
        ]),
      ]),
    );
  }

  Widget _moreWays(BuildContext context) {
    final p = context.sp;
    final s = ref.watch(settingsProvider);
    final found = ref.watch(discoveryProvider);
    return Padding(
      padding: const EdgeInsets.only(top: Space.x2),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Expanded(child: Text('Computers on this Wi-Fi', style: context.tt.titleSmall)),
          if (found.searching) SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.2, color: p.accent)),
        ]),
        const SizedBox(height: Space.x2),
        if (found.found.isEmpty)
          Text(found.searching ? 'Looking...' : 'No computer found yet. Is Spike open on it, on the same Wi-Fi?', style: context.tt.bodySmall)
        else
          for (final ep in found.found)
            EndpointTile(
              ep: PairingSync.withKnownToken(ep, s),
              icon: Icons.wifi_rounded,
              onTap: _busy ? () {} : () => _useComputer(PairingSync.withKnownToken(ep, s)),
            ),
        const SizedBox(height: Space.x1),
        TextButton.icon(
          onPressed: () => setState(() => _address = !_address),
          icon: Icon(_address ? Icons.expand_less_rounded : Icons.edit_rounded, size: 18),
          label: const Text("Type your computer's address"),
        ),
        if (_address) ...[
          Row(children: [
            Expanded(flex: 5, child: TextField(controller: _host, keyboardType: TextInputType.url, decoration: const InputDecoration(hintText: '192.168.1.20'))),
            const SizedBox(width: Space.x3),
            Expanded(flex: 2, child: TextField(controller: _port, keyboardType: TextInputType.number)),
          ]),
          const SizedBox(height: Space.x3),
          PillButton(label: 'Connect', icon: Icons.link_rounded, onTap: _busy ? null : _useAddress),
        ],
      ]),
    );
  }
}
