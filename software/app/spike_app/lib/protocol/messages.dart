/// Typed messages for Spike protocol v1 (software/protocol/PROTOCOL.md).
///
/// Every message type in both directions has a class here with `fields()`
/// (encode) and a decoder branch in [SpikeMessage.fromJson]. The envelope
/// (`v`, `type`, `id`, `re`, `ts`) is added by [SpikeMessage.toJson]; the
/// connection assigns `id`. Unknown fields are ignored; unknown types decode
/// to [UnknownMessage] (the spec's forward-compatibility rules).
library;

import 'dart:convert';

import 'names.dart' as n;

part 'message_types.dart';

/// Who sent a message: decides how `hello` (the only type whose shape
/// differs per direction) is decoded.
enum Sender { brain, client }

class ProtocolException implements Exception {
  ProtocolException(this.code, this.message);
  final String code; // one of names.errorCodes
  final String message;
  @override
  String toString() => 'ProtocolException($code): $message';
}

sealed class SpikeMessage {
  const SpikeMessage({this.id, this.re, this.ts});

  /// Envelope fields as received (null on messages we build to send).
  final int? id;
  final int? re;
  final num? ts;

  String get type;
  Map<String, Object?> fields();

  Map<String, Object?> toJson({int? id, int? re, num? ts}) {
    final out = <String, Object?>{'v': n.protocolVersion, 'type': type, 'id': id ?? this.id ?? 0};
    final r = re ?? this.re;
    if (r != null) out['re'] = r;
    final t = ts ?? this.ts;
    if (t != null) out['ts'] = t;
    fields().forEach((k, v) {
      if (v != null) out[k] = v;
    });
    return out;
  }

  String encode({int? id, int? re, num? ts}) => jsonEncode(toJson(id: id, re: re, ts: ts));

  static SpikeMessage decode(String text, {required Sender from}) {
    final Object? raw;
    try {
      raw = jsonDecode(text);
    } on FormatException catch (e) {
      throw ProtocolException('bad_json', 'not JSON: ${e.message}');
    }
    if (raw is! Map<String, dynamic>) throw ProtocolException('bad_json', 'a message must be a JSON object');
    return fromJson(raw, from: from);
  }

  static SpikeMessage fromJson(Map<String, dynamic> m, {required Sender from}) {
    if (!m.containsKey('v') || !m.containsKey('type')) {
      throw ProtocolException('missing_field', "missing 'v' or 'type'");
    }
    if (m['v'] != n.protocolVersion) {
      throw ProtocolException('version_mismatch', 'protocol v${m['v']} not supported (this is v1)');
    }
    final type = m['type'];
    if (type is! String) throw ProtocolException('bad_value', "'type' must be a string");
    final idRaw = m['id'];
    if (idRaw != null && idRaw is! int) throw ProtocolException('bad_value', "'id' must be an integer");
    final f = _F(m, type);
    final id = idRaw as int?;
    final re = f.intOpt('re');
    final ts = f.numOpt('ts');
    switch (type) {
      case 'hello':
        if (from == Sender.brain) {
          return BrainHello(
            id: id, re: re, ts: ts,
            server: f.str('server'), version: f.str('version'), session: f.strOpt('session'),
            heartbeatS: f.num_('heartbeat_s'), mode: f.str('mode', n.modes),
            names: f.stringMap('names'), wakeWords: f.stringListMap('wake_words'),
            audio: f.mapOpt('audio'), keepalive: f.boolOpt('keepalive') ?? false,
            voiceSource: f.boolOpt('voice_source') ?? false,
            voiceStyle: m.containsKey('voice_style') && m['voice_style'] != null ? f.stringMap('voice_style') : null,
          );
        }
        return ClientHello(
          id: id, re: re, ts: ts,
          role: f.str('role', n.roles), deviceId: f.str('device_id'), fw: f.str('fw'),
          caps: f.strList('caps'), audioOut: f.mapOpt('audio_out'), token: f.strOpt('token'),
          link: f.strOpt('link'),
        );
      case 'ping':
        return PingMsg(id: id, re: re, ts: ts);
      case 'pong':
        return PongMsg(id: id, re: re, ts: ts);
      case 'error':
        return ErrorMsg(id: id, re: re, ts: ts, code: f.str('code'), message: f.strOpt('message'));
      // ------------------------------------------------ brain -> robot
      case 'mood':
        return MoodMsg(id: id, re: re, ts: ts, mood: f.str('mood', n.moods), holdS: f.numOpt('hold_s'));
      case 'action':
        final steps = f.intOpt('steps');
        if (steps != null && !n.actionSteps.contains(steps)) {
          throw ProtocolException('bad_value', "action.steps: '$steps' is not allowed");
        }
        return ActionMsg(
          id: id, re: re, ts: ts, action: f.str('action', n.actions), quiet: f.boolOpt('quiet'),
          direction: f.strOpt('direction', n.actionDirections), steps: steps,
          style: f.strOpt('style', n.actionStyles), side: f.strOpt('side', n.actionSides),
          from: f.strOpt('from', n.actionFroms),
        );
      case 'event':
        return EventMsg(id: id, re: re, ts: ts, event: f.str('event', n.events));
      case 'say':
        return SayMsg(
          id: id, re: re, ts: ts,
          utt: f.str('utt'), seq: f.int_('seq'), isFinal: f.bool_('final'), text: f.str('text'),
          mood: f.strOpt('mood'), durationMs: f.int_('duration_ms'),
          audio: f.nullableMap('audio', required: true), mouth: f.nullableMap('mouth'),
          play: f.boolOpt('play') ?? false,
        );
      case 'say_audio':
        return SayAudioMsg(
          id: id, re: re, ts: ts, utt: f.str('utt'), seq: f.int_('seq'), index: f.int_('index'),
          last: f.bool_('last'), data: f.str('data'),
        );
      case 'stop_speaking':
        return StopSpeakingMsg(id: id, re: re, ts: ts, utt: f.strOpt('utt'));
      case 'listening':
        return ListeningMsg(id: id, re: re, ts: ts, state: f.str('state', n.listenStates));
      case 'look_at':
        return LookAtMsg(id: id, re: re, ts: ts, x: f.num_('x'), y: f.num_('y'), source: f.strOpt('source'));
      case 'sound':
        return SoundMsg(id: id, re: re, ts: ts, sound: f.str('sound', n.sounds));
      case 'alarm':
        return AlarmMsg(
          id: id, re: re, ts: ts, alarmId: f.intOpt('alarm_id'), state: f.str('state', n.alarmStates),
          level: f.intOpt('level'), label: f.strOpt('label'), until: f.numOpt('until'),
        );
      case 'game':
        return GameMsg(
          id: id, re: re, ts: ts, game: f.str('game', const ['rps']), phase: f.str('phase', n.gamePhases),
          count: f.intOpt('count'), owner: f.strOpt('owner'), robot: f.strOpt('robot'),
          result: f.strOpt('result'), score: f.mapOpt('score'),
        );
      case 'set_mode':
        return SetModeMsg(id: id, re: re, ts: ts, mode: f.str('mode', n.modes), quiet: f.boolOpt('quiet'));
      case 'set_recipe':
        return SetRecipeMsg(id: id, re: re, ts: ts, mode: f.str('mode', n.modes), code: f.strOpt('code'),
            recipe: f.mapOpt('recipe'));
      // ------------------------------------------------ robot -> brain
      case 'touch':
        return TouchMsg(id: id, re: re, ts: ts, zone: f.str('zone', n.touchZones),
            gesture: f.strOpt('gesture', n.touchGestures) ?? 'tap');
      case 'imu':
        return ImuMsg(id: id, re: re, ts: ts, event: f.str('event', n.imuEvents));
      case 'edge':
        return EdgeMsg(id: id, re: re, ts: ts, sensor: f.str('sensor', n.edgeSensors),
            state: f.str('state', const ['edge', 'clear']));
      case 'battery':
        return BatteryMsg(id: id, re: re, ts: ts, percent: f.num_('percent'), volts: f.numOpt('volts'),
            charging: f.boolOpt('charging'));
      case 'mood_state':
        return MoodStateMsg(id: id, re: re, ts: ts, mood: f.strOpt('mood', n.moods),
            mode: f.strOpt('mode', n.modes), action: f.strOpt('action'));
      case 'say_state':
        return SayStateMsg(id: id, re: re, ts: ts, utt: f.str('utt'), seq: f.intOpt('seq'),
            state: f.str('state', n.sayStates));
      case 'audio':
        return AudioMsg(id: id, re: re, ts: ts, data: f.str('data'), rate: f.intOpt('rate') ?? 16000,
            seq: f.intOpt('seq'), format: f.strOpt('format', const ['pcm_s16le']) ?? 'pcm_s16le',
            endSilenceMs: f.intOpt('end_silence_ms'));
      case 'camera':
        return CameraMsg(id: id, re: re, ts: ts, data: f.str('data'), seq: f.intOpt('seq'),
            format: f.strOpt('format', const ['jpeg']) ?? 'jpeg', width: f.intOpt('width'), height: f.intOpt('height'));
      case 'text':
        return TextMsg(id: id, re: re, ts: ts, text: f.str('text'));
      case 'alarm_ack':
        return AlarmAckMsg(id: id, re: re, ts: ts, action: f.str('action', const ['stop', 'snooze']));
      case 'log':
        return LogMsg(id: id, re: re, ts: ts, msg: f.str('msg'), level: f.strOpt('level'));
      // ------------------------------------------------ v1.2: the phone app (PROTOCOL.md section 10)
      case 'drive':
        return DriveMsg(id: id, re: re, ts: ts, x: f.num_('x'), y: f.num_('y'), ttlMs: f.intOpt('ttl_ms') ?? 300);
      case 'set_display':
        return SetDisplayMsg(id: id, re: re, ts: ts, captions: f.bool_('captions'));
      case 'timers_get':
        return TimersGetMsg(id: id, re: re, ts: ts);
      case 'timers':
        return TimersMsg(id: id, re: re, ts: ts, items: f.list('items', TimerItem.fromJson));
      case 'timer_set':
        return TimerSetMsg(id: id, re: re, ts: ts, kind: f.str('kind', const ['alarm', 'reminder']),
            due: f.num_('due').toInt(), label: f.strOpt('label'), repeat: f.strOpt('repeat', const ['', 'daily']) ?? '');
      case 'timer_cancel':
        return TimerCancelMsg(id: id, re: re, ts: ts, timerId: f.int_('timer_id'));
      case 'memory_get':
        return MemoryGetMsg(id: id, re: re, ts: ts);
      case 'memory':
        return MemoryMsg(id: id, re: re, ts: ts, items: f.list('items', MemoryItem.fromJson), total: f.intOpt('total'));
      case 'memory_forget':
        return MemoryForgetMsg(id: id, re: re, ts: ts, factId: f.int_('fact_id'));
      case 'memory_forget_all':
        if (f.bool_('confirm') != true) throw ProtocolException('bad_value', "memory_forget_all.confirm: 'false' is not allowed");
        return MemoryForgetAllMsg(id: id, re: re, ts: ts);
      case 'camera_subscribe':
        return CameraSubscribeMsg(id: id, re: re, ts: ts, fps: f.numOpt('fps') ?? 5);
      case 'camera_unsubscribe':
        return CameraUnsubscribeMsg(id: id, re: re, ts: ts);
      case 'robot_status':
        return RobotStatusMsg(id: id, re: re, ts: ts, online: f.bool_('online'), boards: f.strList('boards'),
            drive: f.boolOpt('drive') ?? false, camera: f.boolOpt('camera') ?? false);
      case 'brain_status':
        return BrainStatusMsg(id: id, re: re, ts: ts, llm: f.str('llm'));
      case 'heard':
        return HeardMsg(id: id, re: re, ts: ts, text: f.str('text'), via: f.strOpt('via'), mine: f.boolOpt('mine') ?? false);
      case 'keepalive':
        return KeepaliveMsg(id: id, re: re, ts: ts, warm: f.boolOpt('warm') ?? true);
      case 'voice_source':
        return VoiceSourceMsg(id: id, re: re, ts: ts, voice: f.str('voice', const ['phone', 'laptop']));
      case 'voice_style':
        if (from == Sender.brain) {
          return VoiceStyleMsg(id: id, re: re, ts: ts, styles: f.stringMap('styles'));
        }
        return VoiceStyleMsg(id: id, re: re, ts: ts, mode: f.str('mode', n.modes), style: f.str('style'));
      case 'pairing_get':
        return PairingGetMsg(id: id, re: re, ts: ts);
      case 'pairing':
        return PairingMsg(id: id, re: re, ts: ts, lan: f.bool_('lan'), url: f.str('url'));
      // ------------------------------------------------ v1.3: away from home (PROTOCOL.md section 11)
      case 'hotspot_join':
        final port = f.int_('port');
        if (port < 1 || port > 65535) f._bad('port', port);
        return HotspotJoinMsg(id: id, re: re, ts: ts, ssid: f.str('ssid'), pass: f.str('pass'), port: port,
            token: f.str('token'), host: f.strOpt('host') ?? '');
      case 'hotspot_leave':
        return HotspotLeaveMsg(id: id, re: re, ts: ts);
      case 'hotspot_state':
        return HotspotStateMsg(id: id, re: re, ts: ts,
            state: f.str('state', const ['joining', 'joined', 'failed', 'left']), ip: f.strOpt('ip'),
            reason: f.strOpt('reason'));
      case 'robot_link':
        return RobotLinkMsg(id: id, re: re, ts: ts, brain: f.str('brain', const ['lan', 'ble', 'hotspot', 'none']),
            wifi: f.strOpt('wifi', const ['home', 'hotspot', 'off']) ?? 'off', ip: f.strOpt('ip') ?? '',
            camera: f.boolOpt('camera'));
      case 'robot_link_ack':
        return RobotLinkAckMsg(id: id, re: re, ts: ts, camera: f.bool_('camera'));
      default:
        return UnknownMessage(type, m, id: id, re: re, ts: ts);
    }
  }
}

/// Field reader with the brain's validation rules (protocol.py `validate`).
class _F {
  _F(this.m, this.type);
  final Map<String, dynamic> m;
  final String type;

  Never _missing(String k) => throw ProtocolException('missing_field', "$type: missing '$k'");
  Never _bad(String k, [Object? v]) =>
      throw ProtocolException('bad_value', v == null ? '$type.$k: wrong type' : "$type.$k: '$v' is not allowed");

  String str(String k, [List<String>? allowed]) {
    if (!m.containsKey(k) || m[k] == null) _missing(k);
    return strOpt(k, allowed)!;
  }

  String? strOpt(String k, [List<String>? allowed]) {
    final v = m[k];
    if (v == null) return null;
    if (v is! String) _bad(k);
    if (allowed != null && !allowed.contains(v)) _bad(k, v);
    return v;
  }

  int int_(String k) {
    if (!m.containsKey(k) || m[k] == null) _missing(k);
    return intOpt(k)!;
  }

  int? intOpt(String k) {
    final v = m[k];
    if (v == null) return null;
    if (v is! int) _bad(k);
    return v;
  }

  num num_(String k) {
    if (!m.containsKey(k) || m[k] == null) _missing(k);
    return numOpt(k)!;
  }

  num? numOpt(String k) {
    final v = m[k];
    if (v == null) return null;
    if (v is! num) _bad(k);
    return v;
  }

  bool bool_(String k) {
    if (!m.containsKey(k) || m[k] == null) _missing(k);
    return boolOpt(k)!;
  }

  bool? boolOpt(String k) {
    final v = m[k];
    if (v == null) return null;
    if (v is! bool) _bad(k);
    return v;
  }

  Map<String, dynamic>? mapOpt(String k) {
    final v = m[k];
    if (v == null) return null;
    if (v is! Map) _bad(k);
    return Map<String, dynamic>.from(v);
  }

  /// A field that must be present but may be JSON null (say.audio).
  Map<String, dynamic>? nullableMap(String k, {bool required = false}) {
    if (required && !m.containsKey(k)) _missing(k);
    return mapOpt(k);
  }

  List<String> strList(String k) {
    final v = m[k];
    if (v == null) _missing(k);
    if (v is! List) _bad(k);
    return v.whereType<String>().toList(growable: false);
  }

  /// A required list of objects; entries that are not valid are skipped (forward compatible).
  List<T> list<T>(String k, T? Function(Object?) parse) {
    final v = m[k];
    if (v == null) _missing(k);
    if (v is! List) _bad(k);
    return [for (final e in v) ?parse(e)];
  }

  Map<String, String> stringMap(String k) {
    final v = mapOpt(k) ?? const {};
    return {for (final e in v.entries) if (e.value is String) e.key: e.value as String};
  }

  Map<String, List<String>> stringListMap(String k) {
    final v = mapOpt(k) ?? const {};
    return {
      for (final e in v.entries)
        if (e.value is List) e.key: (e.value as List).whereType<String>().toList(growable: false),
    };
  }
}
