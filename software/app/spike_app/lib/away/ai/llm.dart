/// The phone brain's language models. One small interface so adding a cloud
/// provider (OpenAI, Anthropic, OpenRouter, Groq...) is one class each: it
/// turns the brain's chat messages into its own request, streams text pieces
/// back, and maps its errors onto [LlmErrorKind]. Only Gemini ships now (owner
/// decision 29 Sep); the offline model implements the same interface.
library;

import '../brain/persona.dart' show ChatMessage;

enum LlmErrorKind {
  /// Free-tier quota or rate limit (HTTP 429): Spike says a friendly, in-character line.
  rateLimited,

  /// The key is wrong, revoked or not allowed (HTTP 400 "API key not valid", 401, 403).
  badKey,

  /// No internet, DNS, timeouts.
  network,

  /// The provider refused the prompt or the reply (its own safety block).
  blocked,

  /// Anything else (5xx, a bad reply).
  other,
}

class LlmError implements Exception {
  const LlmError(this.kind, this.message);
  final LlmErrorKind kind;
  final String message; // for logs only: never shown or spoken raw
  @override
  String toString() => 'LlmError(${kind.name}: $message)';
}

abstract class LlmProvider {
  /// Stable id (settings, logs): `gemini`, `offline`.
  String get id;

  /// What the owner sees in Settings.
  String get label;

  /// Reply text pieces as they arrive. Throws [LlmError].
  Stream<String> stream(List<ChatMessage> messages, {int? maxTokens, double temperature = 0.7});

  /// One short, deterministic JSON answer (the safety classifier). Throws [LlmError].
  Future<String> completeJson(String system, String user, Map<String, Object> schema,
      {int maxTokens = 40, Duration timeout = const Duration(seconds: 4)});

  /// "Test key": a cheap call that proves the provider works. Throws [LlmError].
  Future<void> check();
}

/// Providers the app knows how to build, for the Settings picker. Adding one =
/// a class implementing [LlmProvider] + an entry here.
class ProviderInfo {
  const ProviderInfo({required this.id, required this.label, required this.keyHint, required this.keyUrl});
  final String id;
  final String label;
  final String keyHint;
  final String keyUrl; // where the owner gets a key (shown as text; the app never signs in anywhere)
}

const cloudProviders = [
  ProviderInfo(
    id: 'gemini',
    label: 'Google Gemini (free key)',
    keyHint: 'Paste your Gemini API key',
    keyUrl: 'aistudio.google.com/apikey',
  ),
];
