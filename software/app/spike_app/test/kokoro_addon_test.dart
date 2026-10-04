// The optional Kokoro add-on (lib/away/voice/kokoro_addon.dart): the engine is refused unless every hash
// matches, nothing half-installed is left behind, and the Settings card's states. Mocks only: no network, no
// native libraries (the load check is a fake), no Gemini.
import 'dart:io';

import 'package:archive/archive.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:spike_app/away/ai/key_store.dart';
import 'package:spike_app/away/download/bundle.dart';
import 'package:spike_app/away/voice/kokoro_addon.dart';
import 'package:spike_app/away/voice/speaker.dart';
import 'package:spike_app/core/theme.dart';
import 'package:spike_app/features/settings/away_settings.dart';
import 'package:spike_app/state/away.dart';
import 'package:spike_app/state/settings.dart';

/// A tiny stand-in for the upstream archive: the two library paths with fake bytes, plus a file to skip.
({List<int> archive, List<EngineLib> libs}) fakeRelease({String? wrongShaFor}) {
  final ort = List<int>.generate(3000, (i) => i % 251);
  final api = List<int>.generate(1700, (i) => (i * 7) % 253);
  final tar = TarEncoder().encodeBytes(Archive()
    ..addFile(ArchiveFile.bytes('jniLibs/x86/libonnxruntime.so', [1, 2, 3]))
    ..addFile(ArchiveFile.bytes('jniLibs/arm64-v8a/libonnxruntime.so', ort))
    ..addFile(ArchiveFile.bytes('jniLibs/arm64-v8a/libsherpa-onnx-c-api.so', api)));
  final libs = [
    EngineLib('libonnxruntime.so', ort.length, wrongShaFor == 'libonnxruntime.so' ? '0' * 64 : sha256Hex(ort)),
    EngineLib('libsherpa-onnx-c-api.so', api.length, wrongShaFor == 'libsherpa-onnx-c-api.so' ? '0' * 64 : sha256Hex(api)),
  ];
  return (archive: BZip2Encoder().encodeBytes(tar), libs: libs);
}

Future<KokoroEngineFiles> placed(Directory root, List<int> bytes, List<EngineLib> libs, {String? archiveSha}) async {
  final spec = BundleFile(url: 'https://example.invalid/a.tar.bz2', path: 'a.tar.bz2', size: bytes.length, sha256: archiveSha ?? sha256Hex(bytes));
  final e = KokoroEngineFiles(Directory('${root.path}/kokoro_engine'), archive: spec, libs: libs);
  await e.dir.create(recursive: true);
  await e.archiveFile.writeAsBytes(bytes);
  return e;
}

class FakeAway extends AwayController {
  FakeAway(this.pack);
  final KokoroPack pack;
  int voiceChanges = 0;
  @override
  AwayState build() => const AwayState();
  @override
  Future<KokoroPack> voicePack() async => pack;
  @override
  Future<void> voiceChanged() async => voiceChanges++;
}

Future<void> pumpCard(WidgetTester t, KokoroPack pack) async {
  SharedPreferences.setMockInitialValues({});
  final p = await SharedPreferences.getInstance();
  t.view.physicalSize = const Size(1080, 2340);
  t.view.devicePixelRatio = 3;
  addTearDown(t.view.reset);
  await t.pumpWidget(ProviderScope(
    overrides: [
      prefsProvider.overrideWithValue(p),
      awayProvider.overrideWith(() => FakeAway(pack)),
      secretStoreProvider.overrideWithValue(MemorySecretStore()),
    ],
    child: MaterialApp(theme: buildTheme(Brightness.light), home: const Scaffold(body: SingleChildScrollView(child: KokoroAddonCard()))),
  ));
  await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
  for (var i = 0; i < 5; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

/// Makes [pack] look fully installed: the voice marker, the engine's ready marker and both libraries at their
/// pinned sizes (sparse files: no 26 MB written).
void fakeInstalled(KokoroPack pack) {
  Directory(pack.dir.path).createSync(recursive: true);
  File('${pack.dir.path}/${Bundle.completeMarker}').writeAsStringSync('x');
  final e = pack.engine;
  e.dir.createSync(recursive: true);
  for (final l in e.libs) {
    final f = e.libFile(l).openSync(mode: FileMode.write);
    f.truncateSync(l.size);
    f.closeSync();
  }
  File('${e.dir.path}/${KokoroEngineFiles.readyMarker}').writeAsStringSync('{}');
}

void main() {
  late Directory tmp;
  setUp(() => tmp = Directory.systemTemp.createTempSync('kokoro_addon_'));
  tearDown(() {
    if (tmp.existsSync()) tmp.deleteSync(recursive: true);
  });

  group('pins', () {
    test('the engine comes from the upstream sherpa-onnx GitHub release, same version as the vendored bindings', () {
      expect(kokoroEngineArchive.url,
          'https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-v1.13.8-android.tar.bz2');
      expect(kokoroEngineArchive.sha256, matches(RegExp(r'^[0-9a-f]{64}$')));
      expect(kokoroEngineArchive.size, 46093321);
      expect(kokoroEngineLibs.first.name, 'libonnxruntime.so', reason: 'loaded first: the C API needs it by soname');
      for (final l in kokoroEngineLibs) {
        expect(l.sha256, matches(RegExp(r'^[0-9a-f]{64}$')));
        expect(l.tarPath, startsWith('jniLibs/arm64-v8a/'));
      }
      for (final (_, _, url) in kokoroAddonSources) {
        expect(url, isNot(contains('spacez')), reason: 'nothing of the add-on is hosted by SpaceZ');
      }
    });
  });

  group('install', () {
    test('a matching archive installs: libraries checked, loaded once, archive dropped', () async {
      final r = fakeRelease();
      final e = await placed(tmp, r.archive, r.libs);
      String? loadedFrom;
      await e.install(loadCheck: (d) async {
        loadedFrom = d;
        return '1.13.8';
      });
      expect(e.ready, isTrue);
      expect(loadedFrom, e.dir.path);
      expect(e.archiveFile.existsSync(), isFalse);
      expect(File('${e.dir.path}/libonnxruntime.so').lengthSync(), 3000);
      expect(File('${e.dir.path}/jniLibs').existsSync(), isFalse, reason: 'only the two arm64 libraries are kept');
      expect(e.dir.listSync().map((f) => f.uri.pathSegments.last).toSet(),
          {'libonnxruntime.so', 'libsherpa-onnx-c-api.so', KokoroEngineFiles.readyMarker});
    });

    test('HASH MISMATCH of the archive: refused, nothing loaded, nothing left', () async {
      final r = fakeRelease();
      final e = await placed(tmp, r.archive, r.libs, archiveSha: 'f' * 64);
      var loaded = false;
      await expectLater(
          e.install(loadCheck: (_) async {
            loaded = true;
            return '1.13.8';
          }),
          throwsA(isA<KokoroAddonError>().having((x) => x.integrity, 'integrity', isTrue)));
      expect(loaded, isFalse);
      expect(e.ready, isFalse);
      expect(e.dir.existsSync(), isFalse);
    });

    test('HASH MISMATCH of a library inside a genuine-looking archive: refused, nothing loaded, nothing left', () async {
      final r = fakeRelease(wrongShaFor: 'libsherpa-onnx-c-api.so');
      final e = await placed(tmp, r.archive, r.libs);
      var loaded = false;
      await expectLater(
          e.install(loadCheck: (_) async {
            loaded = true;
            return '1.13.8';
          }),
          throwsA(isA<KokoroAddonError>().having((x) => x.integrity, 'integrity', isTrue)));
      expect(loaded, isFalse);
      expect(e.dir.existsSync(), isFalse);
    });

    test('a library that will not load: refused (not an integrity problem), removed, the voice chain unchanged', () async {
      final r = fakeRelease();
      final e = await placed(tmp, r.archive, r.libs);
      await expectLater(e.install(loadCheck: (_) async => throw ArgumentError('dlopen failed')),
          throwsA(isA<KokoroAddonError>().having((x) => x.integrity, 'integrity', isFalse)));
      expect(e.ready, isFalse);
      expect(e.dir.existsSync(), isFalse);
    });

    test('a library of another version is refused', () async {
      final r = fakeRelease();
      final e = await placed(tmp, r.archive, r.libs);
      await expectLater(e.install(loadCheck: (_) async => '1.12.0'), throwsA(isA<KokoroAddonError>()));
      expect(e.ready, isFalse);
    });

    test('a missing archive is refused', () async {
      final e = KokoroEngineFiles(Directory('${tmp.path}/kokoro_engine'));
      await expectLater(e.install(loadCheck: (_) async => '1.13.8'), throwsA(isA<KokoroAddonError>()));
      expect(e.ready, isFalse);
    });

    test('Kokoro is ready only with BOTH the voice files and the engine', () {
      final pack = KokoroPack(Directory('${tmp.path}/kokoro'));
      expect(pack.ready, isFalse);
      fakeInstalled(pack);
      expect(pack.ready, isTrue);
      File('${pack.engine.dir.path}/libsherpa-onnx-c-api.so').deleteSync();
      expect(pack.ready, isFalse, reason: 'a library that vanished is not ready');
    });
  });

  group('Settings card', () {
    setUp(() => debugKokoroAddonSupported = true);
    tearDown(() => debugKokoroAddonSupported = null);

    testWidgets('hidden off Android (the host here is not a phone running Android)', (t) async {
      debugKokoroAddonSupported = null;
      expect(kokoroAddonSupported, isFalse);
      expect(kokoroVoiceAvailable, isFalse);
    });

    testWidgets('not installed: collapsed by default; opened it explains source, size and licences', (t) async {
      final pack = KokoroPack(Directory('${tmp.path}/kokoro'));
      await pumpCard(t, pack);
      expect(find.text('Offline backup voice (Kokoro)'), findsOneWidget);
      expect(find.text('Download and install'), findsNothing, reason: 'collapsed by default');
      expect(find.textContaining('sherpa-onnx'), findsNothing);
      await t.tap(find.text('Offline backup voice (Kokoro)'));
      await t.pump();
      expect(find.textContaining('does not come from SpaceZ'), findsOneWidget);
      expect(find.textContaining('sherpa-onnx project\'s official release on GitHub'), findsOneWidget);
      expect(find.textContaining('Size: about 426 MB to download'), findsOneWidget);
      expect(find.text('espeak-ng (pronunciation, inside the engine): GPL-3.0'), findsOneWidget);
      expect(find.text('sherpa-onnx (speech engine): Apache-2.0'), findsOneWidget);
      expect(find.text('Download and install'), findsOneWidget);
      expect(find.text('Remove'), findsNothing);
      expect(find.text('Installed'), findsNothing);
    });

    testWidgets('installed: an Installed pill; Remove deletes both parts and updates the voice chain', (t) async {
      final pack = KokoroPack(Directory('${tmp.path}/kokoro'));
      fakeInstalled(pack);
      await pumpCard(t, pack);
      expect(find.text('Installed'), findsOneWidget);
      await t.tap(find.text('Offline backup voice (Kokoro)'));
      await t.pump();
      expect(find.text('Download and install'), findsNothing);
      await t.ensureVisible(find.text('Remove'));
      await t.pump();
      await t.tap(find.text('Remove'));
      for (var i = 0; i < 5; i++) {
        await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
        await t.pump();
      }
      expect(pack.engine.dir.existsSync(), isFalse);
      expect(pack.dir.existsSync(), isFalse);
      expect(pack.ready, isFalse);
      expect(find.text('Download and install'), findsOneWidget);
      expect(find.text('Installed'), findsNothing);
    });
  });
}
