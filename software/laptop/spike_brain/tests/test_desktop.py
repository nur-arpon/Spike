"""The Windows desktop app's light brain (config/desktop.toml, software/app/DESIGN.md "Desktop"):
Gemini as the main model, Gemini TTS + Windows' own voice, the v1.8 `voice_style` message, the
packaged-paths settings and the helper-process life cycle (parent watch, stdin EOF).

Gemini is NEVER called for real here: a local mock server stands in for Google, and the key is a
made-up test value (never the owner's)."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import subprocess
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

from spike_brain import protocol as P
from spike_brain.brain import Brain, RunOptions
from spike_brain.config import ConfigError, Settings
from spike_brain.mind.llm import GeminiLLM, LLMError
from spike_brain.speech import gemini_tts as G
from spike_brain.speech.engines import VoiceChain

from .test_applink import APP_HELLO, Phone, _join

FAKE_KEY = "AIzaSyTESTONLY0123456789abcdefghijklmnop"      # not a real key; never sent anywhere but the mock
LAPTOP = Path(__file__).resolve().parents[2]
DART_VOICES = LAPTOP.parent / "app" / "spike_app" / "lib" / "away" / "ai" / "gemini_voices.dart"


# ------------------------------------------------------------------ a mock Google
class MockGemini:
    """A tiny HTTP server that answers like the Gemini REST API. `plan` maps a model (or
    "interactions") to a list of responses, used in order (the last one repeats)."""

    def __init__(self):
        self.requests: list[dict] = []
        self.plan: dict[str, list[tuple[int, object]]] = {}
        mock = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                mock.requests.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
                m = re.search(r"/models/([^:]+):", self.path)
                target = m.group(1) if m else "interactions"
                steps = mock.plan.get(target) or [(404, {"error": {"message": "no such model"}})]
                status, answer = steps.pop(0) if len(steps) > 1 else steps[0]
                if status == 200 and "streamGenerateContent" in self.path:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    for piece in answer:
                        data = {"candidates": [{"content": {"parts": [{"text": piece}]}}]}
                        self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
                        self.wfile.flush()
                    return
                raw = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1beta"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def google():
    m = MockGemini()
    yield m
    m.close()


def wav_b64(seconds=0.2, rate=24000) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        t = np.arange(int(seconds * rate)) / rate
        w.writeframes((np.sin(2 * np.pi * 220 * t) * 8000).astype("<i2").tobytes())
    return base64.b64encode(buf.getvalue()).decode()


def audio_answer(data: str) -> dict:
    return {"id": "x", "steps": [{"content": [{"type": "audio", "data": data}]}]}


# ------------------------------------------------------------------ Gemini as the main model
async def collect(llm, msgs=None):
    return "".join([p async for p in llm.stream(msgs or [{"role": "user", "content": "hi"}])])


async def test_gemini_streams_and_moves_on_when_a_model_is_rate_limited(google):
    google.plan = {"m1": [(429, {"error": {"status": "RESOURCE_EXHAUSTED"}})], "m2": [(200, ["[happy] Hi", " there!"])]}
    llm = GeminiLLM(FAKE_KEY, models=["m1", "m2"], base_url=google.url)
    assert await collect(llm) == "[happy] Hi there!" and llm.model == "m2"
    assert all(r["key"] == FAKE_KEY and FAKE_KEY not in r["path"] for r in google.requests)   # header only
    assert FAKE_KEY not in repr(llm)


async def test_gemini_gone_model_is_skipped_and_bad_key_surfaces(google):
    google.plan = {"m1": [(404, {})], "m2": [(403, {"error": {"message": "API key not valid"}})]}
    llm = GeminiLLM(FAKE_KEY, models=["m1", "m2"], base_url=google.url)
    with pytest.raises(LLMError) as e:
        await collect(llm)
    assert e.value.kind == "bad_key" and "m1" in llm._gone and FAKE_KEY not in str(e.value)


async def test_gemini_retries_without_the_thinking_setting(google):
    google.plan = {"m1": [(400, {"error": {"message": "thinking_level is not supported"}}), (200, ["Okay."])]}
    llm = GeminiLLM(FAKE_KEY, models=["m1"], base_url=google.url)
    assert await collect(llm) == "Okay."
    first, second = google.requests
    assert "thinkingConfig" in first["body"]["generationConfig"]
    assert "thinkingConfig" not in second["body"]["generationConfig"]


async def test_gemini_complete_json_and_blocked_replies(google):
    google.plan = {"m1": [(200, {"candidates": [{"content": {"parts": [{"text": '{"level": "none"}'}]}}]}),
                          (200, {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]})]}
    llm = GeminiLLM(FAKE_KEY, models=["m1"], base_url=google.url)
    schema = {"type": "object", "properties": {"level": {"type": "string"}}}
    assert json.loads(await llm.complete_json("classify", "hello", schema)) == {"level": "none"}
    gen = google.requests[0]["body"]["generationConfig"]
    assert gen["responseMimeType"] == "application/json" and gen["responseJsonSchema"] == schema
    assert gen["temperature"] == 0.0 and google.requests[0]["path"].endswith("/models/m1:generateContent")
    with pytest.raises(LLMError) as e:
        await llm.complete_json("classify", "hello", schema)
    assert e.value.kind == "blocked"
    assert await llm.warm_up("x") == 0.0 and await llm.gpu_share() is None


# ------------------------------------------------------------------ Gemini TTS
def test_tts_request_shape_and_audio_parsing():
    body = G.tts_body("gemini-3.8-flash-tts", "Hi!", "Fenrir", "warm")
    assert body["input"][0]["content"][0]["annotations"] == [{"type": "speech_metadata", "style": "warm"}]
    assert body["generation_config"]["speech_config"] == [{"voice": "Fenrir"}]
    pcm, rate = G.tts_audio(audio_answer(wav_b64(0.1, 24000)))
    assert rate == 24000 and len(pcm) == 2400 and pcm.dtype == np.int16
    raw = (np.ones(480, dtype="<i2") * 5).tobytes()                      # raw L16, no header
    pcm, rate = G.tts_audio({"steps": [{"content": [{"type": "audio", "data": base64.b64encode(raw).decode()}]}]})
    assert rate == 24000 and len(pcm) == 480 and G.tts_audio({"steps": []}) is None


def test_tts_uses_the_picked_style_and_rests_after_429(google):
    google.plan = {"interactions": [(429, {"error": {"status": "RESOURCE_EXHAUSTED"}}), (200, audio_answer(wav_b64()))]}
    now = [1000.0]
    picks = G.VoicePicks({"dog": "street"})
    eng = G.GeminiTTSEngine(FAKE_KEY, picks=picks, models=("flash", "lite"), base_url=google.url, clock=lambda: now[0])
    pcm, rate = eng.synthesize("Get off the couch, champ.", "dog")
    assert len(pcm) > 0 and eng.last_model == "lite"
    first, second = (r["body"] for r in google.requests)
    assert first["model"] == "flash" and second["model"] == "lite"
    assert second["generation_config"]["speech_config"][0]["voice"] == "Algenib"
    assert second["input"][0]["content"][0]["annotations"][0]["style"] == G._STREET_TTS
    # the soft direction for sad lines, whatever the style
    eng.synthesize("I'm here for you.", "dog", soft=True)
    assert google.requests[-1]["body"]["input"][0]["content"][0]["annotations"][0]["style"] == G.SOFT_TTS["dog"]
    assert google.requests[-1]["body"]["model"] == "lite"                # flash still resting
    now[0] += 901
    eng.synthesize("Back again.", "cat")
    assert google.requests[-1]["body"]["model"] == "flash"               # rested long enough
    assert google.requests[-1]["body"]["generation_config"]["speech_config"][0]["voice"] == "Kore"


def test_tts_bad_key_stops_asking(google):
    google.plan = {"interactions": [(401, {"error": {"message": "API key not valid"}})]}
    eng = G.GeminiTTSEngine(FAKE_KEY, base_url=google.url)
    with pytest.raises(G.TtsError) as e:
        eng.synthesize("Hi.", "dog")
    assert e.value.kind == "bad_key" and not eng.available
    n = len(google.requests)
    with pytest.raises(G.TtsError):
        eng.synthesize("Hi.", "dog")
    assert len(google.requests) == n


def test_voice_picks_validate_and_default():
    p = G.VoicePicks({"dog": "nope", "cat": "caring"})
    assert p.as_dict() == {"dog": "energetic", "cat": "caring"}
    assert not p.set("dog", "sassy") and p.set("dog", "street") and p.style("dog").voice == "Algenib"
    assert G.style_by_id("cat", None).voice == "Kore" and G.style_by_id("dog", None).voice == "Fenrir"


def _dart_consts(src: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"const (_\w+) =((?:\s*'(?:[^'\\]|\\.)*')+);", src):
        out[m.group(1)] = "".join(re.findall(r"'((?:[^'\\]|\\.)*)'", m.group(2))).replace("\\'", "'")
    return out


@pytest.mark.skipif(not DART_VOICES.exists(), reason="the app sources are not next to the brain")
def test_styles_match_the_phone_app_exactly():
    """Same Google voice and the same style prompt for every style as lib/away/ai/gemini_voices.dart."""
    src = DART_VOICES.read_text(encoding="utf-8")
    consts = _dart_consts(src)
    dart = {}
    for mode, block in re.findall(r"'(dog|cat)': \[(.*?)\n  \],", src, re.S):
        for sid, voice, tts in re.findall(r"id: '(\w+)'.*?voice: '(\w+)'.*?tts: (_\w+)", block, re.S):
            dart[(mode, sid)] = (voice, consts[tts])
    ours = {(m, s.id): (s.voice, s.tts) for m, styles in G.STYLES.items() for s in styles}
    assert ours == dart and len(ours) == 8
    assert "const defaultStyle = {'dog': 'energetic', 'cat': 'sassy'};" in src
    assert G.DEFAULT_STYLE == {"dog": "energetic", "cat": "sassy"}
    for mode, prompt in G.SOFT_TTS.items():
        assert f"'{prompt}'" in src, mode


# ------------------------------------------------------------------ the voice chain
class FakeGemini:
    def __init__(self, ok=True):
        self.ok, self.available, self.calls = ok, True, []

    def synthesize(self, text, mode, soft=False):
        self.calls.append((text, mode, soft))
        if not self.ok:
            raise G.TtsError("network", "down")
        return (np.ones(2400, dtype=np.int16) * 3000), 24000


class FakeWindows:
    def __init__(self):
        self.calls = []

    def synthesize(self, text, mode="dog", soft=False):
        self.calls.append((text, mode, soft))
        return (np.ones(2205, dtype=np.int16) * 3000), 22050


def test_chain_is_gemini_first_then_windows_and_keeps_one_voice_per_reply():
    gem, win = FakeGemini(), FakeWindows()
    c = VoiceChain("spicy", engine="gemini", gemini=gem, windows=win, mode="cat", say_as_table={"000": "triple zero"})
    assert c.order() == ["owner", "gemini", "kokoro", "piper", "windows"]
    sp = c.synthesize("Call 000 now.", soft=True, utt="u1")
    assert sp.engine == "gemini" and gem.calls[-1] == ("Call triple zero now.", "cat", True)
    assert sp.text == "Call 000 now."                                    # captions keep the digits
    gem.ok = False
    assert c.synthesize("Second.", utt="u2").engine == "windows"
    gem.ok = True
    assert c.synthesize("Third.", utt="u2").engine == "windows"           # same reply: same voice
    assert c.synthesize("New reply.", utt="u3").engine == "gemini"
    gem.available = False                                                 # resting after a 429: no call at all
    n = len(gem.calls)
    assert c.synthesize("Resting.", utt="u4").engine == "windows" and len(gem.calls) == n


def test_old_chains_are_unchanged():
    assert VoiceChain("spike", engine="kokoro").order() == ["owner", "kokoro", "piper"]
    assert VoiceChain("spike", engine="turbo").order() == ["owner", "cache", "turbo", "kokoro", "piper"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows' own voice")
def test_windows_voice_renders_silently_into_memory():
    pytest.importorskip("comtypes")
    from spike_brain.speech.windows_tts import WindowsVoice, pick_voice
    v = WindowsVoice()
    try:
        pcm, rate = v.synthesize("Hello there.", "dog")
        assert rate == 22050 and len(pcm) > rate // 4 and np.abs(pcm).max() > 100
    finally:
        v.close()
    voices = [{"name": "A", "gender": "Female", "language": "409"}, {"name": "B", "gender": "Male", "language": "809"},
              {"name": "C", "gender": "Male", "language": "409"}]
    assert pick_voice(voices, "dog") == 2 and pick_voice(voices, "cat") == 0 and pick_voice([], "dog") is None


# ------------------------------------------------------------------ settings for the packaged brain
def test_desktop_profile_and_packaged_paths(tmp_path):
    home, models = tmp_path / "home", tmp_path / "pkg" / "models"
    s = Settings.load(user_toml=home / "spike_settings.toml", env_file=home / ".env", root=home,
                      profile="desktop", models_root=models)
    assert s.llm.provider == "gemini" and s.tts.engine == "gemini" and s.stt.device == "cpu"
    assert s.vision.enabled is False and s.llm.on_demand is False and s.server.host == "0.0.0.0"
    assert s.path("data/spike_memory.sqlite") == home / "data" / "spike_memory.sqlite"
    assert s.path(s.wake.vosk_model) == models / "vosk" / "vosk-model-small-en-us-0.15"
    assert s.path(str(tmp_path / "abs.txt")) == tmp_path / "abs.txt"
    assert s.override({"x": 1}).models_root == models
    with pytest.raises(ConfigError):
        Settings.load(user_toml=None, profile="../default")


def test_app_flags_build_the_packaged_settings(tmp_path):
    from spike_brain import app
    (tmp_path / "spike_settings.toml").write_text('[life]\ngreet_on_start = false\n', encoding="utf-8")
    args = app.parse_args(["--profile", "desktop", "--home", str(tmp_path), "--models", str(tmp_path / "m"),
                           "--parent-pid", "1234", "--stop-on-stdin-eof"])
    s = app.load_settings(args)
    assert s.root == tmp_path.resolve() and s.models_root == (tmp_path / "m").resolve()
    assert s.life.greet_on_start is False and s.llm.provider == "gemini"
    assert args.parent_pid == 1234 and args.stop_on_stdin_eof


def test_parent_watch_fires_when_the_parent_ends():
    from spike_brain import app
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.4)"])
    fired = threading.Event()
    app.watch_parent(child.pid, fired.set)
    assert not fired.wait(0.1)
    child.wait(5)
    assert fired.wait(5)


def test_stdin_eof_stops_the_helper():
    """The desktop app closes the helper's stdin to ask for a clean stop."""
    code = ("import sys, threading; sys.path.insert(0, r'%s'); from spike_brain import app; "
            "e = threading.Event(); app.watch_stdin(e.set); print('ok' if e.wait(5) else 'no', flush=True)") % LAPTOP
    p = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    time.sleep(0.3)
    p.stdin.close()
    assert p.stdout.read().strip() == "ok"
    p.wait(5)


# ------------------------------------------------------------------ the brain with Gemini, end to end (mock)
@pytest.fixture
async def gemini_brain(tmp_path, google):
    s = Settings.load(user_toml=None, env_file=tmp_path / "none.env", root=tmp_path, profile="desktop",
                      overrides={"server": {"host": "127.0.0.1"},
                                 "memory": {"db_path": str(tmp_path / "mem.sqlite"), "llm_extraction": False},
                                 "safety": {"llm_crisis_check": False},
                                 "life": {"quiet_hours": ["03:00", "03:01"], "greet_on_start": False},
                                 "audio": {"output": "none"},
                                 "llm": {"gemini_models": ["m1"], "gemini_base_url": google.url}})
    s.env["GEMINI_API_KEY"] = FAKE_KEY
    brain = Brain(s, RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=True, llm_on_demand=False,
                                port=0))
    await brain.start()
    ws = await _join(brain.server.port, APP_HELLO)
    phone = Phone(ws)
    hello = await phone.pump(lambda m: m["type"] == "hello")
    await phone.pump(lambda m: m["type"] == "memory")
    yield brain, phone, hello
    await ws.close()
    await brain.shutdown()


async def test_gemini_brain_answers_through_the_persona_and_safety_pipeline(gemini_brain, google):
    brain, phone, hello = gemini_brain
    assert hello["voice_style"] == {"dog": "energetic", "cat": "sassy"}
    assert phone.last("brain_status")["llm"] == "ready" and brain.local_llm.name == "gemini"
    google.plan = {"m1": [(200, ["[mood:happy] Oh hi! ", "I missed you."])]}
    await phone.send("text", text="I'm home, buddy")
    said = await phone.pump(lambda m: m["type"] == "say" and "missed" in m.get("text", ""), timeout=8)
    assert said is not None and "[" not in said["text"]
    assert any(m["type"] == "mood" and m["mood"] == "happy" for m in phone.seen)
    req = next(r for r in google.requests if "streamGenerateContent" in r["path"])
    assert "Spike" in req["body"]["systemInstruction"]["parts"][0]["text"]      # the persona prompt
    assert "I'm home, buddy" in json.dumps(req["body"]["contents"])


async def test_gemini_brain_crisis_line_never_reaches_google(gemini_brain, google):
    brain, phone, _ = gemini_brain
    google.plan = {"m1": [(200, ["[mood:happy] Cool!"])]}
    await phone.send("text", text="I want to kill myself")
    said = await phone.pump(lambda m: m["type"] == "say" and m.get("text"), timeout=8)
    assert said is not None
    await phone.pump(timeout=1.0)
    text = " ".join(m.get("text", "") for m in phone.seen if m["type"] == "say")
    assert "13 11 14" in text or "Lifeline" in text
    assert not any("streamGenerateContent" in r["path"] for r in google.requests)


async def test_voice_style_is_kept_validated_and_shared(gemini_brain, tmp_path):
    brain, phone, _ = gemini_brain
    await phone.send("voice_style", mode="dog", style="street")
    got = await phone.pump(lambda m: m["type"] == "voice_style")
    assert got["styles"] == {"dog": "street", "cat": "sassy"}
    assert brain.voice_picks.style("dog").voice == "Algenib"
    assert json.loads((tmp_path / "app_prefs.json").read_text())["voice_styles"]["dog"] == "street"   # beside the memory
    await phone.send("voice_style", mode="cat", style="street")
    err = await phone.pump(lambda m: m["type"] == "error")
    assert err["code"] == "bad_value"
    with pytest.raises(P.ProtocolError):
        P.validate({"v": 1, "id": 1, "type": "voice_style", "mode": "bird", "style": "x"}, "from_app")


async def test_no_key_means_scripted_lines_and_brain_status_off(tmp_path):
    s = Settings.load(user_toml=None, env_file=tmp_path / "none.env", root=tmp_path, profile="desktop",
                      overrides={"server": {"host": "127.0.0.1"}, "memory": {"db_path": str(tmp_path / "m.sqlite")},
                                 "life": {"greet_on_start": False}})
    s.env.pop("GEMINI_API_KEY", None)
    brain = Brain(s, RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=True, llm_on_demand=False,
                                port=0))
    await brain.start()
    try:
        assert brain.llm is None and brain.app.llm_state() == "off"
    finally:
        await brain.shutdown()


async def test_ollama_brain_hello_has_no_voice_style(settings):
    brain = Brain(settings.override({"life": {"greet_on_start": False}}),
                  RunOptions(mic=False, camera=False, tts=False, text_only=True, llm=False, port=0))
    await brain.start()
    try:
        ws = await _join(brain.server.port, APP_HELLO)
        phone = Phone(ws)
        hello = await phone.pump(lambda m: m["type"] == "hello")
        assert "voice_style" not in hello
        await ws.close()
    finally:
        await brain.shutdown()


def test_protocol_doc_has_v18():
    text = (LAPTOP.parent / "protocol" / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "### 10.11" in text and "`voice_style`" in text and "v1.8" in text
    assert "voice_style" in P.APP_ONLY and "voice_style" in P.BRAIN_TO_APP


def test_owner_toml_with_bom_is_read_and_a_mistake_names_the_file(tmp_path):
    """PowerShell 5 and Notepad write a byte-order mark: that once crashed the brain silently at start."""
    from spike_brain.config import read_toml
    f = tmp_path / "spike_settings.toml"
    f.write_bytes(b"\xef\xbb\xbf[audio]\noutput = \"none\"\n")
    assert read_toml(f) == {"audio": {"output": "none"}}
    f.write_text("[audio\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="spike_settings.toml"):
        read_toml(f)
