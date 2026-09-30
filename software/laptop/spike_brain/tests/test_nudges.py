"""Nudges toward real people come at the right moment: never his first line,
never in the first 10 minutes, only after a real conversation that is
winding down - and his hello always comes first."""
import json
import time

import pytest
from websockets.asyncio.client import connect

from spike_brain.brain import Brain, RunOptions

from .conftest import FakeLLM
from .test_brain import Robot, spoken
from .test_server import ToneVoice


async def make_rig(settings, greet=True):
    s = settings.override({"life": {"quiet_hours": ["03:00", "03:01"], "surprise_cat_mode_per_day": 0,
                                    "greet_on_start": greet},
                           "audio": {"mute_tail_ms": 20}})
    brain = Brain(s, RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=False, port=0))
    await brain.start()
    fake = FakeLLM(["[happy] That sounds fun."])
    brain.llm = brain.local_llm = fake
    brain.speech.text_only = False
    brain.speech.output = "robot"          # never the laptop speakers in tests
    for t in brain._tasks:                 # the tests run the life checks themselves
        t.cancel()
    brain.voices["dog"] = brain.voices["cat"] = ToneVoice()
    return brain, fake


@pytest.fixture
async def chat(settings):
    brain, fake = await make_rig(settings)
    async with connect(f"ws://127.0.0.1:{brain.server.port}/") as ws:
        await ws.send(json.dumps({"v": 1, "type": "hello", "id": 1, "role": "simulator", "device_id": "t",
                                  "fw": "t", "caps": ["face", "speaker", "text"]}))
        robot = Robot(ws)
        await robot.pump(lambda m: m["type"] == "listening")
        yield brain, robot, fake
    await brain.shutdown()


NUDGE_WORDS = ("friend", "outside", "someone", "family", "people", "walk", "message")


async def nudge_now(brain, robot) -> str:
    """Run the life check as if the chat went quiet a minute ago; return what he said."""
    for _ in range(100):                   # let the last reply finish playing first
        if brain.idle():
            break
        await robot.pump(None, 0.02)
    brain.last_interaction = time.monotonic() - 60
    start = len(robot.seen)
    await brain._life_checks()
    await robot.pump(lambda m: m["type"] == "say" and m["final"], 1.0)
    return spoken(robot.seen[start:])


async def test_the_greeting_is_his_first_line(settings):
    brain, _ = await make_rig(settings)
    try:
        assert brain.greeted and brain.said_count == 1
    finally:
        await brain.shutdown()


async def test_no_nudge_in_the_first_ten_minutes(chat):
    brain, robot, _ = chat
    for text in ("hi", "I went to the park", "it was sunny"):
        await robot.say_turn(text)
    assert await nudge_now(brain, robot) == ""                    # 1 minute after start-up
    brain.started_mono -= 11 * 60                                 # ... 11 minutes after start-up
    said = await nudge_now(brain, robot)
    assert said and any(w in said.lower() for w in NUDGE_WORDS), said
    assert brain.memory.last_event("people_nudge") is not None


async def test_no_nudge_without_a_real_conversation(chat):
    brain, robot, _ = chat
    brain.started_mono -= 60 * 60
    await robot.say_turn("hi")
    await robot.say_turn("how are you")
    assert await nudge_now(brain, robot) == ""                    # only 2 things said to him


async def test_no_nudge_while_the_chat_is_still_going(chat):
    brain, robot, _ = chat
    brain.started_mono -= 60 * 60
    for text in ("hi", "tell me a joke", "another one"):
        await robot.say_turn(text)
    brain.last_interaction = time.monotonic() - 5                 # they spoke 5 s ago
    start = len(robot.seen)
    await brain._life_checks()
    assert spoken(robot.seen[start:]) == ""


async def test_no_nudge_before_his_hello(settings):
    brain, fake = await make_rig(settings, greet=False)
    brain.speech.output = "none"           # no robot connected: captions only
    try:
        brain.started_mono -= 60 * 60
        for text in ("hi", "hello", "what's up"):
            await brain.console_turn(text)
        assert not brain.greeted
        assert not brain._nudge_allowed()
    finally:
        await brain.shutdown()


async def test_first_reply_never_carries_a_nudge(chat):
    brain, robot, fake = chat
    brain.started_mono -= 60 * 60                                 # even long after start-up
    await robot.say_turn("I feel a bit lonely today")             # a loneliness signal
    assert "someone they could call" not in fake.calls[-1][-1]["content"]
    await robot.say_turn("I stayed home")
    assert "someone they could call" not in fake.calls[-1][-1]["content"]
    await robot.say_turn("just watched TV")                       # 3rd turn: now it may be woven in
    ctx = fake.calls[-1][-1]["content"]
    assert "someone they could call" in ctx and "helpline" in ctx and "13 11 14" not in ctx


async def test_nudges_are_rare(chat):
    brain, robot, fake = chat
    brain.started_mono -= 60 * 60
    for text in ("hi", "my day was ok", "nothing much"):
        await robot.say_turn(text)
    assert not any("encourage them to call" in c[-1]["content"] for c in fake.calls), \
        "without loneliness the nudge is never woven into a reply"
    assert await nudge_now(brain, robot)
    assert await nudge_now(brain, robot) == ""                    # not again for 20 hours
