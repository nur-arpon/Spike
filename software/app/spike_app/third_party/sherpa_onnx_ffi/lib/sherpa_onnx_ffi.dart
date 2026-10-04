// Spike's entry point to the vendored sherpa-onnx Dart bindings (Apache-2.0, see ../LICENSE and ../README.md).
//
// Upstream's `initBindings()` opens `libsherpa-onnx-c-api.so` by bare name, which only works when the library is
// packed inside the APK (the sherpa_onnx Flutter plugin does that, and with it GPL-3.0 espeak-ng). Spike's APK
// carries no native sherpa-onnx code: the libraries live in the app's private files folder, fetched by the
// owner from the upstream release, so they are opened here by ABSOLUTE path.
library;

import 'dart:ffi';

import 'package:ffi/ffi.dart';

import 'src/sherpa_onnx_bindings.dart';

export 'src/tts.dart';

/// The upstream release these bindings were copied from; the native libraries must be the same version.
const sherpaOnnxBindingVersion = '1.13.8';

/// Opens the native libraries in [dir] and binds every C API function (once per isolate: FFI bindings are
/// per isolate). `libonnxruntime.so` is opened FIRST by absolute path: the C API library names it as a
/// dependency by its bare soname, and the Android linker resolves that against libraries already loaded
/// (the app's files folder is not on its search path). Throws (ArgumentError/UnsupportedError from
/// `DynamicLibrary.open`, or ArgumentError for a missing symbol) when a library is missing, damaged or the
/// wrong version.
void loadSherpaOnnx(String dir) {
  DynamicLibrary.open('$dir/libonnxruntime.so');
  final api = DynamicLibrary.open('$dir/libsherpa-onnx-c-api.so');
  SherpaOnnxBindings.init(api);
}

/// The version string the loaded C library reports (e.g. "1.13.8"); call after [loadSherpaOnnx].
String sherpaOnnxNativeVersion() => SherpaOnnxBindings.getVersionStr?.call().toDartString() ?? '?';
