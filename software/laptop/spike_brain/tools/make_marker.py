"""Print Spike's "home spot" marker (ArUco DICT_4X4_50, id from config).

    python -m spike_brain.tools.make_marker

Writes software/laptop/data/home_marker_<id>.png. Print it so the black
square is exactly aruco.marker_size_m wide (default 5 cm) and tape it where
Spike should return to. The camera then reports its distance and bearing.
"""
from __future__ import annotations

import sys

from ..config import Settings
from ..vision.aruco import make_marker_image


def main() -> int:
    import cv2
    s = Settings.load()
    out = s.path("data") / f"home_marker_{s.aruco.home_marker_id}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), make_marker_image(s.aruco.home_marker_id, s.aruco.dictionary))
    print(f"wrote {out} - print it with the black square {s.aruco.marker_size_m * 100:.0f} cm wide")
    return 0


if __name__ == "__main__":
    sys.exit(main())
