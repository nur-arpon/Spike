// Onboarding v2 (4 Oct 2026): a fresh install opens straight into the app, exploring. The first thing
// that needs Spike's brain asks for it with ONE friendly sheet: a free Gemini key (shape checked only)
// or the code on the owner's computer. Mocks only: no Gemini call, no network, no camera.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/app.dart';
import 'package:spike_app/away/ai/key_store.dart';
import 'package:spike_app/core/platform.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/features/connect/brain_needed.dart';
import 'package:spike_app/features/settings/settings_screen.dart';
import 'package:spike_app/features/talk/talk_screen.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/protocol/messages.dart';
import 'package:spike_app/state/away.dart';
import 'package:spike_app/state/brain_ready.dart';
import 'package:spike_app/state/link.dart';
import 'package:spike_app/state/settings.dart';

/// A link whose "connected" flips when the fake phone brain wakes up (the real one starts once a key is saved).
class _FakeLink implements SpikeLink {
  bool connected = false;
  final sent = <SpikeMessage>[];
  @override
  Stream<SpikeMessage> get messages => const Stream.empty();
  @override
  Stream<LinkStatus> get status => const Stream.empty();
  @override
  LinkStatus get current => LinkStatus(phase: connected ? LinkPhase.connected : LinkPhase.idle);
  @override
  bool send(SpikeMessage msg) {
    if (!connected) return false;
    sent.add(msg);
    return true;
  }

  @override
  bool get legacyBrain => false;
}

/// The away controller without radios, keystore plugin or network: saveKey keeps the key in memory only.
class _FakeAway extends AwayController {
  _FakeAway(this.link, this.store, {this.hasKey = false});
  final _FakeLink link;
  final MemorySecretStore store;
  final bool hasKey;
  int saveCalls = 0;
  @override
  AwayState build() => AwayState(hasKey: hasKey);
  @override
  Future<String?> saveKey(String raw) async {
    saveCalls++;
    await store.write(aiKeyName('gemini'), tidyKey(raw));
    link.connected = true; // the phone brain is up once there is a key
    state = state.copyWith(hasKey: true);
    return null;
  }

  @override
  Future<String?> testKey([String? raw]) => throw StateError('onboarding must never call Gemini');
}

const _validKey = 'AIzaSyA1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q';

late _FakeLink _link;
late MemorySecretStore _store;
late _FakeAway _away;

Future<void> _pump(WidgetTester t, Widget screen, {Map<String, Object> prefs = const {}, bool hasKey = false, Size size = const Size(1080, 2340), double dpr = 3}) async {
  SharedPreferences.setMockInitialValues(prefs);
  final p = await SharedPreferences.getInstance();
  _link = _FakeLink();
  _store = MemorySecretStore();
  _away = _FakeAway(_link, _store, hasKey: hasKey);
  if (hasKey) _link.connected = true;
  t.view.physicalSize = size;
  t.view.devicePixelRatio = dpr;
  addTearDown(t.view.reset);
  await t.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(p),
      secretStoreProvider.overrideWithValue(_store),
      awayProvider.overrideWith(() => _away),
      commandsProvider.overrideWith((ref) => SpikeCommands(_link)),
    ],
    child: MaterialApp(theme: buildTheme(Brightness.light), home: screen),
  ));
  await _settle(t);
}

Future<void> _settle(WidgetTester t, [int n = 30]) async {
  for (var i = 0; i < n; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

/// Type a message in Talk and press the keyboard's send.
Future<void> _sendHello(WidgetTester t) async {
  await t.enterText(find.byType(TextField).first, 'hello Spike');
  await t.testTextInput.receiveAction(TextInputAction.done);
  await _settle(t, 12);
}

void main() {
  tearDown(() => AppPlatform.debugDesktop = null);

  test('fresh launch: the router opens /home (explore), never the connect screen', () {
    SharedPreferences.setMockInitialValues({});
    return SharedPreferences.getInstance().then((p) {
      final c = ProviderContainer(overrides: [prefsProvider.overrideWithValue(p)]);
      addTearDown(c.dispose);
      expect(p.getKeys(), isEmpty, reason: 'a fresh install: nothing saved, not onboarded');
      expect(c.read(settingsProvider).onboarded, isFalse);
      final router = c.read(routerProvider);
      expect(router.routeInformationProvider.value.uri.path, '/home');
      // the old connect screen is still a route (Settings > Connect to Spike pushes it)
      expect(router.configuration.routes.whereType<GoRoute>().any((r) => r.path == '/connect'), isTrue);
    });
  });

  testWidgets('exploring: Settings still reaches the old connect screen as "Connect to Spike"', (t) async {
    await _pump(t, const SettingsScreen());
    expect(find.text('Connect to Spike'), findsOneWidget);
  });

  testWidgets('Talk: sending with no brain shows ONE friendly sheet, in plain English', (t) async {
    await _pump(t, const TalkScreen());
    expect(brainReadyFor(t), isFalse);
    await _sendHello(t);
    expect(find.text('Spike needs his brain'), findsOneWidget);
    expect(find.text('Use a free Gemini key'), findsOneWidget);
    expect(find.text('Scan the code on your computer'), findsOneWidget);
    expect(find.text('Get a free key'), findsOneWidget);
    expect(find.text('More ways'), findsOneWidget);
    // no developer words
    for (final w in ['pair_phone', '127.0.0.1', 'mDNS', 'WebSocket', 'endpoint', 'token']) {
      expect(find.textContaining(w, findRichText: true), findsNothing, reason: w);
    }
    expect(_link.sent, isEmpty, reason: 'nothing is sent while there is no brain');
    // on a 360 x 780 phone both choices and the way out are on screen without scrolling
    for (final f in [find.text('Use this key'), find.text('Scan the code'), find.byTooltip('Keep exploring')]) {
      expect(t.getBottomLeft(f).dy, lessThan(780), reason: 'visible without scrolling');
    }
  });

  testWidgets('pasting a key of the right shape saves it (no Gemini call), closes the sheet and sends the message', (t) async {
    await _pump(t, const TalkScreen());
    await _sendHello(t);
    await t.enterText(find.byKey(const Key('brain_key_field')), '  "$_validKey"\n');
    await t.tap(find.text('Use this key'));
    await _settle(t, 4);
    expect(find.text('Spike has his brain'), findsOneWidget);
    await _settle(t, 30);
    expect(find.text('Spike needs his brain'), findsNothing, reason: 'the sheet closed');
    expect(_away.saveCalls, 1);
    expect(_store.values[aiKeyName('gemini')], _validKey, reason: 'tidied, kept in the secret store');
    // the action resumed: his message went on its way and shows in the chat
    expect(_link.sent.whereType<TextMsg>().map((m) => m.text), ['hello Spike']);
    expect(find.text('hello Spike'), findsOneWidget);
  });

  testWidgets('a key of the wrong shape is refused on the spot and nothing is saved', (t) async {
    await _pump(t, const TalkScreen());
    await _sendHello(t);
    await t.enterText(find.byKey(const Key('brain_key_field')), 'not-a-key');
    await t.tap(find.text('Use this key'));
    await _settle(t, 6);
    expect(find.textContaining('start with AIza'), findsOneWidget);
    expect(find.text('Spike needs his brain'), findsOneWidget, reason: 'still asking');
    expect(_away.saveCalls, 0);
    expect(_store.values, isEmpty);
  });

  testWidgets('dismissing the sheet returns to exploring: nothing sent, nothing saved', (t) async {
    await _pump(t, const TalkScreen());
    await _sendHello(t);
    await t.tap(find.byTooltip('Keep exploring'));
    await _settle(t, 20);
    expect(find.text('Spike needs his brain'), findsNothing);
    expect(_link.sent, isEmpty);
    expect(_store.values, isEmpty);
    expect(find.text('Say hi to Spike'), findsOneWidget, reason: 'the chat is untouched');
    // and asking again works: the sheet comes back for the next brain-needing action
    await t.enterText(find.byType(TextField).first, 'hello again');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await _settle(t, 12);
    expect(find.text('Spike needs his brain'), findsOneWidget);
  });

  testWidgets('with a key already saved there is no sheet: the message just goes', (t) async {
    await _pump(t, const TalkScreen(), hasKey: true);
    await _sendHello(t);
    expect(find.text('Spike needs his brain'), findsNothing);
    expect(_link.sent.whereType<TextMsg>().map((m) => m.text), ['hello Spike']);
  });

  testWidgets('alarms need the computer: the sheet does not offer a Gemini key for them', (t) async {
    await _pump(t, _Harness(BrainReason.alarms));
    await t.tap(find.text('ask'));
    await _settle(t, 15);
    expect(find.text('Spike needs his brain'), findsOneWidget);
    expect(find.text('Use a free Gemini key'), findsNothing);
    expect(find.text('Scan the code on your computer'), findsOneWidget);
  });

  testWidgets('a wide window gets a dialog, not a stretched bottom sheet', (t) async {
    await _pump(t, _Harness(BrainReason.talk), size: const Size(1600, 1000), dpr: 1);
    await t.tap(find.text('ask'));
    await _settle(t, 15);
    expect(find.byType(Dialog), findsOneWidget);
    expect(find.text('Spike needs his brain'), findsOneWidget);
    final w = t.getSize(find.byType(BrainNeededPanel)).width;
    expect(w, lessThanOrEqualTo(480), reason: 'designed width, not stretched');
  });

  testWidgets('the Windows app has its built-in brain: it never asks', (t) async {
    AppPlatform.debugDesktop = true;
    await _pump(t, _Harness(BrainReason.talk), size: const Size(1600, 1000), dpr: 1);
    await t.tap(find.text('ask'));
    await _settle(t, 10);
    expect(find.text('Spike needs his brain'), findsNothing);
    expect(find.text('result: true'), findsOneWidget);
  });
}

bool brainReadyFor(WidgetTester t) {
  final c = ProviderScope.containerOf(t.element(find.byType(TalkScreen)));
  return c.read(brainReadyProvider);
}

class _Harness extends ConsumerStatefulWidget {
  const _Harness(this.reason);
  final BrainReason reason;
  @override
  ConsumerState<_Harness> createState() => _HarnessState();
}

class _HarnessState extends ConsumerState<_Harness> {
  String _r = '';
  @override
  Widget build(BuildContext context) => Scaffold(
        body: Column(children: [
          TextButton(
            onPressed: () async {
              final ok = await ensureBrain(context, ref, reason: widget.reason);
              if (mounted) setState(() => _r = 'result: $ok');
            },
            child: const Text('ask'),
          ),
          Text(_r),
        ]),
      );
}
