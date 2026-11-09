"""
SHEM AI — Tools (function calling)

Read tools see everything: live state, telemetry, insights, inventory, bills,
targets, events, plus arbitrary read-only SQL over the whole database.

Write tools change the system through the same validation the REST API
uses (the router functions / pydantic schemas are reused), so the AI can't
put the database into a state the app itself would reject. Every write is
recorded in ai_action_log and announced on the WebSocket as `ai_action`
so open screens refresh.

A tool function receives (ctx, args) and returns a JSON-serialisable dict.
Optional keys it may add:  "summary" (one line for the UI) and "_ui"
(an action_result component).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, SessionLocal
from app.models.db_models import (
    AIActionLog,
    AIDailyInsight,
    Appliance,
    DeviceStatusEvent,
    ElectricityBill,
    RelayCommand,
)
from app.models.schemas import (
    ApplianceCreate,
    ApplianceSchema,
    ApplianceUpdate,
    ElectricityBillCreate,
    ElectricityBillSchema,
    ElectricityBillUpdate,
    EnergyTargetUpdate,
    HouseholdConfigUpdate,
    RelayCommandDetailResponse,
    RoomCreate,
    RoomUpdate,
)
from app.services.broadcaster import broadcaster
from app.utils.timestamps import parse_iso, utcnow

logger = logging.getLogger(__name__)
settings = get_settings()


class ToolError(Exception):
    pass


@dataclass
class ToolContext:
    db: Session
    mqtt_client: Any = None
    conversation_id: Optional[str] = None


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: Dict[str, Any]
    fn: Callable[[ToolContext, Dict[str, Any]], Dict[str, Any]]
    write: bool
    label: str                                  # shown in the UI while running

    def openai_spec(self) -> Dict[str, Any]:
        return {"type": "function",
                "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


REGISTRY: Dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: Optional[Dict[str, Any]] = None, *,
         write: bool = False, label: str = ""):
    def deco(fn):
        REGISTRY[name] = ToolSpec(name, description,
                                  parameters or {"type": "object", "properties": {}},
                                  fn, write, label or name.replace("_", " ").capitalize())
        return fn
    return deco


def openai_tools() -> List[Dict[str, Any]]:
    return [t.openai_spec() for t in REGISTRY.values()]


# ── JSON-schema helpers ────────────────────────────────────────────────────────

def _simplify(prop: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten pydantic's Optional/anyOf/const output into provider-friendly JSON schema."""
    if "anyOf" in prop:
        options = [p for p in prop["anyOf"] if p.get("type") != "null"]
        base = dict(options[0]) if options else {"type": "string"}
        base.update({k: v for k, v in prop.items() if k in ("description",)})
        prop = base
    out: Dict[str, Any] = {}
    if "const" in prop:
        out["type"], out["enum"] = "string", [prop["const"]]
    # Only keywords every provider accepts; pydantic re-validates everything server-side.
    for key in ("type", "enum", "description", "minimum", "maximum"):
        if key in prop:
            out[key] = prop[key]
    if prop.get("type") == "array" and "items" in prop:
        out["items"] = _simplify(prop["items"])
    out.setdefault("type", "string")
    return out


def schema_from_model(model: type[BaseModel], exclude: tuple = (), extra: Optional[Dict[str, Any]] = None,
                      required: Optional[List[str]] = None) -> Dict[str, Any]:
    js = model.model_json_schema(by_alias=False)
    props = {k: _simplify(v) for k, v in js.get("properties", {}).items() if k not in exclude}
    if extra:
        props = {**extra, **props}
    req = required if required is not None else [r for r in js.get("required", []) if r not in exclude]
    return {"type": "object", "properties": props, "required": req}


def _dump(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True)
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    return obj


def _mqtt_connected(ctx: ToolContext) -> bool:
    return bool(ctx.mqtt_client and getattr(ctx.mqtt_client, "connected", False))


def _action(tool_name: str, status: str, title: str, detail: Optional[str] = None,
            entity_type: Optional[str] = None, entity_id: Optional[str] = None,
            command_id: Optional[str] = None) -> Dict[str, Any]:
    comp = {"type": "action_result", "tool": tool_name, "status": status, "title": title,
            "detail": detail, "entityType": entity_type, "entityId": entity_id, "commandId": command_id}
    return {k: v for k, v in comp.items() if v is not None}


# ═══════════════════════════════════════════════════════════════
# READ TOOLS
# ═══════════════════════════════════════════════════════════════

@tool("get_system_snapshot",
      "Compact live overview: device/MQTT status, latest reading, relay state, today's usage & cost, "
      "target, household, appliance/bill counts and open conflicts. Call this first when unsure.",
      label="Reading system snapshot")
def t_snapshot(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.ai.context import build_snapshot
    return build_snapshot(ctx.db, _mqtt_connected(ctx))


@tool("get_database_schema",
      "List every database table with its columns and types (for query_database).",
      label="Reading database schema")
def t_schema(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    tables = {}
    for t in Base.metadata.sorted_tables:
        tables[t.name] = [f"{c.name} {c.type}" + (" PK" if c.primary_key else "") for c in t.columns]
    return {
        "tables": tables,
        "notes": [
            "Datetimes are stored as naive UTC text 'YYYY-MM-DD HH:MM:SS[.ffffff]'. Local timezone: "
            f"{settings.timezone}. Use datetime(col, '+5 hours', '+30 minutes') style shifts for local time.",
            "telemetry.energy_kwh is a CUMULATIVE register — never SUM it; use telemetry_hourly.energy_kwh "
            "(per-hour consumption) or MAX-MIN of the register within a window without resets.",
            "telemetry holds raw ~2 s readings for the last few days only; telemetry_hourly is kept forever.",
            "Only rows with validity='valid' are trustworthy measurements.",
        ],
    }


_SQL_ALLOWED = re.compile(r"^\s*(select|with)\b", re.I)
_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def run_readonly_sql(sql: str, limit: int = 200, timeout_s: float = 3.0) -> Dict[str, Any]:
    sql = sql.strip().rstrip(";").strip()
    if not _SQL_ALLOWED.match(sql) or ";" in sql:
        raise ToolError("Only a single SELECT (or WITH … SELECT) statement is allowed.")
    path = Path(settings.sqlite_path).resolve()
    conn = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=5, check_same_thread=False)
    try:
        def authorizer(action, *_):
            return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY
        conn.set_authorizer(authorizer)
        deadline = time.monotonic() + timeout_s
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10000)
        try:
            cur = conn.execute(sql)
            rows = cur.fetchmany(limit + 1)
        except sqlite3.DatabaseError as exc:
            raise ToolError(f"SQL error: {exc}")
        columns = [d[0] for d in cur.description or []]
        truncated = len(rows) > limit
        return {"columns": columns, "rows": [list(r) for r in rows[:limit]], "rowCount": min(len(rows), limit),
                "truncated": truncated}
    finally:
        conn.close()


@tool("query_database",
      "Run a read-only SQL SELECT against the SHEM SQLite database (any table). Use get_database_schema "
      "first if you need column names. Max 500 rows.",
      {"type": "object", "properties": {
          "sql": {"type": "string", "description": "A single SELECT/WITH statement"},
          "limit": {"type": "integer", "minimum": 1, "maximum": 500, "description": "Row cap (default 200)"}},
       "required": ["sql"]},
      label="Querying the database")
def t_query(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    return run_readonly_sql(str(args.get("sql", "")), int(args.get("limit") or 200))


@tool("get_latest_telemetry", "Latest AC meter reading (voltage, current, power, PF, Hz, energy register) "
      "with its age/staleness.", label="Reading live meter")
def t_latest(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.telemetry_service import get_latest_telemetry
    return _dump(get_latest_telemetry(ctx.db, settings.device_id))


@tool("get_telemetry_history",
      "Historical meter readings, downsampled. Give hours_back (default 24) or from_time/to_time (UTC ISO). "
      "resolution auto|raw|1m|5m|15m|1h. Returns at most `max_points` points (default 120).",
      {"type": "object", "properties": {
          "hours_back": {"type": "number", "minimum": 0.1, "maximum": 8760},
          "from_time": {"type": "string", "description": "UTC ISO 8601"},
          "to_time": {"type": "string", "description": "UTC ISO 8601"},
          "resolution": {"type": "string", "enum": ["auto", "raw", "1m", "5m", "15m", "1h"]},
          "max_points": {"type": "integer", "minimum": 10, "maximum": 500}}},
      label="Loading usage history")
def t_history(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.telemetry_service import MAX_SPAN, choose_resolution, get_telemetry_history
    try:
        to_dt = parse_iso(args["to_time"]) if args.get("to_time") else utcnow()
        from_dt = parse_iso(args["from_time"]) if args.get("from_time") else \
            to_dt - timedelta(hours=float(args.get("hours_back") or 24))
    except ValueError:
        raise ToolError("Invalid time; use UTC ISO 8601 like 2026-11-01T09:30:00Z.")
    if from_dt >= to_dt:
        raise ToolError("from_time must be before to_time.")
    res = args.get("resolution") or "auto"
    eff = choose_resolution(to_dt - from_dt) if res == "auto" else res
    if to_dt - from_dt > MAX_SPAN[eff]:
        eff = "1h"
    if to_dt - from_dt > MAX_SPAN[eff]:
        raise ToolError(f"Range too large (max {MAX_SPAN[eff].days} days).")
    out = _dump(get_telemetry_history(ctx.db, settings.device_id, from_dt, to_dt, eff, 5000))
    cap = int(args.get("max_points") or 120)
    readings = out.get("readings", [])
    if len(readings) > cap:
        step = len(readings) / cap
        out["readings"] = [readings[int(i * step)] for i in range(cap)]
        out["sampledFrom"] = len(readings)
    out["count"] = len(out["readings"])
    return out


@tool("get_insights", "Measured usage trend, totals, cost, peak, comparison with the previous period, "
      "bill comparison and estimated category breakdown for a week/month/year.",
      {"type": "object", "properties": {"period": {"type": "string", "enum": ["week", "month", "year"]}}},
      label="Analysing usage")
def t_insights(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.insights_service import compute_insights
    return _dump(compute_insights(ctx.db, args.get("period") or "week"))


@tool("get_today_insights", "Energy for one local day (default today): by hour (metered vs simulated), "
      "night/morning/afternoon/evening split with the peak period, per-appliance usage, cost and daily target.",
      {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD, local"}}},
      label="Analysing the day")
def t_today(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.insights_service import compute_today_insights
    try:
        out = _dump(compute_today_insights(ctx.db, date=args.get("date") or None))
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    out["hourlyPoints"] = [p for p in out.get("hourlyPoints", []) if p.get("measured")]
    return out


@tool("get_recommendations", "Data-driven saving recommendations with the evidence for each.",
      label="Finding savings")
def t_recs(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.insights_service import compute_recommendations
    return {"recommendations": _dump(compute_recommendations(ctx.db))}


@tool("detect_conflicts", "Run SHEM's consistency checks: appliance ratings vs measured power, relay vs load, "
      "estimates vs meter, bill rates vs tariff, budget progress, device health.",
      {"type": "object", "properties": {"include_dismissed": {"type": "boolean"}}},
      label="Checking for conflicts")
def t_conflicts(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.ai.conflicts import detect_conflicts
    items = detect_conflicts(ctx.db, bool(args.get("include_dismissed")), _mqtt_connected(ctx))
    return {"conflicts": [c.to_dict() for c in items]}


@tool("list_appliances", "All appliances (id, room, wattage, quantity, daily hours, status, relay channel …).",
      {"type": "object", "properties": {"room_id": {"type": "string"}}}, label="Reading appliances")
def t_list_appliances(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import list_appliances
    return {"appliances": _dump(list_appliances(args.get("room_id"), ctx.db))}


@tool("list_rooms", "All rooms.", label="Reading rooms")
def t_list_rooms(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import list_rooms
    return {"rooms": _dump(list_rooms(ctx.db))}


@tool("list_bills", "All electricity bills, most recent period first.", label="Reading bills")
def t_list_bills(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.bills import list_bills
    return {"bills": _dump(list_bills(ctx.db))}


@tool("get_target", "The monthly energy budget/target.", label="Reading target")
def t_get_target(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.target import get_target
    return _dump(get_target(ctx.db))


@tool("get_household_config", "Household settings (name, type, occupants, area, provider, tariff ₹/kWh).",
      label="Reading household")
def t_get_household(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.household import get_household_config
    return _dump(get_household_config(ctx.db))


@tool("get_relay_status", "Relay 1 reported state plus the most recent relay commands and their outcome.",
      {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}},
      label="Reading relay")
def t_relay_status(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.relay_service import get_relay_status
    cmds = ctx.db.scalars(select(RelayCommand).order_by(desc(RelayCommand.created_at))
                          .limit(int(args.get("limit") or 10))).all()
    return {"relay": _dump(get_relay_status(ctx.db, settings.device_id, 1)),
            "recentCommands": [_dump(RelayCommandDetailResponse.model_validate(c)) for c in cmds],
            "mqttConnected": _mqtt_connected(ctx)}


@tool("get_device_events", "Recent device online/offline events.",
      {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
      label="Reading device events")
def t_events(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.device_service import get_device_status
    rows = ctx.db.scalars(select(DeviceStatusEvent).order_by(desc(DeviceStatusEvent.recorded_at))
                          .limit(int(args.get("limit") or 20))).all()
    return {"status": _dump(get_device_status(ctx.db, settings.device_id, _mqtt_connected(ctx))),
            "events": [{"status": e.status, "at": e.recorded_at.isoformat(), "details": e.details} for e in rows]}


@tool("get_daily_insight", "The stored AI daily briefing for a local date (default: latest).",
      {"type": "object", "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}}},
      label="Reading daily briefing")
def t_daily(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    stmt = select(AIDailyInsight)
    stmt = stmt.where(AIDailyInsight.insight_date == args["date"]) if args.get("date") else \
        stmt.order_by(desc(AIDailyInsight.insight_date))
    row = ctx.db.scalars(stmt.limit(1)).first()
    if row is None:
        return {"found": False}
    return {"found": True, "date": row.insight_date, "headline": row.headline, "content": row.content,
            "facts": json.loads(row.facts_json or "{}")}


@tool("get_ai_action_log", "Actions SHEM AI has taken recently (audit log).",
      {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
      label="Reading action log")
def t_action_log(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    rows = ctx.db.scalars(select(AIActionLog).order_by(desc(AIActionLog.id)).limit(int(args.get("limit") or 20)))
    return {"actions": [{"tool": r.tool, "ok": r.ok, "summary": r.summary, "error": r.error,
                         "at": r.created_at.isoformat()} for r in rows]}


# ═══════════════════════════════════════════════════════════════
# WRITE TOOLS
# ═══════════════════════════════════════════════════════════════

def _publish_relay(ctx: ToolContext, state: str, channel: int = 1):
    from app.mqtt.publisher import publish_relay_command
    if ctx.mqtt_client is None:
        raise ToolError("MQTT service is not running, so the relay can't be switched.")
    ok, resp = publish_relay_command(ctx.mqtt_client, ctx.db, settings.device_id, channel, state)
    if not ok:
        raise ToolError(f"Broker unavailable; command {resp.command_id} was recorded as publish_failed.")
    return resp


@tool("control_relay",
      "Switch physical relay 1 ON or OFF on the SHEM device. Returns once the command is PUBLISHED; the "
      "device confirms asynchronously (tell the user it was sent and is awaiting confirmation).",
      {"type": "object", "properties": {"state": {"type": "string", "enum": ["ON", "OFF"]}},
       "required": ["state"]},
      write=True, label="Switching relay")
def t_control_relay(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    state = str(args.get("state", "")).upper()
    if state not in ("ON", "OFF"):
        raise ToolError("state must be ON or OFF")
    resp = _publish_relay(ctx, state)
    linked = ctx.db.scalar(select(Appliance).where(Appliance.relay_channel == 1))
    if linked is not None:
        linked.status = state.lower()
        linked.updated_at = utcnow()
        ctx.db.commit()
    summary = f"Relay 1 {state} command sent — waiting for the device to confirm."
    return {"command": _dump(resp), "summary": summary,
            "_ui": _action("control_relay", "pending", f"Relay 1 → {state}", "Waiting for device confirmation",
                           "relay", "1", resp.command_id)}


@tool("set_appliance_power",
      "Turn an appliance on or off. Relay-linked appliances are physically switched via the relay (awaits "
      "device confirmation). Appliances without a relay are SIMULATED devices: the switch applies immediately "
      "and overrides their daily routine until its next scheduled change (tell the user it is simulated).",
      {"type": "object", "properties": {
          "appliance_id": {"type": "string"},
          "state": {"type": "string", "enum": ["on", "off"]}},
       "required": ["appliance_id", "state"]},
      write=True, label="Switching appliance")
def t_appliance_power(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    item = ctx.db.get(Appliance, str(args.get("appliance_id")))
    if item is None:
        raise ToolError(f"Appliance '{args.get('appliance_id')}' not found. Use list_appliances for ids.")
    state = str(args.get("state", "")).lower()
    if state not in ("on", "off"):
        raise ToolError("state must be on or off")
    if item.relay_channel:
        resp = _publish_relay(ctx, state.upper(), item.relay_channel)
        item.status = state
        item.updated_at = utcnow()
        ctx.db.commit()
        return {"appliance": _dump(ApplianceSchema.model_validate(item)), "command": _dump(resp),
                "physicallySwitched": True,
                "summary": f"Sent {state.upper()} to relay {item.relay_channel} for {item.name}; awaiting confirmation.",
                "_ui": _action("set_appliance_power", "pending", f"{item.name} → {state.upper()}",
                               "Waiting for device confirmation", "appliance", item.id, resp.command_id)}
    from app.services.simulation_service import simulator
    payload = simulator.command(ctx.db, item, state.upper())
    broadcaster.publish_from_thread("sim_update", payload)
    live = next((x for x in payload["appliances"] if x["applianceId"] == item.id), {})
    ctx.db.refresh(item)
    watts = live.get("powerW") or 0.0
    return {"appliance": _dump(ApplianceSchema.model_validate(item)), "simulated": True, "livePowerW": watts,
            "summary": f"Switched simulated {item.name} {state} (now {watts:.0f} W).",
            "_ui": _action("set_appliance_power", "success", f"{item.name} → {state.upper()} (simulated)",
                           f"{watts:.0f} W now", "appliance", item.id)}


@tool("get_simulation_status",
      "Live state of every SIMULATED appliance (those without a relay): ON/OFF, current watts, auto-routine vs "
      "manual override, routine times and today's kWh. Live home power = metered W + totalPowerW.",
      label="Reading simulated appliances")
def t_sim_status(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.services.simulation_service import simulator
    return simulator.tick(ctx.db)


_APPLIANCE_CREATE = schema_from_model(ApplianceCreate, exclude=("id",))
_APPLIANCE_UPDATE = schema_from_model(ApplianceUpdate, extra={"appliance_id": {"type": "string"}},
                                      required=["appliance_id"])


@tool("create_appliance", "Add an appliance to the inventory. category is one of cooling, lighting, fans, "
      "refrigerator, kitchen, entertainment, heating, other. relay_channel 1 links it to the relay.",
      _APPLIANCE_CREATE, write=True, label="Adding appliance")
def t_create_appliance(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import create_appliance
    out = create_appliance(ApplianceCreate.model_validate(args), ctx.db)
    return {"appliance": _dump(out), "summary": f"Added {out.name}.",
            "_ui": _action("create_appliance", "success", f"Added {out.name}",
                           f"{out.rated_watts or '?'} W × {out.quantity}", "appliance", out.id)}


@tool("update_appliance", "Change appliance fields (only those given). Use null for room_id/relay_channel "
      "to clear them.", _APPLIANCE_UPDATE, write=True, label="Updating appliance")
def t_update_appliance(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import update_appliance
    aid = str(args.pop("appliance_id", ""))
    out = update_appliance(aid, ApplianceUpdate.model_validate(args), ctx.db)
    return {"appliance": _dump(out), "summary": f"Updated {out.name}: {', '.join(args) or 'no changes'}.",
            "_ui": _action("update_appliance", "success", f"Updated {out.name}", ", ".join(args), "appliance", out.id)}


@tool("delete_appliance", "Permanently delete an appliance. Confirm with the user first unless they "
      "explicitly asked.", {"type": "object", "properties": {"appliance_id": {"type": "string"}},
                            "required": ["appliance_id"]}, write=True, label="Deleting appliance")
def t_delete_appliance(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import delete_appliance
    item = ctx.db.get(Appliance, str(args.get("appliance_id")))
    name = item.name if item else args.get("appliance_id")
    delete_appliance(str(args.get("appliance_id")), ctx.db)
    return {"deleted": True, "summary": f"Deleted {name}.",
            "_ui": _action("delete_appliance", "success", f"Deleted {name}", None, "appliance", args.get("appliance_id"))}


@tool("create_room", "Add a room.", schema_from_model(RoomCreate, exclude=("id",)), write=True, label="Adding room")
def t_create_room(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import create_room
    out = create_room(RoomCreate.model_validate(args), ctx.db)
    return {"room": _dump(out), "summary": f"Added room {out.name}.",
            "_ui": _action("create_room", "success", f"Added room {out.name}", None, "room", out.id)}


@tool("update_room", "Rename/change a room.",
      schema_from_model(RoomUpdate, extra={"room_id": {"type": "string"}}, required=["room_id"]),
      write=True, label="Updating room")
def t_update_room(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import update_room
    rid = str(args.pop("room_id", ""))
    out = update_room(rid, RoomUpdate.model_validate(args), ctx.db)
    return {"room": _dump(out), "summary": f"Updated room {out.name}.",
            "_ui": _action("update_room", "success", f"Updated room {out.name}", None, "room", out.id)}


@tool("delete_room", "Delete a room (its appliances are kept, just unassigned). Confirm first.",
      {"type": "object", "properties": {"room_id": {"type": "string"}}, "required": ["room_id"]},
      write=True, label="Deleting room")
def t_delete_room(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.inventory import delete_room
    delete_room(str(args.get("room_id")), ctx.db)
    return {"deleted": True, "summary": f"Deleted room {args.get('room_id')}.",
            "_ui": _action("delete_room", "success", "Room deleted", None, "room", args.get("room_id"))}


@tool("create_bill", "Record an electricity bill. units_consumed_kwh and bill_amount_inr are required; "
      "billing_month (1-12) and billing_year identify the period.",
      schema_from_model(ElectricityBillCreate, exclude=("id",)), write=True, label="Adding bill")
def t_create_bill(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    data = ElectricityBillCreate.model_validate(args)
    bill = ElectricityBill(**data.model_dump(exclude={"id"}, by_alias=False),
                           id=f"bill-{uuid.uuid4().hex[:8]}", created_at=utcnow())
    ctx.db.add(bill)
    ctx.db.commit()
    ctx.db.refresh(bill)
    out = ElectricityBillSchema.model_validate(bill)
    return {"bill": _dump(out), "summary": f"Added bill: {out.units_consumed_kwh:g} kWh, ₹{out.bill_amount_inr:g}.",
            "_ui": _action("create_bill", "success", "Bill added",
                           f"{out.units_consumed_kwh:g} kWh · ₹{out.bill_amount_inr:g}", "bill", out.id)}


@tool("update_bill", "Change fields of an existing bill (only those given).",
      schema_from_model(ElectricityBillUpdate, extra={"bill_id": {"type": "string"}}, required=["bill_id"]),
      write=True, label="Updating bill")
def t_update_bill(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.bills import update_bill
    bid = str(args.pop("bill_id", ""))
    out = update_bill(bid, ElectricityBillUpdate.model_validate(args), ctx.db)
    return {"bill": _dump(out), "summary": f"Updated bill {bid}: {', '.join(args)}.",
            "_ui": _action("update_bill", "success", "Bill updated", ", ".join(args), "bill", bid)}


@tool("delete_bill", "Delete a bill. Confirm first.",
      {"type": "object", "properties": {"bill_id": {"type": "string"}}, "required": ["bill_id"]},
      write=True, label="Deleting bill")
def t_delete_bill(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.bills import delete_bill
    delete_bill(str(args.get("bill_id")), ctx.db)
    return {"deleted": True, "summary": f"Deleted bill {args.get('bill_id')}.",
            "_ui": _action("delete_bill", "success", "Bill deleted", None, "bill", args.get("bill_id"))}


@tool("set_target", "Set the monthly energy budget in ₹ (100–100000). target_type budget|reduction.",
      schema_from_model(EnergyTargetUpdate), write=True, label="Setting target")
def t_set_target(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.target import update_target
    out = update_target(EnergyTargetUpdate.model_validate(args), ctx.db)
    kwh = f" (≈{out.monthly_target_kwh:g} kWh)" if out.monthly_target_kwh else ""
    return {"target": _dump(out), "summary": f"Monthly budget set to ₹{out.monthly_budget_inr:g}{kwh}.",
            "_ui": _action("set_target", "success", f"Budget ₹{out.monthly_budget_inr:g}/month", kwh.strip() or None,
                           "target", "1")}


@tool("clear_target", "Remove the monthly target.", write=True, label="Clearing target")
def t_clear_target(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.target import clear_target
    clear_target(ctx.db)
    return {"cleared": True, "summary": "Monthly target removed.",
            "_ui": _action("clear_target", "success", "Target removed", None, "target", "1")}


@tool("update_household_config", "Change household settings, e.g. tariff_rate_inr_per_kwh, occupants.",
      schema_from_model(HouseholdConfigUpdate), write=True, label="Updating household")
def t_update_household(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.api.household import update_household_config
    out = update_household_config(HouseholdConfigUpdate.model_validate(args), ctx.db)
    return {"household": _dump(out), "summary": f"Household updated: {', '.join(args)}.",
            "_ui": _action("update_household_config", "success", "Household updated", ", ".join(args),
                           "household", "1")}


@tool("dismiss_conflict", "Hide a flagged conflict for 24 h (it comes back if it gets worse).",
      {"type": "object", "properties": {"conflict_id": {"type": "string"}}, "required": ["conflict_id"]},
      write=True, label="Dismissing conflict")
def t_dismiss(ctx: ToolContext, args: Dict[str, Any]) -> Dict[str, Any]:
    from app.ai.conflicts import dismiss_conflict
    if not dismiss_conflict(ctx.db, str(args.get("conflict_id"))):
        raise ToolError("No such active conflict.")
    return {"dismissed": True, "summary": f"Dismissed {args.get('conflict_id')} for 24 h."}


# ═══════════════════════════════════════════════════════════════
# EXECUTION
# ═══════════════════════════════════════════════════════════════

def _error_text(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, ValidationError):
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
    return str(exc)


def execute_tool_sync(name: str, raw_args: str, mqtt_client: Any = None,
                      conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Run one tool in its own DB session. Never raises: errors come back as {ok: false, error}."""
    spec = REGISTRY.get(name)
    if spec is None:
        return {"ok": False, "error": f"Unknown tool '{name}'."}
    try:
        args = json.loads(raw_args or "{}") if isinstance(raw_args, str) else dict(raw_args or {})
        if not isinstance(args, dict):
            raise ValueError
    except (ValueError, TypeError):
        return {"ok": False, "error": "Tool arguments must be a JSON object."}
    logged_args = dict(args)

    with SessionLocal() as db:
        ctx = ToolContext(db=db, mqtt_client=mqtt_client, conversation_id=conversation_id)
        try:
            data = spec.fn(ctx, args)
            ok, error = True, None
        except (ToolError, HTTPException, ValidationError, ValueError) as exc:
            db.rollback()
            data, ok, error = {}, False, _error_text(exc)
        except Exception as exc:  # pragma: no cover - defensive
            db.rollback()
            logger.exception("AI tool %s crashed", name)
            data, ok, error = {}, False, f"Internal error: {type(exc).__name__}"

        ui = data.pop("_ui", None) if ok else None
        summary = data.get("summary") if ok else error
        if spec.write:
            if not ok:
                ui = _action(name, "error", f"{spec.label} failed", error)
            try:
                db.add(AIActionLog(conversation_id=conversation_id, tool=name,
                                   arguments_json=json.dumps(logged_args, default=str), ok=ok,
                                   summary=summary if ok else None, error=error, created_at=utcnow()))
                db.commit()
            except Exception:  # pragma: no cover
                db.rollback()
                logger.exception("Could not write AI action log")
            if ok:
                broadcaster.publish_from_thread("ai_action", {
                    "tool": name, "summary": summary,
                    "entityType": (ui or {}).get("entityType"), "entityId": (ui or {}).get("entityId")})

    result: Dict[str, Any] = {"ok": ok}
    if ok:
        result["data"] = data
    else:
        result["error"] = error
    return {"result": result, "ui": ui, "summary": summary, "write": spec.write}
