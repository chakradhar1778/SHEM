"""Simulated appliances: profiles, routine, manual switch, energy integration and insights integration."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.db_models import SimEnergyHourly
from app.services.simulation_service import (
    describe_routine,
    next_routine_change,
    profile_for,
    routine_intervals,
    scheduled_on,
    simulator,
    unit_power,
)
from app.utils.timestamps import from_local
from conftest import AUTH, FAKE_NOW, seed


def L(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return from_local(datetime(2026, 3, day, hour, minute, second))


def add(client, **body):
    r = client.post("/api/inventory/appliances", headers=AUTH, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def run(start: datetime, seconds: int, step: int = 2) -> dict:
    """Drive the engine like the 2 s background loop would."""
    payload = {}
    with SessionLocal() as db:
        t = start
        while t <= start + timedelta(seconds=seconds):
            payload = simulator.tick(db, t)
            t += timedelta(seconds=step)
        simulator.flush(db)
    return payload


def live(payload: dict, appliance_id: str) -> dict:
    return next(a for a in payload["appliances"] if a["applianceId"] == appliance_id)


# ── pure model ─────────────────────────────────────────────────────────────────

def test_profiles_and_routines():
    assert profile_for("fridge", None) == "fridge"
    assert profile_for(None, "Cooling") == "ac"
    assert profile_for(None, None, "Geyser 15L") == "heater"
    assert routine_intervals("steady", 4) == [(1110, 1350)]            # 6:30pm–10:30pm
    assert routine_intervals("fridge", 3) == [(0, 1440)]               # fridges always run
    assert routine_intervals("fan", 0) == []                           # 0 h → manual only
    fan = routine_intervals("fan", 8)                                  # wraps midnight
    assert scheduled_on(fan, L(10, 23)) and scheduled_on(fan, L(11, 3)) and not scheduled_on(fan, L(11, 9))
    assert next_routine_change(fan, L(10, 21, 30)) == L(10, 22)
    assert describe_routine(fan) == "10pm–6am"


def test_power_profiles_behave_like_real_appliances():
    rng = random.Random(1)
    led = [unit_power("steady", 9, "LED", s, s, 0, rng, 230) for s in range(0, 600, 2)]
    assert all(8.7 < p < 9.3 for p in led)
    ac = [unit_power("ac", 1500, "Split AC", s, s, 0, rng, 230) for s in range(0, 3600, 2)]
    assert ac[0] > 3000                                   # compressor inrush
    assert min(ac) < 150 and max(ac[5:]) > 1400            # compressor cycles off/on
    fridge = [unit_power("fridge", 150, "Fridge", 0, s, 0, rng, 230) for s in range(0, 5400, 2)]
    duty = sum(p > 100 for p in fridge) / len(fridge)
    assert 0.3 < duty < 0.5
    hot = unit_power("heater", 2000, "Geyser", 10, 10, 0, rng, 245)
    assert hot > 2000 * 1.1                               # resistive load follows V²


# ── engine ─────────────────────────────────────────────────────────────────────

def test_appliance_without_relay_is_simulated(client):
    a = add(client, name="LED Bulb", category="Lighting", iconType="bulb", ratedWatts=9, quantity=4, dailyHours=0)
    assert a["isSimulated"] is True and a["simAuto"] is True
    r = add(client, name="Lamp", category="Lighting", iconType="bulb", ratedWatts=9, relayChannel=1)
    assert r["isSimulated"] is False
    # the relay appliance can't be switched through the simulator
    assert client.post(f"/api/simulation/appliances/{r['id']}/command", headers=AUTH,
                       json={"state": "ON"}).status_code == 409
    status = client.get("/api/simulation/status", headers=AUTH).json()
    assert [x["applianceId"] for x in status["appliances"]] == [a["id"]]


def test_manual_switch_draws_power_and_integrates_energy(client):
    a = add(client, name="LED Bulb", category="Lighting", iconType="bulb", ratedWatts=10, quantity=3, dailyHours=0)
    r = client.post(f"/api/simulation/appliances/{a['id']}/command", headers=AUTH, json={"state": "ON"})
    assert r.status_code == 200
    item = live(r.json(), a["id"])
    assert item["state"] == "ON" and item["mode"] == "manual" and item["overrideUntil"] is None
    assert 29 < item["powerW"] < 31                         # 3 × 10 W
    appliance = client.get("/api/inventory/appliances", headers=AUTH).json()[0]
    assert appliance["status"] == "on" and appliance["simManualState"] == "ON"

    simulator.reset()
    run(L(10, 17), 3600)                                    # one hour at ~30 W
    with SessionLocal() as db:
        rows = db.query(SimEnergyHourly).all()
    assert abs(sum(x.energy_kwh for x in rows) - 0.030) < 0.002
    assert abs(sum(x.on_seconds for x in rows) - 3600) < 5

    client.post(f"/api/simulation/appliances/{a['id']}/command", headers=AUTH, json={"state": "OFF"})
    assert live(client.get("/api/simulation/status", headers=AUTH).json(), a["id"])["powerW"] == 0


def test_routine_and_override_expiry(client):
    a = add(client, name="Fan", category="Fans", iconType="fan", ratedWatts=75, dailyHours=8)   # 10pm–6am
    with SessionLocal() as db:
        assert live(simulator.tick(db, L(10, 21)), a["id"])["state"] == "OFF"
        assert live(simulator.tick(db, L(10, 23)), a["id"])["state"] == "ON"
    # Manual OFF at 11pm holds until the routine's next change (6am), then the routine takes over again.
    with SessionLocal() as db:
        from app.models.db_models import Appliance
        item = db.get(Appliance, a["id"])
        item.sim_manual_state, item.sim_override_until = "OFF", L(11, 6)
        db.commit()
        assert live(simulator.tick(db, L(11, 2)), a["id"])["mode"] == "manual"
        assert live(simulator.tick(db, L(11, 2)), a["id"])["state"] == "OFF"
        assert live(simulator.tick(db, L(11, 22, 30)), a["id"])["state"] == "ON"
    # Disabling the routine clears the override and leaves it off.
    client.put(f"/api/inventory/appliances/{a['id']}", headers=AUTH, json={"simAuto": False})
    with SessionLocal() as db:
        assert live(simulator.tick(db, L(11, 23)), a["id"])["mode"] == "off"


def test_washing_machine_programme_finishes_and_switches_off(client):
    a = add(client, name="Washer", category="Washing Machine", iconType="washer", ratedWatts=500, dailyHours=0)
    with SessionLocal() as db:
        from app.models.db_models import Appliance
        item = db.get(Appliance, a["id"])
        item.sim_manual_state = "ON"
        db.commit()
    p = run(L(10, 9), 59 * 60, step=10)
    assert live(p, a["id"])["state"] == "ON"
    p = run(L(10, 10), 120, step=10)
    assert live(p, a["id"])["state"] == "OFF"


# ── insights integration ───────────────────────────────────────────────────────

def test_today_insights_combine_metered_and_simulated(client, freeze_insights):
    relay = add(client, name="LED Bulb", category="Lighting", iconType="bulb", ratedWatts=9, relayChannel=1)
    seed([(L(10, 17, 0), 1.0, 100), (L(10, 17, 50), 1.2, 100)])   # 0.2 kWh metered at 5pm
    tv = add(client, name="TV", category="Entertainment", iconType="tv", ratedWatts=100, dailyHours=0)
    client.post(f"/api/simulation/appliances/{tv['id']}/command", headers=AUTH, json={"state": "ON"})
    simulator.reset()
    run(L(10, 18), 1500, step=5)                           # ~25 min of TV at 6pm

    r = client.get("/api/insights/today", headers=AUTH).json()
    assert r["isToday"] is True and r["hasData"] is True
    assert abs(r["meteredKWh"] - 0.2) < 1e-6 and r["simulatedKWh"] > 0.02
    assert abs(r["energyTodayKWh"] - (r["meteredKWh"] + r["simulatedKWh"])) < 1e-3
    usage = {u["applianceId"]: u for u in r["applianceUsage"]}
    assert usage[relay["id"]]["source"] == "metered" and usage[tv["id"]]["source"] == "simulated"
    assert usage[tv["id"]]["onHours"] > 0.4
    hp = {p["hour"]: p for p in r["hourlyPoints"]}
    assert hp[17]["meteredKWh"] == 0.2 and hp[18]["simulatedKWh"] > 0
    periods = {p["period"]: p for p in r["dayPeriods"]}
    assert periods["afternoon"]["isPeak"] and periods["afternoon"]["topAppliances"][0]["name"] == "LED Bulb"
    assert periods["evening"]["topAppliances"][0]["source"] == "simulated"
    assert r["peak"]["hour"] == 17 and r["peak"]["topAppliance"] == "LED Bulb"
    assert r["applianceBreakdown"] and not any(s["kwh"] == 0 for s in r["applianceBreakdown"])


def test_day_picker_and_daily_totals(client, freeze_insights):
    seed([(L(8, 9), 1.0, 100), (L(8, 20), 2.5, 100)])             # 1.5 kWh on 8 March
    past = client.get("/api/insights/today?date=2026-03-08", headers=AUTH).json()
    assert past["isToday"] is False and past["date"] == "2026-03-08"
    assert abs(past["energyTodayKWh"] - 1.5) < 1e-6
    assert client.get("/api/insights/today?date=2026-03-11", headers=AUTH).status_code == 400
    assert client.get("/api/insights/today?date=bad", headers=AUTH).status_code == 422
    empty = client.get("/api/insights/today?date=2026-03-01", headers=AUTH).json()
    assert empty["hasData"] is False and empty["insightCard"]["title"] == "No data for this day"

    days = client.get("/api/insights/days?days=7", headers=AUTH).json()
    assert [d["date"] for d in days["days"]][-1] == "2026-03-10" and days["days"][-1]["isToday"]
    d8 = next(d for d in days["days"] if d["date"] == "2026-03-08")
    assert abs(d8["kwh"] - 1.5) < 1e-6 and d8["peakPeriod"] == "evening"
    assert days["averageKWh"] == 1.5


def test_week_insights_use_actual_appliance_breakdown(client, freeze_insights):
    tv = add(client, name="TV", category="Entertainment", iconType="tv", ratedWatts=100, dailyHours=0)
    client.post(f"/api/simulation/appliances/{tv['id']}/command", headers=AUTH, json={"state": "ON"})
    simulator.reset()
    run(FAKE_NOW - timedelta(hours=2), 1200, step=10)
    r = client.get("/api/insights?period=week", headers=AUTH).json()
    assert r["hasData"] and r["simulatedKWh"] > 0 and r["meteredKWh"] == 0
    assert r["shiftsAreEstimates"] is False and r["shifts"][0]["categoryId"] == "entertainment"
    assert r["applianceUsage"][0]["name"] == "TV" and r["applianceUsage"][0]["source"] == "simulated"
