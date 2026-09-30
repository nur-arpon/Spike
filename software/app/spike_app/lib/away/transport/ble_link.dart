/// Bluetooth LE link to Spike's screen board (PROTOCOL.md 11.1 to 11.3), the
/// main phone <-> robot link away from home.
///
/// Library: universal_ble (BSD-3-Clause, maintained by Navideck). Chosen over
/// flutter_blue_plus, whose licence since v1.x requires a paid commercial
/// licence for any for-profit use (checked 29 Sep 2026), and over
/// flutter_reactive_ble, which has no bonding API. All calls go through
/// [BleApi] so the link logic is unit-tested with a fake radio.
///
/// Security is the robot's: rx/tx need an encrypted, authenticated (MITM) bond.
/// [BleRobotLink.connect] asks Android to pair when the phone is not bonded
/// yet; Android then shows its own dialog and the owner types the 6-digit
/// passkey shown on Spike's face.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:universal_ble/universal_ble.dart';

import 'ble_frames.dart';
import 'robot_session.dart';

const spikeServiceUuid = 'c0de5b1e-0001-4a3c-9e5f-5370696b6500';
const spikeRxUuid = 'c0de5b1e-0002-4a3c-9e5f-5370696b6500';
const spikeTxUuid = 'c0de5b1e-0003-4a3c-9e5f-5370696b6500';
const spikeInfoUuid = 'c0de5b1e-0004-4a3c-9e5f-5370696b6500';

class FoundRobot {
  const FoundRobot({required this.deviceId, required this.name, this.rssi, this.paired});
  final String deviceId; // the Bluetooth address on Android
  final String name; // "Spike-7c9e2a"
  final int? rssi;
  final bool? paired;
}

/// The radio, as the link needs it (a thin seam over universal_ble's static API).
abstract class BleApi {
  Future<bool> hasPermissions();
  Future<void> requestPermissions();
  Future<bool> bluetoothOn();
  Stream<FoundRobot> scan(Duration timeout);
  Future<void> connect(String deviceId);
  Future<void> disconnect(String deviceId);
  Stream<bool> connection(String deviceId);
  Future<void> discover(String deviceId);
  Future<int> requestMtu(String deviceId, int mtu);
  Future<bool?> isPaired(String deviceId);
  Future<void> pair(String deviceId);
  Future<Uint8List> read(String deviceId, String char);
  Future<void> write(String deviceId, String char, Uint8List value, {bool withoutResponse = false});
  Future<void> subscribe(String deviceId, String char);
  Stream<Uint8List> values(String deviceId, String char);
}

class UniversalBleApi implements BleApi {
  @override
  Future<bool> hasPermissions() => UniversalBle.hasPermissions();
  @override
  Future<void> requestPermissions() => UniversalBle.requestPermissions();
  @override
  Future<bool> bluetoothOn() async => await UniversalBle.getBluetoothAvailabilityState() == AvailabilityState.poweredOn;

  @override
  Stream<FoundRobot> scan(Duration timeout) {
    final out = StreamController<FoundRobot>();
    Timer? stopper;
    out.onListen = () async {
      UniversalBle.onScanResult = (d) {
        if (!out.isClosed) {
          out.add(FoundRobot(deviceId: d.deviceId, name: d.name ?? 'Spike', rssi: d.rssi, paired: d.paired));
        }
      };
      try {
        await UniversalBle.startScan(scanFilter: ScanFilter(withServices: [spikeServiceUuid]));
      } catch (e) {
        out.addError(e);
        await out.close();
        return;
      }
      stopper = Timer(timeout, () async {
        await UniversalBle.stopScan();
        await out.close();
      });
    };
    out.onCancel = () async {
      stopper?.cancel();
      UniversalBle.onScanResult = null;
      await UniversalBle.stopScan();
    };
    return out.stream;
  }

  @override
  Future<void> connect(String deviceId) => UniversalBle.connect(deviceId, timeout: const Duration(seconds: 15));
  @override
  Future<void> disconnect(String deviceId) => UniversalBle.disconnect(deviceId);
  @override
  Stream<bool> connection(String deviceId) => UniversalBle.connectionStream(deviceId);
  @override
  Future<void> discover(String deviceId) => UniversalBle.discoverServices(deviceId);
  @override
  Future<int> requestMtu(String deviceId, int mtu) => UniversalBle.requestMtu(deviceId, mtu);
  @override
  Future<bool?> isPaired(String deviceId) => UniversalBle.isPaired(deviceId);
  @override
  Future<void> pair(String deviceId) => UniversalBle.pair(deviceId, timeout: const Duration(seconds: 60));
  @override
  Future<Uint8List> read(String deviceId, String char) => UniversalBle.read(deviceId, spikeServiceUuid, char);
  @override
  Future<void> write(String deviceId, String char, Uint8List value, {bool withoutResponse = false}) =>
      UniversalBle.write(deviceId, spikeServiceUuid, char, value, withoutResponse: withoutResponse);
  @override
  Future<void> subscribe(String deviceId, String char) =>
      UniversalBle.subscribeNotifications(deviceId, spikeServiceUuid, char);
  @override
  Stream<Uint8List> values(String deviceId, String char) => UniversalBle.characteristicValueStream(deviceId, char);
}

class BleLinkError implements Exception {
  const BleLinkError(this.code, [this.message = '']);
  final String code; // permission | bluetooth_off | connect | not_spike | pairing | subscribe
  final String message;
  @override
  String toString() => 'BleLinkError($code: $message)';
}

/// One connected, bonded robot, carrying framed JSON messages.
class BleRobotPipe implements RobotPipe {
  BleRobotPipe(this._api, this.deviceId, this.name, this.attMtu) {
    _valSub = _api.values(deviceId, spikeTxUuid).listen(_onFrame);
    _connSub = _api.connection(deviceId).listen((up) {
      if (!up) _finish();
    });
  }

  final BleApi _api;
  final String deviceId;
  final String name;
  final int attMtu;
  final _enc = BleFrameEncoder();
  final _dec = BleFrameDecoder();
  final _in = StreamController<String>.broadcast();
  final _closed = Completer<void>();
  StreamSubscription<Uint8List>? _valSub;
  StreamSubscription<bool>? _connSub;
  Future<void> _writes = Future.value(); // one message's frames at a time, in order

  @override
  String get link => 'ble';
  @override
  String get label => '$name over Bluetooth';
  @override
  Stream<String> get incoming => _in.stream;
  @override
  int get maxMessage => bleMaxMessage;
  @override
  Future<void> get closed => _closed.future;

  void _onFrame(Uint8List f) {
    final m = _dec.feed(f);
    if (m == null) return;
    try {
      _in.add(utf8.decode(m));
    } catch (_) {
      // not UTF-8: dropped like any bad message
    }
  }

  @override
  Future<bool> send(String json) {
    if (_closed.isCompleted) return Future.value(false);
    final bytes = utf8.encode(json);
    if (bytes.length > bleMaxMessage) return Future.value(false);
    final frames = _enc.encode(bytes, attMtu);
    final done = Completer<bool>();
    _writes = _writes.then((_) async {
      try {
        for (final f in frames) {
          if (_closed.isCompleted) throw const BleLinkError('closed');
          await _api.write(deviceId, spikeRxUuid, f).timeout(const Duration(seconds: 5));
        }
        done.complete(true);
      } catch (_) {
        done.complete(false);
      }
    });
    return done.future;
  }

  void _finish() {
    if (_closed.isCompleted) return;
    _closed.complete();
    _valSub?.cancel();
    _connSub?.cancel();
    _in.close();
  }

  @override
  Future<void> close() async {
    _finish();
    try {
      await _api.disconnect(deviceId);
    } catch (_) {}
  }
}

class BleRobotLink {
  BleRobotLink([BleApi? api]) : api = api ?? UniversalBleApi();
  final BleApi api;

  /// Permissions are the owner's to grant: this shows Android's own prompt.
  Future<bool> ensurePermissions() async {
    if (await api.hasPermissions()) return true;
    try {
      await api.requestPermissions();
    } catch (_) {
      return false;
    }
    return api.hasPermissions();
  }

  Stream<FoundRobot> scan({Duration timeout = const Duration(seconds: 12)}) => api.scan(timeout);

  /// Connect, find the Spike service, raise the MTU, bond (passkey on Spike's
  /// screen) and subscribe to tx. The robot then starts the session with its hello.
  Future<BleRobotPipe> connect(String deviceId, {String name = 'Spike'}) async {
    if (!await api.hasPermissions()) throw const BleLinkError('permission');
    if (!await api.bluetoothOn()) throw const BleLinkError('bluetooth_off');
    try {
      await api.connect(deviceId);
    } catch (e) {
      throw BleLinkError('connect', e.toString());
    }
    try {
      await api.discover(deviceId);
      var mtu = 23;
      try {
        mtu = await api.requestMtu(deviceId, 517);
      } catch (_) {}
      if (await api.isPaired(deviceId) != true) {
        try {
          await api.pair(deviceId); // Android's dialog: the owner types the passkey on Spike's screen
        } catch (e) {
          throw BleLinkError('pairing', e.toString());
        }
      }
      final pipe = BleRobotPipe(api, deviceId, name, mtu < 23 ? 23 : mtu);
      try {
        await api.subscribe(deviceId, spikeTxUuid);
      } catch (e) {
        await pipe.close();
        throw BleLinkError('subscribe', e.toString());
      }
      return pipe;
    } catch (e) {
      try {
        await api.disconnect(deviceId);
      } catch (_) {}
      rethrow;
    }
  }

  /// The open `info` characteristic: {"pv","fw","device_id","brain"} (readable before pairing).
  Future<Map<String, dynamic>?> readInfo(String deviceId) async {
    try {
      final raw = await api.read(deviceId, spikeInfoUuid);
      final d = jsonDecode(utf8.decode(raw));
      return d is Map<String, dynamic> ? d : null;
    } catch (_) {
      return null;
    }
  }
}
