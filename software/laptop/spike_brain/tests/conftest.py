"""Shared test helpers. Every test runs with no mic, no camera and no GPU."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAPTOP = Path(__file__).resolve().parents[2]
if str(LAPTOP) not in sys.path:
    sys.path.insert(0, str(LAPTOP))

from spike_brain.config import Settings  # noqa: E402

FACE_V2 = LAPTOP.parent / "face_v2"
MODELS = LAPTOP / "models"


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Real default settings + personas, but memory in a temp folder, no user overrides and no
    personal wake words (the owner's own data/personal_wake_words.toml must not change tests)."""
    return Settings.load(user_toml=None, env_file=tmp_path / "none.env",
                         overrides={"memory": {"db_path": str(tmp_path / "mem.sqlite"), "llm_extraction": False},
                                    "safety": {"llm_crisis_check": False},
                                    "wake": {"personal_file": ""}})


class FakeLLM:
    """Streams a canned reply in small pieces, like Ollama does."""
    name = "fake"

    def __init__(self, replies: list[str] | None = None, piece: int = 4):
        self.replies = list(replies or ["[mood:happy] [action:headTilt] Hello there! Nice to see you."])
        self.piece = piece
        self.calls: list[list[dict]] = []

    async def stream(self, messages, max_tokens=None):
        self.calls.append(messages)
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        for i in range(0, len(text), self.piece):
            yield text[i:i + self.piece]

    async def complete_json(self, system, user, schema, max_tokens=120, timeout=8.0):
        return '{"level": "none", "facts": []}'

    async def warm_up(self, system_prompt):
        return 0.0

    async def unload(self):
        return None
