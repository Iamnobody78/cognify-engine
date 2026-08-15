# -*- coding: utf-8 -*-
"""mh_evolve — Meta-Harness 阶段 2' 驱动: LLM Proposer → 候选 → 验证 → Pareto 合并。

对照斯坦福循环 (propose → validate → score → pareto-merge):
  - propose : src/meta_harness/proposer_llm.py (LLM 读 incumbent+轨迹诊断 → 规则候选)
  - validate: src/meta_harness/adapter.py validate_candidate (fail-closed 合并加载)
  - score   : 质量=重放命中率 (有存储时) / 有效基线 0.5; 成本=规则数+LLM 输出长度
  - merge   : src/pareto/frontier.py ParetoFrontier (非支配集)

安全: 候选写入 candidates/{id}/ (gitignore), 报告落 .aionui/context/,
**不自动注入 config/policies.yaml** — 人工/仲裁裁决后注入 (与 P12 人类在环一致)。

用法: .venv-b1\\Scripts\\python.exe scripts/mh_evolve.py --rounds 2 [--db audit.db]
  --db 提供时注入 DENY/ESCALATE 轨迹诊断并做重放命中率评分 (质量真实可算)。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.meta_harness.proposer_llm import LLMProposer, MH_PROPOSER_MODEL  # noqa: E402
from src.pareto.frontier import ParetoFrontier, Point  # noqa: E402
from src.proposer.writer import CandidateWriter  # noqa: E402


def load_incumbent(policies_path: str) -> list[dict]:
    import yaml as _yaml
    p = Path(policies_path)
    if not p.exists():
        return []
    data = _yaml.safe_load(p.read_text(encoding="utf-8"))
    return data.get("rules", []) if isinstance(data, dict) else []


def collect_diagnosis(storage, limit: int = 200, top: int = 15) -> list[str]:
    """从最近决策聚合 (path, method, tool) 计数 → 诊断行。"""
    agg: dict = {}
    for rec in storage.get_recent(limit=limit):
        if rec.get("verdict") not in ("DENY", "ESCALATE"):
            continue
        key = (rec.get("method", "?"), rec.get("path", "?"),
               rec.get("tool_name") or "?")
        agg[key] = agg.get(key, 0) + 1
    return [f"x{cnt} {m} {path} tool={tool}"
            for (m, path, tool), cnt in sorted(agg.items(), key=lambda kv: -kv[1])[:top]]


def score_candidate(candidate_path: Path, storage, rule_count: int, llm_len: int) -> Point:
    """质量=重放命中率 (有存储) 或有效基线; 成本=规则数 + LLM 输出长度代理。"""
    from src.meta_harness.adapter import validate_candidate
    result = validate_candidate(str(candidate_path), "config/policies.yaml", storage)
    hit = result.get("hit_rate")
    quality = hit if (hit is not None and result.get("checked")) else (0.5 if result["valid"] else 0.0)
    cost = float(rule_count) + llm_len / 10000.0  # 输出长度作 token 成本代理
    return Point(id=candidate_path.parent.name, quality=round(quality, 4), cost=round(cost, 4))


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(prog="mh-evolve")
    parser.add_argument("--rounds", type=int, default=1)
    parser.add_argument("--db", help="审计库路径 (提供则诊断+重放评分)")
    parser.add_argument("--policies", default="config/policies.yaml")
    parser.add_argument("--out", default=".aionui/context/mh_evolve_report.md")
    parser.add_argument("--max-candidates", type=int, default=3)
    args = parser.parse_args(argv)

    incumbent = load_incumbent(args.policies)
    storage = None
    diag: list[str] = []
    if args.db:
        from src.storage import Storage
        storage = Storage(db_path=args.db)
        diag = collect_diagnosis(storage)

    proposer = LLMProposer()
    writer = CandidateWriter(".")
    frontier = ParetoFrontier()
    frontier.insert(Point(id="incumbent", quality=0.5, cost=float(len(incumbent))))
    notes: list[str] = []

    started = time.time()
    for rnd in range(1, args.rounds + 1):
        result = proposer.propose(incumbent, diag, max_candidates=args.max_candidates)
        if result["llm_error"]:
            notes.append(f"round {rnd} LLM 不可用 (fail-closed): {result['llm_error'][:200]}")
            print(f"[round {rnd}] LLM 不可达 (fail-closed): {result['llm_error'][:120]}")
            if rnd == 1 and not result["candidates"]:
                notes.append("零候选 — 无进化产出 (诚实的失败路径, 绝不编造)")
                print("[mh-evolve] 零候选 — 无进化产出 (诚实的失败路径)")
        for i, c in enumerate(result["candidates"], 1):
            cand = writer.create(
                name=f"mhllm_r{rnd}_{i}",
                parent_trace_id="",  # 无 trace 时留空; 接入 trace/store 后可填
            )
            cand_path = writer.write_source(cand, "policy.yaml", c["yaml_text"])
            writer.set_metrics(cand, {
                "source": "llm-proposer", "model": proposer.model,
                "rule_count": c["rule_count"], "reason": c["reason"],
                "round": rnd,
            })
            pt = score_candidate(cand_path, storage, c["rule_count"], len(c["yaml_text"]))
            accepted = frontier.insert(pt)
            writer.set_metrics(cand, {**cand.metrics, "pareto_accepted": accepted,
                                      "quality": pt.quality, "cost": pt.cost})
            if storage is None or pt.quality == 0.5:
                notes.append(f"候选 {cand.candidate_id}: 重放未命中/未检查, "
                             f"质量=基线 0.5 (弱信号, 不代表真实治理效果)")
            print(f"[round {rnd}] 候选 {cand.candidate_id} rules={c['rule_count']} "
                  f"q={pt.quality} cost={pt.cost} pareto={'IN' if accepted else 'dominated'}")
            for d in result["dropped"]:
                print(f"[round {rnd}] (丢弃) {d[:100]}")

    elapsed = round(time.time() - started, 1)
    report_lines = [
        f"# mh-evolve 报告 ({elapsed}s)",
        f"- Proposer: LLM ({proposer.model}) | 轮数: {args.rounds} | "
        f"候选写入: candidates/ | 前沿大小: {len(frontier)}",
        f"- ⚠️ 人类在环: 候选未自动注入 {args.policies}; 人工裁决后按 "
        f"`python -m src.meta_harness.adapter validate --candidate <文件>` 复核再注入",
    ]
    for note in notes:
        report_lines.append(f"- ⚠️ {note}")
    report_lines.append("```")
    report_lines.append(frontier.plot_ascii(40, 10))
    report_lines.append("```")
    for p in frontier.frontier():
        report_lines.append(f"- {p.id}: q={p.quality} cost={p.cost}")
    if not diag:
        report_lines.append("\n> 诊断: 未提供 --db, 本轮为无轨迹上下文提议 (质量=有效基线 0.5)")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(report_lines), encoding="utf-8")
    print(f"[mh-evolve] 完成: 前沿={len(frontier)} 报告={args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
