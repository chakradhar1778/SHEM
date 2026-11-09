"""
SHEM Backend — Relay Service
Relay channel state, acknowledgement matching and command timeouts.

Acknowledgement rules
---------------------
* An ack is matched by commandId AND must come from the command's device.
* The first terminal result wins: applied / rejected_* are never overwritten.
* "duplicate" from the firmware means "I already applied this exact command
  ID" (the firmware only stores lastCommandId after applying). It therefore
  never downgrades an applied command; if the original "applied" ack was
  lost, a duplicate ack confirms the command as applied.
* A command already marked "timeout" by the backend that later receives
  "applied" is updated to applied (the relay really switched) with a note.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db_models import RelayChannel, RelayCommand
from app.models.schemas import (
    MQTTRelayAckPayload,
    MQTTRelayStatePayload,
    RelayCommandDetailResponse,
    RelayStatusResponse,
)
from app.services.device_service import get_or_create_device, upsert_relay_channel
from app.utils.timestamps import parse_iso, utcnow

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({
    "applied",
    "rejected_expired",
    "rejected_invalid_channel",
    "rejected_invalid_state",
    "rejected_time_unsynchronized",
})
OPEN_STATUSES = ("pending", "published")


def record_relay_state(db: Session, payload: MQTTRelayStatePayload) -> RelayStatusResponse:
    get_or_create_device(db, payload.deviceId)
    at = utcnow()
    if payload.timestamp:
        try:
            at = min(parse_iso(payload.timestamp), at)
        except ValueError:
            pass
    upsert_relay_channel(db, payload.deviceId, payload.channel, payload.state, at)
    db.commit()
    logger.info("Device %s relay %d reported %s", payload.deviceId, payload.channel, payload.state)
    return get_relay_status(db, payload.deviceId, payload.channel)


def record_command_ack(db: Session, payload: MQTTRelayAckPayload) -> Optional[RelayCommand]:
    """Apply an acknowledgement. Returns the command if its record changed."""
    cmd = db.get(RelayCommand, payload.commandId)
    if cmd is None:
        logger.warning("Ack for unknown command %s (status=%s)", payload.commandId, payload.status)
        return None
    if cmd.device_id != payload.deviceId or cmd.channel != payload.channel:
        logger.warning("Ack for %s from device %s/channel %s does not match the command; ignored",
                       payload.commandId, payload.deviceId, payload.channel)
        return None

    previous = cmd.status
    now = utcnow()

    if previous in TERMINAL_STATUSES:
        if payload.status != previous:
            logger.info("Ignoring ack '%s' for %s: already terminal '%s'",
                        payload.status, cmd.command_id, previous)
        return None

    if payload.status == "duplicate":
        cmd.status = "applied"
        cmd.error_message = "Confirmed by a duplicate acknowledgement (original ack not received)"
    else:
        cmd.status = payload.status
        if payload.status.startswith("rejected_"):
            cmd.error_message = f"Firmware rejected command: {payload.status}"
        elif previous == "timeout":
            cmd.error_message = "Applied by device after the backend had marked the command as timed out"
        else:
            cmd.error_message = None
    cmd.acknowledged_at = now

    if cmd.status == "applied":
        upsert_relay_channel(db, payload.deviceId, payload.channel, payload.commandedState, now)

    db.commit()
    logger.info("Command %s: %s → %s", cmd.command_id, previous, cmd.status)
    return cmd


def check_and_mark_timeouts(db: Session) -> List[RelayCommandDetailResponse]:
    """Mark expired, unacknowledged commands as timeout; return them for broadcasting."""
    now = utcnow()
    expired = db.scalars(
        select(RelayCommand).where(
            RelayCommand.status.in_(OPEN_STATUSES),
            RelayCommand.expires_at < now,
        )
    ).all()
    for cmd in expired:
        cmd.status = "timeout"
        cmd.error_message = "No acknowledgement received before the command expired"
    if expired:
        db.commit()
        logger.warning("Marked %d relay command(s) as timeout", len(expired))
    return [RelayCommandDetailResponse.model_validate(c) for c in expired]


def get_relay_status(db: Session, device_id: str, channel_no: int = 1) -> RelayStatusResponse:
    ch = db.scalar(
        select(RelayChannel).where(RelayChannel.device_id == device_id, RelayChannel.channel == channel_no)
    )
    if ch is None:
        return RelayStatusResponse(device_id=device_id, channel=channel_no)
    return RelayStatusResponse(
        device_id=device_id, channel=channel_no,
        commanded_state=ch.commanded_state, last_reported_at=ch.last_reported_at,
    )


def get_command_detail(db: Session, command_id: str) -> Optional[RelayCommandDetailResponse]:
    cmd = db.get(RelayCommand, command_id)
    return RelayCommandDetailResponse.model_validate(cmd) if cmd else None
