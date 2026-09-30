"""Ollama on demand (v1.2): the brain stays light and always on; the language model is started
when someone needs Spike and unloaded again when nobody has talked to him for a while.

  ensure_ready()  - is `ollama serve` answering? If not, start it (hidden), wait until it answers,
                    then warm the model (load it onto the GPU and cache the persona prompt).
                    Many callers may ask at once; one warm-up runs.
  used()          - a reply was made: the idle clock restarts.
  watch()         - after `idle_unload` with no use the service unloads the model itself (frees
                    the graphics card for the voice) and reports "asleep", so the next request
                    warms it again first instead of timing out on a cold load. This is explicit
                    and does not depend on Ollama's keep_alive, which the always-loaded mode
                    (--llm-at-start) uses to keep the model resident.

States (sent to the app as brain_status.llm): off (no Ollama at all), asleep, warming, ready.
Ollama's own settings (model folder, flash attention, KV cache) are never touched: a started
`ollama serve` inherits the owner's environment unchanged.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger("spike.ollama")

OFF, ASLEEP, WARMING, READY = "off", "asleep", "warming", "ready"


def parse_duration_s(value, default: float = 900.0) -> float:
    """Ollama keep_alive style: "15m", "90s", "1h", "2h30m", or a number of seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip().lower()
    if not text:
        return default
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return float(text)
    total, matched = 0.0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(h|m|s|ms)", text):
        matched = True
        total += float(num) * {"h": 3600, "m": 60, "s": 1, "ms": 0.001}[unit]
    return total if matched else default


def find_ollama(configured: str = "") -> str | None:
    """The ollama executable: the configured path, then PATH, then the Windows per-user install."""
    candidates = [configured] if configured else []
    candidates.append(shutil.which("ollama") or "")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(str(Path(local) / "Programs" / "Ollama" / "ollama.exe"))
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


class OllamaService:
    def __init__(self, host: str = "http://127.0.0.1:11434", *, exe: str = "", idle_unload="15m",
                 start_timeout_s: float = 45.0, auto_start: bool = True, stop_on_exit: bool = True,
                 log_file: Path | None = None, model: Callable[[], str] | None = None,
                 on_state: Callable[[str], None] | None = None,
                 unload: Callable[[], Awaitable[None]] | None = None, clock=time.monotonic):
        self.host = host.rstrip("/")
        self.exe = exe
        self.idle_s = parse_duration_s(idle_unload)
        self.unload = unload
        self.start_timeout_s = start_timeout_s
        self.auto_start = auto_start
        self.stop_on_exit = stop_on_exit
        self.log_file = log_file
        self.model = model or (lambda: "")
        self.on_state = on_state
        self.clock = clock
        self.state = ASLEEP
        self.last_used = clock()
        self.started_proc: subprocess.Popen | None = None
        self._flight: asyncio.Task | None = None
        self._watch: asyncio.Task | None = None
        self.last_error = ""
        self.warm_s: float | None = None

    # ------------------------------------------------------------------ state
    @property
    def ready(self) -> bool:
        return self.state == READY

    def _set(self, state: str) -> None:
        if state != self.state:
            log.info("language model: %s -> %s", self.state, state)
            self.state = state
            if self.on_state:
                try:
                    self.on_state(state)
                except Exception:  # noqa: BLE001
                    log.exception("on_state failed")

    def used(self) -> None:
        self.last_used = self.clock()

    # ------------------------------------------------------------------ HTTP
    async def _get(self, path: str, timeout: float = 1.5):
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get(self.host + path)
            r.raise_for_status()
            return r.json()

    async def server_up(self) -> bool:
        try:
            await self._get("/api/version")
            return True
        except Exception:  # noqa: BLE001
            return False

    async def model_loaded(self) -> bool:
        """Is our model in Ollama's memory right now (`/api/ps`)?"""
        want = self.model()
        try:
            ps = await self._get("/api/ps", timeout=2.0)
        except Exception:  # noqa: BLE001
            return False
        names = {m.get("name") for m in ps.get("models", [])} | {m.get("model") for m in ps.get("models", [])}
        return bool(want) and (want in names or f"{want}:latest" in names)

    # ------------------------------------------------------------------ start
    def _spawn(self) -> bool:
        exe = find_ollama(self.exe)
        if exe is None:
            self.last_error = "Ollama is not installed (ollama.exe not found)"
            return False
        out = subprocess.DEVNULL
        if self.log_file is not None:
            try:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                out = open(self.log_file, "ab")                 # noqa: SIM115 - handed to the child
            except OSError:
                out = subprocess.DEVNULL
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            # the owner's environment as it is (OLLAMA_MODELS etc.): nothing is changed
            self.started_proc = subprocess.Popen([exe, "serve"], stdin=subprocess.DEVNULL, stdout=out,
                                                 stderr=subprocess.STDOUT, creationflags=flags)
        except OSError as e:
            self.last_error = f"could not start Ollama ({e})"
            return False
        finally:
            if out is not subprocess.DEVNULL:
                out.close()                                    # the child keeps its own handle
        log.info("started `ollama serve` (pid %d) because it was not running", self.started_proc.pid)
        return True

    async def _wait_up(self) -> bool:
        end = self.clock() + self.start_timeout_s
        while self.clock() < end:
            if await self.server_up():
                return True
            if self.started_proc is not None and self.started_proc.poll() is not None:
                self.last_error = f"ollama serve exited with code {self.started_proc.returncode}"
                return False
            await asyncio.sleep(0.5)
        self.last_error = f"Ollama did not answer within {self.start_timeout_s:.0f} s"
        return False

    async def ensure_ready(self, warm: Callable[[], Awaitable[float]]) -> bool:
        """Make the model ready (start Ollama if needed, then warm it). True when ready."""
        self.used()
        if self.state == READY:
            return True
        if self._flight is None or self._flight.done():
            self._flight = asyncio.create_task(self._bring_up(warm), name="ollama-up")
        try:
            return await asyncio.shield(self._flight)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            return False

    def kick(self, warm: Callable[[], Awaitable[float]]) -> None:
        """Start warming in the background (the app connected, a wake word, a head tap)."""
        self.used()
        if self.state != READY and (self._flight is None or self._flight.done()):
            self._flight = asyncio.create_task(self._bring_up(warm), name="ollama-up")

    async def _bring_up(self, warm: Callable[[], Awaitable[float]]) -> bool:
        self._set(WARMING)
        if not await self.server_up():
            if not self.auto_start or not self._spawn() or not await self._wait_up():
                log.error("language model unavailable: %s. Spike uses his scripted lines.",
                          self.last_error or "Ollama is not running")
                self._set(OFF)
                return False
        try:
            self.warm_s = await warm()
        except Exception as e:  # noqa: BLE001
            self.last_error = f"{type(e).__name__}: {e}"
            log.error("language model failed to warm up: %s. Spike uses his scripted lines.", self.last_error)
            self._set(OFF)
            return False
        self.used()
        self._set(READY)
        return True

    # ------------------------------------------------------------------ idle
    def start_watch(self, every_s: float = 20.0) -> None:
        if self._watch is None:
            self._watch = asyncio.create_task(self._watch_loop(every_s), name="ollama-idle")

    async def _watch_loop(self, every_s: float) -> None:
        while True:
            await asyncio.sleep(every_s)
            try:
                await self.check_idle()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.debug("idle check failed", exc_info=True)

    async def check_idle(self) -> None:
        if self.state != READY:
            return
        idle = self.clock() - self.last_used
        if idle >= self.idle_s:
            if self.unload is not None:
                try:
                    await self.unload()           # keep_alive=0: Ollama frees the graphics memory now
                except Exception:  # noqa: BLE001
                    log.debug("unload failed", exc_info=True)
            log.info("language model idle for %.0f min: unloaded (it wakes again when needed)", idle / 60)
            self._set(ASLEEP)
        elif idle >= 60 and not await self.model_loaded():
            self._set(ASLEEP)                     # unloaded by someone else (another app, `ollama stop`)

    async def close(self) -> None:
        for t in (self._watch, self._flight):
            if t is not None and not t.done():
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        p = self.started_proc
        if p is not None and self.stop_on_exit and p.poll() is None:
            log.info("stopping the `ollama serve` Spike started (pid %d)", p.pid)
            loop = asyncio.get_running_loop()
            if os.name == "nt":
                # the whole tree: `ollama serve` runs the model in child "runner" processes, which a
                # plain terminate would leave behind holding the graphics memory
                await loop.run_in_executor(None, lambda: subprocess.run(
                    ["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, timeout=15))
            else:
                p.terminate()
            try:
                await loop.run_in_executor(None, p.wait, 10)
            except Exception:  # noqa: BLE001
                p.kill()
