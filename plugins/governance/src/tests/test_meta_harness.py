# GATE2-APPROVED: meta-harness-adapter v1
"""Meta-Harness 轻量适配器测试（TASK-REAL-012 Phase 2）。

验收: scan 生成候选（高频 DENY 聚合 + 已有覆盖跳过 + 窗口过滤）+ validate
（合并加载 fail-closed + 重放命中率）。零侵入: 用 :memory: Storage 构造数据。
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.meta_harness.adapter import (  # noqa: E402
    DEFAULT_MIN_COUNT,
    generate_policy_suggestions,
    validate_candidate,
)
from src.policy import PolicyEngine  # noqa: E402
from src.storage import Storage  # noqa: E402


def _deny_dict(path, method="POST", tool=None, minutes_ago=1, trace="t-root", idx=0):
    ts = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    # id 必须唯一（decisions.id 主键）——同组多条记录用 idx 区分
    return {
        "id": f"d-{abs(hash((path, tool, minutes_ago, idx)))}",
        "verdict": "DENY",
        "reason": "blocked",
        "matched_rule": "block-dangerous-tools",
        "timestamp": ts,
        "path": path,
        "method": method,
        "agent_id": "agent-a",
        "tool_name": tool,
        "tool_lethality": 0.7,
        "trace_id": trace,
        "parent_span_id": None,
    }


def _seed_storage(records, db_path=":memory:"):
    st = Storage(db_path=db_path)
    for rec in records:
        st.save(rec)
    return st


# ── scan: 候选生成 ───────────────────────────────────────────────────

def test_scan_empty_db_yields_no_candidates(tmp_path):
    st = _seed_storage([])
    resp = generate_policy_suggestions(
        st, out_dir=tmp_path, window_seconds=3600, min_count=3,
        policies_path=str(tmp_path / "no-policies.yaml"))
    assert resp == []


def test_scan_high_frequency_deny_generates_candidate(tmp_path):
    recs = [_deny_dict("/api/exec", tool="shell", idx=i) for i in range(4)]
    st = _seed_storage(recs)
    resp = generate_policy_suggestions(
        st, out_dir=tmp_path, window_seconds=3600, min_count=3,
        policies_path=str(tmp_path / "no-policies.yaml"))
    assert len(resp) == 1
    cand = resp[0]
    assert cand["path"] == "/api/exec"
    assert cand["action"] == "DENY"
    assert cand["count"] == 4
    assert len(cand["evidence"]["decision_ids"]) == 4
    # YAML 文件落盘且 PolicyEngine 可加载（候选格式兼容）
    yaml_file = tmp_path / f"{cand['id']}.yaml"
    assert yaml_file.exists()
    engine = PolicyEngine(str(yaml_file))
    assert engine.evaluate("/api/exec", "POST") is not None


def test_scan_min_count_filters_low_frequency(tmp_path):
    st = _seed_storage([_deny_dict("/api/low", idx=i) for i in range(2)])
    resp = generate_policy_suggestions(
        st, out_dir=tmp_path, window_seconds=3600, min_count=3,
        policies_path=str(tmp_path / "no-policies.yaml"))
    assert resp == []


def test_scan_window_filters_old_denies(tmp_path):
    recs = [_deny_dict("/api/stale", minutes_ago=120, idx=i) for i in range(5)]
    st = _seed_storage(recs)
    resp = generate_policy_suggestions(
        st, out_dir=tmp_path, window_seconds=3600, min_count=3,
        policies_path=str(tmp_path / "no-policies.yaml"))
    assert resp == []  # 全部在窗口外


def test_scan_skips_existing_covered_path(tmp_path):
    recs = [_deny_dict("/api/covered", tool="shell", idx=i) for i in range(5)]
    st = _seed_storage(recs)
    policies = tmp_path / "policies.yaml"
    policies.write_text(yaml.safe_dump({
        "name": "test", "version": "0.1",
        "rules": [{
            "name": "existing", "path_pattern": "/api/covered",
            "method": "POST", "action": "DENY",
        }],
    }), encoding="utf-8")
    resp = generate_policy_suggestions(
        st, out_dir=tmp_path, window_seconds=3600, min_count=3,
        policies_path=str(policies))
    assert resp == []  # 已有 DENY 覆盖 → 不重复建议


def test_scan_groups_by_path_and_method(tmp_path):
    recs = [_deny_dict("/api/a", method="GET", idx=i) for i in range(3)] + \
           [_deny_dict("/api/b", method="POST", idx=i) for i in range(3)]
    st = _seed_storage(recs)
    resp = generate_policy_suggestions(
        st, out_dir=tmp_path, window_seconds=3600, min_count=3,
        policies_path=str(tmp_path / "no-policies.yaml"))
    assert len(resp) == 2


def test_scan_ignores_allow_decisions(tmp_path):
    allow = _deny_dict("/api/ok")
    allow["verdict"] = "ALLOW"
    st = _seed_storage([allow] * 5)
    resp = generate_policy_suggestions(
        st, out_dir=tmp_path, window_seconds=3600, min_count=3,
        policies_path=str(tmp_path / "no-policies.yaml"))
    assert resp == []


# ── validate: 候选验证 ───────────────────────────────────────────────

def test_validate_missing_file_is_invalid(tmp_path):
    resp = validate_candidate(tmp_path / "ghost.yaml")
    assert resp["valid"] is False
    assert "不存在" in resp["reason"]


def test_validate_bad_yaml_is_invalid(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{unclosed: [", encoding="utf-8")
    resp = validate_candidate(str(bad), str(tmp_path / "no-policies.yaml"))
    assert resp["valid"] is False


def test_validate_good_candidate_is_valid(tmp_path):
    cand = tmp_path / "good.yaml"
    cand.write_text(yaml.safe_dump({
        "name": "c", "version": "0.0.1",
        "rules": [{
            "name": "auto-1", "path_pattern": "/api/exec",
            "method": "POST", "action": "DENY",
        }],
    }), encoding="utf-8")
    resp = validate_candidate(str(cand), str(tmp_path / "no-policies.yaml"))
    assert resp["valid"] is True
    assert resp["merged_rule_count"] == 1


def test_validate_replay_hit_rate(tmp_path):
    # 构造 3 条 /api/exec DENY（历史证据）→ 候选命中全部 → hit_rate=1.0
    recs = [_deny_dict("/api/exec", tool="shell", idx=i) for i in range(3)]
    st = _seed_storage(recs)
    cand = tmp_path / "replay.yaml"
    cand.write_text(yaml.safe_dump({
        "name": "c", "version": "0.0.1",
        "rules": [{
            "name": "auto-r", "path_pattern": "/api/exec",
            "method": "POST", "action": "DENY",
        }],
    }), encoding="utf-8")
    resp = validate_candidate(str(cand), str(tmp_path / "no-policies.yaml"), storage=st)
    assert resp["valid"] is True
    assert resp["hit_rate"] == 1.0
    assert resp["checked"] == 3


def test_validate_candidate_not_breaking_existing_policies(tmp_path):
    policies = tmp_path / "policies.yaml"
    policies.write_text(yaml.safe_dump({
        "name": "base", "version": "0.1",
        "rules": [{
            "name": "base-rule", "path_pattern": "/api/base",
            "method": "GET", "action": "ALLOW",
        }],
    }), encoding="utf-8")
    cand = tmp_path / "new.yaml"
    cand.write_text(yaml.safe_dump({
        "name": "c", "version": "0.0.1",
        "rules": [{
            "name": "auto-new", "path_pattern": "/api/exec",
            "method": "POST", "action": "DENY",
        }],
    }), encoding="utf-8")
    resp = validate_candidate(str(cand), str(policies))
    assert resp["valid"] is True
    assert resp["merged_rule_count"] == 2  # base + 候选
