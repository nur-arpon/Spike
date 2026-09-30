"""Gemini TTS: Spike's and Spicy's natural Google voice, made on the laptop.

The desktop app's light brain (config/desktop.toml, [tts] engine = "gemini") speaks with the
same Google voices and style prompts the phone app uses (lib/away/ai/gemini_voices.dart and
lib/away/voice/gemini_tts.dart). Owner decisions, 30 Sep 2026 (DESIGN.md "Desktop"):

  * Spike: "Energetic" (Fenrir, the owner's favourite, default) or "Street dog" (Algenib);
    also Upbeat (Puck) and Friendly (Achird).
  * Spicy: "Sassy" (Kore, default), Smooth (Despina), Drawl (Callirrhoe), "Caring girlfriend"
    (Kore, caring; never sexual or flirty).
  * Street dog and Spicy's sassy styles may roast to motivate; that is a behaviour rule of the
    persona prompt, not of the voice (the voice only reads the checked text it is given).
  * Sad, lonely or crisis lines always use the soft direction (no sarcasm, no roasting).

The request (checked 30 Sep 2026, ai.google.dev speech-generation):
  POST /v1beta/interactions
  {"model": "gemini-3.8-flash-tts",
   "input": [{"type": "user_input", "content": [{"type": "text", "text": "...",
              "annotations": [{"type": "speech_metadata", "style": "..."}]}]}],
   "response_format": {"type": "audio"},
   "generation_config": {"speech_config": [{"voice": "Fenrir"}]}}
and the answer's audio is a {"type": "audio", "data": base64} item (a WAV, or raw 16-bit PCM
at 24 kHz). Flash is tried first (better acting), Flash-Lite when Flash's free quota is used
up; when both are rate limited the voice rests and the chain uses the next voice (Windows'
own voice). The key is sent in the header only and never appears in a log or an error.

A drift test (tests/test_desktop_voice.py) reads the Dart file and checks that every style's
Google voice and style prompt here are identical.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass

import numpy as np

log = logging.getLogger("spike.voice")

TTS_MODELS = ("gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts")
TTS_RATE = 24000


@dataclass(frozen=True)
class VoiceStyle:
    id: str
    label: str
    voice: str          # Google's prebuilt voice name, sent as-is
    tts: str            # the style prompt (speech_metadata.style)
    roast: bool = False


# --- the words: identical to lib/away/ai/gemini_voices.dart (drift-tested) -------------------
_DOG_TTS = "warm, playful young puppy, bright and bouncy, quick and smiling, cheeky but kind"
_STREET_TTS = ("gruff, deep and gravelly street dog, confident streetwise swagger, tough and cocky, "
               "unhurried punchy delivery, loyal and warm underneath")
_CAT_TTS = ("sassy, witty and playful, lively and quick with attitude, dry sarcastic comebacks, "
            "a smug little smile in the voice, secretly fond")
_CARING_TTS = ("super caring, warm and affectionate young woman, soft and gentle, attentive and "
               "tender, calm and reassuring, smiling softly")
SOFT_TTS = {
    "cat": "soft, calm, gentle and warm female voice, slow and quiet, caring, no sarcasm",
    "dog": "soft, calm, gentle and warm young male voice, slow and quiet, caring, no excitement",
}

STYLES: dict[str, list[VoiceStyle]] = {
    "dog": [
        VoiceStyle("energetic", "Energetic", "Fenrir", _DOG_TTS),
        VoiceStyle("upbeat", "Upbeat", "Puck", _DOG_TTS),
        VoiceStyle("friendly", "Friendly", "Achird", _DOG_TTS),
        VoiceStyle("street", "Street dog", "Algenib", _STREET_TTS, roast=True),
    ],
    "cat": [
        VoiceStyle("sassy", "Sassy", "Kore", _CAT_TTS, roast=True),
        VoiceStyle("smooth", "Smooth", "Despina", _CAT_TTS, roast=True),
        VoiceStyle("drawl", "Drawl", "Callirrhoe", _CAT_TTS, roast=True),
        VoiceStyle("caring", "Caring girlfriend", "Kore", _CARING_TTS),
    ],
}
DEFAULT_STYLE = {"dog": "energetic", "cat": "sassy"}


def style_by_id(mode: str, style_id: str | None) -> VoiceStyle:
    """The style with that id for this character, else the character's default."""
    styles = STYLES.get(mode) or STYLES["dog"]
    for s in styles:
        if s.id == style_id:
            return s
    default = DEFAULT_STYLE.get(mode, "energetic")
    return next(s for s in styles if s.id == default)


def tts_style(mode: str, soft: bool = False, style: VoiceStyle | None = None) -> str:
    """The style prompt for one line: the picked style, or the soft one for sad/crisis lines."""
    if soft:
        return SOFT_TTS["cat" if mode == "cat" else "dog"]
    return (style or style_by_id(mode, None)).tts


class VoicePicks:
    """The owner's pick per character (protocol v1.8 `voice_style`, kept in data/app_prefs.json
    by applink.py). Starts at the defaults."""

    def __init__(self, picks: dict | None = None):
        self._picks: dict[str, str] = {}
        for mode, sid in (picks or {}).items():
            self.set(mode, sid)

    def set(self, mode: str, style_id: str) -> bool:
        if mode not in STYLES or not any(s.id == style_id for s in STYLES[mode]):
            return False
        self._picks[mode] = style_id
        return True

    def style(self, mode: str) -> VoiceStyle:
        return style_by_id(mode, self._picks.get(mode))

    def as_dict(self) -> dict[str, str]:
        return {m: self.style(m).id for m in STYLES}


# --- the request (pure, tested) -------------------------------------------------------------
def tts_body(model: str, text: str, voice: str, style: str) -> dict:
    return {
        "model": model,
        "input": [{"type": "user_input",
                   "content": [{"type": "text", "text": text,
                                "annotations": [{"type": "speech_metadata", "style": style}]}]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }


def tts_audio(answer) -> tuple[np.ndarray, int] | None:
    """The audio in an interactions answer as (int16 mono samples, rate), or None."""
    found: list[str] = []

    def walk(o) -> None:
        if isinstance(o, dict):
            if o.get("type") == "audio" and isinstance(o.get("data"), str):
                found.append(o["data"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(answer)
    if not found:
        return None
    raw = base64.b64decode(found[-1])
    if raw[:4] == b"RIFF":
        with wave.open(io.BytesIO(raw), "rb") as w:
            ch, rate, width = w.getnchannels(), w.getframerate(), w.getsampwidth()
            frames = w.readframes(w.getnframes())
        if width != 2:
            raise ValueError(f"unexpected sample width {width}")
        pcm = np.frombuffer(frames, dtype="<i2")
        if ch > 1:
            pcm = pcm[::ch]
        return pcm.astype(np.int16), rate
    n = len(raw) & ~1
    return np.frombuffer(raw[:n], dtype="<i2").astype(np.int16), TTS_RATE


class TtsError(Exception):
    """kind: rate_limited | bad_key | resting | network | other (never contains the key)."""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind


class GeminiTTSEngine:
    """One sentence -> Spike's Gemini voice (int16 PCM). Used by speech/engines.py VoiceChain."""

    def __init__(self, api_key: str, picks: VoicePicks | None = None, models: tuple[str, ...] = TTS_MODELS,
                 timeout_s: float = 12.0, rest_s: float = 900.0,
                 base_url: str = "https://generativelanguage.googleapis.com/v1beta", clock=time.monotonic):
        if not api_key:
            raise ValueError("no Gemini key")
        self._key = api_key.strip()
        self.picks = picks or VoicePicks()
        self.models = tuple(models)
        self.timeout_s = timeout_s
        self.rest_s = rest_s
        self.base_url = base_url.rstrip("/")
        self._clock = clock
        self._rest_until: dict[str, float] = {}
        self.bad_key = False
        self.last_model = ""

    def __repr__(self) -> str:
        return f"GeminiTTSEngine(models={self.models})"

    def _resting(self, model: str) -> bool:
        return self._clock() < self._rest_until.get(model, 0.0)

    @property
    def available(self) -> bool:
        return not self.bad_key and any(not self._resting(m) for m in self.models)

    def _post(self, body: dict) -> tuple[int, bytes]:
        req = urllib.request.Request(f"{self.base_url}/interactions", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": self._key})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read()
            except Exception:  # noqa: BLE001
                return e.code, b""
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise TtsError("network", type(e).__name__) from None

    def synthesize(self, text: str, mode: str, soft: bool = False) -> tuple[np.ndarray, int]:
        """Raises TtsError when no model can say it right now (the chain then uses the next voice)."""
        if self.bad_key:
            raise TtsError("bad_key")
        style = self.picks.style(mode)
        prompt = tts_style(mode, soft, style)
        last: TtsError | None = None
        for model in self.models:
            if self._resting(model):
                last = last or TtsError("resting")
                continue
            status, raw = self._post(tts_body(model, text, style.voice, prompt))
            if status == 200:
                try:
                    got = tts_audio(json.loads(raw.decode("utf-8", "replace")))
                except (ValueError, wave.Error) as e:
                    raise TtsError("other", f"bad audio ({type(e).__name__})") from None
                if got is None:
                    raise TtsError("other", "no audio in the answer")
                self.last_model = model
                return got
            low = raw.decode("utf-8", "replace").lower()
            if status == 429 or "resource_exhausted" in low:
                self._rest_until[model] = self._clock() + self.rest_s
                log.info("Gemini voice %s is rate limited; resting it for %d min", model, self.rest_s // 60)
                last = TtsError("rate_limited", f"HTTP {status}")
                continue
            if status in (401, 403) or (status == 400 and "api key" in low):
                self.bad_key = True
                raise TtsError("bad_key", f"HTTP {status}")
            if status == 404:
                self._rest_until[model] = self._clock() + 86400.0      # that model is gone
                last = TtsError("other", "HTTP 404")
                continue
            raise TtsError("other", f"HTTP {status}")
        raise last or TtsError("other", "no TTS model")
