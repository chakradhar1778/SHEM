"""Phases 3–4: MQTT validation, telemetry persistence, device status."""

from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.db_models import Device, DeviceStatusEvent, TelemetryRow
from app.mqtt import handlers as H
from app.services.device_service import mark_stale_devices
from app.utils.timestamps import utcnow
from conftest import AUTH, telemetry_bytes


def _count(model, *where) -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model).where(*where))


def test_valid_ac_telemetry_is_stored_and_served(client):
    H.handle_telemetry(telemetry_bytes(power=98.2, relay1State="ON"))
    r = client.get("/api/telemetry/latest", headers=AUTH).json()
    assert r["available"] is True and r["stale"] is False
    reading = r["reading"]
    assert reading["voltageV"] == 230.4 and reading["activePowerW"] == 98.2
    assert reading["energyKWh"] == 1.245 and reading["supplyType"] == "AC"
    assert reading["loadActive"] is True and reading["relay1State"] == "ON"


def test_dc_supply_is_discarded(client):
    H.handle_telemetry(telemetry_bytes(supplyType="DC"))
    assert _count(TelemetryRow) == 0


def test_wrong_source_is_discarded(client):
    H.handle_telemetry(telemetry_bytes(source="simulation"))
    assert _count(TelemetryRow) == 0


def test_energy_unit_must_be_kwh(client):
    H.handle_telemetry(telemetry_bytes(energyUnit="Wh"))
    d = json.loads(telemetry_bytes())
    d.pop("energyUnit")
    H.handle_telemetry(json.dumps(d).encode())
    assert _count(TelemetryRow) == 0


def test_unknown_device_is_discarded_everywhere(client):
    H.handle_telemetry(telemetry_bytes(deviceId="999"))
    H.handle_device_status(b'{"deviceId":"999","status":"online"}')
    H.handle_relay_state(b'{"deviceId":"999","channel":1,"state":"ON"}')
    assert _count(TelemetryRow) == 0
    assert _count(Device) == 0
    assert _count(DeviceStatusEvent) == 0


def test_malformed_json_is_ignored(client):
    H.handle_telemetry(b"{not json")
    H.handle_telemetry(b"[1,2,3]")
    assert _count(TelemetryRow) == 0


def test_nan_voltage_stored_as_invalid_not_dropped(client):
    H.handle_telemetry(b'{"deviceId":"001","voltage":NaN,"current":0.4,"power":9,"energy":1,'
                       b'"energyUnit":"kWh","supplyType":"AC","source":"PZEM-004T"}')
    assert _count(TelemetryRow, TelemetryRow.validity == "invalid") == 1
    with SessionLocal() as db:
        row = db.scalars(select(TelemetryRow)).one()
        assert row.voltage_v is None and row.energy_kwh is None
    status = client.get("/api/device/status", headers=AUTH).json()
    assert status["pzemReadingsValid"] is False
    assert client.get("/api/telemetry/latest", headers=AUTH).json()["available"] is False


def test_out_of_range_reading_is_invalid(client):
    H.handle_telemetry(telemetry_bytes(voltage=900.0))
    assert _count(TelemetryRow, TelemetryRow.validity == "invalid") == 1


def test_missing_or_bad_frequency_and_pf_become_null(client):
    d = json.loads(telemetry_bytes())
    d.pop("frequency")
    d["powerFactor"] = 3.5
    H.handle_telemetry(json.dumps(d).encode())
    with SessionLocal() as db:
        row = db.scalars(select(TelemetryRow)).one()
    assert row.frequency_hz is None and row.power_factor is None


def test_esp32_pre_ntp_empty_timestamp_uses_receive_time(client):
    H.handle_telemetry(telemetry_bytes(timestamp=""))
    with SessionLocal() as db:
        row = db.scalars(select(TelemetryRow)).one()
    assert abs((row.measured_at - utcnow()).total_seconds()) < 5


def test_future_timestamp_is_clamped(client):
    future = (utcnow() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    H.handle_telemetry(telemetry_bytes(timestamp=future))
    with SessionLocal() as db:
        row = db.scalars(select(TelemetryRow)).one()
    assert row.measured_at <= utcnow() + timedelta(seconds=5)


def test_kwh_is_never_summed(client):
    for e in (5.000, 5.001, 5.002):
        H.handle_telemetry(telemetry_bytes(energy=e))
    latest = client.get("/api/telemetry/latest", headers=AUTH).json()["reading"]
    assert latest["energyKWh"] == 5.002


# ── device status ──────────────────────────────────────────────────────────────

def test_device_online_with_relay_state_after_message(client):
    H.handle_telemetry(telemetry_bytes(relay1State="ON"))
    s = client.get("/api/device/status", headers=AUTH).json()
    assert s["deviceId"] == "001" and s["deviceOnline"] is True and s["mqttConnected"] is True
    assert s["relay1State"] == "ON" and s["pzemReadingsValid"] is True and s["staleSince"] is None
    assert _count(DeviceStatusEvent, DeviceStatusEvent.status == "online") == 1


def test_device_goes_offline_after_threshold(client):
    H.handle_telemetry(telemetry_bytes())
    with SessionLocal() as db:
        db.get(Device, "001").last_seen_at = utcnow() - timedelta(seconds=60)
        db.scalars(select(TelemetryRow)).one().received_at = utcnow() - timedelta(seconds=60)
        db.commit()
        mark_stale_devices(db)
        assert mark_stale_devices(db) == []  # only one transition
    s = client.get("/api/device/status", headers=AUTH).json()
    assert s["deviceOnline"] is False and s["staleSince"] is not None
    assert _count(DeviceStatusEvent, DeviceStatusEvent.status == "offline") >= 1
    assert client.get("/api/telemetry/latest", headers=AUTH).json()["stale"] is True


def test_last_seen_updates_on_each_message(client):
    H.handle_telemetry(telemetry_bytes())
    with SessionLocal() as db:
        db.get(Device, "001").last_seen_at = utcnow() - timedelta(seconds=8)
        db.commit()
    H.handle_telemetry(telemetry_bytes())
    with SessionLocal() as db:
        assert (utcnow() - db.get(Device, "001").last_seen_at).total_seconds() < 3


def test_lwt_offline_without_timestamp(client):
    H.handle_telemetry(telemetry_bytes())
    H.handle_device_status(b'{"deviceId":"001","status":"offline"}')  # exact firmware LWT
    s = client.get("/api/device/status", headers=AUTH).json()
    assert s["deviceOnline"] is False


def test_retained_online_status_does_not_refresh_last_seen(client):
    H.handle_device_status(b'{"deviceId":"001","status":"online","relay1State":"OFF","timestamp":"2026-01-01T00:00:00Z"}',
                           retained=True)
    s = client.get("/api/device/status", headers=AUTH).json()
    assert s["deviceOnline"] is False and s["lastSeenAt"] is None


def test_invalid_status_value_rejected(client):
    H.handle_device_status(b'{"deviceId":"001","status":"rebooting"}')
    assert _count(DeviceStatusEvent) == 0
