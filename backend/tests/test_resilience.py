"""
Acceptance: the backend survives an EMQX disconnect and reconnect.

Runs the REAL MQTTClientManager (paho mocked at the socket boundary) inside
the live app, driving it through connect → telemetry → broker drop →
reconnect, and checks REST, relay safety and WebSocket behaviour throughout.
"""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from unittest.mock import patch

import paho.mqtt.client as paho
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode
from sqlalchemy import func, select

import app.main as main
from app.database import SessionLocal
from app.models.db_models import RelayCommand, TelemetryRow
from app.mqtt.client import MQTTClientManager
from app.mqtt.handlers import (
    broadcast_mqtt_state,
    handle_device_status,
    handle_relay_ack,
    handle_relay_state,
    handle_telemetry,
)
from conftest import AUTH, collect_ws, telemetry_bytes

WS = "/api/stream?api_key=test-key"
CONNECT_OK = ReasonCode(PacketTypes.CONNACK, aName="Success")
DROPPED = ReasonCode(PacketTypes.DISCONNECT, aName="Unspecified error")


@pytest.fixture
def real_mqtt(client):
    with patch("app.mqtt.client.paho.Client"):
        mgr = MQTTClientManager()
    mgr.register_handlers(on_telemetry=handle_telemetry, on_status=handle_device_status,
                          on_relay_state=handle_relay_state, on_relay_ack=handle_relay_ack)
    mgr._client.publish.return_value = SimpleNamespace(rc=paho.MQTT_ERR_SUCCESS)
    mgr.on_state_change = broadcast_mqtt_state      # wired exactly as in main.lifespan
    fake = main.app.state.mqtt_client
    main.app.state.mqtt_client = mgr
    try:
        yield mgr
    finally:
        main.app.state.mqtt_client = fake


def deliver(mgr, topic: str, payload: bytes, retain: bool = False) -> None:
    """Deliver a message the way paho does: on its own network thread."""
    t = threading.Thread(target=mgr._on_message,
                         args=(mgr._client, None, SimpleNamespace(topic=topic, payload=payload, retain=int(retain))))
    t.start()
    t.join()


def telemetry_count() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(TelemetryRow))


def test_backend_survives_broker_disconnect_and_reconnect(client, real_mqtt):
    mgr = real_mqtt
    topic = "shem/device/001/telemetry"

    # ── 1. Connected: telemetry flows end-to-end (paho thread → DB → REST) ──
    mgr._on_connect(mgr._client, None, {}, CONNECT_OK)
    assert client.get("/api/health").json()["status"] == "ok"
    deliver(mgr, topic, telemetry_bytes(power=55.0))
    assert telemetry_count() == 1
    assert client.get("/api/telemetry/latest", headers=AUTH).json()["reading"]["activePowerW"] == 55.0

    with client.websocket_connect(WS) as ws:
        ws.receive_json()

        # ── 2. Broker drops ──
        mgr._on_disconnect(mgr._client, None, None, DROPPED)
        msgs = collect_ws(ws, 4, until=lambda m: any(
            x["type"] == "device_status" and x["data"]["mqttConnected"] is False for x in m))
        assert any(x["type"] == "device_status" and x["data"]["mqttConnected"] is False for x in msgs), \
            [x["type"] for x in msgs]

        health = client.get("/api/health").json()
        assert health["status"] == "degraded" and health["mqttConnected"] is False
        # REST data stays available while MQTT is down
        assert client.get("/api/telemetry/latest", headers=AUTH).status_code == 200
        assert client.get("/api/household/config", headers=AUTH).status_code == 200

        # Relay commands are refused honestly — never reported as success
        r = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH)
        assert r.status_code == 503
        mgr._client.publish.assert_not_called()
        with SessionLocal() as db:
            assert db.scalars(select(RelayCommand)).one().status == "publish_failed"

        # ── 3. Broker comes back: resubscribe, telemetry + commands resume ──
        mgr._on_connect(mgr._client, None, {}, CONNECT_OK)
        assert mgr._client.subscribe.call_count == 2
        msgs = collect_ws(ws, 4, until=lambda m: any(
            x["type"] == "device_status" and x["data"]["mqttConnected"] is True for x in m))
        assert any(x["type"] == "device_status" and x["data"]["mqttConnected"] is True for x in msgs)

        deliver(mgr, topic, telemetry_bytes(power=77.0))
        msgs = collect_ws(ws, 4, until=lambda m: any(x["type"] == "telemetry" for x in m))
        assert any(x["type"] == "telemetry" and x["data"]["activePowerW"] == 77.0 for x in msgs)

    assert telemetry_count() == 2
    assert client.get("/api/health").json()["status"] == "ok"

    r = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH)
    assert r.status_code == 202
    sent_topic, sent_payload = mgr._client.publish.call_args.args
    assert sent_topic == "shem/device/001/relay/1/command"
    assert mgr._client.publish.call_args.kwargs == {"qos": 1, "retain": False}
    cid = json.loads(sent_payload)["commandId"]

    # Device acks through the real dispatch path
    deliver(mgr, "shem/device/001/relay/1/ack", json.dumps({
        "deviceId": "001", "channel": 1, "commandId": cid, "commandedState": "ON",
        "status": "applied", "timestamp": "2026-11-01T09:30:02Z"}).encode())
    assert client.get(f"/api/relay/1/commands/{cid}", headers=AUTH).json()["status"] == "applied"


def test_retained_lwt_after_reconnect_marks_device_offline(client, real_mqtt):
    """On resubscribe the broker replays the retained Last-Will; the device must show offline."""
    mgr = real_mqtt
    mgr._on_connect(mgr._client, None, {}, CONNECT_OK)
    deliver(mgr, "shem/device/001/telemetry", telemetry_bytes())
    assert client.get("/api/device/status", headers=AUTH).json()["deviceOnline"] is True
    mgr._on_disconnect(mgr._client, None, None, DROPPED)
    mgr._on_connect(mgr._client, None, {}, CONNECT_OK)
    deliver(mgr, "shem/device/001/status", b'{"deviceId":"001","status":"offline"}', retain=True)
    assert client.get("/api/device/status", headers=AUTH).json()["deviceOnline"] is False


def test_backend_starts_and_serves_without_a_broker(client, real_mqtt):
    """Never connected (e.g. no internet at boot): API works, health is honest."""
    assert real_mqtt.connected is False
    health = client.get("/api/health").json()
    assert health["status"] == "degraded" and health["dbOk"] is True
    assert client.get("/api/inventory/rooms", headers=AUTH).status_code == 200
    assert client.post("/api/relay/1/command", json={"state": "OFF"}, headers=AUTH).status_code == 503
