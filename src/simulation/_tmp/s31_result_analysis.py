#!/usr/bin/env python3
"""S31 T2 结果分析: 提取 ROUND 12 各候选的 branch_hist 触发分布, 对照 T1 预期.

- D (FLANK 10->15 收窄): 预期 FLANK 触发次数下降
- E (CAUTIOUS-EDGE 0.55->0.60): 预期 ep7 交替死循环打断
- F (FLANK + stuck_counter<3): 预期 FLANK 连续触发受限
"""
import json
import os
import sys
from collections import Counter

SNAP = sys.argv[1] if len(sys.argv) > 1 else "20260808_184101"
BASE = os.path.join(os.path.dirname(__file__), "..", "governance", "meta_harness",
                    "variants", "_snapshots", SNAP)

def load(name):
    p = os.path.join(BASE, name)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def branch_hist_stats(d):
    """统一从 baseline_signal.json 或候选 _report.json 提取 branch_hist 分布."""
    if d is None:
        return None
    # baseline_signal.json: d["signal"]["episodes"]
    if "signal" in d and "episodes" in d["signal"]:
        eps = d["signal"]["episodes"]
        return eps
    # 候选 _report.json: d["trajectory"]["episode_results"]
    if "trajectory" in d and "episode_results" in d["trajectory"]:
        return d["trajectory"]["episode_results"]
    return None

def analyze(name, label, eps):
    if eps is None:
        print(f"[{label}] (no data)")
        return
    n = len(eps)
    steps = [e.get("steps", 0) for e in eps if isinstance(e, dict)]
    avg = sum(steps) / len(steps) if steps else 0
    # branch_hist 聚合
    total = Counter()
    for e in eps:
        if not isinstance(e, dict):
            continue
        bh = e.get("branch_hist") or e.get("branch_history") or {}
        if isinstance(bh, dict):
            for k, v in bh.items():
                total[k] += v
        elif isinstance(bh, list):
            for item in bh:
                if isinstance(item, dict):
                    for k, v in item.items():
                        total[k] += v
    trig = sum(total.values())
    print(f"[{label}] episodes={n} avg_steps={avg:.1f} 触发总数={trig}")
    top = total.most_common(12)
    for k, v in top:
        pct = 100.0 * v / trig if trig else 0
        print(f"    {k}: {v} ({pct:.1f}%)")
    if trig:
        # 熵
        import math
        probs = [v / trig for v in total.values()]
        ent = -sum(p * math.log2(p) for p in probs if p > 0)
        print(f"    branch_hist 熵 = {ent:.4f}")

print(f"=== ROUND 12 (S31_TOPO2) snapshot {SNAP} ===")
base = load("baseline_signal.json")
analyze("baseline_signal.json", "基线", branch_hist_stats(base))

for cand in ["mh_rules_topo_D", "mh_rules_topo_E", "mh_rules_topo_F",
             "mh_rules_topo_A", "mh_mapping_001"]:
    d = load(f"{cand}_report.json")
    print()
    analyze(f"{cand}_report.json", cand, branch_hist_stats(d))
