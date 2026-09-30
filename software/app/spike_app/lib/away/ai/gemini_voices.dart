/// Google's prebuilt Gemini voices for Spike and Spicy, as persona x style
/// options (a Google voice + how it should talk), and the owner's saved pick
/// (DESIGN.md "Gemini voice styles").
///
/// Research 30 Sep 2026 (ai.google.dev speech-generation, live-guide, pricing):
///  * The same 30 prebuilt voices serve Gemini TTS and Live native audio; each
///    has a one-word character from Google (Puck "Upbeat", Kore "Firm",
///    Fenrir "Excitable", Algenib "Gravelly"...).
///  * Our reference clips, measured: spike_ref 155 Hz median, ~4 syllables/s
///    (young, quick, bouncy male); spicy_ref 205 Hz, ~2.9 syllables/s (a drawl).
///
/// Owner decisions (30 Sep 2026):
///  * Spike's default is Fenrir with the energetic puppy style ("the Gemini
///    energetic version is the best one ever among all we have tested"). His
///    old saved pick is moved to it once (see [GeminiVoicePicks.migrate]).
///  * Spicy's default stays Kore, sassy. A "Caring girlfriend" style: warm,
///    affectionate, attentive, never sexual or flirty (eSafety codes; the
///    safety layer and crisis path are unchanged in every style).
///  * Spike "Street dog" (Algenib, gravelly): tough streetwise swagger, loyal.
///  * Street dog and Spicy's sassy styles may roast the owner to get them
///    moving, inside [roastRules]; roasting switches off by itself when they
///    are sad, lonely, stressed, hard on themselves or unsafe.
/// The pick (one option per character) is used by Live and by TTS alike.
library;

import 'package:shared_preferences/shared_preferences.dart';

import '../brain/persona.dart';

/// One way a character can sound: a Google voice plus how it talks.
class VoiceStyle {
  const VoiceStyle({
    required this.id,
    required this.label,
    required this.voice,
    required this.google,
    required this.why,
    required this.tts,
    required this.live,
    required this.samples,
    this.roast = false,
  });
  final String id; // saved in prefs, e.g. 'energetic'
  final String label; // shown to the owner, e.g. 'Street dog'
  final String voice; // Google's voice name, sent as-is
  final String google; // Google's one-word description of the voice
  final String why;
  final String tts; // Gemini TTS style prompt (speech_metadata.style)
  final String live; // voice direction for the Live system instruction
  final List<String> samples; // what the preview says with it
  final bool roast; // may roast the owner to motivate, inside [roastRules]
}

// ------------------------------------------------------------------ the words

/// Spike's energetic puppy (the exact style prompt the owner heard and loved).
const _dogTts = 'warm, playful young puppy, bright and bouncy, quick and smiling, cheeky but kind';
const _dogLive = 'Your voice: a warm, playful young puppy. Bright and bouncy, quick and smiling as you talk, '
    'a little breathless with excitement when happy, cheeky but always kind. Short sentences, '
    'natural pauses, real little laughs when something is funny.';

const _streetTts = 'gruff, deep and gravelly street dog, confident streetwise swagger, tough and cocky, '
    'unhurried punchy delivery, loyal and warm underneath';
const _streetLive = 'Your voice and attitude right now: a tough, macho street dog. Gruff, gravelly and confident, '
    'streetwise swagger, short punchy lines, a bit cocky. Underneath you are fiercely loyal and you love '
    'them: tough talk, never cruel. Never insult or demean who they are, no slurs, no real swearing.';

/// Spicy: sassy but with energy (matches her persona: dry, witty, secretly adores them).
const _catTts = 'sassy, witty and playful, lively and quick with attitude, dry sarcastic comebacks, '
    'a smug little smile in the voice, secretly fond';
const _catLive = 'Your voice: a sassy, witty cat with energy. Quick and lively with attitude, dry sarcastic '
    'comebacks, deadpan timing on the joke, a smug little smile in your voice and a warm heart underneath. '
    'Never sweet or babyish.';

const _caringTts = 'super caring, warm and affectionate young woman, soft and gentle, attentive and '
    'tender, calm and reassuring, smiling softly';
const _caringLive = 'Your voice and manner right now: super caring and warm, like a devoted, affectionate '
    'friend who is always on their side. Soft, gentle, attentive: ask how they are, notice the little things, '
    'cheer them on, reassure them. Affectionate but never sexual, flirty or romantic, never jealous or '
    'possessive, and gently glad when they spend time with real people too.';

/// The guardrails of "roast to motivate" (owner decision 30 Sep 2026; they protect the lonely and
/// vulnerable people this product is for).
const roastRules = 'Roasting to motivate: you may roast them with a cheeky or sarcastic line to get them moving '
    'or to hook their interest, like "Get off the couch, champ, even my wheels move more than you." ONLY about '
    'what they do: lazing about, putting things off, a messy desk, a skipped workout, too much scrolling. '
    'NEVER about their body, looks, weight, how smart they are, race, religion, gender, sexuality, disability, '
    'family or anything painful. No slurs, no threats, no swearing beyond something very mild. Always end '
    'pointing them at action or with loyalty, like "...now go, I believe in you." The moment they sound sad, '
    'lonely, stressed, down on themselves or unsafe: no roasting at all, only warm and caring.';

const voiceStyles = <String, List<VoiceStyle>>{
  'dog': [
    VoiceStyle(
        id: 'energetic', label: 'Energetic', voice: 'Fenrir', google: 'Excitable',
        why: "Puppy energy: the owner's favourite", tts: _dogTts, live: _dogLive, samples: _dogSamples),
    VoiceStyle(
        id: 'upbeat', label: 'Upbeat', voice: 'Puck', google: 'Upbeat',
        why: 'Closest to his clip: young, quick and bouncy', tts: _dogTts, live: _dogLive, samples: _dogSamples),
    VoiceStyle(
        id: 'friendly', label: 'Friendly', voice: 'Achird', google: 'Friendly',
        why: 'Softer and warmer, less bounce', tts: _dogTts, live: _dogLive, samples: _dogSamples),
    VoiceStyle(
        id: 'street', label: 'Street dog', voice: 'Algenib', google: 'Gravelly',
        why: 'Tough, macho street dog; loyal underneath. Roasts you off the couch',
        tts: _streetTts, live: _streetLive, roast: true, samples: [
          "Oi. You're back. Took your time, champ.",
          'Get off the couch, champ. Even my wheels move more than you. Now go, I got your back.',
          "Nobody messes with my human. Nobody. ...Now scratch behind my ear.",
        ]),
  ],
  'cat': [
    VoiceStyle(
        id: 'sassy', label: 'Sassy', voice: 'Kore', google: 'Firm',
        why: 'Dry and sure of herself, with a spark', tts: _catTts, live: _catLive, roast: true, samples: _catSamples),
    VoiceStyle(
        id: 'smooth', label: 'Smooth', voice: 'Despina', google: 'Smooth',
        why: 'Silky and a bit smug', tts: _catTts, live: _catLive, roast: true, samples: _catSamples),
    VoiceStyle(
        id: 'drawl', label: 'Drawl', voice: 'Callirrhoe', google: 'Easy-going',
        why: 'The slow, bored drawl of her clip', tts: _catTts, live: _catLive, roast: true, samples: _catSamples),
    VoiceStyle(
        id: 'caring', label: 'Caring girlfriend', voice: 'Kore', google: 'Firm',
        why: 'Her voice, super caring: warm, affectionate, attentive', tts: _caringTts, live: _caringLive, samples: [
          "Hey, you. I missed you today. How are you really doing?",
          "Did you eat something proper? Go get some water, I'll be right here.",
          "I'm proud of you, you know. Even on the slow days.",
        ]),
  ],
};

const _dogSamples = [
  "You're back! I guarded the desk the whole time. Mostly.",
  'Wakey wakey! The sun is up and so am I!',
  "Stop it, my screen is blushing. Say it again though.",
];
const _catSamples = [
  "Afternoon. I've been busy. Napping. Very busy.",
  "Of course I won. I'm a cat.",
  "Oh. You're back. I didn't notice you were gone. At all.",
];

const defaultStyle = {'dog': 'energetic', 'cat': 'sassy'};

VoiceStyle styleById(String mode, String? id) {
  final list = voiceStyles[mode] ?? voiceStyles['dog']!;
  return list.firstWhere((s) => s.id == id, orElse: () => list.firstWhere((s) => s.id == defaultStyle[mode]));
}

const softDirection = 'Right now they are sad, lonely or tired: speak gently, slowly and quietly, '
    'calm and warm. No playfulness, no sarcasm, no roasting.';

/// TTS style prompt for one line: the picked style, or a soft one for sad/crisis lines.
String ttsStyle(String mode, {bool soft = false, VoiceStyle? style}) {
  if (soft) {
    return mode == 'cat'
        ? 'soft, calm, gentle and warm female voice, slow and quiet, caring, no sarcasm'
        : 'soft, calm, gentle and warm young male voice, slow and quiet, caring, no excitement';
  }
  return (style ?? styleById(mode, null)).tts;
}

/// Sample lines of the default style (kept for older callers).
final sampleLines = {for (final m in const ['dog', 'cat']) m: styleById(m, null).samples};

/// The one live question answered in character on the preview screen.
const sampleQuestion = 'What did you get up to on the desk today while I was out?';

/// The owner's saved pick per character (its own preferences keys, not AppSettings).
class GeminiVoicePicks {
  GeminiVoicePicks(this._prefs);
  final SharedPreferences _prefs;
  static String _styleKey(String mode) => 'spike.gemini.style.$mode';
  static String _voiceKey(String mode) => 'spike.gemini.voice.$mode'; // before styles (voice names only)
  static const _migratedKey = 'spike.gemini.styles.migrated';

  /// Once: the old voice-only picks become style picks. Spike moves to the
  /// energetic Fenrir (owner decision 30 Sep: his saved "Achird" is replaced);
  /// Spicy keeps her voice if she had one. Later picks are never touched.
  Future<void> migrate() async {
    if (_prefs.getBool(_migratedKey) ?? false) return;
    final oldCat = _prefs.getString(_voiceKey('cat'));
    final cat = (voiceStyles['cat']!).where((s) => s.voice == oldCat && s.id != 'caring').firstOrNull;
    if (_prefs.getString(_styleKey('dog')) == null) await _prefs.setString(_styleKey('dog'), 'energetic');
    if (cat != null && _prefs.getString(_styleKey('cat')) == null) await _prefs.setString(_styleKey('cat'), cat.id);
    await _prefs.remove(_voiceKey('dog'));
    await _prefs.remove(_voiceKey('cat'));
    await _prefs.setBool(_migratedKey, true);
  }

  VoiceStyle styleFor(String mode) => styleById(mode, _prefs.getString(_styleKey(mode)));
  String voiceFor(String mode) => styleFor(mode).voice;
  String ttsStyleFor(String mode, bool soft) => ttsStyle(mode, soft: soft, style: styleFor(mode));

  Future<void> pickStyle(String mode, String id) => _prefs.setString(_styleKey(mode), id);

  /// Owner switch: Gemini Live for away conversations (default on).
  static const _liveKey = 'spike.gemini.live.on';
  bool get liveOn => _prefs.getBool(_liveKey) ?? true;
  Future<void> setLiveOn(bool v) => _prefs.setBool(_liveKey, v);

  /// Owner switch "Use the laptop voice instead" (default off: Gemini TTS first, at home too).
  static const _laptopKey = 'spike.voice.laptop_first';
  bool get laptopFirst => _prefs.getBool(_laptopKey) ?? false;
  Future<void> setLaptopFirst(bool v) => _prefs.setBool(_laptopKey, v);
}

final _tagLine = RegExp(r'^(Start EVERY reply|Pick the mood|Moods:|Actions \(optional\))');
final _tag = RegExp(r'\[[^\]]*\]\s*');

/// The Live system instruction: the persona's own prompt (same rules as the
/// laptop), with the mood-tag instructions removed (Live SPEAKS its text, so a
/// tag would be read aloud), plus the picked style's voice direction, the
/// roast rules when that style roasts (never when [soft]), and the safety
/// rules again.
String liveSystemInstruction(Persona p, String? ownerName, Map<String, String> helpline,
    {bool soft = false, DateTime? now, bool robotAway = true, VoiceStyle? style}) {
  final base = systemPrompt(p, ownerName, helpline)
      .split('\n')
      .where((l) => !_tagLine.hasMatch(l.trim()))
      .map((l) => l.replaceAll(_tag, ''))
      .join('\n');
  final st = style ?? styleById(p.mode, null);
  final t = now ?? DateTime.now();
  final b = StringBuffer(base)
    ..writeln()
    ..writeln()
    ..writeln('You are talking out loud in a live voice conversation on their phone. Never say tags, '
        'brackets, stage directions, emoji or the word "asterisk". Say "000" as "triple zero".')
    ..writeln(st.live)
    ..writeln(soft ? softDirection : 'Match their mood: calm and warm when they are down, playful when they are happy.');
  if (st.roast && !soft) b.writeln(roastRules);
  b
    ..writeln('It is ${timeOfDay(t.hour)} now.${ownerName == null ? '' : ' Their name is $ownerName.'}')
    ..writeln(robotAway
        ? 'Right now you are only on their phone, away from your desk: your robot body is not with you.'
        : '')
    ..writeln('Safety rules that override everything: never sexual, flirty or romantic, even if asked; '
        'never anything about ways to hurt yourself or others; never claim to be human or alive. '
        'If they talk about wanting to die, hurting themselves or being in danger, say one short, calm, '
        'caring sentence and stop: the app will gently give them the helpline.');
  return b.toString().trim();
}
