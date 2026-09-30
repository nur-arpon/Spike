"""Download the offline speech models Spike's laptop brain needs.

Owner approved these installs on 2026-09-26 (about 2-3 GB of models).
Everything goes under software/laptop/models/ so the project is self-contained.
Safe to re-run: files that are already present are skipped.
"""
import sys, zipfile, urllib.request
from pathlib import Path
from huggingface_hub import hf_hub_download, snapshot_download

ROOT = Path(__file__).resolve().parent / "models"
ROOT.mkdir(exist_ok=True)

def log(msg):
    print(msg, flush=True)

# 1. Speech-to-text (faster-whisper, CTranslate2 format)
for size in ("base.en", "small.en"):
    dest = ROOT / "whisper" / size
    if (dest / "model.bin").exists():
        log(f"whisper {size}: already there"); continue
    log(f"whisper {size}: downloading")
    snapshot_download(f"Systran/faster-whisper-{size}", local_dir=dest)
    log(f"whisper {size}: done")

# 2. Text-to-speech (Piper). Candidates to audition - the owner picks the final voices.
PIPER = {
    "spike": ["en_US-ryan-medium", "en_US-joe-medium", "en_US-danny-low", "en_GB-alan-medium"],
    "spicy": ["en_US-amy-medium", "en_GB-jenny_dioco-medium", "en_US-kristin-medium", "en_US-hfc_female-medium"],
}
for who, voices in PIPER.items():
    for v in voices:
        lang, rest = v.split("-", 1)
        name, quality = rest.rsplit("-", 1)
        sub = f"{lang.split('_')[0]}/{lang}/{name}/{quality}"
        dest = ROOT / "piper" / who
        dest.mkdir(parents=True, exist_ok=True)
        if (dest / f"{v}.onnx").exists():
            log(f"piper {v}: already there"); continue
        try:
            for ext in (".onnx", ".onnx.json"):
                hf_hub_download("rhasspy/piper-voices", f"{sub}/{v}{ext}", local_dir=ROOT / "piper" / "_hf")
                src = ROOT / "piper" / "_hf" / sub / f"{v}{ext}"
                (dest / f"{v}{ext}").write_bytes(src.read_bytes())
            log(f"piper {v}: done")
        except Exception as e:
            log(f"piper {v}: SKIPPED ({type(e).__name__}: {e})")

# 3. Keyword spotting for the custom wake words (Vosk small English, ~40 MB)
vosk_dir = ROOT / "vosk" / "vosk-model-small-en-us-0.15"
if not vosk_dir.exists():
    log("vosk: downloading")
    zp = ROOT / "vosk" / "small.zip"
    zp.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve("https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip", zp)
    with zipfile.ZipFile(zp) as z:
        z.extractall(ROOT / "vosk")
    zp.unlink()
    log("vosk: done")
else:
    log("vosk: already there")

# 4. openWakeWord shared feature models (melspectrogram + embedding + VAD)
try:
    import openwakeword.utils as oww
    oww.download_models(target_directory=str(ROOT / "openwakeword"))
    log("openwakeword: done")
except Exception as e:
    log(f"openwakeword: SKIPPED ({type(e).__name__}: {e})")

log("ALL DONE")
