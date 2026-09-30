"""Wake-word evaluation with the REAL hearing stack (Silero VAD + Vosk
grammar spotter + Whisper + fuzzy matcher, exactly as the brain runs them).

Speech is synthesized with all 8 Piper voices (4 male, 4 female, US and UK
accents) so the test has many "speakers". Positives must wake Spike/Spicy
and give the right request; negatives (everyday sentences with sound-alike
words) must NOT wake him. Prints hit rate and false-wake rate.

    python -m spike_brain.tools.wake_eval [--voices 8] [--quick]

This is a regression check for tuning, not a substitute for real voices:
record a few real "Spike"s with --debug and add them when the robot is built.
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time

import numpy as np

from ..config import Settings

# (text to synthesize, expected wake word or None, expected request or None)
POSITIVES = [
    ("Spike!", "Spike", ""),
    ("Hey Spike, what time is it?", "Spike", "what time is it"),
    ("Spike, tell me a joke.", "Spike", "tell me a joke"),
    ("What's the weather like, Spike?", "Spike", "What's the weather like"),
    ("Spike, how are you?", "Spike", "how are you"),
    ("Hey Spike!", "Spike", ""),
    ("Hey buddy, remind me to call mum.", "Hey Buddy", "remind me to call mum"),
    ("Spicy, come here.", "Spicy", "come here"),
    ("Hey Spicy, are you awake?", "Spicy", "are you awake"),
]
NEGATIVES = [
    "I like spinach with my dinner.",
    "That is a giant pizza.",
    "This curry is way too spicy.",
    "My buddy called me yesterday.",
    "Hey everybody, dinner is ready.",
    "There was a spike in prices this week.",
    "Michael is coming over later.",
    "I told my friend about the robot.",
    "Can you pass me the remote?",
    "The meeting is at three o'clock.",
    "I need to buy some milk.",
    "Maya and Ryan went to the park.",
    "Spike prices went up again.",
    "Zoe is my cousin from Perth.",
    "Pass the spice rack please.",
    "What a giant mess this is.",
]


def synth_all(settings: Settings, n_voices: int):
    from ..speech.tts import PiperTTS, resample_int16
    voices = sorted(settings.path("models/piper/spike").glob("*.onnx")) + \
        sorted(settings.path("models/piper/spicy").glob("*.onnx"))
    voices = voices[:n_voices]
    out = []
    for v in voices:
        tts = PiperTTS(v)
        for text, wake, req in POSITIVES:
            sp = tts.synthesize(text)
            out.append((v.stem, text, wake, req, resample_int16(sp.pcm, sp.rate, 16000)))
        for text in NEGATIVES:
            sp = tts.synthesize(text)
            out.append((v.stem, text, None, None, resample_int16(sp.pcm, sp.rate, 16000)))
    return out


def run(settings: Settings, clips) -> list[dict]:
    from ..hearing.listener import Listener
    from ..hearing.stt import Transcriber
    from ..hearing.vad import FRAME, make_vad
    from ..hearing.wake import VoskSpotter, WakeMatcher
    s = settings
    aliases = {m: p.wake_aliases for m, p in s.personas.items()}
    vocative = {v for p in s.personas.values() for v in p.vocative_only}
    matcher = WakeMatcher(aliases, s.wake.fuzzy_threshold, vocative)
    spotter = VoskSpotter(s.path(s.wake.vosk_model), aliases)
    prompt_words = sorted({w for p in s.personas.values() for w in [p.name, *p.wake_words]})
    stt = Transcriber(s.path("models/whisper"), s.stt.model, s.stt.cpu_model, s.stt.device,
                      prompt_words=prompt_words)
    results = []
    for voice, text, wake, req, pcm in clips:
        events = []
        done = threading.Event()

        def on_event(kind, data, events=events, done=done):
            events.append((kind, data))
            if kind in ("heard", "wake_rejected", "wake_only", "not_understood"):
                done.set()

        spotter.reset()
        lst = Listener(vad=make_vad(s.vad.engine, s.path(s.vad.model)), matcher=matcher, transcriber=stt,
                       spotter=spotter, on_event=on_event, threshold=s.vad.threshold,
                       end_silence_ms=s.vad.end_silence_ms, min_speech_ms=s.vad.min_speech_ms,
                       preroll_ms=s.vad.preroll_ms, min_conf=s.wake.min_confidence,
                       strong_conf=s.wake.strong_confidence, refractory_s=0)
        lst.start()
        audio = np.concatenate([np.zeros(8000, np.int16), pcm, np.zeros(24000, np.int16)])
        for i in range(0, len(audio) - FRAME + 1, FRAME):
            lst.feed(audio[i:i + FRAME])
        # no wake candidate once the clip has been processed = nothing more will happen
        t_end = time.time() + 4.0
        while not done.is_set() and time.time() < t_end:
            if lst.q.empty() and not any(k == "wake_candidate" for k, _ in events) and time.time() > t_end - 3.5:
                break
            time.sleep(0.02)
        time.sleep(0.05)
        lst.stop()
        kinds = [k for k, _ in events]
        heard = next((d for k, d in events if k == "heard"), None)
        woke = heard is not None or "wake_only" in kinds
        got_wake = heard.wake if heard else next((d.get("wake") for k, d in events if k == "wake_only"), None)
        results.append({"voice": voice, "text": text, "expect": wake, "woke": woke, "wake": got_wake,
                        "request": heard.text if heard else "", "want_request": req,
                        "candidate": "wake_candidate" in kinds})
    return results


def report(results: list[dict]) -> dict:
    pos = [r for r in results if r["expect"]]
    neg = [r for r in results if not r["expect"]]
    hits = [r for r in pos if r["woke"] and r["wake"] == r["expect"]]
    false = [r for r in neg if r["woke"]]
    by_word: dict[str, list] = {}
    for r in pos:
        by_word.setdefault(r["expect"], []).append(r["woke"] and r["wake"] == r["expect"])
    print("\nWake words (hit rate):")
    for w, oks in by_word.items():
        print(f"  {w:10s} {sum(oks)}/{len(oks)}")
    print(f"\nAll positives: {len(hits)}/{len(pos)} woke correctly")
    print(f"False wakes:   {len(false)}/{len(neg)} everyday sentences")
    for r in false:
        print(f"   FALSE WAKE  [{r['voice']}] {r['text']!r} -> {r['wake']} / {r['request']!r}")
    misses = [r for r in pos if r not in hits]
    for r in misses:
        print(f"   missed      [{r['voice']}] {r['text']!r} (candidate={r['candidate']}, got {r['wake']})")
    return {"hits": len(hits), "positives": len(pos), "false": len(false), "negatives": len(neg)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", type=int, default=8)
    ap.add_argument("--rounds", type=int, default=1, help="fresh syntheses per voice (Piper varies each time)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    s = Settings.load()
    t = time.time()
    results = []
    for _ in range(args.rounds):
        clips = synth_all(s, args.voices)
        results += run(s, clips)
    print(f"{len(results)} clips ({args.rounds} round(s) x {args.voices} voices) in {time.time() - t:.0f} s")
    report(results)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    import os
    os._exit(code)
