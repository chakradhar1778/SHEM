"""
SHEM Backend — Telemetry Service
Validates and persists AC PZEM-004T readings; serves latest + history.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import TelemetryRow
from app.models.schemas import (
    LatestTelemetryResponse,
    MQTTTelemetryPayload,
    TelemetryHistoryPoint,
    TelemetryHistoryResponse,
    TelemetryReading,
)
from app.services.device_service import get_or_create_device, mark_device_seen, upsert_relay_channel
from app.services.energy_service import hourly_stats
from app.utils.timestamps import UTC, is_stale, parse_iso, seconds_since, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

# PZEM-004T v3 (100 A) measuring ranges, with a little headroom
MAX_VOLTAGE_V = 300.0
MAX_CURRENT_A = 110.0
MAX_POWER_W = 30000.0
FUTURE_SKEW_SECONDS = 60


@dataclass
class IngestResult:
    row: Optional[TelemetryRow]          # None → message discarded
    discarded_reason: Optional[str] = None
    came_online: bool = False


def _finite_or_none(value: Optional[float], lo: float, hi: float) -> Optional[float]:
    if value is None or not math.isfinite(value) or not (lo <= value <= hi):
        return None
    return value


def ingest_telemetry(db: Session, payload: MQTTTelemetryPayload) -> IngestResult:
    """
    Contract rules (architecture §5):
      * supplyType must be "AC", source "PZEM-004T", energyUnit "kWh" →
        otherwise the message is discarded (never stored as AC data).
      * voltage/current/power/energy must be finite, ≥ 0 and inside the
        PZEM range → otherwise stored with validity="invalid" (values NULL).
      * frequency / powerFactor outside physical range → NULL, never invented.
      * timestamp: UTC ISO 8601. Empty (ESP32 before NTP sync), malformed or
        more than 60 s in the future → the backend receive time is used.
    """
    if payload.supplyType != "AC":
        return IngestResult(None, f"supplyType={payload.supplyType!r} (only AC hardware data is accepted)")
    if payload.source != "PZEM-004T":
        return IngestResult(None, f"source={payload.source!r} (expected 'PZEM-004T')")
    if payload.energyUnit != "kWh":
        return IngestResult(None, f"energyUnit={payload.energyUnit!r} (expected 'kWh')")

    now = utcnow()
    device = get_or_create_device(db, payload.deviceId)

    v, a, w, e = payload.voltage, payload.current, payload.power, payload.energy
    reason = None
    if any(not math.isfinite(x) or x < 0 for x in (v, a, w, e)):
        reason = "Non-finite or negative electrical measurement"
    elif v > MAX_VOLTAGE_V or a > MAX_CURRENT_A or w > MAX_POWER_W:
        reason = "Measurement outside PZEM-004T range"
    valid = reason is None

    measured_at = now
    if payload.timestamp:
        try:
            ts = parse_iso(payload.timestamp)
            if ts <= now + timedelta(seconds=FUTURE_SKEW_SECONDS):
                measured_at = ts
            else:
                logger.warning("Telemetry timestamp %s is in the future; using receive time", payload.timestamp)
        except ValueError:
            logger.warning("Malformed telemetry timestamp %r; using receive time", payload.timestamp)

    relay = payload.relay1State if payload.relay1State in ("ON", "OFF") else None

    row = TelemetryRow(
        device_id=payload.deviceId,
        voltage_v=v if valid else None,
        current_a=a if valid else None,
        active_power_w=w if valid else None,
        energy_kwh=e if valid else None,
        frequency_hz=_finite_or_none(payload.frequency, 40.0, 70.0) if valid else None,
        power_factor=_finite_or_none(payload.powerFactor, 0.0, 1.0) if valid else None,
        relay1_state=relay,
        supply_type="AC",
        source="PZEM-004T",
        validity="valid" if valid else "invalid",
        validity_reason=reason,
        measured_at=measured_at,
        received_at=now,
    )
    db.add(row)

    came_online = mark_device_seen(db, device, now, pzem_valid=valid)
    if relay:
        upsert_relay_channel(db, payload.deviceId, 1, relay, now)

    db.commit()
    db.refresh(row)
    return IngestResult(row, None, came_online)


def reading_from_row(row: TelemetryRow) -> TelemetryReading:
    reading = TelemetryReading.model_validate(row)
    if row.active_power_w is not None:
        reading.load_active = row.active_power_w >= settings.load_active_threshold_w
    return reading


def get_latest_telemetry(db: Session, device_id: str) -> LatestTelemetryResponse:
    row = db.scalar(
        select(TelemetryRow)
        .where(TelemetryRow.device_id == device_id, TelemetryRow.validity == "valid")
        .order_by(TelemetryRow.measured_at.desc(), TelemetryRow.id.desc())
        .limit(1)
    )
    if not row:
        return LatestTelemetryResponse(
            available=False, stale=True, message="No telemetry recorded yet for this device."
        )
    stale = is_stale(row.received_at, settings.stale_telemetry_threshold_seconds)
    return LatestTelemetryResponse(
        available=True,
        stale=stale,
        age_seconds=round(seconds_since(row.received_at), 1),
        reading=reading_from_row(row),
        message="Telemetry is stale (no recent updates)" if stale else "Live reading available",
    )


# ── History ────────────────────────────────────────────────────────────────────

RESOLUTION_SECONDS = {"1m": 60, "5m": 300, "15m": 900}
MAX_SPAN = {"raw": timedelta(days=31), "1m": timedelta(days=31), "5m": timedelta(days=31),
            "15m": timedelta(days=31), "1h": timedelta(days=366)}


def choose_resolution(span: timedelta) -> str:
    if span <= timedelta(minutes=30):
        return "raw"
    if span <= timedelta(hours=6):
        return "1m"
    if span <= timedelta(hours=48):
        return "5m"
    return "1h"


def _r(x: Optional[float], nd: int = 3) -> Optional[float]:
    return round(x, nd) if x is not None else None


def get_telemetry_history(
    db: Session,
    device_id: str,
    from_time: datetime,
    to_time: datetime,
    resolution: str = "auto",
    limit: int = 2000,
) -> TelemetryHistoryResponse:
    """Caller must validate from < to and span ≤ MAX_SPAN[resolution]."""
    if resolution == "auto":
        resolution = choose_resolution(to_time - from_time)

    points: List[TelemetryHistoryPoint] = []
    truncated = False
    note = None
    raw_floor = utcnow() - timedelta(days=settings.raw_telemetry_retention_days)

    base = (
        TelemetryRow.device_id == device_id,
        TelemetryRow.validity == "valid",
        TelemetryRow.measured_at >= from_time,
        TelemetryRow.measured_at <= to_time,
    )

    if resolution == "raw":
        rows = db.scalars(
            select(TelemetryRow).where(*base)
            .order_by(TelemetryRow.measured_at.desc(), TelemetryRow.id.desc())
            .limit(limit + 1)
        ).all()
        truncated = len(rows) > limit
        rows = list(reversed(rows[:limit]))  # keep the most recent `limit` readings
        points = [
            TelemetryHistoryPoint(
                timestamp=r.measured_at, samples=1, voltage_v=r.voltage_v, current_a=r.current_a,
                active_power_w=r.active_power_w, max_power_w=r.active_power_w,
                energy_kwh=r.energy_kwh, frequency_hz=r.frequency_hz, power_factor=r.power_factor,
            )
            for r in rows
        ]
        if truncated:
            note = f"Showing the most recent {limit} raw readings; use a coarser resolution for the full window."

    elif resolution in RESOLUTION_SECONDS:
        step = RESOLUTION_SECONDS[resolution]
        bucket = cast(func.strftime("%s", TelemetryRow.measured_at), Integer) // step
        rows = db.execute(
            select(
                bucket.label("b"),
                func.count().label("n"),
                func.avg(TelemetryRow.voltage_v),
                func.avg(TelemetryRow.current_a),
                func.avg(TelemetryRow.active_power_w),
                func.max(TelemetryRow.active_power_w),
                func.max(TelemetryRow.energy_kwh),
                func.avg(TelemetryRow.frequency_hz),
                func.avg(TelemetryRow.power_factor),
            )
            .where(*base)
            .group_by("b")
            .order_by("b")
        ).all()
        points = [
            TelemetryHistoryPoint(
                timestamp=datetime.fromtimestamp(int(b) * step, tz=UTC), samples=n,
                voltage_v=_r(v, 2), current_a=_r(a, 4), active_power_w=_r(p, 2), max_power_w=pmax,
                energy_kwh=e, frequency_hz=_r(f, 2), power_factor=_r(pf, 3),
            )
            for b, n, v, a, p, pmax, e, f, pf in rows
        ]

    else:  # 1h — served from hourly rollups + raw tail
        stats = hourly_stats(db, device_id, from_time, to_time)
        points = [
            TelemetryHistoryPoint(
                timestamp=s.bucket_start, samples=s.samples, voltage_v=_r(s.voltage_avg, 2),
                current_a=_r(s.current_avg, 4), active_power_w=_r(s.power_avg, 2),
                max_power_w=s.power_max, energy_kwh=s.energy_register_end,
                energy_used_kwh=_r(s.energy_kwh, 4), frequency_hz=_r(s.frequency_avg, 2),
                power_factor=_r(s.power_factor_avg, 3),
            )
            for _, s in sorted(stats.items())
        ]

    if resolution != "1h" and from_time < raw_floor:
        note = (note + " " if note else "") + (
            f"Raw readings are kept for {settings.raw_telemetry_retention_days} days; "
            "use resolution=1h for older data."
        )

    return TelemetryHistoryResponse(
        device_id=device_id, from_time=from_time, to_time=to_time, resolution=resolution,
        count=len(points), truncated=truncated, data_note=note, readings=points,
    )
