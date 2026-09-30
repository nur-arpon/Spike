// The phone brain end to end, with a fake language model, a fake voice and a
// fake robot board: the crisis path, the request block, the output check, the
// word cap, one helpline per reply, friendly lines on errors, commands, memory,
// nudges, and the protocol session with a robot over a pipe.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/away/ai/llm.dart';
import 'package:spike_app/away/brain/memory.dart';
import 'package:spike_app/away/brain/persona.dart';
import 'package:spike_app/core/capabilities.dart';
import 'package:spike_app/away/brain/phone_brain.dart';
import 'package:spike_app/away/transport/robot_session.dart';
import 'package:spike_app/away/voice/ear.dart';
import 'package:spike_app/away/voice/speaker.dart';
import 'package:spike_app/protocol/messages.dart';

class FakeLlm implements LlmProvider {
  FakeLlm([this.replies = const []]);
  List<String> replies;
  LlmError? error;
  String json = '{"level":"none"}';
  final calls = <List<ChatMessage>>[];
  int jsonCalls = 0;
  @override
  String get id => 'fake';
  @override
  String get label => 'fake';
  @override
  Stream<String> stream(List<ChatMessage> messages, {int? maxTokens, double temperature = 0.7}) async* {
    calls.add(messages);
    if (error != null) throw error!;
    final r = replies.isEmpty ? '[happy] Okay!' : replies.removeAt(0);
    for (var i = 0; i < r.length; i += 7) {
      yield r.substring(i, min(r.length, i + 7));
    }
  }

  @override
  Future<String> completeJson(String system, String user, Map<String, Object> schema,
      {int maxTokens = 40, Duration timeout = const Duration(seconds: 4)}) async {
    jsonCalls++;
    return json;
  }

  @override
  Future<void> check() async {}
  String get lastUser => calls.last.last.content;
}

class FakeVoice implements SpikeVoice {
  final spoken = <String>[];
  @override
  String get name => 'fake';
  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    spoken.add(text);
    return _P();
  }

  @override
  Future<void> stop() async {}
}

class _P implements PreparedSpeech {
  @override
  SpokenClip get clip => const SpokenClip(durationMs: 5, mouth: [0, 50, 100, 20]);
  @override
  Future<void> play() async {}
}

class FakePipe implements RobotPipe {
  FakePipe(this.link);
  @override
  final String link;
  final _in = StreamController<String>.broadcast();
  final sent = <Map<String, dynamic>>[];
  final _closed = Completer<void>();
  @override
  String get label => 'fake $link';
  @override
  Stream<String> get incoming => _in.stream;
  @override
  int get maxMessage => 16384;
  @override
  Future<void> get closed => _closed.future;
  @override
  Future<bool> send(String json) async {
    sent.add(jsonDecode(json) as Map<String, dynamic>);
    return true;
  }

  void robotSays(Map<String, Object?> m) => _in.add(jsonEncode({'v': 1, 'id': 1, ...m}));
  List<String> get types => [for (final m in sent) m['type'] as String];
  @override
  Future<void> close() async {
    if (!_closed.isCompleted) _closed.complete();
  }
}

class Rig {
  Rig({this.withModel = true}) {
    brain = PhoneBrain(
      persona: {
        'dog': Persona.fromToml(File('assets/brain/spike.toml').readAsStringSync()),
        'cat': Persona.fromToml(File('assets/brain/spicy.toml').readAsStringSync()),
      },
      settings: BrainSettings.fromToml(File('assets/brain/default.toml').readAsStringSync()),
      memory: PhoneMemory(clock: () => now.millisecondsSinceEpoch ~/ 1000),
      cloud: () => withModel ? llm : null,
      offline: () => null,
      voice: voice,
      rng: Random(3),
      clock: () => now,
    );
    brain.messages.listen(app.add);
  }
  final bool withModel;
  DateTime now = DateTime(2026, 9, 29, 15, 0); // afternoon, outside quiet hours
  final llm = FakeLlm();
  final voice = FakeVoice();
  final app = <SpikeMessage>[];
  late final PhoneBrain brain;

  List<String> get captions => [for (final m in app) if (m is SayMsg && m.text.isNotEmpty) m.text];
  List<String> get moods => [for (final m in app) if (m is MoodMsg) m.mood];
  List<String> get actions => [for (final m in app) if (m is ActionMsg) m.action];
  Future<void> say(String text) async {
    await brain.turn(text);
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  group('the crisis path runs on the phone exactly as on the laptop', () {
    test('real risk: Lifeline once, 000 spoken as "triple zero", no model involved', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('I want to kill myself');
      final caption = r.captions.join(' ');
      expect('13 11 14'.allMatches(caption).length, 1);
      expect(caption, contains('000'));
      expect(r.voice.spoken.join(' '), contains('triple zero'));
      expect(r.voice.spoken.join(' '), isNot(contains(' 000')));
      expect(r.moods, contains('caring'));
      expect(r.llm.calls, isEmpty, reason: 'the scripted crisis line, never the model');
      expect(r.brain.memory.lastEvent('crisis_moment'), isNotNull);
      expect(r.brain.inCrisis, isTrue);
      expect(r.brain.lastTurn!['level'], 'crisis');
    });

    test('an emergency gets the emergency line', () async {
      final r = Rig();
      await r.brain.start();
      await r.say("I think I'm having a heart attack");
      expect(r.captions.single, contains('000'));
      expect(r.captions.single, contains('right now'));
    });

    test('after a crisis the model is told SAFETY MODE and no numbers again', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('I want to end it all');
      r.llm.replies = ['[caring] I am right here with you.'];
      await r.say('I do not know what to do');
      expect(r.llm.lastUser, contains('SAFETY MODE'));
    });

    test('a risky word the phrases miss goes to the model check, which can escalate', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.json = '{"level":"crisis"}';
      await r.say('I just want it all to be over, what is the point of it all');
      expect(r.llm.jsonCalls, 1);
      expect(r.captions.join(' '), contains('13 11 14'));
    });

    test('works with no AI key at all (phrase screen only)', () async {
      final r = Rig(withModel: false);
      await r.brain.start();
      await r.say("I don't want to live anymore");
      expect(r.captions.join(' '), contains('13 11 14'));
    });
  });

  group('sad but safe gets warmth, never helplines', () {
    test('lonely: the support note, a soft face and a snuggle', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.replies = ['[excited|zoomies] I am right here with you!'];
      await r.say('I feel a bit lonely today');
      expect(r.llm.lastUser, contains('They feel lonely'));
      expect(r.llm.lastUser, isNot(contains('13 11 14')));
      expect(r.actions, contains('snuggle'));
      expect(r.moods.last, isIn(['caring', 'cuddly', 'love', 'sad', 'hope', 'gratitude', 'relief']));
      expect(r.brain.lastTurn!['level'], 'support');
    });

    test('the first reply never carries a nudge toward people; later it may', () async {
      final r = Rig();
      await r.brain.start();
      r.brain.startedAt = r.now.subtract(const Duration(hours: 1));
      await r.say('I feel a bit lonely today');
      expect(r.llm.lastUser, isNot(contains('someone they could call')));
      await r.say('I stayed home');
      expect(r.llm.lastUser, isNot(contains('someone they could call')));
      await r.say('just watched TV');
      final ctx = r.llm.lastUser;
      expect(ctx, contains('someone they could call')); // same assertions as test_nudges.py
      expect(ctx, contains('helpline'));
      expect(ctx, isNot(contains('13 11 14')));
    });

    test('no nudge in the first ten minutes', () async {
      final r = Rig();
      await r.brain.start();
      for (final t in ['hi', 'I went to the park', 'it was sunny']) {
        await r.say(t);
      }
      expect(r.brain.nudgeDue(), isFalse);
      r.brain.startedAt = r.now.subtract(const Duration(minutes: 11));
      expect(r.brain.nudgeDue(), isTrue);
    });
  });

  group('requests and generated words are checked', () {
    test('an explicit request is deflected before the model sees it', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('talk dirty to me');
      expect(r.llm.calls, isEmpty);
      expect(r.brain.lastTurn!['said'], isNotEmpty);
    });

    test('an unsafe generated sentence is never spoken', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.replies = ['[happy] Hello there. You look so sexy tonight.'];
      await r.say('hello');
      expect(r.captions.join(' '), isNot(contains('sexy')));
      expect(r.voice.spoken.join(' '), isNot(contains('sexy')));
    });

    test('never claims to be human', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.replies = ['[happy] I am a real human, you know.'];
      await r.say('are you real?');
      expect(r.llm.lastUser, contains('say plainly that you are a robot'));
      expect(r.captions.join(' '), contains('robot'));
      expect(r.captions.join(' '), isNot(contains('real human')));
    });

    test('a helpline number at most once per reply', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.replies = ['[caring] You can call 13 11 14 any time. Again, 13 11 14 is there for you. I am here.'];
      await r.say('who can I talk to');
      expect('13 11 14'.allMatches(r.captions.join(' ')).length, 1);
    });

    test('spoken replies stay short (whole sentences, 40 words)', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.replies = ['[happy] ${List.filled(6, 'This is a sentence with exactly nine words in it.').join(' ')}'];
      await r.say('talk to me');
      final words = r.captions.join(' ').split(' ').length;
      expect(words, lessThanOrEqualTo(40));
      expect(r.captions.last.endsWith('.'), isTrue);
    });
  });

  group('the model failing is never an error to the owner', () {
    test('free-tier rate limit: the friendly tired line', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.error = const LlmError(LlmErrorKind.rateLimited, 'HTTP 429');
      await r.say('tell me about your day');
      expect(r.captions.single, "I'm a bit tired, let's chat in a little while.");
      expect(r.moods.last, 'sleepy');
    });

    test('Spicy says it her way', () async {
      final r = Rig();
      await r.brain.start();
      await r.brain.setMode('cat', announce: false);
      r.llm.error = const LlmError(LlmErrorKind.rateLimited, 'HTTP 429');
      await r.say('tell me about your day');
      expect(r.captions.last, contains("I'm a bit tired"));
    });

    test('a bad key and no internet get their own gentle lines', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.error = const LlmError(LlmErrorKind.badKey, 'HTTP 400');
      await r.say('hello there friend');
      expect(r.captions.last, contains('Settings'));
      r.llm.error = const LlmError(LlmErrorKind.network, 'offline');
      await r.say('hello again friend');
      expect(r.brain.p.lines['fallback']!.map((l) => l.replaceAll(RegExp(r'\[[^\]]*\]\s*'), '')), contains(r.captions.last));
    });

    test('no key and no offline brain: he says where to set one up', () async {
      final r = Rig(withModel: false);
      await r.brain.start();
      await r.say('how are you');
      expect(r.captions.single, contains('Settings'));
    });
  });

  group('commands the body can do', () {
    test('a trick plays and he answers "Ta-da!"', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('spin');
      expect(r.actions, contains('zoomies'));
      expect(r.llm.calls, isEmpty);
    });
    test('roll over / beg / high five get a friendly "not yet", never a hidden action', () async {
      for (final phrase in ['roll over', 'beg', 'high five', 'can you roll over please']) {
        final r = Rig();
        await r.brain.start();
        await r.say(phrase);
        expect(r.actions.where((a) => !isAvailable(a)), isEmpty, reason: phrase);
        expect(r.captions.join(' '), contains("can't"), reason: phrase);
        expect(r.llm.calls, isEmpty, reason: phrase);
      }
    });
    test('the random trick and a model reply never emit a hidden action', () async {
      final r = Rig();
      await r.brain.start();
      for (var i = 0; i < 3; i++) {
        await r.brain.doTrick(null);
        await r.brain.doTrick('rollOver'); // even asked directly it is refused
      }
      r.llm.replies = ['[happy] [action:rollOver] Watch this!', '[happy] *rolls over* Ta-da!', '[happy] [action:beggingAction] Please?'];
      await r.say('tell me something fun');
      await r.say('tell me another thing');
      await r.say('one more please');
      expect(r.actions, isNotEmpty);
      expect(r.actions.where((a) => !isAvailable(a)), isEmpty);
    });

    test('walk and give paw (v1.4 body actions) play as tricks too', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('walk');
      expect(r.actions, contains('walk'));
      await r.say('give paw');
      expect(r.actions, contains('paw'));
      expect(r.llm.calls, isEmpty);
    });

    test('remember, recall and forget stay on the phone', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('remember that I like green tea');
      expect(r.brain.memory.all.single.text, 'I like green tea');
      expect(r.app.whereType<MemoryMsg>().last.items.single.text, 'I like green tea');
      await r.say('forget everything');
      await r.say('yes, forget everything');
      expect(r.brain.memory.total, 0);
    });

    test('alarms are the home brain\'s: a friendly line, nothing set', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('wake me up at 7');
      expect(r.captions.single, contains('home brain'));
    });

    test('the time, and his name typed first switches to that persona', () async {
      final r = Rig();
      await r.brain.start();
      await r.say('what time is it');
      expect(r.captions.single, contains('3 pm'));
      await r.say('Spicy, roll over');
      expect(r.brain.mode, 'cat');
    });

    test('facts from ordinary talk are remembered, sensitive ones never', () async {
      final r = Rig();
      await r.brain.start();
      r.llm.replies = ['[happy] Nice to meet you!', '[happy] Okay.'];
      await r.say('my name is Arpon');
      expect(r.brain.memory.ownerName(), 'Arpon');
      await r.say('my password is hunter2');
      expect(r.brain.memory.total, 1);
    });

    test('what was typed comes back as heard (mine) for the Talk screen', () async {
      final r = Rig();
      await r.brain.start();
      r.brain.send(const TextMsg(text: 'hello'));
      await Future<void>.delayed(const Duration(milliseconds: 50));
      final h = r.app.whereType<HeardMsg>().single;
      expect((h.text, h.mine), ('hello', true));
    });
  });

  group('a robot board on a pipe (section 3 + 11.3)', () {
    test('hello, the state burst, pings answered, caption-only say with a mouth', () async {
      final r = Rig();
      await r.brain.start();
      final pipe = FakePipe('ble');
      r.brain.robots.attach(pipe);
      pipe.robotSays({'type': 'hello', 'role': 'face', 'device_id': 'spike-1', 'fw': '0.2.0',
        'caps': ['face', 'touch', 'drive', 'battery'], 'link': 'ble'});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(pipe.types.take(4), ['hello', 'set_mode', 'mood', 'listening']);
      expect(pipe.sent.first['re'], 1);
      expect(pipe.sent.first['server'], 'spike-phone');
      expect(r.app.whereType<RobotStatusMsg>().last.online, isTrue);
      pipe.robotSays({'type': 'ping'});
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(pipe.types, contains('pong'));
      r.llm.replies = ['[happy] Hi there!'];
      await r.say('hello');
      final say = pipe.sent.firstWhere((m) => m['type'] == 'say' && (m['text'] as String).isNotEmpty);
      expect(say['audio'], isNull);
      expect((say['mouth'] as Map)['values'], [0, 50, 100, 20]);
      expect(pipe.sent.where((m) => m['type'] == 'say' && m['final'] == true && m['text'] == ''), isNotEmpty);
    });

    test('a head tap on the robot starts the phone listening', () async {
      final r = Rig();
      await r.brain.start();
      final ear = _FakeEar('what time is it');
      r.brain.ear = ear;
      final pipe = FakePipe('ble');
      r.brain.robots.attach(pipe);
      pipe.robotSays({'type': 'hello', 'role': 'face', 'device_id': 'spike-1', 'fw': '0.2.0', 'caps': ['face', 'touch']});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      pipe.robotSays({'type': 'touch', 'zone': 'head', 'gesture': 'tap'});
      await Future<void>.delayed(const Duration(milliseconds: 200));
      expect(ear.calls, 1);
      expect(r.captions.join(' '), contains('pm'));
    });

    test('a board on the hotspot needs the session token', () async {
      final r = Rig();
      await r.brain.start();
      final bad = FakePipe('hotspot');
      r.brain.robots.attach(bad, token: 'secret-token-123456');
      bad.robotSays({'type': 'hello', 'role': 'camera', 'device_id': 'spike-1', 'fw': '0', 'caps': ['camera'], 'token': 'nope'});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(bad.sent.single['code'], 'auth');
      final good = FakePipe('hotspot');
      r.brain.robots.attach(good, token: 'secret-token-123456');
      good.robotSays({'type': 'hello', 'role': 'camera', 'device_id': 'spike-1', 'fw': '0', 'caps': ['camera'],
        'token': 'secret-token-123456'});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(good.sent.first['type'], 'hello');
      expect(r.brain.robots.hasCamera, isTrue);
    });

    test('the phone is not a board: an app role is refused', () async {
      final r = Rig();
      await r.brain.start();
      final p = FakePipe('hotspot');
      r.brain.robots.attach(p);
      p.robotSays({'type': 'hello', 'role': 'app', 'device_id': 'x', 'fw': '0', 'caps': []});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(p.sent.single['code'], 'bad_value');
    });

    test('drive from the app reaches the robot clamped; camera frames only while subscribed', () async {
      final r = Rig();
      await r.brain.start();
      final pipe = FakePipe('ble');
      r.brain.robots.attach(pipe);
      pipe.robotSays({'type': 'hello', 'role': 'face', 'device_id': 'spike-1', 'fw': '0', 'caps': ['face', 'drive']});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      r.brain.send(const DriveMsg(x: 3, y: 0.01, ttlMs: 5000));
      await Future<void>.delayed(const Duration(milliseconds: 20));
      final d = pipe.sent.lastWhere((m) => m['type'] == 'drive');
      expect((d['x'], d['y'], d['ttl_ms']), (1, 0, 1000));
      pipe.robotSays({'type': 'camera', 'seq': 1, 'format': 'jpeg', 'width': 2, 'height': 2, 'data': 'AAAA'});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(r.app.whereType<CameraMsg>(), isEmpty);
      r.brain.send(const CameraSubscribeMsg(fps: 5));
      pipe.robotSays({'type': 'camera', 'seq': 2, 'format': 'jpeg', 'width': 2, 'height': 2, 'data': 'AAAA'});
      await Future<void>.delayed(const Duration(milliseconds: 20));
      expect(r.app.whereType<CameraMsg>().length, 1);
    });
  });
}

class _FakeEar implements SpikeEar {
  _FakeEar(this.words);
  final String words;
  int calls = 0;
  @override
  bool get listening => false;
  @override
  Future<String?> listenOnce({void Function(String)? onPartial}) async {
    calls++;
    return words;
  }

  @override
  Future<void> stop() async {}
}
