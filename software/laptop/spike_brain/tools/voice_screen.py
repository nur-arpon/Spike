"""Scores voice clips for the cache builder (tools/build_voice_cache.py). Runs in the
voice lab's scoring Python (voice_lab/.venv-score: UTMOSv2 + faster-whisper), NOT
in the brain's .venv. Standalone: imports nothing from spike_brain.

    <.venv-score python> voice_screen.py jobs.json results.json [--no-utmos]

jobs.json: [{"id": "...", "file": "path.wav", "text": "words the listener must hear"}]
results.json: {id: {"utmos", "heard", "wer", "wpm", "duration_s", "speech_s", "digits_ok"}}

UTMOSv2 is the lab's naturalness predictor (calibrated against the owner's own
verdicts, software/research/voice/lab_results.md section 1): loudness-matched to
-20 dBFS and averaged over 5 passes, exactly as voice_lab/score.py does.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

LAPTOP = Path(__file__).resolve().parents[2]
LAB = LAPTOP / "voice_lab"
os.environ.setdefault("HF_HUB_CACHE", str(LAB / "hf_cache"))
os.environ.setdefault("UTMOSV2_CHACHE", str(LAB / "utmosv2_cache"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402

FILLERS = {"um", "uh", "hmm", "huh", "oh", "ugh", "mm", "mmm", "mrrp", "meow", "ahh", "ah", "aww", "phew", "psst",
           "nom", "purr", "hellooo", "ooh", "yay", "ha", "hm"}
LAUGH = re.compile(r"^(h+a+)+h?$|^(h+e+)+h?$|^heh+$|^m+h?m+$")
NUMWORDS = {"zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
            "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
            "fourteen": "14", "fifteen": "15", "sixteen": "16", "twenty": "20"}


def words(text: str) -> list[str]:
    t = text.lower().replace("’", "'").replace("-", " ")
    out = []
    for w in re.findall(r"[a-z0-9']+", t):
        w = w.strip("'")
        if w and w not in FILLERS and not LAUGH.match(w):
            out.append(w)
    return out


def wer(ref: list[str], hyp: list[str]) -> float:
    if not ref:
        return 0.0
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
            prev, d[j] = d[j], cur
    return d[len(hyp)] / len(ref)


def digit_string(text: str) -> str:
    """'13 11 14 ... 000' and 'thirteen eleven fourteen ... triple zero' -> '131114000'."""
    t = text.lower().replace("triple zero", "000").replace("triple 0", "000").replace("double", "")
    out = []
    for w in re.findall(r"[a-z]+|\d+", t):
        if w.isdigit():
            out.append(w)
        elif w in NUMWORDS and w != "oh":
            out.append(NUMWORDS[w])
    return "".join(out)


def load16(path: str):
    """16-bit WAV -> (float32 at 16 kHz, duration s). Only wave + scipy, so it runs in either venv."""
    import wave
    from fractions import Fraction
    from scipy.signal import resample_poly
    with wave.open(path, "rb") as w:
        ch, sr = w.getnchannels(), w.getframerate()
        y = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    if ch > 1:
        y = y.reshape(-1, ch).mean(axis=1)
    dur = len(y) / sr
    if sr != 16000:
        f = Fraction(16000, sr).limit_denominator(1000)
        y = resample_poly(y, f.numerator, f.denominator).astype(np.float32)
    return y, dur


def speech_span(y16: np.ndarray, sr: int = 16000) -> float:
    """Seconds from the first to the last voiced 20 ms frame (30 dB below the loud frames)."""
    w = sr // 50
    n = len(y16) // w
    if n == 0:
        return 0.0
    rms = np.sqrt((y16[: n * w].reshape(n, w) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    idx = np.where(db > max(np.percentile(db, 95) - 30, -60))[0]
    return 0.0 if len(idx) == 0 else (idx[-1] - idx[0] + 1) * w / sr


def main(argv: list[str]) -> int:
    jobs = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out_path = Path(argv[2])
    use_utmos = "--no-utmos" not in argv
    try:
        import torch
        lib = Path(torch.__file__).parent / "lib"      # ctranslate2 needs cuBLAS/cuDNN: reuse torch's DLLs
        if os.name == "nt" and lib.exists():
            os.add_dll_directory(str(lib))
            os.environ["PATH"] = str(lib) + os.pathsep + os.environ["PATH"]
        dev = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:                                # the brain's .venv (no torch): Whisper only, on the CPU
        torch, dev, use_utmos = None, "cpu", False
    t = time.time()
    utmos = None
    if use_utmos:
        import utmosv2
        utmos = utmosv2.create_model(pretrained=True, device="cuda:0" if dev == "cuda" else "cpu")
    from faster_whisper import WhisperModel
    wdir = str(LAPTOP / "models" / "whisper" / "small.en")
    try:
        whisper = WhisperModel(wdir, device=dev, compute_type="float16" if dev == "cuda" else "int8")
    except Exception:  # noqa: BLE001
        whisper = WhisperModel(wdir, device="cpu", compute_type="int8")
    print(f"screen: models loaded in {time.time() - t:.0f} s ({dev}); {len(jobs)} clips", flush=True)
    res = {}
    for i, j in enumerate(jobs):
        y16, dur = load16(j["file"])
        r = {"duration_s": round(dur, 2)}
        if utmos is not None:
            y = np.clip(y16 * (0.1 / (float(np.sqrt((y16 ** 2).mean())) + 1e-9)), -1, 1).astype(np.float32)
            r["utmos"] = round(float(utmos.predict(data=torch.from_numpy(y), sr=16000,
                                                   device="cuda:0" if dev == "cuda" else "cpu", num_workers=0,
                                                   num_repetitions=5, verbose=False)), 3)
        segs, _ = whisper.transcribe(y16, language="en", beam_size=5, condition_on_previous_text=False,
                                     vad_filter=False)
        heard = " ".join(s.text.strip() for s in segs).strip()
        ref, hyp = words(j["text"]), words(heard)
        span = speech_span(y16)
        r.update(heard=heard, wer=round(wer(ref, hyp), 3), ref_words=len(ref), speech_s=round(span, 2),
                 wpm=round(60 * len(hyp) / span) if span > 0.3 else None)
        want_digits = digit_string(j["text"])
        if re.search(r"\d", j["text"]):
            r["digits_ok"] = bool(want_digits) and want_digits in digit_string(heard)
        res[j["id"]] = r
        if (i + 1) % 25 == 0:
            print(f"screen: {i + 1}/{len(jobs)}", flush=True)
            out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("screen: done", flush=True)
    return 0


if __name__ == "__main__":
    code = main(sys.argv)
    sys.stdout.flush()
    os._exit(code)
