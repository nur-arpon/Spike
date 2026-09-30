"""The brain's side of the Chatterbox Turbo voice: starts the worker process
(speech/turbo_worker.py in .venv-chatterbox), checks its health, restarts it if
it dies or hangs, and asks it for one sentence at a time.

Nothing here imports torch. If anything goes wrong the caller (engines.py)
simply falls back to the next voice, so Spike never goes silent.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

log = logging.getLogger("spike.turbo")

WORKER_SCRIPT = Path(__file__).resolve().with_name("turbo_worker.py")


class TurboUnavailable(Exception):
    """The Turbo voice cannot answer right now (loading, restarting, failed, too slow)."""


@dataclass
class TurboConfig:
    python: Path                      # .venv-chatterbox python.exe
    models: Path                      # models/chatterbox-turbo
    voices: dict[str, Path]           # persona id -> reference clip
    device: str = "cuda"
    dtype: str = "fp32"
    start_timeout_s: float = 180.0    # first load reads ~3 GB from disk
    synth_timeout_s: float = 12.0     # one sentence; slower than this -> fall back
    health_interval_s: float = 5.0
    max_restarts: int = 4             # within restart_window_s, then give up until the next start
    restart_window_s: float = 600.0
    log_file: Path | None = None
    script: Path = WORKER_SCRIPT      # tests swap in a fake worker


class TurboWorker:
    """Supervises one worker process. Thread-safe; all calls are blocking (run them in an executor)."""

    def __init__(self, cfg: TurboConfig):
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.port: int | None = None
        self.token = secrets.token_hex(16)
        self.state = "stopped"          # stopped | starting | ready | failed
        self.last_error = ""
        self.health: dict = {}
        self._restarts: list[float] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._port_seen = threading.Event()
        self._monitor: threading.Thread | None = None
        self._log_fh = None

    # ------------------------------------------------------------------ life cycle
    @property
    def ready(self) -> bool:
        return self.state == "ready"

    def available(self) -> tuple[bool, str]:
        """Can the worker be started at all on this laptop? (files present)"""
        if not self.cfg.python.exists():
            return False, f"no voice Python at {self.cfg.python}"
        if not (self.cfg.models / "t3_turbo_v1.safetensors").exists():
            return False, f"no Turbo weights in {self.cfg.models}"
        missing = [str(p) for p in self.cfg.voices.values() if not Path(p).exists()]
        if missing:
            return False, f"reference clip missing: {missing[0]}"
        return True, ""

    def start(self, wait: bool = False) -> None:
        """Start the worker and its health monitor. With wait=True, block until ready or failed."""
        ok, why = self.available()
        if not ok:
            self.state, self.last_error = "failed", why
            log.warning("Turbo voice not available: %s", why)
            return
        if self._monitor is not None and self._monitor.is_alive():   # a restart after stop(): one monitor only
            self._stop.set()
            self._monitor.join(timeout=10)
        self._stop.clear()
        self._spawn()
        if self._monitor is None or not self._monitor.is_alive():
            self._monitor = threading.Thread(target=self._monitor_loop, name="turbo-monitor", daemon=True)
            self._monitor.start()
        if wait:
            self.wait_ready(self.cfg.start_timeout_s)

    def wait_ready(self, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end and not self._stop.is_set():
            if self.state == "ready":
                return True
            if self.state == "failed":
                return False
            time.sleep(0.2)
        return self.state == "ready"

    def _spawn(self) -> None:
        with self._lock:
            self._kill_proc()
            self.state, self.port = "starting", None
            self._port_seen.clear()
            cmd = [str(self.cfg.python), str(self.cfg.script), "--models", str(self.cfg.models),
                   "--device", self.cfg.device, "--dtype", self.cfg.dtype, "--parent-pid", str(os.getpid())]
            for name, ref in self.cfg.voices.items():
                cmd += ["--voice", f"{name}={ref}"]
            env = dict(os.environ, SPIKE_TTS_TOKEN=self.token, PYTHONUNBUFFERED="1",
                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            env.pop("PYTHONPATH", None)
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            if self.cfg.log_file and self._log_fh is None:
                self.cfg.log_file.parent.mkdir(parents=True, exist_ok=True)
                self._log_fh = open(self.cfg.log_file, "a", encoding="utf-8", errors="replace")
            self._started_at = time.monotonic()
            self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         env=env, creationflags=flags, cwd=str(self.cfg.models.parent))
            log.info("Turbo voice worker starting (pid %d, %s %s)", self.proc.pid, self.cfg.device, self.cfg.dtype)
            threading.Thread(target=self._read_output, args=(self.proc,), name="turbo-out", daemon=True).start()

    def _read_output(self, proc: subprocess.Popen) -> None:
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip()
            if line.startswith("SPIKE_TTS_PORT="):
                if proc is self.proc:
                    self.port = int(line.split("=", 1)[1])
                    self._port_seen.set()
                continue
            if self._log_fh:
                try:
                    self._log_fh.write(time.strftime("%H:%M:%S ") + line + "\n")
                    self._log_fh.flush()
                except (OSError, ValueError):
                    pass
            if "ready on" in line or "Error" in line or "Traceback" in line:
                log.info("voice worker: %s", line[:200])

    def _monitor_loop(self) -> None:
        fails = 0
        while not self._stop.wait(0.5 if self.state == "starting" else self.cfg.health_interval_s):
            proc = self.proc
            if proc is None:
                continue
            if proc.poll() is not None:
                self.last_error = f"worker exited with code {proc.returncode}"
                log.warning("Turbo voice worker stopped unexpectedly (%s)", self.last_error)
                self._restart_or_give_up()
                fails = 0
                continue
            try:
                h = self._get("/health", timeout=3.0)
                self.health = h
                fails = 0
                if h.get("state") == "ready" and self.state != "ready":
                    self.state = "ready"
                    log.info("Turbo voice ready (load %.1f s; %s MiB reserved on the graphics card)",
                             h.get("load_s", 0), h.get("vram_reserved_mib", "?"))
                elif h.get("state") == "error":
                    self.last_error = h.get("error", "load error")
                    log.error("Turbo voice failed to load: %s", self.last_error)
                    self._restart_or_give_up()
                elif self.state == "starting" and time.monotonic() - self._started_at > self.cfg.start_timeout_s:
                    self.last_error = "start timeout"
                    self._restart_or_give_up()
            except TurboUnavailable as e:
                if self.state == "starting" and time.monotonic() - self._started_at < self.cfg.start_timeout_s:
                    continue                            # still booting (port not open yet)
                fails += 1
                if fails >= 3:                          # hung: three missed health checks in a row
                    self.last_error = f"health check failed: {e}"
                    log.warning("Turbo voice worker is not answering; restarting it")
                    self._restart_or_give_up()
                    fails = 0

    def _restart_or_give_up(self) -> None:
        now = time.monotonic()
        self._restarts = [t for t in self._restarts if now - t < self.cfg.restart_window_s]
        if self._stop.is_set():
            return
        if len(self._restarts) >= self.cfg.max_restarts:
            log.error("Turbo voice keeps failing (%s); using the backup voice until Spike restarts",
                      self.last_error)
            with self._lock:
                self._kill_proc()
                self.state = "failed"
            self._stop.set()
            return
        self._restarts.append(now)
        backoff = min(30.0, 2.0 * 2 ** (len(self._restarts) - 1))
        log.info("restarting the Turbo voice in %.0f s (attempt %d)", backoff, len(self._restarts))
        self.state = "starting"
        if not self._stop.wait(backoff):
            self._spawn()

    def stop(self) -> None:
        """Ask the worker to exit, then make sure it is gone."""
        self._stop.set()
        with self._lock:
            if self.proc and self.proc.poll() is None and self.port:
                try:
                    self._post("/shutdown", {}, timeout=2.0)
                except TurboUnavailable:
                    pass
                try:
                    self.proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    pass
            self._kill_proc()
            self.state = "stopped"
            if self._log_fh:
                try:
                    self._log_fh.close()
                except OSError:
                    pass
                self._log_fh = None

    def _kill_proc(self) -> None:
        """Kill the worker AND its real interpreter. On Windows the venv's python.exe is a
        launcher whose child does the work, so killing only the launcher would leave a
        process holding 3 GB of graphics memory (seen on 29 Sep)."""
        p = self.proc
        if p is None:
            return
        if p.poll() is None and os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if p.poll() is None:
            p.kill()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log.error("voice worker pid %d did not exit after kill", p.pid)
        real = self.health.get("pid")
        if real and real != p.pid and _pid_alive(real):
            try:
                os.kill(int(real), 9 if os.name != "nt" else 1)
            except OSError:
                pass
        self.proc = None

    # ------------------------------------------------------------------ requests
    def _url(self, path: str) -> str:
        if not self.port:
            raise TurboUnavailable("worker not listening yet")
        return f"http://127.0.0.1:{self.port}{path}"

    def _get(self, path: str, timeout: float) -> dict:
        req = urllib.request.Request(self._url(path), headers={"X-Spike-Token": self.token})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise TurboUnavailable(str(e)) from e

    def _post(self, path: str, obj: dict, timeout: float) -> tuple[bytes, dict]:
        data = json.dumps(obj).encode()
        req = urllib.request.Request(self._url(path), data=data, method="POST",
                                     headers={"X-Spike-Token": self.token, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            raise TurboUnavailable(f"HTTP {e.code}: {e.read()[:200]!r}") from e
        except (urllib.error.URLError, OSError) as e:
            raise TurboUnavailable(str(e)) from e

    def synthesize(self, voice: str, text: str, seed: int = 1234,
                   timeout: float | None = None) -> tuple[np.ndarray, int, float]:
        """One whole sentence -> (int16 PCM, sample rate, generation ms). Raises TurboUnavailable."""
        if self.state != "ready":
            raise TurboUnavailable(f"Turbo voice is {self.state}")
        body, headers = self._post("/synth", {"voice": voice, "text": text, "seed": int(seed)},
                                   timeout=timeout or self.cfg.synth_timeout_s)
        rate = int(headers.get("X-Sample-Rate", 24000))
        gen_ms = float(headers.get("X-Gen-Ms", 0))
        return np.frombuffer(body, dtype="<i2").astype(np.int16), rate, gen_ms

    def release_memory(self) -> None:
        try:
            self._post("/release", {}, timeout=5.0)
        except TurboUnavailable:
            pass


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x00100000 | 0x1000, False, int(pid))
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def default_python(laptop_dir: Path, setting: str = "") -> Path:
    """The worker's Python: the setting if given, else software/laptop/.venv-chatterbox."""
    if setting:
        p = Path(setting)
        return p if p.is_absolute() else laptop_dir / p
    sub = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    return laptop_dir / ".venv-chatterbox" / sub
