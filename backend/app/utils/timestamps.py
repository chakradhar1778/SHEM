"""
SHEM Backend — Timestamp Utilities
All timestamps are stored and compared in UTC. The configured local timezone
(settings.timezone) is used only for calendar boundaries (today, weeks,
months) and hour-of-day buckets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional
from zoneinfo import ZoneInfo

UTC = timezone.utc


def utcnow() -> datetime:
    """Current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalise to an aware UTC datetime. Naive values are assumed to be UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_iso(dt: Optional[datetime]) -> Optional[str]:
    """Format as 'YYYY-MM-DDTHH:MM:SSZ' (UTC)."""
    dt = as_utc(dt)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def utcnow_iso() -> str:
    return to_iso(utcnow())  # type: ignore[return-value]


def parse_iso(value: str) -> datetime:
    """
    Parse an ISO 8601 string into an aware UTC datetime.
    Offsets other than UTC are converted to UTC.
    Raises ValueError for empty or malformed input.
    """
    if not value or not isinstance(value, str):
        raise ValueError("Timestamp string is empty")
    normalised = value.strip().replace("Z", "+00:00").replace("z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalised)
    except ValueError as exc:
        raise ValueError(f"Cannot parse timestamp '{value}': {exc}") from exc
    return as_utc(dt)  # type: ignore[return-value]


def seconds_since(dt: datetime) -> float:
    return max(0.0, (utcnow() - as_utc(dt)).total_seconds())  # type: ignore[operator]


def is_stale(dt: Optional[datetime], threshold_seconds: float) -> bool:
    if dt is None:
        return True
    return seconds_since(dt) > threshold_seconds


# ── Local-calendar helpers ─────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def local_tz() -> ZoneInfo:
    from app.config import get_settings
    return ZoneInfo(get_settings().timezone)


def to_local(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(local_tz())  # type: ignore[union-attr]


def from_local(local_dt: datetime) -> datetime:
    """Interpret a naive/aware local wall-clock datetime and return UTC."""
    if local_dt.tzinfo is None:
        local_dt = local_dt.replace(tzinfo=local_tz())
    return local_dt.astimezone(UTC)


def local_hour_floor(dt: datetime) -> datetime:
    """UTC datetime of the start of the *local* clock hour containing dt."""
    loc = to_local(dt).replace(minute=0, second=0, microsecond=0)
    return loc.astimezone(UTC)


def local_day_start(dt: datetime) -> datetime:
    """UTC datetime of local midnight for the local day containing dt."""
    loc = to_local(dt).replace(hour=0, minute=0, second=0, microsecond=0)
    return loc.astimezone(UTC)


def local_month_start(dt: datetime) -> datetime:
    loc = to_local(dt).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return loc.astimezone(UTC)


def add_local_months(month_start_utc: datetime, months: int) -> datetime:
    """Shift a UTC instant that is a local month start by N local months."""
    loc = to_local(month_start_utc)
    total = loc.year * 12 + (loc.month - 1) + months
    y, m = divmod(total, 12)
    return from_local(datetime(y, m + 1, 1))


def hour_label(hour: int) -> str:
    """0 → '12am', 13 → '1pm'."""
    suffix = "am" if hour < 12 else "pm"
    h = hour % 12 or 12
    return f"{h}{suffix}"


HOUR = timedelta(hours=1)
DAY = timedelta(days=1)
