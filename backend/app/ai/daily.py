"""
SHEM AI — Daily insights

For a local date D, gather measured facts (energy, cost, peak hour, vs the
7-day average, budget pace, conflicts, recommendations). Deterministic
components (metric cards + hourly chart) are always built from those facts;
the LLM only writes the narrative and tips. Without a provider (or if it
fails) a rule-based narrative is used, so the feature always works.
"""

from __future__ import annotations

import json
import logging
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.components import parse_text
from app.ai.providers import AllProvidersFailed, get_router
from app.config import get_settings
from app.database import SessionLocal
from app.models.db_models import AIDailyInsight
from app.services.energy_service import hourly_stats
from app.services.insights_service import _target, _tariff
from app.utils.timestamps import DAY, from_local, hour_label, local_month_start, to_iso, to_local, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()


def _day_bounds(d: date):
    start = from_local(datetime(d.year, d.month, d.day))
    return start, from_local(datetime.combine(d + timedelta(days=1), datetime.min.time()))


def gather_day_facts(db: Session, d: date) -> Dict[str, Any]:
    from app.ai.conflicts import detect_conflicts
    from app.services.insights_service import compute_recommendations

    device = settings.device_id
    now = utcnow()
    start, end = _day_bounds(d)
    end_eff = min(end, now)
    tariff = _tariff(db)
    stats = hourly_stats(db, device, start, end_eff) if end_eff > start else {}
    by_hour: Dict[int, float] = {}
    max_w: Optional[float] = None
    for t, s in stats.items():
        h = to_local(t).hour
        by_hour[h] = by_hour.get(h, 0.0) + s.energy_kwh
        if s.power_max is not None:
            max_w = s.power_max if max_w is None else max(max_w, s.power_max)
    total = sum(by_hour.values())
    peak_hour = max(by_hour, key=by_hour.get) if by_hour and total > 0 else None

    prev = hourly_stats(db, device, start - 7 * DAY, start)
    prev_days = {to_local(t).date() for t in prev}
    prev_avg = (sum(s.energy_kwh for s in prev.values()) / len(prev_days)) if prev_days else None

    configured, budget = _target(db)
    month0 = local_month_start(end_eff if end_eff > start else start)
    mtd_kwh = sum(s.energy_kwh for s in hourly_stats(db, device, month0, end_eff).values()) if end_eff > month0 else 0
    loc = to_local(start)
    dim = monthrange(loc.year, loc.month)[1]
    daily_budget_kwh = (budget / tariff / dim) if configured and budget else None

    facts: Dict[str, Any] = {
        "date": d.isoformat(), "weekday": d.strftime("%A"), "partialDay": end > now,
        "measuredHours": len(stats), "energyKWh": round(total, 3), "costINR": round(total * tariff, 2),
        "tariffINRperKWh": tariff, "peakHour": hour_label(peak_hour) if peak_hour is not None else None,
        "peakHourKWh": round(by_hour[peak_hour], 3) if peak_hour is not None else None,
        "maxPowerW": round(max_w, 1) if max_w is not None else None,
        "hourly": [{"hour": hour_label(h), "kWh": round(by_hour.get(h, 0.0), 4)} for h in range(24)],
        "prev7DayAvgKWh": round(prev_avg, 3) if prev_avg is not None else None,
        "vsAvgPct": round((total - prev_avg) / prev_avg * 100, 1) if prev_avg and prev_avg > 0 and stats else None,
        "budgetINR": budget if configured else None,
        "dailyBudgetKWh": round(daily_budget_kwh, 3) if daily_budget_kwh else None,
        "monthToDateKWh": round(mtd_kwh, 3), "monthToDateCostINR": round(mtd_kwh * tariff, 2),
    }
    try:
        facts["conflicts"] = [{"id": c.id, "severity": c.severity, "title": c.title, "message": c.message}
                              for c in detect_conflicts(db)[:5]]
    except Exception:
        facts["conflicts"] = []
    try:
        facts["recommendations"] = [{"title": r.title, "evidence": r.evidence}
                                    for r in compute_recommendations(db)[:3]]
    except Exception:
        facts["recommendations"] = []
    return facts


def _fixed_components(f: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not f["measuredHours"]:
        return []
    items = [{"label": "Energy", "value": f["energyKWh"], "unit": "kWh"},
             {"label": "Est. cost", "value": f["costINR"], "unit": "₹"}]
    if f["vsAvgPct"] is not None:
        up = f["vsAvgPct"] > 0
        items.append({"label": "vs 7-day avg", "value": f"{f['vsAvgPct']:+.0f}%",
                      "trend": "up" if up else "down", "tone": "warn" if up else "good"})
    if f["peakHour"]:
        items.append({"label": "Peak hour", "value": f["peakHour"], "delta": f"{f['peakHourKWh']} kWh"})
    comps: List[Dict[str, Any]] = [{"type": "metric_cards", "items": items}]
    comps.append({"type": "chart", "chartType": "bar", "title": "Hourly usage", "unit": "kWh",
                  "series": [{"name": "Measured", "points": [{"x": p["hour"], "y": p["kWh"]} for p in f["hourly"]]}]})
    if f["budgetINR"] and f["dailyBudgetKWh"]:
        comps.append({"type": "progress", "label": "Day vs daily budget", "current": f["energyKWh"],
                      "target": f["dailyBudgetKWh"], "unit": "kWh",
                      "tone": "bad" if f["energyKWh"] > f["dailyBudgetKWh"] else "good"})
    return comps


def _rule_based(f: Dict[str, Any]) -> tuple[str, str]:
    if not f["measuredHours"]:
        return ("No meter readings", f"SHEM received no readings on {f['weekday']} {f['date']}. "
                                     "Check that the meter is powered and online.")
    head = f"{f['energyKWh']:.2f} kWh used (≈₹{f['costINR']:.0f})"
    lines = [f"On **{f['weekday']}** you used **{f['energyKWh']:.2f} kWh**, about **₹{f['costINR']:.0f}**."]
    if f["vsAvgPct"] is not None:
        lines.append(f"That's **{abs(f['vsAvgPct']):.0f}% {'more' if f['vsAvgPct'] > 0 else 'less'}** than "
                     f"your 7-day average of {f['prev7DayAvgKWh']:.2f} kWh.")
    if f["peakHour"]:
        lines.append(f"Usage peaked around **{f['peakHour']}** ({f['peakHourKWh']} kWh).")
    if f["dailyBudgetKWh"]:
        ok = f["energyKWh"] <= f["dailyBudgetKWh"]
        lines.append(f"{'Within' if ok else 'Over'} your daily budget of {f['dailyBudgetKWh']:.2f} kWh.")
    for c in f["conflicts"][:2]:
        lines.append(f"⚠️ {c['title']}: {c['message']}")
    return head, "\n\n".join(lines)


DAILY_PROMPT = """You write SHEM's daily energy briefing for a household in India.
Facts (measured by the meter; costs = energy × tariff, an estimate):
{facts}

Write the briefing:
- First line: a markdown heading "# <headline>" (max 8 words, specific, e.g. "# Evening AC pushed usage up 18%").
- Then 2-4 short sentences interpreting the day (compare with the 7-day average, peak, budget pace).
- Then 1-3 concrete, actionable tips grounded in these facts. You may use a ```shem-ui block of type
  "recommendations" for the tips and "alert" blocks for conflicts. Metric cards and the hourly chart are
  already shown — do not repeat them. Do NOT output a shem-followups block.
Never invent numbers not in the facts. If partialDay is true, it's the day so far."""


async def generate_daily_insight(d: date, use_llm: bool = True) -> Dict[str, Any]:
    import asyncio

    def facts_fn():
        with SessionLocal() as db:
            return gather_day_facts(db, d)
    facts = await asyncio.to_thread(facts_fn)
    fixed = _fixed_components(facts)
    headline, body = _rule_based(facts)
    provider = None
    segments: List[Dict[str, Any]] = [{"type": "text", "content": body}]

    router = get_router()
    if use_llm and router.available and facts["measuredHours"]:
        try:
            turn = await router.complete([
                {"role": "system", "content": "You are SHEM AI, a concise, practical home-energy guide."},
                {"role": "user", "content": DAILY_PROMPT.format(facts=json.dumps(facts, ensure_ascii=False))},
            ], temperature=0.5)
            text = turn.text.strip()
            first, _, rest = text.partition("\n")
            if first.startswith("#"):
                headline, text = first.lstrip("#").strip()[:200] or headline, rest
            llm_segments, _ = parse_text(text)
            if llm_segments:
                segments, provider = llm_segments, turn.provider
        except AllProvidersFailed as exc:
            logger.warning("Daily insight LLM failed, using rule-based text: %s", exc)

    content = "\n\n".join(s["content"] for s in segments if s["type"] == "text")
    all_segments = [{"type": "component", "component": c} for c in fixed] + segments

    def save():
        with SessionLocal() as db:
            row = db.scalar(select(AIDailyInsight).where(AIDailyInsight.insight_date == d.isoformat()))
            if row is None:
                row = AIDailyInsight(insight_date=d.isoformat())
                db.add(row)
            row.headline, row.content = headline, content
            row.segments_json = json.dumps(all_segments, ensure_ascii=False)
            row.facts_json = json.dumps(facts, ensure_ascii=False)
            row.provider, row.generated_at = provider, utcnow()
            db.commit()
            return insight_to_dict(row)
    return await asyncio.to_thread(save)


def insight_to_dict(row: AIDailyInsight) -> Dict[str, Any]:
    return {"date": row.insight_date, "headline": row.headline,
            "segments": json.loads(row.segments_json or "[]"), "facts": json.loads(row.facts_json or "{}"),
            "provider": row.provider, "generatedAt": to_iso(row.generated_at)}


def report_date_due(now: Optional[datetime] = None) -> Optional[date]:
    """Yesterday's date once the local clock passes AI_DAILY_INSIGHT_HOUR, else None."""
    loc = to_local(now or utcnow())
    if loc.hour < settings.ai_daily_insight_hour:
        return None
    return loc.date() - timedelta(days=1)
