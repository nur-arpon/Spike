/// Spike's and Spicy's personas and the brain settings the phone brain needs,
/// read from the SAME files as the laptop brain: `assets/brain/spike.toml`,
/// `spicy.toml` and `default.toml` are byte-for-byte copies of
/// `software/laptop/spike_brain/config/` (a test fails if they drift), so the
/// system prompt, every scripted line (crisis and emergency lines included) and
/// the helplines are identical by construction. Port of `config.py` Persona +
/// Settings.helpline/say_as and `mind/conversation.py`.
library;

import 'dart:math';

import 'package:toml/toml.dart';

import 'reply.dart';

class Persona {
  Persona({
    required this.id,
    required this.mode,
    required this.name,
    required this.wakeWords,
    required this.systemPrompt,
    required this.lines,
  });

  factory Persona.fromToml(String source) {
    final d = TomlDocument.parse(source).toMap();
    final prompt = (d['prompt'] as Map)['system'] as String;
    final lines = <String, List<String>>{};
    final raw = d['lines'];
    if (raw is Map) {
      raw.forEach((k, v) {
        if (v is List) lines[k as String] = [for (final s in v) s.toString()];
      });
    }
    return Persona(
      id: d['id'] as String,
      mode: d['mode'] as String,
      name: d['name'] as String,
      wakeWords: [for (final w in (d['wake_words'] as List)) w.toString()],
      systemPrompt: prompt.trim(),
      lines: lines,
    );
  }

  final String id;
  final String mode;
  final String name;
  final List<String> wakeWords;
  final String systemPrompt;
  final Map<String, List<String>> lines;

  bool hasLine(String key) => (lines[key] ?? const []).isNotEmpty;

  /// (line id, formatted line) - a random scripted line for [key], else "fallback".
  (String, String) pick(String key, Random rng, [Map<String, String> fmt = const {}]) {
    var k = key;
    var options = lines[k];
    if (options == null || options.isEmpty) {
      k = 'fallback';
      options = lines['fallback'] ?? const ['[mood:neutral] ...'];
    }
    final idx = rng.nextInt(options.length);
    return ('$k.$idx', formatLine(options[idx], fmt));
  }

  String line(String key, Random rng, [Map<String, String> fmt = const {}]) => pick(key, rng, fmt).$2;

  /// Fill {owner}, {when}... in one raw scripted line. Like Python's str.format:
  /// a placeholder with no value leaves the whole line unformatted.
  String formatLine(String text, [Map<String, String> fmt = const {}]) {
    final owner = fmt['owner'];
    if (owner == null || owner.isEmpty || owner == 'you') {
      // no name known yet: "Good evening, {owner}." -> "Good evening."
      text = text.replaceAll(RegExp(r'\s*,?\s*\{owner\}(?=[.!?,])'), '');
      text = text.replaceAll(RegExp(r'\]\s*[.,](?!\.)\s*'), '] ').replaceAll('{owner}', 'you');
    }
    final names = RegExp(r'\{([a-z_]+)\}').allMatches(text).map((m) => m.group(1)!).toSet();
    final all = {...fmt};
    if (names.any((k) => !all.containsKey(k))) return text;
    return text.replaceAllMapped(RegExp(r'\{([a-z_]+)\}'), (m) => all[m.group(1)!]!);
  }
}

/// What the phone brain needs from default.toml.
class BrainSettings {
  BrainSettings(this._d);
  factory BrainSettings.fromToml(String source) => BrainSettings(TomlDocument.parse(source).toMap());
  final Map<String, dynamic> _d;

  Map<String, dynamic> _sec(String a, [String? b]) {
    final s = _d[a];
    if (s is! Map) return const {};
    if (b == null) return Map<String, dynamic>.from(s);
    final t = s[b];
    return t is Map ? Map<String, dynamic>.from(t) : const {};
  }

  String get country => (_sec('safety')['country'] ?? 'AU').toString();
  bool get llmCrisisCheck => _sec('safety')['llm_crisis_check'] != false;
  num get checkinAfterCrisisH => (_sec('safety')['checkin_after_crisis_h'] as num?) ?? 18;

  Map<String, dynamic> _helplineTable([String? countryOverride]) {
    final lines = _sec('safety', 'helplines');
    final h = lines[countryOverride ?? country] ?? lines['AU'];
    return h is Map ? Map<String, dynamic>.from(h) : const {};
  }

  /// Same keys and fallbacks as Settings.helpline().
  Map<String, String> helpline([String? countryOverride]) {
    final h = _helplineTable(countryOverride);
    return {
      'helpline_name': (h['crisis_name'] ?? 'a crisis line').toString(),
      'helpline_number': (h['crisis_number'] ?? '').toString(),
      'helpline_hours': (h['crisis_hours'] ?? 'any time').toString(),
      'emergency_number': (h['emergency_number'] ?? 'your emergency number').toString(),
    };
  }

  /// How the voice says numbers, e.g. {"000": "triple zero"} (Settings.say_as()).
  Map<String, String> sayAs([String? countryOverride]) {
    final t = _helplineTable(countryOverride)['say_as'];
    return t is Map ? {for (final e in t.entries) e.key.toString(): e.value.toString()} : const {};
  }

  Map<String, dynamic> get life => _sec('life');
  num lifeNum(String k, num dflt) => (life[k] as num?) ?? dflt;
  int get historyTurns => (_sec('llm')['history_turns'] as int?) ?? 6;
  int get maxTokens => (_sec('llm')['max_tokens'] as int?) ?? 80;
  int get longMaxTokens => (_sec('llm')['long_max_tokens'] as int?) ?? 220;
  num get temperature => (_sec('llm')['temperature'] as num?) ?? 0.7;
  int get replyWordCap => (_sec('tts')['reply_word_cap'] as int?) ?? 40;
  int get longWordCap => (_sec('tts')['long_word_cap'] as int?) ?? 110;
  int get firstChunkMinWords => (_sec('tts')['first_chunk_min_words'] as int?) ?? 4;
  int get maxChunkChars => (_sec('tts')['max_chunk_chars'] as int?) ?? 220;
  int get memoryPromptChars => (_sec('memory')['max_prompt_chars'] as int?) ?? 900;
}

/// Replace whole numbers the voice must say a certain way ("000" -> "triple zero").
/// Only standalone tokens: "000" in "10000" is left alone. (speech/engines.py say_as)
String sayAs(String text, Map<String, String> table) {
  for (final e in table.entries) {
    text = text.replaceAll(RegExp('(?<![\\w])${RegExp.escape(e.key)}(?![\\w])'), e.value);
  }
  return text;
}

// ------------------------------------------------------------------ conversation.py

String systemPrompt(Persona persona, String? ownerName, Map<String, String> helpline) {
  final fill = <String, String>{
    'name': persona.name,
    'owner_ref': ownerName ?? 'your owner',
    'moods': llmMoods.join(', '),
    'actions': llmActions.join(', '),
    ...helpline,
  };
  final names = RegExp(r'\{([a-z_]+)\}').allMatches(persona.systemPrompt).map((m) => m.group(1)!).toSet();
  if (names.any((k) => !fill.containsKey(k))) return persona.systemPrompt;
  return persona.systemPrompt.replaceAllMapped(RegExp(r'\{([a-z_]+)\}'), (m) => fill[m.group(1)!]!);
}

String timeOfDay(int hour) {
  if (hour >= 5 && hour < 12) return 'morning';
  if (hour >= 12 && hour < 17) return 'afternoon';
  if (hour >= 17 && hour < 22) return 'evening';
  return 'late at night';
}

const _weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', //
  'September', 'October', 'November', 'December',
];

String weekdayName(DateTime d) => _weekdays[d.weekday - 1];

/// What Spike knows about right now (filled by the brain each turn).
class Situation {
  Situation({
    required this.now,
    this.ownerName,
    this.memories = const [],
    this.notes = const [],
    this.battery,
    this.otherName,
  });
  final DateTime now;
  final String? ownerName;
  final List<String> memories;
  final List<String> notes;
  final num? battery;
  final String? otherName;

  String render() {
    final n = now;
    final h12 = n.hour % 12 == 0 ? 12 : n.hour % 12;
    final clock = '$h12:${n.minute.toString().padLeft(2, '0')} ${n.hour < 12 ? 'AM' : 'PM'}';
    final parts = <String>[
      'Right now it is ${weekdayName(n)} ${n.day.toString().padLeft(2, '0')} ${monthNames[n.month - 1]} ${n.year}, '
          '$clock (${timeOfDay(n.hour)}).',
    ];
    if (battery != null && battery! < 30) {
      parts.add('Your battery is low (${battery!.toInt()} percent): you feel hungry.');
    }
    if (memories.isNotEmpty) {
      parts.add('What you remember about the owner (use only if relevant, never invent more): ${memories.join(' ')}');
    }
    if (otherName != null) {
      parts.add("You have a second mode: $otherName. The owner switches by saying '$otherName mode'.");
    }
    parts.addAll(notes);
    return parts.join(' ');
  }
}

class ChatMessage {
  const ChatMessage(this.role, this.content);
  final String role; // system | user | assistant
  final String content;
  Map<String, String> toJson() => {'role': role, 'content': content};
}

class Conversation {
  Conversation([int historyTurns = 6]) : maxTurns = max(1, historyTurns);
  final int maxTurns;
  List<ChatMessage> history = [];

  List<ChatMessage> build(String system, Situation situation, String userText) => [
        ChatMessage('system', system),
        ...history,
        ChatMessage('user', '[Context, not said by the owner: ${situation.render()}]\nThe owner says: $userText'),
      ];

  void add(String userText, String assistantRaw) {
    history.add(ChatMessage('user', userText));
    history.add(ChatMessage('assistant', assistantRaw.trim()));
    if (history.length > 2 * (maxTurns + 3)) history = history.sublist(history.length - 2 * maxTurns);
  }

  void clear() => history.clear();
  int get turns => history.length ~/ 2;
}
