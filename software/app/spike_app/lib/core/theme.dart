import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Brand palette (BRIEF.md). Warm and premium, not childish.
abstract final class Brand {
  static const cream = Color(0xFFF3DDBF);
  static const caramel = Color(0xFFB97A4F);
  static const chocolate = Color(0xFF4A3326);
  static const brown = Color(0xFFC98A5E);
  static const tongue = Color(0xFFE0564F);

  // derived neutrals
  static const paper = Color(0xFFFBF5EC); // light background
  static const paperHi = Color(0xFFFFFCF7);
  static const cocoaNight = Color(0xFF17110D); // dark background
  static const cocoaCard = Color(0xFF231A14);
  static const cocoaCardHi = Color(0xFF2E231B);
  static const ok = Color(0xFF5BAE7A);
  static const warn = Color(0xFFE3A13B);
}

/// Semantic colours that differ per theme, reachable with `context.sp`.
@immutable
class SpikePalette extends ThemeExtension<SpikePalette> {
  const SpikePalette({
    required this.bg,
    required this.card,
    required this.cardHi,
    required this.ink,
    required this.muted,
    required this.line,
    required this.accent,
    required this.accentInk,
    required this.shadow,
  });
  final Color bg, card, cardHi, ink, muted, line, accent, accentInk, shadow;

  static const light = SpikePalette(
    bg: Brand.paper,
    card: Brand.paperHi,
    cardHi: Color(0xFFF6EBDD),
    ink: Brand.chocolate,
    muted: Color(0xFF8A7263),
    line: Color(0xFFEADCCB),
    accent: Brand.caramel,
    accentInk: Colors.white,
    shadow: Color(0x334A3326),
  );
  static const dark = SpikePalette(
    bg: Brand.cocoaNight,
    card: Brand.cocoaCard,
    cardHi: Brand.cocoaCardHi,
    ink: Color(0xFFF6E9D8),
    muted: Color(0xFFB39C8A),
    line: Color(0xFF3A2D24),
    accent: Brand.brown,
    accentInk: Color(0xFF1B130E),
    shadow: Color(0x66000000),
  );

  @override
  SpikePalette copyWith() => this;
  @override
  SpikePalette lerp(ThemeExtension<SpikePalette>? other, double t) {
    if (other is! SpikePalette) return this;
    return SpikePalette(
      bg: Color.lerp(bg, other.bg, t)!,
      card: Color.lerp(card, other.card, t)!,
      cardHi: Color.lerp(cardHi, other.cardHi, t)!,
      ink: Color.lerp(ink, other.ink, t)!,
      muted: Color.lerp(muted, other.muted, t)!,
      line: Color.lerp(line, other.line, t)!,
      accent: Color.lerp(accent, other.accent, t)!,
      accentInk: Color.lerp(accentInk, other.accentInk, t)!,
      shadow: Color.lerp(shadow, other.shadow, t)!,
    );
  }
}

extension SpikeThemeX on BuildContext {
  SpikePalette get sp => Theme.of(this).extension<SpikePalette>()!;
  TextTheme get tt => Theme.of(this).textTheme;
  bool get isDark => Theme.of(this).brightness == Brightness.dark;
}

ThemeData buildTheme(Brightness b) {
  final dark = b == Brightness.dark;
  final p = dark ? SpikePalette.dark : SpikePalette.light;
  final scheme = ColorScheme.fromSeed(
    seedColor: Brand.caramel,
    brightness: b,
    primary: p.accent,
    onPrimary: p.accentInk,
    secondary: Brand.tongue,
    surface: p.card,
    onSurface: p.ink,
  );
  final base = ThemeData(useMaterial3: true, brightness: b, colorScheme: scheme);
  final text = base.textTheme.apply(bodyColor: p.ink, displayColor: p.ink).copyWith(
        displaySmall: base.textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -1.2, color: p.ink),
        headlineMedium: base.textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w800, letterSpacing: -0.8, color: p.ink),
        headlineSmall: base.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.5, color: p.ink),
        titleLarge: base.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -0.3, color: p.ink),
        titleMedium: base.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700, color: p.ink),
        labelLarge: base.textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700, letterSpacing: 0.1),
        bodyMedium: base.textTheme.bodyMedium?.copyWith(color: p.ink, height: 1.35),
        bodySmall: base.textTheme.bodySmall?.copyWith(color: p.muted, height: 1.3),
      );
  return base.copyWith(
    scaffoldBackgroundColor: p.bg,
    canvasColor: p.bg,
    textTheme: text,
    extensions: [p],
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: p.ink,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: text.titleLarge,
      systemOverlayStyle: dark ? SystemUiOverlayStyle.light : SystemUiOverlayStyle.dark,
    ),
    sliderTheme: SliderThemeData(
      activeTrackColor: p.accent,
      inactiveTrackColor: p.line,
      thumbColor: p.accent,
      overlayColor: p.accent.withValues(alpha: 0.12),
      trackHeight: 6,
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? p.accentInk : p.muted),
      trackColor: WidgetStateProperty.resolveWith((s) => s.contains(WidgetState.selected) ? p.accent : p.line),
      trackOutlineColor: WidgetStateProperty.all(Colors.transparent),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: p.cardHi,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(18), borderSide: BorderSide.none),
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      hintStyle: TextStyle(color: p.muted),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      backgroundColor: p.ink,
      contentTextStyle: TextStyle(color: p.bg, fontWeight: FontWeight.w600),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    timePickerTheme: TimePickerThemeData(
      backgroundColor: p.card,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
      hourMinuteColor: WidgetStateColor.resolveWith((s) => s.contains(WidgetState.selected) ? p.accent.withValues(alpha: 0.18) : p.cardHi),
      hourMinuteTextColor: WidgetStateColor.resolveWith((s) => s.contains(WidgetState.selected) ? p.accent : p.ink),
      dayPeriodColor: WidgetStateColor.resolveWith((s) => s.contains(WidgetState.selected) ? p.accent : Colors.transparent),
      dayPeriodTextColor: WidgetStateColor.resolveWith((s) => s.contains(WidgetState.selected) ? p.accentInk : p.ink),
      dayPeriodBorderSide: BorderSide(color: p.line),
      dialBackgroundColor: p.cardHi,
      dialHandColor: p.accent,
      dialTextColor: WidgetStateColor.resolveWith((s) => s.contains(WidgetState.selected) ? p.accentInk : p.ink),
      entryModeIconColor: p.muted,
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: p.card,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: p.card,
      showDragHandle: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(28))),
    ),
    pageTransitionsTheme: const PageTransitionsTheme(builders: {
      TargetPlatform.android: PredictiveBackPageTransitionsBuilder(),
    }),
  );
}
