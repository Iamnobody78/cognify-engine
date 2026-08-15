#!/usr/bin/env python3
# 复现测试场景: 精确 mock 文本
import sys
sys.path.insert(0, "governance/meta_harness")

rules_text = "if dist < 0.20:\n    pass\n"
entries = [{"old": "dist < 0.20", "new": "dist < 0.20_X", "expected": 1}]

from evaluator_diff_test import coverage_continuity_check, precheck_topology_validity
ok32, r32 = coverage_continuity_check(entries, rules_text=rules_text)
print("S32:", ok32, "|", r32)

import symbolic_verify as sv
oksv, rsv, st = sv.symbolic_verify_diff(entries, rules_text=rules_text)
print("SYMBOLIC:", oksv, "|", rsv)
print("stats:", st)

okp, rp = precheck_topology_validity(entries, rules_text=rules_text)
print("PRECHECK:", okp, "|", rp)
