"""Spike's voice chain: which engine says a line, and what happens when one fails.

For every sentence the chain tries, in order, and uses the first that works:

  1. the owner's own recording of that scripted line (future; by line id)
  2. a cached Chatterbox Turbo clip (pre-rendered, best of several takes)
  3. live Chatterbox Turbo (the worker process, speech/turbo.py)
  4. Kokoro (am_puck for Spike, af_heart for Spicy; CPU)
  5. Piper Amy (CPU, the last resort)

so he never goes silent. Every result is brought to the same sample rate
(24 kHz) and the same loudness, so a fallback does not jump in volume.

Turbo is given the owner's picked settings (DESIGN.md "Voice"): the persona's
reference clip, seed 1234, a style tag from the mood ([happy], [sarcastic])
and at most ONE non-verbal sound per reply ([laugh], [chuckle], [sigh],
[gasp]). Fillers like "umm" are never typed in (postmortem.md).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .tts import Speech, mouth_envelope, resample_int16

log = logging.getLogger("spike.voice")

OUT_RATE = 24000                      # Turbo and Kokoro both make 24 kHz; Piper is resampled up
TURBO_SOUNDS = ("laugh", "chuckle", "sigh", "gasp", "cough", "clear throat", "sniff", "groan", "shush")
TURBO_STYLES = ("happy", "sarcastic", "angry", "fear", "surprised", "whispering", "crying", "dramatic",
                "narration", "advertisement")
ENGINES = ("turbo", "kokoro", "piper", "gemini")      # gemini: the desktop light brain (speech/gemini_tts.py)
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+(?=[A-Z\"'(])")


# --------------------------------------------------------------------------- Turbo text
@dataclass
class TurboStyle:
    """Per-persona mapping from the brain's moods to Turbo's tags (persona TOML [voice.turbo])."""
    style: dict[str, str] = field(default_factory=dict)      # mood -> style tag name
    sounds: dict[str, str] = field(default_factory=dict)     # mood -> non-verbal sound name

    @classmethod
    def from_config(cls, turbo_cfg: dict) -> "TurboStyle":
        style: dict[str, str] = {}
        for tag, moods in (turbo_cfg.get("style") or {}).items():
            if tag not in TURBO_STYLES:
                raise ValueError(f"unknown Turbo style tag [{tag}] (allowed: {', '.join(TURBO_STYLES)})")
            for m in moods:
                style[str(m)] = tag
        sounds = {}
        for mood, sound in (turbo_cfg.get("sounds") or {}).items():
            if sound not in TURBO_SOUNDS:
                raise ValueError(f"unknown Turbo sound [{sound}] (allowed: {', '.join(TURBO_SOUNDS)})")
            sounds[str(mood)] = sound
        return cls(style, sounds)


def turbo_text(text: str, mood: str | None, style: TurboStyle, soft: bool = False, first: bool = True) -> str:
    """The exact string Turbo is asked to say for one sentence.

    - soft (a sad, lonely or tired owner, a crisis): no tags at all, plain and calm.
    - one style tag at the start when the mood maps to one (Spike B / Spicy C settings).
    - one non-verbal sound per reply (only on its first segment): after the first sentence
      when the segment has more than one, else at the start ("[laugh] I meant to do that.").
    """
    text = " ".join(text.split())
    if soft or not mood or not text:
        return text
    sound = style.sounds.get(mood) if first else None
    if sound:
        parts = _SENTENCE_END.split(text, maxsplit=1)
        text = f"{parts[0]} [{sound}] {parts[1]}" if len(parts) == 2 else f"[{sound}] {text}"
    tag = style.style.get(mood)
    return f"[{tag}] {text}" if tag else text


def say_as(text: str, table: dict[str, str] | None) -> str:
    """Replace whole numbers the voice must say a certain way ("000" -> "triple zero").
    Only standalone tokens: "000" in "10000" is left alone."""
    for written, spoken in (table or {}).items():
        text = re.sub(rf"(?<![\w]){re.escape(written)}(?![\w])", spoken, text)
    return text


def cache_key(persona: str, spoken: str) -> str:
    """Cache entries are found by persona + the exact Turbo text (tags included)."""
    norm = " ".join(spoken.split()).strip()
    return hashlib.sha1(f"{persona}\n{norm}".encode("utf-8")).hexdigest()[:20]


# --------------------------------------------------------------------------- audio helpers
def level(pcm: np.ndarray, rate: int, target_dbfs: float = -20.0, peak: float = 0.89) -> np.ndarray:
    """Same loudness for every engine: the speaking parts are brought to target_dbfs RMS
    (gain limited to -12..+18 dB) and the peak kept under `peak`. A plain gain, nothing trimmed."""
    if len(pcm) == 0:
        return pcm
    x = pcm.astype(np.float32) / 32768.0
    win = max(1, rate // 50)
    n = len(x) // win
    if n == 0:
        return pcm
    frames = x[: n * win].reshape(n, win)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)
    active = rms[rms > 10 ** (-50 / 20)]
    if len(active) == 0:
        return pcm
    cur = 20 * np.log10(np.sqrt(np.mean(active ** 2)))
    gain = 10 ** (np.clip(target_dbfs - cur, -12.0, 18.0) / 20)
    top = float(np.max(np.abs(x))) * gain
    if top > peak:
        gain *= peak / top
    return np.clip(np.round(x * gain * 32768.0), -32768, 32767).astype(np.int16)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """16-bit PCM WAV (mono, or the first channel of stereo) -> (int16, rate)."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: only 16-bit WAV is supported")
        ch, rate = w.getnchannels(), w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.int16)
    if ch > 1:
        data = data.reshape(-1, ch)[:, 0].copy()
    return data, rate


def write_wav(path: Path, pcm: np.ndarray, rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype("<i2").tobytes())


def make_speech(text: str, pcm: np.ndarray, rate: int, engine: str, synth_ms: float,
                target_dbfs: float | None = -20.0, volume: float = 1.0) -> Speech:
    if rate != OUT_RATE:
        pcm = resample_int16(pcm, rate, OUT_RATE)
    if target_dbfs is not None:
        pcm = level(pcm, OUT_RATE, target_dbfs)
    if volume != 1.0:
        pcm = np.clip(np.round(pcm.astype(np.float32) * volume), -32768, 32767).astype(np.int16)
    sp = Speech(text=text, pcm=pcm, rate=OUT_RATE, mouth=mouth_envelope(pcm, OUT_RATE), synth_ms=synth_ms)
    sp.engine = engine
    return sp


# --------------------------------------------------------------------------- sources
class OwnerRecordings:
    """Hook for the owner's own performances (recording_plan.md): a WAV named by line id,
    e.g. voice_recordings/spike/alarm.2.wav, is played instead of any synthetic voice."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def path(self, persona: str, line_id: str) -> Path:
        return self.folder / persona / f"{line_id}.wav"

    def lookup(self, persona: str, line_id: str | None) -> tuple[np.ndarray, int] | None:
        if not line_id:
            return None
        p = self.path(persona, line_id)
        if not p.exists():
            return None
        try:
            return read_wav(p)
        except Exception as e:  # noqa: BLE001
            log.warning("owner recording %s unreadable: %s", p.name, e)
            return None


class ClipCache:
    """Pre-rendered Turbo clips (voice_cache/manifest.json, built by tools/build_voice_cache.py).

    Entries for a persona are ignored if its reference clip changed since the build
    (the cached voice would no longer match the live one)."""

    def __init__(self, folder: Path, ref_hashes: dict[str, str] | None = None):
        self.folder = Path(folder)
        self.entries: dict[str, dict] = {}
        self.manifest: dict = {}
        self._clips: dict[str, tuple[np.ndarray, int]] = {}
        self._lock = threading.Lock()
        self.load(ref_hashes or {})

    def load(self, ref_hashes: dict[str, str]) -> None:
        mf = self.folder / "manifest.json"
        self.entries, self.manifest = {}, {}
        if not mf.exists():
            return
        try:
            self.manifest = json.loads(mf.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.warning("voice cache manifest unreadable (%s); cache off", e)
            return
        stale = set()
        for persona, info in (self.manifest.get("voices") or {}).items():
            want = ref_hashes.get(persona)
            if want and info.get("ref_sha1") and info["ref_sha1"] != want:
                stale.add(persona)
        if stale:
            log.warning("voice cache for %s was made with a different reference clip; rebuild it with "
                        "python -m spike_brain.tools.build_voice_cache", ", ".join(sorted(stale)))
        for key, e in (self.manifest.get("entries") or {}).items():
            if e.get("persona") not in stale and e.get("file"):
                self.entries[key] = e

    def __len__(self) -> int:
        return len(self.entries)

    def lookup(self, persona: str, spoken: str) -> tuple[np.ndarray, int, dict] | None:
        key = cache_key(persona, spoken)
        e = self.entries.get(key)
        if e is None:
            return None
        with self._lock:
            clip = self._clips.get(key)
            if clip is None:
                p = self.folder / e["file"]
                try:
                    clip = read_wav(p)
                except Exception as ex:  # noqa: BLE001
                    log.warning("cached clip %s unreadable (%s)", p.name, ex)
                    self.entries.pop(key, None)
                    return None
                if len(self._clips) < 400:          # ~200 kB each: keep the hot ones in memory
                    self._clips[key] = clip
        return clip[0], clip[1], e


class KokoroEngine:
    """Kokoro v1.0 ONNX on the processor, one model shared by both personas."""

    def __init__(self, model: Path, voices: Path):
        from kokoro_onnx import Kokoro
        t = time.perf_counter()
        self.k = Kokoro(str(model), str(voices))
        self._lock = threading.Lock()
        log.info("Kokoro backup voice loaded in %.1f s", time.perf_counter() - t)

    def synthesize(self, text: str, voice: str, soft: bool = False) -> tuple[np.ndarray, int]:
        with self._lock:
            samples, rate = self.k.create(text, voice=voice, speed=0.92 if soft else 1.0, lang="en-us")
        pcm = np.clip(np.round(np.asarray(samples, dtype=np.float32) * 32767), -32768, 32767).astype(np.int16)
        return pcm, int(rate)


class PiperEngine:
    """Piper Amy, plain (no pitch trick: resampling pitch is what made the old voices robotic)."""

    def __init__(self, model: Path):
        from .tts import PiperTTS
        self.tts = PiperTTS(model, pitch=1.0, speed=1.0)

    def synthesize(self, text: str, soft: bool = False) -> tuple[np.ndarray, int]:
        sp = self.tts.synthesize(text, soft=soft)
        return sp.pcm, sp.rate


# --------------------------------------------------------------------------- the chain
RANK = {"owner": 0, "cache": 1, "turbo": 2, "gemini": 2, "kokoro": 3, "piper": 4, "windows": 5}


class VoiceChain:
    """One persona's voice. Same call shape as PiperTTS (synthesize(text, soft) -> Speech,
    .rate), plus hints the speech output passes when it sees `wants_hints`."""

    wants_hints = True

    def __init__(self, persona: str, *, engine: str = "turbo", style: TurboStyle | None = None,
                 turbo=None, turbo_voice: str | None = None, seed: int = 1234,
                 cache: ClipCache | None = None, recordings: OwnerRecordings | None = None,
                 kokoro: KokoroEngine | None = None, kokoro_voice: str = "am_puck",
                 piper: PiperEngine | None = None, target_dbfs: float = -20.0, volume: float = 1.0,
                 soft_volume: float = 0.85, turbo_timeout_s: float = 12.0, turbo_backoff_s: float = 15.0,
                 say_as_table: dict[str, str] | None = None, gemini=None, windows=None, mode: str = "dog"):
        if engine not in ENGINES:
            raise ValueError(f"tts engine must be one of {ENGINES}, not {engine!r}")
        self.persona, self.engine = persona, engine
        self.style = style or TurboStyle()
        self.turbo, self.turbo_voice, self.seed = turbo, turbo_voice or persona, seed
        self.cache, self.recordings = cache, recordings
        self.kokoro, self.kokoro_voice, self.piper = kokoro, kokoro_voice, piper
        self.target_dbfs, self.volume, self.soft_volume = target_dbfs, volume, soft_volume
        self.turbo_timeout_s, self.turbo_backoff_s = turbo_timeout_s, turbo_backoff_s
        self.say_as_table = dict(say_as_table or {})
        self.gemini, self.windows = gemini, windows     # desktop: Gemini TTS first, Windows' own voice last
        self.mode = mode
        self.rate = OUT_RATE
        self.stats: dict[str, int] = {}
        self.last: dict = {}
        self._turbo_skip_until = 0.0
        self._utt_floor: tuple[str | None, int] = (None, 0)   # (utterance, lowest source rank allowed)

    def order(self) -> list[str]:
        """Sources to try, best first, for the configured engine."""
        if self.engine == "turbo":
            chain = ["owner", "cache", "turbo", "kokoro", "piper"]
        elif self.engine == "kokoro":
            chain = ["owner", "kokoro", "piper"]
        else:
            chain = ["owner", "piper"]
        if self.engine == "gemini":
            chain = ["owner", "gemini", "kokoro", "piper"]
        if self.windows is not None:
            chain.append("windows")          # never silent: Windows' own voice is the very last resort
        return chain

    def warm_up(self) -> None:          # PiperTTS compatibility
        return None

    def _turbo_ok(self) -> bool:
        return (self.turbo is not None and getattr(self.turbo, "ready", False)
                and time.monotonic() >= self._turbo_skip_until)

    def synthesize(self, text: str, soft: bool = False, mood: str | None = None, line_id: str | None = None,
                   first: bool = True, utt: str | None = None) -> Speech | None:
        """One sentence -> Speech from the best source that works, or None if even Piper failed."""
        if not text.strip():
            return None
        caption = text
        text = say_as(text, self.say_as_table)        # what every voice says ("triple zero"); captions keep "000"
        spoken = turbo_text(text, mood, self.style, soft=soft, first=first)
        floor = self._utt_floor[1] if (utt is not None and self._utt_floor[0] == utt) else 0
        vol = self.volume * (self.soft_volume if soft else 1.0)
        tried = []
        for src in self.order():
            if RANK[src] < floor and src != "owner":
                continue                     # a fallback voice started this reply: keep that voice
            t = time.perf_counter()
            try:
                got = self._try(src, text, spoken, soft, line_id)
            except Exception as e:  # noqa: BLE001 - any engine may fail; the next one speaks
                log.warning("%s voice failed for %s (%s: %s); trying the next one", src, self.persona,
                            type(e).__name__, str(e)[:160])
                if src == "turbo":
                    self._turbo_skip_until = time.monotonic() + self.turbo_backoff_s
                got = None
            if got is None:
                tried.append(src)
                continue
            pcm, rate, gen_ms = got
            ms = (time.perf_counter() - t) * 1000
            # cached clips and owner recordings were levelled when made; live engines are levelled now
            sp = make_speech(caption, pcm, rate, src, ms,
                             None if src in ("owner", "cache") else self.target_dbfs, vol)
            self.stats[src] = self.stats.get(src, 0) + 1
            self.last = {"source": src, "ms": round(ms), "gen_ms": round(gen_ms), "spoken": spoken,
                         "skipped": tried}
            if utt is not None and src in ("kokoro", "piper", "windows"):
                self._utt_floor = (utt, RANK[src])
            elif utt is not None and self._utt_floor[0] != utt:
                self._utt_floor = (utt, 0)
            log.debug("%s said by %s in %.0f ms: %s", self.persona, src, ms, spoken)
            return sp
        log.error("no voice could say %r for %s (tried %s)", text[:60], self.persona, ", ".join(tried))
        return None

    def _try(self, src: str, text: str, spoken: str, soft: bool, line_id: str | None):
        if src == "owner":
            r = self.recordings.lookup(self.persona, line_id) if self.recordings else None
            return (r[0], r[1], 0.0) if r else None
        if src == "cache":
            r = self.cache.lookup(self.persona, spoken) if self.cache else None
            return (r[0], r[1], 0.0) if r else None
        if src == "turbo":
            if not self._turbo_ok():
                return None
            pcm, rate, gen_ms = self.turbo.synthesize(self.turbo_voice, spoken, seed=self.seed,
                                                      timeout=self.turbo_timeout_s)
            if len(pcm) < rate // 10:
                raise RuntimeError("Turbo returned (almost) no audio")
            return pcm, rate, gen_ms
        if src == "kokoro":
            if self.kokoro is None:
                return None
            pcm, rate = self.kokoro.synthesize(text, self.kokoro_voice, soft)
            return pcm, rate, 0.0
        if src == "piper":
            if self.piper is None:
                return None
            pcm, rate = self.piper.synthesize(text, soft)
            return pcm, rate, 0.0
        if src == "gemini":
            if self.gemini is None or not self.gemini.available:
                return None                  # no key, or every model resting after a 429: next voice
            pcm, rate = self.gemini.synthesize(text, self.mode, soft)
            return pcm, rate, 0.0
        if src == "windows":
            if self.windows is None:
                return None
            pcm, rate = self.windows.synthesize(text, self.mode, soft)
            return pcm, rate, 0.0
        return None
