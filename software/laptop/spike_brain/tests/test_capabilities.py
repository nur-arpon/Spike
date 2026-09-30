"""The body cannot do everything the face can draw: nothing may choose, send or offer hidden actions."""
import asyncio
import re
from pathlib import Path

import pytest

from spike_brain import capabilities as C
from spike_brain.mind import reply
from spike_brain.mind.intents import TRICKS, match_intent
from spike_brain.mind.reply import normalize_action, parse_reply

from datetime import datetime

NOW = datetime(2026, 9, 30, 12, 0)
NAMES = {"dog": "Spike", "cat": "Spicy"}


def test_hidden_list_is_the_agreed_one():
    assert C.HIDDEN_ACTIONS == {"rollOver", "beggingAction"}
    assert C.is_available("playBow") and C.is_available("paw") and C.is_available(None)
    assert not C.is_available("rollOver") and not C.is_available("beggingAction")


@pytest.mark.parametrize("text", ["roll over", "Roll over!", "beg", "high five", "can you roll over please"])
def test_hidden_trick_words_give_an_unavailable_intent(text):
    i = match_intent(text, NAMES, NOW)
    assert i.name == "trick_unavailable"


def test_every_other_trick_word_is_still_a_trick():
    for word, action in TRICKS.items():
        if C.is_available(action):
            i = match_intent(word, NAMES, NOW)
            assert i.name == "trick" and i.slots["action"] == action


@pytest.mark.parametrize("trick", ["roll over", "beg", "high five"])
@pytest.mark.parametrize("mode", ["dog", "cat"])
def test_unavailable_line_is_in_character_and_offers_a_real_trick(trick, mode):
    line, offer = C.unavailable_line(trick, mode)
    assert C.is_available(offer)
    assert "can't" in line and trick in line
    assert parse_reply(line).action is None
    assert C.unavailable_line("high five")[1] == "paw"


def test_llm_never_offered_or_parsed_a_hidden_action():
    assert not set(reply.LLM_ACTIONS) & C.HIDDEN_ACTIONS
    for word in ("rollOver", "roll over", "roll", "rolls over", "beg", "begging", "beggingAction"):
        assert normalize_action(word) is None
        assert parse_reply(f"[mood:happy] [action:{word}] hi").action is None
    assert parse_reply("[happy] *rolls over* hi").action is None
    assert parse_reply("[happy] *begs* hi").action is None


def test_persona_lines_never_carry_a_hidden_action():
    cfg = Path(__file__).resolve().parents[1] / "config" / "personas"
    for f in cfg.glob("*.toml"):
        for m in re.finditer(r"\[action:(\w+)\]", f.read_text(encoding="utf-8")):
            assert C.is_available(reply.normalize_action(m.group(1)) or "x")
        for line in re.findall(r'"(\[[^"]*)"', f.read_text(encoding="utf-8")):
            assert parse_reply(line).action not in C.HIDDEN_ACTIONS


def test_alarm_escalation_never_uses_a_hidden_action():
    from spike_brain.life.scheduler import AlarmRinger
    assert all(C.is_available(a) for a in AlarmRinger.ACTIONS.values())


def test_send_face_drops_a_hidden_action():
    from spike_brain.brain import Brain

    sent = []

    class Srv:
        def broadcast(self, type_, **f):
            sent.append((type_, f))

    b = Brain.__new__(Brain)
    b.server = Srv()
    b.send_face("action", action="rollOver")
    b.send_face("action", action="beggingAction")
    assert sent == []
    b.send_face("action", action="playBow")
    assert sent == [("action", {"cap": "face", "action": "playBow"})] or sent[0][0] == "action"


def test_random_trick_never_picks_a_hidden_action():
    import random
    from spike_brain.brain import Brain

    sent = []
    b = Brain.__new__(Brain)
    b.mode, b.rng = "dog", random.Random(1)
    b.send_face = lambda t, **f: sent.append(f["action"])

    async def say_line(key, **k):
        pass
    b.say_line = say_line

    async def run():
        for _ in range(60):
            await b.do_trick(None)
    real_sleep = asyncio.sleep

    async def fast(_s):
        await real_sleep(0)
    asyncio.sleep = fast
    try:
        asyncio.run(run())
    finally:
        asyncio.sleep = real_sleep
    assert sent and not set(sent) & C.HIDDEN_ACTIONS


def test_dart_list_matches():
    dart = Path(__file__).resolve().parents[3] / "app" / "spike_app" / "lib" / "core" / "capabilities.dart"
    if not dart.exists():
        pytest.skip("app not present")
    m = re.search(r"hiddenActions\s*=\s*\{([^}]*)\}", dart.read_text(encoding="utf-8"))
    assert {x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()} == set(C.HIDDEN_ACTIONS)
