#!/usr/bin/env python3
"""S31 T2 深度核查: topo_D 报告原始结构 + 基线逐局步数分布.

回答:
1. topo_D 的 branch_hist 键 'abdl:' 是否含未命名子分支 (diff 应用异常迹象)
2. 基线 10 episodes 是否有慢局 (FP-NEG-004 ep7=60步 场景是否在场)
3. D 的 diff 是否真的改动了文件 (找 eval 用临时文件的痕迹)
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
        print(f"  (missing {name})")
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)

print("=== 1. 基线逐局步数分布 ===")
base = load("baseline_signal.json")
eps = base["signal"]["episodes"]
steps = sorted(e.get("steps", 0) for e in eps)
print(f"episodes={len(eps)} steps排序={steps}")
slow = [e for e in eps if e.get("steps", 0) > 30]
print(f"慢局(>30步): {len(slow)} 个")
for e in slow:
    print(f"  steps={e.get('steps')} keys={list(e.keys())}")
    bh = e.get("branch_hist") or e.get("branch_history") or {}
    if isinstance(bh, dict):
        print(f"    branch_hist: {dict(Counter(bh).most_common(8))}")

print("\n=== 2. topo_D 报告结构核查 ===")
d = load("mh_rules_topo_D_report.json")
if d:
    print(f"顶层keys: {list(d.keys())}")
    tr = d.get("trajectory", {})
    print(f"trajectory keys: {list(tr.keys())}")
    res = tr.get("episode_results", [])
    print(f"episode_results: {len(res)} 个")
    # 检查 branch_hist 键格式
    key_counter = Counter()
    for e in res:
        bh = e.get("branch_hist") or e.get("branch_history") or {}
        if isinstance(bh, dict):
            for k in bh:
                key_counter[k] += 1
    print("branch_hist 键样本(前12):")
    for k, v in key_counter.most_common(12):
        print(f"    {repr(k)}: {v}")
    # D 的判定信息
    print("\nD 判定字段:")
    for key in ["verdict", "verdicts", "quality", "fused_quality", "diff_gate",
                "gate", "decision", "results"]:
        if key in d:
            val = d[key]
            s = json.dumps(val, ensure_ascii=False)[:400]
            print(f"  {key}: {s}")

print("\n=== 3. 评估用文件痕迹 (eval 临时目录) ===")
import glob
for pat in ["_tmp/*topo_D*", "governance/meta_harness/*topo_D*", "**/s31*", "**/eval_*"]:
    hits = glob.glob(os.path.join(os.path.dirname(BASE), "..", "..", "..", pat), recursive=False)[:5]
    for h in hits:
        print(f"  {h}")
