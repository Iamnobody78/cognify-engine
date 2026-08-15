# -*- coding: utf-8 -*-
"""Verify mkfs/rmrf/benign through real PolicyEngine.evaluate path (as benchmark does)."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from pathlib import Path
from src.ast_guard import ASTGuard
from src.policy import PolicyEngine

REPO = Path(".").resolve()
engine = PolicyEngine(config_path=str(REPO / "config" / "policies.yaml"), ast_guard=ASTGuard())
PATH, METHOD = "/v1/chat/completions", "POST"

cases = [
    ("mkfs", {"lang": "bash", "body": {"script": "mkfs.ext4 /dev/sdb1"}}),
    ("rmrf", {"lang": "bash", "body": {"script": "rm -rf /"}}),
    ("dd_dev", {"lang": "bash", "body": {"script": "dd if=/dev/zero of=/dev/sda"}}),
    ("benign_ls", {"lang": "bash", "body": {"script": "ls -la /tmp"}}),
    ("mal_delete", {"lang": "sql", "body": {"query": "DELETE FROM users;"}}),
    ("benign_select", {"lang": "sql", "body": {"query": "SELECT * FROM users WHERE id=1;"}}),
]
for label, req in cases:
    rule = engine.evaluate(PATH, METHOD, req)
    print(f"[{label}] blocked={rule is not None} rule={rule}")
