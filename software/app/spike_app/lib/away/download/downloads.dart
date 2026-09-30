/// The phone-side checks around a big download: listing Hugging Face files,
/// free space, mobile data, and the notification permission.
library;

import 'dart:convert';
import 'dart:io';

import 'package:background_downloader/background_downloader.dart';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

import 'bundle.dart';

/// Every entry of a Hugging Face repo at [revision] (all pages of the listing).
Future<List<Map<String, dynamic>>> hfTree(String repo, String revision, {http.Client? client}) async {
  final c = client ?? http.Client();
  try {
    var url = Uri.parse('https://huggingface.co/api/models/$repo/tree/$revision?recursive=true');
    final out = <Map<String, dynamic>>[];
    for (var page = 0; page < 50; page++) {
      final r = await c.get(url).timeout(const Duration(seconds: 20));
      if (r.statusCode != 200) throw HttpException('HTTP ${r.statusCode} listing $repo');
      out.addAll((jsonDecode(r.body) as List<dynamic>).cast<Map<String, dynamic>>());
      final next = nextLink(r.headers['link']);
      if (next == null) break;
      url = Uri.parse(next);
    }
    return out;
  } finally {
    if (client == null) c.close();
  }
}

/// The `rel="next"` URL of an HTTP Link header (Hugging Face paginates listings).
String? nextLink(String? header) {
  if (header == null) return null;
  for (final part in header.split(',')) {
    final m = RegExp(r'<([^>]+)>\s*;\s*rel="?next"?').firstMatch(part.trim());
    if (m != null) return m.group(1);
  }
  return null;
}

const _storage = MethodChannel('spike/storage');

/// Free bytes on the storage the app writes to (Android StatFs), null if unknown.
Future<int?> freeBytes() async {
  try {
    return await _storage.invokeMethod<int>('freeBytes');
  } catch (_) {
    return null;
  }
}

/// Room left for the phone after a download (so it never fills up completely).
const spaceMargin = 200 << 20;

/// Null when [needBytes] fits with room to spare, else the sentence to show.
Future<String?> spaceProblem(int needBytes) async {
  final free = await freeBytes();
  if (free == null || free >= needBytes + spaceMargin) return null;
  return 'Not enough space: this needs ${mb(needBytes + spaceMargin)} free and the phone has ${mb(free)}. '
      'Free some space, then try again.';
}

/// True when the phone is online only through mobile data.
Future<bool> onMobileData() async {
  try {
    final r = await Connectivity().checkConnectivity();
    return r.contains(ConnectivityResult.mobile) &&
        !r.contains(ConnectivityResult.wifi) &&
        !r.contains(ConnectivityResult.ethernet);
  } catch (_) {
    return false;
  }
}

/// Asks (Android 13+) to show the download's progress notification. The
/// download works without it, but then Android may stop it after 9 minutes in
/// the background (it resumes, just more slowly).
Future<void> askNotificationPermission() async {
  if (!Platform.isAndroid) return;
  try {
    final p = FileDownloader().permissions;
    if (await p.status(PermissionType.notifications) != PermissionStatus.granted) {
      await p.request(PermissionType.notifications);
    }
  } catch (e) {
    debugPrint('download: notification permission $e');
  }
}

/// One line about the size and space, e.g. "360 MB download · 12.3 GB free".
Future<String> sizeLine(int bytes, {required bool mobile}) async {
  final free = await freeBytes();
  final base = '${mb(bytes)} download${free == null ? '' : ' · ${mb(free)} free on the phone'}';
  return mobile ? '$base · on mobile data: this uses ${mb(bytes)} of your data' : base;
}
