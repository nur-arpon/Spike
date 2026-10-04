// Renders the robot story page, a robot card and the "imagine this" sheet to PNG files at the S23's
// 412 x 915 (so they can be reviewed without touching the phone). Off by default; run with:
//   $env:SPIKE_SHOTS = '1'; flutter test test/story_shots_test.dart
// Real Roboto and Material icon fonts are loaded from the Flutter SDK (the test font is blocks).
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/features/story/push_copy.dart';
import 'package:spike_app/features/story/push_sheets.dart';
import 'package:spike_app/features/story/push_widgets.dart';
import 'package:spike_app/features/story/story_screen.dart';
import 'package:spike_app/state/settings.dart';

final _on = Platform.environment['SPIKE_SHOTS'] == '1';
const _fonts = 'D:/flutter/bin/cache/artifacts/material_fonts';
const _out = '../screens';

Future<void> _loadFonts() async {
  Future<ByteData> bytes(String f) async => ByteData.sublistView(await File('$_fonts/$f').readAsBytes());
  final roboto = FontLoader('Roboto');
  for (final f in ['regular', 'medium', 'bold', 'black', 'italic', 'light']) {
    roboto.addFont(bytes('roboto-$f.ttf'));
  }
  await roboto.load();
  final icons = FontLoader('MaterialIcons')..addFont(bytes('materialicons-regular.otf'));
  await icons.load();
}

final _key = GlobalKey();

Future<void> _shot(WidgetTester t, String name) async {
  await t.runAsync(() async {
    final b = _key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final img = await b.toImage(pixelRatio: 2);
    final data = await img.toByteData(format: ui.ImageByteFormat.png);
    await File('$_out/$name.png').writeAsBytes(data!.buffer.asUint8List());
  });
}

Future<void> _pump(WidgetTester t, Widget home, {Brightness b = Brightness.light}) async {
  SharedPreferences.setMockInitialValues({});
  final prefs = await SharedPreferences.getInstance();
  t.view.physicalSize = const Size(824, 1830);
  t.view.devicePixelRatio = 2;
  addTearDown(t.view.reset);
  for (final k in ['assets/story/robot_build.json', 'assets/story/founder_note.txt']) {
    rootBundle.evict(k);
  }
  await t.pumpWidget(ProviderScope(
    overrides: [prefsProvider.overrideWithValue(prefs)],
    child: RepaintBoundary(key: _key, child: MaterialApp(debugShowCheckedModeBanner: false, theme: buildTheme(b), home: home)),
  ));
  for (var i = 0; i < 4; i++) {
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 200)));
    for (var j = 0; j < 10; j++) {
      await t.pump(const Duration(milliseconds: 50));
    }
  }
}

void main() {
  testWidgets('screenshots', (t) async {
    await t.runAsync(_loadFonts);
    // 1. the story page (top, and scrolled to the abilities and build progress)
    await _pump(t, const StoryScreen());
    await _shot(t, 'v1_0_4_story');
    await t.scrollUntilVisible(find.byKey(const ValueKey('ability.drive')), 200, scrollable: find.byType(Scrollable).first);
    await t.drag(find.byType(Scrollable).first, const Offset(0, -120));
    for (var j = 0; j < 10; j++) {
      await t.pump(const Duration(milliseconds: 50));
    }
    await _shot(t, 'v1_0_4_story_abilities');
    await t.scrollUntilVisible(find.byKey(const ValueKey('founderNote')), 300, scrollable: find.byType(Scrollable).first);
    await _shot(t, 'v1_0_4_story_founder');

    // 2. a robot card (the Play tab's) under a little page, light and dark
    for (final (dark, name) in [(false, 'v1_0_4_robot_card'), (true, 'v1_0_4_robot_card_dark')]) {
      await _pump(
          t,
          Builder(
              builder: (c) => Scaffold(
                  body: Padding(
                      padding: const EdgeInsets.fromLTRB(20, 80, 20, 0),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: const [
                        PreviewBanner(),
                        SizedBox(height: 24),
                        RobotCard(tab: PushTab.play),
                        SizedBox(height: 16),
                        RobotCard(tab: PushTab.life),
                      ])))),
          b: dark ? Brightness.dark : Brightness.light);
      await _shot(t, name);
    }

    // 3. the "imagine this on your desk" sheet
    await _pump(
        t,
        Consumer(
            builder: (c, ref, _) => Scaffold(
                body: Center(child: TextButton(key: const ValueKey('go'), onPressed: () => maybePeek(c, ref, PeekFeature.drive), child: const Text('go'))))));
    await t.tap(find.byKey(const ValueKey('go')));
    for (var j = 0; j < 40; j++) {
      await t.pump(const Duration(milliseconds: 50));
    }
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 400))); // the picture decodes in real time
    for (var j = 0; j < 10; j++) {
      await t.pump(const Duration(milliseconds: 50));
    }
    await _shot(t, 'v1_0_4_peek');
  }, skip: !_on);
}
