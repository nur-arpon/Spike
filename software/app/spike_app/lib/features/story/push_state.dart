/// What the robot push remembers on the phone (and nothing else, nothing leaves it):
///  * which "imagine this on your desk" peeks were already shown (each feature once, ever), and
///  * when the last 3-day reminder was shown.
/// Stored in the app's own preferences under the `spike.push.*` keys (never rename them, a rename
/// would show everyone every peek again). Also home of the waitlist link logic and the one function
/// that opens it.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/brand.dart';
import '../../state/settings.dart';
import 'push_copy.dart';

const _kPeeked = 'spike.push.peeked';
const _kReminderAt = 'spike.push.reminderAt';
const _kFirstSeen = 'spike.push.firstSeen';

/// How long between two reminders.
const reminderEvery = Duration(days: 3);

/// The reminder is due when [reminderEvery] has passed since [last] (the last reminder, or the first
/// time the app was opened, so a brand-new user is never nagged on day one).
bool reminderDue(DateTime? last, DateTime now) => last != null && now.difference(last) >= reminderEvery;

@immutable
class PushState {
  const PushState({this.peeked = const {}, this.reminderAt, this.firstSeen});
  final Set<String> peeked;
  final DateTime? reminderAt;
  final DateTime? firstSeen;

  /// The moment the next reminder counts from.
  DateTime? get since => reminderAt ?? firstSeen;
}

/// Tests replace this to control "now".
final pushClockProvider = Provider<DateTime Function()>((_) => DateTime.now);

final pushProvider = NotifierProvider<PushNotifier, PushState>(PushNotifier.new);

class PushNotifier extends Notifier<PushState> {
  SharedPreferences get _prefs => ref.read(prefsProvider);

  @override
  PushState build() {
    final p = _prefs;
    DateTime? at(String k) {
      final v = p.getInt(k);
      return v == null ? null : DateTime.fromMillisecondsSinceEpoch(v);
    }

    return PushState(peeked: (p.getStringList(_kPeeked) ?? const []).toSet(), reminderAt: at(_kReminderAt), firstSeen: at(_kFirstSeen));
  }

  /// True the first time [feature] is asked about, and remembers it: each peek is shown once, ever.
  bool takePeek(PeekFeature feature) {
    if (state.peeked.contains(feature.name)) return false;
    final next = {...state.peeked, feature.name};
    _prefs.setStringList(_kPeeked, next.toList());
    state = PushState(peeked: next, reminderAt: state.reminderAt, firstSeen: state.firstSeen);
    return true;
  }

  /// Called on app open: true when the 3-day reminder should show now. The very first open only starts
  /// the clock (the banner already says it all on day one).
  bool takeReminder() {
    final now = ref.read(pushClockProvider)();
    if (state.since == null) {
      _prefs.setInt(_kFirstSeen, now.millisecondsSinceEpoch);
      state = PushState(peeked: state.peeked, firstSeen: now);
      return false;
    }
    if (!reminderDue(state.since, now)) return false;
    _prefs.setInt(_kReminderAt, now.millisecondsSinceEpoch);
    state = PushState(peeked: state.peeked, reminderAt: now, firstSeen: state.firstSeen);
    return true;
  }
}

// ---------------------------------------------------------------- the waitlist link

/// The Google Form link from brand.json; tests override it.
final waitlistUrlProvider = Provider<String>((_) => AppBrand.robotWaitlistUrl);

/// How a link is opened (the external browser); tests override it to record instead of launching.
final urlOpenerProvider = Provider<Future<bool> Function(Uri)>(
  (_) => (u) => launchUrl(u, mode: LaunchMode.externalApplication),
);

/// A usable waitlist link, or null while there is none (empty or not an https address).
Uri? waitlistUri(String raw) {
  final u = Uri.tryParse(raw.trim());
  return u != null && u.scheme == 'https' && u.host.isNotEmpty ? u : null;
}

/// What the main button says and opens right now.
({String label, Uri uri, bool waitlist, String note}) ctaFor(String waitlistUrl) {
  final w = waitlistUri(waitlistUrl);
  return w != null
      ? (label: ctaWaitlist, uri: w, waitlist: true, note: ctaNote)
      : (label: ctaFollow, uri: Uri.parse(robotPageUrl), waitlist: false, note: ctaNoteFollow);
}
