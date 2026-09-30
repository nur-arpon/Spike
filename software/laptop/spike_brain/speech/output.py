"""Getting Spike's voice out: to the robot/simulator over the protocol, or to
the laptop speakers, plus the microphone mute that stops him hearing himself.

Mute rule (brief + PROTOCOL.md 5.4): the mic is muted from the moment the
first segment of an utterance is handed out until `mute_tail_ms` after the
last segment has finished playing (robot `say_state finished` report, or
the local player finishing), with a timeout in case a report never comes.
"""
from __future__ import annotations

import asyncio
import contextvars
import functools
import itertools
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import numpy as np

from .. import protocol as P
from . import stream_audio as SA
from .tts import MOUTH_RATE_HZ, Speech

log = logging.getLogger("spike.voice")

# v1.5 (PROTOCOL.md 10.8, DESIGN.md 6d): the phone app a conversation came from. The brain sets it at
# the start of a turn (task-local, so it follows that turn's replies and nothing else); SpeechOut.begin
# reads it. None = today's behaviour (the robot's speaker or the laptop's).
REPLY_TO: contextvars.ContextVar = contextvars.ContextVar("spike_reply_to", default=None)
_FROM_CONTEXT = object()


class reply_to:
    """`with reply_to(client): await ...` - speech started inside goes to that phone (if it can play).
    Resets on exit, so it never leaks into the connection handler that called it."""

    def __init__(self, client):
        self.client = client
        self._tok = None

    def __enter__(self):
        self._tok = REPLY_TO.set(self.client)
        return self

    def __exit__(self, *exc):
        REPLY_TO.reset(self._tok)
        return False


# PortAudio's own "default output" is not always the speaker the owner hears: on this laptop SteelSeries Sonar
# made it Sonar's virtual *microphone* sink (28 Sep 2026 - every sample played into silence). So an empty setting
# means the Windows default speaker via the MME "Sound Mapper", and a string setting is matched by NAME
# (device indices shift whenever Sonar or a headset reconnects).
SOUND_MAPPER = "Microsoft Sound Mapper - Output"


def resolve_output_device(setting: str | int | None, devices: list[dict] | None = None) -> int | None:
    """Turn the local_output_device setting into a PortAudio output index (None = PortAudio default)."""
    if isinstance(setting, int):
        return setting
    try:
        if devices is None:
            import sounddevice as sd
            devices = list(sd.query_devices())
    except Exception as e:  # noqa: BLE001
        log.warning("could not list audio devices (%s); using the default output", e)
        return None
    outs = [(i, d) for i, d in enumerate(devices) if d.get("max_output_channels", 0) > 0]
    want = (setting or "").strip().lower()
    if want:
        for i, d in outs:
            if want in d["name"].lower():
                log.info("speaker: %s (matched setting %r)", d["name"], setting)
                return i
        log.warning("no speaker matches %r; using the Windows default speaker instead", setting)
    for i, d in outs:
        if d["name"].startswith(SOUND_MAPPER):
            log.info("speaker: Windows default (%s)", d["name"])
            return i
    return None


class LocalPlayer:
    """Plays segments on the laptop speakers, one after another, on its own thread."""

    def __init__(self, device: str | int | None = None):
        self.device = resolve_output_device(device)
        self.q: queue.Queue = queue.Queue()
        self._stop_now = threading.Event()
        self.thread = threading.Thread(target=self._run, name="player", daemon=True)
        self.thread.start()

    def play(self, pcm: np.ndarray, rate: int, on_start: Callable[[], None], on_end: Callable[[bool], None]) -> None:
        self.q.put((pcm, rate, on_start, on_end))

    def stop(self) -> None:
        self._stop_now.set()
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:  # noqa: BLE001
            pass
        while not self.q.empty():
            try:
                _, _, _, on_end = self.q.get_nowait()
                on_end(False)
            except queue.Empty:
                break

    def close(self) -> None:
        self.stop()
        self.q.put(None)

    def _run(self) -> None:
        import sounddevice as sd
        while True:
            item = self.q.get()
            if item is None:
                return
            pcm, rate, on_start, on_end = item
            self._stop_now.clear()
            on_start()
            ok = True
            try:
                sd.play(pcm, rate, device=self.device, blocking=False)
                end = time.monotonic() + len(pcm) / rate + 0.5
                while sd.get_stream().active and time.monotonic() < end:
                    if self._stop_now.is_set():
                        ok = False
                        break
                    time.sleep(0.01)
            except Exception as e:  # noqa: BLE001
                log.warning("local playback failed: %s", e)
                ok = False
            on_end(ok)


@dataclass
class Utterance:
    id: str
    mode: str
    started: float = field(default_factory=time.perf_counter)
    segments: int = 0
    finished: set = field(default_factory=set)
    final_sent: bool = False
    cancelled: bool = False
    t_first_sent: float | None = None
    t_first_played: float | None = None
    total_ms: int = 0
    engines: list = field(default_factory=list)      # which voice said each segment (cache, turbo, ...)
    to: object | None = None                          # v1.5: the phone app that plays this utterance
    stream: object | None = None                      # its Ogg Opus stream (one per utterance)
    done: asyncio.Event = field(default_factory=asyncio.Event)


class SpeechOut:
    def __init__(self, server, voices: dict, *, output: str = "auto",
                 local_device: str | int | None = None, mute_tail_ms: int = 300,
                 report_timeout_s: float = 2.0, set_mic_muted: Callable[[bool], None] = lambda m: None,
                 on_done: Callable[[Utterance], Awaitable[None]] | None = None, text_only: bool = False):
        self.server = server
        self.voices = voices
        self.output = output
        self.local_device = local_device
        self.local: LocalPlayer | None = None
        self.mute_tail_ms = mute_tail_ms
        self.report_timeout_s = report_timeout_s
        self.set_mic_muted = set_mic_muted
        self.on_done = on_done
        self.text_only = text_only
        self._ids = itertools.count(1)
        self.current: Utterance | None = None
        self.utts: dict[str, Utterance] = {}
        self._lock = asyncio.Lock()
        self._muted = False
        self._unmute_task: asyncio.Task | None = None
        self._deadline_task: asyncio.Task | None = None
        self._expected_end = 0.0
        self.loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------ helpers
    def _target(self) -> str:
        if self.text_only or self.output == "none":
            return "none"
        if self.output == "local":
            return "local"
        if self.output == "robot":
            return "robot"
        return "robot" if self.server and self.server.has_cap("speaker") else "local"

    @property
    def speaking(self) -> bool:
        return self.current is not None and not self.current.done.is_set()

    def _mute(self) -> None:
        if self._unmute_task:
            self._unmute_task.cancel()
            self._unmute_task = None
        if not self._muted:
            self._muted = True
            self.set_mic_muted(True)

    def _schedule_unmute(self) -> None:
        async def later():
            await asyncio.sleep(self.mute_tail_ms / 1000)
            self._muted = False
            self.set_mic_muted(False)
        if self._unmute_task:
            self._unmute_task.cancel()
        self._unmute_task = asyncio.create_task(later())

    def app_client(self, utt: Utterance):
        """v1.5 routing rule: the phone that should play `utt`, or None (robot / laptop speaker as before).

        A phone plays an utterance only when the conversation came from it (utt.to), it is still
        connected and it said it can play audio (cap `audio_out`). Then it is the ONLY device that
        plays it: no laptop speaker, no robot speaker (they get the caption and mouth timing)."""
        c = utt.to
        if c is None or self.server is None or not hasattr(c, "has") or not c.has("audio_out"):
            return None
        return c if c in self.server.clients.values() else None

    def begin(self, mode: str, to=_FROM_CONTEXT) -> Utterance:
        """Start a new utterance (interrupts nothing; call stop() first to cut the old one).
        `to`: the phone app to play it on (default: the current turn's REPLY_TO)."""
        self.loop = asyncio.get_running_loop()
        utt = Utterance(id=f"u{next(self._ids)}", mode=mode, to=REPLY_TO.get() if to is _FROM_CONTEXT else to)
        self.utts[utt.id] = utt
        self.current = utt
        if len(self.utts) > 50:
            for k in list(self.utts)[:-20]:
                self.utts.pop(k, None)
        return utt

    async def segment(self, utt: Utterance, text: str, mood: str | None = None, final: bool = False,
                      soft: bool = False, voice_mood: str | None = None, line_id: str | None = None) -> None:
        """Synthesize one sentence and send/play it. Ordered per utterance.

        `mood` goes to the face in the say message (None = leave the face alone); `voice_mood`
        only colours the voice (Turbo style tags) and defaults to `mood`. `line_id` names a
        scripted line (for the owner's own recordings)."""
        if utt.cancelled:
            return
        app = self.app_client(utt)
        target = "app" if app is not None else self._target()
        voice = self.voices.get(utt.mode)
        if not text.strip():
            if final:                                   # end marker (PROTOCOL.md 5.4)
                async with self._lock:
                    seq = utt.segments
                    utt.segments += 1
                    utt.final_sent = True
                    if self.server:
                        self.server.broadcast("say", cap="face", utt=utt.id, seq=seq, final=True, text="",
                                              mood=None, duration_ms=0, audio=None, mouth=None)
                    self._segment_finished(utt.id, seq)
            return
        async with self._lock:
            if utt.cancelled:
                return
            speech: Speech | None = None
            # v1.7: a phone that voices its own replies (Gemini TTS) gets the checked text only
            synth = target in ("robot", "local") or (target == "app" and not self.text_only
                                                     and not getattr(app, "phone_voice", False))
            if synth and voice is not None and text.strip():
                if getattr(voice, "wants_hints", False):          # the voice chain (speech/engines.py)
                    call = functools.partial(voice.synthesize, text, soft, mood=voice_mood or mood,
                                             line_id=line_id, first=utt.segments == 0, utt=utt.id)
                else:                                             # a bare engine (tests, tools)
                    call = functools.partial(voice.synthesize, text, soft)
                try:
                    speech = await asyncio.get_running_loop().run_in_executor(None, call)
                except Exception as e:  # noqa: BLE001 - a voice failure must never end the reply
                    log.error("speech failed (%s); showing the words only", e)
                    speech = None
                if speech is not None:
                    utt.engines.append(getattr(speech, "engine", "") or "voice")
            if utt.cancelled:
                return
            seq = utt.segments
            utt.segments += 1
            if final:
                utt.final_sent = True
            if speech is not None or target == "app":
                self._mute()
            if target == "app":
                self._send_app(app, utt, seq, text, mood, final, speech)
            elif target == "robot":
                self._send_robot(utt, seq, text, mood, final, speech)
            elif target == "local" and speech is not None:
                self._play_local(utt, seq, text, mood, final, speech)
            else:
                self._send_caption(utt, seq, text, mood, final)
            if utt.t_first_sent is None:
                utt.t_first_sent = time.perf_counter()
            dur = speech.duration_ms if speech is not None else _caption_ms(text)
            utt.total_ms += dur
            now = time.perf_counter()
            self._expected_end = max(self._expected_end, now) + dur / 1000
            self._arm_deadline(utt)

    def _send_robot(self, utt, seq, text, mood, final, speech: Speech | None) -> None:
        clients = self.server.with_cap("speaker") if self.server else []
        for c in clients:
            sp = speech.resampled(c.audio_rates[0]) if (speech is not None and c.audio_rates) else speech
            chunks = P.split_audio(sp.pcm.astype("<i2").tobytes()) if sp is not None else []
            audio = None if sp is None else {"format": "pcm_s16le", "rate": sp.rate, "channels": 1,
                                             "samples": int(len(sp.pcm)), "chunks": len(chunks)}
            self.server.send(c, "say", utt=utt.id, seq=seq, final=final, text=text, mood=mood,
                             duration_ms=sp.duration_ms if sp is not None else _caption_ms(text),
                             audio=audio, mouth={"rate_hz": MOUTH_RATE_HZ, "values": sp.mouth} if sp else None)
            for i, ch in enumerate(chunks):
                self.server.send(c, "say_audio", utt=utt.id, seq=seq, index=i, last=i == len(chunks) - 1,
                                 data=P.b64(ch))
        # faces without a speaker still get the caption and the mouth timing
        if self.server:
            for c in self.server.with_cap("face"):
                if c.has("speaker"):
                    continue
                self.server.send(c, "say", utt=utt.id, seq=seq, final=final, text=text, mood=mood,
                                 duration_ms=speech.duration_ms if speech else _caption_ms(text), audio=None,
                                 mouth={"rate_hz": MOUTH_RATE_HZ, "values": speech.mouth} if speech else None)

    def _send_app(self, app, utt: Utterance, seq, text, mood, final, speech: Speech | None) -> None:
        """v1.5: the phone plays this utterance (PROTOCOL.md 10.8). It gets `play: true` and the audio as
        one continuing Ogg Opus stream (or PCM16); every other face (robot, simulator, other phones) gets
        the caption and the mouth timing only. `audio: null` with `play: true` = the phone says it with its
        own voice (the laptop had none for this sentence)."""
        fmt = getattr(app, "audio_format", "") or "pcm_s16le"
        audio, dur, mouth, chunks = None, _caption_ms(text), None, []
        if speech is not None:
            rate = SA.choose_rate(fmt, app.audio_rates)
            sp = speech.resampled(rate)
            try:
                if fmt == "ogg_opus" and utt.stream is None:
                    utt.stream = SA.OpusOggStream(rate)
                data, samples = SA.encode_for_client(utt.stream, fmt, sp.pcm)
            except Exception as e:  # noqa: BLE001 - an encoder failure falls back to plain PCM
                log.warning("Opus encoding failed (%s); sending PCM16", e)
                fmt = "pcm_s16le"
                data, samples = SA.encode_for_client(None, fmt, sp.pcm)
            chunks = SA.split_bytes(data)
            dur = int(round(samples * 1000 / rate))
            mouth = {"rate_hz": MOUTH_RATE_HZ, "values": speech.mouth}
            audio = {"format": fmt, "rate": rate, "channels": 1, "samples": int(samples), "chunks": len(chunks),
                     "bytes": len(data)}
        self.server.send(app, "say", utt=utt.id, seq=seq, final=final, text=text, mood=mood, duration_ms=dur,
                         audio=audio, mouth=mouth, play=True)
        for i, ch in enumerate(chunks):
            self.server.send(app, "say_audio", utt=utt.id, seq=seq, index=i, last=i == len(chunks) - 1,
                             data=P.b64(ch))
        for c in self.server.with_cap("face"):
            if c is not app:
                self.server.send(c, "say", utt=utt.id, seq=seq, final=final, text=text, mood=mood,
                                 duration_ms=dur, audio=None, mouth=mouth)

    def _send_caption(self, utt, seq, text, mood, final) -> None:
        if self.server:
            self.server.broadcast("say", cap="face", utt=utt.id, seq=seq, final=final, text=text, mood=mood,
                                  duration_ms=_caption_ms(text), audio=None, mouth=None)
        asyncio.get_running_loop().call_later(0.05, self._segment_finished, utt.id, seq)

    def _play_local(self, utt, seq, text, mood, final, speech: Speech) -> None:
        if self.local is None:
            self.local = LocalPlayer(self.local_device)
        if self.server:  # the simulator face (if any) shows the caption + mouth while the laptop plays
            self.server.broadcast("say", cap="face", utt=utt.id, seq=seq, final=final, text=text, mood=mood,
                                  duration_ms=speech.duration_ms, audio=None,
                                  mouth={"rate_hz": MOUTH_RATE_HZ, "values": speech.mouth})
        loop = asyncio.get_running_loop()
        self.local.play(speech.pcm, speech.rate,
                        on_start=lambda: loop.call_soon_threadsafe(self._segment_started, utt.id, seq),
                        on_end=lambda ok: loop.call_soon_threadsafe(self._segment_finished, utt.id, seq))

    # ------------------------------------------------------------------ progress reports
    def on_say_state(self, utt_id: str, seq: int | None, state: str, client=None) -> None:
        """Robot/simulator playback reports (protocol say_state). v1.5: for an utterance a phone plays,
        only that phone's reports count (a robot showing its caption must not end it early); a phone's
        report about anything else is ignored (PROTOCOL.md 10.1)."""
        utt = self.utts.get(utt_id)
        if client is not None and utt is not None:
            if utt.to is not None and self.app_client(utt) is not None:
                if client is not utt.to:
                    return
            elif getattr(client, "role", "") == "app":
                return
        if state == "started":
            self._segment_started(utt_id, seq)
        elif state in ("finished", "stopped"):
            self._segment_finished(utt_id, seq)

    def _segment_started(self, utt_id: str, seq: int | None) -> None:
        utt = self.utts.get(utt_id)
        if utt and utt.t_first_played is None:
            utt.t_first_played = time.perf_counter()

    def _segment_finished(self, utt_id: str, seq: int | None) -> None:
        utt = self.utts.get(utt_id)
        if not utt or utt.done.is_set():
            return
        utt.finished.add(seq if seq is not None else len(utt.finished))
        if utt.cancelled or (utt.final_sent and len(utt.finished) >= utt.segments):
            self._complete(utt)

    def _complete(self, utt: Utterance) -> None:
        if utt.done.is_set():
            return
        utt.done.set()
        utt.stream = None
        if self._deadline_task:
            self._deadline_task.cancel()
            self._deadline_task = None
        if self.current is utt or self.current is None or self.current.done.is_set():
            self._schedule_unmute()
        if self.on_done and not utt.cancelled:
            asyncio.create_task(self.on_done(utt))

    def _arm_deadline(self, utt: Utterance) -> None:
        """If playback reports never arrive, finish anyway after the expected end + timeout."""
        if self._deadline_task:
            self._deadline_task.cancel()

        async def deadline():
            while True:
                wait = self._expected_end + self.report_timeout_s - time.perf_counter()
                if wait <= 0:
                    break
                await asyncio.sleep(min(wait, 0.5))
            if not utt.done.is_set() and utt.final_sent:
                log.debug("no playback report for %s, finishing on timeout", utt.id)
                self._complete(utt)
        self._deadline_task = asyncio.create_task(deadline())

    async def finish(self, utt: Utterance) -> None:
        """Mark that no more segments will come (for replies that ended without a final flag)."""
        if not utt.final_sent:
            utt.final_sent = True
            if utt.segments == 0 or len(utt.finished) >= utt.segments:
                self._complete(utt)

    def stop(self) -> None:
        """Cut speech now (barge-in, 'stop')."""
        utt = self.current
        if utt and not utt.done.is_set():
            utt.cancelled = True
            if self.server:
                self.server.broadcast("stop_speaking", utt=utt.id)
            if self.local:
                self.local.stop()
            self._complete(utt)
        self._expected_end = time.perf_counter()

    def close(self) -> None:
        if self.local:
            self.local.close()


def _caption_ms(text: str) -> int:
    return int(min(8000, max(1200, 60 * len(text))))
