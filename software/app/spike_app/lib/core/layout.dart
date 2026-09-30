/// The desktop layout system: size classes, spacing, proportions (software/app/DESIGN.md
/// "Desktop > Proportions"). Every desktop size in the app comes from here: no magic numbers.
///
/// Size classes (logical width of the window; at 125 % / 150 % Windows scaling a 1920 px screen
/// is 1536 / 1280 logical, so the classes follow what the eye actually gets):
///   compact  < 900   the phone layout, unchanged (bottom navigation)
///   medium   900 .. 1399   side rail (icons + labels), two panes
///   expanded 1400 .. 1919  sidebar with names, two panes
///   large    >= 1920       sidebar; Home gets three panes once its room is >= 1924 px
///
/// Principles (owner, 30 Sep 2026): nothing is "just enlarged". Reading text keeps its size at
/// every width (it is read from ~60 cm); extra room goes to more useful content (the conversation,
/// status, controls), never to inflated buttons. Every split is a named ratio.
library;

import 'package:flutter/widgets.dart';

enum SizeClass { compact, medium, expanded, large }

abstract final class Breakpoints {
  static const double medium = 900;
  static const double expanded = 1400;
  static const double large = 1920;

  static SizeClass of(double width) => width >= large
      ? SizeClass.large
      : width >= expanded
          ? SizeClass.expanded
          : width >= medium
              ? SizeClass.medium
              : SizeClass.compact;
}

extension SizeClassX on BuildContext {
  /// The window's size class (from the whole window, not the parent box).
  SizeClass get sizeClass => Breakpoints.of(MediaQuery.sizeOf(this).width);
  bool get isWide => sizeClass != SizeClass.compact;
}

/// The spacing scale: 4-pt base, used in 8-pt steps for layout (4 only inside controls).
abstract final class Space {
  static const double x1 = 4, x2 = 8, x3 = 12, x4 = 16, x5 = 20, x6 = 24, x8 = 32, x10 = 40, x12 = 48, x16 = 64;
}

/// Radii, one scale for the whole brand (soft, like the robot's own shell): a nested surface is
/// always one step smaller than its container.
abstract final class Radii {
  static const double control = 12, tile = 20, card = 28, hero = 34;
}

/// Named proportions.
abstract final class Ratios {
  /// The golden split: the main pane : the side pane = 1.618 : 1 (61.8 % / 38.2 %).
  static const double golden = 1.618;
  static const int goldenMain = 618, goldenSide = 382;

  /// The robot's face screen is 480 x 272 px: every face on screen keeps exactly this aspect.
  static const double face = 480 / 272;

  /// The robot's camera: 4:3.
  static const double camera = 4 / 3;
}

/// Per-size-class metrics (all from [Space]).
@immutable
class DesktopMetrics {
  const DesktopMetrics._(this.cls, this.pagePad, this.gutter, this.navWidth, this.navExtended);

  factory DesktopMetrics.of(SizeClass c) => switch (c) {
        SizeClass.compact => const DesktopMetrics._(SizeClass.compact, Space.x5, Space.x4, 0, false),
        SizeClass.medium => const DesktopMetrics._(SizeClass.medium, Space.x6, Space.x6, 88, false),
        SizeClass.expanded => const DesktopMetrics._(SizeClass.expanded, Space.x8, Space.x8, 232, true),
        SizeClass.large => const DesktopMetrics._(SizeClass.large, Space.x10, Space.x8, 256, true),
      };

  final SizeClass cls;

  /// Page edge padding.
  final double pagePad;

  /// Between panes.
  final double gutter;

  /// The navigation: a rail (88) or a sidebar with names (232 / 256).
  final double navWidth;
  final bool navExtended;

  /// Reading text columns never exceed this (about 70 characters of 16 px text).
  static const double readingMax = 720;

  /// The face is drawn at most at 2x its native 480 px (crisp, and big enough to read from across
  /// the desk); beyond that, the room goes to the conversation.
  static const double faceMax = 960;

  /// The fixed status column of the large layout (fits the longest status line at 14 px).
  static const double statusColumn = 320;

  /// Action tiles: one height at every size (a target, not a decoration): 88 = 56 icon well + 2 x 16.
  static const double actionTile = 88;
}

extension DesktopMetricsX on BuildContext {
  DesktopMetrics get metrics => DesktopMetrics.of(sizeClass);
}

/// Splits [width] (minus one gutter) at the golden ratio: (main, side).
(double, double) goldenSplit(double width, double gutter) {
  final w = width - gutter;
  final main = w * Ratios.goldenMain / 1000;
  return (main, w - main);
}

/// The largest face (480:272) that fits [maxW] x [maxH], never above [DesktopMetrics.faceMax].
Size faceSize(double maxW, double maxH) {
  var w = maxW.clamp(0.0, DesktopMetrics.faceMax);
  if (w / Ratios.face > maxH) w = maxH * Ratios.face;
  return Size(w, w / Ratios.face);
}
