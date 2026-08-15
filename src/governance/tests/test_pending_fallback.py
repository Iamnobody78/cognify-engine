"""TASK-REAL-007 tests — DEBT-0013 / DEBT-0014 / DEBT-0015.

DEBT-0013: degraded buffer overflow must back the evicted record up to a disk
           fallback log instead of silently dropping it.
DEBT-0014: flush_pending() must bound its retries (cap + backoff) and, once the
           cap is hit, persist remaining records to the fallback log — never an
           infinite retry loop against a permanently-down DB.
DEBT-0015: the shutdown flush handler must have an independent timeout so a
           stuck DB cannot eat web.run_app(shutdown_timeout=10) entirely.

FakeConn mirrors tests/test_storage_degraded.py (sqlite3.Connection.execute is
read-only, so a stand-in is required); it is duplicated here on purpose because
importing across test modules is fragile under some pytest rootdir setups.

P2 note (暗雷区): Storage.save() 现在先入 _write_buffer, 满 batch_size 才经
executemany 批量提交。本文件模拟"每次写都失败"的降级盘 —— batch_size=1
使每次 save() 都是立即写尝试, 与旧版逐条提交语义完全一致 (eviction 数学不变:
PENDING_MAX+3 次 save → pending=PENDING_MAX + 3 条最旧记录进 fallback)。
FakeConn 因此补 executemany(), 与 execute() 一样抛 OperationalError。
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import time

from src import main
from src.storage import PENDING_MAX, Storage

DEGRADED_BATCH = 1  # P2: 降级盘语义 = 每次 save 立即 flush 尝试


class FakeConn:
    """Connection stand-in whose execute() always raises (degraded disk)."""

    def __init__(self, raise_on_execute=True):
        self._raise = raise_on_execute
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._raise:
            raise sqlite3.OperationalError("disk I/O error")
        return FakeCursor()

    def executemany(self, *args, **kwargs):
        # P2: save() 经 _flush_write_buffer() 用 executemany 批量提交。
        self.calls.append(("executemany", args, kwargs))
        if self._raise:
            raise sqlite3.OperationalError("disk I/O error")
        return FakeCursor()

    def commit(self):
        pass

    def close(self):
        pass


class FakeCursor:
    def fetchall(self):
        return []

    def fetchone(self):
        return None


def make_decision(decision_id: str = "test-id-pending-fallback") -> dict:
    return {
        "id": decision_id,
        "verdict": "ALLOW",
        "reason": "test",
        "matched_rule": None,
        "timestamp": "2026-08-03T00:00:00+00:00",
        "path": "/api/chat",
        "method": "POST",
        "agent_id": None,
    }


def read_fallback(path) -> list:
    if not os.path.exists(path):
        return []  # no fallback writes happened → empty
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ── DEBT-0013: buffer overflow → disk fallback ──────────────────────────────


def test_overflow_writes_fallback_log(tmp_path):
    fb = tmp_path / "pending_fallback.log"
    s = Storage(db_path=tempfile.mktemp(suffix=".db"), fallback_path=str(fb),
                batch_size=DEGRADED_BATCH)
    s.conn = FakeConn()
    for i in range(PENDING_MAX + 3):
        s.save(make_decision(decision_id=f"fb-{i:04d}"))

    # Buffer stays bounded; exactly the 3 evicted entries are on disk.
    assert s.pending_count() == PENDING_MAX
    lines = read_fallback(fb)
    assert len(lines) == 3
    ids = {line["id"] for line in lines}
    assert ids == {"fb-0000", "fb-0001", "fb-0002"}, "oldest entries evicted to disk"


def test_overflow_fallback_preserves_full_record(tmp_path):
    fb = tmp_path / "pending_fallback.log"
    s = Storage(db_path=tempfile.mktemp(suffix=".db"), fallback_path=str(fb),
                batch_size=DEGRADED_BATCH)
    s.conn = FakeConn()
    d = make_decision(decision_id="fb-full")
    d["reason"] = "full record survives eviction"
    for _ in range(PENDING_MAX + 1):
        s.save(d)
    line = read_fallback(fb)[0]
    assert line["id"] == "fb-full"
    assert line["reason"] == "full record survives eviction"
    assert line["path"] == "/api/chat"


# ── DEBT-0014: flush retry cap + backoff + fallback dump ───────────────────


def test_flush_retry_cap_dumps_to_fallback(tmp_path):
    fb = tmp_path / "pending_fallback.log"
    s = Storage(
        db_path=tempfile.mktemp(suffix=".db"),
        fallback_path=str(fb),
        max_flush_attempts=3,
        flush_backoff=0.0,
        batch_size=DEGRADED_BATCH,
    )
    s.conn = FakeConn()
    s.save(make_decision(decision_id="capf-0"))
    s.save(make_decision(decision_id="capf-1"))

    assert s.flush_pending() == 0  # failure #1
    assert s.pending_count() == 2
    assert s.flush_pending() == 0  # failure #2
    assert s.pending_count() == 2
    assert s.flush_pending() == 0  # failure #3 → cap → fallback dump

    assert s.pending_count() == 0, "buffer cleared — no infinite retry loop"
    ids = {line["id"] for line in read_fallback(fb)}
    assert ids == {"capf-0", "capf-1"}, "cap-hit records persisted to fallback"


def test_flush_backoff_throttles_retries(tmp_path):
    fb = tmp_path / "pending_fallback.log"
    s = Storage(
        db_path=tempfile.mktemp(suffix=".db"),
        fallback_path=str(fb),
        max_flush_attempts=1,
        flush_backoff=3600.0,  # long cooldown window for the test
        batch_size=DEGRADED_BATCH,
    )
    s.conn = FakeConn()
    s.save(make_decision(decision_id="bk-0"))

    assert s.flush_pending() == 0  # attempt fails → cap (1) → fallback dump
    assert s.pending_count() == 0
    ids = [x["id"] for x in read_fallback(fb)]  # GATE 1: bare-Name compare
    assert ids == ["bk-0"]

    s.save(make_decision(decision_id="bk-1"))  # new record during outage
    assert s.pending_count() == 1

    db_attempts = len(s.conn.calls)
    assert s.flush_pending() == 0  # inside backoff window → throttled
    assert len(s.conn.calls) == db_attempts, "no DB write attempted during backoff"
    assert s.pending_count() == 1, "record kept buffered, not dumped, not retried"


def test_flush_success_resets_failure_counter(tmp_path):
    fb = tmp_path / "pending_fallback.log"
    s = Storage(
        db_path=tempfile.mktemp(suffix=".db"),
        fallback_path=str(fb),
        max_flush_attempts=2,
        flush_backoff=0.0,
        batch_size=DEGRADED_BATCH,
    )
    s.conn = FakeConn()
    s.save(make_decision(decision_id="rs-0"))
    assert s.flush_pending() == 0  # failure #1
    s._init()  # disk recovered
    assert s.flush_pending() == 1  # success
    assert s.pending_count() == 0
    assert read_fallback(fb) == [], "no fallback needed after recovery"


# ── DEBT-0015: shutdown flush has an independent timeout ───────────────────


def test_shutdown_flush_timeout_bounded(caplog):
    """The handler must return at its own budget even when flush_pending stalls.

    Proven via the WARNING: wait_for(flush, timeout=0.01) only logs
    "shutdown flush_pending exceeded" if the 10ms budget fired — had the
    timeout been broken, the handler would have awaited the full 0.2s stall
    and no warning would be emitted. (A wall-clock assertion is unreliable
    here because asyncio.run() itself waits for the executor thread at exit —
    a harness artifact, not part of the production shutdown path.)
    """

    class SlowStorage:
        """Storage whose flush_pending stalls (pathological DB lock)."""

        def flush_pending(self):
            time.sleep(0.2)  # far beyond the test-scale budget below
            return 0

    original_storage = main.storage
    original_timeout = main.SHUTDOWN_FLUSH_TIMEOUT
    main.storage = SlowStorage()
    main.SHUTDOWN_FLUSH_TIMEOUT = 0.01  # 10ms test-scale budget
    try:
        with caplog.at_level("WARNING", logger="src.main"):
            asyncio.run(main._flush_pending_on_shutdown(None))  # must not raise
        assert any(
            "shutdown flush_pending exceeded" in r.message for r in caplog.records
        ), "timeout branch fired — handler did not wait out the stall"
    finally:
        main.storage = original_storage
        main.SHUTDOWN_FLUSH_TIMEOUT = original_timeout


def test_shutdown_flush_success_path(tmp_path):
    s = Storage(
        db_path=tempfile.mktemp(suffix=".db"),
        fallback_path=str(tmp_path / "pending_fallback.log"),
        batch_size=DEGRADED_BATCH,
    )
    s.conn = FakeConn()
    s.save(make_decision(decision_id="sd-0"))
    s._init()  # disk recovered before shutdown

    original_storage = main.storage
    main.storage = s
    try:
        asyncio.run(main._flush_pending_on_shutdown(None))
        assert s.pending_count() == 0, "buffered decision flushed at shutdown"
    finally:
        main.storage = original_storage
