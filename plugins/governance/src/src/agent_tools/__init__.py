"""P7 代理自举工具集: self_critic / self_trace / self_heal。

复用原则: 不重实现 L4/L5 能力——self_critic 调 critic.runner.run_all_critics
(AC1 结构化自审), self_trace 调 Storage.get_trace (AC2 因果链),
self_heal 调 meta_harness.adapter.validate_candidate + sandbox
(AC3 修正补丁)。三工具构成 Sense→Diagnose→Remediate 思考链。
"""

from .self_critic import run_self_critic
from .self_trace import get_self_trace
from .self_heal import heal_candidate

__all__ = ["run_self_critic", "get_self_trace", "heal_candidate"]
