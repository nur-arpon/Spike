"""Frozen entry point of Spike's light brain for the Windows desktop app (see spike_brain_desktop.spec)."""
import multiprocessing
import sys

from spike_brain.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
