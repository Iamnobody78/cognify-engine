#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprint 35 T1 测试: Z3 符号验证层 (第四层防护, SYMBOLIC_PROOF_FAIL).

覆盖:
  1. parse_rule_conditions 解析正确性
  2. 基线自检: 联合空洞检测 (S32 单维投影盲区)
  3. diff 级: 条件域收窄 -> SYMBOLIC_PROOF_FAIL 拦截
  4. diff 级: 无覆盖变更 -> 放行
  5. 端到端: precheck_topology_validity 集成 (S32 放行但 Z3 拦截)
  z3 缺失时全部跳过 (降级放行路径, 不阻断管道)。

合成规则文本 (与真实 ABDL 同构, 无 OR 子句以保持 Z3 翻译精确):
  - opp_found=True,  dist<0.6:  R1-CLOSE (angle∈[-10,10], edge<0.65)
                                R2-FLANK-L (angle<-10, edge<0.80)
                                R3-FLANK-R (angle>10, edge<0.80)
  - opp_found=True,  dist>0.6:  R4-OF (edge<0.5)
  - opp_found=False:            R5-LOST (edge<0.3)
                                R6-NEAR (edge∈[0.3,0.6])
                                R7-WARN (edge>0.8)
  基线联合空洞 (Z3 可证, S32 单维投影不可见):
    (opp_found=False, edge∈(0.6,0.8])  R6-NEAR 止于 0.6, R7-WARN 从 0.8 起 (> 严格)
"""

import pytest

z3 = pytest.importorskip("z3", reason="z3-solver 未安装, 符号验证降级放行")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import symbolic_verify as sv
from evaluator_diff_test import precheck_topology_validity

BASE_RULES = """- id: "R1-CLOSE"
  level: 0
  condition: "sensor(opponent_found) == True AND sensor(opponent_dist) < 0.6 AND BETWEEN(sensor(opponent_angle), -10, 10) AND sensor(edge_proximity) < 0.65"
  action: "ActPush"
  priority: 200
- id: "R2-FLANK-L"
  level: 0
  condition: "sensor(opponent_found) == True AND sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80"
  action: "ActFlank"
  priority: 250
- id: "R3-FLANK-R"
  level: 0
  condition: "sensor(opponent_found) == True AND sensor(opponent_angle) > 10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80"
  action: "ActFlank"
  priority: 260
- id: "R4-OF"
  level: 0
  condition: "sensor(opponent_found) == True AND sensor(opponent_dist) > 0.6 AND sensor(edge_proximity) < 0.5"
  action: "ActApproach"
  priority: 300
- id: "R5-LOST"
  level: 0
  condition: "sensor(opponent_found) == False AND sensor(edge_proximity) < 0.3"
  action: "ActExplore"
  priority: 400
- id: "R6-NEAR"
  level: 0
  condition: "sensor(opponent_found) == False AND BETWEEN(sensor(edge_proximity), 0.3, 0.6)"
  action: "ActRetreat"
  priority: 450
- id: "R7-WARN"
  level: 0
  condition: "sensor(opponent_found) == False AND sensor(edge_proximity) > 0.8"
  action: "ActDanger"
  priority: 500
"""


# ---------------------------------------------------------------------------
# 1. 解析正确性
# ---------------------------------------------------------------------------
def test_parse_rule_conditions_count():
    conds = sv.parse_rule_conditions(BASE_RULES)
    assert len(conds) == 7
    ids = [cid for cid, _ in conds]
    assert "R1-CLOSE" in ids and "R7-WARN" in ids


# ---------------------------------------------------------------------------
# 2. 基线自检: 联合空洞 (S32 单维投影盲区)
# ---------------------------------------------------------------------------
def test_baseline_selfcheck_detects_joint_hole():
    """基线联合空洞 (Z3 可证, S32 单维投影不可见).

    合成文本的已知空洞:
      - (opp_found=False, edge∈(0.6,0.8]): R6-NEAR 止于 0.6, R7-WARN 从 0.8 起 (> 严格)
      - (opp_found=True, dist≈0.6 边界): R1-R3 需 dist<0.6, R4-OF 需 dist>0.6
    断言: valid=False 且至少 1 个反例 (具体落在哪个空洞由 Z3 搜索顺序决定).
    """
    valid, reason, stats = sv.symbolic_verify(rules_text=BASE_RULES, max_holes=5)
    assert valid is False, f"应检测到基线联合空洞, reason={reason}"
    assert stats["holes"], "应至少返回 1 个反例"


# ---------------------------------------------------------------------------
# 3. diff 级: 条件域收窄 -> SYMBOLIC_PROOF_FAIL
# ---------------------------------------------------------------------------
def test_diff_narrow_edge_blocked():
    """R1-CLOSE edge<0.65 -> edge<0.30: 联合空间新增空洞.

    新增空洞: (opp_found=True, dist<0.6, angle∈[-10,10], edge∈(0.30,0.65))
      - R1-CLOSE 不匹配 (edge>=0.30)
      - R2/R3-FLANK 不匹配 (angle 在中间)
      - R4-OF 不匹配 (dist<0.6)
    S32 单维投影: edge 维度被 FLANK(0.80)/OF(0.5) 覆盖 -> 投影无空洞, 放行.
    Z3 联合包含验证: 基线有覆盖、候选无覆盖 -> SYMBOLIC_PROOF_FAIL.
    """
    entries = [
        {"old": "sensor(edge_proximity) < 0.65",
         "new": "sensor(edge_proximity) < 0.30",
         "expected": 1},
    ]
    valid, reason, stats = sv.symbolic_verify_diff(entries, rules_text=BASE_RULES)
    assert valid is False, f"应拦截 (SYMBOLIC_PROOF_FAIL), reason={reason}"
    assert "SYMBOLIC_PROOF_FAIL" in reason
    assert stats["new_holes"], "应返回新增空洞反例"


def test_diff_narrow_angle_blocked():
    """R1-CLOSE angle BETWEEN(-10,10) -> BETWEEN(-8,8): 联合空间新增空洞.

    新增空洞: (opp_found=True, dist<0.6, angle∈(-10,-8)∪(8,10), edge<0.65)
      - R1-CLOSE 不匹配 (angle 超出新区间)
      - R2/R3-FLANK 不匹配 (angle 未达 ±10)
    """
    entries = [
        {"old": "BETWEEN(sensor(opponent_angle), -10, 10)",
         "new": "BETWEEN(sensor(opponent_angle), -8, 8)",
         "expected": 1},
    ]
    valid, reason, stats = sv.symbolic_verify_diff(entries, rules_text=BASE_RULES)
    assert valid is False
    assert "SYMBOLIC_PROOF_FAIL" in reason


# ---------------------------------------------------------------------------
# 4. diff 级: 无覆盖变更 -> 放行
# ---------------------------------------------------------------------------
def test_diff_no_change_allowed():
    valid, reason, _ = sv.symbolic_verify_diff([], rules_text=BASE_RULES)
    assert valid is True


def test_diff_action_only_change_allowed():
    """仅 action 变更 (不改变覆盖) -> 放行 (行为影响由差分评估捕获)."""
    entries = [
        {"old": "ActPush", "new": "ActPushHard", "expected": 1},
    ]
    valid, reason, _ = sv.symbolic_verify_diff(entries, rules_text=BASE_RULES)
    assert valid is True


# ---------------------------------------------------------------------------
# 5. 端到端: precheck_topology_validity 集成
# ---------------------------------------------------------------------------
def test_precheck_integration_s32_passes_z3_blocks():
    """S32 放行但 Z3 拦截的端到端案例 (S35 第四层防护价值证明).

    同一收窄 diff: precheck_topology_validity (含 S32 + Z3) 应返回 False
    且 reason 含 SYMBOLIC_PROOF_FAIL (证明第四层防护在预检链中生效).
    """
    entries = [
        {"old": "sensor(edge_proximity) < 0.65",
         "new": "sensor(edge_proximity) < 0.30",
         "expected": 1},
    ]
    valid, reason = precheck_topology_validity(entries, rules_text=BASE_RULES)
    assert valid is False, f"预检链应拦截, reason={reason}"
    assert "SYMBOLIC_PROOF_FAIL" in reason


def test_precheck_integration_no_change_allowed():
    valid, reason = precheck_topology_validity([], rules_text=BASE_RULES)
    assert valid is True
