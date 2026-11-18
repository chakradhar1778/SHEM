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
    ApplianceSchema,
    RelayCommandDetailResponse,
    RelayCommandRequest,
    RelayCommandResponse,
    RelayMismatchConfirmSameResponse,
    RelayMismatchStatus,
    RelayMismatchSwitchRequest,
    RelayStatusResponse,
)
from app.mqtt.publisher import publish_relay_command
from app.services import relay_mismatch_service
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


@router.get("/relay/1/mismatch", response_model=RelayMismatchStatus,
            summary="Live load mismatch status on relay 1", tags=["Relay"])
def relay_mismatch_status(db: Session = Depends(get_db)) -> RelayMismatchStatus:
    """Checks live meter power vs registered appliance rated watts and lists matching appliances."""
    return relay_mismatch_service.evaluate_relay_mismatch(db, settings.device_id, channel=1)


@router.post("/relay/1/mismatch/confirm-same", response_model=RelayMismatchConfirmSameResponse,
             summary="Confirm the plugged-in appliance is still the registered one", tags=["Relay"])
def relay_mismatch_confirm_same(db: Session = Depends(get_db)) -> RelayMismatchConfirmSameResponse:
    """Snoozes normal voltage-variance alerts; returns a safety warning when live power is far beyond rated."""
    return relay_mismatch_service.confirm_same_appliance(db, settings.device_id, channel=1)


@router.post("/relay/1/mismatch/switch", response_model=ApplianceSchema,
             summary="Switch relay 1 to an existing appliance (unassigning the previous one)", tags=["Relay"])
def relay_mismatch_switch(body: RelayMismatchSwitchRequest, db: Session = Depends(get_db)) -> ApplianceSchema:
    target = relay_mismatch_service.switch_relay_appliance(db, body.appliance_id, channel=1)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Appliance not found.")
    return ApplianceSchema.model_validate(target)
