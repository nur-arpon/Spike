"""Labelled voice samples through the REAL brain pipeline, for the owner to hear.

    python -m spike_brain.tools.make_voice_samples

Starts the real brain (language model, voice chain, protocol server) with a fake
robot on the WebSocket that records exactly the audio the robot would play.
Live replies go owner text -> safety -> language model -> sentences -> live
Turbo; cached lines go through say_line -> voice cache. Each WAV starts with a
short spoken label (Kokoro bf_emma), e.g. "Spike, live reply.", then the reply.
Writes voice_samples/integrated/*.wav and index.txt. Plays nothing aloud.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
from pathlib import Path

import numpy as np

from ..brain import Brain, RunOptions
from ..config import Settings
from ..speech.engines import OUT_RATE, KokoroEngine, level, write_wav
from ..speech.tts import resample_int16

LIVE = {"dog": ["Hi Spike, I'm home! How was your day?", "Tell me a joke about your tiny legs."],
        "cat": ["Spicy, what do you think of dogs?", "Did you miss me today?"]}
CACHED = {"dog": ["come_home", "alarm", "hungry"], "cat": ["greet_afternoon", "trick_refuse", "rps_lose"]}
NAMES = {"dog": "Spike", "cat": "Spicy"}


class Recorder:
    """A fake robot: reports playback like the simulator and keeps every audio chunk."""

    def __init__(self, ws):
        self.ws, self.n = ws, 1
        self.say: dict = {}
        self.chunks: dict = {}
        self.order: list = []

    async def send(self, type_, **f):
        self.n += 1
        await self.ws.send(json.dumps({"v": 1, "type": type_, "id": self.n, **f}))

    async def run(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if m["type"] == "say" and m.get("text"):
                k = (m["utt"], m["seq"])
                self.say[k] = m
                self.order.append(k)
                if not m.get("audio"):
                    asyncio.create_task(self.play(m))
            elif m["type"] == "say_audio":
                k = (m["utt"], m["seq"])
                self.chunks.setdefault(k, []).append((m["index"], base64.b64decode(m["data"])))
                if m["last"] and k in self.say:
                    asyncio.create_task(self.play(self.say[k]))
            elif m["type"] == "ping":
                await self.send("pong", re=m["id"])

    async def play(self, say):
        await self.send("say_state", utt=say["utt"], seq=say["seq"], state="started")
        await asyncio.sleep(say["duration_ms"] / 1000 * 0.2)        # no need to wait in real time
        await self.send("say_state", utt=say["utt"], seq=say["seq"], state="finished")

    def take(self, since: int) -> tuple[np.ndarray, list[str]]:
        """Audio of every segment said since index `since`, back to back as the robot plays it."""
        pcm, texts = [], []
        for k in self.order[since:]:
            parts = sorted(self.chunks.get(k, []))
            if not parts:
                continue
            a = np.frombuffer(b"".join(p for _, p in parts), dtype="<i2")
            rate = (self.say[k].get("audio") or {}).get("rate", OUT_RATE)
            pcm.append(resample_int16(a.astype(np.int16), rate, OUT_RATE) if rate != OUT_RATE else a)
            texts.append(self.say[k]["text"])
        return (np.concatenate(pcm) if pcm else np.zeros(0, np.int16)), texts


async def wait_quiet(brain: Brain, timeout: float = 90) -> None:
    t = time.time()
    await asyncio.sleep(0.3)
    while time.time() - t < timeout and ((brain.speech and brain.speech.speaking) or not brain.idle()):
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.5)


async def make(out_dir: Path) -> list[str]:
    from websockets.asyncio.client import connect
    s = Settings.load().override({"vision": {"enabled": False}, "life": {"greet_on_start": False},
                                  "memory": {"llm_extraction": False}, "wake": {"follow_up_s": 0}})
    brain = Brain(s, RunOptions(mic=False, camera=False, port=0, mode="dog"))
    await brain.start()
    vs = brain.voice_set
    ok = vs is not None and vs.turbo is not None and await asyncio.get_running_loop().run_in_executor(
        None, vs.turbo.wait_ready, 240)
    print(f"Turbo {'ready' if ok else 'NOT READY'}; {vs.summary() if vs else ''}", flush=True)
    kokoro = KokoroEngine(s.path(s.tts.kokoro.model), s.path(s.tts.kokoro.voices))
    out_dir.mkdir(parents=True, exist_ok=True)
    index = []
    async with connect(f"ws://127.0.0.1:{brain.server.port}/", max_size=None) as ws:
        await ws.send(json.dumps({"v": 1, "type": "hello", "id": 1, "role": "tool", "device_id": "samples",
                                  "fw": "samples", "caps": ["face", "speaker"]}))
        rec = Recorder(ws)
        rt = asyncio.create_task(rec.run())
        await asyncio.sleep(0.5)
        n = 0
        for mode in ("dog", "cat"):
            if brain.mode != mode:
                await brain.set_mode(mode, announce=False)
                await wait_quiet(brain)
            name = NAMES[mode]
            jobs = [("live", t) for t in LIVE[mode]] + [("cached", k) for k in CACHED[mode]]
            for kind, what in jobs:
                chain = brain.voices[mode]
                before_stats = dict(chain.stats)
                since = len(rec.order)
                if kind == "live":
                    await brain.console_turn(what)
                else:
                    await brain.say_line(what)
                await wait_quiet(brain)
                audio, texts = rec.take(since)
                used = {k: chain.stats.get(k, 0) - before_stats.get(k, 0) for k in chain.stats}
                used = {k: v for k, v in used.items() if v}
                label_text = f"{name}, {'live reply' if kind == 'live' else 'cached line'}."
                lab, lr = await asyncio.get_running_loop().run_in_executor(None, kokoro.synthesize, label_text,
                                                                           "bf_emma")
                lab = level(resample_int16(lab, lr, OUT_RATE), OUT_RATE, -20.0)
                gap = np.zeros(int(0.6 * OUT_RATE), np.int16)       # a clear gap between label and sample
                n += 1
                fname = f"{n:02d} {name.lower()} {kind} - {'-'.join(what.split()[:4]).strip('?!.,')}.wav".replace(
                    "'", "")
                write_wav(out_dir / fname, np.concatenate([lab, gap, audio]), OUT_RATE)
                line = (f"{fname}\n    asked: {what}\n    said: {' '.join(texts)}\n    voice used: {used}  "
                        f"({len(audio) / OUT_RATE:.1f} s)")
                print(line, flush=True)
                index.append(line)
        rt.cancel()
    await brain.shutdown()
    (out_dir / "index.txt").write_text(
        "Labelled samples made through the real brain (fake robot recording what it would play).\n"
        "Each file starts with a spoken label (Kokoro bf_emma).\n\n" + "\n".join(index) + "\n", encoding="utf-8")
    return index


def main(argv=None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    out = Settings.load().path("voice_samples") / "integrated"
    asyncio.run(make(out))
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
