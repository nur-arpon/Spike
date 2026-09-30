import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/features/life/life_screen.dart';
import 'package:spike_app/features/life/memories_screen.dart';
import 'package:spike_app/features/remote/remote_screen.dart';
import 'package:spike_app/features/settings/settings_screen.dart';
import 'package:spike_app/features/talk/talk_screen.dart';
import 'package:spike_app/state/settings.dart';

Future<SharedPreferences> _prefs([Map<String, Object> init = const {}]) async {
  SharedPreferences.setMockInitialValues(init);
  return SharedPreferences.getInstance();
}

Future<void> _pump(WidgetTester t, Widget screen, SharedPreferences prefs, {Brightness b = Brightness.light}) async {
  t.view.physicalSize = const Size(1080, 2340);
  t.view.devicePixelRatio = 3;
  addTearDown(t.view.reset);
  await t.pumpWidget(ProviderScope(
    overrides: [prefsProvider.overrideWithValue(prefs)],
    child: MaterialApp(theme: buildTheme(b), home: screen),
  ));
  // let the spring entrances settle (they never loop, but pumpAndSettle would
  // wait on the pulsing status dots)
  for (var i = 0; i < 30; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  testWidgets('Talk: empty state offers ideas; sending while offline explains why', (t) async {
    await _pump(t, const TalkScreen(), await _prefs());
    expect(find.text('Talk to Spike'), findsOneWidget);
    expect(find.text("What's the time?"), findsOneWidget);
    await t.tap(find.text("What's the time?"));
    for (var i = 0; i < 10; i++) {
      await t.pump(const Duration(milliseconds: 60));
    }
    expect(find.textContaining("isn't connected"), findsOneWidget);
    // nothing was added to the chat, because nothing was sent
    expect(find.text('Say hi to Spike'), findsOneWidget);
  });

  testWidgets('Play: ten distinct actions (no Beg / Roll over: the body cannot), the safety copy and an honest drive state', (t) async {
    await _pump(t, const RemoteScreen(), await _prefs());
    for (final label in ['Bow', 'Zoomies', 'Head tilt', 'Wag dance', 'Sniff', 'Sneeze', 'Walk', 'Give paw', 'Snuggle', 'Slow wag']) {
      expect(find.text(label), findsOneWidget, reason: label);
    }
    for (final label in ['Beg', 'Roll over']) {
      expect(find.text(label), findsNothing, reason: '$label is hidden');
    }
    expect(tricks.map((x) => x.id).toSet().length, tricks.length, reason: 'no two buttons play the same action');
    await t.scrollUntilVisible(find.textContaining('Desk-edge stops are always on'), 300, scrollable: find.byType(Scrollable).first);
    expect(find.textContaining('can never turn them off'), findsOneWidget);
    expect(find.text('Connect Spike first.'), findsOneWidget);
  });

  testWidgets('Play: tapping Walk while offline asks to connect first, like any other trick', (t) async {
    await _pump(t, const RemoteScreen(), await _prefs());
    await t.tap(find.text('Walk'));
    await t.pump();
    expect(find.textContaining('Connect Spike first'), findsOneWidget);
  });

  testWidgets('Memories: offline, the list says to connect (nothing is kept on the phone)', (t) async {
    await _pump(t, const MemoriesScreen(), await _prefs());
    expect(find.text('Connect Spike to see what he remembers.'), findsOneWidget);
  });

  testWidgets('Life: the last alarm list from the brain is shown greyed while offline', (t) async {
    final due = DateTime.now().add(const Duration(hours: 2)).millisecondsSinceEpoch ~/ 1000;
    final prefs = await _prefs({
      'spike.timers.v2': jsonEncode([
        {'id': 5, 'kind': 'alarm', 'due': due, 'label': 'Gym', 'repeat': null, 'state': 'active'},
      ]),
    });
    await _pump(t, const LifeScreen(), prefs);
    expect(find.textContaining('Gym'), findsOneWidget);
    expect(find.textContaining('Last list from Spike'), findsOneWidget);
    expect(find.byTooltip('Cancel'), findsNothing, reason: 'no cancel button while the brain cannot hear it');
  });

  testWidgets('Settings: face sounds are on by default (connected or not)', (t) async {
    final prefs = await _prefs();
    await _pump(t, const SettingsScreen(), prefs);
    final tile = find.widgetWithText(SwitchListTile, 'Face sounds on this phone');
    await t.scrollUntilVisible(tile, 300, scrollable: find.byType(Scrollable).first);
    expect(t.widget<SwitchListTile>(tile).value, isTrue);
  });

  testWidgets('Settings: an old "auto" face-sound choice becomes on', (t) async {
    final prefs = await _prefs({'spike.settings.v1': jsonEncode({'deviceId': 'app-1', 'faceSound': 'auto'})});
    await _pump(t, const SettingsScreen(), prefs);
    final tile = find.widgetWithText(SwitchListTile, 'Face sounds on this phone');
    await t.scrollUntilVisible(tile, 300, scrollable: find.byType(Scrollable).first);
    expect(t.widget<SwitchListTile>(tile).value, isTrue);
  });

  testWidgets('Settings: captions toggle defaults ON and is saved', (t) async {
    final prefs = await _prefs();
    await _pump(t, const SettingsScreen(), prefs);
    final tile = find.widgetWithText(SwitchListTile, "Show captions on Spike's screen");
    await t.scrollUntilVisible(tile, 300, scrollable: find.byType(Scrollable).first);
    await t.ensureVisible(tile); // fully on screen, whatever the sections above it
    await t.pump(const Duration(milliseconds: 300));
    expect(t.widget<SwitchListTile>(tile).value, isTrue);
    await t.tap(tile);
    await t.pump(const Duration(milliseconds: 400));
    expect(t.widget<SwitchListTile>(tile).value, isFalse);
    final saved = jsonDecode(prefs.getString('spike.settings.v1')!) as Map<String, dynamic>;
    expect(saved['showCaptions'], isFalse);
  });

  testWidgets('Settings: renaming Spicy is saved', (t) async {
    final prefs = await _prefs();
    await _pump(t, const SettingsScreen(), prefs);
    final field = find.widgetWithText(TextField, 'Cat name');
    await t.scrollUntilVisible(field, 200, scrollable: find.byType(Scrollable).first);
    await t.enterText(field, 'Whiskers');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await t.pump(const Duration(milliseconds: 300));
    final saved = jsonDecode(prefs.getString('spike.settings.v1')!) as Map<String, dynamic>;
    expect(saved['catName'], 'Whiskers');
  });

  testWidgets('Life: mode switch, alarm and reminder buttons, memory entry', (t) async {
    await _pump(t, const LifeScreen(), await _prefs(), b: Brightness.dark);
    expect(find.text('Alarm'), findsOneWidget);
    expect(find.text('Reminder'), findsOneWidget);
    expect(find.text('Spicy'), findsOneWidget);
    expect(find.text('What Spike remembers'), findsOneWidget);
  });

  testWidgets('Memories: forget everything asks first', (t) async {
    await _pump(t, const MemoriesScreen(), await _prefs());
    final btn = find.text('Forget everything');
    await t.scrollUntilVisible(btn, 300, scrollable: find.byType(Scrollable).first);
    await t.tap(btn);
    await t.pump(const Duration(milliseconds: 400));
    expect(find.text('Make Spike forget everything?'), findsOneWidget);
    await t.tap(find.text('Keep them'));
    await t.pump(const Duration(milliseconds: 400));
    expect(find.text('Make Spike forget everything?'), findsNothing);
  });
}
