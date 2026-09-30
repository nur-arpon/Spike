"""Ollama on demand (mind/ollama_service.py): start, warm, idle, and the brain's use of it.
No real Ollama: the HTTP checks and the process start are replaced."""
import asyncio
import json

import pytest
from websockets.asyncio.client import connect

from spike_brain.brain import Brain, RunOptions
from spike_brain.mind import ollama_service as O

from .conftest import FakeLLM
from .test_brain import Robot, spoken
from .test_server import ToneVoice


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def make(up=True, spawn_ok=True, up_after_spawn=True, keep_alive="15m", clock=None, unload=None):
    states = []
    svc = O.OllamaService(idle_unload=keep_alive, start_timeout_s=2, on_state=states.append, unload=unload,
                          model=lambda: "m:latest", clock=clock or __import__("time").monotonic)
    svc.flags = {"up": up, "spawned": 0, "loaded": True}

    async def server_up():
        return svc.flags["up"]

    async def model_loaded():
        return svc.flags["loaded"]

    def spawn():
        svc.flags["spawned"] += 1
        if spawn_ok and up_after_spawn:
            svc.flags["up"] = True
        return spawn_ok

    svc.server_up, svc.model_loaded, svc._spawn = server_up, model_loaded, spawn
    return svc, states


def test_parse_duration():
    assert O.parse_duration_s("15m") == 900
    assert O.parse_duration_s("90s") == 90
    assert O.parse_duration_s("1h30m") == 5400
    assert O.parse_duration_s(300) == 300
    assert O.parse_duration_s("600") == 600
    assert O.parse_duration_s("nonsense", default=7) == 7


def test_find_ollama_prefers_configured(tmp_path):
    exe = tmp_path / "ollama.exe"
    exe.write_bytes(b"")
    assert O.find_ollama(str(exe)) == str(exe)


async def test_warm_once_for_many_callers():
    svc, states = make(up=True)
    calls = []

    async def warm():
        calls.append(1)
        await asyncio.sleep(0.05)
        return 0.05

    results = await asyncio.gather(*(svc.ensure_ready(warm) for _ in range(4)))
    assert results == [True] * 4 and len(calls) == 1
    assert states == ["warming", "ready"] and svc.ready and svc.flags["spawned"] == 0
    assert await svc.ensure_ready(warm) and len(calls) == 1          # already ready: no second warm-up


async def test_starts_ollama_when_not_running():
    svc, states = make(up=False)

    async def warm():
        return 0.0

    assert await svc.ensure_ready(warm)
    assert svc.flags["spawned"] == 1 and states[-1] == "ready"


async def test_missing_ollama_goes_off_then_retries():
    svc, states = make(up=False, spawn_ok=False)

    async def warm():
        return 0.0

    assert not await svc.ensure_ready(warm)
    assert svc.state == "off"
    svc._spawn = lambda: (svc.flags.__setitem__("up", True), True)[1]  # installed meanwhile
    assert await svc.ensure_ready(warm) and svc.ready


async def test_failed_warm_up_is_off_not_a_crash():
    svc, states = make(up=True)

    async def warm():
        raise RuntimeError("model file missing")

    assert not await svc.ensure_ready(warm)
    assert svc.state == "off" and "model file missing" in svc.last_error


async def test_idle_unload_marks_asleep():
    clock = Clock()
    unloaded = []

    async def unload():
        unloaded.append(clock.t)

    svc, states = make(up=True, keep_alive="15m", clock=clock, unload=unload)

    async def warm():
        return 0.0

    assert await svc.ensure_ready(warm)
    clock.t += 14 * 60
    await svc.check_idle()
    assert svc.ready
    svc.used()
    clock.t += 15 * 60 + 1
    await svc.check_idle()
    assert svc.state == "asleep" and len(unloaded) == 1         # the model is unloaded explicitly


async def test_model_unloaded_elsewhere_is_noticed():
    clock = Clock()
    svc, states = make(up=True, clock=clock)

    async def warm():
        return 0.0

    await svc.ensure_ready(warm)
    svc.flags["loaded"] = False
    clock.t += 120
    await svc.check_idle()
    assert svc.state == "asleep"


# ------------------------------------------------------------------ the brain with an on-demand model
@pytest.fixture
async def rig(settings):
    s = settings.override({"life": {"quiet_hours": ["03:00", "03:01"], "greet_on_start": False},
                           "audio": {"mute_tail_ms": 20, "output": "robot"},
                           "llm": {"warm_wait_s": 0.5}})
    brain = Brain(s, RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=False, port=0))
    await brain.start()
    brain.speech.text_only = False
    brain.voices["dog"] = ToneVoice()
    brain.voices["cat"] = ToneVoice()
    svc, states = make(up=True)
    svc.on_state = brain._on_llm_state
    brain.ollama = svc
    fake = FakeLLM(["[mood:happy] Warm and ready!"])
    warm_delay = {"s": 0.05}

    async def warm():
        await asyncio.sleep(warm_delay["s"])
        brain.local_llm = fake
        brain.llm = fake
        return warm_delay["s"]

    brain._warm_llm = warm
    async with connect(f"ws://127.0.0.1:{brain.server.port}/") as ws:
        await ws.send(json.dumps({"v": 1, "type": "hello", "id": 1, "role": "simulator", "device_id": "t",
                                  "fw": "test", "caps": ["face", "speaker", "touch", "text"]}))
        robot = Robot(ws)
        await robot.pump(lambda m: m["type"] == "listening")
        yield brain, robot, fake, warm_delay
    await brain.shutdown()


async def test_first_request_waits_for_the_warm_up(rig):
    brain, robot, fake, _ = rig
    assert brain.llm is None and brain.ollama.state == "asleep"
    words = spoken(await robot.say_turn("tell me something"))
    assert "Warm and ready" in words and brain.ollama.ready and len(fake.calls) == 1


async def test_slow_warm_up_gets_a_scripted_line_not_silence(rig):
    brain, robot, fake, delay = rig
    delay["s"] = 3.0
    words = spoken(await robot.say_turn("tell me something", timeout=4))
    lines = [ln.split("] ")[-1] for ln in brain.persona.lines["warming"]]
    assert any(ln.split(".")[0] in words for ln in lines), words
    assert fake.calls == []


async def test_asleep_drops_the_local_model(rig):
    brain, robot, fake, _ = rig
    await robot.say_turn("hi")
    assert brain.llm is fake
    brain.ollama._set("asleep")
    assert brain.llm is None and brain.local_llm is None


async def test_head_tap_and_app_connect_wake_the_model(rig):
    brain, robot, fake, _ = rig
    await robot.send("touch", zone="head", gesture="tap")
    for _ in range(40):
        if brain.ollama.ready:
            break
        await asyncio.sleep(0.02)
    assert brain.ollama.ready
