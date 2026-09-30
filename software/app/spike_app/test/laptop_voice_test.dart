import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/away/voice/laptop_voice.dart';
import 'package:spike_app/away/voice/speaker.dart';
import 'package:spike_app/protocol/messages.dart';
import 'package:spike_app/state/link.dart';

/// A player that "plays" in real time: position = wall time since the first bytes, up to what was added.
class FakeStream implements VoiceStream {
  FakeStream(this.format, this.rate);
  final String format;
  final int rate;
  final adds = <Uint8List>[];
  Stopwatch? _sw;
  bool ended = false, stopped = false;

  @override
  void add(Uint8List bytes) {
    adds.add(bytes);
    _sw ??= Stopwatch()..start();
  }

  @override
  void end() => ended = true;

  /// Plays in real time from the first bytes; the player compares it with what it appended.
  @override
  Duration get position => _sw?.elapsed ?? Duration.zero;

  @override
  bool get done => stopped || (ended && position > const Duration(seconds: 2));

  @override
  Future<void> stop() async => stopped = true;
}

class FakeOutput implements VoiceOutput {
  final streams = <FakeStream>[];
  @override
  Future<VoiceStream> open({required String format, required int rate}) async {
    final s = FakeStream(format, rate);
    streams.add(s);
    return s;
  }
}

class FakePhoneVoice implements SpikeVoice {
  final said = <String>[];
  @override
  String get name => 'fake phone';
  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) async {
    said.add(text);
    return _P(const SpokenClip(durationMs: 60, mouth: [10, 50, 90]));
  }

  @override
  Future<void> stop() async {}
}

class _P implements PreparedSpeech {
  _P(this.clip);
  @override
  final SpokenClip clip;
  @override
  Future<void> play() => Future.delayed(Duration(milliseconds: clip.durationMs));
}

const rate = 24000;

SayMsg say(String utt, int seq, String text, {int? samples, int chunks = 1, String fmt = 'ogg_opus', bool last = false}) =>
    SayMsg(
      utt: utt, seq: seq, isFinal: last, text: text, durationMs: (samples ?? 0) * 1000 ~/ rate, play: true,
      audio: samples == null ? null : {'format': fmt, 'rate': rate, 'channels': 1, 'samples': samples, 'chunks': chunks},
      mouth: const {'rate_hz': 50, 'values': [0, 40, 80]},
    );

SayAudioMsg chunk(String utt, int seq, int i, {bool last = true}) =>
    SayAudioMsg(utt: utt, seq: seq, index: i, last: last, data: base64Encode(Uint8List.fromList([seq, i, 1, 2])));

void main() {
  late FakeOutput out;
  late FakePhoneVoice phone;
  late List<String> reports;
  late LaptopVoicePlayer p;
  VoiceOutput? outputOrNull;

  setUp(() {
    out = FakeOutput();
    outputOrNull = out;
    phone = FakePhoneVoice();
    reports = [];
    p = LaptopVoicePlayer(
      output: () async => outputOrNull,
      phoneVoice: () async => phone,
      report: (u, s, st) {
        reports.add('$u/$s/$st');
        return true;
      },
      mode: () => 'dog',
      tick: const Duration(milliseconds: 5),
      tail: const Duration(milliseconds: 30),
      waitNext: const Duration(seconds: 2),
    );
  });

  tearDown(() => p.dispose());

  Future<void> until(bool Function() ok, {int ms = 3000}) async {
    final end = DateTime.now().add(Duration(milliseconds: ms));
    while (!ok()) {
      if (DateTime.now().isAfter(end)) fail('timed out; reports=$reports said=${phone.said}');
      await Future<void>.delayed(const Duration(milliseconds: 5));
    }
  }

  test('sentences of one reply go into ONE stream back to back, reported in order', () async {
    final speaking = <bool>[];
    final saying = <int>[];
    p.speaking.listen(speaking.add);
    p.nowSaying.listen((m) => saying.add(m.seq));
    p.onMessage(say('u1', 0, 'Oh hi!', samples: 2400)); // 100 ms
    p.onMessage(chunk('u1', 0, 0));
    p.onMessage(say('u1', 1, 'Good to see you.', samples: 2400, chunks: 2, last: true));
    p.onMessage(chunk('u1', 1, 0, last: false));
    p.onMessage(chunk('u1', 1, 1));
    await until(() => reports.contains('u1/1/finished'));
    expect(out.streams, hasLength(1));
    final s = out.streams.single;
    expect(s.adds, hasLength(2)); // sentence 1, sentence 2 (its two chunks joined)
    expect(s.adds[1], Uint8List.fromList([1, 0, 1, 2, 1, 1, 1, 2]));
    expect(reports, ['u1/0/started', 'u1/0/finished', 'u1/1/started', 'u1/1/finished']);
    expect(saying, [0, 1]);
    expect(phone.said, isEmpty);
    await until(() => speaking.length == 2);
    expect(speaking, [true, false]);
    expect(p.lastHeard, VoiceHeard.laptop);
  });

  test('a sentence with no laptop audio is said by the phone voice, in its place', () async {
    p.onMessage(say('u2', 0, 'First.', samples: 1200));
    p.onMessage(chunk('u2', 0, 0));
    p.onMessage(say('u2', 1, 'Second from the phone.', last: true));
    await until(() => reports.contains('u2/1/finished'));
    expect(phone.said, ['Second from the phone.']);
    expect(reports.indexOf('u2/0/finished'), lessThan(reports.indexOf('u2/1/started')));
    expect(p.lastHeard, VoiceHeard.phone);
  });

  test('link lost mid-reply: what was announced is still said, the rest by the phone voice', () async {
    p.onMessage(say('u3', 0, 'I was saying.', samples: 1200));
    p.onMessage(chunk('u3', 0, 0));
    p.onMessage(say('u3', 1, 'Then the Wi-Fi went.', samples: 2400, chunks: 2));
    p.onMessage(chunk('u3', 1, 0, last: false)); // the second chunk never comes
    await Future<void>.delayed(const Duration(milliseconds: 20));
    p.onLinkLost();
    await until(() => phone.said.isNotEmpty && reports.where((r) => r.startsWith('u3/1/finished')).isNotEmpty);
    expect(phone.said, ['Then the Wi-Fi went.']);
    expect(out.streams.single.adds, hasLength(1)); // the half sentence was never played
  });

  test('no stream player on this phone: every sentence by the phone voice', () async {
    outputOrNull = null;
    p.onMessage(say('u4', 0, 'Hello.', samples: 1200));
    p.onMessage(chunk('u4', 0, 0));
    p.onMessage(const SayMsg(utt: 'u4', seq: 1, isFinal: true, text: '', durationMs: 0)); // end marker
    await until(() => reports.contains('u4/0/finished'));
    expect(phone.said, ['Hello.']);
  });

  test('a format the phone cannot play falls back to the phone voice', () async {
    p.onMessage(say('u5', 0, 'In mp3.', samples: 1200, fmt: 'mp3', last: true));
    p.onMessage(chunk('u5', 0, 0));
    await until(() => reports.contains('u5/0/finished'));
    expect(phone.said, ['In mp3.']);
    expect(out.streams, isEmpty);
  });

  test('stop_speaking cuts the stream', () async {
    p.onMessage(say('u6', 0, 'A very long story.', samples: 240000));
    p.onMessage(chunk('u6', 0, 0));
    await until(() => out.streams.isNotEmpty);
    p.onMessage(const StopSpeakingMsg(utt: 'u6'));
    await until(() => reports.contains('u6/0/stopped'));
    expect(out.streams.single.stopped, isTrue);
  });

  test('say without play (the robot or laptop plays it) is left alone', () async {
    p.onMessage(const SayMsg(utt: 'u7', seq: 0, isFinal: true, text: 'Not mine.', durationMs: 900));
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(reports, isEmpty);
    expect(p.isSpeaking, isFalse);
  });

  test('speech switched off on the phone: silent, but the timing and reports still run', () async {
    p = LaptopVoicePlayer(
      output: () async => out, phoneVoice: () async => phone, mode: () => 'cat', enabled: () => false,
      report: (u, s, st) {
        reports.add('$u/$s/$st');
        return true;
      },
      tick: const Duration(milliseconds: 5), tail: const Duration(milliseconds: 10),
    );
    p.onMessage(say('u8', 0, 'Shh.', samples: 1200, last: true));
    p.onMessage(chunk('u8', 0, 0));
    await until(() => reports.contains('u8/0/finished'));
    expect(out.streams, isEmpty);
    expect(phone.said, isEmpty);
  });

  test('codec negotiation: hello offers audio_out, Opus first; say.play round-trips', () {
    expect(appCaps, contains('audio_out'));
    expect(appAudioOut['formats'], ['ogg_opus', 'pcm_s16le']);
    final hello = ClientHello(role: 'app', deviceId: 'd', fw: '1', caps: appCaps, audioOut: appAudioOut);
    final j = jsonDecode(hello.encode(id: 1)) as Map<String, dynamic>;
    expect(j['audio_out']['formats'][0], 'ogg_opus');
    final m = SpikeMessage.decode(
        '{"v":1,"type":"say","id":3,"utt":"u1","seq":0,"final":false,"text":"Hi","duration_ms":500,'
        '"audio":{"format":"ogg_opus","rate":24000,"channels":1,"samples":12000,"chunks":1},"play":true}',
        from: Sender.brain) as SayMsg;
    expect(m.play, isTrue);
    final old = SpikeMessage.decode('{"v":1,"type":"say","id":3,"utt":"u1","seq":0,"final":false,"text":"Hi",'
        '"duration_ms":500,"audio":null}', from: Sender.brain) as SayMsg;
    expect(old.play, isFalse);
  });
}
