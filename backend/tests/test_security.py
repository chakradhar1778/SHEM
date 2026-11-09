"""Phase 9: authentication, rate limits, public surface."""

from __future__ import annotations

from app.config import get_settings
from conftest import AUTH

PROTECTED_GET = [
    "/api/device/status", "/api/telemetry/latest", "/api/telemetry/history", "/api/relay/1/status",
    "/api/relay/1/commands/x", "/api/household/config", "/api/inventory/rooms", "/api/inventory/appliances",
    "/api/bills", "/api/target", "/api/insights", "/api/insights/today", "/api/insights/recommendations",
]


def test_health_is_public(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"status", "version", "dbOk", "mqttConnected", "timestamp"}
    assert body["status"] == "ok" and body["mqttConnected"] is True


def test_health_degraded_when_broker_down(client, mqtt):
    mqtt.connected = False
    assert client.get("/api/health").json()["status"] == "degraded"


def test_all_protected_routes_require_key(client):
    for path in PROTECTED_GET:
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers={"X-API-Key": "wrong"}).status_code == 401, path
    assert client.post("/api/relay/1/command", json={"state": "ON"}).status_code == 401
    assert client.put("/api/target", json={"monthlyBudgetINR": 500}).status_code == 401


def test_query_string_key_not_accepted_for_rest(client):
    assert client.get("/api/bills?api_key=test-key").status_code == 401


def test_correct_key_works(client):
    assert client.get("/api/bills", headers=AUTH).status_code == 200


def test_empty_api_key_fails_closed(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "api_key", "")
    monkeypatch.setattr(s, "allow_unauthenticated_dev", False)
    assert client.get("/api/bills").status_code == 401
    assert client.get("/api/bills", headers={"X-API-Key": ""}).status_code == 401


def test_relay_command_rate_limit(client):
    codes = [client.post("/api/relay/1/command", json={"state": "OFF"}, headers=AUTH).status_code for _ in range(11)]
    assert codes[:10] == [202] * 10 and codes[10] == 429


def test_history_rate_limit(client):
    codes = [client.get("/api/telemetry/history", headers=AUTH).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


def test_bill_create_rate_limit(client):
    body = {"unitsConsumedKWh": 10, "billAmountINR": 80}
    codes = [client.post("/api/bills", json=body, headers=AUTH).status_code for _ in range(21)]
    assert codes[:20] == [201] * 20 and codes[20] == 429


def test_rate_limit_is_per_client_behind_tunnel(client):
    for _ in range(10):
        client.post("/api/relay/1/command", json={"state": "OFF"}, headers={**AUTH, "CF-Connecting-IP": "1.1.1.1"})
    blocked = client.post("/api/relay/1/command", json={"state": "OFF"}, headers={**AUTH, "CF-Connecting-IP": "1.1.1.1"})
    other = client.post("/api/relay/1/command", json={"state": "OFF"}, headers={**AUTH, "CF-Connecting-IP": "2.2.2.2"})
    assert blocked.status_code == 429 and other.status_code == 202


def test_cors_only_allows_configured_origins(client):
    ok = client.options("/api/bills", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    bad = client.options("/api/bills", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers
