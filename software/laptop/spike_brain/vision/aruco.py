"""The "home spot": a printed ArUco marker on the desk, for the future
return-home behaviour. Gives distance and bearing from the camera; without
a calibration the focal length is estimated from the horizontal field of
view (config aruco.horizontal_fov_deg), which is good to ~10 %.

Print the marker with:  python -m spike_brain.tools.make_marker
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass
class MarkerPose:
    marker_id: int
    distance_m: float
    bearing_deg: float          # + = marker is to the right of the camera's centre line
    center_px: tuple[float, float]
    size_px: float


class HomeMarkerDetector:
    def __init__(self, dictionary: str = "DICT_4X4_50", marker_id: int = 7, marker_size_m: float = 0.05,
                 horizontal_fov_deg: float = 70.0):
        import cv2
        self.cv2 = cv2
        self.marker_id = marker_id
        self.size_m = marker_size_m
        self.hfov = math.radians(horizontal_fov_deg)
        d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
        self.detector = cv2.aruco.ArucoDetector(d, cv2.aruco.DetectorParameters())

    def camera_matrix(self, w: int, h: int) -> np.ndarray:
        f = (w / 2) / math.tan(self.hfov / 2)
        return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], dtype=np.float64)

    def detect(self, frame_bgr: np.ndarray) -> MarkerPose | None:
        cv2 = self.cv2
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr
        corners, ids, _ = self.detector.detectMarkers(gray)
        if ids is None:
            return None
        for c, i in zip(corners, ids.flatten()):
            if int(i) != self.marker_id:
                continue
            pts = c.reshape(4, 2).astype(np.float64)
            h, w = gray.shape[:2]
            k = self.camera_matrix(w, h)
            s = self.size_m / 2
            obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64)
            ok, rvec, tvec = cv2.solvePnP(obj, pts, k, None, flags=cv2.SOLVEPNP_IPPE_SQUARE)
            if not ok:
                return None
            x, _, z = tvec.flatten()
            center = pts.mean(axis=0)
            side = float(np.mean([np.linalg.norm(pts[j] - pts[(j + 1) % 4]) for j in range(4)]))
            return MarkerPose(int(i), float(np.linalg.norm(tvec)), math.degrees(math.atan2(x, z)),
                              (float(center[0]), float(center[1])), side)
        return None


def make_marker_image(marker_id: int = 7, dictionary: str = "DICT_4X4_50", pixels: int = 600) -> np.ndarray:
    import cv2
    d = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, dictionary))
    img = cv2.aruco.generateImageMarker(d, marker_id, pixels)
    border = pixels // 6
    return cv2.copyMakeBorder(img, border, border, border, border, cv2.BORDER_CONSTANT, value=255)
