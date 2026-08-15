"""Guard the heuristic-rules config equivalence contract (TASK-005 前置配置化).

裁决 (2026-08-05): 只抽魔数入 yaml, 不改行为。本测试守护:
1. _load_heuristic_rules() 返回的值与历史硬编码 (6d1e5d9) 完全一致;
2. V9RuleAgent(force_heuristic=True) 对边界 obs 的分支选择与硬编码时代等价;
3. 配置缺失/损坏时安全回退默认值, 不崩溃。

2026-08-07 修复 (Sprint 9 合入前债务清理):
4 项 action 期望值过时 — v9_gate_evaluator.py 于 2026-08-05 做了动作码对齐
Action enum 的有意修复 (REV_SLOW=6/TURN_R_MILD=10/FW_LEFT_MILD=13/
FW_RIGHT_MILD=16, 原错误值 12/8/4/6 中 6 实为 REV_SLOW 倒车用于前进分支)。
测试仍在断言修复前的错误动作码, 故更新期望值到 Action enum 正确值。
注意: 此失败与 GRIP_DECAY (lightweight_env.py 规则轨衰减) 无关。
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "simulation"))

from v9_gate_evaluator import V9RuleAgent, _HEURISTIC_RULES_DEFAULT, _load_heuristic_rules  # noqa: E402


class TestHeuristicConfigEquivalence:
    """TASK-005: config externalization must not change behavior."""

    def test_loaded_values_match_legacy_hardcoded(self):
        rules = _load_heuristic_rules()
        assert rules["l0_safety"]["edge_danger_f"] == 0.15
        assert rules["l0_safety"]["edge_critical"] == 0.1
        assert rules["l1_tactical"]["opp_detect_dist"] == 0.5
        assert rules["l1_tactical"]["opp_angle_tol"] == 0.3
        assert rules["l2_strategic"]["advance_dist"] == 0.8

    def test_defaults_identical_to_loaded(self):
        loaded = _load_heuristic_rules()
        assert loaded == _HEURISTIC_RULES_DEFAULT

    @pytest.mark.parametrize(
        "obs,expected_branch,expected_action",
        [
            # SR-001 edge_f danger (edge_f 0.05 < critical 0.1)
            # 2026-08-05: 动作码对齐 Action enum 修复 — REV_SLOW=6 (原 12 TURN_R_HARD 旋转错误)
            ([0.05, 0.5, 0.5, 0.5, 1.0, 0.0], "SR-001/edge_f", 6),
            # SR-001 edge_l critical — TURN_R_MILD=10 (原 8 TURN_L_MED 左转错误)
            ([0.5, 0.5, 0.05, 0.5, 1.0, 0.0], "SR-001/edge_l", 10),
            # SR-001 edge_r critical
            ([0.5, 0.5, 0.5, 0.05, 1.0, 0.0], "SR-001/edge_r", 7),
            # SR-001 edge_b critical
            ([0.5, 0.05, 0.5, 0.5, 1.0, 0.0], "SR-001/edge_b", 5),
            # TR-001 charge (opp ahead, aligned)
            ([0.9, 0.9, 0.9, 0.9, 0.3, 0.0], "TR-001/charge", 5),
            # TR-001 right (opp_angle < 0: 对手在右) — FW_RIGHT_MILD=16
            # (原 6 REV_SLOW 倒车错误; 分支名原误标 left — 全代码库约定负角=右, 见
            #  abdl_runner.py:92 / v9_gate_evaluator.py:145,187)
            ([0.9, 0.9, 0.9, 0.9, 0.3, -0.5], "TR-001/right", 16),
            # TR-001 left (opp_angle > 0: 对手在左) — FW_LEFT_MILD=13
            # (原 4 FW_FAST 纯前进错误; 分支名原误标 right)
            ([0.9, 0.9, 0.9, 0.9, 0.3, 0.5], "TR-001/left", 13),
            # TR-002 advance (0.5 <= opp < 0.8)
            ([0.9, 0.9, 0.9, 0.9, 0.6, 0.0], "TR-002/advance", 3),
            # TR-003 search (everything far)
            ([0.9, 0.9, 0.9, 0.9, 0.9, 0.0], "TR-003/search", None),
        ],
    )
    def test_heuristic_branch_choices_unchanged(self, obs, expected_branch, expected_action):
        agent = V9RuleAgent(force_heuristic=True)
        action = agent._heuristic_v9(obs)
        if expected_action is None:
            assert action is not None  # TR-003 search returns a valid action
        else:
            assert action == expected_action
        assert agent._last_heuristic_branch == expected_branch

    def test_config_file_is_single_source(self):
        import yaml

        cfg_path = Path(__file__).resolve().parent.parent / "simulation" / "heuristic_config.yaml"
        assert cfg_path.exists(), "heuristic_config.yaml 必须存在"
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        rules = data["heuristic_rules"]
        assert rules["l0_safety"]["edge_danger_f"] == 0.15
        assert rules["l1_tactical"]["opp_detect_dist"] == 0.5
        assert rules["l2_strategic"]["advance_dist"] == 0.8


class TestS59DefensiveCounter:
    """Sprint 59 (2026-08-10): defensive 反冲回避 + 边缘横向脱离。

    D1/D3: 反冲区边缘 (0.35-0.45) 正面对峙 → TR-004/vectored 侧向曲线绕行,
    不再直线冲锋进 defensive 反冲区 (opp_dist<0.4)。
    D2: 连续 edge_f 规避 → 强制横向转向 (SR-001/edge_f_turn)。
    """

    def test_config_file_has_s59_keys(self):
        import yaml

        cfg_path = Path(__file__).resolve().parent.parent / "simulation" / "heuristic_config.yaml"
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        rules = data["heuristic_rules"]
        assert rules["l1_tactical"]["shove_dist"] == 0.45
        assert rules["l1_tactical"]["charge_dist"] == 0.35
        assert rules["l0_safety"]["edge_f_turn_streak"] == 3
        # S59 新增项必须同步进代码默认值, 保证 _load_heuristic_rules 合并契约
        assert rules["l1_tactical"]["shove_dist"] == _HEURISTIC_RULES_DEFAULT["l1_tactical"]["shove_dist"]
        assert rules["l0_safety"]["edge_f_turn_streak"] == _HEURISTIC_RULES_DEFAULT["l0_safety"]["edge_f_turn_streak"]

    def test_defaults_include_s59_keys(self):
        assert _HEURISTIC_RULES_DEFAULT["l1_tactical"]["shove_dist"] == 0.45
        assert _HEURISTIC_RULES_DEFAULT["l1_tactical"]["charge_dist"] == 0.35
        assert _HEURISTIC_RULES_DEFAULT["l0_safety"]["edge_f_turn_streak"] == 3

    @pytest.mark.parametrize(
        "obs,expected_branch,expected_action",
        [
            # TR-004/vectored_l: 反冲区边缘 (0.42) 正对, 左侧更开阔 (edge_l 0.7 > edge_r 0.4)
            ([0.9, 0.9, 0.7, 0.4, 0.42, 0.0], "TR-004/vectored_l", 13),
            # TR-004/vectored_r: 右侧更开阔
            ([0.9, 0.9, 0.4, 0.7, 0.42, 0.0], "TR-004/vectored_r", 16),
            # charge 收紧: 0.30 (< charge_dist 0.35) 仍直线冲锋
            ([0.9, 0.9, 0.9, 0.9, 0.30, 0.0], "TR-001/charge", 5),
            # charge 收紧: 0.40 (0.35-0.45) 正对 → 不再 charge, 走 vectored
            ([0.9, 0.9, 0.7, 0.4, 0.40, 0.0], "TR-004/vectored_l", 13),
            # 0.45 边界 (>= shove_dist) → 保持 charge (0.45-0.5 区间)
            ([0.9, 0.9, 0.9, 0.9, 0.45, 0.0], "TR-001/charge", 5),
        ],
    )
    def test_vectored_and_charge_tightening(self, obs, expected_branch, expected_action):
        agent = V9RuleAgent(force_heuristic=True)
        action = agent._heuristic_v9(obs)
        assert action == expected_action
        assert agent._last_heuristic_branch == expected_branch

    def test_edge_f_streak_forces_lateral_turn(self):
        # 连续 3 次前缘危险 (edge_f 0.05) → 第 3 次强制转向, 不再直线后退
        agent = V9RuleAgent(force_heuristic=True)
        obs = [0.05, 0.5, 0.5, 0.5, 1.0, 0.0]
        for _ in range(2):
            agent._heuristic_v9(obs)
            assert agent._last_heuristic_branch == "SR-001/edge_f"
        action = agent._heuristic_v9(obs)
        assert action in (7, 10)  # TURN_L_MILD / TURN_R_MILD
        assert agent._last_heuristic_branch == "SR-001/edge_f_turn"

    def test_edge_f_streak_resets_after_escape(self):
        # 脱离前缘危险后 streak 归零: 单次危险不触发转向
        agent = V9RuleAgent(force_heuristic=True)
        obs_danger = [0.05, 0.5, 0.5, 0.5, 1.0, 0.0]
        obs_safe = [0.5, 0.5, 0.5, 0.5, 1.0, 0.0]
        agent._heuristic_v9(obs_danger)   # streak=1
        agent._heuristic_v9(obs_safe)     # reset → streak=0 (TR-003 search)
        action = agent._heuristic_v9(obs_danger)
        assert action == 6  # REV_SLOW, 非转向
        assert agent._last_heuristic_branch == "SR-001/edge_f"
