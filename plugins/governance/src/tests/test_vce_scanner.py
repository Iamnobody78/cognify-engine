"""Sprint 65 (Phase 2): VCE 2.0 扫描器测试 — 治理规则"自审"冲突与盲点。

核心验证:
  1. 契约: 扫描报告含 VCE 2.0 三字段 (Polarization_Index/Value_Tensions/
     Asymmetric_Perspectives) + 扩展 (RuleConflicts/BlindSpots)
  2. 极化: 多 action + priority 差距 → 极化系数合理范围 [0,1]
  3. 张力: 伦理 vs 执行 vs 放行 两两张力检出
  4. 冲突: priority_collision / condition_overlap / action_ambiguity
  5. 盲点: missing_rule_type / declaration_only
  6. 集成: ProtocolGateway.scan() 产出 vce_scan_report (与 introspect 并列)
  7. HONEST-BOUNDARY: honest_boundary 声明检测能力边界
  8. 空输入: 空规则集 → 安全扫描
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.protocol_gateway import ProtocolGateway  # noqa: E402
from src.vce_scanner import (  # noqa: E402
    VCE_KEYS,
    EXTRA_KEYS,
    RuleConflict,
    BlindSpot,
    summarize_scan,
    vce_scan_rules,
)


@pytest.fixture(scope="module")
def gw():
    return ProtocolGateway()


@pytest.fixture(scope="module")
def rule_mces(gw):
    intro = gw.introspect()
    mces = []
    for mod, rmcs in intro["protocols"].items():
        for rmc in rmcs:
            mces.append(rmc)
    return mces


@pytest.fixture(scope="module")
def report(rule_mces):
    return vce_scan_rules(rule_mces)


# ── 1. 契约 ─────────────────────────────────────────────────────────
class TestContract:
    def test_vce_contract_fields(self, report):
        for key in VCE_KEYS:
            assert key in report, f"缺 VCE 2.0 契约字段 {key}"

    def test_extended_fields(self, report):
        for key in EXTRA_KEYS:
            assert key in report

    def test_polarization_in_range(self, report):
        p = report["Polarization_Index"]
        assert 0.0 <= p <= 1.0

    def test_serializable(self, report):
        s = json.dumps(report, ensure_ascii=False)
        assert len(s) > 100

    def test_scan_meta(self, report):
        assert report["scanned_rule_count"] == 9
        assert report["conflict_count"] == len(report["RuleConflicts"])
        assert report["blindspot_count"] == len(report["BlindSpots"])


# ── 2. 极化与张力 ───────────────────────────────────────────────────
class TestPolarityTensions:
    def test_polarity_positive_with_diverse_actions(self, report):
        """9 规则含 3 种 action (ethics/enforce/ok) → 极化应 > 0。"""
        assert report["Polarization_Index"] > 0.0

    def test_value_tensions_detected(self, report):
        """伦理 vs 执行 vs 放行两两张力。"""
        joined = " ".join(report["Value_Tensions"])
        assert "伦理" in joined or "ethical" in joined.lower()

    def test_asymmetry_detected(self, report):
        """声明依赖不对称 (enforce/ok 无独立验证通道)。"""
        assert len(report["Asymmetric_Perspectives"]) >= 1
        assert any("satisfied" in a or "声明" in a for a in report["Asymmetric_Perspectives"])

    def test_empty_scan_safe(self):
        r = vce_scan_rules([])
        assert r["Polarization_Index"] == 0.0
        assert r["scanned_rule_count"] == 0
        assert r["RuleConflicts"] == []


# ── 3. 冲突检测 ─────────────────────────────────────────────────────
class TestConflicts:
    def test_condition_overlap_detected(self, report):
        """enforce/ok 同域重叠 (S63 负向前瞻防护的再验证) — 预期 low 危。"""
        kinds = {c["kind"] for c in report["RuleConflicts"]}
        assert "condition_overlap" in kinds

    def test_action_ambiguity_detected(self, report):
        """ethics(DENY) vs ok(ALLOW) 同域并存 — 预期 low 危。"""
        kinds = {c["kind"] for c in report["RuleConflicts"]}
        assert "action_ambiguity" in kinds

    def test_conflict_fields(self, report):
        for c in report["RuleConflicts"]:
            assert {"rule_a", "rule_b", "kind", "severity", "reason"} <= set(c)
            assert c["severity"] in ("high", "medium", "low")

    def test_no_priority_collision_in_baseline(self, report):
        """基线: 9 规则 priority 唯一 (5/15/20/25/30) → 无 priority_collision。"""
        for c in report["RuleConflicts"]:
            assert c["kind"] != "priority_collision"

    def test_synthetic_priority_collision(self):
        """构造 priority 冲突 → 检出 high 危。"""
        mces = [
            {"rule": "r1", "rule_type": "ethics", "priority": 5, "ast": {}},
            {"rule": "r2", "rule_type": "enforce", "priority": 5, "ast": {}},
        ]
        r = vce_scan_rules(mces)
        hits = [c for c in r["RuleConflicts"] if c["kind"] == "priority_collision"]
        assert len(hits) >= 1
        assert hits[0]["severity"] == "high"


# ── 4. 盲点 ─────────────────────────────────────────────────────────
class TestBlindspots:
    def test_declaration_only_detected(self, report):
        """全部裁决依赖 agent 声明 — 恶意谎报风险。"""
        cats = {s["category"] for s in report["BlindSpots"]}
        assert "declaration_only" in cats

    def test_missing_rule_type_detected(self, gw):
        """构造缺 ok 规则的模块 → 检出 missing_rule_type。"""
        mces = [
            {"rule": "protocol-x-enforce", "rule_type": "enforce", "priority": 15,
             "ast": {}, "origin": {}},
            {"rule": "protocol-x-ethics", "rule_type": "ethics", "priority": 5,
             "ast": {}, "origin": {}},
        ]
        r = vce_scan_rules(mces)
        hits = [s for s in r["BlindSpots"] if s["category"] == "missing_rule_type"]
        assert any("x" in s["description"] for s in hits)
        assert any("ok" in s["description"] for s in hits)

    def test_full_baseline_no_missing(self, report):
        """基线 3 模块 × 3 规则全齐 → 无 missing_rule_type。"""
        for s in report["BlindSpots"]:
            assert s["category"] != "missing_rule_type"


# ── 5. 集成 (ProtocolGateway.scan) ─────────────────────────────────
class TestGatewayScan:
    def test_scan_method_exists(self, gw):
        assert hasattr(gw, "scan")
        scan = gw.scan()
        assert scan["Polarization_Index"] >= 0.0
        assert scan["scanned_rule_count"] == 9

    def test_introspect_scan_parallel(self, gw):
        """introspect() 与 scan() 并列: scan 消费 introspect 产物。"""
        intro = gw.introspect()
        scan = gw.scan()
        # scan 的输入是 introspect 的规则 (同源同数)
        assert scan["scanned_rule_count"] == sum(
            len(rmcs) for rmcs in intro["protocols"].values())

    def test_report_serializable_to_json(self, gw):
        s = json.dumps(gw.scan(), ensure_ascii=False)
        assert s.startswith("{")


# ── 6. HONEST-BOUNDARY 联动 ────────────────────────────────────────
class TestHonestBoundary:
    def test_boundary_declared(self, report):
        assert "honest_boundary" in report
        hb = report["honest_boundary"]
        assert len(hb["detects"]) >= 1
        assert len(hb["does_not_detect"]) >= 1
        assert "恶意 agent 谎报声明" in hb["does_not_detect"][0]

    def test_summary_renders(self, report):
        s = summarize_scan(report)
        assert "VCE 2.0" in s
        assert "极化" in s
