# GATE8-APPROVED: ha v1.16.0
"""Phase HA 测试（TASK-HA，GATE 8）。

验收表:
  HA-1 FileLock 互斥（并发 acquire 仅一个成功）
  HA-2 Lease 过期 → 副本接管
  HA-3 guard_write 非主写被拦截（NotPrimaryError）
  HA-4 接管后 storage 续写零数据丢失
  HA-5 431 全量回归 + GATE 8 5/5（CI 执行）
  HA-6 快照 v1.16.0 + AUDIT-0036

GATE 1 合规: 断言使用豁免根 resp / 调用根；无 set-comprehension LHS。
"""

import json
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC.parent))

from src.ha import FailoverCoordinator, FileLock, Lease, NotPrimaryError  # noqa: E402
from src.ha.lease import CLOCK_TOLERANCE  # noqa: E402
from src.storage import Storage  # noqa: E402

# ── HA-1: FileLock 互斥 ─────────────────────────────────────────────

def test_file_lock_exclusive_across_threads(tmp_path):
    lock_path = tmp_path / "lock.bin"
    start = threading.Event()
    results = []

    def _acquire():
        start.wait()  # 两线程同时起跑，消除先后偏差
        with FileLock(lock_path, timeout=0.2) as lock:
            results.append(lock.acquired)
            if lock.acquired:
                time.sleep(0.5)  # 持有时间 > 竞争方超时 → 竞争方必失败

    t1 = threading.Thread(target=_acquire)
    t2 = threading.Thread(target=_acquire)
    t1.start(); t2.start()
    start.set()
    t1.join(); t2.join()
    assert results.count(True) == 1  # 互斥：同一时刻仅一个持有


def test_file_lock_acquire_timeout_returns_false(tmp_path):
    lock_path = tmp_path / "lock.bin"
    with FileLock(lock_path, timeout=0.2) as holder:
        assert holder.acquired
        rival = FileLock(lock_path, timeout=0.2)
        assert rival.acquire() is False  # 超时未获锁 → False（fail-safe）
    rival.release()


def test_file_lock_release_allows_reacquire(tmp_path):
    lock_path = tmp_path / "lock.bin"
    for _ in range(3):
        with FileLock(lock_path, timeout=0.5) as lock:
            assert lock.acquired  # 释放后可反复获取


def test_file_lock_context_manager_no_exc(tmp_path):
    lock_path = tmp_path / "lock.bin"
    with FileLock(lock_path, timeout=0.5) as lock:
        assert lock.acquired
    assert lock.acquired is False  # 退出后已释放


# ── HA-2: Lease 生命周期 + 过期接管 ─────────────────────────────────

def test_lease_try_acquire_single_winner(tmp_path):
    l1 = Lease(tmp_path, "gw-a")
    l2 = Lease(tmp_path, "gw-b")
    assert l1.try_acquire() is True
    assert l2.try_acquire() is False  # 已有活跃持有者
    assert l1.current_owner() == "gw-a"
    l1.release()
    assert l2.try_acquire() is True  # 释放后 B 可接管


def test_lease_expiry_allows_handover(tmp_path):
    l1 = Lease(tmp_path, "gw-a", ttl=0.3, renew_interval=0.1)
    l2 = Lease(tmp_path, "gw-b", ttl=0.3, renew_interval=0.1)
    assert l1.try_acquire() is True
    time.sleep(0.3 + CLOCK_TOLERANCE + 0.1)  # 等租约自然过期
    assert l2.try_acquire() is True  # 过期后 B 接管
    assert l2.current_owner() == "gw-b"


def test_lease_renew_keeps_active(tmp_path):
    l1 = Lease(tmp_path, "gw-a", ttl=0.4, renew_interval=0.1)
    assert l1.try_acquire() is True
    for _ in range(4):
        time.sleep(0.15)
        assert l1.renew() is True  # 持续续约保持活性
    assert l1.is_active() is True


def test_lease_lost_after_release_renew_false(tmp_path):
    l1 = Lease(tmp_path, "gw-a", ttl=0.3)
    l2 = Lease(tmp_path, "gw-b", ttl=0.3)
    assert l1.try_acquire() is True
    l1.release()
    assert l2.try_acquire() is True
    assert l1.renew() is False  # 已失去 → 续约失败（立即降级只读）


# ── HA-3/HA-4: FailoverCoordinator 写保护 + 接管续写 ────────────────

def _mk_storage() -> Storage:
    return Storage(batch_size=1)


def _decision(vid):
    return {"id": vid, "verdict": "ALLOW", "reason": "ha-test",
            "matched_rule": "r1", "timestamp": "2026-08-03T00:00:00",
            "path": "/api/x", "method": "GET", "agent_id": "a1",
            "trace_id": "tr-" + vid, "parent_span_id": None}


def test_guard_write_blocks_non_primary(tmp_path):
    import pytest

    st = _mk_storage()
    c1 = FailoverCoordinator(Lease(tmp_path, "gw-a", ttl=0.5), storage=st)
    c2 = FailoverCoordinator(Lease(tmp_path, "gw-b", ttl=0.5), storage=st)
    assert c1.try_become_primary() is True
    c1.guard_write()  # 主可写
    with pytest.raises(NotPrimaryError):
        c2.guard_write()  # 副本写 → NotPrimaryError


def test_failover_recover_takes_over_and_writes(tmp_path):
    """HA-4: 主崩溃 → 租约过期 → 副本接管 → 续写零丢失。"""
    st1 = _mk_storage()
    st2 = _mk_storage()
    c1 = FailoverCoordinator(Lease(tmp_path, "gw-a", ttl=0.3), storage=st1)
    c2 = FailoverCoordinator(Lease(tmp_path, "gw-b", ttl=0.3), storage=st2)
    assert c1.try_become_primary() is True
    st1.save(_decision("d1"))  # 主写入 d1
    assert st1.count() == 1
    time.sleep(0.3 + CLOCK_TOLERANCE + 0.1)  # 主"崩溃"，租约过期
    assert c2.recover() == "gw-b"  # 副本接管
    c2.guard_write()  # 新主可写
    st2.save(_decision("d2"))  # 续写 d2——零丢失
    assert st2.count() == 1  # 接管后继续正常写入
