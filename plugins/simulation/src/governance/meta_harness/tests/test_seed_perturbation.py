# -*- coding: utf-8 -*-
"""
test_seed_perturbation.py — Sprint 22 M3 扩展 (种子扰动幅度校验) 回归测试
========================================================================
PM Sprint 22 指令: 在 _seed_variants 中增加扰动幅度校验, 若 |new-old| < 层阈值
(角度≥10° / 阈值≥20% / 系数≥0.2), 则加大扰动或跳过该锚点。

依据: FP-MC-019 (S21 实证 rules 层 INCONCLUSIVE 10/10 — 种子扰动幅度
如角度 ±2°~±5° 远低于 10° 行为感知阈值, 且种子路径不走 LLM prompt)。
"""
import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import variants


# ---------------------------------------------------------------- 1. 幅度计算
def test_mag_rules_between_insufficient():
    mag, cfg = variants.perturbation_magnitude(
        "BETWEEN(sensor(opponent_angle), -15, 15)",
        "BETWEEN(sensor(opponent_angle), -10, 10)", "rules")
    assert mag == pytest.approx(5.0) and mag < cfg["threshold"]


def test_mag_rules_between_ok():
    mag, cfg = variants.perturbation_magnitude(
        "BETWEEN(sensor(opponent_angle), -15, 15)",
        "BETWEEN(sensor(opponent_angle), -5, 5)", "rules")
    assert mag == pytest.approx(10.0) and mag >= cfg["threshold"]


def test_mag_mapping_rel_insufficient():
    mag, cfg = variants.perturbation_magnitude("dist < 0.20", "dist < 0.18", "mapping")
    assert mag == pytest.approx(0.10) and mag < cfg["threshold"]


def test_mag_mapping_rel_ok():
    mag, _ = variants.perturbation_magnitude("dist < 0.20", "dist < 0.15", "mapping")
    assert mag == pytest.approx(0.25)


def test_mag_physics_abs():
    mag, cfg = variants.perturbation_magnitude("TIMESTEP * 0.8", "TIMESTEP * 0.85", "physics")
    assert mag == pytest.approx(0.05) and mag < cfg["threshold"]
    mag2, _ = variants.perturbation_magnitude("TIMESTEP * 0.8", "TIMESTEP * 1.2", "physics")
    assert mag2 == pytest.approx(0.4)


def test_mag_unparseable_returns_none():
    mag, cfg = variants.perturbation_magnitude("DOHYO_RADIUS", "((DOHYO_RADIUS) ** 2)", "physics")
    assert mag is None and cfg is not None


# ---------------------------------------------------------------- 2. 加大扰动
def test_bump_mapping_keeps_direction():
    new_adj, note = variants.bump_magnitude("dist < 0.20", "dist < 0.18", "mapping",
                                            variants.SEED_PERTURBATION_THRESHOLDS["mapping"])
    assert new_adj == "dist < 0.16"  # 保持减小方向, 0.20 -> 0.16 (20%)
    assert "扰动加大" in note


def test_bump_rules_angle_symmetric():
    """S23 回标: BETWEEN 对称区间双侧同步加大 (FP-MC-020 根因修复), 8° 阈值。"""
    new_adj, note = variants.bump_magnitude(
        "BETWEEN(sensor(opponent_angle), -15, 15)",
        "BETWEEN(sensor(opponent_angle), -10, 10)", "rules",
        variants.SEED_PERTURBATION_THRESHOLDS["rules"])
    # 对称双侧: -10,10 -> -7,7 (8° 收窄, 保持 ± 对称)
    assert new_adj == "BETWEEN(sensor(opponent_angle), -7, 7)"
    assert "对称" in note
    mag, cfg = variants.perturbation_magnitude(
        "BETWEEN(sensor(opponent_angle), -15, 15)", new_adj, "rules")
    assert mag + 1e-9 >= cfg["threshold"]
    assert abs(7.0 + (-7.0)) < 1e-9  # 对称保持


def test_bump_rules_symmetric_keeps_symmetry_for_increase():
    """对称区间且原扰动为增大方向: 双侧同步 (含扩窗场景)。"""
    new_adj, note = variants.bump_magnitude(
        "BETWEEN(sensor(opponent_angle), -15, 15)",
        "BETWEEN(sensor(opponent_angle), -16, 16)", "rules",
        variants.SEED_PERTURBATION_THRESHOLDS["rules"])
    assert new_adj == "BETWEEN(sensor(opponent_angle), -23, 23)"  # -16 -> -23 (8° 扩大)
    assert "对称" in note


def test_bump_physics_coefficient():
    new_adj, _ = variants.bump_magnitude("TIMESTEP * 0.8", "TIMESTEP * 0.85", "physics",
                                         variants.SEED_PERTURBATION_THRESHOLDS["physics"])
    assert new_adj == "TIMESTEP * 1.00"  # 0.8 + 0.2
    mag, cfg = variants.perturbation_magnitude("TIMESTEP * 0.8", new_adj, "physics")
    assert mag + 1e-9 >= cfg["threshold"]


def test_bump_unparseable_returns_none():
    new_adj, note = variants.bump_magnitude("DOHYO_RADIUS", "((DOHYO_RADIUS) ** 2)", "physics",
                                            variants.SEED_PERTURBATION_THRESHOLDS["physics"])
    assert new_adj is None and "无法解析" in note


# ---------------------------------------------------------------- 3. _seed_variants 集成
@pytest.fixture
def tmp_repo(tmp_path, monkeypatch):
    mh_dir = tmp_path / "governance" / "meta_harness"
    mh_dir.mkdir(parents=True)
    (tmp_path / "governance" / "meta_language").mkdir(parents=True)
    (tmp_path / "core" / "meta_language").mkdir(parents=True)
    (tmp_path / "simulation").mkdir(parents=True)
    rules = tmp_path / "governance" / "meta_language" / "simulation_rules.abdl"
    rules.write_text(
        "RULE r1: if BETWEEN(sensor(opponent_angle), -15, 15) then steer(0)\n"
        "RULE r2: if sensor(edge_proximity) < 0.80 then steer(180)\n", encoding="utf-8")
    mapping = tmp_path / "core" / "meta_language" / "abdl_action_bridge.py"
    mapping.write_text(
        "if abs(angle) > 40:\n    thrust = FW_HARD\n"
        "if dist < 0.20:\n    thrust = FW_RIGHT_HARD\n"
        "if dist < 0.20:\n    thrust = FW_LEFT_HARD\n"
        "if abs_angle < 15 and dist < 0.22:\n    thrust = FW_MAX\n", encoding="utf-8")
    phys = tmp_path / "simulation" / "lightweight_env.py"
    phys.write_text(
        "    momentum = net * TIMESTEP * 1.0\n"
        "    grip = ((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE) * ((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE) - GRIP_DECAY\n"
        'GRIP_DECAY = float(os.environ.get("BOTTLE_GRIP_DECAY", "0.10"))\n',
        encoding="utf-8")
    # Sprint 28: action_map 层 (S28 A1 轮速增益) — fixture 与 _SEED_PARAMS 同步
    w2d = tmp_path / "simulation" / "wheel_to_discrete.py"
    w2d.write_text(
        "        Action.TURN_L_MED: (0.0, 0.6),\n"
        "        Action.TURN_R_MED: (0.0, -0.6),\n",
        encoding="utf-8")
    hf = {
        "rules": "governance/meta_language/simulation_rules.abdl",
        "mapping": "core/meta_language/abdl_action_bridge.py",
        "physics": "simulation/lightweight_env.py",
        "action_map": "simulation/wheel_to_discrete.py",
    }
    monkeypatch.setattr(variants, "REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(variants, "HARNESS_FILES", dict(hf))
    return tmp_path


def _param_cfg(layer, idx):
    """取 _SEED_PARAMS[layer][idx] 的参数级扰动配置 (fallback 层默认)。"""
    p = variants._SEED_PARAMS[layer][idx]
    return p.get("perturb") or variants.SEED_PERTURBATION_THRESHOLDS[layer]


def test_seed_variants_rules_excluded(tmp_repo):
    """Sprint 24 裁决 2: rules 层种子移出扰动循环 (RULES CLOSED 外部治理),
    _seed_variants("rules", ...) 必须返回空列表并记录 excluded 日志。"""
    import io
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = variants._seed_variants("rules", {}, "test")
    assert out == []
    assert "rules-layer excluded" in buf.getvalue()


def test_seed_variants_bumps_insufficient_seeds(tmp_repo):
    """mapping 两个种子 (动态锚点 + 静态锚点) 扰动均达标, 无跳过。"""
    out = variants._seed_variants("mapping", {}, "test")
    assert len(out) == 2
    for i, v in enumerate(out):
        cfg = _param_cfg("mapping", i)
        mag, _ = variants.perturbation_magnitude(v.diff[0]["old"], v.diff[0]["new"], "mapping", cfg)
        assert mag + 1e-9 >= cfg["threshold"], f"{v.id} 扰动未达标: {mag}"
    # 种子 1: Sprint 27 A1 v3 -> flank 弧线触发 0.20 -> 0.15 (大幅收窄, 实证驱动)
    #          因果裁决: pursue 直冲窗死代码 (FP-NEG-002), v2 放宽 0.20→0.25 REGRESSION
    #          (更少弧线=负效应), 反向补齐 0.20→0.15 强化弧线 (制胜策略)
    assert out[0].diff[0]["old"] == "if dist < 0.20:"
    assert out[0].diff[0]["new"] == "if dist < 0.15:"
    # 种子 2: S23 参数级 rel 20% -> dist < 0.20 -> 0.16
    assert out[1].diff[0]["new"] == "dist < 0.16"


def test_seed_variants_mapping_both_bumped(tmp_repo):
    out = variants._seed_variants("mapping", {}, "test")
    assert len(out) == 2
    for i, v in enumerate(out):
        cfg = _param_cfg("mapping", i)
        mag, _ = variants.perturbation_magnitude(v.diff[0]["old"], v.diff[0]["new"], "mapping", cfg)
        assert mag + 1e-9 >= cfg["threshold"], f"{v.id} 扰动未达标: {mag}"
    assert out[0].diff[0]["new"] == "if dist < 0.15:"   # flank 弧线触发 0.20→0.15 (S27 A1 v3)
    assert out[1].diff[0]["new"] == "dist < 0.16"           # 0.20 -> 0.16 (20%)


def test_seed_variants_physics_bump_and_skip(tmp_repo):
    """physics 三个种子 (2 动态锚点 + 1 静态) 均生成 — Sprint 25 A1: 种子数 1->3。"""
    out = variants._seed_variants("physics", {}, "test")
    assert len(out) == 3
    # 种子 1: 动态锚点解析当前 momentum 系数 1.0 -> 1.20 (abs 0.20 加大后)
    assert out[0].diff[0]["old"] == "momentum = net * TIMESTEP * 1.0"
    assert out[0].diff[0]["new"] == "momentum = net * TIMESTEP * 1.20"
    mag, cfg = variants.perturbation_magnitude(out[0].diff[0]["old"], out[0].diff[0]["new"],
                                               "physics", _param_cfg("physics", 0))
    assert mag + 1e-9 >= cfg["threshold"]
    # 种子 2: 抓地衰减二次 -> 三次 (old != new)
    assert out[1].diff[0]["old"] != out[1].diff[0]["new"]
    assert out[1].diff[0]["new"].count("DOHYO_EDGE_ZONE") == 3
    # 种子 3: GRIP_DECAY 动态锚点 0.10 -> 0.30 (M3 bump 加大后达标)
    assert "GRIP_DECAY" in out[2].diff[0]["old"]
    mag3, cfg3 = variants.perturbation_magnitude(out[2].diff[0]["old"], out[2].diff[0]["new"],
                                                 "physics", _param_cfg("physics", 2))
    assert mag3 + 1e-9 >= cfg3["threshold"]
    assert out[2].diff[0]["new"].count("0.30") >= 1


def test_bump_sign_boundary_rejected():
    """符号安全网 (S23, FP-MC-020 通用防线): abs 阈值误用于 0-1 归一化参数
    (0.80 -> -7.20 恒 True 条件) 被拒绝。"""
    new_adj, note = variants.bump_magnitude(
        "sensor(edge_proximity) < 0.80", "sensor(edge_proximity) < 0.72", "rules",
        variants.SEED_PERTURBATION_THRESHOLDS["rules"])  # 错误配置 (abs 8°)
    assert new_adj is None and "符号边界" in note


def test_seed_variants_anchor_missing_skipped(tmp_repo):
    """锚点缺失仍按 S19 规则跳过 (M3 不干扰)。"""
    rules = tmp_repo / "governance" / "meta_language" / "simulation_rules.abdl"
    rules.write_text("RULE r1: if BETWEEN(sensor(opponent_angle), -30, 30) then steer(0)\n",
                     encoding="utf-8")
    out = variants._seed_variants("rules", {}, "test")
    assert out == []


# ---------------------------------------------------------------- 4. 阈值一致性 + 集成
def test_thresholds_align_distill_d2_prior():
    """SEED_PERTURBATION_THRESHOLDS 与 distill_loop.D2_PRIOR 保持一致 (闭环来源同一)。"""
    import distill_loop
    for layer, cfg in variants.SEED_PERTURBATION_THRESHOLDS.items():
        prior = distill_loop.D2_PRIOR.get(layer)
        assert prior is not None, f"D2_PRIOR 缺层 {layer}"
        if cfg["mode"] == "rel":
            assert f">={int(cfg['threshold'] * 100)}%" in prior["min_change"]
        elif layer == "rules":
            # S23 回标: D2_PRIOR rules 为区间表述 "8-12 度", 校验下界数字出现
            assert str(int(cfg["threshold"])) in prior["min_change"]
        else:
            assert f">={cfg['threshold']:g}" in prior["min_change"]


def test_generate_variants_seed_fallback_applies_m3(tmp_repo):
    """generate_variants 种子降级路径 (round 3 及无 LLM 配置时) 带 M3 校验:
    直接经 _seed_variants 的候选 diff 扰动全部达标 (参数级 cfg)。"""
    cands = variants._seed_variants("rules", {}, "test") + \
        variants._seed_variants("mapping", {}, "test") + \
        variants._seed_variants("physics", {}, "test") + \
        variants._seed_variants("action_map", {}, "test")
    for v in cands:
        idx = int(v.id.rsplit("_", 1)[-1]) - 1
        p = variants._SEED_PARAMS[v.layer][idx]
        cfg = p.get("perturb") or variants.SEED_PERTURBATION_THRESHOLDS[v.layer]
        mag, _ = variants.perturbation_magnitude(v.diff[0]["old"], v.diff[0]["new"], v.layer, cfg)
        if cfg is not None and mag is not None:
            assert mag + 1e-9 >= cfg["threshold"], f"{v.id} 扰动未达标: mag={mag}"
