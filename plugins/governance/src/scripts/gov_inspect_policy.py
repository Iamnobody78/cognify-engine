# -*- coding: utf-8 -*-
"""Inspect policies.yaml + find correct tools request format."""
import sys, yaml, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
d = yaml.safe_load(open("config/policies.yaml", encoding="utf-8"))
print("type:", type(d))
if isinstance(d, dict):
    for k, v in d.items():
        print(f"\n=== {k} ===")
        print(json.dumps(v, ensure_ascii=False, indent=1)[:1500])
elif isinstance(d, list):
    for p in d:
        print("\n=== policy ===")
        print(json.dumps(p, ensure_ascii=False, indent=1)[:1200])
