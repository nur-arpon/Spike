import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/features/connect/pairing.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:web_socket_channel/io.dart';

/// Reaching the laptop brain from any network (PROTOCOL.md 10.7): home Wi-Fi
/// first, then the laptop's Tailscale address, with the same token.
void main() {
  late HttpServer server;
  late List<String> tried;
  late Set<String> reachable;
  BrainClient? client;

  setUp(() async {
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((req) async {
      final ws = await WebSocketTransformer.upgrade(req);
      ws.listen((data) {
        final m = jsonDecode(data as String) as Map<String, dynamic>;
        if (m['type'] == 'hello' && m['token'] == 'tok') {
          ws.add(jsonEncode({'v': 1, 'type': 'hello', 'id': 1, 're': m['id'], 'server': 'spike-brain', 'version': '0.1.0',
            'heartbeat_s': 5, 'mode': 'dog'}));
        } else if (m['type'] == 'ping') {
          ws.add(jsonEncode({'v': 1, 'type': 'pong', 'id': 2, 're': m['id']}));
        }
      });
    });
    tried = [];
    reachable = {};
  });

  tearDown(() async {
    await client?.dispose();
    client = null;
    await server.close(force: true);
  });

  /// Every host resolves to the local fake brain only when [reachable] says so.
  BrainClient make() => client = BrainClient(
        identity: const ClientIdentity(deviceId: 'app-t', fw: '0.3.0', role: 'app'),
        random: Random(2),
        channelFactory: (uri) {
          tried.add(uri.host);
          if (!reachable.contains(uri.host)) throw const SocketException('No route to host');
          return IOWebSocketChannel.connect(uri.replace(host: '127.0.0.1'), connectTimeout: const Duration(seconds: 2));
        },
      );

  BrainEndpoint ep() => BrainEndpoint(host: '192.168.1.20', port: server.port, token: 'tok', alt: const ['100.64.0.7', 'laptop.tail1.ts.net']);

  Future<LinkStatus> connectedStatus(BrainClient c) =>
      c.status.firstWhere((s) => s.isConnected).timeout(const Duration(seconds: 5));

  test('on home Wi-Fi the LAN address is used: "Home Wi-Fi"', () async {
    reachable = {'192.168.1.20', '100.64.0.7'};
    final c = make();
    final done = connectedStatus(c);
    c.connect(ep());
    final s = await done;
    expect(s.host, '192.168.1.20');
    expect(s.viaAlt, isFalse);
    expect(s.routeLabel, 'Home Wi-Fi');
    expect(tried, ['192.168.1.20']);
  });

  test('away from home the Tailscale address answers at once, same token: "Connected from anywhere"', () async {
    reachable = {'100.64.0.7'};
    final c = make();
    final done = connectedStatus(c);
    final t0 = DateTime.now();
    c.connect(ep());
    final s = await done;
    expect(s.host, '100.64.0.7');
    expect(s.viaAlt, isTrue);
    expect(s.routeLabel, 'Connected from anywhere');
    expect(s.attempt, 0);
    expect(tried, ['192.168.1.20', '100.64.0.7']);
    expect(DateTime.now().difference(t0), lessThan(const Duration(milliseconds: 450)), reason: 'no backoff between addresses');
  });

  test('the MagicDNS name is the last try', () async {
    reachable = {'laptop.tail1.ts.net'};
    final c = make();
    final done = connectedStatus(c);
    c.connect(ep());
    expect((await done).host, 'laptop.tail1.ts.net');
    expect(tried, ['192.168.1.20', '100.64.0.7', 'laptop.tail1.ts.net']);
  });

  test('nothing answers: one backoff per round, and every round starts from home Wi-Fi', () async {
    final c = make();
    final retry = c.status.firstWhere((s) => s.phase == LinkPhase.retrying).timeout(const Duration(seconds: 3));
    c.connect(ep());
    final s = await retry;
    expect(s.attempt, 1);
    expect(tried, ['192.168.1.20', '100.64.0.7', 'laptop.tail1.ts.net']);
    await c.status.firstWhere((s) => s.phase == LinkPhase.retrying && s.attempt == 2).timeout(const Duration(seconds: 4));
    expect(tried.sublist(3, 6), ['192.168.1.20', '100.64.0.7', 'laptop.tail1.ts.net']);
  });

  test('an endpoint without Tailscale behaves exactly as before', () async {
    final c = make();
    final retry = c.status.firstWhere((s) => s.phase == LinkPhase.retrying).timeout(const Duration(seconds: 3));
    c.connect(BrainEndpoint(host: '192.168.1.20', port: server.port, token: 'tok'));
    await retry;
    expect(tried, ['192.168.1.20']);
  });

  test('pairing link: ts and tsname become fallback addresses, kept in settings JSON', () {
    final e = parsePairing('spike://pair?host=192.168.1.20&port=8765&token=abc&ts=100.64.0.7&tsname=laptop.tail1.ts.net&name=Spike')!;
    expect(e.host, '192.168.1.20');
    expect(e.alt, ['100.64.0.7', 'laptop.tail1.ts.net']);
    expect(e.hosts, ['192.168.1.20', '100.64.0.7', 'laptop.tail1.ts.net']);
    final back = BrainEndpoint.fromJson(jsonDecode(jsonEncode(e.toJson())) as Map<String, dynamic>)!;
    expect(back.sameRoutes(e), isTrue);
    // an old link (no Tailscale) and an old saved endpoint still work
    expect(parsePairing('spike://pair?host=192.168.1.20&port=8765&token=abc')!.alt, isEmpty);
    expect(BrainEndpoint.fromJson({'host': '192.168.1.20', 'port': 8765})!.alt, isEmpty);
    // a bad ts value is ignored, not trusted
    expect(parsePairing('spike://pair?host=192.168.1.20&ts=bad host&token=abc'), isNull, reason: 'a link with spaces is refused whole');
    expect(parsePairing('spike://pair?host=192.168.1.20&ts=bad%20host&token=abc')!.alt, isEmpty);
    // same brain, new fallback: equal (same brain) but not the same routes
    expect(e == e.withAlt(const []), isTrue);
    expect(e.sameRoutes(e.withAlt(const [])), isFalse);
  });

  test('a working connection is kept when the brain\'s Tailscale address is learnt later', () async {
    reachable = {'192.168.1.20'};
    final c = make();
    final done = connectedStatus(c);
    c.connect(BrainEndpoint(host: '192.168.1.20', port: server.port, token: 'tok'));
    await done;
    final n = tried.length;
    c.updateEndpoint(ep());
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(c.current.isConnected, isTrue);
    expect(c.current.endpoint!.alt, ['100.64.0.7', 'laptop.tail1.ts.net']);
    expect(tried.length, n, reason: 'no reconnect');
  });
}

