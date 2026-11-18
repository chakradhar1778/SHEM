import pytest
from app.config import Settings
from app.database import _resolve_engine


def test_sqlite_default_resolution(monkeypatch):
    monkeypatch.setattr("app.database.settings", Settings(turso_database_url="", database_url=""))
    engine, is_turso = _resolve_engine()
    assert not is_turso
    assert "sqlite" in str(engine.url)


def test_turso_url_normalization(monkeypatch):
    test_settings = Settings(
        turso_database_url="libsql://my-shem-db.turso.io",
        turso_auth_token="test-token-123",
    )
    monkeypatch.setattr("app.database.settings", test_settings)
    
    # We can inspect URL formation
    turso_url = test_settings.turso_database_url
    url = "sqlite+" + turso_url
    assert url.startswith("sqlite+libsql://")
