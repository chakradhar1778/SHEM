"""
Test harness — fully isolated:
  * a temporary SQLite file (never backend/shem.db)
  * a fake MQTT client (never connects to EMQX, never actuates the real relay)
Environment variables are set BEFORE the app is imported because settings
and the engine are created at import time.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

_TMP = tempfile.mkdtemp(prefix="shem-test-")
os.environ.update({
    "SQLITE_PATH": os.path.join(_TMP, "test.db"),
    "UPLOADS_DIR": os.path.join(_TMP, "uploads"),
    "MAX_BILL_DOCUMENT_MB": "1",
    "API_KEY": "test-key",
    "ALLOW_UNAUTHENTICATED_DEV": "false",
    "HEARTBEAT_INTERVAL_SECONDS": "1",
    "MAINTENANCE_INTERVAL_SECONDS": "3600",
    "STALE_TELEMETRY_THRESHOLD_SECONDS": "10",
    "RAW_TELEMETRY_RETENTION_DAYS": "7",
    "TIMEZONE": "Asia/Kolkata",
    "RATE_LIMIT_ENABLED": "true",
    "DEVICE_ID": "001",
    # SHEM AI: never call real providers from tests; fake routers are injected per test.
    "GEMINI_API_KEY": "",
    "GROQ_API_KEY": "",
    "SARVAM_API_KEY": "",
    "AI_BACKGROUND_ENABLED": "false",
    # Simulated appliances: the 2 s background loop is off; tests drive simulator.tick() directly.
    "SIMULATION_ENABLED": "false",
    "ALERTS_ENABLED": "false",
})
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402


class FakeMQTT:
    def __init__(self) -> None:
        self.connected = True
        self.published: List[dict] = []
        self.disconnect_reason = None

    def register_handlers(self, **handlers) -> None:
        self.handlers = handlers

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def publish(self, topic, payload, qos=1, retain=False) -> bool:
        if not self.connected:
            return False
        self.published.append({"topic": topic, "payload": json.loads(payload), "qos": qos, "retain": retain})
        return True


import app.main as main  # noqa: E402

main.MQTTClientManager = FakeMQTT

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models.db_models import TelemetryRow  # noqa: E402
from app.services.device_service import get_or_create_device  # noqa: E402
from app.utils.rate_limit import limiter  # noqa: E402
from app.utils.timestamps import from_local, utcnow  # noqa: E402

AUTH = {"X-API-Key": "test-key"}

# Deterministic "now" for insights tests: Tuesday 10 March 2026, 18:30 IST
FAKE_NOW = from_local(datetime(2026, 3, 10, 18, 30))


@pytest.fixture(scope="session")
def client():
    with TestClient(main.app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def mqtt(client) -> FakeMQTT:
    return main.app.state.mqtt_client


@pytest.fixture(autouse=True)
def clean_state(client):
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"DELETE FROM {table.name}"))
    limiter.reset()
    from app.services.simulation_service import simulator
    simulator.reset()
    fake = main.app.state.mqtt_client
    fake.connected = True
    fake.published.clear()
    yield


@pytest.fixture
def freeze_insights(monkeypatch):
    """Pin the insights clock to FAKE_NOW."""
    import app.services.insights_service as ins
    monkeypatch.setattr(ins, "utcnow", lambda: FAKE_NOW)
    return FAKE_NOW


def telemetry_bytes(**over) -> bytes:
    d = {
        "deviceId": "001", "voltage": 230.4, "current": 0.45, "power": 98.2, "energy": 1.245,
        "energyUnit": "kWh", "frequency": 50.0, "powerFactor": 0.95, "relay1State": "OFF",
        "supplyType": "AC", "source": "PZEM-004T",
        "timestamp": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    d.update(over)
    return json.dumps(d).encode()


def seed(rows, device_id: str = "001") -> None:
    """rows: iterable of (measured_at, energy_kwh, power_w[, pf[, voltage]])."""
    with SessionLocal() as db:
        get_or_create_device(db, device_id)
        for r in rows:
            t, e, p = r[0], r[1], r[2]
            pf = r[3] if len(r) > 3 else 0.95
            v = r[4] if len(r) > 4 else 230.0
            db.add(TelemetryRow(device_id=device_id, voltage_v=v, current_a=p / v, active_power_w=p,
                                energy_kwh=e, power_factor=pf, frequency_hz=50.0, validity="valid",
                                measured_at=t, received_at=t))
        db.commit()


def collect_ws(ws, seconds: float, until: Optional[Callable[[list], bool]] = None) -> list:
    """
    Return WebSocket messages received since the previous call on this socket
    (waiting up to `seconds`, or until `until(messages)` is true).

    One persistent reader thread per socket plus a read cursor, so frames are
    never stolen by a stale reader and frames that arrive between an action
    and the next call are never missed.
    """
    buffer = getattr(ws, "_shem_buffer", None)
    if buffer is None:
        buffer = ws._shem_buffer = []

        def reader():
            try:
                while True:
                    buffer.append(ws.receive_json())
            except Exception:
                pass

        threading.Thread(target=reader, daemon=True).start()

    start = getattr(ws, "_shem_cursor", 0)
    deadline = time.time() + seconds
    while time.time() < deadline:
        if until and until(buffer[start:]):
            break
        time.sleep(0.05)
    end = len(buffer)
    ws._shem_cursor = end
    return buffer[start:end]
