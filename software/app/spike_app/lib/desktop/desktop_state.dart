/// The desktop app's own state (software/app/DESIGN.md "Desktop"): the built-in brain, the link to
/// it, "Start with Windows" and quitting. Riverpod, like the rest of the app.
library;

import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../away/ai/key_store.dart';
import '../core/brand.dart';
import '../protocol/client.dart';
import '../protocol/messages.dart';
import '../state/away.dart' show awayProvider, secretStoreProvider;
import '../state/link.dart';
import '../state/settings.dart';
import 'brain_sidecar.dart';
import 'desktop_channel.dart';

@immutable
class DesktopState {
  const DesktopState({
    this.brain = const BrainSidecarState(),
    this.startWithWindows = StartWithWindows.unknown,
    this.packaged = false,
    this.hasKey = false,
  });
  final BrainSidecarState brain;
  final StartWithWindows startWithWindows;
  final bool packaged;
  final bool hasKey;

  DesktopState copyWith({BrainSidecarState? brain, StartWithWindows? startWithWindows, bool? packaged, bool? hasKey}) =>
      DesktopState(
        brain: brain ?? this.brain,
        startWithWindows: startWithWindows ?? this.startWithWindows,
        packaged: packaged ?? this.packaged,
        hasKey: hasKey ?? this.hasKey,
      );
}

/// Where the built-in brain keeps its data: `%LOCALAPPDATA%\<internal id>\brain` (a rename of the
/// product never moves it; in the installed package Windows keeps it inside the package's own
/// storage and removes it on uninstall).
String brainHome([Map<String, String>? env]) {
  final e = env ?? Platform.environment;
  final dev = e['SPIKE_BRAIN_HOME']; // development and tests only: a scratch data folder
  if (dev != null && dev.isNotEmpty) return dev;
  final base = e['LOCALAPPDATA'] ?? Directory.systemTemp.path;
  return '$base\\${AppBrand.internalId}\\brain';
}

final desktopChannelProvider = Provider<DesktopChannel>((ref) => DesktopChannel());

final brainSidecarProvider = Provider<BrainSidecar>((ref) {
  final s = BrainSidecar(command: BrainCommand.locate(), home: brainHome());
  ref.onDispose(s.dispose);
  return s;
});

class DesktopController extends Notifier<DesktopState> {
  StreamSubscription<BrainSidecarState>? _sub;
  StreamSubscription<SpikeMessage>? _msgs;
  bool _booted = false;

  BrainSidecar get _brain => ref.read(brainSidecarProvider);
  DesktopChannel get _channel => ref.read(desktopChannelProvider);

  @override
  DesktopState build() {
    ref.onDispose(() {
      _sub?.cancel();
      _msgs?.cancel();
    });
    return const DesktopState();
  }

  Future<String?> _key() async {
    try {
      final k = await ref.read(secretStoreProvider).read(aiKeyName('gemini'));
      return (k == null || k.isEmpty) ? null : k;
    } catch (_) {
      return null;
    }
  }

  /// Start the built-in brain and connect to it. Called once at app start (desktop only).
  Future<void> boot() async {
    if (_booted) return;
    _booted = true;
    _sub = _brain.states.listen(_onBrain);
    _msgs = ref.read(brainClientProvider).messages.listen(_onMessage);
    unawaited(refreshStartWithWindows());
    unawaited(_channel.isPackaged().then((p) => state = state.copyWith(packaged: p)));
    final key = await _key();
    state = state.copyWith(hasKey: key != null);
    await _brain.start(geminiKey: key, mic: ref.read(settingsProvider).desktopMic);
  }

  void _onBrain(BrainSidecarState b) {
    final before = state.brain;
    state = state.copyWith(brain: b);
    if (b.up && b.port != null && (before.port != b.port || !before.up)) {
      // the app is the brain's first client, over loopback (no token needed there)
      final ep = BrainEndpoint(host: '127.0.0.1', port: b.port!, name: AppBrand.productName);
      ref.read(settingsProvider.notifier).rememberEndpoint(ep);
      ref.read(brainClientProvider).connect(ep);
    }
  }

  /// v1.8: the brain keeps the voice style picks (they can change from a phone too): follow them here.
  void _onMessage(SpikeMessage m) {
    final styles = switch (m) {
      BrainHello(:final voiceStyle) => voiceStyle,
      VoiceStyleMsg(:final styles) => styles,
      _ => null,
    };
    if (styles == null) return;
    final picks = ref.read(awayProvider.notifier).voicePicks;
    var changed = false;
    for (final e in styles.entries) {
      if (picks.styleFor(e.key).id != e.value) {
        unawaited(picks.pickStyle(e.key, e.value));
        changed = true;
      }
    }
    if (changed) state = state.copyWith(); // the voice card shows the new pick
  }

  /// The Gemini key was saved or removed: the brain starts again with it (it only reads it at start).
  Future<void> keyChanged() async {
    final key = await _key();
    state = state.copyWith(hasKey: key != null);
    await _brain.restart(geminiKey: key, mic: ref.read(settingsProvider).desktopMic);
  }

  /// "Listen for Spike on this computer's microphone".
  Future<void> setMic(bool on) async {
    ref.read(settingsProvider.notifier).update((s) => s.copyWith(desktopMic: on));
    await _brain.restart(geminiKey: await _key(), mic: on);
  }

  Future<void> retryBrain() async {
    await _brain.retry();
  }

  Future<void> refreshStartWithWindows() async {
    state = state.copyWith(startWithWindows: await _channel.startWithWindows());
  }

  Future<void> setStartWithWindows(bool on) async {
    state = state.copyWith(startWithWindows: await _channel.setStartWithWindows(on));
  }

  /// Quit for real (tray > Quit): the brain stops cleanly first.
  Future<void> shutdown() async {
    await ref.read(brainClientProvider).disconnect();
    await _brain.stop();
  }
}

final desktopProvider = NotifierProvider<DesktopController, DesktopState>(DesktopController.new);
