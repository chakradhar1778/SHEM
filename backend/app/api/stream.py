"""
SHEM Backend — WS /api/stream?api_key=<key>

On connect: `init_snapshot` {serverTime, deviceStatus, latestTelemetry, relayStatus, simStatus}
Then pushed: telemetry (~2 s), sim_update (2 s), device_status, relay_state, relay_update, heartbeat (5 s).
The client may send the text "ping" and receives a `pong` event.
Unauthenticated connections are refused (HTTP 403 / close code 1008).
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.config import get_settings
from app.database import SessionLocal
from app.services.broadcaster import broadcaster
from app.services.device_service import get_device_status
from app.services.relay_service import get_relay_status
from app.services.simulation_service import simulator
from app.services.telemetry_service import get_latest_telemetry
from app.utils.security import websocket_authorized
from app.utils.timestamps import utcnow_iso

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _snapshot(mqtt_connected: bool) -> dict:
    with SessionLocal() as db:
        return {
            "serverTime": utcnow_iso(),
            "deviceStatus": get_device_status(db, settings.device_id, mqtt_connected).model_dump(mode="json"),
            "latestTelemetry": get_latest_telemetry(db, settings.device_id).model_dump(mode="json"),
            "relayStatus": get_relay_status(db, settings.device_id, 1).model_dump(mode="json"),
            "simStatus": simulator.tick(db) if settings.simulation_enabled else simulator.last_payload,
        }


@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    if not websocket_authorized(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await broadcaster.connect(websocket)
    try:
        mqtt_client = getattr(websocket.app.state, "mqtt_client", None)
        snapshot = await asyncio.to_thread(_snapshot, bool(mqtt_client and mqtt_client.connected))
        await broadcaster.send_to(websocket, "init_snapshot", snapshot)
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await broadcaster.send_to(websocket, "pong", {"serverTime": utcnow_iso()})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("WebSocket closed: %s", exc)
    finally:
        broadcaster.disconnect(websocket)
