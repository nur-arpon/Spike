// GENERATED from brand.json by tool/sync_brand.dart - do not edit by hand (software/app/RENAMING.md).
//
// Every user-visible PRODUCT, store and publisher name the app shows comes from here: window title,
// tray tooltip and menu, About, notifications, the Store/privacy texts. The characters' names
// (Spike and Spicy) are separate: the owner renames them in Settings (AppSettings.dogName/catName).
library;

/// (Named AppBrand because core/theme.dart's Brand holds the brand COLOURS.)
class AppBrand {
  const AppBrand._();

  /// The app's short name (window title, tray, taskbar, About). Also the Android launcher label.
  static const productName = 'Spike';

  /// The name in the Windows Start menu (the package's VisualElements DisplayName).
  static const startMenuName = 'Spike';

  /// The reserved Microsoft Store name (the package's Properties DisplayName).
  static const storeName = 'Spike - your personal desktop companion';
  static const tagline = 'your personal desktop companion';
  static const publisherDisplayName = 'SpaceZ';
  static const copyrightHolder = 'Nur Ifran Arpon';

  /// The person who made the app (Settings > About "Made by ... · publisher"; the Store's "Developed by").
  static const developerName = 'Nur Ifran Arpon';

  /// Empty until the owner fills them in brand.json.
  static const supportEmail = '';
  static const websiteUrl = 'https://github.com/nur-arpon/Spike';
  static const privacyPolicyUrl = 'https://nur-arpon.github.io/Spike/privacy-policy.html';

  /// PERMANENT internal id: data folders and anything that must survive a rename. Never shown,
  /// never changed (RENAMING.md "never change").
  static const internalId = 'spikebuddy';
}
