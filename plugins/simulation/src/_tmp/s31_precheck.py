#!/usr/bin/env python3
"""Sprint 31 T2 预检: 验证 ROUND 12 候选池 (拓扑 D/E/F + topo_A 回放 + mapping 交叉验证).

检查项:
  1. generate_variants(round_no=12) 候选池 id 集合 = {topo_D, topo_E, topo_F, topo_A, mh_mapping_001}
  2. 每个 diff 的 expected 与 rules/mapping 文件实际 text.count 匹配 (锚点唯一性)
  3. M2.2 拓扑预检: D/E/F/A 无 priority 变更 -> topology_precheck_report 全部放行
  4. 候选 F 的 old 完整条件串精确匹配 ABDL (FLANK-RIGHT/LEFT)
  5. 候选间冲突检查: D (10->15) 与 F (old 含 < -10) 独立 apply 无顺序依赖
     (外环 apply -> 评估 -> restore, 每候选基于快照, 故无 D/F 冲突)
"""
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "governance", "meta_harness"))
sys.path.insert(0, REPO)

from variants import generate_variants, HARNESS_FILES
from evaluator_diff_test import topology_precheck_report

RULES = os.path.join(REPO, HARNESS_FILES["rules"])
MAPPING = os.path.join(REPO, HARNESS_FILES["mapping"])

EXPECTED_POOL = {"mh_rules_topo_D", "mh_rules_topo_E", "mh_rules_topo_F",
                 "mh_rules_topo_A", "mh_mapping_001"}

failures = []

def check(name, cond, detail=""):
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    if not cond:
        failures.append(name)

print("=== S31 T2 precheck: ROUND 12 候选池 ===")
cands = generate_variants(max_per_layer=3, round_no=12)
ids = [c.id for c in cands]
print(f"生成 {len(cands)} 个候选: {ids}")
check("候选池数量 == 5", len(cands) == 5, f"got {len(cands)}")
check("候选池 id 集合正确", set(ids) == EXPECTED_POOL,
      f"got {sorted(set(ids))}, expected {sorted(EXPECTED_POOL)}")

rules_text = open(RULES, encoding="utf-8").read()
mapping_text = open(MAPPING, encoding="utf-8").read()

print("\n=== 锚点唯一性 (expected vs 实际 text.count) ===")
for c in cands:
    src = rules_text if c.layer == "rules" else mapping_text
    for d in c.diff:
        actual = src.count(d["old"])
        exp = d.get("expected")
        ok = (actual == exp and actual >= 1)
        check(f"{c.id}: '{d['old'][:60]}...' expected={exp} actual={actual}",
              ok)
        # 校验 new 中不含残留占位
        if "TODO" in d.get("new", "") or "XXX" in d.get("new", ""):
            check(f"{c.id}: new 含占位符", False, d["new"])

print("\n=== M2.2 拓扑预检 (应全部放行: 无 priority 变更) ===")
for c in cands:
    if c.layer != "rules":
        continue
    valid, reason = topology_precheck_report(c.diff, RULES)
    check(f"{c.id}: 预检放行", valid, reason)

print("\n=== 候选间独立性与 F 精确匹配 ===")
f_var = next((c for c in cands if c.id == "mh_rules_topo_F"), None)
if f_var:
    for d in f_var.diff:
        check(f"F 完整条件串 '{d['old'][:70]}...' 唯一存在", rules_text.count(d["old"]) == 1)
        # 新串必须以 AND stuck_counter 结尾
        check(f"F 新串追加 stuck_counter<3", d["new"].rstrip().endswith("AND sensor(stuck_counter) < 3"),
              d["new"][-60:])
d_var = next((c for c in cands if c.id == "mh_rules_topo_D"), None)
if d_var:
    # D 收窄 10->15, F old 仍用 10 — 外环 restore 隔离保证无顺序依赖; 仅提醒
    print("  [INFO] D (10->15) 与 F (old 含 < -10): 外环逐候选 apply+restore, 无顺序冲突")

print("\n=== 摘要 ===")
if failures:
    print(f"FAILED {len(failures)} 项: {failures}")
    sys.exit(1)
print("ALL PASS — ROUND 12 候选池就绪, 可运行 outer_loop --round 12")
