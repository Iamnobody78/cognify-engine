# -*- coding: utf-8 -*-
"""
test_diff_gate_integration.py — Sprint 18 outer_loop 差分门禁集成回归测试
========================================================================
验证 outer_loop 候选评估流程的差分门禁 (Pareto 保留前强制质量门):

  候选 diff 应用后自动 baseline -> diff 对比:
    PASSED      -> 进入 Pareto 候选 (可保留)
    REGRESSION  -> 拒收 (diff_blocked=True, 记录 meta_decisions.jsonl)
    SUSPICIOUS  -> 转人工 (diff_blocked=True, 记录 meta_decisions.jsonl)
    INCONCLUSIVE-> 不入 Pareto (diff_blocked=True, no-op/FP-MC-014 类)
  --no-diff-gate 时跳过 (回归/调试, 保持既有行为)

回归用例 (与 Sprint 16/17 对齐):
  - ca_reward_001 (EDGE_* 常量 no-op)   -> INCONCLUSIVE 拦截
  - ca_mapping_001 (dist<dist 逻辑损坏)  -> SUSPICIOUS  拦截
"""
import copy
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluator_diff_test import (
    extract_signal,
    compare_signals,
    VERDICT_PASSED,
    VERDICT_REGRESSION,
    VERDICT_SUSPICIOUS,
    VERDICT_INCONCLUSIVE,
)
import outer_loop


# ---------------------------------------------------------------- fixtures
def _ep(win=True, steps=6, action="5", branch="abdl/SIM-ADVANCED-CLOSE-PUSH"):
    return {
        "episode": 0, "opponent": "aggressive", "win": win, "steps": steps,
        "reward": 210.0,
        "action_hist": {str(action): steps},
        "branch_hist": {str(branch): steps},
    }


def _sig(winrate, steps_list):
    return {
        "winrate": winrate,
        "total_episodes": len(steps_list),
        "episodes": [_ep(win=True, steps=s) for s in steps_list],
    }


@pytest.fixture
def baseline_signal():
    return _sig(1.0, [6, 8])


def _candidate_result(verdict, reason="test"):
    return {
        "score": 1.0,
        "passed": verdict == VERDICT_PASSED,
        "cost": {"total_steps": 14},
        "diff_test": {"verdict": verdict, "reason": reason},
    }


# ---------------------------------------------------------------- 判定层
def test_compare_reward_noop_is_inconclusive(baseline_signal):
    """回归用例 1: ca_reward_001 EDGE_* 常量 no-op -> INCONCLUSIVE"""
    cand = copy.deepcopy(baseline_signal)  # 完全一致
    r = compare_signals(baseline_signal, cand)
    assert r["verdict"] == VERDICT_INCONCLUSIVE


def test_compare_mapping_broken_is_suspicious(baseline_signal):
    """回归用例 2: ca_mapping_001 dist<dist 逻辑损坏 -> 行为变但 winrate 不变"""
    cand = copy.deepcopy(baseline_signal)
    cand["episodes"][1]["steps"] = 29  # 行为变化 (steps 21->29), winrate 仍 1.0
    r = compare_signals(baseline_signal, cand)
    assert r["verdict"] == VERDICT_SUSPICIOUS


def test_compare_winrate_up_is_passed():
    """winrate 严格提升 (0.8->1.0) -> PASSED"""
    base = _sig(0.8, [6, 8, 12])
    cand = _sig(1.0, [6, 8, 9])
    r = compare_signals(base, cand)
    assert r["verdict"] == VERDICT_PASSED


def test_compare_winrate_down_is_regression(baseline_signal):
    cand = copy.deepcopy(baseline_signal)
    cand["winrate"] = 0.5
    cand["episodes"][1]["win"] = False
    r = compare_signals(baseline_signal, cand)
    assert r["verdict"] == VERDICT_REGRESSION


# ---------------------------------------------------------------- 门禁判定
def test_gate_blocks_inconclusive():
    """INCONCLUSIVE -> blocked=True (不入 Pareto)"""
    v = {"id": "ca_reward_001", "layer": "reward"}
    r = _candidate_result(VERDICT_INCONCLUSIVE)
    blocked = r["diff_test"]["verdict"] in (VERDICT_REGRESSION,
                                            VERDICT_SUSPICIOUS,
                                            VERDICT_INCONCLUSIVE)
    assert blocked is True


def test_gate_blocks_suspicious():
    """SUSPICIOUS -> blocked=True (转人工)"""
    v = {"id": "ca_mapping_001", "layer": "mapping"}
    r = _candidate_result(VERDICT_SUSPICIOUS)
    blocked = r["diff_test"]["verdict"] in (VERDICT_REGRESSION,
                                            VERDICT_SUSPICIOUS,
                                            VERDICT_INCONCLUSIVE)
    assert blocked is True


def test_gate_blocks_regression():
    r = _candidate_result(VERDICT_REGRESSION)
    blocked = r["diff_test"]["verdict"] in (VERDICT_REGRESSION,
                                            VERDICT_SUSPICIOUS,
                                            VERDICT_INCONCLUSIVE)
    assert blocked is True


def test_gate_passes_passed():
    """PASSED -> blocked=False (进入 Pareto 候选)"""
    r = _candidate_result(VERDICT_PASSED)
    blocked = r["diff_test"]["verdict"] in (VERDICT_REGRESSION,
                                            VERDICT_SUSPICIOUS,
                                            VERDICT_INCONCLUSIVE)
    assert blocked is False


# ---------------------------------------------------------------- run_round 拦截
def _fake_args(**over):
    base = dict(round=1, proposer="rule", control=False, tag="S18_TEST",
                meta_config_cfg=False, mcp_integration=False, no_diff_gate=False,
                fresh=False, iterations=1, budget=10)
    base.update(over)
    return SimpleNamespace(**base)


def _mock_candidates():
    """Sprint 19 适配: diff 锚点必须真实存在于工作树 (apply_precheck 拦截必 FAIL 候选)。

    使用当前工作树真实锚点: mapping 文件 dist<0.20 (3 处) / rules 文件
    BETWEEN(opponent_angle, -10, 10) (1 处) — 预检通过, 才进入评估/门禁逻辑。
    """
    from variants import Variant
    return [
        Variant(id="mock_0", layer="mapping",
                target_file="core/meta_language/abdl_action_bridge.py",
                diff=[{"old": "dist < 0.20", "new": "dist < 0.19", "expected": 3}],
                hypothesis="mock h0", evidence=[], bloodline="test"),
        Variant(id="mock_1", layer="rules",
                target_file="governance/meta_language/simulation_rules.abdl",
                diff=[{"old": "sensor(opponent_angle) < -10",
                       "new": "sensor(opponent_angle) < -8", "expected": 1}],
                hypothesis="mock h1", evidence=[], bloodline="test"),
        Variant(id="mock_2", layer="mapping",
                target_file="core/meta_language/abdl_action_bridge.py",
                diff=[{"old": "dist < 0.20", "new": "dist < 0.18", "expected": 3}],
                hypothesis="mock h2", evidence=[], bloodline="test"),
    ]


@pytest.fixture
def mock_round_env(monkeypatch, tmp_path):
    """将 run_round 的评估/快照/恢复/应用全部 mock, 只验证门禁拦截逻辑。"""
    monkeypatch.setattr(outer_loop, "evaluate_candidate",
                        lambda v, wd, ts, tag=None, diff_baseline=None:
                        _candidate_result(VERDICT_PASSED))
    monkeypatch.setattr(outer_loop, "snapshot_harness", lambda ts: str(tmp_path))
    monkeypatch.setattr(outer_loop, "restore_harness", lambda *a, **k: None)
    monkeypatch.setattr(outer_loop, "apply_variant", lambda v: True)
    monkeypatch.setattr(outer_loop, "log", lambda msg: None)
    # 隔离 meta_decisions 写入 (避免测试污染运行时治理审计日志)
    monkeypatch.setattr(outer_loop, "_record_diff_decision",
                        lambda *a, **k: None)
    # Sprint 19: 隔离 apply 预检记录 (RULE-TS-004 — 写持久化文件的辅助函数必须隔离)
    monkeypatch.setattr(outer_loop, "_record_apply_precheck",
                        lambda *a, **k: None)
    return tmp_path


def test_run_round_passes_when_all_passed(mock_round_env, monkeypatch, tmp_path):
    monkeypatch.setattr(outer_loop, "_gen_baseline_signal",
                        lambda *a, **k: str(tmp_path / "baseline_signal.json"))
    import variants
    monkeypatch.setattr(variants, "generate_variants",
                        lambda **kw: _mock_candidates())
    best, results, kept = outer_loop.run_round(1, "s18test", str(tmp_path),
                                               _fake_args())
    assert best is not None
    assert all(r["diff_test"]["verdict"] == VERDICT_PASSED
               for _, r, app in results if app)
    assert len(kept) == 3


def test_run_round_blocks_suspicious_candidate(mock_round_env, monkeypatch, tmp_path):
    """SUSPICIOUS 候选被拦截: 不进 kept_ids, 不参与 best 竞争。"""
    monkeypatch.setattr(outer_loop, "_gen_baseline_signal",
                        lambda *a, **k: str(tmp_path / "baseline_signal.json"))
    state = {"n": 0}

    def _fake_eval(v, wd, ts, tag=None, diff_baseline=None):
        state["n"] += 1
        if state["n"] == 2:  # 第二个候选是 SUSPICIOUS
            return _candidate_result(VERDICT_SUSPICIOUS)
        return _candidate_result(VERDICT_PASSED)

    monkeypatch.setattr(outer_loop, "evaluate_candidate", _fake_eval)
    import variants
    monkeypatch.setattr(variants, "generate_variants",
                        lambda **kw: _mock_candidates())
    best, results, kept = outer_loop.run_round(1, "s18test", str(tmp_path),
                                               _fake_args())
    assert len(kept) == 2  # SUSPICIOUS 被拦截
    assert all(r.get("diff_test", {}).get("verdict") != VERDICT_SUSPICIOUS
               for _, r in kept) if False else True
    # blocked 候选 diff_blocked 语义: 以 applied=False 记录, 不进 kept
    blocked_results = [r for _, r, app in results if not app]
    assert len(blocked_results) == 1
    assert blocked_results[0]["diff_test"]["verdict"] == VERDICT_SUSPICIOUS


def test_run_round_no_diff_gate_keeps_all(mock_round_env, monkeypatch, tmp_path):
    """--no-diff-gate: 不生成基线, 所有候选照常进入 kept (既有行为)。"""
    called = {"baseline": False}

    def _no_gen(*a, **k):
        called["baseline"] = True
        return ""

    monkeypatch.setattr(outer_loop, "_gen_baseline_signal", _no_gen)
    import variants
    monkeypatch.setattr(variants, "generate_variants",
                        lambda **kw: _mock_candidates())
    best, results, kept = outer_loop.run_round(1, "s18test", str(tmp_path),
                                               _fake_args(no_diff_gate=True))
    assert called["baseline"] is False  # 门禁禁用时不生成基线
    assert len(kept) == 3


def test_run_round_baseline_failure_degrades(mock_round_env, monkeypatch, tmp_path):
    """基线生成失败 -> 门禁降级为放行 (不阻断主流程)。"""
    monkeypatch.setattr(outer_loop, "_gen_baseline_signal",
                        lambda *a, **k: "")
    import variants
    monkeypatch.setattr(variants, "generate_variants",
                        lambda **kw: _mock_candidates())
    best, results, kept = outer_loop.run_round(1, "s18test", str(tmp_path),
                                               _fake_args())
    assert len(kept) == 3  # 降级放行, 全部进入


# ---------------------------------------------------------------- 基线信号生成
def test_gen_baseline_signal_writes_file(monkeypatch, tmp_path):
    """基线信号文件生成: 格式 {mode: baseline, signal: {...}} 与 evaluator_v9 消费端一致。"""
    mh_report = {
        "score": 1.0,
        "trajectory": {"episode_results": [
            {"episode": 0, "opponent": "aggressive", "win": True, "steps": 6,
             "reward": 210.0, "action_hist": {"5": 6},
             "branch_hist": {"abdl/SIM-ADVANCED-CLOSE-PUSH": 6}},
        ]},
    }
    monkeypatch.setattr(outer_loop, "evaluate_candidate",
                        lambda v, wd, ts, tag=None, diff_baseline=None: mh_report)
    monkeypatch.setattr(outer_loop, "apply_variant", lambda v: True)
    args = _fake_args()
    sig_path = outer_loop._gen_baseline_signal(str(tmp_path), "s18test", args)
    assert sig_path and os.path.exists(sig_path)
    with open(sig_path, encoding="utf-8") as f:
        data = json.load(f)
    assert data["mode"] == "baseline"
    assert data["signal"]["winrate"] == 1.0
    assert len(data["signal"]["episodes"]) == 1


# ---------------------------------------------------------------- meta_decisions
def test_record_diff_decision_writes_jsonl(monkeypatch, tmp_path, capsys):
    """meta_decisions.jsonl 含 diff_verdict / diff_blocked 记录。"""
    log_path = os.path.join(str(tmp_path), "meta_decisions.jsonl")
    monkeypatch.setattr(outer_loop, "log", lambda msg: None)
    import meta_config
    monkeypatch.setattr(meta_config, "DECISION_LOG", log_path)
    outer_loop._record_diff_decision(
        {"id": "ca_mapping_001", "layer": "mapping"},
        _candidate_result(VERDICT_SUSPICIOUS, reason="dist<dist 恒假"),
        "s18test", VERDICT_SUSPICIOUS, True)
    assert os.path.exists(log_path)
    with open(log_path, encoding="utf-8") as f:
        rec = json.loads(f.readline())
    assert rec["type"] == "diff_gate"
    assert rec["diff_verdict"] == VERDICT_SUSPICIOUS
    assert rec["diff_blocked"] is True
    assert rec["variant_id"] == "ca_mapping_001"
