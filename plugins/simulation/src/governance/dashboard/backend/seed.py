"""ETL: load mcp_usage_report.jsonl + hypotheses.jsonl into the database.

Usage:
    python seed.py [--usage PATH] [--hyp PATH] [--db-url URL]

Idempotent: clears both tables then reloads (fresh snapshot semantics).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import Base, SessionLocal, engine, init_db  # noqa: E402
from app.models import Hypothesis, MCPUsage  # noqa: E402

GOV_DIR = Path(__file__).resolve().parent.parent.parent  # governance/
DEFAULT_USAGE = GOV_DIR / "meta_harness" / "mcp_usage_report.jsonl"
DEFAULT_HYP = GOV_DIR / "meta_harness" / "experience" / "hypotheses.jsonl"


def _parse_ts(raw: str) -> datetime:
    """Handle both ISO-8601 (usage) and compact 'YYYYMMDD_HHMMSS' (hypotheses)."""
    raw = raw.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.strptime(raw, "%Y%m%d_%H%M%S")


def _extract_score(score) -> float | None:
    """hypotheses score is a dict like {'winrate': 1.0, 'steps': 214}; use winrate."""
    if score is None:
        return None
    if isinstance(score, dict):
        return float(score.get("winrate", 0.0))
    try:
        return float(score)
    except (TypeError, ValueError):
        return None


def load_usage(path: Path) -> list[MCPUsage]:
    rows: list[MCPUsage] = []
    if not path.exists():
        print(f"[seed] WARN: usage file not found: {path}")
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append(
                MCPUsage(
                    ts=_parse_ts(r["ts"]),
                    server=r["server"],
                    tool=r["tool"],
                    args=json.dumps(r.get("args"), ensure_ascii=False)
                    if r.get("args")
                    else None,
                    duration_ms=float(r.get("duration_ms", 0.0)),
                    status=r.get("status", "ok"),
                    error=r.get("error"),
                )
            )
    return rows


def load_hypotheses(path: Path) -> list[Hypothesis]:
    rows: list[Hypothesis] = []
    if not path.exists():
        print(f"[seed] WARN: hypotheses file not found: {path}")
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows.append(
                Hypothesis(
                    ts=_parse_ts(r["ts"]),
                    variant_id=r.get("variant_id") or r.get("id") or "unknown",
                    layer=r.get("layer"),
                    hypothesis=r.get("hypothesis"),
                    outcome=r.get("outcome") or r.get("status"),
                    score=_extract_score(r.get("score")),
                    confidence=(
                        float(r["confidence"])
                        if r.get("confidence") is not None
                        else None
                    ),
                )
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dashboard DB from jsonl logs")
    parser.add_argument("--usage", default=str(DEFAULT_USAGE))
    parser.add_argument("--hyp", default=str(DEFAULT_HYP))
    parser.add_argument("--db-url", default=None)
    args = parser.parse_args()

    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    init_db()
    usage_rows = load_usage(Path(args.usage))
    hyp_rows = load_hypotheses(Path(args.hyp))

    with SessionLocal() as db:
        db.query(MCPUsage).delete()
        db.query(Hypothesis).delete()
        db.add_all(usage_rows)
        db.add_all(hyp_rows)
        db.commit()
        print(f"[seed] usage={len(usage_rows)} hypotheses={len(hyp_rows)} OK")


if __name__ == "__main__":
    main()
