"""Say 'test one', 'test two', ... through each audio output in turn, so the owner can say which he hears."""
import time
import numpy as np, sounddevice as sd
from kokoro_onnx import Kokoro
from pathlib import Path
ROOT = Path(__file__).resolve().parent
k = Kokoro(str(ROOT / "models/kokoro/kokoro-v1.0.onnx"), str(ROOT / "models/kokoro/voices-v1.0.bin"))
DEVICES = [3, 8, 9, 6, 5]   # Sound Mapper (Windows default), Sonar Media, Realtek speakers, Sonar Gaming, monitor
NUM = ["one", "two", "three", "four", "five"]
for n, dev in zip(NUM, DEVICES):
    pcm, sr = k.create(f"Test {n}.", voice="am_puck", speed=1.0, lang="en-us")
    name = sd.query_devices(dev)["name"]
    print(f"test {n} -> device {dev}: {name}", flush=True)
    try:
        sd.play((np.clip(pcm, -1, 1) * 32767).astype(np.int16), sr, device=dev); sd.wait()
    except Exception as e:
        print("   failed:", e, flush=True)
    time.sleep(1.2)
print("done")
