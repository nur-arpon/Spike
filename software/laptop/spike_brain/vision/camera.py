"""Camera sources behind one interface: the laptop webcam now, the robot's
camera board (protocol `camera` JPEG frames) later. Frames live in memory
only; nothing is written to disk unless debug.save_frames is on.
"""
from __future__ import annotations

import logging
import threading
import time

import numpy as np

log = logging.getLogger("spike.camera")


class CameraSource:
    name = "none"

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def latest(self) -> tuple[np.ndarray | None, float, int]:
        """(BGR frame or None, capture time, sequence number)."""
        raise NotImplementedError


class WebcamSource(CameraSource):
    name = "webcam"

    def __init__(self, index: int = 0, width: int = 640, height: int = 480):
        self.index, self.width, self.height = index, width, height
        self._frame: np.ndarray | None = None
        self._t = 0.0
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.cap = None
        self.ok = False

    def start(self) -> None:
        import cv2
        backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(self.index, backend)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            raise RuntimeError(f"webcam {self.index} could not be opened")
        # MJPG + 30 fps: many laptop webcams otherwise fall back to ~5 fps raw YUV
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.ok = True
        self._thread = threading.Thread(target=self._run, name="webcam", daemon=True)
        self._thread.start()
        log.info("webcam %d opened (%dx%d)", self.index,
                 int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    def _run(self) -> None:
        fails = 0
        while not self._stop.is_set():
            ok, frame = self.cap.read()
            if not ok:
                fails += 1
                if fails > 50:
                    log.warning("webcam stopped delivering frames")
                    self.ok = False
                    return
                time.sleep(0.05)
                continue
            fails = 0
            with self._lock:
                self._frame, self._t = frame, time.monotonic()
                self._seq += 1

    def latest(self):
        with self._lock:
            return self._frame, self._t, self._seq

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.5)
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class RemoteCameraSource(CameraSource):
    """JPEG frames from the robot's camera board."""
    name = "robot-camera"

    def __init__(self):
        self._jpeg: bytes | None = None
        self._frame: np.ndarray | None = None
        self._t = 0.0
        self._seq = 0
        self._decoded_seq = -1
        self._lock = threading.Lock()

    def push_jpeg(self, data: bytes, seq: int | None = None) -> None:
        with self._lock:
            self._jpeg = data
            self._t = time.monotonic()
            self._seq = seq if seq is not None else self._seq + 1

    def latest(self):
        import cv2
        with self._lock:
            jpeg, t, seq = self._jpeg, self._t, self._seq
        if jpeg is None:
            return None, 0.0, 0
        if seq != self._decoded_seq:
            frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            self._frame, self._decoded_seq = frame, seq
        return self._frame, t, seq
