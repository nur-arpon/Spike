import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/platform.dart';
import '../features/connect/pairing.dart';
import '../protocol/client.dart';
import '../protocol/messages.dart';
import 'link.dart';
import 'settings.dart';

/// Protocol v1.2 pairing without a QR (PROTOCOL.md 10.7):
///
/// - Whenever the app is connected to a v1.2 brain it asks `pairing_get`. A
///   brain listening on the Wi-Fi answers with its pairing link (LAN address,
///   port, token), which is kept as [AppSettings.wifiPairing]. So a phone that
///   was plugged in once over USB (`adb reverse`, no token needed there) is
///   paired for Wi-Fi too.
/// - When the phone is on USB (127.0.0.1) and the link keeps failing (cable
///   pulled), the app moves to the Wi-Fi pairing by itself.
class PairingSync {
  PairingSync(this.ref) {
    final c = ref.read(brainClientProvider);
    _msgs = c.messages.listen(_onMessage);
    _status = c.status.listen(_onStatus);
  }

  final Ref ref;
  late final StreamSubscription<SpikeMessage> _msgs;
  late final StreamSubscription<LinkStatus> _status;

  /// USB attempts that failed before switching to Wi-Fi (0.5+1+2 s of backoff).
  static const usbGiveUpAfter = 3;

  void _onMessage(SpikeMessage m) {
    final c = ref.read(brainClientProvider);
    if (m is BrainHello && !c.legacyBrain) {
      c.send(const PairingGetMsg());
    } else if (m is PairingMsg) {
      ref.read(lastPairingProvider.notifier).set(m); // the desktop shows it as a QR (desktop_home.dart)
      if (!m.lan) return;
      final ep = parsePairing(m.url);
      if (ep == null || ep.token == null) return;
      final n = ref.read(settingsProvider.notifier);
      final s = ref.read(settingsProvider);
      // the brain in use learnt (or lost) its Tailscale address: keep trying it from now on
      final cur = s.endpoint;
      final refresh = cur != null && cur == ep && !cur.sameRoutes(ep);
      if ((s.wifiPairing?.sameRoutes(ep) ?? false) && !refresh) return;
      n.update((x) => x.copyWith(
            wifiPairing: ep,
            endpoint: refresh ? cur.withAlt(ep.alt) : null,
            recent: [ep, ...x.recent.where((e) => !(e.host == ep.host && e.port == ep.port))].take(5).toList(),
          ));
      if (refresh) c.updateEndpoint(cur.withAlt(ep.alt));
    }
  }

  void _onStatus(LinkStatus s) {
    if (AppPlatform.desktop) return; // the desktop's own brain is always on 127.0.0.1 (no USB to fail over from)
    final ep = s.endpoint;
    final wifi = ref.read(settingsProvider).wifiPairing;
    if (ep == null || wifi == null || s.phase != LinkPhase.retrying) return;
    final onUsb = ep.host == '127.0.0.1' || ep.host == 'localhost';
    if (onUsb && s.attempt >= usbGiveUpAfter) {
      ref.read(settingsProvider.notifier).update((x) => x.copyWith(endpoint: wifi));
      ref.read(brainClientProvider).connect(wifi);
    }
  }

  /// A brain found on the Wi-Fi: the token this phone already has for it, if any.
  static BrainEndpoint withKnownToken(BrainEndpoint found, AppSettings s) {
    if (found.token != null) return found;
    for (final e in [?s.wifiPairing, ...s.recent]) {
      if (e.host == found.host && e.port == found.port && e.token != null) {
        return BrainEndpoint(host: found.host, port: found.port, token: e.token, name: found.name, alt: e.alt);
      }
    }
    return found;
  }

  void dispose() {
    _msgs.cancel();
    _status.cancel();
  }
}

final pairingSyncProvider = Provider<PairingSync>((ref) {
  final p = PairingSync(ref);
  ref.onDispose(p.dispose);
  return p;
});

/// The brain's last answer to `pairing_get` (null until one came).
class LastPairing extends Notifier<PairingMsg?> {
  @override
  PairingMsg? build() => null;
  void set(PairingMsg m) => state = m;
}

final lastPairingProvider = NotifierProvider<LastPairing, PairingMsg?>(LastPairing.new);
