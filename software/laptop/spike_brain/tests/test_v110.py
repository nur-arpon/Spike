"""Protocol v1.10 (the v4 body): action names, numeric `pv`, and the cap gate - driven by the shared
vectors software/protocol/trick_action_vectors.json (PROTOCOL.md 4.1, 5.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from spike_brain import protocol as P

from .test_v19 import FACE_V19, _robot, brain  # noqa: F401  (brain is a fixture)

# A copy of software/protocol/trick_action_vectors.json (that file lives on the fw-v4 branch); when the
# shared one is present in this tree the copy must be identical to it.
_COPY = Path(__file__).resolve().parent / "vectors" / "trick_action_vectors.json"
_SHARED = Path(__file__).resolve().parents[3] / "protocol" / "trick_action_vectors.json"
VECTORS = json.loads(_COPY.read_text(encoding="utf-8"))


def test_local_copy_matches_the_shared_vectors_when_present():
    if not _SHARED.exists():
        pytest.skip("shared vectors not in this tree")
    assert json.loads(_SHARED.read_text(encoding="utf-8")) == VECTORS
BASE = [c for c in FACE_V19["caps"] if c not in ("walk", "paw")]
V4_OFF = BASE + VECTORS["caps"]["gate_off"]
V4_ON = BASE + VECTORS["caps"]["gate_on"]


def hello(caps, hw="v4", pv="1.10"):
    h = {**FACE_V19, "caps": caps, "pv": pv}
    if hw:
        h["hw"] = hw
    return h


def test_pv_compares_numerically():
    assert P.parse_pv("1.10") > P.parse_pv("1.9")
    assert P.pv_at_least("1.10", "1.9") and not P.pv_at_least("1.9", "1.10")
    assert P.parse_pv("") == P.parse_pv(None) == P.parse_pv("x.y") == (0, 0)
    assert P.PROTOCOL_MINOR == "1.10"


def test_vector_actions_and_caps_are_known_names():
    for a in VECTORS["actions"]:
        P.validate({"v": 1, **a["message"]}, "to_robot")
    for name in ("sit", "lieDown", "lie", "stand", "wave"):
        assert name in P.ACTIONS
    caps = set(VECTORS["caps"]["gate_on"]) | set(VECTORS["caps"]["gate_off"])
    assert caps <= set(P.CAPS)
    assert not set(VECTORS["caps"]["never"]) & set(P.CAPS)
    P.validate(hello(V4_ON), "to_brain")                 # hw is an accepted hello field


@pytest.mark.parametrize("case", VECTORS["actions"], ids=lambda c: c["name"])
@pytest.mark.parametrize("gate", ["gate_off", "gate_on"])
async def test_trick_actions_follow_the_cap_gate(brain, case, gate):   # noqa: F811
    msg = case["message"]
    if msg["action"] == "beggingAction":
        pytest.skip("beggingAction stays hidden by capabilities.py (separate decision)")
    ws, r, _ = await _robot(brain, hello(V4_ON if gate == "gate_on" else V4_OFF))
    brain.send_face("action", **{k: v for k, v in msg.items() if k != "type"})
    await r.pump(timeout=0.3)
    sent = [m for m in r.seen if m["type"] == "action" and m["action"] == msg["action"]]
    if case[gate] == "runs":
        assert len(sent) == 1
        assert {k: v for k, v in sent[0].items() if k not in ("v", "id", "ts")} == msg
    else:
        assert case[gate] == "refused" and not sent
    await ws.close()


async def test_stand_needs_a_v4_body(brain):   # noqa: F811
    ws, r, _ = await _robot(brain, hello(BASE, hw=None, pv="1.9"))
    brain.send_face("action", action="stand")
    brain.send_face("action", action="sit")
    await r.pump(timeout=0.3)
    assert not any(m["type"] == "action" and m["action"] in ("stand", "sit") for m in r.seen)
    await ws.close()


async def test_a_phone_does_not_unlock_v4_actions(brain):   # noqa: F811
    from .test_applink import APP_HELLO, _join
    ws = await _join(brain.server.port, {**APP_HELLO, "caps": list(APP_HELLO["caps"]) + ["sit", "lie", "wave"],
                                         "hw": "v4", "pv": "1.10"})
    assert not brain.robot_is_v4() and not brain.can_do_action("sit") and not brain.can_do_action("wave")
    await ws.close()
