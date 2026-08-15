"""T-01 / T-02: seed loading row-count parity with source jsonl logs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models import Hypothesis, MCPUsage

# NOTE: conftest.py sets DATABASE_URL=sqlite:///:memory: and loads real logs
# into the seeded_db fixture; we re-derive expected counts here.

USAGE_LOG = (
    Path(__file__).resolve().parent.parent.parent.parent / "meta_harness" / "mcp_usage_report.jsonl"
)
HYP_LOG = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "meta_harness"
    / "experience"
    / "hypotheses.jsonl"
)


def _count_lines(path: Path) -> int:
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def test_seed_loads_usage_rows(seeded_db):
    """T-01: mcp_usage rows == jsonl non-empty lines (52)."""
    count = seeded_db.query(MCPUsage).count()
    assert count == _count_lines(USAGE_LOG)
    assert count > 0


def test_seed_loads_hypothesis_rows(seeded_db):
    """T-02: hypotheses rows == jsonl non-empty lines (43)."""
    count = seeded_db.query(Hypothesis).count()
    assert count == _count_lines(HYP_LOG)
    assert count > 0


def test_seed_usage_fields_populated(seeded_db):
    """Sanity: every usage row has server/tool/duration/status."""
    rows = seeded_db.query(MCPUsage).all()
    for r in rows:
        assert r.server and r.tool
        assert r.duration_ms >= 0
        assert r.status in ("ok", "error")
