import 'package:flutter/material.dart';

import '../../core/motion.dart';
import '../../core/theme.dart';

/// Spike (dog) | Spicy (cat) switch with a springy sliding thumb. Drag or tap.
class ModeSwitch extends StatelessWidget {
  const ModeSwitch({super.key, required this.mode, required this.dogName, required this.catName, required this.onChanged});
  final String mode;
  final String dogName;
  final String catName;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    final cat = mode == 'cat';
    return GestureDetector(
      onHorizontalDragEnd: (d) {
        final v = d.primaryVelocity ?? 0;
        if (v > 200 && !cat) onChanged('cat');
        if (v < -200 && cat) onChanged('dog');
      },
      child: Container(
        height: 60,
        padding: const EdgeInsets.all(5),
        decoration: BoxDecoration(color: p.cardHi, borderRadius: BorderRadius.circular(30), border: Border.all(color: p.line)),
        child: Stack(children: [
          AnimatedAlign(
            alignment: cat ? Alignment.centerRight : Alignment.centerLeft,
            duration: const Duration(milliseconds: 560),
            curve: Springs.curve,
            child: FractionallySizedBox(
              widthFactor: 0.5,
              heightFactor: 1,
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 400),
                decoration: BoxDecoration(
                  color: cat ? Brand.tongue : p.accent,
                  borderRadius: BorderRadius.circular(25),
                  boxShadow: [BoxShadow(color: (cat ? Brand.tongue : p.accent).withValues(alpha: 0.35), blurRadius: 14, offset: const Offset(0, 5))],
                ),
              ),
            ),
          ),
          Row(children: [
            _Half(label: dogName, sub: 'Dog', icon: Icons.pets_rounded, selected: !cat, onTap: () => cat ? onChanged('dog') : null),
            _Half(label: catName, sub: 'Cat', icon: Icons.emoji_nature_rounded, selected: cat, onTap: () => cat ? null : onChanged('cat')),
          ]),
        ]),
      ),
    );
  }
}

class _Half extends StatelessWidget {
  const _Half({required this.label, required this.sub, required this.icon, required this.selected, required this.onTap});
  final String label;
  final String sub;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final color = selected ? Colors.white : context.sp.ink;
    return Expanded(
      child: Pressable(
        onTap: onTap,
        haptic: false,
        scale: 0.95,
        child: Center(
          child: Row(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, color: color, size: 20),
            const SizedBox(width: 8),
            AnimatedDefaultTextStyle(
              duration: const Duration(milliseconds: 300),
              style: context.tt.titleMedium!.copyWith(color: color),
              child: Text(label),
            ),
            const SizedBox(width: 6),
            Text(sub, style: context.tt.labelSmall?.copyWith(color: color.withValues(alpha: 0.7))),
          ]),
        ),
      ),
    );
  }
}
