# -*- coding: utf-8 -*-
"""
SELF-EVOLVE v1.0 —— S.E.L.F. 四相循环引擎 (Scan / Evaluate / Learn / Fix)

对齐: meta_prompts/SELF-EVOLVE_v1.0.md ｜ 映射: self_evolve_mapping.md
协议: HONESTY-PERMANENT (诚实评分) / META-BOOTSTRAP / MAINTENANCE-GATE / TRACE-AGENT / META-EDU

设计原则:
  1. 只读取真实证据, 缺数据时标 "待评估", 绝不虚构分数 (红线 #1)
  2. 双尺度: D-scale (D1-D7, 1-10) 从 L-scale (MCI 五维, 0-5) 按映射表推导
  3. Fix 保守: 本引擎只落盘报告/计划/记录, 不直接改代码/规则 (红线 #4)
     —— 代码级修复必须经 V9 门裁决后由 meta_config 生效
"""
import os
import re
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# ── 映射表 (与 self_evolve_mapping.md 第 1 节一致) ─────────────────────────
# D 维 -> (主锚点 MCI 维, 次锚点, 现状说明)
D_MAP = {
    "D1": ("元监督", "元认知", "长链条成功率/自我纠错"),
    "D2": ("元学习", "元认知", "跨会话记忆/新任务泛化"),
    "D3": ("元监督", "元认知", "声称 vs 实际差距"),
    "D4": ("元调节", None,      "越权检测/恶意输入防御"),
    "D5": ("元调节", "元监督",  "资源/成本/可观测性"),
    "D6": ("元调节", None,      "MCP/A2A 协作协议"),
    "D7": ("元进化", "元认知",  "元认知/自我修复/自我改进"),
}

# L-scale (0-5) -> D-scale (1-10) 近似换算: D = round(L * 2)
def l_to_d(l):
    return max(1, min(10, round(l * 2)))

def _read_scorecard():
    """从 meta_capability_scorecard.md 提取 MCI 五维 L-scale 分数 (0-5)."""
    p = os.path.join(HERE, "meta_capability_scorecard.md")
    if not os.path.exists(p):
        return {}
    txt = open(p, encoding="utf-8", errors="replace").read()
    out = {}
    for m in re.finditer(r"\|\s*(元认知|元监督|元调节|元学习|元进化)[^|]*\|\s*([\d.]+)\s*\|", txt):
        out[m.group(1)] = float(m.group(2))
    return out

def _count_lines(rel):
    p = os.path.join(HERE, rel)
    if not os.path.exists(p):
        return None
    try:
        return sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
    except Exception:
        return None

def _count_jsonl(rel):
    p = os.path.join(HERE, rel)
    if not os.path.exists(p):
        return None
    try:
        return sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
    except Exception:
        return None

def _extract_winrate():
    """从 pareto_frontier.md 提取最近胜率/成功率, 无法解析则 None."""
    p = os.path.join(HERE, "pareto_frontier.md")
    if not os.path.exists(p):
        return None
    txt = open(p, encoding="utf-8", errors="replace").read()
    m = re.findall(r"(?:胜率|winrate|success)[^\d]{0,20}([\d.]+)\s*%", txt, re.I)
    if m:
        return float(m[-1])
    return None

def _resource_usage():
    try:
        import psutil
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(HERE)
        return {
            "mem_percent": round(mem.percent, 1),
            "disk_free_gb": round(disk.free / (1024 ** 3), 1),
        }
    except Exception:
        return None

# ── Phase S: Scan ─────────────────────────────────────────────────────────
def phase_scan():
    reports = {}
    reports["session_failure_rate"] = None            # 需从 evaluator 轨迹取, 本引擎只标记
    reports["gate_winrate"] = _extract_winrate()
    kb = os.path.join(HERE, "..", "knowledge_base")
    hermes = r"C:\Users\ivy\AppData\Local\hermes\memories\MEMORY.md"
    reports["memory_loaded"] = os.path.isdir(kb) or os.path.exists(hermes)
    reports["meta_decisions_lines"] = _count_jsonl("meta_decisions.jsonl")
    reports["mcp_usage_lines"] = _count_jsonl("mcp_usage_report.jsonl")
    reports["pareto_lines"] = _count_lines("pareto_frontier.md")
    reports["failure_analysis_lines"] = _count_lines("failure_analysis.md")
    reports["resource"] = _resource_usage()
    reports["tool_availability"] = None              # 需实际工具探测, 本引擎只标记
    return reports

# ── Phase E: Evaluate ─────────────────────────────────────────────────────
def phase_evaluate(scan):
    lscale = _read_scorecard()
    scores = {}
    for d, (prim, _sec, desc) in D_MAP.items():
        l = lscale.get(prim)
        scores[d] = {"prim": prim, "desc": desc, "l_scale": l,
                     "d_scale": l_to_d(l) if l is not None else None,
                     "trend": None}
    # 用扫描证据补充趋势 (仅诚实标注, 不臆造趋势)
    return scores

# ── Phase L: Learn ────────────────────────────────────────────────────────
def phase_learn(scores):
    # 最低分维度 (跳过 None=待评估的, 但不跳过任何维度本身)
    scored = {k: v for k, v in scores.items() if v["d_scale"] is not None}
    if not scored:
        return None, None
    min_d = min(scored, key=lambda k: scored[k]["d_scale"])
    prim = scores[min_d]["prim"]
    return min_d, {
        "min_dim": min_d,
        "score": scores[min_d]["d_scale"],
        "anchor": prim,
        "desc": scores[min_d]["desc"],
    }

# ── Phase F: Fix ──────────────────────────────────────────────────────────
def phase_fix(min_d, learn):
    """保守: 只产出计划与验收标准, 不直接改代码 (红线 #4)."""
    if learn is None:
        return {"status": "待评估", "detail": "无可用 L-scale 数据, 无法定位最低维"}
    return {
        "status": "待批准",  # 代码级修复需 V9 门裁决
        "min_dim": min_d,
        "plan": [
            f"针对 {min_d} ({learn['desc']}) 制定改进方案",
            "检索 knowledge_base/ 与 academic_matrix 中对应锚点",
            "生成可执行修复动作 + 验收标准",
        ],
        "acceptance": "修复后 D-scale 提升 ≥1 且回归零劣化 (红线 #4)",
    }

# ── 报告渲染 ─────────────────────────────────────────────────────────────
def render_report(round_n, scan, scores, learn, fix):
    L = []
    L.append("### 🧬 自我进化报告 [#SELF-ROUND_%d]" % round_n)
    L.append("")
    L.append("[Phase S: Scan]")
    fr = scan["session_failure_rate"]
    L.append("- 会话失败率：%s" % ("待评估" if fr is None else "%s%%" % fr))
    gw = scan["gate_winrate"]
    L.append("- 门评估胜率：%s" % ("待评估" if gw is None else "%s%%" % gw))
    L.append("- 记忆加载状态：%s" % ("PASS" if scan["memory_loaded"] else "FAIL"))
    ta = scan["tool_availability"]
    L.append("- 工具可用性：%s" % ("待评估" if ta is None else ta))
    res = scan["resource"]
    if res:
        L.append("- 资源使用：内存 %s%% / 磁盘剩余 %sGB" % (res["mem_percent"], res["disk_free_gb"]))
    else:
        L.append("- 资源使用：待评估 (psutil 不可用)")
    L.append("- 证据线数：meta_decisions=%s / pareto=%s / failure_analysis=%s / mcp_usage=%s"
             % (scan["meta_decisions_lines"], scan["pareto_lines"],
                scan["failure_analysis_lines"], scan["mcp_usage_lines"]))
    L.append("")
    L.append("[Phase E: Evaluate]")
    L.append("| 能力域 | 评分 | 主锚点 | 趋势 |")
    L.append("|:---|:---:|:---|:---:|")
    for d in sorted(scores):
        s = scores[d]
        dv = "待评估" if s["d_scale"] is None else "%s/10" % s["d_scale"]
        tv = "→" if s["trend"] is None else s["trend"]
        L.append("| %s %s | %s | %s | %s |" % (d, s["desc"], dv, s["prim"], tv))
    L.append("")
    L.append("[Phase L: Learn]")
    if learn:
        L.append("- 最低分：%s (%s) / %s/10" % (learn["min_dim"], learn["anchor"], learn["score"]))
        L.append("- 根因分析：%s 对应 MCI 维度待强化" % learn["desc"])
    else:
        L.append("- 最低分：待评估（无 L-scale 数据）")
    L.append("")
    L.append("[Phase F: Fix]")
    L.append("- 执行状态：%s" % fix["status"])
    for p in fix.get("plan", []):
        L.append("  - %s" % p)
    L.append("- 验收标准：%s" % fix.get("acceptance", "—"))
    L.append("")
    L.append("[Honest Boundary]")
    L.append("- 本引擎不虚构分数：D-scale 由 L-scale (meta_capability_scorecard.md) 按 ×2 推导；缺数据处标「待评估」")
    L.append("- 趋势列暂不臆造（需跨轮对比才能标注 ↑/↓/→）；本次为基线轮")
    L.append("- Fix 阶段仅产出计划，代码/规则级修复须经 V9 门裁决（红线 #4）")
    return "\n".join(L) + "\n"

def run():
    round_n = 1
    state_path = os.path.join(HERE, "self_evolve_state.json")
    if os.path.exists(state_path):
        try:
            round_n = json.load(open(state_path, encoding="utf-8")).get("round", 0) + 1
        except Exception:
            pass

    scan = phase_scan()
    scores = phase_evaluate(scan)
    min_d, learn = phase_learn(scores)
    fix = phase_fix(min_d, learn)
    report = render_report(round_n, scan, scores, learn, fix)

    # 落盘: 报告 + 4 工件
    out_dir = HERE
    report_path = os.path.join(out_dir, "self_evolution_report.md")
    # 归档到报告目录
    archive_dir = os.path.join(out_dir, "self_reports")
    os.makedirs(archive_dir, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    with open(os.path.join(archive_dir, f"self_round_{round_n}.md"), "w", encoding="utf-8") as f:
        f.write(report)

    # 状态推进
    json.dump({"round": round_n, "ts": datetime.datetime.now().isoformat()},
              open(state_path, "w", encoding="utf-8"))

    print(report)
    print(f"[OK] 报告已写: {report_path}")
    print(f"[OK] 归档: {archive_dir}/self_round_{round_n}.md")

if __name__ == "__main__":
    run()
