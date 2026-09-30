"""Reference implementation of the BLE framing of PROTOCOL.md 11.2 (v1.3).

The app (Dart), the screen board (C++) and the fake robot all implement the
same rules; `ble_frame_vectors.json` next to PROTOCOL.md is generated from this
file (`python make_ble_vectors.py`) and every implementation's tests replay it.

    header byte: bit 7 START, bit 6 END, bits 5..0 frame counter (0..63)
"""
from __future__ import annotations

START = 0x80
END = 0x40
COUNTER_MASK = 0x3F
MAX_MESSAGE = 16 * 1024


def payload_size(att_mtu: int) -> int:
    """Bytes of message per frame for a negotiated ATT MTU (ATT header 3, our header 1)."""
    return max(1, att_mtu - 3 - 1)


class Encoder:
    """Cuts messages into frames. One encoder per direction per connection."""

    def __init__(self) -> None:
        self.counter = 0

    def reset(self) -> None:
        self.counter = 0

    def encode(self, message: bytes, att_mtu: int) -> list[bytes]:
        if len(message) > MAX_MESSAGE:
            raise ValueError("message over 16 KiB")
        size = payload_size(att_mtu)
        pieces = [message[i:i + size] for i in range(0, len(message), size)] or [b""]
        frames = []
        for i, piece in enumerate(pieces):
            header = self.counter & COUNTER_MASK
            if i == 0:
                header |= START
            if i == len(pieces) - 1:
                header |= END
            frames.append(bytes([header]) + piece)
            self.counter = (self.counter + 1) & COUNTER_MASK
        return frames


class Decoder:
    """Rebuilds messages from frames. feed() returns a finished message or None.

    Events for tests/logs: `self.dropped` counts messages thrown away (lost frames,
    a restart, or too big); `self.too_big` is set once per over-long message."""

    def __init__(self) -> None:
        self.expected: int | None = None
        self.buf: bytearray | None = None
        self.dropped = 0
        self.too_big = False
        self._skip = False            # skipping the rest of an over-long message

    def reset(self) -> None:
        self.expected = None
        self.buf = None
        self._skip = False

    def feed(self, frame: bytes) -> bytes | None:
        if not frame:
            return None
        header, payload = frame[0], frame[1:]
        counter = header & COUNTER_MASK
        if self.expected is not None and counter != self.expected:
            if self.buf is not None:              # frames were lost: drop the partial message
                self.dropped += 1
            self.buf = None
            self._skip = False
        self.expected = (counter + 1) & COUNTER_MASK
        if header & START:
            if self.buf is not None:              # a new message while one was open
                self.dropped += 1
            self.buf = bytearray()
            self._skip = False
        elif self.buf is None:
            return None                           # a continuation with nothing open: drop it
        if self._skip:
            if header & END:
                self.buf = None
                self._skip = False
            return None
        self.buf.extend(payload)
        if len(self.buf) > MAX_MESSAGE:
            self.dropped += 1
            self.too_big = True
            self._skip = not (header & END)
            self.buf = bytearray() if self._skip else None
            return None
        if header & END:
            msg = bytes(self.buf)
            self.buf = None
            return msg
        return None
