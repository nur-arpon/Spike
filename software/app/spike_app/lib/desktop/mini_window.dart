/// The mini window (desktop): Spike's face in a small window that stays on top, for talking to him
/// while working in another app (software/app/DESIGN.md "Desktop > Natural use", task b).
///
/// Ctrl+M or the navigation's "Mini window" enters it; Esc, the expand button or a double click
/// on the face returns to the full window at exactly its previous place and size.
/// Size: the face at 400 px wide (its 480:272 aspect -> 227 px high; 5/6 of the robot's own
/// screen, readable at a glance from the side of a laptop) plus one 56 px control row.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:window_manager/window_manager.dart';

import '../core/layout.dart';
import '../core/theme.dart';
import '../features/face/face_view.dart';
import '../features/talk/talk_screen.dart' show MicButton;
import '../state/link.dart';
import '../state/settings.dart';

/// The face width in the mini window (see the file comment).
const miniFaceWidth = 400.0;

class MiniWindowController extends Notifier<bool> {
  Rect? _saved;
  bool _wasMaximized = false;

  @override
  bool build() => false;

  /// [viewSize]: the Flutter view's size now (MediaQuery), to measure the window frame exactly.
  Future<void> enter([Size? viewSize]) async {
    if (state) return;
    try {
      _wasMaximized = await windowManager.isMaximized();
      if (_wasMaximized) await windowManager.unmaximize();
      _saved = await windowManager.getBounds();
      // the frame (borders + title bar) = the outer window minus what Flutter draws in
      final frame = viewSize == null ? const Size(16, 39) : Size(_saved!.width - viewSize.width, _saved!.height - viewSize.height);
      state = true;
      final faceH = miniFaceWidth / Ratios.face;
      // the client area: face + one control row, with the window frame added by Windows
      const pad = Space.x2;
      final client = Size(miniFaceWidth + 2 * pad, faceH + 56 + 3 * pad);
      await windowManager.setMinimumSize(client);
      await windowManager.setSize(Size(client.width + frame.width, client.height + frame.height));
      await windowManager.setAlwaysOnTop(true);
      await windowManager.setAlignment(Alignment.bottomRight, animate: true);
    } catch (e) {
      debugPrint('mini window: $e');
    }
  }

  Future<void> leave() async {
    if (!state) return;
    state = false;
    try {
      await windowManager.setAlwaysOnTop(false);
      await windowManager.setMinimumSize(const Size(900, 620));
      if (_saved != null) await windowManager.setBounds(_saved!, animate: true);
      if (_wasMaximized) await windowManager.maximize();
    } catch (e) {
      debugPrint('mini window: $e');
    }
  }
}

final miniWindowProvider = NotifierProvider<MiniWindowController, bool>(MiniWindowController.new);

class MiniView extends ConsumerStatefulWidget {
  const MiniView({super.key});
  @override
  ConsumerState<MiniView> createState() => _MiniViewState();
}

class _MiniViewState extends ConsumerState<MiniView> {
  final _face = FaceController();

  @override
  void dispose() {
    _face.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final spike = ref.watch(spikeStateProvider);
    final name = ref.watch(settingsProvider.select((s) => s.nameFor(spike.mode)));
    final status = switch (spike.listening) {
      'listening' || 'wake' => 'Listening...',
      'thinking' => 'Thinking...',
      'speaking' => spike.caption ?? 'Talking',
      _ => spike.caption ?? 'Space to talk',
    };
    return CallbackShortcuts(
      bindings: {const SingleActivator(LogicalKeyboardKey.escape): () => ref.read(miniWindowProvider.notifier).leave()},
      child: Focus(
        autofocus: true,
        child: Scaffold(
          backgroundColor: p.bg,
          body: Padding(
            padding: const EdgeInsets.all(Space.x2),
            child: Column(children: [
              GestureDetector(
                onDoubleTap: () => ref.read(miniWindowProvider.notifier).leave(),
                child: Container(
                  padding: const EdgeInsets.all(Space.x1),
                  decoration: BoxDecoration(color: Brand.chocolate, borderRadius: BorderRadius.circular(Radii.tile)),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(Radii.tile - Space.x1),
                    child: AspectRatio(aspectRatio: Ratios.face, child: FaceView(controller: _face)),
                  ),
                ),
              ),
              const SizedBox(height: Space.x2),
              SizedBox(
                height: 56,
                child: Row(children: [
                  const MicButton(),
                  const SizedBox(width: Space.x3),
                  Expanded(
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(name, style: context.tt.labelLarge?.copyWith(fontWeight: FontWeight.w800)),
                      Text(status, maxLines: 1, overflow: TextOverflow.ellipsis, style: context.tt.bodySmall),
                    ]),
                  ),
                  IconButton(
                    tooltip: 'Back to the full window (Esc)',
                    onPressed: () => unawaited(ref.read(miniWindowProvider.notifier).leave()),
                    icon: const Icon(Icons.open_in_full_rounded),
                  ),
                ]),
              ),
            ]),
          ),
        ),
      ),
    );
  }
}
