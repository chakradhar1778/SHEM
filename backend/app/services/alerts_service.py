"""
SHEM Backend — Alerts (notification bell) and the opt-in budget saver

Checks run every ALERTS_INTERVAL_SECONDS (and on demand). Each alert has a
dedupe key, so it fires once (per bill, per billing cycle, per slab …):

  * bill due in ≤ 3 days / due date passed (≤ 7 days ago)     — any location
  * budget 80 % and 100 % used this billing cycle               — tariff-priced, metered + simulated
  * projected bill above budget (≥ 3 days into the cycle)
  * about to enter a higher slab / entered a higher slab        — slab tariffs
  * a recent bill that disagrees (≥ 30 %/day) with recorded usage — this home's bills only

Budget saver (EnergyTarget.saver_mode):
  off      — nothing
  suggest  — one notification per cycle listing non-essential appliances that are on
  auto     — switches those appliances off (simulator or relay), logs why, notifies.
             An appliance is switched off at most once per 24 h, so if you turn it
             back on, the saver respects that until the next day.
Only appliances marked Essential = "No" are ever touched ("Not sure" is left alone).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.db_models import Appliance, AutomationLog, ElectricityBill, EnergyTarget, Notification, RelayChannel
from app.services import billing_service as bs
from app.utils.timestamps import to_local, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

DUE_SOON_DAYS = 3
OVERDUE_WINDOW_DAYS = 7
MISMATCH_PERCENT = 30.0
MISMATCH_RECENT_DAYS = 60
SAVER_COOLDOWN = timedelta(hours=24)


# ── helpers ────────────────────────────────────────────────────────────────────

def notify(db: Session, key: str, kind: str, severity: str, title: str, message: str,
           link: Optional[str] = None) -> Optional[Notification]:
    """Create the notification unless one with this key already exists."""
    if db.scalar(select(Notification.id).where(Notification.dedupe_key == key)) is not None:
        return None
    n = Notification(dedupe_key=key[:160], kind=kind, severity=severity, title=title[:200], message=message,
                     link=link, created_at=utcnow())
    db.add(n)
    try:
        db.commit()
    except IntegrityError:          # raced with another check
        db.rollback()
        return None
    db.refresh(n)
    return n


def _location_label(tag: Optional[str]) -> str:
    return {"parents_home": "Parents’ home", "office": "Office"}.get(tag or "", tag or "")


def _parse_iso(value: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def _inr(v: float) -> str:
    return f"₹{v:,.0f}"


# ── checks ─────────────────────────────────────────────────────────────────────

def _bill_due(db: Session, today: date) -> List[Notification]:
    out = []
    for b in db.scalars(select(ElectricityBill)).all():
        due = _parse_iso(b.due_date)
        if due is None:
            continue
        days = (due - today).days
        where = "" if bs.is_home_bill(b) else f" ({_location_label(b.location_tag)})"
        label = b.billing_period or "Your electricity bill"
        if 0 <= days <= DUE_SOON_DAYS:
            when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
            n = notify(db, f"bill-due:{b.id}", "bill_due", "warning", f"Bill due {when}{where}",
                       f"{label}: {_inr(b.bill_amount_inr)} is due on {due:%d %b}.", "/bill")
        elif -OVERDUE_WINDOW_DAYS <= days < 0:
            n = notify(db, f"bill-overdue:{b.id}", "bill_due", "critical", f"Bill due date passed{where}",
                       f"{label}: {_inr(b.bill_amount_inr)} was due on {due:%d %b}. Pay it soon to avoid a late fee.",
                       "/bill")
        else:
            n = None
        if n:
            out.append(n)
    return out


def _budget(db: Session, proj: dict, budget: Optional[dict]) -> List[Notification]:
    if not budget:
        return []
    cycle = proj["cycle_start"].isoformat()
    out = []
    pct = budget["used_percent"]
    if pct >= 100:
        n = notify(db, f"budget-100:{cycle}", "budget", "critical", "Budget used up",
                   f"{_inr(budget['spent_inr'])} used this billing cycle — your {_inr(budget['budget_inr'])} budget is "
                   f"spent with {proj['total_days'] - proj['elapsed_days']:.0f} days to go.", "/target")
    elif pct >= 80:
        n = notify(db, f"budget-80:{cycle}", "budget", "warning", "80% of your budget used",
                   f"{_inr(budget['spent_inr'])} of {_inr(budget['budget_inr'])} used this billing cycle.", "/target")
    else:
        n = None
    if n:
        out.append(n)
    if budget["status"] == "at_risk" and proj["elapsed_days"] >= 3 and proj["confidence"] != "low":
        n = notify(db, f"budget-projected:{cycle}", "budget", "warning", "Projected bill above budget",
                   f"At the current pace this cycle's bill will be about {_inr(budget['projected_inr'])}, "
                   f"{_inr(budget['projected_over_inr'])} over your budget.", "/bill")
        if n:
            out.append(n)
    return out


def _slab(db: Session, proj: dict) -> List[Notification]:
    t: bs.Tariff = proj["tariff"]
    if t.mode != "slab":
        return []
    b: bs.BillBreakdown = proj["so_far"]
    cycle = proj["cycle_start"].isoformat()
    out = []
    idx = b.slab_index
    if idx > 0:
        line = b.lines[idx]
        n = notify(db, f"slab-entered:{cycle}:{idx}", "slab", "info", "You've entered a higher slab",
                   f"This cycle is now in the {line.label} slab: each extra kWh costs ₹{line.rate:g} "
                   f"(plus fuel and duty).", "/bill")
        if n:
            out.append(n)
    if b.kwh_to_next_slab is not None and b.next_slab_rate is not None:
        cur = b.lines[idx]
        width = (cur.to_kwh - cur.from_kwh) if cur.to_kwh is not None else None
        near = max(5.0, 0.1 * width) if width else 5.0
        if b.kwh_to_next_slab <= near:
            n = notify(db, f"slab-near:{cycle}:{idx + 1}", "slab", "warning", "About to enter a higher slab",
                       f"{b.kwh_to_next_slab:.1f} kWh left before units cost ₹{b.next_slab_rate:g}/kWh "
                       f"(now ₹{cur.rate:g}).", "/bill")
            if n:
                out.append(n)
    return out


def _bill_mismatch(db: Session) -> List[Notification]:
    out = []
    since = utcnow() - timedelta(days=MISMATCH_RECENT_DAYS)
    for b in db.scalars(select(ElectricityBill).where(ElectricityBill.created_at >= since)).all():
        if not bs.is_home_bill(b):
            continue
        try:
            r = bs.bill_breakdown(db, b)
        except ValueError:
            continue
        v = r["variance_percent"]
        if v is None or r["covered_hours"] < 24 or abs(v) < MISMATCH_PERCENT:
            continue
        more = "more" if v > 0 else "less"
        n = notify(db, f"bill-mismatch:{b.id}", "bill_mismatch", "info", "Bill and recorded usage disagree",
                   f"{b.billing_period or 'A recent bill'}: SHEM recorded {abs(v):.0f}% {more} per day than the bill "
                   f"({r['recorded_daily']:.1f} vs {r['billed_daily']:.1f} kWh/day). Check the units on the bill, or "
                   "the appliances SHEM simulates.", "/bill")
        if n:
            out.append(n)
    return out


# ── budget saver ───────────────────────────────────────────────────────────────

def _is_on(db: Session, a: Appliance) -> bool:
    if a.relay_channel is None:
        return (a.status or "").lower() == "on"
    rc = db.scalar(select(RelayChannel).where(RelayChannel.channel == a.relay_channel))
    return bool(rc and rc.commanded_state == "ON")


def saver_candidates(db: Session) -> List[Appliance]:
    """Appliances the saver may switch off: Essential = No."""
    return list(db.scalars(select(Appliance).where(Appliance.is_essential == "no").order_by(Appliance.name)).all())


def _log(db: Session, a: Optional[Appliance], action: str, reason: str, cycle: str) -> None:
    db.add(AutomationLog(appliance_id=a.id if a else None, appliance_name=a.name if a else None, action=action,
                         reason=reason, cycle_start=cycle, created_at=utcnow()))
    db.commit()


def run_budget_saver(db: Session, proj: dict, budget: Optional[dict], mqtt_client: Any = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"notifications": [], "switched": [], "sim_changed": False}
    target = db.get(EnergyTarget, 1)
    if not target or (target.saver_mode or "off") == "off" or not budget:
        return result
    status = budget["status"]
    triggered = status == "over" or (target.saver_trigger == "at_risk" and status == "at_risk"
                                     and proj["elapsed_days"] >= 1)
    if not triggered:
        return result
    cycle = proj["cycle_start"].isoformat()
    on = [a for a in saver_candidates(db) if _is_on(db, a)]
    if not on:
        return result
    why = (f"bill so far {_inr(budget['spent_inr'])} is over the {_inr(budget['budget_inr'])} budget" if status == "over"
           else f"projected bill {_inr(budget['projected_inr'])} is above the {_inr(budget['budget_inr'])} budget")

    if target.saver_mode == "suggest":
        names = ", ".join(a.name for a in on)
        n = notify(db, f"saver-suggest:{cycle}:{status}", "saver", "warning", "Switch off non-essential appliances?",
                   f"Your {why}. These non-essential appliances are on: {names}.", "/live")
        if n:
            result["notifications"].append(n)
            _log(db, None, "suggested", f"Suggested switching off {names}: {why}.", cycle)
        return result

    now = utcnow()
    from app.services.simulation_service import simulator
    for a in on:
        recent = db.scalar(select(AutomationLog.id).where(
            AutomationLog.appliance_id == a.id, AutomationLog.action == "switched_off",
            AutomationLog.created_at >= now - SAVER_COOLDOWN))
        if recent is not None:
            continue          # already switched off today; the user turned it back on — respect that
        try:
            if a.relay_channel is None:
                simulator.command(db, a, "OFF")
                result["sim_changed"] = True
            else:
                if mqtt_client is None or not getattr(mqtt_client, "connected", False):
                    _log(db, a, "failed", f"Couldn't switch off {a.name}: the relay is not reachable (MQTT offline).", cycle)
                    continue
                from app.mqtt.publisher import publish_relay_command
                ok, _ = publish_relay_command(mqtt_client, db, settings.device_id, a.relay_channel, "OFF")
                if not ok:
                    _log(db, a, "failed", f"Couldn't publish the relay OFF command for {a.name}.", cycle)
                    continue
        except Exception as exc:  # never let one appliance stop the rest
            logger.exception("Budget saver failed for %s", a.name)
            _log(db, a, "failed", f"Couldn't switch off {a.name}: {exc}", cycle)
            continue
        _log(db, a, "switched_off", f"Switched off {a.name} (non-essential): {why}.", cycle)
        result["switched"].append(a.name)
        n = notify(db, f"saver-off:{a.id}:{to_local(now):%Y-%m-%d}", "saver", "success",
                   f"Budget saver switched off {a.name}",
                   f"Your {why}. {a.name} is marked non-essential, so SHEM switched it off. Turn it back on any "
                   "time — the saver won't switch it off again today.", "/live")
        if n:
            result["notifications"].append(n)
    return result


# ── entry point ────────────────────────────────────────────────────────────────

def run_checks(db: Session, mqtt_client: Any = None) -> Dict[str, Any]:
    now = utcnow()
    new: List[Notification] = []
    new += _bill_due(db, to_local(now).date())
    proj = bs.project_cycle(db, now=now)
    budget = bs.budget_status(db, proj)
    new += _budget(db, proj, budget)
    new += _slab(db, proj)
    new += _bill_mismatch(db)
    saver = run_budget_saver(db, proj, budget, mqtt_client)
    new += saver["notifications"]
    return {"notifications": new, "saver": saver}


def _check_once(app) -> Dict[str, Any]:
    from app.database import SessionLocal
    with SessionLocal() as db:
        out = run_checks(db, getattr(app.state, "mqtt_client", None))
        out["notifications"] = [notification_dict(n) for n in out["notifications"]]
        if out["saver"]["sim_changed"]:
            from app.services.simulation_service import simulator
            out["sim_payload"] = simulator.last_payload
        return out


def notification_dict(n: Notification) -> Dict[str, Any]:
    from app.models.schemas import NotificationSchema
    return NotificationSchema.model_validate(n).model_dump(mode="json")


async def alerts_loop(app) -> None:
    import asyncio

    from app.services.broadcaster import broadcaster
    await asyncio.sleep(5)            # let MQTT connect and the simulator tick first
    while True:
        try:
            out = await asyncio.to_thread(_check_once, app)
            for n in out["notifications"]:
                await broadcaster.broadcast("notification", n)
            if out.get("sim_payload"):
                await broadcaster.broadcast("sim_update", out["sim_payload"])
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Alert checks failed")
        await asyncio.sleep(settings.alerts_interval_seconds)
