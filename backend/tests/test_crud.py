"""Phase 7: household, rooms, appliances, bills, target."""

from __future__ import annotations

from conftest import AUTH


def test_household_default_seed_and_round_trip(client):
    cfg = client.get("/api/household/config", headers=AUTH).json()
    assert cfg["occupants"] == 2 and cfg["tariffRateINRPerKWh"] == 7.5
    r = client.put("/api/household/config", headers=AUTH,
                   json={"homeName": "Villa", "occupants": 4, "tariffRateINRPerKWh": 8.0})
    assert r.status_code == 200
    again = client.get("/api/household/config", headers=AUTH).json()
    assert again["homeName"] == "Villa" and again["occupants"] == 4 and again["tariffRateINRPerKWh"] == 8.0


def test_household_accepts_snake_case_and_rejects_null_required(client):
    assert client.put("/api/household/config", headers=AUTH, json={"home_name": "A"}).json()["homeName"] == "A"
    assert client.put("/api/household/config", headers=AUTH, json={"homeName": None}).status_code == 422
    assert client.put("/api/household/config", headers=AUTH, json={"occupants": 0}).status_code == 422


def test_rooms_seeded_and_crud(client):
    rooms = client.get("/api/inventory/rooms", headers=AUTH).json()
    assert [r["id"] for r in rooms] == ["room-living", "room-kitchen", "room-master-bed", "room-bathroom", "room-balcony"]
    room = client.post("/api/inventory/rooms", headers=AUTH, json={"name": "Study", "roomType": "office"}).json()
    assert client.put(f"/api/inventory/rooms/{room['id']}", headers=AUTH, json={"name": "Office"}).json()["name"] == "Office"
    assert client.post("/api/inventory/rooms", headers=AUTH, json={"id": room["id"], "name": "x"}).status_code == 409
    assert client.delete(f"/api/inventory/rooms/{room['id']}", headers=AUTH).status_code == 204
    assert client.delete(f"/api/inventory/rooms/{room['id']}", headers=AUTH).status_code == 404


def test_room_delete_keeps_appliances(client):
    room = client.post("/api/inventory/rooms", headers=AUTH, json={"name": "Study"}).json()
    app_ = client.post("/api/inventory/appliances", headers=AUTH,
                       json={"name": "Lamp", "roomId": room["id"], "ratedWatts": 10}).json()
    client.delete(f"/api/inventory/rooms/{room['id']}", headers=AUTH)
    items = {a["id"]: a for a in client.get("/api/inventory/appliances", headers=AUTH).json()}
    assert app_["id"] in items and items[app_["id"]]["roomId"] is None


def test_appliance_crud_filter_and_unassign(client):
    client.get("/api/inventory/rooms", headers=AUTH)
    a = client.post("/api/inventory/appliances", headers=AUTH,
                    json={"name": "AC", "roomId": "room-living", "category": "cooling",
                          "ratedWatts": 1450, "dailyHours": 6, "isEssential": "yes"}).json()
    assert a["isEssential"] == "yes"
    assert client.post("/api/inventory/appliances", headers=AUTH,
                       json={"name": "X", "isEssential": "maybe"}).status_code == 422
    assert [x["id"] for x in client.get("/api/inventory/appliances?roomId=room-living", headers=AUTH).json()] == [a["id"]]
    u = client.put(f"/api/inventory/appliances/{a['id']}", headers=AUTH, json={"dailyHours": 7.5}).json()
    assert u["dailyHours"] == 7.5 and u["roomId"] == "room-living"  # untouched fields preserved
    u = client.put(f"/api/inventory/appliances/{a['id']}", headers=AUTH, json={"roomId": None}).json()
    assert u["roomId"] is None
    assert client.delete(f"/api/inventory/appliances/{a['id']}", headers=AUTH).status_code == 204


def test_appliance_validation(client):
    assert client.post("/api/inventory/appliances", headers=AUTH,
                       json={"name": "X", "roomId": "no-such-room"}).status_code == 400
    assert client.post("/api/inventory/appliances", headers=AUTH, json={"name": "X", "dailyHours": 25}).status_code == 422
    assert client.post("/api/inventory/appliances", headers=AUTH, json={"name": ""}).status_code == 422


def test_bills_crud_sorted_and_validated(client):
    for m, y in ((3, 2026), (9, 2026), (12, 2025)):
        r = client.post("/api/bills", headers=AUTH,
                        json={"billingMonth": m, "billingYear": y, "unitsConsumedKWh": 100, "billAmountINR": 800})
        assert r.status_code == 201
    bills = client.get("/api/bills", headers=AUTH).json()
    assert [(b["billingYear"], b["billingMonth"]) for b in bills] == [(2026, 9), (2026, 3), (2025, 12)]
    bid = bills[0]["id"]
    assert client.put(f"/api/bills/{bid}", headers=AUTH, json={"billAmountINR": 950}).json()["billAmountINR"] == 950
    assert client.delete(f"/api/bills/{bid}", headers=AUTH).status_code == 204
    assert len(client.get("/api/bills", headers=AUTH).json()) == 2
    bad = {"unitsConsumedKWh": 0, "billAmountINR": 0}
    assert client.post("/api/bills", headers=AUTH, json=bad).status_code == 422
    assert client.post("/api/bills", headers=AUTH,
                       json={"unitsConsumedKWh": 10, "billAmountINR": 5, "billingMonth": 13}).status_code == 422


def test_target_default_upsert_and_validation(client):
    t = client.get("/api/target", headers=AUTH).json()
    assert t["isConfigured"] is False and t["monthlyTargetKWh"] is None
    r = client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 1800, "targetType": "budget"}).json()
    assert r["isConfigured"] is True and r["monthlyBudgetINR"] == 1800 and r["monthlyTargetKWh"] == 240.0
    assert client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 50}).status_code == 422
    assert client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 200000}).status_code == 422
    assert client.put("/api/target", headers=AUTH,
                      json={"monthlyBudgetINR": 500, "targetType": "weird"}).status_code == 422


def test_household_is_configured_flag(client):
    assert client.get("/api/household/config", headers=AUTH).json()["isConfigured"] is False
    r = client.put("/api/household/config", headers=AUTH, json={"isConfigured": True, "homeName": "Home"})
    assert r.json()["isConfigured"] is True
    assert client.put("/api/household/config", headers=AUTH, json={"isConfigured": None}).status_code == 422


def test_bill_optional_period_fields_round_trip(client):
    body = {"unitsConsumedKWh": 240, "billAmountINR": 1920, "billingMonth": 10, "billingYear": 2026,
            "billingPeriodStart": "2026-10-01", "billingPeriodEnd": "2026-10-31", "billingPeriodDays": 31,
            "dueDate": "15 Nov", "documentFilename": "oct.pdf"}
    b = client.post("/api/bills", headers=AUTH, json=body).json()
    for k, v in body.items():
        assert b[k] == v, k
    assert client.post("/api/bills", headers=AUTH,
                       json={**body, "billingPeriodStart": "1 Oct"}).status_code == 422


def test_target_can_be_cleared(client):
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 1800})
    assert client.delete("/api/target", headers=AUTH).status_code == 204
    t = client.get("/api/target", headers=AUTH).json()
    assert t["isConfigured"] is False and t["monthlyBudgetINR"] == 0
