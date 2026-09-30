/// "Set up a robot": gives a robot in setup mode the home Wi-Fi and this computer's address
/// (robot_setup.dart has the portal protocol). Three steps: the home Wi-Fi password -> join the
/// robot's setup Wi-Fi in Windows (we never switch networks ourselves) -> the app sends it.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../core/haptics.dart';
import '../core/theme.dart';
import '../core/widgets.dart';
import '../protocol/client.dart';
import 'desktop_home.dart' show currentWifiName, openLink;
import 'robot_setup.dart';

enum _Step { details, join, sending, done, failed }

class RobotSetupDialog extends StatefulWidget {
  const RobotSetupDialog({super.key, required this.brain, this.portal});

  /// This computer's pairing (home Wi-Fi address, port, token): what the robot will connect to.
  final BrainEndpoint brain;
  final RobotPortal? portal; // tests pass a fake
  @override
  State<RobotSetupDialog> createState() => _RobotSetupDialogState();
}

class _RobotSetupDialogState extends State<RobotSetupDialog> {
  final _ssid = TextEditingController();
  final _pass = TextEditingController();
  late final RobotPortal _portal = widget.portal ?? RobotPortal();
  _Step _step = _Step.details;
  bool _cancelled = false;
  PortalInfo? _found;
  String? _robotId; // the screen board's id, for the camera board that follows
  bool _hidePass = true;

  @override
  void initState() {
    super.initState();
    _ssid.addListener(() => setState(() {}));
    unawaited(currentWifiName().then((n) {
      if (mounted && _ssid.text.isEmpty && !n.toLowerCase().startsWith('spike-')) _ssid.text = n;
    }));
  }

  @override
  void dispose() {
    _cancelled = true;
    _ssid.dispose();
    _pass.dispose();
    if (widget.portal == null) _portal.close();
    super.dispose();
  }

  Future<void> _lookForRobot() async {
    setState(() => _step = _Step.join);
    final found = await waitForPortal(_portal, cancelled: () => _cancelled || !mounted);
    if (!mounted || _cancelled) return;
    if (found == null) {
      setState(() => _step = _Step.failed);
      return;
    }
    _found = found;
    if (found.board == PortalBoard.screen && found.deviceId != null) _robotId = found.deviceId;
    setState(() => _step = _Step.sending);
    final ok = await _portal.save(portalForm(
      board: found.board,
      ssid: _ssid.text.trim(),
      password: _pass.text,
      brainHost: widget.brain.host,
      brainPort: widget.brain.port,
      token: widget.brain.token ?? '',
      robotId: _robotId,
    ));
    if (!mounted) return;
    ok ? Haptics.success() : Haptics.error();
    setState(() => _step = ok ? _Step.done : _Step.failed);
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return AlertDialog(
      title: const Text('Set up a robot'),
      content: SizedBox(
        width: 520,
        child: AnimatedSwitcher(
          duration: const Duration(milliseconds: 300),
          child: switch (_step) {
            _Step.details => Column(key: const ValueKey('details'), mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Text('Switch the robot on. With no Wi-Fi saved it opens a Wi-Fi called "Spike-Setup-..." for 15 minutes '
                    '(the camera board\'s is "Spike-Cam-Setup-...").', style: context.tt.bodyMedium),
                const SizedBox(height: 16),
                TextField(controller: _ssid, decoration: const InputDecoration(labelText: 'Your home Wi-Fi name (2.4 GHz)')),
                const SizedBox(height: 10),
                TextField(
                  controller: _pass,
                  obscureText: _hidePass,
                  autocorrect: false,
                  enableSuggestions: false,
                  decoration: InputDecoration(
                    labelText: 'Its password',
                    suffixIcon: IconButton(
                      tooltip: _hidePass ? 'Show' : 'Hide',
                      icon: Icon(_hidePass ? Icons.visibility_rounded : Icons.visibility_off_rounded),
                      onPressed: () => setState(() => _hidePass = !_hidePass),
                    ),
                  ),
                ),
                const SizedBox(height: 10),
                Text('The robot will connect to this computer at ${widget.brain.host}:${widget.brain.port}. '
                    'The password goes only to the robot; it is not saved here.', style: context.tt.bodySmall),
              ]),
            _Step.join => Column(key: const ValueKey('join'), mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Text('Now join the robot\'s setup Wi-Fi: open the Wi-Fi menu at the bottom right of the screen and pick '
                    '"Spike-Setup-..." (or "Spike-Cam-Setup-..." for the camera).', style: context.tt.bodyMedium),
                const SizedBox(height: 16),
                Row(children: [
                  SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.4, color: p.accent)),
                  const SizedBox(width: 12),
                  Expanded(child: Text('Looking for the robot...', style: context.tt.bodyMedium)),
                ]),
                const SizedBox(height: 14),
                Wrap(children: [
                  PillButton(label: 'Open the Wi-Fi menu', icon: Icons.wifi_rounded, onTap: () => openLink('ms-availablenetworks:')),
                ]),
              ]),
            _Step.sending => Row(key: const ValueKey('sending'), children: [
                SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2.4, color: p.accent)),
                const SizedBox(width: 12),
                const Expanded(child: Text('Found it. Sending your Wi-Fi and this computer\'s address...')),
              ]),
            _Step.done => Column(key: const ValueKey('done'), mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  const Icon(Icons.check_circle_rounded, color: Brand.ok),
                  const SizedBox(width: 10),
                  Expanded(
                      child: Text(_found?.board == PortalBoard.camera ? 'The camera is set up.' : 'The robot is set up.',
                          style: context.tt.titleMedium)),
                ]),
                const SizedBox(height: 10),
                Text('It restarts and joins your Wi-Fi, then connects here by itself. Windows goes back to your home '
                    'Wi-Fi on its own; if it does not, pick it in the Wi-Fi menu.', style: context.tt.bodyMedium),
                if (_found?.board == PortalBoard.screen) ...[
                  const SizedBox(height: 10),
                  Text('The camera board has its own setup Wi-Fi. Set it up the same way next.', style: context.tt.bodySmall),
                ],
              ]),
            _Step.failed => Column(key: const ValueKey('failed'), mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                Row(children: [
                  const Icon(Icons.info_outline_rounded, color: Brand.warn),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(_found == null ? 'No robot found' : 'The robot did not take the settings', style: context.tt.titleMedium),
                  ),
                ]),
                const SizedBox(height: 10),
                Text(
                    _found == null
                        ? 'Check that this computer is on the robot\'s "Spike-Setup-..." Wi-Fi. The setup Wi-Fi closes after '
                            '15 minutes: switching the robot off and on opens it again.'
                        : 'Try again. If it keeps failing, restart the robot to open its setup Wi-Fi again.',
                    style: context.tt.bodyMedium),
              ]),
          },
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(_step == _Step.done ? 'Close' : 'Cancel')),
        if (_step == _Step.details)
          FilledButton(
            onPressed: _ssid.text.trim().isEmpty ? null : _lookForRobot,
            child: const Text('Next'),
          ),
        if (_step == _Step.failed) FilledButton(onPressed: _lookForRobot, child: const Text('Try again')),
        if (_step == _Step.done && _found?.board == PortalBoard.screen)
          FilledButton(onPressed: _lookForRobot, child: const Text('Set up the camera')),
      ],
    );
  }
}
