/// One small WebView interface for the two pages the app hosts (the face_v2 engine and the 3D
/// preview), with an implementation per platform (software/app/DESIGN.md "Desktop"):
///
///  * phone: `webview_flutter` (Android System WebView), as before;
///  * Windows: `webview_windows` (Microsoft Edge WebView2, drawn as a Flutter texture, so our own
///    widgets can sit on top of it and it scrolls and animates with the app).
///
/// Pages talk back through named channels (`SpikeBridge.postMessage("...")`). On Windows a tiny
/// script, added before any page script runs, gives the page the same `SpikeBridge` object and
/// forwards to WebView2's `chrome.webview.postMessage`, so the page code is identical everywhere.
/// The app's assets are served from a private virtual host (https://spike.assets/) mapped to the
/// installed `data\flutter_assets` folder: nothing is reachable from outside, and the page runs
/// as a normal https origin (audio, canvas and module rules behave like on the phone).
library;

import 'dart:async';
import 'dart:io' show Directory, File, Platform;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart' as wf;
import 'package:webview_flutter_android/webview_flutter_android.dart' as wfa;
import 'package:webview_windows/webview_windows.dart' as ww;

import 'brand.dart';
import 'platform.dart';

abstract class SpikeWebController {
  /// [asset] e.g. 'assets/face/face_host.html'. [channels]: name -> handler of the page's messages.
  factory SpikeWebController({
    required String asset,
    Map<String, void Function(String message)> channels = const {},
    FutureOr<void> Function()? onPageFinished,
  }) =>
      AppPlatform.desktop
          ? _WindowsWeb(asset, channels, onPageFinished)
          : _MobileWeb(asset, channels, onPageFinished);

  Future<void> runJs(String code);

  /// The view. [eager]: the page gets every drag (the face and the 3D model follow the finger).
  Widget view({bool eager = true});
  void dispose();
}

// ---------------------------------------------------------------- phone: webview_flutter
class _MobileWeb implements SpikeWebController {
  _MobileWeb(String asset, Map<String, void Function(String)> channels, FutureOr<void> Function()? onPageFinished) {
    _c = wf.WebViewController()
      ..setJavaScriptMode(wf.JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0x00000000));
    for (final e in channels.entries) {
      _c.addJavaScriptChannel(e.key, onMessageReceived: (m) => e.value(m.message));
    }
    _c.setNavigationDelegate(wf.NavigationDelegate(
      // our pages never navigate anywhere else
      onNavigationRequest: (r) =>
          r.url.startsWith('file:///android_asset/') ? wf.NavigationDecision.navigate : wf.NavigationDecision.prevent,
      onPageFinished: (_) => onPageFinished?.call(),
    ));
    final platform = _c.platform;
    if (platform is wfa.AndroidWebViewController) {
      platform.setMediaPlaybackRequiresUserGesture(false); // face sounds without a first tap
    }
    _c.loadFlutterAsset(asset);
  }

  late final wf.WebViewController _c;

  @override
  Future<void> runJs(String code) => _c.runJavaScript(code);

  @override
  Widget view({bool eager = true}) => wf.WebViewWidget(
        controller: _c,
        gestureRecognizers: eager ? {Factory<OneSequenceGestureRecognizer>(() => EagerGestureRecognizer())} : const {},
      );

  @override
  void dispose() {}
}

// ---------------------------------------------------------------- Windows: WebView2
const assetsHost = 'spike.assets';

/// The page's `window.<channel>.postMessage(m)` objects on WebView2 (pure; tested).
String bridgeScript(Iterable<String> channels) {
  final names = channels.map((c) => "'$c'").join(',');
  return "(function(){var w=window.chrome&&window.chrome.webview;if(!w)return;"
      "[$names].forEach(function(n){window[n]={postMessage:function(m){w.postMessage({ch:n,m:String(m)});}};});})();";
}

/// Where the app's assets are on disk in a Windows build (`<exe dir>\data\flutter_assets`).
String windowsAssetsFolder() => '${File(Platform.resolvedExecutable).parent.path}\\data\\flutter_assets';

/// WebView2 keeps its profile here: a writable per-user folder named after the permanent internal
/// id (an installed package folder is read-only, and a rename must not lose it).
String windowsWebViewDataFolder() {
  final base = Platform.environment['LOCALAPPDATA'] ?? Directory.systemTemp.path;
  return '$base\\${AppBrand.internalId}\\webview2';
}

bool _envReady = false;

Future<void> _ensureEnvironment() async {
  if (_envReady) return;
  _envReady = true;
  try {
    await ww.WebviewController.initializeEnvironment(
      userDataPath: windowsWebViewDataFolder(),
      // the face makes its little sounds without waiting for a first click (as on the phone)
      additionalArguments: '--autoplay-policy=no-user-gesture-required',
    );
  } catch (_) {
    // already initialised by an earlier page: fine
  }
}

class _WindowsWeb implements SpikeWebController {
  _WindowsWeb(this.asset, this.channels, this.onPageFinished) {
    _ready = _init();
  }

  final String asset;
  final Map<String, void Function(String)> channels;
  final FutureOr<void> Function()? onPageFinished;
  final ww.WebviewController _c = ww.WebviewController();
  late final Future<void> _ready;
  final _shown = ValueNotifier<bool>(false);
  StreamSubscription<dynamic>? _msgs;
  StreamSubscription<ww.LoadingState>? _loads;
  bool _disposed = false;

  Future<void> _init() async {
    await _ensureEnvironment();
    await _c.initialize();
    if (_disposed) return;
    await _c.setBackgroundColor(Colors.transparent);
    await _c.setPopupWindowPolicy(ww.WebviewPopupWindowPolicy.deny);
    await _c.addVirtualHostNameMapping(assetsHost, windowsAssetsFolder(), ww.WebviewHostResourceAccessKind.deny);
    await _c.addScriptToExecuteOnDocumentCreated(bridgeScript(channels.keys));
    _msgs = _c.webMessage.listen((m) {
      if (m is Map && m['ch'] is String) channels[m['ch']]?.call('${m['m'] ?? ''}');
    }, onError: (Object _) {});
    _loads = _c.loadingState.listen((s) {
      if (s == ww.LoadingState.navigationCompleted) {
        onPageFinished?.call();
      }
    });
    await _c.loadUrl('https://$assetsHost/$asset');
    if (!_disposed) _shown.value = true;
  }

  @override
  Future<void> runJs(String code) async {
    await _ready;
    if (_disposed) return;
    await _c.executeScript(code);
  }

  @override
  Widget view({bool eager = true}) => ValueListenableBuilder<bool>(
        valueListenable: _shown,
        builder: (context, shown, _) => shown ? ww.Webview(_c) : const SizedBox.expand(),
      );

  @override
  void dispose() {
    _disposed = true;
    _msgs?.cancel();
    _loads?.cancel();
    _shown.dispose();
    unawaited(_ready.then((_) => _c.dispose(), onError: (_) => _c.dispose()));
  }
}
