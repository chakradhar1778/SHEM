"""
SHEM Backend — Device Service
Device registry, online/offline transitions, staleness watchdog, status view.

Online rule: connection_status == "online" AND a message was received within
STALE_TELEMETRY_THRESHOLD_SECONDS. A watchdog flips stale devices to offline
and records a device_status_events row (once per transition).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import Device, DeviceStatusEvent, RelayChannel
from app.models.schemas import DeviceStatusResponse
from app.utils.timestamps import is_stale, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()


def get_or_create_device(db: Session, device_id: str) -> Device:
    """
    Return the device row, creating it if missing.

    Race-safe: the MQTT thread and API threads may both see "no device" on a
    fresh database; INSERT … ON CONFLICT DO NOTHING lets exactly one insert win
    without an IntegrityError (which previously lost the telemetry message).
    """
    device = db.get(Device, device_id)
    if device is None:
        result = db.execute(
            sqlite_insert(Device)
            .values(
                device_id=device_id,
                name=f"SHEM Meter {device_id}",
                device_type="ESP32_PZEM",
                connection_status="unknown",
                pzem_valid=False,
                created_at=utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["device_id"])
        )
        if result.rowcount:
            logger.info("Registered new device: %s", device_id)
        device = db.get(Device, device_id)
    return device


def _add_event(db: Session, device_id: str, status: str, details: str, at: datetime) -> None:
    db.add(DeviceStatusEvent(device_id=device_id, status=status, recorded_at=at, details=details))


def upsert_relay_channel(db: Session, device_id: str, channel_no: int, state: str, at: datetime) -> bool:
    """Set the reported commanded state (race-safe upsert). Returns True if the state changed."""
    ch = db.scalar(
        select(RelayChannel).where(RelayChannel.device_id == device_id, RelayChannel.channel == channel_no)
    )
    if ch is None:
        db.execute(
            sqlite_insert(RelayChannel)
            .values(device_id=device_id, channel=channel_no, commanded_state=state, last_reported_at=at)
            .on_conflict_do_update(
                index_elements=["device_id", "channel"],
                set_={"commanded_state": state, "last_reported_at": at},
            )
        )
        return True
    changed = ch.commanded_state != state
    ch.commanded_state = state
    ch.last_reported_at = at
    return changed


def mark_device_seen(db: Session, device: Device, at: datetime, pzem_valid: Optional[bool] = None) -> bool:
    """Update last-seen; returns True if the device transitioned to online."""
    device.last_seen_at = at
    if pzem_valid is not None:
        device.pzem_valid = pzem_valid
    if device.connection_status != "online":
        device.connection_status = "online"
        _add_event(db, device.device_id, "online", "Message received from device", at)
        return True
    return False


def record_status_message(
    db: Session,
    device_id: str,
    status: str,
    relay1_state: Optional[str] = None,
    retained: bool = False,
) -> bool:
    """
    Handle shem/device/{id}/status. Returns True if connection_status changed.
    'online' is published (retained) by the firmware on connect; 'offline' is
    its retained MQTT Last-Will. A retained message replayed by the broker
    when the backend (re)subscribes is NOT proof the device is talking right
    now, so it does not refresh last_seen_at — fresh telemetry will.
    """
    device = get_or_create_device(db, device_id)
    now = utcnow()
    changed = device.connection_status != status

    if status == "online":
        device.connection_status = "online"
        if not retained:
            device.last_seen_at = now
            if relay1_state in ("ON", "OFF"):
                upsert_relay_channel(db, device_id, 1, relay1_state, now)
    else:
        device.connection_status = "offline"
        device.pzem_valid = False

    if changed or not retained:
        detail = f"Status message: {status}, relay1={relay1_state}" + (" (retained)" if retained else "")
        _add_event(db, device_id, status, detail, now)
    db.commit()
    logger.info("Device %s status message: %s", device_id, status)
    return changed


def mark_stale_devices(db: Session) -> List[str]:
    """Flip online devices with no recent messages to offline. Returns affected IDs."""
    threshold = settings.stale_telemetry_threshold_seconds
    now = utcnow()
    affected: List[str] = []
    for device in db.scalars(select(Device).where(Device.connection_status == "online")).all():
        if is_stale(device.last_seen_at, threshold):
            device.connection_status = "offline"
            device.pzem_valid = False
            _add_event(db, device.device_id, "offline", f"No messages for more than {threshold}s (stale)", now)
            affected.append(device.device_id)
    if affected:
        db.commit()
        logger.warning("Device(s) marked offline due to staleness: %s", affected)
    return affected


def get_device_status(db: Session, device_id: str, mqtt_connected: bool) -> DeviceStatusResponse:
    device = db.get(Device, device_id)
    channel = db.scalar(
        select(RelayChannel).where(RelayChannel.device_id == device_id, RelayChannel.channel == 1)
    )
    relay_state = channel.commanded_state if channel else None

    if device is None:
        return DeviceStatusResponse(
            device_id=device_id, mqtt_connected=mqtt_connected, device_online=False,
            connection_status="unknown", relay1_state=relay_state,
        )

    stale = is_stale(device.last_seen_at, settings.stale_telemetry_threshold_seconds)
    online = device.connection_status == "online" and not stale

    return DeviceStatusResponse(
        device_id=device_id,
        mqtt_connected=mqtt_connected,
        device_online=online,
        connection_status="online" if online else ("unknown" if device.last_seen_at is None else "offline"),
        last_seen_at=device.last_seen_at,
        pzem_readings_valid=bool(device.pzem_valid and online),
        relay1_state=relay_state,
        stale_since=device.last_seen_at if (device.last_seen_at and stale) else None,
    )
