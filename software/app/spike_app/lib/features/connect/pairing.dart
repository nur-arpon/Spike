import '../../protocol/client.dart';
import '../../protocol/names.dart';

/// The pairing QR Spike will show (OPEN_QUESTIONS.md P4):
///
///   spike://pair?host=192.168.1.20&port=8765&token=SPIKE_TOKEN&name=Spike
///
/// Also accepted, so a hand-typed address works in the same parser:
///   ws://192.168.1.20:8765/?token=abc      192.168.1.20:8765      192.168.1.20
BrainEndpoint? parsePairing(String raw) {
  final text = raw.trim();
  if (text.isEmpty || RegExp(r'\s').hasMatch(text)) return null;
  Uri? u;
  if (text.startsWith('spike://') || text.startsWith('ws://') || text.startsWith('wss://')) {
    u = Uri.tryParse(text);
  } else if (text.contains('://')) {
    return null; // http(s):// or anything else is not Spike
  } else {
    u = Uri.tryParse('ws://$text');
  }
  if (u == null) return null;
  String? host;
  int? port;
  if (u.scheme == 'spike') {
    if (u.host != 'pair') return null;
    host = u.queryParameters['host'] ?? u.queryParameters['h'];
    port = int.tryParse(u.queryParameters['port'] ?? u.queryParameters['p'] ?? '');
  } else {
    host = u.host;
    port = u.hasPort ? u.port : null;
  }
  if (host == null || host.isEmpty || !_validHost(host)) return null;
  port ??= defaultPort;
  if (port <= 0 || port > 65535) return null;
  final token = u.queryParameters['token'] ?? u.queryParameters['t'];
  final name = u.queryParameters['name'];
  // PROTOCOL.md 10.7: the laptop's Tailscale address and MagicDNS name, tried after `host`
  final alt = [
    for (final k in const ['ts', 'tsname'])
      if (u.queryParameters[k] case final h? when h.isNotEmpty && h != host && _validHost(h)) h,
  ];
  return BrainEndpoint(host: host, port: port, token: (token?.isEmpty ?? true) ? null : token, name: name, alt: alt);
}

bool _validHost(String h) {
  final ipv4 = RegExp(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$').firstMatch(h);
  if (ipv4 != null) {
    return [1, 2, 3, 4].every((i) => int.parse(ipv4.group(i)!) <= 255);
  }
  return RegExp(r'^[A-Za-z0-9]([A-Za-z0-9\-\.]{0,251}[A-Za-z0-9])?$').hasMatch(h);
}
