"""HA L2: 跨平台 OS 级文件锁（Windows msvcrt / POSIX fcntl）。

语义: 短临界区互斥——仅保护租约文件等极短读写操作，绝不长期持有
（长期互斥由 Lease 租约机制承担，锁在此仅保证"同一时刻至多一个进程
写租约文件"）。非阻塞尝试 + 固定间隔重试，超时返回 False（不阻塞调用方）。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":  # pragma: no cover - 平台分支
    import msvcrt
else:  # pragma: no cover - 平台分支
    import fcntl

_RETRY_INTERVAL = 0.05  # 秒


class FileLock:
    """跨平台文件锁上下文管理器。

    用法: with FileLock(path, timeout=1.0) as lock: ...
    若 timeout 内未获锁，acquire() 返回 False（__enter__ 不抛异常，
    调用方检查 .acquired 决定降级路径——fail-safe 而非 fail-crash）。
    """

    def __init__(
        self,
        path: str | Path,
        timeout: float = 1.0,
        retry_interval: float = _RETRY_INTERVAL,
    ) -> None:
        self.path = Path(path)
        self.timeout = timeout
        self.retry_interval = retry_interval
        self._fd: int | None = None
        self.acquired = False

    def acquire(self) -> bool:
        """尝试获取锁；超时返回 False。幂等（已持有则直接返回 True）。"""
        if self.acquired:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self.path, os.O_CREAT | os.O_RDWR)
        # Windows msvcrt.locking 对"超出 EOF 的锁定区域"不产生真实锁
        # （MSDN: 锁定 EOF 之外区域不报错也不生效）——必须保证文件 ≥1 字节。
        if os.fstat(self._fd).st_size == 0:
            os.write(self._fd, b"\x00")
            os.lseek(self._fd, 0, os.SEEK_SET)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if sys.platform == "win32":  # pragma: no cover - 平台分支
                    msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
                else:  # pragma: no cover - 平台分支
                    fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.acquired = True
                return True
            except OSError:
                if time.monotonic() >= deadline:
                    self._close_fd()
                    return False
                time.sleep(self.retry_interval)

    def release(self) -> None:
        """释放锁；未持有则 no-op（幂等）。"""
        if not self.acquired:
            return
        try:
            if sys.platform == "win32":  # pragma: no cover - 平台分支
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:  # pragma: no cover - 平台分支
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            pass
        self._close_fd()
        self.acquired = False

    def _close_fd(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def __enter__(self) -> "FileLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
