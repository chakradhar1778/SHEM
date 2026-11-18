"""
SHEM Backend — SQLite Database Connection
Provides the SQLAlchemy engine, session factory, and Base for ORM models.
"""

from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

def _resolve_engine() -> tuple[object, bool]:
    """
    Returns (engine, is_turso).
    Supports Turso (libSQL) via sqlalchemy-libsql or standard local SQLite.
    """
    turso_url = (settings.turso_database_url or "").strip()
    turso_token = (settings.turso_auth_token or "").strip()
    db_url = (settings.database_url or "").strip()

    if db_url and ("libsql" in db_url):
        turso_url = db_url

    if turso_url:
        # Turso / libSQL URL normalization
        # Accepts: libsql://[db-name]-[org].turso.io, https://..., or sqlite+libsql://...
        url = turso_url
        if url.startswith("libsql://"):
            url = "sqlite+" + url
        elif url.startswith("https://"):
            url = "sqlite+libsql://" + url.removeprefix("https://")
        elif not url.startswith("sqlite+libsql://"):
            url = f"sqlite+libsql://{url}"

        connect_args: dict[str, object] = {}
        if turso_token:
            connect_args["auth_token"] = turso_token
            if "authToken=" not in url:
                delimiter = "&" if "?" in url else "?"
                url = f"{url}{delimiter}authToken={turso_token}"

        if "secure=" not in url:
            delimiter = "&" if "?" in url else "?"
            url = f"{url}{delimiter}secure=true"

        sanitized_url = url.split("authToken=")[0].rstrip("&?")
        logger.info("Connecting to Turso / libSQL: %s", sanitized_url)
        return (
            create_engine(
                url,
                connect_args=connect_args,
                echo=False,
            ),
            True,
        )

    # Standard SQLite
    logger.info("Connecting to SQLite: %s", settings.sqlite_url)
    return (
        create_engine(
            settings.sqlite_url,
            connect_args={"check_same_thread": False, "timeout": 15},
            echo=False,
        ),
        False,
    )


engine, is_turso = _resolve_engine()


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if is_turso:
        # Remote libSQL manages WAL and page allocation server-side
        return
    try:
        cursor = dbapi_connection.cursor()
        # Must run before the first table is created to take effect; lets the
        # retention job hand freed pages back to the OS (PRAGMA incremental_vacuum).
        cursor.execute("PRAGMA auto_vacuum=INCREMENTAL")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, far fewer fsyncs at 0.5 msg/s
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception as exc:
        logger.debug("SQLite pragma setting skipped or unsupported: %s", exc)


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import app.models.db_models  # noqa: F401  (register models)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    logger.info("Database tables created / verified.")


def _add_missing_columns() -> None:
    """
    Minimal forward-only migration: create_all() never alters existing tables,
    so add any model column that is missing from an existing SQLite table.
    New columns must be nullable or have a scalar default (true for all of ours).
    """
    from sqlalchemy.schema import CreateColumn

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = str(CreateColumn(column).compile(dialect=engine.dialect))
                default = column.default.arg if column.default is not None and column.default.is_scalar else None
                if default is not None:
                    literal = int(default) if isinstance(default, bool) else default
                    ddl += f" DEFAULT {literal!r}" if isinstance(literal, str) else f" DEFAULT {literal}"
                conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}')
                logger.warning("Schema upgrade: added column %s.%s", table.name, column.name)


def check_db() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        return False


def incremental_vacuum() -> None:
    """Return free pages to the OS after large deletes (no-op if auto_vacuum is off or using Turso)."""
    if is_turso:
        return
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA incremental_vacuum")
            conn.commit()
    except Exception as exc:  # pragma: no cover
        logger.warning("incremental_vacuum failed: %s", exc)
