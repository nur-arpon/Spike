"""Command line: python -m spike_brain [options]

  (no options)      full Spike: microphone, webcam, voice, simulator link
  --open            also open the face simulator, already connected
  --no-camera       no webcam
  --no-mic          no microphone: type to talk (terminal or the simulator's box)
  --text            console chat only: no audio, no camera (fast testing). Reads typed or
                    piped lines, prints each reply, ends at the end of piped input:
                    printf "hi\nwhat time is it\n" | python -m spike_brain --text --no-camera
  --persona spicy   start as Spicy (or spike)
  --port N          protocol port (default 8765; the next free one is used if busy)
  --lan             also listen on the Wi-Fi (phone app, robot): pairing token, mDNS announcement
  --pair            show the pairing QR for the phone app, then exit
  --llm-at-start    load the language model at start (default: on demand, see [llm] on_demand)
  --no-llm          scripted lines only, no language model (tests)
  --wipe-memory     forget everything Spike remembers, then exit
  --list-mics       show the microphones, then exit
  --debug           verbose logs, and keep heard audio in data/debug
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .brain import Brain, RunOptions
from .config import LAPTOP_DIR, ConfigError, Settings

log = logging.getLogger("spike")

SIM_INDEX = LAPTOP_DIR.parent / "face_v2" / "index.html"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="spike_brain", description="Spike's laptop brain")
    p.add_argument("--open", action="store_true", help="open the face simulator connected to the brain")
    p.add_argument("--no-camera", action="store_true", help="run without the webcam")
    p.add_argument("--no-mic", action="store_true", help="run without the microphone (type to talk)")
    p.add_argument("--text", action="store_true", help="console chat only (no audio, no camera)")
    p.add_argument("--persona", choices=["spike", "spicy", "dog", "cat"], help="who starts")
    p.add_argument("--port", type=int, help="protocol port")
    p.add_argument("--no-llm", action="store_true", help="scripted lines only, no language model (tests)")
    p.add_argument("--host", help="listen address (a robot on Wi-Fi needs 0.0.0.0 and SPIKE_TOKEN in .env)")
    p.add_argument("--lan", action="store_true",
                   help="listen on the Wi-Fi too (= --host 0.0.0.0): the phone app and the robot connect without USB")
    p.add_argument("--pair", action="store_true",
                   help="show the pairing QR for the phone app (scan it in the app), then exit")
    p.add_argument("--llm-at-start", action="store_true",
                   help="load the language model at start instead of on demand")
    p.add_argument("--settings", type=Path, help="settings file (default software/laptop/spike_settings.toml)")
    p.add_argument("--wipe-memory", action="store_true", help="forget everything, then exit")
    p.add_argument("--list-mics", action="store_true", help="list microphones, then exit")
    p.add_argument("--debug", action="store_true", help="verbose logging and debug recordings")
    p.add_argument("--log-file", type=Path, help="also write the log to this file (rotating; the hidden autostart uses it)")
    # the Windows desktop app runs this brain as its background helper (software/app/DESIGN.md "Desktop")
    p.add_argument("--profile", help="extra settings layer from spike_brain/config/<name>.toml (desktop = the light brain)")
    p.add_argument("--home", type=Path, help="folder for data/, logs and the owner's settings (default software/laptop)")
    p.add_argument("--models", type=Path, help="folder that 'models/...' paths point to (default <home>/models)")
    p.add_argument("--parent-pid", type=int, help="stop when this process ends (the desktop app that started us)")
    p.add_argument("--stop-on-stdin-eof", action="store_true",
                   help="stop cleanly when standard input closes (how the desktop app asks us to stop)")
    p.add_argument("--version", action="version", version=f"spike_brain {__version__}")
    return p.parse_args(argv)


def load_settings(args: argparse.Namespace) -> Settings:
    """The settings for this run: defaults, the profile, the owner's file, then flags."""
    kw: dict = {}
    if args.profile:
        kw["profile"] = args.profile
    if args.home:
        home = args.home.resolve()
        kw.update(root=home, user_toml=home / "spike_settings.toml", env_file=home / ".env")
    if args.models:
        kw["models_root"] = args.models.resolve()
    if args.settings:
        kw["user_toml"] = args.settings
    return Settings.load(**kw)


def watch_parent(pid: int, on_gone) -> None:
    """Call on_gone() when process `pid` ends (Windows: wait on its handle; elsewhere: poll).
    The desktop app starts the brain; if the app is killed, the brain must not live on."""
    import threading

    def run() -> None:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wintypes.HANDLE
            k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            k32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            SYNCHRONIZE = 0x00100000
            h = k32.OpenProcess(SYNCHRONIZE, False, pid)
            if not h:
                log.warning("parent process %d is not there; stopping", pid)
                on_gone()
                return
            k32.WaitForSingleObject(h, 0xFFFFFFFF)      # INFINITE
            k32.CloseHandle(h)
        else:
            import time
            while True:
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(1.0)
        log.info("the app that started Spike's brain has closed; stopping")
        on_gone()

    threading.Thread(target=run, name="parent-watch", daemon=True).start()


def watch_stdin(on_eof) -> None:
    """Call on_eof() when standard input closes (the desktop app closes it to ask for a clean stop)."""
    import threading

    def run() -> None:
        try:
            while sys.stdin is not None and sys.stdin.buffer.read(4096):
                pass
        except (OSError, ValueError, AttributeError):
            pass
        on_eof()

    threading.Thread(target=run, name="stdin-watch", daemon=True).start()


def setup_logging(debug: bool, to_stderr: bool = False, log_file: Path | None = None) -> None:
    """Logs go to stdout normally; with --text they go to stderr, so stdout is a
    clean transcript (the replies) that scripts can capture. With --log-file (the
    hidden autostart, where there is no console) they go to a rotating file."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252
        except (AttributeError, ValueError):
            pass
    fmt = logging.Formatter("%(asctime)s %(name)-12s %(message)s", datefmt="%H:%M:%S")
    handlers: list[logging.Handler] = []
    out = sys.stderr if to_stderr else sys.stdout
    if out is not None:                                   # pythonw.exe has no console at all
        handlers.append(logging.StreamHandler(out))
    if log_file is not None:
        from logging.handlers import RotatingFileHandler
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"))
    if not handlers:
        handlers.append(logging.NullHandler())
    for h in handlers:
        h.setFormatter(fmt)
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, handlers=handlers)
    for noisy in ("websockets", "httpx", "httpcore", "faster_whisper", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def open_simulator(port: int) -> None:
    """Open face_v2 in a clean Edge app window (autoplay allowed, so Spike can talk
    without a click first); fall back to the default browser."""
    url = SIM_INDEX.resolve().as_uri() + f"?brain=ws://127.0.0.1:{port}"
    candidates = [shutil.which("msedge"),
                  os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                  os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")]
    edge = next((c for c in candidates if c and Path(c).exists()), None)
    if edge:
        profile = Path(os.environ.get("LOCALAPPDATA", str(LAPTOP_DIR / "data"))) / "SpikeBrain" / "edge-profile"
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([edge, f"--app={url}", "--autoplay-policy=no-user-gesture-required",
                          f"--user-data-dir={profile}", "--no-first-run", "--window-size=1280,860"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)
    log.info("simulator opened: %s", url)


def list_mics() -> None:
    import sounddevice as sd
    default_in = sd.default.device[0]
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and sd.query_hostapis(d["hostapi"])["name"] == "MME":
            print(f"{'*' if i == default_in else ' '} {i:3d}  {d['name']}")
    print("\n* = Windows default. Put a name part or number in spike_settings.toml under [audio] mic_device.")


def show_pairing(args: argparse.Namespace) -> int:
    """Print the pairing QR (and open it as a picture) for the phone app's scanner."""
    from . import discovery
    settings = load_settings(args)
    port = args.port if args.port is not None else settings.server.port
    ip = discovery.lan_ip()
    if ip is None:
        print("This laptop is not on a network right now, so there is nothing to pair over Wi-Fi.")
        return 1
    token = discovery.resolve_token(settings, lan=True)
    name = settings.personas["dog"].name
    ts, ts_name = discovery.tailscale_addrs()
    url = discovery.pairing_url(ip, port, token, name, ts=ts, ts_name=ts_name)
    product = settings.brand.product_name           # one place for the product name ([brand], RENAMING.md)
    print(f"\nScan this in the {product} app (Connect > Scan the pairing code):\n\n{discovery.qr_console(url)}\n")
    print(f"Address {ip}, port {port}. The brain must be running with --lan (autostart does this).")
    if ts:
        print(f"Tailscale {ts}{f' ({ts_name})' if ts_name else ''}: the app reaches Spike from any network "
              "when the phone runs Tailscale on the same account.")
    png = discovery.save_qr_png(url, settings.path(discovery.QR_FILE))
    try:
        os.startfile(str(png))                                  # type: ignore[attr-defined]  (Windows)
    except (AttributeError, OSError):
        print(f"QR picture: {png}")
    return 0


async def amain(args: argparse.Namespace) -> int:
    settings = load_settings(args)
    mode = {"spike": "dog", "dog": "dog", "spicy": "cat", "cat": "cat"}.get(args.persona or "", None)
    host = args.host or ("0.0.0.0" if args.lan else settings.server.host)
    port = args.port if args.port is not None else settings.server.port
    on_demand = bool(settings.llm.get("on_demand", True)) and not args.llm_at_start and not args.text
    # the server checks the port (127.0.0.1 AND ::1) and moves to a free one on loopback;
    # the simulator is opened only once we know which port it got
    opts = RunOptions(mic=not (args.no_mic or args.text), camera=not (args.no_camera or args.text),
                      tts=not args.text, console=args.no_mic or args.text, text_only=args.text,
                      mode=mode, host=host, port=port, llm=not args.no_llm,
                      print_replies=args.text, exit_at_eof=args.text, llm_on_demand=on_demand,
                      on_listening=(lambda p: asyncio.get_running_loop().call_later(1.0, open_simulator, p))
                      if args.open else None)
    if args.debug:
        settings = settings.override({"debug": {"save_audio": True}})
    brain = Brain(settings, opts)
    loop = asyncio.get_running_loop()
    if hasattr(signal, "SIGBREAK"):
        # Ctrl+Break, or closing the console window: shut down properly (unload the model, close
        # the mic and camera) in the few seconds Windows allows, instead of dying mid-sentence.
        signal.signal(signal.SIGBREAK, lambda *_: loop.call_soon_threadsafe(brain.request_stop))

    def stop_soon() -> None:
        if not loop.is_closed():
            loop.call_soon_threadsafe(brain.request_stop)
            # a stop that hangs (a stuck device driver) must not leave the helper running
            import threading
            t = threading.Timer(15.0, lambda: os._exit(0))
            t.daemon = True
            t.start()

    if args.parent_pid:
        watch_parent(args.parent_pid, stop_soon)
    if args.stop_on_stdin_eof:
        watch_stdin(stop_soon)
    await brain.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    log_file = args.log_file if args.log_file is None or args.log_file.is_absolute() \
        else (args.home or LAPTOP_DIR) / args.log_file
    setup_logging(args.debug, to_stderr=args.text, log_file=log_file)
    try:
        if args.list_mics:
            list_mics()
            return 0
        if args.pair:
            return show_pairing(args)
        if args.wipe_memory:
            from .memory.store import Memory
            settings = load_settings(args)
            mem = Memory(settings.path(settings.memory.db_path))
            mem.wipe()
            mem.close()
            print("Spike's memory is wiped. Alarms and reminders are kept.")
            return 0
        return asyncio.run(amain(args))
    except KeyboardInterrupt:
        return 0
    except (ConfigError, RuntimeError) as e:
        log.error("%s", e)
        return 2
