"""
Tests for the three SHEM client requirements:
  1. Relay load mismatch detection, adjustable threshold, big-diff safety warning,
     and re-identification / switching flow.
  2. AI-assisted bill scanning with defined structured error format.
  3. Multiple API keys per provider (Gemini & Groq) with round-robin and back-off.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.ai import providers
from app.ai.providers import LLMRouter, MultiKeyProvider, ProviderTurn
from app.config import Settings
from app.database import SessionLocal
from app.models.db_models import Appliance, RelayChannel
from app.services import relay_mismatch_service
from app.services.device_service import get_or_create_device
from app.utils.timestamps import utcnow
from tests.conftest import AUTH, seed

# Minimal valid 1x1 PNG bytes (passes magic-number check)
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
)


class _StubKeyProvider:
    def __init__(self, name: str, key: str, responses: list):
        self.name = name
        self.model = "stub-model"
        self.key = key
        self.responses = list(responses)
        self.calls = 0

    async def stream(self, messages, tools, temperature):
        self.calls += 1
        item = self.responses.pop(0) if self.responses else f"ok:{self.key}"
        if isinstance(item, Exception):
            raise item
        yield ("text", item)
        yield ("done", ProviderTurn(text=item, tool_calls=[], provider=self.name))


@pytest.fixture(autouse=True)
def _reset_mismatch_and_router():
    relay_mismatch_service.clear_snooze()
    providers.set_router(None)
    yield
    relay_mismatch_service.clear_snooze()
    providers.set_router(None)


def _set_relay_state(state: str = "ON", device_id: str = "001") -> None:
    with SessionLocal() as db:
        get_or_create_device(db, device_id)
        rc = RelayChannel(device_id=device_id, channel=1, commanded_state=state, last_reported_at=utcnow())
        db.add(rc)
        db.commit()


# ═════════════════════════════════════════════════════════════════════════════
# REQUIREMENT 3 — Multi-key round-robin & back-off
# ═════════════════════════════════════════════════════════════════════════════

def test_settings_parses_multiple_keys_deduped():
    s = Settings(
        _env_file=None,
        gemini_api_key="g-fallback",
        gemini_api_keys="g-1, g-2 , g-1,g-3",
        groq_api_key="q-1,q-2",
        groq_api_keys="q-2;q-3",
    )
    assert s.gemini_keys_list == ["g-1", "g-2", "g-3", "g-fallback"]
    assert s.groq_keys_list == ["q-2", "q-3", "q-1"]


def test_multikey_round_robin_and_rate_limit_failover():
    created: dict[str, _StubKeyProvider] = {}
    plans = {
        "k1": ["ok:k1", RuntimeError("429 resource_exhausted quota exceeded")],
        "k2": ["ok:k2", "ok:k2-backup"],
        "k3": ["ok:k3", "ok:k3-second"],
    }

    def factory(key: str):
        stub = _StubKeyProvider("gemini", key, plans[key])
        created[key] = stub
        return stub

    multi = MultiKeyProvider("gemini", ["k1", "k2", "k3"], "https://example.invalid", "m", 10.0, provider_factory=factory)
    router = LLMRouter([multi])

    # First 3 calls round-robin cleanly across k1 -> k2 -> k3
    t1 = asyncio.run(router.complete([{"role": "user", "content": "a"}]))
    t2 = asyncio.run(router.complete([{"role": "user", "content": "b"}]))
    t3 = asyncio.run(router.complete([{"role": "user", "content": "c"}]))
    assert [t1.text, t2.text, t3.text] == ["ok:k1", "ok:k2", "ok:k3"]

    # 4th call starts on k1 -> hits 429 -> immediately rotates to k2 in the same call!
    t4 = asyncio.run(router.complete([{"role": "user", "content": "d"}]))
    assert t4.text == "ok:k2-backup"
    assert multi.key_count == 3
    assert multi.healthy_key_count == 2  # k1 is now in back-off


def test_multikey_auth_failure_disables_key_and_falls_back_to_next_provider():
    def bad_factory(key: str):
        return _StubKeyProvider("gemini", key, [RuntimeError("401 unauthorized invalid api key")])

    def good_factory(key: str):
        return _StubKeyProvider("groq", key, ["groq-saved-the-day"])

    g = MultiKeyProvider("gemini", ["bad-1", "bad-2"], "https://example.invalid", "m", 10.0, provider_factory=bad_factory)
    q = MultiKeyProvider("groq", ["q-good"], "https://example.invalid", "m", 10.0, provider_factory=good_factory)
    router = LLMRouter([g, q])

    turn = asyncio.run(router.complete([{"role": "user", "content": "hi"}]))
    assert turn.provider == "groq"
    assert turn.text == "groq-saved-the-day"
    assert g.healthy_key_count == 0
    assert q.healthy_key_count == 1


# ═════════════════════════════════════════════════════════════════════════════
# REQUIREMENT 2 — AI Bill Scan with defined structured errors
# ═════════════════════════════════════════════════════════════════════════════

def test_bill_scan_success(client):
    payload = json.dumps({
        "ok": True,
        "provider": "TSSPDCL",
        "account_id": "USC-998877",
        "units_kwh": 245.5,
        "amount_inr": 1890.0,
        "billing_month": 10,
        "billing_year": 2026,
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "due_date": "2026-11-15",
        "confidence": "high",
        "warnings": [],
        "scan_note": "Extracted from summary table.",
    })
    gemini = _StubKeyProvider("gemini", "k1", [payload])
    providers.set_router(LLMRouter([gemini]))

    r = client.post("/api/bills/scan", headers={**AUTH, "Content-Type": "image/png"}, content=PNG_BYTES)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["error"] is None
    assert body["provider"] == "TSSPDCL"
    assert body["accountId"] == "USC-998877"
    assert body["unitsKWh"] == 245.5
    assert body["amountINR"] == 1890.0
    assert body["billingMonth"] == 10
    assert body["billingYear"] == 2026
    assert body["dueDate"] == "2026-11-15"
    assert body["confidence"] == "high"


def test_bill_scan_structured_ai_error_not_a_bill(client):
    payload = json.dumps({
        "ok": False,
        "error": {
            "code": "not_a_bill",
            "title": "Not an electricity bill",
            "detail": "This image looks like a grocery receipt rather than an electricity bill.",
            "hint": "Upload a photo or PDF of your electricity utility bill.",
        },
    })
    providers.set_router(LLMRouter([_StubKeyProvider("gemini", "k1", [payload])]))

    r = client.post("/api/bills/scan", headers={**AUTH, "Content-Type": "image/png"}, content=PNG_BYTES)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "not_a_bill"
    assert body["error"]["title"] == "Not an electricity bill"
    assert "grocery receipt" in body["error"]["detail"]
    assert body["error"]["hint"]


def test_bill_scan_groq_only_returns_vision_unsupported(client):
    providers.set_router(LLMRouter([_StubKeyProvider("groq", "q1", ["ignored"])]))
    r = client.post("/api/bills/scan", headers={**AUTH, "Content-Type": "image/png"}, content=PNG_BYTES)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "vision_unsupported"


def test_bill_scan_rejects_disguised_file_with_structured_error(client):
    providers.set_router(LLMRouter([_StubKeyProvider("gemini", "k1", ["ignored"])]))
    r = client.post("/api/bills/scan", headers={**AUTH, "Content-Type": "image/png"}, content=b"not actually a png")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_file"


# ═════════════════════════════════════════════════════════════════════════════
# REQUIREMENT 1 — Relay mismatch detection, settings threshold & re-identification
# ═════════════════════════════════════════════════════════════════════════════

def test_relay_mismatch_voltage_tolerance_vs_alert_vs_big_diff(client):
    # Register a 9W bulb on Relay 1
    r = client.post(
        "/api/inventory/appliances",
        headers=AUTH,
        json={"id": "app-bulb", "name": "LED Bulb", "ratedWatts": 9, "relayChannel": 1},
    )
    assert r.status_code == 201
    _set_relay_state("ON")

    # 1) Normal low/high voltage fluctuation (7.5 W on a 9 W bulb = 16.7% < 30%) -> NO mismatch
    seed([(utcnow(), 1.0, 7.5)])
    m = client.get("/api/relay/1/mismatch", headers=AUTH).json()
    assert m["active"] is False
    assert m["thresholdPercent"] == 30.0

    # 2) Different load (25 W mini fan on 9 W bulb = 177% > 30%, < 5x) -> mismatch active + notification
    seed([(utcnow(), 1.01, 25.0)])
    m2 = client.get("/api/relay/1/mismatch", headers=AUTH).json()
    assert m2["active"] is True
    assert m2["isBigDiff"] is False
    assert m2["applianceId"] == "app-bulb"

    notifs = client.post("/api/notifications/check", headers=AUTH).json()
    mm_notifs = [n for n in notifs["items"] if n["kind"] == "relay_mismatch"]
    assert len(mm_notifs) == 1
    assert mm_notifs[0]["metadata"]["liveWatts"] == 25.0
    assert mm_notifs[0]["metadata"]["applianceId"] == "app-bulb"

    # Confirming "Still LED Bulb" for moderate diff succeeds & snoozes
    c1 = client.post("/api/relay/1/mismatch/confirm-same", headers=AUTH).json()
    assert c1["accepted"] is True
    assert c1["requiresWarning"] is False
    assert client.get("/api/relay/1/mismatch", headers=AUTH).json()["active"] is False

    # 3) Huge diff (1000 W on 9 W bulb >= 5x) overrides snooze AND requires safety warning!
    seed([(utcnow(), 1.05, 1000.0)])
    m3 = client.get("/api/relay/1/mismatch", headers=AUTH).json()
    assert m3["active"] is True
    assert m3["isBigDiff"] is True

    c2 = client.post("/api/relay/1/mismatch/confirm-same", headers=AUTH).json()
    assert c2["accepted"] is False
    assert c2["requiresWarning"] is True
    assert "1000 W" in c2["message"]


def test_relay_mismatch_adjustable_threshold_and_matching_appliance_switch(client):
    # Register 9W Bulb on Relay 1 and 25W Mini Fan (unassigned)
    assert client.post(
        "/api/inventory/appliances",
        headers=AUTH,
        json={"id": "app-bulb", "name": "LED Bulb", "ratedWatts": 9, "relayChannel": 1},
    ).status_code == 201
    assert client.post(
        "/api/inventory/appliances",
        headers=AUTH,
        json={"id": "app-fan", "name": "Mini Fan", "ratedWatts": 25, "relayChannel": None},
    ).status_code == 201
    _set_relay_state("ON")

    # Adjust mismatch threshold in Settings (household config) to 50%
    cfg = client.put("/api/household/config", headers=AUTH, json={"relayMismatchThresholdPercent": 50}).json()
    assert cfg["relayMismatchThresholdPercent"] == 50.0

    # At 12 W (33% off 9W), it's below the new 50% threshold -> inactive
    seed([(utcnow(), 1.0, 12.0)])
    assert client.get("/api/relay/1/mismatch", headers=AUTH).json()["active"] is False

    # At 26 W (matches Mini Fan 25W within threshold!) -> active + suggests Mini Fan
    seed([(utcnow(), 1.01, 26.0)])
    m = client.get("/api/relay/1/mismatch", headers=AUTH).json()
    assert m["active"] is True
    assert m["suggestedAppliance"]["applianceId"] == "app-fan"

    # One-click switch Relay 1 to Mini Fan -> Bulb unassigned (with lastRelayChannel=1), Mini Fan on Relay 1
    sw = client.post("/api/relay/1/mismatch/switch", headers=AUTH, json={"applianceId": "app-fan"})
    assert sw.status_code == 200
    assert sw.json()["relayChannel"] == 1

    with SessionLocal() as db:
        bulb = db.get(Appliance, "app-bulb")
        fan = db.get(Appliance, "app-fan")
        assert bulb is not None and bulb.relay_channel is None and bulb.last_relay_channel == 1
        assert bulb.status == "off" and bulb.sim_manual_state == "OFF"
        assert fan is not None and fan.relay_channel == 1 and fan.last_relay_channel == 1
        assert fan.status == "on"


def test_replace_relay_owner_on_create_appliance(client):
    assert client.post(
        "/api/inventory/appliances",
        headers=AUTH,
        json={"id": "app-bulb", "name": "LED Bulb", "ratedWatts": 9, "relayChannel": 1},
    ).status_code == 201

    # Without replaceRelayOwner -> 409 Conflict (existing behavior preserved)
    conflict = client.post(
        "/api/inventory/appliances",
        headers=AUTH,
        json={"id": "app-fan", "name": "Mini Fan", "ratedWatts": 25, "relayChannel": 1},
    )
    assert conflict.status_code == 409

    # With replaceRelayOwner=True -> atomically unassigns Bulb and assigns Mini Fan
    ok = client.post(
        "/api/inventory/appliances",
        headers=AUTH,
        json={"id": "app-fan", "name": "Mini Fan", "ratedWatts": 25, "relayChannel": 1, "replaceRelayOwner": True},
    )
    assert ok.status_code == 201
    assert ok.json()["relayChannel"] == 1

    with SessionLocal() as db:
        bulb = db.get(Appliance, "app-bulb")
        fan = db.get(Appliance, "app-fan")
        assert bulb is not None and bulb.relay_channel is None and bulb.last_relay_channel == 1
        assert bulb.status == "off" and bulb.sim_manual_state == "OFF"
        assert fan is not None and fan.relay_channel == 1 and fan.last_relay_channel == 1
        assert fan.status == "on"
