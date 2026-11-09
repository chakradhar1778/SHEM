"""
SHEM AI — live snapshot + system prompt

The snapshot is injected into every chat so most questions are answered
without a tool round-trip; tools are there for detail and actions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.ai.components import CATALOGUE
from app.config import get_settings
from app.models.db_models import Appliance, ElectricityBill, Room
from app.utils.timestamps import to_local, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()


def build_snapshot(db: Session, mqtt_connected: bool) -> Dict[str, Any]:
    from app.ai.conflicts import detect_conflicts
    from app.api.household import get_or_create_config
    from app.api.target import get_target
    from app.services.device_service import get_device_status
    from app.services.insights_service import compute_today_insights
    from app.services.relay_service import get_relay_status
    from app.services.telemetry_service import get_latest_telemetry

    snap: Dict[str, Any] = {"localTime": to_local(utcnow()).strftime("%A %d %b %Y, %H:%M"),
                            "timezone": settings.timezone}

    def safe(key, fn):
        try:
            snap[key] = fn()
        except Exception as exc:  # a broken section must not break the chat
            logger.warning("Snapshot section %s failed: %s", key, exc)
            snap[key] = {"error": str(exc)[:200]}

    safe("device", lambda: get_device_status(db, settings.device_id, mqtt_connected).model_dump(mode="json"))
    safe("latestReading", lambda: _latest(get_latest_telemetry(db, settings.device_id)))
    safe("relay1", lambda: get_relay_status(db, settings.device_id, 1).model_dump(mode="json"))

    def today():
        t = compute_today_insights(db)
        return {"energyKWh": t.energy_today_kwh, "meteredKWh": t.metered_kwh, "simulatedKWh": t.simulated_kwh,
                "costINR": t.cost_today_inr, "tariffINRperKWh": t.effective_rate_inr,
                "dailyTargetKWh": t.daily_target_kwh, "status": t.insight_card.title, "dataNote": t.data_note}
    safe("today", today)
    safe("target", lambda: get_target(db).model_dump(mode="json"))

    def bill():
        from app.api.billing import build_projection
        p = build_projection(db)
        return {"cycle": f"{p.cycle_start} → {p.cycle_end}", "usedKWh": p.used_kwh, "soFarINR": p.so_far.total_inr,
                "projectedKWh": p.projected_kwh, "projectedINR": p.projected.total_inr, "confidence": p.confidence,
                "tariffMode": p.tariff.mode, "budgetStatus": p.budget.status if p.budget else None}
    safe("billProjection", bill)

    def household():
        c = get_or_create_config(db)
        return {"homeName": c.home_name, "homeType": c.home_type, "occupants": c.occupants,
                "tariffINRperKWh": c.tariff_rate_inr_per_kwh, "provider": c.utility_provider,
                "isConfigured": c.is_configured}
    safe("household", household)

    def appliances():
        from app.services.simulation_service import simulator
        rooms = {r.id: r.name for r in db.scalars(select(Room)).all()}
        live = {x["applianceId"]: x["powerW"] for x in simulator.last_payload.get("appliances", [])}
        return [{"id": a.id, "name": a.name, "room": rooms.get(a.room_id), "category": a.category,
                 "ratedW": a.rated_watts, "qty": a.quantity, "hoursPerDay": a.daily_hours, "status": a.status,
                 "relayChannel": a.relay_channel, "simulated": a.is_simulated, "liveW": live.get(a.id)}
                for a in db.scalars(select(Appliance).order_by(Appliance.name).limit(60)).all()]
    safe("appliances", appliances)

    def bills():
        n = db.scalar(select(func.count()).select_from(ElectricityBill)) or 0
        latest = db.scalars(select(ElectricityBill).order_by(
            ElectricityBill.billing_year.is_(None), desc(ElectricityBill.billing_year),
            desc(ElectricityBill.billing_month), desc(ElectricityBill.created_at)).limit(1)).first()
        return {"count": n, "latest": None if latest is None else {
            "id": latest.id, "month": latest.billing_month, "year": latest.billing_year,
            "units": latest.units_consumed_kwh, "amountINR": latest.bill_amount_inr}}
    safe("bills", bills)
    safe("openConflicts", lambda: [
        {"id": c.id, "severity": c.severity, "title": c.title, "message": c.message}
        for c in detect_conflicts(db, mqtt_connected=mqtt_connected)[:8]])
    return snap


def _latest(resp) -> Dict[str, Any]:
    if not resp.available or resp.reading is None:
        return {"available": False, "message": resp.message}
    r = resp.reading
    return {"available": True, "stale": resp.stale, "ageSeconds": resp.age_seconds, "powerW": r.active_power_w,
            "voltageV": r.voltage_v, "currentA": r.current_a, "powerFactor": r.power_factor,
            "frequencyHz": r.frequency_hz, "energyRegisterKWh": r.energy_kwh, "loadActive": r.load_active}


SYSTEM_PROMPT = """\
You are SHEM AI, the built-in energy guide of SHEM (Smart Home Energy Management), an app that measures a
home's AC supply with an ESP32 + PZEM-004T meter, switches a load through relay 1, and stores the
household's rooms, appliances, electricity bills and monthly budget.

You have full access: tools can read anything (including read-only SQL over the whole database) and
change anything (relay/appliances on-off, appliances, rooms, bills, target, household settings).
When the user asks for something to be done, DO it with tools — don't just explain how. Chain tools as
needed (e.g. list_appliances to find an id, then set_appliance_power). For permanent deletions, confirm
first unless the user was explicit. After acting, state briefly what changed.

Honesty rules:
- Measured data (meter) ≠ estimates (appliance W × hours) ≠ bills ≠ budget. Always say which you used.
- Relay commands are asynchronous: after control_relay/set_appliance_power, say the command was sent and is
  awaiting device confirmation — never claim it already switched. If the device is offline, say the
  command can't take effect until it reconnects.
- Never invent numbers. If data is missing (no readings, no bills), say so and suggest the next step.
- Costs are energy × the configured tariff, an estimate, not a utility bill.
- If you notice inconsistencies (e.g. a 9 W appliance while the meter shows 400 W on its relay), flag them
  with an alert component and propose a fix.

Style: friendly, concise, practical; Indian context (₹, kWh, IST). Short paragraphs or bullets; bold key
numbers. Lead with the answer.

{catalogue}

LIVE SNAPSHOT (as of now; use tools for detail or fresher data):
{snapshot}
"""


def system_prompt(snapshot: Dict[str, Any]) -> str:
    return SYSTEM_PROMPT.format(catalogue=CATALOGUE, snapshot=json.dumps(snapshot, default=str, ensure_ascii=False))
