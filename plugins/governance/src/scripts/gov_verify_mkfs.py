# -*- coding: utf-8 -*-
"""Verify mkfs is intercepted in benchmark matrix + check its rule path."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from src.ast_guard import guard

# simulate benchmark payloads
cases = [
    {"lang": "bash", "label": "mkfs", "body": {"script": "mkfs.ext4 /dev/sdb1"}},
    {"lang": "bash", "label": "rmrf", "body": {"script": "rm -rf /"}},
    {"lang": "bash", "label": "benign_ls", "body": {"script": "ls -la /home"}},
]
for c in cases:
    try:
        r = guard(c["lang"], c["body"])
        print(f"[{c['label']}] verdict={getattr(r, 'verdict', r)} rule={getattr(r, 'matched_rule', '')}")
    except Exception as e:
        print(f"[{c['label']}] err: {e}")
