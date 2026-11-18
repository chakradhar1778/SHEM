"""
SHEM Backend — SQLite Database Connection
Provides the SQLAlchemy engine, session factory, and Base for ORM models.
"""

from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import QueuePool
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

def build_turso_url(raw_url: str, token: str) -> tuple[str, dict[str, object]]:
    """
    Normalise a Turso URL for sqlalchemy-libsql. Returns (url, connect_args).

    Accepts libsql://<db>-<org>.turso.io, https://..., sqlite+libsql://... or a
    bare host. The auth token must go ONLY in connect_args["auth_token"]: the
    dialect copies URL query params into the HTTP URL it hands to libsql, which
    then requests "/v3/pipeline?authToken=..." and Turso answers 404
    "route not found". A token pasted into the URL is moved to connect_args.
    """
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    url = raw_url.strip()
    for prefix in ("sqlite+libsql://", "libsql://", "https://", "wss://", "http://", "ws://"):
        if url.startswith(prefix):
            url = url.removeprefix(prefix)
            break
    parts = urlsplit("sqlite+libsql://" + url)
    query: dict[str, str] = {}
    for key, value in parse_qsl(parts.query):
        if key.lower() in ("authtoken", "auth_token"):
            token = token or value
        else:
            query[key] = value
    query.setdefault("secure", "true")

    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    return clean, ({"auth_token": token} if token else {})


# Errors after which a libSQL connection must not be reused (Hrana stream gone,
# server-side rollback, or the Rust driver panicking on a dead connection).
_TURSO_BROKEN_MARKERS = (
    "stream error",
    "stream was idle",
    "stream not found",
    "no transaction is active",
    "connection already",
    "unwrap()",
    "baton",
)


def _is_broken_turso_error(exc: BaseException) -> bool:
    text_ = str(exc).lower()
    return type(exc).__name__ == "PanicException" or any(m in text_ for m in _TURSO_BROKEN_MARKERS)


def _harden_turso_engine(eng) -> None:
    """
    * ROLLBACK when the server already ended the transaction (idle-stream
      timeout) raises "cannot rollback - no transaction is active". Treat the
      rollback as done (so the original error surfaces, not this one) and mark
      the connection; the pool replaces it at its next checkout.
    * Any stream/driver failure during a statement invalidates the connection
      at once, so the next request gets a fresh one.
    """
    from sqlalchemy import exc as sa_exc

    broken: set[int] = set()          # id() of DBAPI connections known to be dead
    original_rollback = eng.dialect.do_rollback

    def do_rollback(dbapi_connection):
        try:
            original_rollback(dbapi_connection)
        except BaseException as exc:  # pyo3 PanicException derives from BaseException
            if isinstance(exc, (KeyboardInterrupt, SystemExit)) or not _is_broken_turso_error(exc):
                raise
            # SQLAlchemy may pass a pool proxy here; key on the raw DBAPI connection.
            broken.add(id(getattr(dbapi_connection, "dbapi_connection", dbapi_connection)))
            logger.warning("Turso rollback skipped (%s); connection will be replaced", exc)

    eng.dialect.do_rollback = do_rollback

    @event.listens_for(eng, "checkout")
    def _replace_broken(dbapi_connection, connection_record, connection_proxy):
        if id(dbapi_connection) in broken:
            broken.discard(id(dbapi_connection))
            # Documented pool hook: discards this connection and retries with a new one.
            raise sa_exc.DisconnectionError("Turso connection was left broken; reconnecting")

    @event.listens_for(eng, "close")
    def _forget_closed(dbapi_connection, connection_record):
        broken.discard(id(dbapi_connection))

    @event.listens_for(eng, "handle_error")
    def _invalidate_broken(ctx):
        if _is_broken_turso_error(ctx.original_exception):
            ctx.is_disconnect = True


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
        url, connect_args = build_turso_url(turso_url, turso_token)
        logger.info("Connecting to Turso / libSQL: %s", url)
        turso_engine = create_engine(
            url,
            # The pysqlite dialect treats a URL without a file path as ":memory:"
            # and picks SingletonThreadPool: one connection per thread, shared by
            # every session on that thread, and closed under other threads once
            # more than 5 threads exist. On Turso that caused "detached
            # connection fairy" errors, Rust panics on closed connections and
            # transactions cut short by another session's COMMIT/ROLLBACK.
            # A QueuePool hands each session its own connection (libsql
            # connections are Send + Sync; check_same_thread is not enforced).
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=300,           # refresh long-lived Hrana streams
            connect_args={**connect_args, "check_same_thread": False},
            echo=False,
        )
        _harden_turso_engine(turso_engine)
        return turso_engine, True

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
