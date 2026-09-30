"""Writes software/protocol/ble_frame_vectors.json from ble_frames.py (PROTOCOL.md 11.2).

Run: python software/protocol/tools/make_ble_vectors.py
Every implementation (app, firmware host test, fake robot) replays the file:
  encode: {start_counter, att_mtu, message(utf-8 text)} -> frames (hex)
  decode: frames (hex) in order -> the messages that come out (text), dropped count
"""
from __future__ import annotations

import json
from pathlib import Path

from ble_frames import MAX_MESSAGE, Decoder, Encoder

OUT = Path(__file__).resolve().parents[1] / "ble_frame_vectors.json"


def enc(msg: str, mtu: int, start: int = 0) -> list[str]:
    e = Encoder()
    e.counter = start
    return [f.hex() for f in e.encode(msg.encode("utf-8"), mtu)]


def dec(frames: list[str]) -> dict:
    d = Decoder()
    out = []
    for f in frames:
        m = d.feed(bytes.fromhex(f))
        if m is not None:
            out.append(m.decode("utf-8"))
    return {"frames": frames, "messages": out, "dropped": d.dropped, "too_big": d.too_big}


def main() -> None:
    hello = ('{"v":1,"type":"hello","id":1,"role":"face","device_id":"spike-7c9e2a","fw":"0.2.0",'
             '"caps":["face","speaker","mic","touch","imu","edge","battery","drive"],"link":"ble"}')
    mood = '{"v":1,"type":"mood","id":3,"mood":"happy"}'
    say = ('{"v":1,"type":"say","id":9,"utt":"p4","seq":0,"final":true,"text":"Café time! I’m right here.",'
           '"mood":"happy","duration_ms":1800,"audio":null,"mouth":{"rate_hz":50,"values":[0,12,55,80,61,30,4,0]}}')
    encode = []
    for name, msg, mtu, start in (("ping at MTU 23 (two frames)", '{"v":1,"type":"ping","id":1}', 23, 0),
                                  ("hello at MTU 23", hello, 23, 0),
                                  ("hello at MTU 185", hello, 185, 0),
                                  ("hello at MTU 517 (one frame)", hello, 517, 0),
                                  ("utf-8 caption at MTU 23", say, 23, 5),
                                  ("counter wraps 62 -> 0", hello, 40, 62),
                                  ("empty message", "", 23, 0)):
        encode.append({"name": name, "att_mtu": mtu, "start_counter": start, "message": msg,
                       "frames": enc(msg, mtu, start)})

    h23 = enc(hello, 23)                                 # 10 frames, counters 0..9
    m_after = enc(mood, 23, len(h23))                    # continues the counter
    decode = [
        {"name": "two messages in a row", **dec(h23 + m_after)},
        {"name": "a lost frame drops that message only", **dec(h23[:3] + h23[4:] + enc(mood, 23, len(h23)))},
        {"name": "a START while building restarts", **dec(h23[:4] + enc(mood, 185, 4))},
        {"name": "a continuation with nothing open is dropped", **dec([h23[2]] + enc(mood, 185, 3))},
        {"name": "counter wraps", **dec(enc(hello, 40, 62) + enc(mood, 40, (62 + len(enc(hello, 40, 62))) % 64))},
    ]
    big = '{"v":1,"type":"log","id":2,"msg":"' + "x" * (MAX_MESSAGE) + '"}'
    big_frames = enc_unchecked(big, 517)
    decode.append({"name": "over 16 KiB is dropped, the next message still arrives",
                   **dec(big_frames + enc(mood, 517, len(big_frames) % 64))})
    OUT.write_text(json.dumps({"spec": "PROTOCOL.md 11.2 (v1.3)", "max_message": MAX_MESSAGE,
                               "encode": encode, "decode": decode}, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"wrote {OUT} ({len(encode)} encode, {len(decode)} decode cases)")


def enc_unchecked(msg: str, mtu: int) -> list[str]:
    """Frames for a message the encoder would refuse (to test the receiver's limit)."""
    data = msg.encode("utf-8")
    size = mtu - 4
    pieces = [data[i:i + size] for i in range(0, len(data), size)]
    out = []
    for i, p in enumerate(pieces):
        h = (i & 0x3F) | (0x80 if i == 0 else 0) | (0x40 if i == len(pieces) - 1 else 0)
        out.append((bytes([h]) + p).hex())
    return out


if __name__ == "__main__":
    main()
