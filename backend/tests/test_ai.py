"""SHEM AI: segmenter, tools, conflicts, agent loop, fallback, SSE, daily insights (no real LLM calls)."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from typing import List, Optional

import pytest

from app.ai import providers
from app.ai.components import StreamSegmenter, parse_text
from app.ai.providers import LLMRouter, ProviderTurn, ToolCall
from app.ai.tools import execute_tool_sync, run_readonly_sql, ToolError
from app.database import SessionLocal
from app.models.db_models import AIActionLog, Appliance
from app.utils.timestamps import utcnow
from tests.conftest import AUTH, seed


class ScriptedProvider:
    """Plays back a list of turns: each turn is (text_chunks, [(name, args_dict), ...])."""

    def __init__(self, name: str, turns: List[tuple], fail: Optional[Exception] = None, fail_after_text: bool = False):
        self.name, self.model = name, "fake"
        self.turns = list(turns)
        self.fail, self.fail_after_text = fail, fail_after_text
        self.calls: List[list] = []

    async def stream(self, messages, tools, temperature):
        self.calls.append(messages)
        if self.fail and self.fail_after_text:
            yield ("text", "partial ")
            raise self.fail
        if self.fail:
            raise self.fail
        chunks, calls = self.turns.pop(0)
        for c in chunks:
            yield ("text", c)
        yield ("done", ProviderTurn(
            text="".join(chunks), provider=self.name,
            tool_calls=[ToolCall(id=f"call_{i}", name=n, arguments=json.dumps(a)) for i, (n, a) in enumerate(calls)]))


@pytest.fixture
def use_router():
    def _set(*provs):
        providers.set_router(LLMRouter(list(provs)))
        return provs
    yield _set
    providers.set_router(None)


def _add_appliance(**kw):
    with SessionLocal() as db:
        a = Appliance(id=kw.pop("id", "app-bulb"), name=kw.pop("name", "Bulb"), quantity=1, daily_hours=4,
                      status=kw.pop("status", "on"), created_at=utcnow(), updated_at=utcnow(), **kw)
        db.add(a)
        db.commit()


def _sse_events(text: str):
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        ev = lines[0].removeprefix("event: ")
        out.append((ev, json.loads(lines[1].removeprefix("data: "))))
    return out


# ── Segmenter ──────────────────────────────────────────────────────────────────

def test_segmenter_splits_fences_across_chunks():
    text = ('Hello **there**.\n```shem-ui\n{"type":"metric_cards","items":[{"label":"Today","value":2.4,'
            '"unit":"kWh"}]}\n```\nAfter.\n```shem-followups\n["A?","B?"]\n```')
    seg = StreamSegmenter()
    events = []
    for i in range(0, len(text), 3):            # tiny chunks split every token boundary
        events += seg.feed(text[i:i + 3])
    events += seg.flush()
    streamed = "".join(e["data"]["delta"] for e in events if e["event"] == "text")
    assert "shem-" not in streamed and "```" not in streamed
    segs = seg.final_segments()
    assert [s["type"] for s in segs] == ["text", "component", "text"]
    assert segs[1]["component"]["items"][0]["value"] == 2.4
    assert seg.followups == ["A?", "B?"]


def test_invalid_component_is_dropped_not_shown():
    segs, _ = parse_text('Hi\n```shem-ui\n{"type":"chart","series":[]}\n```\n```shem-ui\nnot json\n```')
    assert segs == [{"type": "text", "content": "Hi"}]


# ── Tools ──────────────────────────────────────────────────────────────────────

def test_readonly_sql_allows_select_and_blocks_writes():
    _add_appliance()
    out = run_readonly_sql("SELECT id, name FROM appliances")
    assert out["rows"] == [["app-bulb", "Bulb"]]
    for bad in ("DELETE FROM appliances", "SELECT 1; DROP TABLE appliances",
                "WITH x AS (SELECT 1) DELETE FROM appliances", "PRAGMA writable_schema=1"):
        with pytest.raises(ToolError):
            run_readonly_sql(bad)
    assert run_readonly_sql("SELECT count(*) FROM appliances")["rows"] == [[1]]


def test_write_tool_validates_logs_and_creates(client):
    r = execute_tool_sync("create_appliance", json.dumps({"name": "Fan", "rated_watts": 75, "category": "fans"}))
    assert r["result"]["ok"] and r["ui"]["status"] == "success"
    bad = execute_tool_sync("create_appliance", json.dumps({"name": "X", "rated_watts": -5}))
    assert not bad["result"]["ok"] and "rated_watts" in bad["result"]["error"]
    with SessionLocal() as db:
        logs = db.query(AIActionLog).all()
    assert [(l.tool, l.ok) for l in logs] == [("create_appliance", True), ("create_appliance", False)]


def test_set_target_and_update_bill_tools(client):
    assert execute_tool_sync("set_target", '{"monthly_budget_inr": 1500}')["result"]["ok"]
    assert client.get("/api/target", headers=AUTH).json()["monthlyBudgetINR"] == 1500
    bill = execute_tool_sync("create_bill", '{"units_consumed_kwh": 200, "bill_amount_inr": 1500}')
    bid = bill["result"]["data"]["bill"]["id"]
    assert execute_tool_sync("update_bill", json.dumps({"bill_id": bid, "bill_amount_inr": 1600}))["result"]["ok"]
    assert client.get("/api/bills", headers=AUTH).json()[0]["billAmountINR"] == 1600


def test_relay_linked_appliance_power_publishes_command(client, mqtt):
    _add_appliance(relay_channel=1, status="off", rated_watts=9)
    r = execute_tool_sync("set_appliance_power", '{"appliance_id": "app-bulb", "state": "on"}', mqtt_client=mqtt)
    assert r["result"]["ok"] and r["result"]["data"]["physicallySwitched"]
    assert r["ui"]["status"] == "pending" and r["ui"]["commandId"]
    assert mqtt.published[-1]["payload"]["state"] == "ON"
    mqtt.connected = False
    r = execute_tool_sync("control_relay", '{"state": "OFF"}', mqtt_client=mqtt)
    assert not r["result"]["ok"] and "publish_failed" in r["result"]["error"]


# ── Conflicts ──────────────────────────────────────────────────────────────────

def _relay_on(client, mqtt):
    from app.services.device_service import upsert_relay_channel, get_or_create_device
    with SessionLocal() as db:
        get_or_create_device(db, "001")
        upsert_relay_channel(db, "001", 1, "ON", utcnow())
        db.commit()


def _online_with_power(watts: float):
    from app.services.device_service import get_or_create_device, mark_device_seen
    now = utcnow()
    seed([(now - timedelta(seconds=s), 1.0 + s / 1e6, watts) for s in (2, 4, 6, 8)])
    with SessionLocal() as db:
        mark_device_seen(db, get_or_create_device(db, "001"), now)
        db.commit()


def test_flags_9w_appliance_drawing_480w(client, mqtt):
    _add_appliance(relay_channel=1, rated_watts=9, category="lighting")
    _relay_on(client, mqtt)
    _online_with_power(480)
    body = client.get("/api/ai/conflicts", headers=AUTH).json()
    c = next(c for c in body["conflicts"] if c["id"] == "over-rated:app-bulb")
    assert c["severity"] == "critical" and "9 W" in c["message"] and "480 W" in c["message"]
    # dismiss hides it
    assert client.post("/api/ai/conflicts/over-rated:app-bulb/dismiss", headers=AUTH).status_code == 204
    ids = [c["id"] for c in client.get("/api/ai/conflicts", headers=AUTH).json()["conflicts"]]
    assert "over-rated:app-bulb" not in ids


def test_flags_implausible_rating_and_bill_rate(client):
    _add_appliance(name="AC", rated_watts=9, category="cooling")
    execute_tool_sync("create_bill", '{"units_consumed_kwh": 100, "bill_amount_inr": 2000}')  # ₹20/kWh vs 7.5
    ids = {c["id"].split(":")[0] for c in client.get("/api/ai/conflicts", headers=AUTH).json()["conflicts"]}
    assert {"rating-implausible", "bill-rate"} <= ids


# ── Agent ──────────────────────────────────────────────────────────────────────

def test_chat_runs_tool_then_answers_with_components(client, use_router):
    _add_appliance(rated_watts=9)
    (p,) = use_router(ScriptedProvider("gemini", [
        (["Let me check."], [("list_appliances", {})]),
        (["You have **1** appliance.\n```shem-ui\n", '{"type":"appliance_card","applianceId":"app-bulb"}\n```\n',
          '```shem-followups\n["Turn it off"]\n```'], []),
    ]))
    r = client.post("/api/ai/chat", json={"message": "What appliances do I have?"}, headers=AUTH)
    assert r.status_code == 200, r.text
    msg = r.json()["message"]
    types = [s["type"] for s in msg["segments"]]
    assert types == ["text", "component"] and msg["followups"] == ["Turn it off"]
    assert msg["provider"] == "gemini"
    # tool result was fed back to the model
    second_call = p.calls[1]
    assert second_call[-1]["role"] == "tool" and "app-bulb" in second_call[-1]["content"]
    assert "LIVE SNAPSHOT" in second_call[0]["content"]

    cid = r.json()["conversationId"]
    conv = client.get(f"/api/ai/conversations/{cid}", headers=AUTH).json()
    assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert client.delete(f"/api/ai/conversations/{cid}", headers=AUTH).status_code == 204


def test_fallback_to_second_provider(client, use_router):
    use_router(ScriptedProvider("gemini", [], fail=RuntimeError("quota"), fail_after_text=True),
               ScriptedProvider("groq", [(["Hi from groq"], [])]))
    r = client.post("/api/ai/chat/stream", json={"message": "hi"}, headers=AUTH)
    events = _sse_events(r.text)
    names = [e for e, _ in events]
    assert "fallback" in names and "reset" in names
    done = dict(events)["done"]["message"]
    assert done["provider"] == "groq" and done["segments"] == [{"type": "text", "content": "Hi from groq"}]
    assert done["followups"]                     # heuristic follow-ups when the model gave none


def test_all_providers_fail_and_unconfigured(client, use_router):
    use_router(ScriptedProvider("gemini", [], fail=RuntimeError("x")))
    assert client.post("/api/ai/chat", json={"message": "hi"}, headers=AUTH).status_code == 503
    use_router()
    r = client.post("/api/ai/chat/stream", json={"message": "hi"}, headers=AUTH)
    assert _sse_events(r.text)[-1][0] == "error"


def test_stream_emits_tool_and_action_events(client, mqtt, use_router):
    _add_appliance(relay_channel=1, status="on")
    use_router(ScriptedProvider("gemini", [
        ([], [("set_appliance_power", {"appliance_id": "app-bulb", "state": "off"})]),
        (["Sent the OFF command; waiting for the device to confirm."], []),
    ]))
    r = client.post("/api/ai/chat/stream", json={"message": "turn off the bulb"}, headers=AUTH)
    names = [e for e, _ in _sse_events(r.text)]
    assert names.index("tool_start") < names.index("tool_end") < names.index("action") < names.index("done")
    done = dict(_sse_events(r.text))["done"]["message"]
    assert done["actions"][0]["commandId"]
    assert mqtt.published[-1]["payload"]["state"] == "OFF"


def test_suggestions_and_status(client):
    s = client.get("/api/ai/suggestions", headers=AUTH).json()["suggestions"]
    assert any("budget" in x["label"].lower() for x in s)
    st = client.get("/api/ai/status", headers=AUTH).json()
    assert st["configured"] is False and st["primaryProvider"] == "gemini"
    assert client.get("/api/ai/status").status_code == 401


# ── Daily insights ─────────────────────────────────────────────────────────────

def test_daily_insight_rule_based_and_llm(client, use_router):
    from app.utils.timestamps import local_day_start
    day0 = local_day_start(utcnow()) - timedelta(days=1)
    seed([(day0 + timedelta(minutes=10 * i), 1.0 + 0.01 * i, 120) for i in range(0, 140)])
    r = client.post("/api/ai/daily-insights/generate", json={}, headers=AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] is None and body["facts"]["energyKWh"] > 0
    assert body["segments"][0]["component"]["type"] == "metric_cards"

    use_router(ScriptedProvider("gemini", [(["# Steady day at home\nUsage was flat."], [])]))
    body = client.post("/api/ai/daily-insights/generate", json={}, headers=AUTH).json()
    assert body["headline"] == "Steady day at home" and body["provider"] == "gemini"
    assert client.get("/api/ai/daily-insights/latest", headers=AUTH).json()["date"] == body["date"]


def test_openai_compat_provider_assembles_streamed_tool_calls():
    """Real OpenAI SDK parsing against a mocked OpenAI-compatible SSE stream (Gemini/Groq shape)."""
    import httpx
    from openai import AsyncOpenAI
    from app.ai.providers import OpenAICompatProvider

    def chunk(delta):
        return "data: " + json.dumps({"id": "x", "object": "chat.completion.chunk", "created": 0, "model": "m",
                                      "choices": [{"index": 0, "delta": delta, "finish_reason": None}]}) + "\n\n"
    body = (chunk({"role": "assistant", "content": "Checking"})
            + chunk({"tool_calls": [{"index": 0, "id": "c1", "type": "function",
                                     "function": {"name": "control_relay", "arguments": '{"sta'},
                                     "extra_content": {"google": {"thought_signature": "sig"}}}]})
            + chunk({"tool_calls": [{"index": 0, "function": {"arguments": 'te":"ON"}'}}]})
            + "data: [DONE]\n\n")
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    p = OpenAICompatProvider("gemini", "k", "https://example.test/v1", "m", 10)
    p.client = AsyncOpenAI(api_key="k", base_url="https://example.test/v1",
                           http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    async def run():
        return [e async for e in p.stream([{"role": "user", "content": "hi"}], [{"type": "function",
                "function": {"name": "control_relay", "parameters": {"type": "object", "properties": {}}}}], 0.2)]
    events = asyncio.run(run())
    turn = events[-1][1]
    assert events[0] == ("text", "Checking") and turn.text == "Checking"
    (call,) = turn.tool_calls
    assert (call.id, call.name, json.loads(call.arguments)) == ("c1", "control_relay", {"state": "ON"})
    assert call.to_message()["extra_content"]["google"]["thought_signature"] == "sig"   # echoed back to Gemini
    assert seen["body"]["stream"] is True and seen["body"]["tool_choice"] == "auto"


def test_groq_requests_drop_gemini_only_fields():
    """A Gemini tool turn followed by a Groq fallback must not send thought signatures / `name` to Groq."""
    from app.ai.providers import _strip_foreign_fields
    msgs = [{"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "x", "arguments": "{}"},
                 "extra_content": {"google": {"thought_signature": "sig"}}}]},
            {"role": "tool", "tool_call_id": "c1", "name": "x", "content": "{}"}]
    out = _strip_foreign_fields(msgs)
    assert set(out[0]["tool_calls"][0]) == {"id", "type", "function"} and "name" not in out[1]
    assert "extra_content" in msgs[0]["tool_calls"][0]          # original (for Gemini) untouched


@pytest.mark.parametrize("raw", [
    'Done.\n```SHEM-followups\n["A?", "B?"]\n```',            # uppercase fence
    'Done.\nSHEM-followups\n["A?", "B?"]',                       # no fence at all (the reported bug)
    'Done.\n**shem-followups**\n["A?", "B?"]\n',                 # bolded tag
    'Done.\n~~~shem-followups\n["A?", "B?"]\n~~~',
])
def test_followups_are_extracted_however_the_model_writes_them(raw):
    segs, fups = parse_text(raw)
    assert segs == [{"type": "text", "content": "Done."}] and fups == ["A?", "B?"]


def test_unfenced_ui_block_becomes_component():
    segs, _ = parse_text('Budget:\nSHEM-ui\n{"type":"progress","label":"Budget","current":1,"target":100}\nBye')
    assert [s["type"] for s in segs] == ["text", "component", "text"] and segs[2]["content"] == "Bye"
