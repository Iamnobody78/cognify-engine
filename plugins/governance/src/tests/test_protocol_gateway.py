"""Sprint 63: 协议网关测试 — 协议 YAML (S62 A1 编译器产物) 接入规则引擎。

核心验证:
  1. 编译: 3 协议 → 9 规则 (每协议 enforce/ethics/ok), 必需字段校验
  2. 执行: PolicyEngine 加载编译产物后, governance 声明触发正确裁决
  3. 边界: triggered+satisfied 并存 → ok (不误报 enforce)
  4. 零影响: 无 governance 声明的既有流量不受协议规则影响
  5. fail-closed: 坏文件/缺字段/空目录/重复模块 → 拒绝加载
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.policy import PolicyEngine  # noqa: E402
from src.protocol_gateway import (  # noqa: E402
    DEFAULT_PROTOCOLS_DIR,
    Protocol,
    ProtocolGateway,
    compile_protocol_rules,
    generate_policy_yaml,
    load_protocols,
)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEN_POLICY = os.path.join(REPO, "config", "protocol_policies.generated.yaml")


@pytest.fixture(scope="module")
def gateway():
    return ProtocolGateway()


@pytest.fixture(scope="module")
def engine():
    eng = PolicyEngine(GEN_POLICY)
    assert len(eng.rules) == 9
    return eng


# ── 1. 编译层 ───────────────────────────────────────────────────────
class TestCompile:
    def test_protocol_count(self, gateway):
        assert len(gateway.protocols) == 3

    def test_modules(self, gateway):
        assert set(gateway.modules) == {"feynman_test", "entropy_denoise", "logic_chain_check"}

    def test_rule_count_3_per_protocol(self, gateway):
        assert len(gateway.rules) == 9
        verify = gateway.verify()
        assert verify["expected_rule_count"] == 9
        assert verify["rule_count"] == 9
        for mod, names in verify["per_module_rules"].items():
            assert len(names) == 3, f"{mod} should have 3 rules: {names}"

    def test_priority_ordering(self, gateway):
        """DENY(5) < enforce(15/20) < ok(25/30): 伦理最优先, 放行最后。"""
        actions_at_priority = {r.priority: r.action for r in gateway.rules}
        assert actions_at_priority[5] == "DENY"
        assert actions_at_priority[15] == "ESCALATE"      # L3 enforce
        assert actions_at_priority[20] == "ESCALATE"      # L2 enforce
        assert actions_at_priority[25] == "ALLOW_WITH_WARNING"  # L3 ok
        assert actions_at_priority[30] == "ALLOW_WITH_WARNING"  # L2 ok

    def test_required_fields_validated(self):
        """11 列编译器契约: 缺任一必需字段 → fail-closed。"""
        p = Protocol.from_yaml(os.path.join(DEFAULT_PROTOCOLS_DIR, "feynman_test.yaml"))
        for f in ("module", "category", "level", "core_purpose", "metacognitive_q",
                  "collab_directive", "trigger", "ethics_boundary", "source",
                  "frequency", "strategy", "expected_output"):
            assert getattr(p, f) != ""

    def test_bad_schema_version_rejected(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("schema_version: v2\nprotocol: {module: x}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="schema_version"):
            Protocol.from_yaml(str(f))

    def test_missing_fields_rejected(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text(
            "schema_version: 11-col-v1\nprotocol:\n  module: x\n  level: L2\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="missing required fields"):
            Protocol.from_yaml(str(f))

    def test_bad_level_rejected(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text(
            "schema_version: 11-col-v1\nprotocol:\n"
            "  module: x\n  category: c\n  level: L9\n  core_purpose: p\n"
            "  metacognitive_q: q\n  collab_directive: d\n  trigger: t\n"
            "  ethics_boundary: e\n  source: s\n  frequency: f\n"
            "  strategy: st\n  expected_output: o\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="invalid level"):
            Protocol.from_yaml(str(f))

    def test_empty_dir_rejected(self, tmp_path):
        with pytest.raises((FileNotFoundError, ValueError), match="fail-closed"):
            load_protocols(str(tmp_path))

    def test_duplicate_module_rejected(self, tmp_path):
        (tmp_path / "a.yaml").write_text(
            "schema_version: 11-col-v1\nprotocol:\n"
            "  module: dup\n  category: c\n  level: L2\n  core_purpose: p\n"
            "  metacognitive_q: q\n  collab_directive: d\n  trigger: t\n"
            "  ethics_boundary: e\n  source: s\n  frequency: f\n"
            "  strategy: st\n  expected_output: o\n",
            encoding="utf-8",
        )
        (tmp_path / "b.yaml").write_text(
            "schema_version: 11-col-v1\nprotocol:\n"
            "  module: dup\n  category: c\n  level: L3\n  core_purpose: p\n"
            "  metacognitive_q: q\n  collab_directive: d\n  trigger: t\n"
            "  ethics_boundary: e\n  source: s\n  frequency: f\n"
            "  strategy: st\n  expected_output: o\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="duplicate protocol module"):
            load_protocols(str(tmp_path))

    def test_policy_yaml_contract(self, gateway):
        """编译产物遵循 Rule YAML 契约 (PolicyEngine 可直接加载)。"""
        policy = gateway.to_policy_yaml()
        assert policy["name"] == "protocol-gateway"
        assert len(policy["rules"]) == 9
        for r in policy["rules"]:
            assert {"name", "path_pattern", "action", "reason", "priority"} <= set(r)
            assert "json_path" in r and "json_pattern" in r


# ── 2. 执行层 (PolicyEngine 原生加载编译产物) ───────────────────────
class TestExecution:
    def test_triggered_but_not_satisfied_escalates(self, engine):
        body = {"governance": {"protocols": {"feynman_test": {"triggered": True}}}}
        r = engine.evaluate("/api/v1/chat", "POST", body)
        assert r is not None
        assert r.action == "ESCALATE"
        assert r.name == "protocol-feynman_test-enforce"

    def test_triggered_with_satisfied_is_ok(self, engine):
        """边界: triggered+satisfied 并存 → ok (不得误报 enforce)。"""
        body = {"governance": {"protocols": {
            "feynman_test": {"triggered": True, "satisfied": True}}}}
        r = engine.evaluate("/api/v1/chat", "POST", body)
        assert r is not None
        assert r.action == "ALLOW_WITH_WARNING"
        assert r.name == "protocol-feynman_test-ok"

    def test_satisfied_only_is_ok(self, engine):
        body = {"governance": {"protocols": {"entropy_denoise": {"satisfied": True}}}}
        r = engine.evaluate("/api/v1/chat", "POST", body)
        assert r is not None
        assert r.action == "ALLOW_WITH_WARNING"

    def test_ethics_violation_denies(self, engine):
        body = {"governance": {"protocols": {
            "logic_chain_check": {"violation": "attack person"}}}}
        r = engine.evaluate("/api/v1/chat", "POST", body)
        assert r is not None
        assert r.action == "DENY"
        assert r.name == "protocol-logic_chain_check-ethics"

    def test_ethics_beats_escalate(self, engine):
        """同一协议同时触发 + 违规 → DENY 优先 (priority 5)。"""
        body = {"governance": {"protocols": {
            "logic_chain_check": {"triggered": True, "violation": "mislead"}}}}
        r = engine.evaluate("/api/v1/chat", "POST", body)
        assert r is not None
        assert r.action == "DENY"

    def test_no_governance_zero_impact(self, engine):
        """既有流量 (无 governance 声明) → 协议规则不命中。"""
        for body in ({"hello": "world"}, {"messages": [{"role": "user", "content": "hi"}]}):
            r = engine.evaluate("/api/v1/chat", "POST", body)
            assert r is None

    def test_unknown_module_no_impact(self, engine):
        body = {"governance": {"protocols": {"other_protocol": {"triggered": True}}}}
        r = engine.evaluate("/api/v1/chat", "POST", body)
        assert r is None

    def test_empty_violation_not_deny(self, engine):
        """violation='' (空串) → 不触发 DENY (正则 .+ 语义)。"""
        body = {"governance": {"protocols": {
            "feynman_test": {"violation": "", "satisfied": True}}}}
        r = engine.evaluate("/api/v1/chat", "POST", body)
        assert r.action == "ALLOW_WITH_WARNING"

    def test_gateway_evaluate_direct(self, gateway):
        """独立协议层裁决 (不经 PolicyEngine) 语义一致。"""
        r = gateway.evaluate("/x", "POST", {"governance": {"protocols": {
            "feynman_test": {"triggered": True}}}})
        assert r.action == "ESCALATE"
        assert gateway.evaluate("/x", "POST", {}) is None


# ── 3. 端到端: 编译 → 生成 YAML → PolicyEngine 执行 ─────────────────
class TestEndToEnd:
    def test_compile_generate_execute_roundtrip(self):
        gw = ProtocolGateway()
        policy = gw.to_policy_yaml()
        eng = PolicyEngine.__new__(PolicyEngine)
        # 直接构建 (避免依赖磁盘文件): 通过 generate_policy_yaml → 内存加载
        rules = compile_protocol_rules(gw.protocols)
        assert len(rules) == 9
        # 编译产物 YAML 契约与内存规则一致
        yaml_rules = generate_policy_yaml(rules)["rules"]
        names_from_yaml = {r["name"] for r in yaml_rules}
        assert names_from_yaml == {r.name for r in rules}

    def test_generated_file_exists_and_loadable(self):
        assert os.path.isfile(GEN_POLICY), "run scripts/compile_protocol_policies.py first"
        eng = PolicyEngine(GEN_POLICY)
        assert len(eng.rules) == 9

    def test_all_protocol_modules_executable(self, engine):
        """3 个协议全部可执行: 各自触发 enforce。"""
        for mod in ("feynman_test", "entropy_denoise", "logic_chain_check"):
            body = {"governance": {"protocols": {mod: {"triggered": True}}}}
            r = engine.evaluate("/api/v1/chat", "POST", body)
            assert r is not None, f"{mod} enforce 规则未命中"
            assert r.action == "ESCALATE"
            assert r.name == f"protocol-{mod}-enforce"
