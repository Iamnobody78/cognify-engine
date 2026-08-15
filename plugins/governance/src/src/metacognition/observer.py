"""元认知观察层 (Meta-Cognition Observer) — v1.39.1-metaobs

设计边界 (用户批准, 2026-08-04):
  1. 记录: 在 storage.save() 之后异步记录决策上下文 (confidence/verdict/
     matched_rule/trace_id/path) 到独立 decision_meta 表, 非阻塞
  2. 一致性: 按 path 分组, 最近 N 条 (默认 50) 的 verdict 分布; 当前决策
     与历史主流偏差超过阈值 (默认 30%) 时触发 MetaEvent
  3. 偏差处理: logger.warning + audit_log.md 追加, 不阻断主流程

明确不做的 (边界):
  - 不预测 (无 embedding/模型)
  - 不阻断 (observer 异常绝不影响网关主路径 — fail-soft)
  - 不修改策略 (policies.yaml 零改动)
  - 不抢 Critic 的活 (Critic 消费 MetaEvent, observer 只产生信号)

设计动机: 外部审查暴露"决策无自我感知"缺口 + 元认知提案 (Meta-Cognition
in AI Governance) 概念本地化 — 但**不依赖任何 0★ 外部仓库** (事实核查
AUDIT-0061: MonikaKroe/meta-cognition-ai-governance 仅 0★, 无集成价值)。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("metacognition.observer")

# 默认参数 (与批准设计一致)
DEFAULT_WINDOW = 50          # 一致性检测窗口: 最近 N 条
DEFAULT_DEVIATION = 0.30     # 偏差阈值: 当前与历史主流偏差超过 30% 触发
DEFAULT_MIN_SAMPLES = 5      # 最少样本数, 不足则不判定 (避免冷启动误报)
DEFAULT_MAX_META_ROWS = 5000 # decision_meta 表行数上限 (防无限膨胀)

# 独立于 decisions 的元数据表: 记录决策上下文 + 观察信号, 不污染审计主链
# v1.42.1-step2: 新增 cot TEXT — 可解释主控 Step 2 的 CoT 决策轨迹
# (真实决策回放: request → policy → breaker/revoke → verdict, JSON 字符串)
_CREATE_META_SQL = """
CREATE TABLE IF NOT EXISTS decision_meta (
    id TEXT PRIMARY KEY,
    trace_id TEXT,
    path TEXT NOT NULL,
    method TEXT,
    verdict TEXT NOT NULL,
    matched_rule TEXT,
    confidence REAL,
    deviation REAL,
    event TEXT,
    cot TEXT,
    timestamp TEXT NOT NULL
)
"""
_INSERT_META_SQL = """INSERT INTO decision_meta
    (id, trace_id, path, method, verdict, matched_rule, confidence,
     deviation, event, cot, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""


@dataclass
class MetaEvent:
    """偏差事件 — observer 的输出信号, 供 Critic/日志消费。

    语义: 当前决策 verdict 与同 path 最近 N 条历史的主流 verdict
    偏差超过阈值。deviation = 1 - (主流占比), 即"非主流程度"。
    """

    path: str
    verdict: str
    majority_verdict: str
    deviation: float
    window: int
    trace_id: Optional[str] = None
    decision_id: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())
    meta: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "verdict": self.verdict,
            "majority_verdict": self.majority_verdict,
            "deviation": round(self.deviation, 4),
            "window": self.window,
            "trace_id": self.trace_id,
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "meta": self.meta,
        }


class MetacognitionObserver:
    """元认知观察层 — 记录 + 一致性检测 + 偏差事件。

    线程安全: 内部锁保护 SQLite 连接 (与 Storage 同模式, 但表独立)。
    fail-soft: 任何异常 (db 锁/损坏/参数错误) 被捕获并降级为 warning,
    绝不向上抛 — 网关主路径不受 observer 影响。
    """

    def __init__(
        self,
        db_path: str | Path,
        window: int = DEFAULT_WINDOW,
        deviation_threshold: float = DEFAULT_DEVIATION,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        max_meta_rows: int = DEFAULT_MAX_META_ROWS,
        audit_log_path: Optional[str | Path] = None,
    ) -> None:
        self.db_path = str(db_path)
        self.window = max(1, int(window))
        self.deviation_threshold = max(0.0, min(1.0, float(deviation_threshold)))
        self.min_samples = max(1, int(min_samples))
        self.max_meta_rows = max(10, int(max_meta_rows))  # 下限 10: 防 0/负值, 且允许小窗口测试
        self.audit_log_path = (
            Path(audit_log_path) if audit_log_path else None)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._closed = False
        try:
            self._init_db()
        except sqlite3.Error as exc:  # pragma: no cover — db 打开失败
            logger.warning("metacognition: DB init failed (%s) — observer degraded", exc)

    # ── 内部: DB 初始化 ────────────────────────────────────────────

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error:
            pass  # :memory: 无 WAL, no-op
        self._conn.execute(_CREATE_META_SQL)
        self._migrate_locked()
        self._conn.commit()

    def _migrate_locked(self) -> None:
        """幂等迁移: 老库无 cot 列 (v1.39.1-metaobs 起) → ALTER ADD COLUMN。

        与 storage.py 的 rationale 迁移同模式: PRAGMA table_info 探测列存在性,
        缺失则 ALTER; 已存在 (新库或已迁移) 则 no-op。失败仅 warning, 不阻断
        主流程 (fail-soft, 观察层契约)。
        """
        try:
            cols = [r[1] for r in self._conn.execute(
                "PRAGMA table_info(decision_meta)").fetchall()]
            if "cot" not in cols:
                self._conn.execute(
                    "ALTER TABLE decision_meta ADD COLUMN cot TEXT")
        except sqlite3.Error as exc:  # pragma: no cover — 迁移失败
            logger.warning("metacognition: cot migration failed (%s) — fail-soft", exc)

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._init_db()
        return self._conn

    # ── 1. 记录 (在 storage.save() 之后调用, 异步/非阻塞) ─────────

    def record(
        self,
        *,
        decision_id: str,
        path: str,
        verdict: str,
        trace_id: Optional[str] = None,
        method: Optional[str] = None,
        matched_rule: Optional[str] = None,
        confidence: Optional[float] = None,
        cot: Optional[str] = None,
    ) -> Optional[MetaEvent]:
        """记录一条决策上下文, 并做一致性检测。

        返回偏差 MetaEvent (若有), 否则 None。调用方 (main.py) 在
        storage.save() 之后以 asyncio.create_task/to_thread 方式调用。
        cot: 可解释主控 Step 2 — 决策轨迹回放 (JSON 字符串), 与决策
        同库落盘供审计追踪; 无 LLM 事后解释 (诚实: 只记录真实发生的事件)。
        """
        try:
            with self._lock:
                self._ensure_conn()
                event = self._detect_deviation_locked(
                    path=path, verdict=verdict, decision_id=decision_id,
                    trace_id=trace_id, matched_rule=matched_rule)
                ts = datetime.now(timezone.utc).isoformat()
                self._conn.execute(
                    _INSERT_META_SQL,
                    (decision_id, trace_id, path, method, verdict,
                     matched_rule, confidence,
                     round(event.deviation, 4) if event else None,
                     "deviation" if event else None, cot, ts),
                )
                self._trim_locked()
                self._conn.commit()
            if event:
                self._emit(event)
            return event
        except sqlite3.Error as exc:  # pragma: no cover — db 故障
            logger.warning("metacognition: record failed (%s) — fail-soft", exc)
            return None

    # ── 2. 一致性检测 (按 path 分组) ──────────────────────────────

    def _detect_deviation_locked(
        self,
        *,
        path: str,
        verdict: str,
        decision_id: str,
        trace_id: Optional[str] = None,
        matched_rule: Optional[str] = None,
    ) -> Optional[MetaEvent]:
        """同 path 最近 N 条的历史 verdict 分布 vs 当前 verdict。

        偏差定义: deviation = 1 - current_ratio, 即当前 verdict 在窗口中
        的稀有度 (当前判定越少见, 偏差越大)。历史全 ALLOW + 当前 DENY →
        deviation = 1.0 (最强偏差信号)。
        触发条件: 样本 >= min_samples 且 deviation > deviation_threshold。
        冷启动 (样本不足) 不判定 — 返回 None, 不误报。
        """
        rows = self._conn.execute(
            "SELECT verdict FROM decision_meta WHERE path = ? "
            "ORDER BY timestamp DESC LIMIT ?",
            (path, self.window),
        ).fetchall()
        if len(rows) < self.min_samples:
            return None
        counts: Dict[str, int] = {}
        for (v,) in rows:
            counts[v] = counts.get(v, 0) + 1
        majority_verdict, majority_count = max(
            counts.items(), key=lambda kv: kv[1])
        current_count = counts.get(verdict, 0)
        current_ratio = current_count / len(rows)
        deviation = 1.0 - current_ratio
        if deviation <= self.deviation_threshold:
            return None
        return MetaEvent(
            path=path,
            verdict=verdict,
            majority_verdict=majority_verdict,
            deviation=deviation,
            window=len(rows),
            trace_id=trace_id,
            decision_id=decision_id,
            meta={
                "counts": counts,
                "current_ratio": round(current_ratio, 4),
                "threshold": self.deviation_threshold,
                "min_samples": self.min_samples,
            },
        )

    # ── 3. 偏差处理 (不阻断主流程) ───────────────────────────────

    def _emit(self, event: MetaEvent) -> None:
        """logger.warning + audit_log.md 追加 (供 Critic 后期消费)。"""
        logger.warning(
            "metacognition deviation: path=%s verdict=%s majority=%s "
            "deviation=%.2f window=%d trace=%s",
            event.path, event.verdict, event.majority_verdict,
            event.deviation, event.window, event.trace_id or "-")
        if self.audit_log_path:
            try:
                line = (f"- METAOBS {event.timestamp} path={event.path} "
                        f"verdict={event.verdict} majority={event.majority_verdict} "
                        f"deviation={event.deviation:.2f} trace={event.trace_id or '-'}\n")
                with self.audit_log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError as exc:  # pragma: no cover — 审计文件不可写
                logger.warning("metacognition: audit log append failed (%s)", exc)

    # ── 内部: 表裁剪 + 查询 ──────────────────────────────────────

    def _trim_locked(self) -> None:
        """decision_meta 行数上限, 防无限膨胀 (保留最新 max_meta_rows 行)。

        注意: DELETE ... WHERE id IN (SELECT ... LIMIT -1 OFFSET ?) 在
        SQLite 中参数化 OFFSET 会静默不生效 (rowcount=0), 因此内联
        max_meta_rows 为字面量。已验证: 内联版正常删除, 参数版不删。
        """
        try:
            limit = int(self.max_meta_rows)
            self._conn.execute(
                "DELETE FROM decision_meta WHERE id IN ("
                "  SELECT id FROM decision_meta ORDER BY timestamp DESC "
                f"  LIMIT -1 OFFSET {limit})")
        except sqlite3.Error:
            pass  # 裁剪失败不阻断写入

    def meta_count(self) -> int:
        """已记录的元数据条数 (测试/监控用)。"""
        try:
            with self._lock:
                self._ensure_conn()
                row = self._conn.execute(
                    "SELECT COUNT(*) FROM decision_meta").fetchone()
                return row[0] if row else 0
        except sqlite3.Error:
            return 0

    def get_meta(self, path: Optional[str] = None,
                 limit: int = 100) -> List[Dict]:
        """读取元数据记录 (测试/诊断用)。"""
        try:
            with self._lock:
                self._ensure_conn()
                if path:
                    rows = self._conn.execute(
                        "SELECT * FROM decision_meta WHERE path = ? "
                        "ORDER BY timestamp DESC LIMIT ?", (path, limit))
                else:
                    rows = self._conn.execute(
                        "SELECT * FROM decision_meta "
                        "ORDER BY timestamp DESC LIMIT ?", (limit,))
                cols = [d[0] for d in rows.description]
                return [dict(zip(cols, r)) for r in rows.fetchall()]
        except sqlite3.Error:
            return []

    def get_events(self, limit: int = 50) -> List[Dict]:
        """偏差事件列表 (event='deviation' 的行, 供 Critic 消费)。"""
        try:
            with self._lock:
                self._ensure_conn()
                rows = self._conn.execute(
                    "SELECT * FROM decision_meta WHERE event = 'deviation' "
                    "ORDER BY timestamp DESC LIMIT ?", (limit,))
                cols = [d[0] for d in rows.description]
                return [dict(zip(cols, r)) for r in rows.fetchall()]
        except sqlite3.Error:
            return []

    def append_drift(self, decision_id: str, drift_score: float,
                     flags: Optional[List[str]] = None) -> bool:
        """Step 3: 向已有 decision_meta 行的 cot 轨迹追加 context_drift 事件。

        漂移检测是异步的 (semantic_context_drift_async), 发生在 record()
        之后 — 因此用 UPDATE 追加而非新建行。幂等语义:
          - 行不存在 → no-op (返回 False, 不报错)
          - 行存在且已有 context_drift → 跳过 (每个 decision 只记录一次)
          - 成功追加 → True
        fail-soft: 任何 sqlite3.Error → warning + False, 不阻断调用方。
        """
        return self._append_event_locked(decision_id, "context_drift",
                                         {"t": "context_drift",
                                          "score": round(float(drift_score), 4),
                                          "flags": [str(f) for f in (flags or [])]})

    def append_semantic(self, decision_id: str, score: float,
                        flags: Optional[List[str]] = None,
                        level: Optional[str] = None) -> bool:
        """Step 4: 向已有 decision_meta 行的 cot 轨迹追加 semantic_judge 事件。

        Judge 语义评估结果 (score/flags/派生 level) 进入 CoT 轨迹, 与
        policy/verdict 事件并列 — "为什么 Judge 这么判"的可解释证据。
        幂等语义与 append_drift 相同: 行缺失 no-op / 已记录跳过 /
        成功追加 True。level 为派生值 (非 judge 原始字段), 从 score 映射:
        >= SEMANTIC_HOOK_THRESHOLD(0.85) → high; >= 0.5 → medium; 否则 low。
        """
        if level is None:
            level = ("high" if score >= 0.85
                     else "medium" if score >= 0.5 else "low")
        return self._append_event_locked(decision_id, "semantic_judge",
                                         {"t": "semantic_judge",
                                          "score": round(float(score), 4),
                                          "level": level,
                                          "flags": [str(f) for f in (flags or [])]})

    def _append_event_locked(self, decision_id: str, marker: str,
                             event: Dict) -> bool:
        """通用追加: 向 decision_meta.cot 追加一个事件 dict (幂等)。

        marker: 幂等标记 — cot 中已含该 marker 字符串则跳过 (每 decision
        每事件类型只记录一次)。行缺失 → no-op False。fail-soft。
        """
        try:
            with self._lock:
                self._ensure_conn()
                row = self._conn.execute(
                    "SELECT cot FROM decision_meta WHERE id = ?",
                    (decision_id,)).fetchone()
                if row is None:
                    return False  # 决策已裁剪/不存在 → no-op
                old = row[0] or ""
                if f'"{marker}"' in old:
                    return False  # 幂等: 已记录过
                drift = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                # 追加到步骤数组尾部 (兼容既有数组, 保持 JSON 合法)
                if old.strip().endswith("]"):
                    new_cot = old.rstrip()[:-1] + "," + drift + "]"
                else:
                    new_cot = "[" + drift + "]"
                self._conn.execute(
                    "UPDATE decision_meta SET cot = ? WHERE id = ?",
                    (new_cot, decision_id))
                self._conn.commit()
                return True
        except sqlite3.Error as exc:  # pragma: no cover — db 故障
            logger.warning("metacognition: append %s failed (%s) — fail-soft",
                           marker, exc)
            return False

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except sqlite3.Error:  # pragma: no cover
                    pass
                self._conn = None
            self._closed = True


# ── CLI: 便捷诊断 (可选) ──────────────────────────────────────────

def _cli() -> int:  # pragma: no cover — 交互式工具
    import argparse

    ap = argparse.ArgumentParser(description="Meta-Cognition observer 诊断")
    ap.add_argument("--db", default="audit.db", help="SQLite 路径")
    ap.add_argument("--events", action="store_true", help="列出偏差事件")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    obs = MetacognitionObserver(db_path=args.db)
    if args.events:
        for ev in obs.get_events(limit=args.limit):
            print(json.dumps(ev, ensure_ascii=False, default=str))
    else:
        print(f"meta rows: {obs.meta_count()} / events: {len(obs.get_events())}")
    obs.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
