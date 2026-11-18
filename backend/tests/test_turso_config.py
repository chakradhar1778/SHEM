import pytest
from app.config import Settings
from app.database import _resolve_engine, build_turso_url


def test_sqlite_default_resolution(monkeypatch):
    monkeypatch.setattr("app.database.settings", Settings(turso_database_url="", database_url=""))
    engine, is_turso = _resolve_engine()
    assert not is_turso
    assert "sqlite" in str(engine.url)


@pytest.mark.parametrize("raw", [
    "libsql://shem-db-me.turso.io",
    "https://shem-db-me.turso.io",
    "shem-db-me.turso.io",
    "sqlite+libsql://shem-db-me.turso.io?secure=true",
])
def test_build_turso_url_keeps_token_out_of_url(raw):
    """A token in the URL query makes libsql request /v3/pipeline?authToken=... -> Turso 404."""
    url, args = build_turso_url(raw, "tok-123")
    assert url == "sqlite+libsql://shem-db-me.turso.io?secure=true"
    assert args == {"auth_token": "tok-123"}


def test_build_turso_url_moves_pasted_token_to_connect_args():
    url, args = build_turso_url("libsql://shem-db-me.turso.io?authToken=pasted", "")
    assert url == "sqlite+libsql://shem-db-me.turso.io?secure=true"
    assert args == {"auth_token": "pasted"}


# ── Connection-pool hardening (exercised on plain SQLite; libsql isn't installable on Windows) ──

def _hardened_sqlite_engine(tmp_path, rollback=None):
    """SQLite engine with the Turso hardening; `rollback(real, dbapi_conn)` replaces ROLLBACK."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import QueuePool
    from app.database import _harden_turso_engine

    eng = create_engine(f"sqlite:///{tmp_path / 't.db'}", poolclass=QueuePool,
                        connect_args={"check_same_thread": False})
    with eng.connect() as c:                    # first connect runs dialect initialisation
        c.execute(text("SELECT 1"))
    if rollback is not None:
        real = eng.dialect.do_rollback
        eng.dialect.do_rollback = lambda conn: rollback(real, conn)
    _harden_turso_engine(eng)
    return eng


NO_TXN = ('Hrana: `stream error: `Error { message: "SQLite error: cannot rollback - '
          'no transaction is active", code: "SQLITE_UNKNOWN" }``')


def test_rollback_on_server_ended_transaction_is_swallowed_and_connection_replaced(tmp_path):
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    state = {"fail": True}

    def rollback(real, conn):
        real(conn)
        if state.pop("fail", False):
            raise ValueError(NO_TXN)

    eng = _hardened_sqlite_engine(tmp_path, rollback)
    with Session(eng) as s:
        first = s.connection().connection.dbapi_connection
        s.execute(text("SELECT 1"))
        s.rollback()                                   # must not raise
    with Session(eng) as s:
        second = s.connection().connection.dbapi_connection
        assert s.execute(text("SELECT 1")).scalar() == 1
    assert second is not first                         # broken connection was replaced


def test_other_rollback_errors_still_raise(tmp_path):
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    def rollback(real, conn):
        raise RuntimeError("disk on fire")

    eng = _hardened_sqlite_engine(tmp_path, rollback)
    s = Session(eng)
    s.execute(text("SELECT 1"))
    with pytest.raises(RuntimeError, match="disk on fire"):
        s.rollback()


def test_stream_errors_invalidate_the_connection(tmp_path):
    from sqlalchemy import event, text
    from sqlalchemy.orm import Session

    eng = _hardened_sqlite_engine(tmp_path)

    @event.listens_for(eng, "before_cursor_execute")
    def boom(conn, cursor, statement, *a):
        if "boom" in statement:
            raise ValueError("Hrana: `stream error: interactive transaction was rolled back because "
                             "the stream was idle for too long")

    with Session(eng) as s:
        first = s.connection().connection.dbapi_connection
        with pytest.raises(Exception):
            s.execute(text("SELECT 'boom'"))
    with Session(eng) as s:
        assert s.connection().connection.dbapi_connection is not first


def test_mqtt_dispatch_survives_driver_panic():
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch
    from app.mqtt.client import MQTTClientManager

    class PanicException(BaseException):     # stand-in for pyo3_runtime.PanicException
        pass

    with patch("app.mqtt.client.paho.Client"):
        mgr = MQTTClientManager()
    panic = MagicMock(side_effect=PanicException("called `Option::unwrap()` on a `None` value"))
    mgr.register_handlers(on_telemetry=panic, on_status=MagicMock(), on_relay_state=MagicMock(), on_relay_ack=MagicMock())
    mgr._on_message(mgr._client, None, SimpleNamespace(topic="shem/device/001/telemetry", payload=b"{}", retain=0))
    panic.assert_called_once()
