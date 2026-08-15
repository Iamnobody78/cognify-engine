# -*- coding: utf-8 -*-
"""
evaluator_diff_test.py — Sprint 17 评估器差分测试框架
=====================================================
让评估器能够区分"好坏改动"，修复 FP-MC-014/015 暴露的评估盲区：
  - FP-MC-014: no-op 改动（如修改未被消费的常量）在基线全胜场景得满分
  - FP-MC-015: 逻辑损坏改动（如 dist < dist 恒 False）通过全链路验证

核心原理：V9GateEvaluator 使用 hashlib 确定性种子（_stable_seed），
同一种子下两次评估结果 bit-identical（已验证）。因此：
  基线评估 vs 应用候选 diff 后的评估 → 逐项对比（winrate + steps 分布
  + 决策指纹 action_hist/branch_hist）→ 判定：
    PASSED        — winrate 提升
    REGRESSION    — winrate 下降
    SUSPICIOUS    — 行为指纹变化但 winrate 不变（逻辑损坏/评估失敏，触发人工审查）
    INCONCLUSIVE  — 全部一致（no-op 改动，不标记 PASSED）

用法:
  # 1) 运行基线（记录当前工作树状态）
  python evaluator_diff_test.py baseline --episodes 10 --agent-mode abdl \
      --out baseline_report.json

  # 2) 应用候选 diff（candidates/<ts>/diff.patch 或 _snapshots/<ts>/ 目录）→ 评估 → 对比 → 恢复
  python evaluator_diff_test.py diff --patch <candidates/xxx/diff.patch> \
      --baseline baseline_report.json --episodes 10 --agent-mode abdl --out diff_report.json
  python evaluator_diff_test.py snapshot --snapshot <variants/_snapshots/xxx> \
      --baseline baseline_report.json --episodes 10 --agent-mode abdl --out diff_report.json

回归用例（Sprint 17 验收）:
  ca_reward_001  (no-op, EDGE_* 未消费)          -> INCONCLUSIVE
  ca_mapping_001 (注释改动, R8 ROUND 1)          -> INCONCLUSIVE
  ca_mapping_001 (逻辑损坏 dist<dist, R8 ROUND 5) -> SUSPICIOUS
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Sprint 35 T1: Z3 符号验证层 (第四层防护, 联合覆盖数学级证明)
# 延迟 import 到函数内 (symbolic_verify 依赖 z3, 缺失时降级放行)

# repo root = bottlesumo_pi (上一级)
REPO_ROOT = Path(__file__).resolve().parents[2]

# 需要随候选快照一起覆盖的目标文件（候选可修改的文件；评估器自身除外——
# v9_gate_evaluator.py 是我们的差分测试基础设施，覆盖它会污染对比信号）
SNAPSHOT_FILES = [
    "simulation/lightweight_env.py",
    "simulation/reward_functions.py",
    "core/meta_language/abdl_action_bridge.py",
    "governance/meta_language/simulation_rules.abdl",
]

VERDICT_PASSED = "PASSED"
VERDICT_REGRESSION = "REGRESSION"
VERDICT_SUSPICIOUS = "SUSPICIOUS"
VERDICT_INCONCLUSIVE = "INCONCLUSIVE"
VERDICT_ERROR = "ERROR"


# ---------------------------------------------------------------- diff 解析
def parse_harness_patch(patch_text: str) -> List[Dict[str, str]]:
    """解析 meta_harness 自定义 diff.patch 格式:
        --- <candidate> diff[N] (<target_file>)
        - old: '...'
        + new: '...'
    """
    entries: List[Dict[str, str]] = []
    cur: Optional[Dict[str, str]] = None
    for line in patch_text.splitlines():
        m = re.match(r"^---\s+\S+\s+diff\[\d+\]\s+\(([^)]+)\)", line)
        if m:
            cur = {"target_file": m.group(1), "old": "", "new": ""}
            entries.append(cur)
            continue
        if cur is None:
            continue
        m_old = re.match(r"^-\s*old:\s*'(.*)'\s*$", line)
        if m_old:
            cur["old"] = m_old.group(1).replace("''", "'")
            continue
        m_new = re.match(r"^\+\s*new:\s*'(.*)'\s*$", line)
        if m_new:
            cur["new"] = m_new.group(1).replace("''", "'")
    return [e for e in entries if e["old"] and e["new"]]


def apply_harness_patch(patch_path: Path, worktree: Path) -> List[Dict[str, str]]:
    """应用 harness 格式 patch 到工作树。返回应用的条目列表。"""
    text = patch_path.read_text(encoding="utf-8", errors="replace")
    entries = parse_harness_patch(text)
    applied: List[Dict[str, str]] = []
    for e in entries:
        target = worktree / e["target_file"]
        if not target.exists():
            print(f"[!] target not found: {e['target_file']}", file=sys.stderr)
            continue
        src = target.read_text(encoding="utf-8", errors="replace")
        cnt = src.count(e["old"])
        if cnt == 0:
            print(f"[!] old not found in {e['target_file']}: {e['old'][:60]!r}",
                  file=sys.stderr)
            continue
        target.write_text(src.replace(e["old"], e["new"]), encoding="utf-8")
        applied.append(e)
    return applied


# ---------------------------------------------------------------- 快照管理
def copy_snapshot(snapshot_dir: Path, worktree: Path) -> List[str]:
    """从 _snapshots/<ts>/ 覆盖 SNAPSHOT_FILES 到工作树。返回覆盖的文件列表。"""
    copied: List[str] = []
    for rel in SNAPSHOT_FILES:
        src = snapshot_dir / Path(rel).name
        dst = worktree / rel
        if src.exists():
            dst.write_bytes(src.read_bytes())
            copied.append(rel)
    return copied


def snapshot_worktree(worktree: Path, out_dir: Path, tag: str) -> Dict[str, str]:
    """保存当前工作树的 SNAPSHOT_FILES 到 out_dir（用于恢复）。"""
    saved: Dict[str, str] = {}
    for rel in SNAPSHOT_FILES:
        src = worktree / rel
        if src.exists():
            dst = out_dir / f"{tag}__{Path(rel).name}"
            dst.write_bytes(src.read_bytes())
            saved[rel] = str(dst)
    return saved


def restore_worktree(saved: Dict[str, str]) -> None:
    """从 saved 映射恢复工作树文件。"""
    for rel, backup in saved.items():
        dst = REPO_ROOT / rel
        dst.write_bytes(Path(backup).read_bytes())
    print(f"[restore] {len(saved)} files restored")


# ---------------------------------------------------------------- 评估
def run_evaluation(episodes: int, agent_mode: str, backend: str = "lightweight"
                   ) -> Dict[str, Any]:
    """运行一次完整评估（含决策指纹）。"""
    sys.path.insert(0, str(REPO_ROOT))
    from simulation.v9_gate_evaluator import V9GateEvaluator
    ev = V9GateEvaluator(episodes=episodes, backend=backend)
    report = ev.evaluate(agent_mode)
    return report


# ---------------------------------------------------------------- 对比判定
def extract_signal(report: Dict[str, Any]) -> Dict[str, Any]:
    """提取差分对比所需的核心信号（winrate + steps 分布 + 决策指纹）。"""
    eps = []
    for e in report.get("episode_results", []):
        # key 统一 str() — 保证实时信号与 JSON 序列化后语义一致 (JSON key 恒为 str)
        eps.append({
            "episode": int(e["episode"]),
            "opponent": str(e["opponent"]),
            "win": bool(e["win"]),
            "steps": int(e["steps"]),
            "reward": float(e["reward"]),
            "action_hist": {str(k): int(v) for k, v in dict(e.get("action_hist", {})).items()},
            "branch_hist": {str(k): int(v) for k, v in dict(e.get("branch_hist", {})).items()},
        })
    return {
        "winrate": float(report.get("winrate", 0.0)),
        "total_episodes": int(report.get("total_episodes", 0)),
        "episodes": eps,
    }


def compare_signals(base: Dict[str, Any], cand: Dict[str, Any],
                    layer: Optional[str] = None) -> Dict[str, Any]:
    """对比基线/候选信号，输出判定。

    Sprint 24 M2 重构: SUSPICIOUS 分支升级为多信号融合决策 —
    winrate (主) + avg_steps (辅) + layer-specific 信号 (如规则触发次数)
    融合为综合质量分数 Q。当行为指纹变化但 winrate 不变时:
        Q >= M2_PASS_Q    -> PASSED      (效率/层信号显著改善)
        Q <= M2_REGRESS_Q -> REGRESSION  (效率/层信号显著退化)
        否则                -> SUSPICIOUS (保留人工审查)
    layer 为 None 时保持 Sprint 17-23 原始语义 (向后兼容)。
    """
    b_eps = base["episodes"]
    c_eps = cand["episodes"]

    # 1) 严格一致（含决策指纹）→ no-op
    identical = (base == cand)

    # 2) 行为指纹：win + steps + action_hist + branch_hist
    #    Sprint 24 M2: layer 提供时纳入 reward (physics 层 reward 变化是
    #    有效行为信号 — 饱和场景下 winrate/steps 可能相同但轨迹质量不同)
    def behavior(e: Dict[str, Any]) -> Tuple:
        fp = (e["opponent"], bool(e["win"]), e["steps"],
              tuple(sorted(e["action_hist"].items())),
              tuple(sorted(e["branch_hist"].items())))
        if layer is not None:
            fp = fp + (round(float(e["reward"]), 6),)
        return fp

    b_beh = [behavior(e) for e in b_eps]
    c_beh = [behavior(e) for e in c_eps]
    behavior_changed = b_beh != c_beh

    b_win = base["winrate"]
    c_win = cand["winrate"]

    # 3) steps 分布统计
    b_steps = [e["steps"] for e in b_eps]
    c_steps = [e["steps"] for e in c_eps]
    b_avg = sum(b_steps) / len(b_steps) if b_steps else 0.0
    c_avg = sum(c_steps) / len(c_steps) if c_steps else 0.0

    if identical:
        verdict, reason = VERDICT_INCONCLUSIVE, \
            "全部信号与基线一致 — 改动无行为影响 (no-op, FP-MC-014 类)"
    elif not behavior_changed:
        verdict, reason = VERDICT_INCONCLUSIVE, \
            f"行为指纹相同 (winrate {b_win:.2f}->{c_win:.2f}) — 无行为影响"
    elif c_win > b_win:
        verdict, reason = VERDICT_PASSED, \
            f"winrate 提升 {b_win:.2f}->{c_win:.2f} (avg_steps {b_avg:.1f}->{c_avg:.1f})"
    elif c_win < b_win:
        verdict, reason = VERDICT_REGRESSION, \
            f"winrate 下降 {b_win:.2f}->{c_win:.2f} (avg_steps {b_avg:.1f}->{c_avg:.1f})"
    else:
        # 行为变化但 winrate 不变 → Sprint 24 M2: 多信号融合判定
        if layer is not None:
            q, sigs = fused_quality(base, cand, layer)
            if q >= M2_PASS_Q:
                verdict, reason = VERDICT_PASSED, \
                    f"M2 多信号融合正向 (Q={q:.2f}, layer={layer}): {sig_detail(sigs)}"
            elif q <= M2_REGRESS_Q:
                verdict, reason = VERDICT_REGRESSION, \
                    f"M2 多信号融合负向 (Q={q:.2f}, layer={layer}): {sig_detail(sigs)}"
            elif abs(q) < M2_NEAR_ZERO_Q:
                # M2 近零档: 所有辅助信号≈0 — 指纹噪声 (无行为影响),
                # 非 SUSPICIOUS (FP-MC-014 no-op 类, 打破 24 条全 SUSPICIOUS 同构)
                verdict, reason = VERDICT_INCONCLUSIVE, \
                    f"M2 信号近零 (Q={q:.2f}, layer={layer}): {sig_detail(sigs)} — 扰动无行为影响"
            else:
                verdict, reason = VERDICT_SUSPICIOUS, \
                    f"M2 融合中性 (Q={q:.2f}, layer={layer}): {sig_detail(sigs)} — 人工审查"
        else:
            # 原始语义 (Sprint 17-23): 评估失敏或逻辑损坏
            verdict, reason = VERDICT_SUSPICIOUS, \
                f"行为指纹变化但 winrate 不变 ({b_win:.2f}) — 逻辑损坏或评估失敏 (FP-MC-015 类)"

    return {
        "verdict": verdict,
        "reason": reason,
        "baseline": {"winrate": b_win, "avg_steps": round(b_avg, 2),
                     "steps": b_steps},
        "candidate": {"winrate": c_win, "avg_steps": round(c_avg, 2),
                      "steps": c_steps},
        "behavior_changed": behavior_changed,
        "identical": identical,
        "layer": layer,
    }


# ---------------------------------------------------------------- M2 多信号融合 (Sprint 24)
# 权重: winrate 主信号已在 compare_signals 主分支处理; 此处融合辅助信号:
#   steps 效率 (avg_steps 相对变化) + layer-specific 信号 (按层定义)
# Sprint 30 M2.1: 三通道 -> 四通道, 新增 branch_hist 熵变化硬信号 (FP-NEG-004):
#   S29 候选 A (edge 0.65->0.80) 的 60 步局 branch_hist 显示主导分支是
#   FLANK-RIGHT:45 + CAUTIOUS-EDGE:13 (侧翼死循环) 而非"L2 空洞" —
#   拓扑候选动机必须用 branch_hist 逐局验证, 不能凭 avg_steps 推断失败模式。
#   熵坍缩 (分支分布集中到少数分支) = 死循环风险 = 负向; 熵分散 = 正向。
M2_W_STEPS = 0.35         # avg_steps 相对变化权重
M2_W_LAYER = 0.35         # layer-specific 信号权重
M2_W_BRANCH = 0.30        # Sprint 30 M2.1: branch_hist 熵变化权重 (FP-NEG-004)
M2_PASS_Q = 0.15          # Q >= +0.15 -> PASSED (效率/层信号显著改善)
M2_REGRESS_Q = -0.15      # Q <= -0.15 -> REGRESSION
M2_NEAR_ZERO_Q = 0.02     # |Q| < 0.02 -> INCONCLUSIVE (所有信号≈0, 扰动无行为影响)
M2_LAYER_SIGNALS = ("rules", "mapping", "physics")


def _layer_specific_signal(base: Dict[str, Any], cand: Dict[str, Any],
                           layer: str) -> Tuple[float, str]:
    """按层计算 layer-specific 信号 (归一化到约 [-1, 1], 正值 = 候选更优)。

    rules  : branch_hist 中规则分支触发总次数 (S23 实证: edge-loop 时
             SIM-HEUR-CAUTIOUS-EDGE 触发 30-46 次 = 转向过度; 触发骤增 = 负向)
    mapping: action_hist 动作分布熵 (熵升 = 动作更多样; 对 mapping 扰动,
             熵显著下降且 winrate 不变 = 动作坍缩 = 负向)
    physics: reward 均值变化率 (相同 winrate 下 reward 更高 = 轨迹更优 = 正向)
    """
    b_eps = base["episodes"]
    c_eps = cand["episodes"]

    def _total(eps, key):
        return sum(sum(e.get(key, {}).values()) for e in eps)

    if layer == "rules":
        b_trig = _total(b_eps, "branch_hist")
        c_trig = _total(c_eps, "branch_hist")
        if b_trig == 0:
            return 0.0, f"rules 触发总数 基线=0 (无规则分支)"
        rel = (b_trig - c_trig) / b_trig  # 正 = 候选触发更少 (更精简)
        return max(-1.0, min(1.0, rel)), \
            f"rules 触发总数 {b_trig}->{c_trig} (rel={rel:+.2f})"
    if layer == "mapping":
        import math

        def _entropy(eps):
            acts = [_total([e], "action_hist") for e in eps]
            n = sum(acts)
            if n == 0:
                return 0.0
            h = 0.0
            for a in acts:
                p = a / n
                if p > 0:
                    h -= p * math.log2(p)
            return h / math.log2(max(len(acts), 2))

        b_h, c_h = _entropy(b_eps), _entropy(c_eps)
        rel = c_h - b_h  # 熵变化 (正 = 更多样)
        return max(-1.0, min(1.0, rel)), \
            f"mapping 动作熵 {b_h:.3f}->{c_h:.3f} (Δ={rel:+.3f})"
    if layer == "physics":
        b_r = sum(e["reward"] for e in b_eps) / max(len(b_eps), 1)
        c_r = sum(e["reward"] for e in c_eps) / max(len(c_eps), 1)
        if abs(b_r) < 1e-9:
            return 0.0, "physics reward 基线=0"
        rel = (c_r - b_r) / abs(b_r)
        return max(-1.0, min(1.0, rel)), \
            f"physics reward {b_r:.3f}->{c_r:.3f} (rel={rel:+.2f})"
    return 0.0, f"未知 layer '{layer}' (无 layer 信号)"


def _branch_hist_signal(base: Dict[str, Any], cand: Dict[str, Any],
                        layer: str) -> Tuple[float, str]:
    """Sprint 30 M2.1 第四通道: branch_hist 熵变化硬信号 (FP-NEG-004 编码)。

    S29 教训: 候选 A (edge 0.65->0.80) 的 60 步局 branch_hist 显示主导分支是
    FLANK-RIGHT:45 + CAUTIOUS-EDGE:13 (侧翼死循环) — 拓扑候选的失败模式
    必须用 branch_hist 逐局验证, 不能凭 avg_steps 推断。
    编码: 每 episode 的 branch_hist 分布熵 (归一化 [0,1], 1=均匀分布):
      - 熵坍缩 (cand 熵显著低于 base) = 分支集中到少数规则 = 死循环/循环风险 = 负向
      - 熵分散 (cand 熵高于 base) = 更多分支被利用 = 正向
    仅在候选层含 branch_hist 语义时启用 (rules/mapping/physics 均产生
    branch_hist); 无分支分布时返回 0 (不惩罚)。
    """
    import math

    # 无 ABDL 分支语义的层 (physics/reward/gate): 不产生 branch_hist 分布,
    # 第四通道不适用 -> 返回 None 触发权重回退三通道 (Sprint 24 行为保持)
    if layer in ("physics", "reward", "gate"):
        return None, "branch_hist 熵: 该层无 ABDL 分支语义 (跳过第四通道)"

    def _avg_entropy(eps):
        hs = []
        for e in eps:
            hist = e.get("branch_hist") or {}
            counts = list(hist.values())
            if not counts:
                continue
            n = sum(counts)
            if n == 0:
                continue
            if len(counts) < 2:
                hs.append(0.0)  # 单分支 = 完全坍缩 (熵 0)
                continue
            h = 0.0
            for c in counts:
                p = c / n
                if p > 0:
                    h -= p * math.log2(p)
            hs.append(h / math.log2(len(counts)))  # 归一化 [0,1]
        return sum(hs) / len(hs) if hs else None

    b_h = _avg_entropy(base["episodes"])
    c_h = _avg_entropy(cand["episodes"])
    if b_h is None or c_h is None:
        return None, "branch_hist 熵: 无分支分布 (跳过第四通道)"
    rel = c_h - b_h  # 正 = 候选分支更多样 (熵升)
    # 归一化: 熵差 0.2 即满幅 (±1); 避免微小波动放大
    sig = max(-1.0, min(1.0, rel / 0.2))
    return sig, f"branch_hist 熵 {b_h:.3f}->{c_h:.3f} (Δ={rel:+.3f})"


def fused_quality(base: Dict[str, Any], cand: Dict[str, Any],
                  layer: str) -> Tuple[float, Dict[str, Any]]:
    """M2 多信号融合: 计算综合质量分数 Q (正值 = 候选更优)。

    Sprint 30 M2.1: 三通道 -> 四通道 (winrate 主信号仍在 compare_signals 主分支)
      Q = w_steps * steps_eff + w_layer * layer_signal + w_branch * branch_signal
      steps_eff = (b_avg - c_avg) / max(b_avg, 1)  — 正 = 候选更快 (效率提升)
      layer_signal = 层特定信号 (见 _layer_specific_signal)
      branch_signal = branch_hist 熵变化 (FP-NEG-004 编码, 见 _branch_hist_signal)
    """
    b_steps = [e["steps"] for e in base["episodes"]]
    c_steps = [e["steps"] for e in cand["episodes"]]
    b_avg = sum(b_steps) / len(b_steps) if b_steps else 0.0
    c_avg = sum(c_steps) / len(c_steps) if c_steps else 0.0
    steps_eff = (b_avg - c_avg) / max(b_avg, 1.0)
    layer_sig, layer_desc = _layer_specific_signal(base, cand, layer)
    branch_sig, branch_desc = _branch_hist_signal(base, cand, layer)
    if branch_sig is None:
        # 无 branch_hist 语义的层 (reward/gate): 回退为三通道,
        # M2_W_BRANCH 按 1:1 回退给 steps/layer -> 完全恢复 Sprint 24 权重
        w_steps = M2_W_STEPS + M2_W_BRANCH / 2.0
        w_layer = M2_W_LAYER + M2_W_BRANCH / 2.0
        branch_sig_f = 0.0
        branch_desc = branch_desc + " (权重回退: 恢复三通道)"
    else:
        # Sprint 30 M2.1 方向约束: 熵升仅在效率同步提升时计为正向;
        # 效率下降时的熵升是触发域扩大造成的抖动 (S29 候选 B 实证:
        # dist>=0.3 触发 214->248, 熵升 +0.024 但 avg_steps 21.4->24.8 恶化),
        # 应置中性, 不能抵消主要负向信号。熵降 (坍缩/死循环) 无条件负向。
        if branch_sig > 0 and steps_eff <= 0:
            branch_desc = branch_desc + " (熵升但效率未升: 计中性, 权重回退)"
            branch_sig_f = 0.0
            # 计中性 = 第四通道无新增信息 -> 权重回退三通道,
            # 避免 0.30 权重稀释主要信号 (S30 M2.3 候选 B 实证:
            # -0.159*0.7=-0.111 滑出 REGRESSION 阈值, 需回退保持 -0.159)
            w_steps = M2_W_STEPS + M2_W_BRANCH / 2.0
            w_layer = M2_W_LAYER + M2_W_BRANCH / 2.0
        else:
            w_steps, w_layer = M2_W_STEPS, M2_W_LAYER
            branch_sig_f = branch_sig
    q = w_steps * steps_eff + w_layer * layer_sig + M2_W_BRANCH * branch_sig_f
    return q, {
        "layer": layer,
        "steps_eff": round(steps_eff, 3),
        "layer_signal": round(layer_sig, 3),
        "layer_desc": layer_desc,
        "branch_signal": round(branch_sig_f, 3),
        "branch_desc": branch_desc,
        "avg_steps": {"base": round(b_avg, 2), "cand": round(c_avg, 2)},
    }


def sig_detail(sigs: Dict[str, Any]) -> str:
    """M2 信号摘要 (可读一行)。"""
    parts = [f"steps_eff={sigs['steps_eff']:+.3f} "
             f"avg_steps {sigs['avg_steps']['base']}->{sigs['avg_steps']['cand']}",
             sigs["layer_desc"]]
    if "branch_desc" in sigs:
        parts.append(sigs["branch_desc"])
    return " | ".join(parts)


# ---------------------------------------------------------------- M2.2b 覆盖连续性预检 (Sprint 32, FP-NEG-005)
# 维度投影: 对条件域收窄/迁移类变更, 检测是否产生"无规则覆盖的连续区间"(覆盖空洞)。
# topo_D 教训 (S31): FLANK 角度 ±10->±15 收窄后 (-15,-10)∪(10,15) 无任何规则匹配
#   -> ABDL 落入无命名默认分支 (裸 'abdl' 键 92 次), avg_steps 21.4->34.1 (+59%)。
#   预检只查 priority 重排 (S30 M2.2) 无法捕获此类损坏 -> S32 升级。

# 传感器维度 -> (最小, 最大) 值域 (仅数值维度可投影)
_COVERAGE_DIMS = {
    "opponent_angle": (-180.0, 180.0),
    "opponent_dist": (0.0, 10.0),
    "edge_proximity": (0.0, 1.0),
}


def _parse_dim_intervals(rules_text: str, dim: str) -> List[Tuple[float, float]]:
    """解析规则文本中某传感器维度的全部触发区间 (闭区间语义, 边界含=)。

    支持 ABDL 条件语法:
      sensor(dim) < X   -> (-inf, X)
      sensor(dim) <= X  -> (-inf, X]
      sensor(dim) > X   -> (X, +inf)
      sensor(dim) >= X  -> [X, +inf)
      BETWEEN(sensor(dim), A, B) -> [A, B]
    返回已排序的闭区间列表 (起点升序)。容错: 无法解析时返回空列表 (视为无覆盖)。
    """
    intervals: List[Tuple[float, float]] = []
    pat_lt = re.compile(rf"sensor\(\s*{dim}\s*\)\s*<=\s*(-?[\d.]+)")
    pat_lt_strict = re.compile(rf"sensor\(\s*{dim}\s*\)\s*<\s*(-?[\d.]+)")
    pat_gt = re.compile(rf"sensor\(\s*{dim}\s*\)\s*>=\s*(-?[\d.]+)")
    pat_gt_strict = re.compile(rf"sensor\(\s*{dim}\s*\)\s*>\s*(-?[\d.]+)")
    pat_between = re.compile(
        rf"BETWEEN\(\s*sensor\(\s*{dim}\s*\)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")

    dim_lo, dim_hi = _COVERAGE_DIMS[dim]
    for m in pat_lt.finditer(rules_text):
        intervals.append((dim_lo, min(dim_hi, float(m.group(1)))))
    for m in pat_lt_strict.finditer(rules_text):
        intervals.append((dim_lo, min(dim_hi, float(m.group(1)))))
    for m in pat_gt.finditer(rules_text):
        intervals.append((max(dim_lo, float(m.group(1))), dim_hi))
    for m in pat_gt_strict.finditer(rules_text):
        intervals.append((max(dim_lo, float(m.group(1))), dim_hi))
    for m in pat_between.finditer(rules_text):
        a, b = float(m.group(1)), float(m.group(2))
        intervals.append((max(dim_lo, min(a, b)), min(dim_hi, max(a, b))))
    intervals.sort()
    return intervals


def _merge_intervals(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """合并重叠/相邻闭区间 -> 覆盖并集 (降噪: 滤除空区间)。"""
    merged: List[Tuple[float, float]] = []
    for lo, hi in intervals:
        if lo > hi:
            continue
        if not merged or lo > merged[-1][1] + 1e-9:
            merged.append((lo, hi))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
    return merged


def _coverage_gaps(rules_text: str, dim: str) -> List[Tuple[float, float]]:
    """返回维度 dim 上未被任何规则覆盖的连续区间 (覆盖空洞)。

    覆盖 = 至少一条规则的条件在 dim 上包含该点 (维度投影; 多条件 AND 规则
    按保守处理: 任一条规则的该维度条件满足即视为该点有潜在覆盖)。
    对条件域收窄检测, 投影足够: 空洞必然无规则可匹配。
    """
    dim_lo, dim_hi = _COVERAGE_DIMS[dim]
    merged = _merge_intervals(_parse_dim_intervals(rules_text, dim))
    if not merged:
        return [(dim_lo, dim_hi)]
    gaps: List[Tuple[float, float]] = []
    cursor = dim_lo
    for lo, hi in merged:
        if lo > cursor + 1e-6:
            gaps.append((cursor, lo))
        cursor = max(cursor, hi)
    if cursor < dim_hi - 1e-6:
        gaps.append((cursor, dim_hi))
    return gaps


def coverage_continuity_check(entries: List[Dict[str, Any]],
                              rules_text: str) -> Tuple[bool, str]:
    """Sprint 32 P0 (FP-NEG-005): 条件域收窄/迁移后的覆盖连续性预检。

    1. 找出 entries 涉及的传感器维度 (数值型: angle/dist/edge)
    2. 模拟应用全部 diff (text.replace) 得到候选规则文本
    3. 对比基线 vs 候选: 候选新增的覆盖空洞 (基线有覆盖、变更后无覆盖)
       -> COVERAGE_GAP 拦截, 不进评估循环
    返回 (valid, reason)。valid=False 时外层记录 topo_precheck_failed。
    """
    involved = {d for en in entries
                for d in _COVERAGE_DIMS
                if f"sensor({d})" in str(en.get("old", ""))
                or f"sensor({d})" in str(en.get("new", ""))}
    if not involved:
        return True, "无数值维度条件变更 (纯 priority/文本变更), 覆盖检查跳过"

    # 模拟应用 (与 apply_variant 相同的 text.replace 语义)
    candidate_text = rules_text
    for idx, en in enumerate(entries):
        old = str(en.get("old", ""))
        new = str(en.get("new", ""))
        if not old:
            continue
        cnt = candidate_text.count(old)
        exp = en.get("expected")
        if cnt == 0 or (exp is not None and cnt != exp):
            return False, (f"COVERAGE_GAP 预检: entry#{idx} 锚点失配 "
                           f"(old 出现 {cnt} 次, expected={exp})")
        candidate_text = candidate_text.replace(old, new, cnt)

    new_gaps: List[str] = []
    for dim in sorted(involved):
        base_gaps = _coverage_gaps(rules_text, dim)
        cand_gaps = _coverage_gaps(candidate_text, dim)
        # 新增空洞 = 候选空洞中未被任何基线空洞完全覆盖的部分
        for gl, gh in cand_gaps:
            covered_by_base = any(bl <= gl + 1e-6 and gh <= bh + 1e-6
                                  for bl, bh in base_gaps)
            if not covered_by_base:
                new_gaps.append(f"{dim} ({gl:.2f},{gh:.2f})")
    if not new_gaps:
        return True, ("条件域变更后维度覆盖连续 (无新增空洞), 放行 — "
                      "行为影响由差分评估捕获")
    return False, ("COVERAGE_GAP: 条件域收窄产生无规则覆盖区间 "
                   f"{', '.join(new_gaps)} -> 拦截 (S31 topo_D 同构损坏)")


# ---------------------------------------------------------------- M2.2 拓扑变更有效性预检 (Sprint 30)
def precheck_topology_validity(entries: List[Dict[str, Any]],
                               rules_text: str) -> Tuple[bool, str]:
    """Sprint 30 M2.2: 拓扑变更有效性预检 — 优先级重排是否改变 resolve_top() 胜者集合。

    S29 教训 (候选 C): SPEED-ADAPT priority 300->350 no-op — ABDL 引擎按 priority
    降序排序后取最高, 300->350 在优先级全序中仍是第 7 位 (350 < 470 且 > 250),
    没有跨越任何邻居规则 → 胜者集合不变 → 结构性 no-op。

    预检规则 (仅涉及 ABDL 优先级重排的候选):
      1. 提取 entries 中所有 "priority: N" -> "priority: M" 变更 (N != M)
      2. 解析 rules_text 中的完整优先级全序 (所有规则的 priority 值)
      3. 对每个变更: 检查区间 (min(N,M), max(N,M)) 内是否存在其他规则 priority
         - 存在 -> 跨越邻居, 排序真实变化 -> 有效拓扑变更 (放行)
         - 不存在 -> 未跨越任何邻居, 胜者集合不变 -> no-op (拦截, 不进入评估循环)
    返回 (valid, reason): valid=False 时外层应记录 topo_precheck_failed 并跳过评估。

    非优先级变更 (阈值/前提/触发域) 不涉及胜者集合重排语义, 直接放行 —
    它们的行为影响由差分评估 (branch_hist 熵第四通道) 捕获。

    Sprint 32 升级 (FP-NEG-005): 在 priority 检查前执行覆盖连续性预检,
    拦截条件域收窄产生的覆盖空洞 (topo_D 同构损坏)。
    """
    # 0) 覆盖连续性预检 (S32 P0, FP-NEG-005) — 条件域收窄/迁移类变更
    cov_ok, cov_reason = coverage_continuity_check(entries, rules_text)
    if not cov_ok:
        return False, cov_reason

    # 0.5) 符号验证预检 (S35 T1, 第四层防护) — 联合空间覆盖包含 (Z3 数学级)
    # S32 是单维投影 (angle/dist/edge 各自合并并集检测空洞); Z3 验证
    # 「候选覆盖 ⊆ 基线覆盖」的联合包含关系, 捕获单维投影盲区的多维联合空洞
    # (如 CLOSE-PUSH edge 0.65->0.30 收窄: 各维度投影均有覆盖, S32 放行,
    #  但联合空间 (opp_found=True, dist<0.6, angle∈(-10,10), edge∈(0.30,0.65))
    #  成空洞 -> SYMBOLIC_PROOF_FAIL)。z3 缺失时降级放行, 不阻断管道。
    try:
        from governance.meta_harness import symbolic_verify as _sym
    except Exception:
        try:
            import symbolic_verify as _sym
        except Exception:
            _sym = None
    if _sym is not None:
        sym_ok, sym_reason, _sym_stats = _sym.symbolic_verify_diff(
            entries, rules_text=rules_text)
        if not sym_ok:
            return False, sym_reason

    # 1) 提取 priority 变更
    prio_changes = []  # (rule_id 或位置, old, new)
    for idx, en in enumerate(entries):
        old = str(en.get("old", ""))
        new = str(en.get("new", ""))
        mo = re.search(r"priority\s*[:=]\s*(\d+)", old)
        mn = re.search(r"priority\s*[:=]\s*(\d+)", new)
        if mo and mn and mo.group(1) != mn.group(1):
            prio_changes.append((idx, int(mo.group(1)), int(mn.group(1))))
    if not prio_changes:
        return True, "无优先级重排 (非拓扑变更, 放行)"

    # 2) 解析 rules_text 的完整优先级全序 (不含变更自身的旧值所在行)
    all_prios = [int(m.group(1)) for m in re.finditer(r"priority\s*[:=]\s*(\d+)",
                                                      rules_text)]
    for idx, old_p, new_p in prio_changes:
        lo, hi = (old_p, new_p) if old_p < new_p else (new_p, old_p)
        # 排除变更自身占位 (旧值), 只统计其他规则的 priority
        crossed = [p for p in all_prios if lo < p < hi]
        if not crossed:
            return False, (f"priority {old_p}->{new_p} (entry#{idx}) 未跨越任何邻居规则: "
                           f"区间 ({lo},{hi}) 内无其他 priority, resolve_top() 胜者集合不变 "
                           f"-> 结构性 no-op (S29 候选 C 同构), 预检拦截")
    return True, (f"priority 重排跨越邻居: "
                  f"{[(old_p, new_p) for _, old_p, new_p in prio_changes]} -> "
                  f"胜者集合可能变化, 放行进入评估")


def topology_precheck_report(entries: List[Dict[str, Any]],
                             rules_path: Optional[str] = None) -> Tuple[bool, str]:
    """读取规则文件后调用 precheck_topology_validity; rules_path 缺省时自动定位。

    Sprint 30 M2.2 挂载点: outer_loop.run_round 在 apply_precheck 之后、
    apply_variant 之前调用 — 预检拦截的候选不消耗评估预算。
    """
    if rules_path is None:
        rules_path = str(REPO_ROOT / "governance/meta_language/simulation_rules.abdl")
    if not os.path.isfile(rules_path):
        return True, f"规则文件缺失 ({rules_path}) — 降级放行"
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            rules_text = f.read()
    except OSError as e:
        return True, f"规则文件读取失败 ({e}) — 降级放行"
    return precheck_topology_validity(entries, rules_text)


# ---------------------------------------------------------------- 主流程
def cmd_baseline(args: argparse.Namespace) -> int:
    report = run_evaluation(args.episodes, args.agent_mode, args.backend)
    sig = extract_signal(report)
    out = {
        "mode": "baseline",
        "agent_mode": args.agent_mode,
        "backend": args.backend,
        "episodes": args.episodes,
        "signal": sig,
        "note": "基线信号 — 差分测试对照基准 (FP-MC-014/015 对策)",
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[baseline] winrate={sig['winrate']:.2f} avg_steps="
          f"{sum(e['steps'] for e in sig['episodes'])/len(sig['episodes']):.1f} "
          f"-> {out_path}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    if baseline.get("mode") != "baseline":
        print(f"[!] {args.baseline} 不是 baseline 报告", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        saved = snapshot_worktree(REPO_ROOT, Path(tmp), "pre")
        try:
            applied = apply_harness_patch(Path(args.patch), REPO_ROOT)
            if not applied:
                print("[!] patch 未应用任何条目 — 检查 diff.patch 格式", file=sys.stderr)
                return 2
            print(f"[apply] {len(applied)} entries applied from {args.patch}")
            cand_report = run_evaluation(args.episodes, args.agent_mode, args.backend)
        finally:
            restore_worktree(saved)

    sig = extract_signal(cand_report)
    verdict = compare_signals(baseline["signal"], sig)
    out = {
        "mode": "diff",
        "patch": str(args.patch),
        "agent_mode": args.agent_mode,
        "verdict": verdict,
        "candidate_signal": sig,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[diff] verdict={verdict['verdict']}")
    print(f"       {verdict['reason']}")
    if verdict["verdict"] == VERDICT_SUSPICIOUS:
        print("[!!] SUSPICIOUS — 需人工审查候选 diff (逻辑损坏或评估失敏)")
    print(f"       -> {out_path}")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    if baseline.get("mode") != "baseline":
        print(f"[!] {args.baseline} 不是 baseline 报告", file=sys.stderr)
        return 2

    snap_dir = Path(args.snapshot)
    if not snap_dir.is_dir():
        print(f"[!] snapshot 目录不存在: {snap_dir}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory() as tmp:
        saved = snapshot_worktree(REPO_ROOT, Path(tmp), "pre")
        try:
            copied = copy_snapshot(snap_dir, REPO_ROOT)
            if not copied:
                print("[!] snapshot 未覆盖任何文件", file=sys.stderr)
                return 2
            print(f"[apply] snapshot {snap_dir.name}: {len(copied)} files overlaid")
            cand_report = run_evaluation(args.episodes, args.agent_mode, args.backend)
        finally:
            restore_worktree(saved)

    sig = extract_signal(cand_report)
    verdict = compare_signals(baseline["signal"], sig)
    out = {
        "mode": "snapshot",
        "snapshot": str(snap_dir),
        "agent_mode": args.agent_mode,
        "verdict": verdict,
        "candidate_signal": sig,
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[snapshot] verdict={verdict['verdict']}")
    print(f"           {verdict['reason']}")
    if verdict["verdict"] == VERDICT_SUSPICIOUS:
        print("[!!] SUSPICIOUS — 需人工审查候选 (逻辑损坏或评估失敏)")
    print(f"           -> {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Sprint 17 评估器差分测试 — 区分好坏改动 (FP-MC-014/015 对策)")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("baseline", help="记录基线信号")
    b.add_argument("--episodes", type=int, default=10)
    b.add_argument("--agent-mode", default="abdl",
                   choices=["abdl", "heuristic", "hybrid"])
    b.add_argument("--backend", default="lightweight", choices=["lightweight", "mujoco"])
    b.add_argument("--out", default="baseline_report.json")
    b.set_defaults(func=cmd_baseline)

    d = sub.add_parser("diff", help="应用 harness diff.patch 并对比")
    d.add_argument("--patch", required=True, help="candidates/<ts>/diff.patch")
    d.add_argument("--baseline", required=True)
    d.add_argument("--episodes", type=int, default=10)
    d.add_argument("--agent-mode", default="abdl",
                   choices=["abdl", "heuristic", "hybrid"])
    d.add_argument("--backend", default="lightweight", choices=["lightweight", "mujoco"])
    d.add_argument("--out", default="diff_report.json")
    d.set_defaults(func=cmd_diff)

    s = sub.add_parser("snapshot", help="用 _snapshots/<ts>/ 覆盖文件并对比")
    s.add_argument("--snapshot", required=True, help="_snapshots/<ts> 目录")
    s.add_argument("--baseline", required=True)
    s.add_argument("--episodes", type=int, default=10)
    s.add_argument("--agent-mode", default="abdl",
                   choices=["abdl", "heuristic", "hybrid"])
    s.add_argument("--backend", default="lightweight", choices=["lightweight", "mujoco"])
    s.add_argument("--out", default="snapshot_report.json")
    s.set_defaults(func=cmd_snapshot)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
