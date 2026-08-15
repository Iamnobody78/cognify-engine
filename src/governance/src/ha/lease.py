"""HA L2: 租约（Lease）——进程活性心跳 + 过期检测。

单写者模型的活性判定: 主实例周期性 renew() 刷新 expires_at；副本实例
轮询 is_active()。主崩溃后租约在 ttl 内自然过期，副本即可接管。

租约文件为 JSON: {"owner_id", "expires_at"}。所有读写由 FileLock
保护（OS 级互斥），保证同一时刻至多一个进程修改租约状态。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .file_lock import FileLock

DEFAULT_TTL = 5.0        # 秒: 租约有效时长
DEFAULT_RENEW = 2.0      # 秒: 主实例续约间隔（应 < ttl/2，防时钟抖动）
CLOCK_TOLERANCE = 1.0    # 秒: 过期判定容差（防时钟抖动误判双主）
_LOCK_TIMEOUT = 1.0      # 秒: 租约文件锁等待上限


class Lease:
    """进程级租约。

    属性: owner_id 唯一标识本实例（如 hostname-pid-随机）。
    try_acquire(): 无活跃持有者 → 成为 owner 并写入租约文件。
    renew(): 仍持有 → 刷新 expires_at；失去 → 返回 False。
    is_active(): 本实例仍为 owner 且未过期。
    """

    def __init__(
        self,
        state_dir: str | Path,
        owner_id: str,
        ttl: float = DEFAULT_TTL,
        renew_interval: float = DEFAULT_RENEW,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.owner_id = owner_id
        self.ttl = ttl
        self.renew_interval = renew_interval
        self.lease_path = self.state_dir / "ha.lease.json"
        self._lock_path = self.state_dir / "ha.lease.lock"
        self._expires_at = 0.0  # monotonic 时钟

    # ── 生命周期 ────────────────────────────────────────────────────

    def try_acquire(self) -> bool:
        """无活跃持有者 → 成为主。已持有者未过期 → 返回 False。"""
        with FileLock(self._lock_path, timeout=_LOCK_TIMEOUT) as lock:
            if not lock.acquired:
                return False
            holder = self._read_lease_locked()
            if holder is not None and holder.get("expires_at", 0.0) > time.monotonic():
                return False  # 仍有活跃持有者
            now = time.monotonic()
            self._expires_at = now + self.ttl
            self._write_lease_locked(now)
            return True

    def renew(self) -> bool:
        """续约；已失去 owner（被接管）→ 返回 False。"""
        with FileLock(self._lock_path, timeout=_LOCK_TIMEOUT) as lock:
            if not lock.acquired:
                return False
            holder = self._read_lease_locked()
            if holder is None or holder.get("owner_id") != self.owner_id:
                return False
            now = time.monotonic()
            self._expires_at = now + self.ttl
            self._write_lease_locked(now)
            return True

    def is_active(self) -> bool:
        """本实例仍为 owner 且租约未过期（含容差）。"""
        with FileLock(self._lock_path, timeout=_LOCK_TIMEOUT) as lock:
            if not lock.acquired:
                return False
            holder = self._read_lease_locked()
        if holder is None or holder.get("owner_id") != self.owner_id:
            return False
        return (holder.get("expires_at", 0.0) + CLOCK_TOLERANCE
                >= time.monotonic())

    def release(self) -> None:
        """主动释放租约（优雅下线）；文件残留由后续接管者覆盖。"""
        with FileLock(self._lock_path, timeout=_LOCK_TIMEOUT) as lock:
            if not lock.acquired:
                return
            holder = self._read_lease_locked()
            if holder is not None and holder.get("owner_id") == self.owner_id:
                try:
                    self.lease_path.unlink(missing_ok=True)
                except OSError:
                    pass
            self._expires_at = 0.0

    # ── 查询 ────────────────────────────────────────────────────────

    def current_owner(self) -> str | None:
        """当前租约文件的 owner_id（无租约 → None）。"""
        with FileLock(self._lock_path, timeout=_LOCK_TIMEOUT) as lock:
            if not lock.acquired:
                return None
            holder = self._read_lease_locked()
        return holder.get("owner_id") if holder else None

    def is_expired(self) -> bool:
        """租约文件存在但已过期（供副本轮询接管时机）。"""
        with FileLock(self._lock_path, timeout=_LOCK_TIMEOUT) as lock:
            if not lock.acquired:
                return False
            holder = self._read_lease_locked()
        if holder is None:
            return False
        return holder.get("expires_at", 0.0) + CLOCK_TOLERANCE < time.monotonic()

    # ── 内部（调用方必须已持有 FileLock）──────────────────────────────

    def _read_lease_locked(self) -> dict | None:
        try:
            with open(self.lease_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def _write_lease_locked(self, now: float) -> None:
        payload = {"owner_id": self.owner_id,
                   "expires_at": round(now + self.ttl, 3),
                   "updated_at": round(now, 3)}
        tmp = self.lease_path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.replace(tmp, self.lease_path)  # 原子替换，防半写
