/// The conversation as a panel (desktop, software/app/DESIGN.md "Desktop"): Home's right pane and
/// the Talk page's main column. Same bubbles, typing dots and mic as the phone's Talk screen.
///
/// Natural use on a laptop: the owner can just start typing anywhere (the key goes to the visible
/// panel's box, [ChatPanel.typeInto]), Enter sends, Esc leaves the box, and Space (outside a text
/// box) turns the microphone on or off (app.dart).
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import 'talk_screen.dart' show ChatBubble, ChatIdeas, MicButton, TypingDots;

class ChatPanel extends ConsumerStatefulWidget {
  const ChatPanel({super.key, this.header = true, this.ideas = true});

  /// Show the "Talk to Spike" header with the listening state and Clear.
  final bool header;

  /// Show conversation starters while the chat is empty.
  final bool ideas;

  /// The panel on screen now (the last one built), for type-anywhere.
  static _ChatPanelState? _active;

  /// A printable key pressed while no text box has focus: it starts a message in the visible panel.
  static bool typeInto(String character) {
    final s = _active;
    if (s == null || !s.mounted) return false;
    s._focus.requestFocus();
    s._text.text = s._text.text + character;
    s._text.selection = TextSelection.collapsed(offset: s._text.text.length);
    return true;
  }

  @override
  ConsumerState<ChatPanel> createState() => _ChatPanelState();
}

class _ChatPanelState extends ConsumerState<ChatPanel> {
  final _text = TextEditingController();
  final _focus = FocusNode();
  bool _hasText = false;

  @override
  void initState() {
    super.initState();
    ChatPanel._active = this;
    _text.addListener(() {
      final has = _text.text.trim().isNotEmpty;
      if (has != _hasText) setState(() => _hasText = has);
    });
  }

  @override
  void dispose() {
    if (identical(ChatPanel._active, this)) ChatPanel._active = null;
    _text.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _send([String? preset]) {
    final t = (preset ?? _text.text).trim();
    if (t.isEmpty) return;
    final cmds = ref.read(commandsProvider);
    if (!cmds.connected) {
      showToast(context, 'Spike\'s brain is still starting. Try again in a moment.', icon: Icons.hourglass_top_rounded);
      return;
    }
    Haptics.confirm();
    cmds.say(t);
    ref.read(chatProvider.notifier).addMine(t);
    if (preset == null) _text.clear();
  }

  @override
  Widget build(BuildContext context) {
    ChatPanel._active = this; // the most recently shown panel takes typed keys
    final p = context.sp;
    final chat = ref.watch(chatProvider);
    final spike = ref.watch(spikeStateProvider);
    final name = ref.watch(settingsProvider.select((s) => s.nameFor(spike.mode)));
    final state = switch (spike.listening) {
      'listening' || 'wake' => 'Listening...',
      'thinking' => 'Thinking...',
      'speaking' => 'Talking',
      _ => 'Type, or press Space and talk',
    };
    return Container(
      decoration: BoxDecoration(
        color: p.card,
        borderRadius: BorderRadius.circular(Radii.card),
        border: Border.all(color: p.line),
      ),
      child: Column(children: [
        if (widget.header)
          Padding(
            padding: const EdgeInsets.fromLTRB(Space.x6, Space.x4, Space.x3, Space.x2),
            child: Row(children: [
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Talk to $name', style: context.tt.titleMedium),
                  Text(state, style: context.tt.bodySmall),
                ]),
              ),
              if (chat.isNotEmpty)
                IconButton(
                  tooltip: 'Clear the conversation',
                  onPressed: () => ref.read(chatProvider.notifier).clear(),
                  icon: Icon(Icons.delete_sweep_rounded, color: p.muted),
                ),
            ]),
          ),
        if (widget.header) Divider(height: 1, color: p.line),
        Expanded(
          child: chat.isEmpty
              ? (widget.ideas ? _Starters(name: name, onPick: _send) : const SizedBox.shrink())
              : ListView.builder(
                  reverse: true,
                  padding: const EdgeInsets.fromLTRB(Space.x4, Space.x3, Space.x4, Space.x3),
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
        Padding(
          padding: const EdgeInsets.fromLTRB(Space.x3, Space.x2, Space.x3, Space.x3),
          child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Expanded(
              child: CallbackShortcuts(
                bindings: {const SingleActivator(LogicalKeyboardKey.escape): () => _focus.unfocus()},
                child: TextField(
                  controller: _text,
                  focusNode: _focus,
                  minLines: 1,
                  maxLines: 4,
                  textCapitalization: TextCapitalization.sentences,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) {
                    _send();
                    _focus.requestFocus(); // keep typing
                  },
                  decoration: InputDecoration(
                    hintText: 'Message $name',
                    filled: true,
                    fillColor: p.cardHi,
                    contentPadding: const EdgeInsets.symmetric(horizontal: Space.x5, vertical: Space.x4),
                    border: OutlineInputBorder(borderRadius: BorderRadius.circular(Radii.card), borderSide: BorderSide.none),
                  ),
                ),
              ),
            ),
            const SizedBox(width: Space.x2),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 240),
              transitionBuilder: (c, a) => ScaleTransition(scale: CurvedAnimation(parent: a, curve: Springs.smoothCurve), child: c),
              child: _hasText
                  ? Tooltip(
                      key: const ValueKey('send'),
                      message: 'Send (Enter)',
                      child: Pressable(
                        onTap: _send,
                        semanticLabel: 'Send',
                        child: Container(
                          width: 56,
                          height: 56,
                          decoration: BoxDecoration(color: p.accent, shape: BoxShape.circle),
                          child: Icon(Icons.arrow_upward_rounded, color: p.accentInk),
                        ),
                      ),
                    )
                  : const Tooltip(key: ValueKey('mic'), message: 'Talk (Space)', child: MicButton()),
            ),
          ]),
        ),
      ]),
    );
  }
}

class _Starters extends StatelessWidget {
  const _Starters({required this.name, required this.onPick});
  final String name;
  final ValueChanged<String> onPick;
  @override
  Widget build(BuildContext context) => LayoutBuilder(
        builder: (context, c) => SingleChildScrollView(
          padding: const EdgeInsets.all(Space.x6),
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: math.max(0, c.maxHeight - Space.x12)),
            child: Center(child: ChatIdeas(name: name, onPick: onPick, embedded: true)),
          ),
        ),
      );
}
