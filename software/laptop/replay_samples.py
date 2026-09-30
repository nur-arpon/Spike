"""Replay saved voice samples through the speakers, in order. Usage: replay_samples.py <folder> [filter]"""
import sys, time, wave
from pathlib import Path
import numpy as np, sounddevice as sd
folder = Path(__file__).resolve().parent / "voice_samples" / sys.argv[1]
flt = sys.argv[2] if len(sys.argv) > 2 else ""
# Pick the output by NAME (indices shift when SteelSeries Sonar reconnects). The Sound Mapper follows the Windows
# default speaker; PortAudio's own default was Sonar's virtual *microphone* sink, which nobody can hear.
DEV = next(i for i, d in enumerate(sd.query_devices()) if d["max_output_channels"] > 0 and "Sound Mapper" in d["name"])
files = sorted(folder.glob("*.wav"), key=lambda p: (not p.name.startswith("spike"), p.name))
for f in files:
    if flt not in f.name: continue
    with wave.open(str(f)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16); sr = w.getframerate()
    print("playing", f.name, flush=True)
    sd.play(pcm, sr, device=DEV); sd.wait(); time.sleep(1.5)
print("done")
