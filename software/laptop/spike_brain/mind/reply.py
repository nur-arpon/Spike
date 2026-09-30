"""Reply format: "[mood:NAME] [action:NAME] spoken words".

The model is asked for that strict tag prefix (streaming-friendly: the mood
arrives before the first word, so the face changes before Spike speaks).
Models slip, so everything here is a fallback parser too: tags anywhere,
bare "[happy]" tags, "Mood: happy" lines, *stage directions*, synonyms
("confused" -> confusion), <think> blocks, emoji and markdown.

StreamParser turns a token stream into events:
  ("tags", mood|None, action|None)   once, before any speech
  ("sentence", text)                 speakable chunks, in order
  ("action", name)                   an action found later in the text
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..capabilities import available, is_available
from ..protocol import ACTIONS, MOODS

# Moods offered to the model (a readable subset; the parser accepts all MOODS).
LLM_MOODS = ("happy", "excited", "love", "laughing", "playful", "curious", "sad", "caring",
             "sleepy", "proud", "embarrassed", "cuddly", "surprised", "sulking", "mischief",
             "smugness", "confusion", "shyness", "gratitude", "relief", "begging", "delight",
             "joy", "hope", "silliness", "jealousy", "suspicion", "nervousness", "awe", "bored",
             "cuteAngry", "determination")
# Only what the real body can do is offered to the model (capabilities.py hides the rest).
LLM_ACTIONS = available(("headTilt", "tailWagDance", "zoomies", "playBow", "rollOver", "sniffAround", "yawn",
                         "beggingAction", "sneeze", "snuggle", "slowWag"))
# Big, bouncy actions: wrong for a sad, lonely or tired owner.
ENERGETIC_ACTIONS = ("tailWagDance", "zoomies", "playBow", "rollOver", "beggingAction", "sniffAround",
                     "sneeze", "pant", "hiccup")
ENERGETIC_MOODS = ("excited", "laughing", "playful", "silliness", "mischief", "smugness", "surprised",
                   "wakeupAlarm", "cuteAngry", "jealousy", "suspicion", "bored", "sulking", "hungry", "awe",
                   "determination", "anger", "frustration", "disgust", "dizzy", "neutral")

_MOOD_LC = {m.lower(): m for m in MOODS}
_ACTION_LC = {a.lower(): a for a in ACTIONS}

MOOD_SYNONYMS = {
    "confused": "confusion", "shy": "shyness", "grateful": "gratitude", "thankful": "gratitude",
    "smug": "smugness", "sassy": "smugness", "sass": "smugness", "unimpressed": "smugness", "silly": "silliness", "goofy": "silliness",
    "jealous": "jealousy", "suspicious": "suspicion", "nervous": "nervousness", "worried": "nervousness",
    "anxious": "nervousness", "determined": "determination", "angry": "cuteAngry", "mad": "cuteAngry",
    "annoyed": "cuteAngry", "grumpy": "cuteAngry", "cute_angry": "cuteAngry", "lonely": "loneliness",
    "tired": "sleepy", "drowsy": "sleepy", "asleep": "sleeping", "loving": "love", "affectionate": "love",
    "teasing": "playful", "cheeky": "mischief", "mischievous": "mischief", "naughty": "mischief",
    "calm": "neutral", "content": "cuddly", "cozy": "cuddly", "cosy": "cuddly", "snuggly": "cuddly",
    "warm": "caring", "gentle": "caring", "concerned": "caring", "sympathetic": "caring",
    "empathetic": "caring", "kind": "caring", "supportive": "caring", "thinking": "curious",
    "thoughtful": "curious", "interested": "curious", "amazed": "awe", "wonder": "awe",
    "happy_excited": "excited", "thrilled": "excited", "glad": "happy", "cheerful": "happy",
    "funny": "laughing", "amused": "laughing", "giggly": "laughing", "hopeful": "hope",
    "relieved": "relief", "scared_": "scared", "afraid": "scared", "frightened": "scared",
    "sorry": "embarrassed", "sheepish": "embarrassed", "pleading": "begging", "sulky": "sulking",
    "pouting": "sulking", "sulk": "sulking", "bored_": "bored", "proud_": "proud", "surprise": "surprised",
    "shocked": "surprised", "delighted": "delight", "joyful": "joy", "sad_": "sad", "unhappy": "sad",
    "grieving": "grief", "hungry_": "hungry", "disgusted": "disgust", "frustrated": "frustration",
}
ACTION_SYNONYMS = {
    "head_tilt": "headTilt", "tilt": "headTilt", "tilthead": "headTilt", "tilts head": "headTilt",
    "wag": "tailWagDance", "tailwag": "tailWagDance", "wags tail": "tailWagDance", "dance": "tailWagDance",
    "happy dance": "tailWagDance", "zoom": "zoomies", "play_bow": "playBow", "bow": "playBow",
    "roll": "rollOver", "roll_over": "rollOver", "rolls over": "rollOver", "sniff": "sniffAround",
    "sniffs": "sniffAround", "sniff_around": "sniffAround", "beg": "beggingAction", "begs": "beggingAction",
    "begging": "beggingAction", "yawns": "yawn", "sneezes": "sneeze", "pants": "pant", "shivers": "shiver",
    "hiccups": "hiccup", "none": "", "no": "", "null": "",
    "snuggles": "snuggle", "cuddle": "snuggle", "lean in": "snuggle", "leanin": "snuggle", "nuzzle": "snuggle",
    "slow wag": "slowWag", "slow_wag": "slowWag", "slowwag": "slowWag", "gentle wag": "slowWag",
}

# stage-direction keywords -> action (for "*wags tail*")
_STAGE_ACTIONS = (("snuggle", "snuggle"), ("cuddle", "snuggle"), ("nuzzle", "snuggle"), ("lean", "snuggle"),
                  ("slow", "slowWag"), ("wag", "tailWagDance"), ("tilt", "headTilt"), ("yawn", "yawn"),
                  ("sniff", "sniffAround"), ("zoom", "zoomies"), ("roll", "rollOver"),
                  ("bow", "playBow"), ("beg", "beggingAction"), ("sneeze", "sneeze"),
                  ("pant", "pant"), ("dance", "tailWagDance"), ("spin", "zoomies"))

TAG_RE = re.compile(r"\[\s*(mood|action|emotion|face)\s*[:=]\s*([^\]\[]{0,40}?)\s*\]", re.I)
BARE_TAG_RE = re.compile(r"\[\s*([A-Za-z_ ]{2,30})\s*\]")
PIPE_TAG_RE = re.compile(r"\[\s*([A-Za-z_ ]{2,30}?)\s*\|\s*([A-Za-z_ ]{0,30}?)\s*\]")   # [mood|action]
# the format placeholders themselves, copied by the model ("[mood] You want to work?")
ANY_TAG_RE = re.compile(r"\[\s*[A-Za-z_]{2,20}(\s*\|\s*[A-Za-z_]{0,20})?\s*\]")
PLACEHOLDER_RE = re.compile(r"\[\s*(mood|action|name|tag|emotion)\s*(\|\s*(action|name))?\s*\]", re.I)
LINE_TAG_RE = re.compile(r"^\s*(mood|action)\s*[:=]\s*([A-Za-z_]+)\s*$", re.I | re.M)
THINK_RE = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)
STAGE_RE = re.compile(r"\*([^*\n]{1,60})\*|\(([a-z][^()\n]{1,40})\)")
# A *starred* bit is a stage direction only if it describes doing something
# ("*wags tail*", "*purrs*"); otherwise it is emphasis ("too *wet*") and the
# word must stay in the speech - dropping it once ate a punchline.
STAGE_VERBS = re.compile(r"\b(wags?|wagging|purrs?|purring|sighs?|giggles?|tilts?|rolls?|yawns?|sniffs?|blinks?|"
                         r"stretch(es)?|laughs?|winks?|nuzzles?|snuggles?|cuddles?|hiss(es)?|meows?|barks?|whines?|"
                         r"spins?|jumps?|bounces?|licks?|paws?|flicks?|smirks?|grins?|beeps?|boops?|leans?|curls?|"
                         r"looks? (away|up|at)|pretends?|ignores?|knocks?|zooms?|blushes|sits?|lies? down|"
                         r"tail|ears?|head)\b", re.I)


def _stage(m: re.Match) -> str:
    inner = m.group(1) or m.group(2) or ""
    return " " if STAGE_VERBS.search(inner) else " " + inner + " "
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF‍️]")
BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
MD_RE = re.compile(r"(\*\*|__|`|^#+\s*|^\s*[-*]\s+)", re.M)


def normalize_mood(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower().replace("-", "_")
    if key in _MOOD_LC:
        return _MOOD_LC[key]
    if key.replace("_", "") in _MOOD_LC:
        return _MOOD_LC[key.replace("_", "")]
    syn = MOOD_SYNONYMS.get(key) or MOOD_SYNONYMS.get(key + "_")
    return syn if syn else None


def normalize_action(name: str | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    if key in _ACTION_LC:
        found = _ACTION_LC[key]
    else:
        k2 = key.replace(" ", "").replace("_", "").replace("-", "")
        if k2 in _ACTION_LC:
            found = _ACTION_LC[k2]
        else:
            found = ACTION_SYNONYMS.get(key, ACTION_SYNONYMS.get(key.replace(" ", "_")))
    # capabilities.py: an action the body cannot do is never parsed out of a reply
    return found if found and is_available(found) else None


def stage_to_action(direction: str) -> str | None:
    d = direction.lower()
    for word, action in _STAGE_ACTIONS:
        if word in d:
            return action if is_available(action) else None
    return None


PET_NAMES = re.compile(r"\s*,?\s*\b(sweetie|sweetheart|honey|darling|babe|my dear|my love|love bug|"
                       r"my (poor |sweet |dear |little )?(girl|boy))\b(?=[\s,.!?]|$)", re.I)


def strip_pet_names(text: str) -> str:
    """'Oh sweetie, that sounds heavy.' -> 'Oh, that sounds heavy.' - Spike and Spicy
    never use romantic pet names (and never guess the owner's gender)."""
    if not PET_NAMES.search(text):
        return text
    out = re.sub(r"\b(Oh|Aw|Aww|Hey|Hi)\s+(sweetie|sweetheart|honey|darling|babe|"
                 r"my (poor |sweet |dear |little )?(girl|boy))\b,?", r"\1,", text, flags=re.I)
    out = PET_NAMES.sub("", out)
    out = re.sub(r"^\s*[,.]\s*", "", out)
    out = re.sub(r",\s*([.!?])", r"\1", out)                # "Aww honey." -> "Aww."
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out[:1].upper() + out[1:]


def clean_speech(text: str) -> str:
    """Make text safe and pleasant to speak: no tags, emoji, markdown, stage directions."""
    text = THINK_RE.sub(" ", text)
    text = TAG_RE.sub(" ", text)
    text = PIPE_TAG_RE.sub(" ", text)
    text = PLACEHOLDER_RE.sub(" ", text)
    text = ANY_TAG_RE.sub(" ", text)                 # an invented "[sass]" / "[laughs]" is never spoken
    text = BOLD_RE.sub(r"\2", text)
    text = STAGE_RE.sub(_stage, text)
    text = EMOJI_RE.sub("", text)
    text = MD_RE.sub("", text)
    text = text.replace("*", " ").replace("#", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,!?;:]|\.(?!\.))", r"\1", text)      # "wet ." -> "wet." (but keep " ...Fine")
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


@dataclass
class ParsedReply:
    mood: str | None
    action: str | None
    text: str


def guess_mood(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("sorry", "sad", "hug", "here for you", "rough")):
        return "caring"
    if any(w in t for w in ("haha", "hehe", "lol", "joke")):
        return "laughing"
    if "!" in t:
        return "happy"
    if t.rstrip().endswith("?"):
        return "curious"
    return "happy"


def parse_reply(raw: str) -> ParsedReply:
    """Parse a complete reply (scripted lines and non-streamed model output)."""
    raw = BOLD_RE.sub(r"\2", THINK_RE.sub(" ", raw or ""))
    mood = action = None
    for kind, val in TAG_RE.findall(raw):
        k = kind.lower()
        if k in ("mood", "emotion", "face") and mood is None:
            mood = normalize_mood(val)
        elif k == "action" and action is None:
            action = normalize_action(val)
    for kind, val in LINE_TAG_RE.findall(raw):
        if kind.lower() == "mood" and mood is None:
            mood = normalize_mood(val)
        elif kind.lower() == "action" and action is None:
            action = normalize_action(val)
    raw = LINE_TAG_RE.sub(" ", raw)

    # compact [mood|action] tags (the format the prompt asks for)
    def pipe(m: re.Match) -> str:
        nonlocal mood, action
        if normalize_mood(m.group(1)) or normalize_action(m.group(2)):
            mood = mood or normalize_mood(m.group(1))
            action = action or normalize_action(m.group(2))
            return " "
        return m.group(0)
    raw = PIPE_TAG_RE.sub(pipe, raw)

    # bare [happy] / [headTilt] tags
    def bare(m: re.Match) -> str:
        nonlocal mood, action
        word = m.group(1)
        if mood is None and normalize_mood(word):
            mood = normalize_mood(word)
            return " "
        if action is None and normalize_action(word):
            action = normalize_action(word)
            return " "
        return m.group(0)
    raw = BARE_TAG_RE.sub(bare, raw)
    for star, paren in STAGE_RE.findall(raw):
        a = stage_to_action(star or paren)
        if a and action is None:
            action = a
    text = clean_speech(raw)
    return ParsedReply(mood=mood, action=action, text=text)


_ABBREV = ("mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "etc.", "e.g.", "i.e.", "a.m.", "p.m.", "no.")
_BOUNDARY = re.compile(r"([.!?…]+[\"')\]]*)(\s+)")
_SOFT_BOUNDARY = re.compile(r"[,;:—]\s")


def split_sentences(text: str, first: bool, first_min_words: int = 4, max_chars: int = 220) -> tuple[list[str], str]:
    """Cut complete chunks off the front of `text`; returns (chunks, remainder).

    A chunk ends at . ! ? ... followed by whitespace (not after abbreviations
    or inside numbers like 7.30). The very first chunk of a reply may also
    end at a comma/semicolon/dash once it has `first_min_words` words, so
    speech starts sooner. Over-long chunks are cut at the last comma/space."""
    chunks: list[str] = []
    while True:
        cut = None
        for m in _BOUNDARY.finditer(text):
            head = text[:m.end(1)]
            tail_word = head.split()[-1].lower() if head.split() else ""
            if tail_word in _ABBREV:
                continue
            if re.search(r"\d\.$", head) and re.match(r"\d", text[m.end():m.end() + 1] or ""):
                continue
            cut = m.end(1)
            break
        if cut is None and first and not chunks:
            for m in _SOFT_BOUNDARY.finditer(text):
                if len(text[:m.start()].split()) >= first_min_words:
                    cut = m.start() + 1
                    break
        if cut is None and len(text) > max_chars:
            window = text[:max_chars]
            cut = max(window.rfind(", "), window.rfind(" "))
            cut = cut + 1 if cut > 20 else max_chars
        if cut is None:
            return chunks, text
        piece = text[:cut].strip()
        text = text[cut:].lstrip()
        if piece:
            chunks.append(piece)
        first = first and not chunks


class StreamParser:
    """Incremental parser for a streamed reply. Feed tokens, get events."""

    def __init__(self, first_chunk_min_words: int = 4, max_chunk_chars: int = 220):
        self.first_min = first_chunk_min_words
        self.max_chars = max_chunk_chars
        self.buf = ""
        self.header_done = False
        self.mood: str | None = None
        self.action: str | None = None
        self.sentences = 0
        self.full = ""

    def _header(self, final: bool) -> list[tuple]:
        """Consume leading tags / think blocks. Returns events once the header ends."""
        while True:
            s = self.buf.lstrip()
            low = s.lower()
            if not final and s and "<think>".startswith(low):
                return []                          # maybe the start of a <think> block
            if low.startswith("<think>"):
                end = low.find("</think>")
                if end < 0:
                    return [] if not final else self._end_header("")
                self.buf = s[end + 8:]
                continue
            if s.startswith("["):
                close = s.find("]")
                if close < 0:
                    if len(s) > 48 or final:     # not a tag after all
                        return self._end_header(s)
                    return []
                tag = s[:close + 1]
                m = TAG_RE.fullmatch(tag)
                b = BARE_TAG_RE.fullmatch(tag)
                pm = PIPE_TAG_RE.fullmatch(tag)
                if pm and (normalize_mood(pm.group(1)) or normalize_action(pm.group(2))):
                    self.mood = self.mood or normalize_mood(pm.group(1))
                    self.action = self.action or normalize_action(pm.group(2))
                elif m:
                    k, v = m.group(1).lower(), m.group(2)
                    if k == "action":
                        self.action = self.action or normalize_action(v)
                    else:
                        self.mood = self.mood or normalize_mood(v)
                elif PLACEHOLDER_RE.fullmatch(tag):
                    pass                           # "[mood]" copied from the prompt: drop it
                elif b and (normalize_mood(b.group(1)) or normalize_action(b.group(1))):
                    if normalize_mood(b.group(1)) and not self.mood:
                        self.mood = normalize_mood(b.group(1))
                    elif normalize_action(b.group(1)) and not self.action:
                        self.action = normalize_action(b.group(1))
                elif b and len(b.group(1).split()) <= 2:
                    pass                           # an invented tag ("[sass]"): never speak it
                else:
                    return self._end_header(s)
                self.buf = s[close + 1:]
                continue
            m = LINE_TAG_RE.match(s)
            if m and "\n" in s:
                if m.group(1).lower() == "mood":
                    self.mood = self.mood or normalize_mood(m.group(2))
                else:
                    self.action = self.action or normalize_action(m.group(2))
                self.buf = s[m.end():]
                continue
            if not s:
                return [] if not final else self._end_header("")
            if re.match(r"^(mood|action)\s*[:=]?\s*[A-Za-z_]*$", s, re.I) and not final:
                return []                          # might become a "Mood: happy" line
            return self._end_header(s)

    def _end_header(self, rest: str) -> list[tuple]:
        self.header_done = True
        self.buf = rest
        return [("tags", self.mood, self.action)]

    def feed(self, token: str) -> list[tuple]:
        self.full += token
        self.buf += token
        events: list[tuple] = []
        if not self.header_done:
            events += self._header(final=False)
            if not self.header_done:
                return events
        events += self._body(final=False)
        return events

    def finish(self) -> list[tuple]:
        events: list[tuple] = []
        if not self.header_done:
            events += self._header(final=True)
        events += self._body(final=True)
        return events

    def _body(self, final: bool) -> list[tuple]:
        events: list[tuple] = []
        # hold back an unfinished stage direction / tag / think block
        text = self.buf
        if not final:
            for opener, closer in (("*", "*"), ("[", "]"), ("<think>", "</think>")):
                i = text.rfind(opener) if opener != "*" else _unclosed_star(text)
                if i >= 0 and closer not in text[i + len(opener):]:
                    text = text[:i]
                    break
        held = self.buf[len(text):]
        # later tags / stage directions -> actions
        for kind, val in TAG_RE.findall(text):
            if kind.lower() == "action":
                a = normalize_action(val)
                if a:
                    events.append(("action", a))
        for star, paren in STAGE_RE.findall(text):
            a = stage_to_action(star or paren)
            if a:
                events.append(("action", a))
        text = THINK_RE.sub(" ", text)
        text = TAG_RE.sub(" ", text)
        text = PIPE_TAG_RE.sub(" ", text)
        text = PLACEHOLDER_RE.sub(" ", text)
        text = BOLD_RE.sub(r"\2", text)
        text = STAGE_RE.sub(_stage, text)
        chunks, rest = split_sentences(text, first=self.sentences == 0,
                                       first_min_words=self.first_min, max_chars=self.max_chars)
        if final:
            rest_clean = clean_speech(rest + held)
            if rest_clean:
                chunks.append(rest_clean)
            rest, held = "", ""
        for c in chunks:
            c = clean_speech(c)
            if c and re.search(r"[A-Za-z0-9]", c):
                events.append(("sentence", c))
                self.sentences += 1
        self.buf = rest + held
        return events


def _unclosed_star(text: str) -> int:
    """Index of a '*' that opens a stage direction not yet closed, else -1."""
    idx = [i for i, ch in enumerate(text) if ch == "*"]
    return idx[-1] if len(idx) % 2 == 1 else -1
