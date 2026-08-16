#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dashboard_gen.py — DEBT-016 偿还: 最小可运行 Dashboard (纯 HTML, 无前端框架)
============================================================================
读取 generate-status 的运行时数据 → 生成自包含 dashboard.html (可静态托管)。
"""
import json
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PROD = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine")
TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")


def collect() -> dict:
    d = {}
    try:
        cert = json.loads((PROD / "certificate.json").read_text(encoding="utf-8"))
        d.update(cert)
    except Exception:
        pass
    try:
        trend = json.loads((TRI / "benchmark/trend_data.json").read_text(encoding="utf-8"))
        runs = trend.get("runs", [])
        d["bench_trend"] = [{"ts": r["ts"][:16], "score": r["total_score"]} for r in runs[-7:]]
    except Exception:
        pass
    try:
        debt = json.loads((TRI / "debt/debt_inventory.json").read_text(encoding="utf-8"))
        debts = debt.get("debts", [])
        d["debt"] = {"total": len(debts),
                     "done": sum(1 for x in debts if x.get("status") == "已解决")}
        d["debt_list"] = [{"id": x.get("id"), "sev": x.get("sev"), "status": x.get("status"),
                           "desc": (x.get("desc") or "")[:50]} for x in debts[:8]]
    except Exception:
        pass
    try:
        ev = json.loads((TRI / "meta/status.json").read_text(encoding="utf-8"))
        d["meta_active"] = ev.get("active_count")
        d["meta_health"] = ev.get("overall_health")
    except Exception:
        pass
    try:
        mc = json.loads((TRI / "meta-call/certification_report.json").read_text(encoding="utf-8"))
        d["call_certified"] = mc.get("certified")
    except Exception:
        pass
    d["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    return d


def gen() -> Path:
    d = collect()
    bench = d.get("bench_trend", [])
    bench_rows = "".join(f"<tr><td>{b['ts']}</td><td>{b['score']}</td></tr>" for b in bench)
    debt_rows = "".join(
        f"<tr><td>{x['id']}</td><td>{x['sev']}</td><td>{x['status']}</td><td>{x['desc']}</td></tr>"
        for x in d.get("debt_list", [])) or "<tr><td colspan=4>无债务记录</td></tr>"
    html = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<title>Cognify Engine Dashboard</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; margin: 2rem; background: #0f1117; color: #e6e8ef; }}
h1 {{ color: #7aa2f7; }} h2 {{ color: #9ece6a; font-size: 1.1rem; margin-top: 2rem; }}
.card {{ display: inline-block; background: #1a1d27; border: 1px solid #2a2e3d; border-radius: 8px;
        padding: 1rem 1.4rem; margin: .4rem; min-width: 140px; }}
.card b {{ display: block; font-size: 1.6rem; color: #7dcfff; }}
table {{ border-collapse: collapse; width: 100%; margin-top: .6rem; }}
td, th {{ border: 1px solid #2a2e3d; padding: .4rem .7rem; font-size: .85rem; text-align: left; }}
th {{ background: #1a1d27; color: #9ece6a; }}
.foot {{ margin-top: 2rem; color: #565f89; font-size: .8rem; }}
</style></head><body>
<h1>🧠 Cognify Engine — 动态仪表板</h1>
<p>由 generate-status 运行时数据生成 · {d.get('ts', '')}</p>
<div class="card"><b>{d.get('meta_active', '?')}</b>元能力 active</div>
<div class="card"><b>{d.get('meta_health', '?')}</b>health</div>
<div class="card"><b>{d.get('benchmark_total', '?')}</b>基准总分</div>
<div class="card"><b>{'✅' if d.get('call_certified') else '❌'}</b>调用链认证</div>
<div class="card"><b>{d.get('debt', {}).get('done', '?')}/{d.get('debt', {}).get('total', '?')}</b>债务</div>
<h2>📊 基准趋势 (近 7 次)</h2>
<table><tr><th>时间</th><th>得分</th></tr>{bench_rows or '<tr><td colspan=2>无数据</td></tr>'}</table>
<h2>📋 债务快照</h2>
<table><tr><th>ID</th><th>级别</th><th>状态</th><th>描述</th></tr>{debt_rows}</table>
<div class="foot">DEBT-016 最小可运行版 (纯 HTML) · 生成: {d.get('ts', '')} · 刷新: 重新运行 cognify generate-dashboard</div>
</body></html>"""
    out = PROD / "plugins/dashboard/dashboard.html"
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    p = gen()
    print(f"[dashboard] 已生成最小可运行仪表板 → {p}")
    print("[dashboard] 静态托管: python -m http.server 8000 --directory plugins/dashboard")
