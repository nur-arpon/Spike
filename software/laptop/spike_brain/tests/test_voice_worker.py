"""Turbo worker supervision (with a fake worker process), the speech output's
hints to the voice chain, scripted line ids, and the cache builder's rules."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from spike_brain.speech.engines import VoiceChain, TurboStyle, write_wav
from spike_brain.speech.output import SpeechOut
from spike_brain.speech.turbo import TurboConfig, TurboUnavailable, TurboWorker, _pid_alive

FAKE_WORKER = Path(__file__).resolve().with_name("fake_turbo_worker.py")


def fake_worker(tmp_path: Path, monkeypatch, **env) -> TurboWorker:
    models = tmp_path / "models"
    models.mkdir(exist_ok=True)
    (models / "t3_turbo_v1.safetensors").write_bytes(b"x")
    ref = tmp_path / "ref.wav"
    write_wav(ref, np.zeros(24000, np.int16), 24000)
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    return TurboWorker(TurboConfig(python=Path(sys.executable), models=models, voices={"spike": ref},
                                   script=FAKE_WORKER, health_interval_s=0.3, start_timeout_s=20,
                                   synth_timeout_s=2.0, max_restarts=2, restart_window_s=60))


def test_worker_starts_answers_and_stops(tmp_path, monkeypatch):
    w = fake_worker(tmp_path, monkeypatch)
    try:
        w.start(wait=True)
        assert w.ready
        pcm, rate, gen_ms = w.synthesize("spike", "Hello.")
        assert rate == 24000 and len(pcm) == 12000
        with pytest.raises(TurboUnavailable):
            w.synthesize("nobody", "Hello.")                      # unknown voice -> fall back, never crash
        pid = w.proc.pid
    finally:
        w.stop()
    assert w.state == "stopped" and w.proc is None
    time.sleep(0.3)
    assert not _pid_alive(pid)


def test_worker_rejects_requests_without_the_token(tmp_path, monkeypatch):
    import urllib.error
    import urllib.request
    w = fake_worker(tmp_path, monkeypatch)
    try:
        w.start(wait=True)
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"http://127.0.0.1:{w.port}/health", timeout=3)
        assert e.value.code == 403
    finally:
        w.stop()


def test_a_crashed_worker_is_restarted(tmp_path, monkeypatch):
    w = fake_worker(tmp_path, monkeypatch, FAKE_TURBO_EXIT_AFTER=1)
    try:
        w.start(wait=True)
        first_pid = w.proc.pid
        w.synthesize("spike", "One.")
        with pytest.raises(TurboUnavailable):
            w.synthesize("spike", "Two.")                         # the worker dies mid-request
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not (w.ready and w.proc and w.proc.pid != first_pid):
            time.sleep(0.2)
        assert w.ready and w.proc.pid != first_pid                # restarted with backoff
        w.synthesize("spike", "Three.")
    finally:
        w.stop()


def test_a_hung_request_times_out(tmp_path, monkeypatch):
    w = fake_worker(tmp_path, monkeypatch, FAKE_TURBO_HANG=1)
    try:
        w.start(wait=True)
        t = time.perf_counter()
        with pytest.raises(TurboUnavailable):
            w.synthesize("spike", "Hello.", timeout=0.5)
        assert time.perf_counter() - t < 2.0
    finally:
        w.stop()


def test_missing_files_mean_no_worker(tmp_path):
    w = TurboWorker(TurboConfig(python=tmp_path / "nope.exe", models=tmp_path, voices={}))
    w.start()
    assert w.state == "failed" and w.proc is None and "Python" in w.last_error


# ------------------------------------------------------------------ speech output -> chain hints
class RecordingChain:
    wants_hints = True
    rate = 24000

    def __init__(self):
        self.calls = []

    def synthesize(self, text, soft=False, mood=None, line_id=None, first=True, utt=None):
        from spike_brain.speech.tts import Speech, mouth_envelope
        self.calls.append(dict(text=text, soft=soft, mood=mood, line_id=line_id, first=first, utt=utt))
        pcm = np.zeros(2400, np.int16)
        sp = Speech(text, pcm, 24000, mouth_envelope(pcm, 24000))
        sp.engine = "turbo"
        return sp


async def test_speech_output_passes_mood_line_id_and_first_segment():
    ch = RecordingChain()
    out = SpeechOut(None, {"dog": ch}, output="robot", report_timeout_s=0.1)
    utt = out.begin("dog")
    await out.segment(utt, "You're home!", mood=None, voice_mood="excited")
    await out.segment(utt, "Tell me everything.", mood=None, voice_mood="excited")
    await out.segment(utt, "", final=True)
    assert [c["first"] for c in ch.calls] == [True, False]
    assert ch.calls[0]["mood"] == "excited" and ch.calls[0]["utt"] == utt.id
    assert utt.engines == ["turbo", "turbo"]
    utt2 = out.begin("dog")
    await out.segment(utt2, "Wakey wakey!", mood="wakeupAlarm", final=True, line_id="alarm.0")
    assert ch.calls[-1]["mood"] == "wakeupAlarm" and ch.calls[-1]["line_id"] == "alarm.0"


async def test_a_voice_exception_shows_the_words_instead_of_ending_the_reply():
    class Broken:
        wants_hints = True
        rate = 24000

        def synthesize(self, *a, **k):
            raise RuntimeError("all voices down")
    out = SpeechOut(None, {"dog": Broken()}, output="robot", report_timeout_s=0.1)
    utt = out.begin("dog")
    await out.segment(utt, "Hello.", final=True)                  # no exception escapes
    assert utt.segments == 1


# ------------------------------------------------------------------ scripted line ids
def test_pick_names_the_line_it_chose(settings):
    import random
    p = settings.personas["dog"]
    rng = random.Random(3)
    line_id, text = p.pick("alarm", rng)
    key, idx = line_id.split(".")
    assert key == "alarm" and p.format_line(p.lines["alarm"][int(idx)]) == text
    assert p.pick("no_such_key")[0].startswith("fallback.")
    # line() is unchanged by the new ids (same random choice for the same seed)
    assert p.line("alarm", random.Random(3)) == p.pick("alarm", random.Random(3))[1]


# ------------------------------------------------------------------ cache builder rules (no GPU)
def test_cache_builder_lists_scripted_lines_and_leaves_changing_ones_live(settings):
    from spike_brain.tools.build_voice_cache import scripted_items
    items, live = scripted_items(settings)
    ids = {(i["persona"], i["line_id"]) for i in items}
    assert ("spike", "greet_morning.0") in ids and ("spicy", "alarm.0") in ids and ("spike", "hungry.1") in ids
    assert any(s.endswith("tell_time.0") for s in live) and any(s.endswith("reminder.0") for s in live)
    crisis = next(i for i in items if i["persona"] == "spike" and i["line_id"] == "crisis.0")
    assert crisis["soft"] and not crisis["spoken"].startswith("[")          # calm voice, no tags
    assert "13 11 14" in crisis["text"]
    assert len({i["key"] for i in items}) == len(items)


def test_cache_builder_screen_rules():
    from spike_brain.tools.build_voice_cache import judge
    it = {"text": "Wakey wakey! The sun is up and so am I!"}
    good = dict(utmos=3.4, wer=0.0, wpm=170, duration_s=3.0, ref_words=10)
    assert judge(it, good)[0]
    assert not judge(it, dict(good, wer=0.4))[0]                            # mumbled words
    assert not judge(it, dict(good, wpm=300))[0]                            # rushed
    assert not judge(it, dict(good, duration_s=30))[0]                      # ran away
    assert not judge(it, dict(good, digits_ok=False))[0]                    # a helpline number misheard
    assert judge(it, dict(good, utmos=3.6))[1] > judge(it, good)[1]         # more natural wins
    short = dict(utmos=3.0, wer=1.0, wpm=None, duration_s=0.6, ref_words=1)
    assert judge({"text": "Mm?"}, short)[0]                                 # one-word lines are not WER-judged
