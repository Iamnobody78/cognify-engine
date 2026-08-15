"""SQLAlchemy ORM models for the MCP monitoring dashboard."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class MCPUsage(Base):
    """One row per MCP tool invocation (from mcp_usage_report.jsonl)."""

    __tablename__ = "mcp_usage"
    __table_args__ = (
        Index("idx_usage_ts", "ts"),
        Index("idx_usage_server", "server"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    server: Mapped[str] = mapped_column(String(64), nullable=False)
    tool: Mapped[str] = mapped_column(String(128), nullable=False)
    args: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Hypothesis(Base):
    """One row per recorded hypothesis (from hypotheses.jsonl)."""

    __tablename__ = "hypotheses"
    __table_args__ = (
        Index("idx_hyp_ts", "ts"),
        Index("idx_hyp_variant", "variant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    variant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    layer: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
