#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — BENCHMARK-FULL-AUTO 统一基准执行器 (B.E.N.C.H.-F.U.L.L.)
====================================================================
- Boot:    检测外部基准依赖 (17 项注册表, ready/missing 诚实标注)
- Execute: 并行/顺序运行本地真实适配器 (MCP 生态/自我意识/元反思/Agent 构建)
- Normalize: 得分归一化 0-100
- Compare: 与上次 full_report.json 对比
- Highlight: P0/P1/P2 问题标记
- Finalize: benchmark_full_report.md + full_report.json
- Loop:    得分 < 阈值 → 修复建议

用法: python runner.py full|status|report
"""
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import PREV, REPORTS, detect_external, run_local  # noqa: E402

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
FULL_MD = TRI / "benchmark/benchmark_full_report.md"


def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def run_full() -> dict:
    REPORTS.mkdir(parents=True, exist_ok=True)
    ext = detect_external()
    local = run_local()
    # ---- Normalize + 汇总 ----
    local_avg = round(sum(r["score"] for r in local) / len(local), 1) if local else 0.0
    installed = [e for e in ext if e["status"] in ("installed", "cloned")]
    prev = _json(PREV, None)
    prev_local = prev.get("local_avg") if prev else None
    delta = round(local_avg - prev_local, 1) if prev_local is not None else None
    # ---- Highlight: P0/P1/P2 ----
    issues = []
    for r in local:
        if not r["passed"]:
            prio = "P0" if r["score"] < 60 else "P1"
            issues.append({"priority": prio, "benchmark": r["id"], "score": r["score"],
                           "detail": r["detail"]})
    if installed:
        issues.append({"priority": "P1", "benchmark": "外部基准接入",
                       "score": None, "detail": f"{len(installed)} 项外部基准已安装待纳入调度"})
    report = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "version": "2.1.3",
        "local_avg": local_avg,
        "prev_local": prev_local,
        "delta": delta,
        "local": local,
        "external": ext,
        "installed_count": len(installed),
        "missing_count": len(ext) - len(installed),
        "issues": issues,
        "passed": sum(1 for r in local if r["passed"]),
        "total": len(local),
    }
    PREV.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # ---- Finalize: 报告 ----
    lines = ["# Cognify-Engine 全基准测试报告 (BENCHMARK-FULL-AUTO)", "",
             f"**测试时间**: {report['ts'][:16]} | **版本**: {report['version']}",
             f"**本地可执行通过率**: {report['passed']}/{report['total']} | "
             f"**本地均分**: {local_avg}/100" + (f" (Δ{delta:+.1f})" if delta is not None else " (首轮基线)"), "",
             "## 本地真实基准 (可执行)", "", "| 基准 | 得分 | 状态 | 详情 |", "|---|---|---|---|"]
    for r in local:
        lines.append(f"| {r['id']} | {r['score']} | {'✅ PASS' if r['passed'] else '❌ FAIL'} | {r['detail']} |")
    lines += ["", "## 外部基准注册表 (Ecosystem 2026-08)", "",
              "| 基准 | 类别 | 优先级 | 阈值 | 状态 | 说明 |", "|---|---|---|---|---|---|"]
    for e in ext:
        st = {"installed": "✅ 已安装", "cloned": "📦 已克隆", "missing": "⬜ 未安装"}.get(e["status"], e["status"])
        lines.append(f"| {e['id']} | {e['cat']} | {e['priority']} | ≥{e['target']} | {st} | {e['note'] or e['install']} |")
    lines += ["", "## 问题标记 (Highlight)", ""]
    if issues:
        for i in issues:
            lines.append(f"- [{i['priority']}] {i['benchmark']}: {i['detail']}")
    else:
        lines.append("- 无 (本地适配器全部通过)")
    lines += ["", "## 与上次对比", f"- 本地均分: {local_avg} (上次 {prev_local})"
              + (f" {'↑' if delta and delta > 0 else '↓' if delta and delta < 0 else '—'}") if delta is not None else "- 首轮基线 (无对比)",
              f"- 外部基准待安装: {report['missing_count']} 项 (诚实标注, 不占通过率)", "",
              "**结论**: " + ("本地适配器全部通过, 建议接入已安装外部基准纳入调度。"
                              if report["passed"] == report["total"]
                              else f"需优先处理 {len(issues)} 项问题。")]
    FULL_MD.write_text("\n".join(lines), encoding="utf-8")
    return report


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "full"
    if cmd == "full":
        r = run_full()
        print(f"[full-bench] 本地 {r['passed']}/{r['total']} | 均分 {r['local_avg']}"
              f" | 外部已安装 {r['installed_count']}/{len(r['external'])}")
        for x in r["local"]:
            print(f"  {'✅' if x['passed'] else '❌'} {x['id']}: {x['score']} | {x['detail']}")
        print(f"[full-bench] → {FULL_MD}")
        return 0 if r["passed"] == r["total"] else 1
    if cmd == "status":
        p = _json(PREV, None)
        if p is None:
            print("[full-bench] 尚无运行记录")
            return 1
        print(f"[full-bench] 最近: {p['ts'][:16]} | 本地 {p['passed']}/{p['total']} | 均分 {p['local_avg']}"
              f" | 外部已安装 {p['installed_count']}")
        return 0
    if cmd == "report":
        if not FULL_MD.exists():
            print("[full-bench] 尚无报告, 先运行 full")
            return 1
        print(FULL_MD.read_text(encoding="utf-8"))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
