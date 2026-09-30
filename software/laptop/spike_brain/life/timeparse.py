"""Spoken time expressions -> datetimes, for alarms and reminders.

Handles what Whisper actually writes ("7:30 a.m.", "7.30pm", "10 minutes")
and what people say ("seven thirty", "half past six", "quarter to nine",
"in an hour and a half", "tomorrow morning at 7", "noon", "midnight").
Pure functions; `now` is always passed in so tests are deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
          "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
          "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def words_to_numbers(text: str) -> str:
    """'seven thirty five' -> '7 35', 'forty five' -> '45', 'seven oh five' -> '7 05'."""
    words = text.lower().split()
    out: list[str] = []
    i = 0

    def split(word: str) -> tuple[str, str] | None:
        m = re.fullmatch(r"([a-z]+)([^a-z]*)", word)
        return (m.group(1), m.group(2)) if m else None

    while i < len(words):
        parts = split(words[i])
        if not parts:
            out.append(words[i])
            i += 1
            continue
        w, tail = parts
        nxt = split(words[i + 1]) if i + 1 < len(words) else None
        if w in _TENS:
            val = _TENS[w]
            if not tail and nxt and nxt[0] in _UNITS and 0 < _UNITS[nxt[0]] < 10:
                val += _UNITS[nxt[0]]
                tail = nxt[1]
                i += 1
            out.append(f"{val}{tail}")
        elif w == "oh" and out and re.fullmatch(r"\d{1,2}", out[-1]) and nxt \
                and nxt[0] in _UNITS and _UNITS[nxt[0]] < 10:
            out.append(f"0{_UNITS[nxt[0]]}{nxt[1]}")
            i += 1
        elif w in _UNITS and w != "oh":
            out.append(f"{_UNITS[w]}{tail}")
        else:
            out.append(words[i])
        i += 1
    return " ".join(out)


def normalize(text: str) -> str:
    t = words_to_numbers(text)
    t = t.replace("a.m.", "am").replace("p.m.", "pm").replace("a.m", "am").replace("p.m", "pm")
    t = re.sub(r"\b(\d{1,2})(\d{2}) ?(am|pm)\b", r"\1:\2 \3", t)   # 730am -> 7:30 am
    t = re.sub(r"(\d)(am|pm)\b", r"\1 \2", t)                        # 7pm -> 7 pm
    t = re.sub(r"\b(\d{1,2})\.(\d{2})\b", r"\1:\2", t)            # 7.30 -> 7:30
    t = re.sub(r"\b(\d{1,2}) (\d{2})\b(?!\s*(minutes?|mins?|hours?|hrs?|seconds?|secs?))", r"\1:\2", t)
    t = re.sub(r"\bhalf an hour\b", "30 minutes", t)
    t = re.sub(r"\ba quarter of an hour\b|\bquarter of an hour\b", "15 minutes", t)
    t = re.sub(r"\ban? (hour|minute|second)", r"1 \1", t)
    t = re.sub(r"\b(\d+) and a half hours?\b", lambda m: f"{int(m.group(1)) * 60 + 30} minutes", t)
    t = re.sub(r"\b1 hour and a half\b", "90 minutes", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass
class When:
    at: datetime
    phrase: str       # the part of the (normalized) text that was the time
    ambiguous: bool = False   # "at 7" with no am/pm hint (could be morning or evening)


_DUR = re.compile(r"\bin (\d+) ?(hours?|hrs?|h)(?: and (\d+) ?(minutes?|mins?))?\b|"
                  r"\bin (\d+) ?(minutes?|mins?|m)\b|\bin (\d+) ?(seconds?|secs?|s)\b")
_CLOCK = re.compile(r"\b(?:at |for |by )?(\d{1,2})(?::(\d{2}))? ?(am|pm|o'?clock)?\b")
_HALF = re.compile(r"\b(?:at )?(half|quarter) (past|to) (\d{1,2})\b")


def parse_duration_minutes(text: str) -> float | None:
    """'10 minutes', 'five more minutes', 'an hour' -> minutes."""
    t = normalize(text)
    m = re.search(r"(\d+) ?(?:more )?(hours?|hrs?)", t)
    mins = re.search(r"(\d+) ?(?:more )?(minutes?|mins?)", t)
    total = 0.0
    if m:
        total += int(m.group(1)) * 60
    if mins:
        total += int(mins.group(1))
    return total or None


def parse_when(text: str, now: datetime, prefer_future: bool = True) -> When | None:
    """Find a time in `text`. Relative ('in 10 minutes') or clock ('at 7:30 pm')."""
    t = normalize(text)
    m = _DUR.search(t)
    if m:
        if m.group(1):
            delta = timedelta(hours=int(m.group(1)), minutes=int(m.group(3) or 0))
        elif m.group(5):
            delta = timedelta(minutes=int(m.group(5)))
        else:
            delta = timedelta(seconds=int(m.group(7)))
        return When(now + delta, m.group(0))

    day_offset = 0
    if re.search(r"\btomorrow\b", t):
        day_offset = 1
    pm_hint = bool(re.search(r"\b(tonight|this evening|in the evening|in the afternoon|this afternoon|at night)\b", t))
    am_hint = bool(re.search(r"\b(in the morning|this morning|tomorrow morning)\b", t))

    hour = minute = None
    phrase = ""
    ampm = None
    if re.search(r"\bnoon\b|\bmidday\b", t):
        hour, minute, ampm, phrase = 12, 0, "pm", "noon"
    elif re.search(r"\bmidnight\b", t):
        hour, minute, ampm, phrase = 0, 0, "am", "midnight"
    else:
        h = _HALF.search(t)
        if h:
            base = int(h.group(3))
            mins = 30 if h.group(1) == "half" else 15
            if h.group(2) == "past":
                hour, minute = base, mins
            else:
                hour, minute = (base - 1 if base > 1 else 12), 60 - mins
            phrase = h.group(0)
            after = t[h.end():h.end() + 4]
            ampm = "am" if after.strip().startswith("am") else ("pm" if after.strip().startswith("pm") else None)
        else:
            for c in _CLOCK.finditer(t):
                has_prefix = c.group(0).startswith(("at ", "for ", "by "))
                if not (has_prefix or c.group(2) or c.group(3)):
                    continue
                hh = int(c.group(1))
                if hh > 23:
                    continue
                hour, minute = hh, int(c.group(2) or 0)
                ampm = c.group(3) if c.group(3) in ("am", "pm") else None
                phrase = c.group(0)
                break
    if hour is None or minute is None or minute > 59:
        return None

    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    candidates: list[datetime] = []
    ambiguous = False
    base_day = (now + timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
    if ampm is None and 1 <= hour <= 12:
        if pm_hint and hour < 12:
            candidates = [base_day.replace(hour=hour + 12, minute=minute)]
        elif am_hint:
            candidates = [base_day.replace(hour=hour % 12, minute=minute)]
        else:
            candidates = [base_day.replace(hour=hour % 12, minute=minute),
                          base_day.replace(hour=(hour % 12) + 12, minute=minute)]
            ambiguous = True
    else:
        candidates = [base_day.replace(hour=hour, minute=minute)]
    if day_offset == 0 and prefer_future:
        future = [c for c in candidates if c > now]
        if future:
            return When(min(future), phrase, ambiguous)
        return When(min(candidates) + timedelta(days=1), phrase, ambiguous)
    return When(min(candidates), phrase, ambiguous)


def say_time(dt: datetime, now: datetime | None = None) -> str:
    """'7:30 am', 'tomorrow at 7 am' - for spoken confirmations."""
    h12 = dt.hour % 12 or 12
    clock = f"{h12}:{dt.minute:02d}" if dt.minute else f"{h12}"
    s = f"{clock} {'am' if dt.hour < 12 else 'pm'}"
    if now is not None:
        days = (dt.date() - now.date()).days
        if days == 1:
            s = "tomorrow at " + s
        elif days > 1:
            s = dt.strftime("%A") + " at " + s
    return s


def say_duration(delta: timedelta) -> str:
    mins = int(round(delta.total_seconds() / 60))
    if mins < 1:
        secs = int(delta.total_seconds())
        return f"{secs} seconds"
    if mins < 60:
        return f"{mins} minute{'s' if mins != 1 else ''}"
    h, m = divmod(mins, 60)
    s = f"{h} hour{'s' if h != 1 else ''}"
    return s + (f" and {m} minutes" if m else "")
