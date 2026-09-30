"""End to end with the real face simulator: face_v2/index.html + brain_link.js
run in jsdom (node) and talk to the real brain over the real protocol."""
import asyncio
import json
import shutil

import pytest

from spike_brain.brain import Brain, RunOptions

from .conftest import FACE_V2, LAPTOP, FakeLLM
from .test_server import ToneVoice

NODE = shutil.which("node")
JSDOM = FACE_V2 / "tools" / "node_modules" / "jsdom"
SCRIPT = LAPTOP / "spike_brain" / "tests" / "sim" / "brain_link_check.js"

pytestmark = pytest.mark.skipif(not (NODE and JSDOM.exists()), reason="needs node + face_v2/tools/node_modules")


async def test_simulator_is_the_robot(settings):
    s = settings.override({"audio": {"mute_tail_ms": 20}, "life": {"quiet_hours": ["03:00", "03:01"]}})
    brain = Brain(s, RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=False, port=0))
    await brain.start()
    fake = FakeLLM(["[mood:excited] [action:tailWagDance] Hello there! I can hear you from the simulator."])
    brain.llm = brain.local_llm = fake
    brain.speech.text_only = False
    brain.voices["dog"] = brain.voices["cat"] = ToneVoice()
    got: list[dict] = []
    real_on_message = brain.on_message

    async def spy(client, msg):
        got.append({"role": client.role, **msg})
        await real_on_message(client, msg)

    brain.server.on_message = spy
    hello_roles = []
    real_connect = brain.on_connect

    async def spy_connect(client):
        hello_roles.append((client.role, sorted(client.caps), client.fw))
        await real_connect(client)

    brain.server.on_connect = spy_connect
    proc = await asyncio.create_subprocess_exec(NODE, str(SCRIPT), str(brain.server.port), "10",
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        for _ in range(300):                          # wait for the page to connect (cold node start is slow)
            if hello_roles:
                break
            await asyncio.sleep(0.1)
        if not hello_roles:
            proc.kill()
            out, err = await proc.communicate()
            pytest.fail("the simulator never connected: " + out.decode(errors="replace")[-600:] +
                        err.decode(errors="replace")[-1200:])
        await asyncio.sleep(3.0)                       # it pats, types, moves the battery, picks up
        await brain.set_mode("cat", announce=True)
        await asyncio.sleep(1.5)
        brain.send_face("game", game="rps", phase="reveal", owner="rock", robot="scissors", result="win",
                        score={"owner": 1, "robot": 0, "draws": 0})
        brain.send_face("alarm", alarm_id=1, state="ringing", level=2, label="Wake up")
        brain.send_face("action", action="snuggle")          # comfort actions are drawn by brain_link.js
        brain.send_face("action", action="slowWag")
        out, err = await asyncio.wait_for(proc.communicate(), timeout=30)
    finally:
        if proc.returncode is None:
            proc.kill()
        await brain.shutdown()
    lines = [ln for ln in out.decode("utf-8", "replace").splitlines() if ln.startswith("{")]
    assert lines, f"no summary from node: {err.decode(errors='replace')[-800:]}"
    summary = json.loads(lines[-1])

    # --- the page side
    assert summary["errors"] == [], summary["errors"]
    assert "on" in summary["states"] and summary["connectedButton"] == "Brain connected"
    assert summary["chatVisible"] and summary["inputClearedAfterSend"]
    assert summary["finalMode"] == "cat", "set_mode from the brain switched the face to Spicy"
    assert summary["maxMouth"] > 0.2, "the mouth moved with the speech envelope"
    assert any("Hello there!" in c for c in summary["captions"]), summary["captions"]
    assert "rock" in summary["rpsLine"] and "scissors" in summary["rpsLine"]
    assert summary["alarmActive"] is True
    assert summary["dogName"] == "Spike" and summary["catName"] == "Spicy"

    # --- the brain side
    role, caps, fw = hello_roles[0]
    assert role == "simulator" and {"face", "speaker", "touch", "text"} <= set(caps) and fw
    types = [(m["type"], m.get("zone") or m.get("event") or m.get("state") or m.get("text")) for m in got]
    assert ("touch", "head") in types, types
    assert ("text", "hello from the simulator") in types
    assert ("imu", "pickup") in types
    assert any(m["type"] == "battery" and m["percent"] == 20 for m in got)
    assert any(m["type"] == "mood_state" for m in got)
    assert ("say_state", "started") in types and ("say_state", "finished") in types
    assert fake.calls and fake.calls[-1][-1]["content"].endswith("hello from the simulator")
