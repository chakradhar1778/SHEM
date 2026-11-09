"""
SHEM Backend — Application Configuration
Reads all settings from environment variables / .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All backend configuration lives here.
    Values are read from environment variables or the .env file.
    No secrets are ever hardcoded.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── MQTT Broker ────────────────────────────────────────────
    mqtt_host: str = "xf061010.ala.asia-southeast1.emqxsl.com"
    mqtt_port: int = 8883
    mqtt_username: str = "shem_backend"
    mqtt_password: str = ""
    mqtt_ca_cert_path: str = "./certs/emqxsl-ca.crt"

    # ── Device ─────────────────────────────────────────────────
    device_id: str = "001"

    # ── Database ───────────────────────────────────────────────
    sqlite_path: str = "./shem.db"

    # ── API Security ───────────────────────────────────────────
    api_key: str = ""
    # Only for local experiments: when API_KEY is empty the API is CLOSED
    # unless this is explicitly set to true.
    allow_unauthenticated_dev: bool = False
    # Honour CF-Connecting-IP / X-Forwarded-For for rate limiting (tunnel setups).
    trust_proxy_headers: bool = True
    expose_docs: bool = True

    # ── Rate limits (slowapi syntax) ───────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_relay_command: str = "10/minute"
    rate_limit_history: str = "30/minute"
    rate_limit_bills_create: str = "20/minute"

    # ── Command & Staleness ────────────────────────────────────
    command_expiry_seconds: int = 30
    stale_telemetry_threshold_seconds: int = 10
    # Measured load activity (separate from relay commanded state)
    load_active_threshold_w: float = 5.0

    # ── Data retention / condensing ────────────────────────────
    # Raw 2-second telemetry is kept this long; older data survives only
    # as hourly rollups in telemetry_hourly (kept indefinitely).
    raw_telemetry_retention_days: int = 7
    # device_status_events and finished relay_commands
    event_retention_days: int = 90
    maintenance_interval_seconds: int = 300
    heartbeat_interval_seconds: int = 5

    # ── Locale ─────────────────────────────────────────────────
    # Used for "today", day/week/month boundaries and hour-of-day buckets.
    timezone: str = "Asia/Kolkata"

    # ── CORS ───────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    # ── Tariff ─────────────────────────────────────────────────
    default_tariff_rate_inr_per_kwh: float = 7.5

    # ── Appliance simulation (appliances without a relay) ─────
    simulation_enabled: bool = True

    # ── SHEM AI (energy guide) ─────────────────────────────────
    # Both providers are called through the OpenAI SDK (OpenAI-compatible
    # endpoints). The primary is tried first; the other one is the fallback.
    ai_enabled: bool = True
    ai_primary_provider: str = "gemini"          # gemini | groq
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ai_temperature: float = 0.4
    ai_request_timeout_seconds: float = 60.0
    ai_max_tool_rounds: int = 8
    ai_history_messages: int = 20                # previous user/assistant messages sent as context
    ai_tool_result_max_chars: int = 12000
    ai_background_enabled: bool = True           # conflict scan + daily insight scheduler
    ai_conflict_scan_interval_seconds: int = 60
    ai_daily_insight_hour: int = 7               # local hour after which yesterday's briefing is generated
    rate_limit_ai_chat: str = "20/minute"

    # ── SHEM AI Live voice (Sarvam) ────────────────────────────
    # Speech-to-text (Saaras, realtime WebSocket with VAD) and text-to-speech
    # (Bulbul). The LLM is still the Gemini/Groq router above.
    sarvam_api_key: str = ""
    sarvam_base_url: str = "https://api.sarvam.ai"
    sarvam_ws_url: str = "wss://api.sarvam.ai"
    sarvam_stt_model: str = "saaras:v3-realtime"     # realtime streaming model
    sarvam_stt_rest_model: str = "saaras:v4"         # one-shot uploads (/voice/transcribe)
    sarvam_stt_language: str = "auto"                # auto-detect, or e.g. en-IN, hi-IN, te-IN
    sarvam_stt_silence_ms: int = 600                 # pause that ends an utterance
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = "shubh"
    sarvam_tts_pace: float = 1.05
    sarvam_tts_sample_rate: int = 22050
    sarvam_tts_default_language: str = "en-IN"       # when the detected language has no voice
    ai_voice_barge_in: bool = True                   # user speaking stops the AI's audio

    # ── Frontend (optional) ────────────────────────────────────
    # If this folder exists (npm run build), the backend also serves the React
    # app at "/", so a single tunnel URL hosts both UI and API (no CORS needed).
    frontend_dist_path: str = "../frontend/dist"

    # ── Server ─────────────────────────────────────────────────
    host: str = "127.0.0.1"
    port: int = 8000
    dev_reload: bool = False

    # ── App Meta ───────────────────────────────────────────────
    app_name: str = "SHEM Backend"
    app_version: str = "0.2.0"

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.sqlite_path}"

    @field_validator("mqtt_port", "port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"port must be 1–65535, got {v}")
        return v

    @field_validator("command_expiry_seconds")
    @classmethod
    def validate_expiry(cls, v: int) -> int:
        if v < 5:
            raise ValueError("command_expiry_seconds must be at least 5")
        return v

    @field_validator("raw_telemetry_retention_days")
    @classmethod
    def validate_retention(cls, v: int) -> int:
        if v < 2:
            raise ValueError("raw_telemetry_retention_days must be at least 2")
        return v

    @field_validator("ai_primary_provider")
    @classmethod
    def validate_ai_provider(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("gemini", "groq"):
            raise ValueError("ai_primary_provider must be 'gemini' or 'groq'")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        ZoneInfo(v)  # raises if unknown (on Windows requires the 'tzdata' package)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
