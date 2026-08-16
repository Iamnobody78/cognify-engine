#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
benchmark.py — BENCHMARK-AUTO + BENCHMARK-CONTINUOUS 基准测试控制器
====================================================================
8 测试域: 元能力/MCP/三系统同步/治理/认知/统一工程/磁盘/元自动化
B.E.N.C.H. 五步法 + T.R.E.N.D. 趋势验证 (阈值 ≥90/80-89/70-79/<70)

用法:
  python benchmark.py all                 # 全部基准 (+ trend/degradation 报告)
  python benchmark.py score               # 健康评分
  python benchmark.py domain <域>         # 特定域
  python benchmark.py report --format json|html|markdown
  python benchmark.py trend               # 趋势
  python benchmark.py warnings            # 退化警告 (域级 >5% 告警, >10% 修复模式)
  python benchmark.py fix                 # 修复模式 (D Decide)
"""
import faulthandler
import json
import shutil
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
BM = TRI / "benchmark"
TREND = BM / "trend_data.json"
REPORT = BM / "benchmark_report.md"
AIONUI_DB = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\aionui-backend.db")
HERMES_CFG = Path(r"C:\Users\ivy\AppData\Local\hermes\config.yaml")
DSH_REF = Path(r"C:\Users\ivy\.dsh\profiles\cognify\MCP_REFERENCE.md")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _json(p: Path, default=None):
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default


# ---------------------------------------------------------------- 8 域测试
def bench_meta_capability() -> dict:
    st = _json(TRI / "meta/status.json", {})
    cl = _json(TRI / "meta/closure/closure_report.json", {})
    active_ok = st.get("active_count") == "30/30"
    closure = cl.get("closure_rate", 0)
    score = round(closure * 100, 1) if active_ok else round(closure * 80, 1)
    return {"domain": "元能力体系", "score": score,
            "passed": active_ok and closure >= 0.9,
            "details": {"active": st.get("active_count"), "closure": closure}}


def bench_mcp() -> dict:
    """三端镜像一致性: ready 服务器须同时存在于 Hermes config 与 AionUi 库。"""
    import yaml
    ready = []
    if (TRI / "config/mcp_registry.yaml").exists():
        try:
            reg = yaml.safe_load((TRI / "config/mcp_registry.yaml").read_text(encoding="utf-8"))
            servers = reg.get("servers", []) if isinstance(reg, dict) else (reg or [])
            ready = [s.get("id") or s.get("name") for s in servers
                     if isinstance(s, dict) and s.get("status") == "ready"]
        except Exception:
            ready = []
    hermes_names = aionui_names = []
    if HERMES_CFG.exists():
        try:
            h = yaml.safe_load(HERMES_CFG.read_text(encoding="utf-8"))
            hermes_names = list((h.get("mcp_servers") or {}).keys())
        except Exception:
            # 兜底: Hermes 可能用双引号写回 Windows 路径 (\\U 等非法转义),
            # 严格 YAML 解析失败时降级为行扫描
            sec = HERMES_CFG.read_text(encoding="utf-8", errors="replace").split("mcp_servers:")[-1]
            hermes_names = [l.strip().rstrip(":") for l in sec.splitlines()
                            if l.startswith("  ") and l.endswith(":") and not l.startswith("    ")]
    if AIONUI_DB.exists():
        try:
            con = sqlite3.connect(AIONUI_DB)
            aionui_names = [r[0] for r in con.execute(
                "SELECT name FROM mcp_servers WHERE enabled='1' AND deleted_at IS NULL").fetchall()]
            con.close()
        except Exception:
            aionui_names = []
    hs, aset = set(hermes_names), set(aionui_names)
    overlap = [r for r in ready if r in hs and r in aset]
    avail = round(len(overlap) / len(ready) * 100, 1) if ready else 0.0
    return {"domain": "MCP生态", "score": min(avail, 100.0),
            "passed": avail >= 95,
            "details": {"ready": len(ready), "overlap": len(overlap),
                        "hermes": len(hermes_names), "aionui": len(aionui_names),
                        "missing": [r for r in ready if r not in hs or r not in aset]}}


def bench_tri_sync() -> dict:
    alive = (TRI / "state/daemon.lock").exists()
    sessions = len(list((TRI / "hub/sessions").rglob("*.zstd"))) if (TRI / "hub/sessions").exists() else 0
    consistency = 100.0 if alive and sessions > 100 else (60.0 if alive else 0.0)
    return {"domain": "三系统同步", "score": consistency,
            "passed": consistency >= 95,
            "details": {"daemon": alive, "sessions": sessions}}


def bench_governance() -> dict:
    import re
    ev = TRI / "debt/pytest_full_20260815.txt"
    score, passed, detail = 0.0, False, "无证据"
    if ev.exists():
        txt = ev.read_text(encoding="utf-8", errors="replace")
        # pytest 在 0 failed 时省略该段, 需分别提取
        m_p = re.search(r"(\d+)\s+passed", txt)
        m_f = re.search(r"(\d+)\s+(?:failed|error)", txt)
        m_s = re.search(r"(\d+)\s+skipped", txt)
        if m_p:
            total = int(m_p.group(1)) + int(m_f.group(1)) if m_f else int(m_p.group(1))
            score = round(int(m_p.group(1)) / total * 100, 1) if total else 0
            passed = (not m_f or int(m_f.group(1)) == 0) and score >= 98
            detail = f"{m_p.group(1)} passed" + (f" / {m_f.group(1)} failed" if m_f else " / 0 failed") \
                     + (f" / {m_s.group(1)} skipped" if m_s else "")
    return {"domain": "治理引擎", "score": min(score, 100.0), "passed": passed,
            "details": {"regression": detail, "evidence": ev.name if ev.exists() else None}}


def bench_cognitive() -> dict:
    """只统计 MMC 自检心跳 (mmce_*): 6/6 闭环闭合率。
    perpetual_* 为汇总报告, 不含闭合段, 不参与认知度量。"""
    hb = list((TRI / "hub/cves/heartbeats").glob("mmce_heartbeat_*.md"))
    closed = sum(1 for h in hb if "循环闭合" in h.read_text(encoding="utf-8", errors="replace"))
    score = round(closed / len(hb) * 100, 1) if hb else 0.0
    return {"domain": "认知引擎", "score": min(score, 100.0),
            "passed": score >= 95 and len(hb) > 0,
            "details": {"heartbeats": len(hb), "closed": closed,
                        "failed": len(hb) - closed}}


def bench_unity() -> dict:
    ver = TRI / "VERSION"
    ver_ok = ver.exists() and ver.read_text(encoding="utf-8").strip() == "2.1.0"
    cfg_ok = (TRI / "config/unified.yaml").exists()
    score = 100.0 if ver_ok and cfg_ok else 50.0
    return {"domain": "统一工程", "score": score, "passed": ver_ok and cfg_ok,
            "details": {"version": "2.1.0", "config": cfg_ok}}


def bench_disk() -> dict:
    t = shutil.disk_usage("C:\\")
    mcp_dir = Path(r"C:\Users\ivy\.aionui-tri-sync\mcp-server")
    mcp_gb = round(sum(p.stat().st_size for p in mcp_dir.rglob("*") if p.is_file()) / 1e9, 2) if mcp_dir.exists() else 0
    ratio = t.used / t.total
    score = 100.0 if ratio < 0.85 else (70.0 if ratio < 0.9 else 40.0)
    passed = mcp_gb <= 5 and ratio < 0.9
    return {"domain": "磁盘健康", "score": score, "passed": passed,
            "details": {"ratio": round(ratio, 3), "mcp_gb": mcp_gb, "free_gb": round(t.free / 1e9, 1)}}


def bench_automation() -> dict:
    upd = _json(TRI / "meta/decision/version_history.jsonl")
    # 从 jsonl 读
    upd_ok = upd if isinstance(upd, list) else []
    selfheal = (TRI / "meta-exec/bootstrap_report.json").exists()
    score = 100.0 if selfheal else 70.0
    return {"domain": "元自动化", "score": score, "passed": score >= 80,
            "details": {"selfheal": selfheal, "updates": len(upd_ok)}}


DOMAINS = [bench_meta_capability, bench_mcp, bench_tri_sync, bench_governance,
           bench_cognitive, bench_unity, bench_disk, bench_automation]


# ---------------------------------------------------------------- B.E.N.C.H.
def run_all() -> dict:
    BM.mkdir(parents=True, exist_ok=True)
    results = [f() for f in DOMAINS]
    # 各域得分钳制 [0,100], 防止单域异常污染总分
    for r in results:
        r["score"] = min(max(r["score"], 0.0), 100.0)
    total = round(sum(r["score"] for r in results) / len(results), 1)
    passed_n = sum(1 for r in results if r["passed"])
    snap = {"ts": _now(), "version": "2.1.0", "total_score": total,
            "passed": passed_n, "total": len(results), "domains": results}
    prev = []
    if TREND.exists():
        prev = json.loads(TREND.read_text(encoding="utf-8")).get("runs", [])
    prev.append({"ts": snap["ts"], "total_score": total, "domains": {r["domain"]: r["score"] for r in results}})
    TREND.write_text(json.dumps({"runs": prev[-30:]}, ensure_ascii=False, indent=2), encoding="utf-8")
    # 报告
    lines = [
        f"# Cognify-Engine 基准测试报告", "",
        f"**测试时间**: {_now()} | **版本**: 2.1.0 | **整体健康评分**: {total}/100", "",
        "| 测试域 | 得分 | 状态 |", "|--------|------|------|",
    ]
    for r in results:
        lines.append(f"| {r['domain']} | {r['score']:.1f} | {'✅ PASS' if r['passed'] else '❌ FAIL'} |")
    lines += ["", f"**通过域**: {passed_n}/{len(results)} | **评级**: "
                  f"{'🟢 优秀' if total >= 90 else '🟡 良好' if total >= 80 else '🟠 警告' if total >= 70 else '🔴 危险'}"]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return snap


def trend() -> list:
    if not TREND.exists():
        return []
    return json.loads(TREND.read_text(encoding="utf-8")).get("runs", [])


def warnings() -> dict:
    """T.R.E.N.D. E-Escalate: 总分与域级双维度退化告警。
    - 相邻运行总分下降 ≥5 → 告警
    - 域得分较上一运行下降 >5% → 告警, >10% → 修复模式 (fix_required)"""
    runs = trend()
    if len(runs) < 2:
        return {"warnings": [], "latest": runs[-1]["total_score"] if runs else None,
                "note": "历史不足 (需 ≥2 次运行)"}
    last2 = runs[-2:]
    w = []
    # 总分维度
    d_total = last2[1]["total_score"] - last2[0]["total_score"]
    if d_total <= -5:
        w.append({"ts": last2[1]["ts"], "domain": "总体", "delta": round(d_total, 1), "level": "告警"})
    # 域级维度
    for dom in set(last2[0]["domains"]) | set(last2[1]["domains"]):
        p, c = last2[0]["domains"].get(dom), last2[1]["domains"].get(dom)
        if p is None or c is None:
            continue
        d = c - p
        if d <= -10:
            w.append({"ts": last2[1]["ts"], "domain": dom, "delta": round(d, 1), "level": "修复模式"})
        elif d <= -5:
            w.append({"ts": last2[1]["ts"], "domain": dom, "delta": round(d, 1), "level": "告警"})
    return {"warnings": w, "latest": last2[1]["total_score"],
            "fix_required": any(x["level"] == "修复模式" for x in w)}


def _rating(t: float) -> str:
    if t >= 90:
        return "🟢 优秀"
    if t >= 80:
        return "🟡 良好"
    if t >= 70:
        return "🟠 警告"
    return "🔴 危险"


def write_reports() -> None:
    """T.R.E.N.D. 产物: trend_report.md (N Notify) + degradation_report.md (R Review)。"""
    runs = trend()
    w = warnings()
    latest = w.get("latest")
    # ---- trend_report.md (N) ----
    tl = ["# 基准趋势报告 (T.R.E.N.D. — Notify)", "",
          f"**最新总分**: {latest}/100 ({_rating(latest) if latest is not None else '?'}) | "
          f"**累计运行**: {len(runs)} 次", "", "| 时间 | 总分 | 评级 |", "|---|---|---|"]
    for r in runs:
        tl.append(f"| {r['ts'][:16]} | {r['total_score']} | {_rating(r['total_score'])} |")
    tl.append("")
    (BM / "trend_report.md").write_text("\n".join(tl), encoding="utf-8")
    # ---- degradation_report.md (R) ----
    dl = ["# 退化审查报告 (T.R.E.N.D. — Review)", "",
          f"**审查窗口**: 最近 {min(len(runs), 3)} 次运行 | 告警阈值: 域级下降 >5% (修复模式 >10%)", ""]
    if len(runs) >= 2:
        prev, cur = runs[-2], runs[-1]
        dl += ["| 测试域 | 上轮 | 本轮 | 变化 | 判定 |", "|---|---|---|---|---|"]
        doms = sorted(set(prev["domains"]) | set(cur["domains"]))
        for dom in doms:
            p, c = prev["domains"].get(dom), cur["domains"].get(dom)
            if p is None or c is None:
                dl.append(f"| {dom} | {p if p is not None else '-'} | {c if c is not None else '-'} | — | 新增/缺失 |")
                continue
            d = c - p
            verdict = "🟢" if d > 0 else ("🔴 修复模式" if d <= -10 else ("⚠️ 告警" if d <= -5 else "🟡 持平"))
            dl.append(f"| {dom} | {p} | {c} | {d:+.1f} | {verdict} |")
    else:
        dl.append("_历史不足 (需 ≥2 次运行), 基线建立中。_")
    dl.append("")
    if w.get("warnings"):
        dl.append("**退化项**")
        for x in w["warnings"]:
            dl.append(f"- {'🔴' if x['level'] == '修复模式' else '⚠️'} {x.get('domain', '总体')}: "
                      f"{x['delta']}% ({x['ts'][:16]})")
    else:
        dl.append("**无退化项** ✅")
    (BM / "degradation_report.md").write_text("\n".join(dl), encoding="utf-8")


# ---------------------------------------------------------------- 命令
FIX_MAP = {
    "元能力体系": "python daemon/meta_capabilities.py status (核对 30 维 active 与闭环率)",
    "MCP生态": "python daemon/mcp_sync.py (三端镜像重同步)",
    "三系统同步": "python daemon/sync_daemon.py (守护恢复)",
    "治理引擎": "python -m pytest tests (cognify-engine 回归)",
    "认知引擎": "python daemon/mmc_agent.py heartbeat (MMC 自检)",
    "统一工程": "核对 VERSION 与 config/unified.yaml",
    "磁盘健康": "cognify meta-disk (磁盘治理)",
    "元自动化": "核对 meta-exec/bootstrap_report.json 与版本账本",
}


def cmd_fix() -> int:
    """修复模式 (D Decide): 退化 >5% 告警, >10% 暂停新功能强制修复。"""
    w = warnings()
    print(f"[bench] 最新总分: {w.get('latest', '?')}")
    if not w.get("warnings"):
        print("[bench] 无退化, 无需修复模式")
        return 0
    for x in w["warnings"]:
        dom = x.get("domain", "总体")
        print(f"  {'🔴' if x['level'] == '修复模式' else '⚠️'} {dom}: 下降 {x['delta']}% "
              f"→ {FIX_MAP.get(dom, '人工介入 (无预置修复命令)')}")
    if w.get("fix_required"):
        print("[bench] 🔴 触发修复模式 (退化 >10%): 先修退化域, 暂停新功能合入")
        return 2
    print("[bench] ⚠️ 存在退化告警 (5%-10%): 优先安排修复")
    return 1


def main():
    argv = sys.argv[1:]
    cmd = (argv[0] if argv else "all").lstrip("-")
    BM.mkdir(parents=True, exist_ok=True)
    if cmd in ("all", "run"):
        s = run_all()
        write_reports()
        print(f"[bench] 整体健康评分: {s['total_score']}/100 | 通过 {s['passed']}/{s['total']}")
        for r in s["domains"]:
            print(f"  {'✅' if r['passed'] else '❌'} {r['domain']}: {r['score']}")
        print(f"[bench] → {REPORT}")
        return 0 if s["passed"] >= 7 else 1
    if cmd == "score":
        s = run_all()
        print(f"[bench] 健康评分: {s['total_score']}/100")
        return 0 if s["total_score"] >= 80 else 1
    if cmd == "domain":
        if len(argv) < 2:
            print("用法: benchmark --domain <域> | 可用域: " + " / ".join(d().get("domain", "?") for d in DOMAINS))
            return 1
        want = argv[1]
        for f in DOMAINS:
            r = f()
            if want in r["domain"] or r["domain"] in want or want.lower() in r["domain"].lower():
                r["score"] = min(max(r["score"], 0.0), 100.0)
                print(f"{'✅' if r['passed'] else '❌'} {r['domain']}: {r['score']}")
                print(f"  详情: {json.dumps(r['details'], ensure_ascii=False)}")
                return 0 if r["passed"] else 1
        print(f"[bench] 未知域: {want}")
        return 1
    if cmd == "report":
        fmt = argv[argv.index("--format") + 1] if "--format" in argv else "markdown"
        run_all()
        write_reports()
        if fmt == "json":
            s = json.loads(REPORT.read_text(encoding="utf-8") if False else "{}")
            out = BM / "benchmark_report.json"
            import re
            snap = trend()[-1] if trend() else {}
            out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[bench] → {out}")
        elif fmt == "html":
            md = REPORT.read_text(encoding="utf-8")
            esc = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html = (f"<!doctype html><html><head><meta charset='utf-8'>"
                    f"<title>Benchmark Report</title></head><body><pre>{esc}</pre></body></html>")
            out = BM / "benchmark_report.html"
            out.write_text(html, encoding="utf-8")
            print(f"[bench] → {out}")
        else:
            print(f"[bench] → {REPORT}")
        return 0
    if cmd == "trend":
        for t in trend()[-10:]:
            print(f"  {t['ts'][:16]} | {t['total_score']}")
        return 0
    if cmd == "warnings":
        w = warnings()
        print(f"[bench] 最新: {w.get('latest', '?')}")
        if w.get("note"):
            print(f"[bench] {w['note']}")
        for x in w.get("warnings", []):
            print(f"  ⚠️ {x.get('domain', '总体')} {x['ts'][:16]} 下降 {x['delta']}% ({x['level']})")
        return 0
    if cmd == "fix":
        return cmd_fix()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
