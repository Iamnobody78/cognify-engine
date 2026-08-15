"""src.bootstrap — P12 自举运行时（确定性调度器，非独立进程）。

感知 → 诊断 → 修复 → 验证 → 部署 的确定性循环，复用 L4/L5 能力
(agent_tools.self_heal / meta_harness.sandbox / codegen.generator)，
状态持久化在 bootstrap_state.db (SQLite)。

设计契约（P12）:
  - 不是守护进程: 由 CI / 人工 / 定时任务按需触发 run_cycle()
  - 确定性: 同一输入信号 → 同一动作序列（无 LLM 随机性）
  - 人类 in-the-loop: codegen 漂移可自动修复+提交; 策略合并
    (deploy_candidate) 与 push 需显式配置或人工确认
  - 失败回滚: 验证失败 → git checkout 还原 + 诊断入库

版本: v1.21.0 (P12)
"""

from .scheduler import BootstrapScheduler, run_cycle
from .sensor import collect_signals
from .diagnoser import diagnose
from .deployer import run_fix

BOOTSTRAP_VERSION = "1.21.0"

__all__ = [
    "BootstrapScheduler",
    "run_cycle",
    "collect_signals",
    "diagnose",
    "run_fix",
    "BOOTSTRAP_VERSION",
]
