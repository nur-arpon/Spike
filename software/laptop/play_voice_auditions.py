"""Play every candidate voice out loud, with Spike's/Spicy's real pitch and speed, so the owner can pick.
Each clip says its own number first. Also saves them to voice_samples/tuned/."""
import sys, time, wave, tomllib
from pathlib import Path
import numpy as np, sounddevice as sd
from spike_brain.speech.tts import PiperTTS

ROOT = Path(__file__).resolve().parent
CFG = ROOT / "spike_brain" / "config" / "personas"
OUT = ROOT / "voice_samples" / "tuned"; OUT.mkdir(parents=True, exist_ok=True)
NUM = ["one", "two", "three", "four", "five", "six", "seven", "eight"]
LINES = {
    "spike": "Hi! I'm Spike. I have tiny legs and very big dreams. Welcome home, I missed you so much!",
    "spicy": "Hi, I'm Spicy. Yes, I heard you. No, I'm not coming. Okay, fine. One pat. Just one.",
}
who_list = sys.argv[1:] or ["spike", "spicy"]
for who in who_list:
    voice_cfg = tomllib.loads((CFG / f"{who}.toml").read_text(encoding="utf-8")).get("voice", {})
    pitch, speed = voice_cfg.get("pitch", 1.0), voice_cfg.get("speed", 1.0)
    for i, model in enumerate(sorted((ROOT / "models" / "piper" / who).glob("*.onnx"))):
        tts = PiperTTS(model, pitch=pitch, speed=speed)
        sp = tts.synthesize(f"{who.title()}, voice {NUM[i]}. {LINES[who]}")
        with wave.open(str(OUT / f"{who} voice {i+1} - {model.stem}.wav"), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sp.rate); wf.writeframes(sp.pcm.astype(np.int16).tobytes())
        print(f"playing {who} voice {i+1} ({model.stem})", flush=True)
        sd.play(sp.pcm.astype(np.int16), sp.rate); sd.wait(); time.sleep(1.5)
print("done")
