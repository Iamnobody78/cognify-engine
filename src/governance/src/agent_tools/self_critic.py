"""self_critic — 自举 Sense 层: 调用 L4 Critic Agent 全套批判者。

返回结构化自审报告 (verdict/findings 聚合)，供诊断环节引用。
"""

from __future__ import annotations

from pathlib import Path

from src.critic import runner as critic_runner


def run_self_critic(
    repo_root: Path | None = None,
    critic_names: list[str] | None = None,
) -> dict:
    """运行 5 批判者并返回结构化报告。

    repo_root: 默认自动定位仓库根（critic.runner._repo_root 上溯）。
    critic_names: 默认全部 5 批判者。

    返回: {verdict, reason, exit_code, per_critic, high_count,
           medium_critics, reports, critic_version}
    """
    root = repo_root or critic_runner._repo_root()
    aggregate = critic_runner.run_all_critics(root, critic_names)
    decision = aggregate["decision"]
    return {
        "verdict": decision["verdict"],           # PASS | REVISION | REJECT
        "reason": decision["reason"],
        "exit_code": decision["exit_code"],
        "per_critic": decision["per_critic"],     # {name: PASS|WARN|FAIL}
        "high_count": decision["high_count"],
        "medium_critics": decision["medium_critics"],
        "reports": aggregate["reports"],          # 证据链（可复核）
        "critic_version": aggregate["critic_version"],
    }
