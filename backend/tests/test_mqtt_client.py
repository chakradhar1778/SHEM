"""MQTTClientManager unit tests — paho is mocked; nothing connects to EMQX."""

from __future__ import annotations

import ssl
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import paho.mqtt.client as paho
import pytest
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from app.config import get_settings
from app.mqtt.client import MQTTClientManager

TOPICS = [
    "shem/device/001/telemetry",
    "shem/device/001/status",
    "shem/device/001/relay/1/state",
    "shem/device/001/relay/1/ack",
]


def rc(packet: int, name: str) -> ReasonCode:
    return ReasonCode(packet, aName=name)


CONNECT_OK = rc(PacketTypes.CONNACK, "Success")
CONNECT_REFUSED = rc(PacketTypes.CONNACK, "Not authorized")
DISCONNECT_UNEXPECTED = rc(PacketTypes.DISCONNECT, "Unspecified error")


@pytest.fixture
def manager():
    """Real manager whose underlying paho client is a MagicMock."""
    with patch("app.mqtt.client.paho.Client") as client_cls:
        mgr = MQTTClientManager()
    mgr.paho_cls = client_cls
    return mgr


def test_client_is_built_securely(manager):
    settings = get_settings()
    kwargs = manager.paho_cls.call_args.kwargs
    assert kwargs["protocol"] == paho.MQTTv311
    assert kwargs["client_id"].startswith("SHEM_BACKEND_")
    client = manager._client
    client.username_pw_set.assert_called_once_with(settings.mqtt_username, settings.mqtt_password)
    tls = client.tls_set.call_args.kwargs
    assert tls["cert_reqs"] == ssl.CERT_REQUIRED          # certificate validation is mandatory
    assert tls["ca_certs"].endswith(settings.mqtt_ca_cert_path.split("/")[-1])
    client.tls_insecure_set.assert_not_called()
    client.reconnect_delay_set.assert_called_once_with(min_delay=1, max_delay=60)


def test_client_ids_are_unique_per_instance():
    with patch("app.mqtt.client.paho.Client"):
        a, b = MQTTClientManager(), MQTTClientManager()
    assert a._client_id != b._client_id


def test_missing_ca_certificate_disables_mqtt_without_crashing(monkeypatch):
    monkeypatch.setattr(get_settings(), "mqtt_ca_cert_path", "./certs/does-not-exist.crt")
    with patch("app.mqtt.client.paho.Client"):
        mgr = MQTTClientManager()          # must not raise
    mgr.start()
    mgr._client.connect_async.assert_not_called()
    assert mgr.connected is False and "CA certificate not found" in mgr.disconnect_reason


def test_start_connects_async_and_survives_connect_errors(manager):
    settings = get_settings()
    manager.start()
    manager._client.connect_async.assert_called_once_with(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    manager._client.loop_start.assert_called_once()

    manager._client.connect_async.side_effect = OSError("DNS failure")
    manager.start()                         # logged, not raised


def test_on_connect_subscribes_to_all_four_topics_qos1(manager):
    manager._on_connect(manager._client, None, {}, CONNECT_OK)
    assert manager.connected is True and manager.last_connect_at is not None
    manager._client.subscribe.assert_called_once_with([(t, 1) for t in TOPICS])


def test_refused_connection_does_not_subscribe(manager):
    manager._on_connect(manager._client, None, {}, CONNECT_REFUSED)
    assert manager.connected is False
    assert "Not authorized" in manager.disconnect_reason
    manager._client.subscribe.assert_not_called()


def test_reconnect_resubscribes(manager):
    manager._on_connect(manager._client, None, {}, CONNECT_OK)
    manager._on_disconnect(manager._client, None, None, DISCONNECT_UNEXPECTED)
    assert manager.connected is False and manager.disconnect_reason
    manager._on_connect(manager._client, None, {}, CONNECT_OK)
    assert manager.connected is True and manager.disconnect_reason is None
    assert manager._client.subscribe.call_count == 2


def test_denied_subscriptions_are_reported(manager):
    manager._on_connect(manager._client, None, {}, CONNECT_OK)
    granted = rc(PacketTypes.SUBACK, "Granted QoS 1")
    denied = rc(PacketTypes.SUBACK, "Not authorized")
    manager._on_subscribe(manager._client, None, 1, [granted, granted, denied, granted])
    assert manager.denied_subscriptions == ["shem/device/001/relay/1/state"]
    manager._on_subscribe(manager._client, None, 2, [granted] * 4)
    assert manager.denied_subscriptions == []


def test_messages_are_dispatched_with_retain_flag(manager):
    handlers = {k: MagicMock() for k in ("on_telemetry", "on_status", "on_relay_state", "on_relay_ack")}
    manager.register_handlers(**handlers)
    for topic, name in zip(TOPICS, handlers):
        manager._on_message(manager._client, None, SimpleNamespace(topic=topic, payload=b"{}", retain=1))
        handlers[name].assert_called_once_with(b"{}", True)


def test_unknown_topic_and_handler_errors_are_contained(manager):
    boom = MagicMock(side_effect=RuntimeError("bad payload"))
    manager.register_handlers(on_telemetry=boom, on_status=MagicMock(), on_relay_state=MagicMock(), on_relay_ack=MagicMock())
    manager._on_message(manager._client, None, SimpleNamespace(topic="shem/device/999/telemetry", payload=b"x", retain=0))
    manager._on_message(manager._client, None, SimpleNamespace(topic=TOPICS[0], payload=b"x", retain=0))  # must not raise
    boom.assert_called_once()


def test_publish_rules(manager):
    assert manager.publish("t", "p") is False                 # not connected → refused, nothing queued
    manager._client.publish.assert_not_called()

    manager._on_connect(manager._client, None, {}, CONNECT_OK)
    manager._client.publish.return_value = SimpleNamespace(rc=paho.MQTT_ERR_SUCCESS)
    assert manager.publish("shem/device/001/relay/1/command", "{}", qos=1, retain=False) is True
    manager._client.publish.assert_called_with("shem/device/001/relay/1/command", "{}", qos=1, retain=False)

    manager._client.publish.return_value = SimpleNamespace(rc=paho.MQTT_ERR_NO_CONN)
    assert manager.publish("t", "p") is False


def test_stop_is_safe(manager):
    manager._on_connect(manager._client, None, {}, CONNECT_OK)
    manager._client.disconnect.side_effect = OSError("already closed")
    manager.stop()
    manager._client.loop_stop.assert_called_once()
    assert manager.connected is False


def test_state_change_hook_fires_on_connect_and_disconnect(manager):
    seen = []
    manager.on_state_change = seen.append
    manager._on_connect(manager._client, None, {}, CONNECT_OK)
    manager._on_disconnect(manager._client, None, None, DISCONNECT_UNEXPECTED)
    manager._on_connect(manager._client, None, {}, CONNECT_REFUSED)   # refused → no "up" event
    assert seen == [True, False]


def test_state_change_hook_errors_are_contained(manager):
    manager.on_state_change = MagicMock(side_effect=RuntimeError("ws down"))
    manager._on_connect(manager._client, None, {}, CONNECT_OK)        # must not raise
    assert manager.connected is True
