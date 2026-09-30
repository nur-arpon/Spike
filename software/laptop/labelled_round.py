"""Short labelled comparison: a narrator names each voice, then ~12 s of that voice. Plays via the Windows default speaker."""
import sys, time, wave
from pathlib import Path
import numpy as np, sounddevice as sd
from kokoro_onnx import Kokoro
ROOT = Path(__file__).resolve().parent
FIN = ROOT / "voice_samples/lab/finalists"
k = Kokoro(str(ROOT / "models/kokoro/kokoro-v1.0.onnx"), str(ROOT / "models/kokoro/voices-v1.0.bin"))
DEV = next(i for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] > 0 and "Sound Mapper" in d["name"])
SR = 24000
def load(p):
    w = wave.open(str(p)); a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    assert w.getframerate() == SR; return a
def clip(a, start=9.0, stop=20.0, gap=0.3):
    # end at the first real pause (>= 0.3 s of near-silence) after 9 s, so no sentence is cut short
    win = int(0.02 * SR); quiet = 0.012; need = int(gap / 0.02); run = 0
    for i in range(int(start * SR), min(len(a), int(stop * SR)) - win, win):
        run = run + 1 if np.abs(a[i:i + win]).max() < quiet else 0
        if run >= need:
            return a[:i].copy()
    return a[:int(stop * SR)].copy()
who = sys.argv[1:] or ["spike", "spicy"]
for arg in who:
    w, _, letters = arg.partition(":")
    for L in (letters or "ABCD"):
        f = next(FIN.glob(f"{w} {L} - *.wav"))
        lab, _ = k.create(f"{w.title()}, voice {L}.", voice="bf_emma", speed=1.0, lang="en-gb")
        x = np.concatenate([lab * 0.8, np.zeros(int(0.5 * SR), np.float32), clip(load(f))])
        print(f"playing {w} {L}", flush=True)
        sd.play(x, SR, device=DEV); sd.wait(); time.sleep(1.8)
print("done")
