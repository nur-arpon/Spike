"""Pure logic behind Spike's eyes (no camera, no MediaPipe - fully testable).

Presence         owner arrived / left, with hysteresis and "away for how long".
EmotionEstimator MediaPipe face blendshapes -> happy / sad / tired / neutral,
                 relative to the owner's own resting face (slow baseline),
                 smoothed over seconds, with a hold time before switching.
classify_rps     a hand (MediaPipe gesture name and/or 21 landmarks) ->
                 rock / paper / scissors.
RpsVote          majority vote over the frames of one "shoot!" window.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field


# ---------------------------------------------------------------------- presence
@dataclass
class PresenceEvent:
    kind: str                 # arrived | left
    away_s: float = 0.0       # for arrived: how long they were gone (inf = first time)


class Presence:
    def __init__(self, present_after_s: float = 1.0, absent_after_s: float = 25.0):
        self.present_after_s = present_after_s
        self.absent_after_s = absent_after_s
        self.present = False
        self.seen_since: float | None = None
        self.last_seen: float | None = None
        self.left_at: float | None = None

    def update(self, face_seen: bool, t: float) -> PresenceEvent | None:
        if face_seen:
            self.last_seen = t
            if self.seen_since is None:
                self.seen_since = t
            if not self.present and t - self.seen_since >= self.present_after_s:
                self.present = True
                away = (self.seen_since - self.left_at) if self.left_at is not None else math.inf
                return PresenceEvent("arrived", away)
            return None
        # not seen this frame
        if self.last_seen is None or t - self.last_seen > 0.25:     # ~2 missed frames at 8 fps
            self.seen_since = None
        if self.present and self.last_seen is not None and t - self.last_seen >= self.absent_after_s:
            self.present = False
            self.left_at = self.last_seen
            return PresenceEvent("left")
        return None


# ---------------------------------------------------------------------- emotion
def _avg(d: dict, *keys: str) -> float:
    vals = [d.get(k, 0.0) for k in keys]
    return sum(vals) / len(vals) if vals else 0.0


@dataclass
class EmotionEstimator:
    window_s: float = 8.0          # smoothing time constant
    baseline_s: float = 300.0      # resting-face baseline time constant
    sad_threshold: float = 0.45
    tired_threshold: float = 0.55
    happy_threshold: float = 0.40
    hold_s: float = 3.0            # a new label must persist this long
    scores: dict = field(default_factory=lambda: {"happy": 0.0, "sad": 0.0, "tired": 0.0})
    base: dict = field(default_factory=dict)
    label: str = "neutral"
    _candidate: str = "neutral"
    _candidate_since: float = 0.0
    _last_t: float | None = None
    _yawn_since: float | None = None

    def raw(self, bs: dict, t: float) -> dict:
        """Instant scores 0..1 from blendshapes (relative to the resting baseline)."""
        smile = _avg(bs, "mouthSmileLeft", "mouthSmileRight")
        frown = _avg(bs, "mouthFrownLeft", "mouthFrownRight")
        inner_up = bs.get("browInnerUp", 0.0)
        press = _avg(bs, "mouthPressLeft", "mouthPressRight")
        closed = _avg(bs, "eyeBlinkLeft", "eyeBlinkRight")
        squint = _avg(bs, "eyeSquintLeft", "eyeSquintRight")
        jaw = bs.get("jawOpen", 0.0)
        rel = {}
        for k, v in (("frown", frown), ("inner_up", inner_up), ("press", press), ("closed", closed), ("smile", smile)):
            b = self.base.get(k, v)
            rel[k] = max(0.0, v - b)
        if jaw > 0.55 and smile < 0.2:
            self._yawn_since = self._yawn_since if self._yawn_since is not None else t
        else:
            self._yawn_since = None
        yawning = self._yawn_since is not None and t - self._yawn_since > 1.2
        happy = min(1.0, max(0.0, smile * 1.5 + 0.3 * squint * smile))
        sad = min(1.0, max(0.0, 1.4 * rel["frown"] + 0.9 * rel["inner_up"] * (1 - smile) + 0.4 * rel["press"]
                           - 0.8 * smile))
        tired = min(1.0, max(0.0, 1.6 * max(0.0, closed - 0.25) + 0.8 * rel["closed"] + (0.6 if yawning else 0.0)))
        return {"happy": happy, "sad": sad, "tired": tired, "_feat": {"frown": frown, "inner_up": inner_up,
                "press": press, "closed": closed, "smile": smile}}

    def update(self, bs: dict, t: float) -> str | None:
        """Feed one frame of blendshapes; returns the new label when it changes."""
        r = self.raw(bs, t)
        dt = 0.125 if self._last_t is None else max(0.0, min(1.0, t - self._last_t))
        self._last_t = t
        a = 1 - math.exp(-dt / self.window_s)
        for k in ("happy", "sad", "tired"):
            self.scores[k] += (r[k] - self.scores[k]) * a
        if self.label == "neutral":                 # learn the resting face only while neutral
            ab = 1 - math.exp(-dt / self.baseline_s)
            for k, v in r["_feat"].items():
                self.base[k] = v if k not in self.base else self.base[k] + (v - self.base[k]) * ab
        cand = self._pick()
        if cand != self._candidate:
            self._candidate, self._candidate_since = cand, t
        if cand != self.label and t - self._candidate_since >= self.hold_s:
            self.label = cand
            return cand
        return None

    def _pick(self) -> str:
        s = self.scores
        if s["sad"] >= self.sad_threshold and s["sad"] >= s["happy"]:
            return "sad"
        if s["tired"] >= self.tired_threshold:
            return "tired"
        if s["happy"] >= self.happy_threshold:
            return "happy"
        # hysteresis: stay in a state until clearly out of it
        if self.label == "sad" and s["sad"] >= self.sad_threshold * 0.7:
            return "sad"
        if self.label == "tired" and s["tired"] >= self.tired_threshold * 0.7:
            return "tired"
        return "neutral"

    def no_face(self, t: float) -> None:
        self._last_t = t


# ---------------------------------------------------------------------- rock paper scissors
GESTURE_TO_RPS = {"Closed_Fist": "rock", "Open_Palm": "paper", "Victory": "scissors"}


def _dist(a, b) -> float:
    return math.dist((a[0], a[1]), (b[0], b[1]))


def fingers_extended(lm: list[tuple[float, float]]) -> list[bool]:
    """Index, middle, ring, pinky: extended if the tip is farther from the wrist
    than the PIP joint (rotation-invariant)."""
    wrist = lm[0]
    out = []
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        out.append(_dist(lm[tip], wrist) > _dist(lm[pip], wrist) * 1.1)
    return out


def classify_rps(gesture: str | None, gesture_score: float, landmarks: list | None) -> str | None:
    if gesture in GESTURE_TO_RPS and gesture_score >= 0.5:
        return GESTURE_TO_RPS[gesture]
    if not landmarks or len(landmarks) < 21:
        return None
    idx, mid, ring, pinky = fingers_extended(landmarks)
    n = sum((idx, mid, ring, pinky))
    if idx and mid and not ring and not pinky:
        return "scissors"
    if n >= 3:                      # an open hand with one finger misread is still paper
        return "paper"
    if n == 0:
        return "rock"
    return None


class RpsVote:
    def __init__(self):
        self.votes: Counter = Counter()

    def add(self, choice: str | None) -> None:
        if choice:
            self.votes[choice] += 1

    def result(self, min_votes: int = 2) -> str | None:
        if not self.votes:
            return None
        choice, n = self.votes.most_common(1)[0]
        return choice if n >= min_votes else None


def beats(a: str, b: str) -> bool:
    return (a, b) in {("rock", "scissors"), ("scissors", "paper"), ("paper", "rock")}


def rps_result(owner: str, robot: str) -> str:
    """From the owner's point of view: win / lose / draw."""
    if owner == robot:
        return "draw"
    return "win" if beats(owner, robot) else "lose"
