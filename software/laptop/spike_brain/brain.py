"""The brain: wires hearing, talking, memory, seeing and life features to the
protocol server. One asyncio loop; heavy work (Whisper, Piper, MediaPipe,
SQLite) runs on worker threads and reports back through the loop.

Order of a spoken request (brain side):
  listener "heard" -> safety screen -> explicit-request block -> command
  intents -> LLM stream -> sentence chunks -> output check -> Piper -> robot
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from . import discovery
from . import protocol as P
from .applink import AppLink
from .capabilities import is_available, unavailable_line
from .config import Persona, Settings
from .hearing.wake import WakeMatcher
from .life import timeparse
from .life.scheduler import AlarmRinger, Scheduler
from .memory import extract
from .memory.store import Memory
from .mind import safety
from .mind.conversation import Conversation, Situation, system_prompt, time_of_day
from .mind.intents import Intent, match_intent
from .mind.llm import GeminiLLM, LLMError, LLMRouter, OllamaLLM
from .mind.reply import StreamParser, parse_reply, strip_pet_names
from .server import BrainServer, Client, is_loopback
from .speech.output import REPLY_TO, SpeechOut, Utterance, reply_to
from .speech.stream_audio import choose_rate
from .vision.signals import rps_result

log = logging.getLogger("spike.brain")

GREETING_LINES = {"come_home", "greet_morning", "greet_afternoon", "greet_evening", "greet_night"}
SOFT_LINES = {"crisis", "emergency", "crisis_followup", "checkin_sad"}      # said in the soft voice
GREETING_WORDS = re.compile(r"\b(hi|hello|hiya|morning|evening|afternoon|night|welcome|g'?day)\b")
ORDER = re.compile(r"^(please |can you |could you |now |ok |okay )?(sit|stand|come|go|get|look|move|stop|be quiet|"
                   r"shush|stay|lie|jump|turn|spin|wait|listen|give|bring|put|show|smile|say|sing|dance)\b")
LONG_REQUEST = re.compile(r"\b(story|stories|jokes|a few|some more|list|sing|song|poem|explain)\b")
FEELING_BETTER = re.compile(r"\b(i'?m (ok|okay|fine|better|good|alright)|feel(ing)? better|that helped|"
                            r"thank you|thanks|haha|lol|you made me (smile|laugh))\b")


JOKE_REQUEST = re.compile(r"\b(joke|jokes|funny|make me laugh|cheer me up with)\b")
FUNNY_MOODS = ("laughing", "playful", "silliness", "mischief", "happy", "embarrassed", "proud", "smugness",
               "delight", "joy", "excited")


def fit_tags(mood: str | None, action: str | None, support: str | None, crisis: bool,
             joke: bool = False) -> tuple[str, str | None]:
    """The face must fit how the owner is (and what he is doing), whatever the model picked."""
    mood = mood or "happy"
    action = action if is_available(action) else None    # capabilities.py
    if joke and not support and not crisis and mood not in FUNNY_MOODS:
        mood = "playful"                              # telling a joke: a joking face
    if crisis:
        return (mood if mood in safety.SOFT_MOODS and mood != "sad" else "caring"), None
    if support in ("sad", "lonely", "grief"):
        return (mood if mood in safety.SOFT_MOODS else ("cuddly" if support == "lonely" else "caring")), "snuggle"
    if support == "tired":
        return (mood if mood in safety.CALM_MOODS else "happy"), "slowWag"
    if mood == "neutral":
        mood = "happy"
    return mood, action


@dataclass
class RunOptions:
    mic: bool = True
    camera: bool = True
    tts: bool = True
    console: bool = False          # read typed lines from the terminal
    text_only: bool = False        # --text: console chat, no audio at all
    mode: str | None = None        # dog | cat
    host: str | None = None
    port: int | None = None
    llm: bool = True               # False = scripted fallback lines only (tests)
    print_replies: bool = False    # print "Spike: [mood] words" lines on stdout (--text)
    exit_at_eof: bool = False      # stop when typed input ends (--text with piped stdin)
    on_listening: Callable[[int], None] | None = None   # called with the port once the server is up
    llm_on_demand: bool = False    # v1.2: start/warm Ollama only when someone needs Spike (app.py: [llm] on_demand)


@dataclass
class OwnerState:
    present: bool | None = None           # None = no camera
    emotion: str = "neutral"
    emotion_since: float = 0.0
    arrived_at: float = 0.0
    last_greet_part: str = ""
    last_greet_day: str = ""
    lonely_signal_at: float = -1e9


@dataclass
class TurnTiming:
    via: str
    speech_end: float = 0.0
    endpoint: float = 0.0
    stt_done: float = 0.0
    llm_start: float = 0.0
    first_token: float = 0.0
    first_sentence: float = 0.0
    first_audio_sent: float = 0.0
    first_played: float = 0.0
    stt_ms: float = 0.0
    tts_first_ms: float = 0.0
    tts_engine: str = ""

    def report(self) -> dict:
        def ms(a, b):
            return round((a - b) * 1000) if a and b else None
        return {"via": self.via, "vad_tail_ms": ms(self.endpoint, self.speech_end), "stt_ms": round(self.stt_ms),
                "llm_first_token_ms": ms(self.first_token, self.llm_start),
                "first_sentence_ms": ms(self.first_sentence, self.llm_start),
                "tts_first_ms": round(self.tts_first_ms), "tts_engine": self.tts_engine,
                "speech_end_to_first_audio_ms": ms(self.first_audio_sent, self.speech_end),
                "speech_end_to_first_played_ms": ms(self.first_played, self.speech_end)}


class Brain:
    def __init__(self, settings: Settings, opts: RunOptions | None = None):
        self.s = settings
        self.opts = opts or RunOptions()
        self.mode = self.opts.mode or settings.persona.start_mode
        self.rng = random.Random()
        self.memory = Memory(settings.path(settings.memory.db_path))
        self.scheduler = Scheduler(self.memory)
        self.conv = Conversation(settings.llm.history_turns)
        host = self.opts.host or settings.server.host
        self.server = BrainServer(host, self.opts.port if self.opts.port is not None else settings.server.port,
                                  heartbeat_s=settings.server.heartbeat_s,
                                  hello_timeout_s=settings.server.hello_timeout_s,
                                  token=discovery.resolve_token(settings, lan=not is_loopback(host)),
                                  trust_loopback=bool(settings.server.get("trust_loopback", True)),
                                  max_message_bytes=settings.server.max_message_kib * 1024,
                                  on_message=self.on_message, on_connect=self.on_connect,
                                  on_disconnect=self.on_disconnect, welcome=self.welcome)
        self.llm: LLMRouter | None = None
        self.local_llm: OllamaLLM | None = None
        self.voices: dict = {}
        self.voice_set = None                     # speech/voices.py VoiceSet (owns the Turbo worker)
        self.speech: SpeechOut | None = None
        self.listener = None
        self.mic = None
        self.remote_mic = None
        self.end_silence_client = None            # the app stream that asked for its own end silence (6.7)
        self.app_mic: tuple[Client, float] | None = None   # v1.5: the phone that last streamed its mic, and when
        self._end_silence_ms = None
        self.eyes = None
        self.remote_cam = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.owner = OwnerState()
        self.robot_mood = "neutral"
        self.battery: float | None = None
        self.charging = False
        self.hunger = "ok"
        self.last_interaction = time.monotonic()
        self.last_checkin = -1e9
        self.crisis_until = 0.0
        self.pending: tuple[str, float, dict] | None = None     # (what, deadline, data) slot filling
        self.forget_all_until = 0.0
        self.ringer: AlarmRinger | None = None
        self.rps: dict | None = None
        self.turn_task: asyncio.Task | None = None
        self.timings: list[dict] = []
        self.current_timing: TurnTiming | None = None
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._bg: set[asyncio.Task] = set()
        self._console_thread: threading.Thread | None = None
        self.started_at = time.time()
        self.started_mono = time.monotonic()
        self.owner_turns = 0           # things the owner said or typed this session
        self.said_count = 0            # things Spike said this session
        self.greeted = False           # has he said hello this session (always his first line)
        self._warmup: asyncio.Task | None = None   # persona prompt caching after a mode switch
        self.support_kind: str | None = None       # the owner is sad / lonely / tired / grieving
        self.support_until = 0.0
        self.turn_said: list[dict] = []           # what Spike said in the current turn
        self.turn_raw_tags: tuple = (None, None)
        self.last_turn: dict = {}                 # summary of the last turn (tools/persona_eval.py)
        self.text_matcher = WakeMatcher({m: p.wake_aliases for m, p in settings.personas.items()},
                                        settings.wake.fuzzy_threshold,
                                        {v for p in settings.personas.values() for v in p.vocative_only})
        self.ollama = None                        # v1.2 mind/ollama_service.py (when llm_on_demand)
        self.app = AppLink(self)                  # v1.2 the phone app's messages (applink.py)
        # v1.8: the owner's Gemini voice style per character (desktop light brain; kept in app_prefs.json)
        from .speech.gemini_tts import VoicePicks
        self.voice_picks = VoicePicks(self.app.prefs.get("voice_styles") or {})

    # ------------------------------------------------------------------ helpers
    @property
    def persona(self) -> Persona:
        return self.s.personas[self.mode]

    @property
    def names(self) -> dict[str, str]:
        return {m: p.name for m, p in self.s.personas.items()}

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)
        return t

    def _threadsafe(self, fn, *args) -> None:
        if self.loop and not self.loop.is_closed():
            self.loop.call_soon_threadsafe(fn, *args)

    def owner_ref(self) -> str:
        return self.memory.owner_name() or "you"

    def quiet_hours(self, now: datetime | None = None) -> bool:
        start, end = self.s.life.quiet_hours
        n = (now or datetime.now()).strftime("%H:%M")
        return (start <= n or n < end) if start > end else (start <= n < end)

    def idle(self) -> bool:
        return not (self.speech and self.speech.speaking) and not (self.turn_task and not self.turn_task.done())

    def welcome(self, client: Client) -> dict:
        audio_rate = self.voices[self.mode].rate if self.voices.get(self.mode) else 22050
        if client.audio_rates:
            audio_rate = client.audio_rates[0]
        audio = {"format": "pcm_s16le", "rate": audio_rate, "channels": 1}
        if client.audio_format:                   # v1.5: a phone that plays the voice (PROTOCOL.md 10.8)
            audio = {"format": client.audio_format, "rate": choose_rate(client.audio_format, client.audio_rates),
                     "channels": 1, "to_app": True}
        hello = {"mode": self.mode, "names": self.names,
                 "wake_words": {m: p.wake_words for m, p in self.s.personas.items()},
                 "audio": audio, "keepalive": True,       # v1.6: understands `keepalive`
                 "voice_source": True}                    # v1.7: understands `voice_source`
        if self._gemini_voice():
            hello["voice_style"] = self.voice_picks.as_dict()   # v1.8: speaks with Gemini TTS, takes `voice_style`
        return hello

    def _gemini_voice(self) -> bool:
        """This brain speaks with Gemini TTS itself ([tts] engine = "gemini", the desktop light brain)."""
        return str(self.s.cfg.tts.get("engine", "turbo")) == "gemini"

    def _llm_provider(self) -> str:
        return str(self.s.llm.get("provider", "ollama"))

    # ------------------------------------------------------------------ v1.5: where Spike's voice plays
    APP_MIC_WINDOW_S = 3.0

    @staticmethod
    def reply_origin(client: Client | None) -> Client | None:
        """THE routing rule (DESIGN.md 6d): a reply plays on the phone the conversation came from when
        that phone is an app with cap `audio_out`; anything else (the robot's or the laptop's mic, a
        tool, the simulator, an older app) -> None = the robot's speaker or the laptop's, as before."""
        if client is None or client.role != "app" or not client.has("audio_out"):
            return None
        return client

    def voice_origin(self) -> Client | None:
        """Who a HEARD request came from: the phone whose mic stream fed the listener in the last few
        seconds (push-to-talk or continuous listening), else None (the laptop's or robot's mic)."""
        if self.app_mic is None:
            return None
        client, at = self.app_mic
        if time.monotonic() - at > self.APP_MIC_WINDOW_S or client not in self.server.clients.values():
            return None
        return self.reply_origin(client)

    def for_app(self, client: Client | None, coro):
        """Run `coro` (a spoken line the phone asked for: a trick's "Ta-da!", goodnight) with its
        speech routed by reply_origin(client)."""
        async def run():
            with reply_to(self.reply_origin(client)):
                return await coro
        return run()

    # ------------------------------------------------------------------ life cycle
    async def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        s = self.s
        try:
            await self.server.start()
        except OSError as e:
            raise RuntimeError(str(e)) from e
        if self.opts.on_listening:
            self.opts.on_listening(self.server.port)
        await self.app.start()
        missed = self.scheduler.recover()
        if missed:
            log.info("%d alarm(s)/reminder(s) were missed while I was off", len(missed))
        if self.opts.llm and self.opts.llm_on_demand and self._llm_provider() == "ollama":
            self._setup_llm_service()            # v1.2: Ollama is started and warmed when someone needs Spike
        elif self.opts.llm:
            await self._init_llm()
        if self.opts.tts and not self.opts.text_only:
            await self.loop.run_in_executor(None, self._load_voices)
        self.speech = SpeechOut(self.server, self.voices, output=s.audio.output,
                                local_device=s.audio.local_output_device or None,
                                mute_tail_ms=s.audio.mute_tail_ms, report_timeout_s=s.audio.say_report_timeout_s,
                                set_mic_muted=self._set_mic_muted, on_done=self._on_speech_done,
                                text_only=self.opts.text_only or not self.opts.tts)
        if not self.opts.text_only:
            await self.loop.run_in_executor(None, self._init_hearing)
        if self.opts.camera and s.vision.enabled and not self.opts.text_only:
            await self.loop.run_in_executor(None, self._init_eyes)
        self._tasks.append(asyncio.create_task(self._tick(), name="life-tick"))
        self._ready.set()
        log.info("%s is awake (brain %s, mode %s). Simulator: face_v2/index.html?brain=%s",
                 self.persona.name, __version__, self.mode, self.server.local_url)
        if self.s.life.greet_on_start and self.owner.present is None:
            await self._greet(first=True)        # no camera: say hello now (with one: when he sees you)
        if self.opts.console or self.opts.text_only or not self.opts.mic:
            self._start_console()

    async def _init_llm(self) -> None:
        s = self.s
        if self._llm_provider() == "gemini":
            self._init_gemini_llm()
            return
        local = OllamaLLM(s.llm.host, s.llm.model, list(s.llm.fallback_models), num_ctx=s.llm.num_ctx,
                          temperature=s.llm.temperature, top_p=s.llm.top_p, repeat_penalty=s.llm.repeat_penalty,
                          max_tokens=s.llm.max_tokens, keep_alive=s.llm.keep_alive,
                          first_token_timeout_s=s.llm.first_token_timeout_s, total_timeout_s=s.llm.total_timeout_s,
                          gpu_layers=int(s.llm.get("gpu_layers", -1)))
        try:
            await local.ensure_model()
            secs = await local.warm_up(system_prompt(self.persona, self.memory.owner_name(), self.s.helpline()))
            log.info("language model %s ready (warm-up %.1f s)", local.model, secs)
            self.local_llm = local
            share = await local.gpu_share()
            if share is not None and share < 0.9:
                log.warning("only %d%% of the language model fits on the graphics card right now (other programs "
                            "are using its memory), so Spike will think slowly. Close big 3D apps and restart him "
                            "for fast replies.", round(share * 100))
        except (LLMError, Exception) as e:  # noqa: BLE001
            log.error("local language model unavailable: %s. Spike will use his scripted lines.", e)
            self.local_llm = None
        cloud = None
        if s.cloud.enabled:
            key = s.secret("GEMINI_API_KEY")
            if key:
                cloud = GeminiLLM(key, s.cloud.model, s.cloud.timeout_s, s.llm.temperature, s.llm.max_tokens)
                log.warning("cloud fallback is ON (%s): text of conversations may be sent to Google", s.cloud.model)
            else:
                log.warning("cloud.enabled is true but GEMINI_API_KEY is not in .env; cloud stays off")
        if self.local_llm or cloud:
            self.llm = LLMRouter(self.local_llm, cloud, s.cloud.use_when)

    def _init_gemini_llm(self) -> None:
        """[llm] provider = "gemini" (the desktop light brain): Gemini is the main model, with the
        owner's own key from the GEMINI_API_KEY environment variable (the desktop app passes it
        from Windows' protected storage; it is never written to a file or a log here). The same
        persona prompt, reply parser and safety checks run on its words as on Ollama's.
        No key yet: scripted lines only, and the app says a key is needed (brain_status off)."""
        s = self.s
        key = s.secret("GEMINI_API_KEY")
        if not key:
            log.warning("no Gemini key yet: Spike answers with his scripted lines until one is added in the app")
            self.local_llm, self.llm = None, None
            return
        models = list(s.llm.get("gemini_models", GeminiLLM.DEFAULT_MODELS))
        g = GeminiLLM(key, models=models, timeout_s=float(s.llm.first_token_timeout_s), temperature=s.llm.temperature,
                      max_tokens=s.llm.max_tokens, total_timeout_s=float(s.llm.total_timeout_s),
                      base_url=s.llm.get("gemini_base_url") or None)      # tests point it at a mock server
        self.local_llm = g                       # "the main model" (complete_json, warm_up... are no-ops/cloud)
        self.llm = LLMRouter(g, None)
        log.info("language model: Gemini (%s); conversation text is sent to Google", ", ".join(models))

    # ------------------------------------------------------------------ language model on demand (v1.2)
    def _setup_llm_service(self) -> None:
        """Nothing is loaded yet: Ollama is started (if it is not running) and the model warmed
        when the app connects, a wake word or head tap is heard, or someone talks to Spike."""
        from .mind.ollama_service import OllamaService
        s = self.s.llm
        self.ollama = OllamaService(
            s.host, exe=str(s.get("ollama_exe", "")), idle_unload=s.get("idle_unload", "15m"),
            start_timeout_s=float(s.get("start_timeout_s", 45)), auto_start=bool(s.get("auto_start", True)),
            stop_on_exit=bool(s.get("stop_started_on_exit", True)),
            log_file=self.s.path("data/logs/ollama_serve.log"),
            model=lambda: self.local_llm.model if self.local_llm else self.s.llm.model,
            on_state=self._on_llm_state,
            unload=lambda: self.local_llm.unload() if self.local_llm else asyncio.sleep(0))
        self.ollama.start_watch()
        log.info("language model: starts on demand (unloaded after %s idle)", s.get("idle_unload", "15m"))

    async def _warm_llm(self) -> float:
        t = time.perf_counter()
        await self._init_llm()                  # the same path as a normal start: pick model, warm, check GPU
        if self.local_llm is None:
            raise RuntimeError("the local model did not load")
        return time.perf_counter() - t

    def wake_llm(self, why: str = "") -> None:
        """Someone needs Spike soon: start warming the model now (no-op when it is ready)."""
        if self.ollama is not None and not self.ollama.ready:
            if self.ollama.state != "warming":
                log.info("waking the language model (%s)", why or "needed")
            self.ollama.kick(self._warm_llm)
        elif self.ollama is not None:
            self.ollama.used()

    def keepalive(self) -> None:
        """v1.6 `keepalive` from a phone with its mic session open: keep the language model warm and
        the listening window open, silently (no face event, no sound; unlike a head tap)."""
        self.wake_llm("keepalive")
        if self.listener:
            self.listener.keep_listening()

    def _on_llm_state(self, state: str) -> None:
        if state in ("asleep", "off"):
            self.local_llm = None               # scripted lines until it is warm again
            cloud = getattr(self.llm, "cloud", None)
            self.llm = LLMRouter(None, cloud, self.s.cloud.use_when) if cloud else None
        self.app.on_llm_state(state)

    async def _await_llm(self) -> bool:
        """Before a reply: wait (a little) for a model that is still warming up."""
        if self.ollama is None:
            return self.llm is not None
        if self.ollama.ready:
            self.ollama.used()
            return True
        try:
            return await asyncio.wait_for(self.ollama.ensure_ready(self._warm_llm),
                                          timeout=float(self.s.llm.get("warm_wait_s", 12)))
        except asyncio.TimeoutError:
            return False

    def _load_voices(self) -> None:
        """Both voice chains (speech/engines.py). Live Turbo loads in the background in its
        own process; until it is ready, cached clips, Kokoro or Piper speak."""
        from .speech.voices import build_voices, llm_reserve_mib
        s = self.s
        # Whisper loads AFTER the voice (in _init_hearing). Only if the owner pinned it to the card
        # ("cuda") is room kept for it; with "auto" the voice comes first and Whisper adapts.
        whisper_on_gpu = not self.opts.text_only and s.stt.device == "cuda"
        reserve = int(s.tts.turbo.get("reserve_whisper_mib", 600)) if whisper_on_gpu else 0
        # On demand the language model is not loaded yet: plan as if it were (DESIGN.md decision 24)
        llm_mib = llm_reserve_mib(on_demand=self.opts.llm and self.opts.llm_on_demand,
                                  loaded=self.local_llm is not None,
                                  llm_mib=int(s.tts.turbo.get("reserve_llm_mib", 5200)))
        try:
            self.voice_set = build_voices(s, reserve_mib=reserve, llm_mib=llm_mib, log_dir=s.path("data") / "logs",
                                          picks=getattr(self, "voice_picks", None))
        except Exception as e:  # noqa: BLE001 - Spike must still start (captions only if all voices fail)
            log.error("voices failed to load: %s", e)
            return
        for mode, chain in self.voice_set.chains.items():
            self.voices[mode] = chain

    def _stt_device(self) -> str:
        """Where Whisper runs. "auto" = the graphics card only if it still has room once the
        Turbo voice has loaded; otherwise the processor (DESIGN.md "Graphics memory": on the
        8 GB laptop card, Whisper there pushed the language model into system memory and made
        every reply ~0.7 s slower)."""
        want = str(self.s.stt.device)
        plan = getattr(self.voice_set, "plan", None)
        if want != "auto" or plan is None or plan.device != "cuda":
            return want
        left = plan.left_mib()
        need = int(self.s.tts.turbo.get("reserve_whisper_mib", 600))
        if left is None or left < need:
            log.info("Whisper runs on the processor (%s MiB left on the graphics card after the voice, it needs "
                     "about %d)", "?" if left is None else left, need)
            return "cpu"
        return want

    def _init_hearing(self) -> None:
        from .hearing.audio import MicSource, RemoteSource
        from .hearing.listener import Listener
        from .hearing.stt import Transcriber
        from .hearing.vad import make_vad
        from .hearing.wake import VoskSpotter, WakeMatcher
        s = self.s
        aliases = {m: p.wake_aliases for m, p in s.personas.items()}
        vocative = {v for p in s.personas.values() for v in p.vocative_only}
        matcher = WakeMatcher(aliases, s.wake.fuzzy_threshold, vocative)
        spotter = None
        try:
            spotter = VoskSpotter(s.path(s.wake.vosk_model), aliases)
            if spotter.missing_words:
                log.info("wake words not in Vosk's dictionary (matched by their sound-alikes instead): %s",
                         ", ".join(spotter.missing_words))
        except Exception as e:  # noqa: BLE001
            log.error("keyword spotter unavailable (%s); only a head tap will wake Spike", e)
        prompt_words = sorted({w for p in s.personas.values() for w in [p.name, *p.wake_words]})
        stt = Transcriber(s.path("models/whisper"), s.stt.model, s.stt.cpu_model, self._stt_device(),
                          s.stt.compute_type_cuda, s.stt.compute_type_cpu, s.stt.beam_size, s.stt.cpu_threads,
                          prompt_words=prompt_words)
        vad = make_vad(s.vad.engine, s.path(s.vad.model))
        self.listener = Listener(vad=vad, matcher=matcher, transcriber=stt, spotter=spotter,
                                 on_event=lambda k, d: self._threadsafe(self._on_listener_event, k, d),
                                 threshold=s.vad.threshold, end_silence_ms=s.vad.end_silence_ms,
                                 min_speech_ms=s.vad.min_speech_ms, max_utterance_s=s.vad.max_utterance_s,
                                 preroll_ms=s.vad.preroll_ms, min_conf=s.wake.min_confidence,
                                 strong_conf=s.wake.strong_confidence, listen_timeout_s=s.wake.listen_timeout_s,
                                 refractory_s=s.wake.refractory_s,
                                 debug_dir=s.path("data/debug") if s.debug.save_audio else None)
        self.listener.start()
        self.remote_mic = RemoteSource()
        if self.opts.mic:
            self.mic = MicSource(s.audio.mic_device or None)
            try:
                self.mic.start(self.listener.feed)
            except Exception as e:  # noqa: BLE001
                log.error("microphone unavailable (%s). Type to talk instead.", e)
                self.mic = None
                self.opts.console = True

    def _init_eyes(self) -> None:
        from .vision.camera import RemoteCameraSource, WebcamSource
        from .vision.eyes import Eyes
        s = self.s
        aruco = None
        if s.aruco.enabled:
            try:
                from .vision.aruco import HomeMarkerDetector
                aruco = HomeMarkerDetector(s.aruco.dictionary, s.aruco.home_marker_id, s.aruco.marker_size_m,
                                           s.aruco.horizontal_fov_deg)
            except Exception as e:  # noqa: BLE001
                log.warning("ArUco home marker disabled: %s", e)
        self.remote_cam = RemoteCameraSource()
        source = WebcamSource(s.vision.camera_index, s.vision.width, s.vision.height)
        self.eyes = Eyes(source, face_model=s.path(s.vision.face_model), gesture_model=s.path(s.vision.gesture_model),
                         on_event=lambda k, d: self._threadsafe(self._on_vision_event, k, d),
                         process_fps=s.vision.process_fps, look_at_hz=s.vision.look_at_hz,
                         present_after_s=s.vision.present_after_s, absent_after_s=s.vision.absent_after_s,
                         emotion_window_s=s.vision.emotion_window_s, sad_threshold=s.vision.sad_threshold,
                         tired_threshold=s.vision.tired_threshold, mirror=s.vision.mirror, aruco=aruco)
        try:
            self.eyes.start()
            self.owner.present = False
        except Exception as e:  # noqa: BLE001
            log.error("camera unavailable (%s); Spike will run without eyes", e)
            self.eyes = None

    async def run(self) -> None:
        """Start, run until asked to stop, shut down. A stop request while the models
        are still loading (closing the window early) is honoured straight away."""
        starting = asyncio.create_task(self.start(), name="start")
        stopping = asyncio.create_task(self._stop.wait(), name="stop-wait")
        try:
            await asyncio.wait({starting, stopping}, return_when=asyncio.FIRST_COMPLETED)
            if starting.done():
                starting.result()                      # start-up errors (e.g. port busy) surface here
                await stopping
            else:
                log.info("stop requested while starting up")
                starting.cancel()
                try:
                    await starting
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        finally:
            stopping.cancel()
            await self.shutdown()

    def request_stop(self) -> None:
        self._stop.set()

    async def shutdown(self) -> None:
        log.info("%s is going to sleep...", self.persona.name)
        for t in self._tasks:
            t.cancel()
        if self.turn_task:
            self.turn_task.cancel()
        if self.speech:
            self.speech.stop()
            self.speech.close()
        if self.voice_set is not None:
            log.info("voices used this session: %s", self.voice_set.summary().get("used"))
            await asyncio.get_running_loop().run_in_executor(None, self.voice_set.close)   # stops the Turbo worker
        if self.mic:
            self.mic.stop()
        if self.listener:
            self.listener.stop()
        if self.eyes:
            self.eyes.stop()
        await self.app.stop()
        await self.server.stop()
        if self.local_llm and self.s.llm.unload_on_exit:
            await self.local_llm.unload()
        if self.ollama is not None:
            await self.ollama.close()           # stops `ollama serve` only if Spike started it
        self.memory.close()
        if self.timings:
            log.info("latency summary: %s", self.latency_summary())

    # ------------------------------------------------------------------ protocol in
    async def on_connect(self, client: Client) -> None:
        self.server.send(client, "set_mode", mode=self.mode)
        self.server.send(client, "mood", mood=self.robot_mood if self.robot_mood in P.MOODS else "neutral")
        self.server.send(client, "listening", state="idle")
        if self.ringer and client.has("face"):
            self.server.send(client, "alarm", alarm_id=self.ringer.timer_id, state="ringing",
                             level=max(0, self.ringer.last_level), label="Wake up")
        await self.app.on_connect(client)       # v1.2: app status and lists, saved face for robots

    async def on_disconnect(self, client: Client) -> None:
        if client is self.end_silence_client:
            self._stream_end_silence(client, None)
        # the speech deadline timer finishes any utterance that was playing there
        await self.app.on_disconnect(client)    # v1.2: drive dead-man stop, robot_status to the app

    async def on_message(self, client: Client, msg: dict) -> None:
        if await self.app.handle(client, msg):  # v1.2: app-only messages (applink.py)
            return
        t = msg["type"]
        if t == "audio":
            if client.role == "app":
                self.app_mic = (client, time.monotonic())
            if self.remote_mic and self.listener:
                self._stream_end_silence(client, msg.get("end_silence_ms"))
                if self.remote_mic._reframer is None:
                    self.remote_mic.start(self.listener.feed)
                self.remote_mic.push(P.unb64(msg["data"]), int(msg.get("rate", 16000)), msg.get("seq"))
        elif t == "camera":
            if self.remote_cam:
                self.remote_cam.push_jpeg(P.unb64(msg["data"]), msg.get("seq"))
        elif t == "say_state":
            if self.speech:
                self.speech.on_say_state(msg["utt"], msg.get("seq"), msg["state"], client=client)
        elif t == "touch":
            if client.role == "app" and msg["zone"] == "head" and msg.get("gesture", "tap") != "release":
                self.app_mic = (client, time.monotonic())      # push-to-talk starts with a head tap
            with reply_to(self.reply_origin(client) if client.role == "app" else None):
                await self.on_touch(msg["zone"], msg.get("gesture", "tap"))
        elif t == "imu":
            await self.on_imu(msg["event"])
        elif t == "battery":
            await self.on_battery(float(msg["percent"]), bool(msg.get("charging", False)), msg.get("volts"))
        elif t == "mood_state":
            if msg.get("mood"):
                self.robot_mood = msg["mood"]
            mode = msg.get("mode")
            if mode in P.MODES and mode != self.mode:
                await self.set_mode(mode, announce=False, from_robot=True)
        elif t == "text":
            text = msg["text"].strip()[:500]
            if text:
                self.start_turn(text, "typed", origin=self.reply_origin(client))
        elif t == "alarm_ack":
            if msg["action"] == "stop":
                await self.alarm_stop()
            else:
                await self.alarm_snooze(None)
        elif t == "edge":
            log.info("edge sensor %s: %s", msg["sensor"], msg["state"])
        elif t == "log":
            log.info("[%s] %s: %s", client.label, msg.get("level", "info"), msg["msg"][:300])

    END_SILENCE_MIN_MS, END_SILENCE_MAX_MS = 1500, 6000

    def _stream_end_silence(self, client: Client, ms) -> None:
        """PROTOCOL.md 6.7: an app mic stream may carry `end_silence_ms` (the owner's
        "Wait before Spike answers"). While it does, a request ends only after that much
        silence; a chunk without it, or that client leaving, puts the brain's own back."""
        if not self.listener:
            return
        if isinstance(ms, int) and not isinstance(ms, bool):
            ms = max(self.END_SILENCE_MIN_MS, min(self.END_SILENCE_MAX_MS, ms))
            if self.end_silence_client is client and self._end_silence_ms == ms:
                return
            self.end_silence_client, self._end_silence_ms = client, ms
            self.listener.set_end_silence(ms)
        elif self.end_silence_client is client:
            self.end_silence_client, self._end_silence_ms = None, None
            self.listener.set_end_silence(self.s.vad.end_silence_ms)

    def send_face(self, type_: str, **fields) -> None:
        if type_ == "action" and not is_available(fields.get("action")):
            log.warning("dropped action %s: the robot body cannot do it (capabilities.py)", fields.get("action"))
            return
        self.server.broadcast(type_, cap="face", **fields)

    def set_listening(self, state: str) -> None:
        self.send_face("listening", state=state)

    def interacted(self) -> None:
        self.last_interaction = time.monotonic()

    # ------------------------------------------------------------------ touch / imu / battery
    async def on_touch(self, zone: str, gesture: str) -> None:
        self.interacted()
        if zone == "head" and gesture != "release":
            self.wake_llm("head tap")
        if zone != "head" or gesture == "release":
            return
        if self.ringer:
            await self.alarm_snooze(None)
            return
        if self.speech and self.speech.speaking:
            self.speech.stop()                       # a tap while he talks = "hush, listen"
        if self.listener:
            self.listener.wake_by_touch("tap")

    async def on_imu(self, event: str) -> None:
        self.interacted()
        if event in ("pickup", "lap") and self.idle() and self.rng.random() < 0.5:
            await self.say_line("picked_up")
        elif event == "fall" and self.idle():
            await self.say_line("fell")

    async def on_battery(self, percent: float, charging: bool, volts=None) -> None:
        s = self.s.life
        prev_level, prev_charging = self.hunger, self.charging
        self.battery, self.charging = percent, charging
        level = "weak" if percent < s.battery_weak_below else ("hungry" if percent < s.battery_hungry_below else "ok")
        self.hunger = "ok" if charging else level
        if charging and not prev_charging:
            if self.idle():
                await self.say_line("charging")
        elif prev_charging and not charging and percent >= 99:
            if self.idle():
                await self.say_line("full")
        elif not charging and level != "ok" and level != prev_level:
            if self.idle():
                await self.say_line("weak" if level == "weak" else "hungry")

    # ------------------------------------------------------------------ hearing events
    def _set_mic_muted(self, muted: bool) -> None:
        if self.listener:
            self.listener.set_muted(muted)

    def _mute_briefly(self, ms: int = 450) -> None:
        """Mute around a short robot sound (yip/meow) so the mic doesn't hear it."""
        if not self.listener or (self.speech and self.speech.speaking):
            return
        self.listener.set_muted(True)

        def unmute():
            if not (self.speech and self.speech.speaking):
                self.listener.set_muted(False)
        self.loop.call_later(ms / 1000, unmute)

    def _on_listener_event(self, kind: str, data) -> None:
        if kind in ("wake_candidate", "wake_only"):
            self.wake_llm("wake word")
        if kind == "wake_candidate":
            self.set_listening("wake")
        elif kind == "wake_rejected":
            self.set_listening("idle")
        elif kind == "wake_only":
            if data.get("mode") and data["mode"] != self.mode and self.s.wake.cross_mode_switch:
                self._spawn(self.set_mode(data["mode"], announce=False))
            self.interacted()
            self.send_face("sound", sound=self.persona.wake_sound)
            self._mute_briefly()
            self.set_listening("listening")
        elif kind == "listening":
            self.set_listening("listening")
        elif kind == "captured":
            self.set_listening("thinking")
        elif kind == "heard":
            self.start_turn(data.text, data.via, data, origin=self.voice_origin())
        elif kind == "not_understood":
            self.set_listening("idle")
            if data.get("via") in ("tap", "wake_only"):
                self._spawn(self.say_line("didnt_catch"))
        elif kind == "listen_timeout":
            self.set_listening("idle")

    # ------------------------------------------------------------------ vision events
    def _on_vision_event(self, kind: str, data) -> None:
        if kind == "look":
            self.send_face("look_at", x=round(data[0], 3), y=round(data[1], 3), source="camera")
        elif kind == "presence":
            self._spawn(self._on_presence(data))
        elif kind == "emotion":
            self.owner.emotion = data
            self.owner.emotion_since = time.monotonic()
            self.memory.log_mood(data, "camera")
            log.info("owner looks %s", data)
            if data == "sad" and self.idle():
                self.send_face("mood", mood="caring")
        elif kind == "rps":
            self._spawn(self._rps_seen(data))
        elif kind == "home_marker":
            if data is None:
                log.info("home marker out of sight")
            else:
                log.info("home marker %d at %.2f m, bearing %.0f deg", data.marker_id, data.distance_m,
                         data.bearing_deg)

    async def _on_presence(self, ev) -> None:
        now = datetime.now()
        if ev.kind == "left":
            self.owner.present = False
            self.memory.log_event("owner_left")
            log.info("owner left")
            return
        self.owner.present = True
        self.owner.arrived_at = time.monotonic()
        self.memory.log_event("owner_arrived")
        log.info("owner arrived (away %s)", "a long time" if ev.away_s == float("inf") else f"{ev.away_s / 60:.0f} min")
        if self.quiet_hours(now) or not self.idle() or self.ringer:
            return
        if await self._crisis_followup_due():
            return
        first_sighting = ev.away_s == float("inf")
        if not first_sighting and self.s.life.greet_on_arrival and ev.away_s / 60 >= self.s.life.come_home_after_min:
            self.send_face("event", event="comeHome")
            await asyncio.sleep(0.6)
            await self.say_line("come_home")
            self.owner.last_greet_part, self.owner.last_greet_day = time_of_day(now.hour), now.date().isoformat()
        elif first_sighting or self.s.life.time_of_day_hello:
            await self._greet(first=first_sighting)

    async def _greet(self, first: bool = False) -> None:
        """Time-of-day hello, once per part of the day. The first line of a session is always one."""
        now = datetime.now()
        part, day = time_of_day(now.hour), now.date().isoformat()
        if (part, day) == (self.owner.last_greet_part, self.owner.last_greet_day) and not first:
            return
        key = {"morning": "greet_morning", "afternoon": "greet_afternoon",
               "evening": "greet_evening"}.get(part, "greet_night")
        self.owner.last_greet_part, self.owner.last_greet_day = part, day
        await self.say_line(key)

    # ------------------------------------------------------------------ console
    def _start_console(self) -> None:
        """Typed input from the terminal, or piped in (scripted personality tests):
        one line at a time, each waiting for the previous reply to finish."""
        if self._console_thread or sys.stdin is None:
            return
        interactive = sys.stdin.isatty()

        def reader():
            if interactive:
                print(f"\nType to talk to {self.persona.name} (Ctrl+C to quit).\n", flush=True)
            while not self._stop.is_set():
                try:
                    line = sys.stdin.readline()
                except (OSError, ValueError, KeyboardInterrupt):
                    line = ""
                if line == "":                                  # end of input
                    break
                line = line.strip()
                if not line:
                    continue
                if not interactive and self.opts.print_replies:
                    print(f"> {line}", flush=True)
                fut = asyncio.run_coroutine_threadsafe(self.console_turn(line), self.loop)
                try:
                    fut.result(timeout=180)
                except Exception:  # noqa: BLE001 - one bad line must not end the chat
                    log.exception("typed line failed")
            if self.opts.exit_at_eof and not self._stop.is_set():
                log.info("end of typed input")
                self._threadsafe(self.request_stop)

        self._console_thread = threading.Thread(target=reader, name="console", daemon=True)
        self._console_thread.start()

    async def console_turn(self, line: str) -> None:
        """Run one typed line to the end: the reply is generated AND finished speaking."""
        self.start_turn(line, "typed")
        task = self.turn_task
        try:
            await task
        except asyncio.CancelledError:
            pass
        utt = self.speech.current if self.speech else None
        if utt is not None:
            try:
                await asyncio.wait_for(utt.done.wait(), timeout=90)
            except asyncio.TimeoutError:
                pass

    # ------------------------------------------------------------------ turns
    def start_turn(self, text: str, via: str, heard=None, origin: Client | None = None) -> None:
        """A request from the owner (heard or typed). A new one replaces a running one.
        `origin`: the phone the request came from (reply_origin); its reply plays there (v1.5)."""
        if self.turn_task and not self.turn_task.done():
            self.turn_task.cancel()
        if self.speech and self.speech.speaking and via != "alarm":
            self.speech.stop()
        self.wake_llm("owner talking")
        self.turn_task = asyncio.create_task(self._turn(text, via, heard, origin), name="turn")

    async def _turn(self, text: str, via: str, heard=None, origin: Client | None = None) -> None:
        REPLY_TO.set(origin)                      # task-local: this turn's replies play on that phone (v1.5)
        if not self._ready.is_set():
            await self._ready.wait()        # still loading models: answer as soon as ready
        self.interacted()
        timing = TurnTiming(via)
        if heard is not None:
            timing.speech_end, timing.endpoint = heard.t_speech_end, heard.t_endpoint
            timing.stt_done, timing.stt_ms = heard.t_stt_done, heard.stt_ms
        else:
            timing.speech_end = timing.endpoint = timing.stt_done = time.perf_counter()
        self.current_timing = timing
        self.owner_turns += 1
        self.turn_said = []
        self.turn_raw_tags = (None, None)
        level, kind = safety.Level.NONE, ""
        log.info("owner (%s): %s", via, text)
        self.app.heard(text, via)                 # v1.2: the app's Talk screen shows what was said
        try:
            if via == "typed":                        # "Spicy, sit down" typed: same as said
                m = self.text_matcher.match(text)
                if m is not None:
                    heard_mode = m.mode
                    if heard_mode != self.mode and self.s.wake.cross_mode_switch:
                        await self.set_mode(heard_mode, announce=False)
                    if not m.rest and not GREETING_WORDS.search(text.lower()):
                        await self.say_line("wake_ack")
                        return
                    text = m.rest or text                 # "Hi Spike!" is a hello to answer
            if heard is not None and heard.mode and heard.mode != self.mode and self.s.wake.cross_mode_switch:
                await self.set_mode(heard.mode, announce=False)
            self.set_listening("thinking")
            # 1. safety and care: how is the owner? (before anything else)
            screen = safety.screen_input(text)
            level, kind = screen.level, screen.kind
            if level != safety.Level.CRISIS and screen.needs_llm_check and self.s.safety.llm_crisis_check \
                    and self.local_llm is not None:
                checked = await self._classify_risk(text)
                if checked == safety.Level.CRISIS:
                    level, kind = checked, "self_harm"
                elif checked == safety.Level.SUPPORT and level == safety.Level.NONE:
                    level, kind = checked, "sad"
            if level == safety.Level.CRISIS:
                await self._crisis(kind)
                return
            if safety.request_blocked(text):
                await self.say_line("unsafe_replacement")
                return
            if level == safety.Level.SUPPORT:
                # tired passes sooner than sad: warmth for 5 min, for 15 when sad, lonely or grieving
                self.support_kind = kind
                self.support_until = time.monotonic() + (5 if kind == "tired" else 15) * 60
                if kind == "lonely":
                    self.owner.lonely_signal_at = time.monotonic()
            elif self.support_kind and FEELING_BETTER.search(text.lower()):
                self.support_kind = None                  # they sound better: humour is allowed again
            # 2. commands
            intent = self._match(text)
            if intent is not None:
                await self._do_intent(intent, text)
                return
            if self.pending and await self._fill_pending(text):
                return
            # 3. conversation
            await self._chat(text, support=self._support())
            # 4. memory
            if level == safety.Level.NONE:
                self._remember_from(text)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a broken turn must never kill Spike
            log.exception("turn failed")
            await self.say_line("fallback")
        finally:
            self.last_turn = {"text": text, "level": level.name, "kind": kind, "said": list(self.turn_said),
                              "raw_tags": self.turn_raw_tags}
            if self.speech is None or not self.speech.speaking:
                self.set_listening("idle")

    def _support(self) -> str | None:
        """How the owner is right now, if they need warmth (sad, lonely, tired, grief)."""
        if self.support_kind and time.monotonic() < self.support_until:
            return self.support_kind
        self.support_kind = None
        return None

    def _match(self, text: str) -> Intent | None:
        return match_intent(text, self.names, datetime.now(), alarm_ringing=self.ringer is not None,
                            in_rps=bool(self.rps and self.rps.get("await_voice")),
                            confirming_forget_all=time.monotonic() < self.forget_all_until)

    async def _classify_risk(self, text: str) -> safety.Level:
        try:
            raw = await self.local_llm.complete_json(safety.CLASSIFIER_SYSTEM, text, safety.CLASSIFIER_SCHEMA,
                                                     max_tokens=20, timeout=4.0)
            level = safety.parse_classifier(raw)
            if level != safety.Level.NONE:
                log.info("safety check: %s", level.name.lower())
            return level
        except LLMError:
            return safety.Level.NONE

    async def _crisis(self, kind: str = "self_harm") -> None:
        """Calm, caring, no jokes; point to real people, numbers said once. Log only that it happened."""
        self.crisis_until = time.monotonic() + 3 * 3600
        self.memory.log_event("crisis_moment")          # no words, no details
        log.warning("crisis safety net engaged (%s; nothing of what was said is stored)", kind)
        self.send_face("mood", mood="caring")
        await self.say_line("emergency" if kind == "emergency" else "crisis", **self.s.helpline())

    async def _crisis_followup_due(self) -> bool:
        last = self.memory.last_event("crisis_moment")
        if last is None:
            return False
        age_h = (time.time() - last) / 3600
        if not (self.s.safety.checkin_after_crisis_h <= age_h <= 72):
            return False
        done = self.memory.last_event("crisis_followup")
        if done is not None and done > last:
            return False
        self.memory.log_event("crisis_followup")
        await self.say_line("crisis_followup")
        return True

    # ------------------------------------------------------------------ talking
    def situation(self, text: str, notes: list[str] | None = None) -> Situation:
        other = [p.name for m, p in self.s.personas.items() if m != self.mode]
        return Situation(now=datetime.now(), owner_name=self.memory.owner_name(), owner_present=self.owner.present,
                         owner_emotion=self.owner.emotion if self.owner.present else None,
                         memories=self.memory.context_for(text, datetime.now().date(), self.s.memory.max_prompt_chars),
                         notes=notes or [], battery=self.battery, other_name=other[0] if other and other[0].lower() in text.lower() else None)

    async def _chat(self, text: str, support: str | None = None, extra_notes: list[str] | None = None,
                    remember_exchange: bool = True) -> None:
        notes = list(extra_notes or [])
        in_crisis = time.monotonic() < self.crisis_until
        if in_crisis:
            notes.append(safety.SAFETY_MODE_NOTE)
        elif support:
            notes.append(safety.SUPPORT_NOTES.get(support, safety.SUPPORT_NOTES["sad"]))
            if support == "lonely" and self._nudge_due(soon_after_lonely=True):
                notes.append(safety.LONELY_CALL_HINT)     # only after a real conversation, never first
                self.memory.log_event("people_nudge")
        elif self.owner.present and self.owner.emotion in ("sad", "tired"):
            notes.append(safety.SUPPORT_NOTES[self.owner.emotion] + " (Your camera sees it on their face.)")
            support = self.owner.emotion
        if safety.is_honesty_question(text):
            notes.append("They are asking what you are. In your first sentence say plainly that you are a robot "
                         "with an AI brain (use the words robot and AI), not a human and not a living animal; "
                         "then say you really do like being with them.")
        if ORDER.search(text.strip().lower()) and support in (None, "tired") and not in_crisis:
            notes.append("This is an order. " + ("Refuse or question it first, then do it anyway in the same reply, "
                         "ending with a line like '...Fine.' Two short sentences."
                         if self.mode == "cat" else "Do it happily, with a short cheeky line."))
        # a loneliness signal earlier, and now ordinary talk: the nudge may be woven in (rarely)
        if not support and not in_crisis and self._lonely() and self._nudge_due(soon_after_lonely=True):
            notes.append("If it fits naturally, warmly encourage them to call or message a friend or family "
                         "member today, or to get outside for a bit.")
            self.memory.log_event("people_nudge")
        if self.ollama is not None and not await self._await_llm() and self.llm is None:
            # v1.2: the model is still waking up (or Ollama is missing): a scripted line, never silence
            await self.say_line("warming" if self.ollama.state == "warming" and self.persona.has_line("warming")
                                else "fallback")
            return
        if self.llm is None:
            await self.say_line("fallback")
            return
        warm = self._warmup
        if warm is not None and not warm.done():
            # a mode switch is still caching the new persona's prompt; racing it made the
            # next reply time out (28 Sep), so wait for it - the reply is then fast
            try:
                await asyncio.wait_for(asyncio.shield(warm), timeout=self.s.llm.first_token_timeout_s)
            except asyncio.TimeoutError:
                pass
        long_ok = bool(LONG_REQUEST.search(text.lower()))
        if long_ok:
            notes.append("They asked for something longer, so you may use up to five short sentences.")
        sysmsg = system_prompt(self.persona, self.memory.owner_name(), self.s.helpline())
        msgs = self.conv.build(sysmsg, self.situation(text, notes), text)
        timing = self.current_timing or TurnTiming("internal")
        reply = await self._stream_reply(
            msgs, timing, support=support,
            word_cap=self.s.tts.long_word_cap if long_ok else self.s.tts.reply_word_cap,
            max_tokens=self.s.llm.long_max_tokens if long_ok else None,
            joke=bool(JOKE_REQUEST.search(text.lower())))
        if reply and remember_exchange:
            self.conv.add(text, reply)

    async def _stream_reply(self, msgs: list[dict], timing: TurnTiming, support: str | None = None,
                            word_cap: int = 40, max_tokens: int | None = None, joke: bool = False) -> str | None:
        """LLM -> sentences -> safety check -> speech, pipelined. Returns the canonical reply text.

        Also enforces the spoken-reply rules: at most `word_cap` words (whole
        sentences only), a helpline number at most once, and a face and voice that
        fit the owner's state (soft voice and a lean-in when they are low)."""
        utt = self.speech.begin(self.mode)
        parser = StreamParser(self.s.tts.first_chunk_min_words, self.s.tts.max_chunk_chars)
        q: asyncio.Queue = asyncio.Queue()
        spoken: list[str] = []
        in_crisis = time.monotonic() < self.crisis_until
        state = {"mood": None, "action": None, "first_mood_sent": False, "support": support,
                 "crisis": in_crisis, "words": 0, "cap": word_cap, "helpline_said": False, "joke": joke}
        soft = bool(support) or in_crisis

        async def speaker():
            first = True
            while True:
                item = await q.get()
                if item is None:
                    break
                sentence, final = item
                t0 = time.perf_counter()
                # the face got its mood once already (mood=None); the voice takes it for its style tags
                await self.speech.segment(utt, sentence, mood=None, final=final, soft=soft,
                                          voice_mood=state["mood"])
                if first:
                    timing.first_audio_sent = utt.t_first_sent or time.perf_counter()
                    timing.tts_first_ms = (time.perf_counter() - t0) * 1000
                    timing.tts_engine = utt.engines[0] if utt.engines else ""
                    first = False
                    self.set_listening("speaking")

        speak_task = asyncio.create_task(speaker())
        timing.llm_start = time.perf_counter()
        stop: str | None = None
        try:
            async for piece in self.llm.stream(msgs, max_tokens=max_tokens):
                if not timing.first_token:
                    timing.first_token = time.perf_counter()
                for ev in parser.feed(piece):
                    stop = self._handle_reply_event(ev, state, spoken, q, timing)
                    if stop:
                        break
                if stop:
                    break
            if not stop:
                for ev in parser.finish():
                    stop = self._handle_reply_event(ev, state, spoken, q, timing, last=True)
                    if stop:
                        break
        except LLMError as e:
            log.warning("language model failed: %s", e)
            if not spoken:
                q.put_nowait(None)
                await speak_task
                await self.say_line("fallback")
                return None
        except asyncio.CancelledError:
            utt.cancelled = True
            speak_task.cancel()
            raise
        if stop and stop != "cap":
            log.warning("output check blocked a reply (%s)", stop)
            key = "honest_robot" if stop == "not_honest" else "unsafe_replacement"
            parsed = parse_reply(self.persona.line(key, self.rng))
            if parsed.mood:
                self.send_face("mood", mood=parsed.mood)
            q.put_nowait((parsed.text, False))
            spoken.append(parsed.text)
        if not state["first_mood_sent"]:
            self._apply_tags(state, None, None)
        q.put_nowait(("", True))                        # end marker
        q.put_nowait(None)
        await speak_task
        self._record_timing(timing, utt)
        if not spoken:
            return None
        text = " ".join(spoken)
        self._said(state["mood"] or "happy", state["action"], text)
        head = f"[{state['mood'] or 'happy'}" + (f"|{state['action']}]" if state["action"] else "]")
        log.info("%s: %s %s", self.persona.name, head, text)
        return f"{head} {text}"

    def _said(self, mood: str, action: str | None, text: str) -> None:
        self.said_count += 1
        self.turn_said.append({"mood": mood, "action": action, "text": text})
        if self.opts.print_replies:
            head = f"[{mood}" + (f"|{action}]" if action else "]")
            print(f"{self.persona.name}: {head} {text}".rstrip(), flush=True)

    def _handle_reply_event(self, ev: tuple, state: dict, spoken: list[str], q: asyncio.Queue,
                            timing: TurnTiming, last: bool = False) -> str | None:
        """Returns a reason to stop the reply (a safety category, or "cap"), else None."""
        kind = ev[0]
        if kind == "tags":
            self._apply_tags(state, ev[1], ev[2])
        elif kind == "action":
            if not state["action"] and not state["crisis"] and not state["support"]:
                state["action"] = ev[1]
                self.send_face("action", action=ev[1])
        elif kind == "sentence":
            sentence = strip_pet_names(ev[1])
            verdict = safety.check_output(sentence) or safety.check_output(" ".join(spoken + [sentence]))
            if verdict:
                return verdict
            if last and spoken and not re.search(r"[.!?…\"')]\s*$", sentence):
                return None                           # a fragment cut off by the token limit: drop it
            if last and not spoken and not re.search(r"[.!?…\"')]\s*$", sentence):
                sentence += "."
            numbers = [self.s.helpline().get("helpline_number", ""), self.s.helpline().get("emergency_number", "")]
            if safety.mentions_helpline(sentence, numbers):
                if state["helpline_said"]:
                    return None                       # never the same helpline twice in one reply
                state["helpline_said"] = True
            words = len(sentence.split())
            if spoken and state["words"] + words > state["cap"]:
                return "cap"                          # spoken replies stay short: whole sentences only
            if not spoken and words > state["cap"]:
                cut = " ".join(sentence.split()[:state["cap"]])
                sentence = (cut[:cut.rfind(",")] if "," in cut[len(cut) // 2:] else cut).rstrip(",;:- ") + "."
                words = len(sentence.split())
            if not state["first_mood_sent"]:
                self._apply_tags(state, None, None)
            if not timing.first_sentence:
                timing.first_sentence = time.perf_counter()
            spoken.append(sentence)
            state["words"] += words
            q.put_nowait((sentence, False))
        return None

    def _apply_tags(self, state: dict, mood: str | None, action: str | None) -> None:
        """Show the face once, before the first word - fitted to how the OWNER is:
        a lean-in and a caring face when they are low, a calm happy face and a slow
        wag when they are tired, nothing bouncy in a hard moment."""
        if state["first_mood_sent"]:
            return
        state["first_mood_sent"] = True
        self.turn_raw_tags = (mood, action)            # what the model chose (tools/persona_eval.py)
        mood, action = fit_tags(mood, action, state.get("support"), state.get("crisis", False),
                                state.get("joke", False))
        state["mood"], state["action"] = mood, action
        self.send_face("mood", mood=mood)
        if action:
            self.send_face("action", action=action)

    async def say_line(self, key: str, **fmt) -> None:
        """Speak a scripted line from the persona file (mood/action tags applied)."""
        fmt.setdefault("owner", self.owner_ref())
        line_id, raw = self.persona.pick(key, self.rng, **fmt)
        if key in GREETING_LINES:
            self.greeted = True
        await self.say_text(raw, soft=key in SOFT_LINES, line_id=line_id)

    async def say_text(self, raw: str, soft: bool = False, line_id: str | None = None) -> None:
        if self.speech is None:
            log.info("%s (not speaking): %s", self.persona.name, raw)
            return
        parsed = parse_reply(raw)
        if parsed.mood:
            self.send_face("mood", mood=parsed.mood)
        if parsed.action:
            self.send_face("action", action=parsed.action)
        if not parsed.text:
            return
        log.info("%s: %s", self.persona.name, raw)
        self._said(parsed.mood or "happy", parsed.action, parsed.text)
        utt = self.speech.begin(self.mode)
        self.set_listening("speaking")
        t0 = time.perf_counter()
        await self.speech.segment(utt, parsed.text, mood=parsed.mood, final=True, soft=soft, line_id=line_id)
        timing = self.current_timing
        if timing is not None and not timing.first_audio_sent and asyncio.current_task() is self.turn_task:
            # a command answered with a scripted line: time it like a chat reply (tools/bench.py --scripted)
            timing.first_audio_sent = utt.t_first_sent or time.perf_counter()
            timing.tts_first_ms = (time.perf_counter() - t0) * 1000
            timing.tts_engine = utt.engines[0] if utt.engines else ""
            self._record_timing(timing, utt)

    async def _on_speech_done(self, utt: Utterance) -> None:
        timing = self.current_timing
        if timing and utt.t_first_played and not timing.first_played:
            timing.first_played = utt.t_first_played
        self.set_listening("idle")
        if not self.listener:
            return
        if self.ringer:
            self.listener.open_follow_up(10, via="alarm")
        elif self.rps and self.rps.get("await_voice"):
            self.listener.open_follow_up(6, via="follow_up")
        elif self.s.wake.follow_up_s > 0:
            self.listener.open_follow_up(self.s.wake.follow_up_s)

    def _record_timing(self, timing: TurnTiming, utt: Utterance) -> None:
        if timing.via not in ("wake", "tap", "follow_up", "wake_only", "typed", "bench"):
            return
        if utt.t_first_played:
            timing.first_played = utt.t_first_played
        rep = timing.report()
        stats = getattr(self.local_llm, "last_stats", None) if self.llm is not None else None
        if stats and getattr(self.llm, "last_used", "") in ("ollama", ""):
            rep["prompt_tokens"] = stats.get("prompt_count")
            rep["prompt_ms"] = round(stats.get("prompt_ms") or 0)
            rep["tokens"] = stats.get("eval_count")
        self.timings.append(rep)
        if self.s.debug.log_latency:
            log.info("latency: %s", rep)

    def latency_summary(self) -> dict:
        vals = [t["speech_end_to_first_audio_ms"] for t in self.timings
                if t.get("speech_end_to_first_audio_ms") and t["via"] != "typed"]
        if not vals:
            return {"turns": len(self.timings)}
        return {"turns": len(vals), "median_ms": statistics.median(vals), "max_ms": max(vals), "min_ms": min(vals)}

    # ------------------------------------------------------------------ memory
    def _remember_from(self, text: str) -> None:
        facts = extract.extract_rules(text, datetime.now())
        ids = []
        for f in facts:
            ids.append(self.memory.remember(f.text, f.kind, subject=f.subject, due=f.due, source="said"))
            log.info("remembered: %s", f.text)
        if ids:
            self.memory.last_ids = ids          # "forget that" = everything from what they just said
        if not facts and self.s.memory.llm_extraction and self.local_llm and extract.worth_llm_extraction(text):
            self._spawn(self._llm_extract(text))

    async def _llm_extract(self, text: str) -> None:
        for _ in range(40):                              # wait until he has finished talking
            if self.idle():
                break
            await asyncio.sleep(0.5)
        try:
            raw = await self.local_llm.complete_json(extract.LLM_SYSTEM, text, extract.LLM_SCHEMA, max_tokens=150,
                                                     timeout=10)
        except LLMError:
            return
        for f in extract.parse_llm_facts(raw):
            self.memory.remember(f.text, f.kind, due=f.due, source="extracted")
            log.info("remembered (llm): %s", f.text)

    # ------------------------------------------------------------------ commands
    async def _do_intent(self, intent: Intent, text: str) -> None:
        n, sl = intent.name, intent.slots
        log.info("command: %s %s", n, {k: str(v) for k, v in sl.items()})
        now = datetime.now()
        if n == "set_mode":
            if sl["mode"] == self.mode:
                await self.say_line("trick_ok")
            else:
                await self.set_mode(sl["mode"], announce=True)
        elif n == "stop":
            if self.speech:
                self.speech.stop()
            self.send_face("mood", mood="neutral")
        elif n == "forget_all":
            self.forget_all_until = time.monotonic() + 30
            await self.say_line("forget_all_confirm")
        elif n == "forget_all_confirmed":
            self.forget_all_until = 0
            self.memory.wipe()
            self.conv.clear()
            await self.say_line("forget_all_done")
        elif n == "forget_all_cancelled":
            self.forget_all_until = 0
            await self.say_line("forget_all_cancelled")
        elif n == "forget_last":
            gone = self.memory.forget_last()
            if self.conv.history:
                self.conv.history = self.conv.history[:-2]
            await self.say_line("forgot" if gone else "nothing_to_forget")
        elif n == "forget_about":
            gone = self.memory.forget_matching(sl["what"])
            await self.say_line("forgot" if gone else "nothing_to_forget")
        elif n == "recall_all":
            facts = self.memory.recall_all(8)
            if not facts:
                await self.say_line("nothing_to_forget")
            else:
                await self._chat(text, extra_notes=["They asked what you remember about them. In two or three short "
                                                    "sentences, tell them these things warmly, in your own words: "
                                                    + " ".join(f + "." for f in facts)], remember_exchange=False)
        elif n == "remember":
            fid = self.memory.remember(sl["fact"], "fact", source="voice")
            log.info("remembered on request (#%d): %s", fid, sl["fact"])
            await self.say_line("remembered")
        elif n == "set_alarm":
            if sl.get("at") is None:
                self.pending = ("alarm", time.monotonic() + 30, {})
                await self.say_line("ask_alarm_time")
            else:
                self.scheduler.add_alarm(sl["at"])
                await self.say_line("alarm_set", when=self._when(sl["at"], now))
        elif n == "set_reminder":
            if sl.get("at") is None:
                self.pending = ("reminder", time.monotonic() + 30, {"what": sl.get("what") or "that thing"})
                await self.say_line("ask_reminder_time")
            else:
                self.scheduler.add_reminder(sl["at"], sl.get("what") or "that thing")
                await self.say_line("reminder_set", when=self._when(sl["at"], now))
        elif n in ("cancel_alarm", "cancel_reminder"):
            if self.ringer and n == "cancel_alarm":
                await self.alarm_stop(quiet=True)
            count = self.scheduler.cancel("alarm" if n == "cancel_alarm" else "reminder")
            await self.say_line("timers_cancelled" if count else "timers_none")
        elif n == "list_timers":
            items = self.scheduler.upcoming()
            if not items:
                await self.say_line("timers_none")
            else:
                parts = []
                for t in items[:4]:
                    w = timeparse.say_time(t.due_dt, now)
                    parts.append(f"an alarm at {w}" if t.kind == "alarm" else f"a reminder at {w} to {t.label}")
                await self.say_line("timers_list", list="You have " + ", and ".join(parts))
        elif n == "tell_time":
            await self.say_line("tell_time", time=timeparse.say_time(now))
        elif n == "tell_date":
            await self.say_line("tell_date", date=now.strftime("%A, %d %B").replace(" 0", " "))
        elif n == "rps_start":
            await self.rps_start()
        elif n == "rps_choice":
            await self._rps_resolve(sl["choice"])
        elif n == "rps_stop":
            self.rps = None
            await self.say_line("stop_ok")
        elif n == "trick":
            await self.do_trick(sl.get("action"))
        elif n == "trick_unavailable":
            line, _offer = unavailable_line(sl["trick"], self.mode)
            await self.say_text(line)
        elif n == "sleep":
            self.send_face("action", action="fallAsleep")
            await self.say_line("sleep")
        elif n == "snooze":
            await self.alarm_snooze(sl.get("minutes"))
        elif n == "alarm_stop":
            await self.alarm_stop()

    def _when(self, at: datetime, now: datetime) -> str:
        delta = at - now
        if delta <= timedelta(hours=1) and delta.total_seconds() > 0:
            return "in " + timeparse.say_duration(delta)
        return "at " + timeparse.say_time(at, now) if at.date() == now.date() else timeparse.say_time(at, now)

    async def _fill_pending(self, text: str) -> bool:
        what, deadline, data = self.pending
        self.pending = None
        if time.monotonic() > deadline:
            return False
        when = timeparse.parse_when(text if re.search(r"\b(in|at)\b", text.lower()) else "at " + text, datetime.now())
        if when is None:
            return False
        now = datetime.now()
        if what == "alarm":
            self.scheduler.add_alarm(when.at)
            await self.say_line("alarm_set", when=self._when(when.at, now))
        else:
            self.scheduler.add_reminder(when.at, data.get("what", "that thing"))
            await self.say_line("reminder_set", when=self._when(when.at, now))
        return True

    async def set_mode(self, mode: str, announce: bool = True, from_robot: bool = False) -> None:
        if mode not in P.MODES or mode == self.mode:
            return
        old = self.persona.name
        self.mode = mode
        log.info("mode: %s -> %s", old, self.persona.name)
        if not from_robot:
            self.send_face("set_mode", mode=mode)
        if self.local_llm:
            self._warmup = self._spawn(self._warm_persona())
        if announce:
            await self.say_line("mode_to_cat" if mode == "cat" else "mode_to_dog")

    async def _warm_persona(self) -> None:
        """Cache the current persona's system prompt in the model (after a mode switch)."""
        try:
            await self.local_llm.warm_up(system_prompt(self.persona, self.memory.owner_name(), self.s.helpline()))
        except Exception as e:  # noqa: BLE001 - a failed warm-up only costs speed
            log.debug("persona warm-up failed: %s", e)

    async def do_trick(self, action: str | None, **extra) -> None:
        if not is_available(action):
            return await self._do_intent(Intent("trick_unavailable", {"trick": "do that"}), "")
        action = action or self.rng.choice(["zoomies", "tailWagDance", "playBow", "paw"])
        if self.mode == "cat" and self.persona.has_line("trick_refuse"):
            # Spicy ignores you on purpose... then does it anyway
            await self.say_line("trick_refuse")
            await asyncio.sleep(self.rng.uniform(2.0, 3.5))
        self.send_face("action", action=action, **extra)      # extra: v1.4 walk/paw fields, if any
        await asyncio.sleep(1.2)
        await self.say_line("trick_ok")

    # ------------------------------------------------------------------ alarms
    async def _ring(self, timer) -> None:
        if self.ringer:
            return
        log.info("alarm %d ringing", timer.id)
        self.ringer = AlarmRinger(timer.id, time.monotonic(), self.s.life.alarm_escalate_s,
                                  self.s.life.alarm_give_up_min * 60)
        if self.speech and self.speech.speaking:
            self.speech.stop()
        if self.listener:
            self.listener.open_follow_up(10, via="alarm")

    async def _ring_tick(self) -> None:
        step = self.ringer.tick(time.monotonic())
        if step is None:
            return
        if step.give_up:
            log.info("alarm %d gave up after %d min", self.ringer.timer_id, self.s.life.alarm_give_up_min)
            self.scheduler.give_up(self.ringer.timer_id)
            self.send_face("alarm", alarm_id=self.ringer.timer_id, state="stopped", level=0, label="Wake up")
            self.ringer = None
            return
        self.send_face("alarm", alarm_id=self.ringer.timer_id, state="ringing", level=step.level, label="Wake up")
        if step.sound:
            self.send_face("sound", sound="meow" if (self.mode == "cat" and step.sound in ("yip", "bark")) else step.sound)
        if step.action:
            self.send_face("action", action=step.action)
        if step.speak and not (self.speech and self.speech.speaking):
            await self.say_line("alarm")
        elif self.listener and not (self.speech and self.speech.speaking):
            self.listener.open_follow_up(10, via="alarm")

    async def alarm_stop(self, quiet: bool = False) -> None:
        if not self.ringer:
            return
        tid = self.ringer.timer_id
        self.ringer = None
        self.scheduler.stop(tid)
        self.send_face("alarm", alarm_id=tid, state="stopped", level=0, label="Wake up")
        self.interacted()
        if not quiet:
            await self.say_line("alarm_stopped")

    async def alarm_snooze(self, minutes: float | None) -> None:
        if not self.ringer:
            return
        tid = self.ringer.timer_id
        self.ringer = None
        minutes = minutes or self.s.life.alarm_snooze_min
        t = self.scheduler.snooze(tid, minutes)
        self.send_face("alarm", alarm_id=tid, state="snoozed", level=0, label="Wake up", until=int(t.due) if t else 0)
        if self.speech and self.speech.speaking:
            self.speech.stop()
        await self.say_line("alarm_snoozed")

    # ------------------------------------------------------------------ rock paper scissors
    async def rps_start(self) -> None:
        self.rps = {"score": (self.rps or {}).get("score", {"owner": 0, "robot": 0, "draws": 0}), "await_voice": False}
        self.send_face("game", game="rps", phase="start", score=self.rps["score"])
        await self.say_line("rps_start")
        if self.speech and self.speech.current:
            try:
                await asyncio.wait_for(self.speech.current.done.wait(), timeout=8)
            except asyncio.TimeoutError:
                pass
        for count in (3, 2, 1):
            self.send_face("game", game="rps", phase="countdown", count=count, score=self.rps["score"])
            self.send_face("sound", sound="pop")
            await asyncio.sleep(0.75)
        self.send_face("game", game="rps", phase="shoot", score=self.rps["score"])
        self.rps["robot"] = self.rng.choice(["rock", "paper", "scissors"])
        if self.eyes and self.owner.present is not False:
            self.eyes.start_rps_window(2.0)          # the result comes back as an "rps" vision event
        else:
            await self._rps_seen(None)

    async def _rps_seen(self, choice: str | None) -> None:
        if not self.rps:
            return
        if choice is None:
            self.rps["await_voice"] = True
            await self.say_line("rps_no_hand")
            return
        await self._rps_resolve(choice)

    async def _rps_resolve(self, owner_choice: str) -> None:
        if not self.rps or "robot" not in self.rps:
            await self.rps_start()
            return
        robot = self.rps["robot"]
        result = rps_result(owner_choice, robot)
        sc = self.rps["score"]
        sc["owner" if result == "win" else "robot" if result == "lose" else "draws"] += 1
        self.rps["await_voice"] = False
        self.rps.pop("robot", None)
        self.send_face("game", game="rps", phase="reveal", owner=owner_choice, robot=robot, result=result, score=sc)
        await self.say_line({"win": "rps_win", "lose": "rps_lose", "draw": "rps_draw"}[result])

    # ------------------------------------------------------------------ life tick
    def _lonely(self) -> bool:
        """They said they feel lonely in the last hour, or have looked sad for 10+ minutes."""
        now = time.monotonic()
        return now - self.owner.lonely_signal_at < 3600 or \
            (self.owner.emotion == "sad" and now - self.owner.emotion_since > 600)

    def _nudge_allowed(self) -> bool:
        """A nudge toward real people is never his opening line: it needs a greeting
        first, a real conversation this session, and some time since start-up."""
        s = self.s.life
        return (self.greeted and self.said_count > 0 and self.owner_turns >= s.people_nudge_min_turns
                and time.monotonic() - self.started_mono >= s.people_nudge_after_start_min * 60)

    def _nudge_due(self, soon_after_lonely: bool = False) -> bool:
        if not self._nudge_allowed():
            return False
        s = self.s.life
        last = self.memory.last_event("people_nudge") or 0.0
        hours = (time.time() - last) / 3600
        gap = s.people_nudge_after_lonely_h if (self._lonely() and soon_after_lonely) else s.people_nudge_min_gap_h
        return hours >= gap and time.monotonic() >= self.crisis_until

    async def _tick(self) -> None:
        last_slow = 0.0
        last_llm_ping = time.monotonic()
        while True:
            await asyncio.sleep(1.0)
            try:
                if self.local_llm is not None and time.monotonic() - last_llm_ping >= 20 * 60:
                    last_llm_ping = time.monotonic()      # keep the model on the card (see OllamaLLM.keep_resident)
                    self._spawn(self.local_llm.keep_resident())
                for t in self.scheduler.due_now():
                    if t.kind == "alarm":
                        await self._ring(t)
                    else:
                        await self._reminder(t)
                if self.ringer:
                    await self._ring_tick()
                now = time.monotonic()
                if now - last_slow >= 30:
                    last_slow = now
                    await self._life_checks()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.exception("life tick failed")

    async def _reminder(self, t) -> None:
        log.info("reminder: %s", t.label)
        while not self.idle():
            await asyncio.sleep(0.5)
        self.send_face("sound", sound="yip" if self.mode == "dog" else "trill")
        await asyncio.sleep(0.4)
        await self.say_line("reminder", what=t.label)

    async def _life_checks(self) -> None:
        if not self.idle() or self.ringer or self.rps or self.quiet_hours():
            return
        s = self.s.life
        now = time.monotonic()
        since_talk_min = (now - self.last_interaction) / 60
        gap_ok = (now - self.last_checkin) / 60 >= s.checkin_min_gap_min
        if self.owner.present and self.owner.emotion == "sad" and gap_ok \
                and (now - self.owner.emotion_since) / 60 >= s.checkin_sad_min:
            self.last_checkin = now
            self.memory.log_event("checkin_sad")
            await self.say_line("checkin_sad")
            return
        if self.owner.present and gap_ok and since_talk_min >= s.checkin_quiet_min \
                and (now - self.owner.arrived_at) / 60 >= s.checkin_quiet_min:
            self.last_checkin = now
            self.memory.log_event("checkin_quiet")
            await self.say_line("checkin_quiet")
            return
        # the chat is winding down: they talked in the last few minutes, but not just now
        if (self.owner.present or since_talk_min < 10) and 0.5 <= since_talk_min <= 5 and self._nudge_due():
            self.memory.log_event("people_nudge")
            await self.say_line("people_nudge")
            return
        around = self.owner.present or (self.owner.present is None and since_talk_min < 10)   # no camera: recent talk
        if around and self.memory.last_event("crisis_moment") and await self._crisis_followup_due():
            return
        per_check = s.surprise_cat_mode_per_day / (86400 / 30)
        if self.owner.present and since_talk_min > 2 and self.rng.random() < per_check \
                and now >= self.crisis_until:
            await self.set_mode("cat" if self.mode == "dog" else "dog", announce=True)
