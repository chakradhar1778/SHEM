"""Phase 5: relay command lifecycle and acknowledgement rules."""

from __future__ import annotations

import json
from datetime import timedelta

from app.database import SessionLocal
from app.models.db_models import RelayCommand
from app.mqtt import handlers as H
from app.services.relay_service import check_and_mark_timeouts
from app.utils.timestamps import utcnow
from conftest import AUTH


def _command(client, state="ON"):
    r = client.post("/api/relay/1/command", json={"state": state}, headers=AUTH)
    assert r.status_code == 202, r.text
    return r.json()


def _ack(cid, status="applied", state="ON", device="001", channel=1):
    H.handle_relay_ack(json.dumps({"deviceId": device, "channel": channel, "commandId": cid,
                                   "commandedState": state, "status": status,
                                   "timestamp": "2026-11-01T09:30:02Z"}).encode())


def _status(client, cid):
    return client.get(f"/api/relay/1/commands/{cid}", headers=AUTH).json()


def test_command_on_fresh_database_publishes_firmware_contract(client, mqtt):
    body = _command(client)  # no telemetry yet → device row did not exist
    assert body["status"] == "published" and body["commandId"].startswith("SHEM-CMD-")
    msg = mqtt.published[-1]
    assert msg["topic"] == "shem/device/001/relay/1/command"
    assert msg["retain"] is False and msg["qos"] == 1
    assert set(msg["payload"]) == {"commandId", "channel", "state", "expiresAtUnix"}
    assert isinstance(msg["payload"]["expiresAtUnix"], int) and msg["payload"]["channel"] == 1
    assert _status(client, body["commandId"])["status"] == "published"


def test_lifecycle_pending_published_applied(client):
    cid = _command(client)["commandId"]
    _ack(cid)
    d = _status(client, cid)
    assert d["status"] == "applied" and d["acknowledgedAt"] and d["publishedAt"]
    relay = client.get("/api/relay/1/status", headers=AUTH).json()
    assert relay["commandedState"] == "ON"


def test_duplicate_ack_never_downgrades_applied(client):
    cid = _command(client)["commandId"]
    _ack(cid, "applied")
    _ack(cid, "duplicate")  # QoS 1 redelivery
    assert _status(client, cid)["status"] == "applied"


def test_duplicate_ack_alone_confirms_application(client):
    cid = _command(client)["commandId"]
    _ack(cid, "duplicate")  # original "applied" ack lost
    d = _status(client, cid)
    assert d["status"] == "applied" and "duplicate" in d["errorMessage"]


def test_rejected_expired_is_terminal(client):
    cid = _command(client)["commandId"]
    _ack(cid, "rejected_expired", state="OFF")
    _ack(cid, "applied")
    d = _status(client, cid)
    assert d["status"] == "rejected_expired" and "rejected" in d["errorMessage"]
    assert client.get("/api/relay/1/status", headers=AUTH).json()["commandedState"] is None


def test_ack_from_other_device_or_channel_ignored(client):
    cid = _command(client)["commandId"]
    _ack(cid, device="999")
    _ack(cid, channel=2)
    assert _status(client, cid)["status"] == "published"


def test_timeout_marking_and_late_applied(client):
    cid = _command(client)["commandId"]
    with SessionLocal() as db:
        db.get(RelayCommand, cid).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        check_and_mark_timeouts(db)
    assert _status(client, cid)["status"] == "timeout"
    _ack(cid, "applied")  # device did apply it, just late
    d = _status(client, cid)
    assert d["status"] == "applied" and "timed out" in d["errorMessage"]


def test_broker_down_returns_503_and_records_publish_failed(client, mqtt):
    mqtt.connected = False
    r = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH)
    assert r.status_code == 503
    with SessionLocal() as db:
        assert db.query(RelayCommand).one().status == "publish_failed"


def test_invalid_state_and_unknown_command(client):
    assert client.post("/api/relay/1/command", json={"state": "MAYBE"}, headers=AUTH).status_code == 422
    assert client.post("/api/relay/1/command", json={}, headers=AUTH).status_code == 422
    assert client.get("/api/relay/1/commands/SHEM-CMD-NOPE", headers=AUTH).status_code == 404


def test_relay_state_topic_updates_channel(client):
    H.handle_relay_state(b'{"deviceId":"001","channel":1,"state":"ON","timestamp":"2026-11-01T09:30:00Z"}')
    assert client.get("/api/relay/1/status", headers=AUTH).json()["commandedState"] == "ON"
    H.handle_relay_state(b'{"deviceId":"001","channel":2,"state":"OFF"}')  # channel 2 not supported
    assert client.get("/api/relay/1/status", headers=AUTH).json()["commandedState"] == "ON"
