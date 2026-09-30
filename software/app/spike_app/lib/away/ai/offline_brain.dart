/// The optional offline brain: a small language model that runs on the phone
/// with no internet. Downloaded ONLY when the owner asks (Settings > Offline
/// brain: size shown, progress, cancel, delete); never bundled in the APK.
///
/// Model choice (29 Sep 2026, licences checked): **Qwen3-0.6B** from
/// `litert-community/Qwen3-0.6B`, the `dynamic_wi4b32_afp32` .litertlm build
/// (345 MB, Apache-2.0, not gated: no Hugging Face account needed). Chosen over
/// Gemma 3 1B (Gemma Terms of Use: a custom licence with use restrictions that
/// flow down to users, and the files are gated behind a Hugging Face login) and
/// over Qwen2.5-0.5B (547 MB .task, older and weaker). It runs through
/// flutter_gemma's LiteRT-LM engine on the CPU (works on phones without a
/// usable GPU, like the Galaxy A50).
///
/// Download (30 Sep 2026): the file is fetched by our own resumable
/// [BundleDownloader] (background_downloader), then handed to flutter_gemma
/// with `.fromFile()`, which registers it in place. flutter_gemma 1.11.2's own
/// network install was the cause of the "never finishes" bug: for Hugging Face
/// URLs it turns resume OFF (it assumes weak ETags; the CDN now sends strong
/// ones), and with `foreground: false` Android's WorkManager kills the work at
/// 9 minutes, so every drop or timeout restarted 345 MB from zero.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:path_provider/path_provider.dart';

import '../brain/persona.dart' show ChatMessage;
import '../download/bundle.dart';
import '../download/bundle_downloader.dart';
import 'llm.dart';

class OfflineModelSpec {
  const OfflineModelSpec({required this.fileName, required this.url, required this.sizeBytes, required this.sha256,
      required this.label, required this.licence});
  final String fileName;
  final String url; // pinned to a repo commit: the size and hash below never change under it
  final int sizeBytes;
  final String sha256; // Hugging Face's LFS oid (= X-Linked-ETag)
  final String label;
  final String licence;
  int get sizeMb => (sizeBytes / 1e6).round(); // decimal, as Android and Hugging Face show it
}

const offlineModel = OfflineModelSpec(
  fileName: 'Qwen3-0.6B_dynamic_wi4b32_afp32.litertlm',
  url: 'https://huggingface.co/litert-community/Qwen3-0.6B/resolve/a3c5d805ae362dff7f580bc25f2dfb9a5a7eaa76/'
      'Qwen3-0.6B_dynamic_wi4b32_afp32.litertlm',
  sizeBytes: 344671744,
  sha256: '03e7da1eb1108b50dffaa9bb52cc7bcbad2eb0c66ca990267f480c1e545d2856',
  label: 'Qwen3 0.6B',
  licence: 'Apache-2.0',
);

enum OfflineState { unknown, notInstalled, downloading, paused, installed, failed }

@immutable
class OfflineStatus {
  const OfflineStatus(this.state, {this.progress = 0, this.error, this.dl});
  final OfflineState state;
  final int progress; // 0..100 while downloading or paused
  final String? error;
  final DlStatus? dl; // the download's detail (waiting for the network, checking...)
}

/// Download manager + provider. All flutter_gemma calls are behind this class.
class OfflineBrain implements LlmProvider {
  OfflineBrain({this.spec = offlineModel});
  final OfflineModelSpec spec;

  final _status = StreamController<OfflineStatus>.broadcast();
  OfflineStatus _current = const OfflineStatus(OfflineState.unknown);
  BundleDownloader? _dl;
  StreamSubscription<DlStatus>? _dlSub;
  InferenceModel? _model;
  InferenceChat? _chat;
  bool _initialized = false;

  Stream<OfflineStatus> get status => _status.stream;
  OfflineStatus get current => _current;
  bool get installed => _current.state == OfflineState.installed;

  void _set(OfflineStatus s) {
    _current = s;
    if (!_status.isClosed) _status.add(s);
  }

  static Future<void> Function()? initializer; // set in main(): registers the LiteRT-LM engine

  Future<void> _init() async {
    if (_initialized) return;
    _initialized = true;
    await initializer?.call();
  }

  Future<Bundle> bundle() async => Bundle(
        id: 'spike_brain',
        root: await getApplicationSupportDirectory(),
        folder: 'offline_brain',
        files: [BundleFile(url: spec.url, path: spec.fileName, size: spec.sizeBytes, sha256: spec.sha256)],
        title: 'Spike\'s offline brain',
      );

  Future<BundleDownloader> _downloader() async {
    final d = _dl ??= BundleDownloader.forBundle(await bundle());
    _dlSub ??= d.status.listen(_onDl);
    return d;
  }

  void _onDl(DlStatus s) {
    final pct = (s.fraction * 100).floor();
    switch (s.phase) {
      case DlPhase.starting || DlPhase.downloading || DlPhase.waitingForNetwork || DlPhase.verifying:
        _set(OfflineStatus(OfflineState.downloading, progress: pct, dl: s));
      case DlPhase.paused:
        _set(OfflineStatus(OfflineState.paused, progress: pct, dl: s));
      case DlPhase.failed:
        _set(OfflineStatus(OfflineState.failed, progress: pct, dl: s, error: downloadProblem(s)));
      case DlPhase.idle:
        _set(const OfflineStatus(OfflineState.notInstalled));
      case DlPhase.installed:
        break; // installed once flutter_gemma has it (_register)
    }
  }

  /// At start-up: installed, part-downloaded (paused), or following a download
  /// that is still running in the background. Never starts a download.
  Future<void> refresh() async {
    try {
      await _init();
      final b = await bundle();
      if (_current.state == OfflineState.downloading) return;
      if (b.isComplete) {
        if (!await FlutterGemma.isModelInstalled(spec.fileName)) await _register(b);
        _set(const OfflineStatus(OfflineState.installed));
        return;
      }
      // an older install through flutter_gemma's own downloader still counts
      if (await FlutterGemma.isModelInstalled(spec.fileName) && !await b.dir.exists()) {
        _set(const OfflineStatus(OfflineState.installed));
        return;
      }
      if (await b.dir.exists()) {
        final d = await _downloader();
        if (await d.runningInBackground()) {
          unawaited(download()); // it is already downloading: follow it
        } else {
          _set(const OfflineStatus(OfflineState.paused));
        }
        return;
      }
      _set(const OfflineStatus(OfflineState.notInstalled));
    } catch (e) {
      debugPrint('offline brain refresh: $e');
      _set(const OfflineStatus(OfflineState.notInstalled));
    }
  }

  /// Starts or resumes (partial data is kept). Only when the owner asks.
  Future<void> download() async {
    if (_current.state == OfflineState.downloading && _dl?.current.busy == true) return;
    await _init();
    final d = await _downloader();
    final s = await d.start();
    if (s.phase == DlPhase.installed) await _register(d.bundle);
  }

  Future<void> _register(Bundle b) async {
    try {
      await FlutterGemma.installModel(modelType: ModelType.qwen3, fileType: ModelFileType.litertlm)
          .fromFile(b.fileFor(b.files.single).path)
          .install();
      _set(const OfflineStatus(OfflineState.installed));
    } catch (e) {
      debugPrint('offline brain: register $e');
      _set(const OfflineStatus(OfflineState.failed, error: 'Downloaded, but the brain would not install. Delete it and try again.'));
    }
  }

  Future<void> pause() async => (await _downloader()).pause();

  /// Stops and deletes the partial download.
  Future<void> cancel() async => (await _downloader()).cancel();

  Future<void> delete() async {
    await _model?.close();
    _model = null;
    await _init();
    try {
      await FlutterGemma.uninstallModel(spec.fileName); // a .fromFile install: forgets it, leaves the file
      await FlutterGemma.clearActiveInferenceIdentity();
    } catch (_) {}
    await (await _downloader()).cancel(); // deletes our folder (and any partial data)
    _set(const OfflineStatus(OfflineState.notInstalled));
  }

  Future<InferenceModel> _load() async {
    final m = _model;
    if (m != null) return m;
    await _init();
    return _model = await FlutterGemma.getActiveModel(maxTokens: 1280, preferredBackend: PreferredBackend.cpu);
  }

  @override
  String get id => 'offline';
  @override
  String get label => 'Offline brain (${spec.label})';

  @override
  Stream<String> stream(List<ChatMessage> messages, {int? maxTokens, double temperature = 0.7}) async* {
    if (!installed) throw const LlmError(LlmErrorKind.other, 'offline brain not installed');
    final InferenceModel model;
    try {
      model = await _load();
    } catch (e) {
      throw LlmError(LlmErrorKind.other, 'offline load failed: ${e.runtimeType}');
    }
    // Qwen3 thinks out loud unless told not to; /no_think switches that off (the
    // reply parser also drops any <think> block, like it does for the laptop's model).
    final system = '${messages.where((m) => m.role == 'system').map((m) => m.content).join('\n\n')}\n/no_think';
    try {
      await _chat?.close(); // one live conversation at a time: each reply starts clean
    } catch (_) {}
    final chat = _chat = await model.createChat(
      systemInstruction: system,
      temperature: temperature,
      topK: 40,
      topP: 0.9,
      modelType: ModelType.qwen3,
      maxOutputTokens: maxTokens ?? 110,
    );
    for (final m in messages.where((m) => m.role != 'system')) {
      await chat.addQueryChunk(Message.text(text: m.content, isUser: m.role == 'user'));
    }
    try {
      await for (final r in chat.generateChatResponseAsync().timeout(const Duration(seconds: 30))) {
        if (r is TextResponse && r.token.isNotEmpty) yield r.token;
      }
    } on TimeoutException {
      await chat.stopGeneration();
      throw const LlmError(LlmErrorKind.other, 'offline model too slow');
    }
  }

  /// The tiny model is not trusted as a safety classifier (the phrase screen,
  /// which runs first and needs no model, is what catches real risk).
  @override
  Future<String> completeJson(String system, String user, Map<String, Object> schema,
          {int maxTokens = 40, Duration timeout = const Duration(seconds: 4)}) =>
      Future.error(const LlmError(LlmErrorKind.other, 'no classifier offline'));

  @override
  Future<void> check() async {
    if (!installed) throw const LlmError(LlmErrorKind.other, 'not installed');
  }

  Future<void> dispose() async {
    await _dlSub?.cancel();
    await _model?.close();
    await _status.close();
  }
}
