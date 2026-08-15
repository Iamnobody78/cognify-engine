#!/usr/bin/env python3
"""验证 S33 D5 校准输出: 置信度重排效果 + 高置信规则分布."""
import json

d = json.load(open("governance/meta_harness/experience/distill_rules_20260808_192416.json"))
print("meta.sprint:", d["meta"]["sprint"])
print("recalibrated:", d["meta"]["recalibrated"])

cal = d["stats"]["d5_calibration"]["calibration"]
print("\n=== D5 校准统计 ===")
print(f"d1_rules: {cal['d1_total_rules']}, d1_high_conf(>=0.5): {cal['d1_high_conf']}")
print(f"d2_rules: {cal['d2_total_rules']}, d2_high_conf(>=0.5): {cal['d2_high_conf']}")
print("\nd1_top (按置信度):")
for r in cal["d1_top"]:
    print(f"  {r['id']}: conf={r['conf']}")
print("\nd2_top (按置信度):")
for r in cal["d2_top"]:
    print(f"  {r['id']}: conf={r['conf']}")

# 验证重排: d1 规则按 confidence 降序
d1 = d["d1_desensitization"]
confs = [r.get("confidence", 0) for r in d1]
sorted_ok = all(confs[i] >= confs[i + 1] for i in range(len(confs) - 1))
print(f"\nD1 降序排列正确: {sorted_ok}")
print(f"D1 置信度范围: {min(confs):.3f} ~ {max(confs):.3f}")

# 高置信规则示例 (top 3)
print("\n=== D1 最高置信规则示例 ===")
for r in d1[:3]:
    print(f"  {r['id']} ({r['layer']}) conf={r['confidence']} "
          f"Q组件={r['signal_components']}")
    print(f"    action: {r['action'][:100]}")

# 验证 S33 候选 G 的记录 (INCONCLUSIVE -> D2)
print("\n=== S33 候选 G 的 D2 规则 ===")
for r in d2r if False else []:
    pass
d2 = d["d2_perturbation_prior"]
for r in d2:
    if "topo_G" in r["id"] or "CAND_G" in r["id"]:
        print(f"  {r['id']} conf={r.get('confidence')}")
print("(候选 G 在 --since 20260808 池中; 若未见, 检查 variant_id 匹配)")
