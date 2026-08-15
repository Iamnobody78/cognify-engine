# -*- coding: utf-8 -*-
"""
test_evaluator_diff_test.py — Sprint 17 评估器差分测试回归测试
=============================================================
验证 evaluator_diff_test 的判定逻辑：
  - 完全一致        -> INCONCLUSIVE (no-op, FP-MC-014 类)
  - 行为变+win率不变 -> SUSPICIOUS  (逻辑损坏/评估失敏, FP-MC-015 类)
  - win率提升       -> PASSED
  - win率下降       -> REGRESSION
  - harness diff.patch 解析
  - JSON 序列化往返稳定性 (int/str key 统一)
"""
import copy
import json

import pytest

from evaluator_diff_test import (
    parse_harness_patch,
    compare_signals,
    extract_signal,
    VERDICT_INCONCLUSIVE,
    VERDICT_SUSPICIOUS,
    VERDICT_PASSED,
    VERDICT_REGRESSION,
)

# ---------------------------------------------------------------- fixtures
def _ep(win=True, steps=6, action="5", branch="abdl/SIM-ADVANCED-CLOSE-PUSH"):
    return {
        "episode": 0, "opponent": "aggressive", "win": win, "steps": steps,
        "reward": 210.0,
        "action_hist": {str(action): steps},
        "branch_hist": {str(branch): steps},
    }


@pytest.fixture
def base_signal():
    return {
        "winrate": 1.0,
        "total_episodes": 2,
        "episodes": [
            _ep(win=True, steps=6),
            _ep(win=True, steps=8),
        ],
    }


# ---------------------------------------------------------------- parse
def test_parse_harness_patch():
    patch = """--- ca_reward_001 diff[0] (simulation/reward_functions.py)
- old: 'EDGE_WARNING = 4.0  # 3-6cm: moderate penalty + early warning'
+ new: 'EDGE_WARNING = 3.5  # 3-6cm: moderate penalty + early warning'
"""
    e = parse_harness_patch(patch)
    assert len(e) == 1
    assert e[0]["target_file"] == "simulation/reward_functions.py"
    assert e[0]["old"].startswith("EDGE_WARNING = 4.0")
    assert e[0]["new"].startswith("EDGE_WARNING = 3.5")


def test_parse_harness_patch_multiple():
    patch = """--- ca_mapping_001 diff[0] (core/meta_language/abdl_action_bridge.py)
- old: 'if dist < 0.20:'
+ new: 'if dist < 0.25:'
--- ca_mapping_001 diff[1] (core/meta_language/abdl_action_bridge.py)
- old: 'return Action.FW_RIGHT_HARD.value'
+ new: 'return Action.FW_RIGHT_MED.value'
"""
    e = parse_harness_patch(patch)
    assert len(e) == 2
    assert e[1]["old"] == "return Action.FW_RIGHT_HARD.value"


# ---------------------------------------------------------------- verdicts
def test_identical_inconclusive(base_signal):
    v = compare_signals(copy.deepcopy(base_signal), copy.deepcopy(base_signal))
    assert v["verdict"] == VERDICT_INCONCLUSIVE
    assert v["identical"] is True
    assert v["behavior_changed"] is False


def test_behavior_change_same_winrate_suspicious(base_signal):
    cand = copy.deepcopy(base_signal)
    cand["episodes"][0]["steps"] = 12
    cand["episodes"][0]["action_hist"] = {"4": 12}
    cand["episodes"][0]["branch_hist"] = {"abdl/SIM-ADVANCED-TURN": 12}
    v = compare_signals(base_signal, cand)
    assert v["verdict"] == VERDICT_SUSPICIOUS
    assert v["behavior_changed"] is True


def test_winrate_up_pass(base_signal):
    base = copy.deepcopy(base_signal)
    base["winrate"] = 0.0
    base["episodes"] = [_ep(win=False, steps=20), _ep(win=False, steps=25)]
    cand = copy.deepcopy(base)
    cand["winrate"] = 1.0
    cand["episodes"] = [_ep(win=True, steps=5), _ep(win=True, steps=7)]
    v = compare_signals(base, cand)
    assert v["verdict"] == VERDICT_PASSED


def test_winrate_down_regression(base_signal):
    base = copy.deepcopy(base_signal)
    base["winrate"] = 1.0
    base["episodes"] = [_ep(win=True, steps=6), _ep(win=True, steps=8)]
    cand = copy.deepcopy(base)
    cand["winrate"] = 0.5
    cand["episodes"] = [_ep(win=True, steps=30), _ep(win=False, steps=40)]
    v = compare_signals(base, cand)
    assert v["verdict"] == VERDICT_REGRESSION


def test_win_flag_change_detected(base_signal):
    """win 字段变化必须影响 behavior 指纹 (T5 修复回归)"""
    cand = copy.deepcopy(base_signal)
    cand["episodes"][1]["win"] = False
    cand["winrate"] = 0.5
    v = compare_signals(base_signal, cand)
    assert v["behavior_changed"] is True
    assert v["verdict"] == VERDICT_REGRESSION


# ---------------------------------------------------------------- serialization
def test_signal_json_roundtrip(base_signal):
    """JSON 往返后信号语义不变 (int/str key 统一)"""
    s = extract_signal({
        "winrate": 1.0,
        "total_episodes": 1,
        "episode_results": [{
            "episode": 0, "opponent": "aggressive", "win": True, "steps": 6,
            "reward": 210.0,
            "action_hist": {5: 6},           # int key — 模拟实时 Counter
            "branch_hist": {"abdl/X": 6},
        }],
    })
    rt = json.loads(json.dumps(s))
    assert s == rt
    assert all(isinstance(k, str) for k in s["episodes"][0]["action_hist"])
