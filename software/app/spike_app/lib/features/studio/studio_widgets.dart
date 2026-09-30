import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../core/haptics.dart';
import '../../core/motion.dart';
import '../../core/theme.dart';

import '../../core/platform.dart';
/// Decodes a data:image/png;base64 URL from the face page.
Uint8List? dataUrlBytes(String? url) {
  if (url == null) return null;
  final i = url.indexOf(',');
  if (i < 0) return null;
  try {
    return base64Decode(url.substring(i + 1));
  } catch (_) {
    return null;
  }
}

Color hexColor(Object? v, [Color fallback = Colors.grey]) {
  final s = v?.toString() ?? '';
  if (!RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(s)) return fallback;
  return Color(int.parse(s.substring(1), radix: 16) | 0xFF000000);
}

String colorHex(Color c) {
  String h(double v) => (v * 255).round().clamp(0, 255).toRadixString(16).padLeft(2, '0').toUpperCase();
  return '#${h(c.r)}${h(c.g)}${h(c.b)}';
}

/// A face thumbnail card (presets, save slots).
class FaceThumb extends StatelessWidget {
  const FaceThumb({super.key, required this.png, required this.label, this.selected = false, this.onTap, this.onLongPress, this.width = 132, this.empty = false});
  final Uint8List? png;
  final String label;
  final bool selected;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final double width;
  final bool empty;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    // desktop: a right click opens the same menu as a long press
    return GestureDetector(
      onSecondaryTap: onLongPress,
      child: Pressable(
      onTap: onTap,
      onLongPress: onLongPress,
      scale: 0.93,
      child: SizedBox(
        width: width,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 380),
            curve: Springs.curve,
            padding: EdgeInsets.all(selected ? 3 : 0),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(18),
              border: Border.all(color: selected ? p.accent : Colors.transparent, width: 2.5),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(selected ? 13 : 16),
              child: AspectRatio(
                aspectRatio: 480 / 272,
                child: empty
                    ? DecoratedBox(
                        decoration: BoxDecoration(color: p.cardHi, border: Border.all(color: p.line)),
                        child: Icon(Icons.add_rounded, color: p.muted),
                      )
                    : png == null
                        ? ColoredBox(color: p.cardHi)
                        : Image.memory(png!, fit: BoxFit.cover, gaplessPlayback: true, filterQuality: FilterQuality.medium),
              ),
            ),
          ),
          const SizedBox(height: 6),
          Text(label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: context.tt.labelMedium?.copyWith(fontWeight: selected ? FontWeight.w800 : FontWeight.w600, color: selected ? p.accent : p.ink)),
        ]),
      ),
      ),
    );
  }
}

/// One feature slot as a row of option chips (tap to wear).
class OptionRow extends StatelessWidget {
  const OptionRow({super.key, required this.label, required this.options, required this.labels, required this.value, required this.onPick});
  final String label;
  final List<String> options;
  final Map<String, String> labels;
  final String value;
  final ValueChanged<String> onPick;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      // desktop: the full inspector width, so wrapped chips start on the left edge like the label
      child: Column(crossAxisAlignment: AppPlatform.desktop ? CrossAxisAlignment.stretch : CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 6),
          child: Text(label, style: context.tt.labelLarge?.copyWith(color: p.muted)),
        ),
        // the desktop inspector wraps its chips (every option in sight); the phone scrolls one row
        if (AppPlatform.desktop)
          Wrap(spacing: 8, runSpacing: 8, children: [for (var i = 0; i < options.length; i++) SizedBox(height: 42, child: _chip(context, i))])
        else
          SizedBox(
            height: 42,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: options.length,
              separatorBuilder: (_, _) => const SizedBox(width: 8),
              itemBuilder: _chip,
            ),
          ),
      ]),
    );
  }

  Widget _chip(BuildContext context, int i) {
    final p = context.sp;
    final o = options[i];
    final sel = o == value;
    return Pressable(
      haptic: false,
      scale: 0.9,
      onTap: () {
        if (!sel) {
          Haptics.tick();
          onPick(o);
        }
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        curve: Springs.curve,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        decoration: BoxDecoration(
          color: sel ? p.accent : p.cardHi,
          borderRadius: BorderRadius.circular(21),
          border: Border.all(color: sel ? p.accent : p.line),
        ),
        // widthFactor 1: as wide as its label, also inside a Wrap
        child: Align(
          widthFactor: 1,
          child: Text(labels[o] ?? o, style: context.tt.labelLarge?.copyWith(color: sel ? p.accentInk : p.ink, fontWeight: FontWeight.w700)),
        ),
      ),
    );
  }
}

/// A colour swatch that opens the colour sheet.
class SwatchTile extends StatelessWidget {
  const SwatchTile({super.key, required this.label, required this.color, required this.onTap});
  final String label;
  final Color color;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Pressable(
      onTap: onTap,
      scale: 0.9,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        AnimatedContainer(
          duration: const Duration(milliseconds: 350),
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            border: Border.all(color: p.card, width: 3),
            boxShadow: [BoxShadow(color: p.line, spreadRadius: 1), BoxShadow(color: color.withValues(alpha: 0.4), blurRadius: 10, offset: const Offset(0, 4))],
          ),
        ),
        const SizedBox(height: 6),
        Text(label, maxLines: 1, overflow: TextOverflow.ellipsis, textAlign: TextAlign.center, style: context.tt.labelSmall),
      ]),
    );
  }
}

const _palette = [
  '#F3DDBF', '#FFF4E4', '#EEEAE3', '#FFFFFF', '#C98A5E', '#B97A4F', '#8A5A3C', '#4A3326',
  '#2E2320', '#0B0D14', '#23272E', '#6B7A8F', '#BFE3F2', '#5FB3E6', '#4A90E2', '#9B6BDB',
  '#D9D2F2', '#F7D9E3', '#FF8C8C', '#FF5C9A', '#E0564F', '#E84A5F', '#FFB86B', '#FFC43D',
  '#E3F2C9', '#7BC96F', '#57C785', '#D4E157', '#FBE7C2', '#E6A04A', '#A8714D', '#8A6A55', //
];

/// Bottom sheet: curated palette + hue / saturation / brightness sliders.
Future<Color?> showColorSheet(BuildContext context, String title, Color start) => showModalBottomSheet<Color>(
      context: context,
      useRootNavigator: true, // above the tab bar
      isScrollControlled: true,
      builder: (_) => _ColorSheet(title: title, start: start),
    );

class _ColorSheet extends StatefulWidget {
  const _ColorSheet({required this.title, required this.start});
  final String title;
  final Color start;
  @override
  State<_ColorSheet> createState() => _ColorSheetState();
}

class _ColorSheetState extends State<_ColorSheet> {
  late HSVColor _hsv = HSVColor.fromColor(widget.start);
  Color get _c => _hsv.toColor();

  void _set(HSVColor h) => setState(() => _hsv = h);

  @override
  Widget build(BuildContext context) {
    final p = context.sp;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.paddingOf(context).bottom),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          AnimatedContainer(
            duration: const Duration(milliseconds: 120),
            width: 44,
            height: 44,
            decoration: BoxDecoration(color: _c, shape: BoxShape.circle, border: Border.all(color: p.line, width: 2)),
          ),
          const SizedBox(width: 14),
          Expanded(child: Text(widget.title, style: context.tt.titleLarge)),
          Text(colorHex(_c), style: context.tt.labelLarge?.copyWith(color: p.muted, fontFeatures: const [FontFeature.tabularFigures()])),
        ]),
        const SizedBox(height: 16),
        Wrap(spacing: 10, runSpacing: 10, children: [
          for (final h in _palette)
            Pressable(
              haptic: false,
              scale: 0.85,
              onTap: () {
                Haptics.tick();
                _set(HSVColor.fromColor(hexColor(h)));
              },
              child: Container(
                width: 34,
                height: 34,
                decoration: BoxDecoration(
                  color: hexColor(h),
                  shape: BoxShape.circle,
                  border: Border.all(color: colorHex(_c) == h ? p.accent : p.line, width: colorHex(_c) == h ? 3 : 1),
                ),
              ),
            ),
        ]),
        const SizedBox(height: 18),
        _GradientSlider(
          label: 'Hue',
          value: _hsv.hue / 360,
          colors: [for (var i = 0; i <= 6; i++) HSVColor.fromAHSV(1, i * 60.0, 1, 1).toColor()],
          onChanged: (v) => _set(_hsv.withHue(v * 360)),
        ),
        _GradientSlider(
          label: 'Richness',
          value: _hsv.saturation,
          colors: [_hsv.withSaturation(0).toColor(), _hsv.withSaturation(1).toColor()],
          onChanged: (v) => _set(_hsv.withSaturation(v)),
        ),
        _GradientSlider(
          label: 'Brightness',
          value: _hsv.value,
          colors: [Colors.black, _hsv.withValue(1).toColor()],
          onChanged: (v) => _set(_hsv.withValue(v)),
        ),
        const SizedBox(height: 10),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52), shape: const StadiumBorder()),
            onPressed: () {
              Haptics.confirm();
              Navigator.pop(context, _c);
            },
            child: const Text('Use this colour'),
          ),
        ),
      ]),
    );
  }
}

class _GradientSlider extends StatelessWidget {
  const _GradientSlider({required this.label, required this.value, required this.colors, required this.onChanged});
  final String label;
  final double value;
  final List<Color> colors;
  final ValueChanged<double> onChanged;
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: context.tt.labelMedium?.copyWith(color: context.sp.muted)),
        const SizedBox(height: 6),
        LayoutBuilder(builder: (context, c) {
          void at(double dx) => onChanged((dx / c.maxWidth).clamp(0.0, 1.0));
          return GestureDetector(
            onPanDown: (d) => at(d.localPosition.dx),
            onPanUpdate: (d) => at(d.localPosition.dx),
            child: SizedBox(
              height: 30,
              child: Stack(clipBehavior: Clip.none, alignment: Alignment.centerLeft, children: [
                Container(height: 18, decoration: BoxDecoration(borderRadius: BorderRadius.circular(9), gradient: LinearGradient(colors: colors))),
                Positioned(
                  left: value.clamp(0.0, 1.0) * c.maxWidth - 14,
                  child: Container(
                    width: 28,
                    height: 28,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      boxShadow: const [BoxShadow(color: Color(0x44000000), blurRadius: 6, offset: Offset(0, 2))],
                    ),
                  ),
                ),
              ]),
            ),
          );
        }),
      ]),
    );
  }
}
