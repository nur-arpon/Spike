/// The phone brain's memory: what the owner told Spike while away, kept ONLY
/// on this phone (a private file in the app's storage), with the same privacy
/// controls as the laptop: the Memories list and forget one / forget
/// everything. Facts come from the same rules as the laptop brain
/// (`memory/extract.py extract_rules`, ported below with its SENSITIVE filter:
/// health, sexuality, religion, money, passwords and crisis talk are never
/// stored). The laptop's optional language-model extraction is NOT used away:
/// it would send extra words to the cloud model.
library;

import 'dart:convert';
import 'dart:io';

class Fact {
  Fact({required this.id, required this.kind, required this.text, this.subject, this.due, required this.at, this.uses = 0});
  final int id;
  String kind;
  String text;
  final String? subject;
  String? due;
  int at; // Unix seconds (updated)
  int uses;

  Map<String, Object?> toJson() =>
      {'id': id, 'kind': kind, 'text': text, 'subject': subject, 'due': due, 'at': at, 'uses': uses};
  static Fact? fromJson(Object? o) {
    if (o is! Map || o['id'] is! int || o['text'] is! String) return null;
    return Fact(
      id: o['id'] as int, kind: (o['kind'] ?? 'fact').toString(), text: o['text'] as String,
      subject: o['subject'] as String?, due: o['due'] as String?, at: (o['at'] as num?)?.toInt() ?? 0,
      uses: (o['uses'] as num?)?.toInt() ?? 0,
    );
  }
}

const factKinds = ['fact', 'preference', 'birthday', 'commitment', 'person', 'name'];

/// Stores facts and a few timestamped events (crisis_moment, people_nudge...: never words).
class PhoneMemory {
  PhoneMemory({this.file, int Function()? clock}) : _clock = clock ?? (() => DateTime.now().millisecondsSinceEpoch ~/ 1000);
  final File? file; // null = in memory only (tests)
  final int Function() _clock;
  final List<Fact> _facts = [];
  final Map<String, List<int>> _events = {};
  int _nextId = 1;
  List<int> lastIds = [];

  Future<void> load() async {
    final f = file;
    if (f == null || !await f.exists()) return;
    try {
      final d = jsonDecode(await f.readAsString()) as Map<String, dynamic>;
      _facts
        ..clear()
        ..addAll([for (final o in (d['facts'] as List? ?? const [])) ?Fact.fromJson(o)]);
      _events.clear();
      (d['events'] as Map? ?? const {}).forEach((k, v) => _events[k as String] = [for (final t in v as List) (t as num).toInt()]);
      _nextId = (d['next_id'] as int?) ?? (_facts.fold<int>(0, (a, f) => f.id > a ? f.id : a) + 1);
    } catch (_) {
      // a damaged file is not fatal: start empty (the owner can't lose more than the file had)
    }
  }

  Future<void> _save() async {
    final f = file;
    if (f == null) return;
    await f.parent.create(recursive: true);
    final tmp = File('${f.path}.tmp');
    await tmp.writeAsString(jsonEncode({
      'facts': [for (final x in _facts) x.toJson()],
      'events': _events,
      'next_id': _nextId,
    }));
    await tmp.rename(f.path);
  }

  List<Fact> get all => List.unmodifiable(_facts.reversed); // newest first
  int get total => _facts.length;

  static String _norm(String t) => t.toLowerCase().replaceAll(RegExp(r'[^a-z0-9 ]'), ' ').replaceAll(RegExp(r'\s+'), ' ').trim();

  /// Same `subject` replaces the old value; the same text updates it.
  Future<int> remember(String text, {String kind = 'fact', String? subject, String? due}) async {
    text = text.trim().replaceAll(RegExp(r'\s+'), ' ').replaceAll(RegExp(r'^[ .]+|[ .]+$'), '');
    if (text.isEmpty) throw ArgumentError('empty memory');
    if (!factKinds.contains(kind)) kind = 'fact';
    Fact? row;
    if (subject != null) row = _facts.where((f) => f.subject == subject).firstOrNull;
    row ??= _facts.where((f) => _norm(f.text) == _norm(text)).firstOrNull;
    if (row != null) {
      row
        ..text = text
        ..kind = kind
        ..due = due ?? row.due
        ..at = _clock();
      _facts
        ..remove(row)
        ..add(row);
    } else {
      row = Fact(id: _nextId++, kind: kind, text: text, subject: subject, due: due, at: _clock());
      _facts.add(row);
    }
    await _save();
    return row.id;
  }

  Future<bool> forget(int id) async {
    final before = _facts.length;
    _facts.removeWhere((f) => f.id == id);
    if (_facts.length == before) return false;
    await _save();
    return true;
  }

  Future<List<String>> forgetLast() async {
    final gone = <String>[];
    for (final id in lastIds) {
      final f = _facts.where((x) => x.id == id).firstOrNull;
      if (f != null && await forget(id)) gone.add(f.text);
    }
    lastIds = [];
    return gone;
  }

  static String _stripPronouns(String text) => text
      .toLowerCase()
      .replaceAll(RegExp(r"\b(i|my|me|that|the|owner'?s?|likes?|loves?)\b"), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();

  /// "Forget that I like pizza": delete the closest fact (token overlap), or null.
  Future<String?> forgetMatching(String query) async {
    final q = _stripPronouns(query).split(' ').where((w) => w.length > 1).toSet();
    if (q.isEmpty) return null;
    Fact? best;
    var score = 0.0;
    for (final f in _facts) {
      final w = _stripPronouns(f.text).split(' ').where((x) => x.length > 1).toSet();
      if (w.isEmpty) continue;
      final s = q.intersection(w).length / q.length;
      if (s > score) {
        best = f;
        score = s;
      }
    }
    if (best != null && score >= 0.6 && await forget(best.id)) return best.text;
    return null;
  }

  /// Forget everything personal (facts and events).
  Future<void> wipe() async {
    _facts.clear();
    _events.clear();
    lastIds = [];
    await _save();
  }

  String? ownerName() {
    final r = _facts.where((f) => f.subject == 'owner_name').firstOrNull;
    if (r == null) return null;
    final m = RegExp(r'name is (.+)$', caseSensitive: false).firstMatch(r.text);
    return (m != null ? m.group(1)! : r.text).replaceAll(RegExp(r'^[ .]+|[ .]+$'), '');
  }

  List<String> recallAll([int limit = 12]) => [for (final f in all.take(limit)) f.text];

  /// Lines of memory for the prompt: the name, facts sharing words with what was said,
  /// the top preferences - within [budget] characters.
  List<String> contextFor(String query, {int budget = 900}) {
    final lines = <String>[];
    final used = <int>{};
    final name = ownerName();
    if (name != null) lines.add("The owner's name is $name.");
    final terms = RegExp(r"[a-z0-9']+").allMatches(query.toLowerCase()).map((m) => m.group(0)!).where((w) => w.length > 3).toSet();
    for (final f in all) {
      if (f.subject == 'owner_name' || used.contains(f.id)) continue;
      final words = RegExp(r"[a-z0-9']+").allMatches(f.text.toLowerCase()).map((m) => m.group(0)!).toSet();
      if (terms.intersection(words).isNotEmpty) {
        lines.add('${f.text}.');
        used.add(f.id);
      }
    }
    for (final f in all.where((f) => f.kind == 'preference').take(3)) {
      if (!used.contains(f.id)) {
        lines.add('${f.text}.');
        used.add(f.id);
      }
    }
    final out = <String>[];
    var size = 0;
    for (final l in lines) {
      if (size + l.length > budget) break;
      out.add(l);
      size += l.length + 1;
    }
    return out;
  }

  Future<void> logEvent(String kind) async {
    (_events[kind] ??= []).add(_clock());
    if (_events[kind]!.length > 50) _events[kind]!.removeAt(0);
    await _save();
  }

  int? lastEvent(String kind) {
    final l = _events[kind];
    return (l == null || l.isEmpty) ? null : l.last;
  }
}

// ------------------------------------------------------------------ extract.py (rules)

class Extracted {
  const Extracted(this.kind, this.text, {this.subject, this.due});
  final String kind;
  final String text;
  final String? subject;
  final String? due;
  @override
  String toString() => 'Extracted($kind, $text, $subject, $due)';
}

const _monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', //
  'September', 'October', 'November', 'December',
];
final Map<String, int> _months = () {
  final m = <String, int>{};
  for (var i = 0; i < 12; i++) {
    m[_monthNames[i].toLowerCase()] = i + 1;
  }
  for (final e in m.entries.toList()) {
    m[e.key.substring(0, 3)] = e.value;
  }
  m['sept'] = 9;
  return m;
}();
const _ord = {
  'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, //
  'eighth': 8, 'ninth': 9, 'tenth': 10, 'eleventh': 11, 'twelfth': 12, 'thirteenth': 13,
  'fourteenth': 14, 'fifteenth': 15, 'sixteenth': 16, 'seventeenth': 17, 'eighteenth': 18,
  'nineteenth': 19, 'twentieth': 20, 'thirtieth': 30,
};
const _notNames = {
  'not', 'just', 'a', 'the', 'and', 'but', 'so', 'i', 'im', 'really', 'very', 'too', 'also', //
  'going', 'gonna', 'here', 'back', 'home', 'sad', 'tired', 'fine', 'ok', 'okay',
};

final sensitive = RegExp(
    r'\b(password|pin|bank|account number|credit card|card number|salary|debt|diagnos\w*|'
    r'medication|meds|pills|depress\w*|anxiety|disorder|illness|disease|cancer|hiv|pregnan\w*|'
    r'sex\w*|gay|lesbian|bisexual|religio\w*|suicid\w*|self harm|kill myself)\b',
    caseSensitive: false);

/// "March 3rd" / "3rd of March" / "the third of march" / "3/3" -> "MM-DD".
String? parseDayMonth(String text) {
  var t = text.toLowerCase();
  for (final e in _ord.entries) {
    if (e.value < 10) t = t.replaceAll(RegExp('\\btwenty[- ]${e.key}\\b'), '${20 + e.value}');
    t = t.replaceAll(RegExp('\\b${e.key}\\b'), '${e.value}');
  }
  t = t.replaceAllMapped(RegExp(r'(\d+)(st|nd|rd|th)\b'), (m) => m.group(1)!);
  final keys = _months.keys.toList()..sort((a, b) => b.length.compareTo(a.length));
  final mon = keys.join('|');
  int d, mo;
  var m = RegExp('\\b(\\d{1,2}) (?:of )?($mon)\\b').firstMatch(t);
  if (m != null) {
    d = int.parse(m.group(1)!);
    mo = _months[m.group(2)]!;
  } else {
    m = RegExp('\\b($mon) (?:the )?(\\d{1,2})\\b').firstMatch(t);
    if (m != null) {
      mo = _months[m.group(1)]!;
      d = int.parse(m.group(2)!);
    } else {
      m = RegExp(r'\b(\d{1,2})/(\d{1,2})\b').firstMatch(t); // Australian order: day/month
      if (m == null) return null;
      d = int.parse(m.group(1)!);
      mo = int.parse(m.group(2)!);
    }
  }
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  return '${mo.toString().padLeft(2, '0')}-${d.toString().padLeft(2, '0')}';
}

const _rel = r'(mum|mom|mother|dad|father|sister|brother|wife|husband|partner|girlfriend|boyfriend|son|daughter|'
    r'friend|best friend|grandma|grandmother|nan|nanna|grandpa|grandfather|boss|cousin|aunt|uncle|dog|cat)';

String _case(String original, String lowered) {
  final i = original.toLowerCase().indexOf(lowered);
  return i >= 0 ? original.substring(i, i + lowered.length) : lowered;
}

String _title(String s) => s.split(' ').map((w) => w.isEmpty ? w : w[0].toUpperCase() + w.substring(1).toLowerCase()).join(' ');

String _sayMd(String due) {
  final p = due.split('-').map(int.parse).toList();
  return '${p[1]} ${_monthNames[p[0] - 1]}';
}

String _youToThey(String text) {
  const swaps = {'my': 'their', 'me': 'them', 'i': 'they', 'myself': 'themselves', 'mine': 'theirs'};
  return text.split(' ').map((w) => swaps[w] ?? w).join(' ');
}

String? _dueFrom(String phrase, DateTime now) {
  final p = phrase.toLowerCase();
  String iso(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
  final today = DateTime(now.year, now.month, now.day);
  if (p == 'today' || p == 'tonight') return iso(today);
  if (p == 'tomorrow') return iso(today.add(const Duration(days: 1)));
  const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
  for (var i = 0; i < 7; i++) {
    if (p.contains(days[i])) {
      var ahead = (i - (now.weekday - 1)) % 7;
      if (ahead == 0) ahead = 7;
      return iso(today.add(Duration(days: ahead)));
    }
  }
  return null;
}

/// Facts from one utterance, by pattern. [] for questions and sensitive topics.
List<Extracted> extractRules(String text, DateTime now) {
  final raw = text.trim();
  final t = raw.toLowerCase().replaceAll('’', "'");
  if (t.isEmpty || sensitive.hasMatch(t)) return const [];
  final out = <Extracted>[];

  var m = RegExp(r"\b(?:my name is|my name's|i'm called|call me|i am called)\s+([a-z][a-z'-]+)").firstMatch(t);
  if (m != null && !_notNames.contains(m.group(1))) {
    var name = _case(raw, m.group(1)!);
    name = name[0].toUpperCase() + name.substring(1);
    final nxt = RegExp(r"^\s+([A-Z][a-z'-]+)\b").firstMatch(raw.substring(m.end));
    if (nxt != null && !_notNames.contains(nxt.group(1)!.toLowerCase())) name += ' ${nxt.group(1)}';
    out.add(Extracted('name', "The owner's name is $name", subject: 'owner_name'));
  }

  m = RegExp(r'\bmy birthday is (?:on )?(.+)$').firstMatch(t);
  if (m != null) {
    final due = parseDayMonth(m.group(1)!);
    if (due != null) {
      out.add(Extracted('birthday', "The owner's birthday is on ${_sayMd(due)}", subject: 'birthday:owner', due: due));
    }
  }
  m = RegExp("\\bmy $_rel(?:'s| )?\\s*([a-z]+)?(?:'s)? birthday is (?:on )?(.+)\$").firstMatch(t);
  if (m != null) {
    final due = parseDayMonth(m.group(3)!);
    if (due != null) {
      final who = 'their ${m.group(1)}${m.group(2) != null ? ' ${_title(_case(raw, m.group(2)!))}' : ''}';
      out.add(Extracted('birthday', 'Birthday of $who is on ${_sayMd(due)}',
          subject: 'birthday:${m.group(1)}:${m.group(2) ?? ''}', due: due));
    }
  }
  m = RegExp(r"\b([a-z]+)'s birthday is (?:on )?(.+)$").firstMatch(t);
  if (m != null &&
      !const ['my', 'your', 'his', 'her', 'their', 'mum', 'mom', 'dad'].contains(m.group(1)) &&
      !out.any((e) => e.kind == 'birthday')) {
    final due = parseDayMonth(m.group(2)!);
    if (due != null) {
      final who = _title(_case(raw, m.group(1)!));
      out.add(Extracted('birthday', "$who's birthday is on ${_sayMd(due)}", subject: 'birthday:${m.group(1)}', due: due));
    }
  }

  if (!t.endsWith('?')) {
    m = RegExp(r"\bi (?:really |absolutely |just )?(love|like|enjoy|adore) ([a-z][a-z '-]{2,40}?)(?:[.!,]|$| so| a lot| very)")
        .firstMatch(t);
    if (m != null && !RegExp(r'^(you|it|that|this|him|her|them|to be|being)\b').hasMatch(m.group(2)!)) {
      out.add(Extracted('preference', 'The owner ${m.group(1)}s ${_case(raw, m.group(2)!.trim())}'));
    }
    m = RegExp(r"\bi (hate|dislike|can't stand|don't like) ([a-z][a-z '-]{2,40}?)(?:[.!,]|$| so| a lot)").firstMatch(t);
    if (m != null && !RegExp(r'^(you|it|that|this|him|her|them|my life|myself)\b').hasMatch(m.group(2)!)) {
      final verb = {'hate': 'hates', 'dislike': 'dislikes', "can't stand": "can't stand", "don't like": "doesn't like"}[m.group(1)]!;
      out.add(Extracted('preference', 'The owner $verb ${_case(raw, m.group(2)!.trim())}'));
    }
    m = RegExp(r"\bmy fav(?:ou?)?rite ([a-z ]{2,20}?) is ([a-z0-9][a-z0-9 '-]{1,40}?)(?:[.!,]|$)").firstMatch(t);
    if (m != null) {
      out.add(Extracted('preference', "The owner's favourite ${m.group(1)!.trim()} is ${m.group(2)!.trim()}",
          subject: 'favourite:${m.group(1)!.trim()}'));
    }
    m = RegExp('\\bi have an? $_rel (?:called|named) ([a-z]+)').firstMatch(t);
    if (m != null) {
      out.add(Extracted('person', 'The owner has a ${m.group(1)} called ${_title(_case(raw, m.group(2)!))}',
          subject: 'person:${m.group(1)}:${m.group(2)}'));
    }
    m = RegExp(r"\bi (work|study) (at|as|in) ([a-z0-9][a-z0-9 &'-]{1,40}?)(?:[.!,]|$)").firstMatch(t);
    if (m != null) {
      out.add(Extracted('fact', 'The owner ${m.group(1)}s ${m.group(2)} ${m.group(3)!.trim()}', subject: m.group(1)));
    }
    m = RegExp(r"\bi live in ([a-z][a-z '-]{1,40}?)(?:[.!,]|$)").firstMatch(t);
    if (m != null) {
      out.add(Extracted('fact', 'The owner lives in ${_title(_case(raw, m.group(1)!))}', subject: 'home'));
    }
    m = RegExp(r"\bi(?:'ll| will|'m going to| am going to|'m gonna| am gonna| have to| need to| must) "
            r"([a-z][a-z0-9 '-]{3,60}?)(?: (tomorrow|tonight|today|on (?:monday|tuesday|wednesday|thursday|"
            r'friday|saturday|sunday)|next week|this weekend))(?:[.!,]|$)')
        .firstMatch(t);
    if (m != null && !RegExp(r'^(be|go to (sleep|bed)|die|kill|hurt)\b').hasMatch(m.group(1)!)) {
      out.add(Extracted('commitment', 'The owner said they will ${_youToThey(m.group(1)!)} ${m.group(2)}',
          due: _dueFrom(m.group(2)!, now)));
    }
  }
  return out;
}
