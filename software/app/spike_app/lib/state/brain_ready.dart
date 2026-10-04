/// Does Spike have a brain to think with right now? (Onboarding v2, 4 Oct 2026.)
///
/// The app opens straight into exploring. Whatever works without a brain (the face, Face Studio,
/// settings, browsing) just works; the moment the owner does something that needs one, the app asks
/// ([ensureBrain] in features/connect/brain_needed.dart) instead of showing a setup gate at launch.
///
/// A brain is any of:
///  * the desktop app: its built-in brain is always there (desktop/brain_sidecar.dart), never asked;
///  * the laptop's brain, reached over Wi-Fi or USB (the home link is connected);
///  * the owner's Gemini key, saved on this phone (the phone becomes the brain, state/away.dart);
///  * the offline on-device model, once downloaded;
///  * a robot already bonded over Bluetooth (the phone brain drives it).
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../away/ai/offline_brain.dart' show OfflineState;
import '../core/platform.dart';
import 'away.dart';
import 'link.dart';
import 'settings.dart';

final brainReadyProvider = Provider<bool>((ref) {
  if (AppPlatform.desktop) return true;
  if (ref.watch(lanStatusProvider).value?.isConnected ?? false) return true;
  if (ref.watch(awayProvider.select((a) => a.hasKey))) return true;
  if (ref.watch(offlineStatusProvider).value?.state == OfflineState.installed) return true;
  return ref.watch(settingsProvider.select((s) => s.robotId != null));
});

/// The same answer, read right now (a tap handler must not wait for a stream's first event).
bool brainReadyNow(WidgetRef ref) {
  if (AppPlatform.desktop) return true;
  return ref.read(settingsProvider).robotId != null ||
      ref.read(brainClientProvider).lan.current.isConnected ||
      ref.read(offlineBrainProvider).installed ||
      ref.read(awayProvider).hasKey;
}

/// Alarms and reminders only exist in the computer's brain (the phone's own brain keeps none).
bool computerBrainReadyNow(WidgetRef ref) => AppPlatform.desktop || ref.read(brainClientProvider).lan.current.isConnected;
