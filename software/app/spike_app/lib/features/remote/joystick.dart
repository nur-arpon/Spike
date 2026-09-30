import 'dart:math';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/physics.dart';

import '../../core/haptics.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';

/// A physical joystick: the knob follows the thumb with rubber-band
/// resistance past the rim, ticks a haptic at each of 8 notches, thuds at the
/// rim, and springs home on release. Reports x,y in -1..1 (y up = +1).
class SpringJoystick extends StatefulWidget {
  const SpringJoystick({super.key, required this.onChanged, this.onStart, this.onRelease, this.size = 220, this.enabled = true});
  final void Function(double x, double y) onChanged;

  /// The thumb left the stick (the knob then springs home). Drive stops here,
  /// not when the spring animation reaches the centre.
  final VoidCallback? onRelease;

  /// The thumb touched the stick (a new drive begins).
  final VoidCallback? onStart;
  final double size;
  final bool enabled;
  @override
  State<SpringJoystick> createState() => _SpringJoystickState();
}

class _SpringJoystickState extends State<SpringJoystick> with TickerProviderStateMixin {
  Offset _knob = Offset.zero; // pixels from centre
  late final AnimationController _home = AnimationController.unbounded(vsync: this);
  Offset _from = Offset.zero;
  int _lastNotch = -1;
  bool _atRim = false;
  bool _active = false;

  double get _radius => widget.size * 0.34;

  @override
  void initState() {
    super.initState();
    _home.addListener(() {
      setState(() => _knob = _from * _home.value);
      _report();
    });
  }

  @override
  void dispose() {
    _home.dispose();
    super.dispose();
  }

  void _report() {
    final r = _radius;
    widget.onChanged((_knob.dx / r).clamp(-1, 1), (-_knob.dy / r).clamp(-1, 1));
  }

  void _move(Offset local) {
    final c = Offset(widget.size / 2, widget.size / 2);
    var d = local - c;
    final len = d.distance;
    final r = _radius;
    if (len > r) {
      // rubber band: past the rim the knob moves only a little further
      final over = len - r;
      d = d / len * (r + over * 0.18).clamp(0, r * 1.15);
    }
    final mag = min(len / r, 1.0);
    final notch = mag < 0.25 ? -1 : ((atan2(d.dy, d.dx) + pi) / (pi / 4)).round() % 8;
    if (notch != _lastNotch) {
      if (notch >= 0) Haptics.tick();
      _lastNotch = notch;
    }
    final rim = len >= r;
    if (rim && !_atRim) Haptics.tap();
    _atRim = rim;
    setState(() => _knob = d);
    _report();
  }

  void _release() {
    widget.onRelease?.call();
    _from = _knob;
    _lastNotch = -1;
    _atRim = false;
    setState(() => _active = false);
    _home.value = 1;
    _home.animateWith(SpringSimulation(Springs.bouncy, 1, 0, 0));
  }

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final s = widget.size;
    final knob = s * 0.36;
    // The stick claims the finger at once: inside a scrolling page a plain pan
    // loses every mostly-vertical drag to the scroll view (found on the A50,
    // 29 Sep), so "forward" and "back" never reached the wheels.
    return RawGestureDetector(
      gestures: {
        if (widget.enabled)
          _EagerPan: GestureRecognizerFactoryWithHandlers<_EagerPan>(
            _EagerPan.new,
            (r) => r
              ..onStart = (d) {
                _home.stop();
                widget.onStart?.call();
                setState(() => _active = true);
                Haptics.tap();
                _move(d.localPosition);
              }
              ..onUpdate = (d) {
                _move(d.localPosition);
              }
              ..onEnd = (_) {
                _release();
              }
              ..onCancel = _release,
          ),
      },
      child: SizedBox(
        width: s,
        height: s,
        child: Stack(alignment: Alignment.center, children: [
          // base
          Container(
            width: s,
            height: s,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(colors: [p.cardHi, p.card], stops: const [0.3, 1]),
              border: Border.all(color: p.line, width: 1.5),
              boxShadow: [BoxShadow(color: p.shadow.withValues(alpha: 0.18), blurRadius: 24, offset: const Offset(0, 10))],
            ),
            child: CustomPaint(painter: _BasePainter(color: p.muted.withValues(alpha: 0.35), active: _active, accent: p.accent, dir: _knob / _radius)),
          ),
          // knob
          Transform.translate(
            offset: _knob,
            child: AnimatedScale(
              scale: _active ? 1.08 : 1,
              duration: const Duration(milliseconds: 300),
              curve: Springs.curve,
              child: Container(
                width: knob,
                height: knob,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: widget.enabled ? [Brand.brown, Brand.caramel] : [p.line, p.muted],
                  ),
                  boxShadow: [BoxShadow(color: Brand.chocolate.withValues(alpha: 0.35), blurRadius: 16, offset: const Offset(0, 8))],
                ),
                child: Icon(Icons.pets_rounded, color: Colors.white.withValues(alpha: 0.9), size: knob * 0.4),
              ),
            ),
          ),
        ]),
      ),
    );
  }
}

class _BasePainter extends CustomPainter {
  _BasePainter({required this.color, required this.active, required this.accent, required this.dir});
  final Color color;
  final bool active;
  final Color accent;
  final Offset dir;
  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.width * 0.34;
    canvas.drawCircle(c, r, Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5);
    for (var i = 0; i < 8; i++) {
      final a = i * pi / 4;
      final o = c + Offset(cos(a), sin(a)) * (size.width * 0.44);
      canvas.drawCircle(o, i.isEven ? 3.2 : 2, Paint()..color = color);
    }
    final mag = dir.distance.clamp(0.0, 1.0);
    if (active && mag > 0.05) {
      final a = atan2(dir.dy, dir.dx);
      canvas.drawArc(Rect.fromCircle(center: c, radius: size.width * 0.44), a - 0.45, 0.9, false, Paint()
        ..color = accent.withValues(alpha: 0.3 + 0.6 * mag)
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeWidth = 6);
    }
  }

  @override
  bool shouldRepaint(_BasePainter o) => o.dir != dir || o.active != active || o.color != color;
}

/// A pan that wins the gesture arena as soon as the finger lands on the stick.
class _EagerPan extends PanGestureRecognizer {
  @override
  void addAllowedPointer(PointerDownEvent event) {
    super.addAllowedPointer(event);
    resolve(GestureDisposition.accepted);
  }
}
