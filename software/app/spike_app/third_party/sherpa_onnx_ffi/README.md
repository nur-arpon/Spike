# sherpa_onnx_ffi: vendored sherpa-onnx Dart bindings (Apache-2.0)

What: the text-to-speech part of the Dart FFI bindings of [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
1.13.8 (Copyright (c) 2024 Xiaomi Corporation, Apache License 2.0, full text in `LICENSE`). Copied on
4 Oct 2026 from the pub.dev package `sherpa_onnx` 1.13.8.

| File | Upstream | Changed? |
|---|---|---|
| `lib/src/sherpa_onnx_bindings.dart` | `sherpa_onnx/lib/src/sherpa_onnx_bindings.dart` | no (SHA-256 57b98c6e...86bc78) |
| `lib/src/tts.dart` | `sherpa_onnx/lib/src/tts.dart` | no (SHA-256 c472fcda...fe0626) |
| `lib/src/tts_config.dart` | `sherpa_onnx/lib/src/tts_config.dart` | no (SHA-256 7396e65a...44ca0e) |
| `lib/sherpa_onnx_ffi.dart` | new (Spike) | replaces upstream's `initBindings()`: opens the libraries by absolute path |

Why vendored: the `sherpa_onnx` Flutter plugin packages (`sherpa_onnx_android_arm64` and friends) put
`libsherpa-onnx-c-api.so` and `libonnxruntime.so` inside the APK, and the C API library links espeak-ng
(GPL-3.0). Spike's APK must contain no GPL code, so this package is PURE DART (no `flutter: plugin:` section, no
native files): only the Dart code is compiled into the app.

The native libraries are an optional add-on the owner installs on his phone (Settings > Voice > Offline backup
voice): the app downloads the official prebuilt Android libraries from the sherpa-onnx GitHub release, checks
their SHA-256, and `loadSherpaOnnx(dir)` opens them from the app's files folder
(`spike_app/lib/away/voice/kokoro_addon.dart`, `software/app/ANDROID-RELEASE.md` "The Kokoro add-on").

Updating: copy the same three files from a newer `sherpa_onnx` release, bump `sherpaOnnxBindingVersion`, and
re-pin the archive and library hashes in `kokoro_addon.dart` to the SAME release (every C function the bindings
look up must exist in the library, or `loadSherpaOnnx` throws).
