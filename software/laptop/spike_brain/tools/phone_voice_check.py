"""End-to-end check of Spike's laptop voice on the phone (protocol v1.5, PROTOCOL.md 10.8).

Plays the part of the phone app against a REAL, already running brain: says hello
as role "app" with cap `audio_out` (Ogg Opus first, like the app), types a message,
collects the reply's audio, reports say_state like the app does, and checks that
the audio decodes (FFmpeg via PyAV) to non-silent speech of the announced length.
Nothing is played out loud.

    python -m spike_brain.tools.phone_voice_check --port 8765 [--format ogg_opus|pcm_s16le]
        [--say "what time is it"] [--say "tell me about your day"] [--save out_dir]

Prints, per message (ms from the typed message leaving this client):
  first_say    the first `say` (caption) arrived
  first_audio  the first `say_audio` frame arrived   <- "typed -> first audio at the app"
  last_audio   the last audio frame of the reply
Exit code 0 = every reply had decodable, non-silent audio of plausible length.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from pathlib import Path

import numpy as np


async def one_turn(ws, ids, text: str, save: Path | None, n: int) -> dict:
    t0 = time.perf_counter()
    ids[0] += 1
    await ws.send(json.dumps({"v": 1, "type": "text", "id": ids[0], "text": text}))
    says, data, first_say, first_audio, last_audio = [], bytearray(), None, None, None
    fmt, rate = None, None
    want, got, final = 0, 0, False          # chunks announced / received; the final say seen
    end = time.monotonic() + 90
    while time.monotonic() < end:
        try:
            m = json.loads(await asyncio.wait_for(ws.recv(), max(0.05, end - time.monotonic())))
        except asyncio.TimeoutError:
            break
        now = (time.perf_counter() - t0) * 1000
        if m["type"] == "ping":
            ids[0] += 1
            await ws.send(json.dumps({"v": 1, "type": "pong", "id": ids[0], "re": m["id"]}))
        elif m["type"] == "say" and m.get("play"):
            if m["text"]:
                says.append(m)
                first_say = first_say or now
                if m["audio"]:
                    fmt, rate = m["audio"]["format"], m["audio"]["rate"]
                    want += m["audio"]["chunks"]
                for state in ("started", "finished"):          # like the app, a little early: no playback here
                    ids[0] += 1
                    await ws.send(json.dumps({"v": 1, "type": "say_state", "id": ids[0], "utt": m["utt"],
                                              "seq": m["seq"], "state": state}))
            final = final or m["final"]
        elif m["type"] == "say_audio":
            from spike_brain import protocol as P
            data += P.unb64(m["data"])
            got += 1
            first_audio = first_audio or now
            last_audio = now
        elif m["type"] == "say" and m["text"]:
            print(f"  !! a say without play: {m['text']!r} (the brain did not route it to this phone)")
        if final and got >= want:
            break
    announced_ms = sum(s["duration_ms"] for s in says if s["audio"])
    res = {"text": text, "said": " ".join(s["text"] for s in says), "format": fmt, "bytes": len(data),
           "first_say": first_say, "first_audio": first_audio, "last_audio": last_audio,
           "announced_ms": announced_ms, "ok": False}
    if not data:
        res["why"] = "no audio"
        return res
    if fmt == "ogg_opus":
        import av
        c = av.open(io.BytesIO(bytes(data)), format="ogg")
        frames = [f.to_ndarray().reshape(-1) for f in c.decode(audio=0)]
        pcm_rate = c.streams.audio[0].codec_context.sample_rate or 48000
        c.close()
        pcm = np.concatenate(frames).astype(np.float32)
        if pcm.dtype.kind != "f" or np.abs(pcm).max() > 2:
            pcm = pcm / 32768.0
    else:
        pcm = np.frombuffer(bytes(data), "<i2").astype(np.float32) / 32768.0
        pcm_rate = rate
    dur_ms = len(pcm) * 1000 / pcm_rate
    rms_db = 20 * np.log10(max(1e-9, float(np.sqrt(np.mean(pcm ** 2)))))
    res.update(decoded_ms=round(dur_ms), rms_dbfs=round(rms_db, 1),
               kbps=round(len(data) * 8 / max(1, dur_ms), 1))
    words = len(res["said"].split())
    plausible = abs(dur_ms - announced_ms) < 120 and 150 * words <= dur_ms + 400 <= 1500 * words + 3000
    res["ok"] = bool(rms_db > -40 and plausible)
    if not res["ok"]:
        res["why"] = f"silent or implausible (rms {rms_db:.1f} dBFS, {dur_ms:.0f} ms for {words} words)"
    if save:
        save.mkdir(parents=True, exist_ok=True)
        (save / f"reply_{n}.{'ogg' if fmt == 'ogg_opus' else 'pcm'}").write_bytes(bytes(data))
    return res


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--format", default="ogg_opus", choices=["ogg_opus", "pcm_s16le"])
    ap.add_argument("--say", action="append")
    ap.add_argument("--save", type=Path)
    ap.add_argument("--token", default="")
    a = ap.parse_args(argv)
    from websockets.asyncio.client import connect
    formats = [a.format] + [f for f in ("ogg_opus", "pcm_s16le") if f != a.format]
    hello = {"v": 1, "type": "hello", "id": 1, "role": "app", "device_id": "phone-voice-check", "fw": "0.3.0",
             "caps": ["face", "text", "mic", "audio_out"], "audio_out": {"formats": formats, "rates": [24000]}}
    if a.token:
        hello["token"] = a.token
    ids = [1]
    all_ok = True
    async with connect(f"ws://{a.host}:{a.port}/", max_size=2 ** 20) as ws:
        await ws.send(json.dumps(hello))
        h = json.loads(await ws.recv())
        print("hello audio:", h.get("audio"))
        # let the on-connect burst pass
        end = time.monotonic() + 1.5
        while time.monotonic() < end:
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), 0.3))
                if m["type"] == "ping":
                    ids[0] += 1
                    await ws.send(json.dumps({"v": 1, "type": "pong", "id": ids[0], "re": m["id"]}))
            except asyncio.TimeoutError:
                pass
        for n, text in enumerate(a.say or ["what time is it", "tell me one nice thing about dogs"]):
            r = await one_turn(ws, ids, text, a.save, n)
            all_ok &= r["ok"]
            print(json.dumps(r, indent=None, default=lambda x: round(x) if isinstance(x, float) else str(x)))
            await asyncio.sleep(1.0)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
