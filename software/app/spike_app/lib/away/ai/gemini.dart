/// Google Gemini over its REST API (server-sent events), with a key the owner
/// pastes from Google AI Studio.
///
/// Why plain REST and not a package (checked 29 Sep 2026): Google's own Dart
/// SDK `google_generative_ai` is marked "not actively maintained" in the Gemini
/// docs, and their recommended replacements need a Firebase project
/// (`firebase_ai`) or a whole framework (Genkit) - neither fits a key the
/// owner pastes. The REST call is the same one the laptop brain's GeminiLLM
/// makes (`mind/llm.py`), so both brains talk to Gemini identically.
///
/// Models: `gemini-3.5-flash-lite` first (the free tier gives it ~500 requests
/// a day; the 3.x "flash" models only ~20), then the fallbacks. A 404 (model
/// gone) or 429 (that model's quota used up) moves on to the next model; when
/// all are rate-limited the brain gets [LlmErrorKind.rateLimited] and Spike
/// says a friendly line instead of an error.
library;

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../brain/persona.dart' show ChatMessage;
import 'llm.dart';

const geminiDefaultModels = ['gemini-3.5-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash'];

class GeminiProvider implements LlmProvider {
  GeminiProvider({
    required String apiKey,
    List<String>? models,
    http.Client? client,
    this.firstTokenTimeout = const Duration(seconds: 12),
    this.totalTimeout = const Duration(seconds: 25),
    this.baseUrl = 'https://generativelanguage.googleapis.com/v1beta',
  })  : _key = apiKey.trim(),
        models = models ?? geminiDefaultModels,
        _client = client ?? http.Client();

  final String _key;
  final List<String> models;
  final http.Client _client;
  final Duration firstTokenTimeout;
  final Duration totalTimeout;
  final String baseUrl;
  final Set<String> _gone = {}; // models that answered 404 this session
  final Set<String> _noThinkingCfg = {}; // models that refused our thinking setting
  String? lastModel;

  @override
  String get id => 'gemini';
  @override
  String get label => 'Gemini';

  Map<String, String> get _headers => {'Content-Type': 'application/json', 'x-goog-api-key': _key};

  /// Same request body as the laptop's GeminiLLM.build_body (system as systemInstruction,
  /// assistant turns as "model", consecutive same-role turns joined), plus the lowest
  /// thinking setting the model allows (spoken replies must start fast).
  Map<String, Object?> buildBody(List<ChatMessage> messages, String model,
      {required double temperature, required int maxTokens, Map<String, Object>? schema}) {
    final system = messages.where((m) => m.role == 'system').map((m) => m.content).join('\n\n');
    final contents = <Map<String, Object?>>[];
    for (final m in messages) {
      if (m.role == 'system') continue;
      final role = m.role == 'assistant' ? 'model' : 'user';
      if (contents.isNotEmpty && contents.last['role'] == role) {
        final parts = contents.last['parts'] as List<Map<String, String>>;
        parts[0] = {'text': '${parts[0]['text']}\n${m.content}'};
      } else {
        contents.add({
          'role': role,
          'parts': [
            {'text': m.content}
          ],
        });
      }
    }
    final gen = <String, Object?>{'temperature': temperature, 'maxOutputTokens': maxTokens};
    if (!_noThinkingCfg.contains(model)) {
      gen['thinkingConfig'] = model.startsWith('gemini-2.') ? {'thinkingBudget': 0} : {'thinkingLevel': 'minimal'};
    }
    if (schema != null) {
      gen['responseMimeType'] = 'application/json';
      gen['responseSchema'] = schema;
    }
    return {
      'contents': contents,
      'generationConfig': gen,
      if (system.isNotEmpty)
        'systemInstruction': {
          'parts': [
            {'text': system}
          ]
        },
    };
  }

  /// Text of one SSE `data:` line (thought parts skipped). Throws on a safety block.
  static String parseSseLine(String line) {
    if (!line.startsWith('data:')) return '';
    final Object? data;
    try {
      data = jsonDecode(line.substring(5).trim());
    } catch (_) {
      return '';
    }
    return textOf(data);
  }

  static String textOf(Object? data) {
    if (data is! Map) return '';
    final block = (data['promptFeedback'] as Map?)?['blockReason'];
    if (block != null) throw LlmError(LlmErrorKind.blocked, 'prompt blocked: $block');
    final out = StringBuffer();
    for (final c in (data['candidates'] as List? ?? const [])) {
      if (c is! Map) continue;
      final reason = c['finishReason'];
      for (final p in ((c['content'] as Map?)?['parts'] as List? ?? const [])) {
        if (p is Map && p['text'] is String && p['thought'] != true) out.write(p['text']);
      }
      if (out.isEmpty && (reason == 'SAFETY' || reason == 'PROHIBITED_CONTENT' || reason == 'BLOCKLIST')) {
        throw LlmError(LlmErrorKind.blocked, 'reply blocked: $reason');
      }
    }
    return out.toString();
  }

  /// Maps an HTTP error to our kinds. Never includes the key.
  static LlmError errorFor(int status, String body) {
    final low = body.toLowerCase();
    if (status == 429 || low.contains('resource_exhausted')) return LlmError(LlmErrorKind.rateLimited, 'HTTP $status');
    if (status == 401 || status == 403 || (status == 400 && (low.contains('api key') || low.contains('api_key')))) {
      return LlmError(LlmErrorKind.badKey, 'HTTP $status');
    }
    if (status >= 500) return LlmError(LlmErrorKind.other, 'HTTP $status');
    return LlmError(LlmErrorKind.other, 'HTTP $status: ${body.length > 200 ? body.substring(0, 200) : body}');
  }

  List<String> get _order => [for (final m in models) if (!_gone.contains(m)) m];

  @override
  Stream<String> stream(List<ChatMessage> messages, {int? maxTokens, double temperature = 0.7}) async* {
    if (_key.isEmpty) throw const LlmError(LlmErrorKind.badKey, 'no key');
    LlmError? last;
    for (final model in _order) {
      var gotAny = false;
      try {
        await for (final piece in _streamModel(model, messages, maxTokens ?? 110, temperature)) {
          gotAny = true;
          lastModel = model;
          yield piece;
        }
        return;
      } on LlmError catch (e) {
        if (gotAny) rethrow; // half a reply already spoken: don't restart elsewhere
        last = e;
        if (e.kind == LlmErrorKind.rateLimited || e.message.startsWith('HTTP 404')) continue;
        rethrow;
      }
    }
    throw last ?? const LlmError(LlmErrorKind.other, 'no Gemini model available');
  }

  Stream<String> _streamModel(String model, List<ChatMessage> messages, int maxTokens, double temperature) async* {
    for (var attempt = 0; attempt < 2; attempt++) {
      final req = http.Request('POST', Uri.parse('$baseUrl/models/$model:streamGenerateContent?alt=sse'))
        ..headers.addAll(_headers)
        ..body = jsonEncode(buildBody(messages, model, temperature: temperature, maxTokens: maxTokens));
      final http.StreamedResponse resp;
      try {
        resp = await _client.send(req).timeout(firstTokenTimeout);
      } on TimeoutException {
        throw const LlmError(LlmErrorKind.network, 'timed out');
      } catch (e) {
        throw LlmError(LlmErrorKind.network, e.runtimeType.toString());
      }
      if (resp.statusCode != 200) {
        final body = await resp.stream.bytesToString().timeout(firstTokenTimeout, onTimeout: () => '');
        if (resp.statusCode == 404) {
          _gone.add(model);
          throw const LlmError(LlmErrorKind.other, 'HTTP 404');
        }
        if (resp.statusCode == 400 && body.toLowerCase().contains('thinking') && !_noThinkingCfg.contains(model)) {
          _noThinkingCfg.add(model); // this model has no such thinking setting: ask again without it
          continue;
        }
        throw errorFor(resp.statusCode, body);
      }
      final deadline = DateTime.now().add(totalTimeout);
      final lines = resp.stream.transform(utf8.decoder).transform(const LineSplitter());
      try {
        await for (final line in lines.timeout(firstTokenTimeout)) {
          if (DateTime.now().isAfter(deadline)) throw const LlmError(LlmErrorKind.network, 'reply too slow');
          final text = parseSseLine(line.trim());
          if (text.isNotEmpty) yield text;
        }
      } on TimeoutException {
        throw const LlmError(LlmErrorKind.network, 'stream stalled');
      }
      return;
    }
  }

  @override
  Future<String> completeJson(String system, String user, Map<String, Object> schema,
      {int maxTokens = 40, Duration timeout = const Duration(seconds: 4)}) async {
    if (_key.isEmpty) throw const LlmError(LlmErrorKind.badKey, 'no key');
    final model = _order.isEmpty ? models.first : _order.first;
    final body = buildBody([ChatMessage('system', system), ChatMessage('user', user)], model,
        temperature: 0, maxTokens: maxTokens, schema: schema);
    try {
      final r = await _client
          .post(Uri.parse('$baseUrl/models/$model:generateContent'), headers: _headers, body: jsonEncode(body))
          .timeout(timeout);
      if (r.statusCode != 200) throw errorFor(r.statusCode, r.body);
      return textOf(jsonDecode(r.body));
    } on TimeoutException {
      throw const LlmError(LlmErrorKind.network, 'timed out');
    } on LlmError {
      rethrow;
    } catch (e) {
      throw LlmError(LlmErrorKind.network, e.runtimeType.toString());
    }
  }

  /// "Test key": a one-token reply from the first model that exists. A key that is
  /// only rate-limited right now still counts as working (the error says so).
  @override
  Future<void> check() async {
    await stream([const ChatMessage('user', 'Say hi.')], maxTokens: 8, temperature: 0).drain<void>();
  }

  void close() => _client.close();
}
