# Spike for Android: the public release identity

Set on 4 Oct 2026 for the first public Android release (1.0.1). Two things here are PERMANENT: once one
copy is installed by anyone, changing either of them strands that copy.

## 1. The application ID: `com.spacez.spike` (PERMANENT, never change)

| What | Value | Where |
|---|---|---|
| applicationId | `com.spacez.spike` | `spike_app/android/app/build.gradle.kts` |
| namespace (Kotlin package of MainActivity, LocalHotspot) | `com.spacez.spike` | same file; sources in `android/app/src/main/kotlin/com/spacez/spike/` |

Android knows an app by this ID. A build with a different ID is a different app: it installs beside the old
one, gets none of its data, and the old one never receives another update. The development builds before
4 Oct 2026 used `com.spikebuddy.spike_app`; those test installs are a separate app now and are removed by
hand (Settings > Apps), never by a script.

Not to be confused with: the Dart package name `spike_app` (pubspec.yaml, `package:spike_app/...` imports)
and the internal id `spikebuddy` (Windows data folders, mutex, the `spikebuddy/desktop` channel). Those are
separate and also never renamed (RENAMING.md). The Android method channels (`spike/storage`,
`spike/hotspot`) do not contain the package name.

## 2. The release signing key (PERMANENT, the worst one to lose)

```
spike_app/android/keystore/spike-release.jks   the keystore (PKCS12), alias `spike`
spike_app/android/key.properties               storePassword, keyPassword, keyAlias, storeFile
```

Both are gitignored (`spike_app/android/.gitignore`: `/keystore/`, `/key.properties`, plus the template's
`key.properties` and `**/*.jks`). **They are not in the repo and not on GitHub.** If the D: drive dies and
there is no backup, they are gone.

Every copy of Spike installed from a public APK checks every later APK against this key. So:

> **If you lose the key or its password, no installed copy can ever be updated again.** Not "re-sign it".
> Android refuses an update signed by a different key. The only way back is for every user to uninstall
> (losing their data) and install a new app. **Never generate a new key.** If the password looks wrong,
> the password is almost certainly right and something is mangling it: handle it from PowerShell, never
> from Git Bash (MSYS rewrites values that look like paths).

Identify the right key by its certificate fingerprint:

```
Owner:  CN=Nur Ifran Arpon, O=SpaceZ
RSA 4096, SHA384withRSA, valid 4 Oct 2026 to 26 Sep 2056
SHA-256: 7E:84:C0:86:E9:21:9D:FE:A1:1C:0C:5E:F5:96:3D:D2:3E:FA:5E:12:F7:F6:E3:CA:26:11:4B:4F:BD:2E:7C:C0
SHA-1:   0E:2F:B5:67:C1:90:11:1C:8F:D9:2C:7B:DF:8E:73:50:EA:D7:33:C7
```

Check a keystore (PowerShell): `keytool -list -v -keystore spike-release.jks` (it asks for the password).
Check a built APK: `apksigner verify --print-certs Spike_x.y.z_android_arm64.apk`; the SHA-256 must match.

### Backups

The key and its password are backed up in private places outside this repository (never in it).

Back up BOTH the .jks and the password; one without the other is useless.

### How the build uses it

`android/app/build.gradle.kts` reads `android/key.properties`. If it exists, release builds are signed with
the key. If it is missing, **every release build fails** with "Release build refused: android/key.properties
... is missing". There is no fallback to the debug key, on purpose: a debug-signed public APK would be a
dead end for everyone who installed it. Debug builds (`flutter run`) are unaffected.

## 3. What the public APK does NOT contain: sherpa-onnx native code (Kokoro is a user-fetched add-on)

sherpa-onnx's C library links espeak-ng (GPL-3.0), which cannot ship inside Spike's all-rights-reserved licence.
So the APK contains **no** sherpa-onnx / ONNX Runtime / espeak-ng native library, and SpaceZ never hosts or
redistributes them. Since 1.0.3 Kokoro is an **optional add-on the user fetches themselves** (the Audacity/LAME
model): Settings > Voice > "Offline backup voice (Kokoro)" (Android only, collapsed by default, never
auto-downloads) > "Download and install".

### The Kokoro add-on (design, 4 Oct 2026)

| Part | Where it comes from | Pinned | Kept on the phone |
|---|---|---|---|
| Speech engine archive | `https://github.com/k2-fsa/sherpa-onnx/releases/download/v1.13.8/sherpa-onnx-v1.13.8-android.tar.bz2` (the upstream project's own release) | 46,093,321 bytes, SHA-256 `2ff63469a71cb6009aa2e3ed5f4a670f8abdcbe4bb9ffd23776afc792a6b4f44` (the digest GitHub publishes for the asset) | deleted after install |
| `libonnxruntime.so` (arm64-v8a, from that archive) | same | 22,249,560 bytes, SHA-256 `33847ad43bffe204699fd4a27f7f3603452a8cdaf2f9a44983a0bc31ffcf2da1` | `files/kokoro_engine/`, read-only |
| `libsherpa-onnx-c-api.so` (arm64-v8a, from that archive) | same | 4,465,168 bytes, SHA-256 `c85e2382e2ca12b0513826be926eaccfea896b4cbf568182e287671ba526f80d` | `files/kokoro_engine/`, read-only |
| Kokoro voice files | Hugging Face `csukuangfj/kokoro-multi-lang-v1_0` at a pinned revision; espeak-ng-data from the sherpa-onnx `tts-models` release (unchanged since 1.0.1, `KokoroPack` in `lib/away/voice/speaker.dart`) | per-file Hugging Face hashes | `files/kokoro/` (~380 MB) |

Total: about 426 MB to download, about 407 MB kept.

How it works:
1. Step 1, engine: `BundleDownloader` (resumable, background, progress, cancel) fetches the archive; a SHA-256
   mismatch is refused (re-fetched once, then the download fails). `KokoroEngineFiles.install()`
   (`lib/away/voice/kokoro_addon.dart`) checks the archive hash again, streams it out (bz2 -> temp tar, no
   130 MB in memory), keeps only the two arm64 libraries, checks EACH against its pinned SHA-256, chmods them
   0444, loads them once in a throw-away isolate and checks the native version is 1.13.8. Only then is
   `.engine-ready` written and the archive deleted. Any mismatch or load failure removes the whole folder and
   the card shows a friendly error; the voice chain is untouched.
2. Step 2, voice files: the existing `KokoroPack` bundle.
3. Kokoro joins the voice chain in its old place (laptop -> Gemini -> Kokoro -> Android) only when
   `KokoroPack.ready` (voice files AND engine). Cancel removes both parts (all-or-nothing); Remove deletes both.
4. Loading: the Dart side is the vendored, unmodified sherpa-onnx 1.13.8 Dart FFI bindings (Apache-2.0,
   `spike_app/third_party/sherpa_onnx_ffi/`, pure Dart, NOT the `sherpa_onnx` Flutter plugin). `loadSherpaOnnx(dir)`
   opens `libonnxruntime.so` first by absolute path (the C API library needs it by soname), then
   `libsherpa-onnx-c-api.so`. Proven on a Galaxy S23 Ultra (Android 16, targetSdk 36) on 4 Oct 2026:
   dlopen from the app's files folder works; engine 28 s, voice files 158 s on Wi-Fi, "Hello, I am Spike."
   synthesised in 2.5 s (probe: `spike_app/tool/device_probe/kokoro_addon_probe.dart`).
5. Updating the engine: bump the vendored bindings and re-pin all three hashes to the SAME release (see
   `third_party/sherpa_onnx_ffi/README.md`). The old private-build route in `spike_app/optional/kokoro_sherpa/`
   is superseded, kept for reference.

Open point for Google Play (not decided): Play's Device and Network Abuse policy forbids an app downloading
executable code (native libraries) from anywhere but Google Play. The sideloaded APK is fine; a Play build would
need the add-on hidden (`kokoroAddonSupported`) or moved to another approach.

Check after every release build (PowerShell, from spike_app):

```powershell
Add-Type -A System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::OpenRead("build\app\outputs\flutter-apk\app-release.apk").Entries |
  ? { $_.FullName -match 'sherpa|espeak|kokoro|onnxruntime' }   # must print nothing
```

A byte search finds "sherpa"/"espeak"/"onnxruntime" only inside `libapp.so` (Spike's compiled Dart: the FFI
function names it looks up, file paths and the card's text). No `.so` in the APK may contain native espeak-ng or
ONNX Runtime symbols (`espeak_Initialize`, `espeak_ng_`, `OrtGetApiBase`): checked on 1.0.3, none.

## 4. Building the public APK

```powershell
$env:PATH = "D:\flutter\bin;$env:PATH"
cd software\app\spike_app
flutter build apk --release --target-platform android-arm64
# then copy build\app\outputs\flutter-apk\app-release.apk to software\app\build_out\Spike_<x.y.z>_android_arm64.apk
```

arm64-v8a only (every phone from the last several years). The jniLibs excludes in build.gradle.kts drop the
Qualcomm NPU skeletons and the Vulkan validation layer. Version: `version:` in pubspec.yaml (x.y.z+build;
the build number must go up for every APK that should install over the previous one). Licences of what
ships: `software/app/THIRD-PARTY-NOTICES-android.md`.
