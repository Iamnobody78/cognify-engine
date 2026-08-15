"""Seed 数据 (S67 spec §10.5, PM P1):
  - 3 条示例策略快照 (引擎真实编译入库 — 9 条规则)
  - 3 个 demo agents
  - 5 条审计事件 (程序化生成, 含谎报降级样本)
  - 2 次 VCE 扫描 (S65 基线: 盲点 3 / 无通道 → S66: 盲点 0 / 通道启用)
  - 实时裁决 demo (裸 satisfied → ESCALATE 入库)

用法: python seed.py [db_path]
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from governance_engine import GovernanceEngine  # noqa: E402
from models import Agent, VceScan  # noqa: E402


def seed(engine: GovernanceEngine) -> None:
    session = engine._factory()
    try:
        # ── demo agents ────────────────────────────────────────────
        agents = [
            Agent(id="agent-solver-a", name="Solver Alpha", role="solver",
                  status="active", sessions=12,
                  last_seen=datetime.utcnow()),
            Agent(id="agent-solver-b", name="Solver Beta", role="solver",
                  status="active", sessions=8,
                  last_seen=datetime.utcnow() - timedelta(minutes=42)),
            Agent(id="agent-critic-c", name="Critic Charlie", role="critic",
                  status="idle", sessions=5,
                  last_seen=datetime.utcnow() - timedelta(days=1)),
        ]
        for a in agents:
            session.merge(a)

        # ── VCE 历史: S65 基线 → S66 验证通道 (拐点) ────────────────
        s65_report = {
            "Polarization_Index": 0.383, "Value_Tensions": [],
            "Asymmetric_Perspectives": [],
            "RuleConflicts": [], "BlindSpots": [{"category": "declaration_only",
                                                  "severity": "medium"}],
            "Verification_Channel": {"enabled": False, "type": "none"},
            "scanned_rule_count": 9, "conflict_count": 6, "blindspot_count": 3,
        }
        s66_report = {
            "Polarization_Index": 0.383, "Value_Tensions": [],
            "Asymmetric_Perspectives": [],
            "RuleConflicts": [], "BlindSpots": [],
            "Verification_Channel": {"enabled": True, "type": "pluggable-validator",
                                      "validator": "baseline"},
            "scanned_rule_count": 9, "conflict_count": 6, "blindspot_count": 0,
        }
        session.add(VceScan(ts=datetime.utcnow() - timedelta(days=1),
                            report=s65_report, polarization=0.383,
                            conflict_count=6, blindspot_count=3,
                            channel_enabled=False))
        session.add(VceScan(ts=datetime.utcnow(), report=s66_report,
                            polarization=0.383, conflict_count=6,
                            blindspot_count=0, channel_enabled=True))
        session.commit()
    finally:
        session.close()

    # ── 审计事件 (程序化: 真实引擎裁决 + 入库) ─────────────────────
    cases = [
        # (agent, path, method, body) — 期望命中协议规则
        ("agent-solver-a", "/gateway", {"governance": {"protocols": {
            "feynman_test": {"satisfied": True,
                             "evidence": "feynman_self_check_v3"}}}}),
        ("agent-solver-b", "/gateway", {"governance": {"protocols": {
            "feynman_test": {"satisfied": True}}}}),          # 谎报嫌疑 (无锚点)
        ("agent-critic-c", "/gateway", {"governance": {"protocols": {
            "logic_chain_check": {"violation": "LCC-101: 步骤 3→4 跳步"}}}}),
        ("agent-solver-a", "/gateway", {"governance": {"protocols": {
            "entropy_denoise": {"satisfied": True,
                                "output": ["要点1", "要点2", "要点3"]}}}}),
        ("agent-solver-b", "/gateway", {"governance": {"protocols": {
            "logic_chain_check": {"satisfied": True}}}}),  # 谎报嫌疑 (无锚点)
    ]
    for agent_id, path, body in cases:
        engine.evaluate_verified(path, "POST", body, agent_id=agent_id)

    print(f"seed ok: {len(agents)} agents, {len(cases)} audit events, "
          f"2 vce scans, {len(engine.gw.rules)} rules snapshotted")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    engine = GovernanceEngine(db_path=db_path)
    seed(engine)
