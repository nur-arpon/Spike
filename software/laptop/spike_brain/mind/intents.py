"""Deterministic commands, handled before (and instead of) the LLM.

Anything with a side effect that must be exactly right - switching to cat
mode, alarms, reminders, forgetting - is matched here with rules, so it is
instant, testable and never hallucinated. Everything else is conversation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..capabilities import is_available
from ..life import timeparse


@dataclass
class Intent:
    name: str
    slots: dict = field(default_factory=dict)


def _clean(text: str) -> str:
    t = (text or "").lower().replace("’", "'")
    t = re.sub(r"[^a-z0-9':. ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .")


# trick word -> action (mostly face_v2, until the legs have their own 'sit' etc.; "walk" and
# "paw" are the real v1.4 body actions, PROTOCOL.md 5.2 - the robot owns the motion)
TRICKS = {
    "sit": "playBow", "sit down": "playBow", "lie down": "napping", "bow": "playBow", "spin": "zoomies", "roll over": "rollOver",
    "play dead": "fallAsleep", "dance": "tailWagDance", "beg": "beggingAction",
    "sneeze": "sneeze", "wag": "tailWagDance", "zoomies": "zoomies", "stretch": "playBow",
    "yawn": "yawn", "high five": "beggingAction",
    "shake": "paw", "paw": "paw", "give paw": "paw",
    "walk": "walk", "walk forward": "walk", "come here": "walk",
}
_TRICK_RE = re.compile(r"^(?:can you |will you |please |now |go on |ok |okay )*(?:do a |do the )?"
                       r"(" + "|".join(sorted(map(re.escape, TRICKS), key=len, reverse=True)) + r")"
                       r"(?: for me)?(?: please| now)?$")


def match_intent(text: str, names: dict[str, str], now: datetime,
                 alarm_ringing: bool = False, in_rps: bool = False,
                 confirming_forget_all: bool = False) -> Intent | None:
    """names = {'dog': 'Spike', 'cat': 'Spicy'} (from config, so renames work)."""
    t = _clean(text)
    if not t:
        return None
    dog, cat = names.get("dog", "spike").lower(), names.get("cat", "spicy").lower()
    words = t.split()

    if confirming_forget_all:
        if re.search(r"\b(yes|yeah|yep|do it|forget everything|i'm sure|i am sure|sure)\b", t) \
                and not re.search(r"\b(no|don't|do not|wait|cancel|never ?mind)\b", t):
            return Intent("forget_all_confirmed")
        return Intent("forget_all_cancelled")

    if alarm_ringing:
        if re.search(r"\b(snooze|more minutes?|let me sleep|not yet|later|five more|5 more)\b", t):
            return Intent("snooze", {"minutes": timeparse.parse_duration_minutes(t)})
        if re.search(r"\b(i'?m up|i am up|i'?m awake|i am awake|i'?m getting up|i am getting up|"
                     r"stop|turn it off|okay okay|ok ok|enough|good morning|alright)\b", t):
            return Intent("alarm_stop")

    if in_rps:
        m = re.search(r"\b(rock|paper|scissors?|stone)\b", t)
        if m:
            choice = {"stone": "rock", "scissor": "scissors"}.get(m.group(1), m.group(1))
            return Intent("rps_choice", {"choice": choice})
        if re.search(r"\b(stop|quit|enough|no more|i'm done)\b", t):
            return Intent("rps_stop")

    # --- mode switching ---------------------------------------------------
    if re.search(rf"\b(cat mode|be (a )?cat|turn into (a )?cat|become (a )?cat|kitty mode|"
                 rf"switch to (the )?cat|{re.escape(cat)} mode|be {re.escape(cat)}|"
                 rf"switch to {re.escape(cat)}|i want {re.escape(cat)})\b", t):
        return Intent("set_mode", {"mode": "cat"})
    if re.search(rf"\b(dog mode|puppy mode|be (a )?dog|turn (back )?into (a )?dog|become (a )?dog|"
                 rf"switch to (the )?dog|{re.escape(dog)} mode|be {re.escape(dog)}|"
                 rf"switch to {re.escape(dog)}|i want {re.escape(dog)}|come back {re.escape(dog)})\b", t):
        return Intent("set_mode", {"mode": "dog"})

    # --- stop talking -----------------------------------------------------
    if len(words) <= 4 and re.fullmatch(r"(ok |okay |please )?(stop|shush|shh+|hush|quiet|be quiet|"
                                        r"stop talking|enough|that's enough|never ?mind)( please)?", t):
        return Intent("stop")

    # --- memory -------------------------------------------------------------
    if re.search(r"\b(forget everything|wipe (your|my) memory|erase (your|my) memory|"
                 r"delete (all )?(your|my) memor(y|ies)|forget all about me)\b", t):
        return Intent("forget_all")
    if re.fullmatch(r"(please |ok |okay )?(forget|forget that|forget it|forget what i (just )?said|"
                    r"don't remember that|scratch that)( please)?", t):
        return Intent("forget_last")
    m = re.match(r"^(?:please |ok |okay )?forget (?:about |that )?(?P<what>.{3,})$", t)
    if m and not m.group("what").startswith(("it ", "everything")):
        return Intent("forget_about", {"what": m.group("what")})
    if re.search(r"\bwhat do you (know|remember) about me\b|\bwhat have you remembered\b", t):
        return Intent("recall_all")
    m = re.match(r"^(?:please |ok |okay |hey )?(?:remember|don't forget|note) (?:that )?(?P<fact>.{3,})$", t)
    if m and not re.match(r"^(when|what|how|the time|me\b)", m.group("fact")):
        return Intent("remember", {"fact": _restore_case(text, m.group("fact"))})

    # --- alarms and reminders ------------------------------------------------
    if re.search(r"\b(cancel|delete|remove|turn off|clear) (the |my |all )?(alarms?|reminders?)\b", t):
        kind = "alarm" if "alarm" in t else "reminder"
        return Intent("cancel_" + kind, {"all": " all " in f" {t} "})
    if re.search(r"\b(what|which|any) (alarms|reminders)\b|\b(list|tell me) (my )?(alarms|reminders)\b|"
                 r"\bdo i have any (alarms|reminders)\b", t):
        return Intent("list_timers")
    if re.search(r"\b(wake me( up)?|set (an |the |my )?alarm|alarm (for|at)|get me up)\b", t):
        when = timeparse.parse_when(t, now)
        at = when.at if when else None
        # "set an alarm for seven" said in the evening means tomorrow morning
        if when and when.ambiguous and now.hour >= 17 and at.hour >= 12 and 4 <= at.hour - 12 <= 11:
            at = at.replace(hour=at.hour - 12)
            if at <= now:
                at += timedelta(days=1)
        return Intent("set_alarm", {"at": at})
    m = re.search(r"\bremind me\b", t)
    if m:
        when = timeparse.parse_when(t, now)
        tn = timeparse.normalize(t)
        what = tn[tn.find("remind me") + len("remind me"):]
        if when:
            what = what.replace(when.phrase.strip(), " ")
        what = re.sub(r"\b(tomorrow( morning| evening| afternoon| night)?|tonight|"
                      r"this (morning|evening|afternoon)|in the (morning|evening|afternoon))\b", " ", what)
        what = re.sub(r"\b(in|at|to|about|that|please|on)\b\s*$", " ", what.strip())
        what = re.sub(r"^\s*(to|about|that|please)\s+", "", what.strip())
        what = _you_form(re.sub(r"\s+", " ", what).strip(" ."))
        return Intent("set_reminder", {"at": when.at if when else None, "what": what})
    if re.search(r"\b(set a |start a )?timer for\b", t):
        when = timeparse.parse_when("in " + t.split("timer for", 1)[1], now)
        return Intent("set_reminder", {"at": when.at if when else None, "what": "your timer is done"})

    # --- time ---------------------------------------------------------------------
    if re.search(r"\bwhat('s| is) the time\b|\bwhat time is it\b|\bgot the time\b", t):
        return Intent("tell_time")
    if re.search(r"\bwhat('s| is) (the date|today's date)\b|\bwhat day is (it|today)\b", t):
        return Intent("tell_date")

    # --- games and tricks ---------------------------------------------------------
    if re.search(r"\brock,? paper,? scissors?\b|\bplay (a game of )?(rps|rock)\b|\blet'?s play\b", t):
        return Intent("rps_start")
    m = _TRICK_RE.match(t)
    if m:
        if not is_available(TRICKS[m.group(1)]):       # capabilities.py: the body cannot do it yet
            return Intent("trick_unavailable", {"trick": m.group(1)})
        return Intent("trick", {"trick": m.group(1), "action": TRICKS[m.group(1)]})
    if re.fullmatch(r"(do a trick|show me a trick|do something cool|do a trick for me)( please)?", t):
        return Intent("trick", {"trick": "random", "action": None})
    if re.fullmatch(r"(go to sleep|go to bed|take a nap|time for bed|goodnight|good night|nap time|"
                    r"sleep)( now)?( (spike|spicy|buddy))?", t):
        return Intent("sleep")
    return None


def _restore_case(original: str, lowered_part: str) -> str:
    """Return `lowered_part` with the owner's original capitalisation if we can find it."""
    idx = original.lower().replace("’", "'").find(lowered_part)
    return original[idx: idx + len(lowered_part)] if idx >= 0 else lowered_part


def _you_form(text: str) -> str:
    """'call my mum' -> 'call your mum' (for the spoken reminder)."""
    swaps = {"my": "your", "i": "you", "me": "you", "mine": "yours", "i'm": "you're", "myself": "yourself"}
    return " ".join(swaps.get(w, w) for w in text.split())
