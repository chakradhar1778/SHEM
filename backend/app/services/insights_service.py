"""
SHEM Backend — Insights & Analytics Service

Data-honesty rules (build plan, hard rules):
  * Energy totals, trends, hourly points and peaks come ONLY from measured
    PZEM register deltas (energy_service.hourly_stats). Buckets without
    readings are reported as usage 0 with measured=false — never filled in.
  * Appliance figures (rated W × daily hours) are returned separately and
    always flagged as estimates.
  * Costs are energy × configured tariff and labelled as estimates.
  * Recommendations fire only when the underlying data supports them, and
    each carries the evidence that triggered it.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import Appliance, ElectricityBill, EnergyTarget, TelemetryRow
from app.models.schemas import (
    ApplianceUsage,
    BillComparison,
    DailyTotal,
    DailyTotalsResponse,
    PeakSummary,
    PeriodTopAppliance,
    CategoryShare,
    DayPeriodBreakdown,
    EnergyRecommendation,
    HourlyPoint,
    InsightCard,
    InsightsKeyInsight,
    InsightsResponse,
    InsightsTrendPoint,
    PeriodComparison,
    TodayInsightsResponse,
)
from app.services.energy_service import HourStats, hourly_stats
from app.utils.timestamps import (
    DAY,
    HOUR,
    add_local_months,
    from_local,
    hour_label,
    local_day_start,
    local_hour_floor,
    local_month_start,
    to_local,
    utcnow,
)

logger = logging.getLogger(__name__)
settings = get_settings()

CATEGORY_NAMES = {
    "cooling": "Air Conditioning",
    "lighting": "Lights",
    "fans": "Fans",
    "refrigerator": "Refrigerator",
    "kitchen": "Kitchen Appliances",
    "entertainment": "Entertainment",
    "heating": "Water Heating",
    "other": "Other Devices",
}

# Recommendation thresholds
LOW_PF_THRESHOLD = 0.85
PF_MIN_LOAD_W = 50.0          # PF at near-zero load is meaningless
VOLTAGE_LOW, VOLTAGE_HIGH = 207.0, 253.0   # 230 V ± 10 %
OVERNIGHT_BASELOAD_W = 100.0
EVENING_SHARE_THRESHOLD = 0.40
MIN_SAMPLES = 30


# ── Shared lookups ─────────────────────────────────────────────────────────────

def _tariff(db: Session) -> float:
    """₹/kWh for cost estimates: the flat rate, or the blended slab rate at this cycle's projected usage."""
    from app.services.billing_service import cost_rate
    return cost_rate(db)


def _target(db: Session) -> Tuple[bool, Optional[float]]:
    t = db.get(EnergyTarget, 1)
    if t and t.is_configured and t.monthly_budget_inr > 0:
        return True, t.monthly_budget_inr
    return False, None


def _days_in_local_month(now: datetime) -> int:
    loc = to_local(now)
    return monthrange(loc.year, loc.month)[1]


def _daily_target_kwh(db: Session, now: datetime, tariff: float) -> Optional[float]:
    """Budget → kWh per billing cycle under the configured tariff (slabs, fixed charge …) → per day."""
    from app.services.billing_service import budget_kwh, cycle_days, load_tariff
    configured, budget = _target(db)
    if not configured or not budget:
        return None
    return budget_kwh(db, budget) / cycle_days(now, load_tariff(db))


def _rate_disclosure(tariff: float, db: Optional[Session] = None) -> str:
    if db is not None:
        from app.services.billing_service import load_tariff
        if not load_tariff(db).is_plain_flat:
            return (f"Estimated cost uses your tariff settings: ₹{tariff:.2f}/kWh blended (slabs, fuel adjustment "
                    "and duty at this cycle's projected usage). Fixed charges are in the projected bill; this is "
                    "not the utility's bill.")
    return (f"Estimated cost uses your configured tariff of ₹{tariff:.2f}/kWh; "
            "it is not a utility billing calculation.")


def _methodology() -> str:
    return (
        "Energy is the difference of the PZEM-004T cumulative kWh register between consecutive "
        f"readings (reset-safe), grouped by local hour ({settings.timezone}). Periods without "
        "readings show 0 and are marked measured=false; energy used during a gap is counted when "
        "readings resume. Appliances without a relay run as realistic simulated devices; their energy is "
        "integrated from simulated power every 2 s and carries a 'Simulated' tag. Category estimates "
        "(rated W × daily hours) are used only when no metered or simulated energy exists."
    )


def _appliance_estimates(db: Session, days: float) -> List[CategoryShare]:
    totals: Dict[str, float] = {}
    for a in db.scalars(select(Appliance)).all():
        if not a.rated_watts or not a.daily_hours:
            continue  # no rating / no usage → no estimate (never default a wattage)
        cat = (a.category or "other").lower()
        totals[cat] = totals.get(cat, 0.0) + a.rated_watts * a.quantity * a.daily_hours * days / 1000.0
    grand = sum(totals.values())
    if grand <= 0:
        return []
    return [
        CategoryShare(
            category_id=cat, category_label=CATEGORY_NAMES.get(cat, cat.capitalize()), icon_type=cat,
            kwh=round(kwh, 2), percentage=round(kwh / grand * 100, 1),
        )
        for cat, kwh in sorted(totals.items(), key=lambda x: x[1], reverse=True)
    ]


def _gap_note(coverage_hours: float, expected_hours: float) -> Optional[str]:
    if coverage_hours == 0:
        return "No measured telemetry in this period yet."
    if coverage_hours < expected_hours * 0.9 and expected_hours - coverage_hours >= 1:
        return (f"Readings exist for {coverage_hours:.0f} of {expected_hours:.0f} hours. Energy used "
                "while the meter was not reporting is added when readings resume, so the "
                "distribution over time may be uneven.")
    return None


# ── Period windows ─────────────────────────────────────────────────────────────

@dataclass
class _Bucket:
    label: str
    start: datetime
    end: datetime


@dataclass
class _Window:
    label: str
    start: datetime
    end: datetime
    buckets: List[_Bucket]
    prev_start: datetime
    prev_end: datetime     # previous period, same elapsed length


def _window(period: str, now: datetime) -> _Window:
    if period == "month":
        m0 = local_month_start(now)
        m1 = add_local_months(m0, 1)
        buckets, s, k = [], m0, 1
        while s < m1:
            e = min(s + 7 * DAY, m1)
            buckets.append(_Bucket(f"Week {k}", s, e))
            s, k = e, k + 1
        p0 = add_local_months(m0, -1)
        return _Window("This month", m0, m1, buckets, p0, min(p0 + (now - m0), m0))
    if period == "year":
        y = to_local(now).year
        y0 = from_local(datetime(y, 1, 1))
        buckets = []
        for i in range(12):
            s = add_local_months(y0, i)
            buckets.append(_Bucket(to_local(s).strftime("%b"), s, add_local_months(y0, i + 1)))
        p0 = from_local(datetime(y - 1, 1, 1))
        return _Window("This year", y0, buckets[-1].end, buckets, p0, min(p0 + (now - y0), y0))
    # week: last 7 local days including today
    d0 = local_day_start(now) - 6 * DAY
    buckets = [_Bucket(to_local(d0 + i * DAY).strftime("%a"), d0 + i * DAY, d0 + (i + 1) * DAY) for i in range(7)]
    return _Window("Last 7 days", d0, d0 + 7 * DAY, buckets, d0 - 7 * DAY, now - 7 * DAY)


# ── Metered + simulated energy per hour ───────────────────────────────────────

METERED_CIRCUIT_ID = "metered-circuit"


@dataclass
class _AppMeta:
    key: str
    name: str
    icon_type: Optional[str]
    category: Optional[str]
    room_name: Optional[str]
    source: str                      # metered | simulated


@dataclass
class _HourUse:
    metered: float = 0.0
    simulated: float = 0.0
    by_app: Dict[str, float] = field(default_factory=dict)
    on_s: Dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.metered + self.simulated


@dataclass
class _Usage:
    hours: Dict[datetime, _HourUse]
    meta: Dict[str, _AppMeta]
    real: Dict[datetime, HourStats]

    def total(self) -> float:
        return sum(h.total for h in self.hours.values())

    def metered(self) -> float:
        return sum(h.metered for h in self.hours.values())

    def simulated(self) -> float:
        return sum(h.simulated for h in self.hours.values())


def _metered_identity(db: Session, rooms: Dict[str, str]) -> _AppMeta:
    """Real PZEM energy belongs to the relay circuit: the relay-linked appliance when there is exactly one."""
    linked = db.scalars(select(Appliance).where(Appliance.relay_channel.is_not(None))).all()
    if len(linked) == 1:
        a = linked[0]
        return _AppMeta(a.id, a.name, a.icon_type, a.category, rooms.get(a.room_id or ""), "metered")
    return _AppMeta(METERED_CIRCUIT_ID, "Metered circuit", "bolt", None, None, "metered")


def _usage(db: Session, device_id: str, start: datetime, end: datetime) -> _Usage:
    """Per-local-hour energy in [start, end): PZEM register deltas + every simulated appliance."""
    from app.models.db_models import Room, SimEnergyHourly
    from app.services.simulation_service import simulator

    rooms = {r.id: r.name for r in db.scalars(select(Room)).all()}
    current = {a.id: a for a in db.scalars(select(Appliance)).all()}
    real = hourly_stats(db, device_id, start, end)
    hours: Dict[datetime, _HourUse] = {}
    meta: Dict[str, _AppMeta] = {}

    if real:
        m = _metered_identity(db, rooms)
        meta[m.key] = m
        for b, st in real.items():
            h = hours.setdefault(b, _HourUse())
            h.metered += st.energy_kwh
            h.by_app[m.key] = h.by_app.get(m.key, 0.0) + st.energy_kwh

    h0 = local_hour_floor(start)
    rows = [(r.appliance_id, r.appliance_name, r.icon_type, r.category, r.bucket_start, r.energy_kwh or 0.0,
             r.on_seconds or 0.0)
            for r in db.scalars(select(SimEnergyHourly).where(
                SimEnergyHourly.bucket_start >= h0, SimEnergyHourly.bucket_start < end)).all()]
    rows += [(aid, name, icon, cat, b, kwh, on_s)
             for aid, name, icon, cat, b, kwh, on_s, _ in simulator.pending_energy() if h0 <= b < end]
    for aid, name, icon, cat, b, kwh, on_s in rows:
        if aid not in meta:
            a = current.get(aid)
            meta[aid] = _AppMeta(aid, a.name if a else name, (a.icon_type if a else None) or icon,
                                 (a.category if a else None) or cat,
                                 rooms.get((a.room_id if a else None) or ""), "simulated")
        h = hours.setdefault(b, _HourUse())
        h.simulated += kwh
        h.by_app[aid] = h.by_app.get(aid, 0.0) + kwh
        h.on_s[aid] = h.on_s.get(aid, 0.0) + on_s
    return _Usage(hours=hours, meta=meta, real=real)


def _appliance_usage(u: _Usage, tariff: float) -> List[ApplianceUsage]:
    totals: Dict[str, float] = {}
    on_s: Dict[str, float] = {}
    by_hour: Dict[str, Dict[int, float]] = {}
    for b, h in u.hours.items():
        hod = to_local(b).hour
        for k, v in h.by_app.items():
            totals[k] = totals.get(k, 0.0) + v
            hrs = by_hour.setdefault(k, {})
            hrs[hod] = hrs.get(hod, 0.0) + v
        for k, v in h.on_s.items():
            on_s[k] = on_s.get(k, 0.0) + v
    grand = sum(totals.values())
    out = []
    for k, kwh in sorted(totals.items(), key=lambda x: x[1], reverse=True):
        m = u.meta[k]
        hrs = by_hour.get(k, {})
        ph = max(hrs, key=hrs.get) if hrs and max(hrs.values()) > 0 else None
        out.append(ApplianceUsage(
            appliance_id=k, name=m.name, icon_type=m.icon_type, category=m.category, room_name=m.room_name,
            source=m.source, kwh=round(kwh, 4), percentage=round(kwh / grand * 100, 1) if grand > 0 else 0.0,
            cost_inr=round(kwh * tariff, 2),
            on_hours=round(on_s.get(k, 0.0) / 3600.0, 2) if m.source == "simulated" else None,
            peak_hour=ph, peak_hour_label=hour_label(ph) if ph is not None else None,
        ))
    return out


def _category_actuals(usage: List[ApplianceUsage]) -> List[CategoryShare]:
    totals: Dict[str, float] = {}
    for a in usage:
        cat = (a.category or "other").lower()
        totals[cat] = totals.get(cat, 0.0) + a.kwh
    grand = sum(totals.values())
    if grand <= 0:
        return []
    return [CategoryShare(category_id=c, category_label=CATEGORY_NAMES.get(c, c.capitalize()), icon_type=c,
                          kwh=round(k, 2), percentage=round(k / grand * 100, 1))
            for c, k in sorted(totals.items(), key=lambda x: x[1], reverse=True)]


# ── /api/insights ──────────────────────────────────────────────────────────────

def compute_insights(db: Session, period: str = "week", device_id: Optional[str] = None) -> InsightsResponse:
    device_id = device_id or settings.device_id
    now = utcnow()
    tariff = _tariff(db)
    win = _window(period, now)
    u = _usage(db, device_id, win.start, now)
    energy = {b: h.total for b, h in u.hours.items()}

    total = u.total()
    coverage = float(len(u.hours))
    expected = max((now - win.start).total_seconds() / 3600.0, 0.0)
    daily_target = _daily_target_kwh(db, now, tariff)

    points: List[InsightsTrendPoint] = []
    for b in win.buckets:
        in_b = [e for t, e in energy.items() if b.start <= t < b.end]
        points.append(InsightsTrendPoint(
            label=b.label, start=b.start,
            usage_kwh=round(sum(in_b), 3),
            target_kwh=round(daily_target * (b.end - b.start) / DAY, 2) if daily_target else None,
            measured=bool(in_b),
        ))
    measured_pts = [p for p in points if p.measured and p.usage_kwh > 0]
    peak = max(measured_pts, key=lambda p: p.usage_kwh) if measured_pts else None
    if peak:
        peak.is_peak = True

    comparison = None
    if win.prev_end > win.prev_start:
        prev = _usage(db, device_id, win.prev_start, win.prev_end)
        if prev.hours:
            prev_total = prev.total()
            comparison = PeriodComparison(
                previous_kwh=round(prev_total, 3),
                previous_coverage_hours=float(len(prev.hours)),
                percent_change=round((total - prev_total) / prev_total * 100, 1) if prev_total > 0 and energy else None,
            )

    key = _key_insight(energy, peak, comparison)
    period_days = (win.end - win.start) / DAY
    usage = _appliance_usage(u, tariff)
    actual_shares = _category_actuals(usage)

    return InsightsResponse(
        period=period, period_label=win.label, period_start=win.start, period_end=win.end,
        total_kwh=round(total, 3), total_cost_inr=round(total * tariff, 2), effective_rate_inr=tariff,
        rate_disclosure=_rate_disclosure(tariff, db), has_data=bool(energy),
        coverage_hours=coverage, expected_hours=round(expected, 1),
        data_note=_gap_note(coverage, expected), methodology_note=_methodology(),
        key_insight=key, trend_points=points,
        shifts=actual_shares or _appliance_estimates(db, period_days),
        shifts_are_estimates=not actual_shares,
        comparison=comparison, bill_comparison=_bill_comparison(db, total, coverage),
        metered_kwh=round(u.metered(), 3), simulated_kwh=round(u.simulated(), 3), appliance_usage=usage,
    )


def _key_insight(energy: Dict[datetime, float], peak: Optional[InsightsTrendPoint],
                 comparison: Optional[PeriodComparison]) -> InsightsKeyInsight:
    if not energy:
        return InsightsKeyInsight(
            title="No measured data for this period yet",
            description="Insights appear once the SHEM meter has reported readings or simulated appliances "
                        "have run. Totals are never estimated from appliance ratings.",
        )
    by_hour: Dict[int, float] = {}
    for t, e in energy.items():
        h = to_local(t).hour
        by_hour[h] = by_hour.get(h, 0.0) + e
    peak_hour = max(by_hour, key=by_hour.get)
    peak_period = f"{hour_label(peak_hour)}–{hour_label((peak_hour + 1) % 24)}"
    if peak is None:
        return InsightsKeyInsight(title="Meter reporting, negligible consumption",
                                  description="Readings were received but almost no energy was used.",
                                  peak_period=None)
    desc_ = f"{peak.usage_kwh:.2f} kWh used on {peak.label}. Usage is typically highest around {peak_period}."
    if comparison and comparison.percent_change is not None:
        word = "more" if comparison.percent_change >= 0 else "less"
        desc_ += f" That is {abs(comparison.percent_change):.0f}% {word} than the previous period."
    return InsightsKeyInsight(title=f"Highest usage: {peak.label}", description=desc_, peak_period=peak_period)


def _latest_bill(db: Session) -> Optional[ElectricityBill]:
    """Most recent bill by its billing period (its own start date, else month/year), not by entry order."""
    from app.services.billing_service import bill_period, load_tariff
    cycle_day = load_tariff(db).cycle_day
    best, best_start = None, None
    from app.services.billing_service import is_home_bill
    for bill in db.scalars(select(ElectricityBill)).all():
        if not is_home_bill(bill):          # other locations aren't this home's usage
            continue
        try:
            start, _, _ = bill_period(bill, cycle_day)
        except ValueError:
            continue
        if best_start is None or start > best_start:
            best, best_start = bill, start
    return best


def _bill_comparison(db: Session, total: float, coverage_hours: float) -> Optional[BillComparison]:
    from app.services.billing_service import bill_period, load_tariff
    bill = _latest_bill(db)
    if not bill or bill.units_consumed_kwh <= 0:
        return None
    start, end, _ = bill_period(bill, load_tariff(db).cycle_day)
    days = max((end - start).days, 1)              # the bill's real period, not a calendar month
    label = bill.billing_period or f"{start.day} {start:%b} – {(end - timedelta(days=1)).day} " \
                                   f"{(end - timedelta(days=1)):%b %Y}"
    return BillComparison(
        billing_label=label,
        bill_daily_kwh=round(bill.units_consumed_kwh / days, 2),
        bill_rate_inr=round(bill.bill_amount_inr / bill.units_consumed_kwh, 2),
        measured_daily_kwh=round(total / (coverage_hours / 24.0), 2) if coverage_hours >= 24 else None,
    )


# ── /api/insights/today (any local date) ───────────────────────────────────────

DAY_PERIODS = (
    ("night", "Night", "12am – 6am", 0, 6),
    ("morning", "Morning", "6am – 12pm", 6, 12),
    ("afternoon", "Afternoon", "12pm – 6pm", 12, 18),
    ("evening", "Evening", "6pm – 12am", 18, 24),
)


def parse_local_date(value: Optional[str], now: datetime) -> datetime:
    """'YYYY-MM-DD' (local) → UTC instant of that local midnight. Raises ValueError if malformed/future."""
    if not value:
        return local_day_start(now)
    d = datetime.strptime(value, "%Y-%m-%d")
    day0 = from_local(datetime(d.year, d.month, d.day))
    if day0 > now:
        raise ValueError("Date is in the future.")
    return day0


def _next_local_day(day0: datetime) -> datetime:
    return from_local(to_local(day0).replace(tzinfo=None) + DAY)


def _day_card(is_today: bool, has_data: bool, total: float, daily_target: Optional[float],
              peak_hour: Optional[int]) -> InsightCard:
    when = "today" if is_today else "on this day"
    if not has_data:
        if is_today:
            return InsightCard(title="Waiting for meter readings",
                               description="No metered or simulated usage has been recorded today yet.",
                               badge_text="No Data")
        return InsightCard(title="No data for this day",
                           description="Neither the meter nor any simulated appliance recorded usage this day.",
                           badge_text="No Data")
    if daily_target:
        pct = total / daily_target * 100
        over = pct > 100
        if is_today:
            title = "Over today's target" if over else "On track today"
        else:
            title = "Over the daily target" if over else "Within the daily target"
        return InsightCard(
            title=title,
            description=f"{total:.2f} kWh used {when} — {pct:.0f}% of the {daily_target:.2f} kWh daily target.",
            badge_text="Over Target" if over else "On Track",
        )
    peak_txt = f" Peak hour: {hour_label(peak_hour)}." if peak_hour is not None else ""
    return InsightCard(title="Today's usage" if is_today else "Usage this day",
                       description=f"{total:.2f} kWh used {when}.{peak_txt} Set a target to track progress.",
                       badge_text="Live Data" if is_today else "History")


def compute_today_insights(db: Session, device_id: Optional[str] = None,
                           date: Optional[str] = None) -> TodayInsightsResponse:
    device_id = device_id or settings.device_id
    now = utcnow()
    tariff = _tariff(db)
    day0 = parse_local_date(date, now)
    is_today = day0 == local_day_start(now)
    end = min(_next_local_day(day0), now)
    u = _usage(db, device_id, day0, end)

    usage: Dict[int, _HourUse] = {to_local(t).hour: h for t, h in u.hours.items()}
    total = u.total()
    daily_target = _daily_target_kwh(db, day0, tariff)
    hourly_target = round(daily_target / 24, 3) if daily_target else None

    measured_hours = [hh for hh in usage if usage[hh].total > 0]
    peak_hour = max(measured_hours, key=lambda x: usage[x].total) if measured_hours else None
    points = []
    for hh in range(24):
        h = usage.get(hh)
        points.append(HourlyPoint(
            hour=hh, time_label=hour_label(hh),
            usage_kwh=round(h.total, 4) if h else 0.0,
            metered_kwh=round(h.metered, 4) if h else 0.0,
            simulated_kwh=round(h.simulated, 4) if h else 0.0,
            target_kwh=hourly_target, is_peak=(hh == peak_hour), measured=h is not None,
        ))

    elapsed_h = (end - day0).total_seconds() / 3600.0
    periods: List[DayPeriodBreakdown] = []
    for key, label, rng, a, b in DAY_PERIODS:
        hrs = {hh: v for hh, v in usage.items() if a <= hh < b}
        kwh = sum(v.total for v in hrs.values())
        apps: Dict[str, float] = {}
        for v in hrs.values():
            for k, e in v.by_app.items():
                apps[k] = apps.get(k, 0.0) + e
        tops = [PeriodTopAppliance(appliance_id=k, name=u.meta[k].name, icon_type=u.meta[k].icon_type,
                                   source=u.meta[k].source, kwh=round(e, 4))
                for k, e in sorted(apps.items(), key=lambda x: x[1], reverse=True)[:3] if e > 0]
        p_hour = max(hrs, key=lambda x: hrs[x].total) if kwh > 0 else None
        span_h = max(0.0, min(float(b), elapsed_h) - a)
        periods.append(DayPeriodBreakdown(
            period=key, label=label, time_range=rng, kwh=round(kwh, 3),
            percentage=round(kwh / total * 100, 1) if total > 0 else 0.0,
            metered_kwh=round(sum(v.metered for v in hrs.values()), 3),
            simulated_kwh=round(sum(v.simulated for v in hrs.values()), 3),
            cost_inr=round(kwh * tariff, 2),
            avg_power_w=round(kwh * 1000 / span_h, 1) if span_h > 0 else 0.0,
            peak_hour=p_hour, peak_hour_label=hour_label(p_hour) if p_hour is not None else None,
            peak_hour_kwh=round(hrs[p_hour].total, 4) if p_hour is not None else None,
            top_appliances=tops,
        ))
    top_period = max(periods, key=lambda p: p.kwh) if total > 0 else None
    if top_period is not None:
        top_period.is_peak = True

    peak = None
    if peak_hour is not None and top_period is not None:
        ph = usage[peak_hour]
        top_app = max(ph.by_app, key=ph.by_app.get) if ph.by_app else None
        # The current hour may be in progress: average over the part that has elapsed.
        elapsed_in_hour = min(1.0, max((end - (day0 + peak_hour * HOUR)).total_seconds() / 3600.0, 1 / 60))
        peak = PeakSummary(period=top_period.period, period_label=top_period.label, hour=peak_hour,
                           hour_label=f"{hour_label(peak_hour)}–{hour_label((peak_hour + 1) % 24)}",
                           hour_kwh=round(ph.total, 4), avg_power_w=round(ph.total * 1000 / elapsed_in_hour, 1),
                           top_appliance=u.meta[top_app].name if top_app else None)

    configured, _ = _target(db)
    appliance_usage = _appliance_usage(u, tariff)
    return TodayInsightsResponse(
        date=to_local(day0).strftime("%Y-%m-%d"), is_today=is_today, has_data=bool(u.hours),
        energy_today_kwh=round(total, 3), daily_target_kwh=round(daily_target, 2) if daily_target else None,
        is_target_configured=configured, cost_today_inr=round(total * tariff, 2),
        effective_rate_inr=tariff, rate_disclosure=_rate_disclosure(tariff, db),
        hourly_points=points, day_periods=periods,
        appliance_breakdown=_category_actuals(appliance_usage) or _appliance_estimates(db, 1),
        insight_card=_day_card(is_today, bool(u.hours), total, daily_target, peak_hour),
        data_note=_gap_note(float(len(u.real)), elapsed_h) if u.real or not u.hours else None,
        methodology_note=_methodology(),
        metered_kwh=round(u.metered(), 3), simulated_kwh=round(u.simulated(), 3),
        appliance_usage=appliance_usage, peak=peak,
    )


# ── /api/insights/days ─────────────────────────────────────────────────────────

def compute_daily_totals(db: Session, days: int = 14, end_date: Optional[str] = None,
                         device_id: Optional[str] = None) -> DailyTotalsResponse:
    device_id = device_id or settings.device_id
    now = utcnow()
    tariff = _tariff(db)
    last0 = parse_local_date(end_date, now)
    today0 = local_day_start(now)
    first_local = to_local(last0).replace(tzinfo=None) - timedelta(days=days - 1)
    first0 = from_local(first_local)
    end = min(_next_local_day(last0), now)
    u = _usage(db, device_id, first0, end)

    per_day: Dict[str, List[Tuple[int, _HourUse]]] = {}
    for b, h in u.hours.items():
        loc = to_local(b)
        per_day.setdefault(loc.strftime("%Y-%m-%d"), []).append((loc.hour, h))

    out: List[DailyTotal] = []
    for i in range(days):
        d = first_local + timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        hrs = per_day.get(key, [])
        kwh = sum(h.total for _, h in hrs)
        peak_period = None
        if kwh > 0:
            sums = {p[0]: sum(h.total for hh, h in hrs if p[3] <= hh < p[4]) for p in DAY_PERIODS}
            peak_period = max(sums, key=sums.get)
        out.append(DailyTotal(
            date=key, weekday=d.strftime("%a"), day_label=f"{d.day} {d.strftime('%b')}",
            kwh=round(kwh, 3), metered_kwh=round(sum(h.metered for _, h in hrs), 3),
            simulated_kwh=round(sum(h.simulated for _, h in hrs), 3), cost_inr=round(kwh * tariff, 2),
            has_data=bool(hrs), is_today=from_local(d) == today0, peak_period=peak_period,
        ))
    with_data = [d.kwh for d in out if d.has_data and not d.is_today]
    target = _daily_target_kwh(db, now, tariff)
    return DailyTotalsResponse(days=out, average_kwh=round(sum(with_data) / len(with_data), 3) if with_data else None,
                               daily_target_kwh=round(target, 2) if target else None)


# ── /api/insights/recommendations ──────────────────────────────────────────────

_PRIORITY = {"high": 0, "medium": 1, "low": 2}


def compute_recommendations(db: Session, device_id: Optional[str] = None) -> List[EnergyRecommendation]:
    device_id = device_id or settings.device_id
    now = utcnow()
    tariff = _tariff(db)
    recs: List[EnergyRecommendation] = []

    # Last 24 h of raw readings — power quality rules
    raw = db.execute(
        select(TelemetryRow.active_power_w, TelemetryRow.power_factor, TelemetryRow.voltage_v)
        .where(TelemetryRow.device_id == device_id, TelemetryRow.validity == "valid",
               TelemetryRow.measured_at >= now - DAY)
    ).all()

    pf_vals = [pf for p, pf, _ in raw if pf is not None and p is not None and p >= PF_MIN_LOAD_W]
    if len(pf_vals) >= MIN_SAMPLES:
        avg_pf = sum(pf_vals) / len(pf_vals)
        if avg_pf < LOW_PF_THRESHOLD:
            recs.append(EnergyRecommendation(
                id="rec-low-pf", title="Low power factor detected", category="efficiency", priority="high",
                description="Inductive loads (motors, pumps, old fans, cheap chargers) draw extra current "
                            "for the same work. Servicing motors or fitting PF correction reduces losses.",
                evidence=f"Average power factor {avg_pf:.2f} over {len(pf_vals)} readings above "
                         f"{PF_MIN_LOAD_W:.0f} W in the last 24 h (threshold {LOW_PF_THRESHOLD}).",
            ))

    volts = [v for _, _, v in raw if v is not None]
    if len(volts) >= MIN_SAMPLES:
        out = sum(1 for v in volts if v < VOLTAGE_LOW or v > VOLTAGE_HIGH)
        if out / len(volts) > 0.05:
            recs.append(EnergyRecommendation(
                id="rec-voltage", title="Supply voltage outside the normal range", category="safety",
                priority="medium",
                description="Sustained under/over-voltage stresses motors and electronics. Consider a "
                            "stabiliser for sensitive appliances or report it to your utility.",
                evidence=f"{out / len(volts):.0%} of {len(volts)} readings in the last 24 h were outside "
                         f"{VOLTAGE_LOW:.0f}–{VOLTAGE_HIGH:.0f} V (min {min(volts):.0f} V, max {max(volts):.0f} V).",
            ))

    # Last 7 days of hourly stats — usage-pattern rules
    week = hourly_stats(db, device_id, now - 7 * DAY, now)
    night = [(t, s) for t, s in week.items() if 1 <= to_local(t).hour < 5]
    nights = {to_local(t).date() for t, _ in night}
    if len(night) >= 9 and len(nights) >= 3:
        samples = sum(s.samples for _, s in night)
        avg_w = sum((s.power_avg or 0) * s.samples for _, s in night) / max(samples, 1)
        if avg_w > OVERNIGHT_BASELOAD_W:
            kwh_month = avg_w * 24 * 30 / 1000
            recs.append(EnergyRecommendation(
                id="rec-overnight-baseload", title="High overnight standby load", category="habits",
                priority="medium",
                description="Something keeps drawing power while the home sleeps. Check set-top boxes, "
                            "chargers, water purifiers and appliances left on standby.",
                evidence=f"Average load 1am–5am was {avg_w:.0f} W across {len(nights)} nights "
                         f"(≈{kwh_month:.0f} kWh / ₹{kwh_month * tariff:.0f} per month if continuous).",
            ))

    week_total = sum(s.energy_kwh for s in week.values())
    if week_total >= 1.0 and len(week) >= 24:
        evening = sum(s.energy_kwh for t, s in week.items() if 18 <= to_local(t).hour < 22)
        share = evening / week_total
        if share > EVENING_SHARE_THRESHOLD:
            heavy = db.scalars(select(Appliance).where(Appliance.rated_watts >= 1500)).all()
            names = ", ".join(a.name for a in heavy[:3])
            recs.append(EnergyRecommendation(
                id="rec-evening-peak", title="Evening peak dominates your usage", category="habits",
                priority="medium",
                description="Moving flexible loads (washing, water heating, charging) out of 6pm–10pm "
                            "flattens your peak" + (f" — e.g. {names}." if names else "."),
                evidence=f"{share:.0%} of the last 7 days' {week_total:.1f} kWh was used between 6pm and 10pm.",
            ))

    configured, budget = _target(db)
    if configured and budget:
        # Same metered + simulated totals and tariff model as the dashboard and projected bill.
        from app.services.billing_service import project_cycle
        proj = project_cycle(db, now=now)
        if proj["elapsed_days"] >= 1 and len(proj["usage"].hours) >= 24:
            projected = proj["projected"].total
            if projected > budget:
                recs.append(EnergyRecommendation(
                    id="rec-budget-projection", title="On course to exceed your monthly budget",
                    category="budget", priority="high",
                    description="At the current pace this billing cycle's estimated bill will be above your target. "
                                "Reducing the largest loads now keeps you within budget.",
                    evidence=f"{proj['used_kwh']:.1f} kWh in {proj['elapsed_days']:.1f} days → projected "
                             f"{proj['projected_kwh']:.0f} kWh ≈ ₹{projected:.0f} vs budget ₹{budget:.0f} "
                             f"(estimate from your tariff settings).",
                ))

    heavy_long = db.scalars(
        select(Appliance).where(Appliance.rated_watts >= 1500, Appliance.daily_hours >= 3)
    ).all()
    if heavy_long:
        top = max(heavy_long, key=lambda a: a.rated_watts * a.daily_hours * a.quantity)
        kwh = top.rated_watts * top.daily_hours * top.quantity / 1000
        recs.append(EnergyRecommendation(
            id="rec-heavy-appliance", title=f"Review usage of {top.name}", category="inventory", priority="low",
            description="This is your largest estimated load. Thermostat settings, timers or an efficient "
                        "model have the biggest effect here.",
            evidence=f"From your inventory: {top.rated_watts:.0f} W × {top.daily_hours:g} h/day × "
                     f"{top.quantity} ≈ {kwh:.1f} kWh/day (estimate).",
        ))

    recs.sort(key=lambda r: _PRIORITY[r.priority])
    return recs
