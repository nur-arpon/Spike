/// The robot's boards as the phone brain sees them: the screen board over BLE
/// and/or over the hotspot, the camera board over the hotspot. One brain, many
/// pipes (PROTOCOL.md 11.4): face messages go to the screen board on the best
/// pipe (the hotspot WebSocket when it is up, else BLE); BLE-only messages
/// (hotspot_join/leave) go over BLE.
library;

import 'dart:async';

import '../../protocol/messages.dart';
import 'robot_session.dart';

class BoardInfo {
  const BoardInfo(this.role, this.link, this.label);
  final String role; // face | camera | robot
  final String link; // ble | hotspot
  final String label;
}

class RobotHub {
  RobotHub({required this.greeting, required this.onBoardLive, required this.onBoardGone, required this.onMessage,
      this.appVersion = '0'});

  final BrainGreeting Function() greeting;
  final void Function(RobotSession) onBoardLive;
  final void Function(RobotSession) onBoardGone;
  final void Function(RobotSession, SpikeMessage) onMessage;
  final String appVersion;

  final List<RobotSession> _sessions = [];
  final _changes = StreamController<void>.broadcast();

  Stream<void> get changes => _changes.stream;
  List<RobotSession> get live => [for (final s in _sessions) if (s.live) s];

  RobotSession? get faceBle => _pick('ble', face: true);
  RobotSession? get faceHotspot => _pick('hotspot', face: true);
  RobotSession? get camera => live.where((s) => s.role == 'camera' || s.caps.contains('camera')).firstOrNull;

  RobotSession? _pick(String link, {required bool face}) =>
      live.where((s) => s.pipe.link == link && (s.role == 'face' || s.role == 'robot')).firstOrNull;

  /// A robot board is connected (on any pipe).
  bool get online => live.any((s) => s.role != 'camera') || camera != null;
  bool get hasDrive => live.any((s) => s.caps.contains('drive'));
  bool get hasCamera => camera != null;
  List<BoardInfo> get boards => [for (final s in live) BoardInfo(s.role, s.pipe.link, s.pipe.label)];
  List<String> get roles => {for (final s in live) s.role}.toList()..sort();

  /// A new pipe (BLE after subscribing, or a board that reached the hotspot server).
  RobotSession attach(RobotPipe pipe, {String? token}) {
    late RobotSession s;
    // BLE: the robot says hello only once the bond is encrypted (pairing may still be finishing)
    final wait = Duration(seconds: pipe.link == 'ble' ? 15 : 5);
    s = RobotSession(pipe, greeting: greeting, token: token, appVersion: appVersion, helloTimeout: wait, onLive: (x) {
      _changes.add(null);
      onBoardLive(x);
    });
    _sessions.add(s);
    s.messages.listen((m) => onMessage(s, m));
    s.done.whenComplete(() {
      _sessions.remove(s);
      _changes.add(null);
      if (s.hello != null) onBoardGone(s);
    });
    return s;
  }

  /// To the screen board (the face and body): hotspot first, else BLE.
  Future<bool> toFace(SpikeMessage m) async {
    for (final s in [faceHotspot, faceBle]) {
      if (s != null && await s.send(m)) return true;
    }
    return false;
  }

  /// BLE only (the hotspot details must never travel in the clear).
  Future<bool> toBle(SpikeMessage m) async => await faceBle?.send(m) ?? false;

  Future<void> closeAll() async {
    for (final s in [..._sessions]) {
      await s.close();
    }
  }

  Future<void> closeLink(String link) async {
    for (final s in [..._sessions.where((s) => s.pipe.link == link)]) {
      await s.close();
    }
  }
}
