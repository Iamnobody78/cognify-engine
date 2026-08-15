"""HA L2/L3: 故障接管协调器（FailoverCoordinator）。

单写者模型: 主实例唯一写 storage，副本只读；主崩溃（租约过期）后
副本 try_become_primary() 接管。guard_write() 在非主写时抛
NotPrimaryError——L3 审计链防分裂的第一道闸（第二道为 decisions.id
PRIMARY KEY 天然防重复写）。
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from .lease import Lease

if TYPE_CHECKING:  # pragma: no cover - 仅类型标注
    from src.storage import Storage


class NotPrimaryError(RuntimeError):
    """当前实例非主，禁止写操作（fail-safe 拦截）。"""


def make_owner_id(prefix: str = "gw") -> str:
    """生成唯一实例 id: <prefix>-<hostname 段>-<uuid4 前 8 位>。"""
    import socket

    host = socket.gethostname().split(".")[0][:12] or "host"
    return f"{prefix}-{host}-{uuid.uuid4().hex[:8]}"


class FailoverCoordinator:
    """租约包装器：接管检测 + 写保护。

    storage: 可选注入——接管成功后由治理层决定是否迁移/恢复未落库缓冲。
    本类不修改 storage 接口（零侵入）。
    """

    def __init__(self, lease: Lease, storage: "Storage | None" = None) -> None:
        self.lease = lease
        self.storage = storage

    # ── 状态 ────────────────────────────────────────────────────────

    def try_become_primary(self) -> bool:
        """尝试成为主（无活跃持有者时成功）。"""
        return self.lease.try_acquire()

    def is_primary(self) -> bool:
        """本实例当前是否为活跃主。"""
        return self.lease.is_active()

    def renew_primary(self) -> bool:
        """主实例续约；失去租约 → False（应立即降级只读）。"""
        return self.lease.renew()

    # ── 写保护（L3 防分裂）───────────────────────────────────────────

    def guard_write(self) -> None:
        """非主写 → NotPrimaryError。写路径入口处调用一次。"""
        if not self.lease.is_active():
            raise NotPrimaryError(
                f"instance {self.lease.owner_id!r} is not the active primary "
                f"(owner={self.lease.current_owner()!r})"
            )

    # ── 接管 ────────────────────────────────────────────────────────

    def recover(self) -> str | None:
        """检测主过期并接管。返回新主 owner_id；仍为副本 → None。

        时序: 副本轮询 is_expired() → True → try_acquire() 成功 → 新主。
        接管成功后不自动写 storage——由治理层决定恢复策略
        （flush 旧写缓冲 / 继续新写入），保持本层职责单一。
        """
        if self.lease.is_expired():
            if self.lease.try_acquire():
                return self.lease.owner_id
        return None
