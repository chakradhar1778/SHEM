"""
SHEM Backend — GET /api/health (public; no secrets or internals exposed).
status is "ok" only when both SQLite and the MQTT broker connection are up.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import get_settings
from app.database import check_db
from app.models.schemas import HealthResponse
from app.utils.timestamps import utcnow

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse, summary="Backend health check", tags=["Health"])
def get_health(request: Request) -> HealthResponse:
    db_ok = check_db()
    mqtt_client = getattr(request.app.state, "mqtt_client", None)
    mqtt_connected = bool(getattr(mqtt_client, "connected", False))
    return HealthResponse(
        status="ok" if db_ok and mqtt_connected else "degraded",
        version=settings.app_version,
        db_ok=db_ok,
        mqtt_connected=mqtt_connected,
        timestamp=utcnow(),
    )
