"""PyInstaller runtime hook for the light brain: a stand-in for PyAV.

faster-whisper imports `av` (FFmpeg, ~67 MB) at module import only for decode_audio(), which
reads audio FILES. The brain always hands Whisper 16 kHz numpy samples from the microphone,
so that path never runs; this stand-in keeps the import working and fails loudly if a file
is ever passed (a bug, not a user situation). See software/app/DESIGN.md "Desktop".
"""
import sys
import types

if "av" not in sys.modules:
    try:
        import av  # noqa: F401  (a full build that has PyAV keeps it)
    except ImportError:
        stub = types.ModuleType("av")

        def _no_files(*_a, **_k):
            raise RuntimeError("decoding audio files is not part of the light brain (pass numpy samples)")

        stub.open = _no_files
        stub.__spike_stub__ = True
        sys.modules["av"] = stub
