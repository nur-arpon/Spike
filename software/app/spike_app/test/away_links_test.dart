// Away links: the Gemini REST client (mocked HTTP, no key needed), the BLE pipe
// over a fake radio (framing, write order, pairing), the hotspot WebSocket
// server with a board connecting over a real socket, and the hub switching
// the screens between the laptop brain and the phone brain.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:spike_app/away/ai/gemini.dart';
import 'package:spike_app/away/ai/key_store.dart';
import 'package:spike_app/away/ai/llm.dart';
import 'package:spike_app/away/brain/persona.dart' show ChatMessage;
import 'package:spike_app/away/transport/ble_frames.dart';
import 'package:spike_app/away/transport/ble_link.dart';
import 'package:spike_app/away/transport/robot_server.dart';
import 'package:spike_app/away/transport/robot_session.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/protocol/messages.dart';
import 'package:spike_app/state/hub.dart';

String sse(String text) => 'data: ${jsonEncode({
      'candidates': [
        {
          'content': {
            'parts': [
              {'text': text}
            ]
          }
        }
      ]
    })}\n\n';

const msgs = [ChatMessage('system', 'You are Spike.'), ChatMessage('user', 'hi'), ChatMessage('assistant', '[happy] Hi!'),
  ChatMessage('user', 'how are you')];

class FakeRadio implements BleApi {
  bool permitted = true, paired = false, on = true;
  final writes = <Uint8List>[];
  final tx = StreamController<Uint8List>.broadcast();
  final conn = StreamController<bool>.broadcast();
  int pairCalls = 0;
  @override
  Future<bool> hasPermissions() async => permitted;
  @override
  Future<void> requestPermissions() async {}
  @override
  Future<bool> bluetoothOn() async => on;
  @override
  Stream<FoundRobot> scan(Duration timeout) => Stream.fromIterable([const FoundRobot(deviceId: 'AA', name: 'Spike-7c9e2a')]);
  @override
  Future<void> connect(String deviceId) async {}
  @override
  Future<void> disconnect(String deviceId) async => conn.add(false);
  @override
  Stream<bool> connection(String deviceId) => conn.stream;
  @override
  Future<void> discover(String deviceId) async {}
  @override
  Future<int> requestMtu(String deviceId, int mtu) async => 23; // worst case: many frames
  @override
  Future<bool?> isPaired(String deviceId) async => paired;
  @override
  Future<void> pair(String deviceId) async {
    pairCalls++;
    paired = true;
  }

  @override
  Future<Uint8List> read(String deviceId, String char) async =>
      Uint8List.fromList(utf8.encode('{"pv":"1.3","fw":"0.2.0","device_id":"spike-7c9e2a","brain":"none"}'));
  @override
  Future<void> write(String deviceId, String char, Uint8List value, {bool withoutResponse = false}) async {
    await Future<void>.delayed(const Duration(milliseconds: 1));
    writes.add(value);
  }

  @override
  Future<void> subscribe(String deviceId, String char) async {}
  @override
  Stream<Uint8List> values(String deviceId, String char) => tx.stream;
}

void main() {
  group('Gemini (REST, mocked)', () {
    test('the request: system instruction, model turns, minimal thinking, the key in a header', () async {
      late http.Request seen;
      final g = GeminiProvider(
        apiKey: 'AIzaTESTKEY',
        client: MockClient.streaming((req, body) async {
          seen = req as http.Request;
          return http.StreamedResponse(Stream.value(utf8.encode(sse('[happy] Great') + sse(', thanks!'))), 200);
        }),
      );
      final out = await g.stream(msgs, maxTokens: 80).join();
      expect(out, '[happy] Great, thanks!');
      expect(seen.url.path, endsWith('/models/gemini-3.5-flash-lite:streamGenerateContent'));
      expect(seen.url.query, 'alt=sse');
      expect(seen.headers['x-goog-api-key'], 'AIzaTESTKEY');
      expect(seen.url.toString(), isNot(contains('AIzaTESTKEY')), reason: 'never in the URL (logs)');
      final body = jsonDecode(seen.body) as Map<String, dynamic>;
      expect(body['systemInstruction']['parts'][0]['text'], 'You are Spike.');
      expect([for (final c in body['contents']) c['role']], ['user', 'model', 'user']);
      expect(body['generationConfig']['maxOutputTokens'], 80);
      expect(body['generationConfig']['thinkingConfig'], {'thinkingLevel': 'minimal'});
    });

    test('429 on one model moves to the next; all of them 429 = rateLimited', () async {
      final tried = <String>[];
      final g = GeminiProvider(
        apiKey: 'k',
        client: MockClient.streaming((req, _) async {
          tried.add(req.url.pathSegments.last.split(':').first);
          if (tried.length < 2) return http.StreamedResponse(Stream.value(utf8.encode('{"error":{"status":"RESOURCE_EXHAUSTED"}}')), 429);
          return http.StreamedResponse(Stream.value(utf8.encode(sse('[happy] Hi'))), 200);
        }),
      );
      expect(await g.stream(msgs).join(), '[happy] Hi');
      expect(tried, ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite']);
      final all429 = GeminiProvider(
          apiKey: 'k', client: MockClient.streaming((req, _) async => http.StreamedResponse(Stream.value([]), 429)));
      await expectLater(all429.stream(msgs).join(),
          throwsA(isA<LlmError>().having((e) => e.kind, 'kind', LlmErrorKind.rateLimited)));
    });

    test('a bad key is badKey; a thinking setting the model refuses is dropped and retried', () async {
      final bad = GeminiProvider(
          apiKey: 'k',
          client: MockClient.streaming((req, _) async =>
              http.StreamedResponse(Stream.value(utf8.encode('{"error":{"message":"API key not valid."}}')), 400)));
      await expectLater(bad.stream(msgs).join(), throwsA(isA<LlmError>().having((e) => e.kind, 'kind', LlmErrorKind.badKey)));
      var n = 0;
      final g = GeminiProvider(
        apiKey: 'k',
        client: MockClient.streaming((req, body) async {
          n++;
          final b = jsonDecode((req as http.Request).body) as Map<String, dynamic>;
          if (b['generationConfig']['thinkingConfig'] != null) {
            return http.StreamedResponse(Stream.value(utf8.encode('{"error":{"message":"thinking level is not supported"}}')), 400);
          }
          return http.StreamedResponse(Stream.value(utf8.encode(sse('ok'))), 200);
        }),
      );
      expect(await g.stream(msgs).join(), 'ok');
      expect(n, 2);
    });

    test('safety blocks and thought parts', () {
      expect(() => GeminiProvider.textOf({'promptFeedback': {'blockReason': 'SAFETY'}}),
          throwsA(isA<LlmError>().having((e) => e.kind, 'kind', LlmErrorKind.blocked)));
      expect(
          GeminiProvider.textOf({
            'candidates': [
              {
                'content': {
                  'parts': [
                    {'text': 'hmm', 'thought': true},
                    {'text': 'Hi!'}
                  ]
                }
              }
            ]
          }),
          'Hi!');
    });

    test('the safety classifier asks for JSON with the schema', () async {
      late Map<String, dynamic> body;
      final g = GeminiProvider(
        apiKey: 'k',
        client: MockClient((req) async {
          body = jsonDecode(req.body) as Map<String, dynamic>;
          return http.Response(jsonEncode({
            'candidates': [
              {
                'content': {
                  'parts': [
                    {'text': '{"level":"support"}'}
                  ]
                }
              }
            ]
          }), 200);
        }),
      );
      expect(await g.completeJson('classify', 'I feel low', const {'type': 'object'}), '{"level":"support"}');
      expect(body['generationConfig']['responseMimeType'], 'application/json');
      expect(body['generationConfig']['temperature'], 0);
    });

    test('pasted keys are tidied and shape-checked', () {
      expect(tidyKey('  "AIzaSyA-bc_123"\n'), 'AIzaSyA-bc_123');
      expect(keyProblem('gemini', ''), isNotNull);
      expect(keyProblem('gemini', 'sk-abc'), contains('AIza'));
      expect(keyProblem('gemini', 'AIza${'x' * 35}'), isNull);
    });
  });

  group('BLE link over a fake radio', () {
    test('connect pairs when not bonded, then frames go out in order at MTU 23', () async {
      final radio = FakeRadio();
      final pipe = await BleRobotLink(radio).connect('AA', name: 'Spike-7c9e2a');
      expect(radio.pairCalls, 1);
      final a = '{"v":1,"type":"mood","id":1,"mood":"happy","hold_s":0}';
      final b = '{"v":1,"type":"action","id":2,"action":"headTilt"}';
      final r = await Future.wait([pipe.send(a), pipe.send(b)]);
      expect(r, [true, true]);
      final dec = BleFrameDecoder();
      final got = [for (final f in radio.writes) dec.feed(f)].whereType<Uint8List>().map(utf8.decode).toList();
      expect(got, [a, b], reason: 'two messages, frames never interleaved');
      expect(radio.writes.every((f) => f.length <= 20), isTrue);
    });

    test('notifications are reassembled into messages; a disconnect closes the pipe', () async {
      final radio = FakeRadio()..paired = true;
      final pipe = await BleRobotLink(radio).connect('AA');
      final got = <String>[];
      pipe.incoming.listen(got.add);
      final hello = '{"v":1,"type":"hello","id":1,"role":"face","device_id":"spike-1","fw":"0.2.0","caps":["face"],"link":"ble"}';
      for (final f in BleFrameEncoder().encode(utf8.encode(hello), 23)) {
        radio.tx.add(f);
      }
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(got, [hello]);
      radio.conn.add(false);
      await pipe.closed.timeout(const Duration(seconds: 1));
      expect(await pipe.send('{}'), isFalse);
    });

    test('no permission or Bluetooth off: clear errors, nothing asked behind the owner\'s back', () async {
      final radio = FakeRadio()..permitted = false;
      await expectLater(BleRobotLink(radio).connect('AA'), throwsA(isA<BleLinkError>().having((e) => e.code, 'code', 'permission')));
      radio
        ..permitted = true
        ..on = false;
      await expectLater(BleRobotLink(radio).connect('AA'), throwsA(isA<BleLinkError>().having((e) => e.code, 'code', 'bluetooth_off')));
    });

    test('the open info characteristic', () async {
      final info = await BleRobotLink(FakeRadio()).readInfo('AA');
      expect(info?['pv'], '1.3');
    });
  });

  group('hotspot server (a board over a real socket)', () {
    test('a board connects, says hello with the token, gets the brain hello', () async {
      final server = RobotServer(port: 0);
      final port = await server.start();
      final sessions = <RobotSession>[];
      server.pipes.listen((p) => sessions.add(RobotSession(p,
          token: 'tok-0123456789abcdef',
          greeting: () => const BrainGreeting(mode: 'dog', names: {'dog': 'Spike'}, wakeWords: {}),
          onLive: (s) => s.send(const SetModeMsg(mode: 'dog')))));
      final ws = await WebSocket.connect('ws://127.0.0.1:$port/');
      final inbox = <Map<String, dynamic>>[];
      ws.listen((d) => inbox.add(jsonDecode(d as String) as Map<String, dynamic>));
      ws.add(jsonEncode({'v': 1, 'type': 'hello', 'id': 1, 'role': 'camera', 'device_id': 'spike-1', 'fw': '0',
        'caps': ['camera'], 'token': 'tok-0123456789abcdef', 'link': 'hotspot'}));
      await Future<void>.delayed(const Duration(milliseconds: 150));
      expect(inbox.map((m) => m['type']).take(2), ['hello', 'set_mode']);
      expect(sessions.single.live, isTrue);
      expect(sessions.single.hello!.link, 'hotspot');
      await ws.close();
      await server.stop();
    });
  });

  group('the hub', () {
    test('screens see the laptop, then the phone, then the laptop again', () async {
      final lan = BrainClient(identity: const ClientIdentity(deviceId: 't', fw: '0', role: 'app'));
      final hub = SpikeHub(lan);
      final phone = _StubPhone();
      final seen = <String>[];
      hub.messages.listen((m) => seen.add(m.type));
      hub.attachPhone(phone);
      phone.emit(const MoodMsg(mood: 'happy'));
      await Future<void>.delayed(Duration.zero);
      expect(seen, isEmpty, reason: 'the laptop is active: phone messages are not shown');
      hub.setActive(BrainHost.phone);
      phone.emit(const MoodMsg(mood: 'sad'));
      await Future<void>.delayed(Duration.zero);
      expect(seen, ['mood']);
      expect(hub.send(const TextMsg(text: 'hi')), isTrue);
      expect(phone.got.single, isA<TextMsg>());
      hub.setActive(BrainHost.laptop);
      expect(hub.send(const TextMsg(text: 'hi')), isFalse, reason: 'the laptop link is not up');
      await hub.dispose();
    });
  });
}

class _StubPhone implements SpikeLink {
  final _m = StreamController<SpikeMessage>.broadcast();
  final _s = StreamController<LinkStatus>.broadcast();
  final got = <SpikeMessage>[];
  void emit(SpikeMessage m) => _m.add(m);
  @override
  Stream<SpikeMessage> get messages => _m.stream;
  @override
  Stream<LinkStatus> get status => _s.stream;
  @override
  LinkStatus get current => const LinkStatus(phase: LinkPhase.connected, brain: BrainHost.phone);
  @override
  bool get legacyBrain => false;
  @override
  bool send(SpikeMessage msg) {
    got.add(msg);
    return true;
  }
}
