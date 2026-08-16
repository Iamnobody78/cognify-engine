#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fusion.py — 轨 C: 双轨融合分析 (基准测试 ↔ 自使用验证 交叉验证)
================================================================
- benchmark_only:        基准通过但自使用无对应场景 → 增强自使用场景
- self_validation_only: 自使用失败且基准无对应域 → 增强基准覆盖
- 双轨差异 >10 分 → 触发深度审查 (state/fusion_deep_review.json)
- 一致性 = 匹配域对得分差 ≤10 的比例
"""
import json
from datetime import datetime
from pathlib import Path

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
BM = TRI / "benchmark"
DB = TRI / "self_validate" / "self_validate.db"
REVIEW = TRI / "state/fusion_deep_review.json"

# 基准域 ↔ 自使用场景 映射 (名称不完全一致, 显式映射)
DOMAIN_SCENARIO = {
    "元能力体系": "元能力自评",
    "MCP生态": "MCP工具自用",
    "治理引擎": "治理引擎自用",
    "认知引擎": "认知引擎自用",
    # 三系统同步/统一工程/磁盘健康/元自动化 无直接自用场景 (benchmark_only 候选)
}


def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_benchmark_latest() -> dict | None:
    runs = _json(BM / "trend_data.json", {}).get("runs", [])
    return runs[-1] if runs else None


def load_self_validate_latest() -> dict | None:
    import sqlite3
    if not DB.exists():
        return None
    con = sqlite3.connect(DB)
    try:
        row = con.execute("SELECT run_id, timestamp, overall_score, passed_scenarios FROM "
                          "self_validation_runs ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        scen = con.execute("SELECT scenario, success, score, details FROM self_validation_scenarios "
                           "WHERE run_id=? ORDER BY id", (row[0],)).fetchall()
        return {"run_id": row[0], "ts": row[1], "overall_score": row[2],
                "passed": row[3], "scenarios": [{"scenario": s, "success": bool(ok), "score": sc,
                                                 "details": json.loads(d) if d else {}}
                                                for s, ok, sc, d in scen]}
    finally:
        con.close()


def analyze(bench: dict | None, selfval: dict | None) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    if bench is None or selfval is None:
        return {"timestamp": now, "ready": False,
                "note": "双轨数据不足 (基准或自使用尚无记录)"}
    gaps, matched = [], []
    # ---- benchmark_only: 基准通过但无对应自用场景 ----
    # benchmark domains 为 {域名: 分数} dict; 通过标准: 域得分 ≥80 (BENCHMARK-AUTO)
    for dom, score in (bench.get("domains") or {}).items():
        scen = DOMAIN_SCENARIO.get(dom)
        sv = next((x for x in selfval["scenarios"] if x["scenario"] == scen), None) if scen else None
        if score >= 80 and sv is None:
            gaps.append({"type": "benchmark_only", "domain": dom,
                         "recommendation": "增加自使用验证场景"})
        elif score >= 80 and sv is not None:
            matched.append({"domain": dom, "bench": score, "self": sv["score"]})
    # ---- self_validation_only: 自用失败且无对应基准域 ----
    for sv in selfval["scenarios"]:
        doms = [d for d, s in DOMAIN_SCENARIO.items() if s == sv["scenario"]]
        if not sv["success"] and not doms:
            gaps.append({"type": "self_validation_only", "scenario": sv["scenario"],
                         "recommendation": "增加基准测试覆盖"})
    # ---- 一致性 (匹配对得分差 ≤10) ----
    consist = 100.0 if matched else 0.0
    big_diff = []
    if matched:
        diffs = [abs(m["bench"] - m["self"]) for m in matched]
        consist = round(sum(1 for d in diffs if d <= 10) / len(diffs) * 100, 1)
        big_diff = [m for m, d in zip(matched, diffs) if d > 10]
    overall = round((bench["total_score"] + selfval["overall_score"]) / 2, 1)
    report = {"timestamp": now, "ready": True,
              "benchmark_total": bench["total_score"],
              "self_validate_total": selfval["overall_score"],
              "overall_health": overall,
              "consistency": consist,
              "gaps": gaps,
              "matched": matched,
              "big_diff": big_diff,
              "actions": []}
    if bench["total_score"] < 80:
        report["actions"].append({"priority": "P0", "action": "修复基准测试失败的域"})
    if selfval["overall_score"] < 80:
        report["actions"].append({"priority": "P0", "action": "修复自使用验证失败的场景"})
    if big_diff:
        report["actions"].append({"priority": "P1", "action": "深度审查双轨差异域",
                                  "domains": [m["domain"] for m in big_diff]})
    # ---- 门禁: 双轨差异 >10 → 深度审查标记 ----
    diff = abs(bench["total_score"] - selfval["overall_score"])
    if diff > 10:
        REVIEW.parent.mkdir(parents=True, exist_ok=True)
        REVIEW.write_text(json.dumps({"mode": "deep-review", "since": now,
                                      "benchmark": bench["total_score"],
                                      "self_validate": selfval["overall_score"],
                                      "diff": round(diff, 1)}, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    elif REVIEW.exists():
        REVIEW.unlink()
    return report


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    b, s = load_benchmark_latest(), load_self_validate_latest()
    rep = analyze(b, s)
    if not rep.get("ready"):
        print(f"[fusion] {rep['note']}")
        sys.exit(1)
    print(f"[fusion] 基准 {rep['benchmark_total']} | 自使用 {rep['self_validate_total']} "
          f"| 整体 {rep['overall_health']} | 一致性 {rep['consistency']}%")
    for g in rep["gaps"]:
        print(f"  gap[{g['type']}] {g.get('domain', g.get('scenario'))} → {g['recommendation']}")
    for a in rep["actions"]:
        print(f"  action[{a['priority']}] {a['action']}")
    sys.exit(0)
