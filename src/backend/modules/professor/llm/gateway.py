"""LLM Gateway: the ONE door every AI Professor model call goes through.

    from modules.professor.llm.gateway import gateway
    res = gateway.generate_json("teach", prompt, TutorTurn, student_key=student_id, prompt_version="teach@1.0")
    res.data           # validated TutorTurn
    res.provider       # "gemini" / "groq" / "ollama" / later our own model
    res.attempts       # every try, with error and latency (for logs and debugging)

What it does on every call:
1. asks the Model Router for the provider order (fallback + canary for our own model later),
2. skips providers that are not configured or are "cooling down" after repeated failures (circuit breaker),
3. calls the provider in JSON mode, extracts and validates the JSON against a Pydantic schema,
4. on invalid JSON: retries the same provider ONCE with a stricter instruction, then moves to the next provider,
5. reports every attempt to the recorder (Step 4 saves them in the llm_calls table),
6. raises GatewayError with all attempts if every provider failed.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Generic, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from modules.professor.llm.providers import CallSettings, Provider, default_providers
from modules.professor.llm.router import ModelRouter

log = logging.getLogger("neuralhub.ai_professor.llm")

T = TypeVar("T", bound=BaseModel)

STRICT_RETRY = (
    "\n\nIMPORTANT: Your previous reply was not valid. Reply with ONLY one valid JSON object that matches the "
    "schema below. No markdown fences, no commentary.\nSchema:\n{schema}"
)


class GatewayError(RuntimeError):
    """Every provider failed. `attempts` explains why."""

    def __init__(self, message: str, attempts: list["Attempt"]):
        super().__init__(message)
        self.attempts = attempts


@dataclass
class Attempt:
    provider: str
    model: str = ""
    ok: bool = False
    error: str = ""            # "" when ok; else e.g. "invalid_json", "schema", "timeout", "provider_error"
    detail: str = ""
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    retry: bool = False        # True for the stricter second try on the same provider


@dataclass
class CallRecord:
    """Everything about one gateway call — the format Step 4 stores (and Phase 7 trains from)."""

    task: str
    prompt_version: str
    student_key: Optional[str]
    prompt: str
    output: str                # raw text of the successful reply ("" if all failed)
    provider: str              # provider that answered ("" if all failed)
    model: str
    ok: bool
    latency_ms: int            # total, including failed tries
    tokens_in: int
    tokens_out: int
    canary: bool
    attempts: list[Attempt] = field(default_factory=list)
    session_id: Optional[str] = None
    first_choice: str = ""     # provider the router put first; != provider means a fallback happened


@dataclass
class GatewayResult(Generic[T]):
    data: T
    text: str
    provider: str
    model: str
    latency_ms: int
    attempts: list[Attempt]


Recorder = Callable[[CallRecord], None]


# ------------------------------------------------------------------ JSON helpers

def extract_json(text: str):
    """First JSON object in a reply (handles ```json fences and text around it)."""
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        return json.loads(cleaned[start : end + 1])
    raise json.JSONDecodeError("no JSON object found", cleaned, 0)


def schema_hint(schema: Type[BaseModel]) -> str:
    return json.dumps(schema.model_json_schema(), ensure_ascii=False)[:3000]


# ------------------------------------------------------------------ circuit breaker

class CircuitBreaker:
    """After `threshold` failures inside `window_s`, skip that provider for `cooldown_s` seconds."""

    def __init__(self, threshold: int = 3, window_s: float = 60, cooldown_s: float = 60, clock=time.monotonic):
        self.threshold, self.window_s, self.cooldown_s, self.clock = threshold, window_s, cooldown_s, clock
        self._fails: dict[str, list[float]] = {}
        self._open_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, name: str) -> bool:
        with self._lock:
            return self.clock() >= self._open_until.get(name, 0)

    def failure(self, name: str) -> None:
        with self._lock:
            now = self.clock()
            fails = [t for t in self._fails.get(name, []) if now - t < self.window_s] + [now]
            self._fails[name] = fails
            if len(fails) >= self.threshold:
                self._open_until[name] = now + self.cooldown_s
                self._fails[name] = []
                log.warning("LLM provider %s paused for %ss after %s failures", name, self.cooldown_s, self.threshold)

    def pause(self, name: str, seconds: float) -> None:
        """Skip this provider right away for `seconds` (used when it says its quota is used up)."""
        with self._lock:
            self._open_until[name] = max(self._open_until.get(name, 0), self.clock() + seconds)
            self._fails[name] = []
        log.warning("LLM provider %s paused for %ss (quota / rate limit)", name, int(seconds))

    def paused_for(self, name: str) -> int:
        with self._lock:
            return max(0, int(self._open_until.get(name, 0) - self.clock()))

    def success(self, name: str) -> None:
        with self._lock:
            self._fails.pop(name, None)
            self._open_until.pop(name, None)


# ------------------------------------------------------------------ quota / rate limits

DAILY_QUOTA_PAUSE_S = 30 * 60  # a per-day quota will not come back in seconds: try again in 30 minutes
RATE_LIMIT_PAUSE_S = 60


def quota_pause_seconds(message: str) -> float:
    """0 if the error is not a quota / rate-limit error, otherwise how long to stop using that provider."""
    m = (message or "").lower()
    if not any(k in m for k in ("429", "resource_exhausted", "rate limit", "rate_limit", "quota", "too many requests")):
        return 0
    mm = re.search(r"(?:retry|try again) in (\d+)m([\d.]+)s", m)  # Groq: "Please try again in 1m30.5s" (exact, also for TPD)
    if mm:
        return min(int(mm.group(1)) * 60 + float(mm.group(2)) + 1, DAILY_QUOTA_PAUSE_S)
    if "perday" in m.replace(" ", "").replace("_", "").replace("-", "") or "per day" in m or "daily" in m:
        return DAILY_QUOTA_PAUSE_S
    if re.search(r"(?:retry|try again) in [\d.]+\s*ms", m):  # "try again in 450ms"
        return 2
    # Gemini "retry in 7s" / "retryDelay: '7s'", Groq "Please try again in 7.5s"
    hint = re.search(r"(?:retry|try again) in ([\d.]+)\s*s", m) or re.search(r"retrydelay'?:\s*'?(\d+)s", m)
    return min(max(float(hint.group(1)) + 1, 2), 10 * 60) if hint else RATE_LIMIT_PAUSE_S


# ------------------------------------------------------------------ gateway

def _log_recorder(rec: CallRecord) -> None:
    log.info(
        "llm task=%s ok=%s provider=%s latency=%sms tokens=%s/%s tries=%s",
        rec.task, rec.ok, rec.provider or "-", rec.latency_ms, rec.tokens_in, rec.tokens_out, len(rec.attempts),
    )


class LLMGateway:
    def __init__(
        self,
        providers: Optional[dict[str, Provider]] = None,
        router: Optional[ModelRouter] = None,
        breaker: Optional[CircuitBreaker] = None,
        recorder: Optional[Recorder] = None,
    ):
        self.providers = providers if providers is not None else default_providers()
        self.router = router or ModelRouter()
        self.breaker = breaker or CircuitBreaker()
        self.recorder: Recorder = recorder or _log_recorder

    # -------------------------------------------------------------- public

    def generate_json(
        self,
        task: str,
        prompt: str,
        schema: Type[T],
        *,
        student_key: Optional[str] = None,
        session_id: Optional[str] = None,
        prompt_version: str = "",
        system: str = "",
        temperature: float = 0.4,
        max_tokens: int = 2048,
        timeout_s: float = 45.0,
        skip: tuple[str, ...] = (),
    ) -> GatewayResult[T]:
        """`skip`: providers not to use for this call (e.g. a slow local model for big background jobs).
        Ignored when it would leave no usable provider."""
        settings = CallSettings(json_mode=True, temperature=temperature, max_tokens=max_tokens, system=system, timeout_s=timeout_s)
        return self._run(task, prompt, settings, schema, student_key, prompt_version, session_id, skip)

    def generate_text(
        self,
        task: str,
        prompt: str,
        *,
        student_key: Optional[str] = None,
        session_id: Optional[str] = None,
        prompt_version: str = "",
        system: str = "",
        temperature: float = 0.4,
        max_tokens: int = 2048,
        timeout_s: float = 45.0,
    ) -> GatewayResult[str]:
        settings = CallSettings(json_mode=False, temperature=temperature, max_tokens=max_tokens, system=system, timeout_s=timeout_s)
        return self._run(task, prompt, settings, None, student_key, prompt_version, session_id)

    # -------------------------------------------------------------- internals

    def _run(self, task, prompt, settings, schema, student_key, prompt_version, session_id=None, skip=()):
        started = time.perf_counter()
        attempts: list[Attempt] = []
        order = self.router.order(task, student_key)
        if skip:
            kept = [n for n in order if n not in skip]
            if any(self.providers.get(n) is not None and self.providers[n].available() for n in kept):
                order = kept
        meta = {"session_id": session_id, "first_choice": order[0] if order else ""}

        for name in order:
            provider = self.providers.get(name)
            if provider is None:
                attempts.append(Attempt(provider=name, error="unknown_provider"))
                continue
            if not provider.available():
                attempts.append(Attempt(provider=name, error="not_configured"))
                continue
            if not self.breaker.allow(name):
                attempts.append(Attempt(provider=name, error="cooling_down"))
                continue

            current_prompt = prompt
            for retry in (False, True):
                if retry and schema is None:
                    break
                result = self._try(provider, current_prompt, settings, schema, retry)
                attempts.append(result[0])
                if result[0].ok:
                    self.breaker.success(name)
                    return self._finish(task, prompt_version, student_key, prompt, started, attempts, result[1], result[2], provider, meta)
                if result[0].error not in ("invalid_json", "schema"):
                    break  # provider itself failed: no point retrying it, go to the next one
                current_prompt = prompt + STRICT_RETRY.format(schema=schema_hint(schema))
            self.breaker.failure(name)

        self._record(task, prompt_version, student_key, prompt, started, attempts, "", None, ok=False, meta=meta)
        summary = "; ".join(f"{a.provider}:{a.error}" for a in attempts) or "no providers"
        raise GatewayError(f"All AI models failed ({summary})", attempts)

    def paused_for(self, names) -> int:
        """Seconds until the first of these providers may be used again (0 = one is usable now)."""
        waits = [self.breaker.paused_for(n) for n in names
                 if self.providers.get(n) is not None and self.providers[n].available()]
        return min(waits) if waits else 0

    def _try(self, provider, prompt, settings, schema, retry):
        t0 = time.perf_counter()
        att = Attempt(provider=provider.name, retry=retry)
        try:
            comp = provider.complete(prompt, settings)
        except Exception as e:  # noqa: BLE001 - any provider failure moves on
            att.latency_ms = int((time.perf_counter() - t0) * 1000)
            pause = quota_pause_seconds(str(e))
            if pause:
                att.error = "quota"
                self.breaker.pause(provider.name, pause)
            else:
                att.error = "timeout" if "timeout" in str(e).lower() or "timed out" in str(e).lower() else "provider_error"
            att.detail = str(e)[:300]
            return att, None, ""
        att.latency_ms = int((time.perf_counter() - t0) * 1000)
        att.model, att.tokens_in, att.tokens_out = comp.model, comp.tokens_in, comp.tokens_out
        if schema is None:
            att.ok = True
            return att, comp.text, comp.text
        try:
            data = schema.model_validate(extract_json(comp.text))
        except json.JSONDecodeError as e:
            att.error, att.detail = "invalid_json", str(e)[:300]
            return att, None, comp.text
        except ValidationError as e:
            att.error, att.detail = "schema", str(e.errors()[:3])[:300]
            return att, None, comp.text
        att.ok = True
        return att, data, comp.text

    def _finish(self, task, prompt_version, student_key, prompt, started, attempts, data, text, provider, meta):
        rec = self._record(task, prompt_version, student_key, prompt, started, attempts, text, provider, ok=True, meta=meta)
        return GatewayResult(
            data=data, text=text, provider=provider.name, model=rec.model, latency_ms=rec.latency_ms, attempts=attempts
        )

    def _record(self, task, prompt_version, student_key, prompt, started, attempts, text, provider, *, ok, meta=None):
        good = next((a for a in reversed(attempts) if a.ok), None)
        rec = CallRecord(
            task=task,
            prompt_version=prompt_version,
            student_key=student_key,
            prompt=prompt,
            output=text if ok else "",
            provider=provider.name if (ok and provider) else "",
            model=good.model if good else "",
            ok=ok,
            latency_ms=int((time.perf_counter() - started) * 1000),
            tokens_in=sum(a.tokens_in for a in attempts),
            tokens_out=sum(a.tokens_out for a in attempts),
            canary=self.router.in_canary(student_key),
            attempts=attempts,
            **(meta or {}),
        )
        try:
            self.recorder(rec)
        except Exception as e:  # noqa: BLE001 - logging must never break teaching
            log.error("LLM recorder failed: %s", e)
        return rec


def _default_recorder() -> Recorder:
    from modules.professor.llm.recorder import default_recorder  # lazy: avoids a DB import cycle

    return default_recorder


# One shared gateway for the app (tests build their own with fake providers).
gateway = LLMGateway(recorder=_default_recorder())
