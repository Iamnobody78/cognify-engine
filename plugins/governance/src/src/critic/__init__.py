"""Critic Agent Team — 批判者代理团队代码化（GATE 8 动态语义门控）。

TASK-REAL-012: 将 .aionui/protocols/critic_team.md 元提示词编译为可执行模块。
5 个批判者 + 协调器 + 裁决器，每次提交后自动运行并输出 .aionui/critic_report.md。

架构:
  src/critic/
    audit_critic.py   — 债务清偿证据 / 审计日志完整性 / 迁移无损 / relay_state 一致
    security_critic.py— 熔断/超时 fail-closed / 路径匹配 / SQL 参数化 / trace 头守卫
    arch_critic.py    — README 宣称 vs 代码 / 铁律 vs CI / 新依赖合理性
    test_critic.py    — 真实断言 / IO 状态迁移 / 覆盖率 / 模块测试对应
    docs_critic.py    — 文档引用存在性 / 版本一致性 / 铁律 vs CI 行为
    verdict.py        — 一票否决(HIGH) / 多数通过(≥4/5) / 需修正(2-3 MEDIUM)
    runner.py         — 协调器: asyncio 并行运行 + 报告渲染 + CLI + exit code
"""

CRITIC_VERSION = "1.0.0"

__all__ = [
    "CRITIC_VERSION",
    "audit_critic",
    "security_critic",
    "arch_critic",
    "test_critic",
    "docs_critic",
    "verdict",
    "runner",
]
