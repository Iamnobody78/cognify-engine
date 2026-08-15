#!/usr/bin/env python3
"""S31 T2: 核对 E/F no-op 逐 episode 一致性 + topo_A 回放分布 + 判定字段."""
import json
import sys
from collections import Counter

SNAP = sys.argv[1] if len(sys.argv) > 1 else "20260808_184101"
BASE = f"governance/meta_harness/variants/_snapshots/{SNAP}"

def load(name):
    try:
        return json.load(open(f"{BASE}/{name}", encoding="utf-8"))
    except Exception as exc:
        print(f"  (load {name} failed: {exc})")
        return None

base = load("baseline_signal.json")
eps_base = base["signal"]["episodes"]
print("=== 基线 vs E/F: 逐局步数对比 (no-op 验证) ===")
for cand in ["mh_rules_topo_E", "mh_rules_topo_F"]:
    d = load(f"{cand}_report.json")
    eps = d["trajectory"]["episode_results"]
    steps_c = [e["steps"] for e in eps]
    steps_b = [e["steps"] for e in eps_base]
    same = steps_c == steps_b
    print(f"{cand}: steps 与基线一致={same}")
    if not same:
        for i, (b, c) in enumerate(zip(steps_b, steps_c)):
            if b != c:
                print(f"  ep{i}: 基线={b} 候选={c}")

print("\n=== 判定字段 (diff_test) ===")
for cand in ["mh_rules_topo_D", "mh_rules_topo_E", "mh_rules_topo_F",
             "mh_rules_topo_A", "mh_mapping_001"]:
    d = load(f"{cand}_report.json")
    if not d:
        continue
    dt = d.get("diff_test", {})
    print(f"{cand}: verdict={dt.get('verdict')} | reason={str(dt.get('reason'))[:130]}")
    if cand == "mh_rules_topo_A":
        print(f"  完整 diff_test: {json.dumps(dt, ensure_ascii=False)[:500]}")

print("\n=== topo_A 分布 vs 基线 ===")
d = load("mh_rules_topo_A_report.json")
eps_a = d["trajectory"]["episode_results"]
ta = Counter()
for e in eps_a:
    bh = e.get("branch_hist") or {}
    for k, v in (bh.items() if isinstance(bh, dict) else []):
        ta[k] += v
tb = Counter()
for e in eps_base:
    bh = e.get("branch_hist") or {}
    for k, v in (bh.items() if isinstance(bh, dict) else []):
        tb[k] += v
print("基线 top10:")
for k, v in tb.most_common(10):
    print(f"  {k}: {v}")
print("topo_A top10:")
for k, v in ta.most_common(10):
    print(f"  {k}: {v}")
