import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/haptics.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/names.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import '../../state/voice.dart';
import 'voice_pill.dart';

class TalkScreen extends ConsumerStatefulWidget {
  const TalkScreen({super.key});
  @override
  ConsumerState<TalkScreen> createState() => _TalkScreenState();
}

class _TalkScreenState extends ConsumerState<TalkScreen> {
  final _text = TextEditingController();
  final _focus = FocusNode();
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    _text.addListener(() {
      final has = _text.text.trim().isNotEmpty;
      if (has != _hasText) setState(() => _hasText = has);
    });
  }

  @override
  void dispose() {
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send([String? preset]) {
    final t = (preset ?? _text.text).trim();
    if (t.isEmpty) return;
    final cmds = ref.read(commandsProvider);
    if (!cmds.connected) {
      Haptics.error();
      showToast(context, 'Spike isn\'t connected. Connect him from Home.', icon: Icons.wifi_off_rounded);
      return;
    }
    Haptics.confirm();
    cmds.say(t);
    ref.read(chatProvider.notifier).addMine(t);
    if (preset == null) _text.clear();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final chat = ref.watch(chatProvider);
    final spike = ref.watch(spikeStateProvider);
    final name = ref.watch(settingsProvider.select((s) => s.nameFor(spike.mode)));
    final connected = ref.watch(linkStatusProvider.select((s) => s.value?.isConnected ?? false));
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;
    final voiceOn = ref.watch(voiceProvider.select((v) => v.on));
    // room for the nav bar, and for the voice pill above it while the mic is on
    final navSpace = bottomInset > 0 ? 8.0 : MediaQuery.paddingOf(context).bottom + 92 + (voiceOn ? voicePillRoom : 0);

    return Scaffold(
      resizeToAvoidBottomInset: false,
      body: SafeArea(
        bottom: false,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 6),
            child: Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Talk to $name', style: context.tt.headlineSmall),
                  const SizedBox(height: 2),
                  Text(
                    switch (spike.listening) {
                      'listening' || 'wake' => 'Listening...',
                      'thinking' => 'Thinking...',
                      'speaking' => 'Talking',
                      _ => connected ? (voiceOn ? 'The mic is on: just talk' : 'Type, or tap the mic and talk') : 'Not connected',
                    },
                    style: context.tt.bodySmall,
                  ),
                ]),
              ),
              StatusPill(label: moodLabel(spike.mood), icon: Icons.mood_rounded),
              if (chat.isNotEmpty)
                IconButton(
                  tooltip: 'Clear chat',
                  onPressed: () {
                    Haptics.tap();
                    ref.read(chatProvider.notifier).clear();
                  },
                  icon: Icon(Icons.delete_sweep_rounded, color: p.muted),
                ),
            ]),
          ),
          Expanded(
            child: chat.isEmpty
                ? ChatIdeas(name: name, onPick: _send)
                : ListView.builder(
                    reverse: true,
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                    itemCount: chat.length + (spike.listening == 'thinking' ? 1 : 0),
                    itemBuilder: (context, i) {
                      if (spike.listening == 'thinking') {
                        if (i == 0) return const TypingDots();
                        i -= 1;
                      }
                      final e = chat[chat.length - 1 - i];
                      return ChatBubble(key: ValueKey('${e.at.microsecondsSinceEpoch}-${e.from}'), entry: e, name: name);
                    },
                  ),
          ),
          AnimatedPadding(
            duration: const Duration(milliseconds: 200),
            padding: EdgeInsets.fromLTRB(12, 6, 12, (bottomInset > 0 ? bottomInset : 0) + navSpace),
            child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              Expanded(
                child: TextField(
                  controller: _text,
                  focusNode: _focus,
                  minLines: 1,
                  maxLines: 4,
                  textCapitalization: TextCapitalization.sentences,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  decoration: InputDecoration(
                    hintText: 'Message $name',
                    contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(28), borderSide: BorderSide.none),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 280),
                transitionBuilder: (c, a) => ScaleTransition(scale: CurvedAnimation(parent: a, curve: Springs.curve), child: c),
                child: _hasText
                    ? Pressable(
                        key: const ValueKey('send'),
                        onTap: _send,
                        semanticLabel: 'Send',
                        child: Container(
                          width: 56,
                          height: 56,
                          decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle),
                          child: Icon(Icons.arrow_upward_rounded, color: p.accentInk),
                        ),
                      )
                    : const MicButton(key: ValueKey('mic')),
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class ChatIdeas extends StatelessWidget {
  const ChatIdeas({super.key, required this.name, required this.onPick, this.embedded = false});
  final String name;
  final ValueChanged<String> onPick;

  /// Inside a panel that scrolls itself (desktop chat_panel.dart): a plain column, desktop wording.
  final bool embedded;
  static const _ideas = [
    "What's the time?",
    'Tell me a joke',
    'What do you remember about me?',
    "Let's play rock paper scissors",
    'Remind me to drink water in 10 minutes',
    'I had a long day',
  ];
  @override
  Widget build(BuildContext context) {
    final children = [
      Icon(Icons.forum_rounded, size: 54, color: context.sp.accent.withValues(alpha: 0.7)),
      const SizedBox(height: 14),
      Text('Say hi to $name', textAlign: TextAlign.center, style: context.tt.titleLarge),
      const SizedBox(height: 6),
      Text(
          embedded
              ? 'Just start typing, or press Space and talk. Or pick one:'
              : 'Everything stays on your laptop. Nothing you say leaves your home.',
          textAlign: TextAlign.center,
          style: context.tt.bodySmall),
      const SizedBox(height: 22),
      Wrap(alignment: WrapAlignment.center, spacing: 8, runSpacing: 8, children: [
        for (final (i, t) in _ideas.indexed)
          Entrance(index: i, child: PillButton(label: t, dense: true, onTap: () => onPick(t))),
      ]),
    ];
    if (embedded) return Column(mainAxisSize: MainAxisSize.min, children: children);
    return ListView(padding: const EdgeInsets.fromLTRB(20, 30, 20, 20), children: children);
  }
}

class ChatBubble extends StatefulWidget {
  const ChatBubble({super.key, required this.entry, required this.name});
  final ChatEntry entry;
  final String name;
  @override
  State<ChatBubble> createState() => ChatBubbleState();
}

class ChatBubbleState extends State<ChatBubble> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController.unbounded(vsync: this, value: 0)
    ..animateWith(SpringSimulation(Springs.bouncy, 0, 1, 0));
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final e = widget.entry;
    final mine = e.from == ChatFrom.me;
    if (e.from == ChatFrom.system) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Center(child: Text(e.text, style: context.tt.bodySmall)),
      );
    }
    final t = TimeOfDay.fromDateTime(e.at).format(context);
    final bubble = Container(
      // phone: most of the width; desktop: a comfortable reading measure (~70 characters)
      constraints: BoxConstraints(maxWidth: math.min(MediaQuery.sizeOf(context).width * 0.76, 560)),
      padding: const EdgeInsets.fromLTRB(16, 11, 16, 11),
      decoration: BoxDecoration(
        color: mine ? p.accent : p.card,
        border: mine ? null : Border.all(color: p.line),
        borderRadius: BorderRadius.only(
          topLeft: const Radius.circular(22),
          topRight: const Radius.circular(22),
          bottomLeft: Radius.circular(mine ? 22 : 6),
          bottomRight: Radius.circular(mine ? 6 : 22),
        ),
      ),
      child: Text(e.text, style: context.tt.bodyLarge?.copyWith(color: mine ? p.accentInk : p.ink, height: 1.3)),
    );
    return AnimatedBuilder(
      animation: _c,
      builder: (_, child) => Opacity(
        opacity: _c.value.clamp(0.0, 1.0),
        child: Transform.translate(
          offset: Offset(0, (1 - _c.value) * 18),
          child: Transform.scale(scale: 0.9 + 0.1 * _c.value, alignment: mine ? Alignment.bottomRight : Alignment.bottomLeft, child: child),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Column(crossAxisAlignment: mine ? CrossAxisAlignment.end : CrossAxisAlignment.start, children: [
          bubble,
          const SizedBox(height: 4),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              if (!mine && e.mood != null) ...[
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(color: p.accent.withValues(alpha: 0.14), borderRadius: BorderRadius.circular(10)),
                  child: Text(moodLabel(e.mood), style: context.tt.labelSmall?.copyWith(color: p.accent, fontWeight: FontWeight.w800)),
                ),
                const SizedBox(width: 6),
              ],
              if (e.voice) ...[Icon(Icons.mic_rounded, size: 12, color: p.muted), const SizedBox(width: 3)],
              Text(t, style: context.tt.labelSmall?.copyWith(color: p.muted)),
            ]),
          ),
        ]),
      ),
    );
  }
}

class TypingDots extends StatefulWidget {
  const TypingDots({super.key});
  @override
  State<TypingDots> createState() => TypingDotsState();
}

class TypingDotsState extends State<TypingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat();
  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 6),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
        decoration: BoxDecoration(color: p.card, borderRadius: BorderRadius.circular(22), border: Border.all(color: p.line)),
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, _) => Row(mainAxisSize: MainAxisSize.min, children: [
            for (var i = 0; i < 3; i++)
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 3),
                width: 8,
                height: 8,
                transform: Matrix4.translationValues(0, -4 * _bump((_c.value - i * 0.15) % 1.0), 0),
                decoration: BoxDecoration(color: p.muted, shape: BoxShape.circle),
              ),
          ]),
        ),
      ),
    );
  }

  static double _bump(double t) => t < 0.4 ? (t < 0.2 ? t / 0.2 : (0.4 - t) / 0.2) : 0;
}

/// Tap to start listening, tap again to stop (owner decision 30 Sep). The same
/// session as the voice pill (state/voice.dart): it keeps listening on every
/// screen. The ring breathes with your voice.
class MicButton extends ConsumerWidget {
  const MicButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final p = context.sp;
    final v = ref.watch(voiceProvider);
    final on = v.on;
    final live = v.phase == VoicePhase.listening;
    return Pressable(
      haptic: false, // start and stop have their own haptics (Haptics.voiceOn / voiceOff)
      scale: 0.9,
      semanticLabel: on ? 'Stop listening' : 'Start listening',
      onTap: () => ref.read(voiceProvider.notifier).toggle(),
      child: AnimatedScale(
        scale: on ? 1.08 : 1,
        duration: const Duration(milliseconds: 420),
        curve: Springs.curve,
        child: SizedBox(
          width: 56,
          height: 56,
          child: Stack(alignment: Alignment.center, clipBehavior: Clip.none, children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 90),
              width: 56 + (live ? 26 * v.level + 8 : (on ? 6 : 0)),
              height: 56 + (live ? 26 * v.level + 8 : (on ? 6 : 0)),
              decoration: BoxDecoration(color: Brand.tongue.withValues(alpha: on ? 0.25 : 0), shape: BoxShape.circle),
            ),
            AnimatedContainer(
              duration: const Duration(milliseconds: 250),
              width: 56,
              height: 56,
              decoration: BoxDecoration(color: on ? Brand.tongue : p.cardHi, shape: BoxShape.circle, border: Border.all(color: p.line)),
              child: Icon(on ? Icons.graphic_eq_rounded : Icons.mic_rounded, color: on ? Colors.white : p.ink),
            ),
          ]),
        ),
      ),
    );
  }
}