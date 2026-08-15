"""Pydantic response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


# ---- health ----
class ServerHealth(BaseModel):
    name: str
    calls: int
    ok: int
    error: int
    success_rate: float
    avg_ms: float
    p95_ms: float
    last_status: str | None = None
    last_ts: datetime | None = None


class HealthResponse(BaseModel):
    servers: list[ServerHealth]


# ---- usage ----
class ToolStat(BaseModel):
    tool: str
    calls: int
    avg_ms: float
    p95_ms: float
    error: int


class UsageSummary(BaseModel):
    total_calls: int
    ok: int
    error: int
    success_rate: float
    avg_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    by_tool: list[ToolStat]


class LatencyOutlier(BaseModel):
    ts: datetime
    server: str
    tool: str
    duration_ms: float
    status: str
    error: str | None = None


class TimelineBucket(BaseModel):
    bucket: str
    calls: int
    errors: int


# ---- hypotheses ----
class VariantStat(BaseModel):
    variant_id: str
    attempts: int
    hits: int
    confidence: float | None = None


class HypothesesSummary(BaseModel):
    variants: list[VariantStat]


class TrendPoint(BaseModel):
    variant_id: str
    ts: datetime
    cumulative_hits: int
    cumulative_attempts: int


class HypothesesTrend(BaseModel):
    trend: list[TrendPoint]
