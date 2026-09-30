"""Alarms and reminders: stored in the memory database, survive restarts.

Scheduler  - add / list / cancel / snooze / stop, and "what is due now".
AlarmRinger - the puppy-style escalation for one ringing alarm, as a pure
              state machine: tick(now) returns what to do (so it is testable
              without a clock or a robot).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..memory.store import Memory

ACTIVE, RINGING, SNOOZED, DONE, CANCELLED, MISSED = "active", "ringing", "snoozed", "done", "cancelled", "missed"


@dataclass
class Timer:
    id: int
    kind: str              # alarm | reminder
    label: str
    due: float             # Unix seconds
    state: str
    repeat: str            # '' or 'daily'
    snoozes: int

    @property
    def due_dt(self) -> datetime:
        return datetime.fromtimestamp(self.due)


class Scheduler:
    def __init__(self, memory: Memory, clock=time.time):
        self.mem = memory
        self.clock = clock

    def _rows(self, sql: str, args=()) -> list[Timer]:
        with self.mem._lock:
            rows = self.mem.db.execute(sql, args).fetchall()
        return [Timer(r["id"], r["kind"], r["label"], r["due"], r["state"], r["repeat"], r["snoozes"]) for r in rows]

    def get(self, tid: int) -> Timer | None:
        r = self._rows("SELECT * FROM timers WHERE id=?", (tid,))
        return r[0] if r else None

    def add(self, kind: str, at: datetime, label: str = "", repeat: str = "") -> Timer:
        if kind not in ("alarm", "reminder"):
            raise ValueError(kind)
        with self.mem._lock:
            cur = self.mem.db.execute(
                "INSERT INTO timers(kind, label, due, state, repeat, created) VALUES (?,?,?,?,?,?)",
                (kind, label, at.timestamp(), ACTIVE, repeat, self.clock()))
        return self.get(cur.lastrowid)

    def add_alarm(self, at: datetime, label: str = "Wake up", repeat: str = "") -> Timer:
        return self.add("alarm", at, label, repeat)

    def add_reminder(self, at: datetime, label: str) -> Timer:
        return self.add("reminder", at, label)

    def upcoming(self, kind: str | None = None) -> list[Timer]:
        if kind:
            return self._rows("SELECT * FROM timers WHERE state IN (?,?) AND kind=? ORDER BY due",
                              (ACTIVE, SNOOZED, kind))
        return self._rows("SELECT * FROM timers WHERE state IN (?,?) ORDER BY due", (ACTIVE, SNOOZED))

    def ringing(self) -> list[Timer]:
        return self._rows("SELECT * FROM timers WHERE state=? ORDER BY due", (RINGING,))

    def cancel(self, kind: str | None = None, only_next: bool = False) -> int:
        items = [t for t in self.upcoming(kind)] + [t for t in self.ringing() if kind in (None, t.kind)]
        if only_next and items:
            items = items[:1]
        with self.mem._lock:
            for t in items:
                self.mem.db.execute("UPDATE timers SET state=? WHERE id=?", (CANCELLED, t.id))
        return len(items)

    def cancel_id(self, tid: int) -> bool:
        """Cancel one alarm or reminder (the app's per-item button). False if it is not pending."""
        t = self.get(tid)
        if t is None or t.state not in (ACTIVE, SNOOZED, RINGING):
            return False
        with self.mem._lock:
            self.mem.db.execute("UPDATE timers SET state=? WHERE id=?", (CANCELLED, tid))
        return True

    def listing(self) -> list[Timer]:
        """Everything still to come or ringing now, soonest first (the app's list)."""
        return self._rows("SELECT * FROM timers WHERE state IN (?,?,?) ORDER BY due", (ACTIVE, SNOOZED, RINGING))

    def due_now(self) -> list[Timer]:
        """Timers whose time has come. Alarms become RINGING, reminders DONE (or re-armed if daily)."""
        now = self.clock()
        due = self._rows("SELECT * FROM timers WHERE state IN (?,?) AND due<=? ORDER BY due", (ACTIVE, SNOOZED, now))
        with self.mem._lock:
            for t in due:
                if t.kind == "alarm":
                    self.mem.db.execute("UPDATE timers SET state=?, fired_at=? WHERE id=?", (RINGING, now, t.id))
                    t.state = RINGING
                else:
                    self._finish(t, now)
        return due

    def _finish(self, t: Timer, now: float) -> None:
        if t.repeat == "daily":
            nxt = t.due
            while nxt <= now:
                nxt += 86400
            self.mem.db.execute("UPDATE timers SET state=?, due=?, snoozes=0, fired_at=? WHERE id=?",
                                (ACTIVE, nxt, now, t.id))
        else:
            self.mem.db.execute("UPDATE timers SET state=?, fired_at=? WHERE id=?", (DONE, now, t.id))

    def snooze(self, tid: int, minutes: float) -> Timer | None:
        now = self.clock()
        with self.mem._lock:
            self.mem.db.execute("UPDATE timers SET state=?, due=?, snoozes=snoozes+1 WHERE id=?",
                                (SNOOZED, now + minutes * 60, tid))
        return self.get(tid)

    def stop(self, tid: int) -> None:
        t = self.get(tid)
        if t:
            with self.mem._lock:
                self._finish(t, self.clock())

    def give_up(self, tid: int) -> None:
        with self.mem._lock:
            self.mem.db.execute("UPDATE timers SET state=? WHERE id=?", (MISSED, tid))

    def recover(self, max_late_s: float = 12 * 3600) -> list[Timer]:
        """At start-up: timers that fell due long ago (brain was off) are marked missed.
        Ringing alarms from a crash go back to active so they ring again."""
        now = self.clock()
        with self.mem._lock:
            self.mem.db.execute("UPDATE timers SET state=? WHERE state=?", (ACTIVE, RINGING))
        missed = self._rows("SELECT * FROM timers WHERE state IN (?,?) AND due<?", (ACTIVE, SNOOZED, now - max_late_s))
        with self.mem._lock:
            for t in missed:
                if t.repeat == "daily":
                    self._finish(t, now)
                else:
                    self.mem.db.execute("UPDATE timers SET state=? WHERE id=?", (MISSED, t.id))
        return missed

    def next_due(self) -> float | None:
        items = self.upcoming()
        return items[0].due if items else None


@dataclass
class RingStep:
    """What the brain should do on this tick of a ringing alarm."""
    level: int                 # 0 soft whine, 1 yips, 2 barks + joke, 3 everything
    speak: bool                # say a wake-up joke now
    sound: str | None
    action: str | None
    give_up: bool = False


class AlarmRinger:
    """Escalation for one ringing alarm. Levels rise every `escalate_s`;
    each level repeats its cue every `repeat_s`; gives up after `give_up_s`."""

    SOUNDS = {0: "whine", 1: "yip", 2: "bark", 3: "bark"}
    ACTIONS = {0: None, 1: "headTilt", 2: "zoomies", 3: "tailWagDance"}

    def __init__(self, timer_id: int, started: float, escalate_s: float = 25, give_up_s: float = 1800,
                 repeat_s: float = 8.0):
        self.timer_id = timer_id
        self.started = started
        self.escalate_s = escalate_s
        self.give_up_s = give_up_s
        self.repeat_s = repeat_s
        self.next_at = started
        self.spoken_levels: set[int] = set()
        self.last_spoke = -1e9
        self.speak_every_s = 45.0
        self.last_level = -1

    def level_at(self, now: float) -> int:
        return min(3, int(max(0.0, now - self.started) // self.escalate_s))

    def tick(self, now: float) -> RingStep | None:
        if now - self.started >= self.give_up_s:
            return RingStep(self.last_level, False, None, None, give_up=True)
        if now < self.next_at:
            return None
        level = self.level_at(now)
        speak = level >= 2 and (level not in self.spoken_levels or now - self.last_spoke >= self.speak_every_s)
        if speak:
            self.spoken_levels.add(level)
            self.last_spoke = now
        new_level = level != self.last_level
        self.last_level = level
        self.next_at = now + (self.repeat_s if level < 3 else self.repeat_s * 1.5)
        return RingStep(level, speak, self.SOUNDS[level], self.ACTIONS[level] if new_level else None)


def next_occurrence(at: datetime, now: datetime) -> datetime:
    while at <= now:
        at += timedelta(days=1)
    return at
