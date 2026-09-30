/// Away from home (protocol v1.3): the automatic choice of brain and links.
///
///   home brain reachable            -> the laptop is the brain (as before)
///   else (away mode on)             -> the phone is the brain; the robot joins
///                                      it over Bluetooth LE when it is near
///   camera wanted (or "keep hotspot")-> the phone's hotspot comes up, the robot
///                                      and its camera board join it
///
/// The phone keeps retrying the laptop in the background (BrainClient's
/// backoff) and hands back to it the moment it answers, or as soon as the robot
/// says it has the home brain (robot_link brain "lan", or error busy).
library;

import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';

import '../away/ai/gemini.dart';
import '../away/ai/key_store.dart';
import '../away/ai/llm.dart';
import '../away/ai/offline_brain.dart';
import '../away/brain/memory.dart';
import '../away/brain/persona.dart';
import '../away/brain/phone_brain.dart';
import '../away/transport/ble_link.dart';
import '../away/transport/hotspot.dart';
import '../away/transport/robot_server.dart';
import '../away/voice/ear.dart';
import '../away/voice/speaker.dart';
import '../away/ai/gemini_voices.dart';
import '../away/voice/gemini_tts.dart';
import '../away/voice/voice_chain.dart';
import '../protocol/client.dart';
import '../protocol/messages.dart';
import '../core/platform.dart';
import 'hub.dart';
import 'link.dart';
import 'settings.dart';

enum RobotConn { none, needsPermission, bluetoothOff, searching, connecting, pairing, connected, failed }

enum HotspotConn { off, starting, joining, up, failed }

@immutable
class AwayState {
  const AwayState({
    this.active = BrainHost.laptop,
    this.robot = RobotConn.none,
    this.robotError,
    this.hotspot = HotspotConn.off,
    this.hotspotReason,
    this.hotspotManual = false,
    this.cameraOnline = false,
    this.hasKey = false,
  });
  final BrainHost active;
  final RobotConn robot;
  final String? robotError;
  final HotspotConn hotspot;
  final String? hotspotReason;
  final bool hotspotManual;
  final bool cameraOnline;
  final bool hasKey;

  bool get away => active == BrainHost.phone;

  AwayState copyWith({
    BrainHost? active,
    RobotConn? robot,
    String? robotError,
    bool clearRobotError = false,
    HotspotConn? hotspot,
    String? hotspotReason,
    bool clearHotspotReason = false,
    bool? hotspotManual,
    bool? cameraOnline,
    bool? hasKey,
  }) =>
      AwayState(
        active: active ?? this.active,
        robot: robot ?? this.robot,
        robotError: clearRobotError ? null : (robotError ?? this.robotError),
        hotspot: hotspot ?? this.hotspot,
        hotspotReason: clearHotspotReason ? null : (hotspotReason ?? this.hotspotReason),
        hotspotManual: hotspotManual ?? this.hotspotManual,
        cameraOnline: cameraOnline ?? this.cameraOnline,
        hasKey: hasKey ?? this.hasKey,
      );
}

/// Secret storage (Android keystore); overridden in tests.
final secretStoreProvider = Provider<SecretStore>((ref) => const KeystoreSecretStore());
final bleLinkProvider = Provider<BleRobotLink>((ref) => BleRobotLink());
final offlineBrainProvider = Provider<OfflineBrain>((ref) {
  final o = OfflineBrain();
  ref.onDispose(o.dispose);
  return o;
});
final offlineStatusProvider = StreamProvider<OfflineStatus>((ref) async* {
  final o = ref.watch(offlineBrainProvider);
  yield o.current;
  yield* o.status;
});

const manualHotspotPassKey = 'spike.hotspot.manual.pass';

class AwayController extends Notifier<AwayState> {
  PhoneBrain? _brain;
  Future<PhoneBrain>? _building;
  GeminiProvider? _gemini;
  Timer? _grace;
  Timer? _robotRetry;
  int _robotFails = 0;
  bool _robotLoop = false;
  final RobotServer _server = RobotServer();
  PhoneHotspot? _hotspot;
  String? _hotspotToken;
  Timer? _hotspotIdle;
  bool _cameraWanted = false;
  StreamSubscription<void>? _hubSub;
  AudioPlayer? _player;
  KokoroVoice? _kokoro;
  GeminiTtsVoice? _gtts; // Gemini natural voice (step 2 of the voice chain), with the owner's key

  SpikeHub get _hub => ref.read(brainClientProvider);

  @override
  AwayState build() {
    final hub = ref.watch(brainClientProvider);
    final sub = hub.lan.status.listen((_) => _evaluate());
    ref.listen(settingsProvider.select((s) => (s.awayMode, s.robotId, s.phoneSpeaks)), (_, _) {
      _evaluate();
      _applyVoice();
    });
    ref.onDispose(() {
      sub.cancel();
      _grace?.cancel();
      _robotRetry?.cancel();
      _hotspotIdle?.cancel();
      _hubSub?.cancel();
      _server.stop();
      _hotspot?.stop();
      _kokoro?.dispose();
      _gtts?.close();
      _player?.dispose();
    });
    Future.microtask(() async {
      await voicePicks.migrate(); // once: Spike -> energetic Fenrir (owner decision 30 Sep)
      await _loadKey();
      // the offline brain is part of the phone's on-device AI (the desktop gets it in a later update, and its
      // engine libraries are not in the light Windows package): never touched there
      if (AppPlatform.onDeviceAiPack) await ref.read(offlineBrainProvider).refresh();
      _evaluate();
    });
    return const AwayState();
  }

  PhoneBrain? get brain => _brain;

  // ---------------------------------------------------------------- the choice of brain
  bool _lanUnreachable(LinkStatus s) =>
      s.phase == LinkPhase.retrying ||
      s.phase == LinkPhase.authFailed ||
      s.phase == LinkPhase.versionMismatch ||
      s.phase == LinkPhase.idle ||
      (s.phase == LinkPhase.connecting && s.attempt >= 1);

  void _evaluate() {
    // the desktop app has its own brain on the same computer: it never becomes a phone brain
    if (AppPlatform.desktop) return;
    final settings = ref.read(settingsProvider);
    final lan = _hub.lan.current;
    if (lan.isConnected) {
      _grace?.cancel();
      _grace = null;
      if (state.away) unawaited(_goHome());
      return;
    }
    if (!settings.awayMode) {
      if (state.away) unawaited(_goHome());
      return;
    }
    if (state.away) {
      _ensureRobotLoop();
      return;
    }
    // never paired with a laptop, or it failed to answer: a short grace so a blip doesn't flip brains
    final neverHome = settings.endpoint == null;
    if (neverHome || _lanUnreachable(lan)) {
      _grace ??= Timer(Duration(milliseconds: neverHome ? 0 : 3000), () {
        _grace = null;
        final now = _hub.lan.current;
        if (!now.isConnected && ref.read(settingsProvider).awayMode) unawaited(_goAway());
      });
    }
  }

  Future<void> _goAway() async {
    final b = await _ensureBrain();
    if (_hub.lan.current.isConnected) return; // the laptop answered meanwhile
    await b.start();
    _hub.setActive(BrainHost.phone);
    state = state.copyWith(active: BrainHost.phone);
    _ensureRobotLoop();
    if (ref.read(settingsProvider).keepHotspot) unawaited(_hotspotUp());
  }

  Future<void> _goHome() async {
    _hub.setActive(BrainHost.laptop);
    state = state.copyWith(active: BrainHost.laptop, robot: RobotConn.none, cameraOnline: false);
    _robotLoop = false;
    _robotRetry?.cancel();
    await _hotspotDown(sendLeave: true);
    await _brain?.stop();
  }

  // ---------------------------------------------------------------- the phone brain
  Future<PhoneBrain> _ensureBrain() => _building ??= _build();

  Future<PhoneBrain> _build() async {
    final dog = Persona.fromToml(await rootBundle.loadString('assets/brain/spike.toml'));
    final cat = Persona.fromToml(await rootBundle.loadString('assets/brain/spicy.toml'));
    final settings = BrainSettings.fromToml(await rootBundle.loadString('assets/brain/default.toml'));
    final dir = await getApplicationSupportDirectory();
    final memory = PhoneMemory(file: File('${dir.path}/phone_brain/memory.json'));
    await memory.load();
    final offline = ref.read(offlineBrainProvider);
    final b = PhoneBrain(
      persona: {'dog': dog, 'cat': cat},
      settings: settings,
      memory: memory,
      cloud: () => _gemini,
      offline: () => offline.installed ? offline : null,
      voice: SilentVoice(),
      ear: AndroidEar(),
      appVersion: appVersion,
    );
    b.cameraWanted = _onCameraWanted;
    b.onRobotLink = (m) {
      if (m.brain == 'lan') _hub.retryNow(); // the robot has the home brain: so may we
      if (m.camera == true) _markCamera(true);
    };
    b.onRobotBusy = _hub.retryNow;
    b.onHotspotState = _onHotspotState;
    _hubSub = b.robots.changes.listen((_) => _onBoardsChanged());
    _brain = b;
    _hub.attachPhone(b);
    await _applyVoice();
    return b;
  }

  /// The phone's voice chain (voice_chain.dart): [laptop voice], Gemini natural
  /// voice when a key is saved, Kokoro when the voice pack is installed, Android's.
  Future<void> _applyVoice() async {
    final b = _brain;
    if (b == null) return;
    if (!ref.read(settingsProvider).phoneSpeaks) {
      b.voice = SilentVoice();
      return;
    }
    final pack = await voicePack();
    if (pack.installed) {
      _player ??= AudioPlayer();
      _kokoro ??= KokoroVoice(pack, _player!);
    }
    b.voice = VoiceChain.ordered(gemini: _gtts, kokoro: pack.installed ? _kokoro : null, android: AndroidVoice());
  }

  /// Gemini natural voice (step 2 of the owner's voice order), or null with no key.
  SpikeVoice? get geminiVoice => _gtts;

  /// The owner's Gemini voice pick per character (Settings > Hear Spike's voices).
  GeminiVoicePicks get voicePicks => GeminiVoicePicks(ref.read(prefsProvider));

  Future<KokoroPack> voicePack() async => KokoroPack(Directory('${(await getApplicationSupportDirectory()).path}/kokoro'));

  /// The voice pack was downloaded or deleted.
  Future<void> voiceChanged() async {
    _kokoro?.dispose();
    _kokoro = null;
    await _applyVoice();
  }

  // ---------------------------------------------------------------- the AI key
  Future<void> _loadKey() async {
    final key = await ref.read(secretStoreProvider).read(aiKeyName('gemini'));
    _gemini = (key == null || key.isEmpty) ? null : GeminiProvider(apiKey: key);
    _gtts?.close();
    _gtts = (key == null || key.isEmpty) ? null : GeminiTtsVoice(apiKey: key, voiceFor: voicePicks.voiceFor, styleFor: voicePicks.ttsStyleFor);
    state = state.copyWith(hasKey: _gemini != null);
    _brain?.modelsChanged();
    await _applyVoice();
  }

  /// Save a pasted key (tidied). Returns null, or why it was refused.
  Future<String?> saveKey(String raw) async {
    final key = tidyKey(raw);
    if (key.isEmpty) return 'Paste a key first';
    await ref.read(secretStoreProvider).write(aiKeyName('gemini'), key);
    await _loadKey();
    return null;
  }

  Future<void> deleteKey() async {
    await ref.read(secretStoreProvider).delete(aiKeyName('gemini'));
    await _loadKey();
  }

  /// "Test key": one tiny real request. Returns null when it works, else a plain message.
  Future<String?> testKey([String? raw]) async {
    final key = raw == null ? await ref.read(secretStoreProvider).read(aiKeyName('gemini')) : tidyKey(raw);
    if (key == null || key.isEmpty) return 'No key saved yet';
    final g = GeminiProvider(apiKey: key);
    try {
      await g.check();
      return null;
    } on LlmError catch (e) {
      return switch (e.kind) {
        LlmErrorKind.badKey => 'Google did not accept this key',
        LlmErrorKind.rateLimited => 'The key works, but its free quota is used up for now',
        LlmErrorKind.network => 'No internet connection',
        _ => 'Gemini did not answer (try again in a minute)',
      };
    } finally {
      g.close();
    }
  }

  void modelsChanged() => _brain?.modelsChanged();

  // ---------------------------------------------------------------- the robot over Bluetooth
  void _ensureRobotLoop() {
    if (_robotLoop || !state.away) return;
    if (ref.read(settingsProvider).robotId == null) return;
    _robotLoop = true;
    unawaited(_robotAttempt());
  }

  Future<void> _robotAttempt() async {
    _robotRetry?.cancel();
    final s = ref.read(settingsProvider);
    final b = _brain;
    if (!_robotLoop || !state.away || s.robotId == null || b == null) {
      _robotLoop = false;
      return;
    }
    if (b.robots.faceBle != null) return;
    final ble = ref.read(bleLinkProvider);
    try {
      if (!await ble.api.hasPermissions()) {
        state = state.copyWith(robot: RobotConn.needsPermission); // the owner grants it (Connect screen)
        _robotLoop = false;
        return;
      }
      state = state.copyWith(robot: RobotConn.connecting, clearRobotError: true);
      final pipe = await ble.connect(s.robotId!, name: s.robotName ?? 'Spike');
      final session = b.robots.attach(pipe);
      _robotFails = 0;
      await session.done;
      state = state.copyWith(robot: RobotConn.searching);
    } on BleLinkError catch (e) {
      _robotFails++;
      state = state.copyWith(
          robot: e.code == 'bluetooth_off' ? RobotConn.bluetoothOff : RobotConn.failed, robotError: e.code);
    } catch (e) {
      _robotFails++;
      state = state.copyWith(robot: RobotConn.failed, robotError: 'connect');
    }
    if (!_robotLoop || !state.away) return;
    final wait = Duration(seconds: min(30, 2 << min(_robotFails, 4)));
    _robotRetry = Timer(wait, () => unawaited(_robotAttempt()));
  }

  /// Pair a robot found by the Connect screen: remember it, connect (Android asks for the passkey).
  Future<void> useRobot(FoundRobot r) async {
    ref.read(settingsProvider.notifier).update((s) => s.copyWith(robotId: r.deviceId, robotName: r.name));
    _robotLoop = false;
    _robotFails = 0;
    if (!state.away && !_hub.lan.current.isConnected) await _goAway();
    _ensureRobotLoop();
  }

  Future<void> forgetRobot() async {
    _robotLoop = false;
    _robotRetry?.cancel();
    await _brain?.robots.closeLink('ble');
    ref.read(settingsProvider.notifier).update((s) => s.copyWith(clearRobot: true));
    state = state.copyWith(robot: RobotConn.none);
  }

  /// After the owner granted Bluetooth (Connect screen): try again now.
  void retryRobot() {
    _robotLoop = false;
    _robotFails = 0;
    _ensureRobotLoop();
  }

  void _onBoardsChanged() {
    final b = _brain;
    if (b == null) return;
    final ble = b.robots.faceBle != null;
    state = state.copyWith(
      robot: ble ? RobotConn.connected : (state.robot == RobotConn.connected ? RobotConn.searching : state.robot),
      cameraOnline: b.robots.hasCamera,
    );
    if (b.robots.hasCamera) _markCamera(true);
    if (ble && (_cameraWanted || ref.read(settingsProvider).keepHotspot) && state.hotspot == HotspotConn.off) {
      unawaited(_hotspotUp());
    }
  }

  void _markCamera(bool on) {
    if (on && !state.cameraOnline) {
      state = state.copyWith(cameraOnline: true);
    }
    if (on) unawaited(_brain?.robots.toFace(const RobotLinkAckMsg(camera: true)));
  }

  // ---------------------------------------------------------------- the hotspot (camera)
  void _onCameraWanted(bool want) {
    _cameraWanted = want;
    _hotspotIdle?.cancel();
    if (want) {
      unawaited(_hotspotUp());
    } else if (!ref.read(settingsProvider).keepHotspot) {
      // a minute of grace: flicking between tabs must not bounce the robot's Wi-Fi
      _hotspotIdle = Timer(const Duration(seconds: 60), () => unawaited(_hotspotDown(sendLeave: true)));
    }
  }

  Future<void> _hotspotUp({bool manual = false}) async {
    final b = _brain;
    if (b == null || !state.away) return;
    if (state.hotspot == HotspotConn.starting || state.hotspot == HotspotConn.joining || state.hotspot == HotspotConn.up) {
      return;
    }
    if (b.robots.faceBle == null) {
      state = state.copyWith(hotspot: HotspotConn.failed, hotspotReason: 'no_robot');
      return;
    }
    state = state.copyWith(hotspot: HotspotConn.starting, clearHotspotReason: true, hotspotManual: manual);
    final PhoneHotspot hs = manual ? ManualHotspot(_loadManual) : LocalOnlyHotspot();
    try {
      if (!await hs.requestPermission()) throw const HotspotError('permission');
      final info = await hs.start();
      _hotspot = hs;
      final port = await _server.start();
      final r = Random.secure();
      _hotspotToken = List.generate(32, (_) => r.nextInt(16).toRadixString(16)).join();
      _serverSub ??= _server.pipes.listen((p) => _brain?.robots.attach(p, token: _hotspotToken));
      state = state.copyWith(hotspot: HotspotConn.joining);
      final ok = await b.robots.toBle(
          HotspotJoinMsg(ssid: info.ssid, pass: info.pass, port: port, token: _hotspotToken!, host: ''));
      if (!ok) throw const HotspotError('generic', 'the robot did not take the details');
      _joinTimeout?.cancel();
      _joinTimeout = Timer(const Duration(seconds: 35), () {
        if (state.hotspot == HotspotConn.joining) unawaited(_hotspotFailed('timeout'));
      });
    } on HotspotError catch (e) {
      await _hotspotFailed(e.code, triedManual: manual);
    }
  }

  StreamSubscription<WsRobotPipe>? _serverSub;
  Timer? _joinTimeout;

  Future<(String, String)?> _loadManual() async {
    final ssid = ref.read(settingsProvider).manualHotspotSsid;
    final pass = await ref.read(secretStoreProvider).read(manualHotspotPassKey);
    if (ssid.isEmpty || pass == null) return null;
    return (ssid, pass);
  }

  Future<void> _hotspotFailed(String reason, {bool triedManual = false}) async {
    await _hotspotDown(sendLeave: false);
    // the phone can't make a hotspot the robot can join: the owner's own hotspot, if saved
    if (!triedManual && await _loadManual() != null) {
      state = state.copyWith(hotspot: HotspotConn.off);
      await _hotspotUp(manual: true);
      return;
    }
    state = state.copyWith(hotspot: HotspotConn.failed, hotspotReason: reason);
  }

  void _onHotspotState(HotspotStateMsg m) {
    switch (m.state) {
      case 'joined':
        _joinTimeout?.cancel();
        state = state.copyWith(hotspot: HotspotConn.up, clearHotspotReason: true);
      case 'failed':
        _joinTimeout?.cancel();
        unawaited(_hotspotFailed(m.reason ?? 'generic', triedManual: state.hotspotManual));
      case 'left':
        if (state.hotspot == HotspotConn.up) state = state.copyWith(hotspot: HotspotConn.off, cameraOnline: false);
    }
  }

  Future<void> _hotspotDown({required bool sendLeave}) async {
    _joinTimeout?.cancel();
    final b = _brain;
    if (b != null && sendLeave && state.hotspot != HotspotConn.off) {
      await b.robots.toBle(const HotspotLeaveMsg());
    }
    await b?.robots.closeLink('hotspot');
    await _server.stop();
    await _serverSub?.cancel();
    _serverSub = null;
    await _hotspot?.stop();
    _hotspot = null;
    _hotspotToken = null;
    if (state.hotspot != HotspotConn.failed) state = state.copyWith(hotspot: HotspotConn.off, cameraOnline: false);
  }

  /// Try the camera link again (after the owner saved a personal hotspot, say).
  void retryHotspot() {
    state = state.copyWith(hotspot: HotspotConn.off, clearHotspotReason: true);
    if (_cameraWanted || ref.read(settingsProvider).keepHotspot) unawaited(_hotspotUp());
  }

  Future<void> saveManualHotspot(String ssid, String pass) async {
    ref.read(settingsProvider.notifier).update((s) => s.copyWith(manualHotspotSsid: ssid.trim()));
    if (pass.isEmpty) {
      await ref.read(secretStoreProvider).delete(manualHotspotPassKey);
    } else {
      await ref.read(secretStoreProvider).write(manualHotspotPassKey, pass);
    }
  }
}

final awayProvider = NotifierProvider<AwayController, AwayState>(AwayController.new);
