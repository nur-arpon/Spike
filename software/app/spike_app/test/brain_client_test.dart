import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/protocol/messages.dart';
import 'package:spike_app/protocol/names.dart';

/// A tiny fake brain on a real local WebSocket, so the client is tested
/// against real frames, close codes and timing.
class FakeBrain {
  late HttpServer server;
  final received = <Map<String, dynamic>>[];
  final sockets = <WebSocket>[];
  String? requireToken;
  bool answerHello = true;
  bool mute = false; // stop answering anything (a hung brain)
  bool refuseAppRole = false; // behave like a v1.1 brain (no role "app")
  int helloCount = 0;
  final _rx = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get rx => _rx.stream;

  Future<void> start() async {
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((req) async {
      final ws = await WebSocketTransformer.upgrade(req);
      sockets.add(ws);
      var out = 0;
      ws.listen((data) {
        final m = jsonDecode(data as String) as Map<String, dynamic>;
        received.add(m);
        _rx.add(m);
        if (mute) return;
        if (m['type'] == 'hello') {
          helloCount++;
          if (requireToken != null && m['token'] != requireToken) {
            safeAdd(ws, jsonEncode({'v': 1, 'type': 'error', 'id': ++out, 're': m['id'], 'code': 'auth'}));
            ws.close(CloseCodes.auth, 'bad token');
            return;
          }
          if (refuseAppRole && m['role'] == 'app') {
            safeAdd(ws, jsonEncode({'v': 1, 'type': 'error', 'id': ++out, 're': m['id'], 'code': 'bad_value',
              'message': "hello.role: 'app' is not allowed"}));
            ws.close(CloseCodes.helloTimeout, 'bad hello');
            return;
          }
          if (!answerHello) return;
          safeAdd(ws, jsonEncode({
            'v': 1, 'type': 'hello', 'id': ++out, 're': m['id'], 'server': 'spike-brain', 'version': '0.1.0',
            'heartbeat_s': 1, 'mode': 'dog', 'names': {'dog': 'Spike', 'cat': 'Spicy'},
          }));
          safeAdd(ws, jsonEncode({'v': 1, 'type': 'mood', 'id': ++out, 'mood': 'happy'}));
        } else if (m['type'] == 'ping') {
          safeAdd(ws, jsonEncode({'v': 1, 'type': 'pong', 'id': ++out, 're': m['id']}));
        }
      });
    });
  }

  static void safeAdd(WebSocket ws, String text) {
    if (ws.closeCode != null) return;
    try {
      ws.add(text);
    } catch (_) {/* closing */}
  }

  int get port => server.port;
  void sendAll(Map<String, dynamic> m) {
    for (final s in sockets) {
      safeAdd(s, jsonEncode(m));
    }
  }

  Future<void> dropAll([int code = 1001]) async {
    for (final s in sockets) {
      await s.close(code);
    }
  }

  Future<void> stop() async {
    await dropAll(1000);
    await server.close(force: true);
    await _rx.close();
  }
}

Future<T> waitFor<T>(Stream<T> s, bool Function(T) test, {Duration timeout = const Duration(seconds: 5)}) =>
    s.firstWhere(test).timeout(timeout);

void main() {
  late FakeBrain brain;
  late BrainClient client;

  setUp(() async {
    brain = FakeBrain();
    await brain.start();
    client = BrainClient(
      identity: const ClientIdentity(deviceId: 'app-test', fw: '0.1.0', caps: ['face', 'text']),
      random: Random(1),
      helloTimeout: const Duration(milliseconds: 800),
      pingEvery: const Duration(milliseconds: 300),
    );
  });
  tearDown(() async {
    await client.dispose();
    await brain.stop();
  });

  test('backoff follows the spec with +-20% jitter', () {
    final rng = Random(3);
    const bases = [500, 1000, 2000, 4000, 8000, 10000, 10000, 10000];
    for (var i = 0; i < bases.length; i++) {
      final d = BrainClient.backoff(i, rng).inMilliseconds;
      expect(d, inInclusiveRange(bases[i] * 0.8, bases[i] * 1.2), reason: 'attempt $i');
    }
  });

  test('hello handshake, then messages flow and ids count up', () async {
    final connected = waitFor(client.status, (s) => s.isConnected);
    final mood = waitFor(client.messages, (m) => m is MoodMsg);
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
    final s = await connected;
    expect(s.hello!.names['cat'], 'Spicy');
    expect(((await mood) as MoodMsg).mood, 'happy');

    final hello = brain.received.first;
    expect(hello['type'], 'hello');
    expect(hello['id'], 1);
    expect(hello['role'], 'tool');
    expect(hello['caps'], ['face', 'text']);
    expect(hello.containsKey('token'), isFalse);

    expect(client.send(const TextMsg(text: 'sit')), isTrue);
    final text = await waitFor(brain.rx, (m) => m['type'] == 'text');
    expect(text['text'], 'sit');
    expect(text['id'], greaterThan(1));
  });

  test('answers brain pings with pong re=id and measures its own round trip', () async {
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
    await waitFor(client.status, (s) => s.isConnected);
    final pong = waitFor(brain.rx, (m) => m['type'] == 'pong');
    brain.sendAll({'v': 1, 'type': 'ping', 'id': 41});
    expect((await pong)['re'], 41);
    final rtt = await waitFor(client.status, (s) => s.rttMs != null);
    expect(rtt.rttMs, lessThan(1000));
  });

  test('reconnects after the brain drops the link, with a fresh hello', () async {
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
    await waitFor(client.status, (s) => s.isConnected);
    final retrying = waitFor(client.status, (s) => s.phase == LinkPhase.retrying);
    await brain.dropAll(1001);
    await retrying;
    await waitFor(client.status, (s) => s.isConnected);
    expect(brain.helloCount, 2);
  });

  test('silence longer than 3 x heartbeat counts as dead, then it reconnects', () async {
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
    await waitFor(client.status, (s) => s.isConnected);
    await Future<void>.delayed(const Duration(milliseconds: 1500));
    expect(client.current.isConnected, isTrue, reason: 'pongs count as inbound traffic');
    brain.mute = true; // heartbeat_s is 1: dead after 3 s of silence
    final s = await waitFor(client.status, (s) => s.phase == LinkPhase.retrying,
        timeout: const Duration(seconds: 6));
    expect(s.error, contains('Lost touch'));
    brain.mute = false;
    await waitFor(client.status, (s) => s.isConnected, timeout: const Duration(seconds: 6));
  });

  test('wrong pairing token: stops with authFailed and does not hammer', () async {
    brain.requireToken = 'right';
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port, token: 'wrong'));
    final s = await waitFor(client.status, (s) => s.phase == LinkPhase.authFailed);
    expect(s.error, isNotNull);
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    expect(brain.helloCount, 1);
  });

  test('right pairing token connects', () async {
    brain.requireToken = 'right';
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port, token: 'right'));
    await waitFor(client.status, (s) => s.isConnected);
    expect(brain.received.first['token'], 'right');
  });

  test('no hello answer: retries', () async {
    brain.answerHello = false;
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
    final s = await waitFor(client.status, (s) => s.phase == LinkPhase.retrying);
    expect(s.attempt, 1);
  });

  test('nobody listening: retrying with a friendly error', () async {
    final port = brain.port;
    await brain.stop();
    brain = FakeBrain();
    await brain.start();
    client.connect(BrainEndpoint(host: '127.0.0.1', port: port));
    final s = await waitFor(client.status, (s) => s.phase == LinkPhase.retrying);
    expect(s.error, isNotEmpty);
  });

  test('send while disconnected returns false', () {
    expect(client.send(const TextMsg(text: 'hi')), isFalse);
  });

  test('disconnect goes idle and stops retrying', () async {
    client.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
    await waitFor(client.status, (s) => s.isConnected);
    await client.disconnect();
    expect(client.current.phase, LinkPhase.idle);
    await Future<void>.delayed(const Duration(milliseconds: 800));
    expect(brain.helloCount, 1);
  });

  group('v1.2 role app', () {
    late BrainClient app;
    setUp(() {
      app = BrainClient(
        identity: const ClientIdentity(deviceId: 'app-phone', fw: '0.2.0', role: 'app', caps: ['face', 'text', 'mic']),
        random: Random(2),
        helloTimeout: const Duration(seconds: 3),
        pingEvery: const Duration(milliseconds: 300),
      );
    });
    tearDown(() => app.dispose());

    test('says hello as app to a v1.2 brain', () async {
      app.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
      await waitFor(app.status, (s) => s.isConnected, timeout: const Duration(seconds: 10));
      expect(brain.received.first['role'], 'app');
      expect(app.legacyBrain, isFalse);
    });

    test('an older brain refuses role app: it joins as tool and says so', () async {
      brain.refuseAppRole = true;
      app.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
      await waitFor(app.status, (s) => s.isConnected, timeout: const Duration(seconds: 6));
      final hellos = brain.received.where((m) => m['type'] == 'hello').toList();
      expect(hellos.first['role'], 'app');
      expect(hellos.last['role'], 'tool');
      expect(app.legacyBrain, isTrue);
    });

    test('drive frames reach the brain in order with ttl', () async {
      app.connect(BrainEndpoint(host: '127.0.0.1', port: brain.port));
      await waitFor(app.status, (s) => s.isConnected, timeout: const Duration(seconds: 10));
      app.send(const DriveMsg(x: 0.2, y: 0.5));
      app.send(const DriveMsg(x: 0, y: 0));
      final stop = await waitFor(brain.rx, (m) => m['type'] == 'drive' && m['y'] == 0);
      final drives = brain.received.where((m) => m['type'] == 'drive').toList();
      expect(drives.first['y'], 0.5);
      expect(stop['ttl_ms'], 300);
      expect(drives.last['id'], greaterThan(drives.first['id'] as int));
    });
  });
}