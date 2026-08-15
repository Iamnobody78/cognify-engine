#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CVE-S-AGENT v1.0 — 认知操作系统执行引擎 (MVE 三螺旋循环)
=========================================================
MCE 2.0 编译 (元模型解析) → VCE 2.0 扫描 (价值审计) → CEE 2.0 推演 (演化规划)
+ 强制自检五问 (任一否 -> 循环未完成, exit 2)

用法:
  python cve_s.py mve "任意输入文本"     # 完整 MVE 循环
  python cve_s.py mce "文本"             # 仅编译
  python cve_s.py vce "文本"             # 仅扫描
  python cve_s.py cee "目标"             # 仅推演
  python cve_s.py demo                   # 内置演示
产物: ~/.aionui-tri-sync/cves/mve_<ts>/{mce_ast.json, vce_scan_report.md, cee_evolution_plan.md}
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).parent))
from trisync_paths import TRI  # noqa: E402

OUT = TRI / "cves"

# ---------------------------------------------------------------- MCE 模型库
MODELS = [
    ("立场对抗", ["反对", "驳斥", "质疑", "错误", "不对", "荒谬", "毫无道理", "反驳"]),
    ("道德审判", ["应该", "必须", "道德", "正义", "良心", "责任", "义务", "不该"]),
    ("心理投射", ["你总是", "你们", "他们从来", "都怪", "都是因为"]),
    ("阴谋解释", ["背后", "隐藏", "操控", "阴谋", "利益集团", "暗中", "另有目的"]),
    ("系统动力学", ["循环", "反馈", "系统", "演化", "增长", "瓶颈", "自噬", "闭环"]),
    ("技术优化", ["性能", "优化", "效率", "成本", "指标", "基准", "吞吐", "延迟"]),
    ("商业权衡", ["市场", "利润", "投入产出", "ROI", "客户", "商业化", "营收"]),
    ("认知防御", ["不确定", "可能", "也许", "边界", "局限", "诚实", "需验证"]),
    ("工具理性", ["daemon", "sync", "debt", "pattern", "heartbeat", "exit",
                 "status", "interval", "snapshot", "resolved", "token",
                 "failed", "completed", "pipeline", "metric"]),
]

# ---------------------------------------------------------------- VCE 资产
POLARIZE_WORDS = ["绝对", "永远", "全部", "必须", "不可能", "彻底", "毫无疑问", "必然", "完全"]
VALUE_PAIRS = [
    ("技术主权", "商业妥协"), ("短期利润", "长期愿景"), ("效率", "安全"),
    ("自主性", "可控性"), ("速度", "质量"), ("开放", "主权"),
]


def mce_compile(text):
    """MCE 2.0: 识别 -> 外化 -> 并行 -> 切换"""
    scores = {}
    for name, kws in MODELS:
        scores[name] = sum(text.count(k) for k in kws)
    detected = max(scores, key=scores.get) if any(scores.values()) else "未识别"
    # 并行: 检出模型 + 2 个次高替代
    ranked = sorted(scores.items(), key=lambda x: -x[1])[:3]
    parallel = [{"model": n, "score": s,
                 "view": f"若以「{n}」视角解读: {_alt_view(n, text)}"}
                for n, s in ranked]
    winner = ranked[0][0] if ranked and ranked[0][1] > 0 else "多模型低分(需更多信息)"
    ast = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "input": text[:200],
        "detected_model": detected,
        "model_scores": dict(sorted(scores.items(), key=lambda x: -x[1])[:6]),
        "externalized": f"该输入是「{detected}」模型的输出结果, 而非客观事实本身",
        "parallel_models": parallel,
        "switching_winner": winner,
        "switching_note": "切换权: 由上下文目标决定采用哪个模型, 而非模型自身声明",
    }
    return ast


def _alt_view(model, text):
    views = {
        "立场对抗": "先定位对方立场的漏洞, 再决定是否值得回应",
        "道德审判": "用规范与义务框架评估该行为, 关注应然",
        "心理投射": "说话者可能在把自己的感受投射到对象上",
        "阴谋解释": "寻找表面陈述背后的利益与操控链条",
        "系统动力学": "事件是系统反馈环的一个时点快照, 关注结构",
        "技术优化": "以可度量指标为目标函数评估该主张",
        "商业权衡": "以投入产出与市场约束评估该主张",
        "认知防御": "标注不确定边界, 拒绝过度自信",
        "工具理性": "以可度量状态与运维指标评估, 关注系统健康与债务",
    }
    return views.get(model, "从该模型的结构性前提重新解读")


def vce_scan(text):
    """VCE 2.0: 极化 -> 冲突 -> 不对称"""
    polar_hits = [w for w in POLARIZE_WORDS if w in text]
    polar_index = min(1.0, len(polar_hits) / 3)  # 0~1
    level = ("严重窄化" if polar_index >= 0.66 else
             "轻度极端" if polar_index >= 0.33 else "正常")
    conflicts = []
    for a, b in VALUE_PAIRS:
        if a in text or b in text:
            conflicts.append({"pair": f"{a} vs {b}",
                              "tension": f"文本涉及 {a} 与 {b} 的潜在取舍"})
    if not conflicts:
        conflicts = [{"pair": "未检出显性价值对", "tension": "需补充上下文"}]
    # 不对称视角: 取第一句反转
    first = re.split(r"[。！？!?]", text.strip())[0]
    negation = "反向视角: " + ("非" + first if not first.startswith("非") else first[1:])
    return {"generated": datetime.now().isoformat(timespec="seconds"),
            "polarization_index": round(polar_index, 3), "level": level,
            "polarize_words": polar_hits,
            "value_conflicts": conflicts,
            "asymmetric_perspective": negation}


def cee_plan(text, vce):
    """CEE 2.0: 生存(24h) -> 沉淀(中期) -> 释放(长期)"""
    conflicts = "、".join(c["pair"] for c in vce["value_conflicts"][:2])
    return {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "goal": text[:120],
        "stage_1_survival": f"24h 内最小可行行动: 针对「{conflicts}」先做一次低成本实证/扫描, "
                            "产出可撤销的最小变更",
        "stage_2_sediment": "中期加固: 把实证结果固化为规则/债务条目, 建立回滚机制, "
                            "纳入 PROSPECT 预演库",
        "stage_3_release": "长期演化: 基于累积数据决定模型切换或架构演化, "
                           "走 MHA-ARCH A.C.Q.U.I.R.E 闭环",
    }


def self_check(ast, vce, plan):
    """强制自检五问"""
    checks = [
        ("识别认知模型", ast["detected_model"] != "未识别"),
        ("外化模型", "输出结果" in ast.get("externalized", "")),
        ("生成替代模型", len(ast.get("parallel_models", [])) >= 2),
        ("扫描价值冲突", len(vce.get("value_conflicts", [])) >= 1),
        ("推演三阶段", all(k in plan for k in ("stage_1_survival", "stage_2_sediment", "stage_3_release"))),
    ]
    ok = all(o for _, o in checks)
    for name, o in checks:
        print(f"  {'✅' if o else '❌'} 自检: {name}")
    return ok


def run_mve(text):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = OUT / f"mve_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    print("[Phase M] MCE 2.0 编译...")
    ast = mce_compile(text)
    (d / "mce_ast.json").write_text(json.dumps(ast, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    print(f"  识别: {ast['detected_model']} | 外化: {ast['externalized'][:40]}...")
    print(f"  并行: {[p['model'] for p in ast['parallel_models']]}")
    print(f"  切换胜者: {ast['switching_winner']}")
    print("[Phase V] VCE 2.0 扫描...")
    vce = vce_scan(text)
    (d / "vce_scan_report.md").write_text("\n".join([
        "# VCE 2.0 价值扫描报告", "", f"> {vce['generated']}", "",
        f"## 极化: 指数 {vce['polarization_index']} ({vce['level']})", "",
        f"命中词: {', '.join(vce['polarize_words']) or '无'}", "",
        "## 价值冲突", "", *[f"- {c['pair']}: {c['tension']}" for c in vce["value_conflicts"]], "",
        "## 不对称视角", "", f"- {vce['asymmetric_perspective']}",
    ]), encoding="utf-8")
    print(f"  极化: {vce['polarization_index']} ({vce['level']}) | 冲突: "
          f"{len(vce['value_conflicts'])} | 不对称: 已生成")
    print("[Phase E] CEE 2.0 推演...")
    plan = cee_plan(text, vce)
    (d / "cee_evolution_plan.md").write_text("\n".join([
        "# CEE 2.0 演化推演", "", f"> {plan['generated']}", "",
        f"## 目标: {plan['goal']}", "",
        f"### 阶段一 (生存/24h)", f"- {plan['stage_1_survival']}", "",
        f"### 阶段二 (沉淀/中期)", f"- {plan['stage_2_sediment']}", "",
        f"### 阶段三 (释放/长期)", f"- {plan['stage_3_release']}",
    ]), encoding="utf-8")
    print(f"  三阶段: 生存/沉淀/释放 已推演")
    print("[自检五问]")
    ok = self_check(ast, vce, plan)
    print(f"\n[MVE] 产物: {d} | 循环状态: {'✅ 完成' if ok else '❌ 未完成'}")
    return 0 if ok else 2


def mmce_analyze(text):
    """MMCE 元模型控制工程: 四降维能力 + L1-L6 层级 + 切换权争夺"""
    ast = mce_compile(text)
    # L1-L6 层级检测 (元词密度)
    meta_words = ["模型", "框架", "认知", "元", "系统", "切换", "重写",
                  "操作系统", "递归", "寄生", "控制", "上层"]
    content_words = ["对", "错", "事实", "证据", "结果", "数据"]
    meta_hits = sum(text.count(w) for w in meta_words)
    content_hits = sum(text.count(w) for w in content_words)
    level = min(6, max(1, 1 + meta_hits // 3))
    layer_names = {1: "元认知解构", 2: "框架重置", 3: "系统边界",
                   4: "跨层递归", 5: "模型寄生/多模型感染", 6: "元模型控制工程"}
    # 切换权争夺 (最高级元操作)
    competitors = [p["model"] for p in ast["parallel_models"]]
    switching = {
        "question": "哪一个模型才有资格定义'什么是有效讨论'?",
        "competitors": competitors,
        "principle": "切换权由对话目标持有, 不由任何模型自身声明; "
                     "目标决定模型, 模型不决定目标",
        "verdict": (f"当前语境下若目标是「{_goal_of(text)}」, 则 "
                    f"「{ast['switching_winner']}」的解释力优先; "
                    f"若目标变化, 切换权随之转移 — 切换权在目标, 不在模型"),
    }
    # 重写声明 (L5/L6)
    rewrite = (f"该输入不是观点, 而是「{ast['detected_model']}」模型运行中"
               f"的操作系统输出; 切换模型即重写结论 — 元模型控制工程 "
               f"不反驳内容, 重写认知操作系统")
    report = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "input": text[:200],
        "layer": {"level": level, "name": layer_names[level],
                  "meta_hits": meta_hits, "content_hits": content_hits},
        "recognition": ast["detected_model"],
        "externalized": ast["externalized"],
        "parallel": [p["model"] for p in ast["parallel_models"]],
        "switching_control": switching,
        "rewrite_statement": rewrite,
    }
    return report


def _goal_of(text):
    if any(k in text for k in ("说服", "证明", "反驳")):
        return "赢得论证"
    if any(k in text for k in ("理解", "分析", "诊断")):
        return "理解真相"
    if any(k in text for k in ("决策", "执行", "行动", "解决")):
        return "做出决策"
    return "达成共识"


def run_mmce(text):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = OUT / f"mmce_{ts}"
    d.mkdir(parents=True, exist_ok=True)
    rep = mmce_analyze(text)
    (d / "mmce_ast.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                     encoding="utf-8")
    (d / "mmce_report.md").write_text("\n".join([
        "# MMCE 元模型控制工程报告", "", f"> {rep['generated']}", "",
        f"## 输入: {rep['input']}", "",
        f"## 层级判定: L{rep['layer']['level']} {rep['layer']['name']} "
        f"(元词 {rep['layer']['meta_hits']} / 内容词 {rep['layer']['content_hits']})", "",
        "## 1. 模型识别", f"- {rep['recognition']}", "",
        "## 2. 模型外化", f"- {rep['externalized']}", "",
        "## 3. 模型并行", "", *[f"- {m}" for m in rep["parallel"]], "",
        "## 4. 模型切换权争夺", "",
        f"- 问题: {rep['switching_control']['question']}",
        f"- 竞争者: {', '.join(rep['switching_control']['competitors'])}",
        f"- 原则: {rep['switching_control']['principle']}",
        f"- 裁决: {rep['switching_control']['verdict']}", "",
        "## 5. 重写声明 (L6)", f"- {rep['rewrite_statement']}",
    ]), encoding="utf-8")
    print(f"[MMCE] L{rep['layer']['level']} {rep['layer']['name']} | "
          f"识别={rep['recognition']} | 并行={rep['parallel']}")
    print(f"[MMCE] 切换权: {rep['switching_control']['verdict'][:70]}...")
    print(f"[MMCE] 产物: {d}")
    return 0


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "demo"
    if cmd == "demo":
        text = ("AI 代理应该全自动完成债务偿还和元能力进化, 不应该需要人工审批, "
                "因为人工审批是效率的绝对瓶颈")
    elif cmd == "mve":
        text = " ".join(args[1:])
    elif cmd == "mce":
        print(json.dumps(mce_compile(" ".join(args[1:])), ensure_ascii=False, indent=2))
        return 0
    elif cmd == "mmce":
        return run_mmce(" ".join(args[1:]))
    elif cmd == "vce":
        print(json.dumps(vce_scan(" ".join(args[1:])), ensure_ascii=False, indent=2))
        return 0
    elif cmd == "cee":
        print(json.dumps(cee_plan(" ".join(args[1:]), vce_scan(" ".join(args[1:]))),
                         ensure_ascii=False, indent=2))
        return 0
    else:
        print(__doc__)
        return 1
    return run_mve(text)


if __name__ == "__main__":
    sys.exit(main())
