"""
SHEM Backend — MQTT Topic Handlers

Run on Paho's network thread: each call opens its own SessionLocal() and
pushes WebSocket events through broadcaster.publish_from_thread().

Common rules for every inbound topic:
  * payload must be valid JSON matching the firmware contract;
  * deviceId must equal the configured DEVICE_ID (unknown devices discarded);
  * relay topics accept channel 1 only.
"""

from __future__ import annotations

import json
import logging
from typing import Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.database import SessionLocal
from app.models.schemas import (
    MQTTRelayAckPayload,
    MQTTRelayStatePayload,
    MQTTStatusPayload,
    MQTTTelemetryPayload,
    RelayCommandDetailResponse,
)
from app.services.broadcaster import broadcaster
from app.services.device_service import get_device_status, record_status_message
from app.services.relay_service import record_command_ack, record_relay_state
from app.services.telemetry_service import ingest_telemetry, reading_from_row

logger = logging.getLogger(__name__)
settings = get_settings()

M = TypeVar("M", bound=BaseModel)


def _parse(topic: str, raw: bytes, model: Type[M]) -> Optional[M]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("[%s] discarded: invalid JSON (%s)", topic, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("[%s] discarded: payload is not a JSON object", topic)
        return None
    if data.get("deviceId") != settings.device_id:
        logger.warning("[%s] discarded: unknown deviceId %r", topic, data.get("deviceId"))
        return None
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        logger.warning("[%s] discarded: payload failed validation: %s", topic, exc.errors()[:3])
        return None


def _broadcast_device_status(mqtt_connected: bool = True) -> None:
    with SessionLocal() as db:
        status = get_device_status(db, settings.device_id, mqtt_connected=mqtt_connected)
    broadcaster.publish_from_thread("device_status", status.model_dump(mode="json"))


def broadcast_mqtt_state(connected: bool) -> None:
    """MQTTClientManager.on_state_change hook: push broker up/down to clients at once."""
    try:
        _broadcast_device_status(mqtt_connected=connected)
    except Exception:
        logger.exception("Could not broadcast MQTT state change")


def handle_telemetry(raw: bytes, retained: bool = False) -> None:
    payload = _parse("telemetry", raw, MQTTTelemetryPayload)
    if payload is None:
        return
    with SessionLocal() as db:
        try:
            result = ingest_telemetry(db, payload)
        except Exception:
            logger.exception("Error storing telemetry")
            return
        if result.row is None:
            logger.warning("[telemetry] discarded: %s", result.discarded_reason)
            return
        if result.row.validity == "valid":
            broadcaster.publish_from_thread("telemetry", reading_from_row(result.row).model_dump(mode="json"))
        else:
            logger.warning("[telemetry] stored as invalid: %s", result.row.validity_reason)
    if result.came_online or result.row.validity != "valid":
        _broadcast_device_status()


def handle_device_status(raw: bytes, retained: bool = False) -> None:
    payload = _parse("status", raw, MQTTStatusPayload)
    if payload is None:
        return
    with SessionLocal() as db:
        try:
            record_status_message(db, payload.deviceId, payload.status, payload.relay1State, retained=retained)
        except Exception:
            logger.exception("Error recording status message")
            return
    _broadcast_device_status()


def handle_relay_state(raw: bytes, retained: bool = False) -> None:
    payload = _parse("relay/state", raw, MQTTRelayStatePayload)
    if payload is None:
        return
    with SessionLocal() as db:
        try:
            status = record_relay_state(db, payload)
        except Exception:
            logger.exception("Error recording relay state")
            return
    broadcaster.publish_from_thread("relay_state", status.model_dump(mode="json"))


def handle_relay_ack(raw: bytes, retained: bool = False) -> None:
    payload = _parse("relay/ack", raw, MQTTRelayAckPayload)
    if payload is None:
        return
    if payload.channel != 1:
        logger.warning("[relay/ack] discarded: unsupported channel %s", payload.channel)
        return
    with SessionLocal() as db:
        try:
            cmd = record_command_ack(db, payload)
        except Exception:
            logger.exception("Error recording relay ack")
            return
        if cmd is None:
            return
        data = RelayCommandDetailResponse.model_validate(cmd).model_dump(mode="json")
    data["commandedState"] = payload.commandedState
    broadcaster.publish_from_thread("relay_update", data)
