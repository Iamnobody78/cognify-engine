#!/usr/bin/env python3
"""验证 D4 蒸馏输出文件内容完整性."""
import json

d = json.load(open("governance/meta_harness/experience/distill_rules_20260808_190458.json"))
print("meta.sprint:", d["meta"]["sprint"])
print("D4 rules:", len(d["d4_governance_discoveries"]))
for r in d["d4_governance_discoveries"]:
    print("  ", r["id"], "-", r["name"])
    print("     rule:", r["rule"][:80], "...")
print("D1 desensitization:", len(d["d1_desensitization"]))
print("D2 perturbation_prior:", len(d["d2_perturbation_prior"]))
print("stats.d4:", d["stats"]["d4"])
