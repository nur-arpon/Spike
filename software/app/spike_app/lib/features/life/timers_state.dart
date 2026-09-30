/// Alarm and reminder helpers.
///
/// The list itself comes from the brain (protocol v1.2 `timers`, see
/// `timersProvider` in state/link.dart). These words are only for a brain
/// older than v1.2, which understands alarms only as speech
/// (spike_brain/mind/intents.py).
library;

String spokenTime(DateTime at, DateTime now) {
  final h12 = at.hour % 12 == 0 ? 12 : at.hour % 12;
  final mm = at.minute.toString().padLeft(2, '0');
  final ampm = at.hour < 12 ? 'am' : 'pm';
  final today = at.year == now.year && at.month == now.month && at.day == now.day;
  final tomorrow = !today && at.difference(DateTime(now.year, now.month, now.day)).inDays == 1;
  final day = today ? '' : (tomorrow ? ' tomorrow' : '');
  return '$h12:$mm $ampm$day';
}

String alarmCommand(DateTime at, DateTime now) => 'set an alarm for ${spokenTime(at, now)}';
String reminderCommand(String what, DateTime at, DateTime now) => 'remind me to $what at ${spokenTime(at, now)}';

/// "Today", "Tomorrow" or the weekday, for a due time.
String dayLabel(DateTime at, DateTime now) {
  final d0 = DateTime(now.year, now.month, now.day);
  final d1 = DateTime(at.year, at.month, at.day);
  final days = d1.difference(d0).inDays;
  if (days <= 0) return 'Today';
  if (days == 1) return 'Tomorrow';
  const names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  return days < 7 ? names[at.weekday - 1] : '${at.day}/${at.month}';
}

/// The next time [t] o'clock comes round (today if still ahead, else tomorrow).
DateTime nextAt(int hour, int minute, DateTime now) {
  var at = DateTime(now.year, now.month, now.day, hour, minute);
  if (!at.isAfter(now)) at = at.add(const Duration(days: 1));
  return at;
}
