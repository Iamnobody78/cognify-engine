#!/usr/bin/env python3
"""S32 P0 冒烟验证: 覆盖连续性预检对 S31 真实候选的判别.

- topo_D (FLANK ±10->±15): 应拦截 COVERAGE_GAP
- topo_E (CAUTIOUS-EDGE 0.55->0.60): 应放行 (edge 维度仍被 CLOSE-PUSH <0.65 覆盖)
- topo_F (FLANK + stuck<3): 应放行 (无数值维度收窄, stuck 不在投影维度)
- topo_A (CLOSE-PUSH 0.65->0.80 对齐): 应放行 (扩宽不产生空洞)
- priority 无跨越 (S29 候选 C 同构): 应放行 (无数值变更, 覆盖检查跳过)
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "governance", "meta_harness"))
sys.path.insert(0, REPO)

from evaluator_diff_test import (coverage_continuity_check, _coverage_gaps,
                                 _parse_dim_intervals, _merge_intervals)

RULES = os.path.join(REPO, "governance", "meta_language", "simulation_rules.abdl")
rules_text = open(RULES, encoding="utf-8").read()

fails = []

def check(name, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got}")
    if not ok:
        fails.append(name)

print("=== 维度投影单元验证 ===")
gaps_angle = _coverage_gaps(rules_text, "opponent_angle")
print(f"  基线 angle 空洞: {gaps_angle}")
check("基线 angle 无空洞", len(gaps_angle), 0)
gaps_edge = _coverage_gaps(rules_text, "edge_proximity")
print(f"  基线 edge 空洞: {gaps_edge}")
# edge: CLOSE-PUSH <0.65 + FLANK <0.80 + SAFETY >0.8 等, 应连续覆盖 [0,1]
check("基线 edge 无空洞", len(gaps_edge), 0)

print("\n=== S31 真实候选判别 ===")
# topo_D: FLANK ±10 -> ±15 (收窄)
d_ok, d_reason = coverage_continuity_check([
    {"old": "sensor(opponent_angle) < -10", "new": "sensor(opponent_angle) < -15"},
    {"old": "sensor(opponent_angle) > 10", "new": "sensor(opponent_angle) > 15"},
], rules_text)
print(f"  topo_D: valid={d_ok} reason={d_reason[:80]}")
check("topo_D 拦截 COVERAGE_GAP", d_ok, False)

# topo_E: CAUTIOUS-EDGE 下界 0.55 -> 0.60
e_ok, e_reason = coverage_continuity_check([
    {"old": "BETWEEN(sensor(edge_proximity), 0.55, 0.78)",
     "new": "BETWEEN(sensor(edge_proximity), 0.60, 0.78)"},
], rules_text)
print(f"  topo_E: valid={e_ok} reason={e_reason[:80]}")
check("topo_E 放行", e_ok, True)

# topo_F: FLANK 加 AND stuck_counter<3 (angle 条件本身不变)
f_ok, f_reason = coverage_continuity_check([
    {"old": "sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80",
     "new": "sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80 AND sensor(stuck_counter) < 3"},
    {"old": "sensor(opponent_angle) > 10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80",
     "new": "sensor(opponent_angle) > 10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80 AND sensor(stuck_counter) < 3"},
], rules_text)
print(f"  topo_F: valid={f_ok} reason={f_reason[:80]}")
check("topo_F 放行", f_ok, True)

# topo_A: CLOSE-PUSH edge 0.65 -> 0.80 (扩宽)
a_ok, a_reason = coverage_continuity_check([
    {"old": "sensor(edge_proximity) < 0.65", "new": "sensor(edge_proximity) < 0.80"},
], rules_text)
print(f"  topo_A: valid={a_ok} reason={a_reason[:80]}")
check("topo_A 放行", a_ok, True)

# priority 无跨越 (S29 候选 C 同构): 无数值变更
p_ok, p_reason = coverage_continuity_check([
    {"old": "priority: 300", "new": "priority: 350"},
], rules_text)
print(f"  priority-only: valid={p_ok} reason={p_reason[:80]}")
check("priority-only 覆盖检查跳过", p_ok, True)

print("\n=== 摘要 ===")
if fails:
    print(f"FAILED {len(fails)}: {fails}")
    sys.exit(1)
print("ALL PASS — P0 覆盖连续性预检判别正确")
