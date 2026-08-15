"""Storage degraded-mode tests (DEBT-0008).

New contract: save() must not raise on sqlite errors — instead it buffers
the decision in an in-memory list with a _cached_at timestamp, and
flush_pending() retries the write later.

NOTE: sqlite3.Connection.execute is read-only (cannot be patch.object'd),
so we substitute a FakeConn whose execute() raises OperationalError.
"""

import os
import sqlite3
import tempfile

from src.storage import Storage


class FakeConn:
    """Connection stand-in whose execute()/executemany() always raise
    (degraded disk). P2: batch flush uses executemany — must raise too."""

    def __init__(self, raise_on_execute=True):
        self._raise = raise_on_execute
        self.calls = []

    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._raise:
            raise sqlite3.OperationalError("disk I/O error")
        return FakeCursor()

    def executemany(self, *args, **kwargs):
        self.calls.append((args, kwargs))
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


def make_storage(batch_size=1) -> Storage:
    # TASK-REAL-007 (DEBT-0013): isolate the disk fallback log so eviction tests
    # never write pending_fallback.log into the repo working tree.
    # P2: 降级测试用 batch_size=1 —— save 立即触发批量 flush，失败即入 _pending
    # （保持"save 失败 → 缓冲立即可见"的 DEBT-0008 契约；默认 100 时失败延迟到满批）。
    return Storage(
        db_path=tempfile.mktemp(suffix=".db"),
        fallback_path=os.path.join(tempfile.mkdtemp(), "pending_fallback.log"),
        batch_size=batch_size,
    )


def make_decision() -> dict:
    return {
        "id": "test-id-0008",
        "verdict": "ALLOW",
        "reason": "test",
        "matched_rule": None,
        "timestamp": "2026-08-03T00:00:00+00:00",
        "path": "/api/chat",
        "method": "POST",
        "agent_id": None,
    }


class TestStorageDegradedMode:
    def test_save_success(self):
        s = make_storage()
        decision = make_decision()
        result = s.save(decision)
        assert result == decision["id"]
        assert s.pending_count() == 0
        s.conn.close()

    def test_save_failure_buffers_in_memory(self):
        s = make_storage()
        s.conn = FakeConn()  # execute() raises OperationalError
        decision = make_decision()

        # MUST NOT raise (DEBT-0008: gateway must not fail)
        result = s.save(decision)

        assert result == decision["id"]
        assert s.pending_count() == 1
        s.conn.close()

    def test_pending_entry_has_cached_at(self):
        s = make_storage()
        s.conn = FakeConn()
        decision = make_decision()

        s.save(decision)

        assert s._pending[0]["_cached_at"]
        # timestamp is ISO-format string
        assert "T" in s._pending[0]["_cached_at"]
        s.conn.close()

    def test_flush_pending_success(self):
        s = make_storage()
        decision = make_decision()

        # Phase 1: degraded disk → buffered
        s.conn = FakeConn()
        s.save(decision)
        assert s.pending_count() == 1

        # Phase 2: disk recovers → _init() rebuilds a healthy connection,
        # flush_pending persists the buffered decision.
        s._init()
        flushed = s.flush_pending()
        assert flushed == 1
        assert s.pending_count() == 0
        recent = s.get_recent(limit=10)
        assert any(
            r.get("id") == decision["id"] for r in recent
        ), "flushed decision must be persisted"
        s.conn.close()

    def test_flush_keeps_failed_entries(self):
        s = make_storage()
        s.conn = FakeConn()
        decision = make_decision()

        s.save(decision)

        # conn.execute still broken → flush fails, entry stays buffered
        flushed = s.flush_pending()

        assert flushed == 0
        assert s.pending_count() == 1
        s.conn.close()

    def test_pending_cap_drops_oldest(self):
        # DEBT-0009: degraded buffer is bounded — filling past PENDING_MAX
        # drops the OLDEST entry so memory stays bounded.
        from src.storage import PENDING_MAX
        s = make_storage()
        s.conn = FakeConn()
        for i in range(PENDING_MAX + 5):
            d = make_decision()
            d["id"] = f"cap-{i:04d}"
            s.save(d)
        assert s.pending_count() == PENDING_MAX
        ids = {e["id"] for e in s._pending}
        assert "cap-0000" not in ids, "oldest entry must be dropped"
        assert f"cap-{PENDING_MAX + 4:04d}" in ids, "newest entry kept"
        s.conn.close()

    def test_shutdown_flush_drains_buffer(self):
        # DEBT-0010: on graceful shutdown main._flush_pending_on_shutdown
        # retries the flush once — a recovered disk drains the whole buffer.
        s = make_storage()
        s.conn = FakeConn()
        for i in range(3):
            d = make_decision()
            d["id"] = f"shutdown-{i}"
            s.save(d)
        assert s.pending_count() == 3
        s._init()  # disk recovers
        flushed = s.flush_pending()
        assert flushed == 3
        assert s.pending_count() == 0
        recent = s.get_recent(limit=10)
        assert any(r.get("id") == "shutdown-2" for r in recent)
        s.conn.close()
