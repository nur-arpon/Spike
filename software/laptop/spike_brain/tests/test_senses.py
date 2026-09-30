"""Hearing and seeing logic without a mic or camera: VAD endpointing,
resampling, wake matching, the listener state machine, TTS helpers, face
emotion, presence and rock-paper-scissors."""
import threading
import time

import numpy as np
import pytest

from spike_brain.hearing.audio import Reframer, RemoteSource, StreamResampler
from spike_brain.hearing.listener import Listener
from spike_brain.hearing.stt import Transcript
from spike_brain.hearing.vad import FRAME, EnergyVAD, Endpointer, SileroVAD
from spike_brain.hearing.wake import VoskHit, WakeMatcher
from spike_brain.speech.tts import mouth_envelope, pitch_shift, trim_silence
from spike_brain.vision.signals import (EmotionEstimator, Presence, RpsVote, classify_rps, rps_result)

from .conftest import MODELS


# ---- audio plumbing -------------------------------------------------------------
def test_reframer_emits_fixed_frames():
    got = []
    r = Reframer(got.append)
    for n in (100, 700, 300, 1000):
        r.push(np.ones(n, dtype=np.int16))
    assert [len(f) for f in got] == [FRAME] * 4 and len(r.buf) == 2100 - 4 * FRAME


@pytest.mark.parametrize("src", [48000, 44100, 32000, 22050])
def test_resampler_rate_is_exact_over_time(src):
    rs = StreamResampler(src, 16000)
    total = sum(len(rs(np.zeros(src // 50, dtype=np.int16))) for _ in range(50))   # 1 s in 20 ms blocks
    assert abs(total - 16000) <= 50


def test_resampler_keeps_a_tone():
    rs = StreamResampler(48000, 16000)
    t = np.arange(48000) / 48000
    x = (np.sin(2 * np.pi * 440 * t) * 10000).astype(np.int16)
    y = np.concatenate([rs(x[i:i + 960]) for i in range(0, len(x), 960)])
    spec = np.abs(np.fft.rfft(y[4000:12000].astype(float)))
    peak_hz = np.argmax(spec) * 16000 / 8000
    assert abs(peak_hz - 440) < 5


def test_remote_source_counts_lost_chunks():
    got = []
    src = RemoteSource()
    src.start(got.append)
    src.push(b"\x00\x00" * 512, 16000, seq=1)
    src.push(b"\x00\x00" * 512, 16000, seq=4)
    assert len(got) == 2 and src.lost == 2


def test_endpointer_start_end_and_blips():
    ep = Endpointer(threshold=0.5, end_silence_ms=320, min_speech_ms=200)
    events = []
    probs = [0.1] * 5 + [0.9] * 20 + [0.1] * 15 + [0.9] * 2 + [0.1] * 15
    for p in probs:
        e = ep.push(p)
        if e:
            events.append((e.kind, e.frame_index))
    assert events[0] == ("start", 5)
    assert events[1] == ("end", 24)            # last voiced frame
    assert ("blip", 41) in events or all(k != "start" for k, _ in events[2:])


def test_energy_vad_separates_speech_from_silence():
    vad = EnergyVAD()
    rng = np.random.default_rng(0)
    quiet = [vad((rng.normal(0, 30, FRAME)).astype(np.int16)) for _ in range(60)]
    loud = [vad((rng.normal(0, 3000, FRAME)).astype(np.int16)) for _ in range(5)]
    assert max(quiet[-10:]) < 0.5 < min(loud)


@pytest.mark.skipif(not (MODELS / "openwakeword" / "silero_vad.onnx").exists(), reason="no silero model")
def test_silero_vad_on_silence_and_noise():
    vad = SileroVAD(MODELS / "openwakeword" / "silero_vad.onnx")
    p = [vad(np.zeros(FRAME, dtype=np.int16)) for _ in range(10)]
    assert max(p) < 0.3


# ---- TTS helpers -----------------------------------------------------------------
def test_pitch_shift_and_mouth():
    rate = 22050
    t = np.arange(rate) / rate
    pcm = (np.sin(2 * np.pi * 200 * t) * 9000).astype(np.int16)
    up = pitch_shift(pcm, 1.1)
    assert abs(len(up) - len(pcm) / 1.1) < 5
    mouth = mouth_envelope(np.concatenate([np.zeros(rate // 2, np.int16), pcm]), rate)
    assert len(mouth) == 75 and max(mouth[:20]) == 0 and max(mouth[30:70]) > 60 and mouth[-1] == 0
    trimmed = trim_silence(np.concatenate([np.zeros(rate, np.int16), pcm, np.zeros(rate, np.int16)]), rate)
    assert len(pcm) < len(trimmed) < len(pcm) + rate * 0.25


# ---- vision ------------------------------------------------------------------------
def test_presence_arrive_and_leave():
    p = Presence(present_after_s=1.0, absent_after_s=5.0)
    ev = [p.update(True, t / 10) for t in range(0, 15)]
    arrived = [e for e in ev if e]
    assert len(arrived) == 1 and arrived[0].kind == "arrived" and arrived[0].away_s == float("inf")
    ev = [p.update(False, 1.5 + t / 10) for t in range(0, 60)]
    assert [e.kind for e in ev if e] == ["left"]
    later = [p.update(True, 20 + t / 10) for t in range(0, 15)]
    back = [e for e in later if e][0]
    assert back.kind == "arrived" and abs(back.away_s - 18.6) < 0.01   # last seen 1.4 s, back at 20 s


def test_brief_glimpses_do_not_count_as_arriving():
    p = Presence(present_after_s=1.0)
    for i in range(30):
        assert p.update(i % 4 == 0, i / 10) is None       # seen only every 0.4 s


def feed(est, bs, seconds, t0=0.0, fps=8):
    label = None
    for i in range(int(seconds * fps)):
        r = est.update(bs, t0 + i / fps)
        label = r or label
    return label


NEUTRAL = {"mouthSmileLeft": 0.05, "mouthSmileRight": 0.05, "mouthFrownLeft": 0.05, "mouthFrownRight": 0.05,
           "browInnerUp": 0.05, "eyeBlinkLeft": 0.1, "eyeBlinkRight": 0.1, "jawOpen": 0.02}


def test_emotion_happy_sad_tired_with_hold():
    est = EmotionEstimator(window_s=3, hold_s=2)
    assert feed(est, NEUTRAL, 20) is None and est.label == "neutral"
    happy = {**NEUTRAL, "mouthSmileLeft": 0.8, "mouthSmileRight": 0.8, "eyeSquintLeft": 0.4, "eyeSquintRight": 0.4}
    assert feed(est, happy, 1, t0=20) is None               # a quick smile is not a mood
    assert feed(est, happy, 15, t0=21) == "happy"
    sad = {**NEUTRAL, "mouthSmileLeft": 0.0, "mouthSmileRight": 0.0, "mouthFrownLeft": 0.55,
           "mouthFrownRight": 0.55, "browInnerUp": 0.6}
    assert feed(est, sad, 25, t0=40) == "sad"
    tired = {**NEUTRAL, "eyeBlinkLeft": 0.75, "eyeBlinkRight": 0.75}
    assert feed(est, tired, 30, t0=70) == "tired"


def test_emotion_is_relative_to_the_owners_resting_face():
    """Someone whose resting mouth turns down should not read as sad."""
    resting = {**NEUTRAL, "mouthFrownLeft": 0.35, "mouthFrownRight": 0.35, "browInnerUp": 0.3}
    est = EmotionEstimator(window_s=3, hold_s=2, baseline_s=5)
    assert feed(est, resting, 60) is None and est.label == "neutral"


def hand(extended: tuple[bool, bool, bool, bool]):
    """21 landmarks of a hand pointing up; each finger extended or curled."""
    lm = [(0.5, 0.9)] + [(0.45, 0.8)] * 4
    for f, ext in enumerate(extended):
        x = 0.4 + f * 0.05
        lm += [(x, 0.7), (x, 0.6), (x, 0.5 if ext else 0.66), (x, 0.4 if ext else 0.7)]
    return lm


@pytest.mark.parametrize("fingers,expect", [((False,) * 4, "rock"), ((True,) * 4, "paper"),
                                            ((True, True, False, False), "scissors"),
                                            ((True, True, True, False), "paper"), ((True, False, False, False), None)])
def test_rps_from_landmarks(fingers, expect):
    assert classify_rps(None, 0.0, hand(fingers)) == expect


def test_rps_gesture_names_win_and_vote():
    assert classify_rps("Victory", 0.9, None) == "scissors"
    assert classify_rps("Victory", 0.2, hand((False,) * 4)) == "rock"
    v = RpsVote()
    for c in ["rock", "rock", None, "paper", "rock"]:
        v.add(c)
    assert v.result() == "rock" and RpsVote().result() is None
    assert rps_result("rock", "scissors") == "win" and rps_result("rock", "paper") == "lose"
    assert rps_result("paper", "paper") == "draw"


# ---- listener state machine (fake VAD / spotter / Whisper) -----------------------
class FakeVAD:
    def reset(self):
        pass

    def __call__(self, frame):
        return 0.95 if np.abs(frame).mean() > 100 else 0.02


class FakeSpotter:
    """Reports a partial wake hit at a chosen frame."""

    def __init__(self, hit_at: int | None, before: int = 0, after: int = 3):
        self.hit_at, self.n, self.before, self.after = hit_at, -1, before, after

    def reset(self):
        pass

    def feed(self, b):
        self.n += 1
        if self.hit_at is not None and self.n == self.hit_at:
            return VoskHit("spike", "Spike", "dog", 0.0, 0, 0, False, 0)
        if self.hit_at is not None and self.n == self.hit_at + 10:
            return VoskHit("spike", "Spike", "dog", 0.97, 0, 0, True, self.after, self.before)
        return None


class FakeWhisper:
    prompt = None

    def __init__(self, text):
        self.text = text
        self.calls = 0

    def transcribe(self, pcm):
        self.calls += 1
        return Transcript(self.text, 0.01, -0.2, len(pcm) / 16000, 5.0)


MATCHER = WakeMatcher({"dog": {"Spike": ["spike"]}, "cat": {"Spicy": ["spicy"]}}, 80, {"spicy"})


def run_listener(text, hit_at, frames, wake_touch=False, mute_at=None, before=0):
    events = []
    done = threading.Event()

    def on_event(kind, data):
        events.append((kind, data))
        if kind in ("heard", "wake_rejected", "not_understood", "listen_timeout", "wake_only"):
            done.set()

    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=FakeWhisper(text), spotter=FakeSpotter(hit_at, before),
                   on_event=on_event, end_silence_ms=320, listen_timeout_s=1.0)
    lst.start()
    if wake_touch:
        lst.wake_by_touch("tap")
    for i, loud in enumerate(frames):
        if mute_at is not None and i == mute_at:
            lst.set_muted(True)
        lst.feed((np.ones(FRAME) * (3000 if loud else 0)).astype(np.int16))
    done.wait(3)
    time.sleep(0.05)
    lst.stop()
    return events


SPEECH = [False] * 10 + [True] * 40 + [False] * 20


def test_wake_word_then_request_in_one_breath():
    ev = run_listener("Spike, what time is it?", hit_at=15, frames=SPEECH)
    kinds = [k for k, _ in ev]
    assert kinds[0] == "wake_candidate" and "captured" in kinds
    heard = dict(ev)["heard"]
    assert heard.text == "what time is it" and heard.wake == "Spike" and heard.via == "wake"
    assert heard.t_speech_end <= heard.t_endpoint <= heard.t_stt_done


def test_false_wake_is_rejected():
    ev = run_listener("the spike in prices was huge", hit_at=15, frames=SPEECH, before=1)
    assert ("wake_rejected" in [k for k, _ in ev]) and "heard" not in [k for k, _ in ev]


def test_head_tap_listens_without_a_wake_word():
    ev = run_listener("tell me a joke", hit_at=None, frames=SPEECH, wake_touch=True)
    heard = dict(ev)["heard"]
    assert heard.text == "tell me a joke" and heard.via == "tap"


def test_tap_with_silence_times_out():
    ev = run_listener("", hit_at=None, frames=[False] * 10, wake_touch=True)
    assert [k for k, _ in ev][-1] == "listen_timeout"


def test_muted_mic_hears_nothing():
    ev = run_listener("Spike, hello", hit_at=15, frames=SPEECH, mute_at=0)
    assert ev == []


def test_vosk_alone_can_confirm_a_misheard_name():
    # Whisper wrote "Sparky" for "Spike", but Vosk was sure and the name opened the sentence
    ev = run_listener("Sparky what time is it", hit_at=15, frames=SPEECH, before=0)
    assert dict(ev)["heard"].text == "Sparky what time is it"


def test_wake_word_alone_opens_listening():
    ev = run_listener("Spike.", hit_at=15, frames=SPEECH)
    assert "wake_only" in [k for k, _ in ev]


def test_whisper_starts_early_and_its_result_is_reused():
    """Speculative STT: one transcription when the silence simply continues..."""
    events, done = [], threading.Event()
    whisper = FakeWhisper("Spike, how are you?")
    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=whisper, spotter=FakeSpotter(15),
                   on_event=lambda k, d: (events.append((k, d)), k == "heard" and done.set()),
                   end_silence_ms=448, listen_timeout_s=1.0)
    lst.start()
    for loud in SPEECH:
        lst.feed((np.ones(FRAME) * (3000 if loud else 0)).astype(np.int16))
    done.wait(3)
    lst.stop()
    assert whisper.calls == 1 and dict(events)["heard"].text == "how are you"


def test_speculation_is_dropped_when_the_owner_keeps_talking():
    """...and a fresh one when they pause (longer than the speculation point) and carry on."""
    events, done = [], threading.Event()
    whisper = FakeWhisper("Spike, tell me a story.")
    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=whisper, spotter=FakeSpotter(15),
                   on_event=lambda k, d: (events.append((k, d)), k == "heard" and done.set()),
                   end_silence_ms=448, listen_timeout_s=1.0)
    lst.start()
    frames = [False] * 10 + [True] * 25 + [False] * 9 + [True] * 20 + [False] * 25
    for loud in frames:
        lst.feed((np.ones(FRAME) * (3000 if loud else 0)).astype(np.int16))
    done.wait(3)
    lst.stop()
    heard = dict(events)["heard"]
    assert whisper.calls == 2 and heard.audio_s > 1.4          # the whole request, both halves


def test_capture_is_right_after_a_mute():
    """Frame numbering survives the endpointer resetting on unmute (regression)."""
    events, done = [], threading.Event()
    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=FakeWhisper("Spike, hi there."),
                   spotter=FakeSpotter(80), on_event=lambda k, d: (events.append((k, d)),   # 35 frames were muted
                                                                   k == "heard" and done.set()),
                   end_silence_ms=320)
    lst.start()
    frames = [False] * 30 + [True] * 20 + [False] * 50 + [False] * 10 + [True] * 30 + [False] * 20
    for i, loud in enumerate(frames):
        if i == 55:
            lst.set_muted(True)
        if i == 90:
            lst.set_muted(False)
        lst.feed((np.ones(FRAME) * (3000 if loud else 0)).astype(np.int16))
    done.wait(3)
    lst.stop()
    heard = dict(events)["heard"]
    assert 0.9 < heard.audio_s < 1.6, heard.audio_s         # 30 voiced frames + preroll, not 5 s of history


def test_app_end_silence_keeps_a_pause_inside_one_request():
    """PROTOCOL.md 6.7 end_silence_ms: a thinking gap shorter than the owner's wait does not
    end the request; the whole of it is heard as one."""
    events, done = [], threading.Event()
    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=FakeWhisper("tell me about the moon"),
                   spotter=None, on_event=lambda k, d: (events.append((k, d)), k == "heard" and done.set()),
                   end_silence_ms=320, listen_timeout_s=5.0)
    lst.start()
    lst.set_end_silence(1500)
    lst.wake_by_touch("tap")
    frames = [False] * 10 + [True] * 20 + [False] * 20 + [True] * 20 + [False] * 60   # a 0.64 s gap
    for loud in frames:
        lst.feed((np.ones(FRAME) * (3000 if loud else 0)).astype(np.int16))
    done.wait(3)
    lst.stop()
    heard = [d for k, d in events if k == "heard"]
    assert len(heard) == 1 and heard[0].audio_s > 1.8, heard       # both halves and the gap


def test_default_end_silence_splits_at_the_same_pause():
    events, done = [], threading.Event()
    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=FakeWhisper("tell me"),
                   spotter=None, on_event=lambda k, d: (events.append((k, d)), k == "heard" and done.set()),
                   end_silence_ms=320, listen_timeout_s=5.0)
    lst.start()
    lst.wake_by_touch("tap")
    for loud in [False] * 10 + [True] * 20 + [False] * 20 + [True] * 20 + [False] * 60:
        lst.feed((np.ones(FRAME) * (3000 if loud else 0)).astype(np.int16))
    done.wait(3)
    lst.stop()
    heard = [d for k, d in events if k == "heard"]
    assert heard and heard[0].audio_s < 1.4                         # only the first half

def test_keepalive_extends_listening_silently():
    events = []
    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=FakeWhisper("x"), spotter=None,
                   on_event=lambda k, d: events.append(k), end_silence_ms=320, listen_timeout_s=0.6)
    lst.start()
    lst.wake_by_touch("tap")
    for _ in range(5):                                   # 5 x 0.25 s > the 0.6 s window, kept open
        time.sleep(0.25)
        lst.keep_listening()
    time.sleep(0.05)
    assert lst.state == lst.LISTEN and events == ["listening"]     # only the tap's own event, nothing from keeps
    time.sleep(0.9)                                      # keepalives stop -> the window times out as before
    lst.stop()
    assert events == ["listening", "listen_timeout"]


def test_keepalive_does_not_open_an_idle_listener():
    events = []
    lst = Listener(vad=FakeVAD(), matcher=MATCHER, transcriber=FakeWhisper("x"), spotter=None,
                   on_event=lambda k, d: events.append(k), end_silence_ms=320, listen_timeout_s=0.6)
    lst.start()
    lst.keep_listening()
    time.sleep(0.2)
    lst.stop()
    assert lst.state == lst.IDLE and events == []
