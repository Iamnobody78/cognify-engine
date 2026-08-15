"""Meta-Harness 层（L5）— 自优化引擎。

Phase 2 (TASK-REAL-012): 轻量适配器 — 融合已批准 D 阶段（统计反馈调节器）
与 Meta-Harness Propose 循环。扫描历史 DENY 决策 → 聚合高频模式 →
生成 pending 规则候选（YAML）→ validate_candidate 重放验证。

零侵入原则（架构蓝图 §一）: 不修改 src/main.py / src/policy.py /
src/storage.py。候选规则是 policy.py 可加载的标准 YAML，处于 pending 状态，
需人工/仲裁采纳后才注入 policies.yaml（行为可逆、拒绝套娃）。
"""

ADAPTER_VERSION = "0.1.0"

__all__ = ["ADAPTER_VERSION", "adapter"]
