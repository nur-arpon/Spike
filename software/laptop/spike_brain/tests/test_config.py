"""Settings, personas and their scripted lines."""
import re

import pytest

from spike_brain import protocol as P
from spike_brain.config import DEFAULT_TOML, Settings, deep_merge, load_env
from spike_brain.mind.reply import TAG_RE, normalize_action, normalize_mood

from .conftest import MODELS


def test_defaults_and_personas_load(settings):
    assert settings.server.port == 8765 and settings.server.host == "127.0.0.1"
    assert settings.cloud.enabled is False, "the cloud must be OFF by default"
    dog, cat = settings.personas["dog"], settings.personas["cat"]
    assert (dog.name, cat.name) == ("Spike", "Spicy")
    assert dog.wake_words == ["Spike", "Hey Buddy"] and cat.wake_words == ["Spicy"]
    for p in (dog, cat):
        assert p.voice_file is None or p.voice_file.suffix == ".onnx"
        assert 1.0 <= p.pitch <= 1.25 and 0.9 <= p.speed <= 1.2
        assert p.wake_sound in P.SOUNDS and p.listen_mood in P.MOODS


@pytest.mark.skipif(not (MODELS / "piper" / "spike").exists(), reason="voices not downloaded")
def test_default_voice_is_first_alphabetically(settings):
    assert settings.personas["dog"].voice_file.name == sorted(p.name for p in (MODELS / "piper" / "spike").glob("*.onnx"))[0]
    assert settings.personas["cat"].voice_file.name == sorted(p.name for p in (MODELS / "piper" / "spicy").glob("*.onnx"))[0]


def test_every_scripted_line_uses_real_moods_and_actions(settings):
    for persona in settings.personas.values():
        for key, lines in persona.lines.items():
            for line in lines:
                for kind, val in TAG_RE.findall(line):
                    if kind.lower() == "mood":
                        assert normalize_mood(val) in P.MOODS, f"{persona.id}.{key}: mood {val}"
                    elif kind.lower() == "action":
                        assert normalize_action(val) in P.ACTIONS, f"{persona.id}.{key}: action {val}"


REQUIRED_LINES = ["fallback", "unsafe_replacement", "didnt_catch", "come_home", "greet_morning", "greet_afternoon",
                  "greet_evening", "greet_night", "checkin_quiet", "checkin_sad", "people_nudge", "alarm",
                  "alarm_snoozed", "alarm_stopped", "reminder", "hungry", "weak", "charging", "full", "picked_up",
                  "fell", "mode_to_cat", "mode_to_dog", "remembered", "forgot", "forget_all_confirm",
                  "forget_all_done", "nothing_to_forget", "rps_start", "rps_no_hand", "rps_win", "rps_lose",
                  "rps_draw", "trick_ok", "honest_robot", "crisis", "crisis_followup", "emergency",
                  "alarm_set", "reminder_set", "ask_alarm_time", "ask_reminder_time", "timers_none", "timers_list",
                  "timers_cancelled", "tell_time", "tell_date", "sleep", "forget_all_cancelled"]


def test_both_personas_have_every_line(settings):
    for persona in settings.personas.values():
        missing = [k for k in REQUIRED_LINES if not persona.has_line(k)]
        assert not missing, f"{persona.id} is missing lines: {missing}"


def test_lines_format_with_their_placeholders(settings):
    fmt = {"owner": "Arpon", "when": "at 7 am", "what": "call your mum", "time": "7 pm", "date": "Monday",
           "list": "You have an alarm", **settings.helpline()}
    for persona in settings.personas.values():
        for key, lines in persona.lines.items():
            for line in lines:
                out = line.format(**fmt)
                assert "{" not in out, f"{persona.id}.{key}"


def test_names_live_only_in_config(settings):
    s = settings.override({})
    s.personas["cat"].name = "Pepper"
    from spike_brain.mind.conversation import system_prompt
    assert "You are Pepper" in system_prompt(s.personas["cat"], None, s.helpline())


def test_user_settings_override_and_env(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SPIKE_TOKEN", raising=False)
    user = tmp_path / "spike_settings.toml"
    user.write_text('[server]\nport = 9001\n[life]\nquiet_hours = ["23:00", "06:00"]\n', encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("# secrets\nGEMINI_API_KEY='abc123'\nexport SPIKE_TOKEN=tok\n", encoding="utf-8")
    s = Settings.load(user_toml=user, env_file=env)
    assert s.server.port == 9001 and s.server.heartbeat_s == 5
    assert s.life.quiet_hours == ["23:00", "06:00"]
    assert s.secret("GEMINI_API_KEY") == "abc123" and s.secret("SPIKE_TOKEN") == "tok"
    assert load_env(tmp_path / "missing.env") == {}


def test_personal_wake_words_come_from_a_local_file_only(tmp_path):
    """The owner's extra wake words live in root/data/ (git-ignored), never in shipped config."""
    s = Settings.load(user_toml=None, env_file=tmp_path / "none.env", root=tmp_path)
    assert s.personas["dog"].wake_words == ["Spike", "Hey Buddy"] and s.personas["cat"].wake_words == ["Spicy"]
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "personal_wake_words.toml").write_text(
        '[dog]\nwake_words = ["Rex"]\nvocative_only = ["rex"]\n[dog.wake_aliases]\n"Rex" = ["Rex", "hey rex", "wrecks"]\n'
        '[cat]\nwake_words = ["Tiggy"]\n', encoding="utf-8")
    s = Settings.load(user_toml=None, env_file=tmp_path / "none.env", root=tmp_path)
    dog, cat = s.personas["dog"], s.personas["cat"]
    assert dog.wake_words == ["Spike", "Hey Buddy", "Rex"] and cat.wake_words == ["Spicy", "Tiggy"]
    assert dog.wake_aliases["Rex"] == ["rex", "hey rex", "wrecks"] and "rex" in dog.vocative_only
    assert cat.wake_aliases["Tiggy"] == ["tiggy"]
    off = Settings.load(user_toml=None, env_file=tmp_path / "none.env", root=tmp_path,
                        overrides={"wake": {"personal_file": ""}})
    assert off.personas["dog"].wake_words == ["Spike", "Hey Buddy"]
    for f in (DEFAULT_TOML, *(DEFAULT_TOML.parent / "personas").glob("*.toml")):
        assert "Rex" not in f.read_text(encoding="utf-8")


def test_placeholder_keys_count_as_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "paste-your-new-key-here")
    s = Settings.load(user_toml=None, env_file=tmp_path / "none.env")
    assert s.secret("GEMINI_API_KEY") is None


def test_deep_merge():
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": 3}}) == {"a": {"b": 1, "c": 3}}


def test_gitignore_keeps_secrets_and_memory_out():
    from spike_brain.config import LAPTOP_DIR
    gi = (LAPTOP_DIR / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "data/", "spike_settings.toml"):
        assert re.search(rf"^{re.escape(pattern)}$", gi, re.M), pattern


@pytest.mark.skipif(not (MODELS / "vosk").exists(), reason="vosk model not downloaded")
def test_every_wake_word_is_reachable_by_the_spotter(settings):
    """Each wake word needs at least one alias Vosk can actually hear (in its dictionary)."""
    from spike_brain.hearing.wake import VoskSpotter
    aliases = {m: p.wake_aliases for m, p in settings.personas.items()}
    sp = VoskSpotter(settings.path(settings.wake.vosk_model), aliases)
    reachable = {sp.phrase_map[g][0] for g in sp.grammar}
    for p in settings.personas.values():
        for w in p.wake_words:
            assert w in reachable, f"{w} has no in-vocabulary alias"


def test_lines_read_naturally_before_the_name_is_known(settings):
    dog, cat = settings.personas["dog"], settings.personas["cat"]
    assert dog.line("greet_evening", owner="you") == "[mood:caring] Good evening. How was your day?"
    assert dog.line("greet_evening", owner="Arpon") == "[mood:caring] Good evening, Arpon. How was your day?"
    for p in (dog, cat):
        for key, lines in p.lines.items():
            for i in range(len(lines)):
                out = p.line.__func__(type("P", (), {"lines": {key: [lines[i]]}})(), key, owner="you",
                                      what="x", when="x", time="x", date="x", list="x", **settings.helpline())
                assert ", you." not in out and "{" not in out, out


def test_ellipsis_lines_survive_the_nameless_cleanup(settings):
    cat = settings.personas["cat"]
    for line in cat.lines["trick_ok"]:
        out = cat.line.__func__(type("P", (), {"lines": {"k": [line]}})(), "k", owner="you")
        assert "] ..." in out and "] .." + "U" not in out, out


def test_spicy_roasts_only_inside_the_guardrails(settings):
    """Owner decision 30 Sep 2026: Spicy may roast to motivate, about habits only, ending on action or
    loyalty, and never when the owner is down (the same rules the app's Gemini styles use)."""
    from spike_brain.mind.conversation import system_prompt
    p = system_prompt(settings.personas["cat"], "Nur", settings.helpline())
    assert "Roasting to motivate" in p
    for must in ("ONLY about what they do", "NEVER about their body", "No slurs", "I believe in you",
                 "sad, lonely, stressed, down on themselves or unsafe: no roasting at all"):
        assert must in p
    assert "Roasting" not in system_prompt(settings.personas["dog"], "Nur", settings.helpline())
