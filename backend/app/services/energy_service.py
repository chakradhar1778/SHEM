"""
SHEM Backend — Energy aggregation, hourly rollups and data retention.

Energy is NEVER computed by summing samples. The PZEM `energy` field is a
cumulative register, so consumption between two consecutive valid readings
is the register difference, with guards for:
  * register reset (PZEM reset / replacement): register drops to ~0 → the new
    value is the energy accumulated since the reset;
  * float noise: tiny negative steps (≤ 10 Wh) count as 0;
  * glitches: a step larger than the meter's maximum possible power over the
    elapsed time is discarded.
Each delta is attributed to the local clock hour of the later reading.

Storage tiers:
  raw `telemetry`        → kept RAW_TELEMETRY_RETENTION_DAYS (default 7)
  `telemetry_hourly`     → one row per local hour, kept indefinitely
`hourly_stats()` transparently merges both, so callers never care which
tier the data came from.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import incremental_vacuum
from app.models.db_models import DeviceStatusEvent, RelayCommand, TelemetryHourly, TelemetryRow
from app.utils.timestamps import HOUR, local_hour_floor, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

RESET_NOISE_KWH = 0.01          # negative steps up to 10 Wh are treated as noise
MAX_METER_POWER_KW = 26.0       # PZEM-004T 100 A × 260 V
OPEN_COMMAND_STATUSES = ("pending", "published")


# ── Register delta ─────────────────────────────────────────────────────────────

def register_delta(prev_kwh: float, cur_kwh: float, elapsed_s: float) -> float:
    if cur_kwh >= prev_kwh:
        delta = cur_kwh - prev_kwh
    elif prev_kwh - cur_kwh <= RESET_NOISE_KWH:
        return 0.0
    else:
        delta = cur_kwh  # register was reset; count what accumulated since
    max_possible = MAX_METER_POWER_KW * max(elapsed_s, 0.0) / 3600.0 + RESET_NOISE_KWH
    if delta > max_possible:
        logger.warning("Discarding implausible energy step %.4f kWh over %.0fs", delta, elapsed_s)
        return 0.0
    return delta


# ── Hour statistics ────────────────────────────────────────────────────────────

@dataclass
class HourStats:
    bucket_start: datetime
    samples: int = 0
    energy_kwh: float = 0.0
    energy_register_end: Optional[float] = None
    last_measured_at: Optional[datetime] = None
    voltage_avg: Optional[float] = None
    voltage_min: Optional[float] = None
    voltage_max: Optional[float] = None
    current_avg: Optional[float] = None
    power_avg: Optional[float] = None
    power_max: Optional[float] = None
    power_factor_avg: Optional[float] = None
    frequency_avg: Optional[float] = None


class _Acc:
    """Accumulates raw readings for one bucket."""

    def __init__(self, bucket_start: datetime) -> None:
        self.b = bucket_start
        self.n = 0
        self.energy = 0.0
        self.e_end: Optional[float] = None
        self.last_t: Optional[datetime] = None
        self.v_sum = self.a_sum = self.p_sum = 0.0
        self.v_min: Optional[float] = None
        self.v_max: Optional[float] = None
        self.p_max: Optional[float] = None
        self.pf_sum = 0.0
        self.pf_n = 0
        self.f_sum = 0.0
        self.f_n = 0

    def add(self, t, v, a, p, e, pf, f, delta) -> None:
        self.n += 1
        self.energy += delta
        self.e_end = e
        self.last_t = t
        self.v_sum += v or 0.0
        self.a_sum += a or 0.0
        self.p_sum += p or 0.0
        if v is not None:
            self.v_min = v if self.v_min is None else min(self.v_min, v)
            self.v_max = v if self.v_max is None else max(self.v_max, v)
        if p is not None:
            self.p_max = p if self.p_max is None else max(self.p_max, p)
        if pf is not None:
            self.pf_sum += pf
            self.pf_n += 1
        if f is not None:
            self.f_sum += f
            self.f_n += 1

    def stats(self) -> HourStats:
        n = self.n or 1
        return HourStats(
            bucket_start=self.b,
            samples=self.n,
            energy_kwh=round(self.energy, 6),
            energy_register_end=self.e_end,
            last_measured_at=self.last_t,
            voltage_avg=round(self.v_sum / n, 3),
            voltage_min=self.v_min,
            voltage_max=self.v_max,
            current_avg=round(self.a_sum / n, 4),
            power_avg=round(self.p_sum / n, 3),
            power_max=self.p_max,
            power_factor_avg=round(self.pf_sum / self.pf_n, 4) if self.pf_n else None,
            frequency_avg=round(self.f_sum / self.f_n, 3) if self.f_n else None,
        )


_RAW_COLS = (
    TelemetryRow.measured_at,
    TelemetryRow.voltage_v,
    TelemetryRow.current_a,
    TelemetryRow.active_power_w,
    TelemetryRow.energy_kwh,
    TelemetryRow.power_factor,
    TelemetryRow.frequency_hz,
)


def _valid_raw(db: Session, device_id: str, start: datetime, end: datetime):
    return db.execute(
        select(*_RAW_COLS)
        .where(
            TelemetryRow.device_id == device_id,
            TelemetryRow.validity == "valid",
            TelemetryRow.measured_at >= start,
            TelemetryRow.measured_at < end,
        )
        .order_by(TelemetryRow.measured_at, TelemetryRow.id)
    ).all()


def _previous_reading(db: Session, device_id: str, before: datetime) -> Optional[Tuple[datetime, float]]:
    """Last known (time, register) before `before`: raw first, then rollups."""
    row = db.execute(
        select(TelemetryRow.measured_at, TelemetryRow.energy_kwh)
        .where(
            TelemetryRow.device_id == device_id,
            TelemetryRow.validity == "valid",
            TelemetryRow.measured_at < before,
        )
        .order_by(TelemetryRow.measured_at.desc(), TelemetryRow.id.desc())
        .limit(1)
    ).first()
    if row and row[1] is not None:
        return row[0], row[1]
    roll = db.execute(
        select(TelemetryHourly.last_measured_at, TelemetryHourly.energy_register_end)
        .where(TelemetryHourly.device_id == device_id, TelemetryHourly.bucket_start < before)
        .order_by(TelemetryHourly.bucket_start.desc())
        .limit(1)
    ).first()
    if roll and roll[0] is not None and roll[1] is not None:
        return roll[0], roll[1]
    return None


def _accumulate(
    rows: Iterable, prev: Optional[Tuple[datetime, float]], accs: Dict[datetime, _Acc]
) -> Optional[Tuple[datetime, float]]:
    for t, v, a, p, e, pf, f in rows:
        if e is None:
            continue
        delta = 0.0
        if prev is not None:
            delta = register_delta(prev[1], e, (t - prev[0]).total_seconds())
        b = local_hour_floor(t)
        acc = accs.get(b)
        if acc is None:
            acc = accs[b] = _Acc(b)
        acc.add(t, v, a, p, e, pf, f, delta)
        prev = (t, e)
    return prev


def raw_hourly_stats(db: Session, device_id: str, start: datetime, end: datetime) -> Dict[datetime, HourStats]:
    """Compute per-local-hour stats directly from raw telemetry in [start, end)."""
    accs: Dict[datetime, _Acc] = {}
    prev = _previous_reading(db, device_id, start)
    chunk = start
    while chunk < end:  # day-sized chunks keep memory bounded
        chunk_end = min(chunk + timedelta(days=1), end)
        prev = _accumulate(_valid_raw(db, device_id, chunk, chunk_end), prev, accs)
        chunk = chunk_end
    return {b: acc.stats() for b, acc in accs.items()}


def last_rolled_bucket(db: Session, device_id: str) -> Optional[datetime]:
    return db.scalar(
        select(func.max(TelemetryHourly.bucket_start)).where(TelemetryHourly.device_id == device_id)
    )


def _row_to_stats(r: TelemetryHourly) -> HourStats:
    return HourStats(
        bucket_start=r.bucket_start, samples=r.sample_count, energy_kwh=r.energy_kwh,
        energy_register_end=r.energy_register_end, last_measured_at=r.last_measured_at,
        voltage_avg=r.voltage_avg, voltage_min=r.voltage_min, voltage_max=r.voltage_max,
        current_avg=r.current_avg, power_avg=r.power_avg, power_max=r.power_max,
        power_factor_avg=r.power_factor_avg, frequency_avg=r.frequency_avg,
    )


def hourly_stats(db: Session, device_id: str, start: datetime, end: datetime) -> Dict[datetime, HourStats]:
    """
    Per-local-hour stats for [start, end), merging rollups (completed, rolled
    hours) with raw telemetry (recent hours not yet rolled up).
    Only hours that contain at least one valid reading are returned.
    """
    start = local_hour_floor(start)
    out: Dict[datetime, HourStats] = {}
    last = last_rolled_bucket(db, device_id)

    if last is not None and last >= start:
        for r in db.scalars(
            select(TelemetryHourly).where(
                TelemetryHourly.device_id == device_id,
                TelemetryHourly.bucket_start >= start,
                TelemetryHourly.bucket_start < end,
            )
        ).all():
            out[r.bucket_start] = _row_to_stats(r)

    tail_start = start if last is None or last < start else last + HOUR
    if tail_start < end:
        out.update(raw_hourly_stats(db, device_id, tail_start, end))
    return out


# ── Rollup job ─────────────────────────────────────────────────────────────────

def rollup_completed_hours(db: Session, device_id: str, now: Optional[datetime] = None) -> int:
    """Condense every completed local hour not yet rolled up. Returns rows written."""
    now = now or utcnow()
    end = local_hour_floor(now)  # hours strictly before the current one are complete
    last = last_rolled_bucket(db, device_id)
    if last is not None:
        start = last + HOUR
    else:
        first = db.scalar(
            select(func.min(TelemetryRow.measured_at)).where(
                TelemetryRow.device_id == device_id, TelemetryRow.validity == "valid"
            )
        )
        if first is None:
            return 0
        start = local_hour_floor(first)
    if start >= end:
        return 0

    stats = raw_hourly_stats(db, device_id, start, end)
    for s in sorted(stats.values(), key=lambda x: x.bucket_start):
        db.add(TelemetryHourly(
            device_id=device_id, bucket_start=s.bucket_start, sample_count=s.samples,
            energy_kwh=s.energy_kwh, energy_register_end=s.energy_register_end,
            last_measured_at=s.last_measured_at, voltage_avg=s.voltage_avg,
            voltage_min=s.voltage_min, voltage_max=s.voltage_max, current_avg=s.current_avg,
            power_avg=s.power_avg, power_max=s.power_max,
            power_factor_avg=s.power_factor_avg, frequency_avg=s.frequency_avg,
        ))
    if stats:
        db.commit()
        logger.info("Rolled up %d hour(s) of telemetry for device %s", len(stats), device_id)
    return len(stats)


# ── Retention job ──────────────────────────────────────────────────────────────

def prune_old_data(db: Session, device_id: str, now: Optional[datetime] = None) -> Dict[str, int]:
    """
    Delete raw telemetry older than the retention window — but only hours that
    are already rolled up — plus old status events and finished commands.
    The most recent valid reading is always kept so /telemetry/latest can
    still report the last known values (marked stale).
    """
    now = now or utcnow()
    counts = {"telemetry": 0, "status_events": 0, "relay_commands": 0}

    cutoff = now - timedelta(days=settings.raw_telemetry_retention_days)
    last = last_rolled_bucket(db, device_id)
    if last is not None:
        cutoff = min(cutoff, last + HOUR)
        keep_id = db.scalar(
            select(TelemetryRow.id)
            .where(TelemetryRow.device_id == device_id, TelemetryRow.validity == "valid")
            .order_by(TelemetryRow.measured_at.desc(), TelemetryRow.id.desc())
            .limit(1)
        )
        stmt = delete(TelemetryRow).where(
            TelemetryRow.device_id == device_id, TelemetryRow.measured_at < cutoff
        )
        if keep_id is not None:
            stmt = stmt.where(TelemetryRow.id != keep_id)
        counts["telemetry"] = db.execute(stmt).rowcount or 0

    event_cutoff = now - timedelta(days=settings.event_retention_days)
    counts["status_events"] = db.execute(
        delete(DeviceStatusEvent).where(DeviceStatusEvent.recorded_at < event_cutoff)
    ).rowcount or 0
    counts["relay_commands"] = db.execute(
        delete(RelayCommand).where(
            RelayCommand.created_at < event_cutoff,
            RelayCommand.status.not_in(OPEN_COMMAND_STATUSES),
        )
    ).rowcount or 0
    db.commit()

    if any(counts.values()):
        logger.info("Retention pruned: %s", counts)
        incremental_vacuum()
    return counts


def run_maintenance(db: Session, device_id: str) -> Dict[str, int]:
    rolled = rollup_completed_hours(db, device_id)
    pruned = prune_old_data(db, device_id)
    return {"rolled_hours": rolled, **pruned}


def stats_by_local_hour_of_day(stats: Dict[datetime, HourStats]) -> Dict[int, List[HourStats]]:
    from app.utils.timestamps import to_local
    by_hour: Dict[int, List[HourStats]] = {}
    for b, s in stats.items():
        by_hour.setdefault(to_local(b).hour, []).append(s)
    return by_hour
