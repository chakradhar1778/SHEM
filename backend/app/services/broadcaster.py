"""
SHEM Backend — WebSocket Broadcaster

MQTT messages arrive on Paho's network thread, which has no asyncio loop.
The broadcaster is bound to the FastAPI event loop at startup and
`publish_from_thread()` schedules sends onto that loop safely.

Message envelope: {"type": <event>, "data": {...}, "sentAt": "<UTC ISO>"}
Events: init_snapshot, telemetry, sim_update, device_status, relay_state,
        relay_update, heartbeat, pong
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import WebSocket

from app.utils.timestamps import utcnow_iso

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 5.0


class WebSocketBroadcaster:
    def __init__(self) -> None:
        # Mutated only on the event-loop thread.
        self._clients: Dict[WebSocket, asyncio.Lock] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients[websocket] = asyncio.Lock()
        logger.info("WebSocket client connected (%d active)", len(self._clients))

    def disconnect(self, websocket: WebSocket) -> None:
        if self._clients.pop(websocket, None) is not None:
            logger.info("WebSocket client disconnected (%d active)", len(self._clients))

    @staticmethod
    def _envelope(event_type: str, data: Dict[str, Any]) -> str:
        return json.dumps({"type": event_type, "data": data, "sentAt": utcnow_iso()})

    async def _send(self, websocket: WebSocket, message: str) -> bool:
        lock = self._clients.get(websocket)
        if lock is None:
            return False
        try:
            async with lock:  # serialise concurrent sends to one socket
                await asyncio.wait_for(websocket.send_text(message), SEND_TIMEOUT_SECONDS)
            return True
        except Exception as exc:
            logger.debug("WebSocket send failed, dropping client: %s", exc)
            return False

    async def send_to(self, websocket: WebSocket, event_type: str, data: Dict[str, Any]) -> bool:
        ok = await self._send(websocket, self._envelope(event_type, data))
        if not ok:
            self.disconnect(websocket)
        return ok

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        if not self._clients:
            return
        message = self._envelope(event_type, data)
        clients = list(self._clients)
        results = await asyncio.gather(*(self._send(ws, message) for ws in clients))
        for ws, ok in zip(clients, results):
            if not ok:
                self.disconnect(ws)

    def publish_from_thread(self, event_type: str, data: Dict[str, Any]) -> None:
        """Thread-safe: schedule a broadcast from any thread (e.g. Paho callbacks)."""
        loop = self._loop
        if loop is None or loop.is_closed() or not self._clients:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        coro = self.broadcast(event_type, data)
        if running is loop:
            loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, loop)


broadcaster = WebSocketBroadcaster()
