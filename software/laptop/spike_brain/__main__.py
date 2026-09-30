"""python -m spike_brain"""
import logging
import os
import sys

from .app import main

if __name__ == "__main__":
    code = main()
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    # os._exit: CUDA Whisper (CTranslate2) can hang the interpreter's normal
    # shutdown on Windows. Everything is already closed and flushed here.
    os._exit(code)
