/// First-time robot Wi-Fi setup from the computer, through the robot's own setup portal
/// (firmware screen_board/src/provision.cpp and camera_board/src/cam_main.cpp).
///
/// A robot with no saved Wi-Fi (or one it cannot reach for 60 s) opens an open network called
/// "Spike-Setup-xxxxxx" (screen board) or "Spike-Cam-Setup-xxxxxx" (camera board) for 15 minutes,
/// with a form at http://192.168.4.1 that takes: ssid, pass, host, port, token (+ robot, the
/// screen board's device id, on the camera board; + ota, optional). This file is that form's client:
/// the owner joins the setup network from Windows' Wi-Fi menu (we never change network settings),
/// the app finds the portal and posts the form with the brain's address and pairing token filled
/// in, so only the home Wi-Fi password is typed. The password goes to the robot only, never saved.
library;

import 'dart:async';

import 'package:http/http.dart' as http;

enum PortalBoard { screen, camera }

class PortalInfo {
  const PortalInfo(this.board, {this.deviceId, this.ssid = '', this.host = ''});
  final PortalBoard board;

  /// The screen board shows its device id (e.g. spike-1a2b3c) under the form: the camera board
  /// needs it to know which robot it belongs to.
  final String? deviceId;

  /// What the robot has saved already (its form is pre-filled with these).
  final String ssid;
  final String host;
}

/// What the portal page says about itself (pure; tested against the firmware's own HTML).
PortalInfo? parsePortalPage(String html) {
  final PortalBoard board;
  if (html.contains('<h2>Spike camera setup</h2>')) {
    board = PortalBoard.camera;
  } else if (html.contains('<h2>Spike setup</h2>')) {
    board = PortalBoard.screen;
  } else {
    return null;
  }
  String value(String name) =>
      RegExp('<input name=$name value="([^"]*)"').firstMatch(html)?.group(1)?.replaceAll('&quot;', '"').replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&amp;', '&') ??
      '';
  final id = RegExp(r'Device (spike-[0-9A-Za-z]+)').firstMatch(html)?.group(1);
  return PortalInfo(board, deviceId: id, ssid: value('ssid'), host: value('host'));
}

/// The form fields to post (pure; tested). Empty password/token keep what the robot has.
Map<String, String> portalForm({
  required PortalBoard board,
  required String ssid,
  required String password,
  required String brainHost,
  required int brainPort,
  required String token,
  String? robotId,
}) =>
    {
      'ssid': ssid,
      'pass': password,
      'host': brainHost,
      'port': '$brainPort',
      'token': token,
      if (board == PortalBoard.camera) 'robot': robotId ?? '',
    };

class RobotPortal {
  RobotPortal({http.Client? client, this.base = 'http://192.168.4.1', this.timeout = const Duration(seconds: 3)})
      : _client = client ?? http.Client();
  final http.Client _client;
  final String base;
  final Duration timeout;

  /// The portal, if this computer can see one right now (it is on the robot's setup network).
  Future<PortalInfo?> probe() async {
    try {
      final r = await _client.get(Uri.parse('$base/')).timeout(timeout);
      if (r.statusCode != 200) return null;
      return parsePortalPage(r.body);
    } catch (_) {
      return null;
    }
  }

  /// Post the form. True when the robot said "Saved" (it restarts and joins the home Wi-Fi).
  Future<bool> save(Map<String, String> form) async {
    try {
      final r = await _client.post(Uri.parse('$base/save'), body: form).timeout(const Duration(seconds: 8));
      return r.statusCode == 200 && r.body.contains('Saved');
    } catch (_) {
      return false;
    }
  }

  void close() => _client.close();
}

/// Waits for a portal to appear (the owner is joining the setup network), checking every
/// [every] until [within] has passed or [cancelled] says stop.
Future<PortalInfo?> waitForPortal(RobotPortal portal,
    {Duration every = const Duration(seconds: 2), Duration within = const Duration(minutes: 5), bool Function()? cancelled}) async {
  final end = DateTime.now().add(within);
  while (DateTime.now().isBefore(end)) {
    if (cancelled?.call() ?? false) return null;
    final p = await portal.probe();
    if (p != null) return p;
    await Future<void>.delayed(every);
  }
  return null;
}
