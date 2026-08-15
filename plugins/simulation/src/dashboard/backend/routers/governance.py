"""治理中心 API 路由 (S67 spec §5 契约)。

10 端点 + 1 预留:
  GET    /api/governance/agents
  GET    /api/governance/agents/{agent_id}/audit
  GET    /api/governance/policies
  GET    /api/governance/policies/{protocol}
  GET    /api/governance/audit
  GET    /api/governance/audit/{audit_id}
  GET    /api/governance/vce/latest
  GET    /api/governance/vce/history
  POST   /api/governance/vce/scan
  POST   /api/governance/evaluate
  POST   /api/governance/audit/ingest   (预留: 外部系统批量写入)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import require_role  # noqa: E402 (RBAC, ARCH-ROUND 2 / GAP-3.1)
from models import User  # noqa: E402

router = APIRouter(prefix="/api/governance", tags=["governance"])

# 引擎门面: main.py 启动时注入 (FastAPI app.state)
def get_engine():
    from fastapi import Request
    def _dep(request: Request):
        return request.app.state.governance_engine
    return _dep


class EvaluateRequest(BaseModel):
    path: str = "/gateway"
    method: str = "POST"
    body: dict = Field(default_factory=dict)
    agent_id: str = "anonymous"


class IngestEvent(BaseModel):
    agent_id: str
    path: str = ""
    method: str = "POST"
    matched_rule: str = ""
    action: str = ""
    channel: str = "none"
    verification: dict = Field(default_factory=dict)
    raw_body: dict = Field(default_factory=dict)


class ProtocolPayload(BaseModel):
    protocol: str
    yaml: str


@router.get("/agents")
def list_agents(engine=Depends(get_engine()), user: User = Depends(require_role("viewer"))):
    return engine.agents()


@router.get("/agents/{agent_id}/audit")
def agent_audit(agent_id: str, limit: int = Query(50, le=200),
                engine=Depends(get_engine()), user: User = Depends(require_role("viewer"))):
    return engine.audit(limit=limit, agent=agent_id)


@router.get("/policies")
def list_policies(engine=Depends(get_engine()), user: User = Depends(require_role("viewer"))):
    return engine.policies()


@router.get("/policies/{protocol}")
def protocol_detail(protocol: str, engine=Depends(get_engine()),
                    user: User = Depends(require_role("viewer"))):
    tree = engine.policies()
    if protocol not in tree.get("modules", {}):
        raise HTTPException(status_code=404,
                            detail=f"protocol {protocol} 不存在")
    return {"protocol": protocol, **tree["modules"][protocol]}


@router.get("/audit")
def list_audit(limit: int = Query(100, le=500),
               rule: str = None, action: str = None,
               agent: str = None, channel: str = None,
               engine=Depends(get_engine()), user: User = Depends(require_role("viewer"))):
    return engine.audit(limit=limit, rule=rule, action=action,
                        agent=agent, channel=channel)


@router.get("/audit/{audit_id}")
def audit_detail(audit_id: int, engine=Depends(get_engine()),
                 user: User = Depends(require_role("viewer"))):
    row = engine.audit_one(audit_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"audit {audit_id} 不存在")
    return row


@router.get("/vce/latest")
def vce_latest(engine=Depends(get_engine()), user: User = Depends(require_role("viewer"))):
    report = engine.vce_latest()
    if report is None:
        raise HTTPException(status_code=404, detail="尚无 VCE 扫描记录")
    return report


@router.get("/vce/history")
def vce_history(limit: int = Query(20, le=100), engine=Depends(get_engine()),
                user: User = Depends(require_role("viewer"))):
    return engine.vce_history(limit=limit)


@router.post("/vce/scan")
def vce_scan(engine=Depends(get_engine()), user: User = Depends(require_role("auditor"))):
    return engine.vce_scan()


# ── 引擎集成端点 (agent → dashboard, 无人类用户上下文; v3.0 服务化解耦时补 API-Key) ──
@router.post("/evaluate")
def evaluate(req: EvaluateRequest, engine=Depends(get_engine())):
    return engine.evaluate_verified(req.path, req.method, req.body,
                                    agent_id=req.agent_id)


@router.post("/audit/ingest")
def audit_ingest(events: list[IngestEvent], engine=Depends(get_engine())):
    """预留: 外部系统批量写入审计事件。"""
    engine.ingest_audit_events([e.model_dump() for e in events])
    return {"ingested": len(events)}


# ── S69 策略编辑器 (编辑→验证→部署 闭环) ────────────────────────────

@router.get("/policies/{protocol}/source")
def protocol_source(protocol: str, engine=Depends(get_engine()),
                    user: User = Depends(require_role("viewer"))):
    """读取协议 YAML 源文本 (编辑器加载)。"""
    src = engine.protocol_source(protocol)
    if src is None:
        raise HTTPException(status_code=404,
                            detail=f"protocol {protocol} 的 YAML 源不存在")
    return src


@router.post("/policies/validate")
def policy_validate(payload: ProtocolPayload, engine=Depends(get_engine()),
                    user: User = Depends(require_role("auditor"))):
    """预编译验证 (零副作用: 临时目录编译, 不写入真实 config)。"""
    try:
        return engine.validate_protocol(payload.protocol, payload.yaml)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/policies/deploy")
def policy_deploy(payload: ProtocolPayload, engine=Depends(get_engine()),
                  admin: User = Depends(require_role("admin"))):
    """部署: 写入 config/protocols/ + 网关热重载 + 策略快照; 失败回滚。

    安全 (ARCH-ROUND 2 / GAP-3.1): 仅 admin 角色可部署治理策略。
    """
    try:
        result = engine.deploy_protocol(payload.protocol, payload.yaml)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not result.get("deployed"):
        raise HTTPException(status_code=422, detail=result)
    return result
