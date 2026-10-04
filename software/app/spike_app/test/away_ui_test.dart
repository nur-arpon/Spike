// Away-from-home screens: the Settings sections (phone brain, AI key, offline
// brain, voice, hotspot) and the Bluetooth card on the Connect screen, with a
// fake away controller (no radio, no keystore).
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/away/ai/key_store.dart';
import 'package:spike_app/away/voice/speaker.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/features/connect/nearby_robot.dart';
import 'package:spike_app/features/settings/away_settings.dart';
import 'package:spike_app/features/settings/voice_preview_screen.dart';
import 'package:spike_app/protocol/client.dart';
import 'package:spike_app/state/away.dart';
import 'package:spike_app/state/settings.dart';

class FakeAway extends AwayController {
  FakeAway(this.initial);
  final AwayState initial;
  @override
  AwayState build() => initial;
  @override
  Future<String?> testKey([String? raw]) async => 'Google did not accept this key';
}

Future<void> pump(WidgetTester t, Widget w, AwayState s, {Map<String, Object> prefs = const {}}) async {
  SharedPreferences.setMockInitialValues(prefs);
  final p = await SharedPreferences.getInstance();
  t.view.physicalSize = const Size(1080, 2340);
  t.view.devicePixelRatio = 3;
  addTearDown(t.view.reset);
  await t.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(p),
      awayProvider.overrideWith(() => FakeAway(s)),
      secretStoreProvider.overrideWithValue(MemorySecretStore()),
    ],
    child: MaterialApp(theme: buildTheme(Brightness.light), home: Scaffold(body: ListView(children: [w]))),
  ));
  for (var i = 0; i < 10; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  testWidgets('Settings away: every section is there and says what it does', (t) async {
    await pump(t, const AwaySettings(), const AwayState(active: BrainHost.phone));
    expect(find.text('Phone brain when away'), findsOneWidget);
    expect(find.text('On now: the phone is his brain'), findsOneWidget);
    expect(find.text('Spike talks on this phone'), findsOneWidget);
    expect(find.textContaining('aistudio.google.com/apikey'), findsOneWidget);
    expect(find.textContaining('Download offline brain (345 MB)'), findsOneWidget);
    // the Kokoro add-on is Android-only (the owner fetches the engine himself): not on this test host
    expect(kokoroAddonSupported, isFalse);
    expect(kokoroVoiceAvailable, isFalse);
    expect(find.text('Offline backup voice (Kokoro)'), findsNothing);
    expect(find.text('Phone hotspot'), findsOneWidget);
  });

  testWidgets('Settings away: on Android the Kokoro add-on card is in the voice section (no engine = hidden)', (t) async {
    debugKokoroAddonSupported = true;
    addTearDown(() => debugKokoroAddonSupported = null);
    await pump(t, const AwaySettings(), const AwayState(active: BrainHost.phone));
    expect(find.text('Offline backup voice (Kokoro)'), findsOneWidget);
    final engine = kokoroEngine;
    kokoroEngine = null;
    addTearDown(() => kokoroEngine = engine);
    expect(kokoroVoiceAvailable, isFalse);
  });

  testWidgets('Hear the voices: a Spike | Spicy switch; each has its styles; a tap picks and saves', (t) async {
    SharedPreferences.setMockInitialValues({});
    final p = await SharedPreferences.getInstance();
    t.view.physicalSize = const Size(1080, 2340);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    await t.pumpWidget(ProviderScope(
      overrides: [
        prefsProvider.overrideWithValue(p),
        awayProvider.overrideWith(() => FakeAway(const AwayState(hasKey: true))),
        secretStoreProvider.overrideWithValue(MemorySecretStore()),
      ],
      child: MaterialApp(theme: buildTheme(Brightness.light), home: const VoicePreviewScreen()),
    ));
    await t.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('Energetic  ·  Fenrir'), findsOneWidget);
    expect(find.textContaining('Now: Energetic · Fenrir'), findsOneWidget);
    await t.scrollUntilVisible(find.textContaining('Street dog'), 300);
    expect(find.textContaining('Street dog  ·  Algenib'), findsOneWidget);
    await t.scrollUntilVisible(find.byType(SegmentedButton<String>), -300);
    await t.tap(find.text('Spicy'));
    await t.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('Sassy  ·  Kore'), findsOneWidget);
    await t.scrollUntilVisible(find.textContaining('Caring girlfriend'), 300);
    await t.tap(find.textContaining('Caring girlfriend'));
    await t.pump(const Duration(milliseconds: 100));
    expect(p.getString('spike.gemini.style.cat'), 'caring');
    expect(find.text('Gemini TTS'), findsWidgets);
    expect(find.text('Gemini Live'), findsWidgets);
  });

  testWidgets('Settings away: saving with no key explains; a wrong key is refused, not saved', (t) async {
    await pump(t, const AwaySettings(), const AwayState());
    await t.tap(find.text('Save'));
    await t.pump(const Duration(milliseconds: 100));
    expect(find.text('Paste a key first'), findsOneWidget);
    await t.enterText(find.byType(TextField).first, 'AIza-not-a-real-key-0000000000000000');
    await t.testTextInput.receiveAction(TextInputAction.done); // the keyboard's Done saves too
    for (var i = 0; i < 5; i++) {
      await t.pump(const Duration(milliseconds: 50));
    }
    expect(find.text('Google did not accept this key'), findsOneWidget);
  });

  testWidgets('Settings away: a failed hotspot says why in plain words, with Retry', (t) async {
    await pump(t, const AwaySettings(), const AwayState(active: BrainHost.phone, hotspot: HotspotConn.failed, hotspotReason: 'not_found'));
    expect(find.textContaining("couldn't see the hotspot"), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('Connect: the Bluetooth card; nothing is scanned until the owner taps Find', (t) async {
    await pump(t, const NearbyRobotCard(), const AwayState());
    expect(find.text('Spike nearby (Bluetooth)'), findsOneWidget);
    expect(find.text('Find Spike nearby'), findsOneWidget);
  });

  testWidgets('Connect: a paired robot shows its state and can be forgotten', (t) async {
    await pump(t, const NearbyRobotCard(), const AwayState(active: BrainHost.phone, robot: RobotConn.needsPermission),
        prefs: {'spike.settings.v1': '{"deviceId":"app-1","robotId":"AA","robotName":"Spike-7c9e2a"}'});
    expect(find.text('Spike-7c9e2a · Needs the Bluetooth permission'), findsOneWidget);
    expect(find.text('Forget'), findsOneWidget);
  });

  test('hotspot problems are plain words for every reason', () {
    for (final r in ['permission', 'band', 'not_found', 'incompatible_mode', 'manual_missing', 'auth', 'no_robot', 'timeout', 'disallowed', null]) {
      expect(hotspotProblem(r), isNot(contains('_')));
    }
  });
}
