/// Reply format "[mood:NAME] [action:NAME] spoken words", ported from the laptop
/// brain (`spike_brain/mind/reply.py`) so the phone brain parses, cleans and
/// chunks replies exactly the same way. Models slip, so this is also a fallback
/// parser: tags anywhere, bare "[happy]", "Mood: happy" lines, *stage
/// directions*, synonyms, `<think>` blocks, emoji and markdown.
///
/// [StreamParser] turns a token stream into events: a [TagsEvent] once, before
/// any speech; [SentenceEvent]s in order; [ActionEvent]s found later.
library;

import '../../core/capabilities.dart';
import '../../protocol/names.dart' as n;

/// Moods offered to the model (a readable subset; the parser accepts all moods).
const llmMoods = [
  'happy', 'excited', 'love', 'laughing', 'playful', 'curious', 'sad', 'caring', //
  'sleepy', 'proud', 'embarrassed', 'cuddly', 'surprised', 'sulking', 'mischief',
  'smugness', 'confusion', 'shyness', 'gratitude', 'relief', 'begging', 'delight',
  'joy', 'hope', 'silliness', 'jealousy', 'suspicion', 'nervousness', 'awe', 'bored',
  'cuteAngry', 'determination',
];
/// Only what the real body can do is offered to the model (core/capabilities.dart hides the rest).
final llmActions = [
  for (final a in const [
    'headTilt', 'tailWagDance', 'zoomies', 'playBow', 'rollOver', 'sniffAround', 'yawn', //
    'beggingAction', 'sneeze', 'snuggle', 'slowWag',
  ])
    if (isAvailable(a)) a,
];

final Map<String, String> _moodLc = {for (final m in n.moods) m.toLowerCase(): m};
final Map<String, String> _actionLc = {for (final a in n.actions) a.toLowerCase(): a};

const moodSynonyms = {
  'confused': 'confusion', 'shy': 'shyness', 'grateful': 'gratitude', 'thankful': 'gratitude',
  'smug': 'smugness', 'sassy': 'smugness', 'sass': 'smugness', 'unimpressed': 'smugness', 'silly': 'silliness',
  'goofy': 'silliness', 'jealous': 'jealousy', 'suspicious': 'suspicion', 'nervous': 'nervousness',
  'worried': 'nervousness', 'anxious': 'nervousness', 'determined': 'determination', 'angry': 'cuteAngry',
  'mad': 'cuteAngry', 'annoyed': 'cuteAngry', 'grumpy': 'cuteAngry', 'cute_angry': 'cuteAngry',
  'lonely': 'loneliness', 'tired': 'sleepy', 'drowsy': 'sleepy', 'asleep': 'sleeping', 'loving': 'love',
  'affectionate': 'love', 'teasing': 'playful', 'cheeky': 'mischief', 'mischievous': 'mischief',
  'naughty': 'mischief', 'calm': 'neutral', 'content': 'cuddly', 'cozy': 'cuddly', 'cosy': 'cuddly',
  'snuggly': 'cuddly', 'warm': 'caring', 'gentle': 'caring', 'concerned': 'caring', 'sympathetic': 'caring',
  'empathetic': 'caring', 'kind': 'caring', 'supportive': 'caring', 'thinking': 'curious',
  'thoughtful': 'curious', 'interested': 'curious', 'amazed': 'awe', 'wonder': 'awe',
  'happy_excited': 'excited', 'thrilled': 'excited', 'glad': 'happy', 'cheerful': 'happy',
  'funny': 'laughing', 'amused': 'laughing', 'giggly': 'laughing', 'hopeful': 'hope',
  'relieved': 'relief', 'scared_': 'scared', 'afraid': 'scared', 'frightened': 'scared',
  'sorry': 'embarrassed', 'sheepish': 'embarrassed', 'pleading': 'begging', 'sulky': 'sulking',
  'pouting': 'sulking', 'sulk': 'sulking', 'bored_': 'bored', 'proud_': 'proud', 'surprise': 'surprised',
  'shocked': 'surprised', 'delighted': 'delight', 'joyful': 'joy', 'sad_': 'sad', 'unhappy': 'sad',
  'grieving': 'grief', 'hungry_': 'hungry', 'disgusted': 'disgust', 'frustrated': 'frustration',
};
const actionSynonyms = {
  'head_tilt': 'headTilt', 'tilt': 'headTilt', 'tilthead': 'headTilt', 'tilts head': 'headTilt',
  'wag': 'tailWagDance', 'tailwag': 'tailWagDance', 'wags tail': 'tailWagDance', 'dance': 'tailWagDance',
  'happy dance': 'tailWagDance', 'zoom': 'zoomies', 'play_bow': 'playBow', 'bow': 'playBow',
  'roll': 'rollOver', 'roll_over': 'rollOver', 'rolls over': 'rollOver', 'sniff': 'sniffAround',
  'sniffs': 'sniffAround', 'sniff_around': 'sniffAround', 'beg': 'beggingAction', 'begs': 'beggingAction',
  'begging': 'beggingAction', 'yawns': 'yawn', 'sneezes': 'sneeze', 'pants': 'pant', 'shivers': 'shiver',
  'hiccups': 'hiccup', 'none': '', 'no': '', 'null': '',
  'snuggles': 'snuggle', 'cuddle': 'snuggle', 'lean in': 'snuggle', 'leanin': 'snuggle', 'nuzzle': 'snuggle',
  'slow wag': 'slowWag', 'slow_wag': 'slowWag', 'slowwag': 'slowWag', 'gentle wag': 'slowWag',
};

const _stageActions = [
  ('snuggle', 'snuggle'), ('cuddle', 'snuggle'), ('nuzzle', 'snuggle'), ('lean', 'snuggle'), //
  ('slow', 'slowWag'), ('wag', 'tailWagDance'), ('tilt', 'headTilt'), ('yawn', 'yawn'),
  ('sniff', 'sniffAround'), ('zoom', 'zoomies'), ('roll', 'rollOver'),
  ('bow', 'playBow'), ('beg', 'beggingAction'), ('sneeze', 'sneeze'),
  ('pant', 'pant'), ('dance', 'tailWagDance'), ('spin', 'zoomies'),
];

final tagRe = RegExp(r'\[\s*(mood|action|emotion|face)\s*[:=]\s*([^\]\[]{0,40}?)\s*\]', caseSensitive: false);
final bareTagRe = RegExp(r'\[\s*([A-Za-z_ ]{2,30})\s*\]');
final pipeTagRe = RegExp(r'\[\s*([A-Za-z_ ]{2,30}?)\s*\|\s*([A-Za-z_ ]{0,30}?)\s*\]');
final anyTagRe = RegExp(r'\[\s*[A-Za-z_]{2,20}(\s*\|\s*[A-Za-z_]{0,20})?\s*\]');
final placeholderRe = RegExp(r'\[\s*(mood|action|name|tag|emotion)\s*(\|\s*(action|name))?\s*\]', caseSensitive: false);
final lineTagRe = RegExp(r'^\s*(mood|action)\s*[:=]\s*([A-Za-z_]+)\s*$', caseSensitive: false, multiLine: true);
final thinkRe = RegExp(r'<think>.*?(</think>|$)', caseSensitive: false, dotAll: true);
final stageRe = RegExp(r'\*([^*\n]{1,60})\*|\(([a-z][^()\n]{1,40})\)');
final stageVerbs = RegExp(
    r'\b(wags?|wagging|purrs?|purring|sighs?|giggles?|tilts?|rolls?|yawns?|sniffs?|blinks?|'
    r'stretch(es)?|laughs?|winks?|nuzzles?|snuggles?|cuddles?|hiss(es)?|meows?|barks?|whines?|'
    r'spins?|jumps?|bounces?|licks?|paws?|flicks?|smirks?|grins?|beeps?|boops?|leans?|curls?|'
    r'looks? (away|up|at)|pretends?|ignores?|knocks?|zooms?|blushes|sits?|lies? down|'
    r'tail|ears?|head)\b',
    caseSensitive: false);

String _stage(Match m) {
  final inner = m.group(1) ?? m.group(2) ?? '';
  return stageVerbs.hasMatch(inner) ? ' ' : ' $inner ';
}

// Python's EMOJI_RE: U+1F000-U+1FAFF, U+2600-U+27BF, U+1F900-U+1F9FF, ZWJ, VS16
final emojiRe = RegExp('[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F900}-\u{1F9FF}‍️]', unicode: true);
final boldRe = RegExp(r'(\*\*|__)(.+?)\1');
final mdRe = RegExp(r'(\*\*|__|`|^#+\s*|^\s*[-*]\s+)', multiLine: true);

String? normalizeMood(String? name) {
  if (name == null || name.isEmpty) return null;
  final key = name.trim().toLowerCase().replaceAll('-', '_');
  if (_moodLc.containsKey(key)) return _moodLc[key];
  final k2 = key.replaceAll('_', '');
  if (_moodLc.containsKey(k2)) return _moodLc[k2];
  final syn = moodSynonyms[key] ?? moodSynonyms['${key}_'];
  return (syn == null || syn.isEmpty) ? null : syn;
}

String? normalizeAction(String? name) {
  if (name == null || name.isEmpty) return null;
  final key = name.trim().toLowerCase();
  final k2 = key.replaceAll(' ', '').replaceAll('_', '').replaceAll('-', '');
  final syn = actionSynonyms[key] ?? actionSynonyms[key.replaceAll(' ', '_')];
  final found = _actionLc[key] ?? _actionLc[k2] ?? ((syn == null || syn.isEmpty) ? null : syn);
  // core/capabilities.dart: an action the body cannot do is never parsed out of a reply
  return isAvailable(found) ? found : null;
}

String? stageToAction(String direction) {
  final d = direction.toLowerCase();
  for (final (word, action) in _stageActions) {
    if (d.contains(word)) return isAvailable(action) ? action : null;
  }
  return null;
}

final _petNames = RegExp(
    r'\s*,?\s*\b(sweetie|sweetheart|honey|darling|babe|my dear|my love|love bug|'
    r'my (poor |sweet |dear |little )?(girl|boy))\b(?=[\s,.!?]|$)',
    caseSensitive: false);

/// "Oh sweetie, that sounds heavy." -> "Oh, that sounds heavy." Spike and Spicy
/// never use romantic pet names (and never guess the owner's gender).
String stripPetNames(String text) {
  if (!_petNames.hasMatch(text)) return text;
  var out = text.replaceAllMapped(
      RegExp(r'\b(Oh|Aw|Aww|Hey|Hi)\s+(sweetie|sweetheart|honey|darling|babe|'
          r'my (poor |sweet |dear |little )?(girl|boy))\b,?', caseSensitive: false),
      (m) => '${m.group(1)},');
  out = out.replaceAll(_petNames, '');
  out = out.replaceAll(RegExp(r'^\s*[,.]\s*'), '');
  out = out.replaceAllMapped(RegExp(r',\s*([.!?])'), (m) => m.group(1)!);
  out = out.replaceAll(RegExp(r'\s{2,}'), ' ').trim();
  return out.isEmpty ? out : out[0].toUpperCase() + out.substring(1);
}

/// Make text safe and pleasant to speak: no tags, emoji, markdown, stage directions.
String cleanSpeech(String text) {
  text = text.replaceAll(thinkRe, ' ');
  text = text.replaceAll(tagRe, ' ');
  text = text.replaceAll(pipeTagRe, ' ');
  text = text.replaceAll(placeholderRe, ' ');
  text = text.replaceAll(anyTagRe, ' ');
  text = text.replaceAllMapped(boldRe, (m) => m.group(2)!);
  text = text.replaceAllMapped(stageRe, _stage);
  text = text.replaceAll(emojiRe, '');
  text = text.replaceAll(mdRe, '');
  text = text.replaceAll('*', ' ').replaceAll('#', ' ');
  text = text.replaceAll(RegExp(r'\s+'), ' ').trim();
  text = text.replaceAllMapped(RegExp(r'\s+([,!?;:]|\.(?!\.))'), (m) => m.group(1)!);
  if (text.length >= 2 && text[0] == text[text.length - 1] && (text[0] == '"' || text[0] == "'")) {
    text = text.substring(1, text.length - 1).trim();
  }
  return text;
}

class ParsedReply {
  const ParsedReply(this.mood, this.action, this.text);
  final String? mood;
  final String? action;
  final String text;
  @override
  String toString() => 'ParsedReply($mood, $action, $text)';
}

/// Parse a complete reply (scripted lines and non-streamed model output).
ParsedReply parseReply(String? rawIn) {
  var raw = (rawIn ?? '').replaceAll(thinkRe, ' ');
  raw = raw.replaceAllMapped(boldRe, (m) => m.group(2)!);
  String? mood;
  String? action;
  for (final m in tagRe.allMatches(raw)) {
    final k = m.group(1)!.toLowerCase();
    final v = m.group(2)!;
    if ((k == 'mood' || k == 'emotion' || k == 'face') && mood == null) {
      mood = normalizeMood(v);
    } else if (k == 'action' && action == null) {
      action = normalizeAction(v);
    }
  }
  for (final m in lineTagRe.allMatches(raw)) {
    final k = m.group(1)!.toLowerCase();
    if (k == 'mood' && mood == null) {
      mood = normalizeMood(m.group(2));
    } else if (k == 'action' && action == null) {
      action = normalizeAction(m.group(2));
    }
  }
  raw = raw.replaceAll(lineTagRe, ' ');
  raw = raw.replaceAllMapped(pipeTagRe, (m) {
    if (normalizeMood(m.group(1)) != null || normalizeAction(m.group(2)) != null) {
      mood ??= normalizeMood(m.group(1));
      action ??= normalizeAction(m.group(2));
      return ' ';
    }
    return m.group(0)!;
  });
  raw = raw.replaceAllMapped(bareTagRe, (m) {
    final word = m.group(1)!;
    if (mood == null && normalizeMood(word) != null) {
      mood = normalizeMood(word);
      return ' ';
    }
    if (action == null && normalizeAction(word) != null) {
      action = normalizeAction(word);
      return ' ';
    }
    return m.group(0)!;
  });
  for (final m in stageRe.allMatches(raw)) {
    final a = stageToAction(m.group(1) ?? m.group(2) ?? '');
    if (a != null && action == null) action = a;
  }
  return ParsedReply(mood, action, cleanSpeech(raw));
}

const _abbrev = ['mr.', 'mrs.', 'ms.', 'dr.', 'st.', 'vs.', 'etc.', 'e.g.', 'i.e.', 'a.m.', 'p.m.', 'no.'];
final _boundary = RegExp('([.!?…]+["\')\\]]*)(\\s+)');
final _softBoundary = RegExp('[,;:—]\\s');

List<String> _words(String s) => s.trim().split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();

/// Cut complete chunks off the front of [text]; returns (chunks, remainder).
/// Same rules as reply.py `split_sentences`.
(List<String>, String) splitSentences(String text, {required bool first, int firstMinWords = 4, int maxChars = 220}) {
  final chunks = <String>[];
  while (true) {
    int? cut;
    for (final m in _boundary.allMatches(text)) {
      final head = text.substring(0, m.start + m.group(1)!.length); // text[:m.end(1)]
      final hw = _words(head);
      final tailWord = hw.isNotEmpty ? hw.last.toLowerCase() : '';
      if (_abbrev.contains(tailWord)) continue;
      final nextChar = m.end < text.length ? text.substring(m.end, m.end + 1) : '';
      if (RegExp(r'\d\.$').hasMatch(head) && RegExp(r'\d').hasMatch(nextChar)) continue;
      cut = m.start + m.group(1)!.length;
      break;
    }
    if (cut == null && first && chunks.isEmpty) {
      for (final m in _softBoundary.allMatches(text)) {
        if (_words(text.substring(0, m.start)).length >= firstMinWords) {
          cut = m.start + 1;
          break;
        }
      }
    }
    if (cut == null && text.length > maxChars) {
      final window = text.substring(0, maxChars);
      final c = window.lastIndexOf(', ') > window.lastIndexOf(' ') ? window.lastIndexOf(', ') : window.lastIndexOf(' ');
      cut = c > 20 ? c + 1 : maxChars;
    }
    if (cut == null) return (chunks, text);
    final piece = text.substring(0, cut).trim();
    text = text.substring(cut).trimLeft();
    if (piece.isNotEmpty) chunks.add(piece);
    first = first && chunks.isEmpty;
  }
}

sealed class ReplyEvent {
  const ReplyEvent();
}

class TagsEvent extends ReplyEvent {
  const TagsEvent(this.mood, this.action);
  final String? mood;
  final String? action;
  @override
  bool operator ==(Object other) => other is TagsEvent && other.mood == mood && other.action == action;
  @override
  int get hashCode => Object.hash(mood, action);
  @override
  String toString() => 'tags($mood, $action)';
}

class SentenceEvent extends ReplyEvent {
  const SentenceEvent(this.text);
  final String text;
  @override
  bool operator ==(Object other) => other is SentenceEvent && other.text == text;
  @override
  int get hashCode => text.hashCode;
  @override
  String toString() => 'sentence($text)';
}

class ActionEvent extends ReplyEvent {
  const ActionEvent(this.action);
  final String action;
  @override
  bool operator ==(Object other) => other is ActionEvent && other.action == action;
  @override
  int get hashCode => action.hashCode;
  @override
  String toString() => 'action($action)';
}

/// Incremental parser for a streamed reply. Feed tokens, get events.
class StreamParser {
  StreamParser({this.firstMinWords = 4, this.maxChars = 220});
  final int firstMinWords;
  final int maxChars;
  String buf = '';
  bool headerDone = false;
  String? mood;
  String? action;
  int sentences = 0;
  String full = '';

  List<ReplyEvent> _header(bool finalCall) {
    while (true) {
      final s = buf.trimLeft();
      final low = s.toLowerCase();
      if (!finalCall && s.isNotEmpty && '<think>'.startsWith(low)) return [];
      if (low.startsWith('<think>')) {
        final end = low.indexOf('</think>');
        if (end < 0) return !finalCall ? [] : _endHeader('');
        buf = s.substring(end + 8);
        continue;
      }
      if (s.startsWith('[')) {
        final close = s.indexOf(']');
        if (close < 0) {
          if (s.length > 48 || finalCall) return _endHeader(s);
          return [];
        }
        final tag = s.substring(0, close + 1);
        final m = _full(tagRe, tag);
        final b = _full(bareTagRe, tag);
        final pm = _full(pipeTagRe, tag);
        if (pm != null && (normalizeMood(pm.group(1)) != null || normalizeAction(pm.group(2)) != null)) {
          mood ??= normalizeMood(pm.group(1));
          action ??= normalizeAction(pm.group(2));
        } else if (m != null) {
          final k = m.group(1)!.toLowerCase();
          if (k == 'action') {
            action ??= normalizeAction(m.group(2));
          } else {
            mood ??= normalizeMood(m.group(2));
          }
        } else if (_full(placeholderRe, tag) != null) {
          // "[mood]" copied from the prompt: drop it
        } else if (b != null && (normalizeMood(b.group(1)) != null || normalizeAction(b.group(1)) != null)) {
          if (normalizeMood(b.group(1)) != null && mood == null) {
            mood = normalizeMood(b.group(1));
          } else if (normalizeAction(b.group(1)) != null && action == null) {
            action = normalizeAction(b.group(1));
          }
        } else if (b != null && _words(b.group(1)!).length <= 2) {
          // an invented tag ("[sass]"): never speak it
        } else {
          return _endHeader(s);
        }
        buf = s.substring(close + 1);
        continue;
      }
      final lm = lineTagRe.matchAsPrefix(s);
      if (lm != null && s.contains('\n')) {
        // Python's LINE_TAG_RE.match anchors at the start; with MULTILINE `$` ends at the line end
        if (lm.group(1)!.toLowerCase() == 'mood') {
          mood ??= normalizeMood(lm.group(2));
        } else {
          action ??= normalizeAction(lm.group(2));
        }
        buf = s.substring(lm.end);
        continue;
      }
      if (s.isEmpty) return !finalCall ? [] : _endHeader('');
      if (RegExp(r'^(mood|action)\s*[:=]?\s*[A-Za-z_]*$', caseSensitive: false).hasMatch(s) && !finalCall) {
        return [];
      }
      return _endHeader(s);
    }
  }

  static final Map<RegExp, RegExp> _anchored = {};

  /// Python's `re.fullmatch`: the whole string must match (backtracking allowed).
  static RegExpMatch? _full(RegExp re, String s) {
    final a = _anchored.putIfAbsent(
        re, () => RegExp('^(?:${re.pattern})\$', caseSensitive: re.isCaseSensitive, dotAll: re.isDotAll));
    return a.firstMatch(s);
  }

  List<ReplyEvent> _endHeader(String rest) {
    headerDone = true;
    buf = rest;
    return [TagsEvent(mood, action)];
  }

  List<ReplyEvent> feed(String token) {
    full += token;
    buf += token;
    final events = <ReplyEvent>[];
    if (!headerDone) {
      events.addAll(_header(false));
      if (!headerDone) return events;
    }
    events.addAll(_body(false));
    return events;
  }

  List<ReplyEvent> finish() {
    final events = <ReplyEvent>[];
    if (!headerDone) events.addAll(_header(true));
    events.addAll(_body(true));
    return events;
  }

  List<ReplyEvent> _body(bool finalCall) {
    final events = <ReplyEvent>[];
    var text = buf;
    if (!finalCall) {
      for (final (opener, closer) in const [('*', '*'), ('[', ']'), ('<think>', '</think>')]) {
        final i = opener != '*' ? text.lastIndexOf(opener) : _unclosedStar(text);
        if (i >= 0 && !text.substring(i + opener.length).contains(closer)) {
          text = text.substring(0, i);
          break;
        }
      }
    }
    var held = buf.substring(text.length);
    for (final m in tagRe.allMatches(text)) {
      if (m.group(1)!.toLowerCase() == 'action') {
        final a = normalizeAction(m.group(2));
        if (a != null) events.add(ActionEvent(a));
      }
    }
    for (final m in stageRe.allMatches(text)) {
      final a = stageToAction(m.group(1) ?? m.group(2) ?? '');
      if (a != null) events.add(ActionEvent(a));
    }
    text = text.replaceAll(thinkRe, ' ');
    text = text.replaceAll(tagRe, ' ');
    text = text.replaceAll(pipeTagRe, ' ');
    text = text.replaceAll(placeholderRe, ' ');
    text = text.replaceAllMapped(boldRe, (m) => m.group(2)!);
    text = text.replaceAllMapped(stageRe, _stage);
    var (chunks, rest) = splitSentences(text, first: sentences == 0, firstMinWords: firstMinWords, maxChars: maxChars);
    if (finalCall) {
      final restClean = cleanSpeech(rest + held);
      if (restClean.isNotEmpty) chunks = [...chunks, restClean];
      rest = '';
      held = '';
    }
    for (var c in chunks) {
      c = cleanSpeech(c);
      if (c.isNotEmpty && RegExp(r'[A-Za-z0-9]').hasMatch(c)) {
        events.add(SentenceEvent(c));
        sentences++;
      }
    }
    buf = rest + held;
    return events;
  }
}

int _unclosedStar(String text) {
  final idx = <int>[];
  for (var i = 0; i < text.length; i++) {
    if (text[i] == '*') idx.add(i);
  }
  return idx.length.isOdd ? idx.last : -1;
}
