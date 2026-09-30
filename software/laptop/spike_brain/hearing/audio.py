"""Where Spike's hearing comes from - one interface, two sources.

MicSource     the laptop microphone (sounddevice), today.
RemoteSource  the robot's mic stream (protocol `audio` messages), later.
Both deliver 16 kHz mono int16 frames of 512 samples to one callback, so
the listener never knows which it is using.
"""
from __future__ import annotations

import logging
import threading
from fractions import Fraction
from typing import Callable

import numpy as np

from .vad import FRAME, SAMPLE_RATE

log = logging.getLogger("spike.audio")

FrameCallback = Callable[[np.ndarray], None]


class Reframer:
    """Collects arbitrary-length int16 chunks and emits fixed 512-sample frames."""

    def __init__(self, on_frame: FrameCallback, frame: int = FRAME):
        self.on_frame = on_frame
        self.frame = frame
        self.buf = np.zeros(0, dtype=np.int16)

    def push(self, pcm: np.ndarray) -> None:
        self.buf = np.concatenate([self.buf, pcm.astype(np.int16, copy=False)])
        n = len(self.buf) // self.frame
        for i in range(n):
            self.on_frame(self.buf[i * self.frame:(i + 1) * self.frame])
        self.buf = self.buf[n * self.frame:]


class StreamResampler:
    """Streaming polyphase resampler (keeps filter state across blocks, so no clicks)."""

    def __init__(self, src: int, dst: int):
        from scipy.signal import firwin
        f = Fraction(dst, src).limit_denominator(1000)
        self.up, self.down = f.numerator, f.denominator
        # Exact streaming filter for small ratios (48k->16k is 1/3). Odd ratios
        # like 44.1k->16k (160/441) use block-wise polyphase instead: the filter
        # would be ~10k taps, and ASR does not hear the tiny block seams.
        self.blockwise = max(self.up, self.down) > 12
        if not self.blockwise:
            taps = 24 * max(self.up, self.down) + 1
            self.h = firwin(taps, 1.0 / max(self.up, self.down), window=("kaiser", 7.0)) * self.up
            self.state = np.zeros(len(self.h) - 1, dtype=np.float64)
        self.phase = 0

    def __call__(self, x: np.ndarray) -> np.ndarray:
        from scipy.signal import lfilter, resample_poly
        if self.up == self.down:
            return x.astype(np.int16)
        if self.blockwise:
            y = resample_poly(x.astype(np.float64), self.up, self.down)
            return np.clip(np.round(y), -32768, 32767).astype(np.int16)
        up = np.zeros(len(x) * self.up, dtype=np.float64)
        up[::self.up] = x.astype(np.float64)
        y, self.state = lfilter(self.h, 1.0, up, zi=self.state)
        start = (-self.phase) % self.down
        out = y[start::self.down]
        self.phase = (self.phase + len(up)) % self.down
        return np.clip(np.round(out), -32768, 32767).astype(np.int16)


class AudioSource:
    name = "none"

    def start(self, on_frame: FrameCallback) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        pass


class MicSource(AudioSource):
    """The laptop microphone. Opens at 16 kHz if the device allows it, otherwise
    at its native rate with streaming resampling."""
    name = "laptop-mic"

    def __init__(self, device: str | int | None = None):
        self.device = device
        self.stream = None
        self.device_name = "?"

    def _pick_device(self):
        import sounddevice as sd
        d = self.device
        if d in (None, ""):
            return None
        if isinstance(d, int) or (isinstance(d, str) and d.isdigit()):
            return int(d)
        for i, info in enumerate(sd.query_devices()):
            if info["max_input_channels"] > 0 and str(d).lower() in info["name"].lower():
                return i
        log.warning("mic '%s' not found, using the default input", d)
        return None

    def start(self, on_frame: FrameCallback) -> None:
        import sounddevice as sd
        dev = self._pick_device()
        info = sd.query_devices(dev, "input")
        self.device_name = info["name"]
        reframer = Reframer(on_frame)
        try:
            sd.check_input_settings(device=dev, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
            rate, resampler = SAMPLE_RATE, None
        except Exception:  # noqa: BLE001 - device can't do 16 kHz natively
            rate = int(info["default_samplerate"])
            resampler = StreamResampler(rate, SAMPLE_RATE)

        def callback(indata, frames, time_info, status):  # runs on PortAudio's thread
            if status:
                log.debug("mic status: %s", status)
            x = indata[:, 0].copy()
            reframer.push(resampler(x) if resampler else x)

        self.stream = sd.InputStream(device=dev, samplerate=rate, channels=1, dtype="int16",
                                     blocksize=int(rate * 0.032), callback=callback, latency="low")
        self.stream.start()
        log.info("microphone: %s at %d Hz%s", self.device_name, rate, " (resampled to 16 kHz)" if resampler else "")

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:  # noqa: BLE001
                pass
            self.stream = None


class RemoteSource(AudioSource):
    """The robot's microphone, arriving as protocol `audio` messages."""
    name = "robot-mic"

    def __init__(self):
        self._reframer: Reframer | None = None
        self._resamplers: dict[int, StreamResampler] = {}
        self._lock = threading.Lock()
        self.last_seq: int | None = None
        self.lost = 0

    def start(self, on_frame: FrameCallback) -> None:
        self._reframer = Reframer(on_frame)

    def stop(self) -> None:
        self._reframer = None

    def push(self, pcm_bytes: bytes, rate: int = SAMPLE_RATE, seq: int | None = None) -> None:
        if self._reframer is None:
            return
        if seq is not None and self.last_seq is not None and seq > self.last_seq + 1:
            self.lost += seq - self.last_seq - 1
        self.last_seq = seq if seq is not None else self.last_seq
        x = np.frombuffer(pcm_bytes[: len(pcm_bytes) // 2 * 2], dtype="<i2")
        with self._lock:
            if rate != SAMPLE_RATE:
                rs = self._resamplers.setdefault(rate, StreamResampler(rate, SAMPLE_RATE))
                x = rs(x)
            self._reframer.push(x)
