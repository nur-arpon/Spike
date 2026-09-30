# Renaming the product (or the publisher)

Every name a customer sees lives in ONE place per codebase. The characters' names (Spike the dog, Spicy the cat)
are NOT product names: they are the owner's to edit in the app (Settings > Names) and live in the brain's personas.
Renaming the product never touches them, and renaming a character never touches the product.

## The one places

| Codebase | File | What it holds |
|---|---|---|
| Flutter app (phone + desktop), Windows package, Android label, Store kit | `spike_app/brand.json` | productName, startMenuName, storeName, tagline, publisherDisplayName, copyrightHolder, supportEmail, websiteUrl, privacyPolicyUrl, internalId |
| Laptop brain | `software/laptop/spike_brain/config/default.toml`, section `[brand]` (`product_name`) | the name in the pairing text and logs |
| Microsoft Store identity (invisible, permanent) | `spike_app/windows/packaging/identity.json` | Package/Identity/Name and Publisher, copied from Partner Center |

Everything else reads these:

- `lib/core/brand.dart` (class `AppBrand`) is generated from brand.json by `dart run tool/sync_brand.dart`.
- The Windows exe's file description, product name and copyright (Runner.rc) come from brand.json through CMake.
- The MSIX manifest's DisplayName, PublisherDisplayName and Start menu name are filled from brand.json by
  `windows/packaging/build_msix.ps1`.
- The Android launcher label is `${appLabel}`, set from brand.json in `android/app/build.gradle.kts`.
- The Store kit (`software/app/store/`) is rendered from `store/templates/` by `store/render_store_kit.ps1`.

## Checklist

1. Edit `spike_app/brand.json` (product, Store and publisher names, support/website/privacy URLs).
2. `cd spike_app` and `dart run tool/sync_brand.dart` (rewrites lib/core/brand.dart and lib/core/version.dart).
3. Edit `[brand] product_name` in `software/laptop/spike_brain/config/default.toml`, then copy the file to
   `spike_app/assets/brain/default.toml` (a test fails if the two differ).
4. `powershell -File software/app/store/render_store_kit.ps1` (re-renders the Store texts and the privacy policy).
5. `flutter test` (the brand tests fail if brand.dart is stale or a name is hard-coded anywhere in lib/) and
   `python -m pytest` in software/laptop.
6. Rebuild: `flutter build apk`, `windows/packaging/build_msix.ps1`, `software/laptop/desktop_build/build_brain.ps1`.
7. In Partner Center: reserve the new name (Product management > Manage app names), and use it in the listing.
   The publisher display name must match the Partner Center account's display name.
8. Store screenshots show the product name in the sidebar: retake them (`spike_app/tool/shoot.ps1`).

## Never rename (permanent identifiers)

Listed in `DESIGN.md` > Desktop > PERMANENT identifiers: the MSIX Package/Identity Name and Publisher, the Android
applicationId `com.spikebuddy.spike_app`, the internal id `spikebuddy` (data folders, the single-instance mutex,
the `spikebuddy/desktop` channel), the Windows app-data folder `com.spikebuddy\spike_app`, the stored-key names
`spike.ai.<provider>.key` and the other `spike.*` preference keys, and the StartupTask id `SpikeStartup`.
Changing any of them would make the Store treat it as a different app, or lose every user's saved settings and keys.
