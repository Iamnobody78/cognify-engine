"""Sprint 66: 验证通道测试 (declaration_only 盲点缓解)。

核心验证 (T2 — 接口):
  1. 构造器注入: ProtocolGateway(validator=...) 生效
  2. set_validator 热切换
  3. 默认 NoopValidator (诚实边界, 无验证器时行为与 S65 一致)
  4. verify_declaration 单条验证调用
  5. evaluate_verified 语义: 放行声明验证失败 → ESCALATE 降级

核心验证 (T3 — 基线验证器):
  6. violation+satisfied 矛盾声明 → verified=False (c=0.95)
  7. satisfied+证据锚点 → verified=True (c=0.8)
  8. satisfied 无锚点 → verified=False (c=0.6) (盲点缓解主路径)
  9. 协议状态缺失/非 dict → verified=False (c=0.9)
 10. 非声明依赖规则 (ethics) → 平凡通过

VCE 联动 (PM 验收项):
 11. 带 verification_channel 扫描 → declaration_only 盲点消失
 12. 无通道扫描 → 行为与 S65 一致 (declaration_only 保留)
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.protocol_gateway import ProtocolGateway  # noqa: E402
from src.verification import (  # noqa: E402
    BaselineDeclarationValidator,
    LLMSemanticValidator,
    NoopValidator,
    VerificationResult,
)
from src.vce_scanner import vce_scan_rules  # noqa: E402


@pytest.fixture(scope="module")
def gateway():
    return ProtocolGateway()


@pytest.fixture(scope="module")
def rules_by_name(gateway):
    return {r.name: r for r in gateway.rules}


# ── T2: 验证器接口 ───────────────────────────────────────────────────

class TestValidatorInjection:
    def test_constructor_injection(self, gateway):
        gw = ProtocolGateway(validator=BaselineDeclarationValidator())
        assert gw.validator.name == "baseline"

    def test_default_noop_validator(self, gateway):
        assert gateway.validator.name == "none"
        assert isinstance(gateway.validator, NoopValidator)

    def test_set_validator_hot_swap(self, gateway):
        gw = ProtocolGateway()
        assert gw.validator.name == "none"
        gw.set_validator(BaselineDeclarationValidator())
        assert gw.validator.name == "baseline"
        gw.set_validator(NoopValidator())
        assert gw.validator.name == "none"

    def test_noop_returns_verified_false(self, gateway):
        res = gateway.verify_declaration(gateway.rules[0], "/gateway", "POST", {})
        assert res.verified is False
        assert res.confidence == 0.0
        assert res.validator == "none"
        assert isinstance(res, VerificationResult)


class TestVerifyDeclaration:
    def test_baseline_invoked_on_ok_rule(self, gateway, rules_by_name):
        gw = ProtocolGateway(validator=BaselineDeclarationValidator())
        rule = rules_by_name["protocol-feynman_test-ok"]
        body = {"governance": {"protocols": {"feynman_test": {"satisfied": True}}}}
        res = gw.verify_declaration(rule, "/gateway", "POST", body)
        assert res.validator == "baseline"
        assert res.verified is False  # 无证据锚点 → 零成本谎报被阻断
        assert res.confidence == 0.6

    def test_evaluate_verified_ok_downgrade_on_unverified(self, gateway, rules_by_name):
        """谎报缓解主路径: ok 规则 + 声明验证失败 → action 降级为 ESCALATE。"""
        gw = ProtocolGateway(validator=BaselineDeclarationValidator())
        body = {"governance": {"protocols": {"feynman_test": {"satisfied": True}}}}
        out = gw.evaluate_verified("/gateway", "POST", body)
        assert out["rule"] == "protocol-feynman_test-ok"
        assert out["action"] == "ESCALATE"
        assert out["verification"]["verified"] is False
        assert out["channel"] == "baseline"

    def test_evaluate_verified_ok_allow_when_anchored(self, gateway, rules_by_name):
        """合法声明 (含证据锚点) 不误伤: 维持 ALLOW_WITH_WARNING。"""
        gw = ProtocolGateway(validator=BaselineDeclarationValidator())
        body = {"governance": {"protocols": {"feynman_test": {
            "satisfied": True, "evidence": "feynman_check_passed"}}}}
        out = gw.evaluate_verified("/gateway", "POST", body)
        assert out["rule"] == "protocol-feynman_test-ok"
        assert out["action"] == "ALLOW_WITH_WARNING"
        assert out["verification"]["verified"] is True

    def test_evaluate_verified_noop_no_downgrade(self, gateway):
        """向后兼容: NoopValidator 不降级 (S65 行为保持)。"""
        body = {"governance": {"protocols": {"feynman_test": {"satisfied": True}}}}
        out = gateway.evaluate_verified("/gateway", "POST", body)
        assert out["rule"] == "protocol-feynman_test-ok"
        assert out["action"] == "ALLOW_WITH_WARNING"  # 不降级
        assert out["verification"]["verified"] is False
        assert out["channel"] == "none"

    def test_evaluate_verified_no_match(self, gateway):
        out = gateway.evaluate_verified("/other", "GET", {})
        assert out["rule"] is None
        assert out["action"] is None
        assert out["verification"] is None


# ── T3: 基线验证器五项检查 ──────────────────────────────────────────

class TestBaselineValidator:
    def test_violation_satisfied_contradiction(self, rules_by_name):
        v = BaselineDeclarationValidator()
        rule = rules_by_name["protocol-feynman_test-ok"]
        body = {"governance": {"protocols": {"feynman_test": {
            "satisfied": True, "violation": "x1y2"}}}}
        res = v.validate(rule, "/gateway", "POST", body)
        assert res.verified is False
        assert res.confidence == 0.95
        assert "矛盾" in res.reason

    def test_evidence_anchor_verified(self, rules_by_name):
        v = BaselineDeclarationValidator()
        rule = rules_by_name["protocol-entropy_denoise-ok"]
        body = {"governance": {"protocols": {"entropy_denoise": {
            "satisfied": True, "output": ["去噪要点1", "去噪要点2"]}}}}
        res = v.validate(rule, "/gateway", "POST", body)
        assert res.verified is True
        assert res.confidence == 0.8

    def test_no_anchor_unverified(self, rules_by_name):
        """盲点缓解主路径: satisfied=true 无任何锚点 → 不可信。"""
        v = BaselineDeclarationValidator()
        rule = rules_by_name["protocol-logic_chain_check-ok"]
        body = {"governance": {"protocols": {"logic_chain_check": {
            "satisfied": True}}}}
        res = v.validate(rule, "/gateway", "POST", body)
        assert res.verified is False
        assert res.confidence == 0.6

    def test_missing_state_malformed(self, rules_by_name):
        v = BaselineDeclarationValidator()
        rule = rules_by_name["protocol-feynman_test-ok"]
        res = v.validate(rule, "/gateway", "POST", {})  # 无 governance 声明
        assert res.verified is False
        assert res.confidence == 0.9
        res2 = v.validate(rule, "/gateway", "POST",
                          {"governance": {"protocols": {"feynman_test": "not-a-dict"}}})
        assert res2.verified is False
        assert res2.confidence == 0.9

    def test_ethics_rule_trivial_pass(self, rules_by_name):
        v = BaselineDeclarationValidator()
        rule = rules_by_name["protocol-feynman_test-ethics"]
        body = {"governance": {"protocols": {"feynman_test": {"satisfied": True}}}}
        res = v.validate(rule, "/gateway", "POST", body)
        assert res.verified is True
        assert res.confidence == 1.0

    def test_not_satisfied_no_claim(self, rules_by_name):
        """未声明 satisfied → 无放行声明可验证 (平凡通过, enforce 路径不受影响)。"""
        v = BaselineDeclarationValidator()
        rule = rules_by_name["protocol-feynman_test-ok"]
        body = {"governance": {"protocols": {"feynman_test": {"triggered": True}}}}
        res = v.validate(rule, "/gateway", "POST", body)
        assert res.verified is True
        assert res.confidence == 1.0


# ── S68 审计回调钩子 ────────────────────────────────────────────────

class TestAuditSink:
    def test_audit_sink_invoked_on_evaluate_verified(self, gateway):
        events = []
        gw = ProtocolGateway(validator=BaselineDeclarationValidator(),
                             audit_sink=events.append)
        body = {"governance": {"protocols": {"feynman_test": {"satisfied": True}}}}
        gw.evaluate_verified("/gateway", "POST", body)
        assert len(events) == 1
        ev = events[0]
        assert ev["rule"] == "protocol-feynman_test-ok"
        assert ev["action"] == "ESCALATE"  # 验证失败降级
        assert ev["path"] == "/gateway" and ev["method"] == "POST"
        assert ev["body"] == body
        assert ev["verification"]["validator"] == "baseline"

    def test_audit_sink_default_none(self, gateway):
        assert gateway.audit_sink is None

    def test_audit_sink_no_match_no_event(self):
        events = []
        gw = ProtocolGateway(validator=BaselineDeclarationValidator(),
                             audit_sink=events.append)
        gw.evaluate_verified("/other", "GET", {})
        assert len(events) == 0  # 无命中规则 → 无裁决事件

    def test_audit_sink_failure_does_not_break_verdict(self):
        def bad_sink(event):
            raise RuntimeError("audit store down")
        gw = ProtocolGateway(validator=BaselineDeclarationValidator(),
                             audit_sink=bad_sink)
        body = {"governance": {"protocols": {"feynman_test": {"satisfied": True}}}}
        out = gw.evaluate_verified("/gateway", "POST", body)
        # fail-open 审计: 审计存储故障不影响治理裁决
        assert out["action"] == "ESCALATE"
        assert out["verification"]["verified"] is False


# ── VCE 联动 (PM 验收项) ─────────────────────────────────────────────

class TestVceLinkage:
    def test_channel_suppresses_declaration_only(self, gateway):
        """带验证通道扫描 → declaration_only 盲点从报告中消失。"""
        intro = gateway.introspect()
        rule_mces = []
        for mod, rmcs in intro["protocols"].items():
            rule_mces.extend(rmcs)
        report = vce_scan_rules(rule_mces, rules=gateway.rules,
                                modules_expected=gateway.modules,
                                verification_channel="baseline")
        cats = [s["category"] for s in report["BlindSpots"]]
        assert "declaration_only" not in cats
        assert report["Verification_Channel"]["enabled"] is True
        assert report["Verification_Channel"]["validator"] == "baseline"
        assert "深层语义谎报" in report["honest_boundary"]["does_not_detect"][0]

    def test_no_channel_keeps_declaration_only(self, gateway):
        """无通道扫描 (S65 兼容) → declaration_only 盲点保留。"""
        intro = gateway.introspect()
        rule_mces = []
        for mod, rmcs in intro["protocols"].items():
            rule_mces.extend(rmcs)
        report = vce_scan_rules(rule_mces, rules=gateway.rules,
                                modules_expected=gateway.modules)
        cats = [s["category"] for s in report["BlindSpots"]]
        assert "declaration_only" in cats
        assert report["Verification_Channel"]["enabled"] is False

    def test_gateway_scan_uses_validator_name(self):
        """ProtocolGateway.scan() 自动携带验证器名称 → 报告一致。"""
        gw = ProtocolGateway(validator=BaselineDeclarationValidator())
        report = gw.scan()
        assert report["Verification_Channel"]["validator"] == "baseline"
        cats = [s["category"] for s in report["BlindSpots"]]
        assert "declaration_only" not in cats


# ── S1: LLM 语义验证器 (策略 A 插槽) ─────────────────────────────────

class TestLLMSemanticValidator:
    """S1 审计缺陷修复: LLM 语义验证层 (fail-open 组合策略)。"""

    def _anchored_body(self):
        """带真实锚点的声明 (基线通过, 需要语义复核)。"""
        return {"governance": {"protocols": {"logic_chain_check": {
            "satisfied": True, "evidence": "logic_chain_check_passed"}}}}

    def _fake_anchored_body(self):
        """锚点存在但语义不支撑 satisfied=true (语义伪造样本)。"""
        return {"governance": {"protocols": {"logic_chain_check": {
            "satisfied": True, "evidence": "logic_chain_check_failed"}}}}

    def _rule(self, gateway):
        return {r.name: r for r in gateway.rules}["protocol-logic_chain_check-ok"]

    # -- fail-open: LLM 缺席 -------------------------------------------

    def test_no_provider_fails_open_to_baseline(self, gateway):
        """未注入 LLM → 回退基线判定, 锚点存在则 verified=True。"""
        v = LLMSemanticValidator(llm_provider=None)
        res = v.validate(self._rule(gateway), "/v1/agents", "POST",
                         self._anchored_body())
        assert res.validator == "semantic-llm"
        assert res.verified is True
        assert "semantic-llm-unavailable" in res.reason

    def test_no_provider_still_blocks_zero_cost_lie(self, gateway):
        """未注入 LLM 时基线拦截仍生效 (零成本谎报 → verified=False)。"""
        v = LLMSemanticValidator(llm_provider=None)
        res = v.validate(self._rule(gateway), "/v1/agents", "POST", {})
        assert res.verified is False
        assert res.confidence >= 0.6

    # -- fail-open: LLM 异常 / 超时 -------------------------------------

    def test_provider_exception_fails_open(self, gateway):
        def boom(ctx):
            raise RuntimeError("llm down")

        v = LLMSemanticValidator(llm_provider=boom, timeout=0.5)
        res = v.validate(self._rule(gateway), "/v1/agents", "POST",
                         self._anchored_body())
        assert res.verified is True          # 回退基线 → 不误伤
        assert "semantic-llm-unavailable" in res.reason

    def test_provider_timeout_fails_open(self, gateway):
        def slow(ctx):
            import time
            time.sleep(2.0)
            return {"verified": True, "confidence": 0.9, "reason": "late"}

        v = LLMSemanticValidator(llm_provider=slow, timeout=0.3)
        res = v.validate(self._rule(gateway), "/v1/agents", "POST",
                         self._anchored_body())
        assert res.verified is True
        assert "semantic-llm-unavailable" in res.reason

    def test_malformed_provider_output_fails_open(self, gateway):
        v = LLMSemanticValidator(llm_provider=lambda ctx: "not-a-dict",
                                 timeout=0.5)
        res = v.validate(self._rule(gateway), "/v1/agents", "POST",
                         self._anchored_body())
        assert res.verified is True
        assert "semantic-llm-unavailable" in res.reason

    # -- 语义复核: 拦截 / 通过 -----------------------------------------

    def test_semantic_intercept_fake_evidence(self, gateway):
        """锚点存在但 LLM 判定语义伪造 → verified=False (S1 核心)。"""

        def judge(ctx):
            out = ctx["protocol_state"]["evidence"]
            return {"verified": out == "logic_chain_check_passed",
                    "confidence": 0.95,
                    "reason": f"evidence={out} vs satisfied=true"}

        v = LLMSemanticValidator(llm_provider=judge, timeout=0.5)
        res = v.validate(self._rule(gateway), "/v1/agents", "POST",
                         self._fake_anchored_body())
        assert res.verified is False
        assert res.confidence == pytest.approx(0.95)

    def test_semantic_confirm_legit_evidence(self, gateway):
        """锚点 + LLM 语义一致 → verified=True, 置信度取保守值。"""

        def judge(ctx):
            return {"verified": True, "confidence": 0.99,
                    "reason": "evidence consistent"}

        v = LLMSemanticValidator(llm_provider=judge, timeout=0.5)
        res = v.validate(self._rule(gateway), "/v1/agents", "POST",
                         self._anchored_body())
        assert res.verified is True
        assert res.confidence <= 0.99          # min(基线0.8, LLM0.99)
        assert "语义复核通过" in res.reason

    # -- 网关集成 ------------------------------------------------------

    def test_gateway_with_llm_validation(self, gateway):
        """with_llm_validation 工厂 → 通道 = semantic-llm。"""
        gw = ProtocolGateway.with_llm_validation(
            llm_provider=lambda ctx: {"verified": True, "confidence": 0.9,
                                      "reason": "ok"},
            timeout=0.5)
        assert gw.validator.name == "semantic-llm"

    def test_gateway_escalates_on_semantic_fake(self, gateway):
        """语义伪造 → 网关将 ALLOW_WITH_WARNING 降级为 ESCALATE。"""

        def judge(ctx):
            out = ctx["protocol_state"]["evidence"]
            return {"verified": out == "logic_chain_check_passed",
                    "confidence": 0.95,
                    "reason": "semantic check"}

        gw = ProtocolGateway.with_llm_validation(llm_provider=judge,
                                                 timeout=0.5)
        verdict = gw.evaluate_verified(
            "/v1/agents", "POST", self._fake_anchored_body())
        assert verdict["action"] == "ESCALATE"
        assert verdict["verification"]["verified"] is False

    def test_gateway_allows_legit_under_llm(self, gateway):
        """合法声明 + LLM 语义通过 → 保持 ALLOW_WITH_WARNING。"""
        gw = ProtocolGateway.with_llm_validation(
            llm_provider=lambda ctx: {"verified": True, "confidence": 0.9,
                                      "reason": "ok"},
            timeout=0.5)
        verdict = gw.evaluate_verified(
            "/v1/agents", "POST", self._anchored_body())
        assert verdict["action"] == "ALLOW_WITH_WARNING"
        assert verdict["verification"]["verified"] is True
        assert verdict["channel"] == "semantic-llm"
