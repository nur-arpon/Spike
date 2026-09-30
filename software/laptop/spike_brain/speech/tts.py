"""Text to speech with Piper, plus the mouth-movement envelope.

Per-persona "puppy" tweak: pitch and speed from the persona file. Pitch is
raised without changing speed by synthesizing slower (length_scale x pitch)
and then resampling by 1/pitch - the classic tape-speed trick, cheap and
artefact-free for the small shifts we use (1.0 to 1.2).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

log = logging.getLogger("spike.tts")

MOUTH_RATE_HZ = 50


@dataclass
class Speech:
    """One synthesized segment: 16-bit mono PCM + mouth envelope."""
    text: str
    pcm: np.ndarray            # int16
    rate: int
    mouth: list[int]           # 0..100 at MOUTH_RATE_HZ
    synth_ms: float = 0.0
    engine: str = ""             # which voice made it: owner, cache, turbo, kokoro, piper

    @property
    def duration_ms(self) -> int:
        return int(round(len(self.pcm) * 1000 / self.rate)) if self.rate else 0

    def resampled(self, rate: int) -> "Speech":
        if not rate or rate == self.rate:
            return self
        pcm = resample_int16(self.pcm, self.rate, rate)
        return Speech(self.text, pcm, rate, self.mouth, self.synth_ms, self.engine)


def resample_int16(pcm: np.ndarray, src: int, dst: int) -> np.ndarray:
    from scipy.signal import resample_poly
    if src == dst or len(pcm) == 0:
        return pcm
    f = Fraction(dst, src).limit_denominator(1000)
    y = resample_poly(pcm.astype(np.float32), f.numerator, f.denominator)
    return np.clip(np.round(y), -32768, 32767).astype(np.int16)


def pitch_shift(pcm: np.ndarray, pitch: float) -> np.ndarray:
    """Resample so the audio plays `pitch` times higher (and shorter) at the same rate."""
    if abs(pitch - 1.0) < 1e-3 or len(pcm) == 0:
        return pcm
    from scipy.signal import resample_poly
    f = Fraction(1 / pitch).limit_denominator(200)
    y = resample_poly(pcm.astype(np.float32), f.numerator, f.denominator)
    return np.clip(np.round(y), -32768, 32767).astype(np.int16)


def mouth_envelope(pcm: np.ndarray, rate: int, hz: int = MOUTH_RATE_HZ,
                   floor_db: float = -46.0, top_db: float = -14.0) -> list[int]:
    """Mouth-open values 0..100, one per 1/hz s: RMS in dBFS mapped floor..top,
    fast attack, slower release (a real jaw can't snap shut)."""
    if len(pcm) == 0 or rate <= 0:
        return []
    win = max(1, rate // hz)
    n = int(np.ceil(len(pcm) / win))
    x = np.zeros(n * win, dtype=np.float32)
    x[:len(pcm)] = pcm.astype(np.float32) / 32768.0
    rms = np.sqrt(np.mean(x.reshape(n, win) ** 2, axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    lvl = np.clip((db - floor_db) / (top_db - floor_db), 0.0, 1.0)
    out, prev = [], 0.0
    for v in lvl:
        prev = v if v > prev else prev * 0.55 + v * 0.45
        out.append(int(round(prev * 100)))
    if out:
        out[-1] = 0
    return out


class PiperTTS:
    """A loaded Piper voice with a persona's pitch/speed. Thread-safe (one synth at a time)."""

    def __init__(self, model_path: Path, pitch: float = 1.0, speed: float = 1.0,
                 noise_scale: float = 0.667, noise_w: float = 0.8, volume: float = 1.0,
                 use_cuda: bool = False):
        from piper import PiperVoice
        if not model_path or not Path(model_path).exists():
            raise FileNotFoundError(f"Piper voice not found: {model_path}")
        t = time.perf_counter()
        self.voice = PiperVoice.load(str(model_path), use_cuda=use_cuda)
        self.model_path = Path(model_path)
        self.rate = int(self.voice.config.sample_rate)
        self.pitch, self.speed = float(pitch), float(speed)
        self.noise_scale, self.noise_w, self.volume = noise_scale, noise_w, volume
        self._lock = threading.Lock()
        log.info("voice %s loaded in %.2f s (%d Hz, pitch %.2f, speed %.2f)",
                 self.model_path.name, time.perf_counter() - t, self.rate, self.pitch, self.speed)

    def synthesize(self, text: str, soft: bool = False) -> Speech:
        """soft=True is the comforting voice (sad, lonely or tired owner): a little
        slower, lower and quieter than his everyday puppy voice."""
        from piper import SynthesisConfig
        t = time.perf_counter()
        speed = self.speed * (0.9 if soft else 1.0)
        pitch = self.pitch * (0.97 if soft else 1.0)
        length = (1.0 / max(0.5, speed)) * max(0.5, pitch)
        cfg = SynthesisConfig(length_scale=length, noise_scale=self.noise_scale,
                              noise_w_scale=self.noise_w, volume=self.volume * (0.75 if soft else 1.0))
        with self._lock:
            chunks = list(self.voice.synthesize(text, cfg))
        if chunks:
            pcm = np.concatenate([c.audio_int16_array.reshape(-1) for c in chunks])
        else:
            pcm = np.zeros(0, dtype=np.int16)
        pcm = pitch_shift(pcm, pitch)
        pcm = trim_silence(pcm, self.rate)
        sp = Speech(text=text, pcm=pcm, rate=self.rate, mouth=mouth_envelope(pcm, self.rate))
        sp.synth_ms = (time.perf_counter() - t) * 1000
        return sp

    def warm_up(self) -> None:
        self.synthesize("Hi.")


def trim_silence(pcm: np.ndarray, rate: int, threshold: int = 180,
                 lead_ms: int = 30, tail_ms: int = 160) -> np.ndarray:
    """Cut Piper's leading/trailing padding. Keeps a short lead-in (so onsets
    are not clipped) and a natural pause after the sentence, because segments
    are played back to back."""
    if len(pcm) == 0:
        return pcm
    loud = np.flatnonzero(np.abs(pcm.astype(np.int32)) > threshold)
    if len(loud) == 0:
        return pcm[: int(rate * lead_ms / 1000)]
    start = max(0, loud[0] - int(rate * lead_ms / 1000))
    end = min(len(pcm), loud[-1] + int(rate * tail_ms / 1000))
    return pcm[start:end]
