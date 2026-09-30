/// The app's side of PROTOCOL.md section 3: connect, hello handshake,
/// heartbeat (answer pings, 3 x heartbeat_s silence = dead), reconnect with
/// the spec's backoff (0.5, 1, 2, 4, 8, max 10 s, +-20 % jitter), per
/// connection message ids, and round-trip latency from our own pings.
library;

import 'dart:async';
import 'dart:math';

import 'package:web_socket_channel/io.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'messages.dart';
import 'names.dart';

typedef ChannelFactory = WebSocketChannel Function(Uri uri);

WebSocketChannel _defaultFactory(Uri uri) =>
    IOWebSocketChannel.connect(uri, connectTimeout: const Duration(seconds: 5));

/// Where the brain is.
class BrainEndpoint {
  const BrainEndpoint({required this.host, this.port = defaultPort, this.token, this.name, this.alt = const []});
  final String host;
  final int port;
  final String? token;
  final String? name; // e.g. the mDNS service name, for display

  /// Other addresses of the same brain, tried after [host] with the same token:
  /// the laptop's Tailscale address and MagicDNS name (PROTOCOL.md 10.7), so the
  /// app reaches it from any network. Not part of equality (same brain).
  final List<String> alt;

  /// Every address to try, home Wi-Fi first.
  List<String> get hosts => [host, for (final h in alt) if (h != host) h];

  Uri get uri => uriFor(host);
  Uri uriFor(String h) => Uri(scheme: 'ws', host: h, port: port, path: '/');
  String get label => name ?? '$host:$port';

  /// Same brain and the same fallback addresses.
  bool sameRoutes(BrainEndpoint? o) {
    if (o == null || o != this || o.alt.length != alt.length) return false;
    for (var i = 0; i < alt.length; i++) {
      if (o.alt[i] != alt[i]) return false;
    }
    return true;
  }

  BrainEndpoint withAlt(List<String> a) => BrainEndpoint(host: host, port: port, token: token, name: name, alt: a);

  Map<String, Object?> toJson() =>
      {'host': host, 'port': port, 'token': token, 'name': name, if (alt.isNotEmpty) 'alt': alt};
  static BrainEndpoint? fromJson(Map<String, dynamic>? m) {
    if (m == null || m['host'] is! String) return null;
    return BrainEndpoint(
      host: m['host'] as String,
      port: m['port'] is int ? m['port'] as int : defaultPort,
      token: m['token'] as String?,
      name: m['name'] as String?,
      alt: [for (final h in (m['alt'] is List ? m['alt'] as List : const [])) if (h is String && h.isNotEmpty) h],
    );
  }

  @override
  bool operator ==(Object other) =>
      other is BrainEndpoint && other.host == host && other.port == port && other.token == token;
  @override
  int get hashCode => Object.hash(host, port, token);
}

/// What this app says about itself in `hello`.
class ClientIdentity {
  const ClientIdentity(
      {required this.deviceId, required this.fw, this.role = 'tool', this.caps = const [], this.audioOut});
  final String deviceId;
  final String fw;
  final String role;
  final List<String> caps;

  /// hello `audio_out` (v1.5, PROTOCOL.md 10.8: the formats this phone can play).
  final Map<String, dynamic>? audioOut;
}

enum LinkPhase { idle, connecting, handshaking, connected, retrying, authFailed, versionMismatch }

/// Who is Spike's brain right now: the laptop (home, protocol sections 1-10) or
/// this phone (away from home, section 11).
enum BrainHost { laptop, phone }

/// What the app's screens talk to: the laptop brain over the LAN ([BrainClient])
/// or the phone brain (away mode). Both speak the same messages, so no screen
/// needs to know which one it is.
abstract class SpikeLink {
  Stream<SpikeMessage> get messages;
  Stream<LinkStatus> get status;
  LinkStatus get current;
  bool send(SpikeMessage msg);
  bool get legacyBrain;
}

class LinkStatus {
  const LinkStatus({
    this.phase = LinkPhase.idle,
    this.endpoint,
    this.attempt = 0,
    this.retryAt,
    this.error,
    this.hello,
    this.rttMs,
    this.brain = BrainHost.laptop,
    this.host,
  });
  final LinkPhase phase;
  final BrainHost brain;
  final BrainEndpoint? endpoint;

  /// The address in use (or being tried): [endpoint]'s host, or one of its alternates.
  final String? host;
  final int attempt; // failed attempts since the last good hello
  final DateTime? retryAt;
  final String? error;
  final BrainHello? hello;
  final int? rttMs;

  bool get isConnected => phase == LinkPhase.connected;
  bool get isTrying =>
      phase == LinkPhase.connecting || phase == LinkPhase.handshaking || phase == LinkPhase.retrying;

  /// Reached through an alternate address (Tailscale): "Connected from anywhere".
  bool get viaAlt => endpoint != null && host != null && host != endpoint!.host;

  /// USB (`adb reverse`): the brain is on this phone's loopback.
  bool get viaUsb => (host ?? endpoint?.host) == '127.0.0.1' || (host ?? endpoint?.host) == 'localhost';

  /// How the laptop is reached, for the UI.
  String get routeLabel => viaUsb ? 'USB' : (viaAlt ? 'Connected from anywhere' : 'Home Wi-Fi');

  LinkStatus copyWith({
    LinkPhase? phase,
    BrainEndpoint? endpoint,
    int? attempt,
    DateTime? retryAt,
    bool clearRetry = false,
    String? error,
    bool clearError = false,
    BrainHello? hello,
    bool clearHello = false,
    int? rttMs,
    BrainHost? brain,
    String? host,
  }) =>
      LinkStatus(
        host: host ?? this.host,
        brain: brain ?? this.brain,
        phase: phase ?? this.phase,
        endpoint: endpoint ?? this.endpoint,
        attempt: attempt ?? this.attempt,
        retryAt: clearRetry ? null : (retryAt ?? this.retryAt),
        error: clearError ? null : (error ?? this.error),
        hello: clearHello ? null : (hello ?? this.hello),
        rttMs: rttMs ?? this.rttMs,
      );
}

class BrainClient implements SpikeLink {
  BrainClient({
    required this.identity,
    ChannelFactory? channelFactory,
    Random? random,
    this.helloTimeout = const Duration(seconds: 5),
    this.pingEvery = const Duration(seconds: 5),
  })  : _factory = channelFactory ?? _defaultFactory,
        _rng = random ?? Random();

  final ClientIdentity identity;
  final ChannelFactory _factory;
  final Random _rng;
  final Duration helloTimeout;
  final Duration pingEvery;

  final _messages = StreamController<SpikeMessage>.broadcast();
  final _status = StreamController<LinkStatus>.broadcast();
  LinkStatus _current = const LinkStatus();

  WebSocketChannel? _ch;
  StreamSubscription<dynamic>? _sub;
  int _gen = 0; // bumps on every connect()/disconnect(): stale callbacks check it
  int _outId = 0;
  Timer? _retryTimer;
  Timer? _watchdog;
  Timer? _pinger;
  Timer? _helloTimer;
  DateTime _lastRx = DateTime.now();
  double _heartbeatS = 5;
  final Map<int, DateTime> _pings = {};
  int? _helloId;
  bool _legacy = false; // the brain predates v1.2 (no role "app"): we said hello as "tool"
  int _hostIdx = 0; // which of endpoint.hosts this attempt uses (home Wi-Fi first, then Tailscale)

  @override
  Stream<SpikeMessage> get messages => _messages.stream;
  @override
  Stream<LinkStatus> get status => _status.stream;
  @override
  LinkStatus get current => _current;

  /// True when the brain is older than protocol v1.2 and refused role "app": the app then
  /// joins as "tool" and uses the v1.1 fallbacks (typed words instead of app messages).
  @override
  bool get legacyBrain => _legacy;

  String get _role => _legacy && identity.role == 'app' ? 'tool' : identity.role;

  /// The spec's reconnect delay for the given failed attempt (0-based).
  static Duration backoff(int attempt, Random rng) {
    const steps = [0.5, 1.0, 2.0, 4.0, 8.0, 10.0];
    final base = steps[min(attempt, steps.length - 1)];
    final jitter = 1 + (rng.nextDouble() * 0.4 - 0.2);
    return Duration(milliseconds: (base * jitter * 1000).round());
  }

  void _set(LinkStatus s) {
    _current = s;
    if (!_status.isClosed) _status.add(s);
  }

  /// Start (or switch) the connection. It keeps itself up until [disconnect].
  void connect(BrainEndpoint endpoint) {
    _gen++;
    if (endpoint != _current.endpoint) _legacy = false;
    _teardown();
    _hostIdx = 0;
    _set(LinkStatus(phase: LinkPhase.connecting, endpoint: endpoint, host: endpoint.host));
    _open(_gen);
  }

  /// The same brain learnt new fallback addresses (pairing): use them from the next
  /// attempt on, without dropping a working connection.
  void updateEndpoint(BrainEndpoint endpoint) {
    if (endpoint != _current.endpoint) return;
    _set(LinkStatus(
      phase: _current.phase, endpoint: endpoint, attempt: _current.attempt, retryAt: _current.retryAt,
      error: _current.error, hello: _current.hello, rttMs: _current.rttMs, brain: _current.brain, host: _current.host,
    ));
  }

  Future<void> disconnect() async {
    _gen++;
    _teardown(code: CloseCodes.normal);
    _set(const LinkStatus());
  }

  /// Send a message now. Returns false when not connected (callers decide
  /// whether to queue; the protocol has no delivery guarantee anyway).
  @override
  bool send(SpikeMessage msg) {
    final ch = _ch;
    if (ch == null || !_current.isConnected) return false;
    return _write(ch, msg);
  }

  bool _write(WebSocketChannel ch, SpikeMessage msg, {int? re}) {
    _outId = _outId >= 0xFFFFFFFF ? 1 : _outId + 1;
    final text = msg.encode(id: _outId, re: re, ts: DateTime.now().millisecondsSinceEpoch);
    if (text.length > maxMessageBytes) return false;
    try {
      ch.sink.add(text);
      if (msg is PingMsg) _pings[_outId] = DateTime.now();
      if (msg is ClientHello) _helloId = _outId;
      return true;
    } catch (_) {
      return false;
    }
  }

  Future<void> _open(int gen) async {
    final ep = _current.endpoint;
    if (ep == null) return;
    _outId = 0;
    _pings.clear();
    final hosts = ep.hosts;
    final host = hosts[_hostIdx % hosts.length];
    if (_current.host != host) _set(_current.copyWith(host: host));
    WebSocketChannel ch;
    try {
      ch = _factory(ep.uriFor(host));
      await ch.ready;
    } catch (e) {
      if (gen != _gen) return;
      _failed(gen, _describe(e));
      return;
    }
    if (gen != _gen) {
      ch.sink.close(CloseCodes.normal);
      return;
    }
    _ch = ch;
    _lastRx = DateTime.now();
    _set(_current.copyWith(phase: LinkPhase.handshaking));
    _sub = ch.stream.listen(
      (data) => _onData(gen, data),
      onDone: () => _onClosed(gen, ch.closeCode, ch.closeReason),
      onError: (Object e) => _onClosed(gen, null, _describe(e)),
      cancelOnError: true,
    );
    _write(ch, ClientHello(
      role: _role,
      deviceId: identity.deviceId,
      fw: identity.fw,
      caps: identity.caps,
      audioOut: identity.audioOut,
      token: ep.token,
    ));
    _helloTimer = Timer(helloTimeout, () {
      if (gen == _gen && _current.phase == LinkPhase.handshaking) {
        _teardown(code: CloseCodes.normal);
        _failed(gen, 'Spike did not answer the hello');
      }
    });
  }

  void _onData(int gen, dynamic data) {
    if (gen != _gen) return;
    _lastRx = DateTime.now();
    if (data is! String) return; // v1: binary frames are ignored
    final SpikeMessage msg;
    try {
      msg = SpikeMessage.decode(data, from: Sender.brain);
    } on ProtocolException {
      return; // a bad message from the brain is dropped, never fatal
    }
    final ch = _ch;
    if (msg is PingMsg && ch != null) {
      _write(ch, const PongMsg(), re: msg.id);
      return;
    }
    if (msg is PongMsg) {
      final sent = _pings.remove(msg.re);
      if (sent != null) _set(_current.copyWith(rttMs: DateTime.now().difference(sent).inMilliseconds));
      return;
    }
    if (msg is BrainHello && _current.phase == LinkPhase.handshaking && (msg.re == null || msg.re == _helloId)) {
      _helloTimer?.cancel();
      _heartbeatS = msg.heartbeatS.toDouble().clamp(1, 60);
      _set(_current.copyWith(phase: LinkPhase.connected, attempt: 0, hello: msg, clearRetry: true, clearError: true));
      _startTimers(gen);
    } else if (msg is ErrorMsg && _current.phase == LinkPhase.handshaking) {
      if (msg.code == 'auth') _set(_current.copyWith(error: 'The pairing code was not accepted'));
      if (msg.code == 'version_mismatch') _set(_current.copyWith(error: 'This app speaks a different protocol version'));
      if (msg.code == 'bad_value' && identity.role == 'app' && !_legacy && (msg.message ?? '').contains('role')) {
        _legacy = true; // a v1.1 brain: the reconnect says hello as "tool"
      }
    }
    if (!_messages.isClosed) _messages.add(msg);
  }

  void _startTimers(int gen) {
    _watchdog?.cancel();
    _watchdog = Timer.periodic(const Duration(seconds: 1), (_) {
      if (gen != _gen) return;
      final silentMs = DateTime.now().difference(_lastRx).inMilliseconds;
      if (silentMs > _heartbeatS * 3 * 1000) {
        _teardown(code: CloseCodes.normal);
        _hostIdx = 0; // a dropped link starts again from home Wi-Fi
        _scheduleRetry(gen, 'Lost touch with Spike');
      }
    });
    _pinger?.cancel();
    void ping() {
      final ch = _ch;
      if (gen == _gen && ch != null && _current.isConnected) {
        _pings.removeWhere((_, t) => DateTime.now().difference(t).inSeconds > 30);
        _write(ch, const PingMsg());
      }
    }

    ping();
    _pinger = Timer.periodic(pingEvery, (_) => ping());
  }

  void _onClosed(int gen, int? code, String? reason) {
    if (gen != _gen) return;
    _teardown();
    if (code == CloseCodes.auth) {
      _set(_current.copyWith(phase: LinkPhase.authFailed, error: 'Spike needs the pairing code (QR) to connect',
          clearHello: true));
      return;
    }
    if (code == CloseCodes.versionMismatch) {
      _set(_current.copyWith(phase: LinkPhase.versionMismatch, error: 'This app and Spike speak different versions',
          clearHello: true));
      return;
    }
    final why = code == CloseCodes.goingAway ? 'Spike\'s brain is shutting down' : (reason?.isNotEmpty == true ? reason : 'Connection closed');
    if (_current.phase == LinkPhase.handshaking) {
      _failed(gen, why); // this address let us in but did not finish: try the next one
    } else {
      _hostIdx = 0; // a dropped link starts again from home Wi-Fi
      _scheduleRetry(gen, why);
    }
  }

  /// An attempt failed before `hello`: try the brain's next address at once
  /// (home Wi-Fi, then Tailscale); after the last one, the spec's backoff.
  void _failed(int gen, String? why) {
    if (gen != _gen) return;
    final hosts = _current.endpoint?.hosts ?? const [];
    if (_hostIdx + 1 < hosts.length) {
      _hostIdx++;
      _teardown();
      _set(_current.copyWith(phase: LinkPhase.connecting, host: hosts[_hostIdx], error: why, clearHello: true));
      _open(gen);
      return;
    }
    _hostIdx = 0;
    _scheduleRetry(gen, why);
  }

  void _scheduleRetry(int gen, String? why) {
    if (gen != _gen) return;
    final attempt = _current.attempt;
    final wait = backoff(attempt, _rng);
    _set(_current.copyWith(
      phase: LinkPhase.retrying,
      attempt: attempt + 1,
      retryAt: DateTime.now().add(wait),
      error: why,
      clearHello: true,
    ));
    _retryTimer?.cancel();
    _retryTimer = Timer(wait, () {
      if (gen != _gen) return;
      _set(_current.copyWith(phase: LinkPhase.connecting, clearRetry: true));
      _open(gen);
    });
  }

  /// Try again right now (the user pulled to refresh or pressed Retry).
  void retryNow() {
    final ep = _current.endpoint;
    if (ep != null) connect(ep);
  }

  void _teardown({int? code}) {
    _retryTimer?.cancel();
    _watchdog?.cancel();
    _pinger?.cancel();
    _helloTimer?.cancel();
    _retryTimer = _watchdog = _pinger = _helloTimer = null;
    _sub?.cancel();
    _sub = null;
    final ch = _ch;
    _ch = null;
    if (ch != null) {
      try {
        ch.sink.close(code ?? CloseCodes.normal);
      } catch (_) {}
    }
  }

  static String _describe(Object e) {
    final s = e.toString();
    if (s.contains('Connection refused')) return 'Nobody is listening there';
    if (s.contains('timed out') || s.contains('TimeoutException')) return 'No answer (is the laptop on this Wi-Fi?)';
    if (s.contains('No route') || s.contains('Network is unreachable')) return 'That address is not reachable';
    if (s.contains('Failed host lookup')) return 'Unknown host name';
    return 'Could not connect';
  }

  Future<void> dispose() async {
    _gen++;
    _teardown(code: CloseCodes.normal);
    await _messages.close();
    await _status.close();
  }
}
