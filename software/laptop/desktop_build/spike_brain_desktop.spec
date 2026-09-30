# PyInstaller spec: Spike's LIGHT brain for the Windows desktop app (software/app/DESIGN.md "Desktop").
#
# Build (from software/laptop):  .\desktop_build\build_brain.ps1
# Uses the CPU-only venv software/laptop/.venv-desktop (no torch, no CUDA, no Ollama, no webcam
# stack). Output: desktop_build/dist/brain/ (onedir) = spike_brain.exe + _internal/, plus the
# models folder the build script copies next to it. The desktop app starts it with
#   spike_brain.exe --profile desktop --home <app data> --models <this folder>\models
#                   --parent-pid <app pid> --stop-on-stdin-eof --port <p> --log-file logs\brain.log
# -*- mode: python -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

HERE = Path(SPECPATH)                    # software/laptop/desktop_build
LAPTOP = HERE.parent                     # software/laptop

datas = [
    (str(LAPTOP / "spike_brain" / "config" / "default.toml"), "spike_brain/config"),
    (str(LAPTOP / "spike_brain" / "config" / "desktop.toml"), "spike_brain/config"),
    (str(LAPTOP / "spike_brain" / "config" / "personas"), "spike_brain/config/personas"),
]
datas += collect_data_files("faster_whisper")          # its own assets (tokenizer bits, VAD model)
binaries = collect_dynamic_libs("vosk") + collect_dynamic_libs("ctranslate2")
# ctranslate2 ships a CUDA cuDNN stub; the light brain runs Whisper on the processor only
binaries = [b for b in binaries if "cudnn" not in Path(b[0]).name.lower()]

hiddenimports = [
    "spike_brain.speech.gemini_tts", "spike_brain.speech.windows_tts",
    "comtypes", "comtypes.client", "comtypes.automation",
    "zeroconf._utils.ipaddress", "zeroconf._handlers.answers",
    "websockets.asyncio.server", "websockets.asyncio.client",
]

excludes = [
    # never part of the light brain (the later on-device AI pack brings its own build)
    "torch", "torchaudio", "chatterbox", "kokoro_onnx", "piper", "mediapipe", "cv2", "ollama",
    "matplotlib", "tkinter", "IPython", "pytest", "sklearn", "pandas", "PIL.ImageQt",
    "av",          # FFmpeg: only for decoding audio FILES, which the brain never does (rthook_av_stub.py)
    "hf_xet",      # Hugging Face download accelerator: the light brain downloads nothing
    "spike_brain.tests", "spike_brain.tools",
]

a = Analysis(
    [str(HERE / "entry.py")],
    pathex=[str(LAPTOP)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    runtime_hooks=[str(HERE / "rthook_av_stub.py")],
    noarchive=False,
    # python-zeroconf is LGPL-2.1: kept as plain .py files (not inside the archive) so it can be replaced
    module_collection_mode={"zeroconf": "py"},
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="spike_brain",
    console=False,                       # a background helper: never a console window
    disable_windowed_traceback=True,
    icon=str(HERE / "brain.ico") if (HERE / "brain.ico").exists() else None,
    version=str(HERE / "version_info.txt") if (HERE / "version_info.txt").exists() else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="brain")
