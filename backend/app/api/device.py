"""SHEM Backend — GET /api/device/status"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.schemas import DeviceStatusResponse
from app.services.device_service import get_device_status

router = APIRouter()
settings = get_settings()


@router.get("/device/status", response_model=DeviceStatusResponse,
            summary="ESP32 online/offline, PZEM validity, relay state", tags=["Device"])
def device_status(request: Request, db: Session = Depends(get_db)) -> DeviceStatusResponse:
    mqtt_client = getattr(request.app.state, "mqtt_client", None)
    return get_device_status(db, settings.device_id, bool(mqtt_client and mqtt_client.connected))
