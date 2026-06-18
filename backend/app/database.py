"""
Database session management.

Uses synchronous SQLAlchemy 1.4 with SQLite.
For a production deployment, swap the DATABASE_URL env var to a PostgreSQL URL
and the engine configuration handles the rest.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.db_models import Base

# Use synchronous SQLite URL (strip async prefix if present)
_sync_url = settings.database_url.replace("+aiosqlite", "")

engine = create_engine(
    _sync_url,
    connect_args={"check_same_thread": False},  # needed for SQLite in a multi-threaded server
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables if they don't exist. Called once on startup."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session and closes it afterward."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager version for use outside of FastAPI route handlers."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
