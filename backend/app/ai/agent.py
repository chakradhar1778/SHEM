"""
SHEM AI — chat agent

chat_events() runs one user turn and yields UI events as dicts
{"event": <name>, "data": {...}}:

  conversation  {conversationId, title}
  provider      {name}
  text          {delta}
  component     {component}
  tool_start    {id, name, label}
  tool_end      {id, name, ok, summary}
  action        {component}                 action_result from a state-changing tool
  fallback      {from, to, discardPartial}
  reset         {segments}                  replace the in-progress message (after a failed attempt)
  followups     {followups}
  done          {conversationId, message}   authoritative final message
  error         {message}
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy import desc, select

from app.ai.components import StreamSegmenter, segments_to_plain
from app.ai.context import build_snapshot, system_prompt
from app.ai.providers import AllProvidersFailed, ProviderTurn, get_router
from app.ai.suggestions import fallback_followups
from app.ai.tools import REGISTRY, execute_tool_sync, openai_tools
from app.config import get_settings
from app.database import SessionLocal
from app.models.db_models import AIConversation, AIMessage
from app.utils.timestamps import to_iso, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Persistence ────────────────────────────────────────────────────────────────

def message_to_dict(m: AIMessage) -> Dict[str, Any]:
    segments = json.loads(m.segments_json) if m.segments_json else (
        [{"type": "text", "content": m.content}] if m.content else [])
    followups = json.loads(m.followups_json or "[]")
    if m.role == "assistant":                      # repair replies stored before the parser fix
        healed = StreamSegmenter()
        healed.segments = segments
        segments = healed.final_segments()
        if healed.followups:
            followups = healed.followups
    return {"id": m.id, "role": m.role, "content": m.content or "", "segments": segments,
            "followups": followups, "actions": json.loads(m.actions_json or "[]"),
            "provider": m.provider, "createdAt": to_iso(m.created_at)}


def conversation_to_dict(c: AIConversation) -> Dict[str, Any]:
    return {"id": c.id, "title": c.title, "createdAt": to_iso(c.created_at), "updatedAt": to_iso(c.updated_at)}


def _ensure_conversation(conversation_id: Optional[str], first_message: str) -> Dict[str, Any]:
    with SessionLocal() as db:
        conv = db.get(AIConversation, conversation_id) if conversation_id else None
        if conv is None:
            title = " ".join(first_message.split())[:60] or "New chat"
            conv = AIConversation(id=conversation_id or f"conv-{uuid.uuid4().hex[:12]}", title=title,
                                  created_at=utcnow(), updated_at=utcnow())
            db.add(conv)
            db.commit()
        return conversation_to_dict(conv)


def _load_history(conversation_id: str) -> List[Dict[str, Any]]:
    """Previous user/assistant turns as plain text (tool traffic is not replayed)."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(AIMessage).where(AIMessage.conversation_id == conversation_id,
                                    AIMessage.role.in_(("user", "assistant")),
                                    AIMessage.tool_calls_json.is_(None))
            .order_by(desc(AIMessage.id)).limit(settings.ai_history_messages)
        ).all()
    out = []
    for m in reversed(rows):
        if m.role == "assistant" and m.segments_json:
            content = segments_to_plain(json.loads(m.segments_json))
        else:
            content = m.content or ""
        if content.strip():
            out.append({"role": m.role, "content": content})
    return out


def _persist(conversation_id: str, rows: List[AIMessage]) -> List[Dict[str, Any]]:
    with SessionLocal() as db:
        for r in rows:
            r.conversation_id = conversation_id
            db.add(r)
        conv = db.get(AIConversation, conversation_id)
        if conv is not None:
            conv.updated_at = utcnow()
        db.commit()
        return [message_to_dict(r) for r in rows]


def _snapshot(mqtt_client: Any) -> Dict[str, Any]:
    with SessionLocal() as db:
        return build_snapshot(db, bool(mqtt_client and getattr(mqtt_client, "connected", False)))


def _fallback_followups() -> List[str]:
    with SessionLocal() as db:
        return fallback_followups(db)


# ── Agent loop ─────────────────────────────────────────────────────────────────

def _ev(event: str, **data: Any) -> Dict[str, Any]:
    return {"event": event, "data": data}


VOICE_PROMPT = """
VOICE MODE (SHEM AI Live): the user is TALKING to you and hears your text read aloud, while the UI
components you emit appear on their screen.
- Reply in the user's spoken language ({language}); match their script (Hindi in Devanagari, etc.).
- Keep the spoken text short: 1-3 natural sentences, no markdown tables, bullet lists, headings or emoji.
  Say numbers the way a person would ("about two point four units", "eighteen rupees").
- Put details (numbers, breakdowns, charts, lists, toggles) into shem-ui components instead of the text,
  and say something like "I've put the breakdown on your screen".
- Still end with a shem-followups block (shown on screen, not spoken).
"""


async def chat_events(user_text: str, conversation_id: Optional[str] = None,
                      mqtt_client: Any = None, voice_language: Optional[str] = None
                      ) -> AsyncIterator[Dict[str, Any]]:
    user_text = (user_text or "").strip()
    conv = await asyncio.to_thread(_ensure_conversation, conversation_id, user_text)
    cid = conv["id"]
    yield _ev("conversation", conversationId=cid, title=conv["title"])

    router = get_router()
    user_row = AIMessage(role="user", content=user_text, created_at=utcnow())
    if not router.available:
        await asyncio.to_thread(_persist, cid, [user_row])
        yield _ev("error", message="SHEM AI isn't configured: set GEMINI_API_KEY and/or GROQ_API_KEY in "
                                   "backend/.env and restart the backend.")
        return

    history = await asyncio.to_thread(_load_history, cid)
    snapshot = await asyncio.to_thread(_snapshot, mqtt_client)
    system = system_prompt(snapshot)
    if voice_language is not None:
        system += VOICE_PROMPT.format(language=voice_language or "auto-detected")
    messages: List[Dict[str, Any]] = [{"role": "system", "content": system},
                                      *history, {"role": "user", "content": user_text}]
    to_persist: List[AIMessage] = [user_row]
    segmenter = StreamSegmenter()
    actions: List[Dict[str, Any]] = []
    tools = openai_tools()
    provider_name: Optional[str] = None
    raw_text_parts: List[str] = []

    try:
        for round_no in range(settings.ai_max_tool_rounds + 1):
            last_round = round_no == settings.ai_max_tool_rounds
            if segmenter.has_text:
                for e in segmenter.feed("\n\n"):
                    yield e
            segmenter.checkpoint()
            turn: Optional[ProviderTurn] = None
            async for kind, payload in router.stream(messages, None if last_round else tools):
                if kind == "provider":
                    provider_name = payload
                    yield _ev("provider", name=payload)
                elif kind == "text":
                    for e in segmenter.feed(payload):
                        yield e
                elif kind == "fallback":
                    yield _ev("fallback", **{"from": payload["from"], "to": payload["to"],
                                             "discardPartial": payload["discardPartial"]})
                    if payload["discardPartial"]:
                        segmenter.rollback()
                        yield _ev("reset", segments=segmenter.final_segments())
                elif kind == "done":
                    turn = payload
            assert turn is not None
            raw_text_parts.append(turn.text)

            if not turn.tool_calls:
                break

            assistant_msg = {"role": "assistant", "content": turn.text or None,
                             "tool_calls": [c.to_message() for c in turn.tool_calls]}
            messages.append(assistant_msg)
            to_persist.append(AIMessage(role="assistant", content=turn.text or None,
                                        tool_calls_json=json.dumps(assistant_msg["tool_calls"]),
                                        provider=turn.provider, created_at=utcnow()))
            for call in turn.tool_calls:
                spec = REGISTRY.get(call.name)
                yield _ev("tool_start", id=call.id, name=call.name, label=spec.label if spec else call.name)
                outcome = await asyncio.to_thread(execute_tool_sync, call.name, call.arguments, mqtt_client, cid)
                result = outcome["result"]
                yield _ev("tool_end", id=call.id, name=call.name, ok=result["ok"], summary=outcome["summary"])
                if outcome["ui"]:
                    actions.append(outcome["ui"])
                    yield _ev("action", component=outcome["ui"])
                content = json.dumps(result, default=str, ensure_ascii=False)
                if len(content) > settings.ai_tool_result_max_chars:
                    content = content[: settings.ai_tool_result_max_chars] + '…"[truncated — narrow the query]"'
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                to_persist.append(AIMessage(role="tool", content=content, tool_call_id=call.id, name=call.name,
                                            created_at=utcnow()))
    except AllProvidersFailed as exc:
        logger.error("All AI providers failed: %s", exc)
        await asyncio.to_thread(_persist, cid, to_persist)
        yield _ev("error", message="SHEM AI couldn't reach any AI provider right now. Please try again shortly.")
        return

    for e in segmenter.flush():
        yield e
    segments = segmenter.final_segments()
    if not segments:
        segments = [{"type": "text", "content": "Done." if actions else "I couldn't produce an answer — "
                                                                        "please rephrase."}]
    followups = segmenter.followups or await asyncio.to_thread(_fallback_followups)
    if not segmenter.followups:
        yield _ev("followups", followups=followups)

    final = AIMessage(role="assistant", content="\n\n".join(p for p in raw_text_parts if p),
                      segments_json=json.dumps(segments, ensure_ascii=False),
                      followups_json=json.dumps(followups, ensure_ascii=False),
                      actions_json=json.dumps(actions, ensure_ascii=False),
                      provider=provider_name, created_at=utcnow())
    to_persist.append(final)
    saved = await asyncio.to_thread(_persist, cid, to_persist)
    yield _ev("done", conversationId=cid, message=saved[-1])


async def chat_once(user_text: str, conversation_id: Optional[str] = None, mqtt_client: Any = None) -> Dict[str, Any]:
    """Non-streaming: run the turn and return {conversationId, message} or raise RuntimeError."""
    async for e in chat_events(user_text, conversation_id, mqtt_client):
        if e["event"] == "done":
            return e["data"]
        if e["event"] == "error":
            raise RuntimeError(e["data"]["message"])
    raise RuntimeError("No response")
