/// Downloads a [Bundle] so that it survives the real world: dropped Wi-Fi,
/// Wi-Fi/mobile handovers, the screen going off, the app going to the
/// background or being closed.
///
/// The transfers are done by `background_downloader` (Android: WorkManager
/// work, as a foreground service with a progress notification for big files):
/// - every file is resumable (HTTP Range + a strong ETag, which Hugging Face's
///   CDN serves); a partial file is KEPT on failure, pause and app restarts;
/// - each file is retried up to [retries] times with exponential backoff
///   (2 s, 4 s, ... 512 s), and a file that fails while the phone is offline
///   waits for the network without spending a retry;
/// - every finished file is checked (size + SHA-256 / git SHA-1) before it
///   counts; the bundle is marked installed only when every file passed.
///
/// One instance per bundle ([forBundle]): the downloader's callbacks are per
/// group, and a second instance would steal them.
library;

import 'dart:async';
import 'dart:collection';
import 'dart:io';

import 'package:background_downloader/background_downloader.dart';
import 'package:flutter/foundation.dart';

import 'bundle.dart';

enum DlPhase { idle, starting, downloading, waitingForNetwork, verifying, paused, installed, failed }

@immutable
class DlStatus {
  const DlStatus(this.phase, {this.done = 0, this.total = 0, this.error, this.integrity = false});
  final DlPhase phase;
  final int done; // bytes
  final int total; // bytes
  final String? error; // for the log; the UI words its own message
  final bool integrity; // failed because a file did not match its checksum

  double get fraction => total <= 0 ? 0 : (done / total).clamp(0.0, 1.0).toDouble();
  bool get busy => const {DlPhase.starting, DlPhase.downloading, DlPhase.waitingForNetwork, DlPhase.verifying}.contains(phase);
  bool get resumable => phase == DlPhase.paused || phase == DlPhase.failed;

  @override
  String toString() => 'DlStatus($phase ${(fraction * 100).round()}% ${error ?? ''})';
}

class BundleDownloader {
  BundleDownloader(this.bundle,
      {FileDownloader? downloader,
      this.smallConcurrency = 4,
      this.retries = 10,
      this.bigFileBytes = 20 << 20,
      this.maxIntegrityRetries = 1,
      this.maxStopRetries = 3,
      this.archiveMinFiles = 10})
      : _dl = downloader ?? FileDownloader();

  static final _instances = <String, BundleDownloader>{};

  /// The one downloader for this bundle id (created on first use).
  static BundleDownloader forBundle(Bundle b, {FileDownloader? downloader}) =>
      _instances.putIfAbsent(b.id, () => BundleDownloader(b, downloader: downloader));

  final Bundle bundle;
  final FileDownloader _dl;
  final int smallConcurrency;
  final int retries; // per file, the downloader's maximum is 10
  final int bigFileBytes; // at or above: started at once, own notification, foreground service
  final int maxIntegrityRetries; // re-downloads of a file that failed its checksum
  final int maxStopRetries; // a file stopped by Android (WorkManager) is started again this often
  final int archiveMinFiles; // an archive is used when at least this many of its files are missing

  final _archiveFor = <String, BundleArchive>{}; // taskId -> archive being fetched
  final _covered = <String, List<BundleFile>>{}; // archive id -> the files it should bring
  final _stops = <String, int>{}; // path -> times Android stopped it this run

  final _events = StreamController<DlStatus>.broadcast();
  DlStatus _cur = const DlStatus(DlPhase.idle);
  Set<String> _verified = {};
  final _queue = Queue<BundleFile>();
  final _inFlight = <String, BundleFile>{}; // taskId -> file: enqueued, running or waiting to retry
  final _bytes = <String, int>{}; // taskId -> bytes so far
  final _waiting = <String>{}; // taskIds waiting to retry
  final _integrityFails = <String, int>{};
  bool _run = false; // a run is in progress
  bool _halted = false; // the last run ended paused/failed: tasks that start by themselves are paused again
  bool _registered = false;
  bool _tracked = false;
  Future<void> _lock = Future.value();
  Completer<DlStatus>? _finished;
  Timer? _emitTimer;

  Stream<DlStatus> get status => _events.stream;
  DlStatus get current => _cur;
  String get _bigGroup => bundle.id;
  String get _smallGroup => '${bundle.id}_small';
  bool _isBig(BundleFile f) => f.size >= bigFileBytes;
  String taskIdFor(BundleFile f) => '${bundle.id}:${f.path}';
  Iterable<String> _allIds() => [...bundle.files, for (final a in bundle.archives) a.asFile].map(taskIdFor);

  DownloadTask taskFor(BundleFile f) {
    final slash = f.path.lastIndexOf('/');
    return DownloadTask(
      taskId: taskIdFor(f),
      url: f.url,
      filename: f.path.substring(slash + 1),
      directory: slash < 0 ? bundle.folder : '${bundle.folder}/${f.path.substring(0, slash)}',
      baseDirectory: BaseDirectory.applicationSupport,
      group: _isBig(f) ? _bigGroup : _smallGroup,
      updates: Updates.statusAndProgress,
      retries: retries,
      allowPause: true,
      requiresWiFi: false, // the owner's call: mobile data is fine (the UI shows the size)
      displayName: mb(f.size),
    );
  }

  /// Bytes still to fetch (for the free-space check); files already proven whole are not counted.
  Future<int> remainingBytes() async {
    final v = await bundle.verifiedPaths();
    return bundle.files.where((f) => !v.contains(f.path)).fold<int>(0, (a, f) => a + f.size);
  }

  /// True when a big file of this bundle is still being fetched by the OS
  /// (e.g. Spike was closed mid-download; the work carried on without it).
  Future<bool> runningInBackground() async {
    for (final f in bundle.files.where(_isBig)) {
      if (await _dl.taskForId(taskIdFor(f)) != null) return true;
    }
    return false;
  }

  /// Starts, or carries on from where it stopped. Completes when the bundle is
  /// installed, paused, failed or cancelled.
  Future<DlStatus> start() {
    final running = _finished;
    if (running != null && !running.isCompleted) return running.future;
    final c = _finished = Completer<DlStatus>();
    _run = true;
    _halted = false;
    _queue.clear();
    _inFlight.clear();
    _bytes.clear();
    _waiting.clear();
    _integrityFails.clear();
    _archiveFor.clear();
    _covered.clear();
    _stops.clear();
    _set(DlPhase.starting);
    _serial(_begin);
    return c.future;
  }

  Future<void> pause() async {
    if (!_run) return;
    _serial(() async {
      await _halt();
      _finish(DlStatus(DlPhase.paused, done: _done(), total: bundle.totalBytes));
    });
    await _lock;
  }

  /// Stops and deletes everything downloaded so far (partial data too).
  Future<void> cancel() async {
    _run = false;
    _halted = false;
    final ids = _allIds().toList();
    _queue.clear();
    _inFlight.clear();
    _bytes.clear();
    _waiting.clear();
    try {
      await _dl.cancelTasksWithIds(ids);
    } catch (e) {
      debugPrint('download ${bundle.id}: cancel $e');
    }
    await bundle.delete();
    await _forgetRecords();
    _finish(const DlStatus(DlPhase.idle));
  }

  void dispose() {
    _emitTimer?.cancel();
    if (_registered) _dl.unregisterCallbacks(group: _bigGroup);
    if (_registered) _dl.unregisterCallbacks(group: _smallGroup);
    _registered = false;
    _instances.remove(bundle.id);
  }

  // ------------------------------------------------------------------ the run

  void _serial(Future<void> Function() job) {
    _lock = _lock.then((_) => job()).catchError((Object e, StackTrace st) {
      debugPrint('download ${bundle.id}: $e\n$st');
      if (_run) _finish(DlStatus(DlPhase.failed, done: _done(), total: bundle.totalBytes, error: '$e'));
    });
  }

  void _register() {
    if (_registered) return;
    _registered = true;
    _dl.configureNotificationForGroup(
      _bigGroup,
      running: TaskNotification('Downloading ${bundle.title}…', '{progress} of {displayName}'),
      paused: TaskNotification('${bundle.title}: paused', 'Open Spike and press Resume'),
      error: TaskNotification('${bundle.title}: stopped', 'Open Spike and press Resume: it carries on where it stopped'),
      progressBar: true,
    );
    for (final g in [_bigGroup, _smallGroup]) {
      _dl.registerCallbacks(group: g, taskStatusCallback: _onStatus, taskProgressCallback: _onProgress);
    }
  }

  Future<void> _begin() async {
    _register();
    if (!_tracked) {
      // records of each task's last status, kept across app restarts: tells a
      // paused task (resume it) from one the OS is still running (follow it)
      for (final g in [_bigGroup, _smallGroup]) {
        await _dl.trackTasksInGroup(g, markDownloadedComplete: false);
      }
      _tracked = true;
    }
    await configureOnce(_dl);
    await bundle.dir.create(recursive: true);
    try {
      await _dl.resumeFromBackground(); // status/resume data the OS delivered while Spike was closed
    } catch (_) {}
    _verified = await bundle.verifiedPaths();
    final fresh = <BundleFile>[];
    for (final f in bundle.files) {
      if (!_run) return;
      if (_verified.contains(f.path)) continue;
      final id = taskIdFor(f);
      if (await _dl.taskForId(id) != null && (await _dl.database.recordForId(id))?.status != TaskStatus.paused) {
        _inFlight[id] = f; // still running (or about to retry) from before: just follow it
        continue;
      }
      final file = bundle.fileFor(f);
      if (await file.exists()) {
        // finished while Spike was closed (or an older download): prove it
        if (await sizeMatches(file, f) && await verifyFile(file, f) == null) {
          _verified.add(f.path);
          continue;
        }
        await _deleteQuietly(file);
      }
      if (await _dl.resume(taskFor(f))) {
        _inFlight[id] = f; // carries on from its partial data
        _bytes[id] = 0;
        continue;
      }
      fresh.add(f);
    }
    await bundle.saveVerified(_verified);
    for (final a in bundle.archives) {
      if (!_run) return;
      await _useArchive(a, fresh);
    }
    fresh.sort((a, b) => b.size.compareTo(a.size)); // big ones first: they run on their own
    _queue.addAll(fresh);
    _set(DlPhase.downloading);
    await _pump();
    await _checkDone();
  }

  /// When many of [a]'s files are still missing, take them out of [fresh] and
  /// fetch (or reuse) the one archive instead.
  Future<void> _useArchive(BundleArchive a, List<BundleFile> fresh) async {
    final covered = fresh.where((f) => f.path.startsWith(a.prefix)).toList();
    final af = a.asFile;
    final id = taskIdFor(af);
    if (covered.length < archiveMinFiles) {
      await _deleteQuietly(bundle.fileFor(af));
      return;
    }
    fresh.removeWhere(covered.contains);
    _covered[a.id] = covered;
    final file = bundle.fileFor(af);
    if (await file.exists() && await verifyFile(file, af) == null) {
      await _archiveLanded(a, fresh); // fetched before, not unpacked yet
      return;
    }
    await _deleteQuietly(file);
    _archiveFor[id] = a;
    if (await _dl.taskForId(id) != null && (await _dl.database.recordForId(id))?.status != TaskStatus.paused) {
      _inFlight[id] = af; // still running from before
      return;
    }
    if (await _dl.resume(taskFor(af))) {
      _inFlight[id] = af;
      _bytes[id] = 0;
      return;
    }
    await _enqueue(af);
  }

  /// The archive is on disk and whole (or not): unpack what is missing and
  /// check every file on its own; anything it could not provide goes to
  /// [into] (default: the front of the queue) to be fetched one by one.
  Future<void> _archiveLanded(BundleArchive a, [List<BundleFile>? into]) async {
    final covered = _covered.remove(a.id) ?? const <BundleFile>[];
    final file = bundle.fileFor(a.asFile);
    final left = <BundleFile>[];
    final problem = await verifyFile(file, a.asFile);
    if (problem != null) {
      debugPrint('download ${bundle.id}: archive ${a.id} not usable ($problem): fetching its files one by one');
      left.addAll(covered);
    } else {
      _set(DlPhase.verifying);
      try {
        await unpackTarBz2(file.path, bundle.dir.path, covered.map((f) => f.path).toSet());
      } catch (e) {
        debugPrint('download ${bundle.id}: archive ${a.id} did not unpack ($e)');
      }
      for (final f in covered) {
        if (await verifyFile(bundle.fileFor(f), f) == null) {
          _verified.add(f.path);
        } else {
          await _deleteQuietly(bundle.fileFor(f));
          left.add(f);
        }
      }
      await bundle.saveVerified(_verified);
      debugPrint('download ${bundle.id}: archive ${a.id} gave ${covered.length - left.length}/${covered.length} files');
    }
    await _deleteQuietly(file);
    if (into != null) {
      into.addAll(left);
    } else {
      for (final f in left) {
        _queue.addFirst(f);
      }
    }
    if (_cur.phase == DlPhase.verifying) _set(DlPhase.downloading);
  }

  Future<void> _pump() async {
    if (!_run) return;
    for (final f in _queue.where(_isBig).toList()) {
      _queue.remove(f);
      await _enqueue(f);
    }
    while (_run && _queue.isNotEmpty && _inFlight.values.where((f) => !_isBig(f)).length < smallConcurrency) {
      await _enqueue(_queue.removeFirst());
    }
  }

  Future<void> _enqueue(BundleFile f) async {
    final id = taskIdFor(f);
    _inFlight[id] = f;
    _bytes[id] = 0;
    if (!await _dl.enqueue(taskFor(f))) {
      _inFlight.remove(id);
      throw StateError('could not start ${f.path}');
    }
  }

  void _onProgress(TaskProgressUpdate u) {
    final f = _inFlight[u.task.taskId];
    if (f == null || u.progress < 0 || u.progress > 1) return;
    final a = _archiveFor[u.task.taskId];
    final size = a == null ? f.size : (_covered[a.id] ?? const <BundleFile>[]).fold<int>(0, (s, x) => s + x.size);
    _bytes[u.task.taskId] = (u.progress * size).round();
    _emitSoon();
  }

  void _onStatus(TaskStatusUpdate u) => _serial(() => _handle(u));

  Future<void> _handle(TaskStatusUpdate u) async {
    final id = u.task.taskId;
    if (!_run) {
      // a paused/failed run: a task the library retried by itself is paused again
      if (_halted && u.status == TaskStatus.running && u.task is DownloadTask) {
        unawaited(_dl.pause(u.task as DownloadTask));
      }
      return;
    }
    final f = _inFlight[id];
    if (f == null) return;
    final archive = _archiveFor[id];
    if (archive != null && u.status.isFinalState) {
      // the archive is only a shortcut: whatever happened, its files still arrive
      _inFlight.remove(id);
      _waiting.remove(id);
      _archiveFor.remove(id);
      _bytes.remove(id);
      if (u.status != TaskStatus.complete) {
        debugPrint('download ${bundle.id}: archive ${archive.id} ${u.status.name}: fetching its files one by one');
        await _deleteQuietly(bundle.fileFor(f));
      }
      await _archiveLanded(archive);
      await _pump();
      await _checkDone();
      return;
    }
    switch (u.status) {
      case TaskStatus.enqueued || TaskStatus.running:
        _waiting.remove(id);
        _emit();
      case TaskStatus.waitingToRetry:
        _waiting.add(id); // its partial data is kept: the retry resumes from there
        _emit();
      case TaskStatus.complete:
        _inFlight.remove(id);
        _waiting.remove(id);
        _bytes[id] = f.size;
        if (_isBig(f)) _set(DlPhase.verifying);
        final file = bundle.fileFor(f);
        final problem = await verifyFile(file, f);
        _bytes.remove(id);
        if (problem == null) {
          _verified.add(f.path);
          await bundle.saveVerified(_verified);
        } else {
          // only THIS file is fetched again; everything already checked stays
          debugPrint('download ${bundle.id}: ${f.path} failed its check ($problem)');
          await _deleteQuietly(file);
          final n = _integrityFails[f.path] = (_integrityFails[f.path] ?? 0) + 1;
          if (n > maxIntegrityRetries) {
            await _halt();
            _finish(DlStatus(DlPhase.failed, done: _done(), total: bundle.totalBytes, error: '${f.path}: $problem', integrity: true));
            return;
          }
          _queue.addFirst(f);
        }
        if (_cur.phase == DlPhase.verifying) _set(DlPhase.downloading);
        await _pump();
        await _checkDone();
      case TaskStatus.paused:
        // paused from the notification: the whole bundle pauses
        _inFlight.remove(id);
        await _halt();
        _finish(DlStatus(DlPhase.paused, done: _done(), total: bundle.totalBytes));
      case TaskStatus.failed || TaskStatus.notFound:
        _inFlight.remove(id);
        _bytes.remove(id);
        await _halt();
        final why = u.status == TaskStatus.notFound ? 'not found: ${f.path}' : (u.exception?.description ?? 'failed');
        _finish(DlStatus(DlPhase.failed, done: _done(), total: bundle.totalBytes, error: why));
      case TaskStatus.canceled:
        // NOT the owner: his Cancel is the app's button (cancel() stops the run
        // first, so its own cancellations never reach here). This is Android
        // stopping the WorkManager job (onStopJob: constraints, quota, the
        // system), or the notification's cancel action. It used to delete the
        // whole bundle - every verified file - which is how a download at 95%
        // started again from zero (phone log 30 Sep 08:31:33). Now: start that
        // one file again; if Android keeps stopping it, pause and keep it all.
        _inFlight.remove(id);
        _waiting.remove(id);
        _bytes.remove(id);
        final n = _stops[f.path] = (_stops[f.path] ?? 0) + 1;
        debugPrint('download ${bundle.id}: ${f.path} was stopped by Android ($n)');
        if (n > maxStopRetries) {
          await _halt();
          _finish(DlStatus(DlPhase.paused, done: _done(), total: bundle.totalBytes));
          return;
        }
        _queue.addFirst(f);
        await _pump();
    }
  }
  /// Stops the run but keeps every byte: running big files are paused (their
  /// partial data is kept for resume), small ones not yet done are dropped.
  Future<void> _halt() async {
    _run = false;
    _halted = true;
    final flights = Map.of(_inFlight);
    _inFlight.clear();
    _queue.clear();
    for (final MapEntry(key: id, value: f) in flights.entries) {
      final paused = await _dl.pause(taskFor(f)).catchError((_) => false);
      // a big file that is only queued or waiting to retry keeps its resume data:
      // it is paused as soon as it runs (see _handle); small files are cheap to redo
      if (!paused && !_isBig(f)) await _dl.cancelTaskWithId(id).catchError((_) => false);
    }
  }

  Future<void> _checkDone() async {
    if (!_run || _inFlight.isNotEmpty || _queue.isNotEmpty) return;
    if (!bundle.files.every((f) => _verified.contains(f.path))) return;
    await bundle.markComplete();
    await _forgetRecords();
    _run = false;
    _finish(DlStatus(DlPhase.installed, done: bundle.totalBytes, total: bundle.totalBytes));
  }

  // ------------------------------------------------------------------ status

  int _done() {
    var d = 0;
    for (final f in bundle.files) {
      if (_verified.contains(f.path)) d += f.size;
    }
    for (final b in _bytes.values) {
      d += b;
    }
    return d;
  }

  void _set(DlPhase p) {
    _cur = DlStatus(p, done: _done(), total: bundle.totalBytes);
    if (!_events.isClosed) _events.add(_cur);
  }

  void _emit() {
    if (!_run) return;
    final offline = _inFlight.isNotEmpty && _inFlight.keys.every(_waiting.contains) && _queue.isEmpty;
    final p = _cur.phase == DlPhase.verifying ? DlPhase.verifying : (offline ? DlPhase.waitingForNetwork : DlPhase.downloading);
    _set(p);
  }

  void _emitSoon() {
    if (_emitTimer?.isActive ?? false) return;
    _emitTimer = Timer(const Duration(milliseconds: 250), _emit);
  }

  void _finish(DlStatus s) {
    _run = false;
    _emitTimer?.cancel();
    _cur = s;
    if (!_events.isClosed) _events.add(s);
    final c = _finished;
    if (c != null && !c.isCompleted) c.complete(s);
  }

  /// The downloader's per-task status records are only needed while a download is unfinished.
  Future<void> _forgetRecords() async {
    try {
      await _dl.database.deleteRecordsWithIds(_allIds());
    } catch (_) {}
  }

  static Future<void> _deleteQuietly(File f) async {
    try {
      if (await f.exists()) await f.delete();
    } catch (_) {}
  }

  static bool _configured = false;

  /// Android: big files run as a foreground service (no 9-minute limit, a
  /// progress notification), and partial files live in the cache folder, where
  /// flutter_gemma's start-up sweep of stray download temp files (it cleans
  /// the app-support folder) cannot delete them.
  static Future<void> configureOnce(FileDownloader dl) async {
    if (_configured || !Platform.isAndroid) return;
    _configured = true;
    try {
      await dl.configure(androidConfig: [
        (Config.runInForegroundIfFileLargerThan, 20),
        (Config.useCacheDir, Config.always),
      ]);
    } catch (e) {
      debugPrint('download: configure $e');
    }
  }
}

/// What to tell the owner when a download stopped.
String downloadProblem(DlStatus s) {
  if (s.integrity) return 'The download arrived damaged, so it was thrown away. Press Resume to fetch it again.';
  if (s.error?.startsWith('not found') ?? false) return 'The file is no longer on Hugging Face: Spike needs an app update.';
  return 'The download stopped (no internet for too long). Press Resume: it carries on where it stopped.';
}
