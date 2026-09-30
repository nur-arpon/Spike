"""Download the two MediaPipe vision models Spike's eyes use (~12 MB total).

Source: Google's official MediaPipe model bucket (the URLs in the MediaPipe
docs). Saved to software/laptop/models/mediapipe/. Safe to re-run.

    python -m spike_brain.tools.fetch_models
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from ..config import LAPTOP_DIR

MODELS = {
    "face_landmarker.task":
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    "gesture_recognizer.task":
        "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
}


def main() -> int:
    dest = LAPTOP_DIR / "models" / "mediapipe"
    dest.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, url in MODELS.items():
        path = dest / name
        if path.exists() and path.stat().st_size > 100_000:
            print(f"{name}: already there ({path.stat().st_size // 1024} KB)")
            continue
        print(f"{name}: downloading from {url}")
        tmp = path.with_suffix(".part")
        try:
            urllib.request.urlretrieve(url, tmp)
            if tmp.stat().st_size < 100_000:
                raise OSError("file too small - not a model")
            tmp.replace(path)
            print(f"{name}: done ({path.stat().st_size // 1024} KB)")
        except OSError as e:
            ok = False
            print(f"{name}: FAILED ({e})")
            if tmp.exists():
                tmp.unlink()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
