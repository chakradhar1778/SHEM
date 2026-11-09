"""Background-loop broadcasts, concurrency, and broadcaster robustness."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.db_models import Device, RelayCommand, TelemetryRow
from app.mqtt import handlers as H
from app.services import broadcaster as bmod
from app.services.broadcaster import WebSocketBroadcaster
from app.utils.timestamps import utcnow
from conftest import AUTH, collect_ws, telemetry_bytes

WS = "/api/stream?api_key=test-key"


# ── Maintenance loop → WebSocket ───────────────────────────────────────────────

def test_command_timeout_is_pushed_to_clients(client):
    cid = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH).json()["commandId"]
    with SessionLocal() as db:
        db.get(RelayCommand, cid).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        msgs = collect_ws(ws, 4, until=lambda m: any(x["type"] == "relay_update" for x in m))
    upd = [x for x in msgs if x["type"] == "relay_update"]
    assert upd and upd[0]["data"]["commandId"] == cid and upd[0]["data"]["status"] == "timeout"


def test_stale_device_is_pushed_offline(client):
    H.handle_telemetry(telemetry_bytes())
    with SessionLocal() as db:
        db.get(Device, "001").last_seen_at = utcnow() - timedelta(seconds=60)
        db.commit()
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        msgs = collect_ws(ws, 4, until=lambda m: any(x["type"] == "device_status" for x in m))
    st = [x for x in msgs if x["type"] == "device_status"]
    assert st and st[0]["data"]["deviceOnline"] is False and st[0]["data"]["staleSince"]


# ── Concurrency (MQTT thread writes while the API reads/writes) ────────────────

def test_concurrent_ingest_and_api_traffic(client):
    """SQLite must not lose messages or return 500s under mixed concurrent load."""
    n_msgs = 150
    errors: list[str] = []

    def ingest(i: int):
        try:
            H.handle_telemetry(telemetry_bytes(energy=1 + i / 1000, power=float(i % 90)))
        except Exception as exc:  # pragma: no cover
            errors.append(repr(exc))

    def api(i: int):
        r = (client.get("/api/telemetry/latest", headers=AUTH) if i % 3
             else client.put("/api/household/config", headers=AUTH, json={"occupants": 1 + i % 5}))
        if r.status_code >= 500:
            errors.append(f"{r.status_code} {r.text[:80]}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(ingest, i) for i in range(n_msgs)] + [pool.submit(api, i) for i in range(60)]
        for f in futures:
            f.result()

    assert not errors, errors[:5]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(TelemetryRow)) == n_msgs


# ── Broadcaster (async) ────────────────────────────────────────────────────────

def fake_ws(send=None):
    ws = MagicMock()
    ws.accept = AsyncMock()
    ws.send_text = send or AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_broadcast_drops_failing_and_slow_clients(monkeypatch):
    monkeypatch.setattr(bmod, "SEND_TIMEOUT_SECONDS", 0.1)
    b = WebSocketBroadcaster()

    async def hang(_msg):
        await asyncio.sleep(5)

    good, broken, slow = fake_ws(), fake_ws(AsyncMock(side_effect=RuntimeError("gone"))), fake_ws(hang)
    for ws in (good, broken, slow):
        await b.connect(ws)
    await b.broadcast("telemetry", {"activePowerW": 1})
    assert b.client_count == 1
    good.send_text.assert_awaited_once()
    await b.broadcast("heartbeat", {})
    assert good.send_text.await_count == 2


@pytest.mark.asyncio
async def test_publish_from_other_thread_reaches_clients():
    b = WebSocketBroadcaster()
    b.bind_loop(asyncio.get_running_loop())
    ws = fake_ws()
    await b.connect(ws)
    t = threading.Thread(target=b.publish_from_thread, args=("telemetry", {"x": 1}))
    t.start()
    t.join()
    for _ in range(50):
        if ws.send_text.await_count:
            break
        await asyncio.sleep(0.02)
    ws.send_text.assert_awaited_once()
    assert '"type": "telemetry"' in ws.send_text.await_args.args[0]


def test_publish_without_loop_or_clients_is_a_noop():
    b = WebSocketBroadcaster()
    b.publish_from_thread("telemetry", {})      # no loop bound, no clients — must not raise


# ── Database failures must not kill the MQTT network thread ───────────────────

@pytest.mark.parametrize("handler, target, payload", [
    ("handle_telemetry", "ingest_telemetry", telemetry_bytes()),
    ("handle_device_status", "record_status_message", b'{"deviceId":"001","status":"online"}'),
    ("handle_relay_state", "record_relay_state", b'{"deviceId":"001","channel":1,"state":"ON"}'),
    ("handle_relay_ack", "record_command_ack",
     b'{"deviceId":"001","channel":1,"commandId":"SHEM-CMD-X","commandedState":"ON","status":"applied"}'),
])
def test_handler_db_errors_are_contained(client, monkeypatch, handler, target, payload):
    from sqlalchemy.exc import OperationalError
    from app.mqtt import handlers

    def db_down(*_a, **_k):
        raise OperationalError("INSERT ...", {}, Exception("database is locked"))

    monkeypatch.setattr(handlers, target, db_down)
    getattr(handlers, handler)(payload)          # must log, not raise
    # and the API keeps working
    assert client.get("/api/health").status_code == 200
