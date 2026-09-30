import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../away/voice/laptop_voice.dart' show audioOutFormats, audioOutRates;
import '../core/capabilities.dart';
import '../core/platform.dart';
import '../core/version.dart';
import '../protocol/client.dart';
import '../protocol/messages.dart';
import 'hub.dart';
import 'settings.dart';

// the app's version comes from pubspec.yaml (lib/core/version.dart, VERSIONING.md)
export '../core/version.dart' show appVersion;

/// The app joins as role `app` (protocol v1.2, PROTOCOL.md section 10) with
/// `face` (so the brain mirrors the face messages to us), `text` (typed talk)
/// and `mic` (push-to-talk). No `speaker` (the robot's cap); since v1.5 the
/// phone plays the voice of its OWN conversations through `audio_out` and
/// reports say_state for those only. A v1.1 brain refuses role `app`; the client then joins as
/// `tool` and [SpikeCommands] falls back to typed words. See DESIGN.md.
const appCaps = ['face', 'text', 'mic', 'audio_out'];

/// The desktop app's caps (no `audio_out`).
const desktopCaps = ['face', 'text', 'mic'];

/// v1.5 (PROTOCOL.md 10.8, owner decision "laptop voice first"): `audio_out` = this phone
/// plays Spike's laptop voice for the conversations that come from it (voice_out.dart).
/// A brain older than v1.5 ignores it and keeps playing on its own speaker.
const appAudioOut = {'formats': audioOutFormats, 'rates': audioOutRates};

/// The one link every screen uses: the laptop brain at home, the phone brain away (hub.dart, away.dart).
final brainClientProvider = Provider<SpikeHub>((ref) {
  final id = ref.read(settingsProvider).deviceId;
  // the desktop app sits next to its brain, which speaks through this computer's speakers (or the robot):
  // no `audio_out` there, so the brain never routes a reply's audio to the app (DESIGN.md "Desktop")
  final desktop = AppPlatform.desktop;
  final c = BrainClient(identity: ClientIdentity(deviceId: id, fw: appVersion, role: 'app', caps: desktop ? desktopCaps : appCaps,
      audioOut: desktop ? null : appAudioOut));
  final hub = SpikeHub(c);
  ref.onDispose(hub.dispose);
  return hub;
});

final linkStatusProvider = StreamProvider<LinkStatus>((ref) async* {
  final c = ref.watch(brainClientProvider);
  yield c.current;
  yield* c.status;
});

/// The laptop link only (the Connect screen), whichever brain the screens see.
final lanStatusProvider = StreamProvider<LinkStatus>((ref) async* {
  final c = ref.watch(brainClientProvider).lan;
  yield c.current;
  yield* c.status;
});

LinkStatus linkNow(Ref ref) => ref.watch(linkStatusProvider).value ?? const LinkStatus();

final brainMessagesProvider = Provider<Stream<SpikeMessage>>((ref) => ref.watch(brainClientProvider).messages);

// ---------------------------------------------------------------- Spike's live state

@immutable
class SpikeState {
  const SpikeState({
    this.mode = 'dog',
    this.mood = 'neutral',
    this.listening = 'idle',
    this.alarmRinging = false,
    this.alarmLabel,
    this.caption,
    this.captionUntil,
    this.game,
    this.battery,
    this.charging = false,
    this.brainNames = const {},
    this.wakeWords = const {},
    this.robotOnline = false,
    this.boards = const [],
    this.robotCamera = false,
    this.robotDrive = false,
    this.llm,
  });
  final String mode;
  final String mood;
  final String listening;
  final bool alarmRinging;
  final String? alarmLabel;
  final String? caption;
  final DateTime? captionUntil;
  final GameMsg? game;

  /// The robot's battery (relayed by a v1.2 brain while the robot is online).
  final double? battery;
  final bool charging;
  final Map<String, String> brainNames;
  final Map<String, List<String>> wakeWords;

  /// v1.2 robot_status: a robot board (not just the simulator) is connected.
  final bool robotOnline;
  final List<String> boards;
  final bool robotCamera;
  final bool robotDrive;

  /// v1.2 brain_status.llm: ready | warming | asleep | off (null = not told).
  final String? llm;

  bool get simulatorOnly => !robotOnline && boards.contains('simulator');

  SpikeState copyWith({
    String? mode,
    String? mood,
    String? listening,
    bool? alarmRinging,
    String? alarmLabel,
    String? caption,
    DateTime? captionUntil,
    bool clearCaption = false,
    GameMsg? game,
    bool clearGame = false,
    double? battery,
    bool clearBattery = false,
    bool? charging,
    Map<String, String>? brainNames,
    Map<String, List<String>>? wakeWords,
    bool? robotOnline,
    List<String>? boards,
    bool? robotCamera,
    bool? robotDrive,
    String? llm,
    bool clearLlm = false,
  }) =>
      SpikeState(
        mode: mode ?? this.mode,
        mood: mood ?? this.mood,
        listening: listening ?? this.listening,
        alarmRinging: alarmRinging ?? this.alarmRinging,
        alarmLabel: alarmLabel ?? this.alarmLabel,
        caption: clearCaption ? null : (caption ?? this.caption),
        captionUntil: clearCaption ? null : (captionUntil ?? this.captionUntil),
        game: clearGame ? null : (game ?? this.game),
        battery: clearBattery ? null : (battery ?? this.battery),
        charging: charging ?? this.charging,
        brainNames: brainNames ?? this.brainNames,
        wakeWords: wakeWords ?? this.wakeWords,
        robotOnline: robotOnline ?? this.robotOnline,
        boards: boards ?? this.boards,
        robotCamera: robotCamera ?? this.robotCamera,
        robotDrive: robotDrive ?? this.robotDrive,
        llm: clearLlm ? null : (llm ?? this.llm),
      );
}

class SpikeStateNotifier extends Notifier<SpikeState> {
  StreamSubscription<SpikeMessage>? _sub;
  StreamSubscription<LinkStatus>? _statusSub;
  Timer? _captionTimer;
  bool _burst = false;
  bool _displaySeen = false;

  @override
  SpikeState build() {
    final c = ref.watch(brainClientProvider);
    _sub = c.messages.listen(_on);
    // the link dropped: what we knew about the robot and the model is stale
    _statusSub = c.status.listen((s) {
      if (!s.isConnected && (state.robotOnline || state.llm != null || state.battery != null)) {
        state = state.copyWith(robotOnline: false, boards: const [], clearBattery: true, clearLlm: true,
            robotCamera: false, robotDrive: false);
      }
    });
    ref.onDispose(() {
      _sub?.cancel();
      _statusSub?.cancel();
      _captionTimer?.cancel();
    });
    return const SpikeState();
  }

  /// The phone face reports mood changes of its own (idle life, pats).
  void localMood(String mood) {
    if (mood != state.mood) state = state.copyWith(mood: mood);
  }

  void localMode(String mode) {
    if (mode != state.mode) state = state.copyWith(mode: mode);
  }

  void _on(SpikeMessage m) {
    switch (m) {
      case BrainHello():
        state = state.copyWith(mode: m.mode, brainNames: m.names, wakeWords: m.wakeWords);
        _burst = true;
        _displaySeen = false;
      case MoodMsg():
        state = state.copyWith(mood: m.mood);
      case SetModeMsg():
        state = state.copyWith(mode: m.mode);
      case ListeningMsg():
        state = state.copyWith(listening: m.state);
      case SayMsg():
        if (m.isEndMarker || m.text.isEmpty) break;
        final hold = Duration(milliseconds: m.durationMs.clamp(1500, 9000) + 900);
        state = state.copyWith(caption: m.text, captionUntil: DateTime.now().add(hold), mood: m.mood);
        _captionTimer?.cancel();
        _captionTimer = Timer(hold, () => state = state.copyWith(clearCaption: true));
      case AlarmMsg():
        state = state.copyWith(alarmRinging: m.state == 'ringing', alarmLabel: m.label);
      case GameMsg():
        state = m.phase == 'end' ? state.copyWith(clearGame: true) : state.copyWith(game: m);
      case RobotStatusMsg():
        state = state.copyWith(robotOnline: m.online, boards: m.boards, robotCamera: m.camera, robotDrive: m.drive,
            clearBattery: !m.online);
      case BatteryMsg():
        state = state.copyWith(battery: m.percent.toDouble(), charging: m.charging ?? false);
      case BrainStatusMsg():
        state = state.copyWith(llm: m.llm);
      case SetDisplayMsg():
        // the brain keeps the captions choice for the robot: it is the truth once set
        _displaySeen = true;
        if (ref.read(settingsProvider).showCaptions != m.captions) {
          ref.read(settingsProvider.notifier).update((s) => s.copyWith(showCaptions: m.captions));
        }
      case MemoryMsg() when _burst:
        // the end of the brain's on-connect burst: a choice made on this phone while
        // offline (captions off) is handed to a brain that has none yet
        _burst = false;
        if (!_displaySeen && !ref.read(settingsProvider).showCaptions) {
          ref.read(brainClientProvider).send(const SetDisplayMsg(captions: false));
        }
      default:
        break;
    }
  }
}

final spikeStateProvider = NotifierProvider<SpikeStateNotifier, SpikeState>(SpikeStateNotifier.new);

// ---------------------------------------------------------------- chat history

enum ChatFrom { me, spike, system }

@immutable
class ChatEntry {
  const ChatEntry({required this.from, required this.text, required this.at, this.mood, this.utt, this.mode, this.voice = false});
  final ChatFrom from;
  final String text;
  final DateTime at;
  final String? mood;
  final String? utt;
  final String? mode;
  final bool voice;
  ChatEntry append(String more, String? newMood) =>
      ChatEntry(from: from, text: '$text $more', at: at, mood: mood ?? newMood, utt: utt, mode: mode, voice: voice);
}

class ChatNotifier extends Notifier<List<ChatEntry>> {
  StreamSubscription<SpikeMessage>? _sub;

  @override
  List<ChatEntry> build() {
    final c = ref.watch(brainClientProvider);
    _sub = c.messages.listen(_on);
    ref.onDispose(() => _sub?.cancel());
    return const [];
  }

  void addMine(String text, {bool voice = false}) =>
      state = [...state, ChatEntry(from: ChatFrom.me, text: text, at: DateTime.now(), voice: voice)];

  void addSystem(String text) => state = [...state, ChatEntry(from: ChatFrom.system, text: text, at: DateTime.now())];

  /// Push-to-talk ended: a "..." bubble until the brain says what it heard
  /// (v1.2 `heard`). If nothing comes (he did not catch it, or an older
  /// brain), it becomes a plain note after a while.
  void addVoice(String name, {bool legacy = false}) {
    final note = '(spoke to $name)';
    if (legacy) {
      addMine(note, voice: true);
      return;
    }
    addMine(voicePlaceholder, voice: true);
    Timer(const Duration(seconds: 12), () {
      final i = state.lastIndexWhere((e) => e.from == ChatFrom.me && e.voice && e.text == voicePlaceholder);
      if (i < 0) return;
      final list = [...state];
      list[i] = ChatEntry(from: ChatFrom.me, text: note, at: list[i].at, voice: true);
      state = list;
    });
  }

  void clear() => state = const [];

  void _on(SpikeMessage m) {
    if (m is HeardMsg) {
      // v1.2: what the owner said out loud (or typed on another device). What this
      // phone typed is already in the chat.
      if (m.mine || m.text.trim().isEmpty) return;
      final list = [...state];
      // push-to-talk leaves a "..." placeholder bubble: the words replace it
      final i = list.lastIndexWhere((e) => e.from == ChatFrom.me && e.voice && e.text == voicePlaceholder);
      final entry = ChatEntry(from: ChatFrom.me, text: m.text, at: DateTime.now(), voice: m.via != 'typed');
      if (i >= 0 && i >= list.length - 2) {
        list[i] = entry;
      } else {
        list.add(entry);
      }
      state = list;
      return;
    }
    if (m is! SayMsg || m.isEndMarker || m.text.trim().isEmpty) return;
    final mode = ref.read(spikeStateProvider).mode;
    final list = [...state];
    // segments of one utterance join into one bubble
    final i = list.lastIndexWhere((e) => e.utt == m.utt && e.from == ChatFrom.spike);
    if (i >= 0 && i == list.length - 1) {
      list[i] = list[i].append(m.text, m.mood);
    } else {
      list.add(ChatEntry(from: ChatFrom.spike, text: m.text, at: DateTime.now(), mood: m.mood, utt: m.utt, mode: mode));
    }
    if (list.length > 300) list.removeRange(0, list.length - 300);
    state = list;
  }
}

/// The bubble push-to-talk shows until the brain says what it heard.
const voicePlaceholder = '…';

final chatProvider = NotifierProvider<ChatNotifier, List<ChatEntry>>(ChatNotifier.new);

// ---------------------------------------------------------------- the brain's lists (v1.2)

@immutable
class BrainList<T> {
  const BrainList({this.items = const [], this.synced = false, this.total, this.at});
  final List<T> items;
  final bool synced; // came from the brain in this connection
  final int? total;
  final DateTime? at;
}

/// Alarms and reminders as the brain keeps them (`timers`, sent on connect
/// and whenever they change). The last list is kept on the phone so it can be
/// shown, greyed, while Spike is away.
class TimersNotifier extends Notifier<BrainList<TimerItem>> {
  static const _k = 'spike.timers.v2';
  StreamSubscription<SpikeMessage>? _sub;
  StreamSubscription<LinkStatus>? _st;

  @override
  BrainList<TimerItem> build() {
    final c = ref.watch(brainClientProvider);
    _sub = c.messages.listen((m) {
      if (m is TimersMsg) {
        state = BrainList(items: m.items, synced: true, at: DateTime.now());
        ref.read(prefsProvider).setString(_k, jsonEncode([for (final t in m.items) t.toJson()]));
      }
    });
    _st = c.status.listen((s) {
      if (!s.isConnected && state.synced) state = BrainList(items: state.items, at: state.at);
    });
    ref.onDispose(() {
      _sub?.cancel();
      _st?.cancel();
    });
    final raw = ref.read(prefsProvider).getString(_k);
    if (raw == null) return const BrainList();
    try {
      final now = DateTime.now();
      return BrainList(items: [
        for (final o in jsonDecode(raw) as List)
          if (TimerItem.fromJson(o) case final t? when t.repeat != null || t.dueAt.isAfter(now)) t,
      ]);
    } catch (_) {
      return const BrainList();
    }
  }
}

final timersProvider = NotifierProvider<TimersNotifier, BrainList<TimerItem>>(TimersNotifier.new);

/// What Spike remembers (`memory`). Never stored on the phone: it is shown only
/// while connected (privacy: the laptop is the one place it lives).
class MemoryNotifier extends Notifier<BrainList<MemoryItem>> {
  StreamSubscription<SpikeMessage>? _sub;
  StreamSubscription<LinkStatus>? _st;

  @override
  BrainList<MemoryItem> build() {
    final c = ref.watch(brainClientProvider);
    _sub = c.messages.listen((m) {
      if (m is MemoryMsg) state = BrainList(items: m.items, synced: true, total: m.total, at: DateTime.now());
    });
    _st = c.status.listen((s) {
      if (!s.isConnected && state.synced) state = const BrainList();
    });
    ref.onDispose(() {
      _sub?.cancel();
      _st?.cancel();
    });
    return const BrainList();
  }
}

final memoryProvider = NotifierProvider<MemoryNotifier, BrainList<MemoryItem>>(MemoryNotifier.new);

/// The robot's camera frames (JPEG bytes), while a screen is subscribed.
final cameraFramesProvider = StreamProvider<Uint8List>((ref) {
  final c = ref.watch(brainClientProvider);
  return c.messages.where((m) => m is CameraMsg).map((m) {
    try {
      return base64Decode((m as CameraMsg).data);
    } catch (_) {
      return Uint8List(0);
    }
  }).where((b) => b.isNotEmpty);
});

// ---------------------------------------------------------------- sending

/// Trick words a v1.1 brain's intent matcher knows (mind/intents.py TRICKS),
/// used only when the brain is too old for `action` from the app.
const legacyTrickWords = {
  'playBow': 'bow', 'zoomies': 'spin', 'beggingAction': 'beg', 'rollOver': 'roll over',
  'tailWagDance': 'dance', 'yawn': 'yawn', 'fallAsleep': 'go to sleep',
  'headTilt': 'tilt your head for me', 'snuggle': 'come and snuggle with me', 'slowWag': 'give me a slow happy wag',
  'sniffAround': 'sniff around', 'sneeze': 'sneeze',
  'walk': 'walk', 'paw': 'give paw',        // v1.4 body actions: an old brain has no gait fields anyway
};

/// Every command the app can send. With a v1.2 brain these are real protocol
/// messages (PROTOCOL.md section 10); with an older brain the few that have no
/// v1.1 message go as the words the owner would say (`text`).
class SpikeCommands {
  SpikeCommands(this._c);
  final SpikeLink _c;

  bool get connected => _c.current.isConnected;
  bool get legacy => _c.legacyBrain;

  bool say(String text) => _c.send(TextMsg(text: text));
  bool touch(String zone, [String gesture = 'tap']) => _c.send(TouchMsg(zone: zone, gesture: gesture));

  /// A pat from the phone. Zone `back`: a head touch would wake the
  /// listener (brain.py on_touch), which a pat must not do.
  bool pat() => touch('back', 'pat');
  bool boop() => touch('nose', 'tap');

  /// Push-to-talk start: a head tap is the protocol's "listen now".
  bool listenNow() => touch('head', 'tap');
  bool alarmStop() => _c.send(const AlarmAckMsg(action: 'stop'));
  bool alarmSnooze() => _c.send(const AlarmAckMsg(action: 'snooze'));

  /// A face_v2 action, or (v1.4) a body action ("walk" / "paw", PROTOCOL.md 5.2). For
  /// tricks Spike also answers out loud ("Ta-da!", owner decision 29 Sep); comfort
  /// actions are silent. The gait fields only mean anything for "walk" / "paw" and are
  /// dropped for a legacy brain, which has no way to use them anyway.
  bool action(String action,
      {bool quiet = false, String? direction, int? steps, String? style, String? side, String? from}) {
    if (!isAvailable(action)) return false; // the body cannot do it (core/capabilities.dart)
    if (legacy) return say(legacyTrickWords[action] ?? action);
    return _c.send(ActionMsg(
      action: action, quiet: quiet ? true : null,
      direction: direction, steps: steps, style: style, side: side, from: from,
    ));
  }

  bool sleep() => action('fallAsleep');

  bool setMode(String mode, {required String catName, required String dogName}) =>
      legacy ? say(mode == 'cat' ? 'switch to cat mode' : 'switch to dog mode') : _c.send(SetModeMsg(mode: mode));

  bool setAlarm(DateTime at, {String? label, bool daily = false}) => _c.send(TimerSetMsg(
      kind: 'alarm', due: at.millisecondsSinceEpoch ~/ 1000, label: label, repeat: daily ? 'daily' : ''));

  bool setReminder(String what, DateTime at) =>
      _c.send(TimerSetMsg(kind: 'reminder', due: at.millisecondsSinceEpoch ~/ 1000, label: what));

  bool cancelTimer(int id) => _c.send(TimerCancelMsg(timerId: id));
  bool refreshTimers() => _c.send(const TimersGetMsg());
  bool refreshMemory() => _c.send(const MemoryGetMsg());
  bool forgetFact(int id) => _c.send(MemoryForgetMsg(factId: id));
  bool forgetEverything() => _c.send(const MemoryForgetAllMsg());

  bool setCaptions(bool on) => _c.send(SetDisplayMsg(captions: on));
  bool wearFace(String mode, {String? code, Map<String, dynamic>? recipe}) =>
      _c.send(SetRecipeMsg(mode: mode, code: code, recipe: recipe));

  /// v1.8 (PROTOCOL.md 10.11): the Gemini voice style for one character, to a brain that speaks with
  /// Gemini TTS itself (the desktop's built-in brain; its hello carries `voice_style`). Else nothing.
  bool voiceStyle(String mode, String style) {
    if (legacy || _c.current.hello?.voiceStyle == null) return false;
    return _c.send(VoiceStyleMsg(mode: mode, style: style));
  }

  bool watchCamera([num fps = 8]) => _c.send(CameraSubscribeMsg(fps: fps));
  bool stopCamera() => _c.send(const CameraUnsubscribeMsg());
  bool askPairing() => _c.send(const PairingGetMsg());

  /// The joystick. [ttlMs] is the dead man's switch: the wheels stop by
  /// themselves when no newer drive arrives in time.
  bool drive(double x, double y, {int ttlMs = 300}) =>
      _c.send(DriveMsg(x: double.parse(x.toStringAsFixed(3)), y: double.parse(y.toStringAsFixed(3)), ttlMs: ttlMs));
}

final commandsProvider = Provider<SpikeCommands>((ref) => SpikeCommands(ref.watch(brainClientProvider)));
