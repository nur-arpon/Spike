# Kokoro on the phone (sherpa-onnx): kept, not built

> **Superseded on 4 Oct 2026 (1.0.3):** the public app now offers Kokoro as an OPTIONAL add-on the user
> installs himself: the APK still has no sherpa-onnx native code; the phone downloads the official libraries
> from the sherpa-onnx GitHub release (SHA-256 checked) and opens them by path with vendored Apache-2.0 Dart
> bindings. See `lib/away/voice/kokoro_addon.dart`, `lib/away/voice/kokoro_voice_addon.dart`,
> `third_party/sherpa_onnx_ffi/` and `software/app/ANDROID-RELEASE.md` "The Kokoro add-on". The private-build
> route below is kept for reference only; do not use it for a public build.

**Why it is out of the public app (4 Oct 2026):** sherpa-onnx's Kokoro front end bundles espeak-ng, which
is GPL-3.0. Spike's licence is all rights reserved, so the public Android build must not contain it. The
public voice chain is: laptop voice (at home) / Gemini natural voice (with the user's key) / Android's own
text-to-speech.

What is where:

| Part | Where | State in the public build |
|---|---|---|
| The engine (isolate + sherpa-onnx calls) | `optional/kokoro_sherpa/kokoro_voice_sherpa.dart` | not compiled (outside `lib/`, excluded in `analysis_options.yaml`) |
| The dependency | `sherpa_onnx` in `pubspec.yaml` | removed, so no `libsherpa-onnx-*.so` / `libonnxruntime.so` / espeak data in the APK |
| The hook | `kokoroEngine` in `lib/away/voice/speaker.dart` | `null`, so `kokoroVoiceAvailable` is false |
| Voice pack download (`KokoroPack`), Settings card | `lib/away/voice/speaker.dart`, `lib/features/settings/away_settings.dart` | kept, hidden while `kokoroVoiceAvailable` is false |

## Putting it back in a PRIVATE build (never a public one under the current licence)

1. `pubspec.yaml`: add `sherpa_onnx: ^1.13.8` under dependencies, then `flutter pub get`.
2. Move `kokoro_voice_sherpa.dart` to `lib/away/voice/kokoro_voice_sherpa.dart`.
3. In `lib/main.dart`, before `runApp`: `kokoroEngine = SherpaKokoroVoice.new;` (import the file and
   `away/voice/speaker.dart`).
4. `flutter test`, then build. The Settings card "Spike's voice" and the Kokoro step of the voice chain
   come back by themselves.

Then check the APK: `lib/arm64-v8a/` lists `libsherpa-onnx-c-api.so` again. Such an APK must not be published.
