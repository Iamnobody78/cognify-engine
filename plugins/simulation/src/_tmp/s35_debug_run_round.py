#!/usr/bin/env python3
# 重现 run_round 测试场景, 定位 good 候选拦截点
import os, sys, json
from types import SimpleNamespace

REPO = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi"
os.chdir(REPO)
sys.path.insert(0, os.path.join(REPO, "governance/meta_harness"))

import outer_loop
import variants as vmod

# 迷你 repo
repo = "/tmp/s35_repro_repo"
os.makedirs(os.path.join(repo, "core/meta_language"), exist_ok=True)
os.makedirs(os.path.join(repo, "simulation"), exist_ok=True)
with open(os.path.join(repo, "core/meta_language/simulation_rules.abdl"), "w") as f:
    f.write("if dist < 0.20:\n    pass\n")
with open(os.path.join(repo, "simulation/lightweight_env.py"), "w") as f:
    f.write("x = 1\n")

outer_loop.REPO_ROOT = repo
outer_loop.HARNESS_FILES = {
    "rules": "core/meta_language/simulation_rules.abdl",
    "mapping": "core/meta_language/abdl_action_bridge.py",
    "physics": "simulation/lightweight_env.py",
}
outer_loop.SNAPSHOT_ROOT = "/tmp/s35_snaps"
outer_loop.META_HARNESS_DIR = "/tmp/s35_meta"

def _mk_variant(vid, layer, target, old, expected):
    return {"id": vid, "layer": layer, "target_file": target,
            "diff": [{"old": old, "new": old + "_X", "expected": expected}],
            "hypothesis": "h", "evidence": [], "bloodline": "test"}

bad = _mk_variant("s19_bad", "rules", "core/meta_language/simulation_rules.abdl",
                  "BETWEEN(sensor(opponent_angle), -15, 15)", 1)
good = _mk_variant("s19_good", "rules", "core/meta_language/simulation_rules.abdl",
                   "dist < 0.20", 1)

print("=== bad apply_precheck ===")
ok, reason = outer_loop.apply_precheck(bad)
print(ok, "|", reason)
print("=== good apply_precheck ===")
ok, reason = outer_loop.apply_precheck(good)
print(ok, "|", reason)
print("=== good topology_precheck ===")
from evaluator_diff_test import topology_precheck_report
ok, reason = topology_precheck_report(good["diff"] or [])
print(ok, "|", reason)
print("=== good diff ===")
print(good["diff"])
