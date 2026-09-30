"""Model plumbing without a model: cloud request shape, SSE parsing, and the
local-first router."""
import pytest

from spike_brain.mind.conversation import Conversation, Situation, system_prompt
from spike_brain.mind.llm import GeminiLLM, LLMError, LLMRouter


class Scripted:
    def __init__(self, name, pieces=None, fail_after=None):
        self.name = name
        self.pieces = pieces or ["Hi", " there."]
        self.fail_after = fail_after
        self.calls = 0

    async def stream(self, messages, max_tokens=None):
        self.calls += 1
        for i, p in enumerate(self.pieces):
            if self.fail_after is not None and i >= self.fail_after:
                raise LLMError(f"{self.name} broke")
            yield p


async def collect(router, msgs=None):
    return "".join([p async for p in router.stream(msgs or [{"role": "user", "content": "x"}])])


async def test_local_first_and_cloud_only_when_local_fails():
    local, cloud = Scripted("ollama"), Scripted("gemini", ["Cloud."])
    r = LLMRouter(local, cloud, "local_fails")
    assert await collect(r) == "Hi there." and cloud.calls == 0 and r.last_used == "ollama"
    broken = Scripted("ollama", fail_after=0)
    r = LLMRouter(broken, cloud, "local_fails")
    assert await collect(r) == "Cloud." and r.last_used == "gemini"


async def test_no_cloud_means_errors_surface():
    r = LLMRouter(Scripted("ollama", fail_after=0), None)
    with pytest.raises(LLMError):
        await collect(r)


async def test_half_spoken_reply_is_not_restarted_elsewhere():
    cloud = Scripted("gemini", ["Cloud."])
    r = LLMRouter(Scripted("ollama", ["One.", " Two."], fail_after=1), cloud)
    with pytest.raises(LLMError):
        await collect(r)
    assert cloud.calls == 0


def test_gemini_request_shape():
    body = GeminiLLM.build_body([{"role": "system", "content": "Be Spike."},
                                 {"role": "user", "content": "hi"}, {"role": "assistant", "content": "[happy] Hi!"},
                                 {"role": "user", "content": "joke?"}, {"role": "user", "content": "please"}],
                                0.8, 110)
    assert body["systemInstruction"]["parts"][0]["text"] == "Be Spike."
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["contents"][-1]["parts"][0]["text"] == "joke?\nplease"
    assert body["generationConfig"]["maxOutputTokens"] == 110


def test_gemini_sse_parsing():
    line = 'data: {"candidates":[{"content":{"parts":[{"text":"Hello"},{"text":" you"}]}}]}'
    assert GeminiLLM.parse_sse_line(line) == "Hello you"
    assert GeminiLLM.parse_sse_line("event: ping") == "" and GeminiLLM.parse_sse_line("data: {bad") == ""


def test_gemini_needs_a_key():
    with pytest.raises(ValueError):
        GeminiLLM("")


def test_prompt_layout_keeps_the_cacheable_prefix(settings):
    from datetime import datetime
    conv = Conversation(history_turns=2)
    sysmsg = system_prompt(settings.personas["dog"], "Arpon", settings.helpline())
    sit = Situation(now=datetime(2026, 9, 28, 19, 5), owner_name="Arpon", owner_present=True,
                    owner_emotion="sad", memories=["The owner loves sushi."], notes=["NOTE"], battery=20,
                    other_name="Spicy")
    m1 = conv.build(sysmsg, sit, "hello")
    assert [m["role"] for m in m1] == ["system", "user"]            # only ONE system message (Qwen rule)
    ctx = m1[-1]["content"]
    for bit in ("Monday 28 September 2026", "7:05 PM", "looks sad", "loves sushi", "NOTE", "battery is low",
                "Spicy mode", "The owner says: hello"):
        assert bit in ctx, bit
    for i in range(6):
        conv.add(f"q{i}", f"[happy] a{i}")
    assert conv.turns <= 5 and conv.history[-1]["content"] == "[happy] a5"
    m2 = conv.build(sysmsg, sit, "next")
    assert m2[0] == m1[0] and m2[1]["content"] == conv.history[0]["content"]
