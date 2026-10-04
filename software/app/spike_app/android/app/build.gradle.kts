import java.util.Properties

plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// android/key.properties: storePassword, keyPassword, keyAlias, storeFile (relative to android/app).
val releaseKeyFile = rootProject.file("key.properties")
val releaseKey = Properties().apply { if (releaseKeyFile.exists()) releaseKeyFile.inputStream().use { load(it) } }

// Fail any release build loudly when the key is missing, instead of signing with the debug key.
gradle.taskGraph.whenReady {
    val wantsRelease = allTasks.any { it.project == project && it.name.contains("Release") }
    if (wantsRelease && !releaseKeyFile.exists()) {
        throw GradleException(
            "Release build refused: android/key.properties (and the keystore it names) is missing. " +
                "Restore them from the backup (software/app/ANDROID-RELEASE.md). Never generate a new key."
        )
    }
}

android {
    // PERMANENT (software/app/ANDROID-RELEASE.md): the public app id. Never change it after release.
    namespace = "com.spacez.spike"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // PERMANENT: the Android application ID every installed copy is known by. Changing it makes a
        // different app (no updates, no data carried over). See software/app/ANDROID-RELEASE.md.
        applicationId = "com.spacez.spike"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        // the launcher label comes from brand.json, the one place for names (software/app/RENAMING.md)
        val brand = groovy.json.JsonSlurper().parse(rootProject.file("../brand.json")) as Map<*, *>
        manifestPlaceholders["appLabel"] = brand["productName"] as String
    }

    packaging {
        jniLibs {
            // v1.3 offline brain (flutter_gemma LiteRT-LM) runs on the CPU: the Qualcomm NPU DSP
            // skeletons (~45 MB) and the Vulkan validation layer (a debugging aid, 14 MB) are not needed.
            excludes += listOf("**/libQnnHtpV*Skel.so", "**/libVkLayer_khronos_validation.so")
        }
    }

    // The PERMANENT release key (software/app/ANDROID-RELEASE.md "The release signing key"). Both files are
    // gitignored and backed up outside the repo. There is NO fallback to the debug key: a release APK signed
    // with any other key could never update the copies people already have installed.
    signingConfigs {
        if (releaseKeyFile.exists()) {
            create("release") {
                keyAlias = releaseKey.getProperty("keyAlias")
                keyPassword = releaseKey.getProperty("keyPassword")
                storeFile = file(releaseKey.getProperty("storeFile"))
                storePassword = releaseKey.getProperty("storePassword")
            }
        }
    }

    buildTypes {
        release {
            if (releaseKeyFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
    }
}

// The public APK is arm64-v8a only (`flutter build apk --release --target-platform android-arm64`). The plugins'
// own native libraries for armeabi-v7a, x86 and x86_64 would otherwise still ship (~20 MB), and a 32-bit phone
// would install an APK with no libflutter.so for it and crash on start. Release only: debug builds keep every ABI
// (emulators). `ndk.abiFilters` does not work here: the Flutter plugin's own ABI list is merged with it.
androidComponents {
    onVariants(selector().withBuildType("release")) { variant ->
        variant.packaging.jniLibs.excludes.addAll(listOf("lib/armeabi-v7a/**", "lib/x86/**", "lib/x86_64/**"))
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
