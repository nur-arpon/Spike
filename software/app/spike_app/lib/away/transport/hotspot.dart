/// The phone's hotspot for Spike's camera (PROTOCOL.md 11.5).
///
/// First choice: Android's LocalOnlyHotspot (`LocalHotspot.kt` over the
/// `spike/hotspot` channel): the app can start and stop it itself, the OS picks
/// a fresh name and password each time, and it has no internet (the robot only
/// needs the phone). It is not always possible: some phones put it on 5 GHz
/// (the ESP32-S3 only has 2.4 GHz), it fails while the normal tethering hotspot
/// is on, and some phones refuse it. Then the fallback: the owner's own
/// personal hotspot, turned on by the owner once, whose name and password the
/// app keeps in the Android keystore ([ManualHotspot]).
library;

import 'dart:async';

import 'package:flutter/services.dart';

class HotspotInfo {
  const HotspotInfo({required this.ssid, required this.pass, this.band = 'unknown', this.manual = false});
  final String ssid;
  final String pass;
  final String band; // 2.4 | 5 | 6 | any | unknown
  final bool manual; // the owner's own personal hotspot

  /// The robot can only join 2.4 GHz.
  bool get robotCanJoin => band != '5' && band != '6';
}

class HotspotError implements Exception {
  const HotspotError(this.code, [this.message = '']);
  final String code; // permission | incompatible_mode | no_channel | disallowed | generic | busy | band | unsupported
  final String message;
  @override
  String toString() => 'HotspotError($code: $message)';
}

abstract class PhoneHotspot {
  Future<bool> requestPermission();
  Future<HotspotInfo> start();
  Future<void> stop();
  Stream<String> get stopped; // "stopped" or a failure reason, while it was up
}

class LocalOnlyHotspot implements PhoneHotspot {
  static const _m = MethodChannel('spike/hotspot');
  static const _e = EventChannel('spike/hotspot/events');
  Stream<String>? _stopped;

  @override
  Future<bool> requestPermission() async {
    try {
      return await _m.invokeMethod<bool>('requestPermission') ?? false;
    } on MissingPluginException {
      return false;
    }
  }

  @override
  Future<HotspotInfo> start() async {
    try {
      final r = await _m.invokeMapMethod<String, Object?>('start');
      final ssid = r?['ssid'] as String?;
      final pass = r?['pass'] as String?;
      if (ssid == null || ssid.isEmpty || pass == null || pass.length < 8) {
        throw const HotspotError('generic', 'no name or password from Android');
      }
      final info = HotspotInfo(ssid: ssid, pass: pass, band: (r?['band'] as String?) ?? 'unknown');
      if (!info.robotCanJoin) {
        await stop();
        throw const HotspotError('band', 'the phone made a 5 GHz hotspot');
      }
      return info;
    } on PlatformException catch (e) {
      throw HotspotError(e.code, e.message ?? '');
    } on MissingPluginException {
      throw const HotspotError('unsupported');
    }
  }

  @override
  Future<void> stop() async {
    try {
      await _m.invokeMethod('stop');
    } catch (_) {}
  }

  @override
  Stream<String> get stopped => _stopped ??= _e
      .receiveBroadcastStream()
      .map((e) => e is Map ? (e['event'] == 'failed' ? (e['reason'] ?? 'failed').toString() : 'stopped') : 'stopped')
      .asBroadcastStream();
}

/// The owner's own personal hotspot (saved name + password): the app cannot
/// switch it on, so [start] only checks that details are saved.
class ManualHotspot implements PhoneHotspot {
  ManualHotspot(this.load);
  final Future<(String, String)?> Function() load;

  @override
  Future<bool> requestPermission() async => true;

  @override
  Future<HotspotInfo> start() async {
    final d = await load();
    if (d == null || d.$1.isEmpty || d.$2.length < 8) throw const HotspotError('manual_missing');
    return HotspotInfo(ssid: d.$1, pass: d.$2, manual: true);
  }

  @override
  Future<void> stop() async {}

  @override
  Stream<String> get stopped => const Stream.empty();
}
