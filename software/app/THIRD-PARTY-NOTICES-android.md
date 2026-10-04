# Third-Party Notices: Spike for Android

Spike (Android app `com.spacez.spike`, version 1.0.3, arm64-v8a) is built with the Dart/Flutter packages,
Android libraries and native libraries listed below. Generated on 4 Oct 2026 from `flutter pub deps --json`
(every package reachable from the non-dev dependencies, with each package's own LICENSE file read from the pub
cache), `gradlew :app:dependencies --configuration releaseRuntimeClasspath` (Android libraries) and the
`lib/arm64-v8a/` folder of the built APK (native libraries). Each component remains under its own licence;
nothing in Spike's own licence (all rights reserved) changes the terms below.

Total: **168** Dart/Flutter packages, **150** Android (Maven) libraries, **30** native libraries in the APK.

**Licences that require attribution if you redistribute a build containing them** (you keep the notice, you
don't need to ask): MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, Zlib, MPL-2.0. This file exists to satisfy
that requirement in one place. Apache-2.0 components that ship a NOTICE file need that NOTICE reproduced too;
the Flutter engine's own third-party notices are inside the APK (`assets/flutter_assets/NOTICES.Z`) and are shown
by Flutter's licence page (`showLicensePage`).

## Copyleft check (GPL / LGPL / AGPL)

**None of the shipped components is under GPL, LGPL or AGPL.**

- **sherpa-onnx native code / espeak-ng (GPL-3.0): not in the APK.** espeak-ng is GPL-3.0 and cannot ship
  inside an all-rights-reserved app, so the `sherpa_onnx` Flutter plugin is not a dependency. Proof on the 1.0.3
  APK: the same 30 native libraries as listed below, no `libsherpa-onnx*`, `libonnxruntime*` or espeak data, and
  no `.so` contains espeak-ng or ONNX Runtime symbols. Only sherpa-onnx's Apache-2.0 Dart bindings are compiled in
  (next section).

## Vendored Dart code: sherpa-onnx Dart FFI bindings (Apache-2.0)

`spike_app/third_party/sherpa_onnx_ffi/` holds three unmodified files of the `sherpa_onnx` 1.13.8 Dart package
(`sherpa_onnx_bindings.dart`, `tts.dart`, `tts_config.dart`) plus Spike's own loader. They are compiled into
`libapp.so` as Dart code; they contain no native code.

```
sherpa-onnx Dart API, version 1.13.8
Copyright (c) 2024 Xiaomi Corporation
https://github.com/k2-fsa/sherpa-onnx
Licensed under the Apache License, Version 2.0 (the "License"); you may not use these files except in
compliance with the License. You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software distributed under the License is
distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
```

The full licence text is in `spike_app/third_party/sherpa_onnx_ffi/LICENSE`. The upstream package ships no
NOTICE file.

## Optional add-on fetched by the user from upstream (not distributed with Spike)

The "Offline backup voice (Kokoro)" add-on (Settings > Voice, Android only) is NOT part of the APK and is not
hosted or redistributed by the publisher. Only when the user taps "Download and install" does the phone download,
straight from the upstream projects, and keep in the app's private storage:

| Part | Fetched from | Licence |
| --- | --- | --- |
| sherpa-onnx C API library (`libsherpa-onnx-c-api.so`, includes espeak-ng) | [sherpa-onnx v1.13.8 GitHub release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/v1.13.8) | sherpa-onnx: Apache-2.0; espeak-ng inside it: [GPL-3.0](https://github.com/espeak-ng/espeak-ng) |
| ONNX Runtime (`libonnxruntime.so`) | same release | [MIT](https://github.com/microsoft/onnxruntime) |
| espeak-ng-data | [sherpa-onnx `tts-models` release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models) | GPL-3.0 |
| Kokoro-82M voice files | [Hugging Face csukuangfj/kokoro-multi-lang-v1_0](https://huggingface.co/csukuangfj/kokoro-multi-lang-v1_0) | Apache-2.0 |

Those parts stay under their own licences; the app shows them with links before the download. Design and
hashes: `software/app/ANDROID-RELEASE.md` "The Kokoro add-on".

- **MPL-2.0** (`bluez`, `dbus`, `nm`, by Canonical): weak copyleft that only covers changes to those files. They
  are the Linux implementations of `universal_ble` and `connectivity_plus`, used unmodified and not used on
  Android at all (listed because they are in the Dart dependency graph).
- The match is on each package's LICENSE text. MPL-2.0's text names the GPL family as "secondary licences"; those
  three were checked by hand and are MPL-2.0 only.

## Not open source, but free to ship (read their terms)

| Component | Comes with | Terms | Note |
| --- | --- | --- | --- |
| Google ML Kit barcode scanning (`com.google.mlkit:*`, `libbarhopper_v3.so`) | `mobile_scanner` (the pairing QR scanner) | [ML Kit Terms of Service](https://developers.google.com/ml-kit/terms) | ML Kit may send anonymous usage and performance data to Google (through `com.google.android.datatransport`). The privacy policy should say so. |
| Google Play services basement / base / tasks, play-services-mlkit-barcode-scanning (`com.google.android.gms:*`) | `mobile_scanner` | [Android Software Development Kit License](https://developer.android.com/studio/terms) | |
| Qualcomm AI Engine Direct (QNN) runtime: `libQnnHtp.so`, `libQnnSystem.so`, `libQnnHtpV73/75/79/81Stub.so` | `flutter_gemma_litertlm` (downloads them from the flutter_gemma GitHub release at build time) | Qualcomm's licence for the QNN/QAIRT redistributable runtime | Used only by the NPU path of the offline brain, which Spike runs on the CPU. About 10 MB; candidates for the existing jniLibs excludes after an on-phone test of the offline brain. |

## Native libraries in the APK (`lib/arm64-v8a/`, 30 files)

| Library | From | Licence |
| --- | --- | --- |
| libflutter.so | Flutter engine (includes Skia, ICU, HarfBuzz, BoringSSL and others; full list in `NOTICES.Z`) | BSD-3-Clause (+ the engine's notices) |
| libapp.so | Spike's own Dart code and the Dart packages below | Spike: all rights reserved; packages: as listed |
| libLiteRtLm.so, libLiteRtGpuAccelerator.so, libLiteRtOpenClAccelerator.so, libLiteRtWebGpuAccelerator.so, libLiteRtTopKOpenClSampler.so, libLiteRtTopKWebGpuSampler.so, libLiteRtDispatch_Qualcomm.so, libGemmaModelConstraintProvider.so | Google LiteRT / LiteRT-LM, via `flutter_gemma_litertlm` | Apache-2.0 |
| libStreamProxy.so | `flutter_gemma_litertlm` | MIT |
| libQnnHtp.so, libQnnSystem.so, libQnnHtpV73Stub.so, libQnnHtpV75Stub.so, libQnnHtpV79Stub.so, libQnnHtpV81Stub.so | Qualcomm QNN runtime, via `flutter_gemma_litertlm` | Qualcomm (see above) |
| libbarhopper_v3.so | Google ML Kit barcode scanning, via `mobile_scanner` | ML Kit Terms (see above) |
| libimage_processing_util_jni.so, libsurface_util_jni.so | AndroidX CameraX, via `mobile_scanner` | Apache-2.0 |
| libdatastore_shared_counter.so | AndroidX DataStore, via `shared_preferences_android` | Apache-2.0 |
| libflutter_soloud_plugin.so | `flutter_soloud` (SoLoud engine and its bundled libraries) | MIT; SoLoud: Zlib ("no attribution in binary form is required") |
| libogg.so, libvorbis.so, libvorbisenc.so, libvorbisfile.so, libopus.so, libFLAC.so | Xiph.Org codecs, via `flutter_soloud` | BSD-3-Clause |
| libdartjni.so | `jni` (dart-lang/native) | BSD-3-Clause |
| libcnativeapi.so | `cnativeapi` (libnativeapi) | MIT |

## Android (Maven) libraries

| Group | Artifacts (version) | Licence |
| --- | --- | --- |
| androidx.activity | activity 1.9.0, activity-ktx 1.9.0 | Apache-2.0 |
| androidx.annotation | annotation 1.10.0, annotation-experimental 1.4.1, annotation-jvm 1.10.0 | Apache-2.0 |
| androidx.appcompat | appcompat 1.6.1, appcompat-resources 1.6.1 | Apache-2.0 |
| androidx.arch.core | core-common 2.2.0, core-runtime 2.2.0 | Apache-2.0 |
| androidx.asynclayoutinflater | asynclayoutinflater 1.0.0 | Apache-2.0 |
| androidx.browser | browser 1.9.0 | Apache-2.0 |
| androidx.camera | camera-camera2 1.6.1, camera-camera2-pipe 1.6.1, camera-core 1.6.1, camera-lifecycle 1.6.1 | Apache-2.0 |
| androidx.camera.featurecombinationquery | featurecombinationquery 1.6.1 | Apache-2.0 |
| androidx.collection | collection 1.4.2, collection-jvm 1.4.2, collection-ktx 1.4.2 | Apache-2.0 |
| androidx.concurrent | concurrent-futures 1.3.0, concurrent-futures-ktx 1.3.0 | Apache-2.0 |
| androidx.coordinatorlayout | coordinatorlayout 1.0.0 | Apache-2.0 |
| androidx.core | core 1.18.0, core-backported-fixes 1.0.0, core-ktx 1.18.0, core-viewtree 1.0.0 | Apache-2.0 |
| androidx.cursoradapter | cursoradapter 1.0.0 | Apache-2.0 |
| androidx.customview | customview 1.1.0 | Apache-2.0 |
| androidx.datastore | datastore 1.1.7, datastore-android 1.1.7, datastore-core 1.1.7, datastore-core-android 1.1.7, datastore-core-okio 1.1.7, datastore-core-okio-jvm 1.1.7, datastore-preferences 1.1.7, datastore-preferences-android 1.1.7, datastore-preferences-core 1.1.7, datastore-preferences-core-android 1.1.7, datastore-preferences-external-protobuf 1.1.7, datastore-preferences-proto 1.1.7 | Apache-2.0 |
| androidx.documentfile | documentfile 1.0.0 | Apache-2.0 |
| androidx.drawerlayout | drawerlayout 1.0.0 | Apache-2.0 |
| androidx.emoji2 | emoji2 1.2.0, emoji2-views-helper 1.2.0 | Apache-2.0 |
| androidx.exifinterface | exifinterface 1.4.2 | Apache-2.0 |
| androidx.fragment | fragment 1.7.1, fragment-ktx 1.7.1 | Apache-2.0 |
| androidx.interpolator | interpolator 1.0.0 | Apache-2.0 |
| androidx.legacy | legacy-support-core-ui 1.0.0, legacy-support-core-utils 1.0.0 | Apache-2.0 |
| androidx.lifecycle | lifecycle-common 2.7.0, lifecycle-common-java8 2.7.0, lifecycle-livedata 2.7.0, lifecycle-livedata-core 2.7.0, lifecycle-livedata-core-ktx 2.7.0, lifecycle-process 2.7.0, lifecycle-runtime 2.7.0, lifecycle-runtime-ktx 2.7.0, lifecycle-service 2.7.0, lifecycle-viewmodel 2.7.0, lifecycle-viewmodel-ktx 2.7.0, lifecycle-viewmodel-savedstate 2.7.0 | Apache-2.0 |
| androidx.loader | loader 1.0.0 | Apache-2.0 |
| androidx.localbroadcastmanager | localbroadcastmanager 1.0.0 | Apache-2.0 |
| androidx.preference | preference 1.2.1, preference-ktx 1.2.1 | Apache-2.0 |
| androidx.print | print 1.0.0 | Apache-2.0 |
| androidx.profileinstaller | profileinstaller 1.3.1 | Apache-2.0 |
| androidx.recyclerview | recyclerview 1.0.0 | Apache-2.0 |
| androidx.resourceinspection | resourceinspection-annotation 1.0.1 | Apache-2.0 |
| androidx.room | room-common 2.7.0, room-common-jvm 2.7.0, room-runtime 2.7.0, room-runtime-android 2.7.0 | Apache-2.0 |
| androidx.savedstate | savedstate 1.2.1, savedstate-ktx 1.2.1 | Apache-2.0 |
| androidx.slidingpanelayout | slidingpanelayout 1.2.0 | Apache-2.0 |
| androidx.sqlite | sqlite 2.5.0, sqlite-android 2.5.0, sqlite-framework 2.5.0, sqlite-framework-android 2.5.0 | Apache-2.0 |
| androidx.startup | startup-runtime 1.1.1 | Apache-2.0 |
| androidx.swiperefreshlayout | swiperefreshlayout 1.0.0 | Apache-2.0 |
| androidx.tracing | tracing 1.3.0, tracing-android 1.3.0, tracing-ktx 1.3.0 | Apache-2.0 |
| androidx.transition | transition 1.4.1 | Apache-2.0 |
| androidx.vectordrawable | vectordrawable 1.1.0, vectordrawable-animated 1.1.0 | Apache-2.0 |
| androidx.versionedparcelable | versionedparcelable 1.1.1 | Apache-2.0 |
| androidx.viewpager | viewpager 1.0.0 | Apache-2.0 |
| androidx.webkit | webkit 1.15.0 | Apache-2.0 |
| androidx.window | window 1.2.0, window-java 1.2.0 | Apache-2.0 |
| androidx.window.extensions.core | core 1.0.0 | Apache-2.0 |
| androidx.work | work-runtime 2.11.0, work-runtime-ktx 2.11.0 | Apache-2.0 |
| com.getkeepsafe.relinker | relinker 1.4.5 | Apache-2.0 |
| com.google.android.datatransport | transport-api 2.2.1, transport-backend-cct 2.3.3, transport-runtime 2.2.6 | Apache-2.0 |
| com.google.android.gms | play-services-base 18.5.0, play-services-basement 18.4.0, play-services-mlkit-barcode-scanning 18.3.1, play-services-tasks 18.2.0 | Android Software Development Kit License (Google, proprietary; free to ship in apps) |
| com.google.android.odml | image 1.0.0-beta1 | Apache-2.0 |
| com.google.auto.value | auto-value-annotations 1.6.3 | Apache-2.0 |
| com.google.code.findbugs | jsr305 3.0.2 | Apache-2.0 |
| com.google.code.gson | gson 2.13.2 | Apache-2.0 |
| com.google.crypto.tink | tink-android 1.23.0 | Apache-2.0 |
| com.google.dagger | dagger 2.59 | Apache-2.0 |
| com.google.errorprone | error_prone_annotations 2.41.0 | Apache-2.0 |
| com.google.firebase | firebase-annotations 16.0.0, firebase-components 16.1.0, firebase-encoders 16.1.0, firebase-encoders-json 17.1.0 | Apache-2.0 |
| com.google.guava | listenablefuture 1.0 | Apache-2.0 |
| com.google.mlkit | barcode-scanning 17.3.0, barcode-scanning-common 17.0.0, common 18.11.0, vision-common 17.3.0, vision-interfaces 16.3.0 | ML Kit Terms of Service (Google, proprietary; free to ship in apps) |
| com.squareup.okhttp3 | okhttp 4.9.0 | Apache-2.0 |
| com.squareup.okio | okio 3.4.0, okio-jvm 3.4.0 | Apache-2.0 |
| io.flutter | arm64_v8a_release 1.0.0-af7e796e161ae0bb1ff0758c71a7105418bd9ded, armeabi_v7a_release 1.0.0-af7e796e161ae0bb1ff0758c71a7105418bd9ded, flutter_embedding_release 1.0.0-af7e796e161ae0bb1ff0758c71a7105418bd9ded, x86_64_release 1.0.0-af7e796e161ae0bb1ff0758c71a7105418bd9ded | BSD-3-Clause |
| jakarta.inject | jakarta.inject-api 2.0.1 | Apache-2.0 |
| javax.inject | javax.inject 1 | Apache-2.0 |
| org.jetbrains | annotations 23.0.0 | Apache-2.0 |
| org.jetbrains.kotlin | kotlin-android-extensions-runtime 1.9.22, kotlin-parcelize-runtime 1.9.22, kotlin-stdlib 2.4.0, kotlin-stdlib-common 2.4.0, kotlin-stdlib-jdk7 1.8.0, kotlin-stdlib-jdk8 1.8.0 | Apache-2.0 |
| org.jetbrains.kotlinx | atomicfu 0.28.0, atomicfu-jvm 0.28.0, kotlinx-coroutines-android 1.11.0, kotlinx-coroutines-bom 1.11.0, kotlinx-coroutines-core 1.11.0, kotlinx-coroutines-core-jvm 1.11.0, kotlinx-serialization-bom 1.9.0, kotlinx-serialization-core 1.9.0, kotlinx-serialization-core-jvm 1.9.0, kotlinx-serialization-json 1.9.0, kotlinx-serialization-json-jvm 1.9.0 | Apache-2.0 |
| org.jspecify | jspecify 1.0.0 | Apache-2.0 |

## Dart/Flutter packages: BSD-3-Clause (110)

| Package | Version | Source |
| --- | --- | --- |
| args | 2.7.0 | [link](https://github.com/dart-lang/core/tree/main/pkgs/args) |
| async | 2.13.1 | [link](https://github.com/dart-lang/core/tree/main/pkgs/async) |
| boolean_selector | 2.1.2 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/boolean_selector) |
| characters | 1.4.1 | [link](https://github.com/dart-lang/core/tree/main/pkgs/characters) |
| code_assets | 1.2.1 | [link](https://github.com/dart-lang/native/tree/main/pkgs/code_assets) |
| collection | 1.19.1 | [link](https://github.com/dart-lang/core/tree/main/pkgs/collection) |
| connectivity_plus | 7.3.1 | [link](https://github.com/fluttercommunity/plus_plugins) |
| connectivity_plus_platform_interface | 2.1.0 | [link](https://github.com/fluttercommunity/plus_plugins) |
| cross_file | 0.3.5+5 | [link](https://github.com/flutter/packages/tree/main/packages/cross_file) |
| crypto | 3.0.7 | [link](https://github.com/dart-lang/core/tree/main/pkgs/crypto) |
| cupertino_ui | 1.1.1 | [link](https://github.com/flutter/packages/tree/main/packages/cupertino_ui) |
| ffi | 2.2.0 | [link](https://github.com/dart-lang/native/tree/main/pkgs/ffi) |
| ffi_leak_tracker | 0.1.2 | [link](https://github.com/halildurmus/win32/tree/main/packages/ffi_leak_tracker) |
| file | 7.0.1 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/file) |
| fixnum | 1.1.1 | [link](https://github.com/dart-lang/core/tree/main/pkgs/fixnum) |
| flutter | 0.0.0 | Flutter SDK |
| flutter_animate | 4.5.2 | [link](https://github.com/gskinner/flutter_animate) |
| flutter_secure_storage | 11.2.0 | [link](https://github.com/mogol/flutter_secure_storage/tree/develop/flutter_secure_storage) |
| flutter_secure_storage_darwin | 0.4.3 | [link](https://github.com/juliansteenbakker/flutter_secure_storage) |
| flutter_secure_storage_linux | 3.0.3 | [link](https://github.com/mogol/flutter_secure_storage) |
| flutter_secure_storage_platform_interface | 2.1.1 | [link](https://github.com/mogol/flutter_secure_storage) |
| flutter_secure_storage_web | 2.1.1 | [link](https://github.com/mogol/flutter_secure_storage) |
| flutter_secure_storage_windows | 4.2.2+spike.1 | vendored: `third_party/` |
| flutter_shaders | 0.1.3 | [link](https://github.com/jonahwilliams/flutter_shaders) |
| genai_primitives | 0.2.4 | [link](https://github.com/flutter/genui/tree/main/packages/genai_primitives) |
| go_router | 18.0.2 | [link](https://github.com/flutter/packages/tree/main/packages/go_router) |
| hooks | 2.0.2 | [link](https://github.com/dart-lang/native/tree/main/pkgs/hooks) |
| http | 1.6.0 | [link](https://github.com/dart-lang/http/tree/master/pkgs/http) |
| http_parser | 4.1.2 | [link](https://github.com/dart-lang/http/tree/master/pkgs/http_parser) |
| intl | 0.20.3 | [link](https://github.com/dart-lang/i18n/tree/main/pkgs/intl) |
| jni | 1.0.3 | [link](https://github.com/dart-lang/native/tree/main/pkgs/jni) |
| jni_flutter | 1.0.3 | [link](https://github.com/dart-lang/native/tree/main/pkgs/jni_flutter) |
| jni_util | 1.0.0 | [link](https://github.com/dart-lang/native/tree/main/pkgs/jni_util) |
| json_annotation | 4.12.0 | [link](https://github.com/google/json_serializable.dart/tree/master/json_annotation) |
| json_schema_builder | 0.1.7 | [link](https://github.com/flutter/genui/tree/main/packages/json_schema_builder) |
| leak_tracker | 11.0.2 | [link](https://github.com/dart-lang/leak_tracker/tree/main/pkgs/leak_tracker) |
| leak_tracker_flutter_testing | 3.0.10 | [link](https://github.com/dart-lang/leak_tracker/tree/main/pkgs/leak_tracker_flutter_testing) |
| leak_tracker_testing | 3.0.2 | [link](https://github.com/dart-lang/leak_tracker/tree/main/pkgs/leak_tracker_testing) |
| listen | 1.0.1 | [link](https://github.com/flutter/core-packages/tree/main/packages/listen) |
| logging | 1.3.0 | [link](https://github.com/dart-lang/core/tree/main/pkgs/logging) |
| matcher | 0.12.20 | [link](https://github.com/dart-lang/test/tree/master/pkgs/matcher) |
| material_ui | 1.5.0 | [link](https://github.com/flutter/packages/tree/main/packages/material_ui) |
| meta | 1.18.3 | [link](https://github.com/dart-lang/sdk/tree/main/pkg/meta) |
| mime | 2.1.0 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/mime) |
| mobile_scanner | 7.4.2 | [link](https://github.com/juliansteenbakker/mobile_scanner) |
| mutex | 3.1.0 | [link](https://github.com/hoylen/dart-mutex) |
| objective_c | 9.5.0 | [link](https://github.com/dart-lang/native/tree/main/pkgs/objective_c) |
| package_config | 3.0.0 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/package_config) |
| path | 1.9.1 | [link](https://github.com/dart-lang/core/tree/main/pkgs/path) |
| path_provider | 2.1.6 | [link](https://github.com/flutter/packages/tree/main/packages/path_provider/path_provider) |
| path_provider_android | 2.3.1 | [link](https://github.com/flutter/packages/tree/main/packages/path_provider/path_provider_android) |
| path_provider_foundation | 2.6.0 | [link](https://github.com/flutter/packages/tree/main/packages/path_provider/path_provider_foundation) |
| path_provider_linux | 2.2.2 | [link](https://github.com/flutter/packages/tree/main/packages/path_provider/path_provider_linux) |
| path_provider_platform_interface | 2.1.3 | [link](https://github.com/flutter/packages/tree/main/packages/path_provider/path_provider_platform_interface) |
| path_provider_windows | 2.3.0 | [link](https://github.com/flutter/packages/tree/main/packages/path_provider/path_provider_windows) |
| platform | 3.2.0 | [link](https://github.com/dart-lang/core/tree/main/pkgs/platform) |
| plugin_platform_interface | 2.1.8 | [link](https://github.com/flutter/packages/tree/main/packages/plugin_platform_interface) |
| pub_semver | 2.2.1 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/pub_semver) |
| qr | 3.0.2 | [link](https://github.com/kevmoo/qr.dart) |
| qr_flutter | 4.1.0 | [link](https://github.com/theyakka/qr.flutter) |
| record | 7.1.1 | [link](https://github.com/llfbandit/record/tree/main/record) |
| record_android | 2.2.0 | [link](https://github.com/llfbandit/record/tree/main/record_android) |
| record_ios | 2.1.1 | [link](https://github.com/llfbandit/record/tree/main/record_ios) |
| record_linux | 2.1.2 | [link](https://github.com/llfbandit/record/tree/main/record_linux) |
| record_macos | 2.1.1 | [link](https://github.com/llfbandit/record/tree/main/record_macos) |
| record_platform_interface | 2.1.0 | [link](https://github.com/llfbandit/record/tree/main/record_platform_interface) |
| record_use | 0.6.0 | [link](https://github.com/dart-lang/native/tree/main/pkgs/record_use) |
| record_web | 2.1.3 | [link](https://github.com/llfbandit/record/tree/main/record_web) |
| record_windows | 2.3.0 | [link](https://github.com/llfbandit/record/tree/main/record_windows) |
| shared_preferences | 2.5.5 | [link](https://github.com/flutter/packages/tree/main/packages/shared_preferences/shared_preferences) |
| shared_preferences_android | 2.4.28 | [link](https://github.com/flutter/packages/tree/main/packages/shared_preferences/shared_preferences_android) |
| shared_preferences_foundation | 2.5.7 | [link](https://github.com/flutter/packages/tree/main/packages/shared_preferences/shared_preferences_foundation) |
| shared_preferences_linux | 2.4.1 | [link](https://github.com/flutter/packages/tree/main/packages/shared_preferences/shared_preferences_linux) |
| shared_preferences_platform_interface | 2.4.2 | [link](https://github.com/flutter/packages/tree/main/packages/shared_preferences/shared_preferences_platform_interface) |
| shared_preferences_web | 2.4.3 | [link](https://github.com/flutter/packages/tree/main/packages/shared_preferences/shared_preferences_web) |
| shared_preferences_windows | 2.4.1 | [link](https://github.com/flutter/packages/tree/main/packages/shared_preferences/shared_preferences_windows) |
| source_span | 1.10.2 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/source_span) |
| speech_to_text | 7.5.0 | [link](https://github.com/csdcorp/speech_to_text) |
| speech_to_text_platform_interface | 2.5.0 | [link](https://github.com/csdcorp/speech_to_text/speech_to_text_platform_interface) |
| speech_to_text_windows | 1.0.1 | [link](https://github.com/csdcorp/speech_to_text) |
| stack_trace | 1.12.2 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/stack_trace) |
| stream_channel | 2.1.4 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/stream_channel) |
| string_scanner | 1.4.1 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/string_scanner) |
| term_glyph | 1.2.2 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/term_glyph) |
| test_api | 0.7.12 | [link](https://github.com/dart-lang/test/tree/master/pkgs/test_api) |
| typed_data | 1.4.0 | [link](https://github.com/dart-lang/core/tree/main/pkgs/typed_data) |
| universal_ble | 2.3.0 | [link](https://navideck.com) |
| url_launcher | 6.3.2 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher) |
| url_launcher_android | 6.3.33 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher_android) |
| url_launcher_ios | 6.4.2 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher_ios) |
| url_launcher_linux | 3.2.3 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher_linux) |
| url_launcher_macos | 3.2.6 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher_macos) |
| url_launcher_platform_interface | 2.3.2 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher_platform_interface) |
| url_launcher_web | 2.4.3 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher_web) |
| url_launcher_windows | 3.1.6 | [link](https://github.com/flutter/packages/tree/main/packages/url_launcher/url_launcher_windows) |
| vector_graphics | 1.2.3 | [link](https://github.com/flutter/packages/tree/main/packages/vector_graphics) |
| vector_graphics_codec | 1.1.13 | [link](https://github.com/flutter/packages/tree/main/packages/vector_graphics_codec) |
| vector_graphics_compiler | 1.3.0 | [link](https://github.com/flutter/packages/tree/main/packages/vector_graphics_compiler) |
| vector_math | 2.4.0 | [link](https://github.com/flutter/core-packages/tree/main/packages/vector_math) |
| vm_service | 15.3.0 | [link](https://github.com/dart-lang/sdk/tree/main/pkg/vm_service) |
| web | 1.1.1 | [link](https://github.com/dart-lang/web) |
| web_socket | 1.0.1 | [link](https://github.com/dart-lang/http/tree/master/pkgs/web_socket) |
| web_socket_channel | 3.0.3 | [link](https://github.com/dart-lang/http/tree/master/pkgs/web_socket_channel) |
| webview_flutter | 4.14.1 | [link](https://github.com/flutter/packages/tree/main/packages/webview_flutter/webview_flutter) |
| webview_flutter_android | 4.14.1 | [link](https://github.com/flutter/packages/tree/main/packages/webview_flutter/webview_flutter_android) |
| webview_flutter_platform_interface | 2.15.1 | [link](https://github.com/flutter/packages/tree/main/packages/webview_flutter/webview_flutter_platform_interface) |
| webview_flutter_wkwebview | 3.26.2 | [link](https://github.com/flutter/packages/tree/main/packages/webview_flutter/webview_flutter_wkwebview) |
| webview_windows | 0.4.0 | [link](https://github.com/jnschulze/flutter-webview-windows) |
| win32 | 6.4.0 | [link](https://win32.pub) |
| xdg_directories | 1.1.0 | [link](https://github.com/flutter/packages/tree/main/packages/xdg_directories) |

## Dart/Flutter packages: MIT (46)

| Package | Version | Source |
| --- | --- | --- |
| archive | 4.3.0 | [link](https://github.com/brendan-duncan/archive) |
| audioplayers | 6.8.1 | [link](https://github.com/bluefireteam/audioplayers) |
| audioplayers_android | 5.3.0 | [link](https://github.com/bluefireteam/audioplayers) |
| audioplayers_darwin | 6.5.0 | [link](https://github.com/bluefireteam/audioplayers) |
| audioplayers_linux | 4.3.0 | [link](https://github.com/bluefireteam/audioplayers) |
| audioplayers_platform_interface | 7.2.0 | [link](https://github.com/bluefireteam/audioplayers) |
| audioplayers_web | 5.3.0 | [link](https://github.com/bluefireteam/audioplayers) |
| audioplayers_windows | 4.4.1 | [link](https://github.com/bluefireteam/audioplayers) |
| background_downloader | 9.6.3 | [link](https://github.com/781flyingdutchman/background_downloader) |
| cnativeapi | 0.3.0 | [link](https://github.com/libnativeapi/nativeapi-flutter) |
| cupertino_icons | 1.0.9 | [link](https://github.com/flutter/packages/tree/main/third_party/packages/cupertino_icons) |
| email_validator | 3.0.0 | [link](https://github.com/fredeil/email-validator.dart) |
| flutter_gemma | 1.11.3 | [link](https://fluttergemma.dev) |
| flutter_gemma_litertlm | 1.8.5 | [link](https://fluttergemma.dev) |
| flutter_riverpod | 3.4.3 | [link](https://riverpod.dev) |
| flutter_soloud | 4.1.7 | [link](https://github.com/alnitak/flutter_soloud) |
| flutter_svg | 2.3.0 | [link](https://github.com/flutter/packages/tree/main/third_party/packages/flutter_svg) |
| flutter_tts | 4.2.5 | [link](https://github.com/dlutton/flutter_tts) |
| flutter_web_bluetooth | 1.1.0 | [link](https://github.com/jeroen1602/flutter_web_bluetooth/) |
| large_file_handler | 0.5.2 | [link](https://github.com/DenisovAV/large_file_handler) |
| nativeapi | 0.3.0 | [link](https://github.com/libnativeapi/nativeapi-flutter) |
| nested | 1.0.0 | [link](https://github.com/rrousselGit/nested) |
| nsd | 5.0.1 | [link](https://github.com/sebastianhaberey/nsd/tree/main/nsd) |
| nsd_android | 2.2.0 | [link](https://github.com/sebastianhaberey/nsd/tree/main/nsd_android) |
| nsd_ios | 3.0.1 | [link](https://github.com/sebastianhaberey/nsd/tree/main/nsd_ios) |
| nsd_macos | 3.0.1 | [link](https://github.com/sebastianhaberey/nsd/tree/main/nsd_macos) |
| nsd_platform_interface | 2.2.0 | [link](https://github.com/sebastianhaberey/nsd/tree/main/nsd_platform_interface) |
| nsd_windows | 3.0.1 | [link](https://github.com/sebastianhaberey/nsd/tree/main/nsd_windows) |
| path_parsing | 1.1.0 | [link](https://github.com/flutter/packages/tree/main/third_party/packages/path_parsing) |
| petitparser | 7.0.2 | [link](https://petitparser.github.io) |
| posix | 6.5.2 | [link](https://github.com/onepub-dev/dart_posix) |
| provider | 6.1.5+1 | [link](https://github.com/rrousselGit/provider) |
| riverpod | 3.4.3 | [link](https://riverpod.dev) |
| screen_retriever | 0.2.2 | [link](https://github.com/leanflutter/screen_retriever) |
| screen_retriever_linux | 0.2.2 | [link](https://github.com/leanflutter/screen_retriever/tree/main/packages/screen_retriever_linux) |
| screen_retriever_macos | 0.2.2 | [link](https://github.com/leanflutter/screen_retriever/tree/main/packages/screen_retriever_macos) |
| screen_retriever_platform_interface | 0.2.2 | [link](https://github.com/leanflutter/screen_retriever/blob/main/packages/screen_retriever_platform_interface) |
| screen_retriever_windows | 0.2.2 | [link](https://github.com/leanflutter/screen_retriever/tree/main/packages/screen_retriever_windows) |
| state_notifier | 1.0.0 | [link](https://github.com/rrousselGit/state_notifier) |
| synchronized | 3.4.2 | [link](https://github.com/tekartik/synchronized.dart/tree/master/synchronized) |
| toml | 0.18.0 | [link](https://github.com/just95/toml.dart) |
| tray_manager | 0.7.0 | [link](https://github.com/leanflutter/tray_manager) |
| uuid | 4.6.0 | [link](https://github.com/Daegalus/dart-uuid) |
| window_manager | 0.5.2 | [link](https://leanflutter.dev) |
| xml | 7.0.1 | [link](https://github.com/renggli/dart-xml) |
| yaml | 3.1.4 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/yaml) |

## Dart/Flutter packages: Apache-2.0 (6)

| Package | Version | Source |
| --- | --- | --- |
| clock | 1.1.3 | [link](https://github.com/dart-lang/tools/tree/main/pkgs/clock) |
| decimal | 3.2.6 | [link](https://github.com/a14n/dart-decimal) |
| fake_async | 1.3.3 | [link](https://github.com/dart-lang/test/tree/master/pkgs/fake_async) |
| material_color_utilities | 0.13.0 | [link](https://github.com/material-foundation/material-color-utilities/tree/main/dart) |
| rational | 2.2.3 | [link](https://github.com/a14n/dart-rational) |
| sky_engine | 0.0.0 | Flutter SDK |

## Dart/Flutter packages: MPL-2.0 (3)

| Package | Version | Source |
| --- | --- | --- |
| bluez | 0.8.3 | [link](https://github.com/canonical/bluez.dart) |
| dbus | 0.7.15 | [link](https://github.com/canonical/dbus.dart) |
| nm | 0.5.0 | [link](https://github.com/canonical/nm.dart) |

## Dart/Flutter packages: BSD-3-Clause (Flutter SDK packages, covered by the Flutter SDK LICENSE) (3)

| Package | Version | Source |
| --- | --- | --- |
| flutter_localizations | 0.0.0 | Flutter SDK |
| flutter_test | 0.0.0 | Flutter SDK |
| flutter_web_plugins | 0.0.0 | Flutter SDK |

---

Regenerate after any dependency change (the same three sources named at the top), and
re-run the copyleft check before every public release.
