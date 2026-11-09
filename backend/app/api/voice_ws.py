"""
SHEM Backend — WS /api/ai/voice/live?api_key=<key>   (SHEM AI Live voice session)

Authenticates like /api/stream (browsers can't set headers on WebSockets).
Close codes: 1008 unauthorized, 1013 voice not configured (SARVAM_API_KEY missing).
Protocol: see app/ai/voice.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, status

from app.ai.sarvam import get_sarvam
from app.ai.voice import handle_live
from app.utils.security import websocket_authorized

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ai/voice/live")
async def voice_live(websocket: WebSocket) -> None:
    if not websocket_authorized(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    if not get_sarvam().configured:
        await websocket.accept()
        await websocket.send_json({"type": "error", "fatal": True,
                                   "message": "Voice isn't configured: set SARVAM_API_KEY in backend/.env."})
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return
    await websocket.accept()
    logger.info("SHEM AI Live session started")
    try:
        await handle_live(websocket, getattr(websocket.app.state, "mqtt_client", None))
    finally:
        logger.info("SHEM AI Live session ended")
