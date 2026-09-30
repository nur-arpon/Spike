"""Voice activity detection and endpointing.

SileroVAD   - the Silero ONNX model shipped with openWakeWord (v4 h/c
              layout; v5 'state' layout also supported). ~0.1 ms per 32 ms
              frame on the CPU.
EnergyVAD   - fallback with an adaptive noise floor (no model needed).
Endpointer  - turns per-frame speech probabilities into "speech started" /
              "speech ended" with hysteresis; the end-silence length is the
              main latency knob (config vad.end_silence_ms).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
FRAME = 512                      # 32 ms at 16 kHz


class SileroVAD:
    def __init__(self, model_path: Path | str):
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self.sess = ort.InferenceSession(str(model_path), sess_options=opts, providers=["CPUExecutionProvider"])
        names = {i.name for i in self.sess.get_inputs()}
        self.v5 = "state" in names
        self.sr = np.array(SAMPLE_RATE, dtype=np.int64)
        self.reset()

    def reset(self) -> None:
        if self.v5:
            self.state = np.zeros((2, 1, 128), dtype=np.float32)
            self.context = np.zeros(64, dtype=np.float32)
        else:
            self.h = np.zeros((2, 1, 64), dtype=np.float32)
            self.c = np.zeros((2, 1, 64), dtype=np.float32)

    def __call__(self, frame: np.ndarray) -> float:
        """Speech probability for one 512-sample int16 frame."""
        x = frame.astype(np.float32) / 32768.0
        if self.v5:
            inp = np.concatenate([self.context, x])[None, :]
            out, self.state = self.sess.run(None, {"input": inp, "state": self.state, "sr": self.sr})
            self.context = x[-64:]
        else:
            out, self.h, self.c = self.sess.run(None, {"input": x[None, :], "h": self.h, "c": self.c, "sr": self.sr})
        return float(out[0][0])


class EnergyVAD:
    """RMS against a slowly adapting noise floor. Returns a pseudo-probability."""

    def __init__(self, margin_db: float = 12.0):
        self.margin_db = margin_db
        self.reset()

    def reset(self) -> None:
        self.floor_db = -60.0

    def __call__(self, frame: np.ndarray) -> float:
        x = frame.astype(np.float32) / 32768.0
        db = 10 * np.log10(np.mean(x * x) + 1e-10)
        rate = 0.05 if db < self.floor_db else 0.002
        self.floor_db += (db - self.floor_db) * rate
        return float(np.clip((db - self.floor_db - self.margin_db / 2) / self.margin_db + 0.5, 0.0, 1.0))


def make_vad(engine: str, model_path: Path | None):
    if engine == "silero" and model_path and Path(model_path).exists():
        return SileroVAD(model_path)
    return EnergyVAD()


@dataclass
class EndpointEvent:
    kind: str                # "start" | "end"
    frame_index: int         # frame where speech started / the last voiced frame
    voiced_ms: int = 0


class Endpointer:
    """Hysteresis over speech probabilities.

    start: `start_frames` frames in a row >= threshold.
    end:   after a start, `end_frames` frames in a row < threshold - 0.15.
    """

    def __init__(self, threshold: float = 0.5, end_silence_ms: int = 450, min_speech_ms: int = 200,
                 frame_ms: float = FRAME * 1000 / SAMPLE_RATE):
        self.threshold = threshold
        self.low = max(0.05, threshold - 0.15)
        self.frame_ms = frame_ms
        self.start_frames = max(1, int(round(min(min_speech_ms, 96) / frame_ms)))
        self.min_speech_frames = max(1, int(round(min_speech_ms / frame_ms)))
        self.end_frames = max(1, int(round(end_silence_ms / frame_ms)))
        self.reset()

    def reset(self) -> None:
        self.in_speech = False
        self.run_hi = 0
        self.run_lo = 0
        self.start_index = -1
        self.last_voiced = -1
        self.voiced = 0
        self.index = -1

    def push(self, prob: float) -> EndpointEvent | None:
        self.index += 1
        if not self.in_speech:
            self.run_hi = self.run_hi + 1 if prob >= self.threshold else 0
            if self.run_hi >= self.start_frames:
                self.in_speech = True
                self.start_index = self.index - self.run_hi + 1
                self.last_voiced = self.index
                self.voiced = self.run_hi
                self.run_lo = 0
                return EndpointEvent("start", self.start_index)
            return None
        if prob >= self.low:
            self.run_lo = 0
            if prob >= self.threshold:
                self.last_voiced = self.index
                self.voiced += 1
            return None
        self.run_lo += 1
        if self.run_lo >= self.end_frames:
            self.in_speech = False
            self.run_hi = 0
            ev = EndpointEvent("end", self.last_voiced, int(self.voiced * self.frame_ms))
            if self.voiced < self.min_speech_frames:
                ev.kind = "blip"            # too short to be a request (a cough, a click)
            return ev
        return None
