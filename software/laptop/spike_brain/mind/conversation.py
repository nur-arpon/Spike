"""Prompt building and conversation history.

Message layout (chosen for Ollama's prompt cache):
  [system: persona prompt]          fixed per persona -> cached
  [history: user/assistant pairs]   grows; trimmed in blocks, not one by one
  [user: "[Context: time, camera, memories, notes] The owner says: ..."]
Only the tail changes between turns, so the model re-reads ~100 tokens, not
the whole prompt, and the first word comes back fast.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ..config import Persona
from .reply import LLM_ACTIONS, LLM_MOODS


def system_prompt(persona: Persona, owner_name: str | None, helpline: dict[str, str]) -> str:
    fill = {"name": persona.name, "owner_ref": owner_name or "your owner",
            "moods": ", ".join(LLM_MOODS), "actions": ", ".join(LLM_ACTIONS), **helpline}
    try:
        return persona.system_prompt.format(**fill)
    except (KeyError, IndexError):
        return persona.system_prompt


def time_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "late at night"


@dataclass
class Situation:
    """What Spike knows about right now (filled by the brain each turn)."""
    now: datetime
    owner_name: str | None = None
    owner_present: bool | None = None       # None = no camera
    owner_emotion: str | None = None        # happy | sad | tired | neutral
    memories: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # safety mode, honesty hint, nudges...
    battery: float | None = None
    other_name: str | None = None           # the other persona's name (for "where is Spike?")

    def render(self) -> str:
        n = self.now
        parts = [f"Right now it is {n.strftime('%A %d %B %Y')}, {n.strftime('%I:%M %p').lstrip('0')} "
                 f"({time_of_day(n.hour)})."]
        if self.owner_present is True:
            mood = f" and looks {self.owner_emotion}" if self.owner_emotion and self.owner_emotion != "neutral" else ""
            parts.append(f"Your camera sees the owner at the desk{mood}.")
        if self.battery is not None and self.battery < 30:
            parts.append(f"Your battery is low ({int(self.battery)} percent): you feel hungry.")
        if self.memories:
            parts.append("What you remember about the owner (use only if relevant, never invent more): "
                         + " ".join(self.memories))
        if self.other_name:
            parts.append(f"You have a second mode: {self.other_name}. The owner switches by saying "
                         f"'{self.other_name} mode'.")
        parts.extend(self.notes)
        return " ".join(parts)


class Conversation:
    def __init__(self, history_turns: int = 6):
        self.max_turns = max(1, history_turns)
        self.history: list[dict] = []

    def build(self, system: str, situation: Situation, user_text: str) -> list[dict]:
        # The "right now" context rides in the last user message: several chat
        # templates (Qwen's included) reject a system message after the first.
        # History keeps only what the owner said, so the cached prefix stays valid.
        msgs = [{"role": "system", "content": system}]
        msgs.extend(self.history)
        msgs.append({"role": "user", "content": f"[Context, not said by the owner: {situation.render()}]\n"
                                                f"The owner says: {user_text}"})
        return msgs

    def add(self, user_text: str, assistant_raw: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_raw.strip()})
        if len(self.history) > 2 * (self.max_turns + 3):
            # trim in a block of 3 exchanges so the prompt cache survives most turns
            self.history = self.history[-2 * self.max_turns:]

    def clear(self) -> None:
        self.history.clear()

    @property
    def turns(self) -> int:
        return len(self.history) // 2
