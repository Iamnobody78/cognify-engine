# -*- coding: utf-8 -*-
"""Verify mkfs + rmrf + benign through real ASTGuard.check_request path."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from src.ast_guard import ASTGuard
from src.policy import PolicyEngine

guard = ASTGuard()
engine = PolicyEngine()

cases = [
    ("mkfs", {"lang": "bash", "body": {"script": "mkfs.ext4 /dev/sdb1"}}),
    ("rmrf", {"lang": "bash", "body": {"script": "rm -rf /"}}),
    ("benign_ls", {"lang": "bash", "body": {"script": "ls -la /home"}}),
    ("benign_select", {"lang": "sql", "body": {"query": "SELECT * FROM users WHERE id=1;"}}),
    ("mal_delete", {"lang": "sql", "body": {"query": "DELETE FROM users;"}}),
]
for label, req in cases:
    try:
        f = guard.check_request(req["lang"], req["body"])
        verdict = getattr(f, "verdict", None) or getattr(f, "severity", None)
        rule = getattr(f, "matched_rule", None) or getattr(f, "rule_id", None)
        print(f"[{label}] {f}")
    except Exception as e:
        print(f"[{label}] guard err: {e}")
    try:
        r = engine.evaluate(req["lang"], req["body"])
        print(f"  engine -> {r}")
    except Exception as e:
        print(f"  engine err: {e}")
