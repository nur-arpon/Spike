// Rewrites lib/core/brand.dart from brand.json (the one place for product names).
//   dart run tool/sync_brand.dart
// test/brand_test.dart fails if the two ever disagree, so a rename cannot be half-done.
import 'dart:convert';
import 'dart:io';

void main() {
  final root = File.fromUri(Platform.script).parent.parent;
  final json = jsonDecode(File('${root.path}/brand.json').readAsStringSync()) as Map<String, dynamic>;
  File('${root.path}/lib/core/brand.dart').writeAsStringSync(render(json));
  stdout.writeln('lib/core/brand.dart written from brand.json');
  final (name, build) = pubspecVersion(File('${root.path}/pubspec.yaml').readAsStringSync());
  File('${root.path}/lib/core/version.dart').writeAsStringSync(renderVersion(name, build));
  stdout.writeln('lib/core/version.dart written from pubspec.yaml ($name+$build)');
}

/// (1.0.0, 1) from the pubspec line `version: 1.0.0+1` (VERSIONING.md: the one source of truth).
(String, int) pubspecVersion(String pubspec) {
  final m = RegExp(r'^version:\s*(\d+\.\d+\.\d+)\+(\d+)\s*$', multiLine: true).firstMatch(pubspec);
  if (m == null) throw const FormatException('pubspec.yaml needs "version: MAJOR.MINOR.PATCH+BUILD"');
  return (m.group(1)!, int.parse(m.group(2)!));
}

String renderVersion(String name, int build) => '''
// GENERATED from pubspec.yaml by tool/sync_brand.dart - do not edit by hand (software/app/VERSIONING.md).
library;

/// The app's version: Settings > About shows "Version \$appVersion"; the phone and desktop apps send it
/// in their hello; the Windows package is \$appVersion.0 and Android's versionName is the same.
const appVersion = '$name';

/// The build number (Android versionCode); it goes up with every build that ships.
const appBuild = $build;
''';

String _q(Object? v) => "'${(v ?? '').toString().replaceAll(r'\', r'\\').replaceAll("'", r"\'")}'";

String render(Map<String, dynamic> j) => '''
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
  static const productName = ${_q(j['productName'])};

  /// The name in the Windows Start menu (the package's VisualElements DisplayName).
  static const startMenuName = ${_q(j['startMenuName'])};

  /// The reserved Microsoft Store name (the package's Properties DisplayName).
  static const storeName = ${_q(j['storeName'])};
  static const tagline = ${_q(j['tagline'])};
  static const publisherDisplayName = ${_q(j['publisherDisplayName'])};
  static const copyrightHolder = ${_q(j['copyrightHolder'])};

  /// The person who made the app (Settings > About "Made by ... · publisher"; the Store's "Developed by").
  static const developerName = ${_q(j['developerName'])};

  /// Empty until the owner fills them in brand.json.
  static const supportEmail = ${_q(j['supportEmail'])};
  static const websiteUrl = ${_q(j['websiteUrl'])};
  static const privacyPolicyUrl = ${_q(j['privacyPolicyUrl'])};

  /// The Google Form people join to be told when the robot body is ready ("I want one"). Empty until the
  /// owner makes the form: the robot story then offers "Follow the build" instead (features/story/).
  static const robotWaitlistUrl = ${_q(j['robotWaitlistUrl'])};

  /// PERMANENT internal id: data folders and anything that must survive a rename. Never shown,
  /// never changed (RENAMING.md "never change").
  static const internalId = ${_q(j['internalId'])};
}
''';
