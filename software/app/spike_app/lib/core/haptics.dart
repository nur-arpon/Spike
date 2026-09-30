import 'package:flutter/services.dart';

/// One place for every haptic in the app, so each gesture has a consistent
/// "weight" and the owner can switch them all off in Settings.
///
/// Mapping (Android): selectionClick = a crisp tick, lightImpact = a soft
/// tap, mediumImpact = a confident press, heavyImpact = a thud,
/// vibrate = the long buzz reserved for errors.
abstract final class Haptics {
  static bool enabled = true;

  /// Scrolling through options, a joystick crossing a notch, a slider step.
  static void tick() {
    if (enabled) HapticFeedback.selectionClick();
  }

  /// Any button press.
  static void tap() {
    if (enabled) HapticFeedback.lightImpact();
  }

  /// A meaningful action was sent (trick, treat, apply face).
  static void confirm() {
    if (enabled) HapticFeedback.mediumImpact();
  }

  /// Big moments: connected, dice roll landing, mode switch.
  static void thud() {
    if (enabled) HapticFeedback.heavyImpact();
  }

  /// A pat on Spike's face: a soft double pulse, like a purr.
  static Future<void> purr() async {
    if (!enabled) return;
    await HapticFeedback.lightImpact();
    await Future<void>.delayed(const Duration(milliseconds: 70));
    await HapticFeedback.selectionClick();
  }

  /// Success: rising double.
  static Future<void> success() async {
    if (!enabled) return;
    await HapticFeedback.lightImpact();
    await Future<void>.delayed(const Duration(milliseconds: 90));
    await HapticFeedback.mediumImpact();
  }

  /// The mic turned on (tap to talk): a firm press, then a rising knock. Unlike any other.
  static Future<void> voiceOn() async {
    if (!enabled) return;
    await HapticFeedback.mediumImpact();
    await Future<void>.delayed(const Duration(milliseconds: 80));
    await HapticFeedback.heavyImpact();
  }

  /// The mic turned off: a thud that falls away to a tick.
  static Future<void> voiceOff() async {
    if (!enabled) return;
    await HapticFeedback.heavyImpact();
    await Future<void>.delayed(const Duration(milliseconds: 110));
    await HapticFeedback.selectionClick();
  }

  static void error() {
    if (enabled) HapticFeedback.vibrate();
  }
}
