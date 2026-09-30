import 'package:flutter/material.dart';

import 'motion.dart';
import 'platform.dart';
import 'theme.dart';

/// The app's card: soft, warm, a large radius and a gentle long shadow.
class SpikeCard extends StatelessWidget {
  const SpikeCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(18),
    this.color,
    this.radius = 28,
    this.onTap,
    this.gradient,
  });
  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color? color;
  final double radius;
  final VoidCallback? onTap;
  final Gradient? gradient;

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final box = DecoratedBox(
      decoration: BoxDecoration(
        color: gradient == null ? (color ?? p.card) : null,
        gradient: gradient,
        borderRadius: BorderRadius.circular(radius),
        border: Border.all(color: p.line.withValues(alpha: context.isDark ? 0.9 : 0.7)),
        boxShadow: [
          BoxShadow(color: p.shadow.withValues(alpha: context.isDark ? 0.35 : 0.10), blurRadius: 28, offset: const Offset(0, 12)),
        ],
      ),
      // a transparent Material so ListTiles and ink inside the card stay visible
      child: Material(type: MaterialType.transparency, child: Padding(padding: padding, child: child)),
    );
    if (onTap == null) return box;
    return Pressable(onTap: onTap, scale: 0.97, child: box);
  }
}

class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.trailing, this.subtitle, this.first = false});
  final String title;
  final String? subtitle;
  final Widget? trailing;

  /// Desktop: the header opens a column, so it sits flush with the column's top (like PaneTitle).
  final bool first;
  @override
  Widget build(BuildContext context) => Padding(
        // desktop: flush with the cards' edge and on the PaneTitle rhythm (32 above, 12 below);
        // the phone keeps its own spacing
        padding: AppPlatform.desktop
            ? EdgeInsets.only(top: first ? 0 : 32, bottom: 12)
            : const EdgeInsets.fromLTRB(4, 22, 4, 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: context.tt.titleLarge),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Text(subtitle!, style: context.tt.bodySmall),
                  ],
                ],
              ),
            ),
            ?trailing,
          ],
        ),
      );
}

/// A pill-shaped button. [filled] = the accent colour.
class PillButton extends StatelessWidget {
  const PillButton({
    super.key,
    required this.label,
    this.icon,
    this.onTap,
    this.filled = false,
    this.dense = false,
    this.color,
  });
  final String label;
  final IconData? icon;
  final VoidCallback? onTap;
  final bool filled;
  final bool dense;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final bg = filled ? (color ?? p.accent) : p.cardHi;
    final fg = filled ? p.accentInk : p.ink;
    return Pressable(
      onTap: onTap,
      enabled: onTap != null,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: dense ? 14 : 20, vertical: dense ? 10 : 14),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(100),
          boxShadow: filled
              ? [BoxShadow(color: (color ?? p.accent).withValues(alpha: 0.35), blurRadius: 16, offset: const Offset(0, 6))]
              : null,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (icon != null) ...[Icon(icon, size: dense ? 18 : 20, color: fg), const SizedBox(width: 8)],
            Flexible(
              child: Text(label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: context.tt.labelLarge?.copyWith(color: fg, fontSize: dense ? 13 : 15)),
            ),
          ],
        ),
      ),
    );
  }
}

/// A small status pill with a coloured dot (connection, mood, battery).
class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.label, this.dot, this.icon, this.pulse = false});
  final String label;
  final Color? dot;
  final IconData? icon;
  final bool pulse;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 350),
      curve: Springs.smoothCurve,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: p.card.withValues(alpha: 0.92),
        borderRadius: BorderRadius.circular(100),
        border: Border.all(color: p.line),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (dot != null) _Dot(color: dot!, pulse: pulse),
        if (icon != null) Icon(icon, size: 16, color: p.muted),
        const SizedBox(width: 7),
        AnimatedSwitcher(
          duration: const Duration(milliseconds: 250),
          transitionBuilder: (c, a) => FadeTransition(
              opacity: a, child: SlideTransition(position: Tween(begin: const Offset(0, 0.4), end: Offset.zero).animate(a), child: c)),
          child: Text(label, key: ValueKey(label), style: context.tt.labelMedium?.copyWith(color: p.ink, fontWeight: FontWeight.w700)),
        ),
      ]),
    );
  }
}

class _Dot extends StatefulWidget {
  const _Dot({required this.color, required this.pulse});
  final Color color;
  final bool pulse;
  @override
  State<_Dot> createState() => _DotState();
}

class _DotState extends State<_Dot> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400));
  @override
  void initState() {
    super.initState();
    if (widget.pulse) _c.repeat();
  }

  @override
  void didUpdateWidget(_Dot old) {
    super.didUpdateWidget(old);
    if (widget.pulse && !_c.isAnimating) _c.repeat();
    if (!widget.pulse && _c.isAnimating) _c.stop();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => SizedBox(
        width: 10,
        height: 10,
        child: AnimatedBuilder(
          animation: _c,
          builder: (_, _) => CustomPaint(painter: _DotPainter(widget.color, widget.pulse ? _c.value : 0)),
        ),
      );
}

class _DotPainter extends CustomPainter {
  _DotPainter(this.color, this.t);
  final Color color;
  final double t;
  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    if (t > 0) {
      canvas.drawCircle(c, 4 + 6 * t, Paint()..color = color.withValues(alpha: (1 - t) * 0.45));
    }
    canvas.drawCircle(c, 4, Paint()..color = color);
  }

  @override
  bool shouldRepaint(_DotPainter o) => o.t != t || o.color != color;
}

/// A square-ish action tile (quick actions, tricks): icon over a label.
class ActionTile extends StatelessWidget {
  const ActionTile({super.key, required this.icon, required this.label, this.onTap, this.tint, this.busy = false});
  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  final Color? tint;
  final bool busy;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final t = tint ?? p.accent;
    return Pressable(
      onTap: onTap,
      enabled: onTap != null,
      scale: 0.9,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Springs.curve,
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 6),
        decoration: BoxDecoration(
          color: busy ? t.withValues(alpha: 0.22) : p.card,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: busy ? t : p.line),
        ),
        child: Column(mainAxisSize: MainAxisSize.min, mainAxisAlignment: MainAxisAlignment.center, children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(color: t.withValues(alpha: context.isDark ? 0.22 : 0.14), shape: BoxShape.circle),
            child: Icon(icon, color: t, size: 24),
          ),
          const SizedBox(height: 8),
          // scales down instead of overflowing with large system text sizes
          Flexible(
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(label,
                  maxLines: 1,
                  textAlign: TextAlign.center,
                  style: context.tt.labelMedium?.copyWith(fontWeight: FontWeight.w700)),
            ),
          ),
        ]),
      ),
    );
  }
}

/// The desktop's action tile: a fixed 88 px target (12 + 40 icon well + 8 + 20 label + 8), the
/// label at the 14 px reading size (never scaled down), for a mouse from ~60 cm (core/layout.dart).
class DeskTile extends StatelessWidget {
  const DeskTile({super.key, required this.icon, required this.label, this.onTap, this.tint, this.busy = false});
  final IconData icon;
  final String label;
  final VoidCallback? onTap;
  final Color? tint;
  final bool busy;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final t = tint ?? p.accent;
    return Pressable(
      onTap: onTap,
      enabled: onTap != null,
      scale: 0.95,
      semanticLabel: label,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 240),
        curve: Springs.smoothCurve,
        height: 88,
        padding: const EdgeInsets.fromLTRB(8, 12, 8, 8),
        decoration: BoxDecoration(
          color: busy ? t.withValues(alpha: 0.22) : p.card,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: busy ? t : p.line),
        ),
        child: Column(children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(color: t.withValues(alpha: context.isDark ? 0.22 : 0.14), shape: BoxShape.circle),
            child: Icon(icon, color: t, size: 22),
          ),
          const SizedBox(height: 8),
          Text(label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: context.tt.bodyMedium?.copyWith(fontSize: 14, height: 1.4, fontWeight: FontWeight.w700)),
        ]),
      ),
    );
  }
}

/// Extra room above the nav bar for toasts: the voice pill's height while the mic is on.
double toastLift = 0;

void showToast(BuildContext context, String text, {IconData? icon}) {
  final m = ScaffoldMessenger.maybeOf(context);
  if (m == null) return;
  m.hideCurrentSnackBar();
  // float above the app's bottom nav bar (and the system bar, and the voice pill)
  final bottom = MediaQuery.paddingOf(context).bottom;
  // desktop (a wide window): a compact note at the bottom centre, never a full-width bar
  final wide = AppPlatform.desktop && MediaQuery.sizeOf(context).width >= 900;
  m.showSnackBar(SnackBar(
    duration: const Duration(milliseconds: 2200),
    width: wide ? 440 : null,
    margin: wide ? null : EdgeInsets.fromLTRB(16, 0, 16, bottom + 92 + toastLift),
    content: Row(children: [
      if (icon != null) ...[Icon(icon, color: context.sp.bg, size: 20), const SizedBox(width: 10)],
      Expanded(child: Text(text)),
    ]),
  ));
}
