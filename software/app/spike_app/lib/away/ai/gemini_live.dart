/// Gemini Live (native audio) over its WebSocket, BidiGenerateContent v1beta.
///
/// Checked 30 Sep 2026 (ai.google.dev/api/live, live-guide, live-session, pricing):
///  * wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent
///  * first message `setup` (model, generationConfig with responseModalities
///    AUDIO + speechConfig voice, systemInstruction, realtimeInputConfig VAD,
///    input/outputAudioTranscription, contextWindowCompression, sessionResumption),
///    then wait for `setupComplete`.
///  * mic in: realtimeInput.audio, 16-bit PCM 16 kHz mono ("audio/pcm;rate=16000");
///    voice out: serverContent.modelTurn inlineData, 16-bit PCM 24 kHz mono.
///  * transcripts: serverContent.inputTranscription / outputTranscription {text}.
///  * a connection lives ~10 min (GoAway warns first); audio sessions 15 min
///    unless contextWindowCompression is on; resumption handles last 2 h.
///  * Models on the free tier: gemini-3.8-live (affective dialog: yes),
///    gemini-3.1-flash-live-preview (no affective dialog),
///    gemini-2.5-flash-native-audio-preview-12-2025.
///
/// The key is the owner's own, pasted into this phone, so it is used on the
/// device (Google's ephemeral tokens exist to keep a SERVER's key out of an
/// app; here there is no server and the key is already on the phone). It goes
/// in the x-goog-api-key header, never in the URL, never in a log or an error.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show debugPrint;
import 'package:web_socket_channel/io.dart';

const liveEndpoint =
    'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent';
const liveModels = ['gemini-3.8-live', 'gemini-3.1-flash-live-preview', 'gemini-2.5-flash-native-audio-preview-12-2025'];
const liveInRate = 16000;
const liveOutRate = 24000;

enum LiveErrorKind { rateLimited, badKey, notFound, badSetup, network, other }

class LiveError implements Exception {
  const LiveError(this.kind, [this.message = '']);
  final LiveErrorKind kind;
  final String message; // never the key
  @override
  String toString() => 'LiveError($kind, $message)';
}

sealed class LiveEvent {
  const LiveEvent();
}

class LiveReady extends LiveEvent {
  const LiveReady();
}

class LiveAudio extends LiveEvent {
  const LiveAudio(this.pcm);
  final Uint8List pcm; // s16le mono 24 kHz
}

class LiveInputText extends LiveEvent {
  const LiveInputText(this.text);
  final String text; // a piece of what the owner said (in order)
}

class LiveOutputText extends LiveEvent {
  const LiveOutputText(this.text);
  final String text; // a piece of what Gemini is saying (in order)
}

class LiveTurnComplete extends LiveEvent {
  const LiveTurnComplete();
}

class LiveInterrupted extends LiveEvent {
  const LiveInterrupted();
}

class LiveGoAway extends LiveEvent {
  const LiveGoAway(this.timeLeft);
  final Duration timeLeft;
}

class LiveResumeHandle extends LiveEvent {
  const LiveResumeHandle(this.handle);
  final String handle;
}

class LiveClosed extends LiveEvent {
  const LiveClosed(this.error);
  final LiveError? error;
}

class LiveConfig {
  const LiveConfig({
    required this.voice,
    required this.systemInstruction,
    this.silenceMs = 3000,
    this.affective = true,
    this.resumeHandle,
  });
  final String voice;
  final String systemInstruction;
  final int silenceMs; // the owner's "Wait before Spike answers"
  final bool affective;
  final String? resumeHandle;
}

bool supportsAffective(String model) => model.startsWith('gemini-3.8-live');
bool usesRealtimeText(String model) => !model.startsWith('gemini-2.');

/// The `setup` message.
Map<String, Object?> buildSetup(String model, LiveConfig c, {bool affective = true}) => {
      'setup': {
        'model': 'models/$model',
        'generationConfig': {
          'responseModalities': ['AUDIO'],
          'speechConfig': {
            'voiceConfig': {
              'prebuiltVoiceConfig': {'voiceName': c.voice}
            }
          },
        },
        // a setup field (live-api/capabilities, JS SDK LiveConnectConfig), NOT inside generationConfig
        if (affective && c.affective && supportsAffective(model)) 'enableAffectiveDialog': true,
        'systemInstruction': {
          'parts': [
            {'text': c.systemInstruction}
          ]
        },
        'realtimeInputConfig': {
          'automaticActivityDetection': {'silenceDurationMs': c.silenceMs, 'prefixPaddingMs': 300},
        },
        'inputAudioTranscription': <String, Object?>{},
        'outputAudioTranscription': <String, Object?>{},
        'contextWindowCompression': {'slidingWindow': <String, Object?>{}},
        'sessionResumption': {if (c.resumeHandle != null) 'handle': c.resumeHandle},
      }
    };

Map<String, Object?> audioMessage(Uint8List pcm16k) => {
      'realtimeInput': {
        'audio': {'data': base64Encode(pcm16k), 'mimeType': 'audio/pcm;rate=$liveInRate'}
      }
    };

Map<String, Object?> textMessage(String model, String text) => usesRealtimeText(model)
    ? {
        'realtimeInput': {'text': text}
      }
    : {
        'clientContent': {
          'turns': [
            {
              'role': 'user',
              'parts': [
                {'text': text}
              ]
            }
          ],
          'turnComplete': true,
        }
      };

Duration _parseDuration(Object? v) {
  final m = RegExp(r'^([\d.]+)s$').firstMatch(v?.toString() ?? '');
  return m == null ? Duration.zero : Duration(milliseconds: (double.parse(m.group(1)!) * 1000).round());
}

/// One server frame (text or UTF-8 bytes) -> events, in the order to act on them.
List<LiveEvent> parseServerFrame(Object? frame) {
  final Object? data;
  try {
    data = jsonDecode(frame is String ? frame : utf8.decode(frame as List<int>));
  } catch (_) {
    return const [];
  }
  if (data is! Map) return const [];
  final out = <LiveEvent>[];
  if (data.containsKey('setupComplete')) out.add(const LiveReady());
  final sc = data['serverContent'];
  if (sc is Map) {
    final input = (sc['inputTranscription'] as Map?)?['text'];
    if (input is String && input.isNotEmpty) out.add(LiveInputText(input));
    final output = (sc['outputTranscription'] as Map?)?['text'];
    if (output is String && output.isNotEmpty) out.add(LiveOutputText(output));
    for (final p in ((sc['modelTurn'] as Map?)?['parts'] as List? ?? const [])) {
      final inline = p is Map ? p['inlineData'] : null;
      if (inline is Map && inline['data'] is String && '${inline['mimeType']}'.startsWith('audio/')) {
        out.add(LiveAudio(base64Decode(inline['data'] as String)));
      }
    }
    if (sc['interrupted'] == true) out.add(const LiveInterrupted());
    if (sc['turnComplete'] == true) out.add(const LiveTurnComplete());
  }
  final ga = data['goAway'];
  if (ga is Map) out.add(LiveGoAway(_parseDuration(ga['timeLeft'])));
  final sr = data['sessionResumptionUpdate'];
  if (sr is Map && sr['resumable'] == true && sr['newHandle'] is String) out.add(LiveResumeHandle(sr['newHandle'] as String));
  return out;
}

/// A server/socket message made safe to show and log: no key, short.
String cleanReason(Object? reason) {
  var r = '${reason ?? ''}'.replaceAll(RegExp(r'AIza[0-9A-Za-z_\-]{10,}'), '<key>');
  r = r.replaceAll(RegExp(r'key=[^&\s]+'), 'key=<key>').replaceAll(RegExp(r'\s+'), ' ').trim();
  return r.length > 160 ? '${r.substring(0, 160)}...' : r;
}

/// What a close before (or during) a session means. Never includes the key.
LiveError errorForClose(int? code, String? reason) {
  final why = cleanReason(reason);
  final r = (reason ?? '').toLowerCase();
  if (r.contains('quota') || r.contains('exhausted') || r.contains('rate limit') || r.contains('429')) {
    return LiveError(LiveErrorKind.rateLimited, 'close $code $why');
  }
  if (r.contains('api key') || r.contains('api_key') || r.contains('permission') || r.contains('unauthenticated')) {
    return LiveError(LiveErrorKind.badKey, 'close $code $why');
  }
  if (r.contains('not found') || r.contains('not supported') || r.contains('is not available')) {
    return LiveError(LiveErrorKind.notFound, 'close $code $why');
  }
  if (code == 1007 || r.contains('invalid') || r.contains('unknown name')) {
    return LiveError(LiveErrorKind.badSetup, 'close $code $why');
  }
  if (code == null || code == 1006) return const LiveError(LiveErrorKind.network, 'connection lost');
  return LiveError(LiveErrorKind.other, 'close $code $why');
}

/// A WebSocket, small enough to fake in tests.
abstract class LiveSocket {
  Stream<Object?> get frames;
  void send(String text);
  Future<void> close();
  int? get closeCode;
  String? get closeReason;
}

typedef LiveConnector = Future<LiveSocket> Function(Uri uri, Map<String, String> headers);

class _IoSocket implements LiveSocket {
  _IoSocket(this._ch);
  final IOWebSocketChannel _ch;
  @override
  Stream<Object?> get frames => _ch.stream;
  @override
  void send(String text) => _ch.sink.add(text);
  @override
  Future<void> close() async => _ch.sink.close();
  @override
  int? get closeCode => _ch.closeCode;
  @override
  String? get closeReason => _ch.closeReason;
}

Future<LiveSocket> ioConnector(Uri uri, Map<String, String> headers) async {
  final ch = IOWebSocketChannel.connect(uri, headers: headers, connectTimeout: const Duration(seconds: 10));
  await ch.ready;
  return _IoSocket(ch);
}

class GeminiLiveSession {
  GeminiLiveSession._(this.model, this._socket) {
    _sub = _socket.frames.listen(
      (f) {
        for (final e in parseServerFrame(f)) {
          if (e is LiveResumeHandle) resumeHandle = e.handle;
          if (!_events.isClosed) _events.add(e);
        }
      },
      onDone: _closed,
      onError: (_) => _closed(),
    );
  }

  final String model;
  final LiveSocket _socket;
  late final StreamSubscription<Object?> _sub;
  final _events = StreamController<LiveEvent>.broadcast();
  bool _open = true;
  bool _closing = false;
  String? resumeHandle;

  Stream<LiveEvent> get events => _events.stream;
  bool get open => _open;

  void _closed() {
    if (!_open) return;
    _open = false;
    final err = _closing ? null : errorForClose(_socket.closeCode, _socket.closeReason);
    if (!_events.isClosed) {
      _events.add(LiveClosed(err));
      _events.close();
    }
  }

  void _send(Map<String, Object?> m) {
    if (_open) _socket.send(jsonEncode(m));
  }

  void sendAudio(Uint8List pcm16k) => _send(audioMessage(pcm16k));
  void sendText(String text) => _send(textMessage(model, text));
  void audioStreamEnd() => _send({
        'realtimeInput': {'audioStreamEnd': true}
      });

  Future<void> close() async {
    _closing = true;
    await _socket.close();
    await _sub.cancel();
    _closed();
  }

  /// Open a session: the first model that answers `setupComplete`. A model that
  /// is missing or out of free quota moves on to the next; a refused optional
  /// field (affective dialog) is retried without it; a bad key stops at once.
  static Future<GeminiLiveSession> connect({
    required String apiKey,
    required LiveConfig config,
    List<String> models = liveModels,
    LiveConnector connector = ioConnector,
    Duration setupTimeout = const Duration(seconds: 10),
  }) async {
    final key = apiKey.trim();
    if (key.isEmpty) throw const LiveError(LiveErrorKind.badKey, 'no key');
    LiveError? last;
    for (final model in models) {
      for (final affective in [true, false]) {
        if (!affective && !(config.affective && supportsAffective(model))) break; // nothing to drop
        final LiveSocket s;
        try {
          s = await connector(Uri.parse(liveEndpoint), {'x-goog-api-key': key});
        } catch (e) {
          final why = cleanReason(e);
          debugPrint('gemini live: $model: could not connect: $why');
          final low = why.toLowerCase();
          // a refused upgrade (HTTP 4xx) is not "no internet"
          if (low.contains('401') || low.contains('403')) throw LiveError(LiveErrorKind.badKey, why);
          if (low.contains('429')) throw LiveError(LiveErrorKind.rateLimited, why);
          throw LiveError(LiveErrorKind.network, why);
        }
        final session = GeminiLiveSession._(model, s);
        final ready = Completer<LiveError?>();
        final sub = session.events.listen((e) {
          if (ready.isCompleted) return;
          if (e is LiveReady) ready.complete(null);
          if (e is LiveClosed) ready.complete(e.error ?? const LiveError(LiveErrorKind.other, 'closed'));
        });
        session._send(buildSetup(model, config, affective: affective));
        final err = await ready.future
            .timeout(setupTimeout, onTimeout: () => const LiveError(LiveErrorKind.network, 'setup timed out'));
        await sub.cancel();
        debugPrint('gemini live: $model${affective && config.affective && supportsAffective(model) ? ' (affective)' : ''}: ${err ?? 'ready'}');
        if (err == null) return session;
        await session.close();
        last = err;
        if (err.kind == LiveErrorKind.badKey || err.kind == LiveErrorKind.network) throw err;
        if (err.kind == LiveErrorKind.badSetup) continue; // try again without the optional field
        break; // rate limited / not found / other: next model
      }
    }
    throw last ?? const LiveError(LiveErrorKind.other, 'no Live model');
  }
}
