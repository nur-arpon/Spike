/// The Windows runner's own channel "spikebuddy/desktop" (windows/runner/desktop_integration.cpp):
/// "Start with Windows" through the package's StartupTask, and "another launch asked us to show".
library;

import 'package:flutter/services.dart';

/// The StartupTask's state as Windows reports it. Only [enabled]/[disabled] can be changed by the
/// app; the user's own choice in Task Manager (disabledByUser) and policies are Windows' to change.
enum StartWithWindows { enabled, disabled, disabledByUser, disabledByPolicy, enabledByPolicy, unsupported, unknown }

StartWithWindows parseStartState(Object? s) => switch (s) {
      'enabled' => StartWithWindows.enabled,
      'disabled' => StartWithWindows.disabled,
      'disabledByUser' => StartWithWindows.disabledByUser,
      'disabledByPolicy' => StartWithWindows.disabledByPolicy,
      'enabledByPolicy' => StartWithWindows.enabledByPolicy,
      'unsupported' => StartWithWindows.unsupported,
      _ => StartWithWindows.unknown,
    };

extension StartWithWindowsText on StartWithWindows {
  bool get isOn => this == StartWithWindows.enabled || this == StartWithWindows.enabledByPolicy;
  bool get canChange => this == StartWithWindows.enabled || this == StartWithWindows.disabled;

  /// A short note under the switch, or null.
  String? get note => switch (this) {
        StartWithWindows.disabledByUser =>
          'Turned off in Windows. Switch it on again in Settings > Apps > Startup.',
        StartWithWindows.disabledByPolicy || StartWithWindows.enabledByPolicy => 'Set by your organisation.',
        StartWithWindows.unsupported => 'Available in the installed app.',
        _ => null,
      };
}

class DesktopChannel {
  DesktopChannel([MethodChannel? channel]) : _ch = channel ?? const MethodChannel('spikebuddy/desktop') {
    _ch.setMethodCallHandler((call) async {
      if (call.method == 'shown') onShown?.call();
      return null;
    });
  }

  final MethodChannel _ch;

  /// Another launch of the app brought this window forward (the runner already showed it).
  void Function()? onShown;

  Future<StartWithWindows> _state(String method) async {
    try {
      return parseStartState(await _ch.invokeMethod<String>(method));
    } on PlatformException {
      return StartWithWindows.unknown;
    } on MissingPluginException {
      return StartWithWindows.unsupported;
    }
  }

  Future<StartWithWindows> startWithWindows() => _state('startupTask.get');
  Future<StartWithWindows> setStartWithWindows(bool on) => _state(on ? 'startupTask.enable' : 'startupTask.disable');

  /// Windows 11: the title bar in the app's background colour (older Windows ignores it).
  Future<void> setCaptionColors(int captionArgb, int textArgb) async {
    try {
      await _ch.invokeMethod<void>('setCaptionColors', {'caption': captionArgb, 'text': textArgb});
    } catch (_) {}
  }

  Future<bool> isPackaged() async {
    try {
      return await _ch.invokeMethod<bool>('isPackaged') ?? false;
    } catch (_) {
      return false;
    }
  }
}
