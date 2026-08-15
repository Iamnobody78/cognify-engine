# -*- coding: utf-8 -*-
"""
test_candidate_apply_diagnosis.py — Sprint 19 候选 apply 诊断与预检回归测试
========================================================================
验证 S19 修复 (候选模板与工作树脱节):
  1. _seed_variants 动态适配: 锚点存在才生成 + 声明真实 expected (多匹配干净 apply)
     - 锚点缺失 (0 处) -> 跳过, 不生成必 FAIL 候选 (修复前静态模板必 FAIL)
     - 锚点存在 (N 处) -> diff expected=N (修复前默认 1, 多匹配 FAIL)
  2. apply_precheck (dry-run): apply 前校验锚点计数, 失败返回原因
     - 锚点计数不匹配 / 作用域越界 / 目标文件缺失
  3. run_round 集成: 预检失败记录 apply_precheck_failed 到 meta_decisions.jsonl,
     且不消耗评估预算 (不进 evaluate_candidate)
回归基线: S19_DIAG 5 轮 apply 成功率 0% (三类失效: A 锚点缺失 / B 多匹配 / C 死锚点)
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import variants
import outer_loop


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """构造迷你工作树: rules/mapping/physics 三文件 + meta_harness 目录。"""
    mh_dir = tmp_path / "governance" / "meta_harness"
    mh_dir.mkdir(parents=True)
    (tmp_path / "governance" / "meta_language").mkdir(parents=True)
    (tmp_path / "core" / "meta_language").mkdir(parents=True)
    (tmp_path / "simulation").mkdir(parents=True)
    # 写入一个"演进后"的 mapping 文件: dist < 0.20 出现 3 次 (多匹配场景)
    mapping = tmp_path / "core" / "meta_language" / "abdl_action_bridge.py"
    mapping.write_text(
        "# gate: dist < 0.20\n"
        "if dist < 0.20:\n"
        "    thrust = FW_HARD\n"
        "if dist < 0.20 and blocked:\n"
        "    thrust = FW_ARC\n", encoding="utf-8")
    # rules 文件 (真实路径: governance/meta_language/): opponent_angle 已演进为 -10 窗
    rules = tmp_path / "governance" / "meta_language" / "simulation_rules.abdl"
    rules.write_text(
        "RULE angle_close: if BETWEEN(sensor(opponent_angle), -10, 10) "
        "then steer(0)\n", encoding="utf-8")
    # physics 文件: 动量已演进为 TIMESTEP * 1.0
    phys = tmp_path / "simulation" / "lightweight_env.py"
    phys.write_text(
        "    momentum = net * TIMESTEP * 1.0\n", encoding="utf-8")
    monkeypatch.setattr(variants, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(variants, "HARNESS_FILES", {
        "rules": "governance/meta_language/simulation_rules.abdl",
        "mapping": "core/meta_language/abdl_action_bridge.py",
        "physics": "simulation/lightweight_env.py",
    })
    monkeypatch.setattr(variants, "META_HARNESS_DIR", str(mh_dir))
    # apply_precheck 读 outer_loop 模块级配置, 需同步 patch
    monkeypatch.setattr(outer_loop, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(outer_loop, "HARNESS_FILES", {
        "rules": "governance/meta_language/simulation_rules.abdl",
        "mapping": "core/meta_language/abdl_action_bridge.py",
        "physics": "simulation/lightweight_env.py",
    })
    return tmp_path


# ---------------------------------------------------------------- _seed_variants 动态适配
def test_seed_skips_missing_anchor(tmp_repo, monkeypatch, capsys):
    """锚点缺失 (0 处) -> 跳过该种子, 不生成必 FAIL 候选 (修复前: 静态模板必 FAIL)。"""
    monkeypatch.setattr(variants, "_SEED_PARAMS", {
        "rules": [{"old": "BETWEEN(sensor(opponent_angle), -15, 15)",
                   "new": "BETWEEN(sensor(opponent_angle), -10, 10)",
                   "hypothesis": "h", "evidence": []}],
    })
    out = variants._seed_variants("rules", {}, "test")
    assert out == []  # 0 处匹配 -> 跳过


def test_seed_declares_real_expected(tmp_repo, monkeypatch):
    """锚点存在 (N 处) -> diff expected=N, 多匹配干净 apply。"""
    monkeypatch.setattr(variants, "_SEED_PARAMS", {
        "mapping": [{"old": "dist < 0.20", "new": "dist < 0.18",
                     "hypothesis": "h", "evidence": []}],
    })
    out = variants._seed_variants("mapping", {}, "test")
    assert len(out) == 1
    assert out[0].diff[0]["expected"] == 3  # 当前工作树 3 处
    assert out[0].id == "mh_mapping_seed_001"
    assert out[0].bloodline.startswith("SEED_TEMPLATE")


def test_seed_missing_file_returns_empty(tmp_repo, monkeypatch):
    """目标文件缺失 -> 返回 [] (修复前: 生成必 FAIL 候选)。"""
    monkeypatch.setattr(variants, "_SEED_PARAMS", {
        "physics": [{"old": "TIMESTEP * 0.8", "new": "TIMESTEP * 0.85",
                     "hypothesis": "h", "evidence": []}],
    })
    monkeypatch.setattr(variants, "HARNESS_FILES", {
        "physics": "core/meta_language/nonexistent.py",
    })
    out = variants._seed_variants("physics", {}, "test")
    assert out == []


def test_mapping_002_declares_expected(tmp_repo, monkeypatch):
    """mh_mapping_002 主路径修复: diff 声明 text.count 真实计数。"""
    monkeypatch.setattr(variants, "HARNESS_FILES", {
        "rules": "core/meta_language/simulation_rules.abdl",
        "mapping": "core/meta_language/abdl_action_bridge.py",
        "physics": "simulation/lightweight_env.py",
    })
    cands = variants.generate_variants(round_no=1, max_per_layer=5)
    m002 = [c for c in cands if c.id == "mh_mapping_002"]
    assert m002, "mh_mapping_002 应生成"
    assert m002[0].diff[0]["expected"] == 3  # 动态感知工作树


# ---------------------------------------------------------------- apply_precheck
def test_precheck_pass_when_counts_match(tmp_repo):
    v = {"id": "t1", "layer": "mapping",
         "target_file": "core/meta_language/abdl_action_bridge.py",
         "diff": [{"old": "dist < 0.20", "new": "dist < 0.18", "expected": 3}]}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is True and reason == ""


def test_precheck_fail_when_count_mismatch(tmp_repo):
    v = {"id": "t2", "layer": "mapping",
         "target_file": "core/meta_language/abdl_action_bridge.py",
         "diff": [{"old": "dist < 0.20", "new": "dist < 0.18", "expected": 1}]}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is False
    assert "锚点计数 3!=1" in reason


def test_precheck_fail_missing_anchor(tmp_repo):
    v = {"id": "t3", "layer": "rules",
         "target_file": "governance/meta_language/simulation_rules.abdl",
         "diff": [{"old": "BETWEEN(sensor(opponent_angle), -15, 15)",
                   "new": "BETWEEN(sensor(opponent_angle), -10, 10)",
                   "expected": 1}]}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is False
    assert "锚点计数 0!=1" in reason


def test_precheck_fail_scope_escape(tmp_repo):
    v = {"id": "t4", "layer": "rules",
         "target_file": "governance/meta_language/simulation_rules.abdl",
         "diff": [{"old": "x", "new": "y", "expected": 1}],
         "extra_files": {"../../evil.py": [{"old": "a", "new": "b", "expected": 1}]}}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is False
    assert "作用域越界" in reason


def test_precheck_fail_missing_target(tmp_repo):
    v = {"id": "t5", "layer": "physics",
         "target_file": "simulation/lightweight_env.py",
         "diff": [{"old": "momentum = net * TIMESTEP * 1.0",
                   "new": "momentum = net * TIMESTEP * 0.9", "expected": 1}]}
    # 正常存在 -> 先验证 pass
    ok, _ = outer_loop.apply_precheck(v)
    assert ok is True
    # 删文件 -> fail
    os.remove(tmp_repo / "simulation" / "lightweight_env.py")
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is False
    assert "目标文件缺失" in reason


# ---------------------------------------------------------------- run_round 集成 (预检记录)
def _fake_args(**over):
    base = dict(round=1, proposer="rule", control=False, tag="S19_TEST",
                meta_config_cfg=False, mcp_integration=False, no_diff_gate=False,
                fresh=False, iterations=1, budget=10)
    base.update(over)
    return SimpleNamespace(**base)


def _mk_variant(vid, layer, target, old, expected):
    from variants import Variant
    return Variant(id=vid, layer=layer, target_file=target,
                   diff=[{"old": old, "new": old + "_X", "expected": expected}],
                   hypothesis="h", evidence=[], bloodline="test")


def test_run_round_records_apply_precheck_failed(monkeypatch, tmp_path):
    """预检失败候选: 记录 apply_precheck_failed, 不进 evaluate_candidate (零评估预算)。"""
    eval_calls = {"n": 0}
    log_path = os.path.join(str(tmp_path), "meta_decisions.jsonl")
    import meta_config
    monkeypatch.setattr(meta_config, "DECISION_LOG", log_path)

    # 构造带"必 FAIL"候选的迷你 repo
    repo = tmp_path / "repo"
    (repo / "core" / "meta_language").mkdir(parents=True)
    (repo / "simulation").mkdir(parents=True)
    rules = repo / "core" / "meta_language" / "simulation_rules.abdl"
    rules.write_text("RULE x: if dist < 0.20 then steer(0)\n", encoding="utf-8")
    (repo / "core" / "meta_language" / "abdl_action_bridge.py").write_text(
        "if dist < 0.20:\n    pass\n", encoding="utf-8")
    (repo / "simulation" / "lightweight_env.py").write_text(
        "x = 1\n", encoding="utf-8")
    monkeypatch.setattr(outer_loop, "REPO_ROOT", str(repo))
    monkeypatch.setattr(outer_loop, "HARNESS_FILES", {
        "rules": "core/meta_language/simulation_rules.abdl",
        "mapping": "core/meta_language/abdl_action_bridge.py",
        "physics": "simulation/lightweight_env.py",
    })
    monkeypatch.setattr(outer_loop, "SNAPSHOT_ROOT", str(tmp_path / "snaps"))
    monkeypatch.setattr(outer_loop, "META_HARNESS_DIR", str(tmp_path))

    # mock: 一个预检失败的候选 (锚点 0 处) + 一个正常的
    import variants as vmod
    bad = _mk_variant("s19_bad", "rules",
                      "core/meta_language/simulation_rules.abdl",
                      "BETWEEN(sensor(opponent_angle), -15, 15)", 1)
    good = _mk_variant("s19_good", "rules",
                       "core/meta_language/simulation_rules.abdl",
                       "dist < 0.20", 1)
    monkeypatch.setattr(vmod, "generate_variants", lambda **kw: [bad, good])

    def _fake_eval(v, wd, ts, tag=None, diff_baseline=None):
        eval_calls["n"] += 1
        return {"score": 1.0, "passed": True,
                "cost": {"total_steps": 10},
                "diff_test": {"verdict": "PASSED", "reason": "ok"}}

    monkeypatch.setattr(outer_loop, "evaluate_candidate", _fake_eval)
    monkeypatch.setattr(outer_loop, "snapshot_harness", lambda ts: str(tmp_path / "snap"))
    monkeypatch.setattr(outer_loop, "restore_harness", lambda *a, **k: None)
    monkeypatch.setattr(outer_loop, "log", lambda msg: None)
    monkeypatch.setattr(outer_loop, "_gen_baseline_signal", lambda *a, **k: "")
    monkeypatch.setattr(outer_loop, "_record_diff_decision", lambda *a, **k: None)
    monkeypatch.setattr(outer_loop, "apply_variant", lambda v: True)
    monkeypatch.setattr(outer_loop, "update_pareto", lambda *a, **k: None)
    monkeypatch.setattr(outer_loop, "append_reflection", lambda *a, **k: None)

    best, results, kept = outer_loop.run_round(1, "s19test", str(tmp_path / "snap"),
                                               _fake_args())
    # bad 候选预检失败 -> 不进 evaluate; good 候选进入
    assert eval_calls["n"] == 1, f"应只评估 good (实际 {eval_calls['n']})"
    assert os.path.exists(log_path)
    with open(log_path, encoding="utf-8") as f:
        recs = [json.loads(l) for l in f if l.strip()]
    pc = [r for r in recs if r.get("type") == "apply_precheck_failed"]
    assert pc and pc[0]["variant_id"] == "s19_bad"
    assert "锚点计数 0!=1" in pc[0]["reason"]
