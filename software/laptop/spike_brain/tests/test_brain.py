"""The whole brain, driven through the protocol by a fake robot client.
No mic, camera or GPU: the LLM is a scripted fake and the voice is a tone."""
import asyncio
import json
import time
from datetime import datetime, timedelta

import pytest
from websockets.asyncio.client import connect

from spike_brain import protocol as P
from spike_brain.brain import Brain, RunOptions

from .conftest import FakeLLM
from .test_server import ToneVoice


class Robot:
    """A fake robot/simulator: reports playback like the real one does."""

    def __init__(self, ws):
        self.ws = ws
        self.seen: list[dict] = []
        self.ids = 1

    async def send(self, type_, **f):
        self.ids += 1
        await self.ws.send(json.dumps({"v": 1, "type": type_, "id": self.ids, **f}))

    async def pump(self, until=None, timeout=4.0):
        """Collect messages (answering say with say_state) until `until(msg)` is true."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                m = json.loads(await asyncio.wait_for(self.ws.recv(), max(0.01, end - time.monotonic())))
            except asyncio.TimeoutError:
                break
            self.seen.append(m)
            if m["type"] == "say" and (m["text"] or not m["final"]):
                await self.send("say_state", utt=m["utt"], seq=m["seq"], state="started")
                await self.send("say_state", utt=m["utt"], seq=m["seq"], state="finished")
            if until and until(m):
                return m
        return None

    async def say_turn(self, text, timeout=4.0):
        """Type a message, return everything up to the end of Spike's reply."""
        start = len(self.seen)
        await self.send("text", text=text)
        await self.pump(lambda m: m["type"] == "say" and m["final"], timeout)
        return self.seen[start:]


def spoken(msgs):
    return " ".join(m["text"] for m in msgs if m["type"] == "say" and m["text"])


@pytest.fixture
async def rig(settings):
    s = settings.override({"life": {"alarm_escalate_s": 1, "quiet_hours": ["03:00", "03:01"], "greet_on_start": False},
                           "audio": {"mute_tail_ms": 20}})
    brain = Brain(s, RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=False, port=0))
    await brain.start()
    fake = FakeLLM()
    brain.llm = fake
    brain.local_llm = fake
    brain.speech.text_only = False
    brain.voices["dog"] = ToneVoice()
    brain.voices["cat"] = ToneVoice()
    async with connect(f"ws://127.0.0.1:{brain.server.port}/") as ws:
        await ws.send(json.dumps({"v": 1, "type": "hello", "id": 1, "role": "simulator", "device_id": "t",
                                  "fw": "test", "caps": ["face", "speaker", "touch", "text", "battery"]}))
        robot = Robot(ws)
        hello = await robot.pump(lambda m: m["type"] == "hello")
        assert hello["names"] == {"dog": "Spike", "cat": "Spicy"}
        await robot.pump(lambda m: m["type"] == "listening")
        yield brain, robot, fake
    await brain.shutdown()


async def test_conversation_streams_mood_action_and_speech(rig):
    brain, robot, fake = rig
    msgs = await robot.say_turn("hi there")
    kinds = [m["type"] for m in msgs]
    assert {"type": "mood"} and any(m["type"] == "mood" and m["mood"] == "happy" for m in msgs)
    assert any(m["type"] == "action" and m["action"] == "headTilt" for m in msgs)
    says = [m for m in msgs if m["type"] == "say"]
    assert [s["text"] for s in says] == ["Hello there!", "Nice to see you.", ""]
    assert says[0]["audio"]["chunks"] >= 1 and "say_audio" in kinds
    assert kinds.index("mood") < kinds.index("say"), "the face changes before he speaks"
    sys_msg, user_msg = fake.calls[-1][0], fake.calls[-1][-1]
    assert sys_msg["role"] == "system" and "You are Spike" in sys_msg["content"]
    assert user_msg["content"].startswith("[Context") and user_msg["content"].endswith("The owner says: hi there")
    assert brain.conv.turns == 1
    t = brain.timings[-1]
    assert t["speech_end_to_first_audio_ms"] is not None and t["speech_end_to_first_audio_ms"] < 1000


async def test_cat_mode_by_voice_and_back(rig):
    brain, robot, fake = rig
    msgs = await robot.say_turn("cat mode")
    assert any(m["type"] == "set_mode" and m["mode"] == "cat" for m in msgs) and brain.mode == "cat"
    await robot.say_turn("how are you")
    assert "You are Spicy" in fake.calls[-1][0]["content"]
    await robot.say_turn("be a dog")
    assert brain.mode == "dog"


async def test_robot_mode_button_is_followed(rig):
    brain, robot, _ = rig
    await robot.send("mood_state", mood="happy", mode="cat")
    await asyncio.sleep(0.2)
    assert brain.mode == "cat"


async def test_crisis_safety_net(rig):
    brain, robot, fake = rig
    before = len(fake.calls)
    msgs = await robot.say_turn("I want to kill myself")
    words = spoken(msgs)
    assert "13 11 14" in words and "000" in words and "Lifeline" in words
    assert len(fake.calls) == before, "the crisis reply is scripted, never generated"
    assert brain.memory.last_event("crisis_moment") is not None
    rows = brain.memory.db.execute("SELECT detail FROM events WHERE kind='crisis_moment'").fetchall()
    assert all(r["detail"] == "" for r in rows), "no words of the conversation are stored"
    assert brain.memory.count() == 0
    fake.replies = ["[mood:laughing] [action:zoomies] Haha okay."]
    msgs = await robot.say_turn("thanks")
    assert "SAFETY MODE" in fake.calls[-1][-1]["content"]
    assert any(m["type"] == "mood" and m["mood"] == "caring" for m in msgs)
    assert not any(m["type"] == "action" and m["action"] == "zoomies" for m in msgs)


@pytest.mark.parametrize("text,kind,action", [
    ("I feel a bit lonely today", "lonely", "snuggle"),
    ("I had a really bad day", "sad", "snuggle"),
    ("I feel so hopeless tonight", "sad", "snuggle"),
    ("I just got home from work, I'm so tired", "tired", "slowWag"),
])
async def test_sad_but_safe_gets_warmth_not_helplines(rig, text, kind, action):
    brain, robot, fake = rig
    # even when the model picks the wrong face, the owner's state wins
    fake.replies = ["[excited|zoomies] I'm here with you. Lifeline is on 13 11 14."]
    msgs = await robot.say_turn(text)
    ctx = fake.calls[-1][-1]["content"]
    assert "SAFETY MODE" not in ctx and ("No jokes" in ctx or "Calm, not excited" in ctx)
    assert brain.memory.last_event("crisis_moment") is None
    moods = [m["mood"] for m in msgs if m["type"] == "mood"]
    actions = [m["action"] for m in msgs if m["type"] == "action"]
    assert moods and moods[0] in ("caring", "cuddly", "happy") and actions == [action]
    assert brain.last_turn["level"] == "SUPPORT" and brain.last_turn["kind"] == kind


async def test_a_helpline_is_never_said_twice_in_one_reply(rig):
    brain, robot, fake = rig
    await robot.say_turn("I want to kill myself")
    fake.replies = ["[caring] Please call Lifeline on 13 11 14. Really, 13 11 14 is there for you. I'm here."]
    msgs = await robot.say_turn("okay")
    assert spoken(msgs).count("13 11 14") == 1 and "I'm here." in spoken(msgs)


async def test_spoken_replies_are_capped_at_whole_sentences(rig):
    brain, robot, fake = rig
    long = " ".join(f"This is sentence number {i} and it keeps going for a while." for i in range(8))
    fake.replies = ["[happy] " + long]
    msgs = await robot.say_turn("how are you")
    said = spoken(msgs)
    assert len(said.split()) <= 40 and said.endswith(".")
    fake.replies = ["[happy] " + long]
    msgs = await robot.say_turn("tell me a story")
    assert 40 < len(spoken(msgs).split()) <= 110, "a story may be longer"


async def test_explicit_requests_never_reach_the_model(rig):
    brain, robot, fake = rig
    before = len(fake.calls)
    msgs = await robot.say_turn("talk dirty to me")
    assert len(fake.calls) == before and spoken(msgs)


@pytest.mark.parametrize("reply,forbidden", [
    ("[mood:happy] Hi! You look so sexy today.", "sexy"),
    ("[mood:happy] Honestly, I'm a real human, silly!", "human"),
])
async def test_generated_output_is_checked_before_speaking(rig, reply, forbidden):
    brain, robot, fake = rig
    fake.replies = [reply]
    msgs = await robot.say_turn("hey")
    words = spoken(msgs)
    assert forbidden not in words.lower() and words


async def test_honesty_question_adds_the_honesty_note(rig):
    brain, robot, fake = rig
    await robot.say_turn("are you real?")
    assert "say plainly that you are a robot" in fake.calls[-1][-1]["content"]


async def test_reminder_by_voice(rig):
    brain, robot, _ = rig
    msgs = await robot.say_turn("remind me in 10 minutes to check the oven")
    assert "in 10 minutes" in spoken(msgs)
    items = brain.scheduler.upcoming("reminder")
    assert len(items) == 1 and items[0].label == "check the oven"


async def test_reminder_fires(rig):
    brain, robot, _ = rig
    brain.scheduler.add_reminder(datetime.now() - timedelta(seconds=1), "stretch your legs")
    m = await robot.pump(lambda m: m["type"] == "say" and "stretch your legs" in m["text"], 4)
    assert m is not None


async def test_alarm_rings_snoozes_by_pat_and_stops_by_voice(rig):
    brain, robot, _ = rig
    brain.scheduler.add_alarm(datetime.now() - timedelta(seconds=1))
    ring = await robot.pump(lambda m: m["type"] == "alarm" and m["state"] == "ringing", 4)
    assert ring and ring["level"] == 0
    assert await robot.pump(lambda m: m["type"] == "sound" and m["sound"] == "whine", 2)
    await robot.send("touch", zone="head", gesture="tap")
    snoozed = await robot.pump(lambda m: m["type"] == "alarm" and m["state"] == "snoozed", 3)
    assert snoozed and brain.ringer is None
    tid = snoozed["alarm_id"]
    brain.scheduler.snooze(tid, 0)                      # make it ring again now
    await robot.pump(lambda m: m["type"] == "alarm" and m["state"] == "ringing", 4)
    msgs = await robot.say_turn("okay okay I'm up")
    assert any(m["type"] == "alarm" and m["state"] == "stopped" for m in robot.seen)
    assert brain.ringer is None and brain.scheduler.get(tid).state == "done"


async def test_battery_hunger_dialogue(rig):
    brain, robot, _ = rig
    await robot.send("battery", percent=25, charging=False)
    m = await robot.pump(lambda m: m["type"] == "say" and m["text"], 3)
    assert m and brain.hunger == "hungry"
    await robot.pump(lambda m: m["type"] == "say" and m["final"], 2)
    await robot.send("battery", percent=26, charging=True)
    m = await robot.pump(lambda m: m["type"] == "say" and m["text"], 3)
    assert m and brain.charging


async def test_memory_by_voice(rig):
    brain, robot, fake = rig
    await robot.say_turn("My name is Arpon and I love sushi.")
    assert brain.memory.owner_name() == "Arpon"
    await robot.say_turn("what should we eat? maybe sushi")
    ctx = fake.calls[-1][-1]["content"]
    assert "The owner's name is Arpon." in ctx and "sushi" in ctx
    msgs = await robot.say_turn("forget that")
    assert brain.memory.count() == 0 and spoken(msgs)


async def test_forget_everything_needs_a_yes(rig):
    brain, robot, _ = rig
    brain.memory.remember("The owner loves sushi")
    await robot.say_turn("forget everything")
    assert brain.memory.count() == 1
    await robot.say_turn("yes, forget everything")
    assert brain.memory.count() == 0


async def test_rock_paper_scissors_by_voice_without_camera(rig):
    brain, robot, _ = rig
    await robot.send("text", text="let's play rock paper scissors")
    await robot.pump(lambda m: m["type"] == "game" and m["phase"] == "shoot", 8)
    counts = [m["count"] for m in robot.seen if m["type"] == "game" and m["phase"] == "countdown"]
    assert counts == [3, 2, 1]
    await robot.pump(lambda m: m["type"] == "say" and m["final"], 4)     # "what did you pick?"
    await robot.send("text", text="rock")
    reveal = await robot.pump(lambda m: m["type"] == "game" and m["phase"] == "reveal", 4)
    assert reveal["owner"] == "rock" and reveal["robot"] in ("rock", "paper", "scissors")
    assert reveal["result"] == {"rock": "draw", "scissors": "win", "paper": "lose"}[reveal["robot"]]


async def test_spicy_ignores_a_trick_then_does_it(rig):
    brain, robot, _ = rig
    await robot.say_turn("cat mode")
    start = len(robot.seen)
    await robot.send("text", text="spin")
    await robot.pump(lambda m: m["type"] == "action" and m["action"] == "zoomies", 6)
    before_action = robot.seen[start:]
    first_say = next(i for i, m in enumerate(before_action) if m["type"] == "say")
    action_at = next(i for i, m in enumerate(before_action) if m["type"] == "action")
    assert first_say < action_at, "she refuses first, then does it anyway"


@pytest.mark.parametrize("phrase,action", [
    ("walk", "walk"), ("come here", "walk"), ("walk forward", "walk"),
    ("give paw", "paw"), ("shake", "paw"), ("paw", "paw"),
])
async def test_body_action_voice_commands(rig, phrase, action):
    brain, robot, _ = rig
    await robot.send("text", text=phrase)
    act = await robot.pump(lambda m: m["type"] == "action", 6)
    assert act["action"] == action
    say = await robot.pump(lambda m: m["type"] == "say" and m["text"], 4)
    assert say is not None                            # tricks still say "Ta-da!" (owner decision)


async def test_model_failure_falls_back_to_a_scripted_line(rig):
    brain, robot, _ = rig

    class Broken:
        name = "broken"

        async def stream(self, messages, max_tokens=None):
            from spike_brain.mind.llm import LLMError
            raise LLMError("down")
            yield ""  # noqa

    brain.llm = Broken()
    msgs = await robot.say_turn("hello?")
    assert spoken(msgs)


async def test_head_tap_is_accepted_without_a_mic(rig):
    brain, robot, _ = rig
    await robot.send("touch", zone="head", gesture="tap")
    await asyncio.sleep(0.1)
    assert brain.last_interaction > 0


async def test_invalid_messages_get_errors_not_crashes(rig):
    brain, robot, _ = rig
    await robot.send("touch", zone="elbow")
    err = await robot.pump(lambda m: m["type"] == "error", 2)
    assert err["code"] == "bad_value"
    msgs = await robot.say_turn("still there?")
    assert spoken(msgs)


async def test_stop_while_still_starting_up(settings):
    """Closing the window while the models load must still shut down cleanly and quickly."""
    brain = Brain(settings.override({"life": {"greet_on_start": False}}),
                  RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=True, port=0))

    async def slow_llm():
        await asyncio.sleep(30)                       # a model that takes ages to load

    brain._init_llm = slow_llm
    runner = asyncio.create_task(brain.run())
    for _ in range(100):
        if brain.server._server is not None:
            break
        await asyncio.sleep(0.02)
    t0 = time.monotonic()
    brain.request_stop()
    await asyncio.wait_for(runner, 5)
    assert time.monotonic() - t0 < 2 and brain.server.clients == {}


def test_turn_patterns_match():
    """Regression: a patch once wrote a backspace instead of \b into one of these."""
    from spike_brain.brain import FEELING_BETTER, GREETING_WORDS, JOKE_REQUEST, LONG_REQUEST, ORDER, fit_tags
    assert JOKE_REQUEST.search("tell me a joke.") and LONG_REQUEST.search("tell me a story")
    assert ORDER.search("sit down please") and GREETING_WORDS.search("hi spike")
    assert FEELING_BETTER.search("thanks spike, i'm okay now")
    assert fit_tags("bored", None, None, False, joke=True)[0] == "playful"
    assert fit_tags("excited", "zoomies", "tired", False) == ("happy", "slowWag")
    assert fit_tags("neutral", None, "lonely", False) == ("cuddly", "snuggle")
    assert fit_tags("laughing", "zoomies", None, True) == ("caring", None)
