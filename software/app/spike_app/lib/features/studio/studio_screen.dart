import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/haptics.dart';
import '../../core/layout.dart';
import '../../core/platform.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';
import '../../core/widgets.dart';
import '../../protocol/messages.dart';
import '../../state/link.dart';
import '../../state/settings.dart';
import '../face/face_view.dart';
import 'studio_state.dart';
import 'studio_widgets.dart';

/// The face_v2 Face Studio, rebuilt as native Flutter controls around the
/// real face engine (a WebView preview). Every option list comes from the
/// bundled recipe.js, so the Studio can't drift from what the robot draws.
class StudioScreen extends ConsumerStatefulWidget {
  const StudioScreen({super.key});
  @override
  ConsumerState<StudioScreen> createState() => _StudioScreenState();
}

class _StudioScreenState extends ConsumerState<StudioScreen> with SingleTickerProviderStateMixin {
  final _face = FaceController();
  late final AnimationController _dice = AnimationController.unbounded(vsync: this);
  String _mode = 'dog';
  Map<String, dynamic>? _draft;
  String _code = '';
  final Map<String, Uint8List?> _presetPng = {};
  final Map<int, Uint8List?> _slotPng = {};
  Timer? _codeDebounce;
  StreamSubscription<SpikeMessage>? _errSub;
  DateTime? _sentRecipeAt;
  int _section = 0; // 0 features, 1 colours, 2 sizes

  @override
  void initState() {
    super.initState();
    _mode = ref.read(spikeStateProvider).mode;
    _boot();
    _errSub = ref.read(brainClientProvider).messages.listen((m) {
      if (m is ErrorMsg && m.code == 'unknown_type' && _sentRecipeAt != null &&
          DateTime.now().difference(_sentRecipeAt!) < const Duration(seconds: 3)) {
        _sentRecipeAt = null;
        if (mounted) {
          showToast(context, 'Saved on the phone. Spike\'s brain can\'t take new faces from the app yet (update coming).',
              icon: Icons.info_outline_rounded);
        }
      }
    });
  }

  Future<void> _boot() async {
    await _face.ready;
    try {
      final raw = await _face.call('catalog') as Map<String, dynamic>;
      final cat = FaceCatalog.fromJson(raw);
      ref.read(studioProvider.notifier).setCatalog(cat);
      if (!mounted) return;
      _loadDraftFor(_mode);
      final thumbs = await _face.call('thumbs', {
        'width': 264,
        'items': [for (final p in cat.presets) {'recipe': p.recipe, 'mode': p.kind}],
      }) as List;
      if (!mounted) return;
      setState(() {
        for (var i = 0; i < cat.presets.length && i < thumbs.length; i++) {
          _presetPng[cat.presets[i].id] = dataUrlBytes(thumbs[i] as String?);
        }
      });
      await _renderSlots();
    } catch (e) {
      debugPrint('studio boot failed: $e');
    }
  }

  void _loadDraftFor(String mode) {
    final st = ref.read(studioProvider);
    final r = st.current[mode] ?? st.catalog?.defaults[mode];
    if (r == null) return;
    _mode = mode;
    _face.setMode(mode);
    _setDraft(Map<String, dynamic>.from(r));
  }

  void _setDraft(Map<String, dynamic> r) {
    setState(() => _draft = r);
    _face.setRecipe(r, _mode);
    _codeDebounce?.cancel();
    _codeDebounce = Timer(const Duration(milliseconds: 180), () async {
      try {
        final c = await _face.call('toCode', {'recipe': r}) as String;
        if (mounted) setState(() => _code = c);
      } catch (_) {}
    });
  }

  void _edit(String key, Object value) {
    final r = Map<String, dynamic>.from(_draft ?? {});
    r[key] = value;
    r['name'] = 'My face';
    _setDraft(r);
  }

  Future<void> _renderSlots() async {
    final slots = ref.read(studioProvider).slots;
    final items = <Map<String, Object?>>[];
    final idx = <int>[];
    for (var i = 0; i < slots.length; i++) {
      final s = slots[i];
      if (s != null) {
        items.add({'recipe': s.recipe, 'mode': s.mode});
        idx.add(i);
      }
    }
    if (items.isEmpty) {
      setState(_slotPng.clear);
      return;
    }
    final out = await _face.call('thumbs', {'width': 240, 'items': items}) as List;
    if (!mounted) return;
    setState(() {
      _slotPng.clear();
      for (var k = 0; k < idx.length && k < out.length; k++) {
        _slotPng[idx[k]] = dataUrlBytes(out[k] as String?);
      }
    });
  }

  void _pickSection(int i) => setState(() => _section = i);

  Future<void> _roll() async {
    Haptics.tap();
    _dice.animateWith(SpringSimulation(Springs.bouncy, _dice.value, _dice.value.roundToDouble() + 1, 12));
    try {
      final r = await _face.call('random') as Map<String, dynamic>;
      await Future<void>.delayed(const Duration(milliseconds: 160));
      Haptics.thud();
      _setDraft(r);
      _face.setMood('excited');
    } catch (_) {}
  }

  void _wear() {
    final r = _draft;
    if (r == null) return;
    Haptics.success();
    ref.read(studioProvider.notifier).wear(_mode, r);
    final name = ref.read(settingsProvider).nameFor(_mode);
    final cmds = ref.read(commandsProvider);
    _face.setMood('proud');
    if (cmds.connected) {
      // v1.2: the brain passes it to the robot and the simulator, and keeps it for when they reconnect
      _sentRecipeAt = DateTime.now();
      cmds.wearFace(_mode, code: _code.isEmpty ? null : _code, recipe: _code.isEmpty ? r : null);
      showToast(context, '$name is wearing the new face', icon: Icons.check_circle_rounded);
    } else {
      showToast(context, 'Saved on this phone. Connect $name and tap Wear to put it on him.', icon: Icons.check_circle_rounded);
    }
  }

  Future<void> _copyCode() async {
    if (_code.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: _code));
    Haptics.confirm();
    if (mounted) showToast(context, 'Share code copied', icon: Icons.copy_rounded);
  }

  Future<void> _pasteCode() async {
    final data = await Clipboard.getData('text/plain');
    final text = data?.text?.trim() ?? '';
    if (!mounted) return;
    final ok = await _loadCode(text);
    if (!ok && mounted) {
      Haptics.error();
      showToast(context, 'No face code on the clipboard. Codes start with SPK1-.', icon: Icons.error_outline_rounded);
    }
  }

  Future<bool> _loadCode(String text) async {
    if (text.isEmpty) return false;
    try {
      final r = await _face.call('fromCode', {'code': text});
      if (r is Map<String, dynamic>) {
        Haptics.success();
        _setDraft(r);
        return true;
      }
    } catch (_) {}
    return false;
  }

  Future<void> _slotTap(int i) async {
    final s = ref.read(studioProvider).slots[i];
    if (s == null) {
      if (_draft == null) return;
      Haptics.success();
      ref.read(studioProvider.notifier).saveSlot(i, _mode, _draft!);
      await _renderSlots();
      if (mounted) showToast(context, 'Saved to slot ${i + 1}', icon: Icons.bookmark_added_rounded);
    } else {
      Haptics.confirm();
      _setDraft(Map<String, dynamic>.from(s.recipe));
    }
  }

  Future<void> _slotMenu(int i) async {
    final s = ref.read(studioProvider).slots[i];
    if (s == null) return;
    final action = await showModalBottomSheet<String>(
      context: context,
      useRootNavigator: true, // above the tab bar
      builder: (c) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          ListTile(leading: const Icon(Icons.save_rounded), title: Text('Save this face over slot ${i + 1}'), onTap: () => Navigator.pop(c, 'over')),
          ListTile(
              leading: const Icon(Icons.delete_outline_rounded, color: Brand.tongue),
              title: const Text('Empty this slot'),
              onTap: () => Navigator.pop(c, 'clear')),
        ]),
      ),
    );
    if (action == 'over' && _draft != null) {
      ref.read(studioProvider.notifier).saveSlot(i, _mode, _draft!);
    } else if (action == 'clear') {
      ref.read(studioProvider.notifier).clearSlot(i);
    } else {
      return;
    }
    Haptics.confirm();
    await _renderSlots();
  }

  @override
  void dispose() {
    _codeDebounce?.cancel();
    _errSub?.cancel();
    _dice.dispose();
    _face.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final st = ref.watch(studioProvider);
    final cat = st.catalog;
    final settings = ref.watch(settingsProvider);
    final bottom = MediaQuery.paddingOf(context).bottom + 100;
    final draft = _draft;
    if (AppPlatform.desktop && context.isWide) return _desktop(context, st, cat, settings, draft);

    return Scaffold(
      body: SafeArea(
        bottom: false,
        child: Column(children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 10, 16, 8),
            child: Row(children: [
              Expanded(child: Text('Face Studio', style: context.tt.headlineSmall)),
              _MiniSeg(
                value: _mode,
                items: {'dog': settings.dogName, 'cat': settings.catName},
                onChanged: (m) {
                  Haptics.tick();
                  _loadDraftFor(m);
                },
              ),
            ]),
          ),
          // ------------------------------------------------ live preview (stays put)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Brand.chocolate,
                borderRadius: BorderRadius.circular(30),
                boxShadow: [BoxShadow(color: p.shadow.withValues(alpha: 0.25), blurRadius: 24, offset: const Offset(0, 10))],
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(23),
                child: AspectRatio(
                  aspectRatio: 480 / 272,
                  child: FaceView(
                    live: false,
                    controller: _face,
                    onEvent: (e) {
                      if (e.name == 'pat') Haptics.purr();
                      if (e.name == 'boop') Haptics.confirm();
                    },
                  ),
                ),
              ),
            ),
          ),
          const SizedBox(height: 10),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Row(children: [
              AnimatedBuilder(
                animation: _dice,
                builder: (_, child) => Transform.rotate(angle: _dice.value * 3.14159 * 2, child: child),
                child: Pressable(
                  onTap: _roll,
                  haptic: false,
                  semanticLabel: 'Roll the dice',
                  child: Container(
                    width: 52,
                    height: 52,
                    decoration: BoxDecoration(color: Brand.tongue, borderRadius: BorderRadius.circular(16)),
                    child: const Icon(Icons.casino_rounded, color: Colors.white, size: 28),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: SizedBox(
                  height: 44,
                  child: ListView(scrollDirection: Axis.horizontal, children: [
                    for (final m in const [('happy', 'Happy'), ('love', 'Love'), ('playful', 'Playful'), ('sad', 'Sad'),
                      ('sleepy', 'Sleepy'), ('cuteAngry', 'Cross'), ('surprised', 'Wow')])
                      Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: PillButton(label: m.$2, dense: true, onTap: () => _face.setMood(m.$1)),
                      ),
                  ]),
                ),
              ),
            ]),
          ),
          const SizedBox(height: 6),
          // ------------------------------------------------ controls
          Expanded(
            child: cat == null || draft == null
                ? Center(child: CircularProgressIndicator(color: p.accent))
                : ShaderMask(
                    shaderCallback: (r) => const LinearGradient(
                      begin: Alignment.topCenter,
                      end: Alignment.bottomCenter,
                      colors: [Color(0x00000000), Color(0xFF000000)],
                      stops: [0, 0.05],
                    ).createShader(r),
                    blendMode: BlendMode.dstIn,
                    child: ListView(
                    padding: EdgeInsets.fromLTRB(16, 4, 16, bottom),
                    children: [
                      const SectionHeader('Start from'),
                      SizedBox(
                        height: 116,
                        child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemCount: cat.presets.length,
                          separatorBuilder: (_, _) => const SizedBox(width: 12),
                          itemBuilder: (context, i) {
                            final pr = cat.presets[i];
                            return FaceThumb(
                              png: _presetPng[pr.id],
                              label: pr.id == 'spicy' ? settings.catName : pr.name,
                              selected: _code.isNotEmpty && _code == pr.code,
                              onTap: () {
                                Haptics.confirm();
                                _setDraft(Map<String, dynamic>.from(pr.recipe));
                              },
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 14),
                      _SectionTabs(index: _section, onChanged: (i) => setState(() => _section = i)),
                      const SizedBox(height: 12),
                      AnimatedSwitcher(
                        duration: const Duration(milliseconds: 300),
                        switchInCurve: Springs.curve,
                        transitionBuilder: (c, a) => FadeTransition(
                          opacity: a,
                          child: SlideTransition(position: Tween(begin: const Offset(0, 0.04), end: Offset.zero).animate(a), child: c),
                        ),
                        child: KeyedSubtree(key: ValueKey(_section), child: _sectionBody(cat, draft)),
                      ),
                      const SectionHeader('Save slots', subtitle: 'Tap an empty slot to save, a full one to load, hold for more'),
                      for (var r = 0; r < st.slots.length; r += 3)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Row(children: [
                            for (var i = r; i < r + 3; i++) ...[
                              if (i > r) const SizedBox(width: 10),
                              Expanded(
                                child: i < st.slots.length
                                    ? FaceThumb(
                                        png: _slotPng[i],
                                        empty: st.slots[i] == null,
                                        width: double.infinity,
                                        label: st.slots[i]?.name ?? 'Slot ${i + 1}',
                                        onTap: () => _slotTap(i),
                                        onLongPress: st.slots[i] == null ? null : () => _slotMenu(i),
                                      )
                                    : const SizedBox(),
                              ),
                            ],
                          ]),
                        ),
                      const SectionHeader('Share code'),
                      SpikeCard(
                        padding: const EdgeInsets.all(14),
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          SelectableText(_code, style: context.tt.bodyMedium?.copyWith(fontFamily: 'monospace', fontWeight: FontWeight.w600)),
                          const SizedBox(height: 12),
                          Row(children: [
                            Expanded(child: PillButton(label: 'Copy', icon: Icons.copy_rounded, dense: true, onTap: _copyCode)),
                            const SizedBox(width: 10),
                            Expanded(child: PillButton(label: 'Paste a code', icon: Icons.content_paste_rounded, dense: true, onTap: _pasteCode)),
                          ]),
                        ]),
                      ),
                      const SizedBox(height: 18),
                      PillButton(
                        label: 'Wear this face',
                        icon: Icons.check_rounded,
                        filled: true,
                        onTap: _wear,
                      ),
                    ],
                  ),
                  ),
          ),
        ]),
      ),
    );
  }

  Widget _sectionBody(FaceCatalog cat, Map<String, dynamic> draft) {
    switch (_section) {
      case 0:
        return Column(children: [
          for (final k in FaceCatalog.slotOrder)
            if (cat.slots[k] != null)
              OptionRow(
                label: cat.slotLabels[k] ?? k,
                options: cat.slots[k]!,
                labels: cat.optionLabels,
                value: draft[k]?.toString() ?? '',
                onPick: (v) => _edit(k, v),
              ),
        ]);
      case 1:
        return GridView.count(
          crossAxisCount: 4,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 14,
          childAspectRatio: 0.9,
          children: [
            for (final k in cat.colors)
              SwatchTile(
                label: cat.colorLabels[k] ?? k,
                color: hexColor(draft[k]),
                onTap: () async {
                  final c = await showColorSheet(context, cat.colorLabels[k] ?? k, hexColor(draft[k]));
                  if (c != null) _edit(k, colorHex(c));
                },
              ),
          ],
        );
      default:
        return Column(children: [
          for (final e in cat.numbers.entries)
            _NumberRow(
              label: cat.numberLabels[e.key] ?? e.key,
              min: e.value[0],
              max: e.value[1],
              value: ((draft[e.key] as num?) ?? e.value[0]).toDouble(),
              onChanged: (v) => _edit(e.key, v),
            ),
        ]);
    }
  }
}

/// Studio on the desktop (DESIGN.md "Desktop > Proportions"): the canvas pane (61.8 %) holds what
/// you look at and keep (the live face, moods and dice, the six save slots in one row, the share
/// code and Wear); the tools pane (38.2 %) holds what you change (starting faces, then features,
/// colours and sizes), and only the tools scroll, so the face you are making never leaves the screen.
extension _StudioDesktop on _StudioScreenState {
  Widget _desktop(BuildContext context, StudioState st, FaceCatalog? cat, AppSettings settings, Map<String, dynamic>? draft) {
    final p = context.sp;
    final m = context.metrics;
    return Scaffold(
      body: Padding(
        padding: EdgeInsets.all(m.pagePad),
        child: LayoutBuilder(builder: (context, c) {
          final (main, side) = goldenSplit(c.maxWidth, m.gutter);
          // the canvas column's fixed parts: header 56, mood row 52, the slots row, the code row 56, gaps
          // a starting face's name ("Sticker Buddy") needs a 104 px thumbnail: three across from 360 px
          final presetCols = side >= 360 ? 3 : 2;
          final slotW = (main - 5 * Space.x3) / 6;
          final slotsH = 28 + slotW / Ratios.face + 6 + 20;
          // seven mood chips (about 500 px with their gaps) next to the 52 px dice fit one row from a 580 px column
          final moodRows = main - 64 >= 520 ? 1 : 2;
          final fixed = 56 + Space.x6 + 16 + Space.x4 + moodRows * 52.0 + (moodRows - 1) * Space.x2 + Space.x6 + Space.x6 + 56;
          final face = faceSize(main - 16, c.maxHeight - fixed - slotsH);
          return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            SizedBox(
              width: main,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SizedBox(
                  height: 56,
                  child: Row(children: [
                    Expanded(child: Text('Face Studio', style: context.tt.headlineMedium?.copyWith(fontWeight: FontWeight.w800))),
                    _MiniSeg(
                      value: _mode,
                      items: {'dog': settings.dogName, 'cat': settings.catName},
                      onChanged: (mo) {
                        Haptics.tick();
                        _loadDraftFor(mo);
                      },
                    ),
                  ]),
                ),
                const SizedBox(height: Space.x6),
                Container(
                  width: face.width + 16,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Brand.chocolate, borderRadius: BorderRadius.circular(Radii.card)),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(Radii.card - 8),
                    child: SizedBox(
                      width: face.width,
                      height: face.height,
                      child: FaceView(live: false, controller: _face),
                    ),
                  ),
                ),
                const SizedBox(height: Space.x4),
                SizedBox(
                  // the moods span the column (not the face): one row from 1280 px up, two on the smallest windows
                  width: main,
                  height: moodRows * 52.0 + (moodRows - 1) * Space.x2,
                  child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    AnimatedBuilder(
                      animation: _dice,
                      builder: (_, child) => Transform.rotate(angle: _dice.value * 3.14159 * 2, child: child),
                      child: Tooltip(
                        message: 'A random face',
                        child: Pressable(
                          onTap: _roll,
                          haptic: false,
                          semanticLabel: 'Roll the dice',
                          child: Container(
                            width: 52,
                            height: 52,
                            decoration: BoxDecoration(color: Brand.tongue, borderRadius: BorderRadius.circular(Radii.control + 4)),
                            child: const Icon(Icons.casino_rounded, color: Colors.white, size: 28),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: Space.x3),
                    Expanded(
                      child: Wrap(spacing: Space.x2, runSpacing: Space.x2, children: [
                        for (final mo in const [('happy', 'Happy'), ('love', 'Love'), ('playful', 'Playful'), ('sad', 'Sad'),
                          ('sleepy', 'Sleepy'), ('cuteAngry', 'Cross'), ('surprised', 'Wow')])
                          PillButton(label: mo.$2, dense: true, onTap: () => _face.setMood(mo.$1)),
                      ]),
                    ),
                  ]),
                ),
                const SizedBox(height: Space.x6),
                Text('Save slots · click to save or load, right click for more', style: context.tt.labelLarge?.copyWith(color: p.muted)),
                const SizedBox(height: Space.x2),
                Row(children: [
                  for (var i = 0; i < st.slots.length; i++) ...[
                    if (i > 0) const SizedBox(width: Space.x3),
                    FaceThumb(
                      png: _slotPng[i],
                      empty: st.slots[i] == null,
                      width: slotW,
                      label: st.slots[i]?.name ?? 'Slot ${i + 1}',
                      onTap: () => _slotTap(i),
                      onLongPress: st.slots[i] == null ? null : () => _slotMenu(i),
                    ),
                  ],
                ]),
                const Spacer(),
                SizedBox(
                  height: 56,
                  child: Row(children: [
                    Expanded(
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: Space.x4),
                        alignment: Alignment.centerLeft,
                        decoration: BoxDecoration(color: p.card, borderRadius: BorderRadius.circular(Radii.tile), border: Border.all(color: p.line)),
                        child: Row(children: [
                          Expanded(
                            child: SelectableText(_code.isEmpty ? '...' : _code,
                                maxLines: 1, style: context.tt.bodyMedium?.copyWith(fontFamily: 'Consolas', fontWeight: FontWeight.w600)),
                          ),
                          IconButton(tooltip: 'Copy the share code', onPressed: _copyCode, icon: const Icon(Icons.copy_rounded)),
                          IconButton(tooltip: 'Paste a share code', onPressed: _pasteCode, icon: const Icon(Icons.content_paste_rounded)),
                        ]),
                      ),
                    ),
                    const SizedBox(width: Space.x3),
                    PillButton(label: 'Wear this face', icon: Icons.check_rounded, filled: true, onTap: _wear),
                  ]),
                ),
              ]),
            ),
            SizedBox(width: m.gutter),
            SizedBox(
              width: side,
              child: cat == null || draft == null
                  ? Center(child: CircularProgressIndicator(color: p.accent))
                  : Container(
                      decoration: BoxDecoration(color: p.card, borderRadius: BorderRadius.circular(Radii.card), border: Border.all(color: p.line)),
                      clipBehavior: Clip.antiAlias,
                      child: ListView(padding: const EdgeInsets.fromLTRB(Space.x5, Space.x5, Space.x5, Space.x6), children: [
                        const SectionHeader('Start from', first: true),
                        GridView(
                          shrinkWrap: true,
                          physics: const NeverScrollableScrollPhysics(),
                          // three starting faces across (two in a narrow inspector, so every name fits);
                          // a row is exactly one 480:272 thumbnail + its label
                          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: presetCols,
                              mainAxisExtent: (side - 2 * Space.x5 - (presetCols - 1) * Space.x3) / presetCols / Ratios.face + 6 + 6 + 20,
                              crossAxisSpacing: Space.x3,
                              mainAxisSpacing: Space.x4),
                          children: [
                            for (final pr in cat.presets)
                              FaceThumb(
                                png: _presetPng[pr.id],
                                width: double.infinity,
                                label: pr.id == 'spicy' ? settings.catName : pr.name,
                                selected: _code.isNotEmpty && _code == pr.code,
                                onTap: () {
                                  Haptics.confirm();
                                  _setDraft(Map<String, dynamic>.from(pr.recipe));
                                },
                              ),
                          ],
                        ),
                        const SizedBox(height: Space.x6),
                        _SectionTabs(index: _section, onChanged: _pickSection),
                        const SizedBox(height: Space.x4),
                        KeyedSubtree(key: ValueKey(_section), child: _sectionBody(cat, draft)),
                      ]),
                    ),
            ),
          ]);
        }),
      ),
    );
  }
}

class _NumberRow extends StatefulWidget {
  const _NumberRow({required this.label, required this.min, required this.max, required this.value, required this.onChanged});
  final String label;
  final double min, max, value;
  final ValueChanged<double> onChanged;
  @override
  State<_NumberRow> createState() => _NumberRowState();
}

class _NumberRowState extends State<_NumberRow> {
  int _lastStep = -1;
  @override
  Widget build(BuildContext context) {
    final pct = ((widget.value - widget.min) / (widget.max - widget.min) * 100).clamp(0, 100).round();
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(children: [
        SizedBox(width: 110, child: Text(widget.label, style: context.tt.labelLarge)),
        Expanded(
          child: Slider(
            min: widget.min,
            max: widget.max,
            value: widget.value.clamp(widget.min, widget.max),
            onChanged: (v) {
              final step = ((v - widget.min) / (widget.max - widget.min) * 20).round();
              if (step != _lastStep) {
                _lastStep = step;
                Haptics.tick();
              }
              widget.onChanged(double.parse(v.toStringAsFixed(3)));
            },
          ),
        ),
        SizedBox(width: 44, child: Text('$pct%', textAlign: TextAlign.right, style: context.tt.labelMedium)),
      ]),
    );
  }
}

class _SectionTabs extends StatelessWidget {
  const _SectionTabs({required this.index, required this.onChanged});
  final int index;
  final ValueChanged<int> onChanged;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    const labels = ['Features', 'Colours', 'Sizes'];
    return Container(
      height: 46,
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: p.cardHi, borderRadius: BorderRadius.circular(23)),
      child: LayoutBuilder(builder: (context, c) {
        final w = c.maxWidth / labels.length;
        return Stack(children: [
          AnimatedPositioned(
            duration: const Duration(milliseconds: 480),
            curve: Springs.curve,
            left: w * index,
            width: w,
            top: 0,
            bottom: 0,
            child: Container(decoration: BoxDecoration(color: p.card, borderRadius: BorderRadius.circular(19), boxShadow: [
              BoxShadow(color: p.shadow.withValues(alpha: 0.15), blurRadius: 8, offset: const Offset(0, 2)),
            ])),
          ),
          Row(children: [
            for (var i = 0; i < labels.length; i++)
              Expanded(
                child: Pressable(
                  haptic: false,
                  onTap: () {
                    if (i != index) Haptics.tick();
                    onChanged(i);
                  },
                  child: Center(
                    child: Text(labels[i],
                        style: context.tt.labelLarge?.copyWith(color: i == index ? p.ink : p.muted, fontWeight: FontWeight.w800)),
                  ),
                ),
              ),
          ]),
        ]);
      }),
    );
  }
}

class _MiniSeg extends StatelessWidget {
  const _MiniSeg({required this.value, required this.items, required this.onChanged});
  final String value;
  final Map<String, String> items;
  final ValueChanged<String> onChanged;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: p.cardHi, borderRadius: BorderRadius.circular(20), border: Border.all(color: p.line)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        for (final e in items.entries)
          Pressable(
            haptic: false,
            onTap: () => e.key == value ? null : onChanged(e.key),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              curve: Springs.curve,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(color: e.key == value ? p.accent : Colors.transparent, borderRadius: BorderRadius.circular(17)),
              child: Text(e.value,
                  style: context.tt.labelLarge?.copyWith(color: e.key == value ? p.accentInk : p.ink, fontWeight: FontWeight.w800)),
            ),
          ),
      ]),
    );
  }
}
