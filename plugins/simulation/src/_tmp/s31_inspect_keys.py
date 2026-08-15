#!/usr/bin/env python3
"""查看 topo_D 报告 episode 的 branch_hist 原始键结构."""
import json
import sys

SNAP = sys.argv[1] if len(sys.argv) > 1 else "20260808_184101"
P = f"governance/meta_harness/variants/_snapshots/{SNAP}/mh_rules_topo_D_report.json"
d = json.load(open(P, encoding="utf-8"))
eps = d["trajectory"]["episode_results"]
print(f"episodes: {len(eps)}")
for idx in [0, 1, len(eps) - 1]:
    e = eps[idx]
    print(f"\nep{idx} keys: {list(e.keys())}")
    print(f"ep{idx} steps: {e.get('steps')}")
    bh = e.get("branch_hist") or e.get("branch_history") or {}
    if isinstance(bh, dict):
        print(f"ep{idx} branch_hist ({len(bh)} 键):")
        for k, v in list(bh.items())[:15]:
            print(f"    {k!r}: {v}")
    elif isinstance(bh, list):
        print(f"ep{idx} branch_hist list len={len(bh)}:")
        for item in bh[:5]:
            print(f"    {json.dumps(item, ensure_ascii=False)[:200]}")
