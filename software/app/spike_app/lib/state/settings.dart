import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/haptics.dart';
import '../protocol/client.dart';

/// Overridden in main() with the loaded instance.
final prefsProvider = Provider<SharedPreferences>((ref) => throw UnimplementedError('prefs not loaded'));

@immutable
class AppSettings {
  const AppSettings({
    required this.deviceId,
    this.endpoint,
    this.recent = const [],
    this.dogName = 'Spike',
    this.catName = 'Spicy',
    this.dogVoice = 'default',
    this.catVoice = 'default',
    this.haptics = true,
    this.faceSounds = true,
    this.themeMode = ThemeMode.system,
    this.onboarded = false,
    this.shareMemories = true,
    this.showCaptions = true,
    this.wifiPairing,
    this.awayMode = true,
    this.phoneSpeaks = true,
    this.robotId,
    this.robotName,
    this.keepHotspot = false,
    this.manualHotspotSsid = '',
    this.voiceWaitS = defaultVoiceWaitS,
    this.desktopMic = true,
    this.trayHintShown = false,
  });
  final String deviceId;
  final BrainEndpoint? endpoint;
  final List<BrainEndpoint> recent;
  final String dogName;
  final String catName;
  final String dogVoice;
  final String catVoice;
  final bool haptics;
  /// Owner decision 29 Sep: the phone face may make its sounds whether or not
  /// Spike is connected (the old default was only when not connected). A
  /// toggle, default on.
  final bool faceSounds;
  final ThemeMode themeMode;
  final bool onboarded;
  final bool shareMemories;

  /// Owner decision 29 Sep: "Show captions on Spike's screen", default ON.
  /// Sent to the brain as v1.2 set_display; the brain keeps it for the robot.
  final bool showCaptions;

  /// v1.2: the brain's Wi-Fi address and token, learnt with pairing_get while
  /// connected (for example over USB). Used to reconnect over Wi-Fi without a QR.
  final BrainEndpoint? wifiPairing;

  /// v1.3 away from home: when the laptop brain can't be reached the phone becomes
  /// Spike's brain (owner decision 29 Sep). A switch in Settings, default on.
  final bool awayMode;

  /// Away, Spike's voice plays on the phone (the robot has no audio over Bluetooth).
  final bool phoneSpeaks;

  /// The robot this phone is bonded with over Bluetooth (its BLE address) and its name.
  final String? robotId;
  final String? robotName;

  /// Keep the phone's hotspot up while away (backup link), not only while the camera is open.
  final bool keepHotspot;

  /// The owner's own personal hotspot name (its password is in the Android keystore),
  /// used when the phone can't make a local-only hotspot the robot can join.
  final String manualHotspotSsid;

  /// Owner decision 30 Sep: the silence that ends a spoken turn ("Wait before Spike
  /// answers"), so breaths and thinking gaps don't cut him off. 1.5 to 6 s, default 3.
  final double voiceWaitS;
  static const defaultVoiceWaitS = 3.0;
  static double clampWait(double s) => s.isNaN ? defaultVoiceWaitS : s.clamp(1.5, 6.0).toDouble();

  /// Desktop: the built-in brain listens for Spike's name on this computer's microphone (default on;
  /// off = the brain starts without a microphone, typing still works). DESIGN.md "Desktop".
  final bool desktopMic;

  /// Desktop: the one-time note that closing the window keeps Spike running in the tray was shown.
  final bool trayHintShown;

  AppSettings copyWith({
    BrainEndpoint? endpoint,
    bool clearEndpoint = false,
    List<BrainEndpoint>? recent,
    String? dogName,
    String? catName,
    String? dogVoice,
    String? catVoice,
    bool? haptics,
    bool? faceSounds,
    ThemeMode? themeMode,
    bool? onboarded,
    bool? shareMemories,
    bool? showCaptions,
    BrainEndpoint? wifiPairing,
    bool? awayMode,
    bool? phoneSpeaks,
    String? robotId,
    String? robotName,
    bool clearRobot = false,
    bool? keepHotspot,
    String? manualHotspotSsid,
    double? voiceWaitS,
    bool? desktopMic,
    bool? trayHintShown,
  }) =>
      AppSettings(
        deviceId: deviceId,
        endpoint: clearEndpoint ? null : (endpoint ?? this.endpoint),
        recent: recent ?? this.recent,
        dogName: dogName ?? this.dogName,
        catName: catName ?? this.catName,
        dogVoice: dogVoice ?? this.dogVoice,
        catVoice: catVoice ?? this.catVoice,
        haptics: haptics ?? this.haptics,
        faceSounds: faceSounds ?? this.faceSounds,
        themeMode: themeMode ?? this.themeMode,
        onboarded: onboarded ?? this.onboarded,
        shareMemories: shareMemories ?? this.shareMemories,
        showCaptions: showCaptions ?? this.showCaptions,
        wifiPairing: wifiPairing ?? this.wifiPairing,
        awayMode: awayMode ?? this.awayMode,
        phoneSpeaks: phoneSpeaks ?? this.phoneSpeaks,
        robotId: clearRobot ? null : (robotId ?? this.robotId),
        robotName: clearRobot ? null : (robotName ?? this.robotName),
        keepHotspot: keepHotspot ?? this.keepHotspot,
        manualHotspotSsid: manualHotspotSsid ?? this.manualHotspotSsid,
        voiceWaitS: voiceWaitS == null ? this.voiceWaitS : clampWait(voiceWaitS),
        desktopMic: desktopMic ?? this.desktopMic,
        trayHintShown: trayHintShown ?? this.trayHintShown,
      );

  String nameFor(String mode) => mode == 'cat' ? catName : dogName;
}

class SettingsNotifier extends Notifier<AppSettings> {
  static const _k = 'spike.settings.v1';

  SharedPreferences get _prefs => ref.read(prefsProvider);

  @override
  AppSettings build() {
    final raw = _prefs.getString(_k);
    Map<String, dynamic> m = const {};
    if (raw != null) {
      try {
        m = jsonDecode(raw) as Map<String, dynamic>;
      } catch (_) {}
    }
    var id = m['deviceId'] as String?;
    if (id == null || id.isEmpty) {
      final r = Random.secure();
      id = 'app-${List.generate(6, (_) => r.nextInt(16).toRadixString(16)).join()}';
    }
    final s = AppSettings(
      deviceId: id,
      endpoint: BrainEndpoint.fromJson(m['endpoint'] as Map<String, dynamic>?),
      recent: [
        for (final e in (m['recent'] as List? ?? const []))
          ?BrainEndpoint.fromJson(e as Map<String, dynamic>?),
      ],
      dogName: (m['dogName'] as String?) ?? 'Spike',
      catName: (m['catName'] as String?) ?? 'Spicy',
      dogVoice: (m['dogVoice'] as String?) ?? 'default',
      catVoice: (m['catVoice'] as String?) ?? 'default',
      haptics: (m['haptics'] as bool?) ?? true,
      // 'faceSound' was auto/on/off before 29 Sep: only an explicit 'off' stays off
      faceSounds: (m['faceSounds'] as bool?) ?? (m['faceSound'] != 'off'),
      themeMode: ThemeMode.values.asNameMap()[m['themeMode']] ?? ThemeMode.system,
      onboarded: (m['onboarded'] as bool?) ?? false,
      shareMemories: (m['shareMemories'] as bool?) ?? true,
      showCaptions: (m['showCaptions'] as bool?) ?? true,
      wifiPairing: BrainEndpoint.fromJson(m['wifiPairing'] as Map<String, dynamic>?),
      awayMode: (m['awayMode'] as bool?) ?? true,
      phoneSpeaks: (m['phoneSpeaks'] as bool?) ?? true,
      robotId: m['robotId'] as String?,
      robotName: m['robotName'] as String?,
      keepHotspot: (m['keepHotspot'] as bool?) ?? false,
      manualHotspotSsid: (m['manualHotspotSsid'] as String?) ?? '',
      voiceWaitS: AppSettings.clampWait((m['voiceWaitS'] as num?)?.toDouble() ?? AppSettings.defaultVoiceWaitS),
      desktopMic: (m['desktopMic'] as bool?) ?? true,
      trayHintShown: (m['trayHintShown'] as bool?) ?? false,
    );
    Haptics.enabled = s.haptics;
    if (raw == null) _save(s);
    return s;
  }

  void _save(AppSettings s) {
    _prefs.setString(
      _k,
      jsonEncode({
        'deviceId': s.deviceId,
        'endpoint': s.endpoint?.toJson(),
        'recent': [for (final e in s.recent) e.toJson()],
        'dogName': s.dogName,
        'catName': s.catName,
        'dogVoice': s.dogVoice,
        'catVoice': s.catVoice,
        'haptics': s.haptics,
        'faceSounds': s.faceSounds,
        'themeMode': s.themeMode.name,
        'onboarded': s.onboarded,
        'shareMemories': s.shareMemories,
        'showCaptions': s.showCaptions,
        'wifiPairing': s.wifiPairing?.toJson(),
        'awayMode': s.awayMode,
        'phoneSpeaks': s.phoneSpeaks,
        'robotId': s.robotId,
        'robotName': s.robotName,
        'keepHotspot': s.keepHotspot,
        'manualHotspotSsid': s.manualHotspotSsid,
        'voiceWaitS': s.voiceWaitS,
        'desktopMic': s.desktopMic,
        'trayHintShown': s.trayHintShown,
      }),
    );
  }

  void update(AppSettings Function(AppSettings) f) {
    final s = f(state);
    Haptics.enabled = s.haptics;
    state = s;
    _save(s);
  }

  void rememberEndpoint(BrainEndpoint ep) {
    update((s) => s.copyWith(
          endpoint: ep,
          onboarded: true,
          recent: [ep, ...s.recent.where((e) => !(e.host == ep.host && e.port == ep.port))].take(5).toList(),
        ));
  }
}

final settingsProvider = NotifierProvider<SettingsNotifier, AppSettings>(SettingsNotifier.new);
