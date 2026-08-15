# -*- coding: utf-8 -*-
"""
test_m2_fused_signals.py — Sprint 24 M2 评估层重构回归测试
===========================================================
验证 compare_signals 的 M2 多信号融合判定:
  - layer=None 时保持 Sprint 17-23 原始语义 (SUSPICIOUS 锁死) — 向后兼容
  - layer 提供时, winrate 不变但行为变化 -> 融合 Q 判定:
      Q >= +0.15  -> PASSED      (效率/层信号显著改善)
      Q <= -0.15  -> REGRESSION  (效率/层信号显著退化)
      否则         -> SUSPICIOUS (保留人工审查)
  - fused_quality 信号分解: steps_eff + layer_signal
  - _layer_specific_signal: rules 触发计数 / mapping 动作熵 / physics reward
  - evaluator_v9 diff_verdict layer 参数透传 (通过 import 模拟)

Sprint 30 M2.1 新增 (S29 FP-NEG-004 教训编码):
  - 第四通道 _branch_hist_signal: branch_hist 熵变化硬信号
    (候选 A edge 0.65->0.80 的 60 步局主导分支是 FLANK-RIGHT 侧翼死循环,
     熵坍缩 = 分支集中到少数规则 = 负向; 熵分散 = 正向)
  - 无 branch_hist 的层 (reward/gate) 权重回退三通道, 恢复 Sprint 24 行为
Sprint 30 M2.2 新增:
  - precheck_topology_validity: 优先级重排未跨越邻居规则 -> 结构性 no-op
    拦截 (S29 候选 C priority 300->350 同构), 不进入评估循环
"""
import json

import pytest

from evaluator_diff_test import (
    compare_signals,
    fused_quality,
    _layer_specific_signal,
    precheck_topology_validity,
    topology_precheck_report,
    coverage_continuity_check,
    VERDICT_INCONCLUSIVE,
    VERDICT_SUSPICIOUS,
    VERDICT_PASSED,
    VERDICT_REGRESSION,
)

# ---------------------------------------------------------------- fixtures
def _ep(win=True, steps=6, action="5", branch="abdl/SIM-ADVANCED-CLOSE-PUSH",
        reward=210.0):
    return {
        "episode": 0, "opponent": "aggressive", "win": win, "steps": steps,
        "reward": reward,
        "action_hist": {str(action): steps},
        "branch_hist": {str(branch): steps},
    }


def _sig(eps):
    wins = sum(1 for e in eps if e["win"])
    return {
        "winrate": wins / len(eps),
        "total_episodes": len(eps),
        "episodes": eps,
    }


@pytest.fixture
def base_rules():
    """基线: rules 层 10 场全胜, 规则触发适中。"""
    eps = [_ep(win=True, steps=20 + i, branch="abdl/SIM-HEUR-CAUTIOUS-EDGE")
           for i in range(10)]
    return _sig(eps)


# ---------------------------------------------------------------- 向后兼容
def test_layer_none_keeps_s23_semantics(base_rules):
    """layer=None (Sprint 17-23 调用路径) 必须保持原 SUSPICIOUS 语义。"""
    cand = copy_sig(base_rules)
    # 行为变化: 动作分布不同, winrate 相同
    cand["episodes"][0]["action_hist"] = {"9": 20}
    r = compare_signals(base_rules, cand)  # 无 layer
    assert r["verdict"] == VERDICT_SUSPICIOUS
    assert r["layer"] is None


def test_layer_none_with_steps_improvement_still_suspicious(base_rules):
    """向后兼容: 即使 steps 显著改善, 无 layer 时仍按原语义 SUSPICIOUS。"""
    cand = copy_sig(base_rules)
    cand["episodes"] = [_ep(win=True, steps=10, branch="abdl/SIM-HEUR-CAUTIOUS-EDGE")
                        for _ in range(10)]
    r = compare_signals(base_rules, cand)
    assert r["verdict"] == VERDICT_SUSPICIOUS


# ---------------------------------------------------------------- M2 判定
def test_m2_rules_trigger_surge_regression(base_rules):
    """rules 层: 触发总数骤增 (edge-loop 特征) -> Q 负 -> REGRESSION。
    S23 实证: SIM-HEUR-CAUTIOUS-EDGE 触发 30-46 次 = 转向过度。"""
    cand = copy_sig(base_rules)
    for e in cand["episodes"]:
        e["branch_hist"] = {"abdl/SIM-HEUR-CAUTIOUS-EDGE": 45}  # 骤增
    r = compare_signals(base_rules, cand, layer="rules")
    assert r["verdict"] == VERDICT_REGRESSION, r["reason"]
    assert "M2" in r["reason"]


def test_m2_rules_trigger_reduction_passed(base_rules):
    """rules 层: 触发总数显著减少且 steps 改善 -> Q 正 -> PASSED。"""
    cand = copy_sig(base_rules)
    for e in cand["episodes"]:
        e["branch_hist"] = {"abdl/SIM-HEUR-CAUTIOUS-EDGE": 2}
        e["steps"] = 15
    r = compare_signals(base_rules, cand, layer="rules")
    assert r["verdict"] == VERDICT_PASSED, r["reason"]


def test_m2_physics_reward_gain_passed():
    """physics 层: 相同 winrate 下 reward 显著提升 -> Q 正 -> PASSED。"""
    base = _sig([_ep(win=True, steps=20, reward=200.0) for _ in range(10)])
    cand = _sig([_ep(win=True, steps=20, reward=300.0) for _ in range(10)])
    r = compare_signals(base, cand, layer="physics")
    assert r["verdict"] == VERDICT_PASSED, r["reason"]
    assert "physics reward" in r["reason"]


def test_m2_physics_reward_loss_regression():
    """physics 层: reward 显著下降 -> Q 负 -> REGRESSION。"""
    base = _sig([_ep(win=True, steps=20, reward=300.0) for _ in range(10)])
    cand = _sig([_ep(win=True, steps=20, reward=200.0) for _ in range(10)])
    r = compare_signals(base, cand, layer="physics")
    assert r["verdict"] == VERDICT_REGRESSION, r["reason"]


def test_m2_neutral_stays_suspicious(base_rules):
    """辅助信号有方向但不足以 PASS/REGRESS -> Q 中性 -> SUSPICIOUS。
    baseline: avg_steps=24.5, rules 触发总数=245。
    cand: steps=19 (steps_eff=(24.5-19)/24.5≈0.2245), 触发=28*10=280
          (layer_sig=(245-280)/245≈-0.1429)
    Q = 0.5*0.2245 + 0.5*(-0.1429) ≈ 0.041 ∈ [0.02, 0.15) -> SUSPICIOUS"""
    cand = copy_sig(base_rules)
    for e in cand["episodes"]:
        e["steps"] = 19
        e["branch_hist"] = {"abdl/SIM-HEUR-CAUTIOUS-EDGE": 28}
    r = compare_signals(base_rules, cand, layer="rules")
    assert r["verdict"] == VERDICT_SUSPICIOUS, r["reason"]
    assert "M2" in r["reason"]


def test_m2_near_zero_signal_inconclusive(base_rules):
    """所有辅助信号≈0 (指纹噪声, 无行为影响) -> INCONCLUSIVE。
    Sprint 24 M2 近零档: 打破 24 条全 SUSPICIOUS 同构的关键。"""
    cand = copy_sig(base_rules)
    # 仅微小指纹噪声: steps/reward/触发均几乎不变
    cand["episodes"][0]["branch_hist"] = {
        "abdl/SIM-HEUR-CAUTIOUS-EDGE": 21}  # 21->20 之一, Q≈0
    r = compare_signals(base_rules, cand, layer="rules")
    assert r["verdict"] == VERDICT_INCONCLUSIVE, r["reason"]
    assert "信号近零" in r["reason"]


# ---------------------------------------------------------------- fused_quality
def test_fused_quality_steps_eff_positive(base_rules):
    """steps 改善 (更快) -> steps_eff 正, 层信号中性 -> Q 偏向正。"""
    cand = copy_sig(base_rules)
    for e in cand["episodes"]:
        e["steps"] = 10  # 21 -> 10, 效率显著提升
    q, sigs = fused_quality(base_rules, cand, "rules")
    assert sigs["steps_eff"] > 0
    assert q > 0


def test_fused_quality_steps_eff_negative(base_rules):
    """steps 恶化 (更慢) -> steps_eff 负。"""
    cand = copy_sig(base_rules)
    for e in cand["episodes"]:
        e["steps"] = 40  # 21 -> 40
    q, sigs = fused_quality(base_rules, cand, "rules")
    assert sigs["steps_eff"] < 0
    assert q < 0


def test_fused_quality_sig_detail_contains_layer(base_rules):
    """sig_detail 摘要包含层特定描述。"""
    cand = copy_sig(base_rules)
    cand["episodes"][0]["branch_hist"] = {"abdl/SIM-HEUR-CAUTIOUS-EDGE": 40}
    from evaluator_diff_test import sig_detail
    q, sigs = fused_quality(base_rules, cand, "rules")
    detail = sig_detail(sigs)
    assert "rules" in detail
    assert "steps_eff" in detail


# ---------------------------------------------------------------- layer 信号
def test_layer_signal_rules_surge_negative(base_rules):
    """rules 触发骤增 -> 信号负向 (edge-loop 特征)。"""
    cand = copy_sig(base_rules)
    for e in cand["episodes"]:
        e["branch_hist"] = {"abdl/SIM-HEUR-CAUTIOUS-EDGE": 45}
    sig, desc = _layer_specific_signal(base_rules, cand, "rules")
    assert sig < 0
    assert "触发总数" in desc


def test_layer_signal_mapping_entropy_collapse():
    """mapping 动作熵坍缩 -> 信号负向。"""
    base = _sig([_ep(win=True, steps=6, action=str(i % 4)) for i in range(8)])
    cand = _sig([_ep(win=True, steps=6, action="0") for _ in range(8)])  # 全同动作
    sig, desc = _layer_specific_signal(base, cand, "mapping")
    assert sig <= 0
    assert "动作熵" in desc


def test_layer_signal_physics_reward_gain_positive():
    base = _sig([_ep(win=True, steps=6, reward=100.0) for _ in range(4)])
    cand = _sig([_ep(win=True, steps=6, reward=150.0) for _ in range(4)])
    sig, desc = _layer_specific_signal(base, cand, "physics")
    assert sig > 0
    assert "reward" in desc


def test_layer_signal_unknown_layer_neutral():
    base = _sig([_ep(win=True) for _ in range(2)])
    cand = _sig([_ep(win=True) for _ in range(2)])
    sig, desc = _layer_specific_signal(base, cand, "unknown")
    assert sig == 0.0
    assert "未知 layer" in desc


def test_layer_signal_rules_zero_baseline():
    """基线 rules 触发为 0 -> 中性信号 (避免除零)。"""
    base = _sig([_ep(win=True, steps=6, branch="") for _ in range(2)])
    cand = _sig([_ep(win=True, steps=6, branch="abdl/SIM-HEUR-CAUTIOUS-EDGE")
                 for _ in range(2)])
    # 空 branch_hist -> 基线触发总数 0
    for e in base["episodes"]:
        e["branch_hist"] = {}
    sig, desc = _layer_specific_signal(base, cand, "rules")
    assert sig == 0.0
    assert "基线=0" in desc


# ---------------------------------------------------------------- evaluator_v9 透传
def test_evaluator_v9_diff_verdict_layer_passthrough(base_rules, tmp_path):
    """diff_verdict 接受 layer 参数并透传给 compare_signals (S24 M2)。"""
    import evaluator_v9

    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(json.dumps({"mode": "baseline",
                                         "signal": base_rules}),
                             encoding="utf-8")
    cand = copy_sig(base_rules)
    for e in cand["episodes"]:
        e["branch_hist"] = {"abdl/SIM-HEUR-CAUTIOUS-EDGE": 45}
    # gate_report 格式 (含 episode_results)
    cand_report = {
        "winrate": 1.0,
        "total_episodes": 10,
        "episode_results": [
            {"episode": e["episode"], "opponent": e["opponent"],
             "win": e["win"], "steps": e["steps"], "reward": e["reward"],
             "action_hist": e["action_hist"], "branch_hist": e["branch_hist"]}
            for e in cand["episodes"]
        ],
    }
    verdict = evaluator_v9.diff_verdict(str(baseline_file), cand_report,
                                        layer="rules")
    assert verdict["verdict"] == VERDICT_REGRESSION


# ---------------------------------------------------------------- Sprint 30 M2.1 第四通道
def test_m2_branch_hist_entropy_collapse_negative(base_rules):
    """M2.1: branch_hist 熵坍缩 (分支集中到少数规则) -> 第四通道负向。

    S29 FP-NEG-004 编码: 候选 A 的 60 步局主导分支 FLANK-RIGHT:45 +
    CAUTIOUS-EDGE:13 (侧翼死循环) — 熵坍缩 = 死循环风险 = 负向信号。
    基线 episode 含多分支分布 (熵高), 候选坍缩到单分支 (熵 0)。"""
    base = _sig([_ep(win=True, steps=6, branch="abdl/SIM-ADVANCED-FLANK-RIGHT")
                 for _ in range(10)])
    for e in base["episodes"]:
        e["branch_hist"] = {"abdl/SIM-ADVANCED-FLANK-RIGHT": 20,
                            "abdl/SIM-HEUR-CAUTIOUS-EDGE": 15,
                            "abdl/SIM-ADVANCED-CLOSE-PUSH": 10}  # 多分支 -> 熵高
    cand = copy_sig(base)
    for e in cand["episodes"]:
        e["branch_hist"] = {"abdl/SIM-ADVANCED-FLANK-RIGHT": 45}  # 熵坍缩
    q, sigs = fused_quality(base, cand, "rules")
    assert sigs["branch_signal"] < 0, sigs["branch_desc"]
    assert "branch_hist 熵" in sigs["branch_desc"]


def test_m2_branch_hist_entropy_diversify_positive(base_rules):
    """M2.1: branch_hist 熵分散 + 效率同步提升 -> 第四通道正向。

    基线单分支 (熵 0), 候选多分支分布 (熵高) 且 steps 更快 -> 正向信号。
    (方向约束: 熵升需效率同步提升才计正; 本测试保证 steps_eff > 0)"""
    base = _sig([_ep(win=True, steps=20, branch="abdl/SIM-HEUR-CAUTIOUS-EDGE")
                 for _ in range(10)])
    for e in base["episodes"]:
        e["branch_hist"] = {"abdl/SIM-HEUR-CAUTIOUS-EDGE": 40}  # 单分支 -> 熵 0
    cand = copy_sig(base)
    for i, e in enumerate(cand["episodes"]):
        e["steps"] = 12 + i  # 效率提升 (steps_eff > 0)
        e["branch_hist"] = {"abdl/SIM-ADVANCED-FLANK-RIGHT": 20 + i,
                            "abdl/SIM-HEUR-CAUTIOUS-EDGE": 20}  # 多分支 -> 熵高
    q, sigs = fused_quality(base, cand, "rules")
    assert sigs["branch_signal"] > 0, sigs["branch_desc"]
    assert "计中性" not in sigs["branch_desc"]


def test_m2_branch_hist_no_branch_fallback_weights(base_rules):
    """M2.1: 无 ABDL 分支语义的层 (physics/reward/gate) -> 第四通道跳过, 权重回退三通道。

    Sprint 24 行为保持: physics reward 300->200 (rel=-0.33) 必须仍判
    REGRESSION (Q=-0.165), 不因第四通道缺失而稀释。"""
    base = _sig([_ep(win=True, steps=20, reward=300.0) for _ in range(10)])
    cand = _sig([_ep(win=True, steps=20, reward=200.0) for _ in range(10)])
    q, sigs = fused_quality(base, cand, "physics")
    assert sigs["branch_signal"] == 0.0
    assert "无 ABDL 分支语义" in sigs["branch_desc"]
    assert "权重回退" in sigs["branch_desc"]
    assert q <= -0.15, f"physics reward 损失必须保持 REGRESSION 阈值 (Q={q:.3f})"


# ---------------------------------------------------------------- Sprint 30 M2.2 拓扑预检
def test_m2_branch_hist_entropy_rise_without_eff_neutral(base_rules):
    """M2.1 方向约束: 熵升但效率未升 -> 第四通道置中性 (S29 候选 B 实证)。

    候选 B (dist>=0.3) 触发域扩大: 熵升 +0.024 (更多规则被触发) 但
    avg_steps 21.4->24.8 恶化 — 熵升是抖动, 不能抵消主要负向信号。
    """
    base = _sig([_ep(win=True, steps=20, branch="abdl/SIM-ADVANCED-FLANK-RIGHT")
                 for _ in range(10)])
    for e in base["episodes"]:
        e["branch_hist"] = {"abdl/SIM-ADVANCED-FLANK-RIGHT": 20,
                            "abdl/SIM-HEUR-CAUTIOUS-EDGE": 15,
                            "abdl/SIM-ADVANCED-CLOSE-PUSH": 10}  # 熵中
    cand = copy_sig(base)
    for i, e in enumerate(cand["episodes"]):
        e["steps"] = 26 + i  # 效率恶化
        e["branch_hist"] = {"abdl/SIM-ADVANCED-FLANK-RIGHT": 18,
                            "abdl/SIM-HEUR-CAUTIOUS-EDGE": 14,
                            "abdl/SIM-ADVANCED-CLOSE-PUSH": 12,
                            "abdl/SIM-HEUR-EXPLORE": 10}  # 熵升 (触发域扩大)
    q, sigs = fused_quality(base, cand, "rules")
    assert sigs["branch_signal"] == 0.0, sigs["branch_desc"]
    assert "计中性" in sigs["branch_desc"]
    # 权重回退后 steps_eff 权重恢复 0.5: Q = 0.5*(-0.20) + 0.5*(-0.159) = -0.18
    assert q <= -0.15, f"效率恶化必须保持 REGRESSION 级负向 (Q={q:.3f})"


def test_m2_branch_hist_entropy_rise_with_eff_positive(base_rules):
    """M2.1 方向约束: 熵升且效率同步提升 -> 第四通道正向保持。"""
    base = _sig([_ep(win=True, steps=20, branch="abdl/SIM-ADVANCED-FLANK-RIGHT")
                 for _ in range(10)])
    for e in base["episodes"]:
        e["branch_hist"] = {"abdl/SIM-ADVANCED-FLANK-RIGHT": 40}  # 单分支 -> 熵 0
    cand = copy_sig(base)
    for i, e in enumerate(cand["episodes"]):
        e["steps"] = 12 + i  # 效率提升
        e["branch_hist"] = {"abdl/SIM-ADVANCED-FLANK-RIGHT": 20,
                            "abdl/SIM-HEUR-CAUTIOUS-EDGE": 20}  # 熵升
    q, sigs = fused_quality(base, cand, "rules")
    assert sigs["branch_signal"] > 0, sigs["branch_desc"]
    assert "计中性" not in sigs["branch_desc"]
    assert q > 0, f"效率提升 + 熵升必须正向 (Q={q:.3f})"


def test_topo_precheck_priority_no_cross_blocked():
    """M2.2: priority 300->350 未跨越任何邻居 -> 结构性 no-op 拦截。

    S29 候选 C 同构: 优先级全序 700/600/590/500/480/470/300/250/200/150,
    300->350 区间 (300,350) 内无其他 priority -> resolve_top() 胜者集合不变。
    """
    rules_text = """
- id: "SIM-TACTIC-OPPONENT-FOUND"
  priority: 700
- id: "SIM-TACTIC-OPPONENT-LOST"
  priority: 600
- id: "SIM-ADVANCED-CLOSE-PUSH"
  priority: 500
- id: "SIM-HEUR-SPEED-ADAPT"
  priority: 300
- id: "SIM-HEUR-CAUTIOUS-EDGE"
  priority: 250
- id: "SIM-HEUR-EXPLORE"
  priority: 200
"""
    entries = [{"old": "priority: 300", "new": "priority: 350"}]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert not valid
    assert "未跨越任何邻居" in reason
    assert "结构性 no-op" in reason


def test_topo_precheck_priority_cross_allowed():
    """M2.2: priority 300->500 跨越邻居 (480/470 在区间内) -> 放行。

    真实拓扑变更: SPEED-ADAPT 提到 FLANK 之上, 胜者集合可能变化。"""
    rules_text = """
- id: "SIM-ADVANCED-FLANK-RIGHT"
  priority: 480
- id: "SIM-ADVANCED-FLANK-LEFT"
  priority: 470
- id: "SIM-HEUR-SPEED-ADAPT"
  priority: 300
- id: "SIM-HEUR-CAUTIOUS-EDGE"
  priority: 250
"""
    entries = [{"old": "priority: 300", "new": "priority: 500"}]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert valid
    assert "跨越邻居" in reason


def test_topo_precheck_non_priority_passthrough():
    """M2.2: 非优先级变更 (阈值/前提) 不涉及胜者集合重排 -> 放行。

    S32 P0 升级: 先跑覆盖连续性检查 (锚点须在规则文本中存在), 无新增空洞
    则放行。此处规则文本含条件行, old 锚点存在, edge 收窄 0.65->0.80 是扩宽
    (空洞缩小) -> 放行。
    """
    rules_text = "- id: 'SIM-ADVANCED-CLOSE-PUSH'\n  priority: 500\n" \
                 "  condition: sensor(edge_proximity) < 0.65\n"
    entries = [{"old": "sensor(edge_proximity) < 0.65",
                "new": "sensor(edge_proximity) < 0.80"}]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert valid
    # S32 语义: 覆盖检查放行 (扩宽无空洞) 后落到无 priority 变更分支
    assert "无优先级重排" in reason


def test_topo_precheck_report_reads_rules_file(tmp_path):
    """M2.2: topology_precheck_report 读取真实规则文件并拦截 no-op 候选 C。"""
    rules = tmp_path / "simulation_rules.abdl"
    rules.write_text(
        "rules:\n"
        "- id: \"SIM-TACTIC-OPPONENT-FOUND\"\n  priority: 700\n"
        "- id: \"SIM-HEUR-SPEED-ADAPT\"\n  priority: 300\n"
        "- id: \"SIM-HEUR-CAUTIOUS-EDGE\"\n  priority: 250\n",
        encoding="utf-8")
    entries = [{"old": "priority: 300", "new": "priority: 350"}]
    valid, reason = topology_precheck_report(entries, str(rules))
    assert not valid
    assert "未跨越任何邻居" in reason


# ---------------------------------------------------------------- S32 P0: 覆盖连续性预检 (FP-NEG-005)
def test_coverage_gap_angle_narrow_blocked():
    """P0: FLANK 角度 ±10->±15 收窄 -> (-15,-10)∪(10,15) 覆盖空洞 -> 拦截。

    S31 topo_D 同构: 条件域收窄后无规则覆盖的连续区间, ABDL 落入默认分支
    导致 avg_steps 21.4->34.1 (+59%)。M2.2 priority 预检无法捕获 (无 priority
    变更), S32 覆盖连续性预检必须拦截。
    """
    rules_text = (
        "rules:\n"
        "- id: \"SIM-ADVANCED-FLANK-RIGHT\"\n  priority: 800\n"
        "  condition: sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6\n"
        "- id: \"SIM-ADVANCED-CLOSE-PUSH\"\n  priority: 500\n"
        "  condition: BETWEEN(sensor(opponent_angle), -10, 10)\n"
        "- id: \"SIM-ADVANCED-FLANK-LEFT\"\n  priority: 800\n"
        "  condition: sensor(opponent_angle) > 10 AND sensor(opponent_dist) < 0.6\n"
    )
    entries = [
        {"old": "sensor(opponent_angle) < -10", "new": "sensor(opponent_angle) < -15"},
        {"old": "sensor(opponent_angle) > 10", "new": "sensor(opponent_angle) > 15"},
    ]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert not valid
    assert "COVERAGE_GAP" in reason
    assert "opponent_angle" in reason


def test_coverage_gap_edge_narrow_covered_by_neighbor():
    """P0: CAUTIOUS-EDGE 0.55->0.60 收窄, 但 (0.55,0.60) 仍被 CLOSE-PUSH <0.65
    覆盖 -> 无新增空洞 -> 放行 (S31 topo_E 同构, 实测 no-op 合理)。"""
    rules_text = (
        "rules:\n"
        "- id: \"SIM-ADVANCED-CLOSE-PUSH\"\n  priority: 500\n"
        "  condition: sensor(edge_proximity) < 0.65\n"
        "- id: \"SIM-HEUR-CAUTIOUS-EDGE\"\n  priority: 250\n"
        "  condition: BETWEEN(sensor(edge_proximity), 0.55, 0.78)\n"
        "- id: \"SIM-ADVANCED-FLANK-RIGHT\"\n  priority: 800\n"
        "  condition: sensor(edge_proximity) < 0.80\n"
    )
    entries = [
        {"old": "BETWEEN(sensor(edge_proximity), 0.55, 0.78)",
         "new": "BETWEEN(sensor(edge_proximity), 0.60, 0.78)"},
    ]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert valid


def test_coverage_gap_append_and_condition_passthrough():
    """P0: FLANK 追加 AND sensor(stuck_counter) < 3 (S31 topo_F 同构) —
    无数值维度收窄 (stuck 不在投影维度) -> 放行。"""
    rules_text = (
        "rules:\n"
        "- id: \"SIM-ADVANCED-FLANK-RIGHT\"\n  priority: 800\n"
        "  condition: sensor(opponent_angle) < -10 AND sensor(edge_proximity) < 0.80\n"
    )
    entries = [
        {"old": "sensor(opponent_angle) < -10 AND sensor(edge_proximity) < 0.80",
         "new": "sensor(opponent_angle) < -10 AND sensor(edge_proximity) < 0.80 "
                "AND sensor(stuck_counter) < 3"},
    ]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert valid


def test_coverage_gap_widen_passthrough():
    """P0: 条件域扩宽 (CLOSE-PUSH 0.65->0.80, S31 topo_A 同构) 不产生空洞 -> 放行。"""
    rules_text = (
        "rules:\n"
        "- id: \"SIM-ADVANCED-CLOSE-PUSH\"\n  priority: 500\n"
        "  condition: sensor(edge_proximity) < 0.65\n"
    )
    entries = [
        {"old": "sensor(edge_proximity) < 0.65", "new": "sensor(edge_proximity) < 0.80"},
    ]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert valid


def test_coverage_gap_anchor_mismatch_blocked():
    """P0: old 锚点在规则文件中不存在 -> 应用必失败 -> 拦截。"""
    rules_text = (
        "rules:\n"
        "- id: \"SIM-ADVANCED-FLANK-RIGHT\"\n  priority: 800\n"
        "  condition: sensor(opponent_angle) < -10\n"
    )
    entries = [
        {"old": "sensor(opponent_angle) < -15", "new": "sensor(opponent_angle) < -20"},
    ]
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert not valid
    assert "锚点失配" in reason


def test_coverage_gap_no_numeric_dim_skips():
    """P0: 无数值维度变更 (纯 priority 文本) -> 覆盖检查跳过。

    注意: S29 M2.2 语义下, 纯 priority 变更若未跨越邻居规则会被拦截
    (结构性 no-op 保护)。此处验证覆盖检查本身放行, priority 判定独立。
    """
    rules_text = (
        "rules:\n"
        "- id: \"SIM-ADVANCED-FLANK-RIGHT\"\n  priority: 800\n"
        "  condition: sensor(opponent_angle) < -10\n"
        "- id: \"SIM-ADVANCED-FLANK-LEFT\"\n  priority: 850\n"
        "  condition: sensor(opponent_angle) > 10\n"
    )
    entries = [
        {"old": "priority: 800", "new": "priority: 860"},
    ]
    # 覆盖检查: involved 为空 -> 跳过
    cov_ok, cov_reason = coverage_continuity_check(entries, rules_text)
    assert cov_ok
    assert "跳过" in cov_reason
    # priority 860 跨越邻居 850 -> 胜者集合可能变化 -> 放行
    valid, reason = precheck_topology_validity(entries, rules_text)
    assert valid


def copy_sig(sig):
    import copy
    return copy.deepcopy(sig)
