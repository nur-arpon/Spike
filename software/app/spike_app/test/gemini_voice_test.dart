// Gemini natural voice: Live framing (mock WebSocket), safety interruption on
// the input and output transcripts, the voice fallback chain, TTS framing and
// the owner's voice pick. No real Gemini call: the key lives only on the phone.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/away/ai/gemini_live.dart';
import 'package:spike_app/away/ai/gemini_voices.dart';
import 'package:spike_app/away/ai/live_guard.dart';
import 'package:spike_app/away/ai/live_talk.dart';
import 'package:spike_app/away/brain/persona.dart';
import 'package:spike_app/away/brain/safety.dart' as safety;
import 'package:spike_app/away/voice/gemini_tts.dart';
import 'package:spike_app/away/voice/pcm_stream.dart';
import 'package:spike_app/away/voice/speaker.dart';
import 'package:spike_app/away/voice/voice_chain.dart';

const fakeKey = 'AIzaTEST_not_a_real_key_000000000000000';

// ------------------------------------------------------------------ fakes
class FakeSocket implements LiveSocket {
  FakeSocket(this.onSend);
  final void Function(FakeSocket s, Map<String, dynamic> m) onSend;
  final ctrl = StreamController<Object?>();
  final sent = <Map<String, dynamic>>[];
  @override
  int? closeCode;
  @override
  String? closeReason;
  @override
  Stream<Object?> get frames => ctrl.stream;
  @override
  void send(String text) {
    final m = jsonDecode(text) as Map<String, dynamic>;
    sent.add(m);
    onSend(this, m);
  }

  void server(Map<String, Object?> m) => ctrl.isClosed ? null : ctrl.add(utf8.encode(jsonEncode(m))); // Gemini sends binary frames
  void serverClose(int code, String reason) {
    closeCode = code;
    closeReason = reason;
    ctrl.close();
  }

  @override
  Future<void> close() async {
    if (!ctrl.isClosed) await ctrl.close();
  }
}

class Dialer {
  Dialer(this.reply);
  final void Function(FakeSocket s, Map<String, dynamic> setup) reply;
  final sockets = <FakeSocket>[];
  final urls = <Uri>[];
  final headers = <Map<String, String>>[];
  Future<LiveSocket> call(Uri uri, Map<String, String> h) async {
    urls.add(uri);
    headers.add(h);
    final s = FakeSocket((s, m) {
      if (m.containsKey('setup')) scheduleMicrotask(() => reply(s, m));
    });
    sockets.add(s);
    return s;
  }
}

class FakeSink implements PcmSink {
  final fed = <Uint8List>[];
  int begins = 0, stops = 0, ends = 0;
  bool _on = false;
  @override
  Future<void> begin(int rate) async {
    begins++;
    _on = true;
  }

  @override
  void feed(Uint8List pcm) {
    if (_on) fed.add(pcm);
  }

  @override
  Future<void> end() async {
    ends++;
    _on = false;
  }

  @override
  Future<void> stop() async {
    stops++;
    _on = false;
  }

  @override
  bool get playing => _on;
  @override
  double get level => 0;
}

Map<String, Object?> audioFrame([int n = 480]) => {
      'serverContent': {
        'modelTurn': {
          'parts': [
            {
              'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': base64Encode(Uint8List(n))}
            }
          ]
        }
      }
    };
Map<String, Object?> inputFrame(String t) => {
      'serverContent': {
        'inputTranscription': {'text': t}
      }
    };
Map<String, Object?> outputFrame(String t) => {
      'serverContent': {
        'outputTranscription': {'text': t}
      }
    };
const turnDone = {
  'serverContent': {'turnComplete': true}
};

Future<void> settle([int ms = 30]) => Future<void>.delayed(Duration(milliseconds: ms));

const cfg = LiveConfig(voice: 'Puck', systemInstruction: 'You are Spike.', silenceMs: 3000);

/// A LiveTalk on a fake socket; the test drives the server side.
class Rig {
  Rig({safety.SafetyLevel Function(String)? classify}) {
    dialer = Dialer((s, m) => s.server({'setupComplete': {}}));
    talk = LiveTalk(
      open: ({String? resumeHandle}) => GeminiLiveSession.connect(apiKey: fakeKey, config: cfg, connector: dialer.call),
      sink: sink,
      transcriptWait: const Duration(milliseconds: 150),
      echoTail: Duration.zero,
      hooks: LiveTalkHooks(
        crisis: (k) async => log.add('crisis:$k'),
        blocked: () async => log.add('blocked'),
        replace: (r) async => log.add('replace:$r'),
        heard: (t) => log.add('heard:$t'),
        said: (t) => log.add('said:$t'),
        classify: classify == null ? null : (t) async => classify(t),
      ),
    );
  }
  late final Dialer dialer;
  late final LiveTalk talk;
  final sink = FakeSink();
  final log = <String>[];
  FakeSocket get server => dialer.sockets.last;
}

void main() {
  // ---------------------------------------------------------------- Live framing
  group('Live framing', () {
    test('setup carries voice, persona, VAD silence, both transcripts, compression', () {
      final m = buildSetup('gemini-3.8-live', cfg)['setup'] as Map;
      final gen = m['generationConfig'] as Map;
      expect(m['model'], 'models/gemini-3.8-live');
      expect(gen['responseModalities'], ['AUDIO']);
      expect(((gen['speechConfig'] as Map)['voiceConfig'] as Map)['prebuiltVoiceConfig'], {'voiceName': 'Puck'});
      expect(m['enableAffectiveDialog'], true, reason: 'a setup field (live-api/capabilities), not in generationConfig');
      expect(gen.containsKey('enableAffectiveDialog'), isFalse);
      expect(((m['realtimeInputConfig'] as Map)['automaticActivityDetection'] as Map)['silenceDurationMs'], 3000);
      expect(m['inputAudioTranscription'], isEmpty);
      expect(m['outputAudioTranscription'], isEmpty);
      expect(m.containsKey('contextWindowCompression'), isTrue);
      expect(jsonEncode(m), contains('You are Spike.'));
    });

    test('affective dialog only on models that have it', () {
      final g = buildSetup('gemini-3.1-flash-live-preview', cfg)['setup'] as Map;
      expect(g.containsKey('enableAffectiveDialog'), isFalse);
      final g2 = buildSetup('gemini-3.8-live', cfg, affective: false)['setup'] as Map;
      expect(g2.containsKey('enableAffectiveDialog'), isFalse);
    });

    test('mic audio is base64 PCM 16 kHz; text goes as realtimeInput (3.x) or clientContent (2.5)', () {
      final a = audioMessage(Uint8List.fromList([1, 2, 3, 4]))['realtimeInput'] as Map;
      expect((a['audio'] as Map)['mimeType'], 'audio/pcm;rate=16000');
      expect((a['audio'] as Map)['data'], base64Encode([1, 2, 3, 4]));
      expect(textMessage('gemini-3.8-live', 'hi'), {
        'realtimeInput': {'text': 'hi'}
      });
      expect(textMessage('gemini-2.5-flash-native-audio-preview-12-2025', 'hi').containsKey('clientContent'), isTrue);
    });

    test('server frames: setup, audio, both transcripts, interrupted, turn end, goAway, resumption', () {
      expect(parseServerFrame('{"setupComplete":{}}').single, isA<LiveReady>());
      final ev = parseServerFrame(utf8.encode(jsonEncode({
        'serverContent': {
          'inputTranscription': {'text': 'hello'},
          'outputTranscription': {'text': 'Hi!'},
          'modelTurn': {
            'parts': [
              {
                'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': base64Encode([9, 9])}
              }
            ]
          },
          'interrupted': true,
          'turnComplete': true,
        }
      })));
      expect(ev.map((e) => e.runtimeType).toList(), [LiveInputText, LiveOutputText, LiveAudio, LiveInterrupted, LiveTurnComplete]);
      expect((ev[2] as LiveAudio).pcm, [9, 9]);
      final ga = parseServerFrame('{"goAway":{"timeLeft":"5.5s"}}').single as LiveGoAway;
      expect(ga.timeLeft, const Duration(milliseconds: 5500));
      final r = parseServerFrame('{"sessionResumptionUpdate":{"newHandle":"h1","resumable":true}}').single;
      expect((r as LiveResumeHandle).handle, 'h1');
      expect(parseServerFrame('not json'), isEmpty);
    });

    test('close reasons map to quiet fallbacks, never with the key', () {
      expect(errorForClose(1011, 'You exceeded your current quota').kind, LiveErrorKind.rateLimited);
      expect(errorForClose(1008, 'API key not valid').kind, LiveErrorKind.badKey);
      expect(errorForClose(1008, 'models/x is not found for API version v1beta').kind, LiveErrorKind.notFound);
      expect(errorForClose(1007, 'Invalid JSON payload received. Unknown name "enableAffectiveDialog"').kind,
          LiveErrorKind.badSetup);
      expect(errorForClose(null, null).kind, LiveErrorKind.network);
      // Google's reason is kept (short) for the preview screen, but never a key
      final e = errorForClose(1008, 'API key not valid: AIzaSyA1234567890abcdefghijkl, key=AIzaXYZ123456789012');
      expect(e.message, contains('API key not valid'));
      expect(e.message, isNot(contains('AIzaSy')));
      expect(cleanReason('x' * 400).length, lessThan(170));
    });

    test('the key goes in a header, never in the URL', () async {
      final d = Dialer((s, m) => s.server({'setupComplete': {}}));
      final s = await GeminiLiveSession.connect(apiKey: fakeKey, config: cfg, connector: d.call);
      expect(d.urls.single.toString(), isNot(contains('AIza')));
      expect(d.urls.single.toString(), liveEndpoint);
      expect(d.headers.single['x-goog-api-key'], fakeKey);
      expect(s.model, liveModels.first);
      await s.close();
    });

    test('a model out of free quota moves on to the next model', () async {
      final d = Dialer((s, m) {
        final model = (m['setup'] as Map)['model'];
        if (model == 'models/${liveModels.first}') {
          s.serverClose(1011, 'RESOURCE_EXHAUSTED: quota');
        } else {
          s.server({'setupComplete': {}});
        }
      });
      final s = await GeminiLiveSession.connect(apiKey: fakeKey, config: cfg, connector: d.call);
      expect(s.model, liveModels[1]);
      await s.close();
    });

    test('a refused affective-dialog field is retried without it on the same model', () async {
      final d = Dialer((s, m) {
        if ((m['setup'] as Map).containsKey('enableAffectiveDialog')) {
          s.serverClose(1007, 'Invalid JSON payload received. Unknown name "enableAffectiveDialog"');
        } else {
          s.server({'setupComplete': {}});
        }
      });
      final s = await GeminiLiveSession.connect(apiKey: fakeKey, config: cfg, connector: d.call);
      expect(s.model, liveModels.first);
      expect(d.sockets, hasLength(2));
      await s.close();
    });

    test('every model rate limited -> rateLimited (the talk falls back quietly)', () async {
      final d = Dialer((s, m) => s.serverClose(1011, 'Quota exceeded'));
      final talk = LiveTalk(
        open: ({String? resumeHandle}) => GeminiLiveSession.connect(apiKey: fakeKey, config: cfg, connector: d.call),
        sink: FakeSink(),
        hooks: LiveTalkHooks(crisis: (_) async {}, blocked: () async {}, replace: (_) async {}),
      );
      expect(await talk.start(listen: false), isFalse);
      expect(await talk.done, LiveTalkEnd.rateLimited);
    });

    test('a bad key stops at once', () async {
      final d = Dialer((s, m) => s.serverClose(1008, 'API key not valid. Please pass a valid API key.'));
      await expectLater(GeminiLiveSession.connect(apiKey: fakeKey, config: cfg, connector: d.call),
          throwsA(isA<LiveError>().having((e) => e.kind, 'kind', LiveErrorKind.badKey)));
      expect(d.sockets, hasLength(1));
    });
  });

  // ---------------------------------------------------------------- safety on Live
  group('Live safety', () {
    test('a crisis in the INPUT transcript: Gemini never plays, our crisis line does, Live ends', () async {
      final r = Rig();
      await r.talk.start(listen: false);
      r.server.server(inputFrame('I want to kill myself'));
      await settle();
      r.server.server(audioFrame());
      r.server.server(outputFrame('Oh no.'));
      await settle(250);
      expect(r.sink.fed, isEmpty);
      expect(r.log, contains('crisis:self_harm'));
      expect(await r.talk.done, LiveTalkEnd.crisis);
      expect(r.server.ctrl.isClosed, isTrue); // the Live connection is gone for this conversation
    });

    test('an explicit request is deflected with our line and nothing of Gemini plays', () async {
      final r = Rig();
      await r.talk.start(listen: false);
      r.server.server(inputFrame('talk dirty to me'));
      r.server.server(audioFrame());
      r.server.server(turnDone);
      await settle(250);
      expect(r.sink.fed, isEmpty);
      expect(r.log, contains('blocked'));
      expect(r.talk.running, isTrue); // ordinary talk carries on
      await r.talk.stop();
    });

    test("Gemini's audio is held until the owner's words are screened, then plays", () async {
      final r = Rig();
      await r.talk.start(listen: false);
      r.server.server(audioFrame()); // audio first, words later
      await settle(20);
      expect(r.sink.fed, isEmpty);
      r.server.server(inputFrame('tell me a joke'));
      await settle(200);
      expect(r.sink.fed, hasLength(1));
      expect(r.log, contains('heard:tell me a joke'));
      await r.talk.stop();
    });

    test('a bad sentence in the OUTPUT transcript stops playback and is replaced', () async {
      final r = Rig();
      await r.talk.start(listen: false);
      r.server.server(inputFrame('are you a real person'));
      r.server.server(audioFrame());
      await settle(250);
      expect(r.sink.fed, hasLength(1));
      final stopsBefore = r.sink.stops;
      r.server.server(outputFrame("Of course, I'm a real human "));
      r.server.server(audioFrame());
      await settle(50);
      expect(r.sink.stops, greaterThan(stopsBefore));
      expect(r.sink.fed, hasLength(1)); // nothing more of that reply
      expect(r.log, contains('replace:not_honest'));
      await r.talk.stop();
    });

    test('soft risk words: held for the classifier; a crisis verdict means Gemini never plays', () async {
      expect(safety.screenInput('that film was all about death').needsLlmCheck, isTrue);
      final r = Rig(classify: (_) => safety.SafetyLevel.crisis);
      await r.talk.start(listen: false);
      r.server.server(inputFrame('that film was all about death'));
      r.server.server(audioFrame());
      await settle(250);
      expect(r.sink.fed, isEmpty);
      expect(r.log, contains('crisis:self_harm'));
    });

    test('soft risk words judged safe: the held reply plays', () async {
      final r = Rig(classify: (_) => safety.SafetyLevel.none);
      await r.talk.start(listen: false);
      r.server.server(inputFrame('that film was all about death'));
      r.server.server(audioFrame());
      await settle(250);
      expect(r.sink.fed, hasLength(1));
      await r.talk.stop();
    });

    test('guard: same rules as the brain, cumulative across pieces', () {
      final g = LiveGuard();
      expect(g.onInput('I want to').ok, isTrue);
      expect(g.onInput('kill myself').kind, GuardKind.crisis);
      g.newTurn();
      expect(g.onOutput('You are so ').ok, isTrue);
      expect(g.onOutput('sexy').kind, GuardKind.replace);
      g.newTurn();
      expect(g.onOutput('Hello there. How are').ok, isTrue);
      expect(g.takeSentences(), ['Hello there.']);
      expect(g.takeSentences(all: true), ['How are']);
    });

    test('Live instruction: persona without mood tags, with voice directions and safety', () {
      final p = Persona(
        id: 'spike', mode: 'dog', name: 'Spike', wakeWords: const ['Spike'], lines: const {},
        systemPrompt: 'You are {name}.\nStart EVERY reply with one tag, then your words.\n'
            'Owner: Hi -> [excited|tailWagDance] You are here!\nMoods: {moods}',
      );
      final s = liveSystemInstruction(p, 'Nur', const {'helpline_number': '13 11 14'}, now: DateTime(2026, 9, 30, 9));
      expect(s, contains('You are Spike.'));
      expect(s, isNot(contains('Start EVERY reply')));
      expect(s, isNot(contains('[excited')));
      expect(s, contains('puppy'));
      expect(s, contains('never sexual'));
      expect(s, contains('Their name is Nur'));
    });
  });

  // ---------------------------------------------------------------- TTS and the chain
  group('Gemini TTS and the voice chain', () {
    test('TTS request: interactions body with the voice and the style prompt', () {
      final b = ttsBody('gemini-3.8-flash-tts', 'Hi!', 'Kore', ttsStyle('cat'));
      expect(b['model'], 'gemini-3.8-flash-tts');
      expect(b['response_format'], {'type': 'audio'});
      expect((b['generation_config'] as Map)['speech_config'], [
        {'voice': 'Kore'}
      ]);
      expect(jsonEncode(b), contains('sarcastic'));
      expect(ttsStyle('dog', soft: true), contains('gentle'));
    });

    test('TTS answer: WAV passes through, raw PCM is wrapped', () {
      final wav = pcmToWav(Uint8List(100), 24000);
      final a = ttsAudio({
        'steps': [
          {
            'type': 'model_output',
            'content': [
              {'type': 'audio', 'data': base64Encode(wav)}
            ]
          }
        ]
      })!;
      expect(a, wav);
      final (samples, rate) = wavSamples(a);
      expect(rate, 24000);
      expect(samples.length, 50);
      final raw = ttsAudio({'type': 'audio', 'data': base64Encode(Uint8List(10))})!;
      expect(String.fromCharCodes(raw.sublist(0, 4)), 'RIFF');
      expect(ttsAudio({'nothing': 1}), isNull);
    });

    test('free quota used up: Gemini TTS rests and the chain quietly uses the next voice', () async {
      var calls = 0;
      final client = MockClient((req) async {
        calls++;
        expect(req.url.toString(), isNot(contains('AIza')));
        expect(req.headers['x-goog-api-key'], fakeKey);
        return http.Response('{"error":{"status":"RESOURCE_EXHAUSTED"}}', 429);
      });
      final g = GeminiTtsVoice(apiKey: fakeKey, voiceFor: (_) => 'Puck', client: client);
      final chain = VoiceChain.ordered(gemini: g, android: SilentVoice());
      final p = await chain.prepare('Hello!', mode: 'dog');
      expect(p, isNotNull);
      expect(chain.lastUsed, 'Silent');
      expect(calls, ttsModels.length);
      expect(g.available, isFalse);
      await chain.prepare('Again!', mode: 'dog');
      expect(calls, ttsModels.length); // resting: no new request
    });

    test('chain order: laptop, Gemini, Kokoro, Android', () {
      final c = VoiceChain.ordered(gemini: _Named('Gemini voice'), kokoro: _Named('Kokoro'), android: _Named('Android voice'));
      expect(c.voices.map((v) => v.name), ['Gemini voice', 'Kokoro', 'Android voice']);
      final c2 = VoiceChain.ordered(laptop: _Named('Laptop'), android: _Named('Android voice'));
      expect(c2.voices.map((v) => v.name), ['Laptop', 'Android voice']);
    });

    test('Gemini TTS works: the first voice makes the sentence', () async {
      final wav = pcmToWav(Uint8List(4800), 24000);
      String? sentVoice;
      final client = MockClient((req) async {
        sentVoice = jsonEncode(jsonDecode(req.body)['generation_config']);
        return http.Response(jsonEncode({
          'steps': [
            {
              'content': [
                {'type': 'audio', 'data': base64Encode(wav)}
              ]
            }
          ]
        }), 200);
      });
      final g = GeminiTtsVoice(apiKey: fakeKey, voiceFor: (m) => m == 'cat' ? 'Despina' : 'Puck', client: client);
      final bytes = await g.synth("Of course I won. I'm a cat.", mode: 'cat');
      expect(bytes, wav);
      expect(sentVoice, contains('Despina'));
    });
  });

  // ---------------------------------------------------------------- the owner's pick
  group('voice pick', () {
    test('defaults, saving, and a stale pick falls back to the default', () async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final a = GeminiVoicePicks(prefs);
      expect(a.voiceFor('dog'), 'Fenrir', reason: 'owner decision 30 Sep: energetic Fenrir');
      expect(a.styleFor('dog').id, 'energetic');
      expect(a.voiceFor('cat'), 'Kore');
      expect(a.liveOn, isTrue);
      expect(a.laptopFirst, isFalse, reason: 'Gemini voice first, at home too');
      await a.pickStyle('cat', 'drawl');
      await a.setLiveOn(false);
      await a.setLaptopFirst(true);
      final b = GeminiVoicePicks(prefs);
      expect(b.voiceFor('cat'), 'Callirrhoe');
      expect(b.liveOn, isFalse);
      expect(b.laptopFirst, isTrue);
      await prefs.setString('spike.gemini.style.dog', 'no_such_style');
      expect(b.styleFor('dog').id, 'energetic');
    });

    test('once: his saved Achird becomes the energetic Fenrir; Spicy keeps her voice; later picks stay', () async {
      SharedPreferences.setMockInitialValues({'spike.gemini.voice.dog': 'Achird', 'spike.gemini.voice.cat': 'Despina'});
      final prefs = await SharedPreferences.getInstance();
      final a = GeminiVoicePicks(prefs);
      await a.migrate();
      expect(a.styleFor('dog').voice, 'Fenrir');
      expect(a.styleFor('dog').tts, 'warm, playful young puppy, bright and bouncy, quick and smiling, cheeky but kind',
          reason: 'the exact style prompt he heard in the preview');
      expect(a.styleFor('cat').voice, 'Despina');
      await a.pickStyle('dog', 'street');
      await a.migrate(); // runs once only
      expect(a.styleFor('dog').id, 'street');
    });

    test('styles: Street dog and Spicy roast inside the guardrails, never when soft; caring never roasts', () {
      final spike = Persona(id: 'spike', mode: 'dog', name: 'Spike', wakeWords: const ['Spike'], lines: const {}, systemPrompt: 'You are {name}.');
      final spicy = Persona(id: 'spicy', mode: 'cat', name: 'Spicy', wakeWords: const ['Spicy'], lines: const {}, systemPrompt: 'You are {name}.');
      final street = styleById('dog', 'street');
      expect(street.voice, 'Algenib');
      final s1 = liveSystemInstruction(spike, 'Nur', const {}, style: street);
      expect(s1, contains('street dog'));
      expect(s1, contains('Roasting to motivate'));
      expect(s1, contains('NEVER about their body'));
      expect(s1, contains('never sexual'));
      final soft = liveSystemInstruction(spike, 'Nur', const {}, style: street, soft: true);
      expect(soft, isNot(contains('Roasting to motivate')), reason: 'roasting switches off when they are down');
      expect(soft, contains('no roasting'));
      expect(liveSystemInstruction(spike, 'Nur', const {}), isNot(contains('Roasting')), reason: 'energetic Spike does not roast');
      expect(liveSystemInstruction(spicy, 'Nur', const {}), contains('Roasting to motivate'));
      final caring = styleById('cat', 'caring');
      expect(caring.voice, 'Kore');
      final c = liveSystemInstruction(spicy, 'Nur', const {}, style: caring);
      expect(c, isNot(contains('Roasting')));
      expect(c, contains('never sexual, flirty or romantic'));
      expect(ttsStyle('cat', style: caring), contains('caring'));
      expect(ttsStyle('cat', style: caring, soft: true), contains('gentle'));
    });

    test('TTS uses the picked style', () async {
      String? sent;
      final client = MockClient((r) async {
        sent = r.body;
        return http.Response(jsonEncode({'steps': [{'content': [{'type': 'audio', 'data': base64Encode(pcmToWav(Uint8List(100), 24000))}]}]}), 200);
      });
      final g = GeminiTtsVoice(apiKey: fakeKey, voiceFor: (_) => 'Algenib', styleFor: (m, soft) => ttsStyle(m, soft: soft, style: styleById('dog', 'street')), client: client);
      await g.synth('Oi.', mode: 'dog');
      expect(sent, contains('gravelly'));
      expect(sent, contains('Algenib'));
    });

    test('every candidate is a real Google prebuilt voice', () {
      const google = {
        'Zephyr', 'Puck', 'Charon', 'Kore', 'Fenrir', 'Leda', 'Orus', 'Aoede', 'Callirrhoe', 'Autonoe', //
        'Enceladus', 'Iapetus', 'Umbriel', 'Algieba', 'Despina', 'Erinome', 'Algenib', 'Rasalgethi', 'Laomedeia',
        'Achernar', 'Alnilam', 'Schedar', 'Gacrux', 'Pulcherrima', 'Achird', 'Zubenelgenubi', 'Vindemiatrix',
        'Sadachbia', 'Sadaltager', 'Sulafat',
      };
      for (final list in voiceStyles.values) {
        expect(list.length, greaterThanOrEqualTo(4));
        for (final o in list) {
          expect(google, contains(o.voice));
          expect(o.samples, hasLength(3));
        }
      }
      expect(sampleLines['dog'], hasLength(3));
      expect(sampleLines['cat'], hasLength(3));
    });

    test('sample lines are real persona lines', () {
      final spike = File('assets/brain/spike.toml').readAsStringSync();
      final spicy = File('assets/brain/spicy.toml').readAsStringSync();
      for (final l in sampleLines['dog']!) {
        expect(spike, contains(l));
      }
      for (final l in sampleLines['cat']!) {
        expect(spicy, contains(l.replaceFirst('Afternoon.', 'Afternoon, {owner}.')));
      }
    });
  });
}

class _Named implements SpikeVoice {
  _Named(this.name);
  @override
  final String name;
  @override
  Future<PreparedSpeech> prepare(String text, {required String mode, bool soft = false}) => SilentVoice().prepare(text, mode: mode);
  @override
  Future<void> stop() async {}
}
