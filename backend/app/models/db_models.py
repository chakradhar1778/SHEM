"""
SHEM Backend — ORM Database Models

Hardware / MQTT tables : devices, telemetry, telemetry_hourly, relay_commands,
                         relay_channels, device_status_events
User / household tables: household_config, rooms, appliances,
                         electricity_bills, energy_targets
Simulation             : sim_energy_hourly (per simulated appliance, per local hour)

Data condensing:
  * `telemetry` holds raw ~2 s PZEM readings for RAW_TELEMETRY_RETENTION_DAYS.
  * `telemetry_hourly` holds one row per local clock hour (energy delta from
    the cumulative PZEM register + electrical aggregates) and is kept
    indefinitely (~8 760 rows/year instead of ~15.7 M raw rows/year).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.utils.timestamps import UTC, utcnow


class UTCDateTime(TypeDecorator):
    """
    Stores datetimes as naive UTC in SQLite and always returns aware UTC
    datetimes, so application code never mixes naive and aware values.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: Optional[datetime], dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value

    def process_result_value(self, value: Optional[datetime], dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


# ═══════════════════════════════════════════════════════════════
# HARDWARE / MQTT TABLES
# ═══════════════════════════════════════════════════════════════

class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(128))
    device_type: Mapped[Optional[str]] = mapped_column(String(64), default="ESP32_PZEM")
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    # "unknown" | "online" | "offline"
    connection_status: Mapped[str] = mapped_column(String(32), default="unknown")
    pzem_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class TelemetryRow(Base):
    """One row per MQTT telemetry message (AC only — DC is discarded)."""
    __tablename__ = "telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"), nullable=False)

    voltage_v: Mapped[Optional[float]] = mapped_column(Float)
    current_a: Mapped[Optional[float]] = mapped_column(Float)
    active_power_w: Mapped[Optional[float]] = mapped_column(Float)
    energy_kwh: Mapped[Optional[float]] = mapped_column(Float)     # cumulative PZEM register
    frequency_hz: Mapped[Optional[float]] = mapped_column(Float)   # NULL when unavailable
    power_factor: Mapped[Optional[float]] = mapped_column(Float)   # NULL when unavailable

    relay1_state: Mapped[Optional[str]] = mapped_column(String(8))
    supply_type: Mapped[str] = mapped_column(String(8), default="AC")
    source: Mapped[str] = mapped_column(String(64), default="PZEM-004T")

    validity: Mapped[str] = mapped_column(String(16), default="valid")  # valid | invalid
    validity_reason: Mapped[Optional[str]] = mapped_column(String(256))

    measured_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        Index("ix_telemetry_device_measured", "device_id", "measured_at"),
    )


class TelemetryHourly(Base):
    """Condensed per-local-hour rollup of raw telemetry (kept indefinitely)."""
    __tablename__ = "telemetry_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"), nullable=False)
    bucket_start: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)  # UTC instant of local hour start

    sample_count: Mapped[int] = mapped_column(Integer, default=0)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)  # register delta attributed to this hour
    energy_register_end: Mapped[Optional[float]] = mapped_column(Float)
    last_measured_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    voltage_avg: Mapped[Optional[float]] = mapped_column(Float)
    voltage_min: Mapped[Optional[float]] = mapped_column(Float)
    voltage_max: Mapped[Optional[float]] = mapped_column(Float)
    current_avg: Mapped[Optional[float]] = mapped_column(Float)
    power_avg: Mapped[Optional[float]] = mapped_column(Float)
    power_max: Mapped[Optional[float]] = mapped_column(Float)
    power_factor_avg: Mapped[Optional[float]] = mapped_column(Float)
    frequency_avg: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("device_id", "bucket_start", name="uq_hourly_device_bucket"),
    )


class RelayCommand(Base):
    """
    Lifecycle record for every relay command.
    pending → published → applied | rejected_* | timeout | publish_failed
    """
    __tablename__ = "relay_commands"

    command_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"), nullable=False)
    channel: Mapped[int] = mapped_column(Integer, default=1)
    requested_state: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(64), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    published_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    __table_args__ = (
        Index("ix_relay_commands_status_expires", "status", "expires_at"),
        Index("ix_relay_commands_created", "created_at"),
    )


class RelayChannel(Base):
    __tablename__ = "relay_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"), nullable=False)
    channel: Mapped[int] = mapped_column(Integer, default=1)
    commanded_state: Mapped[str] = mapped_column(String(8), default="OFF")
    last_reported_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    __table_args__ = (
        UniqueConstraint("device_id", "channel", name="uq_relay_channel"),
    )


class DeviceStatusEvent(Base):
    __tablename__ = "device_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32))  # online | offline
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    details: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_status_events_recorded", "recorded_at"),
    )


# ═══════════════════════════════════════════════════════════════
# USER / HOUSEHOLD TABLES
# ═══════════════════════════════════════════════════════════════

class HouseholdConfig(Base):
    __tablename__ = "household_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    home_name: Mapped[str] = mapped_column(String(128), default="My Home")
    location: Mapped[Optional[str]] = mapped_column(String(128))
    home_type: Mapped[str] = mapped_column(String(64), default="Apartment")
    occupants: Mapped[int] = mapped_column(Integer, default=2)
    floor_area_sqm: Mapped[Optional[float]] = mapped_column(Float)
    utility_provider: Mapped[Optional[str]] = mapped_column(String(128))
    tariff_rate_inr_per_kwh: Mapped[float] = mapped_column(Float, default=7.5)
    # ── Bill model (see services/billing_service.py) ──
    # "flat" = every kWh at tariff_rate_inr_per_kwh; "slab" = tariff_slabs_json.
    tariff_mode: Mapped[str] = mapped_column(String(8), default="flat")
    # JSON list [{"uptoKWh": 100, "rateINR": 4.15}, …, {"uptoKWh": null, "rateINR": 8.2}] — cumulative upper bounds.
    tariff_slabs_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fixed_charge_inr: Mapped[float] = mapped_column(Float, default=0.0)            # per billing cycle
    fuel_adjustment_inr_per_kwh: Mapped[float] = mapped_column(Float, default=0.0)  # FPPCA / FAC
    electricity_duty_percent: Mapped[float] = mapped_column(Float, default=0.0)     # on energy + fuel charges
    billing_cycle_day: Mapped[int] = mapped_column(Integer, default=1)              # meter-reading day, 1–28
    # True once the user has completed the Home Setup flow
    is_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    room_type: Mapped[Optional[str]] = mapped_column(String(64))
    floor: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    appliances: Mapped[list["Appliance"]] = relationship(back_populates="room")


class Appliance(Base):
    __tablename__ = "appliances"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("rooms.id"), nullable=True)
    catalogue_id: Mapped[Optional[str]] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    category: Mapped[Optional[str]] = mapped_column(String(64))
    icon_type: Mapped[Optional[str]] = mapped_column(String(64))
    rated_watts: Mapped[Optional[float]] = mapped_column(Float)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    daily_hours: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="off")
    is_essential: Mapped[Optional[str]] = mapped_column(String(8))  # yes | no | unsure
    brand: Mapped[Optional[str]] = mapped_column(String(128))
    model: Mapped[Optional[str]] = mapped_column(String(128))
    purchase_year: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    # Optional link to a physical relay channel on the SHEM device (NULL = not relay-controlled).
    # One channel can drive at most one appliance entry (enforced in the inventory API).
    relay_channel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # ── Simulation (appliances WITHOUT a relay run as realistic simulated devices) ──
    # sim_auto: follow the daily routine derived from daily_hours + appliance type.
    sim_auto: Mapped[bool] = mapped_column(Boolean, default=True)
    # Manual switch from the app: "ON" | "OFF" (NULL = no manual override).
    sim_manual_state: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    # Manual override lasts until this instant (next routine change); NULL = indefinitely.
    sim_override_until: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    room: Mapped[Optional["Room"]] = relationship(back_populates="appliances")

    @property
    def is_simulated(self) -> bool:
        return self.relay_channel is None


class SimEnergyHourly(Base):
    """
    Energy used by one SIMULATED appliance in one local clock hour.
    No FK to appliances: history survives deleting the appliance (the name is
    snapshotted), exactly like real metered energy does.
    """
    __tablename__ = "sim_energy_hourly"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appliance_id: Mapped[str] = mapped_column(String(64), nullable=False)
    appliance_name: Mapped[str] = mapped_column(String(128))
    icon_type: Mapped[Optional[str]] = mapped_column(String(64))
    category: Mapped[Optional[str]] = mapped_column(String(64))
    bucket_start: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)  # UTC instant of local hour start
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    on_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    power_max: Mapped[Optional[float]] = mapped_column(Float)
    samples: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("appliance_id", "bucket_start", name="uq_sim_hourly_appliance_bucket"),
        Index("ix_sim_hourly_bucket", "bucket_start"),
    )


class ElectricityBill(Base):
    __tablename__ = "electricity_bills"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    utility_provider: Mapped[Optional[str]] = mapped_column(String(128))
    account_id: Mapped[Optional[str]] = mapped_column(String(128))
    billing_month: Mapped[Optional[int]] = mapped_column(Integer)
    billing_year: Mapped[Optional[int]] = mapped_column(Integer)
    billing_period: Mapped[Optional[str]] = mapped_column(String(128))
    billing_period_start: Mapped[Optional[str]] = mapped_column(String(10))   # YYYY-MM-DD
    billing_period_end: Mapped[Optional[str]] = mapped_column(String(10))
    billing_period_days: Mapped[Optional[int]] = mapped_column(Integer)
    due_date: Mapped[Optional[str]] = mapped_column(String(32))
    document_filename: Mapped[Optional[str]] = mapped_column(String(255))
    units_consumed_kwh: Mapped[float] = mapped_column(Float)
    bill_amount_inr: Mapped[float] = mapped_column(Float)
    location_tag: Mapped[Optional[str]] = mapped_column(String(128))
    # Stored bill document (image/PDF) — kept for viewing only, never parsed.
    document_path: Mapped[Optional[str]] = mapped_column(String(255))        # relative to UPLOADS_DIR
    document_content_type: Mapped[Optional[str]] = mapped_column(String(64))
    document_size: Mapped[Optional[int]] = mapped_column(Integer)
    document_uploaded_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
    # Payment: local date the bill was paid (NULL = unpaid). Paid bills get no due/overdue alerts.
    paid_on: Mapped[Optional[str]] = mapped_column(String(10))           # YYYY-MM-DD
    paid_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)     # when it was marked paid
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        Index("ix_bills_year_month", "billing_year", "billing_month"),
    )

    @property
    def has_document(self) -> bool:
        return bool(self.document_path)


class EnergyTarget(Base):
    __tablename__ = "energy_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    monthly_budget_inr: Mapped[float] = mapped_column(Float, default=0.0)
    target_type: Mapped[str] = mapped_column(String(32), default="budget")  # budget | reduction
    is_configured: Mapped[bool] = mapped_column(Boolean, default=False)
    # Budget saver (opt-in): "off" | "suggest" (notify) | "auto" (switch off non-essential appliances)
    saver_mode: Mapped[str] = mapped_column(String(8), default="off")
    # When it acts: "at_risk" (projected bill above budget) | "over" (bill so far above budget)
    saver_trigger: Mapped[str] = mapped_column(String(8), default="at_risk")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS & AUTOMATION
# ═══════════════════════════════════════════════════════════════

class Notification(Base):
    """An alert shown in the app's notification bell. `dedupe_key` makes each alert fire once."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dedupe_key: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(32))          # bill_due | budget | slab | bill_mismatch | saver
    severity: Mapped[str] = mapped_column(String(16))      # info | warning | critical | success
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    link: Mapped[Optional[str]] = mapped_column(String(200))   # in-app route, e.g. /bill
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    read_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)

    __table_args__ = (
        Index("ix_notifications_created", "created_at"),
    )


class AutomationLog(Base):
    """Every action (or suggestion) the budget saver made, and why."""
    __tablename__ = "automation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    appliance_id: Mapped[Optional[str]] = mapped_column(String(64))
    appliance_name: Mapped[Optional[str]] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))         # switched_off | suggested | skipped | failed
    reason: Mapped[str] = mapped_column(Text)
    cycle_start: Mapped[Optional[str]] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        Index("ix_automation_log_created", "created_at"),
    )


# ═══════════════════════════════════════════════════════════════
# SHEM AI TABLES
# ═══════════════════════════════════════════════════════════════

class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(128), default="New chat")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AIMessage(Base):
    """
    One chat message in OpenAI format (role user | assistant | tool).
    Assistant replies shown to the user also carry their parsed `segments`
    (text + UI components), `followups` and tool-produced `actions`.
    """
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), ForeignKey("ai_conversations.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[Optional[str]] = mapped_column(Text)
    tool_calls_json: Mapped[Optional[str]] = mapped_column(Text)
    tool_call_id: Mapped[Optional[str]] = mapped_column(String(128))
    name: Mapped[Optional[str]] = mapped_column(String(64))
    segments_json: Mapped[Optional[str]] = mapped_column(Text)
    followups_json: Mapped[Optional[str]] = mapped_column(Text)
    actions_json: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        Index("ix_ai_messages_conversation", "conversation_id", "id"),
    )


class AIActionLog(Base):
    """Audit trail of every state-changing tool call the AI made."""
    __tablename__ = "ai_action_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(64))
    arguments_json: Mapped[Optional[str]] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    __table_args__ = (
        Index("ix_ai_action_log_created", "created_at"),
    )


class AIDailyInsight(Base):
    """AI daily briefing for one local calendar date."""
    __tablename__ = "ai_daily_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    insight_date: Mapped[str] = mapped_column(String(10), unique=True)   # YYYY-MM-DD (local)
    headline: Mapped[str] = mapped_column(String(256))
    content: Mapped[Optional[str]] = mapped_column(Text)
    segments_json: Mapped[Optional[str]] = mapped_column(Text)
    facts_json: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[Optional[str]] = mapped_column(String(32))          # NULL = rule-based fallback
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AIConflictDismissal(Base):
    """A conflict the user dismissed; it stays hidden until it becomes more severe or expires."""
    __tablename__ = "ai_conflict_dismissals"

    conflict_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    severity: Mapped[str] = mapped_column(String(16))
    dismissed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    dismissed_until: Mapped[Optional[datetime]] = mapped_column(UTCDateTime)
