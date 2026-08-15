"""RES-AGENT: research orchestrator — S.A.M.U.E.L. 可执行主循环.

Survey → Assess → Map → Utilize → Evaluate → Learn
每个 phase 调用对应模块, 产出经 research_gate 验证后才进入下一 phase.
所有产出版本化存储于 governance/research/outputs/.

当前实现 phase: survey (paper_retriever) + gate 验证; 其余 phase 提供
可扩展接口 (TODO 标记), 遵循"最小可执行闭环优先"原则.

Run: python3 governance/research/research_orchestrator.py --task "VLA tactile" --max 5
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paper_retriever import fetch_arxiv, save as save_papers
from research_gate import evaluate_artifact

OUTPUTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")


def phase_survey(query: str, max_results: int) -> str:
    """S: Survey — 检索文献, 产出 papers list, 过 R-gate papers 判据."""
    print(f"[orchestrator] S.Survey: query='{query}'")
    papers = fetch_arxiv(query, max_results)
    out = os.path.join(OUTPUTS, "research_papers_list.json")
    save_papers(papers, out)
    rep = evaluate_artifact("papers", out)
    print(f"[orchestrator] gate: papers passed={rep['passed']} "
          f"({rep['n_pass']}/{rep['n_total']})")
    if not rep["passed"]:
        raise RuntimeError("survey gate FAILED — abort pipeline")
    return out


def phase_survey_notion(urls_path: str = None) -> str:
    """S: Survey (R1 variant) — Notion 页面输入.

    输入可以是: (a) 已编译的结构化 JSON (inputs/r1_notion_pages.json,
    推荐 — 页面为 CSR 墙, 编译脚本处理); (b) 原始 URL 列表 (将尝试抓取,
    失败则报出并建议用户摘要回退).
    产出统一 papers-list schema (pages 视为"文献"), 过 R-gate papers 判据.
    """
    if urls_path and urls_path.endswith(".json"):
        src = urls_path
    else:
        # raw urls: try compile path
        default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "inputs/r1_notion_pages.json")
        src = default if os.path.exists(default) else None
    if not src or not os.path.exists(src):
        raise RuntimeError("notion input not found — compile r1_notion_pages.json "
                           "first (governance/research/compile_r1_input.py)")
    with open(src, "r", encoding="utf-8") as f:
        payload = json.load(f)
    # normalize to papers-list schema for the gate
    papers = []
    for p in payload.get("pages", []):
        papers.append({
            "id": p["id"],
            "title": p["title"],
            "summary": p["summary"],
            "published": "notion-public-page",
            "authors": ["notion-author"],
            "type": p.get("type", "document"),
            "extractable_assets": p.get("extractable_assets", []),
            "key_structures": p.get("key_structures", []),
        })
    out = os.path.join(OUTPUTS, "research_papers_list.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({
            "papers": papers,
            "source": "notion-r1",
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "count": len(papers),
        }, f, ensure_ascii=False, indent=2)
    rep = evaluate_artifact("papers", out)
    print(f"[orchestrator] S.Survey(notion): {len(papers)} pages, "
          f"gate passed={rep['passed']} ({rep['n_pass']}/{rep['n_total']})")
    if not rep["passed"]:
        raise RuntimeError("survey(notion) gate FAILED — abort pipeline")
    return out


def phase_assess(papers_path: str, report_path: str = None) -> str:
    """A: Assess — 深度阅读批判 (五问批判), 提取每篇论文的假设/局限.

    最小实现: 检查 agent 产出的 assess 报告 (s61_assess_report.md 或
    critical_notes_*.md) 是否存在并通过 R-gate "patterns" 判据.
    """
    print("[orchestrator] A.Assess: critical reading (agent-driven)")
    notes_dir = os.path.join(OUTPUTS, "critical_notes")
    os.makedirs(notes_dir, exist_ok=True)
    if report_path and os.path.exists(report_path):
        rep = evaluate_artifact("patterns", report_path)
        print(f"[orchestrator] gate: assess report passed={rep['passed']} "
              f"({rep['n_pass']}/{rep['n_total']})")
        if not rep["passed"]:
            raise RuntimeError("assess gate FAILED — abort pipeline")
    else:
        print("[orchestrator]   (no assess report provided — agent to write)")
    return notes_dir


def phase_map(papers_path: str) -> str:
    """M: Map — 模式提取: 从论文集中提取失败模式/能力边界."""
    with open(papers_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    patterns = []
    for p in payload.get("papers", []):
        # 从摘要提取候选模式关键词 (最小启发式; agent 深度阅读后人工增补)
        text = (p.get("title", "") + " " + p.get("summary", "")).lower()
        if any(k in text for k in ("fail", "limit", "challenge", "bottleneck",
                                   "struggle", "degrade")):
            patterns.append({
                "pattern": f"failure-signal in '{p['title'][:80]}'",
                "evidence": p["id"],
                "source_snippet": p.get("summary", "")[:200],
            })
    out = os.path.join(OUTPUTS, "research_patterns.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"patterns": patterns, "source": papers_path}, f, indent=2,
                  ensure_ascii=False)
    print(f"[orchestrator] M.Map: extracted {len(patterns)} candidate patterns")
    return out


def phase_utilize(artifact_path: str, report_path: str = None) -> str:
    """U: Utilize — 将 map 洞见落地为代码变更 (agent-driven).

    检查 agent 实施的代码变更关联报告 (s61_utilize_report.md) 存在且
    包含 "code-changes" 记录; orchestrator 不直接改代码 — 变更由 agent
    在仓库中执行 (test-driven).
    """
    print("[orchestrator] U.Utilize: code change implementation (agent-driven)")
    if report_path and os.path.exists(report_path):
        rep = evaluate_artifact("experiment", report_path)
        print(f"[orchestrator] gate: utilize report passed={rep['passed']} "
              f"({rep['n_pass']}/{rep['n_total']})")
        if not rep["passed"]:
            raise RuntimeError("utilize gate FAILED — abort pipeline")
    else:
        print("[orchestrator]   (no utilize report provided — agent to write)")
    return report_path or artifact_path


def phase_evaluate(utilize_out: str, report_path: str = None) -> str:
    """E: Evaluate — 门回归 + 性能基准 (agent-driven, 复用 v9_gate)."""
    print("[orchestrator] E.Evaluate: gate regression (agent-driven)")
    if report_path and os.path.exists(report_path):
        rep = evaluate_artifact("evidence", report_path)
        print(f"[orchestrator] gate: evaluate report passed={rep['passed']} "
              f"({rep['n_pass']}/{rep['n_total']})")
        if not rep["passed"]:
            raise RuntimeError("evaluate gate FAILED — abort pipeline")
    else:
        print("[orchestrator]   (no evaluate report provided — agent to write)")
    return report_path or utilize_out


def phase_learn(prev_out: str, report_path: str = None) -> str:
    """L: Learn — 经验固化 (engineering_rules + pattern_library 更新)."""
    print("[orchestrator] L.Learn: knowledge consolidation (agent-driven)")
    if report_path and os.path.exists(report_path):
        rep = evaluate_artifact("synthesis", report_path)
        print(f"[orchestrator] gate: learn report passed={rep['passed']} "
              f"({rep['n_pass']}/{rep['n_total']})")
        if not rep["passed"]:
            raise RuntimeError("learn gate FAILED — abort pipeline")
    else:
        print("[orchestrator]   (no learn report provided — agent to write)")
    return report_path or prev_out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="research question/task")
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--phases", default="survey,map",
                    help="comma-separated phases to run (default: survey,map)")
    ap.add_argument("--input-type", choices=["arxiv", "notion"], default="arxiv",
                    help="corpus source: arxiv (default) or notion (R1)")
    ap.add_argument("--urls", default=None, help="notion URLs or compiled json path")
    ap.add_argument("--assess-report", default=None, help="assess report md path")
    ap.add_argument("--utilize-report", default=None, help="utilize report md path")
    ap.add_argument("--evaluate-report", default=None, help="evaluate report md path")
    ap.add_argument("--learn-report", default=None, help="learn report md path")
    args = ap.parse_args()

    os.makedirs(OUTPUTS, exist_ok=True)
    print(f"[orchestrator] task='{args.task}' phases={args.phases} "
          f"input_type={args.input_type}")
    t0 = time.time()

    survey_out = None
    phase_out = None
    for ph in [p.strip() for p in args.phases.split(",")]:
        if ph == "survey":
            if args.input_type == "notion":
                survey_out = phase_survey_notion(args.urls)
            else:
                survey_out = phase_survey(args.task, args.max)
            phase_out = survey_out
        elif ph == "assess":
            phase_out = phase_assess(survey_out, args.assess_report)
        elif ph == "map":
            phase_out = phase_map(survey_out)
        elif ph == "utilize":
            phase_out = phase_utilize(phase_out, args.utilize_report)
        elif ph == "evaluate":
            phase_out = phase_evaluate(phase_out, args.evaluate_report)
        elif ph == "learn":
            phase_out = phase_learn(phase_out, args.learn_report)
        else:
            raise ValueError(f"unknown phase: {ph}")

    print(f"[orchestrator] pipeline done in {time.time()-t0:.1f}s — "
          f"outputs in {OUTPUTS}/")


if __name__ == "__main__":
    main()
