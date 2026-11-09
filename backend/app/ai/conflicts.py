"""
SHEM AI — Conflict detection (rule-based, deterministic, no LLM needed)

Flags places where what the user entered disagrees with what the meter
measures, or where the system state is inconsistent. Examples:
  * an appliance declared as 9 W while the meter measures 480 W through its relay
  * the relay is commanded OFF but load is still measured
  * appliance estimates (W × hours) far from measured daily energy
  * a bill whose ₹/kWh is far from the configured tariff
  * a monthly budget that is already exceeded / on course to be

Each conflict has a stable `id` so it can be dismissed and so the
background scanner only announces new ones.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import (
    AIConflictDismissal,
    Appliance,
    ElectricityBill,
    RelayChannel,
    RelayCommand,
    TelemetryRow,
)
from app.services.device_service import get_device_status
from app.services.energy_service import hourly_stats
from app.services.billing_service import compute_bill, load_tariff
from app.services.insights_service import _target
from app.utils.timestamps import DAY, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}

# Plausible rated-power ranges per appliance category (W, per unit).
CATEGORY_WATT_RANGES: Dict[str, tuple] = {
    "cooling": (300, 5000),
    "lighting": (1, 300),
    "fans": (10, 200),
    "refrigerator": (40, 800),
    "kitchen": (20, 3500),
    "entertainment": (5, 800),
    "heating": (300, 6000),
}

LIVE_WINDOW = timedelta(minutes=2)       # "current" power = median of the last 2 min of valid readings
OVER_RATED_FACTOR = 2.0                  # measured > 2 × rated …
OVER_RATED_MIN_W = 20.0                  # … and at least 20 W above it
UNDER_RATED_FACTOR = 0.1                 # measured < 10 % of a ≥100 W rating
BILL_RATE_TOLERANCE = 0.35               # ±35 % vs configured tariff
ESTIMATE_RATIO = 3.0                     # estimate vs measured daily energy off by 3×


@dataclass
class Conflict:
    id: str
    severity: str                         # info | warning | critical
    category: str                         # appliance | relay | device | bill | target | household | data
    title: str
    message: str
    evidence: str
    suggestion: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    dismissed: bool = False

    def to_dict(self) -> Dict:
        d = asdict(self)
        return {
            "id": d["id"], "severity": d["severity"], "category": d["category"], "title": d["title"],
            "message": d["message"], "evidence": d["evidence"], "suggestion": d["suggestion"],
            "entityType": d["entity_type"], "entityId": d["entity_id"], "dismissed": d["dismissed"],
        }


def _live_power(db: Session, device_id: str) -> Optional[float]:
    since = utcnow() - LIVE_WINDOW
    vals = [p for (p,) in db.execute(
        select(TelemetryRow.active_power_w).where(
            TelemetryRow.device_id == device_id, TelemetryRow.validity == "valid",
            TelemetryRow.measured_at >= since, TelemetryRow.active_power_w.is_not(None))
    ).all()]
    return statistics.median(vals) if vals else None


def _rated_total(a: Appliance) -> Optional[float]:
    return (a.rated_watts or 0) * (a.quantity or 1) if a.rated_watts else None


def _appliance_rules(db: Session, appliances: List[Appliance], live_w: Optional[float],
                     relay_state: Optional[str], out: List[Conflict]) -> None:
    for a in appliances:
        rated = _rated_total(a)
        # Implausible rating for the category
        rng = CATEGORY_WATT_RANGES.get((a.category or "").lower())
        if a.rated_watts is not None and rng and not (rng[0] <= a.rated_watts <= rng[1]):
            out.append(Conflict(
                id=f"rating-implausible:{a.id}", severity="warning", category="appliance",
                title=f"'{a.name}' rating looks wrong",
                message=f"{a.rated_watts:g} W is unusual for a {a.category} appliance "
                        f"(typical {rng[0]}–{rng[1]} W).",
                evidence=f"rated_watts={a.rated_watts:g}, category={a.category}",
                suggestion="Check the label on the appliance and update its wattage.",
                entity_type="appliance", entity_id=a.id))
        if a.rated_watts is None and a.relay_channel:
            out.append(Conflict(
                id=f"rating-missing:{a.id}", severity="info", category="appliance",
                title=f"'{a.name}' has no wattage", message="Relay-linked appliance without a rated wattage, "
                "so its measured usage can't be checked.", evidence="rated_watts is empty",
                suggestion="Add the rated wattage.", entity_type="appliance", entity_id=a.id))
        if rated and rated * max(a.daily_hours or 0, 0) > 30000:
            out.append(Conflict(
                id=f"estimate-huge:{a.id}", severity="warning", category="appliance",
                title=f"'{a.name}' estimate is very large",
                message=f"{rated:g} W × {a.daily_hours:g} h/day ≈ {rated * a.daily_hours / 1000:.1f} kWh/day.",
                evidence=f"rated {a.rated_watts:g} W × qty {a.quantity}, {a.daily_hours:g} h/day",
                suggestion="Check quantity, wattage and daily hours.", entity_type="appliance", entity_id=a.id))

        if not a.relay_channel:
            continue
        # Status vs relay
        if relay_state in ("ON", "OFF") and (a.status or "").lower() in ("on", "off") \
                and (a.status.lower() == "on") != (relay_state == "ON"):
            out.append(Conflict(
                id=f"status-mismatch:{a.id}", severity="info", category="appliance",
                title=f"'{a.name}' status disagrees with the relay",
                message=f"The appliance is marked '{a.status}' but relay {a.relay_channel} reports {relay_state}.",
                evidence=f"appliance.status={a.status}, relay{a.relay_channel}={relay_state}",
                suggestion="Toggle it once from SHEM so both agree.", entity_type="appliance", entity_id=a.id))
        # Declared rating vs measured power through its relay (the "9 W but 480 W" case)
        if relay_state == "ON" and rated and live_w is not None:
            if live_w > rated * OVER_RATED_FACTOR and live_w - rated > OVER_RATED_MIN_W:
                sev = "critical" if live_w > rated * 10 else "warning"
                out.append(Conflict(
                    id=f"over-rated:{a.id}", severity=sev, category="appliance",
                    title=f"'{a.name}' draws far more than its rating",
                    message=f"It is declared as {rated:g} W, but the meter currently measures {live_w:.0f} W "
                            f"on relay {a.relay_channel} ({live_w / rated:.1f}×).",
                    evidence=f"median power over the last 2 min = {live_w:.1f} W; declared {rated:g} W",
                    suggestion="Either the wattage was entered wrongly, a different/extra load is connected "
                               "to this relay, or the appliance is faulty.",
                    entity_type="appliance", entity_id=a.id))
            elif rated >= 100 and live_w < rated * UNDER_RATED_FACTOR:
                out.append(Conflict(
                    id=f"under-rated:{a.id}", severity="info", category="appliance",
                    title=f"'{a.name}' draws much less than its rating",
                    message=f"Declared {rated:g} W but only {live_w:.0f} W is measured with the relay ON.",
                    evidence=f"median power over the last 2 min = {live_w:.1f} W",
                    suggestion="It may be idle/standby, switched off at the wall, or the rating is too high.",
                    entity_type="appliance", entity_id=a.id))


def detect_conflicts(db: Session, include_dismissed: bool = False, mqtt_connected: bool = True) -> List[Conflict]:
    device_id = settings.device_id
    now = utcnow()
    out: List[Conflict] = []
    tariff_model = load_tariff(db)

    appliances = list(db.scalars(select(Appliance)).all())
    ch = db.scalar(select(RelayChannel).where(RelayChannel.device_id == device_id, RelayChannel.channel == 1))
    relay_state = ch.commanded_state if ch else None
    status = get_device_status(db, device_id, mqtt_connected)
    live_w = _live_power(db, device_id) if status.device_online else None

    _appliance_rules(db, appliances, live_w, relay_state, out)

    # Relay OFF but load measured
    if relay_state == "OFF" and live_w is not None and live_w > max(settings.load_active_threshold_w, 10):
        out.append(Conflict(
            id="relay-off-load", severity="warning", category="relay",
            title="Load measured while the relay is OFF",
            message=f"Relay 1 is OFF but the meter still measures {live_w:.0f} W.",
            evidence=f"relay1=OFF, median power over the last 2 min = {live_w:.1f} W",
            suggestion="The meter may sit on another circuit, or the relay contacts may be stuck — check wiring.",
            entity_type="relay", entity_id="1"))

    # Measured load vs everything that's marked on
    on_rated = sum(_rated_total(a) or 0 for a in appliances if (a.status or "").lower() == "on")
    if live_w is not None and live_w > 50 and appliances and live_w > on_rated * OVER_RATED_FACTOR + 50:
        out.append(Conflict(
            id="unaccounted-load", severity="info", category="appliance",
            title="More load than the appliances marked ON",
            message=f"The meter measures {live_w:.0f} W but appliances marked ON add up to {on_rated:.0f} W.",
            evidence=f"live {live_w:.1f} W vs {on_rated:.0f} W declared ON",
            suggestion="Something not in your inventory is running, or statuses/wattages are out of date."))

    # Device / power quality
    if status.last_seen_at and not status.device_online and now - status.last_seen_at > timedelta(minutes=10):
        mins = (now - status.last_seen_at).total_seconds() / 60
        out.append(Conflict(
            id="device-offline", severity="warning", category="device", title="Meter is offline",
            message=f"No readings for {mins:.0f} minutes; usage during this gap is counted once it reconnects.",
            evidence=f"last seen {status.last_seen_at.isoformat()}",
            suggestion="Check the ESP32's power and Wi-Fi.", entity_type="device", entity_id=device_id))
    latest = db.scalar(select(TelemetryRow).where(TelemetryRow.device_id == device_id,
                                                  TelemetryRow.validity == "valid")
                       .order_by(TelemetryRow.measured_at.desc()).limit(1))
    if latest and status.device_online and latest.voltage_v is not None \
            and not (200 <= latest.voltage_v <= 255):
        out.append(Conflict(
            id="voltage-now", severity="critical" if latest.voltage_v < 180 or latest.voltage_v > 270 else "warning",
            category="device", title="Supply voltage out of range",
            message=f"Live voltage is {latest.voltage_v:.0f} V (normal 207–253 V).",
            evidence=f"latest reading {latest.voltage_v:.1f} V", suggestion="Protect sensitive appliances."))
    hour_ago = now - timedelta(hours=1)
    rows = db.execute(select(TelemetryRow.validity).where(TelemetryRow.device_id == device_id,
                                                          TelemetryRow.measured_at >= hour_ago)).all()
    if len(rows) >= 30:
        bad = sum(1 for (v,) in rows if v != "valid")
        if bad / len(rows) > 0.2:
            out.append(Conflict(
                id="invalid-readings", severity="warning", category="data", title="Many invalid meter readings",
                message=f"{bad} of {len(rows)} readings in the last hour were invalid.",
                evidence="telemetry.validity = invalid", suggestion="Check the PZEM-004T wiring/CT clamp."))

    failed = db.scalars(select(RelayCommand).where(
        RelayCommand.created_at >= now - DAY,
        RelayCommand.status.in_(("timeout", "publish_failed", "rejected_expired", "rejected_invalid_channel",
                                 "rejected_invalid_state", "rejected_time_unsynchronized")))).all()
    if failed:
        kinds = sorted({c.status for c in failed})
        out.append(Conflict(
            id="relay-failures", severity="info", category="relay",
            title=f"{len(failed)} relay command(s) failed today",
            message=f"Failures in the last 24 h: {', '.join(kinds)}.",
            evidence=f"{len(failed)} commands, latest {failed[-1].command_id}",
            suggestion="'rejected_time_unsynchronized' means the ESP32 has no NTP time; 'timeout' means no ack."))

    # Estimates vs measured daily energy (needs ≥2 days of measured coverage in the last 7)
    week = hourly_stats(db, device_id, now - 7 * DAY, now)
    covered_hours = len(week)
    if covered_hours >= 48 and appliances:
        measured_daily = sum(s.energy_kwh for s in week.values()) / (covered_hours / 24)
        estimate_daily = sum((_rated_total(a) or 0) * (a.daily_hours or 0) for a in appliances) / 1000
        if measured_daily > 0.05 and estimate_daily > 0:
            ratio = estimate_daily / measured_daily
            if ratio > ESTIMATE_RATIO or ratio < 1 / ESTIMATE_RATIO:
                out.append(Conflict(
                    id="estimate-vs-measured", severity="info", category="appliance",
                    title="Appliance estimates don't match the meter",
                    message=f"Your appliance list estimates {estimate_daily:.2f} kWh/day; the meter measures "
                            f"{measured_daily:.2f} kWh/day on average.",
                    evidence=f"{covered_hours} measured hours in the last 7 days",
                    suggestion="Adjust daily hours/wattages, or note the meter only covers the circuit it is on."))

    # Bills
    from app.services.billing_service import is_home_bill
    all_bills = list(db.scalars(select(ElectricityBill)).all())
    # Tariff/budget checks apply to this home's bills only; other locations have their own tariffs.
    bills = [b for b in all_bills if is_home_bill(b)]
    seen_periods: Dict[tuple, str] = {}
    for b in bills:
        if b.units_consumed_kwh and b.bill_amount_inr:
            expected = compute_bill(b.units_consumed_kwh, tariff_model).total
            if expected > 0 and abs(b.bill_amount_inr - expected) / expected > BILL_RATE_TOLERANCE:
                rate = b.bill_amount_inr / b.units_consumed_kwh
                out.append(Conflict(
                    id=f"bill-rate:{b.id}", severity="warning", category="bill",
                    title="Bill amount differs from your tariff",
                    message=f"Your tariff settings put {b.units_consumed_kwh:g} kWh at about ₹{expected:.0f}, "
                            f"but this bill is ₹{b.bill_amount_inr:g} (₹{rate:.2f}/kWh).",
                    evidence=f"₹{b.bill_amount_inr:g} billed vs ₹{expected:.0f} expected",
                    suggestion="Check the units/amount on the bill, or update the tariff (slabs, fixed charge, "
                               "fuel adjustment, duty) in Settings to match your bill.",
                    entity_type="bill", entity_id=b.id))
        if b.billing_month and b.billing_year:
            key = (b.location_tag or "my_home", b.billing_year, b.billing_month)
            if key in seen_periods:
                out.append(Conflict(
                    id=f"bill-duplicate:{b.id}", severity="warning", category="bill", title="Duplicate bill",
                    message=f"Two bills are recorded for {b.billing_month:02d}/{b.billing_year}.",
                    evidence=f"bills {seen_periods[key]} and {b.id}", suggestion="Delete one of them.",
                    entity_type="bill", entity_id=b.id))
            seen_periods[key] = b.id
        if b.billing_period_start and b.billing_period_end and b.billing_period_days:
            try:
                from datetime import date
                span = (date.fromisoformat(b.billing_period_end) - date.fromisoformat(b.billing_period_start)).days
                if span < 0 or abs(span - b.billing_period_days) > 2:
                    out.append(Conflict(
                        id=f"bill-period:{b.id}", severity="info", category="bill",
                        title="Bill period doesn't add up",
                        message=f"{b.billing_period_start} → {b.billing_period_end} is {span} days, "
                                f"but the bill says {b.billing_period_days} days.",
                        evidence="billing_period_start/end vs billing_period_days",
                        entity_type="bill", entity_id=b.id))
            except ValueError:
                pass

    # Target — metered + simulated energy priced with the tariff model (same as the projected bill)
    configured, budget = _target(db)
    if configured and budget:
        from app.services.billing_service import project_cycle
        proj = project_cycle(db, tariff_model, now=now)
        spent, projected = proj["so_far"].total, proj["projected"].total
        if tariff_model.fixed_charge and budget <= tariff_model.fixed_charge:
            out.append(Conflict(
                id="target-below-fixed", severity="warning", category="target",
                title="Budget is below the fixed charge",
                message=f"Your ₹{budget:.0f} budget doesn't cover the ₹{tariff_model.fixed_charge:.0f} fixed charge "
                        "on every bill, so it can't be met even with zero usage.",
                evidence="energy_targets.monthly_budget_inr vs tariff fixed charge",
                suggestion="Raise the budget, or check the fixed charge in tariff settings.",
                entity_type="target", entity_id="1"))
        if spent > budget:
            out.append(Conflict(
                id="target-exceeded", severity="critical", category="target", title="Monthly budget exceeded",
                message=f"₹{spent:.0f} used this billing cycle already exceeds your ₹{budget:.0f} budget.",
                evidence=f"{proj['used_kwh']:.2f} kWh ({proj['metered_kwh']:.2f} metered + "
                         f"{proj['simulated_kwh']:.2f} simulated) priced with your tariff",
                suggestion="Cut heavy loads or revise the target.", entity_type="target", entity_id="1"))
        elif proj["elapsed_days"] >= 3 and projected > budget * 1.1:
            out.append(Conflict(
                id="target-at-risk", severity="warning", category="target", title="On course to exceed budget",
                message=f"At the current pace this cycle's bill will be about ₹{projected:.0f} vs a ₹{budget:.0f} budget.",
                evidence=f"₹{spent:.0f} in {proj['elapsed_days']:.1f} days; projected {proj['projected_kwh']:.0f} kWh",
                suggestion="Ask SHEM AI where to cut usage.", entity_type="target", entity_id="1"))
        min_bill = min((b.bill_amount_inr for b in bills if b.bill_amount_inr), default=None)
        if min_bill and budget < min_bill * 0.4:
            out.append(Conflict(
                id="target-unrealistic", severity="info", category="target", title="Budget may be unrealistic",
                message=f"₹{budget:.0f}/month is under 40% of your lowest recorded bill (₹{min_bill:.0f}).",
                evidence="energy_targets vs electricity_bills", entity_type="target", entity_id="1"))

    if tariff_model.mode == "flat" and not (1 <= tariff_model.flat_rate <= 25):
        out.append(Conflict(
            id="tariff-unusual", severity="warning", category="household", title="Unusual tariff",
            message=f"Tariff is set to ₹{tariff_model.flat_rate:.2f}/kWh; Indian residential tariffs are usually "
                    "₹3–12/kWh.",
            evidence="household_config.tariff_rate_inr_per_kwh", suggestion="Check household settings.",
            entity_type="household", entity_id="1"))

    # Dismissals
    dismissals = {d.conflict_id: d for d in db.scalars(select(AIConflictDismissal)).all()}
    result: List[Conflict] = []
    for c in out:
        d = dismissals.get(c.id)
        if d and (d.dismissed_until is None or d.dismissed_until > now) \
                and SEVERITY_RANK[c.severity] <= SEVERITY_RANK.get(d.severity, 0):
            c.dismissed = True
            if not include_dismissed:
                continue
        result.append(c)
    result.sort(key=lambda c: -SEVERITY_RANK[c.severity])
    return result


def dismiss_conflict(db: Session, conflict_id: str, hours: float = 24.0) -> bool:
    current = {c.id: c for c in detect_conflicts(db, include_dismissed=True)}
    c = current.get(conflict_id)
    if c is None:
        return False
    row = db.get(AIConflictDismissal, conflict_id) or AIConflictDismissal(conflict_id=conflict_id)
    row.severity = c.severity
    row.dismissed_at = utcnow()
    row.dismissed_until = utcnow() + timedelta(hours=hours)
    db.merge(row)
    db.commit()
    return True
