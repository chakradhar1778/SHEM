"""Notifications (bill due, budget, slab, bill vs usage), the budget saver, and bills per location."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.database import SessionLocal
from app.models.db_models import Appliance, SimEnergyHourly
from app.services import alerts_service as al
from app.services import billing_service as bs
from app.services.simulation_service import simulator
from app.utils.timestamps import from_local
from conftest import AUTH, FAKE_NOW


def L(day: int, hour: int, month: int = 3) -> datetime:
    return from_local(datetime(2026, month, day, hour))


@pytest.fixture
def frozen(monkeypatch, freeze_insights):
    """Tue 10 March 2026, 18:30 IST everywhere the checks look at the clock."""
    import app.ai.conflicts as conflicts
    for mod in (bs, al, conflicts):
        monkeypatch.setattr(mod, "utcnow", lambda: FAKE_NOW)
    bs.clear_rate_cache()
    return FAKE_NOW


def check(client):
    r = client.post("/api/notifications/check", headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


def keys(db=None):
    with SessionLocal() as s:
        from app.models.db_models import Notification
        return {n.dedupe_key for n in s.query(Notification).all()}


def sim_energy(appliance_id, name, kwh, bucket=None):
    with SessionLocal() as db:
        db.add(SimEnergyHourly(appliance_id=appliance_id, appliance_name=name, icon_type="ac", category="Cooling",
                               bucket_start=bucket or L(5, 20), energy_kwh=kwh, on_seconds=3600, power_max=1500,
                               samples=1))
        db.commit()


# ── item 7: alerts ─────────────────────────────────────────────────────────────

def test_bill_due_soon_and_overdue_fire_once(client, frozen):
    client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 100,
                                                  "billAmountINR": 800, "dueDate": "2026-03-12"})
    client.post("/api/bills", headers=AUTH, json={"billingMonth": 1, "billingYear": 2026, "unitsConsumedKWh": 100,
                                                  "billAmountINR": 700, "dueDate": "2026-03-07",
                                                  "locationTag": "parents_home"})
    client.post("/api/bills", headers=AUTH, json={"billingMonth": 12, "billingYear": 2025, "unitsConsumedKWh": 90,
                                                  "billAmountINR": 650, "dueDate": "2026-01-10"})   # long past: ignored
    r = check(client)
    titles = {n["title"] for n in r["items"]}
    assert "Bill due in 2 days" in titles and "Bill due date passed (Parents’ home)" in titles
    assert r["unreadCount"] == 2
    assert check(client)["unreadCount"] == 2                     # deduplicated


def test_budget_thresholds_and_projection(client, frozen):
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 100})
    from datetime import timedelta
    for h in range(30):                                          # 11 kWh over 30 hours: ₹82.5 at ₹7.5 → 82 %
        sim_energy("app-ac", "AC", 11.0 / 30, L(5, 0) + timedelta(hours=h))
    check(client)
    assert {"budget-80:2026-03-01", "budget-projected:2026-03-01"} <= keys()
    assert "budget-100:2026-03-01" not in keys()
    sim_energy("app-ac", "AC", 3.0, L(6, 20))                    # ₹105 → over
    check(client)
    assert "budget-100:2026-03-01" in keys()


def test_slab_near_and_entered(client, frozen):
    client.put("/api/billing/tariff", headers=AUTH, json={"mode": "slab", "slabs": [
        {"uptoKWh": 50, "rateINR": 4}, {"uptoKWh": 100, "rateINR": 6}, {"uptoKWh": None, "rateINR": 8}]})
    sim_energy("app-ac", "AC", 47.0)                             # 3 kWh before the ₹6 slab
    check(client)
    assert "slab-near:2026-03-01:1" in keys() and not any(k.startswith("slab-entered") for k in keys())
    sim_energy("app-ac", "AC", 10.0, L(6, 20))
    check(client)
    assert "slab-entered:2026-03-01:1" in keys()


def test_bill_vs_usage_mismatch_alert(client, frozen):
    bill = client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026,
                                                         "unitsConsumedKWh": 28, "billAmountINR": 220}).json()
    from datetime import timedelta
    for h in range(24):                                          # 24 recorded hours × 0.5 = 12 kWh/day vs 1 billed
        sim_energy("app-ac", "AC", 0.5, from_local(datetime(2026, 2, 10, 0)) + timedelta(hours=h))
    check(client)
    assert f"bill-mismatch:{bill['id']}" in keys()


def test_mark_read(client, frozen):
    client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 100,
                                                  "billAmountINR": 800, "dueDate": "2026-03-10"})
    items = check(client)["items"]
    assert items[0]["title"] == "Bill due today" and items[0]["readAt"] is None
    assert client.post(f"/api/notifications/{items[0]['id']}/read", headers=AUTH).json()["readAt"]
    assert client.get("/api/notifications", headers=AUTH).json()["unreadCount"] == 0
    assert client.post("/api/notifications/999/read", headers=AUTH).status_code == 404
    assert client.post("/api/notifications/read-all", headers=AUTH).status_code == 200


# ── item 8: budget saver ───────────────────────────────────────────────────────

def _appliances(client):
    tv = client.post("/api/inventory/appliances", headers=AUTH, json={
        "name": "TV", "category": "Entertainment", "iconType": "tv", "ratedWatts": 100, "isEssential": "no"}).json()
    fridge = client.post("/api/inventory/appliances", headers=AUTH, json={
        "name": "Fridge", "category": "Refrigerator", "iconType": "fridge", "ratedWatts": 150,
        "isEssential": "yes"}).json()
    unsure = client.post("/api/inventory/appliances", headers=AUTH, json={
        "name": "Fan", "category": "Fans", "iconType": "fan", "ratedWatts": 75, "isEssential": "unsure"}).json()
    with SessionLocal() as db:
        for a in db.query(Appliance).all():
            a.status = "on"                                      # all running
        db.commit()
    return tv, fridge, unsure


def test_budget_saver_off_suggest_auto(client, frozen):
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 100})
    tv, fridge, fan = _appliances(client)
    sim_energy("app-x", "Heater", 20.0)                          # ₹150 > ₹100 → over

    s = client.get("/api/automation/budget-saver", headers=AUTH).json()
    assert s["mode"] == "off" and [c["name"] for c in s["candidates"]] == ["TV"]
    check(client)
    assert not any(k.startswith("saver") for k in keys())        # off: nothing

    client.put("/api/automation/budget-saver", headers=AUTH, json={"mode": "suggest"})
    check(client)
    assert any(k.startswith("saver-suggest") for k in keys())
    with SessionLocal() as db:
        assert db.get(Appliance, tv["id"]).status == "on"       # suggest never switches

    client.put("/api/automation/budget-saver", headers=AUTH, json={"mode": "auto", "trigger": "over"})
    simulator.reset()
    check(client)
    with SessionLocal() as db:
        assert db.get(Appliance, tv["id"]).sim_manual_state == "OFF"
        assert db.get(Appliance, fridge["id"]).sim_manual_state is None      # essential: untouched
        assert db.get(Appliance, fan["id"]).sim_manual_state is None         # "not sure": untouched
        db.get(Appliance, tv["id"]).status = "on"                            # user turns it back on
        db.commit()
    check(client)
    log = client.get("/api/automation/budget-saver", headers=AUTH).json()["log"]
    assert [e["action"] for e in log].count("switched_off") == 1             # respected for 24 h
    assert any(k.startswith(f"saver-off:{tv['id']}") for k in keys())


def test_budget_saver_waits_for_trigger(client, frozen):
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 1000})
    tv, *_ = _appliances(client)
    client.put("/api/automation/budget-saver", headers=AUTH, json={"mode": "auto", "trigger": "over"})
    sim_energy("app-x", "Heater", 2.0)                           # well within budget
    check(client)
    with SessionLocal() as db:
        assert db.get(Appliance, tv["id"]).sim_manual_state is None


# ── item 9: bills per location ─────────────────────────────────────────────────

def test_other_location_bills_are_kept_out_of_home_analytics(client, frozen):
    client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 280,
                                                  "billAmountINR": 2240})
    office = client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026,
                                                           "unitsConsumedKWh": 900, "billAmountINR": 12000,
                                                           "locationTag": "office"}).json()
    bc = client.get("/api/insights?period=week", headers=AUTH).json()["billComparison"]
    assert bc["billDailyKWh"] == 10.0                            # the home bill, not the office
    assert client.get(f"/api/billing/bills/{office['id']}/appliances", headers=AUTH).status_code == 422
    with SessionLocal() as db:
        from app.ai.conflicts import detect_conflicts
        ids = {c.id for c in detect_conflicts(db, mqtt_connected=True)}
    assert not any(i.startswith("bill-duplicate") for i in ids)  # same month, different places
    assert f"bill-rate:{office['id']}" not in ids                 # office tariff isn't this home's



# ── mark as paid ───────────────────────────────────────────────────────────────

def test_mark_paid_stops_alerts_and_clears_them(client, frozen, monkeypatch):
    import app.api.bills as bills_api
    monkeypatch.setattr(bills_api, "utcnow", lambda: FAKE_NOW)
    due = client.post("/api/bills", headers=AUTH, json={"billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 100,
                                                        "billAmountINR": 800, "dueDate": "2026-03-07"}).json()
    assert due["paidOn"] is None
    assert check(client)["unreadCount"] == 1                      # overdue alert

    paid = client.post(f"/api/bills/{due['id']}/paid", headers=AUTH, json={"paidOn": "2026-03-06"}).json()
    assert paid["paidOn"] == "2026-03-06" and paid["paidAt"]
    assert client.get("/api/notifications", headers=AUTH).json()["unreadCount"] == 0   # its alert marked read

    soon = client.post("/api/bills", headers=AUTH, json={"billingMonth": 3, "billingYear": 2026, "unitsConsumedKWh": 90,
                                                         "billAmountINR": 700, "dueDate": "2026-03-11"}).json()
    client.post(f"/api/bills/{soon['id']}/paid", headers=AUTH)    # default: today
    assert client.get("/api/bills", headers=AUTH).json()[0]["paidOn"] == "2026-03-10"
    assert check(client)["unreadCount"] == 0                      # paid before it was due: no alert

    assert client.post(f"/api/bills/{soon['id']}/paid", headers=AUTH, json={"paidOn": "2026-03-20"}).status_code == 422
    assert client.post(f"/api/bills/{soon['id']}/paid", headers=AUTH, json={"paidOn": "2026-02-30"}).status_code == 422
    assert client.post("/api/bills/nope/paid", headers=AUTH).status_code == 404
    unpaid = client.delete(f"/api/bills/{soon['id']}/paid", headers=AUTH).json()
    assert unpaid["paidOn"] is None and unpaid["paidAt"] is None
