/// Scripted lines that only exist away from home (the phone brain), in the
/// same "[mood:x] words" format as the persona files. Everything else Spike
/// and Spicy say comes from the persona files themselves (assets/brain/*.toml,
/// copies of the laptop's), so the crisis and emergency lines are identical.
library;

const Map<String, Map<String, List<String>>> awayLines = {
  // Free-tier quota or rate limit (owner decision 29 Sep: a friendly in-character line, never an error)
  'rate_limited': {
    'dog': ["[mood:sleepy] I'm a bit tired, let's chat in a little while."],
    'cat': ["[mood:sleepy] I'm a bit tired. Let's chat in a little while... maybe."],
  },
  // No AI key and no offline brain yet: he can still do everything the body can
  'no_brain': {
    'dog': ["[mood:embarrassed] My thinking bit stayed at home. Give me a key in Settings and I'll chat all day!"],
    'cat': ["[mood:smugness] My big brain is at home. Put a key in Settings, then we'll talk."],
  },
  // The key stopped working (revoked, typo): the owner fixes it in Settings
  'bad_key': {
    'dog': ["[mood:confusion] Hmm, my brain key isn't working. Can you check it in Settings?"],
    'cat': ["[mood:suspicion] My brain key isn't working. Settings, please. Chop chop."],
  },
  // Alarms and reminders are kept by the home brain (it rings them even when the phone is off)
  'timers_away': {
    'dog': ["[mood:curious] I keep alarms and reminders on my home brain. Ask me again when we're home!"],
    'cat': ["[mood:smugness] Alarms live on my home brain. Ask me when we're back."],
  },
};

String awayLine(String key, String mode, int pick) {
  final options = awayLines[key]?[mode] ?? awayLines[key]?['dog'] ?? const ['[mood:neutral] ...'];
  return options[pick % options.length];
}
