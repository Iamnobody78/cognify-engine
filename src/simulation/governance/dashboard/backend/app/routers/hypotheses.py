"""Hypotheses endpoints: variant aggregation (F-110 semantics) + cumulative trend."""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Hypothesis
from ..schemas import HypothesesSummary, HypothesesTrend, TrendPoint, VariantStat

router = APIRouter(prefix="/api/hypotheses", tags=["hypotheses"])


@router.get("/summary", response_model=HypothesesSummary)
def hypotheses_summary(db: Session = Depends(get_db)) -> HypothesesSummary:
    rows = db.scalars(select(Hypothesis).order_by(Hypothesis.ts)).all()
    by_variant: dict[str, dict] = defaultdict(
        lambda: {"attempts": 0, "hits": 0, "scores": []}
    )
    for r in rows:
        v = by_variant[r.variant_id]
        v["attempts"] += 1
        if r.outcome == "confirmed" or (r.score is not None and r.score > 0.5):
            v["hits"] += 1
        if r.score is not None:
            v["scores"].append(r.score)

    variants = [
        VariantStat(
            variant_id=vid,
            attempts=v["attempts"],
            hits=v["hits"],
            confidence=round(v["hits"] / v["attempts"], 4)
            if v["attempts"]
            else None,
        )
        for vid, v in sorted(by_variant.items())
    ]
    return HypothesesSummary(variants=variants)


@router.get("/trend", response_model=HypothesesTrend)
def hypotheses_trend(db: Session = Depends(get_db)) -> HypothesesTrend:
    rows = db.scalars(select(Hypothesis).order_by(Hypothesis.ts)).all()
    counters: dict[str, dict] = defaultdict(lambda: {"hits": 0, "attempts": 0})
    trend: list[TrendPoint] = []
    for r in rows:
        c = counters[r.variant_id]
        c["attempts"] += 1
        if r.outcome == "confirmed" or (r.score is not None and r.score > 0.5):
            c["hits"] += 1
        trend.append(
            TrendPoint(
                variant_id=r.variant_id,
                ts=r.ts,
                cumulative_hits=c["hits"],
                cumulative_attempts=c["attempts"],
            )
        )
    return HypothesesTrend(trend=trend)
