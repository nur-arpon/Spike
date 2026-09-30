import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/haptics.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../desktop/desktop_page.dart';
import '../../protocol/messages.dart';
import '../../state/link.dart';
import '../../state/settings.dart';

/// What Spike remembers, with a forget button per fact (protocol v1.2
/// `memory` / `memory_forget` / `memory_forget_all`). The list is never
/// stored on the phone: it is shown only while Spike is connected.
class MemoriesScreen extends ConsumerStatefulWidget {
  const MemoriesScreen({super.key, this.embedded = false});

  /// Inside another page (the desktop's Life): no app bar of its own.
  final bool embedded;
  @override
  ConsumerState<MemoriesScreen> createState() => _MemoriesScreenState();
}

class _MemoriesScreenState extends ConsumerState<MemoriesScreen> {
  final _remember = TextEditingController();

  @override
  void initState() {
    super.initState();
    // fresh list on open (the brain also sends it on connect and on every change)
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final cmds = ref.read(commandsProvider);
      if (cmds.connected && !cmds.legacy) cmds.refreshMemory();
    });
  }

  @override
  void dispose() {
    _remember.dispose();
    super.dispose();
  }

  bool _ready() {
    if (ref.read(commandsProvider).connected) return true;
    Haptics.error();
    showToast(context, 'Connect Spike first. His memory lives on the laptop.', icon: Icons.wifi_off_rounded);
    return false;
  }

  String get _name => ref.read(settingsProvider).nameFor(ref.read(spikeStateProvider).mode);

  Future<void> _forgetOne(MemoryItem m) async {
    if (!_ready()) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Forget this?'),
        content: Text('"${m.text}"\n\n$_name will not remember it any more.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Keep it')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Brand.tongue),
            onPressed: () => Navigator.pop(c, true),
            child: const Text('Forget'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    Haptics.confirm();
    ref.read(commandsProvider).forgetFact(m.id);
  }

  Future<void> _forgetAll() async {
    final name = _name;
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('Make $name forget everything?'),
        content: Text('Every fact $name has learned about you is wiped from the laptop. This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Keep them')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: Brand.tongue),
            onPressed: () => Navigator.pop(c, true),
            child: const Text('Forget everything'),
          ),
        ],
      ),
    );
    if (ok != true || !mounted || !_ready()) return;
    final cmds = ref.read(commandsProvider);
    if (cmds.legacy) {
      // a v1.1 brain: the spoken way ("forget everything", then "yes" within 30 s)
      cmds.say('forget everything');
      await Future<void>.delayed(const Duration(milliseconds: 1800));
      cmds.say('yes, forget everything');
    } else {
      cmds.forgetEverything();
    }
    Haptics.thud();
    if (mounted) showToast(context, '$name has forgotten everything about you', icon: Icons.delete_sweep_rounded);
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final mode = ref.watch(spikeStateProvider.select((s) => s.mode));
    final name = ref.watch(settingsProvider.select((s) => s.nameFor(mode)));
    final mem = ref.watch(memoryProvider);
    final connected = ref.watch(linkStatusProvider.select((s) => s.value?.isConnected ?? false));
    final legacy = ref.watch(commandsProvider).legacy;
    return Scaffold(
      backgroundColor: widget.embedded ? Colors.transparent : null,
      appBar: widget.embedded ? null : AppBar(title: Text('$name\'s memory')),
      body: ListView(
        padding: widget.embedded ? EdgeInsets.zero : EdgeInsets.fromLTRB(20, 4, 20, 30 + MediaQuery.paddingOf(context).bottom),
        children: [
          // embedded (the desktop's Life): the pane's own title says what this is
          if (!widget.embedded) SpikeCard(
            gradient: LinearGradient(
              colors: context.isDark ? [const Color(0xFF3A2A1F), const Color(0xFF231A14)] : [Brand.cream, const Color(0xFFF8EBDA)],
            ),
            child: Row(children: [
              const Icon(Icons.auto_stories_rounded, color: Brand.tongue),
              const SizedBox(width: 12),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(
                    !connected
                        ? 'What $name remembers'
                        : mem.synced
                            ? '$name remembers ${mem.total ?? mem.items.length} ${(mem.total ?? mem.items.length) == 1 ? 'thing' : 'things'}'
                            : 'Asking $name…',
                    style: context.tt.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text('Names, likes, plans you told him. Kept only on your laptop, never on this phone.',
                      style: context.tt.bodySmall?.copyWith(color: p.ink)),
                ]),
              ),
            ]),
          ),
          if (!widget.embedded) const SizedBox(height: 12),
          if (!connected)
            _Note(icon: Icons.wifi_off_rounded, text: widget.embedded ? 'Starting $name\'s brain...' : 'Connect $name to see what he remembers.')
          else if (legacy)
            _Note(icon: Icons.system_update_rounded, text: "$name's brain is older than this app: update it to see the list.")
          else if (mem.synced && mem.items.isEmpty)
            _Note(icon: Icons.spa_rounded, text: 'Nothing yet. Tell $name about yourself and he will remember.')
          else
            for (final (i, m) in mem.items.indexed)
              Entrance(index: i < 12 ? i : 12, key: ValueKey(m.id), child: _FactTile(m: m, onForget: () => _forgetOne(m))),
          if (mem.total != null && mem.total! > mem.items.length)
            Padding(
              padding: const EdgeInsets.only(top: 4, left: 6),
              child: Text('Showing the newest ${mem.items.length} of ${mem.total}.', style: context.tt.bodySmall),
            ),
          if (widget.embedded) const PaneTitle('Teach him something', subtitle: 'He keeps it on this computer') else const SectionHeader('Teach him something'),
          Row(children: [
            Expanded(
              child: TextField(
                controller: _remember,
                textCapitalization: TextCapitalization.sentences,
                decoration: const InputDecoration(hintText: 'I love green tea'),
              ),
            ),
            const SizedBox(width: 10),
            PillButton(
              label: 'Remember',
              dense: true,
              onTap: () {
                final t = _remember.text.trim();
                if (t.isEmpty || !_ready()) return;
                Haptics.confirm();
                ref.read(commandsProvider).say('remember that $t');
                _remember.clear();
              },
            ),
          ]),
          if (widget.embedded) const PaneTitle('Forget', subtitle: 'Privacy comes first') else const SectionHeader('Forget', subtitle: 'Privacy comes first'),
          SpikeCard(
            padding: EdgeInsets.zero,
            child: ListTile(
              leading: const Icon(Icons.delete_forever_rounded, color: Brand.tongue),
              title: const Text('Forget everything', style: TextStyle(color: Brand.tongue, fontWeight: FontWeight.w700)),
              subtitle: const Text('Wipes his whole memory of you. Alarms stay.'),
              onTap: _forgetAll,
            ),
          ),
        ],
      ),
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({required this.icon, required this.text});
  final IconData icon;
  final String text;
  @override
  Widget build(BuildContext context) => SpikeCard(
        child: Row(children: [
          Icon(icon, color: context.sp.muted),
          const SizedBox(width: 12),
          Expanded(child: Text(text, style: context.tt.bodySmall)),
        ]),
      );
}

const _kindIcons = {
  'preference': Icons.favorite_rounded,
  'birthday': Icons.cake_rounded,
  'commitment': Icons.event_note_rounded,
  'person': Icons.people_alt_rounded,
  'name': Icons.badge_rounded,
};

class _FactTile extends StatelessWidget {
  const _FactTile({required this.m, required this.onForget});
  final MemoryItem m;
  final VoidCallback onForget;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final at = DateTime.fromMillisecondsSinceEpoch(m.at * 1000);
    final ago = DateTime.now().difference(at);
    final when = ago.inDays >= 1
        ? '${ago.inDays} ${ago.inDays == 1 ? 'day' : 'days'} ago'
        : ago.inHours >= 1
            ? '${ago.inHours} h ago'
            : 'just now';
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: SpikeCard(
        padding: const EdgeInsets.fromLTRB(16, 10, 4, 10),
        child: Row(children: [
          Icon(_kindIcons[m.kind] ?? Icons.lightbulb_rounded, color: p.accent, size: 22),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(m.text, style: context.tt.bodyMedium?.copyWith(color: p.ink)),
              const SizedBox(height: 2),
              Text(when, style: context.tt.bodySmall),
            ]),
          ),
          IconButton(tooltip: 'Forget this', onPressed: onForget, icon: Icon(Icons.close_rounded, color: p.muted)),
        ]),
      ),
    );
  }
}
