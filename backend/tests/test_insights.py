"""Phase 8: insights, today breakdown and recommendations (clock frozen at FAKE_NOW)."""

from __future__ import annotations

from datetime import datetime

from app.utils.timestamps import from_local
from conftest import AUTH, seed


def L(day: int, hour: int, minute: int = 0):
    """Local (IST) time in March 2026."""
    return from_local(datetime(2026, 3, day, hour, minute))


def seed_week():
    rows = []
    for h in range(1, 22):                      # Sun 8 Mar: 10 → 11 kWh  (1 kWh)
        rows.append((L(8, h), 10 + (h - 1) / 20, 200))
    for h in range(1, 22):                      # Mon 9 Mar: 11 → 14 kWh  (3 kWh)
        rows.append((L(9, h), 11 + 3 * (h - 1) / 20, 600))
    rows += [(L(10, 0, 5), 14.0, 100), (L(10, 18, 0), 14.5, 100)]   # Tue 10 Mar: 0.5 kWh at 6pm
    seed(rows)


def get(client, path):
    r = client.get(path, headers=AUTH)
    assert r.status_code == 200, r.text
    return r.json()


# ── honest empty state ─────────────────────────────────────────────────────────

def test_empty_state_is_not_fabricated(client, freeze_insights):
    r = get(client, "/api/insights?period=week")
    assert r["hasData"] is False and r["totalKWh"] == 0 and r["isModelledEstimate"] is False
    assert all(p["usageKWh"] == 0 and p["measured"] is False and not p["isPeak"] for p in r["trendPoints"])
    assert r["shifts"] == [] and r["dataNote"]
    t = get(client, "/api/insights/today")
    assert t["hasData"] is False and all(p["usageKWh"] == 0 for p in t["hourlyPoints"])
    assert t["dailyTargetKWh"] is None and t["insightCard"]["badgeText"] == "No Data"
    assert get(client, "/api/insights/recommendations") == []


# ── week insights from real register deltas ────────────────────────────────────

def test_week_insights_use_real_per_day_values(client, freeze_insights):
    seed_week()
    r = get(client, "/api/insights?period=week")
    assert r["hasData"] is True
    assert abs(r["totalKWh"] - 4.5) < 1e-6
    by_label = {p["label"]: p for p in r["trendPoints"]}
    assert [p["label"] for p in r["trendPoints"]] == ["Wed", "Thu", "Fri", "Sat", "Sun", "Mon", "Tue"]
    assert abs(by_label["Sun"]["usageKWh"] - 1.0) < 1e-6
    assert abs(by_label["Mon"]["usageKWh"] - 3.0) < 1e-6
    assert abs(by_label["Tue"]["usageKWh"] - 0.5) < 1e-6
    assert by_label["Wed"]["measured"] is False and by_label["Wed"]["usageKWh"] == 0
    assert [p["label"] for p in r["trendPoints"] if p["isPeak"]] == ["Mon"]
    assert r["totalCostINR"] == round(4.5 * 7.5, 2) and r["isCostEstimated"] is True
    assert r["coverageHours"] == 44 and r["dataNote"]           # gaps disclosed
    assert "Mon" in r["keyInsight"]["title"]


def test_targets_only_when_configured(client, freeze_insights):
    seed_week()
    assert all(p["targetKWh"] is None for p in get(client, "/api/insights?period=week")["trendPoints"])
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 2325})  # 310 kWh/month → 10/day in March
    pts = get(client, "/api/insights?period=week")["trendPoints"]
    assert all(abs(p["targetKWh"] - 10.0) < 0.01 for p in pts)


def test_month_and_year_have_trend_points(client, freeze_insights):
    seed_week()
    m = get(client, "/api/insights?period=month")
    assert [p["label"] for p in m["trendPoints"]] == ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5"]
    assert abs(m["trendPoints"][1]["usageKWh"] - 4.5) < 1e-6 and m["trendPoints"][1]["isPeak"]
    y = get(client, "/api/insights?period=year")
    assert len(y["trendPoints"]) == 12 and y["trendPoints"][0]["label"] == "Jan"
    assert abs(y["trendPoints"][2]["usageKWh"] - 4.5) < 1e-6   # March
    assert client.get("/api/insights?period=decade", headers=AUTH).status_code == 422


def test_register_reset_is_handled(client, freeze_insights):
    seed([(L(10, 10), 50.0, 100), (L(10, 11), 51.0, 100), (L(10, 12), 0.1, 100), (L(10, 13), 0.6, 100)])
    assert abs(get(client, "/api/insights?period=week")["totalKWh"] - 1.6) < 1e-6


def test_period_comparison(client, freeze_insights):
    seed([(L(2, 9), 1.0, 100), (L(2, 20), 3.0, 100),      # previous week: 2 kWh
          (L(9, 9), 3.0, 100), (L(9, 20), 6.0, 100)])     # this week: 3 kWh
    r = get(client, "/api/insights?period=week")
    assert abs(r["totalKWh"] - 3.0) < 1e-6
    assert r["comparison"]["previousKWh"] == 2.0 and r["comparison"]["percentChange"] == 50.0


def test_shifts_are_appliance_estimates_only(client, freeze_insights):
    client.post("/api/inventory/appliances", headers=AUTH,
                json={"name": "AC", "category": "cooling", "ratedWatts": 1500, "dailyHours": 6})
    client.post("/api/inventory/appliances", headers=AUTH,
                json={"name": "Fan", "category": "fans", "ratedWatts": 75, "dailyHours": 10})
    client.post("/api/inventory/appliances", headers=AUTH, json={"name": "Unrated lamp", "category": "lighting"})
    r = get(client, "/api/insights?period=week")
    assert r["shiftsAreEstimates"] is True and r["hasData"] is False and r["totalKWh"] == 0
    assert [(s["categoryId"], s["kwh"]) for s in r["shifts"]] == [("cooling", 63.0), ("fans", 5.25)]
    assert all(s["percentChange"] is None for s in r["shifts"])


def test_bill_comparison(client, freeze_insights):
    seed_week()
    client.post("/api/bills", headers=AUTH,
                json={"billingMonth": 2, "billingYear": 2026, "unitsConsumedKWh": 280, "billAmountINR": 2240})
    bc = get(client, "/api/insights?period=week")["billComparison"]
    assert bc["billDailyKWh"] == 10.0 and bc["billRateINR"] == 8.0
    assert abs(bc["measuredDailyKWh"] - round(4.5 / (44 / 24), 2)) < 0.01


# ── today ──────────────────────────────────────────────────────────────────────

def test_today_hourly_bucketing(client, freeze_insights):
    seed_week()
    t = get(client, "/api/insights/today")
    assert t["date"] == "2026-03-10" and t["hasData"] is True
    assert abs(t["energyTodayKWh"] - 0.5) < 1e-6
    assert [p["hour"] for p in t["hourlyPoints"] if p["usageKWh"] > 0] == [18]
    assert [p["hour"] for p in t["hourlyPoints"] if p["measured"]] == [0, 18]
    assert [p["hour"] for p in t["hourlyPoints"] if p["isPeak"]] == [18]
    evening = next(p for p in t["dayPeriods"] if p["period"] == "evening")
    assert evening["percentage"] == 100.0
    assert t["costTodayINR"] == round(0.5 * 7.5, 2)


def test_today_against_target(client, freeze_insights):
    seed_week()
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 116.25})  # 15.5 kWh/month → 0.5 kWh/day
    t = get(client, "/api/insights/today")
    assert t["isTargetConfigured"] is True and abs(t["dailyTargetKWh"] - 0.5) < 0.01
    assert t["insightCard"]["badgeText"] == "On Track"


# ── recommendations fire only with supporting data ─────────────────────────────

def _ids(client):
    return [r["id"] for r in get(client, "/api/insights/recommendations")]


def test_low_power_factor_and_voltage(client, freeze_insights):
    # 40 readings every 5 min from 10:00 on 10 Mar: PF 0.70 at 200 W, voltage 195 V
    seed([(L(10, 10 + i // 12, (i % 12) * 5), 1 + i * 0.01, 200, 0.70, 195.0) for i in range(40)])
    recs = get(client, "/api/insights/recommendations")
    ids = [r["id"] for r in recs]
    assert "rec-low-pf" in ids and "rec-voltage" in ids
    assert recs[0]["priority"] == "high" and all(r["evidence"] for r in recs)


def test_overnight_baseload(client, freeze_insights):
    rows, e = [], 5.0
    for d in (7, 8, 9):
        for h in (1, 2, 3, 4):
            for m in (0, 30):
                e += 0.075
                rows.append((L(d, h, m), e, 150))
    seed(rows)
    assert "rec-overnight-baseload" in _ids(client)


def _seed_evening_heavy():
    rows, e = [], 1.0
    for d in (7, 8, 9):
        for h in range(24):
            e += 0.5 if 18 <= h < 22 else 0.05
            rows.append((L(d, h, 30), e, 300))
    seed(rows)


def test_evening_peak_and_budget_projection(client, freeze_insights):
    _seed_evening_heavy()
    assert "rec-evening-peak" in _ids(client)
    assert "rec-budget-projection" not in _ids(client)          # no target configured
    client.put("/api/target", headers=AUTH, json={"monthlyBudgetINR": 100})
    recs = get(client, "/api/insights/recommendations")
    assert recs[0]["id"] == "rec-budget-projection" and recs[0]["priority"] == "high"


def test_heavy_appliance_from_inventory(client, freeze_insights):
    client.post("/api/inventory/appliances", headers=AUTH,
                json={"name": "Geyser", "category": "heating", "ratedWatts": 2000, "dailyHours": 4})
    assert _ids(client) == ["rec-heavy-appliance"]
