/// What a big download is made of, and how each file is proven whole.
///
/// A [Bundle] is a set of files that land in one folder (Spike's voice pack is
/// ~360 files; the offline brain is one). Each [BundleFile] carries the size
/// and, when Hugging Face publishes one, the hash the server itself stands
/// behind: the SHA-256 of an LFS/Xet file (`lfs.oid` in the tree API, also the
/// `X-Linked-ETag` header), or the git blob SHA-1 of a small file (`oid`). A
/// file counts as downloaded only once its size and hash match; the bundle
/// counts as installed only once every file did ([completeMarker]).
library;

import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:archive/archive.dart' show BZip2Decoder, TarDecoder;
import 'package:crypto/crypto.dart';

class BundleFile {
  const BundleFile({required this.url, required this.path, required this.size, this.sha256, this.gitSha1});

  final String url;
  final String path; // relative to the bundle folder, '/'-separated
  final int size; // bytes, from the server's listing (0 = unknown)
  final String? sha256; // hex, whole-file SHA-256 (Hugging Face LFS/Xet files)
  final String? gitSha1; // hex, git blob SHA-1 (small, non-LFS Hugging Face files)

  /// One entry of `https://huggingface.co/api/models/<repo>/tree/<rev>`.
  static BundleFile fromHfTree(String repo, Map<dynamic, dynamic> e, {String revision = 'main'}) {
    final p = e['path'] as String;
    final lfs = e['lfs'];
    return BundleFile(
      url: 'https://huggingface.co/$repo/resolve/$revision/${p.split('/').map(Uri.encodeComponent).join('/')}',
      path: p,
      size: (e['size'] as num?)?.toInt() ?? 0,
      sha256: lfs is Map ? lfs['oid'] as String? : null,
      gitSha1: lfs is Map ? null : e['oid'] as String?,
    );
  }
}

/// One archive (tar.bz2) that carries many of a bundle's small files in a
/// single resumable download (DESIGN.md "Big downloads": 355 espeak-ng files
/// as 355 requests got HTTP 429 from Hugging Face). It is only a shortcut: every
/// file taken out of it is still checked against its own pinned hash, and a
/// file that does not match (or a broken/missing archive) is fetched on its own.
class BundleArchive {
  const BundleArchive({required this.id, required this.url, required this.size, required this.sha256, required this.prefix});
  final String id; // e.g. 'espeak'
  final String url;
  final int size;
  final String sha256; // pinned by us (the release site publishes no hash)
  final String prefix; // bundle paths it may provide, e.g. 'espeak-ng-data/'

  /// Where it is kept while downloading/unpacking (inside the bundle folder).
  String get fileName => '.archive-$id.tar.bz2';
  BundleFile get asFile => BundleFile(url: url, path: fileName, size: size, sha256: sha256);
}

/// Files that must all arrive before the bundle is usable.
class Bundle {
  const Bundle(
      {required this.id, required this.root, required this.folder, required this.files, required this.title, this.archives = const []});

  final String id; // also the download group, e.g. 'spike_voice'
  final Directory root; // the app-support folder (the downloader's BaseDirectory.applicationSupport)
  final String folder; // the bundle's folder inside [root], e.g. 'kokoro'
  final List<BundleFile> files;
  final String title; // for the notification, e.g. "Spike's voice"
  final List<BundleArchive> archives;

  Directory get dir => Directory('${root.path}/$folder');

  static const completeMarker = '.complete';
  static const progressFile = '.verified.json';

  int get totalBytes => files.fold(0, (a, f) => a + f.size);
  File fileFor(BundleFile f) => File('${dir.path}/${f.path}');
  bool get isComplete => isCompleteDir(dir);
  static bool isCompleteDir(Directory d) => File('${d.path}/$completeMarker').existsSync();

  /// Paths already downloaded AND proven whole (survives app restarts).
  Future<Set<String>> verifiedPaths() async {
    final f = File('${dir.path}/$progressFile');
    try {
      if (!await f.exists()) return {};
      final list = jsonDecode(await f.readAsString()) as List<dynamic>;
      final out = <String>{};
      for (final p in list.cast<String>()) {
        final spec = files.where((x) => x.path == p).firstOrNull;
        // a verified file that has since vanished or changed size is not verified
        if (spec != null && await sizeMatches(fileFor(spec), spec)) out.add(p);
      }
      return out;
    } catch (_) {
      return {}; // unreadable progress = start the checks again, never trust it
    }
  }

  Future<void> saveVerified(Set<String> paths) async {
    await dir.create(recursive: true);
    final tmp = File('${dir.path}/$progressFile.tmp');
    await tmp.writeAsString(jsonEncode(paths.toList()..sort()), flush: true);
    await tmp.rename('${dir.path}/$progressFile');
  }

  Future<void> markComplete() async =>
      File('${dir.path}/$completeMarker').writeAsString(DateTime.now().toIso8601String(), flush: true);

  Future<void> delete() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  }
}

Future<bool> sizeMatches(File f, BundleFile spec) async {
  if (!await f.exists()) return false;
  return spec.size <= 0 || await f.length() == spec.size;
}

/// Checks a downloaded file against its listing. Returns null when it is whole,
/// or a short reason. Hashing runs on another isolate (hundreds of MB).
Future<String?> verifyFile(File f, BundleFile spec) async {
  if (!await f.exists()) return 'missing';
  final len = await f.length();
  if (spec.size > 0 && len != spec.size) return 'size $len, expected ${spec.size}';
  final want256 = spec.sha256?.toLowerCase();
  final wantGit = spec.gitSha1?.toLowerCase();
  if (want256 == null && wantGit == null) return null; // size is all the server gave us
  final path = f.path;
  final got = await Isolate.run(() => _hashFile(path, gitBlob: want256 == null));
  final want = want256 ?? wantGit!;
  return got == want ? null : 'checksum mismatch';
}

/// SHA-256 of the file, or (gitBlob) the git blob SHA-1: `sha1("blob <len>\0" + bytes)`.
Future<String> _hashFile(String path, {required bool gitBlob}) async {
  final f = File(path);
  final out = _DigestSink();
  final ByteConversionSink sink;
  if (gitBlob) {
    sink = sha1.startChunkedConversion(out);
    sink.add(utf8.encode('blob ${await f.length()}\u0000'));
  } else {
    sink = sha256.startChunkedConversion(out);
  }
  await for (final chunk in f.openRead()) {
    sink.add(chunk);
  }
  sink.close();
  return out.value.toString();
}

class _DigestSink implements Sink<Digest> {
  late Digest value;
  @override
  void add(Digest data) => value = data;
  @override
  void close() {}
}

/// Unpacks [archive] (tar.bz2) into [dir], writing only [wanted] paths (each
/// through a temp file, then renamed). Returns the paths written. Runs on
/// another isolate: bzip2 in pure Dart takes a moment.
Future<List<String>> unpackTarBz2(String archive, String dir, Set<String> wanted) =>
    Isolate.run(() => _unpack(archive, dir, wanted));

Future<List<String>> _unpack(String archive, String dir, Set<String> wanted) async {
  final tar = BZip2Decoder().decodeBytes(await File(archive).readAsBytes());
  final out = <String>[];
  for (final e in TarDecoder().decodeBytes(tar)) {
    final name = e.name.startsWith('./') ? e.name.substring(2) : e.name;
    if (!e.isFile || !wanted.contains(name) || name.contains('..')) continue;
    final f = File('$dir/$name');
    await f.parent.create(recursive: true);
    final tmp = File('${f.path}.unpack');
    await tmp.writeAsBytes(e.content, flush: true);
    await tmp.rename(f.path);
    out.add(name);
  }
  return out;
}

/// Hex SHA-256 / git-blob SHA-1 of bytes (for tests and small checks).
String sha256Hex(List<int> bytes) => sha256.convert(bytes).toString();
String gitBlobSha1Hex(List<int> bytes) => sha1.convert([...utf8.encode('blob ${bytes.length}\u0000'), ...bytes]).toString();

/// Sizes as Android's own storage screen shows them (decimal: 1 MB = 1,000,000 bytes).
String mb(int bytes) => bytes >= 1000000000
    ? '${(bytes / 1e9).toStringAsFixed(1)} GB'
    : '${(bytes / 1e6).round()} MB';
