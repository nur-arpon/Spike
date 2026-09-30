"""Kokoro (modern neural TTS, Apache-2.0, runs locally) auditions for Spike and Spicy.
Plays each voice through the speakers (it says its own number first) and saves WAVs to voice_samples/kokoro/."""
import sys, time, wave
from pathlib import Path
import numpy as np, sounddevice as sd
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "voice_samples" / "kokoro"; OUT.mkdir(parents=True, exist_ok=True)
k = Kokoro(str(ROOT / "models/kokoro/kokoro-v1.0.onnx"), str(ROOT / "models/kokoro/voices-v1.0.bin"))
NUM = ["one", "two", "three", "four", "five", "six"]
SETS = {
    "spike": (["am_puck", "am_michael", "bm_fable", "am_fenrir", "am_echo"],
              "Hi! I'm Spike. I have tiny legs and very big dreams. Welcome home, I missed you so much!"),
    "spicy": (["af_heart", "af_bella", "af_nicole", "bf_emma", "af_sky"],
              "Hi, I'm Spicy. Yes, I heard you. No, I'm not coming. Okay, fine. One pat. Just one."),
}
if sys.argv[1:2] == ["list"]:
    print(sorted(k.get_voices())); sys.exit()
for who in (sys.argv[1:] or ["spike", "spicy"]):
    voices, line = SETS[who]
    for i, v in enumerate(voices):
        pcm, sr = k.create(f"{who.title()}, new voice {NUM[i]}. {line}", voice=v, speed=1.0, lang="en-us" if v[0] == "a" else "en-gb")
        pcm16 = (np.clip(pcm, -1, 1) * 32767).astype(np.int16)
        with wave.open(str(OUT / f"{who} new voice {i+1} - {v}.wav"), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr); wf.writeframes(pcm16.tobytes())
        print(f"playing {who} new voice {i+1} ({v})", flush=True)
        sd.play(pcm16, sr); sd.wait(); time.sleep(1.5)
print("done")
