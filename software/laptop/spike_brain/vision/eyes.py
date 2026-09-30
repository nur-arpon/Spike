"""Spike's eyes: one thread that looks at camera frames a few times a second.

  face landmarks + blendshapes -> presence (arrived / left), emotion
                                  (happy / sad / tired), where to look
  hand gestures                -> rock / paper / scissors (only while a round
                                  is waiting for "shoot!", to save CPU)
  ArUco marker                 -> home spot distance and bearing (1 Hz)

Events go to on_event(kind, data) from this thread; the brain marshals them
onto its event loop.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .camera import CameraSource
from .signals import EmotionEstimator, Presence, RpsVote, classify_rps

log = logging.getLogger("spike.eyes")


class Eyes:
    def __init__(self, source: CameraSource, *, face_model: Path, gesture_model: Path,
                 on_event: Callable[[str, Any], None], process_fps: float = 8, look_at_hz: float = 10,
                 present_after_s: float = 1.0, absent_after_s: float = 25, emotion_window_s: float = 8,
                 sad_threshold: float = 0.45, tired_threshold: float = 0.55, mirror: bool = False,
                 aruco=None, debug_dir: Path | None = None):
        self.source = source
        self.face_model, self.gesture_model = Path(face_model), Path(gesture_model)
        self.on_event = on_event
        self.period = 1.0 / max(1.0, process_fps)
        self.look_period = 1.0 / max(1.0, look_at_hz)
        self.presence = Presence(present_after_s, absent_after_s)
        self.emotion = EmotionEstimator(window_s=emotion_window_s, sad_threshold=sad_threshold,
                                        tired_threshold=tired_threshold)
        self.mirror = mirror
        self.aruco = aruco
        self.debug_dir = debug_dir
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._rps_until = 0.0
        self._rps_vote: RpsVote | None = None
        self._rps_lock = threading.Lock()
        self.face = None
        self.gestures = None
        self.last_face_t = 0.0
        self.home = None

    def _load(self) -> None:
        from mediapipe.tasks.python import BaseOptions, vision
        self.face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.face_model)),
            running_mode=vision.RunningMode.VIDEO, num_faces=1, output_face_blendshapes=True,
            min_face_detection_confidence=0.5, min_face_presence_confidence=0.5, min_tracking_confidence=0.5))
        if self.gesture_model.exists():
            self.gestures = vision.GestureRecognizer.create_from_options(vision.GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_path=str(self.gesture_model)),
                running_mode=vision.RunningMode.VIDEO, num_hands=1))

    def start(self) -> None:
        if not self.face_model.exists():
            raise FileNotFoundError(f"{self.face_model} missing - run: python -m spike_brain.tools.fetch_models")
        self._load()
        self.source.start()
        self._thread = threading.Thread(target=self._run, name="eyes", daemon=True)
        self._thread.start()
        log.info("eyes open (%s, %.0f fps processing)", self.source.name, 1 / self.period)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.source.stop()
        for m in (self.face, self.gestures):
            try:
                if m is not None:
                    m.close()
            except Exception:  # noqa: BLE001
                pass

    def start_rps_window(self, seconds: float = 1.4) -> None:
        with self._rps_lock:
            self._rps_vote = RpsVote()
            self._rps_until = time.monotonic() + seconds

    def _run(self) -> None:
        import cv2
        import mediapipe as mp
        t0 = time.monotonic()
        last_ts = -1
        last_seq = -1
        last_look = 0.0
        last_aruco = 0.0
        while not self._stop.is_set():
            loop_start = time.monotonic()
            frame, t_cap, seq = self.source.latest()
            if frame is None or seq == last_seq:
                self._rps_tick(None, time.monotonic())
                time.sleep(0.02)
                continue
            last_seq = seq
            try:
                if self.mirror:
                    frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = max(last_ts + 1, int((time.monotonic() - t0) * 1000))
                last_ts = ts
                now = time.monotonic()
                res = self.face.detect_for_video(image, ts)
                seen = bool(res.face_landmarks)
                ev = self.presence.update(seen, now)
                if ev:
                    self.on_event("presence", ev)
                if seen:
                    self.last_face_t = now
                    if res.face_blendshapes:
                        bs = {c.category_name: c.score for c in res.face_blendshapes[0]}
                        label = self.emotion.update(bs, now)
                        if label:
                            self.on_event("emotion", label)
                    if now - last_look >= self.look_period:
                        nose = res.face_landmarks[0][1]
                        x = max(-1.0, min(1.0, nose.x * 2 - 1))
                        y = max(-1.0, min(1.0, (nose.y * 2 - 1) * 0.8))
                        self.on_event("look", (x, y))
                        last_look = now
                else:
                    self.emotion.no_face(now)
                if self.gestures is not None and self._rps_active(now):
                    g = self.gestures.recognize_for_video(image, ts)
                    name, score, lms = None, 0.0, None
                    if g.gestures:
                        top = g.gestures[0][0]
                        name, score = top.category_name, top.score
                    if g.hand_landmarks:
                        lms = [(p.x, p.y) for p in g.hand_landmarks[0]]
                    self._rps_tick(classify_rps(name, score, lms), now)
                else:
                    self._rps_tick(None, now)
                if self.aruco is not None and now - last_aruco >= 1.0:
                    last_aruco = now
                    pose = self.aruco.detect(frame)
                    if (pose is None) != (self.home is None):
                        self.on_event("home_marker", pose)
                    self.home = pose
            except Exception:  # noqa: BLE001 - keep looking
                log.exception("vision frame failed")
            spare = self.period - (time.monotonic() - loop_start)
            if spare > 0:
                time.sleep(spare)

    def _rps_active(self, now: float) -> bool:
        with self._rps_lock:
            return self._rps_vote is not None and now <= self._rps_until

    def _rps_tick(self, choice: str | None, now: float) -> None:
        with self._rps_lock:
            if self._rps_vote is None:
                return
            if now <= self._rps_until:
                self._rps_vote.add(choice)
                return
            result = self._rps_vote.result(min_votes=2)
            self._rps_vote = None
        self.on_event("rps", result)
