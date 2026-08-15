# GATE2-APPROVED: metacognition observer v1
"""元认知观察层测试 (v1.39.1-metaobs)。

验收 (用户批准设计):
  1. record: 决策上下文写入 decision_meta 表, 非阻塞
  2. consistency: 按 path 分组, 最近 N 条 verdict 分布
  3. deviation: 与历史主流偏差 > 阈值 (默认 30%) 触发 MetaEvent
  4. 边界: 冷启动不误报 / 主流一致不触发 / fail-soft 不抛异常
  5. 集成: get_events 供 Critic 消费, audit_log 追加
"""

import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.metacognition.observer import (  # noqa: E402
    DEFAULT_DEVIATION,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_WINDOW,
    MetaEvent,
    MetacognitionObserver,
)


# ── fixtures ─────────────────────────────────────────────────────

_seq = 0  # 全局序号: 保证每次 record 的 decision_id 唯一


@pytest.fixture
def observer(tmp_path):
    obs = MetacognitionObserver(db_path=tmp_path / "meta.db")
    yield obs
    obs.close()


def _rec(obs, path, verdict, n=1, trace=None, decision_id=None):
    """写入 n 条决策上下文, 返回最后一条的 event。"""
    global _seq
    event = None
    for _ in range(n):
        _seq += 1
        event = obs.record(
            decision_id=decision_id or f"d-{path}-{_seq}",
            path=path,
            verdict=verdict,
            trace_id=trace or f"t-{path}-{_seq}",
            method="POST",
            matched_rule=f"rule-{verdict.lower()}",
            confidence=0.9,
        )
    return event


# ── 1. 记录 ─────────────────────────────────────────────────────

def test_record_writes_meta_row(observer):
    """record 后 decision_meta 表应有 1 行, 字段完整。"""
    _rec(observer, "/v1/chat", "ALLOW")
    assert observer.meta_count() == 1
    rows = observer.get_meta(path="/v1/chat")
    assert len(rows) == 1
    row = rows[0]
    assert row["verdict"] == "ALLOW"
    assert row["path"] == "/v1/chat"
    assert row["method"] == "POST"
    assert row["matched_rule"] == "rule-allow"
    assert row["confidence"] == 0.9
    assert row["event"] is None  # 冷启动: 样本不足, 不触发偏差


def test_record_returns_none_on_cold_start(observer):
    """冷启动 (样本 < min_samples) 不触发偏差, 返回 None。"""
    event = _rec(observer, "/v1/chat", "ALLOW")
    assert event is None


def test_record_preserves_trace_id(observer):
    """trace_id 与 decision_id 正确落盘。"""
    _rec(observer, "/v1/chat", "ALLOW", trace="trace-abc", decision_id="dec-1")
    row = observer.get_meta(path="/v1/chat")[0]
    assert row["trace_id"] == "trace-abc"
    assert row["id"] == "dec-1"


# ── 2. 一致性 (按 path 分组) ────────────────────────────────────

def test_consistency_groups_by_path(observer):
    """不同 path 互不干扰: /a 的主流不影响 /b 的判定。"""
    for _ in range(DEFAULT_MIN_SAMPLES + 2):
        _rec(observer, "/v1/a", "ALLOW")
    # /b 冷启动 — 即使 /a 全是 ALLOW, /b 的 DENY 也不触发 (独立分组)
    event = _rec(observer, "/v1/b", "DENY")
    assert event is None


def test_consistency_majority_agreement_no_event(observer):
    """当前决策与主流一致 → 不触发。"""
    for _ in range(DEFAULT_MIN_SAMPLES):
        _rec(observer, "/v1/chat", "ALLOW")
    event = _rec(observer, "/v1/chat", "ALLOW")
    assert event is None


# ── 3. 偏差触发 ─────────────────────────────────────────────────

def test_deviation_triggered_on_minority(observer):
    """当前决策为少数派且偏差 > 阈值 → 触发 MetaEvent。"""
    # 历史: 8 条 ALLOW (主流)
    for _ in range(DEFAULT_MIN_SAMPLES + 3):
        _rec(observer, "/v1/chat", "ALLOW")
    # 当前: DENY → 少数派
    event = _rec(observer, "/v1/chat", "DENY")
    assert event is not None
    assert event.path == "/v1/chat"
    assert event.verdict == "DENY"
    assert event.majority_verdict == "ALLOW"
    assert event.deviation > DEFAULT_DEVIATION
    assert event.window >= DEFAULT_MIN_SAMPLES


def test_deviation_event_fields(observer):
    """MetaEvent 字段完整 (trace_id / decision_id / meta 分布)。"""
    for _ in range(DEFAULT_MIN_SAMPLES + 3):
        _rec(observer, "/v1/chat", "ALLOW")
    event = _rec(observer, "/v1/chat", "DENY", trace="trace-xyz", decision_id="dec-9")
    assert event.trace_id == "trace-xyz"
    assert event.decision_id == "dec-9"
    assert event.to_dict()["meta"]["counts"]["ALLOW"] >= DEFAULT_MIN_SAMPLES
    assert event.to_dict()["meta"]["threshold"] == DEFAULT_DEVIATION


def test_deviation_within_threshold_no_event(observer):
    """偏差 ≤ 阈值不触发 (边界: 5:5 平局 → 偏差 0.5 > 0.3 触发; 用 4:1)."""
    for _ in range(4):
        _rec(observer, "/v1/chat", "ALLOW")
    _rec(observer, "/v1/chat", "DENY")  # 4 ALLOW + 1 DENY → 主流 ALLOW 占比 0.8
    # 当前 ALLOW = 主流 → 不触发
    event = _rec(observer, "/v1/chat", "ALLOW")
    assert event is None


def test_deviation_after_min_samples_boundary(observer):
    """恰好 min_samples 条历史时的判定。"""
    for _ in range(DEFAULT_MIN_SAMPLES):
        _rec(observer, "/v1/chat", "ALLOW")
    event = _rec(observer, "/v1/chat", "DENY")
    assert event is not None
    assert event.window == DEFAULT_MIN_SAMPLES


# ── 4. 边界与 fail-soft ─────────────────────────────────────────

def test_observer_fail_soft_on_bad_params(observer):
    """异常参数不抛异常: 非法 window/阈值被钳制。"""
    obs = MetacognitionObserver(
        db_path=observer.db_path, window=-5, deviation_threshold=99.0,
        min_samples=0)
    try:
        event = obs.record(decision_id="x", path="/v1/x", verdict="ALLOW")
        assert event is None
        assert obs.window == 1          # 钳制到最小
        assert obs.deviation_threshold == 1.0
        assert obs.min_samples == 1
    finally:
        obs.close()


def test_observer_fail_soft_on_closed(observer):
    """close 后再 record 不抛异常 (fail-soft)."""
    obs = MetacognitionObserver(db_path=observer.db_path)
    obs.close()
    # close 后 _conn=None → record 内部 _ensure_conn 重建连接, 仍可用
    event = obs.record(decision_id="y", path="/v1/y", verdict="ALLOW")
    assert event is None
    obs.close()


def test_record_on_invalid_verdict_still_stores(observer):
    """verdict 任意字符串均可记录 (observer 不做判定, 只观察)。"""
    event = _rec(observer, "/v1/chat", "WEIRD")
    # 冷启动无 event; 数据仍在
    assert observer.meta_count() == 1


# ── 5. 集成: get_events + audit_log ─────────────────────────────

def test_get_events_consumable_by_critic(observer):
    """偏差事件经 get_events 可被 Critic 消费。"""
    for _ in range(DEFAULT_MIN_SAMPLES + 3):
        _rec(observer, "/v1/chat", "ALLOW")
    _rec(observer, "/v1/chat", "DENY")
    events = observer.get_events()
    assert len(events) == 1
    assert events[0]["event"] == "deviation"
    assert events[0]["path"] == "/v1/chat"
    assert events[0]["verdict"] == "DENY"


def test_audit_log_appended(tmp_path):
    """audit_log_path 配置时偏差事件追加写入 (供 Critic 后期消费)。"""
    audit = tmp_path / "audit_log.md"
    obs = MetacognitionObserver(db_path=tmp_path / "meta2.db",
                                audit_log_path=audit)
    try:
        for i in range(DEFAULT_MIN_SAMPLES + 3):
            obs.record(decision_id=f"a{i}", path="/v1/chat", verdict="ALLOW")
        obs.record(decision_id="dev-1", path="/v1/chat", verdict="DENY",
                   trace_id="trace-audit")
        content = audit.read_text(encoding="utf-8")
        assert "METAOBS" in content
        assert "path=/v1/chat" in content
        assert "verdict=DENY" in content
        assert "majority=ALLOW" in content
        assert "trace=trace-audit" in content
    finally:
        obs.close()


def test_audit_log_no_event_no_write(tmp_path):
    """无偏差事件 → audit 文件不产生内容。"""
    audit = tmp_path / "audit_log.md"
    obs = MetacognitionObserver(db_path=tmp_path / "meta3.db",
                                audit_log_path=audit)
    try:
        for i in range(DEFAULT_MIN_SAMPLES):
            obs.record(decision_id=f"n{i}", path="/v1/chat", verdict="ALLOW")
        assert not audit.exists() or audit.read_text(encoding="utf-8") == ""
    finally:
        obs.close()


# ── 6. 参数可配置 ───────────────────────────────────────────────

def test_custom_threshold(observer):
    """自定义阈值: 更敏感 (0.1) 时 8:2 分布也触发。"""
    obs = MetacognitionObserver(db_path=observer.db_path,
                                deviation_threshold=0.1,
                                min_samples=5)
    try:
        for i in range(8):
            obs.record(decision_id=f"c{i}", path="/v1/t", verdict="ALLOW")
        # 8 ALLOW + 1 DENY → 主流占比 0.89, 偏差 0.11 > 0.1 → 触发
        event = obs.record(decision_id="c9", path="/v1/t", verdict="DENY")
        assert event is not None
        assert event.deviation > 0.1
    finally:
        obs.close()


def test_custom_window(observer):
    """窗口截断: window=3 时只看最近 3 条, 旧的主流不参与判定。"""
    obs = MetacognitionObserver(db_path=observer.db_path, window=3,
                                min_samples=2)
    try:
        for i in range(5):
            obs.record(decision_id=f"w{i}", path="/v1/t", verdict="ALLOW")
        # 最近 3 条全是 ALLOW; 当前 DENY → 偏差 1.0 触发
        event = obs.record(decision_id="w5", path="/v1/t", verdict="DENY")
        assert event is not None
        assert event.window == 3
    finally:
        obs.close()


def test_trim_caps_rows(observer):
    """max_meta_rows 裁剪: 超限时最旧行被删除。"""
    obs = MetacognitionObserver(db_path=observer.db_path, max_meta_rows=10)
    try:
        for i in range(15):
            obs.record(decision_id=f"t{i}", path=f"/v1/p{i % 3}",
                       verdict="ALLOW")
        assert obs.meta_count() <= 10
    finally:
        obs.close()
