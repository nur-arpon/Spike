import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/protocol/messages.dart';

/// Round-trip every message type in both directions: encode -> JSON text ->
/// decode gives the same fields and the envelope the spec requires.
void main() {
  Map<String, dynamic> wire(SpikeMessage m, {int id = 7}) =>
      jsonDecode(m.encode(id: id)) as Map<String, dynamic>;

  SpikeMessage round(SpikeMessage m, Sender from) {
    final text = m.encode(id: 3, re: 2, ts: 1000);
    final back = SpikeMessage.decode(text, from: from);
    expect(back.type, m.type);
    expect(back.id, 3);
    expect(back.re, 2);
    expect(back.ts, 1000);
    expect(jsonEncode(back.fields()), jsonEncode(m.fields()), reason: 'fields of ${m.type}');
    return back;
  }

  group('envelope', () {
    test('has v, type and id; optional re/ts only when set', () {
      final j = wire(const TextMsg(text: 'hi'));
      expect(j['v'], 1);
      expect(j['type'], 'text');
      expect(j['id'], 7);
      expect(j.containsKey('re'), isFalse);
      expect(j.containsKey('ts'), isFalse);
    });
    test('null optional fields are left out', () {
      final j = wire(const MoodStateMsg(mode: 'cat'));
      expect(j.keys, containsAll(['v', 'type', 'id', 'mode']));
      expect(j.containsKey('mood'), isFalse);
      expect(j.containsKey('action'), isFalse);
    });
    test('empty token is not sent in hello', () {
      final j = wire(const ClientHello(role: 'tool', deviceId: 'a', fw: '1', caps: ['text'], token: ''));
      expect(j.containsKey('token'), isFalse);
    });
    test('unknown fields are ignored', () {
      final m = SpikeMessage.decode('{"v":1,"type":"mood","id":1,"mood":"happy","sparkle":9}', from: Sender.brain);
      expect(m, isA<MoodMsg>());
      expect((m as MoodMsg).mood, 'happy');
    });
    test('unknown types decode to UnknownMessage', () {
      final m = SpikeMessage.decode('{"v":1,"type":"hug","id":1,"strength":3}', from: Sender.brain);
      expect(m, isA<UnknownMessage>());
      expect(m.type, 'hug');
      expect(m.fields(), {'strength': 3});
    });
  });

  group('errors', () {
    void bad(String text, String code) {
      expect(() => SpikeMessage.decode(text, from: Sender.brain),
          throwsA(isA<ProtocolException>().having((e) => e.code, 'code', code)), reason: text);
    }

    test('not JSON', () => bad('{nope', 'bad_json'));
    test('not an object', () => bad('[1,2]', 'bad_json'));
    test('missing v/type', () => bad('{"type":"mood"}', 'missing_field'));
    test('wrong version', () => bad('{"v":2,"type":"mood","id":1,"mood":"happy"}', 'version_mismatch'));
    test('id must be int', () => bad('{"v":1,"type":"ping","id":"1"}', 'bad_value'));
    test('missing required field', () => bad('{"v":1,"type":"mood","id":1}', 'missing_field'));
    test('bad enum value', () => bad('{"v":1,"type":"mood","id":1,"mood":"happpy"}', 'bad_value'));
    test('wrong field type', () => bad('{"v":1,"type":"look_at","id":1,"x":"left","y":0}', 'bad_value'));
    test('say needs audio present (null ok)', () =>
        bad('{"v":1,"type":"say","id":1,"utt":"u1","seq":0,"final":true,"text":"","duration_ms":0}', 'missing_field'));
  });

  group('brain -> clients', () {
    test('hello', () {
      final m = round(
        const BrainHello(
          server: 'spike-brain', version: '0.1.0', session: 'a41f', heartbeatS: 5, mode: 'dog',
          names: {'dog': 'Spike', 'cat': 'Spicy'},
          wakeWords: {'dog': ['Spike', 'Hey Buddy'], 'cat': ['Spicy']},
          audio: {'format': 'pcm_s16le', 'rate': 22050, 'channels': 1},
        ),
        Sender.brain,
      ) as BrainHello;
      expect(m.names['cat'], 'Spicy');
      expect(m.wakeWords['dog'], ['Spike', 'Hey Buddy']);
    });
    test('mood', () => round(const MoodMsg(mood: 'cuteAngry', holdS: 2), Sender.brain));
    test('action (incl. comfort)', () {
      round(const ActionMsg(action: 'tailWagDance'), Sender.brain);
      round(const ActionMsg(action: 'snuggle'), Sender.brain);
    });
    test('event', () => round(const EventMsg(event: 'comeHome'), Sender.brain));
    test('say with audio + mouth', () {
      final m = round(
        const SayMsg(
          utt: 'u17', seq: 0, isFinal: false, text: "Oh, you're home!", mood: 'excited', durationMs: 1240,
          audio: {'format': 'pcm_s16le', 'rate': 22050, 'channels': 1, 'samples': 27342, 'chunks': 2},
          mouth: {'rate_hz': 50, 'values': [0, 12, 55]},
        ),
        Sender.brain,
      ) as SayMsg;
      expect(m.isEndMarker, isFalse);
    });
    test('say end marker keeps audio:null on the wire', () {
      const m = SayMsg(utt: 'u1', seq: 2, isFinal: true, text: '', durationMs: 0);
      final j = wire(m);
      expect(j.containsKey('audio'), isTrue);
      expect(j['audio'], isNull);
      final back = SpikeMessage.decode(jsonEncode(j), from: Sender.brain) as SayMsg;
      expect(back.isEndMarker, isTrue);
    });
    test('say_audio', () =>
        round(const SayAudioMsg(utt: 'u17', seq: 0, index: 1, last: true, data: 'AAAA'), Sender.brain));
    test('stop_speaking', () {
      round(const StopSpeakingMsg(utt: 'u17'), Sender.brain);
      round(const StopSpeakingMsg(), Sender.brain);
    });
    test('listening', () => round(const ListeningMsg(state: 'thinking'), Sender.brain));
    test('look_at', () => round(const LookAtMsg(x: -0.4, y: 0.1, source: 'camera'), Sender.brain));
    test('sound', () => round(const SoundMsg(sound: 'patSqueak'), Sender.brain));
    test('alarm', () {
      round(const AlarmMsg(alarmId: 3, state: 'ringing', level: 1, label: 'Wake up'), Sender.brain);
      round(const AlarmMsg(state: 'snoozed', until: 1759200000), Sender.brain);
    });
    test('game', () => round(
          const GameMsg(phase: 'reveal', owner: 'rock', robot: 'paper', result: 'lose',
              score: {'owner': 1, 'robot': 2, 'draws': 0}),
          Sender.brain,
        ));
    test('set_mode', () => round(const SetModeMsg(mode: 'cat'), Sender.brain));
    test('set_recipe (code and recipe)', () {
      round(const SetRecipeMsg(mode: 'dog', code: 'SPK1-abc'), Sender.brain);
      round(const SetRecipeMsg(mode: 'cat', recipe: {'fur': '#FFFFFF'}), Sender.brain);
    });
    test('ping / pong / error', () {
      round(const PingMsg(), Sender.brain);
      round(const PongMsg(), Sender.brain);
      round(const ErrorMsg(code: 'bad_value', message: "unknown mood 'happpy'"), Sender.brain);
    });
  });

  group('clients -> brain', () {
    test('hello', () {
      final m = round(
        const ClientHello(role: 'tool', deviceId: 'app-1', fw: '0.1.0', caps: ['face', 'text', 'mic'],
            audioOut: {'rates': [16000], 'format': 'pcm_s16le'}, token: 'secret'),
        Sender.client,
      ) as ClientHello;
      expect(m.caps, ['face', 'text', 'mic']);
      expect(m.token, 'secret');
    });
    test('touch', () => round(const TouchMsg(zone: 'head', gesture: 'pat'), Sender.client));
    test('imu', () => round(const ImuMsg(event: 'lap'), Sender.client));
    test('edge', () => round(const EdgeMsg(sensor: 'front_left', state: 'edge'), Sender.client));
    test('battery', () => round(const BatteryMsg(percent: 27, volts: 7.12, charging: false), Sender.client));
    test('mood_state', () => round(const MoodStateMsg(mood: 'sleepy', mode: 'dog'), Sender.client));
    test('say_state', () => round(const SayStateMsg(utt: 'u17', seq: 0, state: 'finished'), Sender.client));
    test('audio', () => round(const AudioMsg(seq: 1042, data: 'AAAA'), Sender.client));
    test('camera', () =>
        round(const CameraMsg(seq: 88, width: 320, height: 240, data: '/9j/'), Sender.client));
    test('text', () => round(const TextMsg(text: "what's the time?"), Sender.client));
    test('alarm_ack', () => round(const AlarmAckMsg(action: 'snooze'), Sender.client));
    test('log', () => round(const LogMsg(level: 'warn', msg: 'I2S underrun'), Sender.client));
    test('touch gesture defaults to tap', () {
      final m = SpikeMessage.decode('{"v":1,"type":"touch","id":1,"zone":"nose"}', from: Sender.client) as TouchMsg;
      expect(m.gesture, 'tap');
    });
  });

  group('v1.2: the phone app (PROTOCOL.md section 10)', () {
    test('action and set_mode carry quiet only when set', () {
      expect(wire(const ActionMsg(action: 'zoomies')).containsKey('quiet'), isFalse);
      final a = round(const ActionMsg(action: 'zoomies', quiet: true), Sender.client) as ActionMsg;
      expect(a.quiet, isTrue);
      final m = round(const SetModeMsg(mode: 'cat', quiet: true), Sender.client) as SetModeMsg;
      expect(m.quiet, isTrue);
    });
    test('drive (both directions) with the dead-man ttl', () {
      final j = wire(const DriveMsg(x: -0.25, y: 0.6));
      expect([j['x'], j['y'], j['ttl_ms']], [-0.25, 0.6, 300]);
      round(const DriveMsg(x: 0, y: 0, ttlMs: 150), Sender.client);
      round(const DriveMsg(x: 1, y: -1, ttlMs: 1000), Sender.brain);
    });
    test('drive without ttl decodes to 300', () {
      final m = SpikeMessage.decode('{"v":1,"type":"drive","id":1,"x":0.1,"y":0.2}', from: Sender.brain) as DriveMsg;
      expect(m.ttlMs, 300);
    });
    test('set_display', () => round(const SetDisplayMsg(captions: false), Sender.client));
    test('timers_get / timers / timer_set / timer_cancel', () {
      round(const TimersGetMsg(), Sender.client);
      final t = round(
        const TimersMsg(items: [
          TimerItem(id: 12, kind: 'alarm', due: 1759219800, label: 'Wake up'),
          TimerItem(id: 13, kind: 'reminder', due: 1759219860, label: 'water', repeat: 'daily', state: 'snoozed'),
        ]),
        Sender.brain,
      ) as TimersMsg;
      expect(t.items[1].repeat, 'daily');
      expect(t.items[0].dueAt, DateTime.fromMillisecondsSinceEpoch(1759219800 * 1000));
      final s = wire(const TimerSetMsg(kind: 'reminder', due: 1759219800, label: 'drink water'));
      expect(s, containsPair('repeat', ''));
      round(const TimerSetMsg(kind: 'alarm', due: 1759219800, repeat: 'daily'), Sender.client);
      final c = wire(const TimerCancelMsg(timerId: 12));
      expect(c['timer_id'], 12);
      expect(c['id'], 7, reason: 'the envelope id is never the timer id');
      round(const TimerCancelMsg(timerId: 12), Sender.client);
    });
    test('timers skips items it cannot read (forward compatible)', () {
      final m = SpikeMessage.decode(
          '{"v":1,"type":"timers","id":1,"items":[{"id":1,"kind":"alarm","due":5},{"nope":1},{"id":2,"kind":"future","due":9,"x":1}]}',
          from: Sender.brain) as TimersMsg;
      expect(m.items.map((e) => e.id), [1, 2]);
      expect(m.items[1].kind, 'alarm');
    });
    test('memory_get / memory / memory_forget / memory_forget_all', () {
      round(const MemoryGetMsg(), Sender.client);
      final m = round(
        const MemoryMsg(items: [MemoryItem(id: 31, text: 'Arpon likes tea with honey', kind: 'preference', at: 1759180000)], total: 1),
        Sender.brain,
      ) as MemoryMsg;
      expect(m.items.single.text, contains('tea'));
      expect(wire(const MemoryForgetMsg(factId: 31))['fact_id'], 31);
      round(const MemoryForgetMsg(factId: 31), Sender.client);
      expect(wire(const MemoryForgetAllMsg())['confirm'], isTrue);
      round(const MemoryForgetAllMsg(), Sender.client);
      expect(() => SpikeMessage.decode('{"v":1,"type":"memory_forget_all","id":1,"confirm":false}', from: Sender.client),
          throwsA(isA<ProtocolException>()));
    });
    test('camera_subscribe / camera_unsubscribe', () {
      round(const CameraSubscribeMsg(fps: 8), Sender.client);
      round(const CameraUnsubscribeMsg(), Sender.client);
    });
    test('robot_status / brain_status / heard / pairing', () {
      final r = round(const RobotStatusMsg(online: false, boards: ['simulator'], drive: false, camera: false), Sender.brain)
          as RobotStatusMsg;
      expect(r.simulator, isTrue);
      round(const RobotStatusMsg(online: true, boards: ['camera', 'face'], drive: true, camera: true), Sender.brain);
      round(const BrainStatusMsg(llm: 'warming'), Sender.brain);
      final h = round(const HeardMsg(text: 'what time is it', via: 'wake', mine: false), Sender.brain) as HeardMsg;
      expect(h.via, 'wake');
      round(const PairingGetMsg(), Sender.client);
      expect((round(const KeepaliveMsg(), Sender.client) as KeepaliveMsg).warm, isTrue);
      final h16 = round(const BrainHello(server: 's', version: '1', heartbeatS: 5, mode: 'dog', keepalive: true), Sender.brain);
      expect((h16 as BrainHello).keepalive, isTrue);
      round(const PairingMsg(lan: true, url: 'spike://pair?host=192.168.1.2&port=8765&token=t&name=Spike'), Sender.brain);
    });
    test('battery and camera relayed by the brain decode the same way', () {
      final b = SpikeMessage.decode('{"v":1,"type":"battery","id":4,"percent":64,"charging":true}', from: Sender.brain);
      expect((b as BatteryMsg).charging, isTrue);
      final c = SpikeMessage.decode('{"v":1,"type":"camera","id":5,"seq":3,"format":"jpeg","data":"/9j/"}', from: Sender.brain);
      expect((c as CameraMsg).seq, 3);
    });
  });

  group('v1.4: body actions - walk and paw (PROTOCOL.md 5.2)', () {
    test('walk round-trips with its gait fields', () {
      final m = round(
        const ActionMsg(action: 'walk', direction: 'forward', steps: 4, style: 'tiltStep'),
        Sender.brain,
      ) as ActionMsg;
      expect((m.direction, m.steps, m.style), ('forward', 4, 'tiltStep'));
    });
    test('paw round-trips with its fields', () {
      final m = round(const ActionMsg(action: 'paw', side: 'left', from: 'stand'), Sender.client) as ActionMsg;
      expect((m.side, m.from), ('left', 'stand'));
    });
    test('bare walk/paw (no gait fields) leaves them null and off the wire', () {
      final j = wire(const ActionMsg(action: 'walk'));
      for (final k in ['direction', 'steps', 'style', 'side', 'from']) {
        expect(j.containsKey(k), isFalse, reason: k);
      }
      round(const ActionMsg(action: 'walk'), Sender.brain);
      round(const ActionMsg(action: 'paw'), Sender.brain);
    });
    test('bad direction / steps / style / side / from', () {
      for (final bad in [
        '{"v":1,"type":"action","id":1,"action":"walk","direction":"sideways"}',
        '{"v":1,"type":"action","id":1,"action":"walk","steps":0}',
        '{"v":1,"type":"action","id":1,"action":"walk","steps":17}',
        '{"v":1,"type":"action","id":1,"action":"walk","style":"gallop"}',
        '{"v":1,"type":"action","id":1,"action":"paw","side":"front"}',
        '{"v":1,"type":"action","id":1,"action":"paw","from":"lying"}',
      ]) {
        expect(() => SpikeMessage.decode(bad, from: Sender.brain),
            throwsA(isA<ProtocolException>().having((e) => e.code, 'code', 'bad_value')), reason: bad);
      }
    });
  });
}