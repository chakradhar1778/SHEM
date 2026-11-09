"""
Cross-component contracts:
  * ESP32 firmware (Main_Code.ino) ⇄ backend MQTT handlers
  * backend REST responses ⇄ frontend TypeScript types (frontend/src/api/types.ts)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.database import SessionLocal
from app.models.db_models import RelayCommand
from app.mqtt import handlers as H
from conftest import AUTH, telemetry_bytes

# ── Firmware → backend ─────────────────────────────────────────────────────────
# Shapes copied from Main_Code.ino (publishTelemetry / publishDeviceStatus /
# publishRelayState / publishCommandAck / MQTT Last-Will).

FIRMWARE_TELEMETRY_NO_PF = {   # frequency/powerFactor omitted when not finite
    "deviceId": "001", "voltage": 231.2, "current": 0.12, "power": 9.8, "energy": 0.031,
    "energyUnit": "kWh", "relay1State": "OFF", "supplyType": "AC", "source": "PZEM-004T",
    "timestamp": "2026-11-01T09:30:00Z",
}
FIRMWARE_STATUS_ONLINE = {"deviceId": "001", "status": "online", "relay1State": "OFF", "timestamp": "2026-11-01T09:30:00Z"}
FIRMWARE_LWT = b'{"deviceId":"001","status":"offline"}'
FIRMWARE_RELAY_STATE = {"deviceId": "001", "channel": 1, "state": "ON", "timestamp": "2026-11-01T09:30:02Z"}


def test_firmware_telemetry_without_pf_and_frequency(client):
    H.handle_telemetry(json.dumps(FIRMWARE_TELEMETRY_NO_PF).encode())
    r = client.get("/api/telemetry/latest", headers=AUTH).json()["reading"]
    assert r["voltageV"] == 231.2 and r["frequencyHz"] is None and r["powerFactor"] is None


def test_firmware_status_lwt_and_relay_state(client):
    H.handle_device_status(json.dumps(FIRMWARE_STATUS_ONLINE).encode())
    assert client.get("/api/device/status", headers=AUTH).json()["deviceOnline"] is True
    H.handle_relay_state(json.dumps(FIRMWARE_RELAY_STATE).encode())
    assert client.get("/api/relay/1/status", headers=AUTH).json()["commandedState"] == "ON"
    H.handle_device_status(FIRMWARE_LWT)
    assert client.get("/api/device/status", headers=AUTH).json()["deviceOnline"] is False


@pytest.mark.parametrize("ack_status, expected, has_error", [
    ("applied", "applied", False),
    ("duplicate", "applied", True),                 # firmware already applied this exact ID
    ("rejected_expired", "rejected_expired", True),
    ("rejected_invalid_channel", "rejected_invalid_channel", True),
    ("rejected_invalid_state", "rejected_invalid_state", True),
    ("rejected_time_unsynchronized", "rejected_time_unsynchronized", True),
])
def test_every_firmware_ack_status(client, ack_status, expected, has_error):
    cid = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH).json()["commandId"]
    H.handle_relay_ack(json.dumps({
        "deviceId": "001", "channel": 1, "commandId": cid, "commandedState": "OFF" if ack_status != "applied" else "ON",
        "status": ack_status, "timestamp": "2026-11-01T09:30:02Z"}).encode())
    d = client.get(f"/api/relay/1/commands/{cid}", headers=AUTH).json()
    assert d["status"] == expected
    assert bool(d["errorMessage"]) is has_error


def test_unknown_ack_status_is_rejected(client):
    cid = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH).json()["commandId"]
    H.handle_relay_ack(json.dumps({"deviceId": "001", "channel": 1, "commandId": cid,
                                   "commandedState": "ON", "status": "maybe"}).encode())
    assert client.get(f"/api/relay/1/commands/{cid}", headers=AUTH).json()["status"] == "published"


def test_command_is_pending_in_db_before_it_is_published(client, mqtt):
    """Lifecycle: the row exists as 'pending' before the MQTT publish happens."""
    seen = {}
    original = mqtt.publish

    def spy(topic, payload, qos=1, retain=False):
        with SessionLocal() as db:
            seen["status"] = db.get(RelayCommand, json.loads(payload)["commandId"]).status
        return original(topic, payload, qos, retain)

    mqtt.publish = spy
    try:
        r = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH).json()
    finally:
        mqtt.publish = original
    assert seen["status"] == "pending" and r["status"] == "published"


# ── Backend → frontend ─────────────────────────────────────────────────────────

TYPES_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "types.ts"


def ts_required_fields(interface: str) -> set[str]:
    src = TYPES_TS.read_text(encoding="utf-8")
    m = re.search(rf"export interface {interface}\s*\{{(.*?)\n\}}", src, re.S)
    assert m, f"interface {interface} not found in types.ts"
    fields = set()
    depth = 0
    for line in m.group(1).splitlines():
        if depth == 0:
            fm = re.match(r"\s{2}(\w+)(\?)?:", line)
            if fm and not fm.group(2):
                fields.add(fm.group(1))
        depth += line.count("{") - line.count("}")
    return fields


def assert_matches(interface: str, payload: dict):
    missing = ts_required_fields(interface) - set(payload)
    assert not missing, f"{interface}: backend response lacks {sorted(missing)}"


pytestmark_frontend = pytest.mark.skipif(not TYPES_TS.exists(), reason="frontend not present")


@pytestmark_frontend
def test_rest_responses_match_frontend_types(client):
    H.handle_telemetry(telemetry_bytes())
    client.post("/api/inventory/appliances", headers=AUTH,
                json={"name": "Geyser", "category": "heating", "ratedWatts": 2000, "dailyHours": 4})
    client.post("/api/bills", headers=AUTH, json={"unitsConsumedKWh": 100, "billAmountINR": 800,
                                                  "billingMonth": 9, "billingYear": 2026})
    cmd = client.post("/api/relay/1/command", json={"state": "ON"}, headers=AUTH).json()

    checks = {
        "HealthResponse": client.get("/api/health").json(),
        "DeviceStatus": client.get("/api/device/status", headers=AUTH).json(),
        "LatestTelemetryResponse": client.get("/api/telemetry/latest", headers=AUTH).json(),
        "TelemetryReading": client.get("/api/telemetry/latest", headers=AUTH).json()["reading"],
        "TelemetryHistoryResponse": client.get("/api/telemetry/history", headers=AUTH).json(),
        "RelayStatus": client.get("/api/relay/1/status", headers=AUTH).json(),
        "RelayCommandResponse": cmd,
        "RelayCommandDetail": client.get(f"/api/relay/1/commands/{cmd['commandId']}", headers=AUTH).json(),
        "HouseholdConfigDTO": client.get("/api/household/config", headers=AUTH).json(),
        "RoomDTO": client.get("/api/inventory/rooms", headers=AUTH).json()[0],
        "ApplianceDTO": client.get("/api/inventory/appliances", headers=AUTH).json()[0],
        "BillDTO": client.get("/api/bills", headers=AUTH).json()[0],
        "TargetDTO": client.get("/api/target", headers=AUTH).json(),
        "InsightsResponse": client.get("/api/insights?period=week", headers=AUTH).json(),
        "TodayInsightsResponse": client.get("/api/insights/today", headers=AUTH).json(),
        "EnergyRecommendation": client.get("/api/insights/recommendations", headers=AUTH).json()[0],
    }
    hist = checks["TelemetryHistoryResponse"]
    if hist["readings"]:
        checks["TelemetryHistoryPoint"] = hist["readings"][0]
    ins = checks["InsightsResponse"]
    checks["InsightsTrendPoint"] = ins["trendPoints"][0]
    checks["CategoryShare"] = ins["shifts"][0]
    today = checks["TodayInsightsResponse"]
    checks["HourlyPoint"] = today["hourlyPoints"][0]
    checks["DayPeriodBreakdown"] = today["dayPeriods"][0]

    # Simulated appliances: the Geyser has no relay, so it is simulated.
    geyser = checks["ApplianceDTO"]
    sim = client.post(f"/api/simulation/appliances/{geyser['id']}/command", headers=AUTH, json={"state": "ON"}).json()
    checks["SimStatus"] = sim
    checks["SimApplianceLive"] = sim["appliances"][0]
    checks["DailyTotalsResponse"] = client.get("/api/insights/days?days=3", headers=AUTH).json()
    checks["DailyTotal"] = checks["DailyTotalsResponse"]["days"][0]
    from app.database import SessionLocal as _S
    from app.services.simulation_service import simulator
    from app.utils.timestamps import utcnow
    from datetime import timedelta
    with _S() as db:
        t0 = utcnow()
        for i in range(5):
            simulator.tick(db, t0 + timedelta(seconds=2 * i))
    today = client.get("/api/insights/today", headers=AUTH).json()
    checks["ApplianceUsage"] = next(a for a in today["applianceUsage"] if a["source"] == "simulated")
    checks["PeakSummary"] = today["peak"]
    checks["PeriodTopAppliance"] = next(p for p in today["dayPeriods"] if p["topAppliances"])["topAppliances"][0]

    # Billing: tariff + projected bill (with a slab tariff and a budget so every object is present)
    client.put("/api/billing/tariff", headers=AUTH, json={"mode": "slab", "slabs": [
        {"uptoKWh": 100, "rateINR": 4}, {"uptoKWh": None, "rateINR": 7}], "fixedChargeINR": 50})
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 1500})
    checks["Tariff"] = client.get("/api/billing/tariff", headers=AUTH).json()
    checks["TariffSlab"] = checks["Tariff"]["slabs"][0]
    proj = client.get("/api/billing/projection", headers=AUTH).json()
    checks["BillProjection"] = proj
    checks["BillBreakdown"] = proj["projected"]
    checks["BillLine"] = proj["projected"]["lines"][0]
    checks["BudgetStatus"] = proj["budget"]
    if proj["applianceCosts"]:
        checks["ApplianceBillShare"] = proj["applianceCosts"][0]
    bill_id = client.get("/api/bills", headers=AUTH).json()[0]["id"]
    checks["BillApplianceBreakdown"] = client.get(f"/api/billing/bills/{bill_id}/appliances", headers=AUTH).json()
    nl = client.post("/api/notifications/check", headers=AUTH).json()
    checks["NotificationList"] = nl
    if nl["items"]:
        checks["NotificationItem"] = nl["items"][0]
    client.put("/api/automation/budget-saver", headers=AUTH, json={"mode": "suggest"})
    saver = client.get("/api/automation/budget-saver", headers=AUTH).json()
    checks["BudgetSaverSettings"] = saver

    for interface, payload in checks.items():
        assert_matches(interface, payload)


@pytestmark_frontend
def test_websocket_snapshot_matches_frontend_types(client):
    with client.websocket_connect("/api/stream?api_key=test-key") as ws:
        # A broadcast (heartbeat, notification from an earlier test …) can arrive before the snapshot.
        snap = ws.receive_json()
        for _ in range(20):
            if snap["type"] == "init_snapshot":
                break
            snap = ws.receive_json()
        assert snap["type"] == "init_snapshot"
    assert_matches("InitSnapshot", snap["data"])
    assert_matches("DeviceStatus", snap["data"]["deviceStatus"])
    assert_matches("RelayStatus", snap["data"]["relayStatus"])
