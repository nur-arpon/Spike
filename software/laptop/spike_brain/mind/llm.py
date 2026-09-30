"""Language models: local Ollama (default) and an optional cloud fallback.

Local first, always: the cloud client is only built when [cloud] enabled =
true AND a key is in .env, and it only ever receives text.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import AsyncIterator

log = logging.getLogger("spike.llm")


class LLMError(Exception):
    """A model failed. `kind`: other | rate_limited | bad_key | blocked | network (never contains a key)."""

    def __init__(self, message: str = "", kind: str = "other"):
        super().__init__(message)
        self.kind = kind


class OllamaLLM:
    name = "ollama"

    def __init__(self, host: str, model: str, fallback_models: list[str] | None = None, *, num_ctx: int = 4096,
                 temperature: float = 0.8, top_p: float = 0.9, repeat_penalty: float = 1.1,
                 max_tokens: int = 110, keep_alive: str = "60m", first_token_timeout_s: float = 8,
                 total_timeout_s: float = 25, gpu_layers: int = -1):
        import ollama
        self.client = ollama.AsyncClient(host=host)
        self.host = host
        self.model = model
        self.candidates = [model] + list(fallback_models or [])
        self.options = {"num_ctx": num_ctx, "temperature": temperature, "top_p": top_p,
                        "repeat_penalty": repeat_penalty, "num_predict": max_tokens}
        if gpu_layers is not None and gpu_layers >= 0:     # -1 = Ollama puts as many layers on the card as fit
            self.options["num_gpu"] = int(gpu_layers)
        self.keep_alive = keep_alive
        self.first_token_timeout_s = first_token_timeout_s
        self.total_timeout_s = total_timeout_s
        self.last_stats: dict = {}

    async def ensure_model(self) -> str:
        """Pick the first configured model that is installed. Raises LLMError if Ollama is down."""
        try:
            listing = await asyncio.wait_for(self.client.list(), timeout=5)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"Ollama is not reachable at {self.host} ({type(e).__name__})") from e
        have = {m.model for m in listing.models}
        for m in self.candidates:
            if m in have or (":" not in m and f"{m}:latest" in have):
                if m != self.model:
                    log.warning("model %s is not installed; using %s", self.model, m)
                self.model = m
                return m
        raise LLMError(f"none of {self.candidates} is installed in Ollama (have: {sorted(have)})")

    async def warm_up(self, system_prompt: str) -> float:
        """Load the model onto the GPU and cache the persona prompt. Returns seconds."""
        t = time.perf_counter()
        await self.client.chat(model=self.model, messages=[{"role": "system", "content": system_prompt},
                                                           {"role": "user", "content": "hi"}],
                               think=False, keep_alive=self.keep_alive,
                               options={**self.options, "num_predict": 1})
        return time.perf_counter() - t

    async def gpu_share(self) -> float | None:
        """Fraction of the loaded model that sits in GPU memory (1.0 = all), or None."""
        try:
            ps = await asyncio.wait_for(self.client.ps(), timeout=3)
        except Exception:  # noqa: BLE001
            return None
        for m in ps.models:
            if m.model == self.model or m.name == self.model:
                return (m.size_vram or 0) / m.size if m.size else None
        return None

    async def stream(self, messages: list[dict], max_tokens: int | None = None) -> AsyncIterator[str]:
        """Yield reply text pieces. Raises LLMError on connection problems or timeouts."""
        start = time.perf_counter()
        try:
            it = await asyncio.wait_for(
                self.client.chat(model=self.model, messages=messages, stream=True, think=False,
                                 keep_alive=self.keep_alive,
                                 options={**self.options, **({'num_predict': max_tokens} if max_tokens else {})}),
                timeout=self.first_token_timeout_s)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"local model failed to start ({type(e).__name__}: {e})") from e
        first = True
        try:
            while True:
                budget = self.first_token_timeout_s if first else max(1.0, self.total_timeout_s - (time.perf_counter() - start))
                try:
                    chunk = await asyncio.wait_for(it.__anext__(), timeout=budget)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as e:
                    raise LLMError("local model timed out") from e
                piece = chunk.message.content or ""
                if chunk.done:
                    self.last_stats = {"eval_count": chunk.eval_count, "eval_ms": (chunk.eval_duration or 0) / 1e6,
                                       "prompt_count": chunk.prompt_eval_count,
                                       "prompt_ms": (chunk.prompt_eval_duration or 0) / 1e6}
                if piece:
                    first = False
                    yield piece
                if chunk.done:
                    break
        except LLMError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"local model stream failed ({type(e).__name__}: {e})") from e
        finally:
            aclose = getattr(it, "aclose", None)
            if aclose:
                try:
                    await aclose()
                except Exception:  # noqa: BLE001
                    pass

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 120,
                            timeout: float = 8.0) -> str:
        """One short, deterministic, JSON-constrained answer (classifiers, extraction)."""
        try:
            r = await asyncio.wait_for(self.client.chat(
                model=self.model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=schema, think=False, keep_alive=self.keep_alive,
                options={**self.options, "temperature": 0.0, "num_predict": max_tokens}), timeout=timeout)
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"json call failed ({type(e).__name__})") from e
        return r.message.content or ""

    async def keep_resident(self) -> None:
        """Refresh keep_alive without generating (an empty chat only loads/keeps the model).
        While Spike runs, the model must never be unloaded for being idle: reloading it next
        to the Turbo voice would leave only part of it on the graphics card (slow replies)."""
        try:
            await asyncio.wait_for(self.client.chat(model=self.model, messages=[], keep_alive=self.keep_alive,
                                                    options=self.options), timeout=30)
        except Exception as e:  # noqa: BLE001
            log.debug("keep-resident ping failed: %s", e)

    async def unload(self) -> None:
        try:
            await asyncio.wait_for(self.client.chat(model=self.model, messages=[{"role": "user", "content": "."}],
                                                    keep_alive=0, options={"num_predict": 1}), timeout=5)
        except Exception:  # noqa: BLE001
            pass


class GeminiLLM:
    """Google Gemini over REST (server-sent events). Text only.

    Two uses:
      * the optional cloud FALLBACK of the Ollama brain ([cloud] enabled = true), and
      * the MAIN model of the desktop app's light brain ([llm] provider = "gemini",
        config/desktop.toml): the owner's own free key, pasted in the Spike app and handed
        to this process in the GEMINI_API_KEY environment variable (never a file, never logged).

    Same request as the phone app's GeminiProvider (lib/away/ai/gemini.dart): the system prompt
    as systemInstruction, assistant turns as "model", the lowest thinking setting the model
    allows. Models are tried in order: a 404 (model gone) or 429 (that model's free quota used
    up) moves on to the next one; a reply that already started is never restarted elsewhere.
    It also offers the small calls the brain makes of its main model (complete_json for the
    crisis classifier and memory extraction; warm_up/unload/keep_resident are no-ops here).
    """
    name = "gemini"
    BASE = "https://generativelanguage.googleapis.com/v1beta"
    URL = BASE + "/models/{model}:streamGenerateContent?alt=sse"
    DEFAULT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.5-flash")

    def __init__(self, api_key: str, model: str | None = None, timeout_s: float = 12,
                 temperature: float = 0.8, max_tokens: int = 110, *, models: list[str] | None = None,
                 total_timeout_s: float = 25, base_url: str | None = None):
        if not api_key:
            raise ValueError("no Gemini key")
        self._key = api_key.strip()
        self.models = list(models) if models else ([model] if model else list(self.DEFAULT_MODELS))
        self.model = self.models[0]
        self.timeout_s = timeout_s
        self.total_timeout_s = total_timeout_s
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = (base_url or self.BASE).rstrip("/")
        self._gone: set[str] = set()            # models that answered 404 this session
        self._no_thinking_cfg: set[str] = set()  # models that refused our thinking setting
        self.last_stats: dict = {}
        self.last_error_kind = ""

    def __repr__(self) -> str:                  # never shows the key
        return f"GeminiLLM(models={self.models})"

    # ------------------------------------------------------------------ request shape (pure, tested)
    @staticmethod
    def build_body(messages: list[dict], temperature: float, max_tokens: int, model: str | None = None,
                   schema: dict | None = None, thinking: bool = True) -> dict:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "model" if m["role"] == "assistant" else "user"
            if contents and contents[-1]["role"] == role:
                contents[-1]["parts"][0]["text"] += "\n" + m["content"]
            else:
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
        gen: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
        if thinking:
            gen["thinkingConfig"] = ({"thinkingLevel": "minimal"} if model and not model.startswith("gemini-2.")
                                     else {"thinkingBudget": 0})
        if schema is not None:
            gen["responseMimeType"] = "application/json"
            gen["responseJsonSchema"] = schema
        body = {"contents": contents, "generationConfig": gen}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    @staticmethod
    def text_of(data) -> str:
        """Reply text of one answer object (thought parts skipped). Raises LLMError(blocked)."""
        if not isinstance(data, dict):
            return ""
        block = (data.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise LLMError(f"prompt blocked: {block}", "blocked")
        out = []
        for c in data.get("candidates", []) or []:
            if not isinstance(c, dict):
                continue
            got = []
            for p in (c.get("content") or {}).get("parts", []) or []:
                if isinstance(p, dict) and isinstance(p.get("text"), str) and not p.get("thought"):
                    got.append(p["text"])
            if not got and c.get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
                raise LLMError(f"reply blocked: {c.get('finishReason')}", "blocked")
            out.extend(got)
        return "".join(out)

    @staticmethod
    def parse_sse_line(line: str) -> str:
        if not line.startswith("data:"):
            return ""
        try:
            data = json.loads(line[5:].strip())
        except ValueError:
            return ""
        return GeminiLLM.text_of(data)

    @staticmethod
    def error_for(status: int, body: str) -> LLMError:
        """An HTTP error as an LLMError of the right kind (the body is Google's, never has our key)."""
        low = (body or "").lower()
        if status == 429 or "resource_exhausted" in low:
            return LLMError(f"HTTP {status}", "rate_limited")
        if status in (401, 403) or (status == 400 and ("api key" in low or "api_key" in low)):
            return LLMError(f"HTTP {status}", "bad_key")
        return LLMError(f"HTTP {status}", "other")

    # ------------------------------------------------------------------ transport
    def _post(self, url: str, body: dict, timeout: float):
        req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "x-goog-api-key": self._key})
        return urllib.request.urlopen(req, timeout=timeout)

    def _order(self) -> list[str]:
        return [m for m in self.models if m not in self._gone]

    async def stream(self, messages: list[dict], max_tokens: int | None = None) -> AsyncIterator[str]:
        last: LLMError | None = None
        for model in self._order():
            got_any = False
            try:
                async for piece in self._stream_model(model, messages, max_tokens or self.max_tokens):
                    got_any = True
                    self.model = model
                    yield piece
                self.last_error_kind = ""
                return
            except LLMError as e:
                self.last_error_kind = e.kind
                if got_any:              # half a reply already spoken: don't restart elsewhere
                    raise
                last = e
                if e.kind == "rate_limited" or str(e).startswith("HTTP 404"):
                    log.info("gemini %s: %s, trying the next model", model, e)
                    continue
                raise
        raise last or LLMError("no Gemini model available")

    async def _stream_model(self, model: str, messages: list[dict], max_tokens: int) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        for _attempt in range(2):
            q: asyncio.Queue = asyncio.Queue()
            body = self.build_body(messages, self.temperature, max_tokens, model=model,
                                   thinking=model not in self._no_thinking_cfg)
            url = f"{self.base_url}/models/{model}:streamGenerateContent?alt=sse"
            stop = threading.Event()

            def worker(url=url, body=body, q=q, stop=stop):
                try:
                    with self._post(url, body, self.timeout_s) as resp:
                        for raw in resp:
                            if stop.is_set():
                                break
                            try:
                                text = self.parse_sse_line(raw.decode("utf-8", "replace").strip())
                            except LLMError as e:
                                loop.call_soon_threadsafe(q.put_nowait, ("error", e))
                                return
                            if text:
                                loop.call_soon_threadsafe(q.put_nowait, ("text", text))
                    loop.call_soon_threadsafe(q.put_nowait, ("done", None))
                except urllib.error.HTTPError as e:
                    try:
                        detail = e.read().decode("utf-8", "replace")
                    except Exception:  # noqa: BLE001
                        detail = ""
                    loop.call_soon_threadsafe(q.put_nowait, ("http", (e.code, detail)))
                except (urllib.error.URLError, OSError, ValueError) as e:
                    loop.call_soon_threadsafe(q.put_nowait, ("error", LLMError(type(e).__name__, "network")))

            threading.Thread(target=worker, name="gemini", daemon=True).start()
            start = time.perf_counter()
            first = True
            retry = False
            try:
                while True:
                    budget = self.timeout_s if first else max(1.0, self.total_timeout_s - (time.perf_counter() - start))
                    try:
                        kind, val = await asyncio.wait_for(q.get(), timeout=budget)
                    except asyncio.TimeoutError as e:
                        raise LLMError("cloud model timed out", "network") from e
                    if kind == "text":
                        first = False
                        yield val
                    elif kind == "done":
                        return
                    elif kind == "http":
                        status, detail = val
                        if status == 404:
                            self._gone.add(model)
                            raise LLMError("HTTP 404", "other")
                        if status == 400 and "thinking" in detail.lower() and model not in self._no_thinking_cfg:
                            self._no_thinking_cfg.add(model)       # no such thinking setting: ask again without
                            retry = True
                            break
                        raise self.error_for(status, detail)
                    else:
                        raise val
            finally:
                stop.set()
            if not retry:
                return

    async def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 120,
                            timeout: float = 8.0) -> str:
        """One short, deterministic, JSON-constrained answer (the crisis classifier, memory extraction)."""
        order = self._order() or list(self.models)
        model = self.model if self.model in order else order[0]
        body = self.build_body([{"role": "system", "content": system}, {"role": "user", "content": user}],
                               0.0, max_tokens, model=model, schema=schema,
                               thinking=model not in self._no_thinking_cfg)
        url = f"{self.base_url}/models/{model}:generateContent"

        def call() -> str:
            try:
                with self._post(url, body, timeout) as resp:
                    return self.text_of(json.loads(resp.read().decode("utf-8", "replace")))
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    detail = ""
                raise self.error_for(e.code, detail) from None
            except (urllib.error.URLError, OSError, ValueError) as e:
                raise LLMError(f"json call failed ({type(e).__name__})", "network") from None

        try:
            return await asyncio.wait_for(asyncio.to_thread(call), timeout=timeout + 1)
        except asyncio.TimeoutError as e:
            raise LLMError("json call timed out", "network") from e

    # ------------------------------------------------------------------ the main-model contract (no-ops)
    async def ensure_model(self) -> str:
        return self.model

    async def warm_up(self, system_prompt: str) -> float:
        return 0.0                               # nothing to load: the model lives at Google

    async def gpu_share(self) -> float | None:
        return None

    async def keep_resident(self) -> None:
        return None

    async def unload(self) -> None:
        return None


class LLMRouter:
    """Local first; the cloud only if enabled (and only when local fails, by default)."""

    def __init__(self, local: OllamaLLM | None, cloud: GeminiLLM | None = None, use_when: str = "local_fails"):
        self.local = local
        self.cloud = cloud
        self.use_when = use_when
        self.last_used = ""

    async def stream(self, messages: list[dict], max_tokens: int | None = None) -> AsyncIterator[str]:
        order = []
        if self.cloud and self.use_when == "always":
            order = [self.cloud, self.local]
        else:
            order = [self.local, self.cloud]
        errors = []
        for llm in [m for m in order if m is not None]:
            got_any = False
            try:
                async for piece in llm.stream(messages, max_tokens=max_tokens):
                    got_any = True
                    self.last_used = llm.name
                    yield piece
                return
            except LLMError as e:
                errors.append(str(e))
                log.warning("%s: %s", llm.name, e)
                if got_any:          # half a reply already spoken: don't restart elsewhere
                    raise
        raise LLMError("; ".join(errors) or "no language model configured")
