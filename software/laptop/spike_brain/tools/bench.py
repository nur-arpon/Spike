"""Latency benchmark: end of the owner's speech -> Spike's first audio.

Runs the REAL brain (Silero VAD, Vosk, Whisper, Ollama, Piper, protocol
server) with a fake robot on the WebSocket. Spoken requests are synthesized
with a Piper voice that is NOT Spike's, and fed into the listener in real
time, 32 ms at a time, exactly as the microphone would deliver them.

    python -m spike_brain.tools.bench [--turns 6]

Reported per turn (ms):
  vad_tail      silence the VAD waits for before deciding you stopped
  stt           Whisper
  llm_first     first token from the language model
  first_sent    first speakable chunk complete
  tts_first     Piper for that chunk
  to_audio      END OF SPEECH -> first audio sent to the robot   <- the target (< 1500)
  to_played     END OF SPEECH -> robot reports playback started (adds network + buffer)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import threading
import time

import numpy as np

from ..brain import Brain, RunOptions
from ..config import Settings

REQUESTS = [
    "Hey Spike, what's your favourite game?",
    "Spike, tell me something funny.",
    "Spike, how was your day?",
    "Hey Spike, do you like music?",
    "Spike, what should I cook tonight?",
    "Spike, can you cheer me up a little?",
    "Spike, what do you think about cats?",
    "Hey Spike, are you hungry?",
]
# Commands answered with a scripted line (from the voice cache when it is built)
SCRIPTED = [
    "Spike, remember that I like green tea.",
    "Spike, forget that.",
    "Spike, let's play rock paper scissors.",
    "Spike, remember that my sister is called Zoe.",
    "Spike, forget that.",
    "Spike, go to sleep.",
]


class FakeRobot:
    """Plays nothing, but reports playback the way the simulator does (~30 ms after the audio lands)."""

    def __init__(self, ws):
        self.ws = ws
        self.n = 1
        self.pending: dict = {}

    async def send(self, type_, **f):
        self.n += 1
        await self.ws.send(json.dumps({"v": 1, "type": type_, "id": self.n, **f}))

    async def run(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if m["type"] == "say" and m["text"]:
                if m["audio"]:
                    self.pending[(m["utt"], m["seq"])] = m
                else:
                    asyncio.create_task(self.play(m))
            elif m["type"] == "say_audio" and m["last"]:
                say = self.pending.pop((m["utt"], m["seq"]), None)
                if say:
                    asyncio.create_task(self.play(say))
            elif m["type"] == "ping":
                await self.send("pong", re=m["id"])

    async def play(self, say):
        await asyncio.sleep(0.03)
        await self.send("say_state", utt=say["utt"], seq=say["seq"], state="started")
        await asyncio.sleep(say["duration_ms"] / 1000)
        await self.send("say_state", utt=say["utt"], seq=say["seq"], state="finished")


def owner_voice(settings: Settings):
    from ..speech.tts import PiperTTS
    spike_voice = settings.personas["dog"].voice_file
    for p in sorted(settings.path("models/piper/spicy").glob("*.onnx")) + \
            sorted(settings.path("models/piper/spike").glob("*.onnx")):
        if p != spike_voice and "amy" in p.name:
            return PiperTTS(p)
    return PiperTTS(next(p for p in sorted(settings.path("models/piper/spike").glob("*.onnx")) if p != spike_voice))


def feed_realtime(listener, pcm16k: np.ndarray, done: threading.Event) -> None:
    frame, t = 512, time.perf_counter()
    audio = np.concatenate([np.zeros(8000, np.int16), pcm16k, np.zeros(int(16000 * 1.4), np.int16)])
    for i in range(0, len(audio) - frame + 1, frame):
        listener.feed(audio[i:i + frame])
        t += frame / 16000
        delay = t - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
    done.set()


def gpu_used_mib() -> str:
    import subprocess
    try:
        return subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                              capture_output=True, text=True, timeout=5).stdout.strip() + " MiB"
    except Exception:  # noqa: BLE001
        return "?"


async def wake_timed(brain, why: str) -> None:
    """On demand: warm the language model the way the app connecting does, and time it."""
    t = time.perf_counter()
    brain.wake_llm(why)
    ok = await brain.ollama.ensure_ready(brain._warm_llm)
    share = await brain.local_llm.gpu_share() if brain.local_llm else None
    print(f"language model {'ready' if ok else 'NOT ready'} after {time.perf_counter() - t:.1f} s ({why}); "
          f"{'?' if share is None else round(share * 100)}% on the GPU; card used {gpu_used_mib()}", flush=True)


async def bench(turns: int, overrides: dict | None = None, wait_turbo: float = 240.0,
                requests: list[str] | None = None, on_demand: bool = False,
                reload: bool = False) -> list[dict]:
    from websockets.asyncio.client import connect
    from ..speech.tts import resample_int16
    s = Settings.load().override({"wake": {"follow_up_s": 0}, "vision": {"enabled": False},
                                  "memory": {"llm_extraction": False}, **(overrides or {})})
    brain = Brain(s, RunOptions(mic=False, camera=False, port=0, llm_on_demand=on_demand))
    await brain.start()
    vs = brain.voice_set
    if vs is not None and vs.turbo is not None and wait_turbo > 0:        # measure the live voice, not its backup
        ok = await asyncio.get_running_loop().run_in_executor(None, vs.turbo.wait_ready, wait_turbo)
        print(f"Turbo voice {'ready' if ok else 'NOT ready'} ({vs.plan.reason if vs.plan else ''})", flush=True)
    voice = await asyncio.get_running_loop().run_in_executor(None, owner_voice, s)
    if on_demand:
        await wake_timed(brain, "cold start, voice already loaded")
    share = await brain.local_llm.gpu_share() if brain.local_llm else None
    print(f"\nLLM {brain.local_llm.model if brain.local_llm else '-'}: "
          f"{'?' if share is None else round(share * 100)}% on the GPU; "
          f"Whisper {brain.listener.stt.model_name} on {brain.listener.stt.device}; "
          f"voice {vs.summary() if vs else '-'}\n", flush=True)
    results = []
    async with connect(f"ws://127.0.0.1:{brain.server.port}/") as ws:
        await ws.send(json.dumps({"v": 1, "type": "hello", "id": 1, "role": "tool", "device_id": "bench",
                                  "fw": "bench", "caps": ["face", "speaker"]}))
        robot = FakeRobot(ws)
        rt = asyncio.create_task(robot.run())
        for i in range(turns * (2 if reload and on_demand else 1)):
            if reload and on_demand and i == turns:
                print(f"\nwaiting for the idle unload ({s.llm.get('idle_unload')})...", flush=True)
                t_idle = time.time()
                while brain.ollama.state == "ready" and time.time() - t_idle < 600:
                    await asyncio.sleep(1)
                await asyncio.sleep(3)
                print(f"language model {brain.ollama.state} after {time.time() - t_idle:.0f} s; "
                      f"card used {gpu_used_mib()}; voice {vs.turbo.state if vs and vs.turbo else '-'}", flush=True)
                await wake_timed(brain, "reload after idle unload")
            reqs = requests or REQUESTS
            text = reqs[i % len(reqs)]
            sp = voice.synthesize(text)
            pcm = resample_int16(sp.pcm, sp.rate, 16000)
            before = len(brain.timings)
            done = threading.Event()
            threading.Thread(target=feed_realtime, args=(brain.listener, pcm, done), daemon=True).start()
            t0 = time.time()
            while len(brain.timings) == before and time.time() - t0 < 40:
                await asyncio.sleep(0.05)
            while brain.speech.speaking and time.time() - t0 < 60:
                await asyncio.sleep(0.05)
            await asyncio.sleep(0.6)
            if len(brain.timings) > before:
                r = dict(brain.timings[-1])
                if brain.speech.current and brain.speech.current.t_first_played and brain.current_timing:
                    r["speech_end_to_first_played_ms"] = round(
                        (brain.speech.current.t_first_played - brain.current_timing.speech_end) * 1000)
                r["request"] = text
                r["phase"] = "reload" if i >= turns else "warm"
                results.append(r)
                print(f"{i + 1}. {text!r}\n   vad_tail {r['vad_tail_ms']}  stt {r['stt_ms']}  "
                      f"llm_first {r['llm_first_token_ms']}  first_sent {r['first_sentence_ms']}  "
                      f"tts_first {r['tts_first_ms']} ({r.get('tts_engine') or '?'})  ->  "
                      f"to_audio {r['speech_end_to_first_audio_ms']}  "
                      f"to_played {r['speech_end_to_first_played_ms']}  (prompt {r.get('prompt_tokens')} tok in "
                      f"{r.get('prompt_ms')} ms, reply {r.get('tokens')} tok)", flush=True)
            else:
                print(f"{i + 1}. {text!r}: no reply (not heard?)", flush=True)
        rt.cancel()
    if vs is not None:
        print(f"voices used: {vs.summary().get('used')}", flush=True)
    await brain.shutdown()
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--engine", choices=["turbo", "kokoro", "piper"], help="voice engine (default: settings)")
    ap.add_argument("--turbo-dtype", choices=["auto", "fp32", "bf16"], help="Turbo precision (default: settings)")
    ap.add_argument("--whisper", choices=["auto", "cuda", "cpu"], help="where Whisper runs (default: settings)")
    ap.add_argument("--whisper-cpu-model", help="Whisper model used on the processor, e.g. base.en or small.en")
    ap.add_argument("--scripted", action="store_true", help="commands answered with scripted (cached) lines")
    ap.add_argument("--on-demand", action="store_true",
                    help="language model on demand ([llm] on_demand): warmed after the voice, as when the app connects")
    ap.add_argument("--reload", action="store_true",
                    help="with --on-demand: after the turns, wait for the idle unload, wake it again, repeat the turns")
    ap.add_argument("--idle-unload", help="with --reload: [llm] idle_unload for this run (e.g. 30s)")
    ap.add_argument("--llm-gpu-layers", type=int, help="language model layers on the graphics card (-1 = all that fit)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    ov: dict = {}
    if args.engine:
        ov.setdefault("tts", {})["engine"] = args.engine
    if args.turbo_dtype:
        ov.setdefault("tts", {}).setdefault("turbo", {})["dtype"] = args.turbo_dtype
    if args.whisper:
        ov.setdefault("stt", {})["device"] = args.whisper
    if args.whisper_cpu_model:
        ov.setdefault("stt", {})["cpu_model"] = args.whisper_cpu_model
    if args.llm_gpu_layers is not None:
        ov.setdefault("llm", {})["gpu_layers"] = args.llm_gpu_layers
    if args.idle_unload:
        ov.setdefault("llm", {})["idle_unload"] = args.idle_unload
    results = asyncio.run(bench(args.turns, ov, requests=SCRIPTED if args.scripted else None,
                                on_demand=args.on_demand, reload=args.reload))
    if args.on_demand and args.reload:
        for name, part in (("warm (first wake)", "warm"), ("after idle unload + reload", "reload")):
            v = [r["speech_end_to_first_audio_ms"] for r in results
                 if r.get("phase") == part and r.get("speech_end_to_first_audio_ms")]
            if v:
                print(f"{name}: median {statistics.median(v):.0f} ms, min {min(v)}, max {max(v)} (n={len(v)})")
    vals = [r["speech_end_to_first_audio_ms"] for r in results if r.get("speech_end_to_first_audio_ms")]
    played = [r["speech_end_to_first_played_ms"] for r in results if r.get("speech_end_to_first_played_ms")]
    if vals:
        print(f"\nEnd of speech -> first audio sent:  median {statistics.median(vals):.0f} ms, "
              f"min {min(vals)}, max {max(vals)}  (n={len(vals)})")
    if played:
        print(f"End of speech -> playback started:  median {statistics.median(played):.0f} ms, "
              f"min {min(played)}, max {max(played)}")
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)
