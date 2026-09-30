"""Pre-render every scripted line of both characters with Chatterbox Turbo and keep
the best of several takes. One command rebuilds the whole cache:

    python -m spike_brain.tools.build_voice_cache            (only new or changed lines)
    python -m spike_brain.tools.build_voice_cache --force    (everything again)
    options: --takes 3  --only spike|spicy  --no-utmos  --keep-takes

What it does, in plain words:
  1. Lists every scripted line in config/personas/*.toml (greetings, alarms,
     reactions, hunger, check-ins...). Lines that change every time ({when},
     {time}, {what}, {date}, {list}) are left to the live voice. Lines with
     {owner} are made twice: without a name, and with the owner's name if
     Spike already knows it (read-only look at data/spike_memory.sqlite).
  2. Makes several takes of each line with the SAME settings the brain uses
     live (speech/engines.py turbo_text: style tags from the mood, seed 1234
     for the first take, other seeds for the rest; fp32 as the owner's pick).
  3. Screens every take: UTMOSv2 naturalness, Whisper word errors, speaking
     rate, runaway length, and for lines with numbers (helplines) that every
     number was heard. Keeps the best passing take.
  4. Writes voice_cache/<persona>/*.wav (levelled to the brain's loudness) and
     voice_cache/manifest.json, plus report.txt listing weak lines to listen to.

Stop Spike first: this needs the graphics card (about 3.6 GB for the voice).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from ..brain import SOFT_LINES
from ..config import Settings
from ..mind.reply import parse_reply
from ..speech.engines import (OUT_RATE, TurboStyle, cache_key, level, read_wav, resample_int16, say_as, turbo_text,
                              write_wav)
from ..speech.turbo import TurboConfig, TurboWorker, default_python
from ..speech.voices import file_sha1

log = logging.getLogger("spike.cache")

DYNAMIC = re.compile(r"\{(when|what|time|date|list)\}")
SEEDS = [1234, 7, 42, 2026, 99, 314, 777, 1001]
SCREEN = Path(__file__).resolve().with_name("voice_screen.py")

# Screening rules (decided before looking at results; see DESIGN.md "Voice cache").
MAX_WER = 0.25            # more than 1 word in 4 wrong = the take mumbled or skipped words
MIN_WPM, MAX_WPM = 90, 240   # lines of 4+ words; outside = dragged or rushed
RUNAWAY_S_PER_WORD = 1.0  # a clip longer than 1 s per word + 2 s ran away (the Maya1 failure)


def owner_name_readonly(db: Path) -> str | None:
    """The owner's name if Spike knows it, WITHOUT opening the live memory for writing."""
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            r = con.execute("SELECT text FROM facts WHERE subject='owner_name'").fetchone()
        finally:
            con.close()
    except sqlite3.Error:
        return None
    if not r:
        return None
    m = re.search(r"name is (.+)$", r[0], re.I)
    return (m.group(1) if m else r[0]).strip(" .") or None


def scripted_items(settings: Settings, only: str | None = None) -> tuple[list[dict], list[str]]:
    """Every cacheable scripted line variant: dicts with persona, line_id, text, mood, soft, spoken, key."""
    owner = owner_name_readonly(settings.path(settings.memory.db_path))
    help_fmt = settings.helpline()
    items, skipped, seen = [], [], set()
    for mode, p in settings.personas.items():
        if only and p.id != only:
            continue
        style = TurboStyle.from_config(p.voice_cfg.get("turbo") or {})
        for key, options in p.lines.items():
            for idx, raw in enumerate(options):
                line_id = f"{key}.{idx}"
                if DYNAMIC.search(raw):
                    skipped.append(f"{p.id}.{line_id}")
                    continue
                names = ["you"] + ([owner] if owner and "{owner}" in raw else [])
                for name in names:
                    text_raw = p.format_line(raw, owner=name, **help_fmt)
                    parsed = parse_reply(text_raw)
                    if not parsed.text:
                        continue
                    soft = key in SOFT_LINES
                    spoken = turbo_text(say_as(parsed.text, settings.say_as()), parsed.mood, style, soft=soft,
                                        first=True)
                    k = cache_key(p.id, spoken)
                    if k in seen:
                        continue
                    seen.add(k)
                    items.append(dict(persona=p.id, line_id=line_id, text=parsed.text, mood=parsed.mood,
                                      soft=soft, spoken=spoken, key=k, owner_variant=name != "you"))
    return items, skipped


def judge(item: dict, s: dict) -> tuple[bool, float, str]:
    """(passes, score, reason) for one take's screen results."""
    words = max(1, s.get("ref_words") or 1)
    if s.get("duration_s", 0) > RUNAWAY_S_PER_WORD * words + 2.0:
        return False, -9.0, f"ran away ({s['duration_s']} s)"
    if s.get("digits_ok") is False:
        return False, -8.0, f"numbers not heard right ({s.get('heard')!r})"
    wer = s.get("wer", 1.0)
    if words >= 2 and wer > MAX_WER:
        return False, -5.0 - wer, f"word errors {wer:.0%} ({s.get('heard')!r})"
    wpm = s.get("wpm")
    rate_pen = 0.0
    if words >= 4 and wpm:
        if not (MIN_WPM <= wpm <= MAX_WPM):
            return False, -4.0, f"speaking rate {wpm} words/min"
        rate_pen = max(0.0, abs(wpm - 165) - 35) / 100      # gentle nudge towards relaxed speech
    score = (s.get("utmos") or 3.0) - 2.0 * (wer if words >= 2 else 0.0) - rate_pen
    return True, round(score, 3), "ok"


def run_screen(jobs: list[dict], work: Path, use_utmos: bool) -> dict:
    """Score takes in the voice lab's scoring Python; falls back to WER-only in this venv."""
    jf, rf = work / "screen_jobs.json", work / "screen_results.json"
    jf.write_text(json.dumps(jobs), encoding="utf-8")
    score_py = Path(__file__).resolve().parents[2] / "voice_lab" / ".venv-score" / "Scripts" / "python.exe"
    if score_py.exists():
        cmd = [str(score_py), str(SCREEN), str(jf), str(rf)] + ([] if use_utmos else ["--no-utmos"])
        log.info("screening %d takes with %s", len(jobs), "UTMOSv2 + Whisper" if use_utmos else "Whisper")
        subprocess.run(cmd, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        log.warning("voice_lab/.venv-score is gone: screening with Whisper word errors and rate only")
        from . import voice_screen as vs
        vs.main(["voice_screen", str(jf), str(rf), "--no-utmos"])
    return json.loads(rf.read_text(encoding="utf-8"))


def build(settings: Settings, takes: int = 3, only: str | None = None, force: bool = False,
          use_utmos: bool = True, keep_takes: bool = False, extra_takes: int = 2) -> dict:
    cache_dir = settings.path(settings.tts.get("cache_dir", "voice_cache"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    mf = cache_dir / "manifest.json"
    old = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
    items, skipped = scripted_items(settings, only)
    refs = {p.id: settings.path((p.voice_cfg.get("turbo") or {}).get("reference", ""))
            for p in settings.personas.values()}
    ref_sha = {pid: file_sha1(r) for pid, r in refs.items() if r.is_file()}
    old_ok = {pid for pid, v in (old.get("voices") or {}).items() if v.get("ref_sha1") == ref_sha.get(pid)}
    entries = {} if force else {k: e for k, e in (old.get("entries") or {}).items()
                                if e.get("persona") in old_ok and (cache_dir / e.get("file", "")).is_file()}
    todo = [it for it in items if it["key"] not in entries]
    log.info("%d scripted lines (%d already cached, %d to make); %d left to the live voice",
             len(items), len(items) - len(todo), len(todo), len(skipped))
    work = cache_dir / "_takes"
    work.mkdir(exist_ok=True)
    t0 = time.time()
    if todo:
        tcfg = settings.tts.turbo
        worker = TurboWorker(TurboConfig(python=default_python(settings.root, tcfg.get("python", "")),
                                         models=settings.path(tcfg.get("models", "models/chatterbox-turbo")),
                                         voices={pid: r for pid, r in refs.items() if pid in {i["persona"] for i in todo}},
                                         device="cuda", dtype="fp32", synth_timeout_s=60,
                                         log_file=work / "turbo_worker.log"))
        try:
            worker.start(wait=True)
            if not worker.ready:
                raise SystemExit(f"the Turbo voice did not start: {worker.last_error}")
            results = _make_and_screen(worker, todo, work, takes, extra_takes, use_utmos)
        finally:
            worker.stop()
        for it in todo:
            best = results.get(it["key"])
            if not best:
                continue
            if best["screen"].get("digits_ok") is False:
                log.error("%s %s: no take said the helpline numbers right; NOT cached (listen to it live and "
                          "fix its say_as spelling)", it["persona"], it["line_id"])
                continue
            dst_rel = f"{it['persona']}/{it['line_id'].replace('.', '_')}_{it['key'][:8]}.wav"
            pcm, rate = read_wav(Path(best["file"]))
            pcm = resample_int16(pcm, rate, OUT_RATE) if rate != OUT_RATE else pcm
            write_wav(cache_dir / dst_rel, level(pcm, OUT_RATE, float(settings.tts.get("loudness_dbfs", -20))),
                      OUT_RATE)
            entries[it["key"]] = dict(persona=it["persona"], line=it["line_id"], text=it["text"], mood=it["mood"],
                                      soft=it["soft"], spoken=it["spoken"], owner_variant=it["owner_variant"],
                                      file=dst_rel, seed=best["seed"], passed=best["passed"], reason=best["reason"],
                                      scores={k: best["screen"].get(k) for k in ("utmos", "wer", "wpm", "duration_s",
                                                                                 "heard", "digits_ok")},
                                      takes=best["takes"])
    # drop entries for lines that no longer exist, and their files (inside voice_cache only)
    live_keys = {it["key"] for it in items}
    keep = {k: e for k, e in entries.items() if k in live_keys or (only and e.get("persona") != only)}
    for k, e in entries.items():
        if k not in keep:
            (cache_dir / e["file"]).unlink(missing_ok=True)
    manifest = {"version": 1, "engine": "chatterbox-turbo", "built": datetime.now().isoformat(timespec="seconds"),
                "settings": {"dtype": "fp32", "seeds": SEEDS[:takes], "takes": takes, "max_wer": MAX_WER,
                             "wpm": [MIN_WPM, MAX_WPM], "utmos": use_utmos,
                             "loudness_dbfs": settings.tts.get("loudness_dbfs", -20)},
                "voices": {pid: {"reference": str(r.relative_to(settings.root)) if r.is_relative_to(settings.root)
                                 else str(r), "ref_sha1": ref_sha.get(pid)} for pid, r in refs.items()},
                "live_only": skipped, "entries": keep}
    mf.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    _report(cache_dir, manifest)
    if not keep_takes:
        shutil.rmtree(work, ignore_errors=True)
    log.info("voice cache: %d clips, built in %.0f s", len(keep), time.time() - t0)
    return manifest


def _make_and_screen(worker: TurboWorker, todo: list[dict], work: Path, takes: int, extra: int,
                     use_utmos: bool) -> dict:
    """Make `takes` takes per line, screen them, retry failed lines with `extra` more takes."""
    made: dict[str, list[dict]] = {it["key"]: [] for it in todo}

    def make(batch: list[dict], seeds: list[int]) -> list[dict]:
        jobs = []
        for n, it in enumerate(batch):
            for seed in seeds:
                path = work / f"{it['key']}_{seed}.wav"
                pcm, rate, gen_ms = worker.synthesize(it["persona"], it["spoken"], seed=seed, timeout=60)
                write_wav(path, pcm, rate)
                tk = {"id": f"{it['key']}_{seed}", "file": str(path), "text": it["text"], "seed": seed,
                      "gen_ms": round(gen_ms)}
                made[it["key"]].append(tk)
                jobs.append(tk)
            if (n + 1) % 20 == 0:
                log.info("made %d/%d lines", n + 1, len(batch))
        return jobs

    jobs = make(todo, SEEDS[:takes])
    worker.stop()                                     # free the card for the scorer
    screen = run_screen([{k: j[k] for k in ("id", "file", "text")} for j in jobs], work, use_utmos)
    best = _pick(todo, made, screen)
    retry = [it for it in todo if not best[it["key"]]["passed"]]
    if retry and extra > 0:
        log.info("%d lines had no passing take: %d more takes each", len(retry), extra)
        worker.start(wait=True)
        jobs2 = make(retry, SEEDS[takes:takes + extra])
        worker.stop()
        screen.update(run_screen([{k: j[k] for k in ("id", "file", "text")} for j in jobs2], work, use_utmos))
        best.update(_pick(retry, made, screen))
    return best


def _pick(items: list[dict], made: dict, screen: dict) -> dict:
    out = {}
    for it in items:
        rows = []
        for tk in made[it["key"]]:
            s = screen.get(tk["id"], {})
            ok, score, why = judge(it, s)
            rows.append(dict(seed=tk["seed"], passed=ok, score=score, reason=why, screen=s, file=tk["file"]))
        rows.sort(key=lambda r: (r["passed"], r["score"]), reverse=True)
        b = dict(rows[0])
        b["takes"] = [{"seed": r["seed"], "passed": r["passed"], "score": r["score"], "reason": r["reason"],
                       "utmos": r["screen"].get("utmos"), "wer": r["screen"].get("wer"),
                       "wpm": r["screen"].get("wpm")} for r in rows]
        out[it["key"]] = b
    return out


def _report(cache_dir: Path, manifest: dict) -> None:
    es = list(manifest["entries"].values())
    weak = [e for e in es if not e.get("passed")]
    lines = [f"Voice cache report, {manifest['built']}", "",
             f"{len(es)} clips; {len(weak)} kept although no take passed the screen (listen to these first).", ""]
    for p in sorted({e['persona'] for e in es}):
        u = [e["scores"]["utmos"] for e in es if e["persona"] == p and e["scores"].get("utmos")]
        if u:
            lines.append(f"{p}: {len([e for e in es if e['persona'] == p])} clips, UTMOSv2 median "
                         f"{sorted(u)[len(u) // 2]:.2f} (min {min(u):.2f}, max {max(u):.2f})")
    lines += ["", "Weak lines:"] + [f"  {e['persona']} {e['line']}: {e['reason']} -> {e['file']}" for e in weak]
    lines += ["", "Left to the live voice (they change every time):"] + [f"  {s}" for s in manifest["live_only"]]
    (cache_dir / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="pre-render Spike's and Spicy's scripted lines with Turbo")
    ap.add_argument("--takes", type=int, default=3, help="takes per line (best one is kept)")
    ap.add_argument("--only", choices=["spike", "spicy"])
    ap.add_argument("--force", action="store_true", help="remake every line, not only new or changed ones")
    ap.add_argument("--no-utmos", action="store_true", help="screen with Whisper only (faster)")
    ap.add_argument("--keep-takes", action="store_true", help="keep every take in voice_cache/_takes")
    ap.add_argument("--list", action="store_true", help="only list the lines that would be cached")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    s = Settings.load()
    if args.list:
        items, skipped = scripted_items(s, args.only)
        for it in items:
            print(f"{it['persona']:6s} {it['line_id']:24s} {it['spoken']}")
        print(f"\n{len(items)} cacheable, {len(skipped)} live only")
        return 0
    build(s, takes=max(1, min(args.takes, 6)), only=args.only, force=args.force, use_utmos=not args.no_utmos,
          keep_takes=args.keep_takes)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    os._exit(code)