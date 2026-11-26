"""Model providers behind the AI Professor's LLM Gateway.

Each provider turns (prompt, settings) into text plus token counts. Providers never retry or fall back —
that is the gateway's job — and never decide which model to use — that is the router's job.

Adding our own fine-tuned model later (Phase 7) = one more provider (e.g. an Ollama model name).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from dotenv import load_dotenv

load_dotenv()

# Same models the rest of NeuralHub uses (core/llm.py); overridable per environment.
GEMINI_MODEL = os.getenv("AI_PROFESSOR_GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("AI_PROFESSOR_GROQ_MODEL", "openai/gpt-oss-120b")
OLLAMA_MODEL = os.getenv("AI_PROFESSOR_OLLAMA_MODEL", "phi3")
# Fast hosted open-source models (free tiers). Model ids change over time: override them in .env if needed,
# and GET /api/ai-professor/llm/models?provider=cerebras lists the ids your key can use.
CEREBRAS_MODEL = os.getenv("AI_PROFESSOR_CEREBRAS_MODEL", "gpt-oss-120b")
OPENROUTER_MODEL = os.getenv("AI_PROFESSOR_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
MISTRAL_MODEL = os.getenv("AI_PROFESSOR_MISTRAL_MODEL", "mistral-small-latest")  # open-weight (Apache 2.0)


@dataclass
class Completion:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class CallSettings:
    json_mode: bool = True
    temperature: float = 0.4
    max_tokens: int = 2048
    system: str = ""
    timeout_s: float = 45.0
    reasoning: str = ""  # "" = use AI_PROFESSOR_REASONING (default "low"); "low" | "medium" | "high" | "default"


def reasoning_level(settings: CallSettings) -> str:
    """How hard "thinking" models (gpt-oss on Groq, Gemini 2.5) may think. Low = much faster for JSON jobs."""
    v = (settings.reasoning or os.getenv("AI_PROFESSOR_REASONING", "low")).strip().lower()
    return v if v in ("low", "medium", "high") else "default"


GEMINI_THINKING_BUDGET = {"low": 0, "medium": 1024, "high": 4096}


def fit_max_tokens(text: str, wanted: int, tokens_per_minute: int) -> int:
    """Providers like Groq count prompt + max_tokens against a per-minute limit and refuse a request that is
    larger than the whole limit (HTTP 413). Shrink max_tokens so one request always fits."""
    if tokens_per_minute <= 0:
        return wanted
    est_in = int(len(text) / 3.3) + 50  # rough token estimate (safe side)
    return max(512, min(wanted, tokens_per_minute - est_in - 200))


class Provider(Protocol):
    name: str

    def available(self) -> bool: ...

    def complete(self, prompt: str, settings: CallSettings) -> Completion: ...


class ProviderError(RuntimeError):
    """The provider could not answer (network, quota, empty reply…)."""


# ------------------------------------------------------------------ Gemini

class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str = GEMINI_MODEL):
        self.model = model

    def available(self) -> bool:
        return bool(os.getenv("GOOGLE_API_KEY"))

    def complete(self, prompt: str, settings: CallSettings) -> Completion:
        from google.genai import types

        from core.llm_loader import get_gemini_client  # lazy: raises if the key is missing

        opts = dict(
            temperature=settings.temperature,
            max_output_tokens=settings.max_tokens,
            system_instruction=settings.system or None,
            response_mime_type="application/json" if settings.json_mode else None,
        )
        level = reasoning_level(settings)
        if level != "default" and "2.5" in self.model:  # Gemini 2.5 "thinks" before answering: cap it
            budget = GEMINI_THINKING_BUDGET[level]
            if budget == 0 and "pro" in self.model:
                budget = 128  # 2.5 Pro cannot switch thinking off fully
            opts["thinking_config"] = types.ThinkingConfig(thinking_budget=budget)
        try:  # per-call timeout (older google-genai versions may not support it)
            config = types.GenerateContentConfig(
                **opts,
                http_options=types.HttpOptions(timeout=int(settings.timeout_s * 1000)),
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # no tools here
            )
        except Exception:  # noqa: BLE001
            config = types.GenerateContentConfig(**opts)
        res = get_gemini_client().models.generate_content(model=self.model, contents=prompt, config=config)
        text = (getattr(res, "text", "") or "").strip()
        if not text:
            raise ProviderError("empty reply")
        usage = getattr(res, "usage_metadata", None)
        return Completion(
            text=text,
            model=self.model,
            tokens_in=int(getattr(usage, "prompt_token_count", 0) or 0),
            tokens_out=int(getattr(usage, "candidates_token_count", 0) or 0),
        )


# ------------------------------------------------------------------ Groq

class GroqProvider:
    name = "groq"

    def __init__(self, model: str = GROQ_MODEL):
        self.model = model

    def available(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY"))

    def complete(self, prompt: str, settings: CallSettings) -> Completion:
        from groq import Groq

        messages = ([{"role": "system", "content": settings.system}] if settings.system else []) + [
            {"role": "user", "content": prompt}
        ]
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=settings.temperature,
            max_tokens=fit_max_tokens(prompt + settings.system, settings.max_tokens,
                                      int(os.getenv("AI_PROFESSOR_GROQ_TPM", "8000"))),
            timeout=settings.timeout_s,
        )
        if settings.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        level = reasoning_level(settings)
        if level != "default" and "gpt-oss" in self.model:  # reasoning model: think less, answer faster
            kwargs["reasoning_effort"] = level
            kwargs["include_reasoning"] = False
        out = Groq(api_key=os.environ["GROQ_API_KEY"]).chat.completions.create(**kwargs)
        text = (out.choices[0].message.content or "").strip()
        if not text:
            raise ProviderError("empty reply")
        usage = getattr(out, "usage", None)
        return Completion(
            text=text,
            model=self.model,
            tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
            tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
        )


# ------------------------------------------------------------------ OpenAI-compatible APIs (Cerebras, OpenRouter, ...)

class OpenAICompatProvider:
    """Any /v1/chat/completions API. Used for Cerebras and OpenRouter (both run open-source models)."""

    def __init__(self, name: str, base_url: str, key_env: str, model: str, extra_headers: Optional[dict] = None,
                 min_interval_s: float = 0.0, auto_free: bool = False):
        import threading

        self.name = name
        self.base_url = base_url.rstrip("/")
        self.key_env = key_env
        self.model = model
        self.extra_headers = extra_headers or {}
        self.min_interval_s = min_interval_s   # free tiers that allow ~1 request/second: wait instead of a 429
        self.auto_free = auto_free             # OpenRouter: if the model stops being free, pick another free one
        self._gate = threading.Lock()
        self._last = 0.0

    def _wait_turn(self) -> None:
        if self.min_interval_s <= 0:
            return
        import time

        with self._gate:
            gap = self.min_interval_s - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.monotonic()

    PREFERRED_FREE = ("gpt-oss-120b", "gpt-oss-20b", "llama-3.3-70b", "qwen3", "qwen-2.5-72b", "deepseek",
                      "mistral-small", "gemma-3-27b", "llama")

    def pick_free_model(self) -> Optional[str]:
        free = [m for m in self.list_models() if m.endswith(":free")]
        for pref in self.PREFERRED_FREE:
            for m in free:
                if pref in m and m != self.model:
                    return m
        return next((m for m in free if m != self.model), None)

    def available(self) -> bool:
        return bool(os.getenv(self.key_env))

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {os.environ[self.key_env]}", "Content-Type": "application/json",
                **self.extra_headers}

    def _body(self, prompt: str, settings: CallSettings, json_mode: bool) -> dict:
        messages = ([{"role": "system", "content": settings.system}] if settings.system else []) + [
            {"role": "user", "content": prompt}
        ]
        body = {"model": self.model, "messages": messages, "temperature": settings.temperature,
                "max_tokens": settings.max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        level = reasoning_level(settings)
        if level != "default" and "gpt-oss" in self.model:  # reasoning model: think less, answer faster
            if self.name == "openrouter":
                body["reasoning"] = {"effort": level, "exclude": True}
            else:
                body["reasoning_effort"] = level
        return body

    def complete(self, prompt: str, settings: CallSettings) -> Completion:
        import httpx

        url = f"{self.base_url}/chat/completions"
        json_mode = settings.json_mode
        switched = False
        for _ in range(3):
            self._wait_turn()
            r = httpx.post(url, headers=self._headers(), json=self._body(prompt, settings, json_mode),
                           timeout=settings.timeout_s)
            if r.status_code == 400 and json_mode and "response_format" in r.text:
                json_mode = False  # this model has no JSON mode: the prompt already asks for JSON
                continue
            if r.status_code == 404 and self.auto_free and not switched:
                try:
                    new = self.pick_free_model()
                except Exception:  # noqa: BLE001
                    new = None
                if new:
                    import logging

                    logging.getLogger("neuralhub.ai_professor.llm").warning(
                        "%s: model %s is gone, switching to free model %s", self.name, self.model, new)
                    self.model, switched = new, True
                    continue
            break
        if r.status_code >= 400:
            msg = r.text[:400]
            if r.status_code == 429:
                retry = r.headers.get("retry-after")
                msg = f"429 rate limit {msg}" + (f" retry in {retry}s" if retry and retry.isdigit() else "")
            elif r.status_code == 404 or ("model" in msg.lower() and "not found" in msg.lower()):
                msg = f"{r.status_code} model '{self.model}' not available on {self.name}: {msg}"
            raise ProviderError(f"{self.name} {r.status_code}: {msg}")
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        text = ((choice.get("message") or {}).get("content") or "").strip()
        if not text:
            raise ProviderError("empty reply")
        usage = data.get("usage") or {}
        return Completion(text=text, model=data.get("model") or self.model,
                          tokens_in=int(usage.get("prompt_tokens") or 0),
                          tokens_out=int(usage.get("completion_tokens") or 0))

    def list_models(self) -> list[str]:
        import httpx

        r = httpx.get(f"{self.base_url}/models", headers=self._headers(), timeout=20)
        r.raise_for_status()
        return sorted(m.get("id", "") for m in r.json().get("data", []))


def CerebrasProvider(model: str = CEREBRAS_MODEL) -> OpenAICompatProvider:
    return OpenAICompatProvider("cerebras", os.getenv("CEREBRAS_BASE_URL", "https://api.cerebras.ai/v1"),
                                "CEREBRAS_API_KEY", model)


def OpenRouterProvider(model: str = OPENROUTER_MODEL) -> OpenAICompatProvider:
    return OpenAICompatProvider("openrouter", os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
                                "OPENROUTER_API_KEY", model,
                                extra_headers={"HTTP-Referer": "http://localhost:3000", "X-Title": "NeuralHub"},
                                auto_free=True)


def MistralProvider(model: str = MISTRAL_MODEL) -> OpenAICompatProvider:
    return OpenAICompatProvider("mistral", os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1"),
                                "MISTRAL_API_KEY", model,
                                min_interval_s=float(os.getenv("AI_PROFESSOR_MISTRAL_MIN_INTERVAL", "1.2")))


# ------------------------------------------------------------------ Ollama (local; later also our own QLoRA model)

class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str = OLLAMA_MODEL, name: str = "ollama"):
        self.model = model
        self.name = name

    def available(self) -> bool:
        return os.getenv("AI_PROFESSOR_OLLAMA", "true").strip().lower() not in {"0", "false", "no", "off"}

    def complete(self, prompt: str, settings: CallSettings) -> Completion:
        import ollama

        messages = ([{"role": "system", "content": settings.system}] if settings.system else []) + [
            {"role": "user", "content": prompt}
        ]
        client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"), timeout=settings.timeout_s)
        out = client.chat(
            model=self.model,
            messages=messages,
            format="json" if settings.json_mode else "",
            options={"temperature": settings.temperature, "num_predict": settings.max_tokens},
        )
        text = (out.get("message", {}).get("content", "") or "").strip()
        if not text:
            raise ProviderError("empty reply")
        return Completion(
            text=text,
            model=self.model,
            tokens_in=int(out.get("prompt_eval_count", 0) or 0),
            tokens_out=int(out.get("eval_count", 0) or 0),
        )


# ------------------------------------------------------------------ Fake (tests and offline demos)

@dataclass
class FakeProvider:
    """Answers from a list of replies (or a function). A reply that is an Exception is raised."""

    name: str = "fake"
    replies: list = field(default_factory=list)
    fn: Optional[Callable[[str, CallSettings], str]] = None
    is_available: bool = True
    calls: list = field(default_factory=list)
    model: str = "fake-model"

    def available(self) -> bool:
        return self.is_available

    def complete(self, prompt: str, settings: CallSettings) -> Completion:
        self.calls.append(prompt)
        reply = self.fn(prompt, settings) if self.fn else (self.replies.pop(0) if self.replies else "")
        if isinstance(reply, Exception):
            raise reply
        if not reply:
            raise ProviderError("empty reply")
        return Completion(text=reply, model=self.model, tokens_in=len(prompt) // 4, tokens_out=len(reply) // 4)


def default_providers() -> dict[str, Provider]:
    return {p.name: p for p in (GeminiProvider(), GroqProvider(), CerebrasProvider(), OpenRouterProvider(),
                                 MistralProvider(), OllamaProvider())}
