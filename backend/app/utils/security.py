"""
SHEM Backend — API Key Authentication

REST:      X-API-Key header (query-string keys are NOT accepted for REST, so
           keys do not end up in proxy/tunnel access logs or browser history).
WebSocket: browsers cannot set headers on WebSocket requests, so /api/stream
           accepts ?api_key=... (or the X-API-Key header for non-browser clients).

Fail-closed: if API_KEY is empty every protected request is rejected unless
ALLOW_UNAUTHENTICATED_DEV=true is set explicitly.
"""

from __future__ import annotations

import logging
import secrets
from typing import Optional

from fastapi import HTTPException, Security, WebSocket, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def is_valid_api_key(provided: Optional[str]) -> bool:
    settings = get_settings()
    configured = settings.api_key.strip()
    if not configured:
        return settings.allow_unauthenticated_dev
    if not provided:
        return False
    return secrets.compare_digest(provided.strip().encode(), configured.encode())


def require_api_key(header_key: Optional[str] = Security(API_KEY_HEADER)) -> None:
    if not is_valid_api_key(header_key):
        logger.warning("Unauthorized API request rejected (invalid or missing key)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def websocket_authorized(websocket: WebSocket) -> bool:
    provided = websocket.query_params.get("api_key") or websocket.headers.get("x-api-key")
    return is_valid_api_key(provided)
