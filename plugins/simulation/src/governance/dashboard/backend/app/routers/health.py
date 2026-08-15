"""Health endpoint: per-server call/ok/error/latency aggregation."""
from __future__ import annotations

from statistics import median

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import MCPUsage
from ..schemas import HealthResponse, ServerHealth

router = APIRouter(prefix="/api", tags=["health"])


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, int(round(0.95 * len(s))) - 1)
    return s[idx]


@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    servers = []
    for server in sorted(
        set(db.scalars(select(MCPUsage.server)).all())
    ):
        rows = db.scalars(select(MCPUsage).where(MCPUsage.server == server)).all()
        durations = [r.duration_ms for r in rows]
        ok = sum(1 for r in rows if r.status == "ok")
        err = len(rows) - ok
        servers.append(
            ServerHealth(
                name=server,
                calls=len(rows),
                ok=ok,
                error=err,
                success_rate=round(ok / len(rows), 6) if rows else 0.0,
                avg_ms=round(sum(durations) / len(durations), 1) if durations else 0.0,
                p95_ms=round(_p95(durations), 1) if durations else 0.0,
                last_status=rows[-1].status if rows else None,
                last_ts=rows[-1].ts if rows else None,
            )
        )
    return HealthResponse(servers=servers)
