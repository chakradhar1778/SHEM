"""
SHEM Backend — Telemetry endpoints
GET /api/telemetry/latest
GET /api/telemetry/history?from_time=&to_time=&resolution=auto|raw|1m|5m|15m|1h
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.schemas import HistoryResolution, LatestTelemetryResponse, TelemetryHistoryResponse
from app.services.telemetry_service import MAX_SPAN, choose_resolution, get_latest_telemetry, get_telemetry_history
from app.utils.rate_limit import limiter
from app.utils.timestamps import parse_iso, utcnow

router = APIRouter()
settings = get_settings()


@router.get("/telemetry/latest", response_model=LatestTelemetryResponse,
            summary="Latest physical AC reading (with staleness)", tags=["Telemetry"])
def latest_telemetry(db: Session = Depends(get_db)) -> LatestTelemetryResponse:
    return get_latest_telemetry(db, settings.device_id)


def _parse(name: str, value: str):
    try:
        return parse_iso(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Invalid {name}; use UTC ISO 8601, e.g. 2026-11-01T09:30:00Z.")


@router.get("/telemetry/history", response_model=TelemetryHistoryResponse,
            summary="Historical readings, downsampled to the requested resolution", tags=["Telemetry"])
@limiter.limit(settings.rate_limit_history)
def telemetry_history(
    request: Request,
    from_time: Optional[str] = Query(None, description="UTC ISO 8601 (default: to_time minus 24 h)"),
    to_time: Optional[str] = Query(None, description="UTC ISO 8601 (default: now)"),
    resolution: HistoryResolution = Query("auto", description="auto: raw ≤30 min, 1m ≤6 h, 5m ≤48 h, else 1h"),
    limit: int = Query(2000, ge=1, le=5000, description="Max points for raw resolution"),
    db: Session = Depends(get_db),
) -> TelemetryHistoryResponse:
    to_dt = _parse("to_time", to_time) if to_time else utcnow()
    from_dt = _parse("from_time", from_time) if from_time else to_dt - timedelta(hours=24)
    if from_dt >= to_dt:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "from_time must precede to_time.")
    effective = choose_resolution(to_dt - from_dt) if resolution == "auto" else resolution
    if to_dt - from_dt > MAX_SPAN[effective]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Range too large for resolution {effective} (max {MAX_SPAN[effective].days} days).")
    return get_telemetry_history(db, settings.device_id, from_dt, to_dt, effective, limit)
