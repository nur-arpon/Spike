/// The frame every desktop page shares (DESIGN.md "Desktop > Proportions"): the page padding of the
/// size class, a 56 px title row across the whole width (so every pane below starts on the same
/// line), a 24 px gap, then the panes.
library;

import 'package:flutter/material.dart';

import '../core/layout.dart';
import '../core/theme.dart';

class DesktopPage extends StatelessWidget {
  const DesktopPage({super.key, required this.title, required this.body, this.trailing, this.subtitle});
  final String title;
  final String? subtitle;
  final Widget? trailing;

  /// Builds the panes for the room left under the title row.
  final Widget Function(BuildContext context, BoxConstraints room) body;

  /// The title row's height (a 28/36 title, or a 14 subtitle over a 28 title).
  static const double headerHeight = 56;

  @override
  Widget build(BuildContext context) {
    final m = context.metrics;
    return Scaffold(
      body: Padding(
        padding: EdgeInsets.all(m.pagePad),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          SizedBox(
            height: headerHeight,
            child: Row(children: [
              Expanded(
                child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                  if (subtitle != null)
                    Text(subtitle!, style: context.tt.bodyMedium?.copyWith(color: context.sp.muted, fontWeight: FontWeight.w600)),
                  Text(title, maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: context.tt.headlineMedium?.copyWith(fontWeight: FontWeight.w800, height: 1.1)),
                ]),
              ),
              ?trailing,
            ]),
          ),
          const SizedBox(height: Space.x6),
          Expanded(child: LayoutBuilder(builder: body)),
        ]),
      ),
    );
  }
}

/// A pane's section title: 20 px title over a 14 px line, always [height] tall (so panes can be sized
/// exactly), flush with the pane's top when [first], else 32 px of air above it.
class PaneTitle extends StatelessWidget {
  const PaneTitle(this.title, {super.key, this.subtitle, this.first = false});
  final String title;
  final String? subtitle;
  final bool first;

  /// Title (28) + subtitle line (20) + 12 below.
  static const double height = 60;

  /// The height of a later (not first) title, air included.
  static const double heightAfter = height + Space.x8;

  @override
  Widget build(BuildContext context) => Padding(
        padding: EdgeInsets.only(top: first ? 0 : Space.x8),
        child: SizedBox(
          height: height,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, maxLines: 1, overflow: TextOverflow.ellipsis, style: context.tt.titleLarge?.copyWith(height: 1.4)),
            if (subtitle != null)
              Text(subtitle!, maxLines: 1, overflow: TextOverflow.ellipsis, style: context.tt.bodySmall?.copyWith(height: 1.4)),
          ]),
        ),
      );
}