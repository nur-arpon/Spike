"""Picking out things worth remembering from what the owner says.

Two layers:
  rules  - instant and deterministic: names, birthdays, likes/dislikes,
           "I'll ring Mum tomorrow" commitments, pets, where they work/live.
  LLM    - optional, runs in the background after a chat (config
           memory.llm_extraction) for everything the rules miss.
Privacy: health details, sexuality, passwords, money and crisis talk are
never extracted (see DESIGN.md "Memory").
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from ..life import timeparse


@dataclass
class Extracted:
    kind: str
    text: str
    subject: str | None = None
    due: str | None = None


_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December"]
MONTHS = {m.lower(): i for i, m in enumerate(_MONTH_NAMES, 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
_ORD = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
        "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13,
        "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
        "nineteenth": 19, "twentieth": 20, "thirtieth": 30}

_NOT_NAMES = {"not", "just", "a", "the", "and", "but", "so", "i", "im", "really", "very", "too", "also",
              "going", "gonna", "here", "back", "home", "sad", "tired", "fine", "ok", "okay"}

SENSITIVE = re.compile(
    r"\b(password|pin|bank|account number|credit card|card number|salary|debt|diagnos\w*|"
    r"medication|meds|pills|depress\w*|anxiety|disorder|illness|disease|cancer|hiv|pregnan\w*|"
    r"sex\w*|gay|lesbian|bisexual|religio\w*|suicid\w*|self harm|kill myself)\b", re.I)


def parse_day_month(text: str) -> str | None:
    """'March 3rd' / '3rd of March' / 'the third of march' / '3/3' -> 'MM-DD'."""
    t = text.lower()
    for word, n in _ORD.items():
        t = re.sub(rf"\btwenty[- ]{word}\b", str(20 + n), t) if n < 10 else t
        t = re.sub(rf"\b{word}\b", str(n), t)
    t = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", t)
    mon = "|".join(sorted(MONTHS, key=len, reverse=True))
    m = re.search(rf"\b(\d{{1,2}}) (?:of )?({mon})\b", t) or None
    if m:
        d, mo = int(m.group(1)), MONTHS[m.group(2)]
    else:
        m = re.search(rf"\b({mon}) (?:the )?(\d{{1,2}})\b", t)
        if m:
            mo, d = MONTHS[m.group(1)], int(m.group(2))
        else:
            m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", t)          # Australian order: day/month
            if not m:
                return None
            d, mo = int(m.group(1)), int(m.group(2))
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{mo:02d}-{d:02d}"


_REL = r"(mum|mom|mother|dad|father|sister|brother|wife|husband|partner|girlfriend|boyfriend|son|daughter|" \
       r"friend|best friend|grandma|grandmother|nan|nanna|grandpa|grandfather|boss|cousin|aunt|uncle|dog|cat)"


def extract_rules(text: str, now: datetime) -> list[Extracted]:
    """Facts from one utterance, by pattern. Returns [] for questions and sensitive topics."""
    raw = (text or "").strip()
    t = raw.lower().replace("’", "'")
    if not t or SENSITIVE.search(t):
        return []
    out: list[Extracted] = []

    m = re.search(r"\b(?:my name is|my name's|i'm called|call me|i am called)\s+([a-z][a-z'-]+)", t)
    if m and m.group(1) not in _NOT_NAMES:
        name = _case(raw, m.group(1))
        name = name[:1].upper() + name[1:]
        # a surname only if the owner's own text capitalised it ("Sam Lee", not "Sam and")
        nxt = re.match(r"\s+([A-Z][a-z'-]+)\b", raw[m.end():])
        if nxt and nxt.group(1).lower() not in _NOT_NAMES:
            name += " " + nxt.group(1)
        out.append(Extracted("name", f"The owner's name is {name}", subject="owner_name"))

    m = re.search(r"\bmy birthday is (?:on )?(.+)$", t)
    if m:
        due = parse_day_month(m.group(1))
        if due:
            out.append(Extracted("birthday", f"The owner's birthday is on {_say_md(due)}",
                                 subject="birthday:owner", due=due))
    m = re.search(rf"\bmy {_REL}(?:'s| )?\s*([a-z]+)?(?:'s)? birthday is (?:on )?(.+)$", t)
    if m:
        due = parse_day_month(m.group(3))
        if due:
            who = f"their {m.group(1)}" + (f" {_case(raw, m.group(2)).title()}" if m.group(2) else "")
            out.append(Extracted("birthday", f"Birthday of {who} is on {_say_md(due)}",
                                 subject=f"birthday:{m.group(1)}:{m.group(2) or ''}", due=due))
    m = re.search(r"\b([a-z]+)'s birthday is (?:on )?(.+)$", t)
    if m and m.group(1) not in ("my", "your", "his", "her", "their", "mum", "mom", "dad") \
            and not any(e.kind == "birthday" for e in out):
        due = parse_day_month(m.group(2))
        if due:
            who = _case(raw, m.group(1)).title()
            out.append(Extracted("birthday", f"{who}'s birthday is on {_say_md(due)}",
                                 subject=f"birthday:{m.group(1)}", due=due))

    if not t.endswith("?"):
        m = re.search(r"\bi (?:really |absolutely |just )?(love|like|enjoy|adore) ([a-z][a-z '-]{2,40}?)(?:[.!,]|$| so| a lot| very)", t)
        if m and not re.match(r"(you|it|that|this|him|her|them|to be|being)\b", m.group(2)):
            out.append(Extracted("preference", f"The owner {m.group(1)}s {_case(raw, m.group(2).strip())}"))
        m = re.search(r"\bi (hate|dislike|can't stand|don't like) ([a-z][a-z '-]{2,40}?)(?:[.!,]|$| so| a lot)", t)
        if m and not re.match(r"(you|it|that|this|him|her|them|my life|myself)\b", m.group(2)):
            verb = {"hate": "hates", "dislike": "dislikes", "can't stand": "can't stand", "don't like": "doesn't like"}[m.group(1)]
            out.append(Extracted("preference", f"The owner {verb} {_case(raw, m.group(2).strip())}"))
        m = re.search(r"\bmy fav(?:ou?)?rite ([a-z ]{2,20}?) is ([a-z0-9][a-z0-9 '-]{1,40}?)(?:[.!,]|$)", t)
        if m:
            out.append(Extracted("preference", f"The owner's favourite {m.group(1).strip()} is {m.group(2).strip()}",
                                 subject=f"favourite:{m.group(1).strip()}"))
        m = re.search(rf"\bi have an? {_REL} (?:called|named) ([a-z]+)", t)
        if m:
            out.append(Extracted("person", f"The owner has a {m.group(1)} called {_case(raw, m.group(2)).title()}",
                                 subject=f"person:{m.group(1)}:{m.group(2)}"))
        m = re.search(r"\bi (work|study) (at|as|in) ([a-z0-9][a-z0-9 &'-]{1,40}?)(?:[.!,]|$)", t)
        if m:
            out.append(Extracted("fact", f"The owner {m.group(1)}s {m.group(2)} {m.group(3).strip()}",
                                 subject=f"{m.group(1)}"))
        m = re.search(r"\bi live in ([a-z][a-z '-]{1,40}?)(?:[.!,]|$)", t)
        if m:
            out.append(Extracted("fact", f"The owner lives in {_case(raw, m.group(1)).title()}", subject="home"))
        m = re.search(r"\bi(?:'ll| will|'m going to| am going to|'m gonna| am gonna| have to| need to| must) "
                      r"([a-z][a-z0-9 '-]{3,60}?)(?: (tomorrow|tonight|today|on (?:monday|tuesday|wednesday|thursday|"
                      r"friday|saturday|sunday)|next week|this weekend))(?:[.!,]|$)", t)
        if m and not re.match(r"(be|go to (sleep|bed)|die|kill|hurt)\b", m.group(1)):
            due = _due_from(m.group(2), now)
            out.append(Extracted("commitment", f"The owner said they will {_you_to_they(m.group(1))} {m.group(2)}",
                                 due=due))
    return out


def _due_from(phrase: str, now: datetime) -> str | None:
    p = phrase.lower()
    if p in ("today", "tonight"):
        return now.date().isoformat()
    if p == "tomorrow":
        return (now.date().fromordinal(now.date().toordinal() + 1)).isoformat()
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, d in enumerate(days):
        if d in p:
            ahead = (i - now.weekday()) % 7 or 7
            return date.fromordinal(now.date().toordinal() + ahead).isoformat()
    return None


def _say_md(due: str) -> str:
    mo, d = map(int, due.split("-"))
    return f"{d} {_MONTH_NAMES[mo - 1]}"


def _case(original: str, lowered: str) -> str:
    i = original.lower().find(lowered)
    return original[i:i + len(lowered)] if i >= 0 else lowered


def _you_to_they(text: str) -> str:
    swaps = {"my": "their", "me": "them", "i": "they", "myself": "themselves", "mine": "theirs"}
    return " ".join(swaps.get(w, w) for w in text.split())


# ---------------------------------------------------------------------- LLM layer
LLM_SYSTEM = (
    "You pick out durable facts about the owner from one message they said to their robot pet. "
    "Only things they clearly stated about themselves or people and pets in their life: names, "
    "relationships, likes and dislikes, birthdays, plans they committed to, work, hobbies. "
    "Never include health or medical details, sexuality, religion, money, passwords, or anything "
    "about self-harm. No guesses, no opinions of the robot. Write each fact in third person, "
    "starting with 'The owner'. Answer only with JSON: {\"facts\": [{\"kind\": \"fact|preference|"
    "birthday|commitment|person\", \"text\": \"...\", \"date\": \"MM-DD or YYYY-MM-DD or null\"}]}. "
    "Use an empty list when there is nothing worth remembering, which is most of the time.")

LLM_SCHEMA = {"type": "object", "properties": {"facts": {"type": "array", "items": {"type": "object",
              "properties": {"kind": {"type": "string"}, "text": {"type": "string"},
                             "date": {"type": ["string", "null"]}}, "required": ["kind", "text"]}}},
              "required": ["facts"]}


def worth_llm_extraction(text: str) -> bool:
    t = (text or "").strip().lower()
    if len(t.split()) < 5 or t.endswith("?") or SENSITIVE.search(t):
        return False
    return bool(re.search(r"\b(i|i'm|i've|i'll|my|me|we|our)\b", t))


def parse_llm_facts(raw: str) -> list[Extracted]:
    try:
        data = json.loads(raw)
    except ValueError:
        m = re.search(r"\{.*\}", raw or "", re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except ValueError:
            return []
    out = []
    for f in (data.get("facts") or [])[:5] if isinstance(data, dict) else []:
        if not isinstance(f, dict):
            continue
        text = str(f.get("text", "")).strip()
        kind = str(f.get("kind", "fact")).strip().lower()
        if not text or len(text) > 200 or SENSITIVE.search(text) or not text.lower().startswith("the owner"):
            continue
        due = f.get("date")
        due = due if isinstance(due, str) and re.fullmatch(r"(\d{4}-)?\d{2}-\d{2}", due) else None
        out.append(Extracted(kind if kind in ("fact", "preference", "birthday", "commitment", "person") else "fact",
                             text, due=due))
    return out


__all__ = ["Extracted", "extract_rules", "parse_day_month", "worth_llm_extraction", "parse_llm_facts",
           "LLM_SYSTEM", "LLM_SCHEMA", "timeparse"]
