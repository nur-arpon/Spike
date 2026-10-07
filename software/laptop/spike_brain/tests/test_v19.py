"""Protocol v1.9 (PROTOCOL.md changelog v1.9): the brain's half of the day-1 hardening.

- body actions: the exact walk / paw messages are the shared vectors (software/protocol/body_action_vectors.json),
  which the firmware's host test (`face_pc link`) reads too -> spoken "walk" / "give paw" reach the robot's
  parser unchanged; and they are only sent to a robot that announced the caps (the gait-enable gate);
- edge `rear`, `gesture` (and the spoken answer to a wave), `pv` and `robot_tools` in the hello;
- the thinking cue: once per turn, only when the reply is slow, sound only for the speaker that will play it;
- robot tools: diag_get / calib / cam_config relayed to the right board, answers back to the apps,
  robot_status with the boards' caps, camera and screen board paired by the token, not the device_id.
"""
import asyncio
import json
import time
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from spike_brain import protocol as P
from spike_brain.brain import Brain, RunOptions
from spike_brain.mind.intents import TRICK_FIELDS, match_intent

from .conftest import FakeLLM
from .test_applink import APP_HELLO, Phone, _join
from .test_brain import Robot
from .test_server import ToneVoice

VECTORS = Path(__file__).resolve().parents[3] / "protocol" / "body_action_vectors.json"
FACE_V19 = {"v": 1, "type": "hello", "id": 1, "role": "face", "device_id": "spike-abc123", "fw": "0.3.0", "pv": "1.9",
            "caps": ["face", "speaker", "touch", "battery", "drive", "edge", "imu", "gesture", "edge_rear", "captions",
                     "thinking_cue", "diag", "calib", "walk", "paw"]}
CAMERA_V19 = {"v": 1, "type": "hello", "id": 1, "role": "camera", "device_id": "spikecam-77aa00", "fw": "0.3.0",
              "pv": "1.9", "caps": ["camera", "cam_config"]}


class SlowLLM(FakeLLM):
    """The first piece of the reply comes after `delay` seconds (the real model: ~0.6 s, Turbo ~2-3 s more)."""

    def __init__(self, delay: float, **kw):
        super().__init__(**kw)
        self.delay = delay

    async def stream(self, messages, max_tokens=None):
        await asyncio.sleep(self.delay)
        async for piece in super().stream(messages, max_tokens):
            yield piece


@pytest.fixture
async def brain(settings):
    s = settings.override({"life": {"quiet_hours": ["03:00", "03:01"], "greet_on_start": False},
                           "audio": {"mute_tail_ms": 20, "output": "robot"},
                           "app": {"list_poll_s": 0.1}})
    b = Brain(s, RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=False, port=0))
    await b.start()
    fake = FakeLLM()
    b.llm = b.local_llm = fake
    b.speech.text_only = False
    b.voices["dog"] = ToneVoice()
    b.voices["cat"] = ToneVoice()
    yield b
    await b.shutdown()


async def _robot(b, hello=FACE_V19):
    ws = await _join(b.server.port, hello)
    r = Robot(ws)
    h = await r.pump(lambda m: m["type"] == "hello")
    await r.pump(lambda m: m["type"] == "listening")
    return ws, r, h


async def _phone(b):
    ws = await _join(b.server.port, APP_HELLO)
    p = Phone(ws)
    h = await p.pump(lambda m: m["type"] == "hello")
    await p.pump(lambda m: m["type"] == "memory")
    return ws, p, h


# ------------------------------------------------------------------ body actions (B8 / G-2)
def _cases():
    return json.loads(VECTORS.read_text(encoding="utf-8"))["cases"]


def test_spoken_body_actions_match_the_shared_vectors():
    from datetime import datetime
    spoken = [c for c in _cases() if c["said"]]
    assert len(spoken) >= 8
    for c in spoken:
        i = match_intent(c["said"], {"dog": "Spike", "cat": "Spicy"}, datetime(2026, 10, 10, 12))
        assert i is not None and i.name == "trick", c["said"]
        msg = {"type": "action", "action": i.slots["action"], **i.slots["fields"]}
        assert msg == c["message"], (c["said"], msg)
        P.validate({"v": 1, **msg}, "to_robot")          # and the brain's own validator accepts it
    assert set(TRICK_FIELDS) >= {c["said"] for c in spoken}


@pytest.mark.parametrize("case", [c for c in _cases() if c["said"]], ids=lambda c: c["said"])
async def test_spoken_walk_and_paw_reach_the_robot_exactly(brain, case):
    ws, r, _ = await _robot(brain)
    await r.send("text", text=case["said"])
    act = await r.pump(lambda m: m["type"] == "action", 6)
    got = {k: v for k, v in act.items() if k not in ("v", "id", "ts")}
    assert got == case["message"]                       # byte for byte what the firmware vectors expect
    await ws.close()


async def test_body_actions_need_the_caps(brain):
    hello = {**FACE_V19, "caps": [c for c in FACE_V19["caps"] if c not in ("walk", "paw")]}
    ws, r, _ = await _robot(brain, hello)
    await r.send("text", text="walk")
    say = await r.pump(lambda m: m["type"] == "say" and m["text"], 6)
    assert "learning" in say["text"]
    assert not any(m["type"] == "action" and m["action"] == "walk" for m in r.seen)
    # the LLM choosing [action:paw] is dropped as well
    brain.send_face("action", action="paw", side="left")
    await r.pump(timeout=0.3)
    assert not any(m["type"] == "action" and m["action"] == "paw" for m in r.seen)
    await ws.close()


# ------------------------------------------------------------------ hello, edge rear, gesture
async def test_hello_carries_pv_and_robot_tools(brain):
    ws, r, h = await _robot(brain)
    assert h["pv"] == P.PROTOCOL_MINOR == "1.10" and h["robot_tools"] is True
    client = next(c for c in brain.server.clients.values() if c.role == "face")
    assert client.pv == "1.9" and {"gesture", "walk", "calib"} <= client.caps
    await ws.close()


async def test_rear_edge_and_gestures_are_accepted_and_relayed_to_apps(brain):
    pws, phone, _ = await _phone(brain)
    ws, r, _ = await _robot(brain)
    await r.send("edge", sensor="rear", state="edge")
    e = await phone.pump(lambda m: m["type"] == "edge", 3)
    assert e["sensor"] == "rear" and e["state"] == "edge"
    await r.send("gesture", gesture="swipe", dir="left")
    g = await phone.pump(lambda m: m["type"] == "gesture", 3)
    assert g["gesture"] == "swipe" and g["dir"] == "left"
    await r.send("gesture", gesture="sideways")         # not a gesture -> error, nothing relayed
    err = await r.pump(lambda m: m["type"] == "error", 3)
    assert err["code"] == "bad_value"
    await r.send("imu", event="pickup")
    assert (await phone.pump(lambda m: m["type"] == "imu", 3))["event"] == "pickup"
    await ws.close()
    await pws.close()


async def test_a_wave_is_answered_out_loud_but_not_too_often(brain):
    ws, r, _ = await _robot(brain)
    await r.send("gesture", gesture="wave")
    say = await r.pump(lambda m: m["type"] == "say" and m["text"], 4)
    assert say is not None
    await r.pump(lambda m: m["type"] == "say" and m["final"], 4)
    n = brain.said_count
    await r.send("gesture", gesture="wave")              # within 2 minutes: the robot reacts, the brain stays quiet
    await r.pump(timeout=0.6)
    assert brain.said_count == n
    await r.send("gesture", gesture="near")
    await r.pump(timeout=0.3)
    assert brain.said_count == n
    await ws.close()


# ------------------------------------------------------------------ thinking cue (B2)
async def test_slow_reply_gets_one_thinking_cue_with_sound_on_the_robot(brain):
    brain.llm = brain.local_llm = SlowLLM(2.0)
    ws, r, _ = await _robot(brain)
    pws, phone, _ = await _phone(brain)                  # a phone mirrors the face: look, no sound
    msgs = await r.say_turn("tell me something", timeout=8)
    cues = [m for m in msgs if m["type"] == "listening" and m.get("cue")]
    assert len(cues) == 1 and cues[0]["state"] == "thinking" and cues[0]["cue"] == "thinking"
    assert cues[0]["sound"] is True                      # the robot's speaker plays this reply
    first_say = next(i for i, m in enumerate(msgs) if m["type"] == "say")
    assert msgs.index(cues[0]) < first_say               # before the reply, never during it
    pc = await phone.pump(lambda m: m["type"] == "listening" and m.get("cue"), 2)
    assert pc is not None and pc["sound"] is False
    P.validate({"v": 1, **{k: v for k, v in cues[0].items() if k != "v"}}, "to_robot")
    await ws.close()
    await pws.close()


async def test_fast_reply_gets_no_cue(brain):
    ws, r, _ = await _robot(brain)
    msgs = await r.say_turn("hi", timeout=6)
    assert not any(m["type"] == "listening" and m.get("cue") for m in msgs)
    assert brain.cues_sent == 0
    await ws.close()


async def test_cue_can_be_switched_off(brain):
    brain.s = brain.s.override({"tts": {"thinking_cue_s": 0}})
    brain.llm = brain.local_llm = SlowLLM(1.6)
    ws, r, _ = await _robot(brain)
    msgs = await r.say_turn("tell me something", timeout=8)
    assert not any(m["type"] == "listening" and m.get("cue") for m in msgs)
    await ws.close()


# ------------------------------------------------------------------ robot tools (app request R6)
async def test_robot_status_has_the_boards_and_pairs_them_by_token(brain):
    pws, phone, _ = await _phone(brain)
    ws, r, _ = await _robot(brain)
    cws = await _join(brain.server.port, CAMERA_V19)      # its own device_id: still the same robot
    cam = Robot(cws)
    await cam.pump(lambda m: m["type"] == "hello")
    st = await phone.pump(lambda m: m["type"] == "robot_status" and "camera_caps" in m, 3)
    assert st["online"] and st["boards"] == ["camera", "face"]
    assert st["device_id"] == "spike-abc123" and st["fw"] == "0.3.0" and "calib" in st["caps"]
    assert st["camera_caps"] == ["cam_config", "camera"] and st["pv"] == "1.9"
    await cws.close()
    await ws.close()
    await pws.close()


async def test_diag_calib_and_cam_config_are_relayed(brain):
    pws, phone, _ = await _phone(brain)
    ws, r, _ = await _robot(brain)
    cws = await _join(brain.server.port, CAMERA_V19)
    cam = Robot(cws)
    await cam.pump(lambda m: m["type"] == "hello")
    await phone.send("diag_get")
    assert await r.pump(lambda m: m["type"] == "diag_get", 3) is not None
    await r.send("diag", fw="0.3.0", uptime_s=12, lasers={"edge_fl": {"mm": 91, "ok": True}})
    d = await phone.pump(lambda m: m["type"] == "diag", 3)
    assert d["fw"] == "0.3.0" and d["lasers"]["edge_fl"]["mm"] == 91
    await phone.send("calib", op="signtest", side="right")
    c = await r.pump(lambda m: m["type"] == "calib", 3)
    assert c["op"] == "signtest" and c["side"] == "right"
    await r.send("calib_state", op="signtest", state="passed", result={"slope": 0.21, "sign": 1, "saved": True})
    cs = await phone.pump(lambda m: m["type"] == "calib_state", 3)
    assert cs["state"] == "passed" and cs["result"]["sign"] == 1
    await phone.send("cam_config", vflip=True, hmirror=False, save=True)
    cc = await cam.pump(lambda m: m["type"] == "cam_config", 3)
    assert cc["vflip"] is True and cc["hmirror"] is False and cc["save"] is True
    assert not any(m["type"] == "cam_config" for m in r.seen)      # the screen board never gets it
    await cam.send("cam_config", vflip=True, hmirror=False, saved=True)
    assert (await phone.pump(lambda m: m["type"] == "cam_config", 3))["saved"] is True
    await phone.send("calib", op="dance")                          # not an op
    assert (await phone.pump(lambda m: m["type"] == "error", 3))["code"] == "bad_value"
    await cws.close()
    await ws.close()
    await pws.close()


async def test_robot_tools_without_a_board_are_refused(brain):
    pws, phone, _ = await _phone(brain)
    await phone.send("diag_get")
    e = await phone.pump(lambda m: m["type"] == "error", 3)
    assert e["code"] == "bad_value" and "diag" in e["message"]
    ws, r, _ = await _robot(brain, {**FACE_V19, "caps": ["face", "speaker"]})   # an older robot: no calib cap
    await phone.send("calib", op="stop")
    assert (await phone.pump(lambda m: m["type"] == "error", 3))["code"] == "bad_value"
    await ws.close()
    await pws.close()


async def test_a_robot_cannot_send_tools_messages_as_an_app_and_vice_versa(brain):
    pws, phone, _ = await _phone(brain)
    ws, r, _ = await _robot(brain)
    await phone.send("calib_state", op="balance", state="passed")  # a phone is not the robot: ignored
    await phone.send("gesture", gesture="wave")
    await r.pump(timeout=0.4)
    assert brain.said_count == 0
    assert not any(m["type"] == "calib_state" for m in phone.seen)
    await ws.close()
    await pws.close()
