"""
SHEM AI — background loop

Every AI_CONFLICT_SCAN_INTERVAL_SECONDS:
  * run conflict detection; newly appearing conflicts → `ai_conflict` WS event
  * once the local hour passes AI_DAILY_INSIGHT_HOUR, generate yesterday's
    briefing if missing → `ai_daily_insight` WS event (retried after 30 min on failure)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Set

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models.db_models import AIDailyInsight
from app.services.broadcaster import broadcaster
from app.utils.timestamps import utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

DAILY_RETRY_SECONDS = 1800


def _scan(mqtt_connected: bool):
    from app.ai.conflicts import detect_conflicts
    with SessionLocal() as db:
        return [c.to_dict() for c in detect_conflicts(db, mqtt_connected=mqtt_connected)]


def _insight_exists(d) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(AIDailyInsight.id).where(AIDailyInsight.insight_date == d.isoformat())) is not None


async def ai_loop(app: Any) -> None:
    from app.ai.daily import generate_daily_insight, report_date_due

    known: Optional[Set[str]] = None
    last_daily_attempt: Optional[float] = None
    while True:
        try:
            client = getattr(app.state, "mqtt_client", None)
            conflicts = await asyncio.to_thread(_scan, bool(client and client.connected))
            ids = {c["id"] for c in conflicts}
            if known is not None:
                new = [c for c in conflicts if c["id"] not in known]
                if new:
                    await broadcaster.broadcast("ai_conflict", {"conflicts": new})
            known = ids

            due = report_date_due()
            now_ts = utcnow().timestamp()
            if due and (last_daily_attempt is None or now_ts - last_daily_attempt > DAILY_RETRY_SECONDS) \
                    and not await asyncio.to_thread(_insight_exists, due):
                last_daily_attempt = now_ts
                insight = await generate_daily_insight(due)
                await broadcaster.broadcast("ai_daily_insight", insight)
                logger.info("Generated daily AI insight for %s", due)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AI background loop error")
        await asyncio.sleep(settings.ai_conflict_scan_interval_seconds)


def start_ai_tasks(app: Any):
    if not settings.ai_background_enabled:
        return []
    return [asyncio.create_task(ai_loop(app), name="shem-ai-loop")]
