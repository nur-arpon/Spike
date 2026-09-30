"""Chatterbox Turbo voice worker: a small local HTTP server that runs in its OWN
Python (software/laptop/.venv-chatterbox, which has CUDA PyTorch; the brain's
.venv has no torch).

The brain starts and supervises it (speech/turbo.py). It is standalone on
purpose: it imports nothing from spike_brain, only the standard library,
numpy, torch and chatterbox, so it runs in the other venv.

    .venv-chatterbox\\Scripts\\python.exe spike_brain/speech/turbo_worker.py \\
        --models models/chatterbox-turbo --voice spike=...wav --voice spicy=...wav

Listens on 127.0.0.1 only. Prints one line "SPIKE_TTS_PORT=<n>" on stdout once
the socket is open (the model may still be loading; poll /health).

  GET  /health            {"state": "loading"|"ready"|"error", vram, voices, ...}
  POST /synth             {"voice", "text", "seed"} -> 16-bit mono PCM (little endian),
                          headers X-Sample-Rate, X-Gen-Ms, X-Audio-Ms
  POST /release           free cached GPU memory (torch.cuda.empty_cache)
  POST /shutdown          exit cleanly

Every request must carry the header X-Spike-Token equal to the SPIKE_TTS_TOKEN
environment variable the brain set (so no other program on the laptop can
drive it). One sentence per /synth call, whole sentences only: no splitting,
no trimming, no inserted silence (software/research/voice/postmortem.md).
The worker exits by itself when the brain process that started it dies.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Turbo generate() defaults, exactly as the owner's picks (Spike B, Spicy C) were made
# in voice_lab/gen_chatterbox.py: temperature 0.8, top_p 0.95, top_k 1000,
# repetition_penalty 1.2, reference loudness-normalised. Seed 1234 unless the caller asks.
DEFAULT_SEED = 1234


def say(*args, **kwargs) -> None:
    """print() that never raises: if the brain died, stdout is a broken pipe, and a
    failing print must not stop the watchdog from shutting the worker down."""
    try:
        print(*args, **kwargs)
    except (OSError, ValueError):
        pass


class Engine:
    def __init__(self, models: Path, device: str, dtype: str, voices: dict[str, Path]):
        self.models, self.device, self.dtype = models, device, dtype
        self.voice_refs = voices
        self.state = "loading"
        self.error = ""
        self.model = None
        self.conds: dict[str, object] = {}
        self.sr = 24000
        self.lock = threading.Lock()
        self.synth_count = 0
        self.load_s = 0.0
        self.started = time.time()

    def load(self) -> None:
        try:
            t = time.perf_counter()
            import torch
            from chatterbox.tts_turbo import ChatterboxTurboTTS
            dev = self.device
            if dev == "cuda" and not torch.cuda.is_available():
                say("CUDA not available, the voice runs on the processor (slow)", flush=True)
                dev = self.device = "cpu"
            m = ChatterboxTurboTTS.from_local(self.models, dev)
            if self.dtype == "bf16" and dev == "cuda":
                m.t3.to(dtype=torch.bfloat16)          # tested in voice_lab/turbo_speed_probe.py: -0.8 GB
                torch.cuda.empty_cache()                # hand the freed fp32 copy back to the card
            self.model, self.sr = m, int(m.sr)
            for name, ref in self.voice_refs.items():
                self.prepare(name, ref)
            with self.lock:                             # warm-up (first CUDA call compiles kernels)
                torch.manual_seed(DEFAULT_SEED)
                m.conds = next(iter(self.conds.values())) if self.conds else m.conds
                with self.autocast():
                    m.generate("Warming up the voice.")
            self.load_s = time.perf_counter() - t
            self.state = "ready"
            say(f"turbo ready on {dev} ({self.dtype}) in {self.load_s:.1f} s; voices: "
                  f"{', '.join(self.conds) or 'none'}; {self.vram()}", flush=True)
        except Exception as e:  # noqa: BLE001
            self.state, self.error = "error", f"{type(e).__name__}: {e}"
            traceback.print_exc()
            sys.stdout.flush()

    def autocast(self):
        """bf16 mode stores the text-to-token model (t3) in bfloat16 and must run under autocast
        (voice_lab/turbo_speed_probe.py); fp32 mode, as the owner's picks were made, runs as shipped."""
        import contextlib
        import torch
        if self.dtype == "bf16" and self.device == "cuda":
            return torch.autocast("cuda", dtype=torch.bfloat16)
        return contextlib.nullcontext()

    def prepare(self, name: str, ref: Path) -> None:
        """Voice conditioning is computed once per persona and kept (same voice every line)."""
        with self.lock:
            self.model.prepare_conditionals(str(ref), norm_loudness=True)
            self.conds[name] = self.model.conds

    def synth(self, voice: str, text: str, seed: int) -> tuple[bytes, float, float]:
        import numpy as np
        import torch
        if self.state != "ready":
            raise RuntimeError(f"not ready ({self.state})")
        if voice not in self.conds:
            raise KeyError(f"unknown voice {voice!r}")
        with self.lock:
            self.model.conds = self.conds[voice]
            torch.manual_seed(int(seed))
            t = time.perf_counter()
            with self.autocast():
                wav = self.model.generate(text).squeeze(0).float().cpu().numpy()
            if self.device == "cuda":
                torch.cuda.synchronize()
            gen_ms = (time.perf_counter() - t) * 1000
            self.synth_count += 1
        pcm = np.clip(np.round(wav * 32767.0), -32768, 32767).astype("<i2")
        return pcm.tobytes(), gen_ms, len(pcm) * 1000.0 / self.sr

    def vram(self) -> str:
        try:
            import torch
            if self.device != "cuda":
                return "cpu"
            return (f"VRAM allocated {torch.cuda.memory_allocated() / 2**20:.0f} MiB, reserved "
                    f"{torch.cuda.memory_reserved() / 2**20:.0f} MiB, peak reserved "
                    f"{torch.cuda.max_memory_reserved() / 2**20:.0f} MiB")
        except Exception:  # noqa: BLE001
            return "?"

    def health(self) -> dict:
        d = {"state": self.state, "error": self.error, "device": self.device, "dtype": self.dtype,
             "voices": sorted(self.conds), "sample_rate": self.sr, "synth_count": self.synth_count,
             "load_s": round(self.load_s, 1), "uptime_s": round(time.time() - self.started), "pid": os.getpid()}
        try:
            import torch
            if self.device == "cuda" and torch.cuda.is_available():
                d["vram_allocated_mib"] = round(torch.cuda.memory_allocated() / 2**20)
                d["vram_reserved_mib"] = round(torch.cuda.memory_reserved() / 2**20)
                d["vram_peak_reserved_mib"] = round(torch.cuda.max_memory_reserved() / 2**20)
        except Exception:  # noqa: BLE001
            pass
        return d

    def release(self) -> None:
        try:
            import torch
            if self.device == "cuda":
                with self.lock:
                    torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass


def make_handler(engine: Engine, token: str, server_ref: dict):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):   # quiet: the brain logs what matters
            pass

        def _authorised(self) -> bool:
            if token and self.headers.get("X-Spike-Token", "") != token:
                self._json(403, {"error": "bad token"})
                return False
            return True

        def _json(self, code: int, obj: dict) -> None:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 64 * 1024:
                raise ValueError("request too large")
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def do_GET(self):
            if not self._authorised():
                return
            if self.path == "/health":
                self._json(200, engine.health())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._authorised():
                return
            try:
                req = self._body()
            except Exception as e:  # noqa: BLE001
                self._json(400, {"error": str(e)})
                return
            if self.path == "/synth":
                text = str(req.get("text", "")).strip()
                if not text or len(text) > 600:
                    self._json(400, {"error": "text must be 1-600 characters"})
                    return
                try:
                    pcm, gen_ms, audio_ms = engine.synth(str(req.get("voice", "")), text,
                                                         int(req.get("seed", DEFAULT_SEED)))
                except KeyError as e:
                    self._json(404, {"error": str(e)})
                    return
                except Exception as e:  # noqa: BLE001
                    traceback.print_exc()
                    sys.stdout.flush()
                    self._json(503, {"error": f"{type(e).__name__}: {e}"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(pcm)))
                self.send_header("X-Sample-Rate", str(engine.sr))
                self.send_header("X-Gen-Ms", f"{gen_ms:.1f}")
                self.send_header("X-Audio-Ms", f"{audio_ms:.1f}")
                self.end_headers()
                self.wfile.write(pcm)
            elif self.path == "/release":
                engine.release()
                self._json(200, engine.health())
            elif self.path == "/shutdown":
                self._json(200, {"ok": True})
                threading.Thread(target=server_ref["server"].shutdown, daemon=True).start()
            else:
                self._json(404, {"error": "not found"})

    return Handler


def parent_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000 | 0x1000, False, pid)   # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102        # WAIT_TIMEOUT = still running
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Spike's Chatterbox Turbo voice worker")
    ap.add_argument("--models", type=Path, required=True, help="folder with the Turbo weights")
    ap.add_argument("--voice", action="append", default=[], help="name=reference.wav (repeatable)")
    ap.add_argument("--device", default="cuda", choices=["cuda", "cpu"])
    ap.add_argument("--dtype", default="fp32", choices=["fp32", "bf16"])
    ap.add_argument("--port", type=int, default=0, help="0 = any free port (printed on stdout)")
    ap.add_argument("--parent-pid", type=int, default=0, help="exit when this process dies")
    args = ap.parse_args(argv)
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass
    voices = {}
    for v in args.voice:
        name, _, path = v.partition("=")
        voices[name.strip()] = Path(path.strip())
    token = os.environ.get("SPIKE_TTS_TOKEN", "")
    engine = Engine(args.models, args.device, args.dtype, voices)
    ref: dict = {}
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(engine, token, ref))
    server.daemon_threads = True
    ref["server"] = server
    say(f"SPIKE_TTS_PORT={server.server_address[1]}", flush=True)
    threading.Thread(target=engine.load, name="load", daemon=True).start()

    # On Windows a venv's python.exe is a small launcher that starts the real interpreter as
    # its child, so this process has TWO things to watch: the brain (--parent-pid) and the
    # launcher that started us (our direct parent). If the brain kills the launcher during a
    # restart, or the brain itself dies, we must not linger holding 3 GB of graphics memory.
    launcher = os.getppid()

    def watchdog():
        while True:
            time.sleep(1.0)
            if not parent_alive(args.parent_pid) or not parent_alive(launcher):
                say("the brain is gone; the voice worker stops", flush=True)
                threading.Thread(target=server.shutdown, daemon=True).start()
                time.sleep(3.0)
                os._exit(0)          # never hang on a CUDA call or a stuck request
    threading.Thread(target=watchdog, name="watchdog", daemon=True).start()
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        engine.release()
        say("voice worker stopped", flush=True)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)          # do not wait for CUDA/daemon threads: the brain expects a quick exit
