"""Usage endpoints: summary, latency outliers, timeline buckets."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MCPUsage
from ..schemas import (
    LatencyOutlier,
    TimelineBucket,
    ToolStat,
    UsageSummary,
)

router = APIRouter(prefix="/api/usage", tags=["usage"])


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(round(0.95 * len(s))) - 1)
    return s[idx]


@router.get("/summary", response_model=UsageSummary)
def usage_summary(db: Session = Depends(get_db)) -> UsageSummary:
    rows = db.scalars(select(MCPUsage)).all()
    durations = [r.duration_ms for r in rows]
    ok = sum(1 for r in rows if r.status == "ok")
    err = len(rows) - ok

    by_tool: dict[str, dict] = defaultdict(
        lambda: {"calls": 0, "durations": [], "error": 0}
    )
    for r in rows:
        t = by_tool[r.tool]
        t["calls"] += 1
        t["durations"].append(r.duration_ms)
        if r.status != "ok":
            t["error"] += 1

    tools = [
        ToolStat(
            tool=name,
            calls=v["calls"],
            avg_ms=round(sum(v["durations"]) / len(v["durations"]), 1)
            if v["durations"]
            else 0.0,
            p95_ms=round(_p95(v["durations"]), 1),
            error=v["error"],
        )
        for name, v in sorted(by_tool.items())
    ]

    return UsageSummary(
        total_calls=len(rows),
        ok=ok,
        error=err,
        success_rate=round(ok / len(rows), 6) if rows else 0.0,
        avg_ms=round(sum(durations) / len(durations), 1) if durations else 0.0,
        p95_ms=round(_p95(durations), 1),
        min_ms=round(min(durations), 1) if durations else 0.0,
        max_ms=round(max(durations), 1) if durations else 0.0,
        by_tool=tools,
    )


@router.get("/latency", response_model=list[LatencyOutlier])
def latency_outliers(
    threshold: float = Query(2000.0, ge=0.0),
    db: Session = Depends(get_db),
) -> list[LatencyOutlier]:
    rows = db.scalars(select(MCPUsage)).all()
    return [
        LatencyOutlier(
            ts=r.ts,
            server=r.server,
            tool=r.tool,
            duration_ms=r.duration_ms,
            status=r.status,
            error=r.error,
        )
        for r in rows
        if r.duration_ms > threshold or r.status != "ok"
    ]


@router.get("/timeline", response_model=list[TimelineBucket])
def timeline(
    bucket: str = Query("day", pattern="^(day|hour)$"),
    db: Session = Depends(get_db),
) -> list[TimelineBucket]:
    rows = db.scalars(select(MCPUsage)).all()
    groups: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0})
    for r in rows:
        key = r.ts.strftime("%Y-%m-%d") if bucket == "day" else r.ts.strftime("%Y-%m-%d %H:00")
        groups[key]["calls"] += 1
        if r.status != "ok":
            groups[key]["errors"] += 1
    return [
        TimelineBucket(bucket=k, calls=v["calls"], errors=v["errors"])
        for k, v in sorted(groups.items())
    ]
