"""Forward-only column migration and SPA hosting."""

from __future__ import annotations

import sqlite3

from app.config import get_settings
from app.database import _add_missing_columns, engine


def test_missing_columns_are_added(client):
    path = get_settings().sqlite_path
    con = sqlite3.connect(path)
    con.execute("ALTER TABLE household_config DROP COLUMN is_configured")
    con.commit()
    con.close()
    engine.dispose()
    _add_missing_columns()
    con = sqlite3.connect(path)
    cols = {r[1]: r for r in con.execute("PRAGMA table_info(household_config)")}
    con.close()
    assert "is_configured" in cols and cols["is_configured"][4] == "0"   # default false


def test_unknown_api_path_is_404_not_spa(client):
    assert client.get("/api/does-not-exist", headers={"X-API-Key": "test-key"}).status_code == 404
