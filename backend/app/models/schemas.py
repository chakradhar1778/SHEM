"""
SHEM Backend — Pydantic Schemas

API convention
--------------
All API request/response models inherit from ApiModel:
  * JSON keys are camelCase, with energy/currency units spelled the way the
    frontend already uses them: total_kwh → "totalKWh",
    monthly_budget_inr → "monthlyBudgetINR", energy_kwh → "energyKWh".
  * Requests accept either camelCase or snake_case keys.
  * Datetimes are serialised as UTC ISO 8601 strings ("2026-11-01T09:30:00Z").

MQTT payload models (MQTT*) mirror the ESP32 firmware JSON exactly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

from app.utils.timestamps import as_utc, to_iso

_UNIT_WORDS = {"kwh": "KWh", "inr": "INR"}


def api_alias(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(_UNIT_WORDS.get(p, p.capitalize()) for p in parts[1:])


class ApiModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=api_alias,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
        from_attributes=True,
    )


UtcDateTime = Annotated[datetime, AfterValidator(as_utc), PlainSerializer(to_iso, return_type=str)]

ShortText = Annotated[str, Field(min_length=1, max_length=128)]
OptText = Optional[Annotated[str, Field(max_length=128)]]


# ── Health ─────────────────────────────────────────────────────────────────────

class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    version: str
    db_ok: bool
    mqtt_connected: bool
    timestamp: UtcDateTime


# ── Device Status ──────────────────────────────────────────────────────────────

class DeviceStatusResponse(ApiModel):
    device_id: str
    mqtt_connected: bool
    device_online: bool
    connection_status: str = "unknown"
    last_seen_at: Optional[UtcDateTime] = None
    pzem_readings_valid: bool = False
    relay1_state: Optional[Literal["ON", "OFF"]] = None
    stale_since: Optional[UtcDateTime] = None


# ── Telemetry ──────────────────────────────────────────────────────────────────

class TelemetryReading(ApiModel):
    id: Optional[int] = None
    device_id: str
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    active_power_w: Optional[float] = None
    energy_kwh: Optional[float] = None
    frequency_hz: Optional[float] = None
    power_factor: Optional[float] = None
    relay1_state: Optional[str] = None
    # Measured load activity (active power above threshold) — NOT the relay state.
    load_active: Optional[bool] = None
    supply_type: str = "AC"
    source: str = "PZEM-004T"
    validity: str = "valid"
    validity_reason: Optional[str] = None
    measured_at: Optional[UtcDateTime] = None
    received_at: Optional[UtcDateTime] = None


class LatestTelemetryResponse(ApiModel):
    available: bool
    stale: bool
    age_seconds: Optional[float] = None
    reading: Optional[TelemetryReading] = None
    message: Optional[str] = None


class TelemetryHistoryPoint(ApiModel):
    timestamp: UtcDateTime              # bucket start (or reading time for raw)
    samples: int = 1
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    active_power_w: Optional[float] = None    # average over the bucket
    max_power_w: Optional[float] = None
    energy_kwh: Optional[float] = None        # register value at end of bucket
    energy_used_kwh: Optional[float] = None   # consumption inside the bucket (1h resolution)
    frequency_hz: Optional[float] = None
    power_factor: Optional[float] = None


HistoryResolution = Literal["auto", "raw", "1m", "5m", "15m", "1h"]


class TelemetryHistoryResponse(ApiModel):
    device_id: str
    from_time: UtcDateTime
    to_time: UtcDateTime
    resolution: str
    count: int
    truncated: bool = False
    data_note: Optional[str] = None
    readings: List[TelemetryHistoryPoint] = []


# ── Relay ──────────────────────────────────────────────────────────────────────

class RelayCommandRequest(ApiModel):
    state: Literal["ON", "OFF"]


class RelayCommandResponse(ApiModel):
    command_id: str
    channel: int = 1
    requested_state: str
    status: str
    message: str
    created_at: UtcDateTime
    expires_at: UtcDateTime


class RelayStatusResponse(ApiModel):
    device_id: str
    channel: int = 1
    commanded_state: Optional[Literal["ON", "OFF"]] = None   # null = never reported
    last_reported_at: Optional[UtcDateTime] = None


class RelayCommandDetailResponse(ApiModel):
    command_id: str
    device_id: str
    channel: int
    requested_state: str
    status: str
    created_at: UtcDateTime
    published_at: Optional[UtcDateTime] = None
    acknowledged_at: Optional[UtcDateTime] = None
    expires_at: Optional[UtcDateTime] = None
    error_message: Optional[str] = None


# ── Inbound MQTT payloads (firmware JSON shape) ────────────────────────────────

class MQTTTelemetryPayload(BaseModel):
    deviceId: str
    voltage: float
    current: float
    power: float
    energy: float
    energyUnit: Optional[str] = None      # required to equal "kWh" (checked in service)
    frequency: Optional[float] = None
    powerFactor: Optional[float] = None
    relay1State: Optional[str] = None
    supplyType: Optional[str] = None
    source: Optional[str] = None
    timestamp: Optional[str] = None       # "" before the ESP32 has NTP time


class MQTTStatusPayload(BaseModel):
    deviceId: str
    status: Literal["online", "offline"]
    relay1State: Optional[Literal["ON", "OFF"]] = None
    timestamp: Optional[str] = None       # absent in the firmware's LWT message


class MQTTRelayStatePayload(BaseModel):
    deviceId: str
    channel: Literal[1]
    state: Literal["ON", "OFF"]
    timestamp: Optional[str] = None


ACK_STATUSES = (
    "applied",
    "duplicate",
    "rejected_expired",
    "rejected_invalid_channel",
    "rejected_invalid_state",
    "rejected_time_unsynchronized",
)


class MQTTRelayAckPayload(BaseModel):
    deviceId: str
    channel: int
    commandId: str = Field(min_length=1, max_length=64)
    commandedState: Literal["ON", "OFF"]
    status: Literal[ACK_STATUSES]  # type: ignore[valid-type]
    timestamp: Optional[str] = None


# ── Household Config ───────────────────────────────────────────────────────────

class HouseholdConfigSchema(ApiModel):
    home_name: str
    location: Optional[str] = None
    home_type: str
    occupants: int
    floor_area_sqm: Optional[float] = None
    utility_provider: Optional[str] = None
    tariff_rate_inr_per_kwh: float
    is_configured: bool = False
    updated_at: Optional[UtcDateTime] = None


class HouseholdConfigUpdate(ApiModel):
    home_name: Optional[ShortText] = None
    location: OptText = None
    home_type: Optional[ShortText] = None
    occupants: Optional[int] = Field(None, ge=1, le=50)
    floor_area_sqm: Optional[float] = Field(None, gt=0, le=100000)
    utility_provider: OptText = None
    tariff_rate_inr_per_kwh: Optional[float] = Field(None, gt=0, le=100)
    is_configured: Optional[bool] = None


# ── Rooms ──────────────────────────────────────────────────────────────────────

class RoomSchema(ApiModel):
    id: str
    name: str
    room_type: Optional[str] = None
    floor: Optional[int] = None
    created_at: Optional[UtcDateTime] = None


class RoomCreate(ApiModel):
    id: Optional[Annotated[str, Field(min_length=1, max_length=64)]] = None
    name: ShortText
    room_type: OptText = "general"
    floor: Optional[int] = Field(1, ge=-5, le=200)


class RoomUpdate(ApiModel):
    name: Optional[ShortText] = None
    room_type: OptText = None
    floor: Optional[int] = Field(None, ge=-5, le=200)


# ── Appliances ─────────────────────────────────────────────────────────────────

class ApplianceSchema(ApiModel):
    id: str
    room_id: Optional[str] = None
    catalogue_id: Optional[str] = None
    name: str
    category: Optional[str] = None
    icon_type: Optional[str] = None
    rated_watts: Optional[float] = None
    quantity: int = 1
    daily_hours: float = 0.0
    status: str = "off"
    is_essential: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    purchase_year: Optional[int] = None
    notes: Optional[str] = None
    relay_channel: Optional[int] = None
    # True when the appliance is not on a relay → it runs as a simulated device.
    is_simulated: bool = True
    sim_auto: bool = True
    sim_manual_state: Optional[Literal["ON", "OFF"]] = None
    sim_override_until: Optional[UtcDateTime] = None
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class ApplianceCreate(ApiModel):
    id: Optional[Annotated[str, Field(min_length=1, max_length=64)]] = None
    room_id: Optional[str] = None
    catalogue_id: OptText = None
    name: ShortText
    category: OptText = None
    icon_type: OptText = None
    rated_watts: Optional[float] = Field(None, ge=0, le=50000)
    quantity: int = Field(1, ge=1, le=1000)
    daily_hours: float = Field(0.0, ge=0, le=24)
    status: Annotated[str, Field(max_length=32)] = "off"
    is_essential: Optional[Literal["yes", "no", "unsure"]] = None
    brand: OptText = None
    model: OptText = None
    purchase_year: Optional[int] = Field(None, ge=1950, le=2100)
    notes: Optional[Annotated[str, Field(max_length=2000)]] = None
    # Firmware currently implements relay channel 1 only.
    relay_channel: Optional[int] = Field(None, ge=1, le=1)
    # Simulated appliances only: follow the daily routine built from daily_hours.
    sim_auto: bool = True


class ApplianceUpdate(ApiModel):
    """Partial update. Send `"roomId": null` to unassign from a room."""
    room_id: Optional[str] = None
    catalogue_id: OptText = None
    name: Optional[ShortText] = None
    category: OptText = None
    icon_type: OptText = None
    rated_watts: Optional[float] = Field(None, ge=0, le=50000)
    quantity: Optional[int] = Field(None, ge=1, le=1000)
    daily_hours: Optional[float] = Field(None, ge=0, le=24)
    status: Optional[Annotated[str, Field(max_length=32)]] = None
    is_essential: Optional[Literal["yes", "no", "unsure"]] = None
    brand: OptText = None
    model: OptText = None
    purchase_year: Optional[int] = Field(None, ge=1950, le=2100)
    notes: Optional[Annotated[str, Field(max_length=2000)]] = None
    # Send `"relayChannel": null` to detach the appliance from its relay.
    relay_channel: Optional[int] = Field(None, ge=1, le=1)
    sim_auto: Optional[bool] = None


# ── Electricity Bills ──────────────────────────────────────────────────────────

class ElectricityBillSchema(ApiModel):
    id: str
    utility_provider: Optional[str] = None
    account_id: Optional[str] = None
    billing_month: Optional[int] = None
    billing_year: Optional[int] = None
    billing_period: Optional[str] = None
    billing_period_start: Optional[str] = None
    billing_period_end: Optional[str] = None
    billing_period_days: Optional[int] = None
    due_date: Optional[str] = None
    document_filename: Optional[str] = None
    has_document: bool = False
    document_content_type: Optional[str] = None
    document_size: Optional[int] = None
    document_uploaded_at: Optional[UtcDateTime] = None
    paid_on: Optional[str] = None            # local YYYY-MM-DD; None = unpaid
    paid_at: Optional[UtcDateTime] = None
    units_consumed_kwh: float
    bill_amount_inr: float
    location_tag: Optional[str] = None
    created_at: Optional[UtcDateTime] = None


class BillPaidRequest(ApiModel):
    paid_on: Optional[Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]] = None   # default: today (local)


class ElectricityBillCreate(ApiModel):
    id: Optional[Annotated[str, Field(min_length=1, max_length=64)]] = None
    utility_provider: OptText = None
    account_id: OptText = None
    billing_month: Optional[int] = Field(None, ge=1, le=12)
    billing_year: Optional[int] = Field(None, ge=2000, le=2100)
    billing_period: OptText = None
    billing_period_start: Optional[Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]] = None
    billing_period_end: Optional[Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]] = None
    billing_period_days: Optional[int] = Field(None, ge=1, le=366)
    due_date: Optional[Annotated[str, Field(max_length=32)]] = None
    document_filename: Optional[Annotated[str, Field(max_length=255)]] = None
    units_consumed_kwh: float = Field(..., gt=0, le=1_000_000)
    bill_amount_inr: float = Field(..., gt=0, le=10_000_000)
    location_tag: OptText = "my_home"


class ElectricityBillUpdate(ApiModel):
    utility_provider: OptText = None
    account_id: OptText = None
    billing_month: Optional[int] = Field(None, ge=1, le=12)
    billing_year: Optional[int] = Field(None, ge=2000, le=2100)
    billing_period: OptText = None
    billing_period_start: Optional[Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]] = None
    billing_period_end: Optional[Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]] = None
    billing_period_days: Optional[int] = Field(None, ge=1, le=366)
    due_date: Optional[Annotated[str, Field(max_length=32)]] = None
    document_filename: Optional[Annotated[str, Field(max_length=255)]] = None
    units_consumed_kwh: Optional[float] = Field(None, gt=0, le=1_000_000)
    bill_amount_inr: Optional[float] = Field(None, gt=0, le=10_000_000)
    location_tag: OptText = None


# ── Energy Target ──────────────────────────────────────────────────────────────

class EnergyTargetSchema(ApiModel):
    monthly_budget_inr: float
    target_type: Literal["budget", "reduction"] = "budget"
    is_configured: bool = False
    monthly_target_kwh: Optional[float] = None   # budget ÷ configured tariff
    saver_mode: Literal["off", "suggest", "auto"] = "off"
    saver_trigger: Literal["at_risk", "over"] = "at_risk"
    updated_at: Optional[UtcDateTime] = None


class EnergyTargetUpdate(ApiModel):
    monthly_budget_inr: float = Field(..., ge=100, le=100000)
    target_type: Literal["budget", "reduction"] = "budget"


# ── Insights & Analytics ───────────────────────────────────────────────────────

class InsightsTrendPoint(ApiModel):
    label: str
    start: UtcDateTime
    usage_kwh: float
    target_kwh: Optional[float] = None
    is_peak: bool = False
    measured: bool = False      # False → no telemetry in this bucket (usage shown as 0)


class CategoryShare(ApiModel):
    """Household rated-load ESTIMATE per category (not a meter reading)."""
    category_id: str
    category_label: str
    icon_type: str
    kwh: float
    percentage: float
    percent_change: Optional[int] = None   # needs per-category metering; not available
    direction: Literal["up", "down", "neutral"] = "neutral"


class InsightsKeyInsight(ApiModel):
    title: str
    description: str
    peak_period: Optional[str] = None


class PeriodComparison(ApiModel):
    previous_kwh: float
    previous_coverage_hours: float
    percent_change: Optional[float] = None


class BillComparison(ApiModel):
    billing_label: str
    bill_daily_kwh: float
    bill_rate_inr: float
    measured_daily_kwh: Optional[float] = None


class ApplianceUsage(ApiModel):
    """Energy of one appliance in a period: metered (relay circuit, PZEM) or simulated."""
    appliance_id: str
    name: str
    icon_type: Optional[str] = None
    category: Optional[str] = None
    room_name: Optional[str] = None
    source: Literal["metered", "simulated"]
    kwh: float
    percentage: float
    cost_inr: float
    on_hours: Optional[float] = None
    peak_hour: Optional[int] = None
    peak_hour_label: Optional[str] = None


class InsightsResponse(ApiModel):
    period: Literal["week", "month", "year"]
    period_label: str
    period_start: UtcDateTime
    period_end: UtcDateTime
    total_kwh: float
    total_cost_inr: float
    effective_rate_inr: float
    is_cost_estimated: bool = True
    rate_disclosure: str
    has_data: bool
    is_modelled_estimate: bool = False      # totals are always measured, never modelled
    coverage_hours: float
    expected_hours: float
    data_note: Optional[str] = None
    methodology_note: str
    key_insight: InsightsKeyInsight
    trend_points: List[InsightsTrendPoint] = []
    shifts: List[CategoryShare] = []
    shifts_are_estimates: bool = True
    comparison: Optional[PeriodComparison] = None
    bill_comparison: Optional[BillComparison] = None
    metered_kwh: float = 0.0
    simulated_kwh: float = 0.0
    appliance_usage: List[ApplianceUsage] = []


class HourlyPoint(ApiModel):
    hour: int
    time_label: str
    usage_kwh: float
    metered_kwh: float = 0.0
    simulated_kwh: float = 0.0
    target_kwh: Optional[float] = None
    is_peak: bool = False
    measured: bool = False      # any metered OR simulated energy in this hour


class PeriodTopAppliance(ApiModel):
    appliance_id: str
    name: str
    icon_type: Optional[str] = None
    source: Literal["metered", "simulated"]
    kwh: float


class DayPeriodBreakdown(ApiModel):
    period: Literal["night", "morning", "afternoon", "evening"]
    label: str
    time_range: str
    kwh: float
    percentage: float
    metered_kwh: float = 0.0
    simulated_kwh: float = 0.0
    cost_inr: float = 0.0
    avg_power_w: float = 0.0            # kWh ÷ elapsed hours of the period
    is_peak: bool = False               # the period with the most energy that day
    peak_hour: Optional[int] = None
    peak_hour_label: Optional[str] = None
    peak_hour_kwh: Optional[float] = None
    top_appliances: List[PeriodTopAppliance] = []


class PeakSummary(ApiModel):
    period: Optional[str] = None
    period_label: Optional[str] = None
    hour: Optional[int] = None
    hour_label: Optional[str] = None
    hour_kwh: Optional[float] = None
    avg_power_w: Optional[float] = None     # average power during the peak hour
    top_appliance: Optional[str] = None


class InsightCard(ApiModel):
    title: str
    description: str
    badge_text: str


class TodayInsightsResponse(ApiModel):
    date: str                               # local calendar date YYYY-MM-DD
    is_today: bool = True
    has_data: bool
    energy_today_kwh: float
    daily_target_kwh: Optional[float] = None
    is_target_configured: bool
    cost_today_inr: float
    effective_rate_inr: float
    rate_disclosure: str
    hourly_points: List[HourlyPoint] = []
    day_periods: List[DayPeriodBreakdown] = []
    appliance_breakdown: List[CategoryShare] = []
    insight_card: InsightCard
    data_note: Optional[str] = None
    methodology_note: str
    metered_kwh: float = 0.0
    simulated_kwh: float = 0.0
    appliance_usage: List[ApplianceUsage] = []
    peak: Optional[PeakSummary] = None


class DailyTotal(ApiModel):
    date: str                               # local YYYY-MM-DD
    weekday: str
    day_label: str                          # e.g. "9 Nov"
    kwh: float
    metered_kwh: float
    simulated_kwh: float
    cost_inr: float
    has_data: bool
    is_today: bool = False
    peak_period: Optional[str] = None


class DailyTotalsResponse(ApiModel):
    days: List[DailyTotal]
    average_kwh: Optional[float] = None
    daily_target_kwh: Optional[float] = None


# ── Simulation ─────────────────────────────────────────────────────────────────

class SimCommandRequest(ApiModel):
    state: Literal["ON", "OFF"]


class SimApplianceLive(ApiModel):
    appliance_id: str
    name: str
    icon_type: Optional[str] = None
    room_id: Optional[str] = None
    state: Literal["ON", "OFF"]
    power_w: float
    mode: Literal["auto", "manual", "off"]
    sim_auto: bool
    override_until: Optional[str] = None
    next_change_at: Optional[str] = None
    routine: Optional[str] = None
    today_kwh: float
    rated_watts: Optional[float] = None
    quantity: int = 1


class SimStatusResponse(ApiModel):
    appliances: List[SimApplianceLive]
    total_power_w: float
    voltage_v: Optional[float] = None
    server_time: Optional[str] = None


class EnergyRecommendation(ApiModel):
    id: str
    title: str
    description: str
    category: str
    priority: Literal["high", "medium", "low"]
    evidence: str                           # the measured/user data that triggered it


# ── Billing: tariff + projected bill ───────────────────────────────────────────

class TariffSlab(ApiModel):
    upto_kwh: Optional[float] = Field(None, gt=0, le=1_000_000)   # None = no upper limit (last slab)
    rate_inr: float = Field(..., ge=0, le=100)


class TariffSchema(ApiModel):
    mode: Literal["flat", "slab"]
    flat_rate_inr: float
    slabs: List[TariffSlab] = []
    fixed_charge_inr: float = 0.0
    fuel_adjustment_inr_per_kwh: float = 0.0
    electricity_duty_percent: float = 0.0
    billing_cycle_day: int = 1
    utility_provider: Optional[str] = None


class TariffUpdate(ApiModel):
    mode: Optional[Literal["flat", "slab"]] = None
    flat_rate_inr: Optional[float] = Field(None, gt=0, le=100)
    slabs: Optional[List[TariffSlab]] = Field(None, max_length=12)
    fixed_charge_inr: Optional[float] = Field(None, ge=0, le=100_000)
    fuel_adjustment_inr_per_kwh: Optional[float] = Field(None, ge=0, le=20)
    electricity_duty_percent: Optional[float] = Field(None, ge=0, le=50)
    billing_cycle_day: Optional[int] = Field(None, ge=1, le=28)


class BillLine(ApiModel):
    label: str
    from_kwh: float
    to_kwh: Optional[float] = None
    kwh: float
    rate_inr: float
    amount_inr: float


class BillBreakdownSchema(ApiModel):
    kwh: float
    lines: List[BillLine]
    energy_charge_inr: float
    fuel_charge_inr: float
    duty_inr: float
    fixed_charge_inr: float
    total_inr: float
    effective_rate_inr: Optional[float] = None
    variable_rate_inr: Optional[float] = None
    marginal_rate_inr: float
    slab_index: int
    kwh_to_next_slab: Optional[float] = None
    next_slab_rate_inr: Optional[float] = None


class BudgetStatus(ApiModel):
    budget_inr: float
    budget_kwh: float
    spent_inr: float
    projected_inr: float
    projected_over_inr: float
    used_percent: float
    remaining_kwh: float
    daily_allowance_kwh: Optional[float] = None
    status: Literal["on_track", "at_risk", "over"]


class BillProjectionResponse(ApiModel):
    cycle_start: str                    # local YYYY-MM-DD (inclusive)
    cycle_end: str                      # local YYYY-MM-DD (exclusive: first day of the next cycle)
    cycle_days: int
    elapsed_days: float
    days_left: float
    used_kwh: float
    metered_kwh: float
    simulated_kwh: float
    daily_kwh: float
    projected_kwh: float
    pace_basis: Literal["cycle", "last24h"]
    confidence: Literal["low", "medium", "high"]
    so_far: BillBreakdownSchema
    projected: BillBreakdownSchema
    tariff: TariffSchema
    budget: Optional[BudgetStatus] = None
    appliance_costs: List["ApplianceBillShare"] = []
    disclaimer: str


class BillEstimateRequest(ApiModel):
    kwh: float = Field(..., ge=0, le=1_000_000)


class ApplianceBillShare(ApiModel):
    appliance_id: str
    name: str
    icon_type: Optional[str] = None
    source: Literal["metered", "simulated"]
    kwh: float
    share_percent: float
    cost_inr: float


class BillApplianceBreakdown(ApiModel):
    bill_id: str
    billing_label: str
    period_start: str                   # local YYYY-MM-DD, inclusive
    period_end: str                     # local YYYY-MM-DD, exclusive
    period_source: Literal["dates", "cycle"]
    bill_kwh: float
    bill_amount_inr: float
    measured_kwh: float
    metered_kwh: float
    simulated_kwh: float
    coverage_percent: float
    fixed_charge_inr: float
    variable_rate_inr: float
    appliances: List[ApplianceBillShare]
    rest_kwh: float
    rest_inr: float
    rest_percent: float
    notes: List[str] = []
    period_days: float = 0.0
    covered_hours: int = 0
    billed_daily_kwh: Optional[float] = None       # bill kWh ÷ period days
    recorded_daily_kwh: Optional[float] = None     # SHEM metered + simulated kWh per recorded day (≥ 6 h data)
    variance_percent: Optional[float] = None       # recorded vs billed, per day


BillProjectionResponse.model_rebuild()



# ── Notifications & budget saver ───────────────────────────────────────────────

class NotificationSchema(ApiModel):
    id: int
    kind: str
    severity: Literal["info", "warning", "critical", "success"]
    title: str
    message: str
    link: Optional[str] = None
    created_at: UtcDateTime
    read_at: Optional[UtcDateTime] = None


class NotificationList(ApiModel):
    items: List[NotificationSchema]
    unread_count: int


class AutomationLogEntry(ApiModel):
    id: int
    appliance_id: Optional[str] = None
    appliance_name: Optional[str] = None
    action: Literal["switched_off", "suggested", "skipped", "failed"]
    reason: str
    cycle_start: Optional[str] = None
    created_at: UtcDateTime


class SaverCandidate(ApiModel):
    appliance_id: str
    name: str
    icon_type: Optional[str] = None
    is_on: bool
    simulated: bool


class BudgetSaverSettings(ApiModel):
    mode: Literal["off", "suggest", "auto"]
    trigger: Literal["at_risk", "over"]
    budget_configured: bool
    candidates: List[SaverCandidate] = []
    log: List[AutomationLogEntry] = []


class BudgetSaverUpdate(ApiModel):
    mode: Optional[Literal["off", "suggest", "auto"]] = None
    trigger: Optional[Literal["at_risk", "over"]] = None
