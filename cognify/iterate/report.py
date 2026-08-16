#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report.py — 轨 D: 每日迭代报告 + 冲刺模式检测 (SELF-VALIDATE-ITERATE)
=====================================================================
- --report:  双轨融合 → benchmark/daily_iteration_report.md (每日 08:00 调度)
- --sprint:  连续 3 天整体健康无改进 → 冲刺模式 (state/sprint_mode.json)
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fusion import analyze, load_benchmark_latest, load_self_validate_latest  # noqa: E402

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
BM = TRI / "benchmark"
DAILY = BM / "daily_iteration_report.md"
SPRINT = TRI / "state/sprint_mode.json"
VERSION = "2.1.1"


def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _rating(t: float) -> str:
    if t >= 90:
        return "🟢 优秀"
    if t >= 80:
        return "🟡 良好"
    if t >= 70:
        return "🟠 警告"
    return "🔴 危险"


def gen_report() -> dict:
    bench = load_benchmark_latest()
    selfval = load_self_validate_latest()
    fusion = analyze(bench, selfval)
    now = datetime.now().isoformat(timespec="seconds")
    if not fusion.get("ready"):
        lines = [f"# Cognify-Engine 每日迭代报告", "", f"**日期**: {now[:10]} | **版本**: {VERSION}",
                 "", f"**整体健康评分**: — (双轨数据不足: {fusion.get('note')})"]
        DAILY.write_text("\n".join(lines), encoding="utf-8")
        return fusion
    # 基准快照表
    btable = ["| 测试域 | 基准 | 自使用 | 状态 |", "|---|---|---|---|"]
    for dom, score in (bench.get("domains") or {}).items():
        sv = next((m["self"] for m in fusion["matched"] if m["domain"] == dom), "—")
        st = "✅" if score >= 80 else "❌"
        btable.append(f"| {dom} | {score} | {sv} | {st} |")
    # 自使用快照表
    stable = ["| 场景 | 得分 | 状态 | 详情 |", "|---|---|---|---|"]
    for sv in selfval.get("scenarios", []):
        det = json.dumps(sv.get("details", {}), ensure_ascii=False)[:60]
        stable.append(f"| {sv['scenario']} | {sv['score']} | {'✅' if sv['success'] else '❌'} | {det} |")
    # 融合分析
    glines = [f"- **一致性**: {fusion['consistency']}%"]
    if fusion["gaps"]:
        glines.append("- **发现的缺口**:")
        for g in fusion["gaps"]:
            glines.append(f"  1. [{g['type']}] {g.get('domain', g.get('scenario'))} → {g['recommendation']}")
    else:
        glines.append("- **发现的缺口**: 无")
    if fusion["big_diff"]:
        glines.append("- **双轨差异** (深度审查): " + ", ".join(m["domain"] for m in fusion["big_diff"]))
    # 动作
    alines = [f"{i + 1}. [{a['priority']}] {a['action']}" for i, a in enumerate(fusion["actions"])] or ["无"]
    lines = [
        f"# Cognify-Engine 每日迭代报告", "",
        f"**日期**: {now[:10]} | **版本**: {VERSION}",
        f"**整体健康评分**: {fusion['overall_health']}/100 ({_rating(fusion['overall_health'])})", "",
        "## 基准测试快照", *btable, "",
        "## 自使用验证快照", *stable, "",
        "## 双轨融合分析", *glines, "",
        "## 今日迭代动作", *alines, "",
        "## 发布候选状态", f"- [ ] 本周候选版本: v{VERSION}-rc",
        f"- [ ] 待修复问题: {sum(1 for a in fusion['actions'] if a['priority'] == 'P0')} 个 P0",
        "- [ ] 门禁: 基准 ≥90 (当前 " + str(fusion["benchmark_total"]) + ") / 自使用 ≥90 (当前 "
        + str(fusion["self_validate_total"]) + ")",
    ]
    DAILY.write_text("\n".join(lines), encoding="utf-8")
    return fusion


def check_sprint() -> dict:
    """连续 3 天整体健康无改进 → 冲刺模式。"""
    runs = _json(BM / "trend_data.json", {}).get("runs", [])
    import sqlite3
    sv_daily = {}
    db = TRI / "self_validate/self_validate.db"
    if db.exists():
        con = sqlite3.connect(db)
        for ts, sc in con.execute("SELECT timestamp, overall_score FROM self_validation_runs"):
            sv_daily[ts[:10]] = max(sv_daily.get(ts[:10], 0), sc)
        con.close()
    days = sorted(set(r["ts"][:10] for r in runs) | set(sv_daily.keys()))[-4:]
    history = []
    for d in days:
        b = max([r["total_score"] for r in runs if r["ts"][:10] == d], default=None)
        s = sv_daily.get(d)
        if b is not None and s is not None:
            history.append({"day": d, "overall": round((b + s) / 2, 1)})
    sprint = False
    if len(history) >= 3:
        last3 = history[-3:]
        sprint = all(last3[i]["overall"] <= last3[i - 1]["overall"] for i in (1, 2))
    mode = {"mode": "sprint" if sprint else "normal", "checked": datetime.now().isoformat(timespec="seconds"),
            "days": history}
    SPRINT.parent.mkdir(parents=True, exist_ok=True)
    SPRINT.write_text(json.dumps(mode, ensure_ascii=False, indent=2), encoding="utf-8")
    return mode


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "report":
        f = gen_report()
        if not f.get("ready"):
            print(f"[iterate] {f.get('note')}")
            return 1
        print(f"[iterate] 每日报告: 整体 {f['overall_health']} | 一致性 {f['consistency']}% "
              f"| 缺口 {len(f['gaps'])} | 动作 {len(f['actions'])}")
        print(f"[iterate] → {DAILY}")
        return 0 if f["overall_health"] >= 80 else 1
    if cmd == "sprint":
        m = check_sprint()
        print(f"[iterate] 模式: {m['mode']} | 近 {len(m['days'])} 天: "
              + " → ".join(f"{d['day'][5:]}:{d['overall']}" for d in m["days"]))
        return 0 if m["mode"] == "normal" else 2
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
