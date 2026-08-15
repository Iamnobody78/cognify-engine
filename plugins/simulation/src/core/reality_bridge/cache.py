"""SQLite cache for RealitySample persistence and offline querying.

Provides:
  - Insert/save RealitySamples
  - Query by channel, time range, episode, tags
  - Aggregation queries (avg reward per channel, winrate trend, etc.)
  - Auto-create schema on first use
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .models import Channel, RealitySample


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reality_samples (
    sample_id   TEXT PRIMARY KEY,
    channel     TEXT NOT NULL,
    timestamp   REAL NOT NULL,
    episode_id  INTEGER DEFAULT 0,
    step        INTEGER DEFAULT 0,
    obs         TEXT,          -- JSON array
    action      INTEGER,
    reward      REAL DEFAULT 0.0,
    win         INTEGER DEFAULT 0,
    episode_length INTEGER DEFAULT 0,
    loss        REAL,
    q_value     REAL,
    epsilon     REAL,
    lr          REAL,
    annotation  TEXT,
    corrected_action INTEGER,
    confidence  REAL DEFAULT 1.0,
    rule_version TEXT,
    gate_decisions TEXT,       -- JSON object
    tags        TEXT,          -- JSON array
    extra       TEXT           -- JSON object
);

CREATE INDEX IF NOT EXISTS idx_channel_ts
    ON reality_samples(channel, timestamp);

CREATE INDEX IF NOT EXISTS idx_episode
    ON reality_samples(channel, episode_id);

CREATE INDEX IF NOT EXISTS idx_win
    ON reality_samples(channel, win);

CREATE TABLE IF NOT EXISTS gap_reports (
    report_id   TEXT PRIMARY KEY,
    generated_at REAL NOT NULL,
    simulation_gap REAL DEFAULT 0.0,
    training_gap REAL DEFAULT 0.0,
    user_feedback_gap REAL DEFAULT 0.0,
    shadow_loop_gap REAL DEFAULT 0.0,
    overall_gap REAL DEFAULT 0.0,
    severity    TEXT DEFAULT 'none',
    detail      TEXT DEFAULT ''
);
"""


class RealityCache:
    """Persistent SQLite cache for RealitySamples."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path(__file__).resolve().parent / "reality_cache.sqlite"
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    # ── Context manager ─────────────────────────────────────────────────

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()

    def open(self) -> None:
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Write ───────────────────────────────────────────────────────────

    def insert(self, sample: RealitySample) -> None:
        if not self._conn:
            raise RuntimeError("Cache not open. Use with RealityCache() as c: or call .open()")
        d = sample.to_dict()
        self._conn.execute(
            """INSERT OR REPLACE INTO reality_samples
               (sample_id, channel, timestamp, episode_id, step, obs, action,
                reward, win, episode_length, loss, q_value, epsilon, lr,
                annotation, corrected_action, confidence,
                rule_version, gate_decisions, tags, extra)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                d["sample_id"], d["channel"], d["timestamp"],
                d["episode_id"], d["step"],
                json.dumps(d["obs"]) if d["obs"] else None,
                d["action"], d["reward"], d["win"], d["episode_length"],
                d["loss"], d["q_value"], d["epsilon"], d["lr"],
                d["annotation"], d["corrected_action"], d["confidence"],
                d["rule_version"],
                json.dumps(d["gate_decisions"]) if d["gate_decisions"] else None,
                json.dumps(d["tags"]),
                json.dumps(d["extra"]),
            ),
        )

    def insert_many(self, samples: List[RealitySample]) -> int:
        """Batch insert. Returns count inserted."""
        if not self._conn:
            raise RuntimeError("Cache not open.")
        count = 0
        for s in samples:
            self.insert(s)
            count += 1
        self._conn.commit()
        return count

    def save_gap_report(self, report: "GapReport") -> None:  # noqa: F821
        if not self._conn:
            raise RuntimeError("Cache not open.")
        d = report.to_dict()
        self._conn.execute(
            """INSERT OR REPLACE INTO gap_reports
               (report_id, generated_at, simulation_gap, training_gap,
                user_feedback_gap, shadow_loop_gap, overall_gap,
                severity, detail)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                d["report_id"], d["generated_at"],
                d["simulation_gap"], d["training_gap"],
                d["user_feedback_gap"], d["shadow_loop_gap"],
                d["overall_gap"], d["severity"], d["detail"],
            ),
        )
        self._conn.commit()

    # ── Read ────────────────────────────────────────────────────────────

    def query(
        self,
        channel: Optional[Channel] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        min_episode: Optional[int] = None,
        max_episode: Optional[int] = None,
        tag: Optional[str] = None,
        limit: int = 1000,
    ) -> List[RealitySample]:
        """Flexible query with multiple filters."""
        if not self._conn:
            raise RuntimeError("Cache not open.")

        clauses = []
        params: list = []

        if channel is not None:
            clauses.append("channel = ?")
            params.append(channel.value)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            clauses.append("timestamp <= ?")
            params.append(until)
        if min_episode is not None:
            clauses.append("episode_id >= ?")
            params.append(min_episode)
        if max_episode is not None:
            clauses.append("episode_id <= ?")
            params.append(max_episode)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        sql = f"SELECT * FROM reality_samples {where} ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()

        results: List[RealitySample] = []
        for row in rows:
            d = dict(row)
            # post-filter by tag (LIKE is slow in JSON, do in Python)
            if tag is not None:
                tags = json.loads(d.get("tags", "[]") or "[]")
                if tag not in tags:
                    continue
            results.append(self._row_to_sample(d))

        return results

    def stats(
        self,
        channel: Optional[Channel] = None,
        since: Optional[float] = None,
    ) -> Dict:
        """Aggregate statistics for a channel and time range."""
        if not self._conn:
            raise RuntimeError("Cache not open.")

        clauses = []
        params: list = []
        if channel is not None:
            clauses.append("channel = ?")
            params.append(channel.value)
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)

        where = ""
        if clauses:
            where = "WHERE " + " AND ".join(clauses)

        sql = f"""
            SELECT
                COUNT(*) as total,
                AVG(reward) as avg_reward,
                SUM(win) as total_wins,
                COUNT(CASE WHEN win=1 THEN 1 END) * 1.0 / MAX(COUNT(*), 1) as winrate,
                AVG(episode_length) as avg_episode_length,
                AVG(loss) as avg_loss,
                AVG(q_value) as avg_q,
                AVG(epsilon) as avg_epsilon,
                AVG(lr) as avg_lr
            FROM reality_samples
            {where}
        """
        row = self._conn.execute(sql, params).fetchone()
        return {
            "total_samples": row[0] or 0,
            "avg_reward": round(row[1] or 0.0, 4),
            "total_wins": row[2] or 0,
            "winrate": round(row[3] or 0.0, 4),
            "avg_episode_length": round(row[4] or 0.0, 2),
            "avg_loss": round(row[5] or 0.0, 6) if row[5] else None,
            "avg_q": round(row[6] or 0.0, 4) if row[6] else None,
            "avg_epsilon": round(row[7] or 0.0, 4) if row[7] else None,
            "avg_lr": round(row[8] or 0.0, 8) if row[8] else None,
        }

    def latest_gap_report(self) -> Optional[Dict]:
        """Return the most recent gap report."""
        if not self._conn:
            raise RuntimeError("Cache not open.")
        row = self._conn.execute(
            "SELECT * FROM gap_reports ORDER BY generated_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return dict(row)

    def total_count(self, channel: Optional[Channel] = None) -> int:
        if not self._conn:
            return 0
        if channel:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM reality_samples WHERE channel=?",
                (channel.value,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM reality_samples"
            ).fetchone()
        return row[0] if row else 0

    # ── Internal ────────────────────────────────────────────────────────

    def _row_to_sample(self, d: Dict) -> RealitySample:
        """Convert a SQLite row dict back to a RealitySample."""
        obs = None
        if d.get("obs"):
            try:
                obs = json.loads(d["obs"])
            except (json.JSONDecodeError, TypeError):
                pass

        gate_decisions = None
        if d.get("gate_decisions"):
            try:
                gate_decisions = json.loads(d["gate_decisions"])
            except (json.JSONDecodeError, TypeError):
                pass

        tags = []
        if d.get("tags"):
            try:
                tags = json.loads(d["tags"])
            except (json.JSONDecodeError, TypeError):
                pass
        # Handle list columns that may already be parsed
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                tags = [tags]

        extra = {}
        if d.get("extra"):
            try:
                extra = json.loads(d["extra"])
            except (json.JSONDecodeError, TypeError):
                pass
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (json.JSONDecodeError, TypeError):
                extra = {}

        return RealitySample(
            sample_id=d.get("sample_id", ""),
            channel=Channel(d.get("channel", "simulation")),
            timestamp=d.get("timestamp", 0.0),
            episode_id=d.get("episode_id", 0),
            step=d.get("step", 0),
            obs=obs,
            action=d.get("action"),
            reward=d.get("reward", 0.0),
            win=bool(d.get("win", 0)),
            episode_length=d.get("episode_length", 0),
            loss=d.get("loss"),
            q_value=d.get("q_value"),
            epsilon=d.get("epsilon"),
            lr=d.get("lr"),
            annotation=d.get("annotation"),
            corrected_action=d.get("corrected_action"),
            confidence=d.get("confidence", 1.0),
            rule_version=d.get("rule_version"),
            gate_decisions=gate_decisions,
            tags=tags,
            extra=extra,
        )
