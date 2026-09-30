"""The voice chain (speech/engines.py, voices.py, turbo.py): engine selection, the
fallback order, the clip cache, Turbo tags, and the worker supervisor (with a
fake worker: no GPU, no torch)."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from spike_brain.speech import engines as E
from spike_brain.speech.engines import (ClipCache, OwnerRecordings, TurboStyle, VoiceChain, cache_key, level,
                                        turbo_text, write_wav)
from spike_brain.speech.turbo import TurboConfig, TurboUnavailable, TurboWorker
from spike_brain.speech.voices import plan_turbo

FAKE_WORKER = Path(__file__).resolve().with_name("fake_turbo_worker.py")
SPIKE_STYLE = TurboStyle(style={"happy": "happy", "excited": "happy", "smugness": "sarcastic"},
                         sounds={"laughing": "laugh", "sulking": "sigh"})


def tone(seconds=0.5, rate=24000, amp=6000):
    t = np.arange(int(rate * seconds)) / rate
    return (np.sin(2 * np.pi * 220 * t) * amp).astype(np.int16)


# ------------------------------------------------------------------ fakes
class FakeTurbo:
    def __init__(self, ready=True, fail=False, delay=0.0):
        self.ready, self.fail, self.delay = ready, fail, delay
        self.calls = []

    def synthesize(self, voice, text, seed=1234, timeout=None):
        self.calls.append((voice, text, seed))
        if self.fail:
            raise TurboUnavailable("boom")
        time.sleep(self.delay)
        return tone(), 24000, 5.0


class FakeEngine:
    """Stands in for KokoroEngine / PiperEngine."""
    def __init__(self, rate=24000, fail=False):
        self.rate, self.fail, self.calls = rate, fail, []

    def synthesize(self, text, *args):
        self.calls.append((text, args))
        if self.fail:
            raise RuntimeError("engine down")
        return tone(rate=self.rate), self.rate


def chain(**kw) -> VoiceChain:
    kw.setdefault("style", SPIKE_STYLE)
    return VoiceChain("spike", **kw)


# ------------------------------------------------------------------ Turbo text
def test_style_tag_comes_from_the_mood():
    assert turbo_text("You're home!", "excited", SPIKE_STYLE) == "[happy] You're home!"
    assert turbo_text("Of course I won.", "smugness", SPIKE_STYLE) == "[sarcastic] Of course I won."
    assert turbo_text("Hmm, okay.", "curious", SPIKE_STYLE) == "Hmm, okay."          # no tag for this mood
    assert turbo_text("Hello.", None, SPIKE_STYLE) == "Hello."


def test_one_sound_per_reply_placed_after_the_first_sentence():
    assert turbo_text("I meant to do that.", "laughing", SPIKE_STYLE) == "[laugh] I meant to do that."
    assert turbo_text("Tiny legs, big fall. I'm okay!", "laughing", SPIKE_STYLE) == \
        "Tiny legs, big fall. [laugh] I'm okay!"
    # later sentences of the same reply never get another sound
    assert turbo_text("And another thing.", "laughing", SPIKE_STYLE, first=False) == "And another thing."


def test_a_low_owner_gets_the_plain_voice():
    assert turbo_text("I'm right here with you.", "excited", SPIKE_STYLE, soft=True) == "I'm right here with you."
    assert turbo_text("Oh no.", "laughing", SPIKE_STYLE, soft=True) == "Oh no."


def test_no_typed_fillers_are_ever_added():
    for mood in ("excited", "laughing", "smugness", "sulking", "curious"):
        out = turbo_text("Okay then.", mood, SPIKE_STYLE).lower()
        assert "umm" not in out and " um " not in f" {out} " and "like," not in out


def test_unknown_turbo_tags_are_rejected():
    with pytest.raises(ValueError):
        TurboStyle.from_config({"style": {"giggly": ["happy"]}})
    with pytest.raises(ValueError):
        TurboStyle.from_config({"sounds": {"laughing": "haha"}})


def test_persona_files_map_moods_to_real_turbo_tags(settings):
    from spike_brain.protocol import MOODS
    for p in settings.personas.values():
        st = TurboStyle.from_config(p.voice_cfg["turbo"])        # raises on a tag Turbo does not have
        assert set(st.style) <= set(MOODS) and set(st.sounds) <= set(MOODS)
        assert Path(settings.path(p.voice_cfg["turbo"]["reference"])).name.endswith("_ref.wav")
    assert settings.personas["cat"].voice_cfg["turbo"]["style"]["sarcastic"]      # Spicy C: sarcastic tag
    assert settings.personas["dog"].voice_cfg["turbo"]["style"]["happy"]          # Spike B: style tags


# ------------------------------------------------------------------ level
def test_levelling_matches_loudness_without_trimming():
    quiet, loud = tone(amp=800), tone(amp=20000)
    a, b = level(quiet, 24000), level(loud, 24000)
    assert len(a) == len(quiet) and len(b) == len(loud)          # nothing cut
    ra = 20 * np.log10(np.sqrt(np.mean((a / 32768.0) ** 2)))
    rb = 20 * np.log10(np.sqrt(np.mean((b / 32768.0) ** 2)))
    assert abs(ra - rb) < 1.0
    assert np.abs(b).max() <= 0.9 * 32768


# ------------------------------------------------------------------ engine selection and fallback
def test_live_turbo_is_used_when_ready():
    t = FakeTurbo()
    sp = chain(turbo=t, kokoro=FakeEngine(), piper=FakeEngine(22050)).synthesize("You're home!", mood="excited")
    assert sp.engine == "turbo" and sp.rate == 24000
    assert t.calls == [("spike", "[happy] You're home!", 1234)]


def test_turbo_failure_falls_back_to_kokoro_then_piper():
    k, p = FakeEngine(), FakeEngine(22050)
    c = chain(turbo=FakeTurbo(fail=True), kokoro=k, piper=p)
    assert c.synthesize("Hello there.").engine == "kokoro"
    c2 = chain(turbo=FakeTurbo(fail=True), kokoro=FakeEngine(fail=True), piper=p)
    sp = c2.synthesize("Hello there.")
    assert sp.engine == "piper" and sp.rate == 24000              # Piper's 22.05 kHz brought to 24 kHz


def test_turbo_is_skipped_for_a_while_after_a_failure():
    t = FakeTurbo(fail=True)
    c = chain(turbo=t, kokoro=FakeEngine(), turbo_backoff_s=30)
    c.synthesize("One.")
    c.synthesize("Two.")
    assert len(t.calls) == 1                                    # the second line did not wait on a broken Turbo


def test_turbo_not_ready_yet_uses_the_backup_without_waiting():
    t = FakeTurbo(ready=False)
    sp = chain(turbo=t, kokoro=FakeEngine()).synthesize("Hi.")
    assert sp.engine == "kokoro" and t.calls == []


def test_never_silent_until_every_engine_failed():
    c = chain(turbo=FakeTurbo(fail=True), kokoro=FakeEngine(fail=True), piper=FakeEngine(fail=True))
    assert c.synthesize("Hello.") is None                     # then the speech output shows the words only


def test_engine_setting_kokoro_and_piper():
    t = FakeTurbo()
    c = chain(engine="kokoro", turbo=t, kokoro=FakeEngine(), piper=FakeEngine())
    assert c.order() == ["owner", "kokoro", "piper"] and c.synthesize("Hi.").engine == "kokoro"
    assert t.calls == []
    c = chain(engine="piper", turbo=t, kokoro=FakeEngine(), piper=FakeEngine(22050))
    assert c.synthesize("Hi.").engine == "piper"
    with pytest.raises(ValueError):
        chain(engine="espeak")


def test_a_reply_keeps_one_voice_after_a_fallback():
    t = FakeTurbo(fail=True)
    c = chain(turbo=t, kokoro=FakeEngine(), turbo_backoff_s=0)
    assert c.synthesize("First.", utt="u1", first=True).engine == "kokoro"
    t.fail = False
    assert c.synthesize("Second.", utt="u1", first=False).engine == "kokoro"   # same reply: same voice
    assert c.synthesize("New reply.", utt="u2", first=True).engine == "turbo"


# ------------------------------------------------------------------ cache and owner recordings
def _make_cache(folder: Path, persona: str, spoken: str, ref_sha: str = "abc") -> None:
    key = cache_key(persona, spoken)
    write_wav(folder / persona / "x.wav", tone(1.0), 24000)
    (folder / "manifest.json").write_text(json.dumps({
        "version": 1, "voices": {persona: {"ref_sha1": ref_sha}},
        "entries": {key: {"persona": persona, "file": f"{persona}/x.wav", "spoken": spoken}}}), encoding="utf-8")


def test_cached_clip_wins_over_live_turbo(tmp_path):
    _make_cache(tmp_path, "spike", "[happy] Wakey wakey!")
    t = FakeTurbo()
    c = chain(turbo=t, cache=ClipCache(tmp_path, {"spike": "abc"}), kokoro=FakeEngine())
    sp = c.synthesize("Wakey wakey!", mood="excited")
    assert sp.engine == "cache" and t.calls == []
    assert chain(turbo=t, cache=ClipCache(tmp_path), kokoro=FakeEngine()).synthesize(
        "Something new.", mood="excited").engine == "turbo"      # not cached -> live


def test_cache_key_includes_the_tags():
    assert cache_key("spike", "[happy] Hi.") != cache_key("spike", "Hi.")
    assert cache_key("spike", "Hi.") != cache_key("spicy", "Hi.")
    assert cache_key("spike", "Hi.  ") == cache_key("spike", "Hi.")


def test_cache_made_with_another_reference_clip_is_ignored(tmp_path):
    _make_cache(tmp_path, "spike", "Hi.", ref_sha="old")
    assert len(ClipCache(tmp_path, {"spike": "new"})) == 0
    assert len(ClipCache(tmp_path, {"spike": "old"})) == 1


def test_missing_or_broken_cache_is_harmless(tmp_path):
    assert len(ClipCache(tmp_path / "nothing")) == 0
    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    assert len(ClipCache(tmp_path)) == 0


def test_owner_recording_by_line_id_beats_everything(tmp_path):
    rec = OwnerRecordings(tmp_path)
    write_wav(rec.path("spike", "alarm.2"), tone(0.8, 16000), 16000)
    _make_cache(tmp_path / "cache", "spike", "Hellooo!")
    c = chain(recordings=rec, cache=ClipCache(tmp_path / "cache"), turbo=FakeTurbo(), kokoro=FakeEngine())
    sp = c.synthesize("Hellooo!", line_id="alarm.2")
    assert sp.engine == "owner" and sp.rate == 24000
    assert c.synthesize("Hellooo!", line_id="alarm.1").engine == "cache"     # no recording for that line


# ------------------------------------------------------------------ graphics memory plan
def test_turbo_plan_picks_the_lighter_setting_when_memory_is_short():
    assert plan_turbo("auto", "auto", 5000, 3600, 2700).dtype == "fp32"
    assert plan_turbo("auto", "auto", 3000, 3600, 2700).dtype == "bf16"
    assert plan_turbo("auto", "auto", 3500, 3600, 2700, reserve_mib=600).dtype == "bf16"
    p = plan_turbo("auto", "auto", 1500, 3600, 2700)
    assert p.device == "cuda" and p.dtype == "bf16" and "overcommitted" in p.reason
    assert plan_turbo("auto", "auto", None, 3600, 2700).device is None         # no NVIDIA card: cache + Kokoro
    assert plan_turbo("off", "auto", 9000, 3600, 2700).device is None
    assert plan_turbo("auto", "fp32", 1000, 3600, 2700).dtype == "fp32"         # the owner's explicit choice wins


def test_on_demand_language_model_is_planned_as_if_loaded():
    from spike_brain.speech.voices import llm_reserve_mib
    # always loaded: the model is already on the card when the voice plans, nothing extra kept
    assert llm_reserve_mib(on_demand=False, loaded=False, llm_mib=5200) == 0
    assert llm_reserve_mib(on_demand=True, loaded=True, llm_mib=5200) == 0
    # on demand and not loaded yet: keep its measured footprint
    kept = llm_reserve_mib(on_demand=True, loaded=False, llm_mib=5200)
    assert kept == 5200
    assert llm_reserve_mib(on_demand=True, loaded=False, llm_mib=-1) == 0
    # the 8 GB card with the model not loaded (7.3 GB free): fp32 would fit now, but on demand
    # the voice must pick bf16, exactly as in the always-loaded mode (2.1 GB free after the model)
    assert plan_turbo("auto", "auto", 7300, 3600, 2700).dtype == "fp32"
    p = plan_turbo("auto", "auto", 7300, 3600, 2700, reserve_mib=kept)
    assert p.device == "cuda" and p.dtype == "bf16" and "5200 MiB kept" in p.reason
    assert p.dtype == plan_turbo("auto", "auto", 7300 - 5200, 3600, 2700).dtype
    # a card big enough for both still gets fp32
    assert plan_turbo("auto", "auto", 11000, 3600, 2700, reserve_mib=kept).dtype == "fp32"
    # the owner's explicit setting still wins
    assert plan_turbo("auto", "fp32", 7300, 3600, 2700, reserve_mib=kept).dtype == "fp32"


def test_memory_left_after_the_voice_counts_the_on_demand_model():
    """brain._stt_device puts Whisper on the card only if room is left: the on-demand model
    must count, or Whisper would take its place while it sleeps."""
    from spike_brain.speech.voices import TurboPlan
    p = TurboPlan("cuda", "bf16", "", free_mib=7300, need_mib=2700)
    assert p.left_mib() == 4600
    p.llm_mib = 5200
    assert p.left_mib() == -600
    assert TurboPlan(None, "fp32", "", free_mib=None).left_mib() is None


def test_brain_keeps_room_for_the_on_demand_model(monkeypatch, tmp_path):
    """brain._load_voices passes the model's footprint to the voice plan only when on demand."""
    from spike_brain import brain as B
    from spike_brain.speech import voices as V
    seen = {}

    def fake_build(settings, **kw):
        seen.update(kw)
        return V.VoiceSet()

    monkeypatch.setattr(V, "build_voices", fake_build)
    from spike_brain.config import Settings
    s = Settings.load().override({"stt": {"device": "auto"}, "tts": {"turbo": {"reserve_llm_mib": 5100}}})

    class Fake:
        pass
    for on_demand, loaded, want in ((True, False, 5100), (True, True, 0), (False, False, 0)):
        b = Fake()
        b.s, b.voices, b.voice_set = s, {}, None
        b.opts = B.RunOptions(llm_on_demand=on_demand)
        b.local_llm = object() if loaded else None
        seen.clear()
        B.Brain._load_voices(b)
        assert seen["llm_mib"] == want and seen["reserve_mib"] == 0


def test_voice_says_helpline_numbers_as_words_but_captions_keep_digits():
    from spike_brain.speech.engines import say_as
    t = {"000": "triple zero"}
    assert say_as("If you're in danger, call 000.", t) == "If you're in danger, call triple zero."
    assert say_as("It costs 10000 dollars.", t) == "It costs 10000 dollars."
    turbo = FakeTurbo()
    c = chain(turbo=turbo, kokoro=FakeEngine(), say_as_table=t)
    sp = c.synthesize("Please call 000 right now.", soft=True)
    assert turbo.calls[0][1] == "Please call triple zero right now." and sp.text == "Please call 000 right now."


def test_settings_say_as_for_australia(settings):
    assert settings.say_as().get("000") == "triple zero"
