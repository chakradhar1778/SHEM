"""Bill engine: slab tariff, billing cycle, projected bill, and budget checks on metered + simulated energy."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.ai.conflicts import detect_conflicts
from app.database import SessionLocal
from app.services import billing_service as bs
from app.services.simulation_service import simulator
from app.utils.timestamps import from_local
from conftest import AUTH, FAKE_NOW, seed

SLABS = [{"uptoKWh": 100, "rateINR": 4}, {"uptoKWh": 200, "rateINR": 6}, {"uptoKWh": None, "rateINR": 8}]


def L(day: int, hour: int, minute: int = 0) -> datetime:
    return from_local(datetime(2026, 3, day, hour, minute))


@pytest.fixture
def frozen(monkeypatch, freeze_insights):
    """Pin the billing clock to FAKE_NOW (Tue 10 March 2026, 18:30 IST) too."""
    import app.ai.conflicts as conflicts
    monkeypatch.setattr(bs, "utcnow", lambda: FAKE_NOW)
    monkeypatch.setattr(conflicts, "utcnow", lambda: FAKE_NOW)
    bs.clear_rate_cache()
    return FAKE_NOW


def put_tariff(client, **body):
    r = client.put("/api/billing/tariff", headers=AUTH, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── engine ─────────────────────────────────────────────────────────────────────

def test_slab_bill_with_fixed_fuel_and_duty():
    t = bs.Tariff(mode="slab", slabs=[bs.Slab(100, 4), bs.Slab(200, 6), bs.Slab(None, 8)],
                  fixed_charge=110, fuel_per_kwh=0.3, duty_percent=9)
    b = bs.compute_bill(250, t)
    assert [ln.amount for ln in b.lines] == [400, 600, 400]
    assert b.energy_charge == 1400 and b.fuel_charge == 75 and b.duty == 132.75 and b.total == 1717.75
    assert b.slab_index == 2 and b.kwh_to_next_slab is None
    low = bs.compute_bill(80, t)
    assert low.slab_index == 0 and low.kwh_to_next_slab == 20 and low.next_slab_rate == 6
    assert low.marginal_rate == round((4 + 0.3) * 1.09, 3)
    assert abs(bs.kwh_for_amount(1717.75, t) - 250) < 0.01
    assert bs.kwh_for_amount(100, t) == 0.0                      # below the fixed charge
    assert bs.compute_bill(50, t, fixed_fraction=0.5).fixed_charge == 55


def test_flat_tariff_is_unchanged():
    t = bs.Tariff(flat_rate=7.5)
    assert t.is_plain_flat and bs.compute_bill(100, t).total == 750 and bs.kwh_for_amount(750, t) == 100


def test_slab_validation():
    assert bs.validate_slabs([bs.Slab(100, 4), bs.Slab(None, 6)]) is None
    assert "increase" in bs.validate_slabs([bs.Slab(100, 4), bs.Slab(50, 6), bs.Slab(None, 8)])
    assert "last slab" in bs.validate_slabs([bs.Slab(100, 4), bs.Slab(200, 6)])
    assert "open-ended" in bs.validate_slabs([bs.Slab(None, 4), bs.Slab(None, 6)])


def test_billing_cycle_from_meter_reading_day():
    assert bs.cycle_bounds(L(10, 9), 1) == (datetime(2026, 3, 1).date(), datetime(2026, 4, 1).date())
    assert bs.cycle_bounds(L(10, 9), 14) == (datetime(2026, 2, 14).date(), datetime(2026, 3, 14).date())
    assert bs.cycle_bounds(L(14, 0, 30), 14) == (datetime(2026, 3, 14).date(), datetime(2026, 4, 14).date())


# ── API ────────────────────────────────────────────────────────────────────────

def test_tariff_api_round_trip_and_validation(client):
    t = client.get("/api/billing/tariff", headers=AUTH).json()
    assert t["mode"] == "flat" and t["billingCycleDay"] == 1
    r = client.put("/api/billing/tariff", headers=AUTH, json={"mode": "slab"})
    assert r.status_code == 422                                 # no slabs yet
    bad = client.put("/api/billing/tariff", headers=AUTH,
                     json={"slabs": [{"uptoKWh": 100, "rateINR": 4}, {"uptoKWh": 50, "rateINR": 6}]})
    assert bad.status_code == 422
    t = put_tariff(client, mode="slab", slabs=SLABS, fixedChargeINR=110, fuelAdjustmentINRPerKWh=0.3,
                   electricityDutyPercent=9, billingCycleDay=14)
    assert t["mode"] == "slab" and len(t["slabs"]) == 3 and t["billingCycleDay"] == 14
    est = client.post("/api/billing/estimate", headers=AUTH, json={"kwh": 250}).json()
    assert est["totalINR"] == 1717.75 and est["lines"][2]["label"] == "Above 200 kWh"
    assert client.put("/api/billing/tariff", headers=AUTH, json={"billingCycleDay": 31}).status_code == 422


def test_projection_uses_metered_and_simulated_energy(client, frozen):
    put_tariff(client, mode="slab", slabs=SLABS, fixedChargeINR=100)
    # Calendar cycle (day 1): 9.75 days elapsed on 10 March 18:30.
    seed([(L(2, 0), 0.0, 100), (L(10, 18), 30.0, 100)])        # 30 kWh metered this cycle
    with SessionLocal() as db:
        from app.models.db_models import SimEnergyHourly
        db.add(SimEnergyHourly(appliance_id="app-ac", appliance_name="AC", icon_type="ac", category="Cooling",
                               bucket_start=L(9, 22), energy_kwh=9.0, on_seconds=3600, power_max=1500, samples=1))
        db.commit()
    p = client.get("/api/billing/projection", headers=AUTH).json()
    assert p["cycleStart"] == "2026-03-01" and p["cycleEnd"] == "2026-04-01" and p["cycleDays"] == 31
    assert abs(p["usedKWh"] - 39.0) < 1e-6 and p["meteredKWh"] == 30.0 and p["simulatedKWh"] == 9.0
    assert abs(p["projectedKWh"] - 39.0 / 9.770833 * 31) < 0.5   # ≈ 124 kWh at the cycle pace
    assert p["projected"]["slabIndex"] == 1 and p["projected"]["fixedChargeINR"] == 100
    assert p["soFar"]["fixedChargeINR"] < 100                   # pro-rated so far
    # Only two readings: the pace is cycle-based but coverage is under 24 h, so confidence stays low.
    assert p["paceBasis"] == "cycle" and p["confidence"] == "low" and p["budget"] is None

    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 500})
    b = client.get("/api/billing/projection", headers=AUTH).json()["budget"]
    assert b["status"] == "at_risk" and b["projectedOverINR"] > 0
    assert abs(b["budgetKWh"] - (100 + (500 - 100 - 400) / 6)) < 0.01   # ₹500 buys 100 kWh after the fixed ₹100


def test_target_kwh_and_costs_follow_slab_tariff(client, frozen):
    put_tariff(client, mode="slab", slabs=SLABS, fixedChargeINR=100)
    t = client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 1100}).json()
    assert t["monthlyTargetKWh"] == 200.0                       # 100 fixed + 400 + 600
    seed([(L(10, 9), 1.0, 100), (L(10, 17), 3.0, 100)])
    today = client.get("/api/insights/today", headers=AUTH).json()
    assert today["dailyTargetKWh"] == round(200 / 31, 2)
    assert "blended" in today["rateDisclosure"]
    assert today["effectiveRateINR"] == 4.0                     # still in the first slab at this pace


# ── item 1: budget checks see simulated appliances ─────────────────────────────

def test_budget_conflict_counts_simulated_appliances(client, frozen):
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 100})
    tv = client.post("/api/inventory/appliances", headers=AUTH,
                     json={"name": "Heater", "category": "Heating", "iconType": "heater", "ratedWatts": 2000}).json()
    with SessionLocal() as db:
        from app.models.db_models import SimEnergyHourly
        db.add(SimEnergyHourly(appliance_id=tv["id"], appliance_name="Heater", icon_type="heater",
                               category="Heating", bucket_start=L(5, 20), energy_kwh=20.0, on_seconds=3600 * 10,
                               power_max=2000, samples=100))
        db.commit()
        ids = {c.id: c for c in detect_conflicts(db, mqtt_connected=True)}
    # No metered energy at all: the old check (meter only) would have stayed silent.
    assert "target-exceeded" in ids and "simulated" in ids["target-exceeded"].evidence


def test_bill_check_uses_tariff_model(client, frozen):
    put_tariff(client, mode="slab", slabs=SLABS, fixedChargeINR=110)
    # 250 kWh under this tariff = 400 + 600 + 400 + 110 = ₹1510 → a ₹1500 bill is consistent
    client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026,
                                                  "unitsConsumedKWh": 250, "billAmountINR": 1500})
    client.post("/api/bills", headers=AUTH, json={"billingMonth": 1, "billingYear": 2026,
                                                  "unitsConsumedKWh": 250, "billAmountINR": 4000})
    with SessionLocal() as db:
        bill_conflicts = [c for c in detect_conflicts(db, mqtt_connected=True) if c.id.startswith("bill-rate:")]
    assert len(bill_conflicts) == 1 and "₹4000" in bill_conflicts[0].message


def test_projection_early_in_cycle_uses_last_24h(client, monkeypatch):
    now = L(1, 6)                                              # 6 h into a calendar cycle
    monkeypatch.setattr(bs, "utcnow", lambda: now)
    import app.services.insights_service as ins
    monkeypatch.setattr(ins, "utcnow", lambda: now)
    seed([(now - timedelta(hours=20), 0.0, 100), (now - timedelta(hours=1), 6.0, 100)])
    simulator.reset()
    p = client.get("/api/billing/projection", headers=AUTH).json()
    assert p["paceBasis"] == "last24h" and p["confidence"] == "low"
    assert p["projectedKWh"] > 100                             # ~6 kWh/day × 31 days


def test_budget_below_fixed_charge_is_flagged(client, frozen):
    put_tariff(client, fixedChargeINR=120)
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 100})
    with SessionLocal() as db:
        ids = {c.id for c in detect_conflicts(db, mqtt_connected=True)}
    assert "target-below-fixed" in ids



# ── item 3: cost per appliance on each bill ────────────────────────────────────

def _sim(db, appliance_id, name, bucket, kwh):
    from app.models.db_models import SimEnergyHourly
    db.add(SimEnergyHourly(appliance_id=appliance_id, appliance_name=name, icon_type="ac", category="Cooling",
                           bucket_start=bucket, energy_kwh=kwh, on_seconds=3600, power_max=1000, samples=1))


def test_bill_split_across_appliances_fixed_and_rest(client, frozen):
    put_tariff(client, fixedChargeINR=100)
    bill = client.post("/api/bills", headers=AUTH, json={
        "billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 100, "billAmountINR": 900}).json()
    seed([(from_local(datetime(2026, 2, 2)), 0.0, 100), (from_local(datetime(2026, 2, 20)), 20.0, 100)])
    with SessionLocal() as db:
        _sim(db, "app-ac", "AC", from_local(datetime(2026, 2, 10, 22)), 50.0)
        _sim(db, "app-ac", "AC", from_local(datetime(2026, 3, 2, 22)), 99.0)      # next period: ignored
        db.commit()
    r = client.get(f"/api/billing/bills/{bill['id']}/appliances", headers=AUTH).json()
    assert r["periodStart"] == "2026-02-01" and r["periodEnd"] == "2026-03-01" and r["periodSource"] == "cycle"
    assert r["measuredKWh"] == 70.0 and r["meteredKWh"] == 20.0 and r["simulatedKWh"] == 50.0
    assert r["fixedChargeINR"] == 100 and r["variableRateINR"] == 8.0      # (900 − 100) / 100 kWh
    shares = {a["name"]: a for a in r["appliances"]}
    assert shares["AC"]["costINR"] == 400.0 and shares["AC"]["source"] == "simulated"
    assert shares["Metered circuit"]["costINR"] == 160.0
    assert r["restKWh"] == 30.0 and r["restINR"] == 240.0
    total = sum(a["costINR"] for a in r["appliances"]) + r["fixedChargeINR"] + r["restINR"]
    assert abs(total - 900) < 0.01                                          # every rupee accounted for


def test_bill_split_scales_when_measured_exceeds_billed(client, frozen):
    bill = client.post("/api/bills", headers=AUTH, json={
        "billingPeriodStart": "2026-02-05", "billingPeriodEnd": "2026-02-06",
        "unitsConsumedKWh": 10, "billAmountINR": 75}).json()
    with SessionLocal() as db:
        _sim(db, "app-ac", "AC", from_local(datetime(2026, 2, 6, 20)), 40.0)  # end date is inclusive
        db.commit()
    r = client.get(f"/api/billing/bills/{bill['id']}/appliances", headers=AUTH).json()
    assert r["periodSource"] == "dates" and r["periodEnd"] == "2026-02-07"
    assert r["appliances"][0]["costINR"] == 75.0 and r["restINR"] == 0
    assert any("scaled" in n for n in r["notes"])


def test_bill_without_period_or_usage(client, frozen):
    empty = client.post("/api/bills", headers=AUTH, json={
        "billingMonth": 1, "billingYear": 2026, "unitsConsumedKWh": 50, "billAmountINR": 400}).json()
    r = client.get(f"/api/billing/bills/{empty['id']}/appliances", headers=AUTH).json()
    assert r["appliances"] == [] and r["restINR"] == 400 and r["notes"]
    assert client.get("/api/billing/bills/nope/appliances", headers=AUTH).status_code == 404


def test_projected_bill_per_appliance(client, frozen):
    put_tariff(client, fixedChargeINR=50)
    with SessionLocal() as db:
        _sim(db, "app-ac", "AC", L(5, 22), 30.0)
        _sim(db, "app-tv", "TV", L(6, 20), 10.0)
        db.commit()
    p = client.get("/api/billing/projection", headers=AUTH).json()
    costs = {a["name"]: a["costINR"] for a in p["applianceCosts"]}
    variable = p["projected"]["totalINR"] - p["projected"]["fixedChargeINR"]
    assert abs(costs["AC"] - variable * 0.75) < 0.05 and abs(costs["TV"] - variable * 0.25) < 0.05



# ── item 4: bill vs recorded usage (per day over the recorded hours) ──────────

def test_bill_vs_recorded_usage_per_day(client, frozen):
    bill = client.post("/api/bills", headers=AUTH, json={
        "billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 280, "billAmountINR": 2100}).json()
    with SessionLocal() as db:   # 12 recorded hours, 6 kWh in total → 12 kWh per recorded day
        for h in range(12):
            _sim(db, "app-ac", "AC", from_local(datetime(2026, 2, 10, 8 + h)), 0.5)
        db.commit()
    r = client.get(f"/api/billing/bills/{bill['id']}/appliances", headers=AUTH).json()
    assert r["periodDays"] == 28 and r["coveredHours"] == 12
    assert r["billedDailyKWh"] == 10.0 and r["recordedDailyKWh"] == 12.0 and r["variancePercent"] == 20.0


def test_recorded_daily_needs_enough_hours(client, frozen):
    bill = client.post("/api/bills", headers=AUTH, json={
        "billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 280, "billAmountINR": 2100}).json()
    with SessionLocal() as db:
        _sim(db, "app-ac", "AC", from_local(datetime(2026, 2, 10, 8)), 2.0)
        db.commit()
    r = client.get(f"/api/billing/bills/{bill['id']}/appliances", headers=AUTH).json()
    assert r["recordedDailyKWh"] is None and r["variancePercent"] is None and r["billedDailyKWh"] == 10.0
