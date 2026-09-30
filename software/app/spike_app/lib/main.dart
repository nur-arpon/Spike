import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:flutter_gemma_litertlm/flutter_gemma_litertlm.dart';

import 'app.dart';
import 'away/ai/offline_brain.dart';
import 'core/platform.dart';
import 'desktop/desktop_window.dart';
import 'state/settings.dart';
import 'state/voice.dart';

Future<void> main(List<String> args) async {
  WidgetsFlutterBinding.ensureInitialized();
  final desktop = AppPlatform.desktop;
  final prefs = await SharedPreferences.getInstance();
  if (desktop) {
    // Windows: our own window (size and place remembered, title, close-to-tray) and the built-in brain
    await initDesktopWindow(prefs);
    VoiceController.brainOwnMic = true; // the brain hears the computer's microphone itself
  } else {
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
    await SystemChrome.setPreferredOrientations([DeviceOrientation.portraitUp]);
    // the offline brain's engine, registered only when the owner first uses it (it is optional)
    OfflineBrain.initializer = () => FlutterGemma.initialize(inferenceEngines: const [LiteRtLmEngine()]);
  }
  runApp(ProviderScope(
    overrides: [prefsProvider.overrideWithValue(prefs)],
    // Windows started us at sign-in ("Start with Windows"): stay in the tray until opened
    child: SpikeApp(startHidden: desktop && args.contains('--startup'), startRoute: startRouteFrom(args)),
  ));
}
