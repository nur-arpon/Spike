// The resumable downloader against a fake file server: our BundleDownloader and
// background_downloader's real Dart layer (retries, backoff, pause/resume data),
// with a fake Android side (support/fake_bg_native.dart) doing the HTTP.
import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:archive/archive.dart' show Archive, ArchiveFile, BZip2Encoder, TarEncoder;
import 'package:background_downloader/background_downloader.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:spike_app/away/download/bundle.dart';
import 'package:spike_app/away/download/bundle_downloader.dart';
import 'package:spike_app/away/download/downloads.dart';
import 'package:spike_app/away/voice/speaker.dart';

import 'support/fake_bg_native.dart';

class _MemStorage implements PersistentStorage {
  final records = <String, TaskRecord>{};
  final resumeData = <String, ResumeData>{};
  final paused = <String, Task>{};
  @override
  Future<void> initialize() async {}
  @override
  (String, int) get currentDatabaseVersion => ('', 0);
  @override
  Future<(String, int)> get storedDatabaseVersion async => ('', 0);
  @override
  Future<void> storeTaskRecord(TaskRecord r) async => records[r.taskId] = r;
  @override
  Future<TaskRecord?> retrieveTaskRecord(String id) async => records[id];
  @override
  Future<List<TaskRecord>> retrieveAllTaskRecords() async => records.values.toList();
  @override
  Future<void> removeTaskRecord(String? id) async => id == null ? records.clear() : records.remove(id);
  @override
  Future<void> storePausedTask(Task t) async => paused[t.taskId] = t;
  @override
  Future<Task?> retrievePausedTask(String id) async => paused[id];
  @override
  Future<List<Task>> retrieveAllPausedTasks() async => paused.values.toList();
  @override
  Future<void> removePausedTask(String? id) async => id == null ? paused.clear() : paused.remove(id);
  @override
  Future<void> storeResumeData(ResumeData d) async => resumeData[d.taskId] = d;
  @override
  Future<ResumeData?> retrieveResumeData(String id) async => resumeData[id];
  @override
  Future<List<ResumeData>> retrieveAllResumeData() async => resumeData.values.toList();
  @override
  Future<void> removeResumeData(String? id) async => id == null ? resumeData.clear() : resumeData.remove(id);
}

/// Serves byte blobs with Range support and a strong ETag, like Hugging Face's CDN.
class _FakeServer {
  late HttpServer _s;
  final files = <String, List<int>>{};
  final dropAfter = <String, int>{}; // cut the connection after N bytes, once
  final requests = <String>[]; // "name range"
  final tooMany = <String, int>{}; // answer HTTP 429 this many times first (Hugging Face rate limit)
  Duration chunkDelay = Duration.zero;

  String url(String name) => 'http://127.0.0.1:${_s.port}/$name';

  Future<void> start() async {
    _s = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    _s.listen(_serve);
  }

  Future<void> _serve(HttpRequest req) async {
    final name = req.uri.pathSegments.join('/');
    final range = req.headers.value('range');
    requests.add('$name ${range ?? '-'}');
    final data = files[name];
    final res = req.response;
    final busy = tooMany[name] ?? 0;
    if (busy > 0) {
      tooMany[name] = busy - 1;
      res.statusCode = 429;
      await res.close();
      return;
    }
    if (data == null) {
      res.statusCode = 404;
      await res.close();
      return;
    }
    var start = 0;
    final m = range == null ? null : RegExp(r'bytes=(\d+)-').firstMatch(range);
    if (m != null) start = int.parse(m.group(1)!);
    res.statusCode = m == null ? 200 : 206;
    res.headers.set('etag', '"${sha256Hex(data).substring(0, 16)}"');
    res.headers.set('accept-ranges', 'bytes');
    res.headers.contentType = ContentType.binary;
    res.contentLength = data.length - start;
    if (m != null) res.headers.set('content-range', 'bytes $start-${data.length - 1}/${data.length}');
    final cut = dropAfter.remove(name);
    if (cut != null) {
      // write the response by hand on the raw socket, then cut it mid-file
      final socket = await res.detachSocket(writeHeaders: false);
      final etag = sha256Hex(data).substring(0, 16);
      final status = m == null ? '200 OK' : '206 Partial Content';
      socket.write('HTTP/1.1 $status\r\ncontent-length: ${data.length - start}\r\netag: "$etag"\r\n'
          'accept-ranges: bytes\r\ncontent-type: application/octet-stream\r\n\r\n');
      socket.add(data.sublist(start, start + cut));
      await socket.flush();
      socket.destroy();
      return;
    }
    var pos = start;
    try {
      while (pos < data.length) {
        final end = min(pos + 65536, data.length);
        res.add(data.sublist(pos, end));
        await res.flush();
        pos = end;
        if (chunkDelay > Duration.zero) await Future<void>.delayed(chunkDelay);
      }
      await res.close();
    } catch (_) {
      // the client went away (pause)
    }
  }

  Future<void> close() => _s.close(force: true);
}

List<int> _bytes(int n, int seed) {
  final r = Random(seed);
  return List<int>.generate(n, (_) => r.nextInt(256));
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  HttpOverrides.global = null; // the test binding answers every HTTP request with 400; we talk to a real local server
  late Directory tmp;
  late _FakeServer server;
  late FakeBgNative native;
  final storage = _MemStorage();

  setUpAll(() async {
    tmp = await Directory.systemTemp.createTemp('spike_dl_test');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    messenger.setMockMethodCallHandler(const MethodChannel('plugins.flutter.io/path_provider'), (call) async {
      final sub = call.method == 'getTemporaryDirectory' ? 'temp' : 'support';
      final d = Directory('${tmp.path}/$sub');
      await d.create(recursive: true);
      return d.path;
    });
    messenger.setMockMethodCallHandler(const MethodChannel('dev.fluttercommunity.plus/connectivity'), (call) async => ['wifi']);
    native = FakeBgNative(Directory('${tmp.path}/cache')..createSync(recursive: true))..install();
    FileDownloader(persistentStorage: storage);
    server = _FakeServer();
    await server.start();
  });

  tearDownAll(() async {
    await server.close();
    FileDownloader().destroy();
    native.close();
    try {
      await tmp.delete(recursive: true);
    } catch (_) {}
  });

  Bundle bundleOf(String id, List<BundleFile> files) =>
      Bundle(id: id, root: Directory('${tmp.path}/support'), folder: id, files: files, title: 'Test');

  test('a dropped connection is retried and resumes from the partial data', () async {
    final data = _bytes(3 << 20, 1);
    server.files['drop.bin'] = data;
    server.dropAfter['drop.bin'] = 1600 * 1024;
    final b = bundleOf('t_drop', [BundleFile(url: server.url('drop.bin'), path: 'drop.bin', size: data.length, sha256: sha256Hex(data))]);
    final dl = BundleDownloader(b);
    final s = await dl.start().timeout(const Duration(seconds: 60));
    dl.dispose();

    expect(s.phase, DlPhase.installed, reason: '$s');
    expect(await File('${b.dir.path}/drop.bin').readAsBytes(), data);
    expect(b.isComplete, isTrue);
    final ranged = server.requests.where((r) => r.startsWith('drop.bin bytes=')).toList();
    expect(ranged, isNotEmpty, reason: 'the retry must ask only for the missing part: ${server.requests}');
    final from = int.parse(RegExp(r'bytes=(\d+)-').firstMatch(ranged.first)!.group(1)!);
    expect(from, greaterThan(1 << 20));
  });

  test('a paused download resumes from its partial file after a restart', () async {
    final data = _bytes(4 << 20, 2);
    server.files['pause.bin'] = data;
    server.chunkDelay = const Duration(milliseconds: 15);
    final b = bundleOf('t_pause', [BundleFile(url: server.url('pause.bin'), path: 'pause.bin', size: data.length, sha256: sha256Hex(data))]);
    final first = BundleDownloader(b);
    final halfway = Completer<void>();
    final sub = first.status.listen((s) {
      if (s.fraction > 0.35 && !halfway.isCompleted) halfway.complete();
    });
    final run = first.start();
    await halfway.future.timeout(const Duration(seconds: 30));
    await first.pause();
    final paused = await run.timeout(const Duration(seconds: 10));
    await sub.cancel();
    first.dispose(); // the app goes away
    expect(paused.phase, DlPhase.paused);
    expect(b.isComplete, isFalse);
    await Future<void>.delayed(const Duration(milliseconds: 500)); // the pause settles, resume data is stored

    server.chunkDelay = Duration.zero;
    final second = BundleDownloader(b); // a fresh start of the app
    final s = await second.start().timeout(const Duration(seconds: 60));
    second.dispose();

    expect(s.phase, DlPhase.installed, reason: '$s');
    expect(await File('${b.dir.path}/pause.bin').readAsBytes(), data);
    final ranged = server.requests.where((r) => r.startsWith('pause.bin bytes=')).toList();
    expect(ranged, isNotEmpty, reason: 'the second run must continue, not restart: ${server.requests}');
    final from = int.parse(RegExp(r'bytes=(\d+)-').firstMatch(ranged.last)!.group(1)!);
    expect(from, greaterThan(1 << 20));
  });

  test('cancel stops the download and deletes the partial data', () async {
    final data = _bytes(4 << 20, 5);
    server.files['cancel.bin'] = data;
    server.chunkDelay = const Duration(milliseconds: 15);
    final b = bundleOf('t_cancel', [BundleFile(url: server.url('cancel.bin'), path: 'cancel.bin', size: data.length, sha256: sha256Hex(data))]);
    final dl = BundleDownloader(b);
    final started = Completer<void>();
    final sub = dl.status.listen((s) {
      if (s.fraction > 0.2 && !started.isCompleted) started.complete();
    });
    final run = dl.start();
    await started.future.timeout(const Duration(seconds: 30));
    await dl.cancel();
    final s = await run.timeout(const Duration(seconds: 10));
    await sub.cancel();
    server.chunkDelay = Duration.zero;
    dl.dispose();
    expect(s.phase, DlPhase.idle);
    expect(await b.dir.exists(), isFalse);
    expect(await storage.retrieveResumeData(dl.taskIdFor(b.files.single)), isNull);
  });

  test('a file that fails its checksum is fetched again, then refused; never marked installed', () async {
    final data = _bytes(64 * 1024, 3);
    server.files['bad.bin'] = data;
    final b = bundleOf('t_bad', [BundleFile(url: server.url('bad.bin'), path: 'bad.bin', size: data.length, sha256: sha256Hex([1, 2, 3]))]);
    final dl = BundleDownloader(b);
    final s = await dl.start().timeout(const Duration(seconds: 30));
    dl.dispose();

    expect(s.phase, DlPhase.failed);
    expect(s.integrity, isTrue);
    expect(b.isComplete, isFalse);
    expect(await File('${b.dir.path}/bad.bin').exists(), isFalse, reason: 'a damaged file is not kept');
    expect(server.requests.where((r) => r.startsWith('bad.bin')).length, 2, reason: 'one re-download, then give up');
  });

  test('a short file (size mismatch) is never marked installed', () async {
    final data = _bytes(10 * 1024, 4);
    server.files['short.bin'] = data;
    final b = bundleOf('t_short', [BundleFile(url: server.url('short.bin'), path: 'short.bin', size: data.length + 5)]);
    final dl = BundleDownloader(b);
    final s = await dl.start().timeout(const Duration(seconds: 30));
    dl.dispose();
    expect(s.phase, DlPhase.failed);
    expect(b.isComplete, isFalse);
  });

  test('many small files in folders: git hashes checked, finished files are not fetched again', () async {
    final files = <BundleFile>[];
    for (var i = 0; i < 9; i++) {
      final d = _bytes(1000 + i * 37, 10 + i);
      final name = 'small/d${i % 3}/f$i';
      server.files[name] = d;
      files.add(BundleFile(url: server.url(name), path: name, size: d.length, gitSha1: gitBlobSha1Hex(d)));
    }
    final b = bundleOf('t_small', files);
    final dl = BundleDownloader(b, smallConcurrency: 3);
    expect((await dl.start().timeout(const Duration(seconds: 30))).phase, DlPhase.installed);
    for (final f in files) {
      expect(await File('${b.dir.path}/${f.path}').readAsBytes(), server.files[f.path]);
    }
    final before = server.requests.length;
    await File('${b.dir.path}/${Bundle.completeMarker}').delete(); // e.g. killed just before the marker
    expect((await dl.start().timeout(const Duration(seconds: 30))).phase, DlPhase.installed);
    expect(server.requests.length, before, reason: 'verified files are kept');
    dl.dispose();
  });

  // ---- 30 Sep 2026, S23 log: the voice pack dropped at ~95% and began again at zero.
  // Android stopped WorkManager jobs (TaskRunner: "was canceled, ignoring exception: Job was
  // cancelled"); the downloader took TaskStatus.canceled for the owner's Cancel and deleted the
  // whole bundle (08:31:33 "Canceling taskIds [spike_voice:LICENSE, ..."), so model.onnx, already
  // downloaded and checked at 08:28, was fetched again from zero at 08:31:50.
  int hits(String name) => server.requests.where((r) => r.startsWith('$name ')).length;

  test('Android stopping a file never deletes the bundle: checked files stay, only that file is fetched again', () async {
    final big = _bytes(3 << 20, 20);
    final small = _bytes(40 * 1024, 21);
    server.files['stop/model.bin'] = big;
    server.files['stop/tokens.txt'] = small;
    native.systemStopAfter['stop/model.bin'] = 2 << 20; // stopped near the end
    final b = bundleOf('t_stop', [
      BundleFile(url: server.url('stop/model.bin'), path: 'model.bin', size: big.length, sha256: sha256Hex(big)),
      BundleFile(url: server.url('stop/tokens.txt'), path: 'tokens.txt', size: small.length, gitSha1: gitBlobSha1Hex(small)),
    ]);
    final dl = BundleDownloader(b, bigFileBytes: 1 << 20);
    final s = await dl.start().timeout(const Duration(seconds: 60));
    dl.dispose();
    expect(s.phase, DlPhase.installed, reason: '$s');
    expect(b.isComplete, isTrue);
    expect(await File('${b.dir.path}/model.bin').readAsBytes(), big);
    expect(hits('stop/tokens.txt'), 1, reason: 'a checked file is never fetched again');
    expect(hits('stop/model.bin'), 2, reason: 'only the stopped file is started again');
  });

  test('a failure near the end keeps every checked file: Resume fetches only what is missing', () async {
    final files = <BundleFile>[];
    for (var i = 0; i < 6; i++) {
      final d = _bytes(2000 + i, 30 + i);
      server.files['end/f$i'] = d;
      files.add(BundleFile(url: server.url('end/f$i'), path: 'f$i', size: d.length, gitSha1: gitBlobSha1Hex(d)));
    }
    final last = _bytes(5000, 40);
    // not on the server yet: 404 -> the run stops as failed
    files.add(BundleFile(url: server.url('end/last'), path: 'last', size: last.length, gitSha1: gitBlobSha1Hex(last)));
    final b = bundleOf('t_end', files);
    final dl = BundleDownloader(b, smallConcurrency: 1);
    final first = await dl.start().timeout(const Duration(seconds: 30));
    expect(first.phase, DlPhase.failed, reason: '$first');
    expect(await b.dir.exists(), isTrue);
    server.files['end/last'] = last;
    final again = await dl.start().timeout(const Duration(seconds: 30));
    dl.dispose();
    expect(again.phase, DlPhase.installed, reason: '$again');
    for (var i = 0; i < 6; i++) {
      expect(hits('end/f$i'), lessThanOrEqualTo(1), reason: 'f$i was already checked');
    }
  });

  test('HTTP 429 (too many requests) is waited out and retried', () async {
    final d = _bytes(3000, 50);
    server.files['busy/a'] = d;
    server.tooMany['busy/a'] = 1;
    final b = bundleOf('t_429', [BundleFile(url: server.url('busy/a'), path: 'a', size: d.length, gitSha1: gitBlobSha1Hex(d))]);
    final dl = BundleDownloader(b);
    final s = await dl.start().timeout(const Duration(seconds: 30));
    dl.dispose();
    expect(s.phase, DlPhase.installed, reason: '$s');
    expect(hits('busy/a'), 2);
  });

  group('many small files as one archive', () {
    (List<BundleFile>, BundleArchive) setUpArchive(String tag, {bool badArchive = false}) {
      final files = <BundleFile>[];
      final tar = Archive();
      for (var i = 0; i < 12; i++) {
        final d = _bytes(700 + i * 13, 60 + i);
        final p = 'espeak-ng-data/d${i % 2}/x$i';
        server.files['$tag/$p'] = d;
        files.add(BundleFile(url: server.url('$tag/$p'), path: p, size: d.length, gitSha1: gitBlobSha1Hex(d)));
        if (i == 11) continue; // not in the archive at all
        tar.add(ArchiveFile.bytes(p, i == 5 ? _bytes(d.length, 999) : d)); // x5: a different version
      }
      final model = _bytes(9000, 70);
      server.files['$tag/model.onnx'] = model;
      files.add(BundleFile(url: server.url('$tag/model.onnx'), path: 'model.onnx', size: model.length, sha256: sha256Hex(model)));
      final bz = BZip2Encoder().encodeBytes(TarEncoder().encodeBytes(tar));
      server.files['$tag/espeak.tar.bz2'] = bz;
      final a = BundleArchive(
          id: 'espeak',
          url: server.url('$tag/espeak.tar.bz2'),
          size: bz.length,
          sha256: badArchive ? sha256Hex([0]) : sha256Hex(bz),
          prefix: 'espeak-ng-data/');
      return (files, a);
    }

    test('one download for the lot; each file still checked; a mismatch is fetched on its own', () async {
      final (files, a) = setUpArchive('ar1');
      final b = Bundle(id: 't_ar1', root: Directory('${tmp.path}/support'), folder: 't_ar1', files: files, title: 'T', archives: [a]);
      final dl = BundleDownloader(b);
      final s = await dl.start().timeout(const Duration(seconds: 60));
      dl.dispose();
      expect(s.phase, DlPhase.installed, reason: '$s');
      for (final f in files) {
        expect(await File('${b.dir.path}/${f.path}').readAsBytes(), server.files['ar1/${f.path}'], reason: f.path);
      }
      expect(hits('ar1/espeak.tar.bz2'), 1);
      expect(hits('ar1/espeak-ng-data/d1/x5'), 1, reason: 'did not match its own hash');
      expect(hits('ar1/espeak-ng-data/d1/x11'), 1, reason: 'not in the archive');
      expect(hits('ar1/espeak-ng-data/d0/x0') + hits('ar1/espeak-ng-data/d1/x3'), 0, reason: 'came from the archive');
      expect(await File('${b.dir.path}/${a.fileName}').exists(), isFalse, reason: 'the archive is removed after unpacking');
    });

    test('an archive that fails its check falls back to file by file', () async {
      final (files, a) = setUpArchive('ar2', badArchive: true);
      final b = Bundle(id: 't_ar2', root: Directory('${tmp.path}/support'), folder: 't_ar2', files: files, title: 'T', archives: [a]);
      final dl = BundleDownloader(b);
      final s = await dl.start().timeout(const Duration(seconds: 60));
      dl.dispose();
      expect(s.phase, DlPhase.installed, reason: '$s');
      expect(hits('ar2/espeak-ng-data/d0/x0'), 1);
      expect(b.isComplete, isTrue);
    });
  });


  test('git blob hash matches Hugging Face (tokens.txt oid)', () {
    // `git hash-object` of "a\n" is 78981922613b2afb6025042ff6bd878ac1994e85
    expect(gitBlobSha1Hex('a\n'.codeUnits), '78981922613b2afb6025042ff6bd878ac1994e85');
  });

  test('voice file list: each file once (the old listing fetched espeak files twice)', () {
    Map<String, dynamic> f(String p, [bool lfs = false]) => {
          'type': 'file',
          'path': p,
          'size': 10,
          'oid': 'abc',
          if (lfs) 'lfs': {'oid': 'f' * 64, 'size': 10},
        };
    final tree = [
      f('model.onnx', true), f('voices.bin', true), f('tokens.txt'), f('README.md'),
      f('espeak-ng-data/en_dict'), f('espeak-ng-data/voices/!v/Alex'),
      f('espeak-ng-data/en_dict'), f('espeak-ng-data/voices/!v/Alex'), // the overlapping second listing
      {'type': 'directory', 'path': 'espeak-ng-data'},
    ];
    final files = KokoroPack.pickFiles(tree);
    expect(files.map((e) => e.path).toSet().length, files.length);
    expect(files.map((e) => e.path), containsAll(['model.onnx', 'voices.bin', 'tokens.txt', 'espeak-ng-data/en_dict']));
    expect(files.any((e) => e.path == 'README.md'), isFalse);
    final model = files.firstWhere((e) => e.path == 'model.onnx');
    expect(model.sha256, 'f' * 64);
    expect(model.url, contains('/resolve/$kokoroRevision/model.onnx'));
    expect(files.firstWhere((e) => e.path == 'tokens.txt').gitSha1, 'abc');
  });

  test('Link header pagination', () {
    expect(nextLink('<https://huggingface.co/api/x?cursor=abc>; rel="next"'), 'https://huggingface.co/api/x?cursor=abc');
    expect(nextLink(null), isNull);
    expect(nextLink('<https://a>; rel="prev"'), isNull);
  });
}
