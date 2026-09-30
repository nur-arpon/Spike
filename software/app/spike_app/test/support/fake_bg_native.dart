// A stand-in for background_downloader's Android side (DownloadTaskRunner.kt),
// so the package's real Dart layer (queueing, retries with backoff, pause and
// resume bookkeeping) and our BundleDownloader run in a unit test against a
// real HTTP server. It mirrors the native behaviour that matters here:
// - streams into a temp file, moves it to the task's path on success;
// - resumes with `Range: bytes=N-` from the temp file, refusing if the ETag
//   changed or is weak;
// - on failure after more than 1 MB, posts resume data (so a retry resumes);
// - pause posts resume data and the paused status; cancel deletes the temp.
// (The package's own desktop engine can't run in flutter_test: its isolate
// needs BackgroundIsolateBinaryMessenger, which the test shell lacks.)
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:background_downloader/background_downloader.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class _Job {
  _Job(this.taskJson, this.task);
  final String taskJson;
  final DownloadTask task;
  bool pause = false;
  bool cancel = false;
}

class FakeBgNative {
  FakeBgNative(this.tempDir);
  final Directory tempDir;
  final running = <String, _Job>{};

  /// url path -> bytes: Android stops that job once (WorkManager onStopJob), which
  /// the real TaskRunner reports as TaskStatus.canceled ("Job was cancelled").
  final systemStopAfter = <String, int>{};
  final _client = HttpClient();
  var _n = 0;

  static const _channel = MethodChannel('com.bbflight.background_downloader');
  static const _background = 'com.bbflight.background_downloader.background';

  void install() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_channel, _handle);
  }

  Future<Object?> _handle(MethodCall call) async {
    final a = call.arguments;
    switch (call.method) {
      case 'enqueue':
        final args = a as List<dynamic>;
        final json = args[0] as String;
        final task = Task.createFromJson(jsonDecode(json) as Map<String, dynamic>) as DownloadTask;
        final resumePath = args.length > 2 ? args[2] as String? : null;
        final start = args.length > 3 ? (args[3] as num?)?.toInt() ?? 0 : 0;
        final eTag = args.length > 4 ? args[4] as String? : null;
        final job = running[task.taskId] = _Job(json, task);
        unawaited(_run(job, resumePath, start, eTag));
        return true;
      case 'pause':
        final id = a is List ? a.first as String : a as String;
        final job = running[id];
        if (job == null) return false;
        job.pause = true;
        return true;
      case 'cancelTasksWithIds':
        for (final id in (a as List<dynamic>).cast<String>()) {
          running[id]?.cancel = true;
        }
        return true;
      case 'taskForId':
        return running[a as String]?.taskJson;
      case 'allTasks':
        return running.values.map((j) => j.taskJson).toList();
      case 'reset':
        return 0;
      case 'platformVersion':
        return '34';
      case 'popResumeData' || 'popStatusUpdates' || 'popProgressUpdates' || 'popUndeliveredData':
        return '{}';
      default:
        return true;
    }
  }

  Future<void> _post(String method, List<Object?> args) async {
    final data = const StandardMethodCodec().encodeMethodCall(MethodCall(method, args));
    await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .handlePlatformMessage(_background, data, (_) {});
  }

  Future<void> _status(_Job j, TaskStatus s) => _post('statusUpdate', [j.taskJson, s.index]);

  Future<void> _run(_Job j, String? resumePath, int start, String? eTag) async {
    final temp = File(resumePath ?? '${tempDir.path}/com.bbflight.background_downloader${_n++}');
    var written = start;
    String? serverTag;
    var ranges = false;
    try {
      await _status(j, TaskStatus.running);
      final req = await _client.getUrl(Uri.parse(j.task.url));
      if (start > 0) req.headers.set('range', 'bytes=$start-');
      final res = await req.close();
      if (res.statusCode == 404) {
        running.remove(j.task.taskId);
        await _status(j, TaskStatus.notFound);
        return;
      }
      if (res.statusCode >= 400) throw HttpException('HTTP ${res.statusCode}');
      serverTag = res.headers.value('etag');
      ranges = res.headers.value('accept-ranges') == 'bytes' || res.statusCode == 206;
      await _post('canResume', [j.taskJson, ranges]);
      if (start > 0 && (res.statusCode != 206 || serverTag != eTag || (eTag?.startsWith('W/') ?? false))) {
        if (await temp.exists()) await temp.delete();
        throw const HttpException('Cannot resume: ETag is not identical, or is weak');
      }
      final total = start + res.contentLength;
      final sink = temp.openWrite(mode: start > 0 ? FileMode.append : FileMode.write);
      try {
        await for (final chunk in res) {
          if (j.cancel || j.pause) break;
          sink.add(chunk);
          written += chunk.length;
          final stopAt = systemStopAfter[Uri.parse(j.task.url).path.substring(1)];
          if (stopAt != null && written >= stopAt) {
            systemStopAfter.remove(Uri.parse(j.task.url).path.substring(1));
            j.cancel = true;
            break;
          }
          await _post('progressUpdate', [j.taskJson, written / total, total, 1.0, 1000]);
        }
      } finally {
        await sink.close();
      }
      if (j.cancel) {
        running.remove(j.task.taskId);
        if (await temp.exists()) await temp.delete();
        await _status(j, TaskStatus.canceled);
        return;
      }
      if (j.pause) {
        running.remove(j.task.taskId);
        await _post('resumeData', [j.taskJson, temp.path, written, serverTag]);
        await _status(j, TaskStatus.paused);
        return;
      }
      if (written < total) throw const SocketException('Connection closed while receiving data');
      final dest = File(await j.task.filePath());
      await dest.parent.create(recursive: true);
      if (await dest.exists()) await dest.delete();
      await temp.rename(dest.path);
      running.remove(j.task.taskId);
      await _status(j, TaskStatus.complete);
    } catch (e) {
      running.remove(j.task.taskId);
      if (ranges && written > 1 << 20 && await temp.exists()) {
        await _post('resumeData', [j.taskJson, temp.path, written, serverTag]);
      } else if (await temp.exists()) {
        await temp.delete();
      }
      await _post('statusUpdate', [j.taskJson, TaskStatus.failed.index, 'TaskConnectionException', '$e', -1, null]);
    }
  }

  void close() => _client.close(force: true);
}
