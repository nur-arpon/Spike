// The robot push (features/story/): the story page, the waitlist button, the once-only peeks, the
// 3-day reminder, the robot cards on the tabs, and a scan that the copy never promises more than the
// body does. Mocks only: no network, no browser, no Gemini.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/away/ai/key_store.dart';
import 'package:spike_app/core/brand.dart';
import 'package:spike_app/core/capabilities.dart';
import 'package:spike_app/core/platform.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/features/life/life_screen.dart';
import 'package:spike_app/features/remote/remote_screen.dart';
import 'package:spike_app/features/story/push_copy.dart';
import 'package:spike_app/features/story/push_sheets.dart';
import 'package:spike_app/features/story/push_state.dart';
import 'package:spike_app/features/story/push_widgets.dart';
import 'package:spike_app/features/story/story_screen.dart';
import 'package:spike_app/features/talk/talk_screen.dart';
import 'package:spike_app/state/away.dart';
import 'package:spike_app/state/settings.dart';

const _form = 'https://docs.google.com/forms/d/e/TEST/viewform';

Future<SharedPreferences> _prefs([Map<String, Object> init = const {}]) async {
  SharedPreferences.setMockInitialValues(init);
  return SharedPreferences.getInstance();
}

class _Rig {
  final opened = <Uri>[];
  DateTime now = DateTime(2026, 10, 5, 9);
}

Future<void> _pump(WidgetTester t, Widget screen, SharedPreferences prefs,
    {_Rig? rig, String url = _form, Size size = const Size(412, 915), Brightness b = Brightness.light}) async {
  rig ??= _Rig();
  for (final k in ['assets/story/robot_build.json', 'assets/story/founder_note.txt']) {
    rootBundle.evict(k); // the cache would hand back a load started in an earlier test's fake clock
  }
  t.view.physicalSize = size * 2;
  t.view.devicePixelRatio = 2;
  addTearDown(t.view.reset);
  await t.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(prefs),
      secretStoreProvider.overrideWithValue(MemorySecretStore()),
      waitlistUrlProvider.overrideWithValue(url),
      urlOpenerProvider.overrideWithValue((u) async {
        rig!.opened.add(u);
        return true;
      }),
      pushClockProvider.overrideWithValue(() => rig!.now),
    ],
    child: MaterialApp(theme: buildTheme(b), home: screen),
  ));
  await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 150))); // let the bundled files load
  for (var i = 0; i < 30; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

Future<void> _settle(WidgetTester t, [int ms = 1500]) async {
  for (var i = 0; i < ms ~/ 50; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  setUp(resetPushSheets);
  group('story page', () {
    testWidgets('renders every section on a phone, with the founder note from its text file', (t) async {
      await _pump(t, const StoryScreen(), await _prefs());
      expect(find.text(storyHeadline), findsOneWidget);
      final list = find.byType(Scrollable).first;
      for (final f in [find.text(storyBeginTitle), find.text(storyThingsTitle), find.text(storyBuildTitle), find.byKey(const ValueKey('founderNote'))]) {
        await t.scrollUntilVisible(f, 300, scrollable: list);
        expect(f, findsOneWidget);
        if (f == find.text(storyBeginTitle)) {
          expect(find.textContaining(startupLine(AppBrand.publisherDisplayName, AppBrand.developerName)), findsOneWidget);
        }
      }
      final note = File('assets/story/founder_note.txt').readAsStringSync().trim();
      expect(note, startsWith("Hi, I'm ${AppBrand.developerName}."));
      expect(find.text(note), findsOneWidget);
      // the five build steps from the bundled copy
      for (final s in ['Designed', 'Firmware', 'Parts and printing', 'First assembly', 'First steps']) {
        await t.scrollUntilVisible(find.text(s), 200, scrollable: list);
        expect(find.text(s), findsOneWidget, reason: s);
      }
    });

    testWidgets('lists exactly the body abilities, walk and give paw only as in development', (t) async {
      await _pump(t, const StoryScreen(), await _prefs());
      final list = find.byType(Scrollable).first;
      await t.scrollUntilVisible(find.byKey(const ValueKey('ability.drive')), 300, scrollable: list);
      for (final a in bodyAbilities) {
        final chip = find.byKey(ValueKey('ability.${a.action}'));
        expect(chip, findsOneWidget, reason: a.label);
        expect(find.descendant(of: chip, matching: find.text(storyInDevelopment)), a.inDevelopment ? findsOneWidget : findsNothing, reason: a.label);
      }
      expect(bodyAbilities.where((a) => a.inDevelopment).map((a) => a.action).toSet(), {'walk', 'paw'});
    });

    for (final size in const [Size(412, 915), Size(1366, 768), Size(1920, 1080)]) {
      testWidgets('has no overflow or stretching at ${size.width.toInt()} x ${size.height.toInt()}', (t) async {
        await _pump(t, const StoryScreen(), await _prefs(), size: size);
        expect(t.takeException(), isNull);
        expect(find.text(storyHeadline), findsOneWidget);
        if (size.width >= 900) {
          // two panes: the picture and the button beside the reading column, which stays readable
          expect(t.getSize(find.text(storyHeadline)).width, lessThanOrEqualTo(800));
          expect(find.text(ctaWaitlist), findsOneWidget);
        }
      });
    }
  });

  group('the main button', () {
    testWidgets('opens the waitlist form when the link is set', (t) async {
      final rig = _Rig();
      await _pump(t, const StoryScreen(), await _prefs(), rig: rig);
      expect(find.text(ctaWaitlist), findsWidgets);
      expect(find.text(ctaFollow), findsNothing);
      await t.tap(find.text(ctaWaitlist).first);
      await t.pump();
      expect(rig.opened, [Uri.parse(_form)]);
    });

    testWidgets('falls back to "Follow the build" and the website while the link is empty (or not https)', (t) async {
      for (final empty in ['', '  ', 'http://insecure.example/form', 'not a link']) {
        final rig = _Rig();
        await _pump(t, const StoryScreen(), await _prefs(), rig: rig, url: empty);
        expect(find.text(ctaFollow), findsWidgets, reason: '"$empty"');
        expect(find.text(ctaWaitlist), findsNothing);
        await t.tap(find.text(ctaFollow).first);
        await t.pump();
        expect(rig.opened, [Uri.parse(robotPageUrl)], reason: '"$empty"');
      }
    });

    test('the shipped brand.json link is the real https form (or empty)', () {
      expect(AppBrand.robotWaitlistUrl.isEmpty || waitlistUri(AppBrand.robotWaitlistUrl) != null, isTrue);
      expect(ctaFor(AppBrand.robotWaitlistUrl).label, AppBrand.robotWaitlistUrl.isEmpty ? ctaFollow : ctaWaitlist);
    });
  });

  group('imagine this on your desk (peek)', () {
    Widget host() => Consumer(
          builder: (context, ref, _) => Scaffold(
            body: Column(children: [
              for (final f in PeekFeature.values)
                TextButton(key: ValueKey('use.${f.name}'), onPressed: () => maybePeek(context, ref, f), child: Text('use ${f.name}')),
            ]),
          ),
        );

    testWidgets('shows once per feature, ever, and is dismissible', (t) async {
      final prefs = await _prefs();
      await _pump(t, host(), prefs);
      for (final f in PeekFeature.values) {
        await t.tap(find.byKey(ValueKey('use.${f.name}')));
        await _settle(t, 1800);
        expect(find.text(peekHeadline), findsOneWidget, reason: '${f.name} first time');
        expect(find.text(peekLines[f]!), findsOneWidget);
        expect(find.text(ctaWaitlist), findsOneWidget);
        await t.tap(find.text(laterLabel));
        await _settle(t, 800);
        expect(find.text(peekHeadline), findsNothing);
        // second time: nothing
        await t.tap(find.byKey(ValueKey('use.${f.name}')));
        await _settle(t, 1800);
        expect(find.text(peekHeadline), findsNothing, reason: '${f.name} second time');
      }
      // and not after a restart either: it is saved
      await _pump(t, host(), prefs);
      await t.tap(find.byKey(const ValueKey('use.trick')));
      await _settle(t, 1800);
      expect(find.text(peekHeadline), findsNothing);
    });

    testWidgets('a swipe-away counts as seen (the flag is saved before the sheet opens)', (t) async {
      final prefs = await _prefs();
      await _pump(t, host(), prefs);
      await t.tap(find.byKey(const ValueKey('use.drive')));
      await t.pump();
      expect(prefs.getStringList('spike.push.peeked'), ['drive']);
      await _settle(t, 1500);
    });
  });

  group('the 3-day reminder', () {
    test('is due after exactly three days', () {
      final a = DateTime(2026, 10, 1, 8);
      expect(reminderDue(null, a), isFalse);
      expect(reminderDue(a, a.add(const Duration(days: 2, hours: 23))), isFalse);
      expect(reminderDue(a, a.add(const Duration(days: 3))), isTrue);
      expect(reminderDue(a, a.add(const Duration(days: 9))), isTrue);
    });

    test('the first open only starts the clock; then every three days', () async {
      final prefs = await _prefs();
      var now = DateTime(2026, 10, 1, 8);
      final c = ProviderContainer(overrides: [prefsProvider.overrideWithValue(prefs), pushClockProvider.overrideWithValue(() => now)]);
      addTearDown(c.dispose);
      final n = c.read(pushProvider.notifier);
      expect(n.takeReminder(), isFalse, reason: 'day one: the banner is enough');
      now = now.add(const Duration(days: 2));
      expect(n.takeReminder(), isFalse);
      now = now.add(const Duration(days: 1));
      expect(n.takeReminder(), isTrue);
      expect(n.takeReminder(), isFalse, reason: 'not twice in a row');
      now = now.add(const Duration(days: 2, hours: 23));
      expect(n.takeReminder(), isFalse);
      now = now.add(const Duration(hours: 1));
      expect(n.takeReminder(), isTrue);
      // remembered across a restart
      final c2 = ProviderContainer(overrides: [prefsProvider.overrideWithValue(prefs), pushClockProvider.overrideWithValue(() => now)]);
      addTearDown(c2.dispose);
      expect(c2.read(pushProvider.notifier).takeReminder(), isFalse);
    });

    testWidgets('on app open it shows the progress and the button, and swipes away', (t) async {
      final rig = _Rig();
      final prefs = await _prefs({
        'spike.push.firstSeen': rig.now.subtract(const Duration(days: 4)).millisecondsSinceEpoch,
      });
      await _pump(t, const ReminderHost(delay: Duration(milliseconds: 100), child: Scaffold(body: Text('the app'))), prefs, rig: rig);
      for (var i = 0; i < 4; i++) {
        await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100))); // the bundled file loads in real time
        await _settle(t, 400);
      }
      expect(find.text(reminderTitle), findsOneWidget);
      expect(find.textContaining('Step 3 of 5: Parts and printing'), findsOneWidget);
      expect(find.text(ctaWaitlist), findsOneWidget);
      await t.tap(find.text(laterLabel));
      await _settle(t, 800);
      expect(find.text(reminderTitle), findsNothing);
      expect(prefs.getInt('spike.push.reminderAt'), rig.now.millisecondsSinceEpoch);
    });

    testWidgets('a new user is not shown it on the first open', (t) async {
      final prefs = await _prefs();
      await _pump(t, const ReminderHost(delay: Duration(milliseconds: 100), child: Scaffold(body: Text('the app'))), prefs);
      await _settle(t, 1500);
      expect(find.text(reminderTitle), findsNothing);
      expect(prefs.getInt('spike.push.firstSeen'), isNotNull);
    });
  });

  group('robot cards', () {
    for (final e in {PushTab.play: const RemoteScreen(), PushTab.talk: const TalkScreen(), PushTab.life: const LifeScreen()}.entries) {
      testWidgets('${e.key.name}: its own card, with its own words, at the end of the page', (t) async {
        await _pump(t, e.value, await _prefs());
        final card = find.byKey(ValueKey('robotCard.${e.key.name}'));
        await t.scrollUntilVisible(card, 300, scrollable: find.byType(Scrollable).first);
        expect(card, findsOneWidget);
        expect(find.text(tabCards[e.key]!.$1), findsOneWidget);
      });
    }

    testWidgets('the card and the banner are one tap from the story, and each card is a different message', (t) async {
      await _pump(t, const Column(children: [PreviewBanner(), RobotCard(tab: PushTab.home)]), await _prefs());
      expect(find.text(bannerTitle), findsOneWidget);
      expect(find.byKey(const ValueKey('robotCard.home')), findsOneWidget);
      expect(tabCards.values.map((v) => v.$1).toSet().length, PushTab.values.length);
    });

    test('Home and Studio place theirs (those two screens hold a live face and cannot be built in a test)', () {
      expect(File('lib/features/home/home_screen.dart').readAsStringSync(), allOf(contains('PreviewBanner()'), contains('RobotCard(tab: PushTab.home)')));
      expect(File('lib/features/studio/studio_screen.dart').readAsStringSync(), contains('RobotCard(tab: PushTab.studio)'));
    });

    testWidgets('the Windows layout shows none of the unsolicited pieces yet', (t) async {
      AppPlatform.debugDesktop = true;
      addTearDown(() => AppPlatform.debugDesktop = null);
      await _pump(t, const Column(children: [PreviewBanner(), RobotCard(tab: PushTab.play)]), await _prefs());
      expect(find.text(bannerTitle), findsNothing);
      expect(find.byKey(const ValueKey('robotCard.play')), findsNothing);
    });
  });

  group('claims stay inside what the body can do', () {
    // things the body cannot do (core/capabilities.dart "Cannot"), and a few words that would over-promise
    const banned = [
      'roll over', 'rolls over', 'roll ', 'beg', 'high five', 'high-five', 'jump', 'fetch', 'fly', 'climb', 'stairs', 'carry',
      'cook', 'clean', 'camera', 'security', 'guard', 'available now', 'order', 'buy now', 'price', r'$', 'ship', 'delivery', 'preorder',
    ];

    test('no word in any push copy or the founder note promises an impossible thing', () {
      final all = [...allPushCopy(), File('assets/story/founder_note.txt').readAsStringSync()].join('\n').toLowerCase();
      for (final w in banned) {
        expect(all.contains(w), isFalse, reason: 'copy contains "$w"');
      }
    });

    test('every ability named in the sales list is a real one, never a hidden action', () {
      for (final a in bodyAbilities) {
        expect(hiddenActions.contains(a.action), isFalse, reason: a.label);
        expect(hiddenActions.contains(a.label), isFalse);
      }
      expect(bodyAbilities.map((a) => a.label.toLowerCase()).join(' '), isNot(anyOf(contains('roll'), contains('beg'), contains('jump'))));
      // only walk and give paw are "in development"
      expect(bodyAbilities.where((a) => a.inDevelopment).length, 2);
    });

    test('the peeks speak only of tricks, the wag, driving with desk-edge stops, and lying down', () {
      expect(peekLines.keys.toSet(), PeekFeature.values.toSet());
      expect(peekLines[PeekFeature.drive], contains('Desk-edge stops'));
    });
  });
}
