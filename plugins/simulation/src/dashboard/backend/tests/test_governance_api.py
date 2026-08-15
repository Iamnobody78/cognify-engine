"""S68 Phase 1: 治理中心 API 测试。

覆盖: 10 端点契约 + 审计自动入库 + 谎报降级 demo + 策略快照 + VCE 历史。
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from governance_engine import GovernanceEngine  # noqa: E402
from seed import seed  # noqa: E402


@pytest.fixture(scope="module")
def client():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    # 临时协议目录 (复制真实协议) — 避免 deploy 测试污染真实 config/protocols
    proto_dir = os.path.join(tmp, "protocols")
    os.makedirs(proto_dir)
    real_proto_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),  # tests
        "..", "..", "..", "..",  # → 会话仓库根 (aionrs-temp-...)
        "agent-governance-v2", "config", "protocols")
    import shutil
    for f in os.listdir(real_proto_dir):
        if f.endswith(".yaml"):
            shutil.copy2(os.path.join(real_proto_dir, f),
                         os.path.join(proto_dir, f))

    engine = GovernanceEngine(protocols_dir=proto_dir, db_path=db_path)
    seed(engine)

    from main import app
    app.state.governance_engine = engine
    with TestClient(app) as c:
        # RBAC (ARCH-ROUND 2 / GAP-3.1): startup seed 创建 admin → 登录注入认证头
        r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, f"admin login failed: {r.text}"
        token = r.json()["token"]
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c


# ── 代理清单 ────────────────────────────────────────────────────────

class TestAgents:
    def test_list_agents(self, client):
        r = client.get("/api/governance/agents")
        assert r.status_code == 200
        agents = r.json()
        assert len(agents) == 3
        ids = {a["id"] for a in agents}
        assert {"agent-solver-a", "agent-solver-b", "agent-critic-c"} <= ids

    def test_agent_aggregates(self, client):
        agents = client.get("/api/governance/agents").json()
        b = next(a for a in agents if a["id"] == "agent-solver-b")
        # agent-solver-b: 裸 satisfied (无锚点) → ESCALATE + verified_fail ×1
        #               + violation+satisfied → ESCALATE + verified_fail ×1
        assert b["escalations"] == 2
        assert b["verified_fail"] == 2
        assert b["verified_ok"] == 0

    def test_agent_audit(self, client):
        r = client.get("/api/governance/agents/agent-solver-a/audit?limit=50")
        assert r.status_code == 200
        evs = r.json()
        assert len(evs) == 2  # feynman 锚定 + entropy 锚定
        assert all(e["agent_id"] == "agent-solver-a" for e in evs)


# ── 策略管理 ────────────────────────────────────────────────────────

class TestPolicies:
    def test_policies_tree(self, client):
        r = client.get("/api/governance/policies")
        assert r.status_code == 200
        mods = r.json()["modules"]
        assert set(mods.keys()) == {"feynman_test", "entropy_denoise",
                                    "logic_chain_check"}
        total = sum(len(m["rules"]) for m in mods.values())
        assert total == 9  # ethics/enforce/ok × 3

    def test_policy_has_mce_and_conflicts(self, client):
        mods = client.get("/api/governance/policies").json()["modules"]
        ok_rule = next(r for r in mods["feynman_test"]["rules"]
                       if r["rule_type"] == "ok")
        assert "mce" in ok_rule  # why_exists 摘要
        assert "conflicts" in ok_rule

    def test_protocol_detail(self, client):
        r = client.get("/api/governance/policies/feynman_test")
        assert r.status_code == 200
        assert len(r.json()["rules"]) == 3

    def test_protocol_404(self, client):
        assert client.get("/api/governance/policies/nope").status_code == 404


# ── 审计查看 ────────────────────────────────────────────────────────

class TestAudit:
    def test_list_audit(self, client):
        r = client.get("/api/governance/audit?limit=20")
        assert r.status_code == 200
        evs = r.json()
        assert len(evs) == 5  # seed 5 条
        assert all("verification" in e and "raw_body" in e for e in evs)

    def test_audit_filter_action(self, client):
        evs = client.get("/api/governance/audit?action=ESCALATE").json()
        assert len(evs) == 2  # agent-solver-b 两条降级
        assert all(e["action"] == "ESCALATE" for e in evs)

    def test_audit_filter_rule(self, client):
        evs = client.get("/api/governance/audit?rule=protocol-feynman_test-ok").json()
        assert len(evs) == 2

    def test_audit_detail(self, client):
        evs = client.get("/api/governance/audit?limit=1").json()
        aid = evs[0]["id"]
        r = client.get(f"/api/governance/audit/{aid}")
        assert r.status_code == 200
        assert r.json()["id"] == aid

    def test_audit_404(self, client):
        assert client.get("/api/governance/audit/99999").status_code == 404


# ── VCE 可视化 ──────────────────────────────────────────────────────

class TestVce:
    def test_vce_latest(self, client):
        r = client.get("/api/governance/vce/latest")
        assert r.status_code == 200
        rep = r.json()
        assert rep["blindspot_count"] == 0
        assert rep["Verification_Channel"]["enabled"] is True

    def test_vce_history_trend(self, client):
        hist = client.get("/api/governance/vce/history").json()
        assert len(hist) == 2
        oldest = hist[-1]  # S65 基线
        assert oldest["blindspot_count"] == 3
        assert oldest["channel_enabled"] is False

    def test_vce_scan_trigger(self, client):
        r = client.post("/api/governance/vce/scan")
        assert r.status_code == 200
        rep = r.json()
        assert "Polarization_Index" in rep
        # 触发后历史 +1
        hist = client.get("/api/governance/vce/history?limit=10").json()
        assert len(hist) == 3


# ── 实时裁决 (谎报降级 demo) ────────────────────────────────────────

class TestEvaluate:
    def test_zero_cost_bypass_escalated(self, client):
        r = client.post("/api/governance/evaluate", json={
            "agent_id": "agent-solver-b",
            "path": "/gateway", "method": "POST",
            "body": {"governance": {"protocols": {"feynman_test": {
                "satisfied": True}}}},
        })
        assert r.status_code == 200
        out = r.json()
        assert out["rule"] == "protocol-feynman_test-ok"
        assert out["action"] == "ESCALATE"          # 谎报缓解主路径
        assert out["verification"]["verified"] is False
        assert out["verification"]["confidence"] == 0.6

    def test_legitimate_anchored_allowed(self, client):
        r = client.post("/api/governance/evaluate", json={
            "agent_id": "agent-solver-a",
            "body": {"governance": {"protocols": {"entropy_denoise": {
                "satisfied": True, "output": ["a", "b"]}}}},
        })
        out = r.json()
        assert out["action"] == "ALLOW_WITH_WARNING"
        assert out["verification"]["verified"] is True

    def test_evaluate_writes_audit(self, client):
        before = len(client.get("/api/governance/audit?limit=500").json())
        client.post("/api/governance/evaluate", json={
            "agent_id": "agent-critic-c",
            "body": {"governance": {"protocols": {"feynman_test": {
                "satisfied": True}}}},
        })
        after = len(client.get("/api/governance/audit?limit=500").json())
        assert after == before + 1


# ── 预留: 审计批量写入 ──────────────────────────────────────────────

class TestIngest:
    def test_audit_ingest(self, client):
        r = client.post("/api/governance/audit/ingest", json=[
            {"agent_id": "agent-solver-a", "matched_rule": "external-1",
             "action": "ALLOW_WITH_WARNING", "channel": "baseline"},
            {"agent_id": "agent-solver-b", "matched_rule": "external-2",
             "action": "DENY", "channel": "baseline"},
        ])
        assert r.status_code == 200
        assert r.json()["ingested"] == 2


# ── S69 策略编辑器 (编辑→验证→部署 闭环) ────────────────────────────

# 11 列声明式协议 (编译器从 protocol 块生成 3 条规则: enforce/ethics/ok)
VALID_YAML = """schema_version: 11-col-v1
source: notion:N1 (编辑验证用例)
protocol:
  module: feynman_test
  category: 自我檢核
  level: L2
  core_purpose: 验证理解深度 (编辑器用例)
  metacognitive_q: 我能向新手解释这个协议吗？
  collab_directive: 请用费曼测试检查我的理解
  trigger: 每次新协议入库时
  ethics_boundary: 不用于误导性简化
  source: notion:N1 (编辑验证用例)
  frequency: 每次入库
  strategy: AI 自动审核 + 费曼问答对
  expected_output: 理解深度评分 ≥ 80%
"""

# 缺 expected_output 字段 → 编译器 fail-closed 拒绝
BROKEN_YAML = """schema_version: 11-col-v1
source: notion:N1 (broken)
protocol:
  module: feynman_test
  category: 自我檢核
  level: L2
  core_purpose: 缺字段用例
  metacognitive_q: q
  collab_directive: d
  trigger: t
  ethics_boundary: e
  source: s
  frequency: f
  strategy: st
"""


class TestPolicyEditor:
    def test_protocol_source(self, client):
        r = client.get("/api/governance/policies/feynman_test/source")
        assert r.status_code == 200
        assert "yaml" in r.json()
        assert "feynman_test" in r.json()["yaml"]

    def test_source_404(self, client):
        assert client.get("/api/governance/policies/nope/source").status_code == 404

    def test_validate_ok(self, client):
        r = client.post("/api/governance/policies/validate", json={
            "protocol": "feynman_test", "yaml": VALID_YAML})
        assert r.status_code == 200
        out = r.json()
        assert out["valid"] is True
        assert out["rules_count"] == 3  # enforce/ethics/ok
        assert "DENY" in out["rule_types"] and "ESCALATE" in out["rule_types"]

    def test_validate_broken_missing_field(self, client):
        r = client.post("/api/governance/policies/validate", json={
            "protocol": "feynman_test", "yaml": BROKEN_YAML})
        assert r.status_code == 200
        assert r.json()["valid"] is False
        assert len(r.json()["errors"]) >= 1

    def test_validate_bad_yaml_syntax(self, client):
        r = client.post("/api/governance/policies/validate", json={
            "protocol": "feynman_test", "yaml": "name: [unclosed"})
        assert r.status_code == 200
        assert r.json()["valid"] is False

    def test_validate_missing_schema_version(self, client):
        r = client.post("/api/governance/policies/validate", json={
            "protocol": "feynman_test", "yaml": "protocol:\n  module: x"})
        assert r.status_code == 200
        assert r.json()["valid"] is False
        assert "schema_version" in r.json()["errors"][0]

    def test_validate_path_traversal_blocked(self, client):
        r = client.post("/api/governance/policies/validate", json={
            "protocol": "../../etc/passwd", "yaml": VALID_YAML})
        assert r.status_code == 400  # 白名单拒绝

    def test_deploy_success_and_reload(self, client):
        r = client.post("/api/governance/policies/deploy", json={
            "protocol": "feynman_test", "yaml": VALID_YAML})
        assert r.status_code == 200
        assert r.json()["deployed"] is True
        assert r.json()["rules_count"] == 9      # 全网关规则 (3 协议 × 3)
        assert r.json()["protocol_rules"] == 3   # 本协议规则
        # 部署后策略视图可读
        assert client.get("/api/governance/policies/feynman_test").status_code == 200

    def test_deploy_invalid_rejected(self, client):
        r = client.post("/api/governance/policies/deploy", json={
            "protocol": "feynman_test", "yaml": BROKEN_YAML})
        assert r.status_code == 422  # 验证失败 → 拒绝部署 (422)
        assert r.json()["detail"]["deployed"] is False
# ── A4: API 版本化 (/v1/ 前缀) ─────────────────────────────────────

def test_v1_versioned_health(client):
    """A4: /v1/api/health 可达且标记 api_version。"""
    r = client.get("/v1/api/health")
    assert r.status_code == 200
    assert r.json()["api_version"] == "v1"

def test_v1_auth_login(client):
    """A4: /v1/api/auth/login 与遗留 /api/auth/login 行为一致。"""
    r1 = client.post("/v1/api/auth/login",
                     json={"username": "admin", "password": "admin123"})
    r2 = client.post("/api/auth/login",
                     json={"username": "admin", "password": "admin123"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert "token" in r1.json()

def test_v1_governance_agents_mirrors_legacy(client):
    """A4: /v1/api/governance/agents 与遗留端点返回一致 (挂载生效)。"""
    r1 = client.get("/v1/api/governance/agents")
    r2 = client.get("/api/governance/agents")
    assert r1.status_code == 200
    assert r1.json() == r2.json()

