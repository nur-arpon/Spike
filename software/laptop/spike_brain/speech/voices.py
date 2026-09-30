"""Builds both personas' voice chains from the settings (speech/engines.py) and
decides how the Turbo voice uses the graphics card (DESIGN.md "Voice" and
"Graphics memory").
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .engines import ClipCache, KokoroEngine, OwnerRecordings, PiperEngine, TurboStyle, VoiceChain
from .turbo import TurboConfig, TurboWorker, default_python

log = logging.getLogger("spike.voice")


def gpu_free_mib() -> int | None:
    """Free memory on the NVIDIA card, from nvidia-smi (None = no NVIDIA card or no driver tool)."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        return int(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


@dataclass
class TurboPlan:
    device: str | None          # "cuda" | "cpu" | None (= no live Turbo; cache + Kokoro)
    dtype: str
    reason: str
    free_mib: int | None = None     # free on the card when planned (after the language model loaded)
    need_mib: int = 0               # what the chosen Turbo setting takes
    llm_mib: int = 0                # kept for the language model that loads later (on demand; llm_reserve_mib)

    def left_mib(self) -> int | None:
        """Card memory still free once Turbo (and a model that loads on demand) are in (None = unknown)."""
        if self.free_mib is None:
            return None
        return self.free_mib - (self.need_mib if self.device == "cuda" else 0) - self.llm_mib


def plan_turbo(device: str, dtype: str, free_mib: int | None, need_fp32: int, need_bf16: int,
               reserve_mib: int = 0) -> TurboPlan:
    """How to run live Turbo, given the free graphics memory AFTER the language model loaded.

    reserve_mib is memory another part of the brain still has to load (Whisper on the card,
    and the language model when it is on demand: graphics_reserve_mib).
    fp32 is the owner's picked sound; bf16 is the lighter setting (measured: 0.9 GB less,
    about 20 % slower). When neither fits, Turbo still runs in bf16: Windows then lends the
    card system memory (the driver's normal "sysmem fallback"), which the 29 Sep bench
    showed is still usable; the brain logs it so the owner knows why it may be slower."""
    device, dtype = (device or "auto").lower(), (dtype or "auto").lower()
    if device == "off":
        return TurboPlan(None, "fp32", "live Turbo switched off in settings")
    if device == "cpu":
        return TurboPlan("cpu", "fp32", "live Turbo on the processor (settings)")
    if free_mib is None:
        if device == "cuda":
            return TurboPlan("cuda", "fp32" if dtype == "auto" else dtype, "no nvidia-smi; trying the card anyway")
        return TurboPlan(None, "fp32", "no NVIDIA graphics card found: cached clips and Kokoro only")
    if dtype in ("fp32", "bf16"):
        return TurboPlan("cuda", dtype, f"{dtype} (settings); {free_mib} MiB free")
    avail = free_mib - reserve_mib
    if avail >= need_fp32:
        return TurboPlan("cuda", "fp32", f"fp32: {free_mib} MiB free, enough for the full voice")
    kept = f", {reserve_mib} MiB kept for parts that load later" if reserve_mib else ""
    if avail >= need_bf16:
        return TurboPlan("cuda", "bf16", f"bf16: only {free_mib} MiB free{kept}, lighter setting")
    return TurboPlan("cuda", "bf16", f"bf16, overcommitted: only {free_mib} MiB free{kept} (needs {need_bf16}); "
                                     "Windows will lend system memory, the voice may be slower")


def llm_reserve_mib(*, on_demand: bool, loaded: bool, llm_mib: int) -> int:
    """Card memory the voice keeps for the language model (DESIGN.md 6c, decision 24).

    Always-loaded mode: the model is on the card before the voice plans, so the measured free
    memory already accounts for it (0). On demand ([llm] on_demand): the voice plans while the
    model is NOT loaded, but it comes back whenever someone talks to Spike, so plan as if it
    were loaded (its measured footprint). Turbo then takes the same setting as in the
    always-loaded mode (bf16 on the 8 GB card), never fp32 that would leave the model only
    part of the card when it wakes, and Whisper stays off the card the same way."""
    return max(0, int(llm_mib)) if on_demand and not loaded else 0


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@dataclass
class VoiceSet:
    chains: dict = field(default_factory=dict)       # mode ("dog"/"cat") -> VoiceChain
    turbo: TurboWorker | None = None
    cache: ClipCache | None = None
    plan: TurboPlan | None = None
    gemini: object | None = None     # speech/gemini_tts.py GeminiTTSEngine (desktop)
    windows: object | None = None    # speech/windows_tts.py WindowsVoice (desktop)

    def close(self) -> None:
        if self.turbo is not None:
            self.turbo.stop()
        if self.windows is not None:
            self.windows.close()

    def summary(self) -> dict:
        return {"engine": next(iter(self.chains.values())).engine if self.chains else None,
                "turbo": None if self.turbo is None else self.turbo.state,
                "turbo_plan": None if self.plan is None else f"{self.plan.device} {self.plan.dtype}",
                "cached_clips": len(self.cache) if self.cache else 0,
                "used": {m: dict(c.stats) for m, c in self.chains.items()}}


def build_voices(settings, *, start_turbo: bool = True, reserve_mib: int = 0, llm_mib: int = 0,
                 log_dir: Path | None = None, load_kokoro: bool = True, load_piper: bool = True,
                 picks=None) -> VoiceSet:
    """Both personas' chains. Turbo is started in the background (it takes 15-45 s to load);
    until it is ready, lines come from the cache, Kokoro or Piper. reserve_mib: kept for Whisper
    on the card; llm_mib: kept for a language model that loads later (llm_reserve_mib).

    engine = "gemini" (the desktop light brain, config/desktop.toml): Gemini TTS with the owner's
    picked styles (`picks`, a speech/gemini_tts.py VoicePicks), then Windows' own voice; no Turbo,
    no clip cache, and Kokoro/Piper only if [tts.gemini] local_backups = true (their models are
    not in the light package)."""
    s = settings
    tts = s.cfg.tts
    engine = str(tts.get("engine", "turbo"))
    tcfg = tts.get("turbo")
    tcfg = tcfg.to_dict() if tcfg is not None else {}
    vs = VoiceSet()

    refs: dict[str, Path] = {}
    for mode, p in s.personas.items():
        ref = (p.voice_cfg.get("turbo") or {}).get("reference")
        if ref:
            refs[p.id] = s.path(ref)
    ref_hashes = {pid: file_sha1(r) for pid, r in refs.items() if r.exists()}

    if engine == "turbo":
        vs.cache = ClipCache(s.path(tts.get("cache_dir", "voice_cache")), ref_hashes)
        if len(vs.cache):
            log.info("voice cache: %d pre-made clips", len(vs.cache))
        else:
            log.info("voice cache is empty (make it with: python -m spike_brain.tools.build_voice_cache)")
        if start_turbo:
            free = gpu_free_mib()
            vs.plan = plan_turbo(tcfg.get("device", "auto"), tcfg.get("dtype", "auto"), free,
                                 int(tcfg.get("vram_fp32_mib", 3600)), int(tcfg.get("vram_bf16_mib", 2700)),
                                 reserve_mib + llm_mib)
            vs.plan.free_mib = free
            vs.plan.llm_mib = llm_mib if vs.plan.device == "cuda" else 0
            vs.plan.need_mib = int(tcfg.get("vram_bf16_mib" if vs.plan.dtype == "bf16" else "vram_fp32_mib", 3600))
            log.info("Turbo voice plan: %s", vs.plan.reason)
            if vs.plan.device is not None:
                cfg = TurboConfig(python=default_python(s.root, tcfg.get("python", "")),
                                  models=s.path(tcfg.get("models", "models/chatterbox-turbo")),
                                  voices=refs, device=vs.plan.device, dtype=vs.plan.dtype,
                                  start_timeout_s=float(tcfg.get("start_timeout_s", 180)),
                                  synth_timeout_s=float(tcfg.get("synth_timeout_s", 12)),
                                  log_file=(log_dir / "turbo_worker.log") if log_dir else None)
                vs.turbo = TurboWorker(cfg)
                vs.turbo.start(wait=False)

    gemini = windows = None
    if engine == "gemini":
        gcfg = tts.get("gemini")
        gcfg = gcfg.to_dict() if gcfg is not None else {}
        key = s.secret("GEMINI_API_KEY")
        if key:
            from .gemini_tts import TTS_MODELS, GeminiTTSEngine
            gemini = GeminiTTSEngine(key, picks=picks, models=tuple(gcfg.get("models", TTS_MODELS)),
                                     timeout_s=float(gcfg.get("timeout_s", 12)),
                                     rest_s=float(gcfg.get("rest_min", 15)) * 60,
                                     **({"base_url": gcfg["base_url"]} if gcfg.get("base_url") else {}))
            log.info("voice: Gemini TTS (%s), Windows' own voice as the backup", ", ".join(gemini.models))
        else:
            log.warning("voice: no Gemini key yet, so Spike speaks with Windows' own voice until one is added")
        if not bool(gcfg.get("local_backups", False)):
            load_kokoro = load_piper = False
    wcfg = tts.get("windows")
    if bool(wcfg.get("enabled", False)) if wcfg is not None else engine == "gemini":
        try:
            from .windows_tts import WindowsVoice
            windows = WindowsVoice()
            log.info("Windows' own voice ready (Spike: %s, Spicy: %s)", windows.voice_name("dog"),
                     windows.voice_name("cat"))
        except Exception as e:  # noqa: BLE001
            log.error("Windows' own voice unavailable: %s", e)
    vs.gemini, vs.windows = gemini, windows

    kokoro = piper = None
    if load_kokoro and engine in ("turbo", "kokoro", "gemini"):
        kcfg = tts.get("kokoro")
        try:
            kokoro = KokoroEngine(s.path(kcfg.model), s.path(kcfg.voices))
        except Exception as e:  # noqa: BLE001
            log.error("Kokoro backup voice unavailable: %s", e)
    if load_piper:
        pcfg = tts.get("piper")
        try:
            piper = PiperEngine(s.path(pcfg.fallback))
        except Exception as e:  # noqa: BLE001
            log.error("Piper backup voice unavailable: %s", e)

    recordings = OwnerRecordings(s.path(tts.get("recordings_dir", "voice_recordings")))
    for mode, p in s.personas.items():
        turbo_cfg = p.voice_cfg.get("turbo") or {}
        vs.chains[mode] = VoiceChain(
            p.id, engine=engine, style=TurboStyle.from_config(turbo_cfg), turbo=vs.turbo, turbo_voice=p.id,
            seed=int(turbo_cfg.get("seed", 1234)), cache=vs.cache, recordings=recordings, kokoro=kokoro,
            kokoro_voice=str(p.voice_cfg.get("kokoro_voice", "am_puck" if mode == "dog" else "af_heart")),
            piper=piper, target_dbfs=float(tts.get("loudness_dbfs", -20)), volume=float(tts.get("volume", 1.0)),
            turbo_timeout_s=float(tcfg.get("synth_timeout_s", 12)), say_as_table=s.say_as(),
            gemini=gemini, windows=windows, mode=mode)
    return vs
