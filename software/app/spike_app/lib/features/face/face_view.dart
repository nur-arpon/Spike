import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/haptics.dart';
import '../../core/spike_web_view.dart';
import '../../protocol/messages.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import '../../state/voice_out.dart';
import '../studio/studio_state.dart';

/// An event the face page reported (pat, boop, state, caption, ready).
class FaceEvent {
  const FaceEvent(this.name, this.data);
  final String name;
  final Map<String, dynamic> data;
}

/// Talks to assets/face/face_host.js inside one WebView (core/spike_web_view.dart: Android's
/// WebView on the phone, Edge WebView2 on Windows).
class FaceController {
  FaceController() {
    web = SpikeWebController(asset: 'assets/face/face_host.html', channels: {'SpikeBridge': _onPost});
  }

  late final SpikeWebController web;
  final _events = StreamController<FaceEvent>.broadcast();
  final _ready = Completer<void>();
  final Map<int, Completer<Object?>> _calls = {};
  int _nextCall = 0;
  bool _disposed = false;

  Stream<FaceEvent> get events => _events.stream;
  Future<void> get ready => _ready.future;
  bool get isReady => _ready.isCompleted;

  void _onPost(String raw) {
    Map<String, dynamic> m;
    try {
      m = jsonDecode(raw) as Map<String, dynamic>;
    } catch (_) {
      return;
    }
    final ev = m['ev'] as String? ?? '';
    if (ev == 'ready' && !_ready.isCompleted) _ready.complete();
    if (ev == 'result') {
      final c = _calls.remove(m['id']);
      if (c == null) return;
      if (m['ok'] == true) {
        c.complete(m['value']);
      } else {
        c.completeError(StateError(m['value'].toString()));
      }
      return;
    }
    if (!_events.isClosed) _events.add(FaceEvent(ev, m));
  }

  Future<void> js(String code) async {
    if (_disposed) return;
    await ready;
    if (_disposed) return;
    try {
      await web.runJs(code);
    } catch (e) {
      debugPrint('face js failed: $e');
    }
  }

  /// Call SpikeFace.call(method) and wait for its answer.
  Future<Object?> call(String method, [Map<String, Object?> args = const {}]) async {
    await ready;
    final id = ++_nextCall;
    final c = Completer<Object?>();
    _calls[id] = c;
    await js('SpikeFace.call($id, ${jsonEncode(method)}, ${jsonEncode(args)})');
    return c.future.timeout(const Duration(seconds: 8), onTimeout: () {
      _calls.remove(id);
      throw TimeoutException('face call $method');
    });
  }

  Future<void> handle(SpikeMessage m) => js('SpikeFace.handle(${jsonEncode(m.toJson())})');
  Future<void> setMode(String mode) => js('SpikeFace.setMode(${jsonEncode(mode)})');
  Future<void> setMood(String mood) => js('SpikeFace.setMood(${jsonEncode(mood)})');
  Future<void> playAction(String a) => js('SpikeFace.playAction(${jsonEncode(a)})');
  Future<void> event(String e) => js('SpikeFace.event(${jsonEncode(e)})');
  Future<void> pat() => js('SpikeFace.pat()');
  Future<void> boop() => js('SpikeFace.boop()');
  Future<void> song() => js('SpikeFace.song()');
  Future<void> setSound(bool on) => js('SpikeFace.setSound(${on ? 'true' : 'false'})');
  Future<void> setInteractive(bool on) => js('SpikeFace.setInteractive(${on ? 'true' : 'false'})');
  Future<void> setPaused(bool on) => js('SpikeFace.setPaused(${on ? 'true' : 'false'})');
  Future<void> setNames(String dog, String cat) => js('SpikeFace.setNames(${jsonEncode(dog)}, ${jsonEncode(cat)})');
  Future<void> setRecipe(Map<String, dynamic> recipe, String mode) =>
      js('SpikeFace.setRecipe(${jsonEncode(recipe)}, ${jsonEncode(mode)})');

  void dispose() {
    _disposed = true;
    for (final c in _calls.values) {
      if (!c.isCompleted) c.completeError(StateError('disposed'));
    }
    _calls.clear();
    _events.close();
    web.dispose();
  }
}

/// Protocol messages the phone face mirrors from the brain.
bool _mirrors(SpikeMessage m) =>
    m is BrainHello ||
    m is MoodMsg ||
    m is ActionMsg ||
    m is EventMsg ||
    m is SoundMsg ||
    m is LookAtMsg ||
    m is SetModeMsg ||
    m is SetRecipeMsg ||
    m is ListeningMsg ||
    (m is SayMsg && !m.play) || // v1.5: what THIS phone plays reaches the face as it starts (nowSaying)
    m is StopSpeakingMsg ||
    m is AlarmMsg ||
    m is GameMsg;

/// Spike's live face. When [live] it mirrors the brain's face messages and
/// sends pats/boops back; otherwise it is a local preview (Studio).
class FaceView extends ConsumerStatefulWidget {
  const FaceView({super.key, this.live = true, this.controller, this.onEvent, this.interactive = true});
  final bool live;
  final FaceController? controller;
  final void Function(FaceEvent e)? onEvent;
  final bool interactive;

  @override
  ConsumerState<FaceView> createState() => _FaceViewState();
}

class _FaceViewState extends ConsumerState<FaceView> {
  late final FaceController _face = widget.controller ?? FaceController();
  StreamSubscription<SpikeMessage>? _msgs;
  StreamSubscription<SayMsg>? _saying;
  StreamSubscription<FaceEvent>? _evs;

  @override
  void initState() {
    super.initState();
    _evs = _face.events.listen(_onFaceEvent);
    _face.ready.then((_) => _sync());
    if (widget.live) {
      _msgs = ref.read(brainClientProvider).messages.listen((m) {
        if (_mirrors(m)) _face.handle(m);
      });
      _saying = ref.read(nowSayingProvider).listen(_face.handle); // lip-sync with the phone's own playback
    }
  }

  Future<void> _sync() async {
    if (!mounted) return;
    final s = ref.read(settingsProvider);
    await _face.setNames(s.dogName, s.catName);
    if (!widget.live) {
      await _face.setSound(s.faceSounds);
      return; // the Studio drives its preview's recipe and mode itself
    }
    final recipes = ref.read(studioProvider);
    for (final mode in const ['dog', 'cat']) {
      final r = recipes.current[mode];
      if (r != null) await _face.setRecipe(r, mode);
    }
    await _face.setMode(ref.read(spikeStateProvider).mode);
    await _face.setSound(s.faceSounds); // owner decision 29 Sep: connected or not
    await _face.setInteractive(widget.interactive);
  }


  void _onFaceEvent(FaceEvent e) {
    if (!widget.live) {
      widget.onEvent?.call(e);
      return;
    }
    final cmds = ref.read(commandsProvider);
    switch (e.name) {
      case 'pat':
        Haptics.purr();
        cmds.pat();
      case 'boop':
        Haptics.confirm();
        cmds.boop();
      case 'state':
        final mood = e.data['mood'] as String?;
        if (mood != null && !ref.read(brainClientProvider).current.isConnected) {
          ref.read(spikeStateProvider.notifier).localMood(mood);
        }
      default:
        break;
    }
    widget.onEvent?.call(e);
  }

  @override
  void dispose() {
    _msgs?.cancel();
    _saying?.cancel();
    _evs?.cancel();
    if (widget.controller == null) _face.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // keep names, recipes, sound and mode in step with the rest of the app
    ref.listen(settingsProvider, (_, _) => _sync());
    if (widget.live) {
      ref.listen(studioProvider, (_, _) => _sync());
      ref.listen(linkStatusProvider.select((s) => s.value?.isConnected), (_, _) => _sync());
      ref.listen(spikeStateProvider.select((s) => s.mode), (_, m) => _face.setMode(m));
    }
    return _face.web.view();
  }
}
