"""Phase 6: WebSocket live stream."""

from __future__ import annotations

import json
import threading

import pytest
from starlette.websockets import WebSocketDisconnect

from app.mqtt import handlers as H
from conftest import AUTH, collect_ws, telemetry_bytes

WS = "/api/stream?api_key=test-key"


def _types(msgs):
    return [m["type"] for m in msgs]


def test_unauthenticated_websocket_rejected(client):
    for url in ("/api/stream", "/api/stream?api_key=wrong"):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(url) as ws:
                ws.receive_json()


def test_init_snapshot(client):
    with client.websocket_connect(WS) as ws:
        first = ws.receive_json()
    assert first["type"] == "init_snapshot"
    assert {"serverTime", "deviceStatus", "latestTelemetry", "relayStatus"} <= set(first["data"])


def test_telemetry_from_mqtt_thread_is_pushed(client):
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        t = threading.Thread(target=H.handle_telemetry, args=(telemetry_bytes(power=123.0),))
        t.start()
        t.join()
        msgs = collect_ws(ws, 5, until=lambda m: "telemetry" in _types(m))
    tel = [m for m in msgs if m["type"] == "telemetry"]
    assert tel, _types(msgs)
    assert tel[0]["data"]["activePowerW"] == 123.0 and tel[0]["data"]["measuredAt"]


def test_heartbeat_is_sent(client):
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        msgs = collect_ws(ws, 4, until=lambda m: "heartbeat" in _types(m))
    hb = [m for m in msgs if m["type"] == "heartbeat"]
    assert hb and "serverTime" in hb[0]["data"] and "mqttConnected" in hb[0]["data"]


def test_relay_ack_pushes_relay_update(client):
    cid = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH).json()["commandId"]
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        payload = json.dumps({"deviceId": "001", "channel": 1, "commandId": cid,
                              "commandedState": "ON", "status": "applied"}).encode()
        threading.Thread(target=H.handle_relay_ack, args=(payload,)).start()
        msgs = collect_ws(ws, 5, until=lambda m: "relay_update" in _types(m))
    upd = [m for m in msgs if m["type"] == "relay_update"]
    assert upd and upd[0]["data"]["commandId"] == cid
    assert upd[0]["data"]["status"] == "applied" and upd[0]["data"]["commandedState"] == "ON"


def test_ping_pong(client):
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        ws.send_text("ping")
        msgs = collect_ws(ws, 3, until=lambda m: "pong" in _types(m))
    assert "pong" in _types(msgs)


def test_disconnected_clients_are_removed(client):
    from app.services.broadcaster import broadcaster
    import time
    with client.websocket_connect(WS) as ws:
        ws.receive_json()
        assert broadcaster.client_count >= 1
    deadline = time.time() + 3
    while broadcaster.client_count and time.time() < deadline:
        time.sleep(0.05)
    assert broadcaster.client_count == 0
