"""Database engine and session setup.

Kept separate from the table definitions so tests can point at a temporary file without importing
anything that reads the real configuration.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import DATABASE_URL
from .models import Base


def create_db_engine(url: str = DATABASE_URL) -> Engine:
    """Create the engine and apply the two SQLite settings this pipeline depends on."""
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def apply_sqlite_pragmas(dbapi_connection, connection_record) -> None:
        """Enable WAL and a busy timeout on every new connection.

        WAL lets a reader run while the recompute holds its write transaction, which matters
        because the frontend refetches the moment the ingestion mutation resolves; the timeout
        makes a reader wait rather than fail immediately if it still collides.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Build the session factory for this engine."""
    return sessionmaker(bind=engine, future=True, expire_on_commit=False)


def create_all(engine: Engine) -> None:
    """Create any missing tables. Safe to call on every start."""
    Base.metadata.create_all(engine)
