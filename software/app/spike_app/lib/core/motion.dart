import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';

import 'haptics.dart';

/// Spring constants used everywhere (critically tuned by feel, mirrored on
/// Apple's "snappy"/"bouncy" presets). Nothing in the app uses a linear tween.
abstract final class Springs {
  /// Press feedback: quick, a hint of overshoot.
  static const press = SpringDescription(mass: 1, stiffness: 520, damping: 26);

  /// Things landing into place (cards, chips): a visible bounce.
  static const bouncy = SpringDescription(mass: 1, stiffness: 300, damping: 16);

  /// Large movements (sheets, joystick return): no wobble, fast settle.
  static const smooth = SpringDescription(mass: 1, stiffness: 240, damping: 30);

  /// A spring-shaped curve for implicit animations (AnimatedFoo widgets).
  static const Curve curve = _SpringCurve(bouncy);
  static const Curve smoothCurve = _SpringCurve(smooth);
}

class _SpringCurve extends Curve {
  const _SpringCurve(this.spring);
  final SpringDescription spring;
  @override
  double transformInternal(double t) {
    final sim = SpringSimulation(spring, 0, 1, 0);
    // stretch the simulation so it has (almost) settled at t = 1
    return sim.x(t * 0.9);
  }
}

/// A child that squishes under the finger and springs back, with a haptic.
/// The whole app's buttons are built on this.
class Pressable extends StatefulWidget {
  const Pressable({
    super.key,
    required this.child,
    this.onTap,
    this.onLongPress,
    this.scale = 0.94,
    this.haptic = true,
    this.enabled = true,
    this.semanticLabel,
  });
  final Widget child;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final double scale;
  final bool haptic;
  final bool enabled;
  final String? semanticLabel;

  @override
  State<Pressable> createState() => _PressableState();
}

class _PressableState extends State<Pressable> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController.unbounded(vsync: this, value: 1);
  bool _hover = false; // a mouse is over it (desktop): it lifts a little
  bool _focus = false; // keyboard focus (desktop, Tab): a ring, and Enter/Space press it

  double get _rest => _hover || _focus ? 1.035 : 1.0;

  void _to(double target, {double velocity = 0}) {
    _c.animateWith(SpringSimulation(Springs.press, _c.value, target, velocity));
  }

  void _activate() {
    if (widget.haptic) Haptics.tap();
    _c.value = widget.scale;
    _to(_rest, velocity: 4);
    widget.onTap?.call();
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final on = widget.enabled && (widget.onTap != null || widget.onLongPress != null);
    final ring = Theme.of(context).colorScheme.primary;
    return Semantics(
      button: true,
      enabled: on,
      label: widget.semanticLabel,
      child: FocusableActionDetector(
        enabled: on,
        mouseCursor: on ? SystemMouseCursors.click : MouseCursor.defer,
        actions: {ActivateIntent: CallbackAction<ActivateIntent>(onInvoke: (_) => on ? _activate() : null)},
        onShowHoverHighlight: (v) {
          if (v == _hover) return;
          setState(() => _hover = v);
          _to(_rest);
        },
        onShowFocusHighlight: (v) {
          if (v == _focus) return;
          setState(() => _focus = v);
          _to(_rest);
        },
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: on ? (_) => _to(widget.scale) : null,
          onTapUp: on
              ? (_) {
                  _to(_rest, velocity: 4);
                  if (widget.haptic) Haptics.tap();
                  widget.onTap?.call();
                }
              : null,
          onTapCancel: on ? () => _to(_rest) : null,
          onLongPress: on && widget.onLongPress != null
              ? () {
                  Haptics.confirm();
                  _to(_rest, velocity: 6);
                  widget.onLongPress!();
                }
              : null,
          child: AnimatedBuilder(
            animation: _c,
            builder: (_, child) => Transform.scale(scale: _c.value, child: child),
            child: AnimatedOpacity(
              duration: const Duration(milliseconds: 200),
              opacity: widget.enabled ? 1 : 0.45,
              child: DecoratedBox(
                position: DecorationPosition.foreground,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: _focus ? ring : Colors.transparent, width: 2),
                ),
                child: widget.child,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Fades + slides + springs its child in when first built. [index] staggers
/// siblings (40 ms apart).
class Entrance extends StatefulWidget {
  const Entrance({super.key, required this.child, this.index = 0, this.offset = 24});
  final Widget child;
  final int index;
  final double offset;
  @override
  State<Entrance> createState() => _EntranceState();
}

class _EntranceState extends State<Entrance> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController.unbounded(vsync: this, value: 0);

  @override
  void initState() {
    super.initState();
    Future<void>.delayed(Duration(milliseconds: 40 * widget.index.clamp(0, 12)), () {
      if (mounted) _c.animateWith(SpringSimulation(Springs.bouncy, 0, 1, 0));
    });
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _c,
        builder: (_, child) => Opacity(
          opacity: _c.value.clamp(0.0, 1.0),
          child: Transform.translate(offset: Offset(0, (1 - _c.value) * widget.offset), child: child),
        ),
        child: widget.child,
      );
}
