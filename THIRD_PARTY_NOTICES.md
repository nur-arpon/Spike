# Third-party notices

Spike is proprietary (see [LICENSE](LICENSE)). It is built with, and in a few places includes, work by
others. Every component below keeps its own licence. Nothing in the Spike licence restricts your rights
under those licences to the third-party components themselves.

This repository contains **source only**. No model weights, voice models, voice recordings, virtual
environments, SDKs or build outputs are committed; the tools that fetch them download them from their
original publishers under the publishers' own terms.

## 1. Included in this repository

| Component | Where | Licence |
|---|---|---|
| three.js (Three.js Authors, 2010-2023) | inlined in `preview_3d/*.html` and `software/app/spike_app/assets/viewer3d/preview_v6.html`; the original `@license` header is kept in each file | MIT |
| flutter_secure_storage_windows (German Saprykin and contributors), patched copy | `software/app/spike_app/third_party/flutter_secure_storage_windows/` (its `LICENSE` file is kept alongside) | BSD-3-Clause |
| Flutter project templates (The Flutter Authors): Windows runner, CMake files, Android Gradle scripts, generated plugin registrants | `software/app/spike_app/windows/`, `software/app/spike_app/android/` | BSD-3-Clause |

## 2. Used by the phone and desktop app (fetched by `flutter pub get`, not included)

Declared in `software/app/spike_app/pubspec.yaml`, with exact versions in `pubspec.lock`. Each package's
licence is on its pub.dev page. Main ones:

| Package | Licence |
|---|---|
| Flutter SDK, cupertino_icons, http, crypto, path_provider, shared_preferences, url_launcher, webview_flutter, flutter_lints | BSD-3-Clause |
| flutter_riverpod, go_router, web_socket_channel, flutter_animate, flutter_svg, archive, toml, connectivity_plus, audioplayers, record, speech_to_text, flutter_tts, nsd, mobile_scanner, universal_ble, flutter_secure_storage, background_downloader, qr_flutter, window_manager, tray_manager, screen_retriever, webview_windows, flutter_launcher_icons | MIT or BSD-3-Clause (per package) |
| sherpa_onnx (k2-fsa) | Apache-2.0 |
| flutter_gemma, flutter_gemma_litertlm | per package (pub.dev) |
| flutter_soloud (SoLoud engine) | MIT / zlib |

## 3. Used by the firmware (fetched by PlatformIO, not included)

| Library | Licence |
|---|---|
| Arduino-ESP32 core (Espressif) | LGPL-2.1 |
| ESP-IDF components, esp32-camera (Espressif) | Apache-2.0 |
| ArduinoJson (Benoit Blanchon) | MIT |
| NimBLE-Arduino (h2zero) | Apache-2.0 |
| GFX Library for Arduino (moononournation) | see upstream repository |
| VL53L0X (Pololu) | see upstream repository (Pololu licence with ST API notice) |

## 4. Used by the laptop brain (installed with pip, not included)

The packaged Windows brain lists its runtime components and their licences in
`software/laptop/desktop_build/THIRD_PARTY_NOTICES.txt`. In summary: Python (PSF), NumPy and SciPy
(BSD-3-Clause), ONNX Runtime (MIT), CTranslate2 and faster-whisper (MIT), tokenizers and huggingface_hub
(Apache-2.0), Vosk (Apache-2.0), sounddevice and PortAudio (MIT), websockets (BSD-3-Clause),
python-zeroconf (LGPL-2.1-or-later), RapidFuzz (MIT), qrcode (BSD-3-Clause), comtypes (MIT). Development
and test tools also use Pillow (HPND), OpenCV (Apache-2.0), PyAV (BSD-3-Clause), MediaPipe (Apache-2.0),
pytest (MIT) and PyMuPDF (AGPL-3.0, used only by a local guide-rendering tool, never distributed).

## 5. Models and voices (downloaded on demand, never included)

| Model | Publisher | Licence |
|---|---|---|
| Whisper base.en / small.en (CTranslate2 conversion) | OpenAI / SYSTRAN | MIT |
| vosk-model-small-en-us-0.15 | Alpha Cephei | Apache-2.0 |
| Silero VAD | Silero Team | MIT |
| Kokoro-82M (via kokoro-onnx) | hexgrad | Apache-2.0 |
| Chatterbox TTS weights | Resemble AI | MIT |
| Piper voices (`en_US-*`) | Rhasspy / per-voice dataset authors | per voice (see each voice's model card) |
| Gemma on-device models (LiteRT-LM) | Google | Gemma Terms of Use |
| Gemini API (cloud service, used with the user's own key) | Google | Gemini API Terms of Service |

**espeak-ng (GPL-3.0-or-later).** Some text-to-speech engines above (Piper, Kokoro's phonemizer) can use
espeak-ng for pronunciation. espeak-ng is not part of this repository and is not bundled with any Spike
build; where it is used, it is installed separately under its own GPL licence.

## 6. Excluded on purpose

Anything whose terms do not allow redistribution, or that belongs to someone else, is kept out of this
repository: third-party reference images, voice reference recordings, all model weights, the NuGet
command-line binary, and all built installers and packages.
