"""Data condensing: register deltas, hourly rollups, retention, history downsampling."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models.db_models import DeviceStatusEvent, RelayCommand, TelemetryHourly, TelemetryRow
from app.services.energy_service import (
    hourly_stats,
    prune_old_data,
    register_delta,
    rollup_completed_hours,
)
from app.utils.timestamps import utcnow
from conftest import AUTH, FAKE_NOW, seed


def _count(model, *where):
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(model).where(*where))


def test_register_delta_rules():
    assert register_delta(10.0, 10.5, 3600) == 0.5            # normal
    assert register_delta(10.0, 9.995, 2) == 0.0              # float noise
    assert register_delta(50.0, 0.2, 60) == 0.2               # meter reset
    assert register_delta(1.0, 500.0, 2) == 0.0               # impossible glitch (> 26 kW)
    assert abs(register_delta(1.0, 30.0, 4 * 3600) - 29.0) < 1e-9   # long gap, plausible


def _seed_two_periods():
    old = FAKE_NOW - timedelta(days=10)
    recent = FAKE_NOW - timedelta(days=1)
    rows, e = [], 100.0
    for base in (old, recent):
        for i in range(30):                    # 5 hours, every 10 minutes, 1 kW
            e += 1 / 6
            rows.append((base + timedelta(minutes=10 * i), round(e, 6), 1000))
    seed(rows)
    return old, recent


def test_rollup_is_lossless_and_prune_keeps_history():
    old, recent = _seed_two_periods()
    with SessionLocal() as db:
        before = hourly_stats(db, "001", old - timedelta(hours=1), FAKE_NOW)
        written = rollup_completed_hours(db, "001", now=FAKE_NOW)
        assert written == len(before) and written >= 10
        after_rollup = hourly_stats(db, "001", old - timedelta(hours=1), FAKE_NOW)
        counts = prune_old_data(db, "001", now=FAKE_NOW)
        after_prune = hourly_stats(db, "001", old - timedelta(hours=1), FAKE_NOW)

    total = lambda s: round(sum(x.energy_kwh for x in s.values()), 6)
    assert total(before) == total(after_rollup) == total(after_prune)
    assert {b: round(s.energy_kwh, 6) for b, s in before.items()} == {b: round(s.energy_kwh, 6) for b, s in after_prune.items()}
    assert counts["telemetry"] == 30                                   # the 10-day-old raw rows
    assert _count(TelemetryRow) == 30                                  # recent raw rows kept
    assert _count(TelemetryHourly) == written
    with SessionLocal() as db:                                         # rollup is idempotent
        assert rollup_completed_hours(db, "001", now=FAKE_NOW) == 0


def test_prune_never_deletes_unrolled_raw_data():
    seed([(FAKE_NOW - timedelta(days=20, minutes=i), 1 + i / 1000, 100) for i in range(5)])
    with SessionLocal() as db:
        prune_old_data(db, "001", now=FAKE_NOW)   # no rollup has run yet
    assert _count(TelemetryRow) == 5


def test_latest_valid_reading_survives_pruning():
    seed([(FAKE_NOW - timedelta(days=20, minutes=i), 1 + (5 - i) / 1000, 100) for i in range(5)])
    with SessionLocal() as db:
        rollup_completed_hours(db, "001", now=FAKE_NOW)
        prune_old_data(db, "001", now=FAKE_NOW)
    assert _count(TelemetryRow) == 1


def test_old_events_and_finished_commands_pruned(client):
    seed([(FAKE_NOW - timedelta(hours=2), 1.0, 10)])
    old = FAKE_NOW - timedelta(days=120)
    with SessionLocal() as db:
        db.add(DeviceStatusEvent(device_id="001", status="online", recorded_at=old))
        db.add(DeviceStatusEvent(device_id="001", status="online", recorded_at=FAKE_NOW))
        db.add(RelayCommand(command_id="A", device_id="001", requested_state="ON", status="applied", created_at=old))
        db.add(RelayCommand(command_id="B", device_id="001", requested_state="ON", status="applied", created_at=FAKE_NOW))
        db.commit()
        prune_old_data(db, "001", now=FAKE_NOW)
    assert _count(DeviceStatusEvent) == 1
    with SessionLocal() as db:
        assert [c.command_id for c in db.scalars(select(RelayCommand))] == ["B"]


# ── history downsampling (real clock) ──────────────────────────────────────────

def _seed_last_two_hours():
    start = utcnow() - timedelta(hours=2)
    seed([(start + timedelta(seconds=6 * i), 1 + i / 10000, 100 + i % 50) for i in range(1200)])


def test_history_auto_resolution_covers_whole_window(client):
    _seed_last_two_hours()
    r = client.get("/api/telemetry/history", headers=AUTH).json()     # default 24 h → 5 min buckets
    assert r["resolution"] == "5m" and 20 <= r["count"] <= 30
    last = r["readings"][-1]["timestamp"]
    assert last >= (utcnow() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert sum(p["samples"] for p in r["readings"]) == 1200


def test_history_raw_is_truncated_to_most_recent(client):
    _seed_last_two_hours()
    r = client.get("/api/telemetry/history?resolution=raw&limit=100", headers=AUTH).json()
    assert r["count"] == 100 and r["truncated"] is True and r["dataNote"]
    assert r["readings"][-1]["timestamp"] >= (utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_history_hourly_and_range_limits(client):
    _seed_last_two_hours()
    r = client.get("/api/telemetry/history?resolution=1h", headers=AUTH).json()
    assert r["resolution"] == "1h" and 2 <= r["count"] <= 3
    assert abs(sum(p["energyUsedKWh"] for p in r["readings"]) - 0.1199) < 0.001
    bad = client.get("/api/telemetry/history?from_time=2026-01-01T00:00:00Z&to_time=2026-03-01T00:00:00Z&resolution=raw",
                     headers=AUTH)
    assert bad.status_code == 400
    ok = client.get("/api/telemetry/history?from_time=2026-01-01T00:00:00Z&to_time=2026-03-01T00:00:00Z&resolution=1h",
                    headers=AUTH)
    assert ok.status_code == 200
    assert client.get("/api/telemetry/history?from_time=2026-03-02T00:00:00Z&to_time=2026-03-01T00:00:00Z",
                      headers=AUTH).status_code == 400
    assert client.get("/api/telemetry/history?from_time=yesterday", headers=AUTH).status_code == 400
