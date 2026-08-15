#!/usr/bin/env python3
"""BottleSumo V9 Gate — Meta-Harness Evaluator 适配器.

实现 Stanford IRIS Lab Meta-Harness (arXiv:2603.28052) 的 Evaluator 契约:
    evaluate(harness_working_tree) -> {score, passed, cost, trajectory}

Harness 范围见 governance/meta_harness/domain_spec.md。

用法:
    python3 governance/meta_harness/evaluator_v9.py [--episodes 10] [--tag ID] [--json out.json]
    python3 governance/meta_harness/evaluator_v9.py --diff-baseline baseline.json [--tag ID]

差分测试 (Sprint 17, FP-MC-014/015 对策):
    --diff-baseline <json>  评估后与基线信号对比, 输出 verdict:
        PASSED       winrate 提升
        REGRESSION   winrate 下降
        SUSPICIOUS   行为指纹变化但 winrate 不变 (逻辑损坏/评估失敏 → 人工审查)
        INCONCLUSIVE 全部一致 (no-op 改动)

退出码: 0 = PASS (winrate >= 0.6), 1 = FAIL (与 V9 门一致)。
"""
import argparse
import json
import os
import subprocess
import sys
import time
from typing import Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GATE_SCRIPT = os.path.join(REPO_ROOT, "simulation", "v9_gate_evaluator.py")
THRESHOLD = 0.6  # V9_WINRATE_THRESHOLD


def diff_verdict(baseline_path: str, gate_report: dict,
                 layer: Optional[str] = None) -> dict:
    """与基线信号对比, 输出差分判定 (Sprint 17 FP-MC-014/015 对策).

    复用 evaluator_diff_test.compare_signals 的判定逻辑, 避免双实现。
    基线文件为 evaluator_diff_test.py baseline 子命令的输出:
        {"mode": "baseline", "signal": {...}}
    gate_report 必须是 v9_gate_evaluator.py 的原始 report (含 winrate/
    episode_results 字段)。
    Sprint 24 M2: layer 参数启用多信号融合判定 (winrate 主 + avg_steps 辅
    + layer-specific 信号), 打破饱和场景 SUSPICIOUS 全锁死同构。
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from evaluator_diff_test import compare_signals, extract_signal

    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    if baseline.get("mode") != "baseline":
        raise ValueError(
            f"{baseline_path} 不是 baseline 报告 "
            f"(需 evaluator_diff_test.py baseline 生成)"
        )
    cand_sig = extract_signal(gate_report)
    return compare_signals(baseline["signal"], cand_sig, layer=layer)


def evaluate(episodes: int = 10, agent: str = "abdl",
             diff_baseline: Optional[str] = None,
             layer: Optional[str] = None) -> dict:
    """Run the V9 gate against the current working tree; return the MH report."""
    cmd = [
        sys.executable, GATE_SCRIPT,
        "--episodes", str(episodes),
        "--agent", agent,
        "--json",
    ]
    t0 = time.monotonic()
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=1800
    )
    wall_s = time.monotonic() - t0

    # Parse the gate's JSON report from stdout (the gate prints a multi-line
    # pretty-printed JSON — extract the first '{' .. last '}' region).
    report = None
    text = proc.stdout
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            report = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Gate JSON unparseable: {exc}") from exc
    if report is None:
        raise RuntimeError(
            f"Gate produced no JSON report (exit {proc.returncode}).\n"
            f"stdout tail: {proc.stdout[-500:]}\nstderr tail: {proc.stderr[-500:]}"
        )

    # The gate report is flat at top level (no summary block):
    #   winrate / passed / wins / losses / per_strategy / episode_results
    winrate = report.get("winrate")
    passed = report.get("passed")
    if passed is None and winrate is not None:
        passed = winrate >= THRESHOLD
    total_steps = sum(
        e.get("steps", 0) for e in report.get("episode_results", [])
    )
    mh_report = {
        "score": winrate,
        "passed": passed,
        "cost": {
            "wall_s": round(wall_s, 1),
            "total_steps": total_steps,
            "episodes": len(report.get("episode_results", [])),
        },
        "trajectory": {
            "per_strategy": report.get("per_strategy", {}),
            "episode_results": report.get("episode_results", []),
        },
        "gate_exit": proc.returncode,
    }
    # Sprint 17: 差分测试 — 在 gate 原始 report 仍可用时与基线对照
    # (FP-MC-014/015 对策: 区分 no-op/逻辑损坏与真实改善)
    if diff_baseline:
        try:
            verdict = diff_verdict(diff_baseline, report, layer=layer)
            mh_report["diff_test"] = verdict
            print(f"[diff] verdict={verdict['verdict']}: {verdict['reason']}",
                  file=sys.stderr)
            if verdict["verdict"] == "SUSPICIOUS":
                print("[diff] !! SUSPICIOUS — 需人工审查候选 (逻辑损坏或评估失敏)",
                      file=sys.stderr)
        except Exception as exc:  # 差分失败不阻断评估
            print(f"[diff] WARNING: 差分测试失败: {exc}", file=sys.stderr)
    return mh_report


def main() -> int:
    ap = argparse.ArgumentParser(description="BottleSumo Meta-Harness Evaluator")
    ap.add_argument("--episodes", type=int, default=10)
    ap.add_argument("--agent", choices=["abdl", "heuristic", "v11"], default="abdl")
    ap.add_argument("--tag", default=None, help="variant id for provenance")
    ap.add_argument("--json", default=None, help="write MH report to path")
    ap.add_argument(
        "--diff-baseline", default=None, metavar="JSON",
        help="基线信号文件 (evaluator_diff_test.py baseline 输出); "
             "提供后评估结果与基线对比输出差分判定",
    )
    ap.add_argument(
        "--layer", default=None, choices=["rules", "mapping", "physics"],
        help="Sprint 24 M2: 候选所属层, 启用多信号融合判定 "
             "(winrate+avg_steps+layer-specific 信号)",
    )
    args = ap.parse_args()

    report = evaluate(episodes=args.episodes, agent=args.agent,
                      diff_baseline=args.diff_baseline, layer=args.layer)
    if args.tag:
        report["tag"] = args.tag

    out = json.dumps(report, indent=1)
    if args.json:
        with open(args.json, "w") as f:
            f.write(out)
        print(f"report written -> {args.json}")
    print(out)

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
