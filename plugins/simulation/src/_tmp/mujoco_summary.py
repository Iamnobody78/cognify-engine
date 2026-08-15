#!/usr/bin/env python3
"""Summarize a V9 gate report JSON (any backend)."""
import json
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else ".aionui/meta_governance/gate/v9_gate_report.json"
with open(path, encoding="utf-8") as f:
    raw = f.read()
# Strip noisy INFO lines that the evaluator prints to stdout before the JSON dump.
lines = [ln for ln in raw.splitlines() if not ln.startswith("[!]")]
r = json.loads("\n".join(lines))

print(f"agent: {r.get('agent_name')} | backend: {r.get('backend')} | mode: {r.get('mode')}")
print(f"winrate: {r.get('winrate')} | wins: {r.get('wins')} | losses: {r.get('losses')} | threshold: {r.get('threshold')} | passed: {r.get('passed')}")
eps = r.get("episode_results", [])
print(f"total_episodes: {r.get('total_episodes')} | episode_results: {len(eps)}")
if eps:
    c = Counter((e.get("opponent") or e.get("strategy") or "?", e.get("win")) for e in eps)
    for k in sorted(c):
        print(f"  {k[0]:<10} win={k[1]} -> {c[k]}")
    print("per-episode (opponent, win, steps):")
    for e in eps:
        print(f"  {e.get('opponent') or e.get('strategy') or '?':<10} win={bool(e.get('win'))}  steps={e.get('steps')}")
print("per_strategy:")
for k, v in (r.get("per_strategy") or {}).items():
    print(f"  {k}: {v}")
