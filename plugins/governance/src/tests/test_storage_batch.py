"""P2 (暗雷区) — SQLite 批量提交 + WAL 测试。

验证:
  1. 写锁竞争降低: 正常路径批量提交（batch_size=100 → commit 次数 N/100）
  2. 读-己-写一致: 未满批记录在 get_*/count/get_trace 立即可见（读路径 flush）
  3. 并发安全: 100 线程并发 save 无丢失（锁串行化 + 单事务批量）
  4. 降级保持: 批量 flush 失败 → _pending 缓冲（DEBT-0008 语义不回归）
  5. WAL 生效: 文件库 journal_mode=wal（写不阻塞读）
  6. 熔断状态仍立即持久化（不走缓冲 —— DEBT-0011 语义保持）
"""

import sqlite3
import threading
import time
import uuid

import pytest

from src.storage import Storage, DEFAULT_BATCH_SIZE


def _decision(i: int = 0) -> dict:
    return {
        "id": f"p2-{uuid.uuid4().hex[:8]}-{i}",
        "verdict": "ALLOW",
        "reason": "batch-test",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "path": "/api/x",
        "method": "GET",
        "matched_rule": None,
        "rationale": "P2 test",
    }


# ── 1. 批量提交 + 合并行为 ─────────────────────────────────────────────

def test_save_batches_and_reduces_commits(tmp_path):
    """批量合并: 150 条 save → 满批自动 flush（1 次）+ 读路径 flush（1 次）
    = 2 次批量提交（旧实现 150 次逐条 commit）。"""
    db = tmp_path / "b.db"
    storage = Storage(str(db))
    flush_calls = []

    orig_flush = storage._flush_write_buffer

    def _spy():
        flush_calls.append(len(storage._write_buffer))
        return orig_flush()

    storage._flush_write_buffer = _spy
    try:
        for i in range(150):
            storage.save(_decision(i))
        # 满批(100)时自动 flush 1 次
        assert flush_calls and flush_calls[0] == 100
        # 读路径 flush 剩余 50
        assert storage.count() == 150
        assert len(flush_calls) == 2
        assert flush_calls[1] == 50
        # 缓冲已清空（批量提交完成，无残留）
        assert len(storage._write_buffer) == 0
    finally:
        storage._flush_write_buffer = orig_flush
        storage.close()


def test_read_your_write_unflushed(tmp_path):
    db = tmp_path / "b.db"
    storage = Storage(str(db))
    try:
        d = _decision(1)
        storage.save(d)  # 未满批，仍在缓冲
        got = storage.get_by_id(d["id"])
        assert got is not None and got["id"] == d["id"]  # 读路径 flush
        assert storage.count() == 1
    finally:
        storage.close()


def test_trace_readable_before_batch_full(tmp_path):
    db = tmp_path / "b.db"
    storage = Storage(str(db))
    try:
        storage.save(_decision(1))
        storage.save(_decision(2))
        tree = storage.get_trace("no-such-trace")  # 读路径 flush 不崩溃
        assert tree == []
        assert storage.count() == 2
    finally:
        storage.close()


# ── 2. 并发安全 ────────────────────────────────────────────────────────

def test_concurrent_saves_100_no_loss(tmp_path):
    db = tmp_path / "conc.db"
    storage = Storage(str(db), batch_size=25)
    errors = []

    def _worker(i):
        try:
            storage.save(_decision(i))
        except Exception as e:  # pragma: no cover
            errors.append(e)

    try:
        threads = [threading.Thread(target=_worker, args=(i,))
                   for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert storage.count() == 100  # 无丢失（锁 + 单事务批量）
    finally:
        storage.close()


# ── 3. 降级保持（DEBT-0008 语义不回归）────────────────────────────────

def test_batch_flush_failure_falls_back_to_pending(tmp_path):
    """真实失败路径: 底层连接关闭 → executemany 抛 ProgrammingError
    （sqlite3.Error 子类）→ 满批 flush 失败 → 降级缓冲不丢记录。"""
    db = tmp_path / "d.db"
    storage = Storage(str(db), batch_size=3)
    try:
        storage.conn.close()  # 制造真实写失败（不走 storage.close() 以免 flush）
        for i in range(5):
            storage.save(_decision(i))
        # 3 条满批 flush 失败 → _pending；2 条未满批仍在 _write_buffer
        assert storage.pending_count() == 3
        assert len(storage._write_buffer) == 2
        # 显式 flush 把剩余 2 条也转降级（DB 不可用时不调读路径 —— 读失败应暴露）
        storage.flush_pending()
        assert storage.pending_count() == 5
    finally:
        storage.close()


def test_flush_pending_recovers_buffer(tmp_path):
    db = tmp_path / "e.db"
    storage = Storage(str(db), batch_size=3)
    try:
        storage.conn.close()  # 失败路径
        for i in range(5):
            storage.save(_decision(i))
        storage.flush_pending()  # 缓冲 2 条转 pending；逐条重试也失败 → 0
        assert storage.pending_count() == 5
        # 重建底层连接（表已存在）→ flush_pending 恢复落库
        storage.conn = sqlite3.connect(str(db))
        assert storage.flush_pending() == 5
        assert storage.count() == 5
        assert storage.pending_count() == 0
    finally:
        storage.close()


# ── 4. WAL + breaker 立即持久化 ────────────────────────────────────────

def test_wal_enabled_on_file_db(tmp_path):
    db = tmp_path / "w.db"
    storage = Storage(str(db))
    try:
        mode = storage.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal", f"journal_mode={mode}, 期望 wal"
    finally:
        storage.close()


def test_breaker_state_persists_immediately(tmp_path):
    """DEBT-0011: 熔断状态不走批量缓冲 — 立即提交（重启防绕过冷却窗）。"""
    db = tmp_path / "br.db"
    storage = Storage(str(db))
    try:
        storage.save(_decision(1))  # 制造缓冲未满状态
        storage.save_breaker_state(count=7, last_escalate=123.0, tripped_until=456.0)
        st = storage.load_breaker_state()
        assert st["count"] == 7
        assert st["tripped_until"] == 456.0  # 无需 flush 即可见
    finally:
        storage.close()


def test_batch_size_default():
    assert DEFAULT_BATCH_SIZE == 100  # 协议确认表: batch_size=100
