"""Revoke registry — P1 (暗雷区) 异步弱监督的撤销信号通道。

语义: 后台语义审计（LLM-Judge）发现高风险时 revoke(trace_id) —— 该调用链
的**后续**请求被短路为 SUSPEND（403 挂起待人工复审）。当前已放行的请求无法
收回（异步弱监督的本质），但审计链完整：撤销事件以 SUSPEND DecisionRecord
形式持久化（intercept 入口短路时自动落库，rationale 标注撤销原因）。

线程模型: 进程内单事件循环访问（asyncio 单线程），无需锁。
容量防护: 有界注册表（默认 10_000 条），超出时驱逐最旧条目 —— 防内存膨胀。

生产多实例提示: 内存注册表是单实例语义；多副本需外部共享（Redis）—— 属
P6+ 生产化命题，不阻塞本阶段。
"""

from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

MAX_ENTRIES = 10_000


class RevokeRegistry:
    """trace_id → (timestamp, reason, score) 撤销注册表。"""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._entries: Dict[str, Tuple[float, str, float]] = {}
        self._max_entries = max_entries

    def revoke(self, trace_id: str, reason: str, score: float) -> None:
        """撤销 trace 链（幂等：重复撤销覆盖原因）。"""
        if not trace_id:
            return
        self._entries[trace_id] = (time.time(), reason, score)
        if len(self._entries) > self._max_entries:
            self._evict_oldest()

    def is_revoked(self, trace_id: Optional[str]) -> bool:
        """该 trace 是否已被撤销（None/空 → False，新链不受影响）。"""
        return bool(trace_id) and trace_id in self._entries

    def reason_for(self, trace_id: str) -> Optional[str]:
        entry = self._entries.get(trace_id)
        return entry[1] if entry else None

    def score_for(self, trace_id: str) -> Optional[float]:
        entry = self._entries.get(trace_id)
        return entry[2] if entry else None

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)

    def _evict_oldest(self) -> None:
        oldest = min(self._entries, key=lambda k: self._entries[k][0])
        del self._entries[oldest]


# 进程级单例（main.py 导入即用；测试可重建独立实例）
revoke_registry = RevokeRegistry()
