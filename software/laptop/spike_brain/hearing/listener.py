"""The listening state machine: wake word / head tap -> request -> transcript.

  IDLE ----(Vosk hears an alias)----> CAPTURE --(VAD end)--> Whisper --> wake confirmed?
    ^  \\--(head tap / follow-up)--> LISTEN --(VAD start..end)--> Whisper --> request
    |                                   |  (timeout)
    +-----------------------------------+
  MUTED: every frame is dropped while Spike talks (+300 ms, set by the brain).

Runs on its own worker thread (frames arrive from the mic thread through a
queue); Whisper runs on a second thread so frame processing never stalls.
Results go to `on_event(kind, data)`, which the brain marshals onto asyncio.
Timestamps are time.perf_counter() so the brain can measure latency from
the end of the owner's speech.
"""
from __future__ import annotations

import collections
import logging
import queue
import re
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .vad import FRAME, SAMPLE_RATE, Endpointer

log = logging.getLogger("spike.listen")

FRAME_S = FRAME / SAMPLE_RATE
SHORT_ANSWERS = {"yes", "no", "yeah", "nope", "yep", "sure", "okay", "ok", "thanks", "thank you", "please",
                 "maybe", "rock", "paper", "scissors", "stop", "snooze", "good", "bad", "fine", "hi", "hello"}


@dataclass
class Heard:
    text: str
    via: str                    # wake | tap | follow_up | alarm
    wake: str | None = None     # canonical wake word
    mode: str | None = None     # dog | cat (whose wake word)
    t_speech_end: float = 0.0   # perf_counter at the last voiced frame
    t_endpoint: float = 0.0     # perf_counter when the end of speech was decided
    t_stt_done: float = 0.0
    stt_ms: float = 0.0
    audio_s: float = 0.0


class Listener:
    IDLE, CAPTURE, LISTEN = "idle", "capture", "listen"

    def __init__(self, *, vad, matcher, transcriber, spotter=None, on_event: Callable[[str, Any], None],
                 threshold: float = 0.5, end_silence_ms: int = 450, min_speech_ms: int = 200,
                 max_utterance_s: float = 15, preroll_ms: int = 320, min_conf: float = 0.6,
                 strong_conf: float = 0.9, listen_timeout_s: float = 5.0, refractory_s: float = 1.0,
                 debug_dir: Path | None = None, clock=time.perf_counter):
        self.vad = vad
        self.matcher = matcher
        self.stt = transcriber
        self.spotter = spotter
        self.on_event = on_event
        self.ep = Endpointer(threshold, end_silence_ms, min_speech_ms)
        self.ep_offset = 0          # listener frame number of the endpointer's frame 0 (it resets on unmute)
        self.spec_frames = max(2, int(round(min(220, end_silence_ms * 0.5) / 1000 / FRAME_S)))
        self.max_frames = int(max_utterance_s / FRAME_S)
        self.preroll = int(preroll_ms / 1000 / FRAME_S)
        self.min_conf, self.strong_conf = min_conf, strong_conf
        self.listen_timeout_s = listen_timeout_s
        self.refractory_s = refractory_s
        self.debug_dir = debug_dir
        self.clock = clock

        self.q: queue.Queue = queue.Queue()
        self.ring: collections.deque = collections.deque(maxlen=int(20 / FRAME_S))
        self.index = -1
        self.frame_time: dict[int, float] = {}
        self.state = self.IDLE
        self.muted = False
        self.cap: dict | None = None            # current capture
        self.listen_until = 0.0
        self.listen_via = "tap"
        self.last_wake_at = -1e9
        self.last_segment: tuple[int, int] | None = None
        self.stt_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stt")
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="listener", daemon=True)

    # ------------------------------------------------------------------ control (any thread)
    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.q.put(("stop", None))
        self.thread.join(timeout=2)
        self.stt_pool.shutdown(wait=False, cancel_futures=True)

    def feed(self, frame: np.ndarray) -> None:
        self.q.put(("frame", (frame, self.clock())))

    def set_muted(self, muted: bool) -> None:
        self.q.put(("mute", muted))

    def wake_by_touch(self, via: str = "tap", timeout_s: float | None = None) -> None:
        self.q.put(("listen", (via, timeout_s or self.listen_timeout_s)))

    def keep_listening(self) -> None:
        """Silently push the end of an open listening window (a v1.6 `keepalive`). Emits nothing."""
        self.q.put(("keep", None))

    def open_follow_up(self, seconds: float, via: str = "follow_up") -> None:
        if seconds > 0:
            self.q.put(("listen", (via, seconds)))

    def cancel(self) -> None:
        self.q.put(("cancel", None))

    def set_end_silence(self, ms: int) -> None:
        """How long a silence ends a request (the phone app's "Wait before Spike answers",
        PROTOCOL.md 6.7 `end_silence_ms`). Applies from the next frame on."""
        self.q.put(("end_silence", int(ms)))

    # ------------------------------------------------------------------ worker
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                kind, data = self.q.get(timeout=0.1)
            except queue.Empty:
                self._check_timeout()
                continue
            try:
                if kind == "frame":
                    self._frame(*data)
                elif kind == "mute":
                    self._set_muted(data)
                elif kind == "listen":
                    self._start_listen(*data)
                elif kind == "keep":
                    if self.state == self.LISTEN and self.cap is None:
                        self.listen_until = self.clock() + self.listen_timeout_s
                elif kind == "cancel":
                    self._to_idle()
                elif kind == "end_silence":
                    self.ep.end_frames = max(1, int(round(data / self.ep.frame_ms)))
                elif kind == "stop":
                    break
            except Exception:  # noqa: BLE001 - never let the ears die
                log.exception("listener error")
                self._to_idle()
            self._check_timeout()

    def _set_muted(self, muted: bool) -> None:
        if muted == self.muted:
            return
        self.muted = muted
        if muted:
            if self.state == self.CAPTURE:
                self.cap = None
            self.state = self.IDLE if self.state == self.CAPTURE else self.state
        else:
            self.ep.reset()
            self.ep_offset = self.index + 1
            self.vad.reset()
            if self.spotter:
                self.spotter.reset()

    def _to_idle(self) -> None:
        self.state = self.IDLE
        self.cap = None

    def _start_listen(self, via: str, timeout_s: float) -> None:
        self.state = self.LISTEN
        self.listen_via = via
        self.listen_until = self.clock() + timeout_s
        self.cap = None
        if self.ep.in_speech:                      # already talking: capture from the start of this speech
            self.cap = {"start": max(self._ep_start() - self.preroll, self.index - self.max_frames),
                        "via": via, "wake": None, "mode": None, "conf": 0.0}
        if via in ("tap", "wake_only"):
            self.on_event("listening", {"via": via})

    def _check_timeout(self) -> None:
        if self.state == self.LISTEN and self.cap is None and self.clock() > self.listen_until:
            via = self.listen_via
            self._to_idle()
            self.on_event("listen_timeout", {"via": via})

    def _frame(self, frame: np.ndarray, t: float) -> None:
        self.index += 1
        i = self.index
        self.ring.append((i, frame))
        self.frame_time[i] = t
        if len(self.frame_time) > self.ring.maxlen + 64:
            for k in [k for k in self.frame_time if k < i - self.ring.maxlen]:
                del self.frame_time[k]
        if self.muted:
            return
        prob = self.vad(frame)
        ev = self.ep.push(prob)
        if ev:
            ev.frame_index += self.ep_offset            # into this listener's frame numbering
        hit = self.spotter.feed(frame.tobytes()) if self.spotter else None

        if ev and ev.kind == "start" and self.state == self.LISTEN and self.cap is None:
            self.cap = {"start": max(0, ev.frame_index - self.preroll), "via": self.listen_via,
                        "wake": None, "mode": None, "conf": 0.0}
        if hit:
            self._on_hit(hit)
        if self.cap is not None and i - self.cap["start"] > self.max_frames:
            self._finish_capture(i, forced=True)       # over-long speech: cut it here
            return
        if ev and ev.kind in ("end", "blip"):
            self.last_segment = (self._ep_start(), ev.frame_index)
            if self.cap is not None and ev.kind == "end":
                self._finish_capture(ev.frame_index)
            elif self.cap is not None and self.state == self.LISTEN:
                self.cap = None                   # a cough while waiting: keep waiting
        elif self.cap is not None and self.ep.in_speech and self.ep.run_lo == self.spec_frames:
            self._speculate()

    def _ep_start(self) -> int:
        return self.ep.start_index + self.ep_offset

    def _speculate(self) -> None:
        """The owner has been quiet for ~220 ms: start Whisper now on the audio so
        far. If the silence lasts to the real endpoint, that result is used and
        Whisper's time disappears from the wait; if they speak again, it is dropped."""
        last = self.ep.last_voiced + self.ep_offset
        end = min(self.index, last + int(0.15 / FRAME_S))
        frames = [f for (k, f) in self.ring if self.cap["start"] <= k <= end]
        if frames:
            self.cap["spec"] = (last, self.stt_pool.submit(self.stt.transcribe, np.concatenate(frames)))

    def _on_hit(self, hit) -> None:
        now = self.clock()
        if self.cap is not None:
            if hit.final:
                self._note_final(self.cap, hit)
            return
        if self.state != self.IDLE or now - self.last_wake_at < self.refractory_s:
            return
        # a wake candidate: capture this whole utterance (from its speech start)
        if self.ep.in_speech:
            start = max(0, self._ep_start() - self.preroll)
            self.cap = {"start": start, "via": "wake", "wake": hit.canonical, "mode": hit.mode, "conf": 0.0}
            if hit.final:
                self._note_final(self.cap, hit)
            self.state = self.CAPTURE
            self.on_event("wake_candidate", {"wake": hit.canonical, "mode": hit.mode})
        elif hit.final and self.last_segment:
            # Vosk finished after the VAD already ended the segment: use that segment
            s, e = self.last_segment
            self.cap = {"start": max(0, s - self.preroll), "via": "wake", "wake": hit.canonical,
                        "mode": hit.mode, "conf": 0.0}
            self._note_final(self.cap, hit)
            self.state = self.CAPTURE
            self.on_event("wake_candidate", {"wake": hit.canonical, "mode": hit.mode})
            self._finish_capture(e)

    @staticmethod
    def _note_final(cap: dict, hit) -> None:
        """Remember Vosk's final verdict on the wake word: its confidence, and
        whether the name was at the edge of the utterance (a call) or in the
        middle of a sentence (talking ABOUT Spike)."""
        cap["final_seen"] = True
        if hit.conf >= cap.get("conf", 0.0):
            cap["conf"] = hit.conf
            cap["edge"] = hit.words_before == 0 or hit.words_after == 0

    def _finish_capture(self, last_voiced: int, forced: bool = False) -> None:
        cap, self.cap = self.cap, None
        if cap is None:
            return
        end = min(self.index, last_voiced + int(0.15 / FRAME_S))
        frames = [f for (k, f) in self.ring if cap["start"] <= k <= end]
        if not frames:
            self._to_idle()
            return
        pcm = np.concatenate(frames)
        t_speech_end = self.frame_time.get(last_voiced, self.clock())   # a frame arrives when its audio ends
        t_endpoint = self.clock()
        via = cap["via"]
        if via == "wake":
            self.last_wake_at = t_endpoint
        self.state = self.IDLE
        self.on_event("captured", {"via": via, "audio_s": len(pcm) / SAMPLE_RATE})
        spec = cap.get("spec")
        ready = spec[1] if spec and spec[0] == last_voiced and not forced else None
        self.stt_pool.submit(self._transcribe, pcm, cap, t_speech_end, t_endpoint, ready)

    # ------------------------------------------------------------------ STT thread
    def _transcribe(self, pcm: np.ndarray, cap: dict, t_speech_end: float, t_endpoint: float,
                    ready=None) -> None:
        try:
            tr = ready.result() if ready is not None else self.stt.transcribe(pcm)
        except Exception:  # noqa: BLE001
            log.exception("transcription failed")
            self.on_event("not_understood", {"via": cap["via"]})
            return
        t_done = self.clock()
        self._debug_save(pcm, tr.text)
        prompt = getattr(self.stt, "prompt", None)
        text = tr.text.strip()
        usable = tr.usable and not (prompt and _norm(text) == _norm(prompt))
        heard = Heard(text="", via=cap["via"], wake=cap.get("wake"), mode=cap.get("mode"),
                      t_speech_end=t_speech_end, t_endpoint=t_endpoint, t_stt_done=t_done,
                      stt_ms=tr.ms, audio_s=tr.audio_s)
        log.info("heard (%s, %.0f ms stt, vosk conf %.2f): %r", cap["via"], tr.ms, cap.get("conf", 0), text)

        if cap["via"] == "wake":
            m = self.matcher.match(text) if usable else None
            conf = cap.get("conf", 0.0)
            vosk_sure = conf >= self.strong_conf and cap.get("edge", False)
            vosk_doubts = cap.get("final_seen", False) and conf < self.min_conf
            if m is not None and vosk_doubts and m.score < 90:
                m = None                           # Whisper's match is weak and Vosk heard something else
            if m is None and not vosk_sure:
                self.on_event("wake_rejected", {"wake": cap.get("wake"), "text_len": len(text)})
                return
            if m is not None:
                heard.wake, heard.mode = m.wake_word, m.mode
                if cap.get("mode") and m.mode != cap["mode"]:
                    # Whisper and Vosk disagree on WHO was called ("Spike!" heard as "Spicy!"):
                    # Vosk only knows the names, so trust it - a wrong mode switch is worse
                    heard.wake, heard.mode = cap["wake"], cap["mode"]
                request = m.rest
            else:
                request = text
            if not request or not re.search(r"[A-Za-z]", request):
                self.on_event("wake_only", {"wake": heard.wake, "mode": heard.mode})
                self.q.put(("listen", ("wake_only", self.listen_timeout_s)))
                return
            heard.text = request
            self.on_event("heard", heard)
            return

        # tap / follow-up / wake_only / alarm: no wake word needed, but strip one if said
        if not usable:
            self.on_event("not_understood", {"via": cap["via"]})
            return
        m = self.matcher.match(text, allow_end=False)
        request = m.rest if (m and m.rest) else text
        if m:
            heard.wake, heard.mode = m.wake_word, m.mode
        if cap["via"] == "follow_up":
            words = _norm(request).split()
            if len(words) < 2 and _norm(request) not in SHORT_ANSWERS:
                self.on_event("not_understood", {"via": "follow_up"})
                return
        heard.text = request
        self.on_event("heard", heard)

    def _debug_save(self, pcm: np.ndarray, text: str) -> None:
        if not self.debug_dir:
            return
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            name = time.strftime("%Y%m%d-%H%M%S") + "_" + re.sub(r"[^a-z0-9]+", "-", text.lower())[:40] + ".wav"
            with wave.open(str(self.debug_dir / name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SAMPLE_RATE)
                w.writeframes(pcm.astype(np.int16).tobytes())
        except OSError:
            log.warning("could not save debug audio")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z' ]", " ", (text or "").lower())).strip()
