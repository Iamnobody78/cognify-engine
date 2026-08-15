"""Database engine/session factory.

Supports both SQLite (dev/CI default) and PostgreSQL (production via
DATABASE_URL). Dialect-compatible schema keeps the ORM portable.
"""
from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

_DEFAULT_URL = "sqlite:///./dashboard.db"


def _build_engine_url() -> str:
    """Prefer DATABASE_URL (PostgreSQL in production), fall back to SQLite."""
    return os.environ.get("DATABASE_URL", _DEFAULT_URL)


_url = _build_engine_url()
_connect_args = {}
if _url.startswith("sqlite"):
    # share one in-memory connection across threads (needed for :memory: tests)
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    _url,
    connect_args=_connect_args,
    poolclass=StaticPool if _url == "sqlite:///:memory:" else None,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency: yield a session, close on teardown."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (idempotent)."""
    from . import models  # noqa: F401  ensure models are registered

    Base.metadata.create_all(bind=engine)
