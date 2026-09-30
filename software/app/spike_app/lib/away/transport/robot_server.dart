/// The phone brain's small WebSocket server for robot boards that joined the
/// phone's hotspot (PROTOCOL.md 11.5). Same wire rules as the laptop brain:
/// one JSON object per text frame, 64 KiB max, binary frames ignored. Every
/// board must present the one-time token of this hotspot session in its hello
/// (checked by [RobotSession]).
library;

import 'dart:async';
import 'dart:io';

import '../../protocol/names.dart' as n;
import 'robot_session.dart';

class WsRobotPipe implements RobotPipe {
  WsRobotPipe(this._ws, this._peer) {
    _sub = _ws.listen((d) {
      if (d is String && d.length <= n.maxMessageBytes * 4) _in.add(d); // binary frames: ignored (v1)
    }, onDone: _done, onError: (_) => _done(), cancelOnError: true);
  }
  final WebSocket _ws;
  final String _peer;
  final _in = StreamController<String>.broadcast();
  final _closed = Completer<void>();
  StreamSubscription<dynamic>? _sub;

  void _done() {
    if (!_closed.isCompleted) _closed.complete();
    _in.close();
  }

  @override
  String get link => 'hotspot';
  @override
  String get label => 'board at $_peer over the hotspot';
  @override
  Stream<String> get incoming => _in.stream;
  @override
  int get maxMessage => n.maxMessageBytes;
  @override
  Future<void> get closed => _closed.future;

  @override
  Future<bool> send(String json) async {
    if (_closed.isCompleted || _ws.readyState != WebSocket.open) return false;
    try {
      _ws.add(json);
      return true;
    } catch (_) {
      return false;
    }
  }

  @override
  Future<void> close() async {
    await _sub?.cancel();
    try {
      await _ws.close(1000);
    } catch (_) {}
    _done();
  }
}

class RobotServer {
  RobotServer({this.port = 8766});
  final int port;
  HttpServer? _server;
  final _pipes = StreamController<WsRobotPipe>.broadcast();

  Stream<WsRobotPipe> get pipes => _pipes.stream;
  int? get boundPort => _server?.port;
  bool get running => _server != null;

  /// Listens on every interface (the hotspot's address changes per session and
  /// per phone); the per-session token in hello is what keeps strangers out.
  Future<int> start() async {
    if (_server != null) return _server!.port;
    HttpServer s;
    try {
      s = await HttpServer.bind(InternetAddress.anyIPv4, port);
    } on SocketException {
      s = await HttpServer.bind(InternetAddress.anyIPv4, 0); // the port is taken: any free one
    }
    _server = s;
    s.listen((req) async {
      if (!WebSocketTransformer.isUpgradeRequest(req)) {
        req.response
          ..statusCode = HttpStatus.upgradeRequired
          ..close();
        return;
      }
      try {
        final ws = await WebSocketTransformer.upgrade(req);
        ws.pingInterval = const Duration(seconds: 5);
        _pipes.add(WsRobotPipe(ws, req.connectionInfo?.remoteAddress.address ?? '?'));
      } catch (_) {}
    });
    return s.port;
  }

  Future<void> stop() async {
    final s = _server;
    _server = null;
    await s?.close(force: true);
  }
}
