"""
SHEM Backend — Background maintenance loops

fast loop (every HEARTBEAT_INTERVAL_SECONDS, default 5 s)
  * mark expired relay commands as timeout → `relay_update` events
  * mark stale devices offline            → `device_status` events
  * MQTT connect/disconnect changes       → `device_status` events
  * `heartbeat` event {serverTime, mqttConnected}

slow loop (every MAINTENANCE_INTERVAL_SECONDS, default 300 s; runs once at startup)
  * roll completed hours into telemetry_hourly
  * prune raw telemetry / old events beyond retention

Database work runs in a worker thread so the event loop never blocks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI

from app.config import get_settings
from app.database import SessionLocal
from app.services.broadcaster import broadcaster
from app.services.device_service import get_device_status, mark_stale_devices
from app.services.energy_service import run_maintenance
from app.services.relay_service import check_and_mark_timeouts
from app.utils.timestamps import utcnow_iso

logger = logging.getLogger(__name__)
settings = get_settings()


def _mqtt_connected(app: FastAPI) -> bool:
    client = getattr(app.state, "mqtt_client", None)
    return bool(client and client.connected)


def _fast_db_work(mqtt_connected: bool) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    with SessionLocal() as db:
        timed_out = [c.model_dump(mode="json") for c in check_and_mark_timeouts(db)]
        stale = mark_stale_devices(db)
        status = None
        if stale:
            status = get_device_status(db, settings.device_id, mqtt_connected).model_dump(mode="json")
        return timed_out, status


def _device_status_dict(mqtt_connected: bool) -> Dict[str, Any]:
    with SessionLocal() as db:
        return get_device_status(db, settings.device_id, mqtt_connected).model_dump(mode="json")


async def fast_loop(app: FastAPI) -> None:
    last_mqtt: Optional[bool] = None
    while True:
        try:
            mqtt = _mqtt_connected(app)
            timed_out, status = await asyncio.to_thread(_fast_db_work, mqtt)
            for cmd in timed_out:
                await broadcaster.broadcast("relay_update", cmd)
            if status is None and last_mqtt is not None and mqtt != last_mqtt:
                status = await asyncio.to_thread(_device_status_dict, mqtt)
            if status is not None:
                await broadcaster.broadcast("device_status", status)
            last_mqtt = mqtt
            await broadcaster.broadcast("heartbeat", {"serverTime": utcnow_iso(), "mqttConnected": mqtt})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fast maintenance loop error")
        await asyncio.sleep(settings.heartbeat_interval_seconds)


def _slow_db_work() -> Dict[str, int]:
    with SessionLocal() as db:
        return run_maintenance(db, settings.device_id)


async def slow_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_slow_db_work)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Rollup/retention job error")
        await asyncio.sleep(settings.maintenance_interval_seconds)


def start_background_tasks(app: FastAPI) -> List[asyncio.Task]:
    return [
        asyncio.create_task(fast_loop(app), name="shem-fast-loop"),
        asyncio.create_task(slow_loop(), name="shem-slow-loop"),
    ]
