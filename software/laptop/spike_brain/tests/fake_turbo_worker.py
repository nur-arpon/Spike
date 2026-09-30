"""A stand-in for speech/turbo_worker.py in tests: same command line and HTTP API,
no torch, no GPU. Answers /synth with 0.5 s of tone. Behaviour switches (env):

  FAKE_TURBO_EXIT_AFTER=n   exit hard after n synth calls (a crash)
  FAKE_TURBO_HANG=1         /synth never answers (a hung worker)
  FAKE_TURBO_LOAD_S=x       pretend loading takes x seconds
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models")
    ap.add_argument("--voice", action="append", default=[])
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--dtype", default="fp32")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--parent-pid", type=int, default=0)
    args = ap.parse_args()
    token = os.environ.get("SPIKE_TTS_TOKEN", "")
    exit_after = int(os.environ.get("FAKE_TURBO_EXIT_AFTER", "0") or 0)
    hang = os.environ.get("FAKE_TURBO_HANG") == "1"
    load_s = float(os.environ.get("FAKE_TURBO_LOAD_S", "0.2"))
    state = {"state": "loading", "n": 0, "started": time.time()}
    voices = sorted(v.partition("=")[0] for v in args.voice)

    def loaded():
        time.sleep(load_s)
        state["state"] = "ready"
    threading.Thread(target=loaded, daemon=True).start()

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.headers.get("X-Spike-Token") != token:
                return self._json(403, {"error": "bad token"})
            self._json(200, {"state": state["state"], "pid": os.getpid(), "voices": voices, "synth_count": state["n"],
                             "load_s": load_s, "dtype": args.dtype, "device": args.device})

        def do_POST(self):
            if self.headers.get("X-Spike-Token") != token:
                return self._json(403, {"error": "bad token"})
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/shutdown":
                self._json(200, {"ok": True})
                threading.Thread(target=lambda: (time.sleep(0.1), os._exit(0)), daemon=True).start()
                return
            if self.path != "/synth":
                return self._json(404, {})
            if req.get("voice") not in voices:
                return self._json(404, {"error": "unknown voice"})
            state["n"] += 1
            if exit_after and state["n"] > exit_after:
                os._exit(3)
            if hang:
                time.sleep(3600)
            t = np.arange(12000) / 24000
            pcm = (np.sin(2 * np.pi * 200 * t) * 6000).astype("<i2").tobytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(pcm)))
            self.send_header("X-Sample-Rate", "24000")
            self.send_header("X-Gen-Ms", "5.0")
            self.end_headers()
            self.wfile.write(pcm)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    print(f"SPIKE_TTS_PORT={srv.server_address[1]}", flush=True)
    print(f"fake turbo ready on {args.device} ({args.dtype})", flush=True)
    srv.serve_forever(poll_interval=0.1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
