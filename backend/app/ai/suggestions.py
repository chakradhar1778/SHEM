"""
SHEM AI — conversation starters (rule-based from live state; no LLM call, instant)
and fallback follow-ups when the model doesn't provide any.
"""

from __future__ import annotations

from typing import Dict, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.db_models import Appliance, ElectricityBill
from app.services.insights_service import _target


def _s(label: str, prompt: str, icon: str) -> Dict[str, str]:
    return {"label": label, "prompt": prompt, "icon": icon}


def starter_suggestions(db: Session, mqtt_connected: bool = True, limit: int = 6) -> List[Dict[str, str]]:
    from app.ai.conflicts import detect_conflicts

    out: List[Dict[str, str]] = []
    conflicts = detect_conflicts(db, mqtt_connected=mqtt_connected)
    serious = [c for c in conflicts if c.severity in ("warning", "critical")]
    if serious:
        out.append(_s(f"Explain {len(serious)} flagged issue{'s' if len(serious) > 1 else ''}",
                      "Explain the issues SHEM has flagged and how to fix each one.", "alert"))
    out.append(_s("Today's usage", "How much energy have I used today and what did it cost?", "bolt"))

    configured, _ = _target(db)
    if configured:
        out.append(_s("Am I on budget?", "Am I on track for my monthly budget? Show my progress.", "target"))
    else:
        out.append(_s("Set a monthly budget", "Help me set a realistic monthly electricity budget.", "target"))

    linked = db.scalar(select(Appliance).where(Appliance.relay_channel.is_not(None)).limit(1))
    if linked is not None:
        verb = "off" if (linked.status or "").lower() == "on" else "on"
        out.append(_s(f"Turn {linked.name} {verb}", f"Turn {verb} the {linked.name}.", "power"))

    if not db.scalar(select(func.count()).select_from(ElectricityBill)):
        out.append(_s("Add my electricity bill", "I want to add my latest electricity bill.", "bill"))
    else:
        out.append(_s("Compare with my bill", "How does my measured usage compare with my latest bill?", "bill"))

    if not db.scalar(select(func.count()).select_from(Appliance)):
        out.append(_s("Set up my appliances", "Help me add the appliances in my home.", "home"))

    out.append(_s("This week's trend", "Show my energy trend for this week and the peak hours.", "chart"))
    out.append(_s("Ways to save", "Give me the 3 most effective ways to cut my electricity bill.", "tips"))
    return out[:limit]


def fallback_followups(db: Session) -> List[str]:
    return [s["prompt"] for s in starter_suggestions(db, limit=4)[1:4]]
