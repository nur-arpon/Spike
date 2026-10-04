// Device proof of the Kokoro add-on, with no taps and no network calls other than the add-on's own upstream
// downloads (no Gemini, no Spike brain). Built as a RELEASE APK of com.spacez.spike (same release key, so
// `adb install -r` keeps the installed app's data; no uninstall path), run once, then the real release APK is
// reinstalled over it. Results go to logcat with the tag text "KOKORO-PROBE".
//
//   flutter build apk --release --target-platform android-arm64 -t tool/device_probe/kokoro_addon_probe.dart
//
// It runs the real installer code: downloadAndInstallEngine (BundleDownloader + KokoroEngineFiles.install,
// SHA-256 checked) and the KokoroPack voice download, then synthesises one short phrase with AddonKokoroVoice
// into a buffer (prepare() only: nothing is played).
import 'dart:async';
import 'dart:io';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:spike_app/away/download/bundle_downloader.dart';
import 'package:spike_app/away/voice/kokoro_addon.dart';
import 'package:spike_app/away/voice/kokoro_voice_addon.dart';
import 'package:spike_app/away/voice/speaker.dart';

final _lines = ValueNotifier<List<String>>([]);

void _log(String s) {
  debugPrint('KOKORO-PROBE $s');
  _lines.value = [..._lines.value, s];
}

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(MaterialApp(
    home: Scaffold(
      body: SafeArea(
        child: ValueListenableBuilder<List<String>>(
          valueListenable: _lines,
          builder: (_, l, _) => ListView(padding: const EdgeInsets.all(12), children: [
            const Text('Kokoro add-on device probe (temporary build)'),
            for (final s in l) Text(s),
          ]),
        ),
      ),
    ),
  ));
  unawaited(_probe());
}

Future<void> _probe() async {
  final sw = Stopwatch()..start();
  try {
    final support = (await getApplicationSupportDirectory()).path;
    final pack = KokoroPack(Directory('$support/kokoro'));
    final engine = pack.engine;
    _log('start: engine.ready=${engine.ready} voice.installed=${pack.installed} dir=${engine.dir.path}');

    // step 1: the engine (46 MB archive from the sherpa-onnx GitHub release, SHA-256 pinned)
    final edl = BundleDownloader.forBundle(engine.bundle);
    var last = -1;
    final esub = edl.status.listen((s) {
      final pc = (s.fraction * 100).round();
      if (pc ~/ 10 != last ~/ 10 || s.phase != DlPhase.downloading) _log('engine $s');
      last = pc;
    });
    final es = await downloadAndInstallEngine(engine, edl);
    await esub.cancel();
    _log('engine download: $es; ready=${engine.ready} after ${sw.elapsed.inSeconds}s');
    if (!engine.ready) throw StateError('engine not ready');
    for (final l in kokoroEngineLibs) {
      final st = await engine.libFile(l).stat();
      _log('  ${l.name}: ${st.size} bytes, mode ${st.modeString()}');
    }
    _log('load check: native version ${await realEngineLoadCheck(engine.dir.path)}');

    // step 2: the voice files (Hugging Face, pinned revision; espeak-ng-data from the sherpa-onnx release)
    final bundle = await pack.bundle();
    final vdl = BundleDownloader.forBundle(bundle);
    last = -1;
    final vsub = vdl.status.listen((s) {
      final pc = (s.fraction * 100).round();
      if (pc ~/ 10 != last ~/ 10 || s.phase != DlPhase.downloading) _log('voice $s');
      last = pc;
    });
    final vs = await vdl.start();
    await vsub.cancel();
    _log('voice download: $vs; installed=${pack.installed} ready=${pack.ready} after ${sw.elapsed.inSeconds}s');
    if (!pack.ready) throw StateError('voice pack not ready');

    // step 3: one short phrase, synthesised into a buffer (prepare() does not play it)
    final voice = AddonKokoroVoice(pack, AudioPlayer());
    final t0 = sw.elapsedMilliseconds;
    final said = await voice.prepare('Hello, I am Spike.', mode: 'dog');
    final mouth = said.clip.mouth ?? const <int>[];
    final peak = mouth.isEmpty ? 0 : mouth.reduce((a, b) => a > b ? a : b);
    _log('synth: ${said.clip.durationMs} ms of audio in ${sw.elapsedMilliseconds - t0} ms; '
        'mouth frames ${mouth.length}, peak $peak');
    voice.dispose();
    _log(said.clip.durationMs > 300 && peak > 0 ? 'RESULT PASS' : 'RESULT FAIL (empty audio)');
  } catch (e, st) {
    _log('RESULT FAIL $e');
    debugPrint('$st');
  }
}
