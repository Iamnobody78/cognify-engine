"""GovernanceEngine 门面 — 同进程集成 agent-governance-v2 (S67 spec §3.1 方案 B)。

职责:
  1. 构建 ProtocolGateway(validator=BaselineDeclarationValidator(), audit_sink=...)
  2. 审计事件自动入库 (audit_events 表) — contextvar 传递 agent_id (线程安全)
  3. 策略快照入库 (policy_snapshots) + MCE 自省摘要
  4. 代理聚合指标 (escalations / verified_ok / verified_fail)
  5. VCE 扫描触发与历史

依赖注入: agent-governance-v2 通过相对路径引入 (同会话目录);
可用环境变量 GOV_AGENTS_V2_PATH 覆盖。
"""
import contextvars
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime

import yaml  # noqa: E402

# ── agent-governance-v2 引入 ─────────────────────────────────────────
_DEFAULT_V2 = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))), "agent-governance-v2")
_AGENTS_V2 = os.getenv("GOV_AGENTS_V2_PATH", _DEFAULT_V2)
if _AGENTS_V2 not in sys.path:
    sys.path.insert(0, _AGENTS_V2)

from src.protocol_gateway import ProtocolGateway  # noqa: E402
from src.verification import BaselineDeclarationValidator  # noqa: E402

from models import Agent, AuditEvent, PolicySnapshot, VceScan  # noqa: E402
from database import build_engine, build_session_factory, get_session_factory  # noqa: E402

# contextvar: 当前 evaluate 调用的 agent_id (thread-safe, FastAPI 线程池兼容)
_CTX_AGENT = contextvars.ContextVar("gov_agent_id", default="anonymous")


class GovernanceEngine:
    """治理引擎门面 (单例, 启动时构建)。"""

    def __init__(self, protocols_dir=None, db_path=None, snapshot=True):
        if db_path:
            self._factory = build_session_factory(build_engine(db_path))
        else:
            self._factory = get_session_factory()
        self._protocols_dir = protocols_dir or self._default_protocols_dir()
        # 引擎: 验证器 + 审计回调
        self._build_gateway()
        if snapshot:
            self._snapshot_policies()

    # -- 网关构建/热重载 (S69 策略编辑器) -------------------------------

    @staticmethod
    def _default_protocols_dir() -> str:
        return os.path.join(_AGENTS_V2, "config", "protocols")

    def _build_gateway(self) -> None:
        self.gw = ProtocolGateway(
            protocols_dir=self._protocols_dir,
            validator=BaselineDeclarationValidator(),
            audit_sink=self._on_audit,
        )

    def _rebuild_gateway(self) -> None:
        """部署后热重载: 重建网关 (保留 validator + audit_sink)。"""
        self._build_gateway()

    # -- 审计回调 (由 ProtocolGateway.evaluate_verified 调用) ----------

    def _on_audit(self, event: dict) -> None:
        """写入 audit_events (fail-open: 入库失败不影响裁决)。"""
        try:
            session = self._factory()
            try:
                session.add(AuditEvent(
                    agent_id=_CTX_AGENT.get(),
                    path=event.get("path", ""),
                    method=event.get("method", "POST"),
                    matched_rule=event.get("rule") or "",
                    action=event.get("action") or "",
                    channel=event.get("channel", "none"),
                    verification=event.get("verification") or {},
                    raw_body=event.get("body") or {},
                ))
                session.commit()
            finally:
                session.close()
        except Exception:
            pass  # fail-open 审计

    # -- 评估 -----------------------------------------------------------

    def evaluate_verified(self, path: str, method: str, body: dict,
                          agent_id: str = "anonymous") -> dict:
        """裁决+验证, agent_id 随审计入库。"""
        token = _CTX_AGENT.set(agent_id)
        try:
            return self.gw.evaluate_verified(path, method, body)
        finally:
            _CTX_AGENT.reset(token)

    # -- 策略快照 --------------------------------------------------------

    def _snapshot_policies(self) -> None:
        session = self._factory()
        try:
            for r in self.gw.rules:
                session.add(PolicySnapshot(
                    protocol=(r.name.split("-")[1] if r.name.count("-") >= 2
                              else "unknown"),
                    rule_type=(r.name.split("-")[2] if r.name.count("-") >= 2
                               else "?"),
                    rule_name=r.name,
                    priority=r.priority,
                    action=r.action,
                    json_path=r.json_path or "",
                    json_pattern=r.json_pattern or "",
                    origin=getattr(r, "origin", "") or "",
                ))
            session.commit()
        finally:
            session.close()

    # -- S69 策略编辑器: validate / deploy / source ---------------------

    @staticmethod
    def _safe_protocol_name(name: str) -> str:
        """协议名白名单: 仅 [a-z_][a-z0-9_]* (防路径穿越)。"""
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", name or ""):
            raise ValueError(f"非法协议名: {name!r} (仅允许小写字母/数字/下划线)")
        return name

    def protocol_source(self, name: str) -> dict:
        """读取协议 YAML 源文本 (编辑器加载用)。"""
        self._safe_protocol_name(name)
        path = os.path.join(self._protocols_dir, f"{name}.yaml")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return {"protocol": name, "yaml": f.read()}

    def validate_protocol(self, name: str, yaml_text: str) -> dict:
        """预编译验证 (不写入真实 config):
          1. YAML 语法检查
          2. schema_version 契约检查 (11-col-v1)
          3. 临时目录预编译 (load_protocols 做全部 fail-closed 字段校验)
        """
        self._safe_protocol_name(name)
        # 1) YAML 语法
        try:
            data = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            return {"valid": False, "protocol": name, "errors": [f"YAML 语法错误: {e}"]}
        if not isinstance(data, dict):
            return {"valid": False, "protocol": name,
                    "errors": ["YAML 顶层必须是对象 (protocol 声明)"]}
        # 2) schema 契约
        if data.get("schema_version") != "11-col-v1":
            return {"valid": False, "protocol": name,
                    "errors": [f"schema_version 必须是 '11-col-v1' (fail-closed) — "
                               f"got {data.get('schema_version')!r}"]}
        # 3) 预编译 (临时目录, 零副作用) — 编译器校验 12 必填字段/level 合法性
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, f"{name}.yaml"), "w",
                      encoding="utf-8") as f:
                f.write(yaml_text)
            try:
                gw = ProtocolGateway(protocols_dir=td)
                return {"valid": True, "protocol": name,
                        "errors": [], "rules_count": len(gw.rules),
                        "rule_types": sorted({r.action for r in gw.rules})}
            except Exception as e:
                return {"valid": False, "protocol": name,
                        "errors": [f"编译失败: {e}"]}

    def deploy_protocol(self, name: str, yaml_text: str) -> dict:
        """部署: 写入 config/protocols/{name}.yaml → 网关热重载 → 策略快照。
        失败自动回滚 (备份恢复 + 网关重建)。
        """
        self._safe_protocol_name(name)
        # 部署前先验证 (拒绝非法内容写入真实 config)
        check = self.validate_protocol(name, yaml_text)
        if not check.get("valid"):
            return {"deployed": False, "protocol": name,
                    "error": "; ".join(check.get("errors", []))}

        target = os.path.join(self._protocols_dir, f"{name}.yaml")
        backup = None
        if os.path.exists(target):
            backup = target + ".bak"
            shutil.copy2(target, backup)
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(yaml_text)
            self._rebuild_gateway()
            self._snapshot_policies()
            proto_rules = [r for r in self.gw.rules
                           if r.name.startswith(f"protocol-{name}-")]
            return {"deployed": True, "protocol": name,
                    "rules_count": len(self.gw.rules),
                    "protocol_rules": len(proto_rules)}
        except Exception as e:
            if backup and os.path.exists(backup):
                shutil.copy2(backup, target)
            self._rebuild_gateway()
            return {"deployed": False, "protocol": name, "error": str(e)}

    # -- 查询: 代理清单 ---------------------------------------------------

    def agents(self) -> list:
        session = self._factory()
        try:
            rows = session.query(Agent).order_by(Agent.id).all()
            out = []
            for a in rows:
                agg = self._agent_aggregates(session, a.id)
                out.append({
                    "id": a.id, "name": a.name, "role": a.role,
                    "status": a.status,
                    "last_seen": a.last_seen.isoformat() if a.last_seen else None,
                    "sessions": a.sessions,
                    "escalations": agg["escalations"],
                    "verified_ok": agg["verified_ok"],
                    "verified_fail": agg["verified_fail"],
                })
            return out
        finally:
            session.close()

    @staticmethod
    def _agent_aggregates(session, agent_id: str) -> dict:
        events = session.query(AuditEvent).filter(
            AuditEvent.agent_id == agent_id).all()
        return {
            "escalations": sum(1 for e in events if e.action == "ESCALATE"),
            "verified_ok": sum(1 for e in events
                               if e.verification and e.verification.get("verified")),
            "verified_fail": sum(1 for e in events
                                 if e.verification
                                 and not e.verification.get("verified")),
        }

    # -- 查询: 策略 ---------------------------------------------------------

    def policies(self) -> dict:
        """按模块聚合规则树, 附带 MCE why-exists 摘要与冲突标记。"""
        session = self._factory()
        try:
            snaps = session.query(PolicySnapshot).order_by(
                PolicySnapshot.priority).all()
            mce = self._load_mce()
            vce = self.vce_latest(session=session)
            conflicts = {c.get("rule"): c for c in
                         (vce or {}).get("RuleConflicts", [])}
            modules = {}
            for s in snaps:
                mod = modules.setdefault(s.protocol, {"rules": []})
                rule_entry = {
                    "rule_name": s.rule_name, "rule_type": s.rule_type,
                    "priority": s.priority, "action": s.action,
                    "json_path": s.json_path, "json_pattern": s.json_pattern,
                    "origin": s.origin,
                    "conflicts": [c for c in conflicts.values()
                                  if c.get("rule") == s.rule_name],
                }
                # MCE 摘要 (why_exists / what_it_governs)
                for rmc in mce.get("protocols", {}).get(s.protocol, []):
                    if rmc.get("rule") == s.rule_name:
                        rule_entry["mce"] = {
                            "why_exists": rmc.get("why_exists"),
                            "what_it_governs": rmc.get("what_it_governs"),
                        }
                mod["rules"].append(rule_entry)
            return {"modules": modules, "scanned_at": datetime.utcnow().isoformat()}
        finally:
            session.close()

    def _load_mce(self) -> dict:
        path = os.path.join(_AGENTS_V2, "config", "mce_introspection.generated.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    # -- 查询: 审计 ---------------------------------------------------------

    def audit(self, limit: int = 100, rule: str = None, action: str = None,
              agent: str = None, channel: str = None) -> list:
        session = self._factory()
        try:
            q = session.query(AuditEvent).order_by(AuditEvent.id.desc())
            if rule:
                q = q.filter(AuditEvent.matched_rule == rule)
            if action:
                q = q.filter(AuditEvent.action == action)
            if agent:
                q = q.filter(AuditEvent.agent_id == agent)
            if channel:
                q = q.filter(AuditEvent.channel == channel)
            rows = q.limit(min(limit, 500)).all()
            return [self._audit_row(e) for e in rows]
        finally:
            session.close()

    def audit_one(self, audit_id: int) -> dict:
        session = self._factory()
        try:
            e = session.get(AuditEvent, audit_id)
            return self._audit_row(e) if e else None
        finally:
            session.close()

    def ingest_audit_events(self, events: list) -> None:
        """预留端点: 外部系统批量写入审计事件。"""
        session = self._factory()
        try:
            for ev in events:
                session.add(AuditEvent(
                    agent_id=ev.get("agent_id", "anonymous"),
                    path=ev.get("path", ""),
                    method=ev.get("method", "POST"),
                    matched_rule=ev.get("matched_rule", ""),
                    action=ev.get("action", ""),
                    channel=ev.get("channel", "none"),
                    verification=ev.get("verification") or {},
                    raw_body=ev.get("raw_body") or {},
                ))
            session.commit()
        finally:
            session.close()

    @staticmethod
    def _audit_row(e: AuditEvent) -> dict:
        return {
            "id": e.id,
            "ts": e.ts.isoformat() if e.ts else None,
            "agent_id": e.agent_id,
            "path": e.path, "method": e.method,
            "matched_rule": e.matched_rule, "action": e.action,
            "channel": e.channel,
            "verification": e.verification,
            "raw_body": e.raw_body,
        }

    # -- 查询: VCE ----------------------------------------------------------

    def vce_latest(self, session=None) -> dict:
        own = session is None
        session = session or self._factory()
        try:
            row = session.query(VceScan).order_by(VceScan.id.desc()).first()
            return row.report if row else None
        finally:
            if own:
                session.close()

    def vce_history(self, limit: int = 20) -> list:
        session = self._factory()
        try:
            rows = session.query(VceScan).order_by(VceScan.id.desc()).limit(
                min(limit, 100)).all()
            return [{
                "id": r.id, "ts": r.ts.isoformat() if r.ts else None,
                "polarization": r.polarization,
                "conflict_count": r.conflict_count,
                "blindspot_count": r.blindspot_count,
                "channel_enabled": r.channel_enabled,
            } for r in rows]
        finally:
            session.close()

    def vce_scan(self) -> dict:
        """触发重扫 (同步执行 scan() 并入库)。"""
        report = self.gw.scan()
        session = self._factory()
        try:
            session.add(VceScan(
                report=report,
                polarization=report.get("Polarization_Index", 0.0),
                conflict_count=report.get("conflict_count", 0),
                blindspot_count=report.get("blindspot_count", 0),
                channel_enabled=report.get("Verification_Channel", {}).get(
                    "enabled", False),
            ))
            session.commit()
        finally:
            session.close()
        return report
