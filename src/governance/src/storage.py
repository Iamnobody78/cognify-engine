"""SQLite-based persistent decision storage — not an in-memory dict."""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional

PENDING_MAX = 1000  # DEBT-0009: cap on degraded-mode in-memory buffer (memory safety)
FALLBACK_PATH = "pending_fallback.log"  # DEBT-0013/0014: JSONL disk fallback for records SQLite cannot accept
MAX_FLUSH_ATTEMPTS = 5      # DEBT-0014: consecutive-failure cap before disk fallback (no infinite retry)
FLUSH_BACKOFF_SECONDS = 2.0  # DEBT-0014: min wall-clock gap between flush retries (throttle)
DEFAULT_BATCH_SIZE = 100    # P2 (暗雷区): 正常路径批量提交阈值 — 写锁竞争 N次/秒 → N/100次/秒
logger = logging.getLogger(__name__)


class Storage:
    def __init__(
        self,
        db_path: str = ":memory:",
        fallback_path: str = FALLBACK_PATH,            # DEBT-0013: overflow/eviction disk log
        max_flush_attempts: int = MAX_FLUSH_ATTEMPTS,  # DEBT-0014: retry cap before disk fallback
        flush_backoff: float = FLUSH_BACKOFF_SECONDS,  # DEBT-0014: throttle between retries
        batch_size: int = DEFAULT_BATCH_SIZE,          # P2: 批量提交阈值
    ):
        self.db_path = db_path
        self.fallback_path = fallback_path
        self.max_flush_attempts = max_flush_attempts
        self.flush_backoff = flush_backoff
        self.batch_size = batch_size
        self.conn: Optional[sqlite3.Connection] = None
        # v0.2.2 (external critique #3.1): saves now run via asyncio.to_thread
        # on the event loop; the single shared connection (check_same_thread=False)
        # must be serialized across threads → guard every operation with a lock.
        self._lock = threading.Lock()
        self._pending: List[Dict] = []  # DEBT-0008: degraded-mode in-memory buffer
        self._write_buffer: List[Dict] = []  # P2: 正常路径批量提交缓冲
        self._flush_failures = 0        # DEBT-0014: consecutive failed flush attempts
        self._last_flush_attempt = 0.0  # DEBT-0014: monotonic clock of last flush attempt
        self._init()

    def _init(self) -> None:
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        # P2 (暗雷区): WAL 模式 — 写不阻塞读（100+ 并发时读侧不再等写锁）；
        # synchronous=NORMAL 在 WAL 下是安全的降同步（崩溃最多丢最后提交，
        # 不会损坏库）。:memory: 库返回 "memory"（no-op，不报错）。
        try:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error:
            logger.warning("storage: WAL pragma unavailable (db_path=%r) — 退化回默认 journal", self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                verdict TEXT NOT NULL,
                reason TEXT NOT NULL,
                matched_rule TEXT,
                timestamp TEXT NOT NULL,
                path TEXT NOT NULL,
                method TEXT NOT NULL,
                agent_id TEXT,
                tool_name TEXT,
                tool_lethality REAL,
                trace_id TEXT,
                parent_span_id TEXT,
                rationale TEXT
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ts ON decisions(timestamp DESC)
        """)
        # 注意: idx_trace 必须在 _migrate() 之后创建 — 旧库此时才具备
        # trace_id 列, 提前建索引会触发 "no such column" (TASK-REAL-011 修复)
        self._migrate()
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_trace ON decisions(trace_id)
        """)
        # DEBT-0011: persisted circuit-breaker state (single-row KV) so a gateway
        # restart cannot reset escalate counters and bypass the cooldown window.
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS breaker_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def _migrate(self) -> None:
        """TASK-REAL-010/011 + TASK-REAL-012 Phase 4: additive schema migrations.

        Pre-existing databases gain tool_name / tool_lethality (REAL-010),
        trace_id / parent_span_id (REAL-011) and rationale (REAL-012 Phase 4,
        治理大脑 Phase 1 可解释字段) via SQLite ALTER TABLE ADD COLUMN
        (non-destructive, defaults NULL); fresh databases already carry all
        columns in CREATE TABLE. Old rows read back with NULL — no data loss,
        no backfill. All migrations are additive and idempotent.
        """
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(decisions)")}
        if "tool_name" not in cols:
            self.conn.execute("ALTER TABLE decisions ADD COLUMN tool_name TEXT")
        if "tool_lethality" not in cols:
            self.conn.execute("ALTER TABLE decisions ADD COLUMN tool_lethality REAL")
        if "trace_id" not in cols:
            self.conn.execute("ALTER TABLE decisions ADD COLUMN trace_id TEXT")
        if "parent_span_id" not in cols:
            self.conn.execute("ALTER TABLE decisions ADD COLUMN parent_span_id TEXT")
        if "rationale" not in cols:
            self.conn.execute("ALTER TABLE decisions ADD COLUMN rationale TEXT")

    _INSERT_SQL = """INSERT INTO decisions (id, verdict, reason, matched_rule, timestamp, path, method, agent_id, tool_name, tool_lethality, trace_id, parent_span_id, rationale)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""

    @staticmethod
    def _entry_tuple(decision: Dict):
        return (
            decision["id"], decision["verdict"], decision["reason"],
            decision.get("matched_rule"), decision["timestamp"], decision["path"],
            decision["method"], decision.get("agent_id"), decision.get("tool_name"),
            decision.get("tool_lethality"), decision.get("trace_id"),
            decision.get("parent_span_id"), decision.get("rationale"),
        )

    def _buffer_or_fallback(self, entries: List[Dict]) -> None:
        """P2: 批量 flush 失败 → 整体转降级缓冲（DEBT-0008 语义保持）;
        超 PENDING_MAX 时最旧记录转磁盘 fallback（DEBT-0009/0013 保持）。
        调用方必须已持有 self._lock。"""
        for entry in entries:
            entry.setdefault("_cached_at",
                             datetime.now(timezone.utc).isoformat())
        self._pending.extend(entries)
        if len(self._pending) > PENDING_MAX:
            overflow = self._pending[: len(self._pending) - PENDING_MAX]
            self._pending = self._pending[len(overflow):]
            for dropped in overflow:
                self._append_fallback(dropped)
            logger.warning(
                "degraded buffer full (%d): %d oldest decision(s) backed up to %s",
                PENDING_MAX, len(overflow), self.fallback_path)

    def _flush_write_buffer(self) -> int:
        """P2 (暗雷区): 批量提交缓冲（单事务 executemany）。持锁调用。
        返回 flush 条数；失败 → 整体转降级缓冲（不丢记录，不抛异常）。"""
        if not self._write_buffer:
            return 0
        batch = self._write_buffer
        self._write_buffer = []
        try:
            self.conn.executemany(
                self._INSERT_SQL,
                [self._entry_tuple(d) for d in batch],
            )
            self.conn.commit()
            return len(batch)
        except sqlite3.Error:
            self._buffer_or_fallback(batch)
            return 0

    def save(self, decision: Dict) -> str:
        # P2 (暗雷区): 正常路径不再逐条 commit —— 入缓冲，满 batch_size 时
        # 单事务批量提交。写锁竞争从 N 次/秒 → N/batch_size 次/秒。
        # 审计延迟上限 = batch_size 条（读路径/close/flush_pending 都会 flush）。
        with self._lock:
            self._write_buffer.append(dict(decision))
            if len(self._write_buffer) >= self.batch_size:
                self._flush_write_buffer()
        return decision["id"]

    def flush_pending(self) -> int:
        """DEBT-0008: retry writing buffered decisions. Returns number flushed.

        DEBT-0014: bounded retries — after max_flush_attempts consecutive failed
        attempts (throttled by flush_backoff seconds between attempts) the
        remaining entries are persisted to the disk fallback log and the buffer
        is cleared, so a permanently-down DB cannot cause an infinite retry loop.
        """
        now = time.monotonic()
        with self._lock:
            self._flush_write_buffer()  # P2: 先提交正常路径缓冲
            if not self._pending:
                self._flush_failures = 0
                return 0
            # DEBT-0014 backoff: inside the cooldown window after the retry cap
            # was hit, skip DB work entirely (no write amplification).
            if self._flush_failures >= self.max_flush_attempts and \
                    now - self._last_flush_attempt < self.flush_backoff:
                return 0
            self._last_flush_attempt = now
            flushed = 0
            remaining = []
            for entry in self._pending:
                try:
                    self.conn.execute(
                        """INSERT INTO decisions (id, verdict, reason, matched_rule, timestamp, path, method, agent_id, tool_name, tool_lethality, trace_id, parent_span_id, rationale)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            entry["id"],
                            entry["verdict"],
                            entry["reason"],
                            entry.get("matched_rule"),
                            entry["timestamp"],
                            entry["path"],
                            entry["method"],
                            entry.get("agent_id"),
                            entry.get("tool_name"),
                            entry.get("tool_lethality"),
                            entry.get("trace_id"),
                            entry.get("parent_span_id"),
                            entry.get("rationale"),
                        ),
                    )
                    self.conn.commit()
                    flushed += 1
                except sqlite3.Error:
                    remaining.append(entry)
            if remaining:
                self._flush_failures = min(self._flush_failures + 1, self.max_flush_attempts)
                if self._flush_failures >= self.max_flush_attempts:
                    # DEBT-0014: cap reached → durable escape hatch, stop retrying.
                    for entry in remaining:
                        self._append_fallback(entry)
                    logger.warning(
                        "flush_pending: %d consecutive failures — %d record(s) backed up to %s",
                        self.max_flush_attempts, len(remaining), self.fallback_path,
                    )
                    remaining = []
            else:
                self._flush_failures = 0
            self._pending = remaining
        return flushed

    def _append_fallback(self, entry: Dict) -> None:
        """DEBT-0013/0014: append one record as a JSON line to the fallback log.

        Best-effort by design — if the disk itself is unavailable we cannot do
        better, but we must NEVER raise here (gateway must not fail).
        Caller must already hold self._lock.
        """
        try:
            with open(self.fallback_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.error("fallback log write failed (%s): record %s lost", e, entry.get("id"))

    def pending_count(self) -> int:
        """DEBT-0008: number of decisions buffered in degraded mode."""
        with self._lock:
            return len(self._pending)

    def get_recent(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            self._flush_write_buffer()  # P2: 读-己-写一致（flush 后查）
            rows = self.conn.execute(
                "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count(self) -> int:
        with self._lock:
            self._flush_write_buffer()  # P2: 读-己-写一致
            row = self.conn.execute("SELECT COUNT(*) FROM decisions").fetchone()
        return row[0] if row else 0

    def get_by_id(self, decision_id: str) -> Optional[Dict]:
        with self._lock:
            self._flush_write_buffer()  # P2: 读-己-写一致
            row = self.conn.execute(
                "SELECT * FROM decisions WHERE id = ?", (decision_id,)
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_trace(self, trace_id: str, max_depth: int = 50, max_nodes: int = 500) -> List[Dict]:
        """TASK-REAL-011 (C 阶段): 递归 CTE 返回整条因果调用树。

        根 = 该 trace 下 parent_span_id IS NULL 的节点; 子 = parent_span_id
        指向父决策 id 的行 (span_id == decision.id)。按 depth + timestamp
        排序。防护: UNION 去重天然终止环 (SQLite 递归 CTE 语义) + max_depth
        上限双保险 + max_nodes 上限防滥用。无记录返回 [] (调用方 404)。
        """
        sql = """
        WITH RECURSIVE tree(
            id, verdict, reason, matched_rule, timestamp, path, method,
            agent_id, tool_name, tool_lethality, trace_id, parent_span_id, depth
        ) AS (
            SELECT id, verdict, reason, matched_rule, timestamp, path, method,
                   agent_id, tool_name, tool_lethality, trace_id, parent_span_id, 0
            FROM decisions
            WHERE trace_id = ? AND parent_span_id IS NULL
            UNION
            SELECT d.id, d.verdict, d.reason, d.matched_rule, d.timestamp, d.path,
                   d.method, d.agent_id, d.tool_name, d.tool_lethality,
                   d.trace_id, d.parent_span_id, t.depth + 1
            FROM decisions d JOIN tree t ON d.parent_span_id = t.id
            WHERE d.trace_id = ? AND t.depth < ?
        )
        SELECT id, verdict, reason, matched_rule, timestamp, path, method,
               agent_id, tool_name, tool_lethality, trace_id, parent_span_id, depth
        FROM tree
        ORDER BY depth, timestamp
        LIMIT ?
        """
        try:
            with self._lock:
                self._flush_write_buffer()  # P2: 读-己-写一致（get_trace 可见未满批的写入）
                rows = self.conn.execute(sql, (trace_id, trace_id, max_depth, max_nodes)).fetchall()
        except sqlite3.Error:
            logger.warning("get_trace failed (degraded): returning empty tree")
            return []
        out = []
        for row in rows:
            node = self._row_to_dict(row[:12])
            node["depth"] = row[12]
            out.append(node)
        return out

    def save_breaker_state(self, count: int, last_escalate: float, tripped_until: float) -> None:
        """DEBT-0011: persist circuit-breaker state across restarts."""
        state = {"count": count, "last_escalate": last_escalate, "tripped_until": tripped_until}
        try:
            with self._lock:
                self.conn.execute(
                    "INSERT OR REPLACE INTO breaker_state (key, value) VALUES (?, ?)",
                    ("breaker", json.dumps(state)),
                )
                self.conn.commit()
        except sqlite3.Error:
            logger.warning("save_breaker_state failed (degraded): state not persisted")

    def load_breaker_state(self) -> Dict:
        """DEBT-0011: restore breaker state at startup; defaults if absent."""
        default = {"count": 0, "last_escalate": 0.0, "tripped_until": 0.0}
        try:
            with self._lock:
                row = self.conn.execute(
                    "SELECT value FROM breaker_state WHERE key = ?", ("breaker",)
                ).fetchone()
        except sqlite3.Error:
            return default
        if not row:
            return default
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return default

    @staticmethod
    def _row_to_dict(row) -> Dict:
        return {
            "id": row[0],
            "verdict": row[1],
            "reason": row[2],
            "matched_rule": row[3],
            "timestamp": row[4],
            "path": row[5],
            "method": row[6],
            "agent_id": row[7],
            "tool_name": row[8],
            "tool_lethality": row[9],
            "trace_id": row[10],
            "parent_span_id": row[11],
            "rationale": row[12] if len(row) > 12 else None,
        }

    def close(self) -> None:
        if self.conn:
            try:
                with self._lock:
                    self._flush_write_buffer()  # P2: 关闭前落库未满批记录
            except sqlite3.Error:
                pass
            self.conn.close()
