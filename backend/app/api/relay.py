"""
SHEM Backend — Relay control (channel 1 only)
GET  /api/relay/1/status
POST /api/relay/1/command            {"state": "ON" | "OFF"}
GET  /api/relay/1/commands/{commandId}
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.schemas import (
    RelayCommandDetailResponse,
    RelayCommandRequest,
    RelayCommandResponse,
    RelayStatusResponse,
)
from app.mqtt.publisher import publish_relay_command
from app.services.relay_service import get_command_detail, get_relay_status
from app.utils.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


@router.get("/relay/1/status", response_model=RelayStatusResponse,
            summary="Last reported commanded state of relay 1", tags=["Relay"])
def relay_status(db: Session = Depends(get_db)) -> RelayStatusResponse:
    return get_relay_status(db, settings.device_id, 1)


@router.post("/relay/1/command", response_model=RelayCommandResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Request relay 1 ON/OFF (result arrives via acknowledgement)", tags=["Relay"])
@limiter.limit(settings.rate_limit_relay_command)
def issue_relay_command(request: Request, cmd_in: RelayCommandRequest,
                        db: Session = Depends(get_db)) -> RelayCommandResponse:
    """
    Returns 202 with status "published": the command is on its way, NOT applied.
    Poll GET /relay/1/commands/{commandId} or listen for the `relay_update`
    WebSocket event; only status "applied" means the firmware switched the relay.
    """
    mqtt_client = getattr(request.app.state, "mqtt_client", None)
    if mqtt_client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "MQTT service is not running.")
    success, response = publish_relay_command(mqtt_client, db, settings.device_id, 1, cmd_in.state)
    if not success:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"Broker unavailable; command {response.command_id} recorded as publish_failed.")
    return response


@router.get("/relay/1/commands/{command_id}", response_model=RelayCommandDetailResponse,
            summary="Relay command lifecycle", tags=["Relay"])
def command_detail(command_id: str, db: Session = Depends(get_db)) -> RelayCommandDetailResponse:
    """Statuses: pending, published, applied, rejected_*, timeout, publish_failed."""
    detail = get_command_detail(db, command_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Command not found.")
    return detail
