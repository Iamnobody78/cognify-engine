#!/usr/bin/env python3
"""检查 meta_decisions.jsonl 中 S31 (20260808) 的 diff_gate 判定分布."""
import json
from collections import Counter

PATH = "governance/meta_harness/meta_decisions.jsonl"
recs = []
with open(PATH, encoding="utf-8") as f:
    for ln in f:
        ln = ln.strip()
        if not ln:
            continue
        try:
            recs.append(json.loads(ln))
        except json.JSONDecodeError:
            continue

s31 = [r for r in recs if r.get("ts", "").startswith("20260808")]
print(f"20260808 总记录: {len(s31)}")
types = Counter(r.get("type") for r in s31)
print(f"类型分布: {dict(types)}")

dg = [r for r in s31 if r.get("type") == "diff_gate"]
print(f"diff_gate 记录: {len(dg)}")
vd = Counter(r.get("diff_verdict") for r in dg)
print(f"判定分布: {dict(vd)}")
for r in dg[-8:]:
    print(f"  {r.get('ts')} {r.get('variant_id','?'):30s} {r.get('layer','?'):8s} "
          f"{r.get('diff_verdict','?'):14s} Q={r.get('quality')}")
