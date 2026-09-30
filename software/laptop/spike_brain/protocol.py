"""Spike protocol v1 - see software/protocol/PROTOCOL.md (the spec wins).

Pure functions and constants only (no I/O), so the same rules are easy to
test and to mirror in the ESP32 firmware.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = 1
MAX_MESSAGE_BYTES = 64 * 1024          # what a sender may send
AUDIO_CHUNK_SAMPLES = 8192             # say_audio chunk size (16 KiB raw)

# --- names shared with face_v2 (tests/test_protocol.py checks they match) ---
MOODS = (
    "neutral", "happy", "excited", "love", "laughing", "playful", "curious",
    "sad", "caring", "sleepy", "sleeping", "bored", "sulking", "scared",
    "surprised", "cuteAngry", "dizzy", "proud", "embarrassed", "begging",
    "cuddly", "wakeupAlarm",
    "joy", "delight", "anger", "frustration", "disgust", "grief",
    "loneliness", "hope", "shyness", "jealousy", "confusion", "suspicion",
    "relief", "gratitude", "mischief", "determination", "nervousness",
    "awe", "smugness", "silliness", "hungry",
)
ACTIONS = (
    "wakeUp", "fallAsleep", "napping", "dozing", "deepSleepDreams", "tripBump",
    "sneeze", "hiccup", "shiver", "pant", "tailWagDance", "zoomies", "headTilt",
    "sniffAround", "beggingAction", "rollOver", "playBow", "yawn", "boop",
    "snuggle", "slowWag", "walk", "paw",
)
# Comfort actions added in v1.1 (PROTOCOL.md 5.2): not in face_v2/actions.js; the
# simulator draws them in brain_link.js, the firmware implements them itself.
COMFORT_ACTIONS = ("snuggle", "slowWag")
# Body actions added in v1.4 (PROTOCOL.md 5.2): also not in face_v2/actions.js and also
# robot-side only, but (unlike the comfort actions) the simulator does not draw them -
# there is no face_v2 motion for a walk or a paw to fall back to.
BODY_ACTIONS = ("walk", "paw")
ACTION_DIRECTIONS = ("forward", "back")
ACTION_STEPS = tuple(range(1, 17))                 # walk.steps: 1..16
ACTION_STYLES = ("auto", "tiltStep", "rearStep", "march")
ACTION_SIDES = ("left", "right")
ACTION_FROMS = ("stand", "sit")
EVENTS = ("sayHi", "greetByTimeOfDay", "comeHome", "ownerLooksSad", "pickedUp",
          "fellOver", "ignoredNudge")
SOUNDS = ("yip", "bark", "whine", "sniff", "sigh", "snore", "giggle", "meow",
          "purr", "hiss", "trill", "yawn", "sneeze", "hiccup", "growl", "munch",
          "pop", "boop", "patSqueak")
MODES = ("dog", "cat")
ROLES = ("simulator", "face", "camera", "robot", "tool", "app")   # "app" = the phone app (v1.2)
BOARD_ROLES = ("face", "camera", "robot")                          # the physical robot's own boards
CAPS = ("face", "speaker", "mic", "camera", "touch", "imu", "edge", "battery", "drive", "text",
        "audio_out")                         # v1.5: a phone app that plays Spike's voice (PROTOCOL.md 10.8)
LISTEN_STATES = ("idle", "wake", "listening", "thinking", "speaking")
TOUCH_ZONES = ("head", "nose", "back", "chin")
TOUCH_GESTURES = ("tap", "pat", "hold", "release")
IMU_EVENTS = ("pickup", "putdown", "shake", "fall", "lap")
EDGE_SENSORS = ("front_left", "front_right", "rear_left", "rear_right")
SAY_STATES = ("started", "finished", "stopped")
ALARM_STATES = ("ringing", "snoozed", "stopped")
GAME_PHASES = ("start", "countdown", "shoot", "reveal", "end")
RPS = ("rock", "paper", "scissors", "unknown")
ERROR_CODES = ("bad_json", "missing_field", "bad_value", "unknown_type",
               "version_mismatch", "not_ready", "auth", "too_big")
RESERVED_TYPES = ("move", "ota", "config")

# Close codes (PROTOCOL.md section 3)
CLOSE_NORMAL, CLOSE_GOING_AWAY = 1000, 1001
CLOSE_HELLO_TIMEOUT, CLOSE_VERSION, CLOSE_ABUSE, CLOSE_AUTH = 4000, 4001, 4002, 4003

# type -> {field: (python types, allowed values or None, required)}
_STR, _NUM, _INT, _BOOL = (str,), (int, float), (int,), (bool,)
_LIST, _DICT = (list,), (dict,)
_NULLDICT = (dict, type(None))

ROBOT_TO_BRAIN: dict[str, dict[str, tuple]] = {
    "hello": {"role": (_STR, ROLES, True), "device_id": (_STR, None, True),
              "fw": (_STR, None, True), "caps": (_LIST, None, True),
              "audio_out": (_DICT, None, False), "token": (_STR, None, False)},
    "touch": {"zone": (_STR, TOUCH_ZONES, True), "gesture": (_STR, TOUCH_GESTURES, False)},
    "imu": {"event": (_STR, IMU_EVENTS, True)},
    "edge": {"sensor": (_STR, EDGE_SENSORS, True), "state": (_STR, ("edge", "clear"), True)},
    "battery": {"percent": (_NUM, None, True), "volts": (_NUM, None, False),
                "charging": (_BOOL, None, False)},
    "mood_state": {"mood": (_STR, MOODS, False), "mode": (_STR, MODES, False)},
    "say_state": {"utt": (_STR, None, True), "seq": (_INT, None, False),
                  "state": (_STR, SAY_STATES, True)},
    "audio": {"data": (_STR, None, True), "rate": (_INT, None, False), "seq": (_INT, None, False),
              "format": (_STR, ("pcm_s16le",), False),
              # v1.2 app mic: the silence that ends a request on this stream (6.7), clamped 1500..6000
              "end_silence_ms": (_INT, None, False)},
    "camera": {"data": (_STR, None, True), "format": (_STR, ("jpeg",), False),
               "seq": (_INT, None, False)},
    "text": {"text": (_STR, None, True)},
    "alarm_ack": {"action": (_STR, ("stop", "snooze"), True)},
    "log": {"msg": (_STR, None, True), "level": (_STR, None, False)},
    "pong": {},
    "ping": {},
    "error": {"code": (_STR, None, True)},
}

BRAIN_TO_ROBOT: dict[str, dict[str, tuple]] = {
    "hello": {"server": (_STR, None, True), "version": (_STR, None, True),
              "heartbeat_s": (_NUM, None, True), "mode": (_STR, MODES, True)},
    "mood": {"mood": (_STR, MOODS, True), "hold_s": (_NUM, None, False)},
    "action": {"action": (_STR, ACTIONS, True),
               # v1.4 body actions (5.2): optional fields, only meaningful for "walk" / "paw"
               "direction": (_STR, ACTION_DIRECTIONS, False), "steps": (_INT, ACTION_STEPS, False),
               "style": (_STR, ACTION_STYLES, False), "side": (_STR, ACTION_SIDES, False),
               "from": (_STR, ACTION_FROMS, False)},
    "event": {"event": (_STR, EVENTS, True)},
    "say": {"utt": (_STR, None, True), "seq": (_INT, None, True), "final": (_BOOL, None, True),
            "text": (_STR, None, True), "duration_ms": (_INT, None, True),
            "audio": (_NULLDICT, None, True), "mouth": (_NULLDICT, None, False)},
    "say_audio": {"utt": (_STR, None, True), "seq": (_INT, None, True), "index": (_INT, None, True),
                  "last": (_BOOL, None, True), "data": (_STR, None, True)},
    "stop_speaking": {},
    "listening": {"state": (_STR, LISTEN_STATES, True)},
    "look_at": {"x": (_NUM, None, True), "y": (_NUM, None, True)},
    "sound": {"sound": (_STR, SOUNDS, True)},
    "alarm": {"state": (_STR, ALARM_STATES, True), "level": (_INT, None, False)},
    "game": {"game": (_STR, ("rps",), True), "phase": (_STR, GAME_PHASES, True)},
    "set_mode": {"mode": (_STR, MODES, True)},
    "set_recipe": {"mode": (_STR, MODES, True)},
    "ping": {},
    "pong": {},
    "error": {"code": (_STR, ERROR_CODES, True)},
    # --- v1.2 (PROTOCOL.md section 10): new brain -> robot types ---
    "drive": {"x": (_NUM, None, True), "y": (_NUM, None, True), "ttl_ms": (_INT, None, True)},
    "set_display": {"captions": (_BOOL, None, False)},
}

# --- v1.2: what the brain sends a client with role "app" (everything a robot gets, plus these) ---
BRAIN_TO_APP: dict[str, dict[str, tuple]] = {
    **BRAIN_TO_ROBOT,
    "timers": {"items": (_LIST, None, True)},
    "memory": {"items": (_LIST, None, True), "total": (_INT, None, False)},
    "robot_status": {"online": (_BOOL, None, True), "boards": (_LIST, None, True)},
    "brain_status": {"llm": (_STR, None, True)},
    "heard": {"text": (_STR, None, True)},
    "pairing": {"lan": (_BOOL, None, True), "url": (_STR, None, True)},
    "voice_style": {"styles": (_DICT, None, True)},       # v1.8: the Gemini voice style picked per character
    "battery": {"percent": (_NUM, None, True), "volts": (_NUM, None, False), "charging": (_BOOL, None, False)},
    "camera": {"data": (_STR, None, True), "format": (_STR, ("jpeg",), False), "seq": (_INT, None, False)},
}

# --- v1.2: what a client with role "app" (the phone) may send (PROTOCOL.md section 10) ---
LLM_STATES = ("ready", "warming", "asleep", "off")
TIMER_KINDS = ("alarm", "reminder")
DRIVE_TTL_MS = (100, 1000)          # accepted range of drive.ttl_ms (the brain clamps into it)

APP_ONLY: dict[str, dict[str, tuple]] = {
    # the face and body, exactly as the brain would send them to the robot
    "action": {"action": (_STR, ACTIONS, True), "quiet": (_BOOL, None, False),
               "direction": (_STR, ACTION_DIRECTIONS, False), "steps": (_INT, ACTION_STEPS, False),
               "style": (_STR, ACTION_STYLES, False), "side": (_STR, ACTION_SIDES, False),
               "from": (_STR, ACTION_FROMS, False)},
    "mood": {"mood": (_STR, MOODS, True), "hold_s": (_NUM, None, False)},
    "event": {"event": (_STR, EVENTS, True)},
    "sound": {"sound": (_STR, SOUNDS, True)},
    "set_mode": {"mode": (_STR, MODES, True), "quiet": (_BOOL, None, False)},
    "set_recipe": {"mode": (_STR, MODES, True), "code": (_STR, None, False), "recipe": (_DICT, None, False)},
    "set_display": {"captions": (_BOOL, None, True)},
    "drive": {"x": (_NUM, None, True), "y": (_NUM, None, True), "ttl_ms": (_INT, None, False)},
    # lists the app shows
    "timers_get": {},
    "timer_set": {"kind": (_STR, TIMER_KINDS, True), "due": (_NUM, None, True), "label": (_STR, None, False),
                  "repeat": (_STR, ("", "daily"), False)},
    "timer_cancel": {"timer_id": (_INT, None, True)},
    "memory_get": {},
    "memory_forget": {"fact_id": (_INT, None, True)},
    "memory_forget_all": {"confirm": (_BOOL, (True,), True)},
    "camera_subscribe": {"fps": (_NUM, None, False)},
    "camera_unsubscribe": {},
    "pairing_get": {},
    "keepalive": {"warm": (_BOOL, None, False)},     # v1.6: silent "still here" (PROTOCOL.md 10.9)
    "voice_source": {"voice": (_STR, ("phone", "laptop"), True)},   # v1.7: who voices this phone's replies (10.10)
    "voice_style": {"mode": (_STR, MODES, True), "style": (_STR, None, True)},   # v1.8: the laptop's Gemini voice style (10.11)
}
APP_TO_BRAIN: dict[str, dict[str, tuple]] = {**ROBOT_TO_BRAIN, **APP_ONLY}


class ProtocolError(Exception):
    """A message broke the protocol. `code` is one of ERROR_CODES."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class IdCounter:
    """Per-connection outgoing message id (1, 2, 3, ... wraps at uint32)."""
    value: int = 0

    def next(self) -> int:
        self.value = self.value + 1 if self.value < 0xFFFFFFFF else 1
        return self.value


def make(type_: str, msg_id: int, re: int | None = None, **fields: Any) -> dict:
    """Build a message dict with the envelope filled in."""
    msg: dict[str, Any] = {"v": PROTOCOL_VERSION, "type": type_, "id": msg_id, "ts": now_ms()}
    if re is not None:
        msg["re"] = re
    msg.update(fields)
    return msg


def encode(msg: dict) -> str:
    """JSON text for the wire (compact, UTF-8 safe, no NaN)."""
    return json.dumps(msg, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def decode(text: str | bytes) -> dict:
    """Parse one frame. Raises ProtocolError for anything that is not a v1 envelope."""
    if isinstance(text, (bytes, bytearray)):
        raise ProtocolError("bad_json", "binary frames are not used in v1")
    try:
        msg = json.loads(text)
    except (ValueError, RecursionError) as e:
        raise ProtocolError("bad_json", f"not JSON: {e}") from None
    if not isinstance(msg, dict):
        raise ProtocolError("bad_json", "a message must be a JSON object")
    if "v" not in msg or "type" not in msg:
        raise ProtocolError("missing_field", "missing 'v' or 'type'")
    if msg["v"] != PROTOCOL_VERSION:
        raise ProtocolError("version_mismatch", f"protocol v{msg['v']} not supported (this is v1)")
    if not isinstance(msg["type"], str):
        raise ProtocolError("bad_value", "'type' must be a string")
    if "id" in msg and (not isinstance(msg["id"], int) or isinstance(msg["id"], bool)):
        raise ProtocolError("bad_value", "'id' must be an integer")
    return msg


def validate(msg: dict, direction: str) -> None:
    """Check the fields of a decoded message. direction: 'to_brain', 'from_app'
    (to the brain from a client with role "app", v1.2) or 'to_robot'.

    Unknown extra fields are fine (forward compatibility). Unknown types raise
    ProtocolError('unknown_type')."""
    table = {"to_brain": ROBOT_TO_BRAIN, "from_app": APP_TO_BRAIN, "to_app": BRAIN_TO_APP}.get(direction, BRAIN_TO_ROBOT)
    spec = table.get(msg["type"])
    if spec is None:
        raise ProtocolError("unknown_type", f"unknown message type '{msg['type']}'")
    for name, (types, allowed, required) in spec.items():
        if name not in msg:
            if required:
                raise ProtocolError("missing_field", f"{msg['type']}: missing '{name}'")
            continue
        val = msg[name]
        if val is None and not required:
            continue
        if isinstance(val, bool) and bool not in types:
            raise ProtocolError("bad_value", f"{msg['type']}.{name}: wrong type")
        if not isinstance(val, types):
            raise ProtocolError("bad_value", f"{msg['type']}.{name}: wrong type")
        if allowed is not None and val not in allowed:
            raise ProtocolError("bad_value", f"{msg['type']}.{name}: '{val}' is not allowed")


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as e:
        raise ProtocolError("bad_value", f"bad base64: {e}") from None


def split_audio(pcm: bytes, chunk_samples: int = AUDIO_CHUNK_SAMPLES) -> list[bytes]:
    """Split 16-bit mono PCM into say_audio-sized pieces (never splits a sample)."""
    step = chunk_samples * 2
    return [pcm[i:i + step] for i in range(0, len(pcm), step)] or [b""]
