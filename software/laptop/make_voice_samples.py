"""Render one sample line per candidate Piper voice so the owner can pick Spike's and Spicy's voices."""
import wave
from pathlib import Path
from piper import PiperVoice

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "voice_samples"
OUT.mkdir(exist_ok=True)
LINES = {
    "spike": "Hi! I'm Spike. I have tiny legs and very big dreams. Welcome home, I missed you so much!",
    "spicy": "Hi, I'm Spicy. Yes, I heard you. No, I'm not coming. Okay, fine. One pat. Just one.",
}
for who, line in LINES.items():
    for i, model in enumerate(sorted((ROOT / "models" / "piper" / who).glob("*.onnx")), 1):
        voice = PiperVoice.load(str(model))
        out = OUT / f"{who} voice {i} - {model.stem}.wav"
        with wave.open(str(out), "wb") as wf:
            voice.synthesize_wav(line, wf)
        print(out.name, out.stat().st_size)
