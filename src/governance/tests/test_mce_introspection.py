"""Sprint 64 (Phase 1): MCE 2.0 AST 自省测试 — 治理规则可反问"我为什么存在"。

核心验证:
  1. AST 契约: mce_compile 输出对齐 meta_edu MCE 2.0 契约 (5 字段)
  2. 自省接口: why_exists / what_it_governs / constraints 可回答
  3. 溯源: 规则 AST 携带协议 origin (module/level/trigger/ethics/output)
  4. 张力: 每规则类型检测潜在冲突 (enforce vs ok / ethics 优先 / ok 声明风险)
  5. 完整性: 3 协议 × 3 规则全部编译, 无遗漏
  6. 复用: build_mce_introspection 从 S63 协议+规则直接构建
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.mce_introspection import (  # noqa: E402
    AST_KEYS,
    ProtocolMCE,
    RuleMCE,
    build_mce_introspection,
)
from src.protocol_gateway import ProtocolGateway  # noqa: E402


@pytest.fixture(scope="module")
def gw():
    return ProtocolGateway()


@pytest.fixture(scope="module")
def introspection(gw):
    return build_mce_introspection(gw.protocols, gw.rules)


# ── 1. AST 契约 ─────────────────────────────────────────────────────
class TestASTContract:
    def test_ast_has_all_contract_fields(self, introspection):
        for pms in introspection:
            for rmc in pms.rule_mces:
                ast = rmc.compile()
                for key in AST_KEYS:
                    assert key in ast, f"{rmc.rule.name} 缺 {key}"

    def test_core_directive_answers_why(self, introspection):
        """Core_Directive 回答"为什么存在": 含规则类型语义 + 协议名。"""
        for pms in introspection:
            for rmc in pms.rule_mces:
                why = rmc.why_exists()
                assert pms.protocol_module in why
                assert rmc.rule.name in why

    def test_entities_extracted(self, introspection):
        """Entities 非空且含协议模块名。"""
        for pms in introspection:
            entities = pms.summary()["entities"]
            assert len(entities) >= 1
            assert pms.protocol_module in entities

    def test_entropy_in_range(self, introspection):
        for pms in introspection:
            for rmc in pms.rule_mces:
                e = rmc.ast["Entropy_Score"]
                assert 0.1 <= e <= 0.9


# ── 2. 自省接口 ─────────────────────────────────────────────────────
class TestIntrospectionAPI:
    def test_why_exists(self, introspection):
        """规则可反问"我为什么存在"。"""
        rmc = introspection[0].rule_mces[0]
        why = rmc.why_exists()
        assert isinstance(why, str) and len(why) > 10

    def test_what_it_governs(self, introspection):
        """规则可回答"我在治理什么"。"""
        rmc = introspection[0].rule_mces[0]
        governs = rmc.what_it_governs()
        assert isinstance(governs, list) and len(governs) >= 1

    def test_constraints(self, introspection):
        """规则可列出结构约束。"""
        for pms in introspection:
            for rmc in pms.rule_mces:
                cons = rmc.constraints()
                assert len(cons) >= 1
                assert any("trigger" in c for c in cons)

    def test_rule_types_all_present(self, introspection):
        types = set()
        for pms in introspection:
            types.update(pms.summary()["rule_types"])
        assert types == {"ethics", "enforce", "ok"}


# ── 3. 溯源 ─────────────────────────────────────────────────────────
class TestOrigin:
    def test_origin_traceability(self, introspection):
        """规则 AST 携带完整协议溯源。"""
        for pms in introspection:
            for rmc in pms.rule_mces:
                d = rmc.to_dict()
                assert d["origin"]["trigger"] != ""
                assert d["origin"]["ethics_boundary"] != ""
                assert d["origin"]["expected_output"] != ""
                assert d["origin"]["core_purpose"] != ""

    def test_serializable(self, introspection):
        import json
        for pms in introspection:
            for rmc in pms.rule_mces:
                d = rmc.to_dict()
                # 必须可 JSON 序列化 (可审计/可版本化)
                s = json.dumps(d, ensure_ascii=False)
                assert len(s) > 50


# ── 4. 张力向量 ─────────────────────────────────────────────────────
class TestTensions:
    def test_enforce_tension_notes_boundary(self, introspection):
        """enforce 规则张力: 必须提及 triggered+satisfied 并存误报防护。"""
        for pms in introspection:
            for rmc in pms.rule_mces:
                if rmc.rule_type == "enforce":
                    assert any("负向前瞻" in t or "并存" in t for t in rmc.ast["Tension_Vectors"])

    def test_ethics_tension_notes_priority(self, introspection):
        for pms in introspection:
            for rmc in pms.rule_mces:
                if rmc.rule_type == "ethics":
                    assert any("priority" in t or "压过" in t for t in rmc.ast["Tension_Vectors"])

    def test_ok_tension_notes_declaration_risk(self, introspection):
        for pms in introspection:
            for rmc in pms.rule_mces:
                if rmc.rule_type == "ok":
                    assert any("声明" in t for t in rmc.ast["Tension_Vectors"])


# ── 5. 完整性 ───────────────────────────────────────────────────────
class TestCompleteness:
    def test_all_protocols_introspected(self, introspection):
        modules = {pms.protocol_module for pms in introspection}
        assert modules == {"feynman_test", "entropy_denoise", "logic_chain_check"}

    def test_3_rules_per_protocol(self, introspection):
        for pms in introspection:
            assert len(pms.rule_mces) == 3

    def test_rule_count_total(self, introspection):
        total = sum(len(pms.rule_mces) for pms in introspection)
        assert total == 9

    def test_protocol_mce_summary(self, introspection):
        for pms in introspection:
            s = pms.summary()
            assert s["rule_count"] == 3
            assert len(s["why_exists"]) == 3


# ── 6. 复用 (直接自建) ──────────────────────────────────────────────
class TestDirectBuild:
    def test_rule_mce_direct(self):
        from src.policy import Rule
        r = Rule(name="protocol-feynman_test-enforce", path_pattern="*",
                 action="ESCALATE", priority=20, reason="x")
        rmc = RuleMCE(rule=r, protocol_module="feynman_test", rule_type="enforce",
                      trigger_text="每次新协议入库时", ethics_boundary="不用于误导性简化",
                      expected_output="理解深度评分 ≥ 80%", level="L2",
                      core_purpose="验证理解深度")
        ast = rmc.compile()
        assert ast["Core_Directive"]
        assert "feynman_test" in rmc.why_exists()
        assert "每次新协议入库时" in rmc.constraints()[0]

    def test_empty_protocols_ok(self, gw):
        intro = build_mce_introspection([], [])
        assert intro == []

    def test_gateway_introspect_integration(self, gw):
        """ProtocolGateway.introspect() 集成点: S63 产物 → S64 自省。"""
        intro = gw.introspect()
        assert intro["version"] == "MCE-2.0"
        assert set(intro["protocols"].keys()) == {
            "feynman_test", "entropy_denoise", "logic_chain_check"}
        total = sum(len(rmcs) for rmcs in intro["protocols"].values())
        assert total == 9
        # 每条规则 AST 可审计
        for mod, rmcs in intro["protocols"].items():
            for rmc in rmcs:
                assert rmc["rule"].startswith(f"protocol-{mod}-")
                assert rmc["origin"]["trigger"] != ""
                assert "Core_Directive" in rmc["ast"]
