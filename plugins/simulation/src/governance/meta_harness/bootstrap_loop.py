# -*- coding: utf-8 -*-
"""
bootstrap_loop.py —— 数据驱动自举循环 (D7 自我进化闭环)

对齐: SELF-EVOLVE D7 / meta_bootstrap (A.S.C.E.N.D.) / meta_evol 三缺口
  缺口 1: 架构演进决策未形式化 (无 ROADMAP.md)  -> formalize_decision()
  缺口 2: 自举循环 (用自身输出改进自身) 未落地    -> run() 闭环
  缺口 3: 开放式改进未与变体生成联动            -> 待接 (记录在 DEC)

闭环: scan_rules -> scan_scorecard -> select_target -> allocate_rule_id -> formalize_decision
设计原则:
  1. 数据驱动: 分数/差距/规则 ID 全部从磁盘真实文件解析, 不硬编码
  2. 自指: 本循环修复"自举循环未落地"这一缺口本身 (bootstrap the bootstrap)
  3. 诚实: ID 冲突如实报告, 不做无证据的分数修改
"""
import os
import re
import json
import sys
import time

# Windows 控制台默认 cp950, emoji 会触发 UnicodeEncodeError; 统一 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DATE = time.strftime("%Y-%m-%d")
TS = time.strftime("%Y%m%d_%H%M%S")


def _p(name):
    return os.path.join(HERE, name)


# ── scan_rules: 扫描 RULE-MC 编号, 检测冲突 ────────────────────────────────
def scan_rules():
    txt = ""
    try:
        with open(_p("meta_engineering_rules.md"), encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        pass
    # 只匹配表格行首列 (| RULE-MC-NNN |), 避免描述文字里的 "原 RULE-MC-011" 误判
    ids = re.findall(r"^\|\s*RULE-MC-(\d+)\s*\|", txt, re.M)
    counts = {}
    for i in ids:
        n = int(i)
        counts[n] = counts.get(n, 0) + 1
    collisions = {n: c for n, c in counts.items() if c > 1}
    max_n = max(counts.keys()) if counts else 0
    return {"counts": counts, "collisions": collisions, "max_n": max_n}


# ── scan_scorecard: 解析五维分数 (动态) ────────────────────────────────────
DIM_NAMES = ["元认知", "元监督", "元调节", "元学习", "元进化"]
DIM_EN = {
    "元认知": "Meta-Cognition",
    "元监督": "Meta-Supervision",
    "元调节": "Meta-Regulation",
    "元学习": "Meta-Learning",
    "元进化": "Meta-Evolution",
}


def _dim_en(dim):
    return DIM_EN.get(dim, dim)


def scan_scorecard():
    txt = ""
    try:
        with open(_p("meta_capability_scorecard.md"), encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        return {}
    out = {}
    for m in re.finditer(r"\|\s*(元认知|元监督|元调节|元学习|元进化)\s*\([^)]*\)\s*\|\s*([\d.]+)\s*\|", txt):
        out[m.group(1)] = float(m.group(2))
    return out


def _gaps_for(txt, dim):
    """提取维度 detail 段里 '**差距' 之后的 '- ' 行."""
    # 定位 "### {dim}" 段
    m = re.search(r"###\s*%s\s*\([^)]*\).*?\n(.*?)(?=\n###\s|\n##\s|$)" % re.escape(dim), txt, re.S)
    if not m:
        return []
    seg = m.group(1)
    # 差距段
    g = re.search(r"\*\*差距[^*]*\*\*:\s*\n(.*)", seg, re.S)
    if not g:
        return []
    lines = [ln.strip("- ").strip() for ln in g.group(1).splitlines()]
    return [ln for ln in lines if ln]


# ── select_target: 数据驱动选择最低分维度 + 差距 ────────────────────────────
def select_target(scorecard):
    txt = ""
    try:
        with open(_p("meta_capability_scorecard.md"), encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except OSError:
        pass
    if not scorecard:
        return None
    min_dim = min(scorecard, key=lambda d: scorecard[d])
    gaps = _gaps_for(txt, min_dim)
    return {"dim": min_dim, "score": scorecard[min_dim], "gaps": gaps}


# ── allocate_rule_id: max+1, 冲突安全 ──────────────────────────────────────
def allocate_rule_id(scan):
    return "RULE-MC-%03d" % (scan["max_n"] + 1)


# ── formalize_decision: 架构演进决策 -> ROADMAP.md ─────────────────────────
def _next_dec_id():
    p = _p("ROADMAP.md")
    if not os.path.exists(p):
        return 1
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
        # 只解析末尾序列号 DEC-YYYYMMDD-NNN, 避免把日期 20260813 误当序号
        ids = [int(x) for x in re.findall(r"DEC-\d{8}-(\d{3})", txt)]
        return max(ids) + 1 if ids else 1
    except OSError:
        return 1


def formalize_decision(dec):
    p = _p("ROADMAP.md")
    dec_id = "DEC-%s-%03d" % (DATE.replace("-", ""), _next_dec_id())
    header = ""
    if not os.path.exists(p):
        header = ("# ROADMAP —— 架构演进决策记录 (元进化)\n\n"
                  "> 生成: bootstrap_loop.py ｜ 性质: 架构演进决策形式化 (meta_evol 缺口 1 修复)\n"
                  "> 因果推理要求: 每个 DEC 必须回答 为何失败 / 在哪分歧 / 如何精准修复\n\n")
    else:
        header = ""
    block = ("## %s — %s\n\n" % (dec_id, dec["title"])
             + "- **决策**: %s\n" % dec["decision"]
             + "- **维度**: %s\n" % dec["dim"]
             + "- **因果推理**:\n")
    for line in dec.get("causal", []):
        block += "  - %s\n" % line
    block += "- **证据**: %s\n" % dec.get("evidence", "—")
    block += "- **验收**: %s\n" % dec.get("acceptance", "—")
    block += "\n"
    with open(p, "a", encoding="utf-8") as f:
        f.write(header + block)
    return dec_id


# ── 反退化守卫 (RULE-MC-019): 检测"伪进化"——目标与历史 DEC 相同且差距未闭合 ─────────
def _all_dec_signatures():
    """读取 ROADMAP.md 所有 DEC 的 (维度, 证据) 签名列表 (按时间正序)。

    用于检测伪进化: 若本轮 select_target 选中的目标 + 差距 与任一历史 DEC 一致,
    说明该差距此前已被形式化但从未真正闭合 —— 禁止再写一条重复 DEC。
    """
    p = _p("ROADMAP.md")
    if not os.path.exists(p):
        return []
    try:
        txt = open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return []
    blocks = re.findall(r"## (DEC-\d{8}-\d{3}) — (.+?)\n(.*?)(?=\n## DEC-|\Z)", txt, re.S)
    sigs = []
    for dec_id, title, body in blocks:
        dim_m = re.search(r"- \*\*维度\*\*:\s*(.+)", body)
        ev_m = re.search(r"- \*\*证据\*\*:\s*(.+)", body)
        sigs.append({
            "dec_id": dec_id,
            "title": title,
            "dim": dim_m.group(1).strip() if dim_m else "",
            "evidence": ev_m.group(1).strip() if ev_m else "",
        })
    return sigs


def _detect_stale(target):
    """若 target 与任一历史 DEC 是同一维度 + 同一差距 (未闭合), 返回命中 DEC 信息, 否则 None。"""
    if not target:
        return None
    gaps = [g for g in target["gaps"] if g]
    if not gaps:
        return None
    for sig in _all_dec_signatures():
        # 维度匹配: DEC 的维度里应含 target dim (如 "元认知 (Meta-Cognition)")
        if target["dim"] not in sig["dim"]:
            continue
        # 差距匹配: 本轮差距候选是否已在上轮证据里逐条出现 (全包含 = 未闭合)
        if all(g in sig["evidence"] for g in gaps):
            return sig
    return None


# ── run: 闭环 ─────────────────────────────────────────────────────────────
def run():
    out = {}
    out["rules"] = scan_rules()
    out["scorecard"] = scan_scorecard()
    out["target"] = select_target(out["scorecard"])
    out["next_rule_id"] = allocate_rule_id(out["rules"])

    # 反退化守卫: 伪进化检测 (RULE-MC-019)
    stale = _detect_stale(out["target"])
    if stale:
        return _stale_report(out, stale)

    # 决策: 数据驱动 —— 由 select_target 选中的最低分维度生成 (非硬编码)
    t = out["target"]
    if t:
        gaps_txt = "; ".join(t["gaps"]) if t["gaps"] else "无明确差距(需进一步探查)"
        dim_label = "%s (%s)" % (t["dim"], _dim_en(t["dim"]))
        dec = {
            "title": "数据驱动目标: %s 最低分 %.1f/5" % (t["dim"], t["score"]),
            "decision": "针对 %s (scorecard 最低分 %.1f/5), 将差距候选固化为下一轮可执行规则 %s" % (
                dim_label, t["score"], out["next_rule_id"]),
            "dim": dim_label,
            "causal": [
                "为何失败: %s 得分最低 (%.1f/5), 是当前 5 维元能力中最薄弱环节" % (t["dim"], t["score"]),
                "在哪分歧: 自举闭环(scan/select/allocate/formalize)已能定位最低分, 但定位结果尚未转化为实际的规则/能力修复动作",
                "如何修复: 将 select_target 输出的差距候选 (%s) 转成 %s, 在下一轮 loop 中闭合" % (gaps_txt, out["next_rule_id"]),
            ],
            "evidence": "scorecard=%s; 差距候选=%s" % (json.dumps(out["scorecard"], ensure_ascii=False), gaps_txt),
            "acceptance": "下一轮 scan_scorecard 中 %s 分数提升 (需证据, 无证据不改分)" % t["dim"],
        }
    else:
        dec = {
            "title": "自举循环落地 (无可用分数)",
            "decision": "scan_scorecard 未解析到分数, 仅建立闭环机制 + 形式化决策",
            "dim": "元进化 (Meta-Evolution)",
            "causal": [
                "为何失败: scorecard 未解析到任何分数, 无法数据驱动定位目标",
                "在哪分歧: scan_scorecard 正则未匹配到分数行",
                "如何修复: 检查 meta_capability_scorecard.md 的表格格式与 scan_scorecard 正则",
            ],
            "evidence": "scorecard=%s" % json.dumps(out["scorecard"], ensure_ascii=False),
            "acceptance": "下一轮 scan_scorecard 能解析出 5 维分数",
        }
    out["dec_id"] = formalize_decision(dec)

    # 更新改进目标 (数据驱动)
    t = out["target"]
    if t:
        with open(_p("meta_improvement_target.md"), "w", encoding="utf-8") as f:
            f.write("# 元能力改进目标 (META-IMPROVEMENT TARGET)\n\n"
                    "> 生成: %s (%s) | 来源: bootstrap_loop.py 数据驱动\n\n"
                    "- **维度**: %s (%s/5, scorecard 最低分)\n"
                    "- **差距候选**:\n" % (DATE, TS, t["dim"], t["score"]))
            for g in t["gaps"]:
                f.write("  - %s\n" % g)
            f.write("\n- **决策**: %s\n" % out["dec_id"])

    # 决策追加
    with open(_p("meta_decisions.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": TS, "type": "bootstrap_loop", "dec_id": out["dec_id"],
            "target_dim": t["dim"] if t else None,
            "rule_collisions_found": out["rules"]["collisions"],
            "next_rule_id": out["next_rule_id"],
        }, ensure_ascii=False) + "\n")

    # 报告
    L = []
    L.append("### 🧬 自举循环报告 [BOOTSTRAP]")
    L.append("")
    L.append("[scan_rules]")
    L.append("- 现有 RULE-MC 最高编号: %d" % out["rules"]["max_n"])
    L.append("- ID 冲突: %s" % (out["rules"]["collisions"] or "无"))
    L.append("- 下一可用 ID: %s" % out["next_rule_id"])
    L.append("")
    L.append("[scan_scorecard]")
    for d in DIM_NAMES:
        s = out["scorecard"].get(d)
        L.append("- %s: %s" % (d, ("%.1f" % s) if s is not None else "待解析"))
    L.append("")
    L.append("[select_target]")
    if t:
        L.append("- 最低分: %s (%.1f/5)" % (t["dim"], t["score"]))
        L.append("- 差距:")
        for g in t["gaps"]:
            L.append("  - %s" % g)
    else:
        L.append("- 无可用分数")
    L.append("")
    L.append("[formalize_decision]")
    L.append("- 决策记录: %s -> ROADMAP.md" % out["dec_id"])
    L.append("")
    L.append("[Honest Boundary]")
    L.append("- 本循环不修改分数(无证据不改分); 只建立闭环机制 + 数据驱动决策形式化")
    L.append("- 缺口 3(变体生成联动)仍未闭合, 待下一轮接; 本 DEC 仅形式化最低分维度定位结果")
    return "\n".join(L) + "\n"


# ── 伪进化报告 (RULE-MC-019): 目标未闭合时禁止重复形式化, 转为"需实施"信号 ──────
def _stale_report(out, sig):
    t = out["target"]
    L = []
    L.append("=" * 62)
    L.append("[RULE-MC-019 反退化守卫] 检测到伪进化, 已阻止重复 DEC 形式化")
    L.append("=" * 62)
    L.append("本轮 select_target: %s (%.1f/5)" % (t["dim"], t["score"]))
    L.append("差距候选: %s" % ("; ".join(t["gaps"]) if t["gaps"] else "无"))
    L.append("")
    L.append("历史 DEC (%s) 已形式化同一目标且差距未闭合:" % sig["dec_id"])
    L.append("  维度: %s" % sig["dim"])
    L.append("  证据: %s" % sig["evidence"])
    L.append("")
    L.append("根因: run() 只做 formalize (写 DEC), 未做 implement (真正落规则) + verify (复核闭合)。")
    L.append("动作: 禁止再写重复 DEC; 必须转入实施阶段 (meta_bootstrap.evolve 或手动固化 RULE-MC)。")
    L.append("")
    L.append("[下一轮目标] 闭合差距 %s (%s) 而不是再次形式化" % (t["dim"], t["score"]))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    print(run())
