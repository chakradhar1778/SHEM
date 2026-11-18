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
