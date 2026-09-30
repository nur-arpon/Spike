import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/features/connect/pairing.dart';
import 'package:spike_app/features/life/timers_state.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/protocol/names.dart' as n;
import 'package:spike_app/state/pairing_sync.dart';
import 'package:spike_app/state/settings.dart';

List<String> _jsList(String file, String varName) {
  final src = File(file).readAsStringSync();
  final start = src.indexOf('var $varName = [');
  expect(start, greaterThanOrEqualTo(0), reason: '$varName in $file');
  final end = src.indexOf('];', start);
  return RegExp(r"'([A-Za-z]+)'").allMatches(src.substring(start, end)).map((m) => m.group(1)!).toList();
}

void main() {
  group('names match the bundled face_v2 engine', () {
    test('moods', () => expect(n.moods, _jsList('assets/face/moods.js', 'MOODS')));
    test('actions = keys of ACTIONS in actions.js (+ v1.1 comfort + v1.4 body actions)', () {
      final src = File('assets/face/actions.js').readAsStringSync();
      final block = src.substring(src.indexOf('var ACTIONS = {'), src.indexOf('var ACTION_LABELS'));
      final keys = RegExp(r'^    ([a-zA-Z]+): \{', multiLine: true).allMatches(block).map((m) => m.group(1)!).toList();
      expect(n.actions, [...keys, ...n.comfortActions, ...n.bodyActions]);
    });
    test('every mood has a label', () {
      for (final m in n.moods) {
        expect(n.moodLabels[m], isNotNull, reason: m);
      }
    });
  });

  group('pairing QR / typed address', () {
    test('spike:// QR with token and name', () {
      final ep = parsePairing('spike://pair?host=192.168.1.20&port=8766&token=abc123&name=Spike')!;
      expect(ep.host, '192.168.1.20');
      expect(ep.port, 8766);
      expect(ep.token, 'abc123');
      expect(ep.name, 'Spike');
      expect(ep.uri.toString(), 'ws://192.168.1.20:8766/');
    });
    test('short keys', () {
      final ep = parsePairing('spike://pair?h=10.0.0.5&p=8765&t=x')!;
      expect((ep.host, ep.port, ep.token), ('10.0.0.5', 8765, 'x'));
    });
    test('ws:// url', () {
      final ep = parsePairing('ws://192.168.1.20:8765/?token=abc')!;
      expect((ep.host, ep.port, ep.token), ('192.168.1.20', 8765, 'abc'));
    });
    test('bare host and host:port', () {
      expect(parsePairing('192.168.1.20')!.port, n.defaultPort);
      expect(parsePairing('127.0.0.1:8766')!.port, 8766);
      expect(parsePairing('arpon-laptop.local')!.host, 'arpon-laptop.local');
    });
    test('rejects junk', () {
      for (final bad in ['', 'hello world', 'spike://other?host=1.2.3.4', '300.1.1.1', '1.2.3.4:99999', 'https://evil.example/x y']) {
        expect(parsePairing(bad), isNull, reason: bad);
      }
    });
  });

  group('alarm words the brain understands', () {
    final now = DateTime(2026, 9, 29, 20, 0);
    test('today and tomorrow', () {
      expect(alarmCommand(DateTime(2026, 9, 29, 21, 5), now), 'set an alarm for 9:05 pm');
      expect(alarmCommand(DateTime(2026, 9, 30, 7, 30), now), 'set an alarm for 7:30 am tomorrow');
      expect(alarmCommand(DateTime(2026, 9, 30, 0, 15), now), 'set an alarm for 12:15 am tomorrow');
    });
    test('reminder', () {
      expect(reminderCommand('drink water', DateTime(2026, 9, 29, 22, 15), now), 'remind me to drink water at 10:15 pm');
    });
  });

  group('v1.2 pairing', () {
    test('the brain pairing link parses to the Wi-Fi endpoint with its token', () {
      final ep = parsePairing('spike://pair?host=192.168.1.102&port=8765&token=abc-DEF_123&name=Spike')!;
      expect([ep.host, ep.port, ep.token, ep.name], ['192.168.1.102', 8765, 'abc-DEF_123', 'Spike']);
    });
    test('a brain found on the Wi-Fi gets the token this phone learnt earlier', () {
      const wifi = BrainEndpoint(host: '192.168.1.102', port: 8765, token: 'tok');
      const s = AppSettings(deviceId: 'a', wifiPairing: wifi);
      final found = PairingSync.withKnownToken(const BrainEndpoint(host: '192.168.1.102', port: 8765, name: 'Spike'), s);
      expect(found.token, 'tok');
      expect(found.name, 'Spike');
      final other = PairingSync.withKnownToken(const BrainEndpoint(host: '192.168.1.50', port: 8765), s);
      expect(other.token, isNull, reason: 'never hand a token to a different brain');
    });
    test('the role list includes app', () => expect(n.roles, contains('app')));
  });
}