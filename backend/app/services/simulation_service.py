"""
SHEM Backend — Appliance simulation engine

The hardware prototype has ONE relay + PZEM meter, so only one appliance can
be measured for real. Every appliance that is NOT linked to a relay runs as a
realistic simulated device:

  * Power follows a type-specific profile (fridge / AC compressor cycles with
    start-up inrush, washing-machine and dishwasher programmes that finish and
    switch themselves off, geyser thermostat, TV content fluctuation, fan
    drift, resistive loads scaling with supply voltage …) × quantity.
  * On/off follows a daily routine built from the appliance's "hours used per
    day" (lights in the evening, fans/AC at night, geyser in the morning,
    fridge always on …) unless `sim_auto` is off.
  * The app's on/off switch is a manual override that lasts until the next
    routine change (or indefinitely when the routine is disabled).
  * Energy is integrated every tick (P × Δt) and stored per appliance per
    local hour in `sim_energy_hourly`, so insights treat it like metered energy.
  * Live power is pushed on the WebSocket as `sim_update` every tick.

Nothing is back-filled: simulated history starts when the appliance is added
and only accrues while the backend is running.
"""

from __future__ import annotations

import logging
import math
import random
import threading
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import Appliance, SimEnergyHourly, TelemetryRow
from app.utils.timestamps import DAY, local_day_start, local_hour_floor, to_iso, to_local, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

TICK_SECONDS = 2.0
FLUSH_SECONDS = 30.0
MAX_TICK_GAP_S = 10.0          # never integrate across a longer pause (sleep / restart)
NOMINAL_V = 230.0


# ═══════════════════════════════════════════════════════════════
# PROFILES
# ═══════════════════════════════════════════════════════════════

ICON_PROFILE = {
    "bulb": "steady", "tube": "tube", "cfl": "tube", "lamp": "steady",
    "fan": "fan", "ac": "ac", "fridge": "fridge", "tv": "tv",
    "heater": "heater", "pot": "cooker", "washer": "washer", "microwave": "microwave",
    "mixer": "mixer", "purifier": "purifier", "dishwasher": "dishwasher",
}
CATEGORY_PROFILE = {
    "lighting": "steady", "fans": "fan", "cooling": "ac", "refrigerator": "fridge",
    "entertainment": "tv", "heating": "heater", "washing machine": "washer",
    "water purifier": "purifier", "kitchen": "microwave",
}

# Programme appliances run a fixed cycle then switch themselves off.
PROGRAMME_SECONDS = {"washer": 60 * 60, "dishwasher": 90 * 60, "microwave": 5 * 60, "mixer": 3 * 60}

# Daily-routine windows: (start hour, max length h). Hours are filled in order.
ROUTINE_WINDOWS: Dict[str, List[Tuple[float, float]]] = {
    "steady": [(18.5, 5.0), (5.5, 1.5), (12.0, 6.0), (0.0, 5.5)],
    "tube": [(18.5, 5.0), (5.5, 1.5), (12.0, 6.0), (0.0, 5.5)],
    "fan": [(22.0, 8.0), (13.0, 4.0), (17.0, 5.0), (6.0, 7.0)],
    "ac": [(22.5, 7.5), (13.0, 4.0), (17.0, 5.5), (6.0, 7.0)],
    "tv": [(19.0, 4.0), (8.0, 2.0), (13.0, 4.0), (15.0, 4.0)],
    "heater": [(6.5, 1.5), (19.0, 1.5), (8.0, 10.0)],
    "washer": [(9.0, 3.0), (12.0, 6.0)],
    "dishwasher": [(21.5, 2.0), (12.0, 9.0)],
    "default": [(18.0, 6.0), (8.0, 4.0), (12.0, 6.0), (0.0, 8.0)],
}
# Spread evenly across these slots instead of filling in order.
ROUTINE_SLOTS: Dict[str, List[float]] = {
    "microwave": [7.5, 13.0, 20.0], "cooker": [7.5, 13.0, 20.0], "mixer": [7.5, 13.0, 20.0],
    "purifier": [7.0, 12.0, 19.0],
}


def profile_for(icon_type: Optional[str], category: Optional[str], name: str = "") -> str:
    if icon_type and icon_type.lower() in ICON_PROFILE:
        return ICON_PROFILE[icon_type.lower()]
    cat = (category or "").lower()
    if cat in CATEGORY_PROFILE:
        return CATEGORY_PROFILE[cat]
    n = name.lower()
    for key, prof in (("fridge", "fridge"), ("refrigerator", "fridge"), ("ac", "ac"), ("fan", "fan"),
                      ("geyser", "heater"), ("heater", "heater"), ("tv", "tv"), ("wash", "washer"),
                      ("light", "steady"), ("bulb", "steady")):
        if key in n.split() or (len(key) > 3 and key in n):
            return prof
    return "default"


def _seed(appliance_id: str) -> int:
    return zlib.crc32(appliance_id.encode("utf-8"))


def _wave(t: float, period: float, phase: float) -> float:
    return math.sin(2 * math.pi * (t / period) + phase)


def unit_power(profile: str, rated: float, name: str, on_s: float, abs_s: float, phase: float,
               rng: random.Random, voltage: float) -> float:
    """
    Instantaneous power (W) of ONE unit that has been ON for `on_s` seconds.
    `abs_s` is a monotonic clock for always-cycling appliances (fridge), and
    `phase` a per-appliance offset so identical appliances don't move in lockstep.
    """
    if rated <= 0:
        return 0.0
    noise = lambda pct: 1.0 + rng.gauss(0.0, pct)  # noqa: E731
    v2 = (voltage / NOMINAL_V) ** 2

    if profile == "steady":                      # LED driver: constant power
        return rated * noise(0.006)
    if profile == "tube":                        # ballast warm-up then steady
        warm = 1.12 if on_s < 45 else 1.0
        return rated * warm * noise(0.01)
    if profile == "fan":
        return rated * (0.93 + 0.04 * _wave(on_s, 420, phase)) * noise(0.012)
    if profile == "tv":                          # brightness follows content
        return rated * (0.78 + 0.12 * _wave(on_s, 37, phase) + 0.06 * _wave(on_s, 11, phase * 2)) * noise(0.03)
    if profile == "ac":
        if on_s < 4:                             # compressor inrush
            return rated * 2.4 * noise(0.05)
        if "inverter" in name.lower():           # pull-down, then modulate
            if on_s < 600:
                return rated * (1.05 + 0.03 * _wave(on_s, 90, phase)) * noise(0.02)
            return rated * (0.58 + 0.12 * _wave(on_s, 900, phase)) * noise(0.025)
        cycle = (on_s + phase * 300) % 1800      # 30 min: ~21 min compressor, ~9 min fan only
        if cycle < 1260:
            return rated * (0.95 + 0.04 * _wave(on_s, 300, phase)) * noise(0.02)
        return rated * 0.07 * noise(0.05)
    if profile == "fridge":                      # always-cycling compressor, ~40 % duty
        cycle = (abs_s + phase * 1000) % 2700
        if cycle < 3:
            return rated * 3.0 * noise(0.05)     # start-up surge
        if cycle < 1080:
            return rated * (0.92 + 0.06 * (cycle / 1080)) * noise(0.02)
        return 2.0 * noise(0.1)                  # electronics / light only
    if profile == "heater":                      # resistive, thermostat after heat-up
        if on_s < 25 * 60 or (on_s - 25 * 60) % 900 < 120:
            return rated * v2 * noise(0.004)
        return 0.0
    if profile == "cooker":                      # cook at full power, then keep warm
        return rated * v2 * noise(0.005) if on_s < 25 * 60 else rated * 0.06 * noise(0.05)
    if profile == "microwave":
        return rated * (1.0 if on_s < 2 else 0.97) * noise(0.015)
    if profile == "mixer":                       # bursts of blending
        return rated * (0.85 if int(on_s) % 20 < 14 else 0.25) * noise(0.06)
    if profile == "purifier":                    # RO pump fills tank, then standby
        return rated * noise(0.02) if on_s % 3600 < 25 * 60 else 4.0 * noise(0.1)
    if profile == "washer":                      # 60 min programme
        m = on_s / 60
        if m < 5:
            return 12.0 * noise(0.05)                                    # filling
        if m < 15:
            return rated * 0.9 * v2 * noise(0.01)                        # water heating
        if m < 35:
            return rated * (0.35 if int(on_s) % 20 < 15 else 0.03) * noise(0.05)  # agitation
        if m < 45:
            return rated * (0.25 if int(on_s) % 20 < 15 else 0.03) * noise(0.05)  # rinse
        if m < 55:
            return rated * min(1.0, 0.4 + (m - 45) * 0.08) * noise(0.03)  # spin ramp
        return 15.0 * noise(0.05)                                        # drain
    if profile == "dishwasher":                  # 90 min programme
        m = on_s / 60
        if m < 5 or 40 <= m < 45 or 80 <= m:
            return 25.0 * noise(0.05)                                    # fill / drain / dry fan
        if m < 25 or 60 <= m < 75:
            return rated * v2 * noise(0.006)                             # heating
        return rated * 0.08 * noise(0.04)                                # wash pump
    return rated * (0.9 + 0.05 * _wave(on_s, 300, phase)) * noise(0.02)


# ═══════════════════════════════════════════════════════════════
# DAILY ROUTINE
# ═══════════════════════════════════════════════════════════════

def routine_intervals(profile: str, daily_hours: float) -> List[Tuple[int, int]]:
    """Local minute-of-day intervals [start, end) when the routine has the appliance ON (may wrap midnight)."""
    hours = max(0.0, min(24.0, daily_hours or 0.0))
    if hours <= 0:
        return []
    if profile == "fridge" or hours >= 23.9:
        return [(0, 1440)]
    if profile in PROGRAMME_SECONDS:             # make sure the window fits one whole programme
        hours = max(hours, PROGRAMME_SECONDS[profile] / 3600.0)

    out: List[Tuple[int, int]] = []
    if profile in ROUTINE_SLOTS:
        slots = ROUTINE_SLOTS[profile]
        per = hours / len(slots)
        for h in slots:
            out.append((int(h * 60), int(h * 60 + per * 60)))
    else:
        left = hours
        for start, max_len in ROUTINE_WINDOWS.get(profile, ROUTINE_WINDOWS["default"]):
            if left <= 0:
                break
            length = min(left, max_len)
            out.append((int(start * 60), int((start + length) * 60)))
            left -= length
    return [(s % 1440, e - (s - s % 1440)) for s, e in out if e > s]


def _in_intervals(minute: float, intervals: List[Tuple[int, int]]) -> bool:
    for s, e in intervals:
        if s <= minute < e or (e > 1440 and minute < e - 1440):
            return True
    return False


def scheduled_on(intervals: List[Tuple[int, int]], at: datetime) -> bool:
    loc = to_local(at)
    return _in_intervals(loc.hour * 60 + loc.minute + loc.second / 60.0, intervals)


def next_routine_change(intervals: List[Tuple[int, int]], at: datetime) -> Optional[datetime]:
    """First instant after `at` when the routine state flips (minute resolution, ≤ 48 h ahead)."""
    if not intervals or intervals == [(0, 1440)]:
        return None
    cur = scheduled_on(intervals, at)
    t = at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(48 * 60):
        if scheduled_on(intervals, t) != cur:
            return t
        t += timedelta(minutes=1)
    return None


def describe_routine(intervals: List[Tuple[int, int]]) -> Optional[str]:
    if not intervals:
        return None
    if intervals == [(0, 1440)]:
        return "Always on (cycles automatically)"

    def fmt(m: int) -> str:
        m %= 1440
        h, mm = divmod(m, 60)
        suffix = "am" if h < 12 else "pm"
        return f"{h % 12 or 12}{':%02d' % mm if mm else ''}{suffix}"
    return ", ".join(f"{fmt(s)}–{fmt(e)}" for s, e in intervals)


# ═══════════════════════════════════════════════════════════════
# ENGINE
# ═══════════════════════════════════════════════════════════════

@dataclass
class _Bucket:
    start: datetime
    energy_kwh: float = 0.0
    on_seconds: float = 0.0
    power_max: float = 0.0
    samples: int = 0


@dataclass
class _Runtime:
    appliance_id: str
    rng: random.Random
    phase: float
    on: bool = False
    on_since: Optional[datetime] = None
    power_w: float = 0.0
    name: str = ""
    icon_type: Optional[str] = None
    category: Optional[str] = None
    pending: Dict[datetime, _Bucket] = field(default_factory=dict)   # not yet flushed
    today_flushed_kwh: float = 0.0


class SimulationEngine:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rt: Dict[str, _Runtime] = {}
        self._last_tick: Optional[datetime] = None
        self._last_flush: Optional[datetime] = None
        self._today: Optional[datetime] = None
        self._today_totals: Dict[str, float] = {}
        self._voltage = NOMINAL_V
        self._last_payload: Dict[str, Any] = {"appliances": [], "totalPowerW": 0.0, "serverTime": None}
        self._mono0 = utcnow()

    # ── helpers ───────────────────────────────────────────────────────────────
    def _runtime(self, a: Appliance) -> _Runtime:
        rt = self._rt.get(a.id)
        if rt is None:
            seed = _seed(a.id)
            rt = self._rt[a.id] = _Runtime(appliance_id=a.id, rng=random.Random(seed),
                                           phase=(seed % 1000) / 1000.0 * 2 * math.pi,
                                           today_flushed_kwh=self._today_totals.get(a.id, 0.0))
        rt.name, rt.icon_type, rt.category = a.name, a.icon_type, a.category
        return rt

    def _supply_voltage(self, db: Session, now: datetime) -> float:
        row = db.execute(
            select(TelemetryRow.voltage_v, TelemetryRow.measured_at)
            .where(TelemetryRow.device_id == settings.device_id, TelemetryRow.validity == "valid")
            .order_by(TelemetryRow.measured_at.desc()).limit(1)
        ).first()
        if row and row[0] and (now - row[1]).total_seconds() < 60:
            self._voltage = float(row[0])
        else:  # no fresh meter reading: a gently wandering 230 V mains
            self._voltage += (NOMINAL_V - self._voltage) * 0.05 + random.gauss(0, 0.4)
        return self._voltage

    @staticmethod
    def desired_state(a: Appliance, intervals: List[Tuple[int, int]], now: datetime) -> Tuple[bool, str]:
        """(on?, mode) where mode is 'manual' | 'auto' | 'off'."""
        if a.sim_manual_state and (a.sim_override_until is None or a.sim_override_until > now):
            return a.sim_manual_state == "ON", "manual"
        if a.sim_auto and intervals:
            return scheduled_on(intervals, now), "auto"
        return False, "off"

    def _load_today(self, db: Session, now: datetime) -> None:
        day0 = local_day_start(now)
        if self._today == day0:
            return
        self._today = day0
        totals: Dict[str, float] = {}
        for aid, kwh in db.execute(
            select(SimEnergyHourly.appliance_id, SimEnergyHourly.energy_kwh)
            .where(SimEnergyHourly.bucket_start >= day0)
        ).all():
            totals[aid] = totals.get(aid, 0.0) + (kwh or 0.0)
        for rt in self._rt.values():
            rt.today_flushed_kwh = totals.get(rt.appliance_id, 0.0)
            # unflushed energy from before midnight belongs to yesterday's buckets: keep it pending
        self._today_totals = totals

    # ── tick ──────────────────────────────────────────────────────────────────
    def tick(self, db: Session, now: Optional[datetime] = None) -> Dict[str, Any]:
        with self._lock:
            now = now or utcnow()
            dt = 0.0 if self._last_tick is None else (now - self._last_tick).total_seconds()
            dt = max(0.0, min(dt, MAX_TICK_GAP_S))
            self._last_tick = now
            self._load_today(db, now)
            voltage = self._supply_voltage(db, now)
            abs_s = (now - self._mono0).total_seconds()

            appliances = db.scalars(select(Appliance).where(Appliance.relay_channel.is_(None))).all()
            seen = set()
            status_changed = False
            out: List[Dict[str, Any]] = []
            for a in appliances:
                seen.add(a.id)
                rt = self._runtime(a)
                profile = profile_for(a.icon_type, a.category, a.name)
                intervals = routine_intervals(profile, a.daily_hours)
                on, mode = self.desired_state(a, intervals, now)

                if on and not rt.on:
                    rt.on, rt.on_since = True, now
                elif not on and rt.on:
                    rt.on, rt.on_since = False, None

                # Programme appliances finish and switch themselves off.
                prog = PROGRAMME_SECONDS.get(profile)
                if rt.on and prog and rt.on_since and (now - rt.on_since).total_seconds() >= prog:
                    rt.on, rt.on_since = False, None
                    a.sim_manual_state = "OFF"
                    a.sim_override_until = next_routine_change(intervals, now) if a.sim_auto and intervals else None
                    mode = "manual"
                    status_changed = True
                    logger.info("Simulated %s finished its programme and switched off", a.name)

                if rt.on:
                    on_s = (now - rt.on_since).total_seconds() if rt.on_since else 0.0
                    p = unit_power(profile, a.rated_watts or 0.0, a.name, on_s, abs_s, rt.phase, rt.rng, voltage)
                    rt.power_w = max(0.0, p) * max(1, a.quantity)
                else:
                    rt.power_w = 0.0

                new_status = "on" if rt.on else "off"
                if a.status != new_status:
                    a.status = new_status
                    status_changed = True

                if dt > 0:
                    b0 = local_hour_floor(now)
                    bucket = rt.pending.get(b0) or rt.pending.setdefault(b0, _Bucket(b0))
                    bucket.energy_kwh += rt.power_w * dt / 3_600_000.0
                    bucket.on_seconds += dt if rt.on else 0.0
                    bucket.power_max = max(bucket.power_max, rt.power_w)
                    bucket.samples += 1

                today_kwh = rt.today_flushed_kwh + sum(
                    b.energy_kwh for b in rt.pending.values() if b.start >= self._today)
                change = next_routine_change(intervals, now) if mode == "auto" else None
                out.append({
                    "applianceId": a.id, "name": a.name, "iconType": a.icon_type, "roomId": a.room_id,
                    "state": "ON" if rt.on else "OFF", "powerW": round(rt.power_w, 1),
                    "mode": mode, "simAuto": bool(a.sim_auto),
                    "overrideUntil": to_iso(a.sim_override_until) if mode == "manual" else None,
                    "nextChangeAt": to_iso(change) if change else None,
                    "routine": describe_routine(intervals),
                    "todayKWh": round(today_kwh, 4),
                    "ratedWatts": a.rated_watts, "quantity": a.quantity,
                })

            # Appliances deleted or moved onto a relay: flush and forget.
            gone = [aid for aid in self._rt if aid not in seen]
            if gone:
                self._flush(db, only=gone)
                for aid in gone:
                    self._rt.pop(aid, None)

            if status_changed:
                db.commit()
            if self._last_flush is None or (now - self._last_flush).total_seconds() >= FLUSH_SECONDS \
                    or any(len(rt.pending) > 1 for rt in self._rt.values()):
                self._flush(db)
                self._last_flush = now

            self._last_payload = {
                "appliances": out,
                "totalPowerW": round(sum(x["powerW"] for x in out), 1),
                "voltageV": round(voltage, 1),
                "serverTime": to_iso(now),
            }
            return self._last_payload

    # ── persistence ───────────────────────────────────────────────────────────
    def _flush(self, db: Session, only: Optional[List[str]] = None) -> None:
        wrote = False
        for rt in list(self._rt.values()):
            if only is not None and rt.appliance_id not in only:
                continue
            for b0, b in list(rt.pending.items()):
                if b.samples == 0:
                    continue
                row = db.scalar(select(SimEnergyHourly).where(
                    SimEnergyHourly.appliance_id == rt.appliance_id, SimEnergyHourly.bucket_start == b0))
                if row is None:
                    row = SimEnergyHourly(appliance_id=rt.appliance_id, appliance_name=rt.name,
                                          icon_type=rt.icon_type, category=rt.category, bucket_start=b0,
                                          energy_kwh=0.0, on_seconds=0.0, power_max=0.0, samples=0)
                    db.add(row)
                row.appliance_name, row.icon_type, row.category = rt.name, rt.icon_type, rt.category
                row.energy_kwh = (row.energy_kwh or 0.0) + b.energy_kwh
                row.on_seconds = (row.on_seconds or 0.0) + b.on_seconds
                row.power_max = max(row.power_max or 0.0, b.power_max)
                row.samples = (row.samples or 0) + b.samples
                row.updated_at = utcnow()
                if self._today is not None and b0 >= self._today:
                    rt.today_flushed_kwh += b.energy_kwh
                wrote = True
            rt.pending.clear()
        if wrote:
            db.commit()

    def flush(self, db: Session) -> None:
        with self._lock:
            self._flush(db)

    def pending_energy(self) -> List[Tuple[str, str, Optional[str], Optional[str], datetime, float, float, float]]:
        """Unflushed (appliance_id, name, icon, category, bucket, kWh, on_s, power_max) for live-accurate insights."""
        with self._lock:
            return [(rt.appliance_id, rt.name, rt.icon_type, rt.category, b.start, b.energy_kwh, b.on_seconds,
                     b.power_max) for rt in self._rt.values() for b in rt.pending.values() if b.samples]

    # ── manual switch ─────────────────────────────────────────────────────────
    def command(self, db: Session, appliance: Appliance, state: str) -> Dict[str, Any]:
        """Apply the app's on/off switch now. Returns the fresh live payload."""
        with self._lock:
            now = utcnow()
            profile = profile_for(appliance.icon_type, appliance.category, appliance.name)
            intervals = routine_intervals(profile, appliance.daily_hours)
            appliance.sim_manual_state = state
            appliance.sim_override_until = (
                next_routine_change(intervals, now) if appliance.sim_auto and intervals else None)
            appliance.updated_at = now
            db.commit()
            return self.tick(db, now)

    def clear_override(self, db: Session, appliance: Appliance) -> None:
        appliance.sim_manual_state = None
        appliance.sim_override_until = None
        db.commit()

    @property
    def last_payload(self) -> Dict[str, Any]:
        with self._lock:
            return self._last_payload

    def reset(self) -> None:  # tests
        with self._lock:
            self.__init__()


simulator = SimulationEngine()


# ═══════════════════════════════════════════════════════════════
# BACKGROUND LOOP
# ═══════════════════════════════════════════════════════════════

def _tick_once() -> Dict[str, Any]:
    from app.database import SessionLocal
    with SessionLocal() as db:
        return simulator.tick(db)


def flush_on_shutdown() -> None:
    from app.database import SessionLocal
    try:
        with SessionLocal() as db:
            simulator.flush(db)
    except Exception:  # pragma: no cover
        logger.exception("Could not flush simulated energy on shutdown")


async def simulation_loop() -> None:
    import asyncio

    from app.services.broadcaster import broadcaster
    while True:
        try:
            payload = await asyncio.to_thread(_tick_once)
            await broadcaster.broadcast("sim_update", payload)
        except asyncio.CancelledError:
            await asyncio.to_thread(flush_on_shutdown)
            raise
        except Exception:
            logger.exception("Simulation tick failed")
        await asyncio.sleep(TICK_SECONDS)
