# -*- coding: utf-8 -*-
"""
test_always_false_detection.py — Sprint 20 P1 恒 False 模式检测回归测试
========================================================================
验证 P1 三层防御 (PM 指令: 自引用比较 dist < dist / 空条件 等, 作为 apply 预检的补充层):
  1. detect_always_false 纯函数: 三类模式 (自引用比较 / 空条件 / 恒 False 字面量)
  2. 生成层拦截: resolve_diff 对 LLM 候选的恒 False diff 返回 False (绝不带病入环)
  3. 运行时拦截: apply_precheck 在锚点计数之前拦截恒 False (第二道防线)
  4. run_round 集成: 恒 False 候选记录 apply_precheck_failed + 零评估预算

回归基线: S19_VERIFY 修复后候选全部干净 apply, 但恒 False 候选 (自引用/空条件)
此前只能靠 diff 门禁事后拦截 (浪费评估预算); P1 将其前移至 apply 之前。
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import variants
import outer_loop
import code_agent_proposer


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    """构造迷你工作树 (与 test_candidate_apply_diagnosis 同构)。"""
    mh_dir = tmp_path / "governance" / "meta_harness"
    mh_dir.mkdir(parents=True)
    (tmp_path / "governance" / "meta_language").mkdir(parents=True)
    (tmp_path / "core" / "meta_language").mkdir(parents=True)
    (tmp_path / "simulation").mkdir(parents=True)
    mapping = tmp_path / "core" / "meta_language" / "abdl_action_bridge.py"
    mapping.write_text(
        "# gate: dist < 0.20\n"
        "if dist < 0.20:\n"
        "    thrust = FW_HARD\n"
        "if dist < 0.20 and blocked:\n"
        "    thrust = FW_ARC\n", encoding="utf-8")
    rules = tmp_path / "governance" / "meta_language" / "simulation_rules.abdl"
    rules.write_text(
        "RULE angle_close: if BETWEEN(sensor(opponent_angle), -10, 10) "
        "then steer(0)\n", encoding="utf-8")
    phys = tmp_path / "simulation" / "lightweight_env.py"
    phys.write_text(
        "    momentum = net * TIMESTEP * 1.0\n", encoding="utf-8")
    hf = {
        "rules": "governance/meta_language/simulation_rules.abdl",
        "mapping": "core/meta_language/abdl_action_bridge.py",
        "physics": "simulation/lightweight_env.py",
    }
    monkeypatch.setattr(variants, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(variants, "HARNESS_FILES", dict(hf))
    monkeypatch.setattr(variants, "META_HARNESS_DIR", str(mh_dir))
    monkeypatch.setattr(outer_loop, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(outer_loop, "HARNESS_FILES", dict(hf))
    monkeypatch.setattr(code_agent_proposer, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(code_agent_proposer, "HARNESS_FILES", dict(hf))
    return tmp_path


# ===================================================== 1. detect_always_false 纯函数
def test_af_self_cmp_lt_blocks():
    """自引用比较 dist < dist -> 拦截, 标注恒 False。"""
    r = variants.detect_always_false("x = 1", "if dist < dist:")
    assert "自引用比较" in r and "恒 False" in r


def test_af_self_cmp_le_verdict_true():
    """自引用比较 d <= d 恒 True (无信息量) -> 同样拦截。"""
    r = variants.detect_always_false("x", "if d <= d:")
    assert "自引用比较" in r and "恒 True" in r


def test_af_self_cmp_negative():
    """正常比较不误报。"""
    assert variants.detect_always_false("x", "if dist < 0.20:") == ""
    assert variants.detect_always_false("x", "if opponent_angle > 15:") == ""
    assert variants.detect_always_false("momentum = net * TIMESTEP * 1.0", "y") == ""


def test_af_empty_cond_blocks():
    """空条件 if: / if (): -> 拦截。"""
    assert "空条件" in variants.detect_always_false("x", "if:")
    assert "空条件" in variants.detect_always_false("x", "if ():")
    assert "空条件" in variants.detect_always_false("x", "while :")


def test_af_empty_cond_negative():
    """非空条件不误报 (含括号条件)。"""
    assert variants.detect_always_false("x", "if dist < 0.20:") == ""
    assert variants.detect_always_false("x", "if (dist < 0.20):") == ""
    assert variants.detect_always_false("x", "while d > 0.1:") == ""


def test_af_false_literal_blocks():
    """恒 False 字面量条件 if 0: / while False: / if 0.0: / elif None:。"""
    assert "恒 False 字面量" in variants.detect_always_false("x", "if 0:")
    assert "恒 False 字面量" in variants.detect_always_false("x", "while False:")
    assert "恒 False 字面量" in variants.detect_always_false("x", "if 0.0:")
    assert "恒 False 字面量" in variants.detect_always_false("x", "elif None:")


def test_af_false_literal_negative():
    """真值字面量不误报: if 0.5: (非零真) / if 1: / if x:。"""
    assert variants.detect_always_false("x", "if 0.5:") == ""
    assert variants.detect_always_false("x", "if 1:") == ""
    assert variants.detect_always_false("x", "if x:") == ""


def test_af_checks_old_line_too():
    """old 行本身含恒 False 模式时同样拦截 (候选修改问题行时风险放大)。"""
    assert "恒 False 字面量" in variants.detect_always_false("if 0:", "x = 1")


def test_af_blank_lines_ignored():
    assert variants.detect_always_false("", "") == ""
    assert variants.detect_always_false(None, "") == ""


# ===================================================== 2. 生成层: resolve_diff 拦截
def test_resolve_diff_blocks_self_cmp(tmp_repo):
    """形态 B: LLM 候选 new 含自引用比较 -> resolve_diff 拒绝。"""
    v = {"id": "af1", "layer": "rules", "target_file": "governance/meta_language/simulation_rules.abdl",
         "diff": [{"old": "BETWEEN(sensor(opponent_angle), -10, 10)",
                   "new": "if angle < angle: then steer(0)", "expected": 1}]}
    ok, reason, out = code_agent_proposer.resolve_diff(v)
    assert ok is False
    assert "恒 False 模式" in reason and "自引用比较" in reason
    assert out == []


def test_resolve_diff_blocks_false_literal(tmp_repo):
    """形态 A: anchor 定位整行, new 含 if 0: -> resolve_diff 拒绝。"""
    v = {"id": "af2", "layer": "rules", "target_file": "governance/meta_language/simulation_rules.abdl",
         "diff": [{"anchor": "angle_close",
                   "new": "RULE angle_close: if 0: then steer(0)", "expected": 1}]}
    ok, reason, out = code_agent_proposer.resolve_diff(v)
    assert ok is False
    assert "恒 False 模式" in reason and "恒 False 字面量" in reason


def test_resolve_diff_passes_normal(tmp_repo):
    """正常候选不受影响 (回归保护)。"""
    v = {"id": "af3", "layer": "rules", "target_file": "governance/meta_language/simulation_rules.abdl",
         "diff": [{"old": "BETWEEN(sensor(opponent_angle), -10, 10)",
                   "new": "BETWEEN(sensor(opponent_angle), -8, 8)", "expected": 1}]}
    ok, reason, out = code_agent_proposer.resolve_diff(v)
    assert ok is True
    assert len(out) == 1 and out[0]["new"] == "BETWEEN(sensor(opponent_angle), -8, 8)"


# ===================================================== 3. 运行时: apply_precheck 拦截
def test_precheck_blocks_self_cmp(tmp_repo):
    """恒 False 检测先于锚点计数: 即使 expected 正确也拦截。"""
    v = {"id": "af4", "layer": "mapping",
         "target_file": "core/meta_language/abdl_action_bridge.py",
         "diff": [{"old": "dist < 0.20", "new": "if dist < dist:", "expected": 3}]}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is False
    assert "恒 False 模式" in reason and "自引用比较" in reason


def test_precheck_blocks_false_literal(tmp_repo):
    v = {"id": "af5", "layer": "mapping",
         "target_file": "core/meta_language/abdl_action_bridge.py",
         "diff": [{"old": "dist < 0.20", "new": "if 0: thrust = FW_HARD", "expected": 3}]}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is False
    assert "恒 False 模式" in reason and "恒 False 字面量" in reason


def test_precheck_blocks_old_line_always_false(tmp_repo):
    """old 自身含恒 False (候选试图修改坏行) -> 拦截。"""
    v = {"id": "af6", "layer": "mapping",
         "target_file": "core/meta_language/abdl_action_bridge.py",
         "diff": [{"old": "if dist < dist:", "new": "if dist < 0.18:", "expected": 1}]}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is False
    assert "恒 False 模式" in reason


def test_precheck_passes_normal(tmp_repo):
    """正常候选不受影响 (回归保护)。"""
    v = {"id": "af7", "layer": "mapping",
         "target_file": "core/meta_language/abdl_action_bridge.py",
         "diff": [{"old": "dist < 0.20", "new": "dist < 0.18", "expected": 3}]}
    ok, reason = outer_loop.apply_precheck(v)
    assert ok is True and reason == ""


# ===================================================== 4. run_round 集成
def _fake_args(**over):
    base = dict(round=1, proposer="rule", control=False, tag="S20_TEST",
                meta_config_cfg=False, mcp_integration=False, no_diff_gate=False,
                fresh=False, iterations=1, budget=10)
    base.update(over)
    return SimpleNamespace(**base)


def _mk_variant(vid, layer, target, old, new, expected):
    from variants import Variant
    return Variant(id=vid, layer=layer, target_file=target,
                   diff=[{"old": old, "new": new, "expected": expected}],
                   hypothesis="h", evidence=[], bloodline="test")


def test_run_round_records_apply_precheck_failed_for_self_cmp(monkeypatch, tmp_path):
    """恒 False 候选: 记录 apply_precheck_failed (reason 含恒 False), 不进 evaluate (零预算)。"""
    eval_calls = {"n": 0}
    log_path = os.path.join(str(tmp_path), "meta_decisions.jsonl")
    import meta_config
    monkeypatch.setattr(meta_config, "DECISION_LOG", log_path)

    repo = tmp_path / "repo"
    (repo / "core" / "meta_language").mkdir(parents=True)
    (repo / "simulation").mkdir(parents=True)
    (repo / "core" / "meta_language" / "simulation_rules.abdl").write_text(
        "RULE x: if dist < 0.20 then steer(0)\n", encoding="utf-8")
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

    import variants as vmod
    bad = _mk_variant("s20_bad", "mapping",
                      "core/meta_language/abdl_action_bridge.py",
                      "dist < 0.20", "if dist < dist:", 1)
    good = _mk_variant("s20_good", "mapping",
                       "core/meta_language/abdl_action_bridge.py",
                       "dist < 0.20", "dist < 0.18", 1)
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

    best, results, kept = outer_loop.run_round(1, "s20test", str(tmp_path / "snap"),
                                               _fake_args())
    assert eval_calls["n"] == 1, f"应只评估 good (实际 {eval_calls['n']})"
    with open(log_path, encoding="utf-8") as f:
        recs = [json.loads(l) for l in f if l.strip()]
    pc = [r for r in recs if r.get("type") == "apply_precheck_failed"]
    assert pc and pc[0]["variant_id"] == "s20_bad"
    assert "恒 False 模式" in pc[0]["reason"]
    assert "自引用比较" in pc[0]["reason"]
