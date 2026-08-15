# GATE2-APPROVED: meta-harness-sandbox v1
"""Meta-Harness 评估沙箱测试（TASK-REAL-012 Phase 3）。

验收: 冲突检测（同 path+method 不同 action → fail-closed）/ pytest 回归 /
可逆部署（backup + 按 name 去重）/ 评估报告。
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.meta_harness.sandbox import (  # noqa: E402
    check_conflicts,
    deploy_candidate,
    evaluate_candidate_in_sandbox,
    generate_eval_report,
    run_pytest_regression,
)
from src.meta_harness.adapter import generate_policy_suggestions  # noqa: E402
from src.storage import Storage  # noqa: E402


def _cand_yaml(tmp_path, name="auto-test", path="/api/exec", action="DENY",
               method="POST"):
    f = tmp_path / f"{name}.yaml"
    f.write_text(yaml.safe_dump({
        "name": "c", "version": "0.0.1",
        "rules": [{"name": name, "path_pattern": path, "method": method,
                   "action": action}],
    }), encoding="utf-8")
    return f


def _policies_yaml(tmp_path, rules):
    f = tmp_path / "policies.yaml"
    f.write_text(yaml.safe_dump(
        {"name": "base", "version": "0.1", "rules": rules},
        allow_unicode=True), encoding="utf-8")
    return f


# ── 冲突检测 ─────────────────────────────────────────────────────────

def test_conflict_detected_high(tmp_path):
    policies = _policies_yaml(tmp_path, [{
        "name": "base-exec", "path_pattern": "/api/exec", "method": "POST",
        "action": "ALLOW"}])
    cand = _cand_yaml(tmp_path, path="/api/exec")  # 候选 DENY vs 现有 ALLOW
    resp = check_conflicts(cand, policies)
    assert any(c["severity"] == "HIGH" for c in resp)
    assert any("action" in c["detail"] for c in resp)


def test_no_conflict_when_different_path(tmp_path):
    policies = _policies_yaml(tmp_path, [{
        "name": "base-other", "path_pattern": "/api/other", "method": "POST",
        "action": "ALLOW"}])
    cand = _cand_yaml(tmp_path, path="/api/exec")
    resp = check_conflicts(cand, policies)
    assert resp == []


def test_same_action_marks_redundant_low(tmp_path):
    policies = _policies_yaml(tmp_path, [{
        "name": "base-exec", "path_pattern": "/api/exec", "method": "POST",
        "action": "DENY"}])
    cand = _cand_yaml(tmp_path, path="/api/exec")
    resp = check_conflicts(cand, policies)
    assert any(c["severity"] == "LOW" for c in resp)


# ── 沙箱评估 ─────────────────────────────────────────────────────────

def test_sandbox_evaluate_good_candidate_deployable(tmp_path):
    cand = _cand_yaml(tmp_path)
    resp = evaluate_candidate_in_sandbox(cand, tmp_path / "ghost.yaml")
    assert resp["deployable"] is True
    assert any("无 action 冲突" in r for r in resp["reasons"])


def test_sandbox_evaluate_conflict_not_deployable(tmp_path):
    policies = _policies_yaml(tmp_path, [{
        "name": "base-exec", "path_pattern": "/api/exec", "method": "POST",
        "action": "ALLOW"}])
    cand = _cand_yaml(tmp_path, path="/api/exec")
    resp = evaluate_candidate_in_sandbox(cand, policies)
    assert resp["deployable"] is False
    assert len(resp["conflicts"]) == 1


def test_sandbox_evaluate_bad_candidate_not_deployable(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{broken: [", encoding="utf-8")
    resp = evaluate_candidate_in_sandbox(bad, tmp_path / "ghost.yaml")
    assert resp["deployable"] is False
    assert resp["checked"] == 0


def test_sandbox_evaluate_with_storage_replay(tmp_path):
    # 3 条 /api/exec DENY → hit_rate=1.0
    st = Storage(db_path=":memory:")
    now = datetime.now(timezone.utc).isoformat()
    for i in range(3):
        st.save({"id": f"s-{i}", "verdict": "DENY", "reason": "r",
                 "matched_rule": "r", "timestamp": now, "path": "/api/exec",
                 "method": "POST", "agent_id": "a", "tool_name": None,
                 "tool_lethality": None, "trace_id": None, "parent_span_id": None})
    cand = _cand_yaml(tmp_path)
    resp = evaluate_candidate_in_sandbox(cand, tmp_path / "ghost.yaml", storage=st)
    assert resp["hit_rate"] == 1.0
    assert resp["checked"] == 3


# ── pytest 回归 ──────────────────────────────────────────────────────

def test_pytest_regression_subset_passes(tmp_path):
    # 用本测试文件子集验证回归通道真实工作（不跑全量，保持快速）
    subset = REPO_ROOT / "tests" / "test_models_types.py"
    resp = run_pytest_regression(tests_dir=subset, timeout=120)
    assert resp["tests_passed"] is True
    assert resp["exit_code"] == 0
    assert "passed" in resp["summary"]


# ── 可逆部署 ─────────────────────────────────────────────────────────

def test_deploy_creates_backup_and_merges(tmp_path):
    policies = _policies_yaml(tmp_path, [{
        "name": "base-rule", "path_pattern": "/api/base", "method": "GET",
        "action": "ALLOW"}])
    cand = _cand_yaml(tmp_path, name="auto-new")
    resp = deploy_candidate(cand, policies)
    assert resp["deployed"] is True
    assert resp["added"] == 1
    assert resp["total_rules"] == 2
    # backup 文件存在
    backups = list(tmp_path.glob("policies.yaml.bak-*"))
    assert len(backups) == 1
    # 合并后策略可加载，含新规则
    from src.policy import PolicyEngine
    engine = PolicyEngine(str(policies))
    assert engine.evaluate("/api/exec", "POST") is not None
    assert engine.evaluate("/api/base", "GET") is not None


def test_deploy_idempotent_by_name(tmp_path):
    policies = _policies_yaml(tmp_path, [])
    cand = _cand_yaml(tmp_path, name="auto-dup")
    first = deploy_candidate(cand, policies)
    second = deploy_candidate(cand, policies)
    assert first["total_rules"] == 1
    assert second["total_rules"] == 1  # 同 name 替换不重复
    assert second["added"] == 1


def test_deploy_missing_candidate_fails(tmp_path):
    resp = deploy_candidate(tmp_path / "ghost.yaml", tmp_path / "p.yaml")
    assert resp["deployed"] is False


# ── 评估报告 ─────────────────────────────────────────────────────────

def test_eval_report_contains_verdict_and_evidence(tmp_path):
    cand = _cand_yaml(tmp_path)
    resp = evaluate_candidate_in_sandbox(cand, tmp_path / "ghost.yaml")
    md = generate_eval_report(cand, resp)
    assert "沙箱评估报告" in md
    assert "可部署" in md
    assert "命中率" in md
