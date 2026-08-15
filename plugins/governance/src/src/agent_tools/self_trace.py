"""self_trace — 自举 Diagnose 层: 提取整条因果链供诊断。

复用 Storage.get_trace 的递归 CTE 语义（防环 + max_depth + max_nodes 双保险），
不重实现图遍历。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.storage import Storage


def get_self_trace(
    trace_id: str,
    storage: "Storage | None" = None,
    max_depth: int = 50,
    max_nodes: int = 500,
) -> dict:
    """返回 trace_id 的完整因果链（含 depth 标注）。

    storage: 显式传入 Storage 实例；None 时懒加载（:memory:，仅会话内可用，
    生产请传入持久化实例）。
    无记录返回 {"nodes": [], "depth": 0}（上游应判 404）。
    """
    if storage is None:
        from src.storage import Storage

        storage = Storage()
    nodes = storage.get_trace(trace_id, max_depth, max_nodes)
    return {
        "trace_id": trace_id,
        "nodes": nodes,
        "depth": max((n.get("depth", 0) for n in nodes), default=0),
        "node_count": len(nodes),
    }
