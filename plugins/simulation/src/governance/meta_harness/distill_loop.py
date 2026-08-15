# -*- coding: utf-8 -*-
"""
distill_loop.py — Sprint 21 P2 自蒸馏数据管道 (M1)
====================================================
PM 裁决 (Sprint 20): M1+M3 优先, M2 延后; 不触发 V9 门路径; 证据文档简化格式。

防 decoding collapse 核心设计 (对齐 arXiv 2607.17558 Why Does FADS Fail?):
  不蒸馏 LLM 自由文本 (重复模板风险), 蒸馏结构化判定语义——
  diff_verdict (确定性标签) + 行为指纹差异 (reason 类别) + 扰动幅度 (层先验表)。

输入: meta_decisions.jsonl (diff_gate 记录) + mcp_usage_report.jsonl (工具分布上下文)
输出: experience/distill_rules_<ts>.json (版本化规则) + 统计摘要

蒸馏资产:
  D1 失敏检测规则  : SUSPICIOUS = winrate 饱和时行为指纹变化 -> 评估失敏信号
  D2 扰动映射先验  : INCONCLUSIVE = 扰动未跨越行为感知阈值 -> 生成层最小扰动 (M3 提示注入)
  D3 多样性度量    : layer x verdict 分布 + 各层拦截占比 (跨轮诊断, 供 stagnation 归因)

运行: python distill_loop.py [--decisions <path>] [--mcp <path>] [--since <ts>]
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

# 层 -> 建议扰动幅度 (D2 默认先验表; rules 于 S23 回标: INCONCLUSIVE 下界 5°(±15->±10 无行为变化)
# + REGRESSION 上界 10°(S22 ±15->-5,10 不对称窗劣化) -> 安全区间 8-12°)
D2_PRIOR = {
    "rules": {"kind": "角度锚点", "min_change": "8-12 度 (安全区间, >12° 有劣化风险)",
              "example": "BETWEEN(-15,15) -> BETWEEN(-7,7) 对称收窄 8°"},
    "mapping": {"kind": "数值阈值", "min_change": ">=20%",
                "example": "dist < 0.20 -> dist < 0.16 或 dist < 0.25"},
    "physics": {"kind": "物理系数", "min_change": ">=0.2",
                "example": "TIMESTEP*0.8 -> TIMESTEP*1.2"},
    # Sprint 28 A1 (PM 裁决): TURN_*_MED 轮速增益, 绝对差 0.6->0.8 = 0.2
    "action_map": {"kind": "轮速幅值", "min_change": ">=0.2",
                   "example": "Action.TURN_R_MED: (0.0,-0.6) -> (0.0,-0.8) (L/R 对称)"},
}

# 默认路径 (相对 meta_harness 目录)
DEFAULT_DECISIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "meta_decisions.jsonl")
DEFAULT_MCP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "mcp_usage_report.jsonl")
DEFAULT_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "experience")


def load_jsonl(path):
    """读取 jsonl, 容错空行/坏行。返回 list[dict]。"""
    recs = []
    with open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                recs.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
    return recs


def filter_diff_gate(recs, verdicts=None):
    """过滤 diff_gate 记录; verdicts 非空时按判定白名单过滤。"""
    dg = [r for r in recs if r.get("type") == "diff_gate"]
    if verdicts:
        dg = [r for r in dg if r.get("diff_verdict") in verdicts]
    return dg


def _winrate_saturated(rec):
    """score==1.0 视为 winrate 饱和 (与 S19/S20 观察一致)。"""
    s = rec.get("score")
    return s is not None and float(s) >= 1.0


def distill_d1(dg):
    """D1 失敏检测规则: SUSPICIOUS 记录 -> 评估失敏信号。

    每条 SUSPICIOUS 的语义: 行为指纹变化但 winrate 不变 —— 若 winrate 饱和,
    说明评估对行为变化失敏 (FP-MC-015 类), 需降级到次级信号。
    """
    rules, stats = [], {"count": 0, "saturated": 0, "by_layer": {}}
    for r in dg:
        if r.get("diff_verdict") != "SUSPICIOUS":
            continue
        stats["count"] += 1
        layer = r.get("layer", "?")
        stats["by_layer"][layer] = stats["by_layer"].get(layer, 0) + 1
        sat = _winrate_saturated(r)
        if sat:
            stats["saturated"] += 1
        rules.append({
            "id": f"D1-{r.get('variant_id', '?')}",
            "source": r.get("ts", "?"),
            "layer": layer,
            "signal": ("winrate 饱和 (1.0) 时行为指纹变化" if sat
                       else "行为指纹变化但 winrate 不变"),
            "verdict": "SUSPICIOUS",
            "action": ("评估层降级到次级信号 (steps/动作熵/对抗配置), 否则无法区分好坏"
                       if sat else "转人工审查行为指纹差异"),
            "evidence": [r.get("reason", "")],
            "quality": r.get("quality"),
            "reason_raw": r.get("reason", ""),
        })
    return rules, stats


def distill_d2(dg):
    """D2 扰动-行为映射先验: INCONCLUSIVE 记录 -> 层级最小扰动建议。

    每条 INCONCLUSIVE 的语义: 行为指纹不变 (信号相同) —— 扰动未跨越行为感知阈值。
    归纳为生成层先验 (M3 注入 code_agent_proposer 辅助提示), 并验证 D2_PRIOR 表。
    """
    rules, stats = [], {"count": 0, "by_layer": {}}
    for r in dg:
        if r.get("diff_verdict") != "INCONCLUSIVE":
            continue
        stats["count"] += 1
        layer = r.get("layer", "?")
        stats["by_layer"][layer] = stats["by_layer"].get(layer, 0) + 1
        prior = D2_PRIOR.get(layer, {"kind": "通用", "min_change": "未知",
                                     "example": "请显著加大扰动"})
        rules.append({
            "id": f"D2-{r.get('variant_id', '?')}",
            "source": r.get("ts", "?"),
            "layer": layer,
            "signal": "扰动未跨越行为感知阈值 (行为指纹不变)",
            "verdict": "INCONCLUSIVE",
            "action": f"生成层注入最小扰动先验: {prior['kind']} 变化 {prior['min_change']} "
                      f"(例: {prior['example']})",
            "min_change": prior["min_change"],
            "evidence": [r.get("reason", "")],
            "quality": r.get("quality"),
            "reason_raw": r.get("reason", ""),
        })
    return rules, stats


def distill_d3(dg, mcp=None):
    """D3 候选多样性度量: layer x verdict 分布矩阵 + MCP 工具分布上下文。"""
    layers = sorted({r.get("layer", "?") for r in dg})
    verdicts = sorted({r.get("diff_verdict", "?") for r in dg})
    matrix = {l: {v: 0 for v in verdicts} for l in layers}
    for r in dg:
        matrix[r.get("layer", "?")][r.get("diff_verdict", "?")] += 1
    stats = {
        "total_blocked": len(dg),
        "layer_x_verdict": matrix,
        "by_verdict": {v: sum(matrix[l][v] for l in layers) for v in verdicts},
        "mcp_tools": _mcp_tool_dist(mcp) if mcp else {},
    }
    return stats


# ---------------------------------------------------------------- D4 治理发现蒸馏 (Sprint 32, V9 门触发)
# 输入: Sprint 31 三大治理发现 (结构化, 非 LLM 自由文本 -> 防 decoding collapse)
#   1. FP-NEG-005 覆盖真空: topo_D FLANK ±10->±15 收窄 -> (-15,-10)∪(10,15) 无规则覆盖
#      裸 abdl 分支 92 次, avg_steps 21.4->34.1 (+59%) -> 拓扑候选需覆盖连续性预检
#   2. FP-NEG-006 归因修正: ep7 交替死循环 = FLANK 高频正常重复 (stuck 恒<3, 0.55~0.60
#      空采样) -> 干预点是 FLANK 触发次数上限, 非 stuck 传感器
#   3. CAUTIOUS-EDGE 冗余: topo_A 回放 CLOSE-PUSH 上界对齐后 CAUTIOUS-EDGE 13->0
#      消失, 步数仅 -1 -> 可被 CLOSE-PUSH 无损替代 -> S32 候选 G 移除评估
D4_DISCOVERIES = [
    {
        "id": "D4-1",
        "name": "覆盖连续性预检 (coverage continuity precheck)",
        "source": "FP-NEG-005 / Sprint 31 topo_D REGRESSION (Q=-0.53)",
        "symptom": "条件域收窄产生无规则覆盖的连续区间 -> ABDL 落入无命名默认分支, 行为随机化",
        "evidence": "sensor(opponent_angle) < -10 -> < -15 后 (-15,-10)∪(10,15) 无匹配; 裸 'abdl' 键 92 次; avg_steps +59%",
        "rule": ("规则拓扑候选 apply 前必须执行覆盖连续性预检; 条件域收窄/迁移类变更 "
                 "需验证邻居规则在收窄区间有覆盖 (或候选同时补足覆盖), 否则标 COVERAGE_GAP 拦截"),
        "trigger": "diff 含 sensor(<dim>) < X -> < Y (Y<X) 或 > X -> > Y (Y>X) 或 BETWEEN 收窄",
    },
    {
        "id": "D4-2",
        "name": "慢局归因修正 (FLANK 高频重复, 非 stuck 死锁)",
        "source": "FP-NEG-006 / Sprint 31 topo_E/topo_F 双 no-op 证伪",
        "symptom": "分支高频触发被误判为死循环/stuck, 导致错误的退出机制设计",
        "evidence": "ep7 FLANK-RIGHT 45 + CAUTIOUS-EDGE 13; topo_F stuck_counter<3 逐位 no-op (stuck 恒<3); topo_E 0.55->0.60 空采样",
        "rule": ("FLANK 类分支高频重复触发时, 先用 branch_hist 逐局验证触发时 stuck_counter "
                 "是否真达到阈值; 若恒<3 则干预点应为触发次数上限 (per-episode cap), "
                 "而非 stuck 传感器门控"),
        "trigger": "慢局 (>30 步) 由单一分支 >40 次触发主导",
    },
    {
        "id": "D4-3",
        "name": "冗余分支识别 (CAUTIOUS-EDGE 可无损替代)",
        "source": "Sprint 31 topo_A 回放 (INCONCLUSIVE -> SUSPICIOUS, M2 四通道捕获)",
        "symptom": "分支触发域被邻居规则覆盖时, 分支本身近似冗余",
        "evidence": "CLOSE-PUSH edge 0.65->0.80 对齐后 CAUTIOUS-EDGE 13->0 消失, 步数仅 -1",
        "rule": ("若某分支的触发域被邻居规则完全包含, 且移除后步数变化 <=1, "
                 "标记为冗余候选 (S32 候选 G); 移除评估须在覆盖预检 (D4-1) 稳定后进行"),
        "trigger": "覆盖投影显示分支触发域 ⊆ 邻居触发域",
    },
]


def distill_d4(discoveries=None):
    """D4 治理发现蒸馏: 将 Sprint 31 结构化发现编码为可复用规则库。

    返回 (rules, stats)。discoveries 为空时使用内置 D4_DISCOVERIES (S31 实证)。
    """
    src = discoveries or D4_DISCOVERIES
    rules, stats = [], {"count": 0, "ids": []}
    for disc in src:
        rules.append({
            "id": disc["id"],
            "name": disc["name"],
            "source": disc["source"],
            "symptom": disc["symptom"],
            "evidence": disc["evidence"],
            "rule": disc["rule"],
            "trigger": disc["trigger"],
        })
        stats["count"] += 1
        stats["ids"].append(disc["id"])
    return rules, stats


def _mcp_tool_dist(mcp):
    """MCP 工具调用分布 (蒸馏上下文: 元认知工具使用情况)。"""
    dist = {}
    for r in mcp:
        t = r.get("tool", "?")
        dist[t] = dist.get(t, 0) + 1
    return dict(sorted(dist.items(), key=lambda kv: -kv[1])[:10])


# ---------------------------------------------------------------- D5 置信度校准 (Sprint 33, PM 裁决 P1)
# 基于 M2 四通道信号 (Q 值强度 + branch_hist 熵响应) 对 D1/D2 蒸馏规则重新排序:
#   - |Q| 越大 -> 行为影响越确定 -> 该记录的蒸馏规则置信度越高
#   - branch_hist 熵响应 (|Δ熵|) 越大 -> 拓扑级行为变化越显著 -> 加分
#   - winrate 饱和 (score==1.0) 时步骤/熵成为唯一次级信号 -> 校准降级 (S20 失敏)
# 输出: 每条 D1/D2 规则附带 confidence, 并按 confidence 降序重排 (精炼规则库)。
def recalibrate_rules(dg):
    """D5 校准: 用 M2 四通道信号对 D1/D2 规则置信度校准并降序重排。

    每条规则自带 quality/reason_raw (distill_d1/d2 生成时附带), 无需再匹配记录。
    同 variant 多条记录 (重复 id) 按 (quality, 熵响应) 聚合成单条, 取最强信号。
    返回 {"d1": 重排规则, "d2": 重排规则, "stats": 校准统计}。
    """
    d1, s1 = distill_d1(dg)
    d2, s2 = distill_d2(dg)

    def entropy_delta(reason_raw):
        m = re.search(r"Δ=([+-][\d.]+)", reason_raw or "")
        return abs(float(m.group(1))) if m else 0.0

    def score(rule, saturated):
        q = rule.get("quality")
        q = float(q) if q is not None else 0.0
        aq = abs(q)
        ae = entropy_delta(rule.get("reason_raw"))
        base = min(1.0, aq * 10 + ae * 20)
        if saturated:
            base *= 0.6
        return round(max(0.05, min(1.0, base)), 3)

    def aggregate(rules):
        """按 id 聚合: 重复 id 取置信度最高者, 标记重复数。"""
        best = {}
        for r in rules:
            q = r.get("quality")
            sat = q is not None and abs(float(q)) < 0.02  # 中性 Q + SUSPICIOUS = 失敏
            conf = score(r, sat)
            if r["id"] not in best or conf > best[r["id"]]["confidence"]:
                best[r["id"]] = dict(r, confidence=conf,
                                     signal_components={
                                         "abs_q": round(abs(float(q)) if q is not None else 0, 3),
                                         "abs_entropy_delta": round(entropy_delta(r.get("reason_raw")), 3)})
        return sorted(best.values(), key=lambda r: -r["confidence"])

    d1 = aggregate(d1)
    d2 = aggregate(d2)
    stats = {
        "d1_total_rules": len(d1),
        "d2_total_rules": len(d2),
        "d1_high_conf": sum(1 for r in d1 if r["confidence"] >= 0.5),
        "d2_high_conf": sum(1 for r in d2 if r["confidence"] >= 0.5),
        "d1_top": [{"id": r["id"], "conf": r["confidence"], "layer": r["layer"]} for r in d1[:5]],
        "d2_top": [{"id": r["id"], "conf": r["confidence"], "layer": r["layer"]} for r in d2[:5]],
    }
    return {"d1": d1, "d2": d2}, {"d1": s1, "d2": s2, "calibration": stats}


def write_rules(rules, out_dir, ts=None):
    """版本化输出: experience/distill_rules_<ts>.json (含 meta + rules + stats)。"""
    os.makedirs(out_dir, exist_ok=True)
    ts = ts or datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"distill_rules_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)
    return path


def run(decisions_path=None, mcp_path=None, out_dir=None, since=None, recalibrate=False):
    """主流程: 读 -> 过滤 -> 蒸馏 (可选 D5 校准) -> 版本化输出。返回摘要 dict。"""
    decisions_path = decisions_path or DEFAULT_DECISIONS
    mcp_path = mcp_path or DEFAULT_MCP
    out_dir = out_dir or DEFAULT_OUT

    recs = load_jsonl(decisions_path)
    if since:
        recs = [r for r in recs if r.get("ts", "") >= since]
    dg = filter_diff_gate(recs)

    mcp = load_jsonl(mcp_path) if os.path.exists(mcp_path) else []
    if since:
        mcp = [r for r in mcp if r.get("ts", "") >= since]

    d1, s1 = distill_d1(dg)
    d2, s2 = distill_d2(dg)
    s3 = distill_d3(dg, mcp)
    d4, s4 = distill_d4()

    # Sprint 33 P1: D5 置信度校准 (PM 指令 --recalibrate) — 基于 M2 四通道信号重排
    cal = None
    if recalibrate:
        cal_out, cal_stats = recalibrate_rules(dg)
        d1 = cal_out["d1"]
        d2 = cal_out["d2"]
        cal = cal_stats
        s1.update(cal["d1"])
        s2.update(cal["d2"])

    rules = {
        "meta": {
            "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "since": since or "all",
            "decisions": decisions_path,
            "mcp": mcp_path,
            "sprint": "S33-M1 (候选 G 后自蒸馏迭代, D5 置信度校准)",
            "anti_collapse": "structured verdict distillation (no LLM free text)",
            "recalibrated": bool(recalibrate),
        },
        "d1_desensitization": d1,
        "d2_perturbation_prior": d2,
        "d3_diversity": s3,
        "d4_governance_discoveries": d4,
        "stats": {"d1": s1, "d2": s2, "d3": s3, "d4": s4, "d5_calibration": cal},
    }
    out = write_rules(rules, out_dir)
    summary = {
        "diff_gate_total": len(dg),
        "suspicious": s1["count"],
        "inconclusive": s2["count"],
        "saturated_suspicious": s1["saturated"],
        "governance_discoveries": s4["ids"],
        "rules_file": out,
        "d3": s3,
        "d5": cal,
    }
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="Sprint 21 P2 自蒸馏数据管道 (M1), S33 扩展 D5 校准")
    ap.add_argument("--decisions", default=DEFAULT_DECISIONS)
    ap.add_argument("--mcp", default=DEFAULT_MCP)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--since", default=None, help="ts 前缀过滤 (如 20260808)")
    ap.add_argument("--recalibrate", action="store_true",
                    help="S33 P1: 用 M2 四通道信号对 D1/D2 规则置信度校准并降序重排")
    a = ap.parse_args(argv)
    s = run(a.decisions, a.mcp, a.out, a.since, a.recalibrate)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
