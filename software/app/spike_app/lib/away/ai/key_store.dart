/// Where the owner's AI key lives: flutter_secure_storage, which on Android
/// encrypts it with a key held in the Android Keystore (never in plain
/// preferences, never in logs, never sent anywhere but to the provider).
library;

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class SecretStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class KeystoreSecretStore implements SecretStore {
  const KeystoreSecretStore();
  static const _s = FlutterSecureStorage();
  @override
  Future<String?> read(String key) => _s.read(key: key);
  @override
  Future<void> write(String key, String value) => _s.write(key: key, value: value);
  @override
  Future<void> delete(String key) => _s.delete(key: key);
}

/// For tests.
class MemorySecretStore implements SecretStore {
  final Map<String, String> values = {};
  @override
  Future<String?> read(String key) async => values[key];
  @override
  Future<void> write(String key, String value) async => values[key] = value;
  @override
  Future<void> delete(String key) async => values.remove(key);
}

String aiKeyName(String providerId) => 'spike.ai.$providerId.key';

/// A pasted key, tidied: spaces, quotes and line breaks from copy-paste removed.
String tidyKey(String raw) => raw.trim().replaceAll(RegExp(r'''[\s"'`]'''), '');

/// A cheap shape check before any network call (Gemini keys start "AIza" and are 39 chars).
String? keyProblem(String providerId, String key) {
  if (key.isEmpty) return 'Paste a key first';
  if (providerId == 'gemini' && !RegExp(r'^AIza[0-9A-Za-z_\-]{30,}$').hasMatch(key)) {
    return "That doesn't look like a Gemini key (they start with AIza)";
  }
  return null;
}
