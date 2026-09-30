"""Speech to text with faster-whisper: GPU (CUDA float16) when it works,
CPU int8 otherwise. The CUDA runtime DLLs come from the nvidia-cublas-cu12
and nvidia-cudnn-cu12 wheels in the venv; they must be on the DLL search
path before ctranslate2 loads, which `enable_cuda_dlls()` arranges.
"""
from __future__ import annotations

import glob
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger("spike.stt")

_dll_done = False


def enable_cuda_dlls() -> list[str]:
    """Put the venv's nvidia/*/bin folders on the DLL path (Windows). Idempotent."""
    global _dll_done
    added: list[str] = []
    if _dll_done or os.name != "nt":
        return added
    for base in {sys.prefix, os.path.dirname(os.path.dirname(os.__file__))}:
        for b in glob.glob(os.path.join(base, "Lib", "site-packages", "nvidia", "*", "bin")):
            try:
                os.add_dll_directory(b)
            except (OSError, AttributeError):
                pass
            if b not in os.environ.get("PATH", ""):
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")
            added.append(b)
    _dll_done = True
    return added


# Whisper's classic phantom outputs on silence / noise.
PHANTOMS = {"thank you", "thanks for watching", "thank you for watching", "you", "bye", "okay",
            "subtitles by the amara org community", "thanks", "so", "uh", "um", "hmm", "oh", "the end"}


@dataclass
class Transcript:
    text: str
    no_speech_prob: float
    avg_logprob: float
    audio_s: float
    ms: float

    @property
    def usable(self) -> bool:
        t = re.sub(r"[^a-z' ]", "", self.text.lower()).strip()
        if not t:
            return False
        if self.no_speech_prob > 0.75 and self.avg_logprob < -0.9:
            return False
        if t in PHANTOMS and (self.no_speech_prob > 0.3 or self.audio_s < 0.8):
            return False
        return True


class Transcriber:
    def __init__(self, models_dir: Path, gpu_model: str = "small.en", cpu_model: str = "base.en",
                 device: str = "auto", compute_type_cuda: str = "float16", compute_type_cpu: str = "int8",
                 beam_size: int = 1, cpu_threads: int = 0, prompt_words: list[str] | None = None):
        from faster_whisper import WhisperModel
        self.beam_size = beam_size
        self.prompt = (", ".join(prompt_words) + ".") if prompt_words else None
        self.device = "cpu"
        t = time.perf_counter()
        if device in ("auto", "cuda"):
            enable_cuda_dlls()
            try:
                import ctranslate2
                if ctranslate2.get_cuda_device_count() > 0:
                    self.model = WhisperModel(str(models_dir / gpu_model), device="cuda",
                                              compute_type=compute_type_cuda)
                    self.model_name = gpu_model
                    self.device = "cuda"
                    self._probe()
            except Exception as e:  # noqa: BLE001 - any CUDA problem -> CPU
                if device == "cuda":
                    raise
                log.warning("GPU speech recognition unavailable (%s: %s); using the CPU",
                            type(e).__name__, str(e)[:120])
                self.device = "cpu"
        if self.device == "cpu":
            self.model = WhisperModel(str(models_dir / cpu_model), device="cpu",
                                      compute_type=compute_type_cpu, cpu_threads=cpu_threads)
            self.model_name = cpu_model
            self._probe()
        log.info("speech recognition: whisper %s on %s (ready in %.1f s)",
                 self.model_name, self.device, time.perf_counter() - t)

    def _probe(self) -> None:
        """Run once on silence: surfaces missing DLLs now, not on the first request."""
        segs, _ = self.model.transcribe(np.zeros(16000, dtype=np.float32), language="en", beam_size=1,
                                        without_timestamps=True)
        list(segs)

    def transcribe(self, pcm: np.ndarray) -> Transcript:
        """pcm: int16 or float32 mono at 16 kHz."""
        t = time.perf_counter()
        audio = pcm.astype(np.float32) / 32768.0 if pcm.dtype == np.int16 else pcm.astype(np.float32)
        segs, _info = self.model.transcribe(
            audio, language="en", beam_size=self.beam_size, without_timestamps=True,
            condition_on_previous_text=False, vad_filter=False, initial_prompt=self.prompt,
            temperature=0.0)
        segs = list(segs)
        text = " ".join(s.text.strip() for s in segs).strip()
        nsp = max((s.no_speech_prob for s in segs), default=1.0)
        alp = float(np.mean([s.avg_logprob for s in segs])) if segs else -5.0
        return Transcript(text, nsp, alp, len(audio) / 16000.0, (time.perf_counter() - t) * 1000)
