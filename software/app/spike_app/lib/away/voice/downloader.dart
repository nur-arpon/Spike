/// Downloads a set of files into a folder with one overall progress, cancel,
/// and an all-or-nothing finish (files land as `.part` and are renamed only
/// when every one arrived, then a `.complete` marker is written). Used for
/// Spike's on-device voice (Kokoro), which is fetched only when the owner asks.
library;

import 'dart:async';
import 'dart:io';

import 'package:http/http.dart' as http;

class RemoteFile {
  const RemoteFile(this.url, this.path, this.size);
  final String url;
  final String path; // relative to the target folder
  final int size; // expected bytes (for progress; 0 = unknown)
}

class DownloadCancelled implements Exception {
  const DownloadCancelled();
}

class FolderDownload {
  FolderDownload(this.dir, this.files, {http.Client? client}) : _client = client ?? http.Client();
  final Directory dir;
  final List<RemoteFile> files;
  final http.Client _client;
  bool _cancelled = false;

  static const marker = '.complete';

  int get totalBytes => files.fold(0, (a, f) => a + f.size);
  static bool isComplete(Directory dir) => File('${dir.path}/$marker').existsSync();

  void cancel() => _cancelled = true;

  /// Runs the download; [onProgress] gets 0..1. Throws [DownloadCancelled] or an I/O error.
  Future<void> run(void Function(double) onProgress, {int parallel = 4}) async {
    await dir.create(recursive: true);
    final total = totalBytes == 0 ? 1 : totalBytes;
    var done = 0;
    final queue = [...files];
    final parts = <File>[];

    Future<void> worker() async {
      while (queue.isNotEmpty) {
        if (_cancelled) throw const DownloadCancelled();
        final f = queue.removeAt(0);
        final out = File('${dir.path}/${f.path}.part');
        await out.parent.create(recursive: true);
        parts.add(out);
        final resp = await _client.send(http.Request('GET', Uri.parse(f.url))).timeout(const Duration(seconds: 30));
        if (resp.statusCode != 200) throw HttpException('HTTP ${resp.statusCode} for ${f.path}');
        final sink = out.openWrite();
        try {
          await for (final chunk in resp.stream.timeout(const Duration(seconds: 30))) {
            if (_cancelled) throw const DownloadCancelled();
            sink.add(chunk);
            done += chunk.length;
            onProgress((done / total).clamp(0, 1).toDouble());
          }
        } finally {
          await sink.close();
        }
      }
    }

    try {
      await Future.wait([for (var i = 0; i < parallel; i++) worker()]);
      for (final p in parts) {
        await p.rename(p.path.substring(0, p.path.length - 5));
      }
      await File('${dir.path}/$marker').writeAsString(DateTime.now().toIso8601String());
      onProgress(1);
    } catch (_) {
      for (final p in parts) {
        if (await p.exists()) await p.delete();
      }
      rethrow;
    }
  }

  void close() => _client.close();
}
