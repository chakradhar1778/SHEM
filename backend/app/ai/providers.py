"""
SHEM AI — LLM providers (OpenAI SDK against OpenAI-compatible endpoints)

Gemini: https://generativelanguage.googleapis.com/v1beta/openai/
Groq:   https://api.groq.com/openai/v1

LLMRouter.stream() tries the primary provider, and on any error moves on to
the fallback. Events it yields:

  ("provider", name)                       a provider attempt started
  ("text", delta)                          streamed assistant text
  ("fallback", {from, to, error, discardPartial})
  ("done", ProviderTurn)                   the final assembled turn

If every provider fails, AllProvidersFailed is raised.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, Tuple

from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

Event = Tuple[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str
    extra: Dict[str, Any] = field(default_factory=dict)   # provider-specific fields to echo back

    def to_message(self) -> Dict[str, Any]:
        msg: Dict[str, Any] = {"id": self.id, "type": "function",
                               "function": {"name": self.name, "arguments": self.arguments or "{}"}}
        msg.update(self.extra)   # e.g. Gemini thought signatures (extra_content)
        return msg


@dataclass
class ProviderTurn:
    text: str
    tool_calls: List[ToolCall]
    provider: str


class AllProvidersFailed(RuntimeError):
    def __init__(self, errors: List[str]):
        super().__init__("; ".join(errors) or "No AI provider is configured.")
        self.errors = errors


class LLMProvider(Protocol):
    name: str
    model: str

    def stream(self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]],
               temperature: float) -> AsyncIterator[Event]: ...


_STANDARD_TOOL_CALL_KEYS = ("id", "type", "function")


def _strip_foreign_fields(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop provider-specific tool-call fields (e.g. Gemini thought signatures) and `name`,
    which stricter OpenAI-compatible APIs such as Groq reject with a 400."""
    out = []
    for m in messages:
        m = {k: v for k, v in m.items() if k != "name"}
        if m.get("tool_calls"):
            m["tool_calls"] = [{k: tc[k] for k in _STANDARD_TOOL_CALL_KEYS if k in tc} for tc in m["tool_calls"]]
        out.append(m)
    return out


class OpenAICompatProvider:
    def __init__(self, name: str, api_key: str, base_url: str, model: str, timeout: float):
        self.name = name
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=1)

    async def stream(self, messages, tools, temperature) -> AsyncIterator[Event]:
        if self.name != "gemini":
            messages = _strip_foreign_fields(messages)
        kwargs: Dict[str, Any] = {"model": self.model, "messages": messages,
                                  "temperature": temperature, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        response = await self.client.chat.completions.create(**kwargs)

        text: List[str] = []
        slots: Dict[Any, Dict[str, Any]] = {}
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                text.append(delta.content)
                yield ("text", delta.content)
            for tc in delta.tool_calls or []:
                key = tc.index if tc.index is not None else (tc.id or len(slots))
                slot = slots.setdefault(key, {"id": None, "name": "", "arguments": "", "extra": {}})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function is not None:
                    if tc.function.name and not slot["name"]:
                        slot["name"] = tc.function.name
                    if tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
                extra = getattr(tc, "model_extra", None) or {}
                slot["extra"].update({k: v for k, v in extra.items() if v is not None})

        calls = [
            ToolCall(id=s["id"] or f"call_{uuid.uuid4().hex[:12]}", name=s["name"],
                     arguments=s["arguments"] or "{}", extra=s["extra"])
            for s in slots.values() if s["name"]
        ]
        yield ("done", ProviderTurn(text="".join(text), tool_calls=calls, provider=self.name))


class KeyState:
    """In-memory per-key health tracking with exponential back-off."""
    def __init__(self, key: str, provider: LLMProvider, index: int):
        self.key = key
        self.provider = provider
        self.index = index
        self.backoff_until: float = 0.0   # monotonic seconds; 0 = healthy
        self.fail_count: int = 0
        self.auth_failed: bool = False    # 401/403: skip for process lifetime
        self.last_error: Optional[str] = None

    @property
    def healthy(self) -> bool:
        return not self.auth_failed and time.monotonic() >= self.backoff_until

    def record_rate_limit(self, err: str = "") -> float:
        self.fail_count += 1
        delay = float(min(60 * (2 ** (self.fail_count - 1)), 3600))
        self.backoff_until = time.monotonic() + delay
        self.last_error = err[:200] or "rate_limited"
        return delay

    def record_transient_failure(self, err: str = "") -> float:
        self.fail_count += 1
        delay = float(min(15 * (2 ** (self.fail_count - 1)), 300))
        self.backoff_until = time.monotonic() + delay
        self.last_error = err[:200] or "transient_error"
        return delay

    def record_auth_failure(self, err: str = "") -> None:
        self.auth_failed = True
        self.last_error = err[:200] or "auth_failed"

    def record_success(self) -> None:
        self.fail_count = 0
        self.backoff_until = 0.0
        self.last_error = None


def _classify_key_error(exc: Exception) -> str:
    """Classify an API exception into 'auth' | 'rate_limit' | 'bad_request' | 'transient'."""
    status_code = getattr(exc, "status_code", None)
    text = f"{type(exc).__name__} {exc}".lower()
    if status_code in (401, 403) or any(tok in text for tok in ("401", "403", "unauthorized", "invalid api key", "api_key_invalid", "permission_denied", "forbidden")):
        return "auth"
    if status_code == 429 or any(tok in text for tok in ("429", "quota", "rate limit", "rate_limit", "resource_exhausted", "too many requests")):
        return "rate_limit"
    if status_code == 400 or "400" in text and "bad request" in text:
        return "bad_request"
    return "transient"


class MultiKeyProvider:
    """
    One logical provider (e.g. 'gemini' or 'groq') backed by N API keys.

    - Round-robins across all healthy keys for balanced usage.
    - On key failure (429/quota, 401/403 auth, timeout/5xx) before partial text is
      streamed, marks the key's health state and immediately retries with the next
      healthy key of the same provider.
    - Raises only when every key for this provider has failed or is in back-off
      (allowing LLMRouter to fall back to the secondary provider).
    """
    def __init__(
        self,
        name: str,
        keys: List[str],
        base_url: str,
        model: str,
        timeout: float,
        provider_factory=None,
    ):
        self.name = name
        self.model = model
        self._base_url = base_url
        self._timeout = timeout
        factory = provider_factory or (
            lambda k: OpenAICompatProvider(name, k, base_url, model, timeout)
        )
        self._states: List[KeyState] = [KeyState(k, factory(k), i) for i, k in enumerate(keys)]
        self._pointer: int = 0
        self._lock = asyncio.Lock()

    @property
    def key_count(self) -> int:
        return len(self._states)

    @property
    def healthy_key_count(self) -> int:
        return sum(1 for st in self._states if st.healthy)

    async def _ordered_candidates(self) -> List[KeyState]:
        """Return healthy keys starting at the current round-robin pointer and advance it."""
        async with self._lock:
            n = len(self._states)
            if n == 0:
                return []
            start = self._pointer % n
            ordered = [self._states[(start + i) % n] for i in range(n)]
            healthy = [st for st in ordered if st.healthy]
            if healthy:
                # Advance pointer past the first key we're about to try.
                self._pointer = (healthy[0].index + 1) % n
            return healthy

    async def stream(self, messages, tools, temperature) -> AsyncIterator[Event]:
        candidates = await self._ordered_candidates()
        if not candidates:
            raise RuntimeError(f"All {self.name} API keys ({self.key_count}) are currently in back-off or disabled.")

        last_exc: Optional[Exception] = None
        for idx, state in enumerate(candidates):
            emitted_text = False
            try:
                async for event in state.provider.stream(messages, tools, temperature):
                    if event[0] == "text":
                        emitted_text = True
                    yield event
                state.record_success()
                return
            except Exception as exc:
                last_exc = exc
                kind = _classify_key_error(exc)
                if kind == "auth":
                    state.record_auth_failure(str(exc))
                    logger.warning("AI key #%d (%s) auth failure — disabled for this session.", state.index + 1, self.name)
                elif kind == "rate_limit":
                    delay = state.record_rate_limit(str(exc))
                    logger.warning("AI key #%d (%s) rate-limited — back-off %.0fs.", state.index + 1, self.name, delay)
                elif kind == "bad_request":
                    # Request itself is rejected (e.g., unsupported feature/model) — retrying another key won't help.
                    raise
                else:
                    delay = state.record_transient_failure(str(exc))
                    logger.warning("AI key #%d (%s) transient error (%s) — back-off %.0fs.",
                                   state.index + 1, self.name, type(exc).__name__, delay)

                # If partial text was already yielded to the caller, let LLMRouter handle fallback cleanly.
                if emitted_text or idx + 1 >= len(candidates):
                    raise
                logger.info("Rotating %s to next API key (#%d of %d).", self.name, candidates[idx + 1].index + 1, self.key_count)

        assert last_exc is not None
        raise last_exc


class LLMRouter:
    def __init__(self, providers: List[LLMProvider]):
        self.providers = providers

    @property
    def available(self) -> bool:
        return bool(self.providers)

    def get_provider(self, name: str) -> Optional[LLMProvider]:
        target = name.strip().lower()
        for p in self.providers:
            if p.name.lower() == target:
                return p
        return None

    async def stream(
        self,
        messages,
        tools=None,
        temperature: Optional[float] = None,
        provider_name: Optional[str] = None,
    ) -> AsyncIterator[Event]:
        temp = get_settings().ai_temperature if temperature is None else temperature
        pool = [p for p in self.providers if p.name == provider_name] if provider_name else self.providers
        if not pool:
            raise AllProvidersFailed([f"Provider '{provider_name}' is not configured." if provider_name else "No AI provider is configured."])
        errors: List[str] = []
        for i, provider in enumerate(pool):
            emitted_text = False
            yield ("provider", provider.name)
            try:
                async for kind, payload in provider.stream(messages, tools, temp):
                    if kind == "text":
                        emitted_text = True
                    yield (kind, payload)
                return
            except Exception as exc:  # network, auth, quota, bad request, model errors …
                err = f"{provider.name}: {type(exc).__name__}: {str(exc)[:300]}"
                logger.warning("AI provider failed — %s", err)
                errors.append(err)
                if i + 1 < len(pool):
                    yield ("fallback", {"from": provider.name, "to": pool[i + 1].name,
                                        "error": err, "discardPartial": emitted_text})
        raise AllProvidersFailed(errors)

    async def complete(
        self,
        messages,
        temperature: Optional[float] = None,
        provider_name: Optional[str] = None,
    ) -> ProviderTurn:
        """Non-streaming convenience (no tools): returns the final turn."""
        turn: Optional[ProviderTurn] = None
        async for kind, payload in self.stream(messages, None, temperature, provider_name=provider_name):
            if kind == "done":
                turn = payload
        assert turn is not None
        return turn


def provider_specs() -> List[Dict[str, Any]]:
    s = get_settings()
    g_keys = s.gemini_keys_list
    q_keys = s.groq_keys_list
    specs: Dict[str, Dict[str, Any]] = {
        "gemini": {
            "name": "gemini",
            "api_key": g_keys[0] if g_keys else "",
            "api_keys": g_keys,
            "base_url": s.gemini_base_url,
            "model": s.gemini_model,
        },
        "groq": {
            "name": "groq",
            "api_key": q_keys[0] if q_keys else "",
            "api_keys": q_keys,
            "base_url": s.groq_base_url,
            "model": s.groq_model,
        },
    }
    order = [s.ai_primary_provider] + [n for n in specs if n != s.ai_primary_provider]
    return [specs[n] for n in order]


def _build_router() -> LLMRouter:
    s = get_settings()
    providers: List[LLMProvider] = []
    if s.ai_enabled:
        for spec in provider_specs():
            keys: List[str] = spec["api_keys"]
            if keys:
                providers.append(MultiKeyProvider(spec["name"], keys, spec["base_url"],
                                                  spec["model"], s.ai_request_timeout_seconds))
    return LLMRouter(providers)


_router: Optional[LLMRouter] = None


def get_router() -> LLMRouter:
    global _router
    if _router is None:
        _router = _build_router()
    return _router


def set_router(router: Optional[LLMRouter]) -> None:
    """Override (tests) or reset (None → rebuilt from settings on next use)."""
    global _router
    _router = router
