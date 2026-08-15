#!/usr/bin/env python3
"""Sprint 33 T2 预检: 验证 ROUND 13 候选池 (候选 G + topo_A 回放 + mapping 交叉验证).

检查项:
  1. generate_variants(round_no=13) 候选池 id 集合 = {mh_rules_topo_G, mh_rules_topo_A, mh_mapping_001}
  2. 候选 G 的 old 锚点 (CAUTIOUS-EDGE 规则块) 在规则文件中唯一存在
  3. M2.2 覆盖预检: G 移除 CAUTIOUS-EDGE 后 edge 维度无新增空洞 (CLOSE-PUSH<0.65+FLANK<0.80 覆盖) -> 放行
  4. priority 预检: G 无 priority 变更 -> 放行
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "governance", "meta_harness"))
sys.path.insert(0, REPO)

from variants import generate_variants, HARNESS_FILES
from evaluator_diff_test import precheck_topology_validity, _coverage_gaps

RULES = os.path.join(REPO, HARNESS_FILES["rules"])
EXPECTED_POOL = {"mh_rules_topo_G", "mh_rules_topo_A", "mh_mapping_001"}

failures = []

def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)

print("=== S33 T2 precheck: ROUND 13 候选池 ===")
cands = generate_variants(max_per_layer=3, round_no=13)
ids = [c.id for c in cands]
print(f"生成 {len(cands)} 个候选: {ids}")
check("候选池 id 集合正确", set(ids) == EXPECTED_POOL,
      f"got {sorted(set(ids))}, expected {sorted(EXPECTED_POOL)}")

rules_text = open(RULES, encoding="utf-8").read()
g_var = next((c for c in cands if c.id == "mh_rules_topo_G"), None)
check("候选 G 生成", g_var is not None)
if g_var:
    d = g_var.diff[0]
    actual = rules_text.count(d["old"])
    check(f"G 锚点 (CAUTIOUS-EDGE 块) 唯一存在: expected={d['expected']} actual={actual}",
          actual == d["expected"] and actual == 1)
    # 覆盖预检
    valid, reason = precheck_topology_validity(g_var.diff, rules_text)
    print(f"  [{'PASS' if valid else 'FAIL'}] G 预检放行: {reason[:90]}")
    if not valid:
        failures.append("G 预检放行")
    # 明确验证: 移除后 edge 维度无新增空洞
    import copy
    sim = copy.deepcopy(g_var.diff)
    sim_text = rules_text
    for en in sim:
        sim_text = sim_text.replace(en["old"], en["new"])
    gaps = _coverage_gaps(sim_text, "edge_proximity")
    check(f"移除后 edge 维度无空洞: {gaps}", len(gaps) == 0, f"gaps={gaps}")

# topo_A 与 mapping 交叉验证存在
check("topo_A 回放入池", any(c.id == "mh_rules_topo_A" for c in cands))
check("mapping_001 交叉验证入池", any(c.id == "mh_mapping_001" for c in cands))

print("\n=== 摘要 ===")
if failures:
    print(f"FAILED {len(failures)} 项: {failures}")
    sys.exit(1)
print("ALL PASS — ROUND 13 候选池就绪, 可运行 outer_loop --round 13")
