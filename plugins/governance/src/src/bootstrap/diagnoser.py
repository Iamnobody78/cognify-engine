"""diagnoser — P12 诊断层: 将感知信号映射为可执行/需人工的动作。

输出统一的诊断列表:
  [
    {"category": str, "severity": "LOW|MEDIUM|HIGH",
     "fixable": bool,            # 是否可自动修复（确定性）
     "action": str|None,         # fixable 时的动作键（见 deployer.ACTIONS）
     "evidence": str, "signal": str}
  ]

确定性原则: 同一信号集 → 同一诊断集（无随机）。无法自动修复的
一律 fixable=False（需人工），绝不默认替人类做非确定性决策。
"""

from __future__ import annotations

# 可自动修复的动作键（与 deployer.ACTIONS 对应）
ACTION_REGENERATE_CODEGEN = "REGENERATE_CODEGEN"
ACTION_NOOP = "NOOP"


def diagnose(signals: dict) -> list[dict]:
    """把 collect_signals() 的输出映射为诊断列表。"""
    out: list[dict] = []
    codegen = signals.get("codegen", {})
    git = signals.get("git", {})
    tests = signals.get("tests", {})
    critic = signals.get("critic", {})
    debt = signals.get("debt", {})

    # 1. codegen 漂移 → 可自动修复（确定性生成，逐字节可复现）
    if codegen.get("drift"):
        out.append({
            "category": "codegen",
            "severity": "MEDIUM" if codegen.get("generated") else "HIGH",
            "fixable": True,
            "action": ACTION_REGENERATE_CODEGEN,
            "evidence": codegen.get("reason", "codegen drift"),
            "signal": "codegen",
        })
    else:
        out.append({
            "category": "codegen", "severity": "LOW", "fixable": False,
            "action": ACTION_NOOP, "evidence": "codegen 一致", "signal": "codegen",
        })

    # 2. 测试失败 → 不可自动修复（需要根因分析，可能涉及语义）
    if tests.get("had_failures"):
        failed = tests.get("last_failed") or ["(未执行)"]
        out.append({
            "category": "tests", "severity": "HIGH", "fixable": False,
            "action": None,
            "evidence": f"失败 {len(failed)} 项: {failed[:5]}",
            "signal": "tests",
        })
    else:
        out.append({
            "category": "tests", "severity": "LOW", "fixable": False,
            "action": ACTION_NOOP, "evidence": tests.get("summary", "无失败"),
            "signal": "tests",
        })

    # 3. critic 未关闭建议 → 需人工（语义建议，不可盲改）
    if critic.get("open_count", 0) > 0:
        out.append({
            "category": "critic", "severity": "MEDIUM", "fixable": False,
            "action": None,
            "evidence": f"{critic['open_count']} 条未关闭建议",
            "signal": "critic",
        })

    # 4. 活跃债务 → 需人工（债务处置是治理决策，非自动修复）
    if debt.get("active_count", 0) > 0:
        out.append({
            "category": "debt", "severity": "LOW", "fixable": False,
            "action": None,
            "evidence": f"{debt['active_count']} 条活跃债务",
            "signal": "debt",
        })

    # 5. git 工作区脏（非生成物）→ 需人工确认，不自动提交他人改动
    changed = [p for p in git.get("changed", [])
               if "src/codegen/_generated_matches.py" not in p]
    if changed:
        out.append({
            "category": "git", "severity": "MEDIUM", "fixable": False,
            "action": None,
            "evidence": f"未提交变更 {len(changed)} 项: {changed[:5]}",
            "signal": "git",
        })

    return out


def fixable_diagnoses(diagnoses: list[dict]) -> list[dict]:
    """仅返回可自动修复的诊断（按 severity 排序: HIGH→LOW）。"""
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted([d for d in diagnoses if d.get("fixable") and d.get("action")],
                  key=lambda d: order.get(d.get("severity", "LOW"), 9))


def human_review_required(diagnoses: list[dict]) -> list[dict]:
    """返回需要人工处理的诊断（供报告与裁决门使用）。"""
    return [d for d in diagnoses if not d.get("fixable")]
