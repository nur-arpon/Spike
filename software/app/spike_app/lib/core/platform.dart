/// Which kind of device the app runs on, in ONE place (software/app/DESIGN.md "Desktop").
///
/// The phone app and the Windows desktop app are the same code. On the desktop:
///  * the built-in brain runs on this computer (desktop/brain_sidecar.dart) and the app is its
///    first client over 127.0.0.1; the phone and the robot connect to it over the home Wi-Fi;
///  * the phone-only parts are hidden, not deleted: away-from-home phone brain, Bluetooth robot
///    link, phone hotspot, QR scanner, Gemini Live on the phone, the offline brain and voice pack
///    downloads (the "on-device AI pack" comes to the desktop in a later update);
///  * Spike's voice plays from the brain (laptop speakers or the robot), so the app does not ask
///    for `audio_out`, and listening uses the computer's microphone through the brain.
///
/// Tests flip [AppPlatform.debugDesktop] to render the desktop variant on any host.
library;

import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';

class AppPlatform {
  const AppPlatform._();

  /// Null = the real platform. Tests set true/false (and reset it in tearDown).
  static bool? debugDesktop;

  /// The Windows desktop app. Under `flutter test` (which runs on the developer's Windows PC) the app
  /// is the phone app unless a test asks for the desktop with [debugDesktop].
  static bool get desktop => debugDesktop ?? (!kIsWeb && Platform.isWindows && !_underTest);

  static final bool _underTest = !kIsWeb && Platform.environment.containsKey('FLUTTER_TEST');

  /// A phone (Android today).
  static bool get phone => !desktop;

  /// Features that exist only on the phone (see the list above).
  static bool get awayFromHome => phone;
  static bool get qrScanner => phone;
  static bool get haptics => phone;
  static bool get onDeviceAiPack => phone; // offline brain (+ the optional Kokoro add-on, Android only: speaker.dart kokoroVoiceAvailable)
}
