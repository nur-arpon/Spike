import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/haptics.dart';
import '../../core/motion.dart';
import '../../core/platform.dart';
import '../../core/spike_web_view.dart';
import '../../core/theme.dart';

/// The approved 3D preview (preview_3d/... v6, inner-ear camera), bundled
/// offline. Its own page chrome is hidden and replaced by native controls
/// that press its buttons, so it feels like part of the app.
class ViewerScreen extends StatefulWidget {
  const ViewerScreen({super.key});
  @override
  State<ViewerScreen> createState() => _ViewerScreenState();
}

const _schemes = [
  ('caramel', 'Caramel', Color(0xFFF1DEC2), Color(0xFFB97A4F)),
  ('choc', 'Choc', Color(0xFFF1DEC2), Color(0xFF5A3A2A)),
  ('latte', 'Latte', Color(0xFFF4E6D0), Color(0xFFD2AE86)),
  ('toy', 'Toy', Color(0xFFF3DDBF), Color(0xFFC98A5E)),
  ('original', 'Original', Color(0xFFEEEAE3), Color(0xFF3A3E44)),
];
const _screens = [('face', 'Face', Icons.mood_rounded), ('sleep', 'Asleep', Icons.bedtime_rounded), ('off', 'Off', Icons.power_settings_new_rounded)];
const _views = [('34', '3/4'), ('front', 'Front'), ('side', 'Side'), ('back', 'Back'), ('top', 'Top')];

class _ViewerScreenState extends State<ViewerScreen> {
  late final SpikeWebController _web;
  bool _ready = false;
  String _scheme = 'caramel';
  String _screen = 'face';
  String _view = '34';
  bool _xray = false;
  bool _labels = false;

  static const _inject = r'''
(function(){
  var css = document.createElement('style');
  css.textContent = `
    html,body{background:transparent!important;overflow:hidden!important;height:100%!important}
    .wrap{padding:0!important;max-width:none!important;display:block!important}
    .wrap > header, .wrap > section:not(.stage), .wrap > footer, aside{display:none!important}
    .stage{display:block!important}
    .viewer{position:fixed!important;left:0!important;right:0!important;top:calc(50vh - 62vw - 90px)!important;height:118vw!important;max-height:none!important;aspect-ratio:auto!important;border:0!important;border-radius:0!important;background:transparent!important}
    .toolbar,.optbar,.swatches,.hint{display:none!important}
  `;
  document.head.appendChild(css);
  document.documentElement.setAttribute('data-theme', window.__spikeTheme || 'light');
  try { document.getElementById('m-ear').click(); } catch(e) {}
  try { var lt = document.getElementById('labtog'); if (lt && lt.getAttribute('aria-pressed') === 'true') lt.click(); } catch(e) {}
  window.dispatchEvent(new Event('resize'));
  var sel = document.querySelector('.sw[aria-pressed="true"]');
  if (window.SpikeViewer) SpikeViewer.postMessage(sel ? sel.id.replace('c-','') : '');
})();
''';

  /// On a desktop window the model fills the whole window (the phone layout sizes it by width).
  static const _desktopCss = r'''
(function(){
  var css = document.createElement('style');
  css.textContent = `.viewer{top:0!important;bottom:0!important;height:100vh!important}`;
  document.head.appendChild(css);
  window.dispatchEvent(new Event('resize'));
})();
''';

  @override
  void initState() {
    super.initState();
    _web = SpikeWebController(
      asset: 'assets/viewer3d/preview_v6.html',
      channels: {
        'SpikeViewer': (m) {
          if (m.isNotEmpty && mounted) setState(() => _scheme = m);
        },
      },
      onPageFinished: () async {
        if (!mounted) return;
        final theme = context.isDark ? 'dark' : 'light';
        await _web.runJs("window.__spikeTheme='$theme';$_inject${AppPlatform.desktop ? _desktopCss : ''}");
        await Future<void>.delayed(const Duration(milliseconds: 250));
        if (mounted) setState(() => _ready = true);
      },
    );
  }

  @override
  void dispose() {
    _web.dispose();
    super.dispose();
  }

  void _click(String id) => _web.runJs("try{document.getElementById('$id').click()}catch(e){}");

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final top = MediaQuery.paddingOf(context).top;
    final bottom = MediaQuery.paddingOf(context).bottom;
    return Scaffold(
      backgroundColor: p.bg,
      body: Stack(children: [
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: RadialGradient(
                center: const Alignment(0, -0.3),
                radius: 1.1,
                colors: context.isDark ? [const Color(0xFF3A2C22), Brand.cocoaNight] : [Colors.white, const Color(0xFFEFE2D1)],
              ),
            ),
          ),
        ),
        Positioned.fill(
          child: AnimatedOpacity(
            opacity: _ready ? 1 : 0,
            duration: const Duration(milliseconds: 600),
            curve: Curves.easeOut,
            child: _web.view(),
          ),
        ),
        if (!_ready) Center(child: CircularProgressIndicator(color: p.accent)),
        Positioned(
          top: top + 8,
          left: 12,
          right: 12,
          child: Row(children: [
            _Glass(
              child: IconButton(
                icon: const Icon(Icons.close_rounded),
                onPressed: () {
                  Haptics.tap();
                  context.pop();
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Spike in 3D', style: context.tt.titleLarge),
                Text(AppPlatform.desktop ? 'Drag to turn · scroll to zoom' : 'Drag to turn · pinch to zoom', style: context.tt.bodySmall),
              ]),
            ),
            _Glass(
              child: IconButton(
                tooltip: 'See inside',
                isSelected: _xray,
                icon: Icon(_xray ? Icons.visibility_rounded : Icons.visibility_outlined, color: _xray ? p.accent : p.ink),
                onPressed: () {
                  Haptics.tick();
                  setState(() => _xray = !_xray);
                  _click('xray');
                },
              ),
            ),
            const SizedBox(width: 8),
            _Glass(
              child: IconButton(
                tooltip: 'Labels',
                icon: Icon(Icons.label_rounded, color: _labels ? p.accent : p.ink),
                onPressed: () {
                  Haptics.tick();
                  setState(() => _labels = !_labels);
                  _click('labtog');
                },
              ),
            ),
          ]),
        ),
        Positioned(
          left: 12,
          right: 12,
          bottom: bottom + 12,
          child: _Glass(
            radius: 28,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
                  for (final s in _schemes)
                    _SchemeDot(
                      label: s.$2,
                      a: s.$3,
                      b: s.$4,
                      selected: _scheme == s.$1,
                      onTap: () {
                        Haptics.tick();
                        setState(() => _scheme = s.$1);
                        _click('c-${s.$1}');
                      },
                    ),
                ]),
                const SizedBox(height: 12),
                _Seg(
                  items: [for (final s in _screens) (s.$1, s.$2, s.$3)],
                  value: _screen,
                  onChanged: (v) {
                    setState(() => _screen = v);
                    _click('s-$v');
                  },
                ),
                const SizedBox(height: 8),
                _Seg(
                  items: [for (final v in _views) (v.$1, v.$2, null)],
                  value: _view,
                  onChanged: (v) {
                    setState(() => _view = v);
                    _click('v-$v');
                  },
                ),
              ]),
            ),
          ),
        ),
      ]),
    );
  }
}

class _Glass extends StatelessWidget {
  const _Glass({required this.child, this.radius = 24});
  final Widget child;
  final double radius;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Container(
      decoration: BoxDecoration(
        color: p.card.withValues(alpha: 0.9),
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: p.line),
        boxShadow: [BoxShadow(color: p.shadow.withValues(alpha: 0.18), blurRadius: 20, offset: const Offset(0, 8))],
      ),
      child: child,
    );
  }
}

class _SchemeDot extends StatelessWidget {
  const _SchemeDot({required this.label, required this.a, required this.b, required this.selected, required this.onTap});
  final String label;
  final Color a, b;
  final bool selected;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Pressable(
      onTap: onTap,
      haptic: false,
      scale: 0.88,
      child: Column(children: [
        AnimatedContainer(
          duration: const Duration(milliseconds: 380),
          curve: Springs.curve,
          width: selected ? 46 : 40,
          height: selected ? 46 : 40,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(colors: [a, a, b, b], stops: const [0, 0.5, 0.5, 1], begin: Alignment.topLeft, end: Alignment.bottomRight),
            border: Border.all(color: selected ? p.accent : p.line, width: selected ? 3 : 1.5),
          ),
        ),
        const SizedBox(height: 4),
        Text(label, style: context.tt.labelSmall?.copyWith(fontWeight: selected ? FontWeight.w800 : FontWeight.w600, color: selected ? p.accent : p.ink)),
      ]),
    );
  }
}

class _Seg extends StatelessWidget {
  const _Seg({required this.items, required this.value, required this.onChanged});
  final List<(String, String, IconData?)> items;
  final String value;
  final ValueChanged<String> onChanged;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final idx = items.indexWhere((e) => e.$1 == value).clamp(0, items.length - 1);
    return Container(
      height: 42,
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: p.cardHi, borderRadius: BorderRadius.circular(21)),
      child: LayoutBuilder(builder: (context, c) {
        final w = c.maxWidth / items.length;
        return Stack(children: [
          AnimatedPositioned(
            duration: const Duration(milliseconds: 460),
            curve: Springs.curve,
            left: w * idx,
            width: w,
            top: 0,
            bottom: 0,
            child: Container(decoration: BoxDecoration(color: p.accent, borderRadius: BorderRadius.circular(18))),
          ),
          Row(children: [
            for (final it in items)
              Expanded(
                child: Pressable(
                  haptic: false,
                  onTap: () {
                    if (it.$1 != value) Haptics.tick();
                    onChanged(it.$1);
                  },
                  child: Center(
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      if (it.$3 != null) ...[
                        Icon(it.$3, size: 16, color: it.$1 == value ? p.accentInk : p.ink),
                        const SizedBox(width: 4),
                      ],
                      Text(it.$2,
                          style: context.tt.labelMedium?.copyWith(color: it.$1 == value ? p.accentInk : p.ink, fontWeight: FontWeight.w800)),
                    ]),
                  ),
                ),
              ),
          ]),
        ]);
      }),
    );
  }
}
