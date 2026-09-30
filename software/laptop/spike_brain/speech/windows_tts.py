"""Windows' own voice (SAPI 5): the last resort of the desktop brain's voice chain.

Used only when the Gemini voice cannot speak (no internet, no key, free quota used up), so
Spike is never silent. SAPI is part of every Windows install: no download, no GPU. It is
driven through COM with `comtypes` (dynamic dispatch, so nothing is generated at run time,
which also works in the frozen app) and renders into a memory stream: nothing plays here,
the brain's normal speech output plays the samples (laptop speaker or the robot).

COM objects belong to the thread that made them, so one worker thread owns the voice and
every request goes through it.
"""
from __future__ import annotations

import logging
import queue
import sys
import threading

import numpy as np

log = logging.getLogger("spike.voice")

SAFT22kHz16BitMono = 22     # SpeechAudioFormatType
RATE = 22050


def pick_voice(voices: list[dict], mode: str) -> int | None:
    """Index of the best installed voice for the character: English, male for Spike, female for
    Spicy (US English first, then any English, then any voice of that gender, then the first)."""
    want = "female" if mode == "cat" else "male"

    def score(v: dict) -> tuple:
        lang = str(v.get("language", "")).lower()
        english_us = lang in ("409",)
        english = english_us or lang in ("809", "c09", "1009", "1409", "4009", "1809", "3409", "2409")
        return (str(v.get("gender", "")).lower() == want, english_us, english)

    if not voices:
        return None
    best = max(range(len(voices)), key=lambda i: score(voices[i]))
    return best


class WindowsVoice:
    """synthesize(text, mode, soft) -> (int16 samples, 22050). Raises RuntimeError if SAPI fails."""

    def __init__(self, timeout_s: float = 15.0):
        if sys.platform != "win32":
            raise RuntimeError("Windows' voice is only on Windows")
        self.timeout_s = timeout_s
        self._jobs: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._error: Exception | None = None
        self.voices: list[dict] = []
        self._thread = threading.Thread(target=self._run, name="windows-voice", daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("Windows' voice did not start")
        if self._error is not None:
            raise RuntimeError(f"Windows' voice unavailable: {self._error}")

    def _run(self) -> None:
        try:
            import comtypes
            import comtypes.client as cc
            comtypes.CoInitialize()
            sp = cc.CreateObject("SAPI.SpVoice", dynamic=True)
            tokens = sp.GetVoices()
            toks = [tokens.Item(i) for i in range(tokens.Count)]
            for t in toks:
                def attr(name, t=t):
                    try:
                        return str(t.GetAttribute(name) or "")
                    except Exception:  # noqa: BLE001
                        return ""
                self.voices.append({"name": str(t.GetDescription()), "gender": attr("Gender"),
                                    "language": attr("Language").split(";")[0].lower()})
        except Exception as e:  # noqa: BLE001
            self._error = e
            self._ready.set()
            return
        self._ready.set()
        chosen: dict[str, int | None] = {m: pick_voice(self.voices, m) for m in ("dog", "cat")}
        while True:
            job = self._jobs.get()
            if job is None:
                break
            text, mode, soft, out = job
            try:
                idx = chosen.get(mode)
                if idx is not None:
                    sp.Voice = toks[idx]
                sp.Rate = -1 if soft else 0              # -10..10; a little slower when gentle
                stream = cc.CreateObject("SAPI.SpMemoryStream", dynamic=True)
                fmt = stream.Format
                fmt.Type = SAFT22kHz16BitMono
                stream.Format = fmt
                sp.AudioOutputStream = stream
                sp.Speak(text, 0)                        # SVSFDefault: synchronous, into the stream
                data = bytes(stream.GetData())
                out.put(np.frombuffer(data[: len(data) & ~1], dtype="<i2").astype(np.int16))
            except Exception as e:  # noqa: BLE001
                out.put(e)
        try:
            comtypes.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass

    def voice_name(self, mode: str) -> str:
        i = pick_voice(self.voices, mode)
        return self.voices[i]["name"] if i is not None else ""

    def synthesize(self, text: str, mode: str = "dog", soft: bool = False) -> tuple[np.ndarray, int]:
        out: queue.Queue = queue.Queue()
        self._jobs.put((text, mode, soft, out))
        try:
            got = out.get(timeout=self.timeout_s)
        except queue.Empty:
            raise RuntimeError("Windows' voice timed out") from None
        if isinstance(got, Exception):
            raise RuntimeError(f"Windows' voice failed ({type(got).__name__})") from None
        return got, RATE

    def close(self) -> None:
        self._jobs.put(None)
