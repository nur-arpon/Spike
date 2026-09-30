"""Wake words: "Spike", "Hey Buddy" (dog) and "Spicy" (cat), plus any personal
extras the owner adds on his own laptop ([wake] personal_file, git-ignored).

None of these has a stock openWakeWord model, and a personal name may not
even be an English word, so wake-up is two independent checks that must agree:

1. VoskSpotter - Vosk small-en with a tiny grammar (the alias phrases from
   the persona files + "[unk]"). Streaming, CPU, ~2 % of a core. Anything
   that is not an alias is pushed into [unk], which is what keeps false
   wakes low. Gives a word confidence.
2. WakeMatcher - rapidfuzz on the Whisper transcript of the same audio:
   the wake word must be at the START or the END of the utterance
   ("Spike, what's the time" / "what's the time, Spike"), not in the middle
   of a sentence about Spike.

The listener accepts a wake when Vosk is very sure, or when Vosk is fairly
sure and Whisper agrees (thresholds in config [wake]).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

log = logging.getLogger("spike.wake")


def _norm(text: str) -> str:
    t = (text or "").lower().replace("’", "'")
    t = re.sub(r"[^a-z' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class WakeMatch:
    wake_word: str        # canonical, e.g. "Hey Buddy"
    mode: str             # dog | cat
    score: float          # 0..100
    rest: str             # the request with the wake phrase removed
    where: str            # start | end | only


_GREETINGS = {"hey", "hi", "ok", "okay", "oi", "yo", "hello"}


class WakeMatcher:
    """Fuzzy wake-word matching on text (Whisper transcripts or typed input).

    Aliases that are ordinary English words ("spicy", "spike") only count
    when said like a name: followed by a pause/punctuation ("Spicy, what's
    up?"), alone ("Spicy!"), or after a comma at the end ("what's up,
    spicy?"). "Spicy food is great" does not wake her."""

    def __init__(self, aliases_by_mode: dict[str, dict[str, list[str]]], threshold: float = 80,
                 vocative_only: set[str] | None = None):
        # aliases_by_mode = {"dog": {"Spike": ["spike", "hey spike", ...], ...}, "cat": {...}}
        self.threshold = threshold
        self.vocative_only = {_norm(v) for v in (vocative_only or set())}
        self.entries: list[tuple[str, str, str]] = []      # (alias, canonical, mode)
        for mode, table in aliases_by_mode.items():
            for canonical, aliases in table.items():
                for a in {_norm(canonical), *(_norm(x) for x in aliases)}:
                    if a:
                        self.entries.append((a, canonical, mode))
        self.entries.sort(key=lambda e: -len(e[0].split()))

    def _best(self, words: list[str]) -> tuple[str, str, float, int, str] | None:
        """Best alias matching words[0:n] -> (canonical, mode, score, n, alias)."""
        best = None
        for alias, canonical, mode in self.entries:
            n = len(alias.split())
            if n > len(words):
                continue
            if n > 1 and alias.split()[0] in _GREETINGS and words[0] != alias.split()[0]:
                continue                  # "the spicy" must not pass for "hey spicy"
            cand = " ".join(words[:n])
            s = fuzz.ratio(cand, alias)
            # short aliases must match tighter ("spike" vs "spite"/"like")
            need = self.threshold + (8 if len(alias) <= 5 else 0)
            if s >= need and (best is None or s > best[2] or (s == best[2] and n > best[3])):
                best = (canonical, mode, s, n, alias)
        return best

    def match(self, text: str, allow_end: bool = True) -> WakeMatch | None:
        words, pause = _tokens(text)
        if not words:
            return None
        lead = 0
        while lead < len(words) - 1 and words[lead] in ("hey", "hi", "oi", "ok", "okay", "yo", "um", "uh", "so"):
            lead += 1
        # start: allow a greeting word before the name ("hey spike")
        for start in sorted({0, lead}):
            b = self._best(words[start:start + 3])
            if not b:
                continue
            canonical, mode, score, n, alias = b
            last = start + n - 1
            if alias in self.vocative_only and start == 0 and last < len(words) - 1 and not pause[last]:
                continue                              # "spicy food..." - a word, not her name
            rest = " ".join(words[start + n:])
            return WakeMatch(canonical, mode, score, _restore(text, rest), "only" if not rest else "start")
        if allow_end and len(words) >= 2:
            for n in (3, 2, 1):
                if n >= len(words):
                    continue
                b = self._best(words[-n:])
                if not (b and b[3] == n):
                    continue
                canonical, mode, score, _, alias = b
                if alias in self.vocative_only and not pause[len(words) - n - 1]:
                    continue                          # "...the spicy" is not "..., Spicy"
                rest = " ".join(words[:-n])
                return WakeMatch(canonical, mode, score, _restore(text, rest), "end")
        return None


def _tokens(text: str) -> tuple[list[str], list[bool]]:
    """Words, and for each word whether a pause (punctuation) follows it."""
    toks = re.findall(r"[a-z']+|[,.!?;:…—]", (text or "").lower().replace("’", "'"))
    words: list[str] = []
    pause: list[bool] = []
    for t in toks:
        if t[0].isalpha() or t[0] == "'":
            w = t.strip("'")
            if w:
                words.append(w)
                pause.append(False)
        elif words:
            pause[-1] = True
    return words, pause


def _restore(original: str, lowered_rest: str) -> str:
    """Give back the request in the original casing/punctuation where possible."""
    if not lowered_rest:
        return ""
    words = lowered_rest.split()
    pat = r"\W*".join(re.escape(w) for w in words)
    m = re.search(pat, original, re.I)
    return original[m.start():m.end()].strip(" ,.!?") if m else lowered_rest


@dataclass
class VoskHit:
    phrase: str            # grammar phrase heard, e.g. "hey buddy"
    canonical: str
    mode: str
    conf: float            # 0..1 (0 for partial results)
    start_s: float         # seconds since this recognizer started
    end_s: float
    final: bool
    words_after: int       # [unk] words after the wake phrase in this result
    words_before: int = 0  # words before it (a name in mid-sentence is not a call)


class VoskSpotter:
    """Grammar-constrained Vosk keyword spotter over 16 kHz int16 frames."""

    def __init__(self, model_dir: Path | str, aliases_by_mode: dict[str, dict[str, list[str]]]):
        import vosk
        vosk.SetLogLevel(-1)
        self.model = vosk.Model(str(model_dir))
        self.phrase_map: dict[str, tuple[str, str]] = {}
        for mode, table in aliases_by_mode.items():
            for canonical, aliases in table.items():
                for a in {_norm(canonical), *(_norm(x) for x in aliases)}:
                    self.phrase_map.setdefault(a, (canonical, mode))
        self.grammar = self._in_vocab(sorted(self.phrase_map))
        log.info("wake grammar: %s", ", ".join(self.grammar))
        self.samples = 0
        self._new()

    def _in_vocab(self, phrases: list[str]) -> list[str]:
        """Keep phrases whose every word is in the Vosk dictionary (Vosk silently
        drops unknown grammar words, which would make a phrase match anything)."""
        words = sorted({w for p in phrases for w in p.split()})
        missing = {w for w in words if self.model.vosk_model_find_word(w) < 0}
        self.missing_words = sorted(missing)
        return [p for p in phrases if not (set(p.split()) & missing)]

    def _new(self) -> None:
        import vosk
        self.rec = vosk.KaldiRecognizer(self.model, 16000, json.dumps(self.grammar + ["[unk]"]))
        self.rec.SetWords(True)
        self.rec.SetPartialWords(True)
        self.offset_s = self.samples / 16000.0
        self.partial_seen: str | None = None

    def reset(self) -> None:
        self._new()

    def feed(self, frame_bytes: bytes) -> VoskHit | None:
        """Feed 16-bit mono PCM. Returns a hit (partial first, then final) or None."""
        self.samples += len(frame_bytes) // 2
        if self.rec.AcceptWaveform(frame_bytes):
            res = json.loads(self.rec.Result())
            hit = self._scan(res.get("result", []), final=True)
            self.partial_seen = None
            return hit
        res = json.loads(self.rec.PartialResult())
        words = res.get("partial_result") or []
        if not words and res.get("partial"):
            words = [{"word": w, "conf": 0.0, "start": 0.0, "end": 0.0} for w in res["partial"].split()]
        hit = self._scan(words, final=False)
        if hit and hit.phrase != self.partial_seen:
            self.partial_seen = hit.phrase
            return hit
        return None

    def _scan(self, words: list[dict], final: bool) -> VoskHit | None:
        toks = [w.get("word", "") for w in words]
        for n in (3, 2, 1):
            for i in range(0, len(toks) - n + 1):
                phrase = " ".join(toks[i:i + n])
                if phrase in self.phrase_map:
                    canonical, mode = self.phrase_map[phrase]
                    seg = words[i:i + n]
                    conf = min(float(w.get("conf", 0.0)) for w in seg) if final else 0.0
                    after = sum(1 for t in toks[i + n:] if t)
                    return VoskHit(phrase, canonical, mode, conf,
                                   self.offset_s + float(seg[0].get("start", 0.0)),
                                   self.offset_s + float(seg[-1].get("end", 0.0)), final, after,
                                   words_before=sum(1 for t in toks[:i] if t))
        return None
