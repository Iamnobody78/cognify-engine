#!/usr/bin/env python3
# S35 T1 验收: 验证 symbolic_verify_diff 拦截能力 (PM 验收①: 至少 1 个拓扑候选被 Z3 拦截)
import sys
sys.path.insert(0, "governance/meta_harness")

import symbolic_verify as sv

RULES = "governance/meta_language/simulation_rules.abdl"

with open(RULES, "r", encoding="utf-8") as f:
    rules_text = f.read()

# ---- 场景 1: CLOSE-PUSH edge 0.65 -> 0.30 收窄 (S32 单维投影盲区案例) ----
print("=" * 70)
print("场景 1: CLOSE-PUSH edge <0.65 -> <0.30 收窄 (预期: SYMBOLIC_PROOF_FAIL 拦截)")
entries1 = [
    {
        "old": "sensor(edge_proximity) < 0.65",
        "new": "sensor(edge_proximity) < 0.30",
        "expected": 1,
    }
]
valid1, reason1, stats1 = sv.symbolic_verify_diff(entries1, rules_text=rules_text)
print(f"valid={valid1}")
print(f"reason: {reason1}")
print(f"stats: {stats1}")

# 对比: S32 单维投影是否放行 (证明 Z3 捕获的是 S32 盲区)
from evaluator_diff_test import coverage_continuity_check
ok32, reason32 = coverage_continuity_check(entries1, rules_text=rules_text)
print(f"-- S32 coverage_continuity_check: valid={ok32} ({reason32})")
print("-- Z3 优于 S32 的案例:", "YES" if (ok32 and not valid1) else "NO")

# ---- 场景 2: 无变更候选 (预期: 放行, 空洞为基线既有) ----
print("=" * 70)
print("场景 2: 无变更候选 (预期: 放行)")
valid2, reason2, stats2 = sv.symbolic_verify_diff([], rules_text=rules_text)
print(f"valid={valid2}")
print(f"reason: {reason2}")

# ---- 场景 3: FLANK edge 0.80 -> 0.75 收窄 (预期: 拦截, 与场景1类似) ----
print("=" * 70)
print("场景 3: FLANK-RIGHT edge <0.80 -> <0.75 收窄 (预期: 拦截)")
entries3 = [
    {
        "old": "sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80",
        "new": "sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.75",
        "expected": 1,
    }
]
valid3, reason3, stats3 = sv.symbolic_verify_diff(entries3, rules_text=rules_text)
print(f"valid={valid3}")
print(f"reason: {reason3}")
ok32b, reason32b = coverage_continuity_check(entries3, rules_text=rules_text)
print(f"-- S32: valid={ok32b} ({reason32b})")

# ---- 验收判定 ----
print("=" * 70)
intercepted = (not valid1) or (not valid3)
accepted = intercepted and valid2
print(f"验收: 场景1/3 至少一个被拦截={intercepted}, 场景2 放行={valid2}")
print("最终:", "PASS - Z3 拦截能力验证成功" if accepted else "FAIL")
sys.exit(0 if accepted else 1)
