"""Chatterbox (MIT, local, GPU) auditions: expressive versions of the voices the owner approved.
Chatterbox copies the voice of a short reference clip (here the approved Kokoro samples) and adds emotion.
Plays each through the speakers (it says its own number first) and saves WAVs to voice_samples/chatterbox/."""
import sys, time
from pathlib import Path
import wave
import numpy as np, sounddevice as sd, torch
from chatterbox.tts import ChatterboxTTS

ROOT = Path(__file__).resolve().parent
KOK = ROOT / "voice_samples" / "kokoro"
OUT = ROOT / "voice_samples" / "chatterbox"; OUT.mkdir(parents=True, exist_ok=True)
NUM = ["one", "two", "three", "four", "five", "six"]
SPIKE = "Oh my gosh, you're home! I missed you so much. I even practised a new trick. Well... I fell over. But it was a really good fall!"
SPICY = "Oh. It's you. I wasn't waiting by the door or anything. Okay, maybe a little. Now pat me. Right now."
TAKES = {  # (reference clip, exaggeration, cfg_weight)
    "spike": [("spike new voice 1 - am_puck.wav", 0.55, 0.5), ("spike new voice 1 - am_puck.wav", 0.85, 0.35),
              ("spike new voice 2 - am_michael.wav", 0.7, 0.4)],
    "spicy": [("spicy new voice 1 - af_heart.wav", 0.6, 0.45), ("spicy new voice 2 - af_bella.wav", 0.8, 0.35),
              (None, 0.7, 0.4)],
}
t0 = time.time()
model = ChatterboxTTS.from_pretrained(device="cuda")
print(f"model loaded in {time.time()-t0:.1f}s, VRAM {torch.cuda.memory_allocated()/2**30:.2f} GB", flush=True)
for who in (sys.argv[1:] or ["spike", "spicy"]):
    for i, (ref, ex, cfg) in enumerate(TAKES[who]):
        text = f"{who.title()}, chatterbox voice {NUM[i]}. " + (SPIKE if who == "spike" else SPICY)
        t = time.time()
        wav = model.generate(text, audio_prompt_path=str(KOK / ref) if ref else None, exaggeration=ex, cfg_weight=cfg)
        gen = time.time() - t
        pcm = wav.squeeze(0).cpu().numpy()
        name = f"{who} chatterbox voice {i+1} - {(ref or 'default').split(' - ')[-1].replace('.wav','')} ex{ex}.wav"
        with wave.open(str(OUT / name), "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(model.sr)
            wf.writeframes((np.clip(pcm, -1, 1) * 32767).astype(np.int16).tobytes())
        print(f"playing {who} chatterbox voice {i+1} (ref {ref}, exaggeration {ex}) - made {len(pcm)/model.sr:.1f}s of audio in {gen:.1f}s", flush=True)
        sd.play(pcm, model.sr); sd.wait(); time.sleep(1.5)
print(f"peak VRAM {torch.cuda.max_memory_allocated()/2**30:.2f} GB")
print("done")
