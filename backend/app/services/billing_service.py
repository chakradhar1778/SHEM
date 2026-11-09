"""
SHEM Backend — Bill engine: tariff model, billing cycle and projected bill

A real Indian residential bill is not kWh × one rate. This models the parts a
household can read off its own bill:

  * energy charge   — flat ₹/kWh, or rising slabs (cumulative upper bounds per cycle)
  * fuel adjustment — FPPCA / FAC, ₹ per kWh
  * electricity duty — % of (energy + fuel) charges
  * fixed charge    — ₹ per billing cycle (read the total off the bill)

The billing cycle runs from the meter-reading day (`billing_cycle_day`, e.g.
14 → the 14th to the 13th of the next month); day 1 is a calendar month.

The projection uses metered + simulated energy for the cycle so far (the same
totals the dashboard shows) and extrapolates at the cycle-to-date pace. It is
an estimate, labelled as such — not the utility's bill.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import EnergyTarget, HouseholdConfig
from app.utils.timestamps import DAY, from_local, to_local, utcnow

settings = get_settings()

MAX_KWH = 1_000_000.0


# ═══════════════════════════════════════════════════════════════
# TARIFF
# ═══════════════════════════════════════════════════════════════

@dataclass
class Slab:
    upto_kwh: Optional[float]      # cumulative upper bound in the cycle; None = no limit
    rate: float


@dataclass
class Tariff:
    mode: str = "flat"
    flat_rate: float = 7.5
    slabs: List[Slab] = field(default_factory=list)
    fixed_charge: float = 0.0
    fuel_per_kwh: float = 0.0
    duty_percent: float = 0.0
    cycle_day: int = 1

    @property
    def is_plain_flat(self) -> bool:
        """Flat rate with no extras: cost is exactly kWh × rate."""
        return self.mode != "slab" and not self.fixed_charge and not self.fuel_per_kwh and not self.duty_percent

    def energy_slabs(self) -> List[Slab]:
        if self.mode == "slab" and self.slabs:
            return self.slabs
        return [Slab(None, self.flat_rate)]


def parse_slabs(raw: Optional[str]) -> List[Slab]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    out = []
    for s in data if isinstance(data, list) else []:
        try:
            upto = s.get("uptoKWh")
            out.append(Slab(None if upto is None else float(upto), float(s["rateINR"])))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return out


def validate_slabs(slabs: List[Slab]) -> Optional[str]:
    """Returns an error message, or None when the slab table is usable."""
    if not slabs:
        return "Add at least one slab."
    prev = 0.0
    for i, s in enumerate(slabs):
        if not (0 <= s.rate <= 100):
            return f"Slab {i + 1}: rate must be between ₹0 and ₹100 per kWh."
        last = i == len(slabs) - 1
        if s.upto_kwh is None and not last:
            return f"Slab {i + 1}: only the last slab can be open-ended."
        if s.upto_kwh is not None:
            if s.upto_kwh <= prev:
                return f"Slab {i + 1}: limits must increase (got {s.upto_kwh:g} after {prev:g})."
            prev = s.upto_kwh
    if slabs[-1].upto_kwh is not None:
        return "The last slab must have no upper limit (it covers all remaining units)."
    return None


def slabs_to_json(slabs: List[Slab]) -> str:
    return json.dumps([{"uptoKWh": s.upto_kwh, "rateINR": s.rate} for s in slabs])


def tariff_from_config(cfg: Optional[HouseholdConfig]) -> Tariff:
    if cfg is None:
        return Tariff(flat_rate=settings.default_tariff_rate_inr_per_kwh)
    rate = cfg.tariff_rate_inr_per_kwh if cfg.tariff_rate_inr_per_kwh and cfg.tariff_rate_inr_per_kwh > 0 \
        else settings.default_tariff_rate_inr_per_kwh
    slabs = parse_slabs(cfg.tariff_slabs_json)
    mode = "slab" if (cfg.tariff_mode == "slab" and slabs and validate_slabs(slabs) is None) else "flat"
    return Tariff(mode=mode, flat_rate=rate, slabs=slabs, fixed_charge=max(0.0, cfg.fixed_charge_inr or 0.0),
                  fuel_per_kwh=max(0.0, cfg.fuel_adjustment_inr_per_kwh or 0.0),
                  duty_percent=max(0.0, cfg.electricity_duty_percent or 0.0),
                  cycle_day=min(28, max(1, cfg.billing_cycle_day or 1)))


def load_tariff(db: Session) -> Tariff:
    return tariff_from_config(db.get(HouseholdConfig, 1))


# ═══════════════════════════════════════════════════════════════
# BILL CALCULATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class SlabLine:
    label: str
    from_kwh: float
    to_kwh: Optional[float]
    kwh: float
    rate: float
    amount: float


@dataclass
class BillBreakdown:
    kwh: float
    lines: List[SlabLine]
    energy_charge: float
    fuel_charge: float
    duty: float
    fixed_charge: float
    total: float
    effective_rate: Optional[float]      # total ÷ kWh (incl. fixed)
    variable_rate: Optional[float]       # (energy + fuel + duty) ÷ kWh
    marginal_rate: float                 # cost of the next kWh, incl. fuel + duty
    slab_index: int                      # slab the next kWh falls in
    kwh_to_next_slab: Optional[float]
    next_slab_rate: Optional[float]


def _slab_label(lo: float, hi: Optional[float]) -> str:
    return f"{lo:g}–{hi:g} kWh" if hi is not None else (f"Above {lo:g} kWh" if lo > 0 else "All units")


def compute_bill(kwh: float, t: Tariff, fixed_fraction: float = 1.0) -> BillBreakdown:
    """Bill for `kwh` used in one cycle. `fixed_fraction` pro-rates the fixed charge (cycle-to-date bills)."""
    kwh = max(0.0, min(float(kwh), MAX_KWH))
    slabs = t.energy_slabs()
    lines: List[SlabLine] = []
    lo, left, energy = 0.0, kwh, 0.0
    slab_index, kwh_to_next, next_rate = len(slabs) - 1, None, None
    found = False
    for i, s in enumerate(slabs):
        hi = s.upto_kwh
        width = (hi - lo) if hi is not None else float("inf")
        used = min(left, width)
        amount = used * s.rate
        energy += amount
        lines.append(SlabLine(_slab_label(lo, hi), lo, hi, round(used, 4), s.rate, round(amount, 2)))
        if not found and hi is not None and kwh < hi:   # the next kWh falls in this slab
            found = True
            slab_index, kwh_to_next = i, round(hi - kwh, 4)
            next_rate = slabs[i + 1].rate if i + 1 < len(slabs) else None
        left -= used
        lo = hi if hi is not None else lo
    fuel = kwh * t.fuel_per_kwh
    duty = (energy + fuel) * t.duty_percent / 100.0
    fixed = t.fixed_charge * max(0.0, min(1.0, fixed_fraction))
    total = energy + fuel + duty + fixed
    mrate = slabs[slab_index].rate
    marginal = (mrate + t.fuel_per_kwh) * (1 + t.duty_percent / 100.0)
    return BillBreakdown(
        kwh=round(kwh, 4), lines=lines, energy_charge=round(energy, 2), fuel_charge=round(fuel, 2),
        duty=round(duty, 2), fixed_charge=round(fixed, 2), total=round(total, 2),
        effective_rate=round(total / kwh, 3) if kwh > 0 else None,
        variable_rate=round((energy + fuel + duty) / kwh, 3) if kwh > 0 else None,
        marginal_rate=round(marginal, 3), slab_index=slab_index,
        kwh_to_next_slab=kwh_to_next, next_slab_rate=next_rate,
    )


def kwh_for_amount(amount: float, t: Tariff) -> float:
    """kWh per cycle whose full bill (incl. fixed charge) equals `amount` — inverse of compute_bill."""
    if amount <= t.fixed_charge:
        return 0.0
    if t.is_plain_flat:
        return amount / t.flat_rate
    lo, hi = 0.0, 1.0
    while compute_bill(hi, t).total < amount and hi < MAX_KWH:
        hi *= 2
    for _ in range(60):
        mid = (lo + hi) / 2
        if compute_bill(mid, t).total < amount:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


# ═══════════════════════════════════════════════════════════════
# BILLING CYCLE
# ═══════════════════════════════════════════════════════════════

def _add_month(d: date) -> date:
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, d.day)


def _sub_month(d: date) -> date:
    y, m = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return date(y, m, d.day)


def cycle_bounds(now: datetime, cycle_day: int) -> Tuple[date, date]:
    """Local [start, end) dates of the billing cycle containing `now` (cycle_day 1–28)."""
    today = to_local(now).date()
    start = date(today.year, today.month, cycle_day)
    if today < start:
        start = _sub_month(start)
    return start, _add_month(start)


def cycle_instants(start: date, end: date) -> Tuple[datetime, datetime]:
    return from_local(datetime(start.year, start.month, start.day)), from_local(datetime(end.year, end.month, end.day))


# ═══════════════════════════════════════════════════════════════
# COST RATE used by every "estimated cost" figure
# ═══════════════════════════════════════════════════════════════

_RATE_CACHE: Dict[str, Tuple[float, float]] = {}
_RATE_TTL_S = 60.0


def cost_rate(db: Session) -> float:
    """
    ₹ per kWh for cost estimates (insights, today, per appliance).
    Flat with no extras: the flat rate. Otherwise the blended variable rate
    (energy + fuel + duty, excluding the fixed charge) at this cycle's projected
    consumption, so cost figures match where the bill is heading.
    """
    cfg = db.get(HouseholdConfig, 1)
    t = tariff_from_config(cfg)
    if t.is_plain_flat:
        return t.flat_rate
    key = f"{cfg.updated_at if cfg else ''}|{t.cycle_day}"
    hit = _RATE_CACHE.get(key)
    if hit and hit[1] > time.monotonic():
        return hit[0]
    proj = project_cycle(db, t)
    b = proj["projected"]
    rate = b.variable_rate if b.variable_rate else compute_bill(0, t).marginal_rate
    _RATE_CACHE.clear()
    _RATE_CACHE[key] = (rate, time.monotonic() + _RATE_TTL_S)
    return rate


def clear_rate_cache() -> None:
    _RATE_CACHE.clear()


def budget_kwh(db: Session, budget_inr: float) -> float:
    """kWh per cycle that a ₹ budget buys under the configured tariff."""
    return kwh_for_amount(budget_inr, load_tariff(db))


def cycle_days(now: datetime, t: Tariff) -> int:
    s, e = cycle_bounds(now, t.cycle_day)
    return (e - s).days


# ═══════════════════════════════════════════════════════════════
# PROJECTION
# ═══════════════════════════════════════════════════════════════

def project_cycle(db: Session, t: Optional[Tariff] = None, now: Optional[datetime] = None) -> dict:
    """Cycle-to-date usage and bill, and the projected full-cycle bill."""
    from app.services.insights_service import _usage   # lazy: insights imports this module

    t = t or load_tariff(db)
    now = now or utcnow()
    start_d, end_d = cycle_bounds(now, t.cycle_day)
    start, end = cycle_instants(start_d, end_d)
    total_days = (end - start) / DAY
    elapsed_days = max((now - start) / DAY, 0.0)
    u = _usage(db, settings.device_id, start, now)
    used = u.total()

    basis = "cycle"
    if elapsed_days >= 1:
        daily = used / elapsed_days
    else:  # too early in the cycle: use the last 24 h of usage as the pace
        recent = _usage(db, settings.device_id, now - DAY, now)
        daily, basis = recent.total(), "last24h"
    projected_kwh = max(used, used + daily * max(total_days - elapsed_days, 0.0))
    coverage_h = len(u.hours)
    confidence = "low" if elapsed_days < 2 or coverage_h < 24 else "medium" if elapsed_days < 7 else "high"

    return {
        "tariff": t, "cycle_start": start_d, "cycle_end": end_d, "start": start, "end": end,
        "total_days": total_days, "elapsed_days": elapsed_days, "used_kwh": used,
        "metered_kwh": u.metered(), "simulated_kwh": u.simulated(), "daily_kwh": daily,
        "projected_kwh": projected_kwh, "basis": basis, "confidence": confidence,
        "so_far": compute_bill(used, t, fixed_fraction=elapsed_days / total_days if total_days else 1.0),
        "projected": compute_bill(projected_kwh, t),
        "usage": u,
    }


def budget_status(db: Session, proj: dict) -> Optional[dict]:
    target = db.get(EnergyTarget, 1)
    if not target or not target.is_configured or target.monthly_budget_inr <= 0:
        return None
    t: Tariff = proj["tariff"]
    budget = target.monthly_budget_inr
    kwh_cap = kwh_for_amount(budget, t)
    remaining_days = max(proj["total_days"] - proj["elapsed_days"], 0.0)
    remaining_kwh = kwh_cap - proj["used_kwh"]
    return {
        "budget_inr": budget, "budget_kwh": kwh_cap,
        "spent_inr": proj["so_far"].total, "projected_inr": proj["projected"].total,
        "projected_over_inr": round(proj["projected"].total - budget, 2),
        "used_percent": round(proj["so_far"].total / budget * 100, 1),
        "remaining_kwh": round(remaining_kwh, 3),
        "daily_allowance_kwh": round(remaining_kwh / remaining_days, 3) if remaining_days > 0 else None,
        "status": ("over" if proj["so_far"].total > budget else
                   "at_risk" if proj["projected"].total > budget else "on_track"),
    }


# ═══════════════════════════════════════════════════════════════
# COST PER APPLIANCE (bills and the projected bill)
# ═══════════════════════════════════════════════════════════════

@dataclass
class ApplianceShare:
    appliance_id: str
    name: str
    icon_type: Optional[str]
    source: str                 # metered | simulated
    kwh: float
    share_percent: float        # of the bill's total amount
    cost: float


def appliance_kwh(usage) -> List[Tuple[str, float]]:
    """(appliance key, kWh) from an insights _Usage, largest first."""
    totals: Dict[str, float] = {}
    for h in usage.hours.values():
        for k, v in h.by_app.items():
            totals[k] = totals.get(k, 0.0) + v
    return sorted(((k, v) for k, v in totals.items() if v > 0), key=lambda x: x[1], reverse=True)


def allocate(usage, billed_kwh: float, variable_amount: float, total_amount: float) -> dict:
    """
    Split `variable_amount` (bill minus fixed charge) across appliances by their kWh at the bill's own
    average variable rate. Billed units SHEM did not measure become "rest of home". When measured kWh
    exceeds the billed units (simulated devices aren't on the real meter), shares are scaled to fit.
    """
    items = appliance_kwh(usage)
    measured = sum(v for _, v in items)
    rate = variable_amount / billed_kwh if billed_kwh > 0 else 0.0
    scale = min(1.0, billed_kwh / measured) if measured > 0 else 0.0
    shares: List[ApplianceShare] = []
    for key, kwh in items:
        m = usage.meta[key]
        cost = kwh * scale * rate
        shares.append(ApplianceShare(key, m.name, m.icon_type, m.source, round(kwh, 4),
                                     round(cost / total_amount * 100, 1) if total_amount > 0 else 0.0,
                                     round(cost, 2)))
    rest_kwh = max(0.0, billed_kwh - measured)
    rest_cost = rest_kwh * rate
    return {
        "measured_kwh": measured, "scale": scale, "variable_rate": rate, "appliances": shares,
        "rest_kwh": rest_kwh, "rest_cost": round(rest_cost, 2),
        "rest_percent": round(rest_cost / total_amount * 100, 1) if total_amount > 0 else 0.0,
    }


def bill_period(bill, cycle_day: int) -> Tuple[date, date, str]:
    """Local [start, end) of a recorded bill: its own dates, else the billing cycle starting in its month."""
    if bill.billing_period_start and bill.billing_period_end:
        try:
            s, e = date.fromisoformat(bill.billing_period_start), date.fromisoformat(bill.billing_period_end)
            if e >= s:
                return s, date.fromordinal(e.toordinal() + 1), "dates"     # bill end date is inclusive
        except ValueError:
            pass
    if bill.billing_month and bill.billing_year:
        s = date(bill.billing_year, bill.billing_month, cycle_day)
        return s, _add_month(s), "cycle"
    raise ValueError("This bill has no billing period (month/year or start/end dates).")


def bill_breakdown(db: Session, bill) -> dict:
    """
    A recorded bill vs what SHEM recorded in its period: the split per appliance (fixed charge, rest of
    home) and the billed vs recorded kWh per day (over the hours SHEM was recording, so partial coverage
    still compares fairly).
    """
    from app.services.insights_service import _usage

    t = load_tariff(db)
    start_d, end_d, source = bill_period(bill, t.cycle_day)
    start, end = cycle_instants(start_d, end_d)
    now = utcnow()
    u = _usage(db, settings.device_id, start, min(end, now))
    total = bill.bill_amount_inr
    fixed = min(t.fixed_charge, total)
    alloc = allocate(u, bill.units_consumed_kwh, total - fixed, total)

    period_h = max((min(end, now) - start).total_seconds() / 3600.0, 0.0)
    covered_h = len(u.hours)
    coverage = covered_h / period_h * 100 if period_h > 0 else 0.0
    period_days = (end - start).total_seconds() / 86400.0
    billed_daily = bill.units_consumed_kwh / period_days if period_days > 0 else None
    recorded_daily = alloc["measured_kwh"] / covered_h * 24 if covered_h >= 6 and alloc["measured_kwh"] > 0 else None
    variance = (recorded_daily - billed_daily) / billed_daily * 100 if recorded_daily and billed_daily else None

    notes = []
    if not alloc["appliances"]:
        notes.append("SHEM has no metered or simulated usage in this period, so the bill can't be split by appliance.")
    elif alloc["scale"] < 1.0:
        notes.append(f"SHEM recorded {alloc['measured_kwh']:.1f} kWh but the bill has {bill.units_consumed_kwh:g} kWh; "
                     "shares are scaled to the billed units (simulated devices aren't on the real meter).")
    if coverage < 90 and alloc["appliances"]:
        notes.append(f"Usage was recorded for {coverage:.0f}% of the period, so the split covers only that time.")
    return {
        "period_start": start_d, "period_end": end_d, "period_source": source, "fixed": fixed,
        "period_days": period_days, "covered_hours": covered_h, "coverage_percent": min(100.0, coverage),
        "billed_daily": billed_daily, "recorded_daily": recorded_daily, "variance_percent": variance,
        "notes": notes, "usage": u, **alloc,
    }


def projected_appliance_costs(proj: dict) -> List[ApplianceShare]:
    """Projected bill per appliance: each appliance's cycle-to-date kWh share of the projected usage charges."""
    b: BillBreakdown = proj["projected"]
    variable_total = b.total - b.fixed_charge
    items = appliance_kwh(proj["usage"])
    used = sum(v for _, v in items)
    out = []
    for key, kwh in items:
        m = proj["usage"].meta[key]
        cost = variable_total * kwh / used if used > 0 else 0.0
        out.append(ApplianceShare(key, m.name, m.icon_type, m.source, round(kwh, 4),
                                  round(cost / b.total * 100, 1) if b.total > 0 else 0.0, round(cost, 2)))
    return out
