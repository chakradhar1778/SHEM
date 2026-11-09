"""
SHEM Backend — Paho MQTT Client Manager

Responsibilities:
  - Connect to EMQX Cloud over MQTT/TLS with CA validation.
  - Subscribe to all 4 inbound device topics on connect.
  - Dispatch received messages to topic handlers.
  - Auto-reconnect with exponential back-off.
  - Expose connection state (connected, last_connect_at, disconnect_reason).
  - Run Paho's network loop on its own thread so FastAPI stays non-blocking.

Security rules:
  - TLS with trusted CA — no insecure mode.
  - Separate credentials from the ESP32 (shem_backend vs shem_esp32).
  - Client ID is unique per run to avoid accidental session takeover.
"""

from __future__ import annotations

import logging
import os
import ssl
import uuid
from datetime import datetime
from typing import Callable, Optional

import paho.mqtt.client as paho

from app.config import get_settings
from app.utils.timestamps import utcnow

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Topic constants ────────────────────────────────────────────────────────────
def _topics(device_id: str) -> dict[str, str]:
    prefix = f"shem/device/{device_id}"
    return {
        "telemetry":    f"{prefix}/telemetry",
        "status":       f"{prefix}/status",
        "relay_state":  f"{prefix}/relay/1/state",
        "relay_ack":    f"{prefix}/relay/1/ack",
        "relay_cmd":    f"{prefix}/relay/1/command",  # publish-only for backend
    }


class MQTTClientManager:
    """
    Manages the lifecycle of the Paho MQTT client for the SHEM backend.
    One instance lives in app.state for the duration of the server process.
    """

    def __init__(self) -> None:
        self.connected: bool = False
        self.last_connect_at: Optional[datetime] = None
        self.disconnect_reason: Optional[str] = None

        self._topics = _topics(settings.device_id)
        # Message dispatch table: topic → handler callable
        # Populated by register_handlers() called from main.py lifespan.
        self._handlers: dict[str, Callable[[bytes, bool], None]] = {}
        self._tls_error: Optional[str] = None
        # Topics the broker refused (e.g. missing EMQX authorization rule); empty when all granted
        self.denied_subscriptions: list[str] = []
        # Called (on the paho thread) with True/False whenever the broker
        # connection goes up or down, so clients are told immediately.
        self.on_state_change: Optional[Callable[[bool], None]] = None
        self._pending_sub_topics: list[str] = []

        # Unique client ID per process run — prevents accidental session takeover
        short_id = uuid.uuid4().hex[:8].upper()
        self._client_id = f"SHEM_BACKEND_{short_id}"

        self._client = self._build_client()

    # ── Public API ─────────────────────────────────────────────────────────────

    def register_handlers(
        self,
        on_telemetry: Callable[[bytes, bool], None],
        on_status: Callable[[bytes, bool], None],
        on_relay_state: Callable[[bytes, bool], None],
        on_relay_ack: Callable[[bytes, bool], None],
    ) -> None:
        """
        Wire topic → handler after the client is built but before start().
        Called from main.py lifespan so services (and their DB sessions) are ready.
        """
        self._handlers = {
            self._topics["telemetry"]:   on_telemetry,
            self._topics["status"]:      on_status,
            self._topics["relay_state"]: on_relay_state,
            self._topics["relay_ack"]:   on_relay_ack,
        }
        logger.info("MQTT handlers registered for device %s", settings.device_id)

    def start(self) -> None:
        """Connect to the broker and start the background network loop."""
        if self._tls_error:
            # Run without MQTT rather than crash: REST data (household, bills…)
            # stays available and /api/health reports mqttConnected=false.
            self.disconnect_reason = self._tls_error
            logger.error("MQTT disabled: %s", self._tls_error)
            return
        host = settings.mqtt_host
        port = settings.mqtt_port
        logger.info(
            "MQTT connecting → %s:%s as client '%s'", host, port, self._client_id
        )
        try:
            self._client.connect_async(host, port, keepalive=60)
            self._client.loop_start()
        except Exception as exc:
            logger.error("MQTT initial connect failed: %s", exc)

    def stop(self) -> None:
        """Gracefully disconnect and stop the network loop."""
        logger.info("MQTT disconnecting…")
        try:
            self._client.disconnect()
        except Exception:
            pass
        self._client.loop_stop()
        self.connected = False
        logger.info("MQTT stopped.")

    def publish(
        self,
        topic: str,
        payload: str,
        qos: int = 1,
        retain: bool = False,
    ) -> bool:
        """
        Publish a message to the broker.
        Returns True if the message was queued successfully.

        IMPORTANT: relay commands must always be called with retain=False.
        """
        if not self.connected:
            logger.warning("MQTT publish skipped — not connected. Topic: %s", topic)
            return False
        result = self._client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc != paho.MQTT_ERR_SUCCESS:
            logger.error(
                "MQTT publish failed rc=%s topic=%s", result.rc, topic
            )
            return False
        return True

    @property
    def relay_command_topic(self) -> str:
        return self._topics["relay_cmd"]

    # ── Internal ───────────────────────────────────────────────────────────────

    def _build_client(self) -> paho.Client:
        client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id=self._client_id,
            protocol=paho.MQTTv311,
        )

        # Credentials
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

        # TLS — validate CA, no insecure shortcuts
        self._configure_tls(client)

        # Callbacks
        client.on_connect    = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message    = self._on_message
        client.on_subscribe  = self._on_subscribe

        # Reconnect delay: 1 s initially, up to 60 s
        client.reconnect_delay_set(min_delay=1, max_delay=60)

        return client

    def _configure_tls(self, client: paho.Client) -> None:
        ca_path = os.path.abspath(settings.mqtt_ca_cert_path)
        if not os.path.isfile(ca_path):
            # Do not crash the API: start() will report MQTT as disabled.
            self._tls_error = (
                f"MQTT CA certificate not found at {ca_path}. Download it from the "
                "EMQX Cloud deployment page and set MQTT_CA_CERT_PATH."
            )
            return
        client.tls_set(
            ca_certs=ca_path,
            certfile=None,
            keyfile=None,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS_CLIENT,
        )
        logger.info("MQTT TLS configured with CA: %s", ca_path)

    def _notify_state(self, connected: bool) -> None:
        if self.on_state_change is None:
            return
        try:
            self.on_state_change(connected)
        except Exception:
            logger.exception("MQTT state-change callback failed")

    # ── Paho Callbacks (run on Paho's internal thread) ─────────────────────────

    def _on_connect(
        self,
        client: paho.Client,
        userdata,
        flags,
        reason_code,
        properties=None,
    ) -> None:
        if reason_code.is_failure:
            self.connected = False
            self.disconnect_reason = str(reason_code)
            logger.error("MQTT connect refused: %s", reason_code)
            return

        self.connected = True
        self.last_connect_at = utcnow()
        self.disconnect_reason = None
        logger.info("MQTT connected to %s:%s", settings.mqtt_host, settings.mqtt_port)
        self._notify_state(True)

        # Subscribe to all 4 inbound topics at QoS 1
        subs = [
            (self._topics["telemetry"],   1),
            (self._topics["status"],      1),
            (self._topics["relay_state"], 1),
            (self._topics["relay_ack"],   1),
        ]
        self._pending_sub_topics = [t for t, _ in subs]
        client.subscribe(subs)
        logger.info("MQTT subscribing to %d topics", len(subs))

    def _on_disconnect(
        self,
        client: paho.Client,
        userdata,
        disconnect_flags,
        reason_code,
        properties=None,
    ) -> None:
        self.connected = False
        self.disconnect_reason = str(reason_code)
        self._notify_state(False)
        if reason_code.is_failure:
            logger.warning(
                "MQTT disconnected unexpectedly: %s — will auto-reconnect", reason_code
            )
        else:
            logger.info("MQTT disconnected cleanly.")

    def _on_subscribe(
        self,
        client: paho.Client,
        userdata,
        mid,
        reason_code_list,
        properties=None,
    ) -> None:
        denied = [
            topic for topic, rc in zip(self._pending_sub_topics, reason_code_list)
            if getattr(rc, "is_failure", False)
        ]
        self.denied_subscriptions = denied
        if denied:
            logger.error("MQTT broker DENIED subscriptions: %s — check the EMQX authorization rules", denied)
        else:
            logger.info("MQTT subscriptions granted: %s", [str(rc) for rc in reason_code_list])

    def _on_message(
        self,
        client: paho.Client,
        userdata,
        msg: paho.MQTTMessage,
    ) -> None:
        """
        Dispatches every incoming message to the registered topic handler.
        Runs on Paho's internal thread — handlers must be thread-safe.
        """
        topic = msg.topic
        handler = self._handlers.get(topic)

        if handler is None:
            logger.warning("MQTT message on unregistered topic: %s", topic)
            return

        logger.debug("MQTT ← %s  (%d bytes)", topic, len(msg.payload))
        try:
            handler(msg.payload, bool(msg.retain))
        except Exception as exc:
            logger.exception(
                "MQTT handler error for topic %s: %s", topic, exc
            )

