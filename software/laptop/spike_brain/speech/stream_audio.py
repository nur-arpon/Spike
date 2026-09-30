"""Spike's voice for a phone (protocol v1.5, PROTOCOL.md 10.8): one continuous
Ogg Opus stream per utterance, sentence by sentence, or plain PCM16.

Why one stream per utterance and not one file per sentence: the phone appends
every sentence to the same player buffer, so sentences follow each other with
no gap and no player restart (DESIGN.md 6d). Each sentence is padded with
silence to a whole 20 ms Opus frame and flushed to a page boundary, so a
sentence is complete (decodable to its last sample) the moment its bytes
arrive; the phone never waits for the next sentence to hear the end of this one.

Opus comes from PyAV (`av`, already in the brain's .venv for faster-whisper;
its wheels bundle libopus). The Ogg pages are written here (RFC 3533 + RFC 7845):
~60 lines, no second library, and full control over when a page is flushed.
If PyAV or libopus is missing, `opus_available()` is False and every phone gets
PCM16 instead.
"""
from __future__ import annotations

import logging
import struct

import numpy as np

log = logging.getLogger("spike.voice.stream")

OPUS_RATES = (8000, 12000, 16000, 24000, 48000)
DEFAULT_RATE = 24000               # the voice chain's own rate (engines.py brings everything to 24 kHz)
DEFAULT_BITRATE = 32000            # ~4 KB/s: fine on mobile data through Tailscale
FRAME_MS = 20
FORMATS = ("ogg_opus", "pcm_s16le")   # what the brain can send, preferred first
CHUNK_BYTES = 12 * 1024            # say_audio payload before base64 (16 KiB of JSON text)

_opus_ok: bool | None = None


def opus_available() -> bool:
    """True when PyAV with libopus is importable (checked once)."""
    global _opus_ok
    if _opus_ok is None:
        try:
            import av
            _opus_ok = "libopus" in av.codecs_available
        except Exception as e:  # noqa: BLE001
            log.warning("no Opus encoder (%s): phones get PCM16", e)
            _opus_ok = False
    return _opus_ok


def choose_format(offered: list[str] | None) -> str:
    """The first format in the phone's list that this brain can make (PCM16 if none match)."""
    for f in offered or []:
        if f == "ogg_opus" and opus_available():
            return f
        if f == "pcm_s16le":
            return f
    return "pcm_s16le"


def choose_rate(fmt: str, offered: list[int] | None) -> int:
    """Opus: the phone's first rate that Opus supports, else 24 kHz. PCM: the phone's first rate, else 24 kHz."""
    for r in offered or []:
        if fmt != "ogg_opus" or r in OPUS_RATES:
            return int(r)
    return DEFAULT_RATE


def split_bytes(data: bytes, size: int = CHUNK_BYTES) -> list[bytes]:
    return [data[i:i + size] for i in range(0, len(data), size)] or [b""]


# ---------------------------------------------------------------------- Ogg (RFC 3533)
def _crc_table() -> list[int]:
    t = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else (r << 1)
        t.append(r & 0xFFFFFFFF)
    return t


_CRC = _crc_table()


def _crc(data: bytes) -> int:
    """Ogg's CRC-32: polynomial 0x04C11DB7, not reflected, init 0, no final xor."""
    c = 0
    for b in data:
        c = ((c << 8) & 0xFFFFFFFF) ^ _CRC[((c >> 24) & 0xFF) ^ b]
    return c


def ogg_page(packets: list[bytes], granule: int, serial: int, seq: int, *, bos: bool = False,
             eos: bool = False) -> bytes:
    """One Ogg page holding whole packets (the caller keeps it under 255 lacing values)."""
    lacing = bytearray()
    for p in packets:
        n = len(p)
        lacing += b"\xff" * (n // 255) + bytes([n % 255])
    if len(lacing) > 255:
        raise ValueError("too many packets for one Ogg page")
    flags = (2 if bos else 0) | (4 if eos else 0)
    head = struct.pack("<4sBBqIIIB", b"OggS", 0, flags, granule, serial, seq, 0, len(lacing)) + bytes(lacing)
    body = b"".join(packets)
    crc = _crc(head + body)
    return head[:22] + struct.pack("<I", crc) + head[26:] + body


def _lacing_len(p: bytes) -> int:
    return len(p) // 255 + 1


# ---------------------------------------------------------------------- Opus in Ogg (RFC 7845)
class OpusOggStream:
    """One utterance's Ogg Opus stream for one phone. `add(pcm)` returns the bytes for that sentence
    (the two header pages first, on the first call) and how many samples it holds after padding."""

    def __init__(self, rate: int = DEFAULT_RATE, bitrate: int = DEFAULT_BITRATE, serial: int | None = None):
        import av
        if rate not in OPUS_RATES:
            raise ValueError(f"Opus cannot run at {rate} Hz")
        self.rate = rate
        self.frame = rate * FRAME_MS // 1000
        cc = av.CodecContext.create("libopus", "w")
        cc.sample_rate = rate
        cc.layout = "mono"
        cc.format = "s16"
        cc.bit_rate = bitrate
        cc.options = {"application": "audio", "frame_duration": str(FRAME_MS), "vbr": "on"}
        cc.open()
        self._cc = cc
        self._av = av
        head = bytes(cc.extradata or b"")
        if not head.startswith(b"OpusHead"):          # libavcodec always makes it; keep a correct fallback
            head = struct.pack("<8sBBHIhB", b"OpusHead", 1, 1, 312, rate, 0, 0)
        self._head = head
        self.serial = serial if serial is not None else (id(self) & 0x7FFFFFFF)
        self._seq = 0
        self._granule = 0                             # 48 kHz samples of every packet written so far
        self._pts = 0
        self._started = False

    def _headers(self) -> bytes:
        tags = b"spike-brain"
        comment = b"OpusTags" + struct.pack("<I", len(tags)) + tags + struct.pack("<I", 0)
        out = ogg_page([self._head], 0, self.serial, 0, bos=True) + ogg_page([comment], 0, self.serial, 1)
        self._seq = 2
        return out

    def add(self, pcm: np.ndarray) -> tuple[bytes, int]:
        pcm = np.asarray(pcm, dtype=np.int16).reshape(-1)
        pad = (-len(pcm)) % self.frame
        if pad or len(pcm) == 0:
            pcm = np.concatenate([pcm, np.zeros(pad or self.frame, np.int16)])
        out = bytearray()
        if not self._started:
            out += self._headers()
            self._started = True
        packets: list[bytes] = []
        for i in range(0, len(pcm), self.frame):
            f = self._av.AudioFrame.from_ndarray(pcm[i:i + self.frame].reshape(1, -1), format="s16", layout="mono")
            f.sample_rate = self.rate
            f.pts = self._pts
            self._pts += self.frame
            packets += [bytes(p) for p in self._cc.encode(f)]
        per = 48000 // self.rate * self.frame            # 48 kHz samples per packet
        page: list[bytes] = []
        lacing = 0
        for p in packets:
            if page and lacing + _lacing_len(p) > 255:
                out += ogg_page(page, self._granule, self.serial, self._seq)
                self._seq += 1
                page, lacing = [], 0
            page.append(p)
            lacing += _lacing_len(p)
            self._granule += per
        if page:
            out += ogg_page(page, self._granule, self.serial, self._seq)
            self._seq += 1
        return bytes(out), len(pcm)


def encode_for_client(stream: "OpusOggStream | None", fmt: str, pcm: np.ndarray) -> tuple[bytes, int]:
    """One sentence for one phone: (bytes, samples). PCM16 needs no stream."""
    if fmt == "ogg_opus" and stream is not None:
        return stream.add(pcm)
    pcm = np.asarray(pcm, dtype=np.int16).reshape(-1)
    return pcm.astype("<i2").tobytes(), len(pcm)
