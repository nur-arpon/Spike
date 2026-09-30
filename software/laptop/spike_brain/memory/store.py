"""Spike's memory: one local SQLite file, easy to read, easy to wipe.

Tables
  facts       things the owner told him (facts, preferences, birthdays,
              commitments "I'll ring Mum tomorrow", people), FTS5-indexed
  mood_diary  how the owner seemed (camera / conversation), one row per sample,
              never a transcript
  events      moments worth knowing later (came home, crisis moment - no
              words, nudge given, ...)
  timers      alarms and reminders (life/scheduler.py owns their logic)
  meta        schema version

Nothing here leaves the laptop. `wipe()` or deleting the file forgets all.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    subject TEXT,
    due TEXT,
    source TEXT NOT NULL DEFAULT 'voice',
    created REAL NOT NULL,
    updated REAL NOT NULL,
    last_used REAL,
    uses INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS facts_subject ON facts(subject);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE OF text ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO facts_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TABLE IF NOT EXISTS mood_diary (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, day TEXT NOT NULL,
    mood TEXT NOT NULL, source TEXT NOT NULL, score REAL
);
CREATE INDEX IF NOT EXISTS diary_day ON mood_diary(day);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_kind ON events(kind, ts);
CREATE TABLE IF NOT EXISTS timers (
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
    due REAL NOT NULL, state TEXT NOT NULL DEFAULT 'active', repeat TEXT NOT NULL DEFAULT '',
    created REAL NOT NULL, snoozes INTEGER NOT NULL DEFAULT 0, fired_at REAL
);
CREATE INDEX IF NOT EXISTS timers_due ON timers(state, due);
"""

FACT_KINDS = ("fact", "preference", "birthday", "commitment", "person", "name")
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "at", "is", "are", "was", "i", "you",
         "me", "my", "your", "it", "that", "this", "what", "do", "does", "did", "for", "with", "be",
         "have", "has", "had", "so", "but", "not", "just", "about", "can", "could", "would", "will",
         "hey", "hi", "spike", "spicy", "please", "like", "know", "tell", "okay", "ok", "really"}


@dataclass
class Fact:
    id: int
    kind: str
    text: str
    subject: str | None
    due: str | None
    created: float


class Memory:
    def __init__(self, path: Path | str, clock=time.time):
        self.path = Path(path) if path != ":memory:" else path
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._lock = threading.RLock()
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL" if isinstance(self.path, Path) else "PRAGMA journal_mode=MEMORY")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(SCHEMA)
        self.db.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema', ?)", (str(SCHEMA_VERSION),))
        self.last_ids: list[int] = []          # facts touched most recently (for "forget that")

    def close(self) -> None:
        with self._lock:
            self.db.close()

    # ------------------------------------------------------------------ facts
    def remember(self, text: str, kind: str = "fact", subject: str | None = None,
                 due: str | None = None, source: str = "voice") -> int:
        """Store a fact. Same `subject` replaces the old value; near-duplicate text updates it."""
        text = re.sub(r"\s+", " ", (text or "").strip()).strip(" .")
        if not text:
            raise ValueError("empty memory")
        kind = kind if kind in FACT_KINDS else "fact"
        now = self.clock()
        with self._lock:
            row = None
            if subject:
                row = self.db.execute("SELECT id FROM facts WHERE subject=?", (subject,)).fetchone()
            if row is None:
                row = self._near_duplicate(text)
            if row is not None:
                self.db.execute("UPDATE facts SET text=?, kind=?, due=COALESCE(?, due), updated=?, source=? WHERE id=?",
                                (text, kind, due, now, source, row["id"]))
                fid = row["id"]
            else:
                cur = self.db.execute(
                    "INSERT INTO facts(kind, text, subject, due, source, created, updated) VALUES (?,?,?,?,?,?,?)",
                    (kind, text, subject, due, source, now, now))
                fid = cur.lastrowid
            self._touch([fid])
            return fid

    def _near_duplicate(self, text: str):
        from rapidfuzz import fuzz
        best, best_score = None, 0.0
        for r in self.db.execute("SELECT id, text FROM facts ORDER BY updated DESC LIMIT 400"):
            s = fuzz.token_set_ratio(text.lower(), r["text"].lower())
            if s > best_score:
                best, best_score = r, s
        return best if best_score >= 92 else None

    def _touch(self, ids: list[int]) -> None:
        if ids:
            self.last_ids = list(ids)

    def get(self, fid: int) -> Fact | None:
        with self._lock:
            r = self.db.execute("SELECT * FROM facts WHERE id=?", (fid,)).fetchone()
        return _fact(r) if r else None

    def all_facts(self) -> list[Fact]:
        with self._lock:
            return [_fact(r) for r in self.db.execute("SELECT * FROM facts ORDER BY created")]

    def newest(self, limit: int = 200) -> list[Fact]:
        """The most recently stored or changed facts first (the app's memory list)."""
        with self._lock:
            return [_fact(r) for r in self.db.execute("SELECT * FROM facts ORDER BY updated DESC, id DESC LIMIT ?",
                                                      (limit,))]

    def signature(self) -> tuple:
        """Changes whenever a fact is added, changed or forgotten (cheap: one indexed query)."""
        with self._lock:
            r = self.db.execute("SELECT COUNT(*), COALESCE(MAX(updated), 0), COALESCE(MAX(id), 0), "
                                "COALESCE(SUM(id), 0) FROM facts").fetchone()
        return tuple(r)

    def count(self) -> int:
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

    def forget(self, fid: int) -> bool:
        with self._lock:
            n = self.db.execute("DELETE FROM facts WHERE id=?", (fid,)).rowcount
        self.last_ids = [i for i in self.last_ids if i != fid]
        return n > 0

    def forget_last(self) -> list[str]:
        """'Forget that': drop the most recently stored/used facts. Returns their texts."""
        gone = []
        for fid in list(self.last_ids):
            f = self.get(fid)
            if f and self.forget(fid):
                gone.append(f.text)
        self.last_ids = []
        return gone

    def forget_matching(self, query: str, min_score: float = 62) -> str | None:
        """'Forget that I like pizza': delete the closest fact. Returns its text or None."""
        from rapidfuzz import fuzz
        q = _strip_pronouns(query)
        best, score = None, 0.0
        for f in self.all_facts():
            s = max(fuzz.token_set_ratio(q, _strip_pronouns(f.text)), fuzz.partial_ratio(q, f.text.lower()))
            if s > score:
                best, score = f, s
        if best and score >= min_score and self.forget(best.id):
            return best.text
        return None

    def wipe(self) -> None:
        """Forget everything personal (facts, diary, events). Alarms stay."""
        with self._lock:
            self.db.execute("DELETE FROM facts")
            self.db.execute("DELETE FROM mood_diary")
            self.db.execute("DELETE FROM events")
            self.db.execute("INSERT INTO facts_fts(facts_fts) VALUES ('rebuild')")
            self.db.execute("VACUUM")
        self.last_ids = []

    # ------------------------------------------------------------------ retrieval
    def search(self, query: str, limit: int = 6) -> list[Fact]:
        terms = [w for w in re.findall(r"[a-z0-9']+", (query or "").lower())
                 if w not in _STOP and len(w) > 2]
        if not terms:
            return []
        fts = " OR ".join(f'"{w.replace(chr(34), "")}"*' if len(w) > 3 else f'"{w}"' for w in terms[:12])
        with self._lock:
            rows = self.db.execute(
                "SELECT f.* FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
                "WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts) LIMIT ?", (fts, limit)).fetchall()
        return [_fact(r) for r in rows]

    def owner_name(self) -> str | None:
        with self._lock:
            r = self.db.execute("SELECT text FROM facts WHERE subject='owner_name'").fetchone()
        if not r:
            return None
        m = re.search(r"name is (.+)$", r["text"], re.I)
        return (m.group(1) if m else r["text"]).strip(" .")

    def upcoming(self, today: date, days: int = 14) -> list[tuple[Fact, int]]:
        """Birthdays / commitments due within `days` (with days-until)."""
        out = []
        for f in self.all_facts():
            if not f.due:
                continue
            d = _next_date(f.due, today)
            if d is None:
                continue
            delta = (d - today).days
            if 0 <= delta <= days:
                out.append((f, delta))
        out.sort(key=lambda x: x[1])
        return out

    def context_for(self, query: str, today: date, budget_chars: int = 900) -> list[str]:
        """Lines of memory for the LLM prompt: name, relevant facts, upcoming dates, recent mood."""
        lines: list[str] = []
        used: list[int] = []
        name = self.owner_name()
        if name:
            lines.append(f"The owner's name is {name}.")
        for f, days in self.upcoming(today):
            when = "today" if days == 0 else ("tomorrow" if days == 1 else f"in {days} days")
            lines.append(f"Coming up {when}: {f.text}.")
            used.append(f.id)
        for f in self.search(query):
            if f.id not in used and f.subject != "owner_name":
                lines.append(f"{f.text}.")
                used.append(f.id)
        with self._lock:
            prefs = self.db.execute("SELECT * FROM facts WHERE kind='preference' ORDER BY uses DESC, updated DESC LIMIT 3").fetchall()
        for r in prefs:
            if r["id"] not in used:
                lines.append(f"{r['text']}.")
                used.append(r["id"])
        mood = self.recent_mood_summary(today)
        if mood:
            lines.append(mood)
        out, total = [], 0
        for ln in lines:
            if total + len(ln) > budget_chars:
                break
            out.append(ln)
            total += len(ln) + 1
        if used:
            now = self.clock()
            with self._lock:
                self.db.executemany("UPDATE facts SET uses=uses+1, last_used=? WHERE id=?", [(now, i) for i in used])
        return out

    def recall_all(self, limit: int = 12) -> list[str]:
        with self._lock:
            rows = self.db.execute("SELECT id, text FROM facts ORDER BY updated DESC LIMIT ?", (limit,)).fetchall()
        self._touch([r["id"] for r in rows])
        return [r["text"] for r in rows]

    # ------------------------------------------------------------------ mood diary
    def log_mood(self, mood: str, source: str, score: float | None = None, ts: float | None = None) -> None:
        ts = self.clock() if ts is None else ts
        day = datetime.fromtimestamp(ts).date().isoformat()
        with self._lock:
            self.db.execute("INSERT INTO mood_diary(ts, day, mood, source, score) VALUES (?,?,?,?,?)",
                            (ts, day, mood, source, score))

    def mood_days(self, today: date, days: int = 7) -> dict[str, dict[str, int]]:
        start = (today - timedelta(days=days - 1)).isoformat()
        out: dict[str, dict[str, int]] = {}
        with self._lock:
            for r in self.db.execute("SELECT day, mood, COUNT(*) n FROM mood_diary WHERE day>=? GROUP BY day, mood",
                                     (start,)):
                out.setdefault(r["day"], {})[r["mood"]] = r["n"]
        return out

    def recent_mood_summary(self, today: date) -> str | None:
        days = self.mood_days(today, 3)
        parts = []
        for d in sorted(days):
            moods = days[d]
            top = max(moods, key=moods.get)
            if top in ("sad", "tired", "stressed", "lonely") and moods[top] >= 3:
                label = "today" if d == today.isoformat() else datetime.fromisoformat(d).strftime("%A")
                parts.append(f"{label} they seemed {top}")
        return ("Mood diary: " + "; ".join(parts) + ".") if parts else None

    # ------------------------------------------------------------------ events
    def log_event(self, kind: str, detail: str = "", ts: float | None = None) -> None:
        with self._lock:
            self.db.execute("INSERT INTO events(ts, kind, detail) VALUES (?,?,?)",
                            (self.clock() if ts is None else ts, kind, detail))

    def last_event(self, kind: str) -> float | None:
        with self._lock:
            r = self.db.execute("SELECT MAX(ts) FROM events WHERE kind=?", (kind,)).fetchone()
        return r[0] if r and r[0] is not None else None

    def count_events(self, kind: str, since: float) -> int:
        with self._lock:
            return self.db.execute("SELECT COUNT(*) FROM events WHERE kind=? AND ts>=?", (kind, since)).fetchone()[0]


def _fact(r: sqlite3.Row) -> Fact:
    return Fact(r["id"], r["kind"], r["text"], r["subject"], r["due"], r["created"])


def _strip_pronouns(text: str) -> str:
    t = re.sub(r"\b(i|my|me|that|the|owner'?s?|likes?|loves?)\b", " ", text.lower())
    return re.sub(r"\s+", " ", t).strip()


def _next_date(due: str, today: date) -> date | None:
    """due is 'MM-DD' (yearly, birthdays) or 'YYYY-MM-DD' (one-off)."""
    try:
        if re.fullmatch(r"\d{2}-\d{2}", due):
            m, d = map(int, due.split("-"))
            for year in (today.year, today.year + 1):
                try:
                    cand = date(year, m, d)
                except ValueError:          # 29 Feb in a non-leap year
                    cand = date(year, m, 28)
                if cand >= today:
                    return cand
            return None
        return date.fromisoformat(due)
    except ValueError:
        return None
