import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/away/voice/turn_ear.dart';
import 'package:spike_app/core/haptics.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/features/life/memories_screen.dart';
import 'package:spike_app/features/settings/settings_screen.dart';
import 'package:spike_app/features/talk/ptt.dart';
import 'package:spike_app/features/talk/talk_screen.dart';
import 'package:spike_app/features/talk/voice_pill.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/protocol/messages.dart';
import 'package:spike_app/state/link.dart';
import 'package:spike_app/state/settings.dart';
import 'package:spike_app/state/voice.dart';

// ---------------------------------------------------------------- fakes
class FakeLink implements VoiceLink {
  @override
  bool away = false;
  @override
  bool canInterrupt = true;
  final audio = <AudioMsg>[];
  final heardTexts = <String>[];
  final awayListens = <bool>[];
  int taps = 0, interrupts = 0, keeps = 0;
  bool keepSupported = true;
  final _heard = StreamController<String>.broadcast();
  @override
  bool sendAudio(AudioMsg m) {
    audio.add(m);
    return true;
  }

  @override
  bool listenNow() {
    taps++;
    return true;
  }

  @override
  bool keepAlive() {
    if (!keepSupported) return false;
    keeps++;
    return true;
  }

  @override
  void heard(String text) => heardTexts.add(text);
  final sentTexts = <String>[];
  @override
  bool sendText(String text) {
    sentTexts.add(text);
    return true;
  }

  @override
  void awayListening(bool on) => awayListens.add(on);
  @override
  Future<void> interrupt() async => interrupts++;
  @override
  Stream<String> get heardWords => _heard.stream;
  void brainHeard(String t) => _heard.add(t);
}

class FakeMic implements MicStream {
  bool permission = true;
  StreamController<Uint8List>? ctl;
  int starts = 0, stops = 0;
  @override
  Future<bool> hasPermission() async => permission;
  @override
  Future<Stream<Uint8List>> start() async {
    starts++;
    ctl = StreamController<Uint8List>();
    return ctl!.stream;
  }

  @override
  Future<void> stop() async {
    stops++;
    await ctl?.close();
    ctl = null;
  }

  /// 100 ms of loud audio (so 2.5 chunks of 40 ms).
  void speak() => ctl?.add(Uint8List.fromList(List.generate(3200, (i) => i.isEven ? 0x00 : 0x30)));
}

class FakeEar implements TurnEar {
  Completer<EarTurn>? pending;
  int listens = 0, cancels = 0;
  Duration? wait;
  void Function(String)? onWords;
  @override
  Future<EarTurn> listenTurn({required Duration wait, void Function(String)? onWords, void Function(double)? onLevel}) {
    listens++;
    this.wait = wait;
    this.onWords = onWords;
    return (pending = Completer<EarTurn>()).future;
  }

  @override
  Future<void> cancel() async {
    cancels++;
    final p = pending;
    if (p != null && !p.isCompleted) p.complete(const EarTurn(EarEnd.cancelled));
  }

  void say(String t) {
    onWords?.call(t);
    pending!.complete(EarTurn(EarEnd.words, t));
  }
}

class FakeSpike extends SpikeStateNotifier {
  @override
  SpikeState build() => const SpikeState();
  void listening(String l) => state = state.copyWith(listening: l);
  void ringing(bool r) => state = state.copyWith(alarmRinging: r);
}

const connected = LinkStatus(phase: LinkPhase.connected, endpoint: BrainEndpoint(host: '192.168.1.20'));

class Rig {
  Rig(this.c, this.link, this.mic, this.ear, this.links);
  final ProviderContainer c;
  final FakeLink link;
  final FakeMic mic;
  final FakeEar ear;
  final StreamController<LinkStatus> links;
  VoiceController get voice => c.read(voiceProvider.notifier);
  VoiceState get state => c.read(voiceProvider);
  FakeSpike get spike => c.read(spikeStateProvider.notifier) as FakeSpike;

  static Future<Rig> make({bool away = false, LinkStatus first = connected}) async {
    SharedPreferences.setMockInitialValues({});
    final prefs = await SharedPreferences.getInstance();
    final link = FakeLink()..away = away;
    final mic = FakeMic();
    final ear = FakeEar();
    final links = StreamController<LinkStatus>.broadcast();
    final c = ProviderContainer(overrides: [
      prefsProvider.overrideWithValue(prefs),
      voiceLinkProvider.overrideWithValue(link),
      micStreamProvider.overrideWithValue(mic),
      turnEarProvider.overrideWithValue(ear),
      spikeStateProvider.overrideWith(FakeSpike.new),
      linkStatusProvider.overrideWith((ref) async* {
        yield first;
        yield* links.stream;
      }),
    ]);
    // listened, as the app's VoiceOverlay does (an unlistened provider is paused in Riverpod 3)
    c.listen(voiceProvider, (_, _) {});
    c.listen(spikeStateProvider, (_, _) {});
    await settle();
    return Rig(c, link, mic, ear, links);
  }

  Future<void> linkTo(LinkStatus s) async {
    links.add(s);
    await settle();
  }

  void dispose() {
    c.dispose();
    links.close();
  }
}

Future<void> settle([int ms = 20]) => Future<void>.delayed(Duration(milliseconds: ms));

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  Haptics.enabled = false;

  group('voice session (home: the laptop brain, mic streamed to its Whisper: the fallback)', () {
    setUp(() => VoiceController.phoneEarAtHome = false);
    tearDown(() => VoiceController.phoneEarAtHome = true);
    test('tap starts: the mic streams, with the owner\'s wait, and the brain is asked to listen', () async {
      final r = await Rig.make();
      expect(await r.voice.start(), isTrue);
      await settle();
      expect(r.state.phase, VoicePhase.listening);
      expect(r.mic.starts, 1);
      expect(r.link.taps, 1, reason: 'a head tap = listen now');
      r.mic.speak();
      await settle();
      expect(r.link.audio, isNotEmpty);
      expect(r.link.audio.every((m) => m.endSilenceMs == 3000), isTrue);
      expect(r.state.level, greaterThan(0));
      r.dispose();
    });

    test('quiet listening sends silent keep-alives, never a head tap; none while Spike talks', () async {
      VoiceController.keepAliveEvery = const Duration(milliseconds: 30);
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      final taps = r.link.taps;
      await settle(200);
      expect(r.link.keeps, greaterThanOrEqualTo(3));
      expect(r.link.taps, taps, reason: 'the keep-alive must not be a head tap (face flicker)');
      r.spike.listening('speaking');
      await settle(60);
      final k = r.link.keeps;
      await settle(150);
      expect(r.link.keeps, k, reason: 'nothing while Spike thinks or talks');
      await r.voice.stop();
      final k2 = r.link.keeps;
      await settle(150);
      expect(r.link.keeps, k2, reason: 'the timer stops with the session');
      r.dispose();
      VoiceController.keepAliveEvery = const Duration(seconds: 2);
    });

    test('an older brain: the keep-alive sends nothing and is never replaced by a tap', () async {
      VoiceController.keepAliveEvery = const Duration(milliseconds: 30);
      final r = await Rig.make();
      r.link.keepSupported = false;
      await r.voice.start();
      await settle();
      final taps = r.link.taps;
      await settle(200);
      expect(r.link.keeps, 0);
      expect(r.link.taps, taps);
      r.dispose();
      VoiceController.keepAliveEvery = const Duration(seconds: 2);
    });

    test('keep-alive support needs a v1.6 hello on the laptop link', () {
      const old = BrainHello(server: 's', version: '0.9', heartbeatS: 5, mode: 'dog');
      const neu = BrainHello(server: 's', version: '1.0', heartbeatS: 5, mode: 'dog', keepalive: true);
      expect(keepAliveSupported(away: false, legacy: false, hello: neu), isTrue);
      expect(keepAliveSupported(away: false, legacy: false, hello: old), isFalse);
      expect(keepAliveSupported(away: false, legacy: false, hello: null), isFalse);
      expect(keepAliveSupported(away: true, legacy: false, hello: neu), isFalse);
      expect(keepAliveSupported(away: false, legacy: true, hello: neu), isFalse);
    });

    test('tap again stops: mic closed, the turn in progress is closed with silence', () async {
      final r = await Rig.make();
      await r.voice.toggle();
      await settle();
      r.link.audio.clear();
      await r.voice.toggle();
      expect(r.state.on, isFalse);
      expect(r.mic.stops, 1);
      expect(r.link.audio.length, 15);
      expect(r.link.audio.every((m) => m.endSilenceMs == null), isTrue, reason: "the brain's own end silence again");
      r.dispose();
    });

    test('Spike thinking or talking pauses the stream; idle resumes and re-opens listening', () async {
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      r.spike.listening('speaking');
      await settle();
      expect(r.state.phase, VoicePhase.paused);
      expect(r.state.spikeTalking, isTrue);
      r.link.audio.clear();
      r.mic.speak();
      await settle();
      expect(r.link.audio, isEmpty, reason: 'his own voice is never sent');
      final taps = r.link.taps;
      r.spike.listening('idle');
      await settle(450);
      expect(r.state.phase, VoicePhase.listening);
      expect(r.link.taps, taps + 1);
      r.mic.speak();
      await settle();
      expect(r.link.audio, isNotEmpty);
      r.dispose();
    });

    test('no re-arm tap while an alarm rings (a head tap would snooze it)', () async {
      final r = await Rig.make();
      r.spike.ringing(true);
      await r.voice.start();
      await settle(450);
      expect(r.link.taps, 0);
      r.spike.ringing(false);
      await settle(450);
      expect(r.link.taps, 1);
      r.dispose();
    });

    test('a tap on the pill while he talks interrupts him', () async {
      final r = await Rig.make();
      await r.voice.start();
      r.spike.listening('speaking');
      await settle();
      await r.voice.interrupt();
      expect(r.link.interrupts, 1);
      r.dispose();
    });

    test('the app going to the background stops it (inactive, like a permission prompt, does not)', () async {
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      r.voice.onLifecycle(AppLifecycleState.inactive);
      await settle();
      expect(r.state.on, isTrue);
      r.voice.onLifecycle(AppLifecycleState.paused);
      await settle();
      expect(r.state.on, isFalse);
      expect(r.mic.stops, 1);
      expect(r.state.notice, contains('only listens while the app is open'));
      r.dispose();
    });

    test('a refused microphone stops it with a clear notice', () async {
      final r = await Rig.make();
      r.mic.permission = false;
      expect(await r.voice.start(), isFalse);
      expect(r.state.on, isFalse);
      expect(r.state.notice, 'Allow the microphone to talk to Spike');
      r.dispose();
    });

    test('not connected: nothing starts', () async {
      final r = await Rig.make(first: const LinkStatus());
      expect(await r.voice.start(), isFalse);
      expect(r.state.on, isFalse);
      expect(r.mic.starts, 0);
      expect(r.state.notice, contains("isn't connected"));
      r.dispose();
    });

    test('the link drops: waiting (mic closed), then back to listening when Spike returns', () async {
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      await r.linkTo(const LinkStatus(phase: LinkPhase.retrying, attempt: 1));
      expect(r.state.phase, VoicePhase.waiting);
      expect(r.state.on, isTrue);
      expect(r.mic.stops, 1);
      await r.linkTo(connected);
      await settle();
      expect(r.state.phase, VoicePhase.listening);
      expect(r.mic.starts, 2);
      r.dispose();
    });

    test('pairing refused = gone for good: it stops', () async {
      final r = await Rig.make();
      await r.voice.start();
      await r.linkTo(const LinkStatus(phase: LinkPhase.authFailed));
      expect(r.state.on, isFalse);
      expect(r.state.notice, contains('Lost touch'));
      r.dispose();
    });

    test('waiting too long for a lost brain stops it (and says so)', () async {
      final keep = VoiceController.lostAfter;
      VoiceController.lostAfter = const Duration(milliseconds: 100);
      final r = await Rig.make();
      await r.voice.start();
      await r.linkTo(const LinkStatus(phase: LinkPhase.retrying, attempt: 1));
      await settle(200);
      expect(r.state.on, isFalse);
      VoiceController.lostAfter = keep;
      r.dispose();
    });

    test('the wait setting is clamped to 1.5..6 s and sent with the stream', () async {
      final r = await Rig.make();
      r.c.read(settingsProvider.notifier).update((s) => s.copyWith(voiceWaitS: 10));
      expect(r.c.read(settingsProvider).voiceWaitS, 6);
      r.c.read(settingsProvider.notifier).update((s) => s.copyWith(voiceWaitS: 0.2));
      expect(r.c.read(settingsProvider).voiceWaitS, 1.5);
      r.c.read(settingsProvider.notifier).update((s) => s.copyWith(voiceWaitS: 4.5));
      await r.voice.start();
      await settle();
      r.mic.speak();
      await settle();
      expect(r.link.audio.first.endSilenceMs, 4500);
      r.dispose();
    });

    test('what the brain heard shows briefly as a caption', () async {
      final r = await Rig.make();
      await r.voice.start();
      r.link.brainHeard('what time is it');
      await settle();
      expect(r.state.caption, 'what time is it');
      r.dispose();
    });
  });

  // Owner bug 30 Sep: at home the laptop's CPU Whisper (base.en) misheard him. Now the phone's own
  // recognizer hears the turn (same as away) and the laptop brain gets the words as `text`.
  group('voice session (home: the phone hears, the laptop gets text)', () {
    test('a spoken turn goes to the laptop as text; no mic stream; keep-alives still sent', () async {
      VoiceController.keepAliveEvery = const Duration(milliseconds: 30);
      final r = await Rig.make();
      expect(await r.voice.start(), isTrue);
      await settle();
      expect(r.state.phase, VoicePhase.listening);
      expect(r.mic.starts, 0, reason: 'no raw audio to the laptop');
      expect(r.ear.listens, 1);
      expect(r.ear.wait, const Duration(seconds: 3), reason: "the owner's wait");
      await settle(120);
      expect(r.link.keeps, greaterThanOrEqualTo(2));
      r.ear.say('what time is it');
      await settle();
      expect(r.link.sentTexts, ['what time is it']);
      expect(r.link.heardTexts, isEmpty, reason: 'not the phone brain: the laptop is the brain at home');
      expect(r.link.awayListens, isEmpty);
      expect(r.state.phase, VoicePhase.paused);
      VoiceController.keepAliveEvery = const Duration(seconds: 2);
      r.dispose();
    });

    test('does not hear himself: Spike talking cancels the ear; it listens again after', () async {
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      r.ear.say('tell me a joke');
      await settle();
      r.spike.listening('speaking');
      await settle();
      expect(r.state.phase, VoicePhase.paused);
      final before = r.ear.listens;
      r.spike.listening('idle');
      await settle();
      expect(r.state.phase, VoicePhase.listening);
      expect(r.ear.listens, before + 1);
      r.dispose();
    });

    test('Spike speaking on his own mid-listen: the ear is cancelled (his voice is never sent)', () async {
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      r.spike.listening('speaking');
      await settle();
      expect(r.ear.cancels, greaterThanOrEqualTo(1));
      expect(r.link.sentTexts, isEmpty);
      r.dispose();
    });

    test('no phone recognizer: falls back to streaming the mic to the laptop', () async {
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      r.ear.pending!.complete(const EarTurn(EarEnd.unavailable));
      await settle(60);
      expect(r.state.on, isTrue);
      expect(r.mic.starts, 1, reason: 'the laptop Whisper path');
      r.mic.speak();
      await settle();
      expect(r.link.audio, isNotEmpty);
      r.dispose();
    });

    test('tapping off right after speaking still sends what was heard', () async {
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      r.ear.onWords!('good night spike');
      await settle();
      await r.voice.stop();
      await settle();
      expect(r.link.sentTexts, ['good night spike']);
      r.dispose();
    });
  });

  group('voice session (away: the phone brain)', () {
    test('listens a whole turn, hands it to the phone brain, pauses for the reply, listens again', () async {
      final r = await Rig.make(away: true);
      await r.voice.start();
      await settle();
      expect(r.ear.listens, 1);
      expect(r.ear.wait, const Duration(seconds: 3));
      expect(r.link.awayListens.last, isTrue);
      r.ear.say('tell me a joke');
      await settle();
      expect(r.link.heardTexts, ['tell me a joke']);
      expect(r.state.phase, VoicePhase.paused);
      r.spike.listening('thinking');
      await settle();
      r.spike.listening('speaking');
      await settle();
      expect(r.ear.listens, 1, reason: 'the ear stays closed while he talks');
      r.spike.listening('idle');
      await settle();
      expect(r.state.phase, VoicePhase.listening);
      expect(r.ear.listens, 2);
      r.dispose();
    });

    test('Spike speaking on his own closes the ear (never transcribes himself), then it listens again', () async {
      final r = await Rig.make(away: true);
      await r.voice.start();
      await settle();
      r.spike.listening('speaking');
      await settle();
      expect(r.ear.cancels, 1);
      expect(r.state.phase, VoicePhase.paused);
      r.spike.listening('idle');
      await settle();
      expect(r.ear.listens, 2);
      r.dispose();
    });

    test('tapping off right after speaking still sends what was heard', () async {
      final r = await Rig.make(away: true);
      await r.voice.start();
      await settle();
      r.ear.onWords!('remind me to call mum');
      await r.voice.stop();
      expect(r.link.heardTexts, ['remind me to call mum']);
      expect(r.state.on, isFalse);
      r.dispose();
    });

    test('home <-> away switch under a running session changes the ear, and stays on', () async {
      VoiceController.phoneEarAtHome = false; // home on the mic-stream path here
      addTearDown(() => VoiceController.phoneEarAtHome = true);
      final r = await Rig.make();
      await r.voice.start();
      await settle();
      expect(r.mic.starts, 1);
      r.link.away = true;
      await r.linkTo(const LinkStatus(phase: LinkPhase.connected, brain: BrainHost.phone));
      await settle();
      expect(r.mic.stops, 1);
      expect(r.ear.listens, 1);
      expect(r.state.on, isTrue);
      expect(r.state.away, isTrue);
      r.dispose();
    });
  });

  group('turn stitching (Android recognizer sessions)', () {
    test('sessions that end on a short pause are joined; the turn ends only after the full wait', () {
      var now = DateTime(2026, 9, 30, 12);
      final st = TurnStitcher(wait: const Duration(seconds: 3), clock: () => now);
      expect(st.complete(), isFalse, reason: 'nothing said yet');
      st.partial('so I was');
      st.partial('so I was thinking');
      st.sessionEnded(); // Samsung ended the session after a 1 s breath
      now = now.add(const Duration(milliseconds: 1500));
      expect(st.complete(), isFalse);
      st.partial('about the weekend');
      now = now.add(const Duration(milliseconds: 2900));
      expect(st.complete(), isFalse);
      expect(st.text, 'so I was thinking about the weekend');
      now = now.add(const Duration(milliseconds: 200));
      expect(st.complete(), isTrue);
    });

    test('recognizer sound level maps to 0..1', () {
      expect(levelFromDb(-10), 0);
      expect(levelFromDb(10), 1);
      expect(levelFromDb(4), closeTo(0.5, 0.01));
    });

    test('the pcm chunker cuts 40 ms chunks and keeps the rest', () {
      final ch = PcmChunker(1280);
      expect(ch.add(Uint8List(1000)), isEmpty);
      final out = ch.add(Uint8List(2000));
      expect(out.length, 2);
      expect(out.every((c) => c.length == 1280), isTrue);
    });
  });

  // ---------------------------------------------------------------- the pill on every screen
  group('voice pill', () {
    // the owner's S23 Ultra: 1440 x 3088 px at 3.5 = 411 dp wide
    Future<Rig> pumpApp(WidgetTester t, Widget home) async {
      t.view.physicalSize = const Size(1440, 3088);
      t.view.devicePixelRatio = 3.5;
      addTearDown(t.view.reset);
      late Rig r;
      await t.runAsync(() async => r = await Rig.make());
      await t.pumpWidget(UncontrolledProviderScope(
        container: r.c,
        child: MaterialApp(
          theme: buildTheme(Brightness.light),
          builder: (context, child) => VoiceOverlay(child: child!),
          home: home,
        ),
      ));
      await t.pump(const Duration(milliseconds: 100));
      return r;
    }

    Future<void> frames(WidgetTester t, [int n = 12]) async {
      for (var i = 0; i < n; i++) {
        await t.pump(const Duration(milliseconds: 50));
      }
    }

    testWidgets('hidden while off; on every screen while on; the stop button ends it', (t) async {
      final r = await pumpApp(t, const TalkScreen());
      expect(find.byKey(const ValueKey('voicePill')), findsNothing);
      // the Talk screen's mic: one tap starts it (no holding)
      await t.tap(find.bySemanticsLabel('Start listening'));
      await t.runAsync(() => settle(50));
      await frames(t);
      expect(r.state.on, isTrue);
      expect(find.byKey(const ValueKey('voicePill')), findsOneWidget);
      expect(find.bySemanticsLabel('Stop listening'), findsWidgets, reason: 'the Talk mic now says stop, like the pill');
      expect(find.byKey(const ValueKey('voicePillStop')), findsOneWidget);
      // navigate: Settings, then Memories; it keeps listening and the pill stays
      final nav = t.state<NavigatorState>(find.byType(Navigator).first);
      nav.push(MaterialPageRoute<void>(builder: (_) => const SettingsScreen()));
      await frames(t);
      expect(find.byType(SettingsScreen), findsOneWidget);
      expect(find.byKey(const ValueKey('voicePill')), findsOneWidget);
      nav.push(MaterialPageRoute<void>(builder: (_) => const MemoriesScreen()));
      await frames(t);
      expect(find.byKey(const ValueKey('voicePill')), findsOneWidget);
      // tapping elsewhere on the screen does not stop it
      await t.tapAt(const Offset(200, 300));
      await frames(t, 4);
      expect(r.state.on, isTrue);
      // the pill's stop button does
      await t.tap(find.byKey(const ValueKey('voicePillStop')));
      await t.runAsync(() => settle(50));
      await frames(t);
      expect(r.state.on, isFalse);
      expect(find.byKey(const ValueKey('voicePill')), findsNothing);
      r.dispose();
    });

    testWidgets('the pill says when Spike talks, and fits its text on a phone', (t) async {
      final r = await pumpApp(t, const MemoriesScreen());
      await t.runAsync(() async {
        await r.voice.start();
        r.spike.listening('speaking');
        await settle(50);
      });
      await frames(t);
      expect(find.textContaining('is talking'), findsOneWidget);
      expect(find.text('Tap to cut in'), findsOneWidget);
      final pill = t.getSize(find.byKey(const ValueKey('voicePill')));
      expect(pill.width, closeTo(1440 / 3.5 - 32, 0.1));
      expect(pill.height, voicePillHeight);
      // no clipped label: its text fits (ellipsis only for long captions)
      for (final text in ['Spike is talking', 'Tap to cut in']) {
        expect(t.renderObject<RenderParagraph>(find.text(text)).didExceedMaxLines, isFalse, reason: text);
      }
      r.dispose();
    });
  });
}
