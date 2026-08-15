"""self_heal — 自举 Remediate 层: 沙箱评估候选，生成修正建议。

复用 meta_harness.adapter.validate_candidate + sandbox.evaluate_candidate_in_sandbox
(语法 + 冲突 + 重放 + 可选 pytest)。不可部署时基于 reasons/conflicts
生成结构化修正补丁建议；绝不自动写主 policies.yaml（裁决权在治理层）。
"""

from __future__ import annotations

from pathlib import Path

from src.meta_harness import sandbox as _sandbox
from src.meta_harness.adapter import DEFAULT_POLICIES, validate_candidate

# 修正建议模板: 按失败类别给出可执行的 YAML 修改方向
_FIX_HINTS = {
    "syntax": "候选 YAML 语法/结构不合法: 检查 rules 列表元素字段",
    "conflict": "action 冲突需人工裁决: 收敛为单一 action 或按优先级拆分规则",
    "replay": "重放命中率不足: 检查 path/method 前缀与 json_path 键名是否匹配真实请求",
    "regression": "pytest 回归失败: 先修测试红线，再重新提交候选",
}


def heal_candidate(
    candidate_path: str | Path,
    policies_path: str | Path | None = None,
    storage=None,
    run_tests: bool = False,
    tests_dir: str | Path = "tests",
) -> dict:
    """评估候选并返回 {deployable, reasons, conflicts, hit_rate, fixes}。

    fixes: 不可部署时的结构化修正建议列表 [{"category", "hint", "evidence"}]；
           deployable=True 时为空列表。
    """
    cand = Path(candidate_path)
    policies = Path(policies_path) if policies_path is not None else Path(DEFAULT_POLICIES)

    # 1. 语法/语义验证（fail-closed，先于沙箱）
    base = validate_candidate(cand, policies, storage=storage)
    if not base["valid"]:
        return {
            "deployable": False,
            "reasons": [base["reason"]],
            "conflicts": [],
            "hit_rate": None,
            "fixes": [_fix("syntax", base["reason"])],
            "checked": 0,
        }

    # 2. 完整沙箱评估（冲突 + 重放 + 可选回归）
    result = _sandbox.evaluate_candidate_in_sandbox(
        cand, policies, storage=storage,
        run_tests=run_tests, tests_dir=tests_dir,
    )
    fixes: list[dict] = []
    if result["conflicts"]:
        evidence = "; ".join(
            f"{c.get('action')}:{c.get('severity')}" for c in result["conflicts"]
        )
        fixes.append(_fix("conflict", evidence))
    if result.get("hit_rate") is not None and result["hit_rate"] < 1.0:
        fixes.append(_fix("replay", f"hit_rate={result['hit_rate']:.3f}"))
    if result.get("tests") and not result["tests"]["tests_passed"]:
        fixes.append(_fix("regression", result["tests"].get("summary", "")))
    if not fixes and not result["deployable"]:
        # 兜底: 无明确类别但不可部署（防御性）
        fixes.append(_fix("syntax", "; ".join(result["reasons"])))

    return {
        "deployable": result["deployable"],
        "reasons": result["reasons"],
        "conflicts": result["conflicts"],
        "hit_rate": result["hit_rate"],
        "fixes": fixes,
        "checked": result["checked"],
    }


def _fix(category: str, evidence: str) -> dict:
    return {
        "category": category,
        "hint": _FIX_HINTS.get(category, _FIX_HINTS["syntax"]),
        "evidence": evidence,
    }
