/// The phone brain: Spike's brain while away from home (protocol v1.3,
/// PROTOCOL.md section 11). It is a port of the laptop brain's turn logic
/// (`spike_brain/brain.py` + `applink.py`), scoped to what the robot can do:
///
///   heard/typed -> safety screen (+ model check) -> crisis path | request
///   block -> commands (intents) -> language model (Gemini, or the offline
///   brain) -> sentence chunks -> output check -> voice on the phone + face on
///   the robot and in the app
///
/// To the app's screens it looks exactly like the laptop brain (it implements
/// [SpikeLink] and emits the same messages), so every screen works unchanged.
/// To the robot it IS a brain: it answers the boards' hellos over BLE or the
/// hotspot ([RobotHub]).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math';

import '../../protocol/client.dart';
import '../../protocol/messages.dart';
import '../../protocol/names.dart' as n;
import '../ai/llm.dart';
import '../transport/robot_hub.dart';
import '../transport/robot_session.dart';
import '../voice/ear.dart';
import '../voice/speaker.dart';
import '../../core/capabilities.dart';
import 'away_lines.dart';
import 'intents.dart';
import 'memory.dart';
import 'persona.dart';
import 'reply.dart';
import 'safety.dart' as safety;

const greetingLines = {'come_home', 'greet_morning', 'greet_afternoon', 'greet_evening', 'greet_night'};
const softLines = {'crisis', 'emergency', 'crisis_followup', 'checkin_sad'}; // said in the soft voice
final _greetingWords = RegExp(r"\b(hi|hello|hiya|morning|evening|afternoon|night|welcome|g'?day)\b");
final _order = RegExp(r'^(please |can you |could you |now |ok |okay )?(sit|stand|come|go|get|look|move|stop|be quiet|'
    r'shush|stay|lie|jump|turn|spin|wait|listen|give|bring|put|show|smile|say|sing|dance)\b');
final _longRequest = RegExp(r'\b(story|stories|jokes|a few|some more|list|sing|song|poem|explain)\b');
final _feelingBetter = RegExp(r"\b(i'?m (ok|okay|fine|better|good|alright)|feel(ing)? better|that helped|"
    r'thank you|thanks|haha|lol|you made me (smile|laugh))\b');
final _jokeRequest = RegExp(r'\b(joke|jokes|funny|make me laugh|cheer me up with)\b');
const funnyMoods = [
  'laughing', 'playful', 'silliness', 'mischief', 'happy', 'embarrassed', 'proud', 'smugness', //
  'delight', 'joy', 'excited',
];
const sleepActions = ['fallAsleep', 'napping', 'dozing', 'deepSleepDreams'];
const quietActions = ['wakeUp', 'snuggle', 'slowWag', 'boop'];

/// The face must fit how the owner is, whatever the model picked (brain.py fit_tags).
(String, String?) fitTags(String? mood, String? action, String? support, bool crisis, {bool joke = false}) {
  var m = mood ?? 'happy';
  if (joke && support == null && !crisis && !funnyMoods.contains(m)) m = 'playful';
  if (crisis) return ((safety.softMoods.contains(m) && m != 'sad') ? m : 'caring', null);
  if (support == 'sad' || support == 'lonely' || support == 'grief') {
    return (safety.softMoods.contains(m) ? m : (support == 'lonely' ? 'cuddly' : 'caring'), 'snuggle');
  }
  if (support == 'tired') return (safety.calmMoods.contains(m) ? m : 'happy', 'slowWag');
  if (m == 'neutral') m = 'happy';
  return (m, action);
}

/// The language model the brain should use right now (Gemini with the owner's
/// key, the offline brain, or none), decided by the app's settings.
typedef ModelPicker = LlmProvider? Function();

class PhoneBrain implements SpikeLink {
  PhoneBrain({
    required this.persona,
    required this.settings,
    required this.memory,
    required this.cloud,
    required this.offline,
    required this.voice,
    this.ear,
    this.appVersion = '0',
    Random? rng,
    DateTime Function()? clock,
  })  : rng = rng ?? Random(),
        _clock = clock ?? DateTime.now {
    conv = Conversation(settings.historyTurns);
    robots = RobotHub(
      greeting: () => BrainGreeting(mode: mode, names: names, wakeWords: wakeWords),
      appVersion: appVersion,
      onBoardLive: _onBoardLive,
      onBoardGone: (_) => _robotStatus(),
      onMessage: _onRobotMessage,
    );
  }

  /// {'dog': Spike, 'cat': Spicy}
  final Map<String, Persona> persona;
  final BrainSettings settings;
  final PhoneMemory memory;
  final ModelPicker cloud;
  final ModelPicker offline;
  SpikeVoice voice;
  SpikeEar? ear;
  final String appVersion;
  final Random rng;
  final DateTime Function() _clock;
  late final Conversation conv;
  late final RobotHub robots;

  String mode = 'dog';
  String robotMood = 'neutral';
  String listeningState = 'idle';
  bool captions = true;
  Map<String, Map<String, Object?>> recipes = {};
  Map<String, Object?>? battery;
  bool _cameraSubscribed = false;

  Persona get p => persona[mode]!;
  Map<String, String> get names => {for (final e in persona.entries) e.key: e.value.name};
  Map<String, List<String>> get wakeWords => {for (final e in persona.entries) e.key: e.value.wakeWords};

  // ---------------------------------------------------------------- SpikeLink (what the app sees)
  final _toApp = StreamController<SpikeMessage>.broadcast();
  final _status = StreamController<LinkStatus>.broadcast();
  LinkStatus _current = const LinkStatus(brain: BrainHost.phone);

  @override
  Stream<SpikeMessage> get messages => _toApp.stream;
  @override
  Stream<LinkStatus> get status => _status.stream;
  @override
  LinkStatus get current => _current;
  @override
  bool get legacyBrain => false;
  bool get running => _current.isConnected;

  void _setStatus(LinkStatus s) {
    _current = s;
    if (!_status.isClosed) _status.add(s);
  }

  void _app(SpikeMessage m) {
    if (!_toApp.isClosed) _toApp.add(m);
  }

  /// Face messages go to the robot's screen board and to the app (which mirrors the face).
  void face(SpikeMessage m) {
    if (m is ActionMsg && !isAvailable(m.action)) return; // the body cannot do it (core/capabilities.dart)
    if (m is MoodMsg) robotMood = m.mood;
    if (m is ListeningMsg) listeningState = m.state;
    _app(m);
    robots.toFace(m);
  }

  void setListening(String state) => face(ListeningMsg(state: state));

  // ---- Gemini Live (away/ai/live_talk.dart): a spoken conversation outside the turn loop.
  // Safety for it is live_guard.dart + [crisis]/[sayLine] below; these only show it.
  int _liveUtt = 0, _liveSeq = 0;

  /// The owner's words heard by Live (one per turn), shown like any heard turn.
  void liveHeard(String text) {
    lastInteraction = _clock();
    ownerTurns++;
    greeted = true;
    _turnGen++; // a running scripted turn gives way
    _liveUtt++;
    _liveSeq = 0;
    _app(HeardMsg(text: text, via: 'phone_mic'));
  }

  /// One sentence Spike says through Live: a caption for the app and the robot (babble mouth).
  void liveSaid(String text) {
    final words = text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
    final say = SayMsg(
        utt: 'live$_liveUtt', seq: _liveSeq++, isFinal: false, text: text, mood: null,
        durationMs: max(900, (words / 2.6 * 1000).round()), audio: null);
    _said('happy', null, text);
    _app(say);
    robots.toFace(say);
  }

  // ---------------------------------------------------------------- life cycle
  DateTime startedAt = DateTime.now();
  DateTime lastInteraction = DateTime.now();
  DateTime? crisisUntil;
  DateTime? supportUntil;
  String? supportKind;
  DateTime? lonelySignalAt;
  DateTime? forgetAllUntil;
  bool greeted = false;
  int saidCount = 0;
  int ownerTurns = 0;
  Map<String, Object?>? rps;
  Timer? _life;
  Future<void>? _turn;
  int _turnGen = 0;
  String _lastGreetPart = '';
  String _lastGreetDay = '';

  /// Become Spike's brain: tell the app everything a brain tells it on connect.
  Future<void> start() async {
    if (running) return;
    startedAt = lastInteraction = _clock();
    _setStatus(LinkStatus(
      phase: LinkPhase.connected,
      brain: BrainHost.phone,
      hello: BrainHello(server: 'spike-phone', version: appVersion, heartbeatS: 5, mode: mode, names: names, wakeWords: wakeWords),
    ));
    _app(current.hello!);
    _app(SetModeMsg(mode: mode));
    _app(MoodMsg(mood: n.moods.contains(robotMood) ? robotMood : 'neutral'));
    _app(const ListeningMsg(state: 'idle'));
    _robotStatus();
    _brainStatus();
    _app(SetDisplayMsg(captions: captions));
    // no 	imers: alarms live on the laptop; the app keeps showing its last list from there
    _sendMemory();
    _life = Timer.periodic(const Duration(seconds: 30), (_) => lifeChecks());
  }

  /// Stop being the brain (the laptop took over, or the app closes). Robot links close.
  Future<void> stop() async {
    _life?.cancel();
    _turnGen++;
    await voice.stop();
    await robots.closeAll();
    _setStatus(const LinkStatus(brain: BrainHost.phone));
  }

  Future<void> dispose() async {
    await stop();
    await _toApp.close();
    await _status.close();
  }

  void _robotStatus() => _app(RobotStatusMsg(
      online: robots.online, boards: robots.roles, drive: robots.hasDrive, camera: robots.hasCamera));

  String get llmState {
    final m = cloud() ?? offline();
    return m == null ? 'off' : 'ready';
  }

  void _brainStatus() => _app(BrainStatusMsg(llm: llmState));

  /// The app changed the key or the offline brain: tell the screens.
  void modelsChanged() {
    if (running) _brainStatus();
  }

  void _sendMemory() {
    final items = [
      for (final f in memory.all.take(200))
        MemoryItem(id: f.id, text: f.text.length > 300 ? f.text.substring(0, 300) : f.text, kind: f.kind, at: f.at)
    ];
    _app(MemoryMsg(items: items, total: memory.total));
  }

  // ---------------------------------------------------------------- app -> brain (SpikeCommands)
  @override
  bool send(SpikeMessage m) {
    if (!running) return false;
    unawaited(_fromApp(m));
    return true;
  }

  Future<void> _fromApp(SpikeMessage m) async {
    switch (m) {
      case TextMsg():
        final t = m.text.trim();
        if (t.isNotEmpty) startTurn(t.length > 500 ? t.substring(0, 500) : t, 'typed', mine: true);
      case TouchMsg():
        await onTouch(m.zone, m.gesture);
      case ActionMsg():
        lastInteraction = _clock();
        final quiet = m.quiet == true;
        if (sleepActions.contains(m.action)) {
          face(ActionMsg(action: m.action));
          if (!quiet) await sayLine('sleep');
        } else if (quiet || quietActions.contains(m.action)) {
          face(ActionMsg(action: m.action));
        } else {
          await doTrick(m.action);
        }
      case MoodMsg():
        face(MoodMsg(mood: m.mood, holdS: m.holdS?.clamp(0, 600)));
      case EventMsg():
        lastInteraction = _clock();
        face(EventMsg(event: m.event));
      case SoundMsg():
        face(SoundMsg(sound: m.sound));
      case SetModeMsg():
        if (m.mode == mode) {
          _app(SetModeMsg(mode: mode));
        } else {
          await setMode(m.mode, announce: m.quiet != true);
        }
      case SetRecipeMsg():
        final rec = <String, Object?>{if (m.code != null) 'code': m.code, if (m.recipe != null) 'recipe': m.recipe};
        if (rec.isEmpty || (m.code != null && (m.code!.isEmpty || m.code!.length > 400)) ||
            (m.recipe != null && jsonEncode(m.recipe).length > 4096)) {
          _app(const ErrorMsg(code: 'bad_value', message: 'set_recipe: bad code or recipe'));
          return;
        }
        recipes[m.mode] = rec;
        robots.toFace(SetRecipeMsg(mode: m.mode, code: m.code, recipe: m.recipe));
      case SetDisplayMsg():
        captions = m.captions;
        face(SetDisplayMsg(captions: captions));
      case DriveMsg():
        // the robot's own reflexes (desk edge, pick-up, battery) filter every drive
        final x = m.x.clamp(-1, 1), y = m.y.clamp(-1, 1);
        robots.toFace(DriveMsg(x: x.abs() < 0.02 ? 0 : x, y: y.abs() < 0.02 ? 0 : y, ttlMs: m.ttlMs.clamp(100, 1000)));
      case CameraSubscribeMsg():
        _cameraSubscribed = true;
        cameraWanted?.call(true);
      case CameraUnsubscribeMsg():
        _cameraSubscribed = false;
        cameraWanted?.call(false);
      case MemoryGetMsg():
        _sendMemory();
      case MemoryForgetMsg():
        if (!await memory.forget(m.factId)) _app(const ErrorMsg(code: 'bad_value', message: 'no such memory'));
        _sendMemory();
      case MemoryForgetAllMsg():
        await memory.wipe();
        conv.clear();
        _sendMemory();
      case TimersGetMsg():
        break; // the laptop's list stays as it was (greyed) while away
      case TimerSetMsg() || TimerCancelMsg():
        _app(const ErrorMsg(code: 'bad_value', message: "alarms are kept by Spike's home brain"));
      case AlarmAckMsg():
        break; // no alarms ring away from home
      case PairingGetMsg():
        _app(const PairingMsg(lan: false, url: ''));
      case PingMsg():
        break;
      default:
        break; // audio (push-to-talk PCM) is the laptop's; away the phone's ear listens (listen())
    }
  }

  /// Wants the camera (the Play screen's camera card): the app brings up the hotspot.
  void Function(bool)? cameraWanted;

  // ---------------------------------------------------------------- robot -> brain
  void _onBoardLive(RobotSession s) {
    if (s.role != 'camera') {
      s.send(SetModeMsg(mode: mode));
      s.send(MoodMsg(mood: n.moods.contains(robotMood) ? robotMood : 'neutral'));
      s.send(ListeningMsg(state: listeningState == 'speaking' ? 'idle' : listeningState));
      for (final e in recipes.entries) {
        s.send(SetRecipeMsg(mode: e.key, code: e.value['code'] as String?, recipe: e.value['recipe'] as Map<String, dynamic>?));
      }
      s.send(SetDisplayMsg(captions: captions));
    }
    _robotStatus();
    if (s.role != 'camera' && s.pipe.link == 'ble') unawaited(_greetRobot());
  }

  /// Spike says hello when his body joins the phone brain (once per part of the day).
  Future<void> _greetRobot() async {
    await Future<void>.delayed(const Duration(milliseconds: 800));
    if (!idle) return;
    await greet();
  }

  void _onRobotMessage(RobotSession s, SpikeMessage m) {
    switch (m) {
      case TouchMsg():
        unawaited(onTouch(m.zone, m.gesture));
      case ImuMsg():
        lastInteraction = _clock();
        if ((m.event == 'pickup' || m.event == 'lap') && idle && rng.nextDouble() < 0.5) {
          unawaited(sayLine('picked_up'));
        } else if (m.event == 'fall' && idle) {
          unawaited(sayLine('fell'));
        }
      case BatteryMsg():
        battery = {'percent': m.percent, 'volts': m.volts, 'charging': m.charging};
        _app(BatteryMsg(percent: m.percent, volts: m.volts, charging: m.charging));
        unawaited(_onBattery(m.percent.toDouble(), m.charging ?? false));
      case CameraMsg():
        if (_cameraSubscribed) _app(m);
      case MoodStateMsg():
        if (m.mood != null) robotMood = m.mood!;
        if (m.mode != null && m.mode != mode) unawaited(setMode(m.mode!, announce: false, fromRobot: true));
      case TextMsg():
        startTurn(m.text.trim(), 'typed');
      case RobotLinkMsg():
        final was = robotLink?.brain;
        if ((m.brain == 'ble' || m.brain == 'hotspot') && (was == null || was == 'lan' || was == 'none')) {
          _onBoardLive(s); // PROTOCOL.md 11.4: what we sent while the laptop had him was answered busy
        }
        robotLink = m;
        onRobotLink?.call(m);
      case HotspotStateMsg():
        onHotspotState?.call(m);
      case ErrorMsg():
        if (m.code == 'busy') onRobotBusy?.call();
      default:
        break; // say_state, edge, log: nothing to do here
    }
  }

  RobotLinkMsg? robotLink;
  void Function(RobotLinkMsg)? onRobotLink;
  void Function(HotspotStateMsg)? onHotspotState;
  void Function()? onRobotBusy;

  String hunger = 'ok';
  bool charging = false;

  Future<void> _onBattery(double percent, bool nowCharging) async {
    final hungryBelow = settings.lifeNum('battery_hungry_below', 30);
    final weakBelow = settings.lifeNum('battery_weak_below', 15);
    final prevLevel = hunger, prevCharging = charging;
    charging = nowCharging;
    final level = percent < weakBelow ? 'weak' : (percent < hungryBelow ? 'hungry' : 'ok');
    hunger = nowCharging ? 'ok' : level;
    if (nowCharging && !prevCharging) {
      if (idle) await sayLine('charging');
    } else if (prevCharging && !nowCharging && percent >= 99) {
      if (idle) await sayLine('full');
    } else if (!nowCharging && level != 'ok' && level != prevLevel) {
      if (idle) await sayLine(level == 'weak' ? 'weak' : 'hungry');
    }
  }

  /// A head tap (on the robot or the app's face) = "listen now" (brain.py on_touch).
  Future<void> onTouch(String zone, String gesture) async {
    lastInteraction = _clock();
    if (zone != 'head' || gesture == 'release') return;
    if (_speaking) await voice.stop();
    unawaited(listen());
  }

  /// Listen once with the phone's ear, then take the words as a turn.
  Future<void> listen() async {
    final e = ear;
    if (e == null || e.listening) return;
    face(SoundMsg(sound: mode == 'cat' ? 'trill' : 'yip'));
    setListening('listening');
    final words = await e.listenOnce();
    if (words == null || words.trim().isEmpty) {
      setListening('idle');
      return;
    }
    startTurn(words.trim(), 'phone_mic');
  }

  /// The owner interrupted (a tap on the app's voice pill): stop talking now, drop
  /// the rest of this reply and let the app listen again. Like the head tap's hush,
  /// without starting the phone's own ear (the app's voice session is listening).
  Future<void> hush() async {
    if (!_speaking) return;
    _hushGen++;
    _turnGen++;
    await voice.stop();
  }

  int _hushGen = 0;

  // ---------------------------------------------------------------- turns (brain.py _turn)
  bool _speaking = false;
  bool get idle => !_speaking && _turn == null;
  List<Map<String, Object?>> turnSaid = [];
  Map<String, Object?>? lastTurn;

  /// A request from the owner (heard or typed). A new one replaces a running one.
  void startTurn(String text, String via, {bool mine = false}) {
    if (text.isEmpty) return;
    final gen = ++_turnGen;
    if (_speaking) unawaited(voice.stop());
    _app(HeardMsg(text: text, via: via, mine: mine));
    final f = _runTurn(text, via, gen);
    _turn = f;
    f.whenComplete(() {
      if (identical(_turn, f)) _turn = null;
    });
  }

  /// Run one turn to the end (tests await this).
  Future<void> turn(String text, {String via = 'typed'}) {
    startTurn(text, via);
    return _turn ?? Future.value();
  }

  bool _stale(int gen) => gen != _turnGen;

  Future<void> _runTurn(String text, String via, int gen) async {
    lastInteraction = _clock();
    ownerTurns++;
    greeted = true; // the owner opened: a nudge can no longer be his first line
    turnSaid = [];
    var level = safety.SafetyLevel.none;
    var kind = '';
    try {
      if (via == 'typed') {
        // "Spicy, sit down" typed: the name is a call, like said aloud
        final m = RegExp('^\\s*(${[for (final p in persona.values) RegExp.escape(p.name)].join('|')})\\b[\\s,!.:-]*',
                caseSensitive: false)
            .firstMatch(text);
        if (m != null) {
          final called = persona.entries.firstWhere((e) => e.value.name.toLowerCase() == m.group(1)!.toLowerCase()).key;
          if (called != mode) await setMode(called, announce: false);
          final rest = text.substring(m.end).trim();
          if (rest.isEmpty && !_greetingWords.hasMatch(text.toLowerCase())) {
            await sayLine('wake_ack');
            return;
          }
          if (rest.isNotEmpty) text = rest;
        }
      }
      setListening('thinking');
      // 1. safety and care: how is the owner? (before anything else)
      final screen = safety.screenInput(text);
      level = screen.level;
      kind = screen.kind;
      if (level != safety.SafetyLevel.crisis && screen.needsLlmCheck && settings.llmCrisisCheck) {
        final checked = await _classifyRisk(text);
        if (_stale(gen)) return;
        if (checked == safety.SafetyLevel.crisis) {
          level = checked;
          kind = 'self_harm';
        } else if (checked == safety.SafetyLevel.support && level == safety.SafetyLevel.none) {
          level = checked;
          kind = 'sad';
        }
      }
      if (level == safety.SafetyLevel.crisis) {
        await crisis(kind);
        return;
      }
      if (safety.requestBlocked(text)) {
        await sayLine('unsafe_replacement');
        return;
      }
      if (level == safety.SafetyLevel.support) {
        // tired passes sooner than sad: warmth for 5 min, for 15 when sad, lonely or grieving
        supportKind = kind;
        supportUntil = _clock().add(Duration(minutes: kind == 'tired' ? 5 : 15));
        if (kind == 'lonely') lonelySignalAt = _clock();
      } else if (supportKind != null && _feelingBetter.hasMatch(text.toLowerCase())) {
        supportKind = null;
      }
      // 2. commands
      final intent = matchIntent(text, names,
          inRps: rps?['await_voice'] == true,
          confirmingForgetAll: forgetAllUntil != null && _clock().isBefore(forgetAllUntil!));
      if (intent != null) {
        await _doIntent(intent, text);
        return;
      }
      // 3. conversation
      await chat(text, support: _support(), gen: gen);
      // 4. memory (only ordinary talk: never from a sad or risky moment)
      if (level == safety.SafetyLevel.none) await _rememberFrom(text);
    } catch (e) {
      if (!_stale(gen)) await sayLine('fallback'); // a broken turn must never kill Spike
    } finally {
      lastTurn = {'text': text, 'level': level.name, 'kind': kind, 'said': [...turnSaid]};
      if (!_speaking && !_stale(gen)) setListening('idle');
    }
  }

  String? _support() {
    if (supportKind != null && supportUntil != null && _clock().isBefore(supportUntil!)) return supportKind;
    supportKind = null;
    return null;
  }

  bool get inCrisis => crisisUntil != null && _clock().isBefore(crisisUntil!);

  Future<safety.SafetyLevel> _classifyRisk(String text) async {
    final m = cloud(); // only the cloud model is trusted as a second safety check
    if (m == null) return safety.SafetyLevel.none;
    try {
      final raw = await m.completeJson(safety.classifierSystem, text, safety.classifierSchema,
          maxTokens: 20, timeout: const Duration(seconds: 4));
      return safety.parseClassifier(raw);
    } catch (_) {
      return safety.SafetyLevel.none;
    }
  }

  /// Calm, caring, no jokes; points to real people, the numbers said once. Only that it
  /// happened is logged (brain.py _crisis).
  Future<void> crisis(String kind) async {
    crisisUntil = _clock().add(const Duration(hours: 3));
    await memory.logEvent('crisis_moment'); // no words, no details
    face(const MoodMsg(mood: 'caring'));
    await sayLine(kind == 'emergency' ? 'emergency' : 'crisis', settings.helpline());
  }

  Future<bool> crisisFollowupDue() async {
    final last = memory.lastEvent('crisis_moment');
    if (last == null) return false;
    final ageH = (_clock().millisecondsSinceEpoch ~/ 1000 - last) / 3600;
    if (ageH < settings.checkinAfterCrisisH || ageH > 72) return false;
    final done = memory.lastEvent('crisis_followup');
    if (done != null && done > last) return false;
    await memory.logEvent('crisis_followup');
    await sayLine('crisis_followup');
    return true;
  }

  // ---------------------------------------------------------------- commands
  Future<void> _doIntent(Intent intent, String text) async {
    final sl = intent.slots;
    final now = _clock();
    switch (intent.name) {
      case 'set_mode':
        if (sl['mode'] == mode) {
          await sayLine('trick_ok');
        } else {
          await setMode(sl['mode'] as String, announce: true);
        }
      case 'stop':
        await voice.stop();
        face(const MoodMsg(mood: 'neutral'));
      case 'forget_all':
        forgetAllUntil = now.add(const Duration(seconds: 30));
        await sayLine('forget_all_confirm');
      case 'forget_all_confirmed':
        forgetAllUntil = null;
        await memory.wipe();
        conv.clear();
        _sendMemory();
        await sayLine('forget_all_done');
      case 'forget_all_cancelled':
        forgetAllUntil = null;
        await sayLine('forget_all_cancelled');
      case 'forget_last':
        final gone = await memory.forgetLast();
        if (conv.history.length >= 2) conv.history = conv.history.sublist(0, conv.history.length - 2);
        _sendMemory();
        await sayLine(gone.isNotEmpty ? 'forgot' : 'nothing_to_forget');
      case 'forget_about':
        final gone = await memory.forgetMatching(sl['what'] as String);
        _sendMemory();
        await sayLine(gone != null ? 'forgot' : 'nothing_to_forget');
      case 'recall_all':
        final facts = memory.recallAll(8);
        if (facts.isEmpty) {
          await sayLine('nothing_to_forget');
        } else {
          await chat(text,
              extraNotes: [
                'They asked what you remember about them. In two or three short sentences, tell them these things '
                    'warmly, in your own words: ${facts.map((f) => '$f.').join(' ')}'
              ],
              rememberExchange: false);
        }
      case 'remember':
        await memory.remember(sl['fact'] as String, kind: 'fact');
        _sendMemory();
        await sayLine('remembered');
      case 'timers_away':
        await sayRaw(awayLine('timers_away', mode, rng.nextInt(9)));
      case 'tell_time':
        await sayLine('tell_time', {'time': sayTime(now)});
      case 'tell_date':
        await sayLine('tell_date', {'date': '${weekdayName(now)}, ${now.day} ${monthNames[now.month - 1]}'});
      case 'rps_start':
        await rpsStart();
      case 'rps_choice':
        await _rpsResolve(sl['choice'] as String);
      case 'rps_stop':
        rps = null;
        await sayLine('stop_ok');
      case 'trick':
        await doTrick(sl['action'] as String?);
      case 'trick_unavailable':
        await sayRaw(unavailableLine(sl['trick'] as String, mode).$1);
      case 'sleep':
        face(const ActionMsg(action: 'fallAsleep'));
        await sayLine('sleep');
    }
  }

  Future<void> setMode(String m, {bool announce = true, bool fromRobot = false}) async {
    if (!n.modes.contains(m) || m == mode) return;
    mode = m;
    if (fromRobot) {
      _app(SetModeMsg(mode: m));
    } else {
      face(SetModeMsg(mode: m));
    }
    if (announce) await sayLine(m == 'cat' ? 'mode_to_cat' : 'mode_to_dog');
  }

  Future<void> doTrick(String? action) async {
    if (!isAvailable(action)) return sayRaw(unavailableLine('do that', mode).$1);
    final a = action ?? const ['paw', 'zoomies', 'tailWagDance', 'playBow'][rng.nextInt(4)];
    if (mode == 'cat' && p.hasLine('trick_refuse')) {
      // Spicy ignores you on purpose... then does it anyway
      await sayLine('trick_refuse');
      await Future<void>.delayed(Duration(milliseconds: 2000 + rng.nextInt(1500)));
    }
    face(ActionMsg(action: a));
    await Future<void>.delayed(const Duration(milliseconds: 1200));
    await sayLine('trick_ok');
  }

  // rock paper scissors by voice (the phone brain has no camera hand tracking)
  Future<void> rpsStart() async {
    final score = (rps?['score'] as Map<String, int>?) ?? {'owner': 0, 'robot': 0, 'draws': 0};
    rps = {'score': score, 'await_voice': false};
    face(GameMsg(game: 'rps', phase: 'start', score: score));
    await sayLine('rps_start');
    for (final c in [3, 2, 1]) {
      face(GameMsg(game: 'rps', phase: 'countdown', count: c, score: score));
      face(const SoundMsg(sound: 'pop'));
      await Future<void>.delayed(const Duration(milliseconds: 750));
    }
    face(GameMsg(game: 'rps', phase: 'shoot', score: score));
    rps!['robot'] = const ['rock', 'paper', 'scissors'][rng.nextInt(3)];
    rps!['await_voice'] = true;
    await sayLine('rps_no_hand');
  }

  Future<void> _rpsResolve(String owner) async {
    final r = rps;
    if (r == null || r['robot'] == null) {
      await rpsStart();
      return;
    }
    final robot = r['robot'] as String;
    const beats = {'rock': 'scissors', 'paper': 'rock', 'scissors': 'paper'};
    final result = owner == robot ? 'draw' : (beats[owner] == robot ? 'win' : 'lose');
    final sc = r['score'] as Map<String, int>;
    final k = result == 'win' ? 'owner' : (result == 'lose' ? 'robot' : 'draws');
    sc[k] = (sc[k] ?? 0) + 1;
    r['await_voice'] = false;
    r.remove('robot');
    face(GameMsg(game: 'rps', phase: 'reveal', owner: owner, robot: robot, result: result, score: sc));
    await sayLine(const {'win': 'rps_win', 'lose': 'rps_lose', 'draw': 'rps_draw'}[result]!);
  }

  Future<void> _rememberFrom(String text) async {
    final facts = extractRules(text, _clock());
    final ids = <int>[];
    for (final f in facts) {
      ids.add(await memory.remember(f.text, kind: f.kind, subject: f.subject, due: f.due));
    }
    if (ids.isNotEmpty) {
      memory.lastIds = ids; // "forget that" = everything from what they just said
      _sendMemory();
    }
  }

  // ---------------------------------------------------------------- talking (brain.py _chat)
  bool get lonely {
    final now = _clock();
    return lonelySignalAt != null && now.difference(lonelySignalAt!).inMinutes < 60;
  }

  bool nudgeAllowed() {
    final minTurns = settings.lifeNum('people_nudge_min_turns', 3);
    final afterStart = settings.lifeNum('people_nudge_after_start_min', 10);
    return greeted && saidCount > 0 && ownerTurns >= minTurns && _clock().difference(startedAt).inSeconds >= afterStart * 60;
  }

  bool nudgeDue({bool soonAfterLonely = false}) {
    if (!nudgeAllowed()) return false;
    final last = memory.lastEvent('people_nudge') ?? 0;
    final hours = (_clock().millisecondsSinceEpoch ~/ 1000 - last) / 3600;
    final gap = (lonely && soonAfterLonely)
        ? settings.lifeNum('people_nudge_after_lonely_h', 3)
        : settings.lifeNum('people_nudge_min_gap_h', 20);
    return hours >= gap && !inCrisis;
  }

  String? _ownerRef() => memory.ownerName();

  Situation situation(String text, List<String> notes) {
    final other = [for (final e in persona.entries) if (e.key != mode) e.value.name];
    return Situation(
      now: _clock(),
      ownerName: memory.ownerName(),
      memories: memory.contextFor(text, budget: settings.memoryPromptChars),
      notes: notes,
      battery: battery?['percent'] as num?,
      otherName: other.isNotEmpty && text.toLowerCase().contains(other.first.toLowerCase()) ? other.first : null,
    );
  }

  Future<void> chat(String text,
      {String? support, List<String> extraNotes = const [], bool rememberExchange = true, int? gen}) async {
    final g = gen ?? _turnGen;
    final notes = [...extraNotes];
    if (inCrisis) {
      notes.add(safety.safetyModeNote);
    } else if (support != null) {
      notes.add(safety.supportNotes[support] ?? safety.supportNotes['sad']!);
      if (support == 'lonely' && nudgeDue(soonAfterLonely: true)) {
        notes.add(safety.lonelyCallHint); // only after a real conversation, never first
        await memory.logEvent('people_nudge');
      }
    }
    if (safety.isHonestyQuestion(text)) {
      notes.add('They are asking what you are. In your first sentence say plainly that you are a robot '
          'with an AI brain (use the words robot and AI), not a human and not a living animal; '
          'then say you really do like being with them.');
    }
    if (_order.hasMatch(text.trim().toLowerCase()) && (support == null || support == 'tired') && !inCrisis) {
      notes.add('This is an order. ${mode == 'cat' ? "Refuse or question it first, then do it anyway in the same reply, "
          "ending with a line like '...Fine.' Two short sentences." : 'Do it happily, with a short cheeky line.'}');
    }
    if (support == null && !inCrisis && lonely && nudgeDue(soonAfterLonely: true)) {
      notes.add('If it fits naturally, warmly encourage them to call or message a friend or family '
          'member today, or to get outside for a bit.');
      await memory.logEvent('people_nudge');
    }
    if (!robots.online) {
      notes.add('Right now you are only on their phone screen, away from your desk: your robot body is not with you.');
    }
    final longOk = _longRequest.hasMatch(text.toLowerCase());
    if (longOk) notes.add('They asked for something longer, so you may use up to five short sentences.');
    final sys = systemPrompt(p, _ownerRef(), settings.helpline());
    final msgs = conv.build(sys, situation(text, notes), text);

    final models = [cloud(), offline()].whereType<LlmProvider>().toList();
    if (models.isEmpty) {
      await sayRaw(awayLine('no_brain', mode, rng.nextInt(9)));
      return;
    }
    LlmError? lastErr;
    for (final model in models) {
      final r = await _streamReply(model, msgs,
          support: support,
          wordCap: longOk ? settings.longWordCap : settings.replyWordCap,
          maxTokens: longOk ? settings.longMaxTokens : settings.maxTokens,
          joke: _jokeRequest.hasMatch(text.toLowerCase()),
          gen: g);
      if (r.error == null) {
        if (r.text != null && rememberExchange) conv.add(text, r.text!);
        return;
      }
      lastErr = r.error;
      if (r.spokeAny || _stale(g)) return; // half a reply said: never restart elsewhere
    }
    if (_stale(g)) return;
    switch (lastErr?.kind) {
      case LlmErrorKind.rateLimited:
        await sayRaw(awayLine('rate_limited', mode, rng.nextInt(9)));
      case LlmErrorKind.badKey:
        await sayRaw(awayLine('bad_key', mode, rng.nextInt(9)));
      case LlmErrorKind.blocked:
        await sayLine('unsafe_replacement');
      default:
        await sayLine('fallback');
    }
  }

  /// LLM -> sentences -> safety check -> speech (brain.py _stream_reply), with the same
  /// spoken-reply rules: at most [wordCap] words (whole sentences), a helpline number at
  /// most once, and a face and voice that fit how the owner is.
  Future<({String? text, LlmError? error, bool spokeAny})> _streamReply(LlmProvider model, List<ChatMessage> msgs,
      {String? support, required int wordCap, int? maxTokens, bool joke = false, required int gen}) async {
    final parser = StreamParser(firstMinWords: settings.firstChunkMinWords, maxChars: settings.maxChunkChars);
    final spoken = <String>[];
    final crisisNow = inCrisis;
    final soft = support != null || crisisNow;
    String? stateMood, stateAction;
    var firstMoodSent = false, words = 0, helplineSaid = false;
    final speech = _SpeechQueue(this, soft: soft);
    final helpNums = [settings.helpline()['helpline_number']!, settings.helpline()['emergency_number']!];

    void applyTags(String? mood, String? action) {
      if (firstMoodSent) return;
      firstMoodSent = true;
      final (m, a) = fitTags(mood, action, support, crisisNow, joke: joke);
      stateMood = m;
      stateAction = a;
      face(MoodMsg(mood: m));
      if (a != null) face(ActionMsg(action: a));
    }

    String? handle(ReplyEvent ev, {bool last = false}) {
      switch (ev) {
        case TagsEvent():
          applyTags(ev.mood, ev.action);
        case ActionEvent():
          if (stateAction == null && !crisisNow && support == null) {
            stateAction = ev.action;
            face(ActionMsg(action: ev.action));
          }
        case SentenceEvent():
          var sentence = stripPetNames(ev.text);
          final verdict = safety.checkOutput(sentence) ?? safety.checkOutput([...spoken, sentence].join(' '));
          if (verdict != null) return verdict;
          final ends = RegExp('[.!?\u2026"\')]\\s*\$');
          if (last && spoken.isNotEmpty && !ends.hasMatch(sentence)) return null; // a fragment cut off by the limit
          if (last && spoken.isEmpty && !ends.hasMatch(sentence)) sentence += '.';
          if (safety.mentionsHelpline(sentence, helpNums)) {
            if (helplineSaid) return null; // never the same helpline twice in one reply
            helplineSaid = true;
          }
          var w = sentence.split(RegExp(r'\s+')).where((x) => x.isNotEmpty).length;
          if (spoken.isNotEmpty && words + w > wordCap) return 'cap';
          if (spoken.isEmpty && w > wordCap) {
            final cut = sentence.split(RegExp(r'\s+')).take(wordCap).join(' ');
            final half = cut.substring(cut.length ~/ 2);
            sentence = '${(half.contains(',') ? cut.substring(0, cut.lastIndexOf(',')) : cut).replaceAll(RegExp(r'[,;:\- ]+$'), '')}.';
            w = sentence.split(RegExp(r'\s+')).length;
          }
          if (!firstMoodSent) applyTags(null, null);
          spoken.add(sentence);
          words += w;
          speech.add(sentence);
      }
      return null;
    }

    String? stop;
    LlmError? error;
    try {
      await for (final piece in model.stream(msgs, maxTokens: maxTokens, temperature: settings.temperature.toDouble())) {
        if (_stale(gen)) break;
        for (final ev in parser.feed(piece)) {
          stop = handle(ev);
          if (stop != null) break;
        }
        if (stop != null) break;
      }
      if (stop == null && !_stale(gen)) {
        for (final ev in parser.finish()) {
          stop = handle(ev, last: true);
          if (stop != null) break;
        }
      }
    } on LlmError catch (e) {
      error = e;
    } catch (e) {
      error = LlmError(LlmErrorKind.other, e.runtimeType.toString());
    }
    if (error != null && spoken.isEmpty) {
      await speech.finish(cancel: true);
      return (text: null, error: error, spokeAny: false);
    }
    if (stop != null && stop != 'cap') {
      final parsed = parseReply(p.line(stop == 'not_honest' ? 'honest_robot' : 'unsafe_replacement', rng));
      if (parsed.mood != null) face(MoodMsg(mood: parsed.mood!));
      speech.add(parsed.text);
      spoken.add(parsed.text);
    }
    if (!firstMoodSent) applyTags(null, null);
    await speech.finish(cancel: _stale(gen));
    if (spoken.isEmpty) return (text: null, error: error, spokeAny: false);
    final said = spoken.join(' ');
    _said(stateMood ?? 'happy', stateAction, said);
    final head = '[${stateMood ?? 'happy'}${stateAction != null ? '|$stateAction' : ''}]';
    return (text: '$head $said', error: null, spokeAny: true);
  }

  void _said(String mood, String? action, String text) {
    saidCount++;
    turnSaid.add({'mood': mood, 'action': action, 'text': text});
  }

  /// A scripted line from the persona file (mood/action tags applied).
  Future<void> sayLine(String key, [Map<String, String> fmt = const {}]) async {
    final f = {...fmt};
    final owner = _ownerRef();
    if (owner != null) f['owner'] = owner;
    final (_, raw) = p.pick(key, rng, f);
    if (greetingLines.contains(key)) greeted = true;
    await sayRaw(raw, soft: softLines.contains(key));
  }

  Future<void> sayRaw(String raw, {bool soft = false}) async {
    final parsed = parseReply(raw);
    if (parsed.mood != null) face(MoodMsg(mood: parsed.mood!));
    if (parsed.action != null) face(ActionMsg(action: parsed.action!));
    if (parsed.text.isEmpty) return;
    _said(parsed.mood ?? 'happy', parsed.action, parsed.text);
    final q = _SpeechQueue(this, soft: soft)..add(parsed.text);
    await q.finish();
  }

  Future<void> greet() async {
    final now = _clock();
    final part = timeOfDay(now.hour);
    final day = '${now.year}-${now.month}-${now.day}';
    if (part == _lastGreetPart && day == _lastGreetDay) return;
    _lastGreetPart = part;
    _lastGreetDay = day;
    final key = const {'morning': 'greet_morning', 'afternoon': 'greet_afternoon', 'evening': 'greet_evening'}[part] ??
        'greet_night';
    await sayLine(key);
  }

  bool quietHours([DateTime? at]) {
    final q = settings.life['quiet_hours'];
    if (q is! List || q.length != 2) return false;
    int mins(String s) {
      final p = s.split(':');
      return int.parse(p[0]) * 60 + int.parse(p[1]);
    }

    final t = at ?? _clock();
    final now = t.hour * 60 + t.minute, a = mins(q[0].toString()), b = mins(q[1].toString());
    return a <= b ? (now >= a && now < b) : (now >= a || now < b);
  }

  /// Every 30 s (brain.py _life_checks, the parts that need no camera): the gentle
  /// nudge toward real people as a chat winds down, and the day-after check-in.
  Future<void> lifeChecks() async {
    if (!idle || rps != null || quietHours()) return;
    final sinceTalkMin = _clock().difference(lastInteraction).inSeconds / 60;
    if (sinceTalkMin < 10 && sinceTalkMin >= 0.5 && sinceTalkMin <= 5 && nudgeDue()) {
      await memory.logEvent('people_nudge');
      await sayLine('people_nudge');
      return;
    }
    if (sinceTalkMin < 10 && memory.lastEvent('crisis_moment') != null) await crisisFollowupDue();
  }
}

/// Sentences are voiced one after another; the next is prepared while one plays.
/// Each goes to the app and the robot as a caption-only `say` with the mouth
/// envelope (PROTOCOL.md 11.3), then plays on the phone.
class _SpeechQueue {
  _SpeechQueue(this.b, {required this.soft})
      : utt = 'p${++_n}',
        _hush = b._hushGen;
  static int _n = 0;
  final PhoneBrain b;
  final int _hush; // hush() since this reply began: the rest is dropped
  final bool soft;
  final String utt;
  int _seq = 0;
  final List<Future<PreparedSpeech?>> _prepared = [];
  final List<String> _texts = [];
  Future<void> _chain = Future.value();
  bool _cancel = false;

  void add(String text) {
    final spokenText = sayAs(text, b.settings.sayAs());
    final prep = b.voice.prepare(spokenText, mode: b.mode, soft: soft).then<PreparedSpeech?>((v) => v, onError: (_) => null);
    _prepared.add(prep);
    _texts.add(text);
    final i = _texts.length - 1;
    _chain = _chain.then((_) => _play(i));
  }

  Future<void> _play(int i) async {
    if (_cancel || b._hushGen != _hush) return;
    final sp = await _prepared[i];
    if (_cancel || b._hushGen != _hush) return;
    final clip = sp?.clip ?? SpokenClip(durationMs: 1500);
    final say = SayMsg(
      utt: utt, seq: _seq++, isFinal: false, text: _texts[i], mood: null, durationMs: clip.durationMs,
      audio: null, mouth: clip.mouth == null ? null : {'rate_hz': clip.mouthHz, 'values': clip.mouth},
    );
    if (!b._speaking) {
      b._speaking = true;
      b.setListening('speaking');
    }
    b._app(say);
    b.robots.toFace(say);
    if (sp != null) {
      await sp.play();
    } else {
      await Future<void>.delayed(Duration(milliseconds: clip.durationMs));
    }
  }

  Future<void> finish({bool cancel = false}) async {
    if (cancel) {
      _cancel = true;
      await b.voice.stop();
    }
    await _chain;
    // end marker (5.4)
    final end = SayMsg(utt: utt, seq: _seq, isFinal: true, text: '', durationMs: 0, audio: null);
    b._app(end);
    b.robots.toFace(end);
    if (b._speaking) {
      b._speaking = false;
      b.setListening('idle');
    }
  }
}
