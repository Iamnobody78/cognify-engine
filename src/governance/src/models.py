"""Pydantic schemas for the governance gateway:
HTTP request/response contracts and the persisted decision record.

Type policy (AUDIT-0006): strong types (Verdict enum, timezone-aware
datetime) are kept through the persistence boundary; field_serializer
converts them at the serialization edge instead of degrading the model.
"""

from enum import Enum
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union

from pydantic import BaseModel, Field, field_serializer


class Verdict(str, Enum):
    """五级判定响应（TASK-REAL-012 Phase 4 治理大脑 Phase 1）:
    ALLOW / ALLOW_WITH_WARNING / ESCALATE / DENY / SUSPEND。
    既有值语义不变（增量扩展，不破坏旧行为）。
    """
    ALLOW = "ALLOW"
    ALLOW_WITH_WARNING = "ALLOW_WITH_WARNING"
    ESCALATE = "ESCALATE"
    DENY = "DENY"
    SUSPEND = "SUSPEND"


class InterceptRequest(BaseModel):
    path: str
    method: str
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Union[Dict[str, Any], str]] = None
    agent_id: Optional[str] = None


class InterceptResponse(BaseModel):
    verdict: Verdict
    reason: str
    decision_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    matched_rule: Optional[str] = None
    # TASK-REAL-011 (C): trace_id 回传给调用方 — 串联多 Agent 调用链
    trace_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float


class DecisionRecord(BaseModel):
    """Persisted decision.

    Keeps the same strong types as InterceptResponse (Verdict enum,
    timezone-aware datetime) instead of degrading to bare str; field
    serializers convert at the persistence edge (AUDIT-0006).
    """

    id: str
    verdict: Verdict
    reason: str
    matched_rule: Optional[str] = None
    # TASK-REAL-012 Phase 4 (治理大脑 Phase 1): 可解释字段 — 为什么这么判。
    # 来自匹配规则的 reason + 上下文（熔断/超时/语义旁路追加说明）。
    rationale: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    path: str
    method: str
    agent_id: Optional[str] = None
    # TASK-REAL-010 (Step 1 可解释审计): 工具杀伤半径审计字段
    #   tool_name      — 请求中杀伤半径最高的工具名 (归一化前原样, 供归因)
    #   tool_lethality — 对应 Ls (0.0-1.0, 见 src/lethality.py); None = 无工具声明
    tool_name: Optional[str] = None
    tool_lethality: Optional[float] = None
    # TASK-REAL-011 (C 阶段 Trace): 因果链字段 — 串联多 Agent 调用链
    #   trace_id       — 整条调用链根标识 (X-Trace-ID 或入口生成的新 UUID)
    #   parent_span_id — 父决策的 id (span_id == decision.id; NULL = 链根)
    trace_id: Optional[str] = None
    parent_span_id: Optional[str] = None

    @field_serializer("verdict")
    def serialize_verdict(self, value: Verdict) -> str:
        return value.value

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return value.isoformat()
