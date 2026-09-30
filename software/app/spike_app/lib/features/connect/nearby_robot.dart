import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../away/transport/ble_link.dart';
import '../../core/haptics.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../state/away.dart';
import '../../state/settings.dart';

/// Pair the robot over Bluetooth LE for away from home (protocol v1.3). The
/// permission prompt, and the passkey dialog, are Android's own: the owner
/// decides. Nothing is scanned until he taps "Find".
class NearbyRobotCard extends ConsumerStatefulWidget {
  const NearbyRobotCard({super.key});
  @override
  ConsumerState<NearbyRobotCard> createState() => _NearbyRobotCardState();
}

class _NearbyRobotCardState extends ConsumerState<NearbyRobotCard> {
  final List<FoundRobot> _found = [];
  StreamSubscription<FoundRobot>? _scan;
  bool _scanning = false;
  String? _note;

  @override
  void dispose() {
    _scan?.cancel();
    super.dispose();
  }

  Future<void> _find() async {
    Haptics.tap();
    final ble = ref.read(bleLinkProvider);
    if (!await ble.ensurePermissions()) {
      setState(() => _note = 'Spike needs the Nearby devices (Bluetooth) permission to find him.');
      return;
    }
    ref.read(awayProvider.notifier).retryRobot();
    setState(() {
      _found.clear();
      _scanning = true;
      _note = null;
    });
    await _scan?.cancel();
    _scan = ble.scan().listen(
      (r) {
        if (!_found.any((f) => f.deviceId == r.deviceId)) setState(() => _found.add(r));
      },
      onError: (_) => setState(() {
        _scanning = false;
        _note = 'Bluetooth could not search. Is it switched on?';
      }),
      onDone: () => setState(() {
        _scanning = false;
        if (_found.isEmpty) _note = 'No Spike nearby. Is he switched on and close to the phone?';
      }),
    );
  }

  Future<void> _use(FoundRobot r) async {
    Haptics.confirm();
    await _scan?.cancel();
    setState(() => _scanning = false);
    await ref.read(awayProvider.notifier).useRobot(r);
    if (mounted) {
      showToast(context, 'When your phone asks, type the 6-digit code on ${r.name}\'s screen', icon: Icons.pin_rounded);
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final s = ref.watch(settingsProvider);
    final away = ref.watch(awayProvider);
    final paired = s.robotId != null;
    final stateText = switch (away.robot) {
      RobotConn.connected => 'Connected over Bluetooth',
      RobotConn.needsPermission => 'Needs the Bluetooth permission',
      RobotConn.bluetoothOff => 'Bluetooth is off',
      RobotConn.connecting || RobotConn.pairing => 'Connecting...',
      RobotConn.failed => 'Not in reach right now',
      _ => away.away ? 'Looking for him...' : 'Used when you are away from home',
    };
    return SpikeCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.bluetooth_rounded, color: p.accent, size: 28),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('Spike nearby (Bluetooth)', style: context.tt.titleMedium),
              Text('Away from home your phone becomes his brain', style: context.tt.bodySmall),
            ]),
          ),
        ]),
        const SizedBox(height: 12),
        if (paired)
          Row(children: [
            Icon(away.robot == RobotConn.connected ? Icons.check_circle_rounded : Icons.pets_rounded,
                color: away.robot == RobotConn.connected ? Brand.ok : p.muted, size: 20),
            const SizedBox(width: 8),
            Expanded(
              child: Text('${s.robotName ?? 'Spike'} · $stateText', style: context.tt.bodyMedium),
            ),
            TextButton(
              onPressed: () {
                Haptics.tap();
                ref.read(awayProvider.notifier).forgetRobot();
              },
              child: const Text('Forget'),
            ),
          ]),
        for (final r in _found)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.pets_rounded),
            title: Text(r.name),
            subtitle: Text(r.rssi == null ? 'Nearby' : (r.rssi! > -65 ? 'Very close' : 'In range')),
            trailing: const Icon(Icons.chevron_right_rounded),
            onTap: () => _use(r),
          ),
        if (_note != null)
          Padding(
            padding: const EdgeInsets.only(top: 6, bottom: 4),
            child: Text(_note!, style: context.tt.bodySmall?.copyWith(color: p.muted)),
          ),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(
            child: PillButton(
              label: _scanning ? 'Searching...' : (paired ? 'Find again' : 'Find Spike nearby'),
              icon: Icons.bluetooth_searching_rounded,
              onTap: _scanning ? null : _find,
            ),
          ),
        ]),
      ]),
    );
  }
}
