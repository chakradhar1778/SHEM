"""
SHEM Backend — FastAPI Application Entry Point

Startup:
  1. Create/verify SQLite tables
  2. Bind the WebSocket broadcaster to the running event loop
  3. Start the MQTT client (TLS, auto-reconnect) and register topic handlers
  4. Start background loops (heartbeat/timeouts/staleness, rollup/retention)

The frontend never talks to EMQX — every request goes through this API.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.ai.background import start_ai_tasks
from app.api import (ai, bills, device, health, household, insights, inventory, relay, simulation, stream, target,
                     telemetry, voice_ws)
from app.config import get_settings
from app.database import init_db
from app.mqtt.client import MQTTClientManager
from app.mqtt.handlers import (
    broadcast_mqtt_state,
    handle_device_status,
    handle_relay_ack,
    handle_relay_state,
    handle_telemetry,
)
from app.services.broadcaster import broadcaster
from app.services.maintenance import start_background_tasks
from app.services.simulation_service import simulation_loop
from app.utils.rate_limit import limiter
from app.utils.security import require_api_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("SHEM Backend v%s starting", settings.app_version)
    if not settings.api_key.strip():
        if settings.allow_unauthenticated_dev:
            logger.warning("API_KEY is empty and ALLOW_UNAUTHENTICATED_DEV=true — API is OPEN (dev only!)")
        else:
            logger.error("API_KEY is empty — all protected endpoints will return 401 until it is set")

    init_db()
    broadcaster.bind_loop(asyncio.get_running_loop())

    mqtt_client = MQTTClientManager()
    mqtt_client.register_handlers(
        on_telemetry=handle_telemetry,
        on_status=handle_device_status,
        on_relay_state=handle_relay_state,
        on_relay_ack=handle_relay_ack,
    )
    mqtt_client.on_state_change = broadcast_mqtt_state
    mqtt_client.start()
    app.state.mqtt_client = mqtt_client

    tasks = start_background_tasks(app) + start_ai_tasks(app)
    if settings.simulation_enabled:
        tasks.append(asyncio.create_task(simulation_loop(), name="shem-simulation"))
    logger.info("SHEM Backend ready on %s:%s", settings.host, settings.port)

    yield

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    mqtt_client.stop()
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="SHEM — Smart Home Energy Management backend: real AC telemetry from PZEM-004T via "
                "EMQX MQTT, relay control, household data, bills, targets and insights.",
    lifespan=lifespan,
    docs_url="/docs" if settings.expose_docs else None,
    redoc_url="/redoc" if settings.expose_docs else None,
    openapi_url="/openapi.json" if settings.expose_docs else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# Public
app.include_router(health.router, prefix="/api")
# WebSocket authenticates inside the handler (?api_key=…)
app.include_router(stream.router, prefix="/api")
app.include_router(voice_ws.router, prefix="/api")
# Protected (X-API-Key)
_auth = [Depends(require_api_key)]
for module in (device, telemetry, relay, household, inventory, bills, target, insights, simulation, ai):
    app.include_router(module.router, prefix="/api", dependencies=_auth)


_DIST = Path(settings.frontend_dist_path).resolve()

if (_DIST / "index.html").is_file():
    # Serve the built React app (SPA): real files as-is, every other non-API
    # path falls back to index.html so client-side routes work on reload.
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        candidate = (_DIST / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(_DIST):
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html", headers={"Cache-Control": "no-cache"})
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {"name": settings.app_name, "version": settings.app_version, "health": "/api/health"}
