"""
SHEM Backend — Relay load-mismatch detection & re-identification.

Compares the live PZEM active power reading on relay channel 1 against the
registered appliance's rated watts (using the user-adjustable threshold from
HouseholdConfig, default 30%).

When a mismatch is detected:
  1. Looks for other appliances in inventory whose rated watts match the live
     load (preferring appliances previously plugged into Relay 1).
  2. Emits a `relay_mismatch` Notification (with structured metadata_json) so
     the notification bell and the appliance warning tag both light up.
  3. Supports resolution actions:
     - confirm_same: allows normal voltage fluctuation, but flags a hard safety
       warning when live power >= rated * big_diff_factor (default 5x).
     - switch_relay_appliance: unassigns the old appliance (remembering
       last_relay_channel = 1) and assigns the matching appliance to Relay 1.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import Appliance, HouseholdConfig, Notification, RelayChannel, TelemetryRow
from app.models.schemas import (
    RelayMismatchCandidate,
    RelayMismatchConfirmSameResponse,
    RelayMismatchStatus,
)
from app.utils.timestamps import utcnow

logger = logging.getLogger(__name__)

# In-memory snooze map: (channel, appliance_id) -> monotonic timestamp until which
# normal (non-big-diff) mismatch alerts are suppressed after the user clicks "Still same".
_snoozed_until: Dict[Tuple[int, str], float] = {}


def clear_snooze() -> None:
    """Clear in-memory snooze state (used in tests)."""
    _snoozed_until.clear()


def _is_snoozed(channel: int, appliance_id: str) -> bool:
    until = _snoozed_until.get((channel, appliance_id), 0.0)
    return time.monotonic() < until


def get_mismatch_threshold(db: Session) -> float:
    s = get_settings()
    cfg = db.get(HouseholdConfig, 1)
    if cfg is not None and cfg.relay_mismatch_threshold_percent is not None:
        return float(max(5.0, min(100.0, cfg.relay_mismatch_threshold_percent)))
    return float(s.relay_mismatch_threshold_percent)


def _latest_power_w(db: Session, device_id: str) -> Optional[float]:
    """Return the most recent valid active_power_w reading (within the last 60 s)."""
    cutoff = utcnow() - timedelta(seconds=60)
    row = db.scalar(
        select(TelemetryRow)
        .where(
            TelemetryRow.device_id == device_id,
            TelemetryRow.validity == "valid",
            TelemetryRow.active_power_w.is_not(None),
            TelemetryRow.measured_at >= cutoff,
        )
        .order_by(TelemetryRow.measured_at.desc(), TelemetryRow.id.desc())
        .limit(1)
    )
    return float(row.active_power_w) if row and row.active_power_w is not None else None


def _relay_commanded_on(db: Session, device_id: str, channel: int) -> bool:
    rc = db.scalar(
        select(RelayChannel).where(
            RelayChannel.device_id == device_id,
            RelayChannel.channel == channel,
        )
    )
    return bool(rc and rc.commanded_state == "ON")


def _find_matching_appliances(
    db: Session,
    current_appliance_id: str,
    live_w: float,
    threshold_percent: float,
    channel: int = 1,
) -> List[RelayMismatchCandidate]:
    """Find other appliances in inventory whose rated watts match the live power reading."""
    rows = db.scalars(
        select(Appliance).where(
            Appliance.id != current_appliance_id,
            Appliance.rated_watts.is_not(None),
            Appliance.rated_watts > 0,
        )
    ).all()
    candidates: List[RelayMismatchCandidate] = []
    for a in rows:
        rated = float(a.rated_watts or 0.0)
        if rated <= 0:
            continue
        dev = abs(live_w - rated) / rated * 100.0
        if dev <= threshold_percent:
            candidates.append(
                RelayMismatchCandidate(
                    appliance_id=a.id,
                    name=a.name,
                    icon_type=a.icon_type,
                    rated_watts=round(rated, 1),
                    was_on_relay=(a.last_relay_channel == channel),
                    deviation_percent=round(dev, 1),
                )
            )
    # Prefer appliances that were previously plugged into this relay, then closest wattage match.
    candidates.sort(key=lambda c: (not c.was_on_relay, c.deviation_percent, c.name.lower()))
    return candidates[:5]


def _unread_mismatch_notification_id(db: Session) -> Optional[int]:
    return db.scalar(
        select(Notification.id)
        .where(Notification.kind == "relay_mismatch", Notification.read_at.is_(None))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(1)
    )


def evaluate_relay_mismatch(
    db: Session,
    device_id: str,
    channel: int = 1,
    ignore_snooze: bool = False,
) -> RelayMismatchStatus:
    """Evaluate live Relay 1 load vs its registered appliance right now."""
    s = get_settings()
    threshold = get_mismatch_threshold(db)
    base = RelayMismatchStatus(
        active=False,
        channel=channel,
        threshold_percent=threshold,
        big_diff_factor=s.relay_mismatch_big_diff_factor,
    )
    if not s.relay_mismatch_enabled:
        return base

    appliance: Optional[Appliance] = db.scalar(
        select(Appliance).where(Appliance.relay_channel == channel).limit(1)
    )
    if appliance is None or appliance.rated_watts is None or appliance.rated_watts <= 0:
        return base

    base.appliance_id = appliance.id
    base.appliance_name = appliance.name
    base.icon_type = appliance.icon_type
    base.rated_watts = round(float(appliance.rated_watts), 1)

    if not _relay_commanded_on(db, device_id, channel):
        return base

    live_w = _latest_power_w(db, device_id)
    if live_w is None or live_w < s.relay_mismatch_min_watts:
        return base

    rated = float(appliance.rated_watts)
    deviation = abs(live_w - rated) / rated * 100.0
    is_big = live_w >= rated * s.relay_mismatch_big_diff_factor

    base.live_watts = round(live_w, 1)
    base.deviation_percent = round(deviation, 1)
    base.is_big_diff = is_big

    if deviation <= threshold:
        return base

    # Respect snooze for normal variance, but never suppress a big-diff safety warning.
    if not ignore_snooze and not is_big and _is_snoozed(channel, appliance.id):
        return base

    matches = _find_matching_appliances(db, appliance.id, live_w, threshold, channel)
    base.active = True
    base.matching_appliances = matches
    base.suggested_appliance = matches[0] if matches else None
    base.notification_id = _unread_mismatch_notification_id(db)
    return base


def check_relay_mismatch(db: Session, device_id: str, channel: int = 1) -> List[Notification]:
    """Called from the alerts loop. Creates a `relay_mismatch` notification if active."""
    s = get_settings()
    status = evaluate_relay_mismatch(db, device_id, channel)
    if not status.active or not status.appliance_id or status.live_watts is None or status.rated_watts is None:
        return []

    now = utcnow()
    cooldown_sec = max(60, s.relay_mismatch_cooldown_minutes * 60)
    window = int(now.timestamp() // cooldown_sec)
    level = "big" if status.is_big_diff else "warn"
    dedupe = f"relay-mismatch:{channel}:{status.appliance_id}:{level}:{window}"

    if db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe)) is not None:
        return []

    meta: Dict[str, object] = {
        "relay": channel,
        "liveWatts": status.live_watts,
        "ratedWatts": status.rated_watts,
        "deviationPercent": status.deviation_percent,
        "thresholdPercent": status.threshold_percent,
        "isBigDiff": status.is_big_diff,
        "applianceId": status.appliance_id,
        "applianceName": status.appliance_name,
        "iconType": status.icon_type,
        "suggestedAppliance": (
            status.suggested_appliance.model_dump(by_alias=True)
            if status.suggested_appliance
            else None
        ),
    }

    if status.is_big_diff:
        severity = "critical"
        title = f"Relay {channel}: unexpected high load ({status.live_watts:.0f} W)"
        message = (
            f"Live load ({status.live_watts:.0f} W) is {status.deviation_percent:.0f}% off "
            f"{status.appliance_name}'s rated {status.rated_watts:.0f} W — far too large for voltage fluctuation. "
            f"Tap to check or switch the appliance on Relay {channel}."
        )
    elif status.suggested_appliance:
        severity = "warning"
        title = f"Relay {channel}: looks like {status.suggested_appliance.name}?"
        message = (
            f"Live power is {status.live_watts:.0f} W (currently set to {status.appliance_name} · "
            f"{status.rated_watts:.0f} W). Tap to switch Relay {channel} to {status.suggested_appliance.name} "
            f"or add another appliance."
        )
    else:
        severity = "warning"
        title = f"Relay {channel}: load differs from {status.appliance_name}"
        message = (
            f"Live power ({status.live_watts:.0f} W) differs from {status.appliance_name}'s rated "
            f"{status.rated_watts:.0f} W by {status.deviation_percent:.0f}%. "
            f"Is it still {status.appliance_name}, or another appliance?"
        )

    n = Notification(
        dedupe_key=dedupe[:160],
        kind="relay_mismatch",
        severity=severity,
        title=title[:200],
        message=message,
        link="/live",
        metadata_json=json.dumps(meta),
        created_at=now,
    )
    db.add(n)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return []
    db.refresh(n)
    logger.info(
        "Relay mismatch alert: ch%d live=%.1fW rated=%.1fW appliance=%s big=%s",
        channel, status.live_watts, status.rated_watts, status.appliance_name, status.is_big_diff,
    )
    return [n]


def mark_mismatch_notifications_read(db: Session) -> None:
    db.execute(
        update(Notification)
        .where(Notification.kind == "relay_mismatch", Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )


def confirm_same_appliance(
    db: Session,
    device_id: str,
    channel: int = 1,
) -> RelayMismatchConfirmSameResponse:
    """Handle user saying 'It is still the same appliance'."""
    s = get_settings()
    status = evaluate_relay_mismatch(db, device_id, channel, ignore_snooze=True)
    if not status.active or not status.appliance_id:
        mark_mismatch_notifications_read(db)
        db.commit()
        return RelayMismatchConfirmSameResponse(
            accepted=True,
            requires_warning=False,
            message="No active load mismatch right now.",
        )

    if status.is_big_diff:
        return RelayMismatchConfirmSameResponse(
            accepted=False,
            requires_warning=True,
            live_watts=status.live_watts,
            rated_watts=status.rated_watts,
            deviation_percent=status.deviation_percent,
            message=(
                f"{status.live_watts:.0f} W is far beyond what a {status.rated_watts:.0f} W "
                f"{status.appliance_name} can normally draw (even with voltage swings). "
                "Please inspect the appliance and socket for faults, or go back and register it as a different appliance."
            ),
        )

    cooldown_sec = max(60, s.relay_mismatch_cooldown_minutes * 60)
    _snoozed_until[(channel, status.appliance_id)] = time.monotonic() + cooldown_sec
    mark_mismatch_notifications_read(db)
    db.commit()
    return RelayMismatchConfirmSameResponse(
        accepted=True,
        requires_warning=False,
        live_watts=status.live_watts,
        rated_watts=status.rated_watts,
        deviation_percent=status.deviation_percent,
        message=f"Got it — keeping {status.appliance_name} on Relay {channel}.",
    )


def switch_relay_appliance(db: Session, target_appliance_id: str, channel: int = 1) -> Optional[Appliance]:
    """Unassign current owner of `channel` (turning it OFF) and assign `target_appliance_id` (turning it ON)."""
    target = db.get(Appliance, target_appliance_id)
    if target is None:
        return None
    now = utcnow()
    s = get_settings()
    current_owners = db.scalars(
        select(Appliance).where(Appliance.relay_channel == channel, Appliance.id != target_appliance_id)
    ).all()
    for owner in current_owners:
        owner.relay_channel = None
        owner.last_relay_channel = channel
        owner.status = "off"
        owner.sim_manual_state = "OFF"
        owner.sim_override_until = None
        owner.updated_at = now
        _snoozed_until.pop((channel, owner.id), None)

    target.relay_channel = channel
    target.last_relay_channel = channel
    target.status = "on"
    target.sim_manual_state = None
    target.sim_override_until = None
    target.updated_at = now
    _snoozed_until.pop((channel, target.id), None)

    # Ensure Relay 1 state is ON since the newly switched appliance is active
    from app.services.device_service import upsert_relay_channel
    upsert_relay_channel(db, s.device_id, channel, "ON", now)

    mark_mismatch_notifications_read(db)
    db.commit()
    db.refresh(target)

    # Broadcast simulation update & relay state so all live subscribers reflect the state changes
    try:
        from app.services.broadcaster import broadcaster
        from app.services.simulation_service import simulation_service
        sim_payload = simulation_service.tick(db, now)
        broadcaster.publish_from_thread("sim_update", sim_payload)
        broadcaster.publish_from_thread("relay_state", {
            "deviceId": s.device_id,
            "channel": channel,
            "state": "ON",
        })
    except Exception as exc:
        logger.debug("Broadcaster publish error in switch_relay_appliance: %s", exc)

    return target
