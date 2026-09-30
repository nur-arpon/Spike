import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:nsd/nsd.dart' as nsd;

import '../../protocol/client.dart';

/// mDNS / DNS-SD service type Spike's brain will advertise (OPEN_QUESTIONS P4).
const spikeServiceType = '_spike._tcp';

@immutable
class DiscoveryState {
  const DiscoveryState({this.found = const [], this.searching = false, this.error});
  final List<BrainEndpoint> found;
  final bool searching;
  final String? error;
}

/// Looks for brains on the Wi-Fi while something is watching it.
class DiscoveryNotifier extends Notifier<DiscoveryState> {
  nsd.Discovery? _d;
  Timer? _stopTimer;

  @override
  DiscoveryState build() {
    ref.onDispose(_stop);
    Future.microtask(start);
    return const DiscoveryState(searching: true);
  }

  Future<void> start() async {
    await _stop();
    state = DiscoveryState(found: state.found, searching: true);
    try {
      final d = await nsd.startDiscovery(spikeServiceType, ipLookupType: nsd.IpLookupType.v4);
      _d = d;
      d.addListener(() => _publish(d));
      _publish(d);
      // a scan does not need to run forever: stop after 20 s, the user can rescan
      _stopTimer = Timer(const Duration(seconds: 20), () async {
        await _stop();
        state = DiscoveryState(found: state.found, searching: false);
      });
    } catch (e) {
      state = DiscoveryState(found: state.found, searching: false, error: 'Wi-Fi search is not available ($e)');
    }
  }

  void _publish(nsd.Discovery d) {
    final out = <BrainEndpoint>[];
    for (final s in d.services) {
      final addr = s.addresses?.where((a) => a.address.isNotEmpty).firstOrNull?.address ?? s.host;
      if (addr == null || s.port == null) continue;
      String? txt(String k) {
        final v = s.txt?[k];
        return v == null ? null : utf8.decode(v, allowMalformed: true);
      }

      out.add(BrainEndpoint(host: addr, port: s.port!, name: txt('name') ?? s.name));
    }
    state = DiscoveryState(found: out, searching: _d != null);
  }

  Future<void> _stop() async {
    _stopTimer?.cancel();
    _stopTimer = null;
    final d = _d;
    _d = null;
    if (d != null) {
      try {
        await nsd.stopDiscovery(d);
      } catch (_) {}
    }
  }
}

final discoveryProvider = NotifierProvider.autoDispose<DiscoveryNotifier, DiscoveryState>(DiscoveryNotifier.new);
