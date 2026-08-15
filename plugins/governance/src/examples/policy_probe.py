"""Policy probe: dump YAML rules and cross-check against src.danger.is_dangerous().

Usage:
    python examples/policy_probe.py
Exit code 0 = consistent, 1 = at least one DENY/ESCALATE rule uncovered
or one ALLOW rule wrongly flagged as dangerous.
"""

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Single source of truth: import from src.danger, don't duplicate constants.
from src.danger import is_dangerous, DANGEROUS_PREFIXES
from src.policy import _parse_json_path

BLOCKING_ACTIONS = ("DENY", "ESCALATE")
ALLOWED_ACTIONS = BLOCKING_ACTIONS + ("ALLOW",)

POLICIES = REPO_ROOT / "config" / "policies.yaml"


def main() -> int:
    with open(POLICIES, encoding="utf-8") as fh:
        rules = yaml.safe_load(fh)["rules"]

    print(f"policy file: {POLICIES}")
    print(f"{'name':<24}{'action':<10}{'priority':<9}path_pattern")
    for r in rules:
        print(f"{r.get('name','?'):<24}{r.get('action','?'):<10}"
              f"{r.get('priority','?'):<9}{r.get('path_pattern','?')}")

    warnings = []

    # ── HIGH fix (Reviewer REJECT): action whitelist ──
    # Unknown/misspelled action (e.g. 'deny', 'DENNY') is silently ALLOWed
    # at runtime (main.py else-branch) AND skipped by this probe → CI green
    # while governance is fail-open. Must hard-fail instead.
    for i, r in enumerate(rules):
        action = r.get("action")
        if action not in ALLOWED_ACTIONS:
            warnings.append(
                f"rule[{i}] '{r.get('name','?')}': action={action!r} is NOT in "
                f"{ALLOWED_ACTIONS} — runtime would silently ALLOW it. "
                f"Fix the YAML (case-sensitive) or add to whitelist."
            )

    for r in rules:
        name = r.get("name", "?")
        action = r.get("action", "")
        path = r.get("path_pattern", "")
        method = r.get("method")
        if action not in ALLOWED_ACTIONS:
            continue  # already reported above

        # TASK-REAL-010 (B): json_path 条件规则是"体内治理" — 触发条件由请求体
        # JSON 决定, 路径覆盖不变量不适用 (timeout 分支的 path 启发式看不到
        # body, 该缺口已登记 DEBT-0021)。但条件规则自身有严格约束:
        if r.get("json_path") is not None:
            jp, jpt = r.get("json_path"), r.get("json_pattern")
            if action == "ALLOW":
                warnings.append(
                    f"{name}: ALLOW + json_path 条件规则是白名单走火器 — "
                    f"body 内容满足条件即放行, 拒绝该组合"
                )
            if action in BLOCKING_ACTIONS and not jpt:
                warnings.append(
                    f"{name}: DENY/ESCALATE + json_path 必须携带 json_pattern — "
                    f"仅凭路径存在即拦截过于宽泛 (误伤普通 'name' 字段)"
                )
            try:
                _parse_json_path(jp)
            except ValueError as e:
                warnings.append(f"{name}: json_path {jp!r} 语法错误 — {e} (fail-closed 要求加载期校验)")
            if jpt:
                try:
                    re.compile(jpt)
                except re.error as e:
                    warnings.append(f"{name}: json_pattern {jpt!r} 非法正则 — {e}")
            continue  # 条件规则不参与 is_dangerous 路径覆盖检查

        # Missing method = wildcard (matches all) per policy.py Rule.matches
        if method is None:
            # treat as wildcard: check path against is_dangerous for any method
            dangerous = any(is_dangerous(path, m) for m in ("GET", "POST", "DELETE", "PUT", "PATCH"))
            method_for_report = "*"
        else:
            dangerous = is_dangerous(path, method)
            method_for_report = method
        if action in BLOCKING_ACTIONS and not dangerous:
            warnings.append(f"{name}: {action} rule '{path}' ({method_for_report}) NOT covered by is_dangerous()")
        if action == "ALLOW" and dangerous:
            warnings.append(f"{name}: ALLOW rule '{path}' ({method_for_report}) wrongly flagged as dangerous")

    # ── MEDIUM fix (Reviewer): orphan-prefix reverse check ──
    # A prefix in is_dangerous with NO matching YAML rule means the
    # timeout fail-closed branch would DENY requests the YAML has allowed.
    covered_prefixes = set()
    for r in rules:
        path = r.get("path_pattern", "")
        for prefix in DANGEROUS_PREFIXES:
            if path.startswith(prefix) or f"/{prefix.lstrip('/')}*" in path:
                covered_prefixes.add(prefix)
    for prefix in DANGEROUS_PREFIXES:
        if prefix not in covered_prefixes:
            warnings.append(f"orphan prefix '{prefix}' in is_dangerous() has NO YAML rule — timeout branch would DENY allowed traffic")

    if warnings:
        print(f"WARNING: {len(warnings)} inconsistency(ies):")
        for w in warnings:
            print(f"  - {w}")
        return 1
    print("OK: all actions valid, blocking rules covered, no orphan prefixes, no ALLOW mis-flag")
    return 0


if __name__ == "__main__":
    sys.exit(main())
