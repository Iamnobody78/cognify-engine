"""Phase HA: 三循环引擎高可用——多实例协调（文件锁 + 租约 + 故障接管）。

L2 跨进程协调: FileLock（OS 级短临界区）+ Lease（心跳时间戳活性判定）
+ FailoverCoordinator（单写者模型，非主写拦截 + 过期接管）。
L3 审计链防分裂: decisions.id PRIMARY KEY + guard_write 拦截非主写。
"""

from .file_lock import FileLock
from .lease import Lease
from .failover import FailoverCoordinator, NotPrimaryError

__all__ = ["FileLock", "Lease", "FailoverCoordinator", "NotPrimaryError"]
