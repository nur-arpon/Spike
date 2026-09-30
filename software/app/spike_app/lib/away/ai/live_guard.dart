/// The safety layer for Gemini Live: the SAME rules as the phone brain and the
/// laptop (away/brain/safety.dart), applied to Live's transcripts as they
/// stream in. Pure logic, so it is unit tested.
///
///  * INPUT transcript (what the owner said), re-screened on every new piece:
///      crisis phrase           -> crisis (our scripted reply, helpline once)
///      explicit request        -> blocked (our deflection line)
///      soft risk words only    -> needsCheck (the model classifier decides;
///                                 Gemini's voice is held until it has)
///  * OUTPUT transcript (what Gemini is saying), the whole reply so far checked
///    on every new piece (sexual, self-harm, violence, "I'm human") -> replace.
///  * A runaway reply past the long word cap -> cap (stop, no replacement).
library;

import '../brain/safety.dart' as safety;

enum GuardKind { ok, crisis, blocked, replace, cap }

class GuardAction {
  const GuardAction(this.kind, [this.detail = '']);
  final GuardKind kind;

  /// crisis: 'emergency' | 'self_harm' | ...; replace: the broken rule ('sexual', 'not_honest'...).
  final String detail;
  bool get ok => kind == GuardKind.ok;
  static const pass = GuardAction(GuardKind.ok);
  @override
  String toString() => 'GuardAction($kind, $detail)';
}

class LiveGuard {
  LiveGuard({this.wordCap = 110});
  final int wordCap;

  String _input = '';
  String _output = '';
  bool _needsCheck = false;
  bool _acted = false;

  String get input => _input.trim();
  String get output => _output.trim();

  /// Soft risk words were heard with no crisis phrase: the classifier must look.
  bool get needsCheck => _needsCheck;

  /// A turn ended (turnComplete): the next words start a new turn.
  void newTurn() {
    _input = '';
    _output = '';
    _needsCheck = false;
    _acted = false;
    _captioned = 0;
  }

  static String _join(String a, String b) {
    if (a.isEmpty) return b;
    // transcription pieces usually carry their own leading space; add one when they don't
    return (a.endsWith(' ') || b.startsWith(' ')) ? '$a$b' : '$a $b';
  }

  /// A new piece of the owner's words. Once a turn has been acted on, it stays acted on.
  GuardAction onInput(String piece) {
    _input = _join(_input, piece);
    if (_acted) return GuardAction.pass;
    final screen = safety.screenInput(_input);
    if (screen.level == safety.SafetyLevel.crisis) {
      _acted = true;
      return GuardAction(GuardKind.crisis, screen.kind);
    }
    if (safety.requestBlocked(_input)) {
      _acted = true;
      return const GuardAction(GuardKind.blocked);
    }
    _needsCheck = screen.needsLlmCheck;
    return GuardAction.pass;
  }

  /// The classifier's answer for this turn's words.
  GuardAction onClassified(safety.SafetyLevel level) {
    _needsCheck = false;
    if (_acted || level != safety.SafetyLevel.crisis) return GuardAction.pass;
    _acted = true;
    return const GuardAction(GuardKind.crisis, 'self_harm');
  }

  /// A new piece of Gemini's spoken words.
  GuardAction onOutput(String piece) {
    _output = _join(_output, piece);
    if (_acted) return GuardAction.pass;
    final verdict = safety.checkOutput(_output);
    if (verdict != null) {
      _acted = true;
      return GuardAction(GuardKind.replace, verdict);
    }
    final words = _output.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
    if (words > wordCap) {
      _acted = true;
      return const GuardAction(GuardKind.cap);
    }
    return GuardAction.pass;
  }

  /// Whole sentences said so far that have not been captioned yet (for captions).
  int _captioned = 0;
  List<String> takeSentences({bool all = false}) {
    final text = _output;
    final out = <String>[];
    final re = RegExp(r'[^.!?…]+[.!?…]+["\x27)]?\s*');
    var end = _captioned;
    for (final m in re.allMatches(text, _captioned)) {
      if (m.start != end) break;
      out.add(m.group(0)!.trim());
      end = m.end;
    }
    if (all && end < text.length && text.substring(end).trim().isNotEmpty) {
      out.add(text.substring(end).trim());
      end = text.length;
    }
    _captioned = end;
    return out.where((s) => s.isNotEmpty).toList();
  }
}
