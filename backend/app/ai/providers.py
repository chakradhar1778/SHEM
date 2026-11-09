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

import logging
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


class LLMRouter:
    def __init__(self, providers: List[LLMProvider]):
        self.providers = providers

    @property
    def available(self) -> bool:
        return bool(self.providers)

    async def stream(self, messages, tools=None, temperature: Optional[float] = None) -> AsyncIterator[Event]:
        temp = get_settings().ai_temperature if temperature is None else temperature
        errors: List[str] = []
        for i, provider in enumerate(self.providers):
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
                if i + 1 < len(self.providers):
                    yield ("fallback", {"from": provider.name, "to": self.providers[i + 1].name,
                                        "error": err, "discardPartial": emitted_text})
        raise AllProvidersFailed(errors)

    async def complete(self, messages, temperature: Optional[float] = None) -> ProviderTurn:
        """Non-streaming convenience (no tools): returns the final turn."""
        turn: Optional[ProviderTurn] = None
        async for kind, payload in self.stream(messages, None, temperature):
            if kind == "done":
                turn = payload
        assert turn is not None
        return turn


def provider_specs() -> List[Dict[str, str]]:
    s = get_settings()
    specs = {
        "gemini": {"name": "gemini", "api_key": s.gemini_api_key.strip(), "base_url": s.gemini_base_url,
                   "model": s.gemini_model},
        "groq": {"name": "groq", "api_key": s.groq_api_key.strip(), "base_url": s.groq_base_url,
                 "model": s.groq_model},
    }
    order = [s.ai_primary_provider] + [n for n in specs if n != s.ai_primary_provider]
    return [specs[n] for n in order]


def _build_router() -> LLMRouter:
    s = get_settings()
    providers: List[LLMProvider] = []
    if s.ai_enabled:
        for spec in provider_specs():
            if spec["api_key"]:
                providers.append(OpenAICompatProvider(spec["name"], spec["api_key"], spec["base_url"],
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
