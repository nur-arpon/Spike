part of 'messages.dart';

// ============================================================ both directions

class PingMsg extends SpikeMessage {
  const PingMsg({super.id, super.re, super.ts});
  @override
  String get type => 'ping';
  @override
  Map<String, Object?> fields() => const {};
}

class PongMsg extends SpikeMessage {
  const PongMsg({super.id, super.re, super.ts});
  @override
  String get type => 'pong';
  @override
  Map<String, Object?> fields() => const {};
}

class ErrorMsg extends SpikeMessage {
  const ErrorMsg({required this.code, this.message, super.id, super.re, super.ts});
  final String code;
  final String? message;
  @override
  String get type => 'error';
  @override
  Map<String, Object?> fields() => {'code': code, 'message': message};
}

/// A type this app does not know (newer brain). Kept for logging only.
class UnknownMessage extends SpikeMessage {
  const UnknownMessage(this.rawType, this.raw, {super.id, super.re, super.ts});
  final String rawType;
  final Map<String, dynamic> raw;
  @override
  String get type => rawType;
  @override
  Map<String, Object?> fields() =>
      {for (final e in raw.entries) if (!const {'v', 'type', 'id', 're', 'ts'}.contains(e.key)) e.key: e.value};
}

// ============================================================ brain -> clients

class BrainHello extends SpikeMessage {
  const BrainHello({
    required this.server,
    required this.version,
    required this.heartbeatS,
    required this.mode,
    this.session,
    this.names = const {},
    this.wakeWords = const {},
    this.audio,
    this.keepalive = false,
    this.voiceSource = false,
    this.voiceStyle,
    super.id,
    super.re,
    super.ts,
  });
  final String server;
  final String version;
  final String? session;
  final num heartbeatS;
  final String mode;
  final Map<String, String> names;
  final Map<String, List<String>> wakeWords;
  final Map<String, dynamic>? audio;

  /// v1.6: this brain understands the app's silent `keepalive` (PROTOCOL.md 10.9).
  final bool keepalive;

  /// v1.7: this brain understands `voice_source` (PROTOCOL.md 10.10).
  final bool voiceSource;

  /// v1.8: the Gemini voice style per character, present only when the brain speaks with Gemini TTS
  /// itself (the desktop light brain, PROTOCOL.md 10.11). Null = it does not take `voice_style`.
  final Map<String, String>? voiceStyle;
  @override
  String get type => 'hello';
  @override
  Map<String, Object?> fields() => {
        'server': server, 'version': version, 'session': session, 'heartbeat_s': heartbeatS, 'mode': mode,
        'names': names, 'wake_words': wakeWords, 'audio': audio, if (keepalive) 'keepalive': true,
        if (voiceSource) 'voice_source': true, if (voiceStyle != null) 'voice_style': voiceStyle,
      };
}

class MoodMsg extends SpikeMessage {
  const MoodMsg({required this.mood, this.holdS, super.id, super.re, super.ts});
  final String mood;
  final num? holdS;
  @override
  String get type => 'mood';
  @override
  Map<String, Object?> fields() => {'mood': mood, 'hold_s': holdS};
}

class ActionMsg extends SpikeMessage {
  const ActionMsg({
    required this.action,
    this.quiet,
    this.direction,
    this.steps,
    this.style,
    this.side,
    this.from,
    super.id,
    super.re,
    super.ts,
  });
  final String action;

  /// v1.2, app -> brain only: true = no spoken line with it.
  final bool? quiet;

  /// v1.4 body actions (PROTOCOL.md 5.2), only meaningful for "walk": "forward" (default) or "back".
  final String? direction;

  /// v1.4: "walk" step count, 1..16 (default 4).
  final int? steps;

  /// v1.4: "walk" gait style ("auto" default, "tiltStep", "rearStep", "march").
  final String? style;

  /// v1.4: "paw" side, "left" (default) or "right".
  final String? side;

  /// v1.4: "paw" starting pose, "stand" (default) or "sit".
  final String? from;
  @override
  String get type => 'action';
  @override
  Map<String, Object?> fields() =>
      {'action': action, 'quiet': quiet, 'direction': direction, 'steps': steps, 'style': style, 'side': side, 'from': from};
}

class EventMsg extends SpikeMessage {
  const EventMsg({required this.event, super.id, super.re, super.ts});
  final String event;
  @override
  String get type => 'event';
  @override
  Map<String, Object?> fields() => {'event': event};
}

class SayMsg extends SpikeMessage {
  const SayMsg({
    required this.utt,
    required this.seq,
    required this.isFinal,
    required this.text,
    required this.durationMs,
    this.mood,
    this.audio,
    this.mouth,
    this.play = false,
    super.id,
    super.re,
    super.ts,
  });
  final String utt;
  final int seq;
  final bool isFinal;
  final String text;
  final String? mood;
  final int durationMs;
  final Map<String, dynamic>? audio;
  final Map<String, dynamic>? mouth;

  /// v1.5 (PROTOCOL.md 10.8): THIS phone plays the segment (the audio that follows,
  /// or its own voice when `audio` is null). Absent: someone else plays it.
  final bool play;

  /// The end marker of PROTOCOL.md 5.4: nothing to show or play.
  bool get isEndMarker => text.isEmpty && isFinal && audio == null;
  @override
  String get type => 'say';
  @override
  Map<String, Object?> toJson({int? id, int? re, num? ts}) =>
      super.toJson(id: id, re: re, ts: ts)..['audio'] = audio; // audio is required even when null
  @override
  Map<String, Object?> fields() => {
        'utt': utt, 'seq': seq, 'final': isFinal, 'text': text, 'mood': mood, 'duration_ms': durationMs,
        'mouth': mouth, 'play': play ? true : null,
      };
}

class SayAudioMsg extends SpikeMessage {
  const SayAudioMsg({
    required this.utt,
    required this.seq,
    required this.index,
    required this.last,
    required this.data,
    super.id,
    super.re,
    super.ts,
  });
  final String utt;
  final int seq;
  final int index;
  final bool last;
  final String data;
  @override
  String get type => 'say_audio';
  @override
  Map<String, Object?> fields() => {'utt': utt, 'seq': seq, 'index': index, 'last': last, 'data': data};
}

class StopSpeakingMsg extends SpikeMessage {
  const StopSpeakingMsg({this.utt, super.id, super.re, super.ts});
  final String? utt;
  @override
  String get type => 'stop_speaking';
  @override
  Map<String, Object?> fields() => {'utt': utt};
}

class ListeningMsg extends SpikeMessage {
  const ListeningMsg({required this.state, super.id, super.re, super.ts});
  final String state;
  @override
  String get type => 'listening';
  @override
  Map<String, Object?> fields() => {'state': state};
}

class LookAtMsg extends SpikeMessage {
  const LookAtMsg({required this.x, required this.y, this.source, super.id, super.re, super.ts});
  final num x;
  final num y;
  final String? source;
  @override
  String get type => 'look_at';
  @override
  Map<String, Object?> fields() => {'x': x, 'y': y, 'source': source};
}

class SoundMsg extends SpikeMessage {
  const SoundMsg({required this.sound, super.id, super.re, super.ts});
  final String sound;
  @override
  String get type => 'sound';
  @override
  Map<String, Object?> fields() => {'sound': sound};
}

class AlarmMsg extends SpikeMessage {
  const AlarmMsg({required this.state, this.alarmId, this.level, this.label, this.until, super.id, super.re, super.ts});
  final int? alarmId;
  final String state;
  final int? level;
  final String? label;
  final num? until;
  @override
  String get type => 'alarm';
  @override
  Map<String, Object?> fields() =>
      {'alarm_id': alarmId, 'state': state, 'level': level, 'label': label, 'until': until};
}

class GameMsg extends SpikeMessage {
  const GameMsg({
    required this.phase,
    this.game = 'rps',
    this.count,
    this.owner,
    this.robot,
    this.result,
    this.score,
    super.id,
    super.re,
    super.ts,
  });
  final String game;
  final String phase;
  final int? count;
  final String? owner;
  final String? robot;
  final String? result;
  final Map<String, dynamic>? score;
  @override
  String get type => 'game';
  @override
  Map<String, Object?> fields() => {
        'game': game, 'phase': phase, 'count': count, 'owner': owner, 'robot': robot, 'result': result,
        'score': score,
      };
}

class SetModeMsg extends SpikeMessage {
  const SetModeMsg({required this.mode, this.quiet, super.id, super.re, super.ts});
  final String mode;

  /// v1.2, app -> brain only: true = switch without the spoken announcement.
  final bool? quiet;
  @override
  String get type => 'set_mode';
  @override
  Map<String, Object?> fields() => {'mode': mode, 'quiet': quiet};
}

class SetRecipeMsg extends SpikeMessage {
  const SetRecipeMsg({required this.mode, this.code, this.recipe, super.id, super.re, super.ts});
  final String mode;
  final String? code;
  final Map<String, dynamic>? recipe;
  @override
  String get type => 'set_recipe';
  @override
  Map<String, Object?> fields() => {'mode': mode, 'code': code, 'recipe': recipe};
}

// ============================================================ clients -> brain

class ClientHello extends SpikeMessage {
  const ClientHello({
    required this.role,
    required this.deviceId,
    required this.fw,
    required this.caps,
    this.audioOut,
    this.token,
    this.link,
    super.id,
    super.re,
    super.ts,
  });
  final String role;
  final String deviceId;
  final String fw;
  final List<String> caps;
  final Map<String, dynamic>? audioOut;
  final String? token;

  /// v1.3 (PROTOCOL.md 11.3, 11.5): the pipe a robot board says hello on, `ble` or `hotspot`.
  final String? link;
  @override
  String get type => 'hello';
  @override
  Map<String, Object?> fields() => {
        'role': role, 'device_id': deviceId, 'fw': fw, 'caps': caps, 'audio_out': audioOut,
        'token': (token == null || token!.isEmpty) ? null : token, 'link': link,
      };
}

class TouchMsg extends SpikeMessage {
  const TouchMsg({required this.zone, this.gesture = 'tap', super.id, super.re, super.ts});
  final String zone;
  final String gesture;
  @override
  String get type => 'touch';
  @override
  Map<String, Object?> fields() => {'zone': zone, 'gesture': gesture};
}

class ImuMsg extends SpikeMessage {
  const ImuMsg({required this.event, super.id, super.re, super.ts});
  final String event;
  @override
  String get type => 'imu';
  @override
  Map<String, Object?> fields() => {'event': event};
}

class EdgeMsg extends SpikeMessage {
  const EdgeMsg({required this.sensor, required this.state, super.id, super.re, super.ts});
  final String sensor;
  final String state;
  @override
  String get type => 'edge';
  @override
  Map<String, Object?> fields() => {'sensor': sensor, 'state': state};
}

class BatteryMsg extends SpikeMessage {
  const BatteryMsg({required this.percent, this.volts, this.charging, super.id, super.re, super.ts});
  final num percent;
  final num? volts;
  final bool? charging;
  @override
  String get type => 'battery';
  @override
  Map<String, Object?> fields() => {'percent': percent, 'volts': volts, 'charging': charging};
}

class MoodStateMsg extends SpikeMessage {
  const MoodStateMsg({this.mood, this.mode, this.action, super.id, super.re, super.ts});
  final String? mood;
  final String? mode;
  final String? action;
  @override
  String get type => 'mood_state';
  @override
  Map<String, Object?> fields() => {'mood': mood, 'mode': mode, 'action': action};
}

class SayStateMsg extends SpikeMessage {
  const SayStateMsg({required this.utt, required this.state, this.seq, super.id, super.re, super.ts});
  final String utt;
  final int? seq;
  final String state;
  @override
  String get type => 'say_state';
  @override
  Map<String, Object?> fields() => {'utt': utt, 'seq': seq, 'state': state};
}

class AudioMsg extends SpikeMessage {
  const AudioMsg({required this.data, this.rate = 16000, this.seq, this.format = 'pcm_s16le', this.endSilenceMs, super.id, super.re, super.ts});
  final String data;
  final int rate;
  final int? seq;
  final String format;

  /// v1.2 app mic (6.7): the silence that ends a request on this stream ("Wait before Spike answers").
  final int? endSilenceMs;
  @override
  String get type => 'audio';
  @override
  Map<String, Object?> fields() => {'seq': seq, 'rate': rate, 'format': format, 'end_silence_ms': endSilenceMs, 'data': data};
}

class CameraMsg extends SpikeMessage {
  const CameraMsg({required this.data, this.seq, this.format = 'jpeg', this.width, this.height, super.id, super.re, super.ts});
  final String data;
  final int? seq;
  final String format;
  final int? width;
  final int? height;
  @override
  String get type => 'camera';
  @override
  Map<String, Object?> fields() =>
      {'seq': seq, 'format': format, 'width': width, 'height': height, 'data': data};
}

class TextMsg extends SpikeMessage {
  const TextMsg({required this.text, super.id, super.re, super.ts});
  final String text;
  @override
  String get type => 'text';
  @override
  Map<String, Object?> fields() => {'text': text};
}

class AlarmAckMsg extends SpikeMessage {
  const AlarmAckMsg({required this.action, super.id, super.re, super.ts});
  final String action; // stop | snooze
  @override
  String get type => 'alarm_ack';
  @override
  Map<String, Object?> fields() => {'action': action};
}

class LogMsg extends SpikeMessage {
  const LogMsg({required this.msg, this.level, super.id, super.re, super.ts});
  final String msg;
  final String? level;
  @override
  String get type => 'log';
  @override
  Map<String, Object?> fields() => {'level': level, 'msg': msg};
}

// ============================================================ v1.2: the phone app (PROTOCOL.md section 10)

/// Wheels (10.3). Both directions: app -> brain, brain -> robot.
class DriveMsg extends SpikeMessage {
  const DriveMsg({required this.x, required this.y, this.ttlMs = 300, super.id, super.re, super.ts});
  final num x; // turn -1 (left) .. 1 (right)
  final num y; // speed -1 (back) .. 1 (forward)
  final int ttlMs; // dead man's switch
  @override
  String get type => 'drive';
  @override
  Map<String, Object?> fields() => {'x': x, 'y': y, 'ttl_ms': ttlMs};
}

/// Caption bubbles on the robot's screen (10.2).
class SetDisplayMsg extends SpikeMessage {
  const SetDisplayMsg({required this.captions, super.id, super.re, super.ts});
  final bool captions;
  @override
  String get type => 'set_display';
  @override
  Map<String, Object?> fields() => {'captions': captions};
}

class TimersGetMsg extends SpikeMessage {
  const TimersGetMsg({super.id, super.re, super.ts});
  @override
  String get type => 'timers_get';
  @override
  Map<String, Object?> fields() => const {};
}

/// One alarm or reminder as the brain keeps it.
class TimerItem {
  const TimerItem({required this.id, required this.kind, required this.due, this.label = '', this.repeat, this.state = 'active'});
  final int id;
  final String kind; // alarm | reminder
  final int due; // Unix seconds
  final String label;
  final String? repeat; // null | daily
  final String state; // active | snoozed | ringing
  DateTime get dueAt => DateTime.fromMillisecondsSinceEpoch(due * 1000);
  Map<String, Object?> toJson() => {'id': id, 'kind': kind, 'due': due, 'label': label, 'repeat': repeat, 'state': state};
  static TimerItem? fromJson(Object? o) {
    if (o is! Map || o['id'] is! int || o['due'] is! num) return null;
    final kind = o['kind'] == 'reminder' ? 'reminder' : 'alarm';
    return TimerItem(
      id: o['id'] as int, kind: kind, due: (o['due'] as num).toInt(),
      label: o['label'] is String ? o['label'] as String : '',
      repeat: o['repeat'] is String && (o['repeat'] as String).isNotEmpty ? o['repeat'] as String : null,
      state: o['state'] is String ? o['state'] as String : 'active',
    );
  }
}

class TimersMsg extends SpikeMessage {
  const TimersMsg({required this.items, super.id, super.re, super.ts});
  final List<TimerItem> items;
  @override
  String get type => 'timers';
  @override
  Map<String, Object?> fields() => {'items': [for (final t in items) t.toJson()]};
}

class TimerSetMsg extends SpikeMessage {
  const TimerSetMsg({required this.kind, required this.due, this.label, this.repeat = '', super.id, super.re, super.ts});
  final String kind;
  final int due;
  final String? label;
  final String repeat; // '' | daily
  @override
  String get type => 'timer_set';
  @override
  Map<String, Object?> fields() => {'kind': kind, 'due': due, 'label': label, 'repeat': repeat};
}

class TimerCancelMsg extends SpikeMessage {
  const TimerCancelMsg({required this.timerId, super.id, super.re, super.ts});
  final int timerId;
  @override
  String get type => 'timer_cancel';
  @override
  Map<String, Object?> fields() => {'timer_id': timerId};
}

class MemoryGetMsg extends SpikeMessage {
  const MemoryGetMsg({super.id, super.re, super.ts});
  @override
  String get type => 'memory_get';
  @override
  Map<String, Object?> fields() => const {};
}

/// One thing Spike remembers about the owner.
class MemoryItem {
  const MemoryItem({required this.id, required this.text, this.kind = 'fact', this.at = 0});
  final int id;
  final String text;
  final String kind; // fact | preference | birthday | commitment | person | name
  final int at; // Unix seconds
  Map<String, Object?> toJson() => {'id': id, 'text': text, 'kind': kind, 'at': at};
  static MemoryItem? fromJson(Object? o) {
    if (o is! Map || o['id'] is! int || o['text'] is! String) return null;
    return MemoryItem(id: o['id'] as int, text: o['text'] as String,
        kind: o['kind'] is String ? o['kind'] as String : 'fact', at: o['at'] is num ? (o['at'] as num).toInt() : 0);
  }
}

class MemoryMsg extends SpikeMessage {
  const MemoryMsg({required this.items, this.total, super.id, super.re, super.ts});
  final List<MemoryItem> items;
  final int? total;
  @override
  String get type => 'memory';
  @override
  Map<String, Object?> fields() => {'items': [for (final m in items) m.toJson()], 'total': total};
}

class MemoryForgetMsg extends SpikeMessage {
  const MemoryForgetMsg({required this.factId, super.id, super.re, super.ts});
  final int factId;
  @override
  String get type => 'memory_forget';
  @override
  Map<String, Object?> fields() => {'fact_id': factId};
}

class MemoryForgetAllMsg extends SpikeMessage {
  const MemoryForgetAllMsg({super.id, super.re, super.ts});
  @override
  String get type => 'memory_forget_all';
  @override
  Map<String, Object?> fields() => const {'confirm': true};
}

class CameraSubscribeMsg extends SpikeMessage {
  const CameraSubscribeMsg({this.fps = 5, super.id, super.re, super.ts});
  final num fps;
  @override
  String get type => 'camera_subscribe';
  @override
  Map<String, Object?> fields() => {'fps': fps};
}

class CameraUnsubscribeMsg extends SpikeMessage {
  const CameraUnsubscribeMsg({super.id, super.re, super.ts});
  @override
  String get type => 'camera_unsubscribe';
  @override
  Map<String, Object?> fields() => const {};
}

class RobotStatusMsg extends SpikeMessage {
  const RobotStatusMsg({required this.online, this.boards = const [], this.drive = false, this.camera = false, super.id, super.re, super.ts});
  final bool online; // a robot board is connected (not just the simulator)
  final List<String> boards;
  final bool drive;
  final bool camera;
  bool get simulator => boards.contains('simulator');
  @override
  String get type => 'robot_status';
  @override
  Map<String, Object?> fields() => {'online': online, 'boards': boards, 'drive': drive, 'camera': camera};
}

class BrainStatusMsg extends SpikeMessage {
  const BrainStatusMsg({required this.llm, super.id, super.re, super.ts});
  final String llm; // ready | warming | asleep | off
  @override
  String get type => 'brain_status';
  @override
  Map<String, Object?> fields() => {'llm': llm};
}

/// What the owner said or typed to Spike (for Talk).
class HeardMsg extends SpikeMessage {
  const HeardMsg({required this.text, this.via, this.mine = false, super.id, super.re, super.ts});
  final String text;
  final String? via;
  final bool mine; // this phone typed it
  @override
  String get type => 'heard';
  @override
  Map<String, Object?> fields() => {'text': text, 'via': via, 'mine': mine};
}

/// v1.6, app -> brain: "the mic session is open and I am quiet": keeps the language model warm and an
/// open listening window open, silently (no face event, no sound). Only for a brain whose hello says
/// `keepalive` (PROTOCOL.md 10.9).
class KeepaliveMsg extends SpikeMessage {
  const KeepaliveMsg({this.warm = true, super.id, super.re, super.ts});
  final bool warm;
  @override
  String get type => 'keepalive';
  @override
  Map<String, Object?> fields() => {'warm': warm};
}

/// `voice_source` (v1.7, PROTOCOL.md 10.10): who voices the replies this phone plays.
/// "phone": the brain sends each sentence as text only (`play: true`, `audio: null`) and the
/// phone speaks it (Gemini TTS first); "laptop": the brain's own voice, as in v1.5.
class VoiceSourceMsg extends SpikeMessage {
  const VoiceSourceMsg({required this.voice, super.id, super.re, super.ts});
  final String voice; // phone | laptop
  @override
  String get type => 'voice_source';
  @override
  Map<String, Object?> fields() => {'voice': voice};
}

/// `voice_style` (v1.8, PROTOCOL.md 10.11). App -> brain: [mode] + [style] (the owner's pick for one
/// character). Brain -> app: [styles], every character's pick, after any change.
class VoiceStyleMsg extends SpikeMessage {
  const VoiceStyleMsg({this.mode, this.style, this.styles, super.id, super.re, super.ts});
  final String? mode; // dog | cat (app -> brain)
  final String? style; // e.g. energetic, street, sassy, caring (app -> brain)
  final Map<String, String>? styles; // brain -> app
  @override
  String get type => 'voice_style';
  @override
  Map<String, Object?> fields() => {'mode': mode, 'style': style, 'styles': styles};
}

class PairingGetMsg extends SpikeMessage {
  const PairingGetMsg({super.id, super.re, super.ts});
  @override
  String get type => 'pairing_get';
  @override
  Map<String, Object?> fields() => const {};
}

class PairingMsg extends SpikeMessage {
  const PairingMsg({required this.lan, required this.url, super.id, super.re, super.ts});
  final bool lan;
  final String url;
  @override
  String get type => 'pairing';
  @override
  Map<String, Object?> fields() => {'lan': lan, 'url': url};
}

// ============================================================ v1.3: away from home (PROTOCOL.md section 11)

/// Phone -> robot over BLE only (11.5): join the phone's hotspot.
class HotspotJoinMsg extends SpikeMessage {
  const HotspotJoinMsg({required this.ssid, required this.pass, required this.port, required this.token,
      this.host = '', super.id, super.re, super.ts});
  final String ssid;
  final String pass;
  final int port;
  final String token;
  final String host; // '' = the Wi-Fi gateway (the phone)
  @override
  String get type => 'hotspot_join';
  @override
  Map<String, Object?> fields() => {'ssid': ssid, 'pass': pass, 'port': port, 'token': token, 'host': host};
}

class HotspotLeaveMsg extends SpikeMessage {
  const HotspotLeaveMsg({super.id, super.re, super.ts});
  @override
  String get type => 'hotspot_leave';
  @override
  Map<String, Object?> fields() => const {};
}

/// Robot -> phone (11.5): joining | joined (ip) | failed (reason) | left.
class HotspotStateMsg extends SpikeMessage {
  const HotspotStateMsg({required this.state, this.ip, this.reason, super.id, super.re, super.ts});
  final String state;
  final String? ip;
  final String? reason;
  @override
  String get type => 'hotspot_state';
  @override
  Map<String, Object?> fields() => {'state': state, 'ip': ip, 'reason': reason};
}

/// Robot -> phone (11.4): whose commands the robot follows, and its Wi-Fi.
class RobotLinkMsg extends SpikeMessage {
  const RobotLinkMsg({required this.brain, this.wifi = 'off', this.ip = '', this.camera, super.id, super.re, super.ts});
  final String brain; // lan | ble | hotspot | none
  final String wifi; // home | hotspot | off
  final String ip;
  final bool? camera;
  @override
  String get type => 'robot_link';
  @override
  Map<String, Object?> fields() => {'brain': brain, 'wifi': wifi, 'ip': ip, 'camera': camera};
}

/// Phone -> robot (11.6): the camera board has reached the phone.
class RobotLinkAckMsg extends SpikeMessage {
  const RobotLinkAckMsg({required this.camera, super.id, super.re, super.ts});
  final bool camera;
  @override
  String get type => 'robot_link_ack';
  @override
  Map<String, Object?> fields() => {'camera': camera};
}
