/// Deterministic commands, handled before (and instead of) the language model.
/// Port of `spike_brain/mind/intents.py` with the same regexes, so a command
/// said to the phone brain does exactly what it does at home. One difference,
/// by design: alarms and reminders live on the laptop brain (it rings them when
/// the phone is off), so away they are recognised and answered with a friendly
/// "at home" line (intent `timers_away`) instead of being set.
library;

import '../../core/capabilities.dart';

class Intent {
  const Intent(this.name, [this.slots = const {}]);
  final String name;
  final Map<String, Object?> slots;
  @override
  String toString() => 'Intent($name, $slots)';
}

String _clean(String? text) {
  var t = (text ?? '').toLowerCase().replaceAll('’', "'");
  t = t.replaceAll(RegExp(r"[^a-z0-9':. ]+"), ' ');
  t = t.replaceAll(RegExp(r'\s+'), ' ');
  return t.replaceAll(RegExp(r'^[ .]+|[ .]+$'), '');
}

/// Trick word -> action (mostly face_v2, until the legs have their own sit etc.; "walk" and
/// "paw" are the phone-only Spike's own face/animation reactions here - away from home there
/// is no real robot body to move, PROTOCOL.md 5.2's v1.4 body actions are laptop<->robot only).
const tricks = {
  'sit': 'playBow', 'sit down': 'playBow', 'lie down': 'napping', 'bow': 'playBow', 'spin': 'zoomies',
  'roll over': 'rollOver', 'play dead': 'fallAsleep', 'dance': 'tailWagDance', 'beg': 'beggingAction',
  'sneeze': 'sneeze', 'wag': 'tailWagDance', 'zoomies': 'zoomies', 'stretch': 'playBow',
  'yawn': 'yawn', 'high five': 'beggingAction',
  'shake': 'paw', 'paw': 'paw', 'give paw': 'paw',
  'walk': 'walk', 'walk forward': 'walk', 'come here': 'walk',
};

final RegExp _trickRe = () {
  final words = tricks.keys.toList()..sort((a, b) => b.length.compareTo(a.length));
  return RegExp(r'^(?:can you |will you |please |now |go on |ok |okay )*(?:do a |do the )?'
      '(${words.map(RegExp.escape).join('|')})'
      r'(?: for me)?(?: please| now)?$');
}();

Intent? matchIntent(String text, Map<String, String> names,
    {bool inRps = false, bool confirmingForgetAll = false}) {
  final t = _clean(text);
  if (t.isEmpty) return null;
  final dog = (names['dog'] ?? 'spike').toLowerCase();
  final cat = (names['cat'] ?? 'spicy').toLowerCase();
  final words = t.split(' ');
  bool has(String p) => RegExp(p).hasMatch(t);
  bool full(String p) => RegExp('^(?:$p)\$').hasMatch(t);

  if (confirmingForgetAll) {
    if (has(r"\b(yes|yeah|yep|do it|forget everything|i'm sure|i am sure|sure)\b") &&
        !has(r"\b(no|don't|do not|wait|cancel|never ?mind)\b")) {
      return const Intent('forget_all_confirmed');
    }
    return const Intent('forget_all_cancelled');
  }

  if (inRps) {
    final m = RegExp(r'\b(rock|paper|scissors?|stone)\b').firstMatch(t);
    if (m != null) {
      final c = {'stone': 'rock', 'scissor': 'scissors'}[m.group(1)] ?? m.group(1)!;
      return Intent('rps_choice', {'choice': c});
    }
    if (has(r"\b(stop|quit|enough|no more|i'm done)\b")) return const Intent('rps_stop');
  }

  // --- mode switching
  final c = RegExp.escape(cat), d = RegExp.escape(dog);
  if (has('\\b(cat mode|be (a )?cat|turn into (a )?cat|become (a )?cat|kitty mode|'
      'switch to (the )?cat|$c mode|be $c|switch to $c|i want $c)\\b')) {
    return const Intent('set_mode', {'mode': 'cat'});
  }
  if (has('\\b(dog mode|puppy mode|be (a )?dog|turn (back )?into (a )?dog|become (a )?dog|'
      'switch to (the )?dog|$d mode|be $d|switch to $d|i want $d|come back $d)\\b')) {
    return const Intent('set_mode', {'mode': 'dog'});
  }

  // --- stop talking
  if (words.length <= 4 &&
      full(r"(ok |okay |please )?(stop|shush|shh+|hush|quiet|be quiet|stop talking|enough|that's enough|never ?mind)( please)?")) {
    return const Intent('stop');
  }

  // --- memory
  if (has(r'\b(forget everything|wipe (your|my) memory|erase (your|my) memory|'
      r'delete (all )?(your|my) memor(y|ies)|forget all about me)\b')) {
    return const Intent('forget_all');
  }
  if (full(r"(please |ok |okay )?(forget|forget that|forget it|forget what i (just )?said|"
      r"don't remember that|scratch that)( please)?")) {
    return const Intent('forget_last');
  }
  var m = RegExp(r'^(?:please |ok |okay )?forget (?:about |that )?(.{3,})$').firstMatch(t);
  if (m != null && !m.group(1)!.startsWith('it ') && !m.group(1)!.startsWith('everything')) {
    return Intent('forget_about', {'what': m.group(1)});
  }
  if (has(r'\bwhat do you (know|remember) about me\b|\bwhat have you remembered\b')) {
    return const Intent('recall_all');
  }
  m = RegExp(r"^(?:please |ok |okay |hey )?(?:remember|don't forget|note) (?:that )?(.{3,})$").firstMatch(t);
  if (m != null && !RegExp(r'^(when|what|how|the time|me\b)').hasMatch(m.group(1)!)) {
    return Intent('remember', {'fact': _restoreCase(text, m.group(1)!)});
  }

  // --- alarms and reminders: the laptop brain keeps them (see the library comment)
  if (has(r'\b(cancel|delete|remove|turn off|clear) (the |my |all )?(alarms?|reminders?)\b') ||
      has(r'\b(what|which|any) (alarms|reminders)\b|\b(list|tell me) (my )?(alarms|reminders)\b|'
          r'\bdo i have any (alarms|reminders)\b') ||
      has(r'\b(wake me( up)?|set (an |the |my )?alarm|alarm (for|at)|get me up)\b') ||
      has(r'\bremind me\b') ||
      has(r'\b(set a |start a )?timer for\b')) {
    return const Intent('timers_away');
  }

  // --- time
  if (has(r"\bwhat('s| is) the time\b|\bwhat time is it\b|\bgot the time\b")) return const Intent('tell_time');
  if (has(r"\bwhat('s| is) (the date|today's date)\b|\bwhat day is (it|today)\b")) return const Intent('tell_date');

  // --- games and tricks
  if (has(r"\brock,? paper,? scissors?\b|\bplay (a game of )?(rps|rock)\b|\blet'?s play\b")) {
    return const Intent('rps_start');
  }
  m = _trickRe.firstMatch(t);
  if (m != null) {
    // core/capabilities.dart: a trick the body cannot do gets a friendly "not yet" instead
    if (!isAvailable(tricks[m.group(1)])) return Intent('trick_unavailable', {'trick': m.group(1)});
    return Intent('trick', {'trick': m.group(1), 'action': tricks[m.group(1)]});
  }
  if (full(r'(do a trick|show me a trick|do something cool|do a trick for me)( please)?')) {
    return const Intent('trick', {'trick': 'random', 'action': null});
  }
  if (full(r'(go to sleep|go to bed|take a nap|time for bed|goodnight|good night|nap time|'
      r'sleep)( now)?( (spike|spicy|buddy))?')) {
    return const Intent('sleep');
  }
  return null;
}

String _restoreCase(String original, String loweredPart) {
  final idx = original.toLowerCase().replaceAll('’', "'").indexOf(loweredPart);
  return idx >= 0 ? original.substring(idx, idx + loweredPart.length) : loweredPart;
}

/// "7:30 am", "tomorrow at 7 am" (life/timeparse.py say_time).
String sayTime(DateTime dt, [DateTime? now]) {
  final h12 = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
  final clock = dt.minute != 0 ? '$h12:${dt.minute.toString().padLeft(2, '0')}' : '$h12';
  var s = '$clock ${dt.hour < 12 ? 'am' : 'pm'}';
  if (now != null) {
    final days = DateTime(dt.year, dt.month, dt.day).difference(DateTime(now.year, now.month, now.day)).inDays;
    if (days == 1) {
      s = 'tomorrow at $s';
    } else if (days > 1) {
      const wd = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
      s = '${wd[dt.weekday - 1]} at $s';
    }
  }
  return s;
}
