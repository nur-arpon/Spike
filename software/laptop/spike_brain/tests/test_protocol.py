"""Protocol v1: envelopes, validation, round trips, and the face_v2 name lists."""
import json
import re

import pytest

from spike_brain import protocol as P

from .conftest import FACE_V2

ROBOT_EXAMPLES = {
    "hello": {"role": "face", "device_id": "spike-1", "fw": "0.1.0", "caps": ["face", "mic"],
              "audio_out": {"rates": [16000]}},
    "touch": {"zone": "head", "gesture": "tap"},
    "imu": {"event": "pickup"},
    "edge": {"sensor": "front_left", "state": "edge"},
    "battery": {"percent": 27, "volts": 7.1, "charging": False},
    "mood_state": {"mood": "sleepy", "mode": "dog"},
    "say_state": {"utt": "u1", "seq": 0, "state": "finished"},
    "audio": {"seq": 3, "rate": 16000, "format": "pcm_s16le", "data": P.b64(b"\x00\x01" * 160)},
    "camera": {"seq": 1, "format": "jpeg", "width": 2, "height": 2, "data": P.b64(b"\xff\xd8\xff")},
    "text": {"text": "hello"},
    "alarm_ack": {"action": "snooze"},
    "log": {"level": "warn", "msg": "I2S underrun"},
    "pong": {"re": 4},
}
BRAIN_EXAMPLES = {
    "hello": {"server": "spike-brain", "version": "0.1.0", "heartbeat_s": 5, "mode": "dog"},
    "mood": {"mood": "cuteAngry", "hold_s": 0},
    "action": {"action": "tailWagDance"},
    "event": {"event": "comeHome"},
    "say": {"utt": "u1", "seq": 0, "final": True, "text": "Hi!", "duration_ms": 400, "audio": None,
            "mouth": {"rate_hz": 50, "values": [0, 50, 0]}},
    "say_audio": {"utt": "u1", "seq": 0, "index": 0, "last": True, "data": P.b64(b"\x00\x00")},
    "stop_speaking": {"utt": "u1"},
    "listening": {"state": "thinking"},
    "look_at": {"x": -0.4, "y": 0.1, "source": "camera"},
    "sound": {"sound": "whine"},
    "alarm": {"alarm_id": 3, "state": "ringing", "level": 1},
    "game": {"game": "rps", "phase": "reveal", "owner": "rock", "robot": "paper", "result": "lose"},
    "set_mode": {"mode": "cat"},
    "set_recipe": {"mode": "dog", "code": "SPK1-x"},
    "ping": {},
    "error": {"code": "bad_value", "message": "x"},
}


@pytest.mark.parametrize("type_", sorted(ROBOT_EXAMPLES))
def test_robot_messages_round_trip(type_):
    msg = P.make(type_, 7, **ROBOT_EXAMPLES[type_])
    back = P.decode(P.encode(msg))
    assert back == msg
    P.validate(back, "to_brain")
    assert back["v"] == 1 and back["id"] == 7 and isinstance(back["ts"], int)


@pytest.mark.parametrize("type_", sorted(BRAIN_EXAMPLES))
def test_brain_messages_round_trip(type_):
    msg = P.make(type_, 1, re=3, **BRAIN_EXAMPLES[type_])
    back = P.decode(P.encode(msg))
    assert back == msg and back["re"] == 3
    P.validate(back, "to_robot")


def test_unknown_fields_are_ignored():
    msg = P.decode('{"v":1,"type":"touch","id":2,"zone":"head","future_field":{"a":1}}')
    P.validate(msg, "to_brain")                     # no error


@pytest.mark.parametrize("raw,code", [
    ("not json", "bad_json"),
    ("[1,2]", "bad_json"),
    ('{"type":"touch"}', "missing_field"),
    ('{"v":2,"type":"touch","id":1}', "version_mismatch"),
    ('{"v":1,"type":5}', "bad_value"),
    ('{"v":1,"type":"touch","id":"x"}', "bad_value"),
])
def test_decode_errors(raw, code):
    with pytest.raises(P.ProtocolError) as e:
        P.decode(raw)
    assert e.value.code == code


def test_binary_frames_rejected():
    with pytest.raises(P.ProtocolError):
        P.decode(b"\x00\x01")


@pytest.mark.parametrize("msg,code", [
    ({"v": 1, "type": "warp_drive", "id": 1}, "unknown_type"),
    ({"v": 1, "type": "touch", "id": 1}, "missing_field"),
    ({"v": 1, "type": "touch", "id": 1, "zone": "tail"}, "bad_value"),
    ({"v": 1, "type": "battery", "id": 1, "percent": "low"}, "bad_value"),
    ({"v": 1, "type": "battery", "id": 1, "percent": 40, "charging": "yes"}, "bad_value"),
    ({"v": 1, "type": "mood_state", "id": 1, "mood": "happpy"}, "bad_value"),
])
def test_validation_errors(msg, code):
    with pytest.raises(P.ProtocolError) as e:
        P.validate(msg, "to_brain")
    assert e.value.code == code


def test_bool_is_not_a_number():
    with pytest.raises(P.ProtocolError):
        P.validate({"v": 1, "type": "battery", "id": 1, "percent": True}, "to_brain")


def test_audio_split_keeps_samples_whole():
    pcm = bytes(range(256)) * 200                   # 51200 bytes = 25600 samples
    parts = P.split_audio(pcm, 8192)
    assert b"".join(parts) == pcm
    assert all(len(p) % 2 == 0 for p in parts)
    assert len(parts) == 4 and len(parts[0]) == 16384
    assert P.split_audio(b"") == [b""]


def test_base64_roundtrip_and_errors():
    assert P.unb64(P.b64(b"spike")) == b"spike"
    with pytest.raises(P.ProtocolError):
        P.unb64("not base64!!")


def test_id_counter_wraps_at_uint32():
    c = P.IdCounter(0xFFFFFFFE)
    assert c.next() == 0xFFFFFFFF
    assert c.next() == 1


def test_messages_fit_the_size_limit():
    chunk = P.split_audio(b"\x01\x00" * 8192)[0]
    msg = P.encode(P.make("say_audio", 1, utt="u99999", seq=12, index=40, last=False, data=P.b64(chunk)))
    assert len(msg.encode()) < 24 * 1024             # an ESP32 never parses more than ~24 KiB


# ---- the names are shared with face_v2: they must never drift ----------------
def _js_array(src: str, name: str) -> list[str]:
    m = re.search(rf"var {name} = \[(.*?)\];", src, re.S)
    return re.findall(r"'([A-Za-z]+)'", m.group(1))


def test_moods_match_face_v2():
    src = (FACE_V2 / "moods.js").read_text(encoding="utf-8")
    assert tuple(_js_array(src, "MOODS")) == P.MOODS


def test_actions_match_face_v2():
    src = (FACE_V2 / "actions.js").read_text(encoding="utf-8")
    block = src[src.index("var ACTIONS = {"):src.index("var ACTION_NAMES")]
    keys = re.findall(r"^\s{4}([A-Za-z]+): \{ label:", block, re.M)
    assert set(keys) == set(P.ACTIONS) - set(P.COMFORT_ACTIONS) - set(P.BODY_ACTIONS)
    link = (FACE_V2 / "brain_link.js").read_text(encoding="utf-8")
    for a in P.COMFORT_ACTIONS:                       # the simulator draws the brain-level ones itself
        assert re.search(rf"\b{a}: function", link), f"brain_link.js does not implement {a}"


def test_body_actions_accept_their_optional_fields():
    for direction in P.ACTION_DIRECTIONS:
        for steps in (1, 4, 16):
            msg = {"v": 1, "id": 1, "type": "action", "action": "walk",
                   "direction": direction, "steps": steps, "style": "tiltStep"}
            P.validate(msg, "to_robot")
            P.validate(msg, "from_app")
    for side in P.ACTION_SIDES:
        for frm in P.ACTION_FROMS:
            msg = {"v": 1, "id": 1, "type": "action", "action": "paw", "side": side, "from": frm}
            P.validate(msg, "to_robot")
            P.validate(msg, "from_app")
    # bare, no optional fields - matches the brain's own defaults (direction/steps/style/side/from)
    P.validate({"v": 1, "id": 1, "type": "action", "action": "walk"}, "to_robot")
    P.validate({"v": 1, "id": 1, "type": "action", "action": "paw"}, "to_robot")


@pytest.mark.parametrize("msg", [
    {"v": 1, "id": 1, "type": "action", "action": "walk", "direction": "sideways"},
    {"v": 1, "id": 1, "type": "action", "action": "walk", "steps": 0},
    {"v": 1, "id": 1, "type": "action", "action": "walk", "steps": 17},
    {"v": 1, "id": 1, "type": "action", "action": "walk", "style": "gallop"},
    {"v": 1, "id": 1, "type": "action", "action": "paw", "side": "front"},
    {"v": 1, "id": 1, "type": "action", "action": "paw", "from": "lying"},
])
def test_body_actions_reject_bad_optional_fields(msg):
    with pytest.raises(P.ProtocolError) as e:
        P.validate(msg, "to_robot")
    assert e.value.code == "bad_value"


def test_events_and_sounds_exist_in_face_v2():
    beh = (FACE_V2 / "behaviour.js").read_text(encoding="utf-8")
    for ev in P.EVENTS:
        assert re.search(rf"function {ev}\(", beh), ev
    link = (FACE_V2 / "brain_link.js").read_text(encoding="utf-8")
    for s in P.SOUNDS:
        assert re.search(rf"\b{s}: 'play", link), f"brain_link.js has no mapping for sound {s}"
    sounds = (FACE_V2 / "sounds.js").read_text(encoding="utf-8")
    for fn in re.findall(r": '(play[A-Za-z]+)'", link):
        assert f"function {fn}(" in sounds, fn


def test_protocol_doc_lists_every_type():
    doc = (FACE_V2.parent / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    for t in set(P.ROBOT_TO_BRAIN) | set(P.BRAIN_TO_ROBOT):
        assert f"`{t}`" in doc, t


def test_json_is_compact_and_utf8():
    s = P.encode(P.make("say", 1, utt="u", seq=0, final=True, text="café", duration_ms=1, audio=None))
    assert " " not in s.replace("café", "") and "é" in s
    assert json.loads(s)["text"] == "café"
