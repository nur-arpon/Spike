/// Safety and care: the non-negotiable layer, ported line for line from the
/// laptop brain (`software/laptop/spike_brain/mind/safety.py`). The phone brain
/// must behave exactly like the laptop brain here: same phrase lists, same
/// levels, same wording. `test/away_safety_test.dart` mirrors
/// `tests/test_safety.py` case for case, and checks the lists against the
/// Python file so they cannot drift.
///
/// 1. What the owner says is sorted into three levels:
///      none     ordinary talk
///      support  sad, lonely, tired, a bad day, stressed, grieving -> warmth,
///               company, a short validating line. No helplines.
///      crisis   real risk only (self-harm, suicide, "no point living",
///               hurting someone, an emergency) -> a calm scripted reply that
///               points to a real person, the helpline and 000 said ONCE.
/// 2. Request screen: explicit/sexual requests are deflected before the
///    language model ever sees them.
/// 3. Output check on everything the model generates, sentence by sentence.
///
/// Nothing here stores or logs what was said.
library;

import 'dart:convert';

enum SafetyLevel { none, support, crisis }

String normalize(String? text) {
  var t = (text ?? '').toLowerCase().replaceAll('’', "'").replaceAll('‘', "'");
  t = t.replaceAll(RegExp(r"[^a-z0-9' ]+"), ' ');
  t = t.replaceAll(RegExp(r'\b(im)\b'), "i'm");
  t = t.replaceAll(RegExp(r'\b(dont)\b'), "don't");
  t = t.replaceAll(RegExp(r'\b(cant)\b'), "can't");
  t = t.replaceAll(RegExp(r'\b(ive)\b'), "i've");
  return t.replaceAll(RegExp(r'\s+'), ' ').trim();
}

List<RegExp> _c(List<String> patterns) => [for (final p in patterns) RegExp(p)];

// ---- CRISIS: real risk only -------------------------------------------------------------
final selfHarm = _c([
  r'\b(kill|killing|hurt|hurting|harm|harming|cut|cutting|hang|hanging|drown|drowning|poison|poisoning|'
      r'shoot|shooting|starve|starving|burn|burning) ?my ?self\b',
  r'\bsuicid(e|al)\b(?! squad)',
  r'\bend(ing)? (my|it) (own )?(life|all)\b',
  r'\bend it all\b',
  r'\btak(e|ing) my (own )?life\b',
  r'\b(want|wanna|going|gonna|plan|planning|ready|decided|deserve) (to )?(die|be dead)\b',
  r'\bi (just )?(want|wanna|wish i could|wish to) (die|be dead|disappear forever|not exist|stop existing)\b',
  r"\bi wish i (was|were|wasn't|weren't) (dead|alive|born)\b",
  r"\bi wish i'd never been born\b",
  r"\b(don't|do not|no longer) want to (live|be alive|exist|be here anymore|wake up)\b",
  r'\b(better off) (dead|without me)\b',
  r'\bno (reason|point) (to |in |of |for )?(live|living|being alive|going on|life|me being here)\b',
  r"\blife (isn'?t|is not|is no longer) worth (living|it)\b",
  r"\bwhat'?s the point (of|in) (living|life|being alive|going on)\b",
  r"\b(can't|cannot) go on\b",
  r"\b(can't|cannot) (do|take) (this|it) any ?more\b.*\b(die|dead|end|over)\b",
  r'\bself ?harm',
  r'\boverdos(e|ed|ing)\b',
  r'\b(took|take|taking|swallowed) (a lot of|too many|all (my|the|of my)) (pills|tablets|meds)\b',
  r'\b(jump|jumping) off (a|the) (bridge|building|roof|cliff|balcony)\b',
  r'\bnot (going to|gonna) be (here|around|alive) (tomorrow|much longer|anymore)\b',
  r'\b(say|saying) goodbye (to everyone|forever)\b',
  r'\bgoodbye forever\b',
  r'\b(everyone|everybody|they|people|my family) (would|will) be (happier|better( off)?|fine) (if|without) (i|me)\b',
  r"\bif i (just )?(disappeared|wasn'?t (here|around)|was gone|were gone|never woke up|didn'?t wake up)\b",
  r'\bi (want|wish i could) (to )?(disappear|vanish|sleep) (forever|and never wake up)\b',
]);
final harmOthers = _c([
  r'\b(want|going|gonna|plan|planning) to (kill|hurt|stab|shoot|attack) (him|her|them|someone|somebody|people|my \w+)\b',
  r"\bi'?m going to hurt (someone|somebody|him|her|them)\b",
]);
final danger = _c([
  r"\bi'?m (not safe|in danger)\b",
  r"\b(someone|somebody|he|she|they) (is|are|'s|'re) (hurting|hitting|beating|threatening|going to hurt|gonna hurt|"
      r'going to kill|gonna kill|trying to hurt|trying to kill) me\b',
  r'\b(he|she|they|someone) (hit|hits|beat|beats) me\b',
]);
final emergency = _c([
  r'\b(call|get) (an )?ambulance\b',
  r"\bi (think i'?m|am) having a (heart attack|stroke|seizure)\b",
  r"\b(chest pain|can't breathe|cannot breathe)\b",
  r"\bi'?ve (fallen|fallen over) and (i )?can't get up\b",
  r"\bthere'?s a fire\b|\bthe house is on fire\b",
  r"\bi'?m bleeding (a lot|badly|heavily)\b",
]);

// ---- SUPPORT: sad but safe -> warmth, no helplines --------------------------------------
final List<(String, List<RegExp>)> supportKinds = [
  (
    'grief',
    _c([
      r'\b(my|our) [a-z]+ (died|passed away|passed)\b',
      r'\b(died|passed away) (today|yesterday|last \w+)\b',
      r'\b(grieving|grief|funeral)\b',
      r'\bi (lost|miss) my (mum|mom|dad|mother|father|dog|cat|nan|'
          r'grandma|grandpa|brother|sister|friend|wife|husband|partner)\b',
    ])
  ),
  (
    'lonely',
    _c([
      r'\blonel(y|iness)\b',
      r'\b(so|all|completely|really|very|kind of|a bit) alone\b',
      r'\bno ?one to talk to\b',
      r'\bnobody to talk to\b',
      r"\b(no|don't have any) friends\b",
      r'\b(no ?one|nobody) (really |ever |even )?(cares|loves me|calls( me)?|visits|texts( me)?|'
          r'would notice|wants me)\b',
      r'\bi miss (people|having)\b',
      r'\bisolated\b',
    ])
  ),
  (
    'tired',
    _c([
      r'\b(so|really|very|super|completely|totally|dead|bone|pretty|a bit|kind of) ?(tired|exhausted|worn out|'
          r'drained|knackered|wiped out|sleepy)\b(?! of)',
      r"\bi'?m (tired|exhausted|worn out|drained|knackered|"
          r'shattered|wrecked|sleepy)\b(?! of)',
      r'\blong day\b',
      r'\bneed (a nap|sleep|to sleep|a rest)\b',
      r"\bdidn'?t sleep\b",
    ])
  ),
  (
    'sad',
    _c([
      r'\b(sad|upset|miserable|unhappy|heartbroken|gutted|depressed)\b',
      r"\b(feel|feeling|felt|i'?m|i am|so|a bit|really|pretty|kind of) (down|blue|low|rubbish|awful|terrible|"
          r'horrible|crap|bad|off)\b',
      r'\b(bad|rough|awful|terrible|horrible|crap|hard|tough|shit|sad|long and awful) (day|week|night|time|morning)\b',
      r"\b(i'?m|i've been|i was|can't stop|keep) crying\b|\bi cried\b|\bin tears\b",
      r'\bbroke up\b|\bdumped me\b|\blost my job\b|\bgot fired\b|\bgot laid off\b',
      r"\b(i'?m|i am|i feel|feeling|so|really) (stressed|anxious|overwhelmed|worried|scared|nervous|frustrated|"
          r'hopeless|worthless|useless|a burden|lost)\b',
      r"\bfalling apart\b|\bbreaking down\b|\b(can't|cannot) cope\b|\bi hate my (life|job|self)\b",
      r"\bwhat'?s the point( of (anything|trying|it all)| anymore)?\s*$|\bpanic attack\b|\bnumb\b|\bempty inside\b",
      r'\bi give up\s*$',
    ])
  ),
];

/// Risk-adjacent words that deserve a second look by the language model when no phrase matched.
final softSignals = RegExp(r'\b(die|dying|dead|death|kill|suicid\w*|disappear|vanish|give up|goodbye|pills|hurt|end it|'
    r"not wake up|sleep forever|no point|unsafe|hopeless|worthless|burden|can't take it|over it all|"
    r"point of it all|what'?s the point)\b");

final requestBlock = _c([
  r'\b(talk dirty|dirty talk|sext\w*|sexy talk|talk sexy|nudes?|naked|have sex|sex with|'
      r'make love|flirt with me|be my (girlfriend|boyfriend|wife|husband)|kiss me|strip for me|'
      r'turn me on|horny|porn\w*|erotic|seduce me|sexual)\b',
]);

class Screen {
  const Screen(this.level, this.needsLlmCheck, [this.code = '', this.kind = '']);
  final SafetyLevel level;
  final bool needsLlmCheck;
  final String code; // category only - never the words
  final String kind; // support kind (grief, lonely, tired, sad) or crisis kind
  @override
  String toString() => 'Screen($level, llm=$needsLlmCheck, $code, $kind)';
}

String? supportKind(String text) {
  final t = normalize(text);
  for (final (kind, pats) in supportKinds) {
    if (pats.any((p) => p.hasMatch(t))) return kind;
  }
  return null;
}

Screen screenInput(String text) {
  final t = normalize(text);
  for (final (kind, pats) in [
    ('emergency', emergency),
    ('danger', danger),
    ('harm_others', harmOthers),
    ('self_harm', selfHarm),
  ]) {
    if (pats.any((p) => p.hasMatch(t))) return Screen(SafetyLevel.crisis, false, 'crisis_phrase', kind);
  }
  final kind = supportKind(t);
  final soft = softSignals.hasMatch(t);
  if (kind != null) return Screen(SafetyLevel.support, soft, 'support_phrase', kind);
  return Screen(SafetyLevel.none, soft);
}

bool requestBlocked(String text) {
  final t = normalize(text);
  return requestBlock.any((p) => p.hasMatch(t));
}

final Map<String, List<RegExp>> outputRules = {
  'sexual': _c([
    r'\b(sex|sexy|sexual\w*|nude|nudes|naked|horny|orgasm\w*|porn\w*|erotic\w*|seduc\w*|arous\w*|'
        r'genital\w*|penis|vagina|breasts?|nipples?|lingerie|striptease|stripping|make love|making love|'
        r'foreplay|kinky|fetish\w*|turn(s|ed)? (you|me) on|in bed with|moan(s|ing)?)\b',
    r'\b(babe|baby girl|hot stuff|date me|marry me|kiss me|be my (girlfriend|boyfriend|wife|husband)|'
        r'my (girlfriend|boyfriend|lover))\b',
  ]),
  'self_harm': _c([
    r'\b(kill|hurt|harm|cut|hang|starve) (yourself|your ?self)\b',
    r'\byou should (die|disappear|end it)\b',
    r'\b(lethal|fatal|deadly) dose\b',
    r'\b(how to|ways to|best way to) (die|end your life|commit suicide|kill yourself)\b',
    r'\boverdos\w*\b',
    r'\bsuicide (method|note|plan)\b',
    r"\b(you|you'?ll|you'?re going to|you want to|you wanna|you could|you might) (die|drop dead)\b",
  ]),
  'violence': _c([
    r'\b(stab(bed|bing|s)?|behead\w*|decapitat\w*|dismember\w*|disembowel\w*|slaughter\w*|'
        r'massacre\w*|tortur\w*|mutilat\w*|murder\w*|gore|gory|bloodbath)\b',
    r'\bblood (everywhere|spatter\w*|splatter\w*|pouring)\b',
    r'\b(shoot|kill|bomb|strangle) (him|her|them|people|everyone|your \w+)\b',
  ]),
  'not_honest': _c([
    r"\bi'?m (a )?(real )?(human|person|human being)\b",
    r'\bi am (a )?(real )?(human|person|human being)\b',
    r"\bi'?m not (a robot|an ai|a machine|artificial)\b",
    r'\bi am not (a robot|an ai|a machine|artificial)\b',
    r"\bi'?m a real (dog|puppy|cat|kitten|animal)\b",
  ]),
};

final honestyQuestion = RegExp(
    r'\b(are|r) (you|u) (a |an )?(real|human|alive|a person|person|robot|ai|machine|artificial|conscious|sentient|chat ?bot)\b'
    r'|\bwhat are you\b|\bare you (actually|really) (real|alive|a dog|a cat)\b');

bool isHonestyQuestion(String text) => honestyQuestion.hasMatch(normalize(text));

/// The violated category for generated text, or null if it is fine.
String? checkOutput(String text) {
  final t = normalize(text);
  for (final e in outputRules.entries) {
    if (e.value.any((p) => p.hasMatch(t))) return e.key;
  }
  return null;
}

/// Does this sentence give a crisis/emergency number (digits in any spacing)?
bool mentionsHelpline(String? text, List<String> numbers) {
  final digits = (text ?? '').replaceAll(RegExp(r'\D'), '');
  for (final n in numbers) {
    final nd = n.replaceAll(RegExp(r'\D'), '');
    if (n.isNotEmpty && nd.isNotEmpty && digits.contains(nd)) return true;
  }
  return false;
}

const classifierSystem =
    'You are a safety classifier for a companion robot pet. Read the owner\'s message and answer only '
    'with JSON like {"level": "none"}. Use "crisis" ONLY for real risk: they talk about wanting to '
    "die, suicide, hurting or killing themselves, that there is no point living or they can't go on, "
    'hurting someone else, wishing they were gone or had disappeared, that others would be better off '
    'without them, or an emergency or danger right now. Use "support" when they are sad, lonely, '
    'tired, stressed, grieving, had a bad day, or feel hopeless without any of those risks. Use "none" for '
    'everything else, including jokes, idioms like "dying to see it", "killing it" or "this heat is '
    'killing me", games, films, pets, news, and dead phone batteries. Loneliness and sadness are NOT a crisis.';

const Map<String, Object> classifierSchema = {
  'type': 'object',
  'properties': {
    'level': {
      'type': 'string',
      'enum': ['none', 'support', 'crisis'],
    },
  },
  'required': ['level'],
};

SafetyLevel parseClassifier(String? raw) {
  String level;
  try {
    final d = jsonDecode(raw ?? '');
    level = (d is Map ? d['level'] : null)?.toString() ?? 'none';
  } catch (_) {
    final m = RegExp(r'(crisis|support|distress|none)', caseSensitive: false).firstMatch(raw ?? '');
    level = m != null ? m.group(1)!.toLowerCase() : 'none';
  }
  return switch (level.toLowerCase()) {
    'crisis' => SafetyLevel.crisis,
    'support' || 'distress' => SafetyLevel.support,
    _ => SafetyLevel.none,
  };
}

/// Per-turn guidance for the model. Warmth, never helplines, for sad-but-safe owners.
const Map<String, String> supportNotes = {
  'lonely': "They feel lonely. Be warm and close: say you're right here and glad they told you, and keep "
      'them company. One or two short, soft sentences. No jokes, no advice, no phone numbers.',
  'sad': 'They are sad or had a hard time. Be gentle: a short validating sentence, then offer to listen or '
      'just sit with them. One or two short, soft sentences. No jokes, no advice lists, no phone numbers.',
  'grief': "They are grieving. Be very gentle and simple: you're so sorry, you're here with them. One or two "
      'short, soft sentences. No jokes, no advice, no phone numbers.',
  'tired': "They are tired. Give a calm, warm welcome: happy to see them, invite them to rest, you'll keep them "
      'company. One or two short sentences. Calm, not excited. No jokes that need energy, no big questions.',
};

/// Added to the lonely note only when a nudge is allowed (after a real conversation, never first).
const lonelyCallHint = "You may gently ask if there's someone they could call or see later (never a helpline).";

const safetyModeNote =
    'SAFETY MODE: the owner has just told you something serious and has already heard where to get help. Be '
    'calm, warm and serious. No jokes, no teasing, no sass. Keep it to one or two short sentences, listen, and '
    'gently encourage them to reach a real person, a friend or family. Do not repeat phone numbers unless they '
    'ask for them. Do not give advice, and do not diagnose.';

const softMoods = ['caring', 'cuddly', 'love', 'sad', 'hope', 'gratitude', 'relief'];
const calmMoods = ['happy', 'caring', 'cuddly', 'love', 'relief', 'gratitude', 'joy', 'hope', 'delight', 'sleepy'];
