#!/usr/bin/env python3
"""GATE 7: policy-code drift detector (+ P11 codegen sync check).

Detects drift between the DENY rules in config/policies.yaml and the
DANGEROUS_PREFIXES heuristic in src/danger.py (AUDIT-0004 lesson: a YAML
action written as lowercase 'deny' passed CI while the runtime silently
fell through to ALLOW; and the heuristic used to live as a separate
function in src/main.py that could drift from the YAML).

What it actually checks (real semantics, no fake asserts):
  1. Every DENY rule's path prefix in policies.yaml must be covered by a
     prefix in DANGEROUS_PREFIXES (the runtime heuristic). A DENY path
     that the heuristic does not know about means: when policy evaluation
     times out, that dangerous path is NOT recognized as dangerous.
  2. Every DENY prefix in DANGEROUS_PREFIXES should map to at least one
     DENY rule in the YAML (orphan-prefix reverse check).
  3. Action values must be in the whitelist {ALLOW, DENY, ESCALATE} —
     an unknown/lowercase value would make the runtime else-branch ALLOW.
  4. (TASK-REAL-010) json_path 条件规则豁免 path 覆盖检查 — 它们由请求体
     JSON 触发, timeout 分支的 path 启发式看不到 body (DEBT-0021), 但
     action 白名单检查照常生效。
  5. (P11) codegen drift — src/codegen/_generated_matches.py must match
     what src/codegen/generator.py would emit for the current YAML.
     --generate 模式在漂移时自动重新生成（"自生成"闭环）；默认模式
     报告漂移并 exit 1（强制提交生成物）。

Exit codes: 0 = consistent, 1 = drift found.
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple

import yaml

# scripts/ is not on sys.path when run directly: add repo root so
# `from src.codegen.generator import ...` resolves from any CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):  # Windows cp950 兼容
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.codegen.generator import generate as codegen_generate

POLICY_FILE = Path("config/policies.yaml")
MAIN_FILE = Path("src/main.py")
DANGER_FILE = Path("src/danger.py")
GENERATED_FILE = Path("src/codegen/_generated_matches.py")
ALLOWED_ACTIONS = {"ALLOW", "DENY", "ESCALATE"}


def load_dangerous_prefixes() -> List[str]:
    """Read DANGEROUS_PREFIXES tuple via AST (real runtime constant).

    DEBT-0002: the heuristic moved from src/main.py to src/danger.py.
    Scan danger.py first; fall back to main.py for older checkouts.
    """
    import ast

    for file in (DANGER_FILE, MAIN_FILE):
        if not file.exists():
            continue
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "DANGEROUS_PREFIXES":
                        if isinstance(node.value, ast.Tuple):
                            return [c.value for c in node.value.elts
                                    if isinstance(c, ast.Constant)]
    return []


def load_policy_non_allow_paths() -> Tuple[List[str], List[str]]:
    """Return (non_allow_paths, invalid_actions) from policies.yaml.

    non_allow = DENY + ESCALATE: both are "governed" paths that the
    runtime heuristic must recognize so the timeout path never silently
    lets them through (fail-closed principle).
    """
    data = yaml.safe_load(POLICY_FILE.read_text(encoding="utf-8"))
    non_allow_paths: List[str] = []
    invalid_actions: List[str] = []
    for rule in data.get("rules", []):
        action_raw = str(rule.get("action", ""))
        # AUDIT-0004 lesson: check the RAW value, not upper()-ed.
        # 'deny' (lowercase) would pass action=='DENY' after .upper() but the
        # runtime else-branch would silently ALLOW it. Exact match required.
        if action_raw not in ALLOWED_ACTIONS:
            invalid_actions.append(action_raw)
        # TASK-REAL-010 (B): json_path 规则是"体内治理" — 触发条件由请求体 JSON
        # 决定而非路径; 不进入 path 覆盖检查 (timeout 分支的 path 启发式看不到
        # body, 该缺口已登记 DEBT-0021)。action 白名单检查对它们仍然生效。
        if action_raw in ("DENY", "ESCALATE") and rule.get("json_path") is None:
            non_allow_paths.append(rule.get("path_pattern", ""))
    return non_allow_paths, invalid_actions


def prefix_covered(deny_path: str, prefixes: List[str]) -> bool:
    """True if some dangerous prefix is a path-prefix of the deny_path."""
    base = deny_path.rstrip("/")
    for p in prefixes:
        if base == p.rstrip("/") or base.startswith(p.rstrip("/") + "/"):
            return True
    return False


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--generate",
        action="store_true",
        help="auto-regenerate src/codegen/_generated_matches.py on drift "
             "(default: report drift and exit 1)",
    )
    args = ap.parse_args(argv)
    errors: List[str] = []

    # 1. action whitelist (AUDIT-0004 HIGH fix)
    _, invalid_actions = load_policy_non_allow_paths()
    for act in invalid_actions:
        errors.append(
            f"invalid action '{act}' in {POLICY_FILE} — must be one of "
            f"{sorted(ALLOWED_ACTIONS)} (lowercase/typo would silently ALLOW)"
        )

    # 2. DENY+ESCALATE coverage by runtime heuristic
    prefixes = load_dangerous_prefixes()
    non_allow_paths, _ = load_policy_non_allow_paths()
    for p in non_allow_paths:
        if not prefix_covered(p, prefixes):
            errors.append(
                f"governed rule '{p}' not covered by DANGEROUS_PREFIXES "
                f"{prefixes} — timeout path would not recognize it as dangerous"
            )

    # 3. orphan prefixes (reverse check)
    for p in prefixes:
        if not any(prefix_covered(gp, [p]) for gp in non_allow_paths):
            errors.append(
                f"DANGEROUS_PREFIX '{p}' has no matching DENY/ESCALATE rule "
                f"in {POLICY_FILE} — orphan prefix (AUDIT-0004 reverse check)"
            )

    # 4. P11 codegen drift — committed matchers must equal regenerated output
    written, diags = codegen_generate(POLICY_FILE, GENERATED_FILE)
    if written and not args.generate:
        errors.append(
            f"{GENERATED_FILE} is stale — run `python -m src.codegen.generator` "
            "or `policy_sync.py --generate` and commit the regenerated file"
        )

    if errors:
        print("GATE 7 (policy-sync): DRIFT FOUND")
        for e in errors:
            print(f"  - {e}")
        return 1

    for d in diags:
        print(f"GATE 7 (policy-sync): {d}")
    if args.generate and written:
        print("GATE 7 (policy-sync): regenerated matchers — commit the diff")
    print(f"GATE 7 (policy-sync): PASS — {len(non_allow_paths)} governed rules, "
          f"{len(prefixes)} prefixes, {len(invalid_actions)} invalid actions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
