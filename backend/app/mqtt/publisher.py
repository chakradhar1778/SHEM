"""
SHEM Backend — MQTT Relay Command Publisher
Persists, then publishes, outbound relay commands to the ESP32.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Tuple

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import RelayCommand
from app.models.schemas import RelayCommandResponse
from app.services.device_service import get_or_create_device
from app.utils.command_id import generate_command_id
from app.utils.timestamps import utcnow

if TYPE_CHECKING:
    from app.mqtt.client import MQTTClientManager

logger = logging.getLogger(__name__)
settings = get_settings()


def publish_relay_command(
    mqtt_client: "MQTTClientManager",
    db: Session,
    device_id: str,
    channel: int,
    state: str,
) -> Tuple[bool, RelayCommandResponse]:
    """
    Store a pending command, publish it with QoS 1 and retain=False (a
    retained ON command could energise the load on ESP32 reconnect), then
    mark it published. Success is only reported to users after the ack.
    """
    if channel != 1:
        raise ValueError("Only relay channel 1 is supported on current hardware.")
    if state not in ("ON", "OFF"):
        raise ValueError(f"Invalid relay state '{state}', must be 'ON' or 'OFF'.")

    now = utcnow()
    expires_at = now + timedelta(seconds=settings.command_expiry_seconds)
    command_id = generate_command_id()

    get_or_create_device(db, device_id)  # FK target must exist even before first telemetry
    cmd = RelayCommand(
        command_id=command_id, device_id=device_id, channel=channel,
        requested_state=state, status="pending", created_at=now, expires_at=expires_at,
    )
    db.add(cmd)
    db.commit()

    payload = json.dumps({
        "commandId": command_id,
        "channel": channel,
        "state": state,
        "expiresAtUnix": int(expires_at.timestamp()),
    })
    topic = f"shem/device/{device_id}/relay/{channel}/command"
    success = mqtt_client.publish(topic=topic, payload=payload, qos=1, retain=False)

    if success:
        cmd.status = "published"
        cmd.published_at = utcnow()
        message = f"Relay {state} command published; waiting for device acknowledgement."
        logger.info("Relay command %s published (state=%s)", command_id, state)
    else:
        cmd.status = "publish_failed"
        cmd.error_message = "MQTT client is not connected to the broker."
        message = "Could not publish command to the MQTT broker."
        logger.error("Relay command %s could not be published", command_id)
    db.commit()

    return success, RelayCommandResponse(
        command_id=command_id, channel=channel, requested_state=state, status=cmd.status,
        message=message, created_at=now, expires_at=expires_at,
    )
