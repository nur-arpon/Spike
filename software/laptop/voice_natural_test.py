"""Natural-speech test: fillers, little laughs/sighs, and real pauses between phrases.
Standard Chatterbox (emotion control) vs Chatterbox Turbo (faster, [laugh]/[sigh] tags), for Spike and Spicy.
Plays through the Windows default speaker and saves to voice_samples/natural/."""
import re, time, wave
from pathlib import Path
import numpy as np, sounddevice as sd, torch

ROOT = Path(__file__).resolve().parent
S = ROOT / "voice_samples"
OUT = S / "natural"; OUT.mkdir(parents=True, exist_ok=True)
DEV = next(i for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] > 0 and "Sound Mapper" in d["name"])

SPIKE = ("Oh! Hey... you're home! Umm, I missed you. Like, so much. [laugh] "
         "I even practised a new trick. Well... I kinda fell over. [chuckle] But hey, it was a really good fall!")
SPICY = ("Oh. It's you. [sigh] I wasn't waiting by the door or anything. "
         "Okay... fine. Maybe a little. Hmm. Now pat me. Right now, please.")
GAP = {"...": 0.45, ".": 0.32, "!": 0.28, "?": 0.3}   # seconds of silence after each phrase

def phrases(text, keep_tags):
    if not keep_tags:
        text = re.sub(r"\s*\[[a-z]+\]\s*", " ", text)
    parts = re.findall(r"[^.!?]+(?:\.\.\.|[.!?])?(?:\s*\[[a-z]+\])?", text)
    return [p.strip() for p in parts if p.strip()]

def trim(x, sr, thr=0.01):
    idx = np.where(np.abs(x) > thr)[0]
    return x[max(0, idx[0] - int(0.03 * sr)): idx[-1] + int(0.06 * sr)] if len(idx) else x

def speak(gen, text, sr, keep_tags):
    out = []
    for p in phrases(text, keep_tags):
        x = trim(gen(p).squeeze(0).cpu().numpy(), sr)
        end = p.rstrip()
        end = re.sub(r"\s*\[[a-z]+\]$", "", end)
        gap = next((g for k, g in GAP.items() if end.endswith(k)), 0.25)
        out += [x, np.zeros(int(gap * sr), np.float32)]
    return np.concatenate(out)

def save_play(name, x, sr, label):
    with wave.open(str(OUT / f"{name}.wav"), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    print("playing", label, flush=True)
    sd.play(x.astype(np.float32), sr, device=DEV); sd.wait(); time.sleep(1.5)

results = {}
from chatterbox.tts import ChatterboxTTS
m = ChatterboxTTS.from_pretrained(device="cuda")
for who, text, ref, ex in [("spike", SPIKE, S / "kokoro/spike new voice 1 - am_puck.wav", 0.85),
                           ("spicy", SPICY, S / "kokoro/spicy new voice 1 - af_heart.wav", 0.6)]:
    t = time.time()
    intro = m.generate(f"{who.title()}, natural voice one.", audio_prompt_path=str(ref), exaggeration=ex, cfg_weight=0.3)
    x = speak(lambda p: m.generate(p, audio_prompt_path=str(ref), exaggeration=ex, cfg_weight=0.3), text, m.sr, keep_tags=False)
    results[f"{who} standard"] = (time.time() - t, len(x) / m.sr)
    save_play(f"{who} natural voice 1 - chatterbox", np.concatenate([trim(intro.squeeze(0).cpu().numpy(), m.sr), np.zeros(int(0.6*m.sr), np.float32), x]), m.sr, f"{who} natural voice 1 (standard)")
del m; torch.cuda.empty_cache(); torch.cuda.reset_peak_memory_stats()

from chatterbox.tts_turbo import ChatterboxTurboTTS
t0 = time.time(); tm = ChatterboxTurboTTS.from_pretrained(device="cuda"); print(f"turbo loaded {time.time()-t0:.0f}s", flush=True)
for who, text, ref in [("spike", SPIKE, S / "chatterbox/spike chatterbox voice 2 - am_puck ex0.85.wav"),
                       ("spicy", SPICY, S / "chatterbox/spicy chatterbox voice 1 - af_heart ex0.6.wav")]:
    t = time.time()
    intro = tm.generate(f"{who.title()}, natural voice two.", audio_prompt_path=str(ref))
    x = speak(lambda p: tm.generate(p, audio_prompt_path=str(ref)), text, tm.sr, keep_tags=True)
    results[f"{who} turbo"] = (time.time() - t, len(x) / tm.sr)
    save_play(f"{who} natural voice 2 - turbo", np.concatenate([trim(intro.squeeze(0).cpu().numpy(), tm.sr), np.zeros(int(0.6*tm.sr), np.float32), x]), tm.sr, f"{who} natural voice 2 (turbo)")
print(f"turbo peak VRAM {torch.cuda.max_memory_allocated()/2**30:.2f} GB")
for k, (g, a) in results.items(): print(f"{k}: {g:.1f}s to make {a:.1f}s of speech")
print("done")
