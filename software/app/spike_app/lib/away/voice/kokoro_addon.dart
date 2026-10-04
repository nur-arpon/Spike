/// The Kokoro speech engine as an OPTIONAL add-on the owner fetches himself (Android only).
///
/// Why: Kokoro runs through sherpa-onnx, whose native library links espeak-ng (GPL-3.0). Spike's
/// licence is all rights reserved, so the APK carries NO sherpa-onnx / ONNX Runtime / espeak-ng
/// native code, and the publisher never hosts or redistributes those binaries. When the owner taps
/// "Download and install" in Settings > Voice, the phone itself downloads the OFFICIAL prebuilt
/// Android libraries straight from the sherpa-onnx project's own GitHub release (the way Audacity
/// users once fetched the LAME encoder themselves), checks them against the hashes pinned below,
/// and keeps the two arm64 libraries in the app's private files folder. The voice files come from
/// their own upstream pages (speaker.dart KokoroPack). The app's Dart code opens the libraries by
/// absolute path (third_party/sherpa_onnx_ffi, Apache-2.0).
///
/// Pinned on 4 Oct 2026 (software/app/ANDROID-RELEASE.md "The Kokoro add-on"):
/// - the archive's SHA-256 is the one GitHub itself publishes for the release asset;
/// - the two libraries' SHA-256 were taken from that archive (arm64-v8a);
/// - the version matches the vendored Dart bindings (1.13.8): every C function they bind exists.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:archive/archive.dart' show BZip2Decoder, InputFileStream, OutputFileStream;
import 'package:sherpa_onnx_ffi/sherpa_onnx_ffi.dart' show loadSherpaOnnx, sherpaOnnxNativeVersion, sherpaOnnxBindingVersion;

import '../download/bundle.dart';
import '../download/bundle_downloader.dart';

/// The upstream release asset (k2-fsa/sherpa-onnx, tag v1.13.8): prebuilt Android libraries for
/// every ABI. Only the two arm64-v8a libraries below are kept.
const kokoroEngineArchive = BundleFile(
  url: 'https://github.com/k2-fsa/sherpa-onnx/releases/download/v$sherpaOnnxBindingVersion/'
      'sherpa-onnx-v$sherpaOnnxBindingVersion-android.tar.bz2',
  path: 'sherpa-onnx-v$sherpaOnnxBindingVersion-android.tar.bz2',
  size: 46093321,
  sha256: '2ff63469a71cb6009aa2e3ed5f4a670f8abdcbe4bb9ffd23776afc792a6b4f44',
);

class EngineLib {
  const EngineLib(this.name, this.size, this.sha256);
  final String name;
  final int size;
  final String sha256;
  String get tarPath => 'jniLibs/arm64-v8a/$name';
}

/// In load order: ONNX Runtime first (the C API library depends on it by soname).
const kokoroEngineLibs = [
  EngineLib('libonnxruntime.so', 22249560, '33847ad43bffe204699fd4a27f7f3603452a8cdaf2f9a44983a0bc31ffcf2da1'),
  EngineLib('libsherpa-onnx-c-api.so', 4465168, 'c85e2382e2ca12b0513826be926eaccfea896b4cbf568182e287671ba526f80d'),
];

/// What the engine takes on the phone once installed (the archive itself is deleted).
int get kokoroEngineInstalledBytes => kokoroEngineLibs.fold(0, (a, l) => a + l.size);

/// Where each part comes from and its licence, for the Settings card.
const kokoroAddonSources = [
  ('sherpa-onnx (speech engine)', 'Apache-2.0', 'https://github.com/k2-fsa/sherpa-onnx'),
  ('espeak-ng (pronunciation, inside the engine)', 'GPL-3.0', 'https://github.com/espeak-ng/espeak-ng'),
  ('ONNX Runtime (inside the engine)', 'MIT', 'https://github.com/microsoft/onnxruntime'),
  ('Kokoro-82M voices (sherpa-onnx export)', 'Apache-2.0', 'https://huggingface.co/csukuangfj/kokoro-multi-lang-v1_0'),
];

class KokoroAddonError implements Exception {
  const KokoroAddonError(this.message, {this.integrity = false});
  final String message; // for the log
  final bool integrity; // a hash did not match: the files were refused
  @override
  String toString() => 'KokoroAddonError($message)';
}

/// Loads the libraries in [dir] and returns the version the native code reports (runs in a
/// throw-away isolate in the app; tests inject their own).
typedef EngineLoadCheck = Future<String> Function(String dir);

Future<String> realEngineLoadCheck(String dir) => Isolate.run(() {
      loadSherpaOnnx(dir);
      return sherpaOnnxNativeVersion();
    });

/// The load check the app uses (tests swap in a fake: there are no Android libraries on their host).
EngineLoadCheck kokoroEngineLoadCheck = realEngineLoadCheck;

/// The engine's folder: `<app support>/kokoro_engine/`.
class KokoroEngineFiles {
  KokoroEngineFiles(this.dir, {this.archive = kokoroEngineArchive, this.libs = kokoroEngineLibs});
  final Directory dir;
  final BundleFile archive;
  final List<EngineLib> libs;

  /// Written only after the libraries were checked AND loaded once without an error.
  static const readyMarker = '.engine-ready';

  String get _folder => dir.uri.pathSegments.where((s) => s.isNotEmpty).last;

  /// The download (one file, resumable, checked against [archive]'s SHA-256 by the downloader).
  Bundle get bundle => Bundle(id: 'kokoro_engine', root: dir.parent, folder: _folder, files: [archive], title: 'Kokoro engine');

  File get archiveFile => File('${dir.path}/${archive.path}');
  File libFile(EngineLib l) => File('${dir.path}/${l.name}');

  /// Installed and proven to load (sizes re-checked: a file that vanished or changed is not ready).
  bool get ready {
    if (!File('${dir.path}/$readyMarker').existsSync()) return false;
    for (final l in libs) {
      final f = libFile(l);
      if (!f.existsSync() || f.lengthSync() != l.size) return false;
    }
    return true;
  }

  /// The archive arrived (the downloader proved it): take the two libraries out, check each
  /// against its pinned SHA-256, make them read-only, load them once, then mark ready and drop the
  /// archive. Anything that does not match is refused: the whole folder is removed and nothing is
  /// loaded. Throws [KokoroAddonError].
  Future<void> install({EngineLoadCheck? loadCheck}) async {
    try {
      final problem = await verifyFile(archiveFile, archive);
      if (problem != null) throw KokoroAddonError('archive: $problem', integrity: problem == 'checksum mismatch' || problem.startsWith('size'));
      final wanted = {for (final l in libs) l.tarPath: l.name};
      final got = await Isolate.run(() => _extract(archiveFile.path, dir.path, wanted));
      for (final l in libs) {
        if (!got.contains(l.name)) throw KokoroAddonError('${l.name} not in the archive');
        final spec = BundleFile(url: '', path: l.name, size: l.size, sha256: l.sha256);
        final bad = await verifyFile(libFile(l), spec);
        if (bad != null) throw KokoroAddonError('${l.name}: $bad', integrity: true);
      }
      for (final l in libs) {
        await _readOnly(libFile(l));
      }
      final version = await (loadCheck ?? kokoroEngineLoadCheck)(dir.path);
      if (version != sherpaOnnxBindingVersion) throw KokoroAddonError('engine reports version $version, expected $sherpaOnnxBindingVersion');
      await File('${dir.path}/$readyMarker').writeAsString(jsonEncode({'version': version, 'at': DateTime.now().toIso8601String()}), flush: true);
      if (await archiveFile.exists()) await archiveFile.delete();
    } on KokoroAddonError {
      await delete();
      rethrow;
    } catch (e) {
      await delete();
      throw KokoroAddonError('$e');
    }
  }

  Future<void> delete() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  }

  /// Android 14+ asks that dynamically loaded code is read-only; harmless elsewhere.
  static Future<void> _readOnly(File f) async {
    if (!Platform.isAndroid) return;
    try {
      await Process.run('chmod', ['0444', f.path]);
    } catch (_) {}
  }
}

/// Streams the .tar.bz2 to a temporary .tar (no 130 MB in memory), then copies out only the
/// [wanted] tar paths (tar path -> file name in [dir]). Returns the file names written.
Future<List<String>> _extract(String archive, String dir, Map<String, String> wanted) async {
  final tarPath = '$dir/.engine.tar';
  final input = InputFileStream(archive);
  final output = OutputFileStream(tarPath);
  try {
    BZip2Decoder().decodeStream(input, output);
  } finally {
    await input.close();
    await output.close();
  }
  final out = <String>[];
  final raf = await File(tarPath).open();
  try {
    final len = await raf.length();
    var pos = 0;
    while (pos + 512 <= len) {
      await raf.setPosition(pos);
      final h = await raf.read(512);
      if (h.every((b) => b == 0)) break;
      final name = _tarString(h, 0, 100);
      // POSIX ustar keeps a path prefix at 345; GNU tar ("ustar  ") keeps timestamps there instead
      final posix = h[257] == 0x75 && h[262] == 0 && _tarString(h, 257, 6) == 'ustar';
      final prefix = posix ? _tarString(h, 345, 155) : '';
      final sizeField = _tarString(h, 124, 12).trim();
      final size = sizeField.isEmpty ? 0 : int.parse(sizeField, radix: 8);
      final type = h[156];
      var full = prefix.isEmpty ? name : '$prefix/$name';
      if (full.startsWith('./')) full = full.substring(2);
      final dest = wanted[full];
      if (dest != null && (type == 0x30 || type == 0) && !dest.contains('/') && !dest.contains('..')) {
        final part = File('$dir/$dest.part');
        final sink = part.openWrite();
        var left = size;
        await raf.setPosition(pos + 512);
        while (left > 0) {
          final chunk = await raf.read(left < (1 << 20) ? left : (1 << 20));
          if (chunk.isEmpty) break;
          sink.add(chunk);
          left -= chunk.length;
        }
        await sink.flush();
        await sink.close();
        final target = File('$dir/$dest');
        if (await target.exists()) await target.delete();
        await part.rename(target.path);
        out.add(dest);
      }
      pos += 512 + ((size + 511) ~/ 512) * 512;
    }
  } finally {
    await raf.close();
    await File(tarPath).delete();
  }
  return out;
}

String _tarString(List<int> h, int start, int n) {
  final end = h.sublist(start, start + n).indexOf(0);
  return latin1.decode(h.sublist(start, end < 0 ? start + n : start + end));
}

/// Step 1 of installing the add-on (Settings card and the device probe use the same code): fetch
/// the engine archive (resumable; the downloader refuses it if its SHA-256 does not match), then
/// [KokoroEngineFiles.install]. Returns the download's final status; throws [KokoroAddonError]
/// when the files were refused or would not load. Step 2 is the voice files ([KokoroPack.bundle]).
Future<DlStatus> downloadAndInstallEngine(KokoroEngineFiles engine, BundleDownloader dl,
    {EngineLoadCheck? loadCheck, void Function()? onInstalling}) async {
  if (engine.ready) return const DlStatus(DlPhase.installed);
  final s = await dl.start();
  if (s.phase != DlPhase.installed) return s;
  onInstalling?.call();
  await engine.install(loadCheck: loadCheck);
  return s;
}
