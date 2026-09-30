/// The phone brain's side of PROTOCOL.md section 3, for one robot board on one
/// pipe (BLE or the hotspot WebSocket): the board says hello first (within 5
/// s), the phone answers with a brain hello, then set_mode and mood; the phone
/// pings every heartbeat and treats 3 heartbeats of silence as a dead link.
/// Robot-to-brain messages come out of [messages], already decoded.
library;

import 'dart:async';

import '../../protocol/messages.dart';
import '../../protocol/names.dart' as n;

/// A bidirectional text pipe to one robot board.
abstract class RobotPipe {
  /// `ble` or `hotspot`.
  String get link;

  /// Human description for logs/UI ("Spike-7c9e2a over Bluetooth").
  String get label;

  /// Complete JSON messages from the board.
  Stream<String> get incoming;

  /// Send one complete JSON message. False if the pipe is closed or it can't carry it.
  Future<bool> send(String json);

  /// Largest message this pipe carries (BLE: 16 KiB).
  int get maxMessage;

  /// Completes when the pipe closes (either side).
  Future<void> get closed;

  Future<void> close();
}

/// What the phone brain says about itself in hello, and what it re-sends on connect.
class BrainGreeting {
  const BrainGreeting({required this.mode, required this.names, required this.wakeWords, this.heartbeatS = 5});
  final String mode;
  final Map<String, String> names;
  final Map<String, List<String>> wakeWords;
  final int heartbeatS;
}

enum SessionState { handshaking, live, closed }

class RobotSession {
  RobotSession(
    this.pipe, {
    required this.greeting,
    required this.onLive,
    this.token,
    this.appVersion = '0',
    this.helloTimeout = const Duration(seconds: 5),
  }) {
    _sub = pipe.incoming.listen(_onText, onDone: () => _close('pipe closed'));
    pipe.closed.whenComplete(() => _close('pipe closed'));
    _helloTimer = Timer(helloTimeout, () {
      if (state == SessionState.handshaking) _close('no hello in time', code: 'not_ready');
    });
  }

  final RobotPipe pipe;
  final BrainGreeting Function() greeting;

  /// Called once the board's hello was accepted: send the state burst (set_mode,
  /// mood, recipe, display...) with [send].
  final void Function(RobotSession) onLive;

  /// Required in the board's hello when set (the hotspot's one-time token).
  final String? token;
  final String appVersion;
  final Duration helloTimeout;

  final _messages = StreamController<SpikeMessage>.broadcast();
  StreamSubscription<String>? _sub;
  Timer? _helloTimer;
  Timer? _pinger;
  Timer? _watchdog;
  int _outId = 0;
  DateTime _lastRx = DateTime.now();
  SessionState state = SessionState.handshaking;
  ClientHello? hello;
  String? closeReason;
  final _closedC = Completer<void>();

  Stream<SpikeMessage> get messages => _messages.stream;
  Future<void> get done => _closedC.future;
  bool get live => state == SessionState.live;
  String get role => hello?.role ?? '?';
  List<String> get caps => hello?.caps ?? const [];

  Future<bool> send(SpikeMessage m, {int? re}) async {
    if (state == SessionState.closed) return false;
    _outId = _outId >= 0xFFFFFFFF ? 1 : _outId + 1;
    final text = m.encode(id: _outId, re: re, ts: DateTime.now().millisecondsSinceEpoch);
    if (text.length > pipe.maxMessage) return false;
    return pipe.send(text);
  }

  void _onText(String text) {
    _lastRx = DateTime.now();
    final SpikeMessage m;
    try {
      m = SpikeMessage.decode(text, from: Sender.client);
    } on ProtocolException catch (e) {
      send(ErrorMsg(code: e.code, message: e.message));
      return;
    }
    if (state == SessionState.handshaking) {
      if (m is! ClientHello) {
        send(ErrorMsg(code: 'not_ready', message: 'say hello first'), re: m.id);
        return;
      }
      if (!const ['face', 'camera', 'robot'].contains(m.role)) {
        send(ErrorMsg(code: 'bad_value', message: 'role ${m.role} is not a robot board'), re: m.id);
        _close('wrong role');
        return;
      }
      if (token != null && m.token != token) {
        send(const ErrorMsg(code: 'auth', message: 'bad or missing token'), re: m.id);
        _close('bad token', code: 'auth');
        return;
      }
      hello = m;
      state = SessionState.live;
      _helloTimer?.cancel();
      final g = greeting();
      send(
        BrainHello(
          server: 'spike-phone', version: appVersion, session: 'p${DateTime.now().millisecondsSinceEpoch % 100000}',
          heartbeatS: g.heartbeatS, mode: g.mode, names: g.names, wakeWords: g.wakeWords,
          audio: const {'format': 'pcm_s16le', 'rate': 22050, 'channels': 1},
        ),
        re: m.id,
      );
      _startHeartbeat(g.heartbeatS);
      onLive(this);
      return;
    }
    if (m is PingMsg) {
      send(const PongMsg(), re: m.id);
      return;
    }
    if (m is PongMsg) return;
    if (!_messages.isClosed) _messages.add(m);
  }

  void _startHeartbeat(int hb) {
    _pinger = Timer.periodic(Duration(seconds: hb), (_) => send(const PingMsg()));
    _watchdog = Timer.periodic(const Duration(seconds: 1), (_) {
      if (DateTime.now().difference(_lastRx).inMilliseconds > hb * 3 * 1000) _close('silent for 3 heartbeats');
    });
  }

  void _close(String why, {String? code}) {
    if (state == SessionState.closed) return;
    state = SessionState.closed;
    closeReason = why;
    _helloTimer?.cancel();
    _pinger?.cancel();
    _watchdog?.cancel();
    _sub?.cancel();
    pipe.close();
    _messages.close();
    if (!_closedC.isCompleted) _closedC.complete();
  }

  Future<void> close() async => _close('closed by the phone');
}

/// PROTOCOL.md rule 4: every mood/action name must be one the robot knows.
bool knownAction(String a) => n.actions.contains(a);
