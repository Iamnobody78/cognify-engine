"""Shared fixtures: in-memory SQLite DB seeded from the real jsonl logs."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# MUST be set before importing app modules: in-memory SQLite, shared pool
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from seed import load_hypotheses, load_usage  # noqa: E402

GOV_DIR = BACKEND_DIR.parent.parent  # governance/
USAGE_LOG = GOV_DIR / "meta_harness" / "mcp_usage_report.jsonl"
HYP_LOG = GOV_DIR / "meta_harness" / "experience" / "hypotheses.jsonl"


@pytest.fixture()
def seeded_db():
    """Fresh in-memory DB per test, loaded from real logs."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add_all(load_usage(USAGE_LOG))
    db.add_all(load_hypotheses(HYP_LOG))
    db.commit()
    yield db
    db.close()


@pytest.fixture()
def client():
    """TestClient backed by a fresh seeded in-memory DB."""
    from fastapi.testclient import TestClient

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add_all(load_usage(USAGE_LOG))
    db.add_all(load_hypotheses(HYP_LOG))
    db.commit()
    db.close()

    with TestClient(app) as c:
        yield c
