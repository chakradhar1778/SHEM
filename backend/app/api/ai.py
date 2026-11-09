"""
SHEM Backend — SHEM AI endpoints

GET    /api/ai/status
GET    /api/ai/suggestions
POST   /api/ai/chat                  {message, conversationId?} → {conversationId, message}
POST   /api/ai/chat/stream           same body → text/event-stream (see app/ai/agent.py for events)
GET    /api/ai/conversations
GET    /api/ai/conversations/{id}
DELETE /api/ai/conversations/{id}
GET    /api/ai/conflicts?includeDismissed=false
POST   /api/ai/conflicts/{id}/dismiss
GET    /api/ai/daily-insights?limit=7
GET    /api/ai/daily-insights/latest
POST   /api/ai/daily-insights/generate   {date?: YYYY-MM-DD}  (default: yesterday)
GET    /api/ai/actions?limit=50
"""

from __future__ import annotations

import json
import logging
from datetime import date as Date, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.ai import agent
from app.ai.conflicts import detect_conflicts, dismiss_conflict
from app.ai.daily import generate_daily_insight, insight_to_dict
from app.ai.providers import get_router, provider_specs
from app.ai.suggestions import starter_suggestions
from app.config import get_settings
from app.database import get_db
from app.models.db_models import AIActionLog, AIConversation, AIDailyInsight, AIMessage
from app.models.schemas import ApiModel
from app.utils.rate_limit import limiter
from app.utils.timestamps import to_iso, to_local, utcnow

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["SHEM AI"])
settings = get_settings()


class ChatRequest(ApiModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = Field(None, max_length=64)


class GenerateInsightRequest(ApiModel):
    date: Optional[Date] = None


def _mqtt(request: Request):
    return getattr(request.app.state, "mqtt_client", None)


def _mqtt_connected(request: Request) -> bool:
    c = _mqtt(request)
    return bool(c and getattr(c, "connected", False))


@router.get("/status")
def ai_status() -> Dict[str, Any]:
    specs = provider_specs()
    return {"enabled": settings.ai_enabled, "configured": get_router().available,
            "primaryProvider": settings.ai_primary_provider,
            "providers": [{"name": s["name"], "model": s["model"], "configured": bool(s["api_key"])} for s in specs]}


@router.get("/suggestions")
def suggestions(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    return {"suggestions": starter_suggestions(db, _mqtt_connected(request))}


@router.post("/chat")
@limiter.limit(settings.rate_limit_ai_chat)
async def chat(request: Request, body: ChatRequest) -> Dict[str, Any]:
    try:
        return await agent.chat_once(body.message, body.conversation_id, _mqtt(request))
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))


def _sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
@limiter.limit(settings.rate_limit_ai_chat)
async def chat_stream(request: Request, body: ChatRequest) -> StreamingResponse:
    mqtt = _mqtt(request)

    async def gen():
        try:
            async for e in agent.chat_events(body.message, body.conversation_id, mqtt):
                yield _sse(e["event"], e["data"])
        except Exception:
            logger.exception("AI chat stream failed")
            yield _sse("error", {"message": "Something went wrong in SHEM AI."})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations")
def list_conversations(limit: int = Query(30, ge=1, le=200), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.scalars(select(AIConversation).order_by(desc(AIConversation.updated_at)).limit(limit)).all()
    return [agent.conversation_to_dict(c) for c in rows]


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    conv = db.get(AIConversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    msgs = db.scalars(select(AIMessage).where(
        AIMessage.conversation_id == conversation_id, AIMessage.role.in_(("user", "assistant")),
        AIMessage.tool_calls_json.is_(None)).order_by(AIMessage.id)).all()
    return {**agent.conversation_to_dict(conv), "messages": [agent.message_to_dict(m) for m in msgs]}


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, db: Session = Depends(get_db)) -> Response:
    conv = db.get(AIConversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    db.execute(delete(AIMessage).where(AIMessage.conversation_id == conversation_id))
    db.delete(conv)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conflicts")
def conflicts(request: Request, include_dismissed: bool = Query(False, alias="includeDismissed"),
              db: Session = Depends(get_db)) -> Dict[str, Any]:
    items = detect_conflicts(db, include_dismissed, _mqtt_connected(request))
    return {"scannedAt": to_iso(utcnow()), "conflicts": [c.to_dict() for c in items]}


@router.post("/conflicts/{conflict_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss(conflict_id: str, db: Session = Depends(get_db)) -> Response:
    if not dismiss_conflict(db, conflict_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such active conflict.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/daily-insights")
def daily_insights(limit: int = Query(7, ge=1, le=90), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.scalars(select(AIDailyInsight).order_by(desc(AIDailyInsight.insight_date)).limit(limit)).all()
    return [insight_to_dict(r) for r in rows]


@router.get("/daily-insights/latest")
def latest_daily_insight(db: Session = Depends(get_db)) -> Dict[str, Any]:
    row = db.scalars(select(AIDailyInsight).order_by(desc(AIDailyInsight.insight_date)).limit(1)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No daily insight yet.")
    return insight_to_dict(row)


@router.post("/daily-insights/generate")
@limiter.limit(settings.rate_limit_ai_chat)
async def generate_insight(request: Request, body: Optional[GenerateInsightRequest] = None) -> Dict[str, Any]:
    today = to_local(utcnow()).date()
    d = (body.date if body and body.date else None) or today - timedelta(days=1)
    if d > today:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Date cannot be in the future.")
    return await generate_daily_insight(d)


@router.get("/actions")
def action_log(limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = db.scalars(select(AIActionLog).order_by(desc(AIActionLog.id)).limit(limit)).all()
    return [{"id": r.id, "conversationId": r.conversation_id, "tool": r.tool,
             "arguments": json.loads(r.arguments_json or "{}"), "ok": r.ok, "summary": r.summary,
             "error": r.error, "createdAt": to_iso(r.created_at)} for r in rows]


# ── Voice (Sarvam) ─────────────────────────────────────────────────────────────

class SpeakRequest(ApiModel):
    text: str = Field(min_length=1, max_length=2500)
    language: Optional[str] = Field(None, max_length=16)


@router.get("/voice/status")
def voice_status() -> Dict[str, Any]:
    from app.ai.sarvam import get_sarvam
    return {"configured": bool(get_sarvam().configured), "sttModel": settings.sarvam_stt_model,
            "ttsModel": settings.sarvam_tts_model, "speaker": settings.sarvam_tts_speaker,
            "language": settings.sarvam_stt_language, "bargeIn": settings.ai_voice_barge_in}


def _require_voice():
    from app.ai.sarvam import get_sarvam
    client = get_sarvam()
    if not client.configured:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Voice isn't configured: set SARVAM_API_KEY in backend/.env and restart.")
    return client


@router.post("/voice/transcribe")
@limiter.limit(settings.rate_limit_ai_chat)
async def voice_transcribe(request: Request, language: Optional[str] = Query(None, max_length=16)) -> Dict[str, Any]:
    """Raw audio in the request body (≤30 s; webm/ogg/wav/mp3…, Content-Type set accordingly)."""
    from app.ai.sarvam import SarvamError
    client = _require_voice()
    audio = await request.body()
    if not audio:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty audio body.")
    if len(audio) > 10 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Audio too large (max 10 MB / 30 s).")
    ctype = (request.headers.get("content-type") or "audio/webm").split(";")[0]
    ext = {"audio/wav": "wav", "audio/x-wav": "wav", "audio/mpeg": "mp3", "audio/ogg": "ogg",
           "audio/mp4": "m4a", "audio/webm": "webm"}.get(ctype, "webm")
    try:
        return await client.transcribe(audio, f"speech.{ext}", ctype, language)
    except SarvamError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))


@router.post("/voice/speak")
@limiter.limit(settings.rate_limit_ai_chat)
async def voice_speak(request: Request, body: SpeakRequest) -> Response:
    """Text → WAV audio (Sarvam Bulbul)."""
    from app.ai.sarvam import SarvamError
    from app.ai.voice import clean_for_speech
    client = _require_voice()
    try:
        wav = await client.synthesize(clean_for_speech(body.text), body.language or settings.sarvam_tts_default_language)
    except SarvamError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
    return Response(content=wav, media_type="audio/wav")
