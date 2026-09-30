// The Windows desktop app (software/app/DESIGN.md "Desktop"): the built-in brain helper, the
// WebView bridge, robot Wi-Fi setup, Start with Windows, the desktop voice session, the v1.8
// voice style, and the desktop screens. No real process, network or Gemini call: fakes only.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/app.dart' show AppShell;
import 'package:spike_app/core/brand.dart';
import 'package:spike_app/core/haptics.dart';
import 'package:spike_app/core/platform.dart';
import 'package:spike_app/core/spike_web_view.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/desktop/brain_sidecar.dart';
import 'package:spike_app/desktop/desktop_channel.dart';
import 'package:spike_app/desktop/desktop_home.dart';
import 'package:spike_app/desktop/desktop_nav.dart';
import 'package:spike_app/desktop/desktop_state.dart';
import 'package:spike_app/desktop/robot_setup.dart';
import 'package:spike_app/features/settings/settings_screen.dart';
import 'package:spike_app/protocol/messages.dart';
import 'package:spike_app/state/link.dart';
import 'package:spike_app/state/pairing_sync.dart';
import 'package:spike_app/state/settings.dart';
import 'package:spike_app/state/voice.dart';

import 'voice_session_test.dart' show Rig, settle;

/// The real dart:io HTTP client (flutter_test installs a stub by default).
class _RealHttp extends HttpOverrides {}

// ---------------------------------------------------------------- a fake brain process
class FakeProcess implements Process {
  FakeProcess(this.pid);
  @override
  final int pid;
  final _exit = Completer<int>();
  final stdinClosed = Completer<void>();
  bool killed = false;
  bool exitOnStdinClose = true;
  late final IOSink _stdin = IOSink(_StdinSink(this));

  void crash(int code) {
    if (!_exit.isCompleted) _exit.complete(code);
  }

  @override
  Future<int> get exitCode => _exit.future;
  @override
  IOSink get stdin => _stdin;
  @override
  Stream<List<int>> get stdout => const Stream.empty();
  @override
  Stream<List<int>> get stderr => const Stream.empty();
  @override
  bool kill([ProcessSignal signal = ProcessSignal.sigterm]) {
    killed = true;
    crash(-1);
    return true;
  }
}

class _StdinSink implements StreamConsumer<List<int>> {
  _StdinSink(this.p);
  final FakeProcess p;
  @override
  Future<void> addStream(Stream<List<int>> stream) => stream.drain<void>();
  @override
  Future<void> close() async {
    if (!p.stdinClosed.isCompleted) p.stdinClosed.complete();
    if (p.exitOnStdinClose) p.crash(0);
  }
}

class Launch {
  Launch(this.exe, this.args, this.env);
  final String exe;
  final List<String> args;
  final Map<String, String> env;
}

const _cmd = BrainCommand(exe: r'C:\app\brain\spike_brain.exe', models: r'C:\app\brain\models', workDir: r'C:\app\brain');
const _key = 'AIzaSyTESTONLY0123456789abcdefghijklmnop'; // a made-up test value, never a real key

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  Haptics.enabled = false;

  group('built-in brain helper', () {
    late List<Launch> launches;
    late List<FakeProcess> procs;
    Set<int> busy = {};
    BrainSidecar make({BrainCommand? cmd = _cmd, List<Duration>? backoff, Duration grace = const Duration(seconds: 2)}) {
      launches = [];
      procs = [];
      return BrainSidecar(
        command: cmd,
        home: r'C:\data\spikebuddy\brain',
        parentPid: 4242,
        portFree: (p) async => !busy.contains(p),
        stopGrace: grace,
        backoff: backoff ?? const [Duration(milliseconds: 10), Duration(milliseconds: 10)],
        starter: (exe, args, {required environment, workingDirectory}) async {
          launches.add(Launch(exe, args, environment));
          final p = FakeProcess(1000 + procs.length);
          procs.add(p);
          return p;
        },
      );
    }

    setUp(() => busy = {});

    test('starts on the first free port with the desktop profile; the key only in its environment', () async {
      busy = {8765}; // e.g. the owner's own brain from run_spike_wifi.bat
      final s = make();
      final port = await s.start(geminiKey: _key);
      expect(port, 8766);
      expect(s.state.run, BrainRun.running);
      final l = launches.single;
      expect(l.exe, _cmd.exe);
      expect(l.args, containsAllInOrder(['--profile', 'desktop', '--home', r'C:\data\spikebuddy\brain', '--models', _cmd.models]));
      expect(l.args, containsAll(['--port', '8766', '--parent-pid', '4242', '--stop-on-stdin-eof', '--no-camera']));
      expect(l.args, isNot(contains('--no-mic')));
      expect(l.args.join(' '), isNot(contains(_key)), reason: 'never on the command line');
      expect(l.env['GEMINI_API_KEY'], _key);
      await s.stop();
    });

    test('no key = an EMPTY variable (a GEMINI_API_KEY in the user environment is never picked up)', () {
      expect(BrainSidecar.environment(null)['GEMINI_API_KEY'], '');
      expect(make().args(8765, mic: false), contains('--no-mic'));
    });

    test('a clean stop closes stdin; a hung brain is killed after the grace time', () async {
      final s = make(grace: const Duration(milliseconds: 50));
      await s.start();
      final p = procs.single;
      await s.stop();
      expect(p.stdinClosed.isCompleted, isTrue);
      expect(p.killed, isFalse);
      expect(s.state.run, BrainRun.stopped);
      await s.start();
      final hung = procs.last..exitOnStdinClose = false;
      await s.stop();
      expect(hung.killed, isTrue);
    });

    test('a crash restarts it with back-off; too many crashes = failed', () async {
      final s = make();
      await s.start();
      procs.last.crash(3);
      await settle(60);
      expect(launches.length, 2);
      expect(s.state.run, BrainRun.running);
      procs.last.crash(3);
      await settle(60);
      expect(launches.length, 3);
      procs.last.crash(3);
      await settle(60);
      expect(s.state.run, BrainRun.failed);
      expect(launches.length, 3, reason: 'no more restarts after the limit');
      await s.retry();
      expect(s.state.run, BrainRun.running);
      await s.stop();
    });

    test('restart with a new key stops the old run first; missing brain / all ports busy are reported', () async {
      final s = make();
      await s.start();
      final first = procs.single;
      await s.restart(geminiKey: _key);
      expect(first.stdinClosed.isCompleted, isTrue);
      expect(launches.last.env['GEMINI_API_KEY'], _key);
      await s.stop();
      final none = make(cmd: null);
      expect(await none.start(), isNull);
      expect(none.state.run, BrainRun.missing);
      busy = {8765, 8766, 8767, 8768, 8769};
      final full = make();
      expect(await full.start(), isNull);
      expect(full.state.run, BrainRun.failed);
    });

    test('data folder: the permanent internal id, never the product name; a scratch folder for dev', () {
      expect(brainHome({'LOCALAPPDATA': r'C:\Users\x\AppData\Local'}), r'C:\Users\x\AppData\Local\spikebuddy\brain');
      expect(AppBrand.internalId, 'spikebuddy');
      expect(brainHome({'LOCALAPPDATA': r'C:\L', 'SPIKE_BRAIN_HOME': r'D:\scratch'}), r'D:\scratch');
    });

    test('locates the packaged brain next to the app, else a dev checkout', () {
      final dir = Directory.systemTemp.createTempSync('spike_locate');
      addTearDown(() => dir.deleteSync(recursive: true));
      final exe = '${dir.path}\\spike_app.exe';
      expect(BrainCommand.locate(appExe: exe, env: const {}), isNull);
      Directory('${dir.path}\\brain').createSync();
      File('${dir.path}\\brain\\spike_brain.exe').writeAsStringSync('');
      final c = BrainCommand.locate(appExe: exe, env: const {})!;
      expect(c.exe, endsWith(r'brain\spike_brain.exe'));
      expect(c.models, endsWith(r'brain\models'));
      expect(c.prefix, isEmpty);
    });
  });

  group('WebView2 bridge', () {
    test('the page gets the same channel objects as on the phone', () {
      final js = bridgeScript(['SpikeBridge', 'SpikeViewer']);
      expect(js, contains("'SpikeBridge','SpikeViewer'"));
      expect(js, contains('chrome.webview'));
      expect(js, contains('postMessage({ch:n,m:String(m)})'));
      expect(assetsHost, 'spike.assets');
    });
  });

  group('robot Wi-Fi setup (the firmware portal)', () {
    // the exact HTML the firmware sends (screen_board/src/provision.cpp, camera_board/src/cam_main.cpp)
    const screenPage = '<!doctype html><html><head><title>Spike setup</title></head><body><h2>Spike setup</h2>'
        '<form method=post action=/save><label>Home Wi-Fi name (2.4 GHz)<input name=ssid value="Home &amp; Co"></label>'
        '<label>Laptop brain address (IP)<input name=host value="192.168.1.5"></label>'
        '<button>Save and restart</button></form><p>Device spike-1a2b3c</p></body></html>';
    const camPage = '<html><body><h2>Spike camera setup</h2><form method=post action=/save>'
        '<label>Home Wi-Fi name (2.4 GHz)<input name=ssid value=""></label></form></body></html>';

    test('recognises each board and reads what it has saved', () {
      final s = parsePortalPage(screenPage)!;
      expect(s.board, PortalBoard.screen);
      expect(s.deviceId, 'spike-1a2b3c');
      expect(s.ssid, 'Home & Co');
      expect(s.host, '192.168.1.5');
      expect(parsePortalPage(camPage)!.board, PortalBoard.camera);
      expect(parsePortalPage('<html>a router login</html>'), isNull);
    });

    test('the form: brain address and token filled in; the robot id only for the camera', () {
      final f = portalForm(board: PortalBoard.screen, ssid: 'Home', password: 'pw', brainHost: '192.168.1.102', brainPort: 8765, token: 'tok');
      expect(f, {'ssid': 'Home', 'pass': 'pw', 'host': '192.168.1.102', 'port': '8765', 'token': 'tok'});
      final c = portalForm(board: PortalBoard.camera, ssid: 'Home', password: 'pw', brainHost: 'h', brainPort: 1, token: 't', robotId: 'spike-1a2b3c');
      expect(c['robot'], 'spike-1a2b3c');
    });

    test('talks to a portal over HTTP: probe, then save', () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      final posted = <String>[];
      server.listen((r) async {
        if (r.method == 'GET') {
          r.response.headers.contentType = ContentType.html;
          r.response.write(screenPage);
        } else {
          posted.add(await utf8.decoder.bind(r).join());
          r.response.write('<html><body><h2>Saved. Spike restarts now.</h2></body></html>');
        }
        await r.response.close();
      });
      addTearDown(() => server.close(force: true));
      // flutter_test replaces HTTP with a stub that always answers 400: this test needs the real one
      await HttpOverrides.runWithHttpOverrides(() async {
      final portal = RobotPortal(base: 'http://127.0.0.1:${server.port}');
      addTearDown(portal.close);
      final found = await waitForPortal(portal, every: const Duration(milliseconds: 10), within: const Duration(seconds: 2));
      expect(found?.board, PortalBoard.screen);
      final ok = await portal.save(portalForm(
          board: PortalBoard.screen, ssid: 'Home', password: 'p w&', brainHost: '192.168.1.102', brainPort: 8765, token: 'tok'));
      expect(ok, isTrue);
      expect(Uri.splitQueryString(posted.single), containsPair('pass', 'p w&'));
      expect(await RobotPortal(base: 'http://127.0.0.1:1').probe(), isNull, reason: 'nothing there = not found, no throw');
      }, _RealHttp());
    });
  });

  group('Start with Windows', () {
    test('states from the runner channel, and what the owner may change', () async {
      expect(parseStartState('enabled').isOn, isTrue);
      expect(parseStartState('disabledByUser').canChange, isFalse);
      expect(parseStartState('disabledByUser').note, contains('Startup'));
      expect(parseStartState('nonsense'), StartWithWindows.unknown);
      const ch = MethodChannel('spikebuddy/desktop.test');
      final calls = <String>[];
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(ch, (c) async {
        calls.add(c.method);
        return c.method == 'startupTask.enable' ? 'enabled' : 'disabled';
      });
      final d = DesktopChannel(ch);
      expect(await d.startWithWindows(), StartWithWindows.disabled);
      expect(await d.setStartWithWindows(true), StartWithWindows.enabled);
      expect(calls, ['startupTask.get', 'startupTask.enable']);
    });
  });

  group('voice style (protocol v1.8)', () {
    test('encodes and decodes both directions, and the hello field', () {
      final out = const VoiceStyleMsg(mode: 'dog', style: 'street').toJson(id: 3);
      expect(out, {'v': 1, 'type': 'voice_style', 'id': 3, 'mode': 'dog', 'style': 'street'});
      final fromApp = SpikeMessage.fromJson(out, from: Sender.client) as VoiceStyleMsg;
      expect((fromApp.mode, fromApp.style), ('dog', 'street'));
      final fromBrain = SpikeMessage.fromJson(
          {'v': 1, 'type': 'voice_style', 'id': 9, 'styles': {'dog': 'street', 'cat': 'sassy'}}, from: Sender.brain) as VoiceStyleMsg;
      expect(fromBrain.styles, {'dog': 'street', 'cat': 'sassy'});
      final hello = SpikeMessage.fromJson({
        'v': 1, 'type': 'hello', 'id': 1, 'server': 'spike-brain', 'version': '1.0.0', 'heartbeat_s': 5, 'mode': 'dog',
        'voice_style': {'dog': 'energetic', 'cat': 'caring'},
      }, from: Sender.brain) as BrainHello;
      expect(hello.voiceStyle, {'dog': 'energetic', 'cat': 'caring'});
      final old = SpikeMessage.fromJson(
          {'v': 1, 'type': 'hello', 'id': 1, 'server': 'spike-brain', 'version': '0.1.0', 'heartbeat_s': 5, 'mode': 'dog'},
          from: Sender.brain) as BrainHello;
      expect(old.voiceStyle, isNull);
    });
  });

  group('desktop voice session: the brain hears the computer mic itself', () {
    setUp(() => VoiceController.brainOwnMic = true);
    tearDown(() => VoiceController.brainOwnMic = false);

    test('tap on = listen now + silent keep-alives; no audio from the app, no mic of its own', () async {
      VoiceController.keepAliveEvery = const Duration(milliseconds: 30);
      final r = await Rig.make();
      expect(await r.voice.start(), isTrue);
      await settle(120);
      expect(r.state.phase, VoicePhase.listening);
      expect(r.link.taps, 1);
      expect(r.link.keeps, greaterThanOrEqualTo(2));
      expect(r.mic.starts, 0, reason: 'the app never opens the microphone on the desktop');
      await r.voice.stop();
      expect(r.link.audio, isEmpty, reason: 'nothing is streamed (no closing silence either)');
      r.dispose();
      VoiceController.keepAliveEvery = const Duration(seconds: 2);
    });

    test('with the microphone switched off for Spike, the mic button explains instead', () async {
      final r = await Rig.make();
      r.c.read(settingsProvider.notifier).update((s) => s.copyWith(desktopMic: false));
      expect(await r.voice.start(), isFalse);
      expect(r.state.notice, contains('microphone is off'));
      r.dispose();
    });
  });

  group('desktop screens', () {
    setUp(() => AppPlatform.debugDesktop = true);
    tearDown(() => AppPlatform.debugDesktop = null);

    Future<ProviderContainer> pump(WidgetTester t, Widget child, {List overrides = const []}) async {
      SharedPreferences.setMockInitialValues({});
      final prefs = await SharedPreferences.getInstance();
      final c = ProviderContainer(overrides: [prefsProvider.overrideWithValue(prefs), ...overrides.cast()]);
      await t.binding.setSurfaceSize(const Size(1280, 1600));
      addTearDown(() => t.binding.setSurfaceSize(null));
      await t.pumpWidget(UncontrolledProviderScope(
        container: c,
        child: MaterialApp(theme: buildTheme(Brightness.light), home: child),
      ));
      await t.pump(const Duration(milliseconds: 300));
      return c;
    }

    testWidgets('Settings: the computer section, key, voice and About; no phone-only sections', (t) async {
      final c = await pump(t, const SettingsScreen());
      expect(find.text('Spike on this computer'), findsOneWidget);
      expect(find.text('Start with Windows'), findsOneWidget);
      expect(find.text('Listen on this computer\'s microphone'), findsOneWidget);
      final list = find.byType(Scrollable).first;
      await t.scrollUntilVisible(find.text('Gemini natural voice'), 300, scrollable: list);
      expect(find.text('Gemini natural voice'), findsOneWidget);
      await t.scrollUntilVisible(find.byKey(const ValueKey('aboutVersion')), 300, scrollable: list);
      expect(find.text('Version $appVersion'), findsOneWidget);
      expect(find.text('Made by ${AppBrand.developerName} · ${AppBrand.publisherDisplayName}'), findsOneWidget);
      expect(find.text('Away from home'), findsNothing);
      expect(find.text('Haptics'), findsNothing);
      expect(find.text('Spike\'s brain at home'), findsNothing);
      c.dispose();
    });

    testWidgets('Phone and robot: the pairing QR with the typed address, and robot setup', (t) async {
      final c = await pump(t, const PhoneAndRobotScreen());
      expect(find.text('Starting Spike\'s brain...'), findsOneWidget);
      c.read(lastPairingProvider.notifier).set(
          const PairingMsg(lan: true, url: 'spike://pair?host=192.168.1.102&port=8766&token=abcdef123456&name=Spike'));
      await t.pump(const Duration(milliseconds: 300));
      expect(find.text('Scan it with your phone'), findsOneWidget);
      expect(find.text('192.168.1.102'), findsOneWidget);
      expect(find.text('8766'), findsOneWidget);
      expect(find.text('abcdef123456'), findsNothing, reason: 'the pairing code is hidden until asked');
      await t.tap(find.byTooltip('Show'));
      await t.pump();
      expect(find.text('abcdef123456'), findsOneWidget);
      expect(find.text('Get Tailscale'), findsOneWidget);
      expect(find.text('Set up a robot'), findsWidgets);
      c.dispose();
    });

    testWidgets('the side rail: every tab, Phone and Settings', (t) async {
      // a large window: the full sidebar with its long labels (a small one shows the icon rail)
      t.view.physicalSize = const Size(1920, 1080);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      final c = await pump(t, Scaffold(body: Row(children: [DesktopNav(index: 3, items: AppShell.desktopSections, onTap: (_) {})])));
      for (final l in ['Home', 'Play', 'Studio', 'Life', 'Phone and robot', 'Settings', 'Mini window', AppBrand.productName]) {
        expect(find.text(l), findsWidgets, reason: l);
      }
      c.dispose();
    });

    test('the desktop joins without audio_out; the phone keeps it', () {
      expect(desktopCaps, isNot(contains('audio_out')));
      expect(appCaps, contains('audio_out'));
    });
  });

  group('one place for names and the version', () {
    final root = Directory.current.path;
    test('brand.json and lib/core/brand.dart agree (run: dart run tool/sync_brand.dart)', () {
      final j = jsonDecode(File('$root/brand.json').readAsStringSync()) as Map<String, dynamic>;
      expect(AppBrand.productName, j['productName']);
      expect(AppBrand.storeName, j['storeName']);
      expect(AppBrand.startMenuName, j['startMenuName']);
      expect(AppBrand.publisherDisplayName, j['publisherDisplayName']);
      expect(AppBrand.copyrightHolder, j['copyrightHolder']);
      expect(AppBrand.developerName, j['developerName']);
      expect(AppBrand.developerName, isNotEmpty);
      expect(AppBrand.internalId, j['internalId']);
    });

    test('the Android launcher label comes from brand.json, not the manifest', () {
      expect(File('$root/android/app/src/main/AndroidManifest.xml').readAsStringSync(), contains(r'android:label="${appLabel}"'));
      expect(File('$root/android/app/build.gradle.kts').readAsStringSync(), contains('manifestPlaceholders["appLabel"]'));
    });

    test('pubspec, lib/core/version.dart and the brain report the same version', () {
      final pub = RegExp(r'^version:\s*(\d+\.\d+\.\d+)\+(\d+)', multiLine: true)
          .firstMatch(File('$root/pubspec.yaml').readAsStringSync())!;
      expect(appVersion, pub.group(1));
      final brain = File('$root/../../laptop/spike_brain/__init__.py');
      if (brain.existsSync()) {
        expect(brain.readAsStringSync(), contains('__version__ = "${pub.group(1)}"'));
      }
    });

    test('no product, store or publisher name is hard-coded in the app code', () {
      final names = {AppBrand.storeName, AppBrand.tagline, AppBrand.publisherDisplayName, AppBrand.developerName, 'Desk Buddy'}..removeWhere((n) => n.isEmpty);
      final offenders = <String>[];
      for (final f in Directory('$root/lib').listSync(recursive: true).whereType<File>()) {
        if (!f.path.endsWith('.dart') || f.path.endsWith('brand.dart')) continue;
        final text = f.readAsStringSync();
        for (final n in names) {
          if (text.contains(n)) offenders.add('${f.path}: $n');
        }
      }
      expect(offenders, isEmpty);
    });
  });
}
