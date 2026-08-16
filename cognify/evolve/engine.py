#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine.py — EVOLVE-FORCE v1.0 永不偷懒强制进化引擎
====================================================
核心: 无证据 = 没进化。每 24h 至少 2 项可验证进化证据, 否则强制进化模式。

E.V.O.L.V.E. 六步法:
  E Evidence  — 扫描过去 24h 活动 (commit/测试/性能/文档/新功能), 5 项 ≥3 满足
  V Verify    — 验证证据真实 (commit 存在/文件在位/变更可查), 证伪 → 调查标记
  O Organize  — 分类 (fix/optimize/new/docs/test) + 贡献度评分 (0-100)
  L Log       — evolution_audit.jsonl 追加写 (永不可删除, 写后校验)
  V Validate  — 双轨验证 (基准 + 自使用), 低于上周期 → 进化失败回滚标记
  E Enforce   — 门禁失败 → 强制进化模式 (债务 P0 优先提案 + 报告)

用法:
  python engine.py report     # 完整六步 (每日 23:30 调度)
  python engine.py status     # 今日进化状态
  python engine.py trend      # 历史趋势
  python engine.py force      # 触发强制进化模式
  python engine.py activate   # 创建每日调度任务
"""
import os
import faulthandler
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(os.environ.get("COGNIFY_TRI", r"C:\Users\ivy\.aionui-tri-sync"))
PROD = Path(os.environ.get("COGNIFY_PROD", r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine"))
EV = TRI / "evolve"
AUDIT = EV / "evolution_audit.jsonl"
STATE = TRI / "state/evolve_force_mode.json"
ROLLBACK = TRI / "state/evolution_rollback.json"
VERSION = "2.1.2"
TYPES = {"fix": "修复", "optimize": "优化", "new": "新增", "docs": "文档", "test": "测试"}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _git(args: list, timeout=30) -> str:
    try:
        r = subprocess.run(["git", "-C", str(PROD), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return (r.stdout or r.stderr or "").strip()
    except Exception:
        return ""


# ---------------------------------------------------------------- Phase E: Evidence
def scan_evidence() -> dict:
    """扫描过去 24h 进化证据 (5 检查项, 全部真实可验证)。"""
    since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    commits = _git(["log", f"--since={since}", "--pretty=format:%h|%s|%an"])
    rows = [c for c in commits.splitlines() if "|" in c] if commits else []
    feat_rows = [r for r in rows if re.match(r"^\w+\|feat(\(|\b)", r)]
    docs_rows = [r for r in rows if re.search(r"docs/|CHANGELOG|README|\.md", r.split("|", 2)[1])]
    # 1) 新 commit
    c_ok = len(rows) >= 1
    # 2) 测试通过率 (pytest 最新证据, 阈值 ≥98%)
    pytest_file = None
    cands = sorted(TRI.glob("debt/pytest_full_*.txt"), reverse=True)
    if cands:
        pytest_file = cands[0]
    test_rate = None
    if pytest_file is not None:
        txt = pytest_file.read_text(encoding="utf-8", errors="replace")
        m_p = re.search(r"(\d+)\s+passed", txt)
        m_f = re.search(r"(\d+)\s+(?:failed|error)", txt)
        if m_p:
            total = int(m_p.group(1)) + (int(m_f.group(1)) if m_f else 0)
            test_rate = round(int(m_p.group(1)) / total * 100, 1) if total else 0.0
    t_ok = test_rate is not None and test_rate >= 98
    # 3) 性能改进: benchmark 总分较上一运行不倒退 (首日无对比 → 不满足, 诚实)
    trend = _json(TRI / "benchmark/trend_data.json", {}).get("runs", [])
    perf_delta = None
    if len(trend) >= 2:
        perf_delta = round(trend[-1]["total_score"] - trend[-2]["total_score"], 1)
    p_ok = perf_delta is not None and perf_delta >= 0
    # 4) 文档更新
    d_ok = len(docs_rows) >= 1
    # 5) 新功能上线
    n_ok = len(feat_rows) >= 1
    # 6) 元调用链认证 (META-CALL-FORCE: 部署了≠用上了, 认证失败=证据缺口)
    cert = _json(TRI / "meta-call/certification_report.json", None)
    m_ok = bool(cert and cert.get("certified"))
    checks = [
        {"item": "新 commit", "ok": c_ok, "detail": f"{len(rows)} 个提交"},
        {"item": "测试通过率", "ok": t_ok, "detail": f"{test_rate}%" if test_rate is not None else "无证据"},
        {"item": "性能改进", "ok": p_ok, "detail": f"{perf_delta:+.1f}" if perf_delta is not None else "首日无对比"},
        {"item": "文档更新", "ok": d_ok, "detail": f"{len(docs_rows)} 处"},
        {"item": "新功能", "ok": n_ok, "detail": f"{len(feat_rows)} 个 feat"},
        {"item": "元调用链认证", "ok": m_ok,
         "detail": f"{cert.get('ts', '无')[:16]} {'✅ CERTIFIED' if m_ok else '❌ 未认证'}"},
    ]
    passed_n = sum(1 for c in checks if c["ok"])
    return {"ts": _now(), "since": since, "checks": checks, "passed": passed_n,
            "total": len(checks), "commits": [r.split("|", 1)[0] for r in rows],
            "gate": passed_n >= 4, "force_required": passed_n < 4}


def evidence_report() -> dict:
    EV.mkdir(parents=True, exist_ok=True)
    ev = scan_evidence()
    (EV / f"evolution_evidence_{datetime.now().strftime('%Y%m%d')}.json").write_text(
        json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    return ev


# ---------------------------------------------------------------- Phase V: Verify
def verify_evidence(ev: dict) -> dict:
    """验证证据真实: commit 存在 / pytest 文件在位 / feat 与文档变更可查。"""
    items = []
    for h in ev.get("commits", [])[:10]:
        # git cat-file -e 存在时无输出; 失败时 stderr 有 "fatal:"
        exists = not _git(["cat-file", "-e", h + "^{commit}"])
        items.append({"commit": h, "exists": exists})
    pytest_ok = bool(list(TRI.glob("debt/pytest_full_*.txt")))
    forged = [i for i in items if not i["exists"]]
    result = {"ts": _now(), "commits_verified": items, "pytest_evidence": pytest_ok,
              "forged": forged}
    if forged:
        ROLLBACK.parent.mkdir(parents=True, exist_ok=True)
        ROLLBACK.write_text(json.dumps({"mode": "investigate", "since": _now(),
                                        "forged": forged}, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    (EV / f"evolution_verification.md").write_text(
        "\n".join(["# 进化证据验证 (Phase V)", "",
                   f"**时间**: {_now()} | **提交验证**: {len(items)} 个",
                   f"- 证伪项: {len(forged)}" + (f" ({[i['commit'] for i in forged]})" if forged else ""),
                   f"- pytest 证据: {'✅ 在位' if pytest_ok else '❌ 缺失'}"]),
        encoding="utf-8")
    return result


# ---------------------------------------------------------------- Phase O: Organize
def organize_evidence(ev: dict) -> dict:
    """分类 + 贡献度评分 (0-100) + 与上周期对比。"""
    commits = ev.get("commits", [])
    feats = len([1 for c in commits if c])
    # 上一周期: 审计 jsonl 逐行读最后一条 (jsonl 不可用 json.loads 整读)
    prev_day = None
    if AUDIT.exists():
        rows = [json.loads(l) for l in
                AUDIT.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
        if rows:
            prev_day = rows[-1]
    org = {"ts": _now(), "items": [], "prev": prev_day}
    for c in ev.get("checks", []):
        t = {"新 commit": "test", "测试通过率": "test", "性能改进": "optimize",
             "文档更新": "docs", "新功能": "new"}.get(c["item"], "fix")
        score = 100 if c["ok"] else 20
        org["items"].append({"type": t, "type_cn": TYPES.get(t, t), "item": c["item"],
                             "ok": c["ok"], "score": score, "detail": c["detail"]})
    org["avg_score"] = round(sum(i["score"] for i in org["items"]) / len(org["items"]), 1) if org["items"] else 0
    (EV / f"evolution_organized_{datetime.now().strftime('%Y%m%d')}.json").write_text(
        json.dumps(org, ensure_ascii=False, indent=2), encoding="utf-8")
    return org


# ---------------------------------------------------------------- Phase L: Log
def log_evidence(ev: dict, verify: dict, org: dict, overall: float) -> bool:
    """审计日志追加写 (永不可删除), 写后校验存在性。"""
    entry = {"id": f"EVO-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}",
             "ts": _now(), "version": VERSION,
             "evidence_passed": ev["passed"], "evidence_total": ev["total"],
             "gate": ev["gate"], "commits": ev.get("commits", []),
             "forged": len(verify.get("forged", [])),
             "avg_score": org.get("avg_score"), "overall": overall,
             "audit": True}
    with open(AUDIT, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return AUDIT.exists() and entry["id"] in AUDIT.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------- Phase V: Validate
def _consume(consumer, producer, artifact):
    try:
        sys.path.insert(0, str(PROD / "cognify/self"))
        import consumption  # noqa: PLC0415
        consumption.log_consumption(producer, consumer, artifact)
    except Exception:
        pass


def validate_dual_track() -> dict:
    """双轨验证: 基准 trend 最新 + 自使用最近记录 → overall; 低于上周期 → 回滚标记。"""
    trend = _json(TRI / "benchmark/trend_data.json", {}).get("runs", [])
    bench = trend[-1]["total_score"] if trend else None
    _consume("evolve", "meta-call/certification_report", "certification_report.json")
    sv = _json(TRI / "self_validate/self_validation_result.json", None)
    selfval = sv.get("overall_score") if sv else None
    overall = round((bench + selfval) / 2, 1) if bench is not None and selfval is not None else None
    # 上周期 (audit 最后一条)
    prev_overall = None
    if AUDIT.exists():
        for line in AUDIT.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    prev_overall = json.loads(line).get("overall")
                except Exception:
                    pass
    regression = (prev_overall is not None and overall is not None and overall < prev_overall)
    if regression:
        ROLLBACK.parent.mkdir(parents=True, exist_ok=True)
        ROLLBACK.write_text(json.dumps({"mode": "rollback", "since": _now(),
                                        "prev": prev_overall, "now": overall},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
    (EV / "evolution_validation_report.md").write_text(
        "\n".join(["# 双轨验证报告 (Phase V)", "",
                   f"**时间**: {_now()}",
                   f"- 基准: {bench} | 自使用: {selfval} | 整体: {overall}",
                   f"- 上周期整体: {prev_overall}",
                   f"- 回滚: {'🔴 触发' if regression else '✅ 未触发'}"]),
        encoding="utf-8")
    return {"bench": bench, "self_validate": selfval, "overall": overall,
            "prev_overall": prev_overall, "regression": regression}


# ---------------------------------------------------------------- Phase E: Enforce
def enforce() -> dict:
    """强制进化模式: 债务 P0 优先提案 (top3) + 报告。"""
    debt = _json(TRI / "debt/debt_inventory.json", {}).get("debts", [])
    open_debts = [d for d in debt if d.get("status") != "已解决"]
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    open_debts.sort(key=lambda d: order.get(d.get("sev"), 9))
    proposals = [{"debt": d.get("id"), "sev": d.get("sev"), "module": d.get("module"),
                  "desc": d.get("desc", ""), "solution": (d.get("solution") or "")[:120]}
                 for d in open_debts[:3]]
    mode = {"mode": "force", "since": _now(), "proposals": proposals}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(mode, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# 强制进化报告 (Phase E Enforce)", "",
             f"**时间**: {_now()} | **模式**: 🔴 强制进化 (门禁未达标)", "",
             "## 进化提案 (债务优先级 Top3)", "", "| # | 债务 | 级别 | 模块 | 建议 |", "|---|---|---|---|---|"]
    for i, p in enumerate(proposals, 1):
        lines.append(f"| {i} | {p['debt']} | {p['sev']} | {p['module']} | {p['desc'][:60]} |")
    lines += ["", "执行路径: 选择最高优先级提案 → 实现 → 提交 (含 commit hash) → "
                   "重跑 `cognify evolve --report` 闭环验证"]
    (EV / f"enforced_evolution_report.md").write_text("\n".join(lines), encoding="utf-8")
    return mode


# ---------------------------------------------------------------- 完整链 + CLI
def run_full() -> dict:
    ev = evidence_report()
    verify = verify_evidence(ev)
    org = organize_evidence(ev)
    val = validate_dual_track()
    logged = log_evidence(ev, verify, org, val.get("overall"))
    if not logged:
        print("[evolve] 🔴 审计记录失败 — 进化视为无效, 必须重新执行")
        return {"ok": False, "reason": "audit-log-failed"}
    if ev["force_required"] or val.get("regression") or verify.get("forged"):
        mode = enforce()
    else:
        mode = {"mode": "normal"}
        STATE.write_text(json.dumps({"mode": "normal", "last_ok": _now()},
                                    ensure_ascii=False, indent=2), encoding="utf-8")
    # 每日报告 (用户格式)
    lines = [f"### ⚡ 每日进化报告 [#EVO-{datetime.now().strftime('%Y-%m-%d')}]", "",
             f"**日期**: {datetime.now().strftime('%Y-%m-%d')} | **版本**: {VERSION}",
             f"**门禁状态**: {'✅ 全部通过' if ev['gate'] and not val.get('regression') else '🔴 强制进化'}", "",
             "#### 进化证据清单", "", "| # | 类型 | 描述 | 改进幅度 | Commit | 验证 |", "|---|---|---|---|---|---|"]
    for i, c in enumerate(ev["checks"], 1):
        h = ev["commits"][0][:7] if i == 1 and ev["commits"] else "—"
        lines.append(f"| {i} | {TYPES.get(org['items'][i-1]['type'], '?')} | {c['item']} | {c['detail']} | {h} | {'✅' if c['ok'] else '❌'} |")
    lines += ["", "#### 对比上一周期",
              f"- 证据项: {ev['passed']}/{ev['total']} | 整体评分: {val.get('overall')} (上期 {val.get('prev_overall')})",
              "- 强制模式: " + ("🔴 触发" if mode.get("mode") == "force" else "✅ 未触发"), "",
              "#### 明日进化方向"]
    if mode.get("proposals"):
        for p in mode["proposals"]:
            lines.append(f"- {p['sev']}: {p['debt']} {p['desc'][:70]}")
    else:
        lines.append("- 保持双轨验证持续运行, 提升治理/认知域自使用评分")
    lines += ["", "#### 历史进化趋势", "", "| 日期 | 证据项 | 整体评分 |", "|---|---|---|"]
    if AUDIT.exists():
        for line in AUDIT.read_text(encoding="utf-8", errors="replace").splitlines()[-7:]:
            if line.strip():
                try:
                    e = json.loads(line)
                    lines.append(f"| {e['ts'][:10]} | {e['evidence_passed']}/{e['evidence_total']} | {e['overall']} |")
                except Exception:
                    pass
    (EV / f"evolution_report_{datetime.now().strftime('%Y%m%d')}.md").write_text(
        "\n".join(lines), encoding="utf-8")
    return {"ok": True, "evidence": ev["passed"], "total": ev["total"],
            "overall": val.get("overall"), "mode": mode.get("mode"),
            "regression": val.get("regression"), "report": EV / f"evolution_report_{datetime.now().strftime('%Y%m%d')}.md"}


def cmd_status() -> int:
    ev = scan_evidence()
    mode = _json(STATE, {})
    print(f"[evolve] 今日证据: {ev['passed']}/{ev['total']} | 门禁: {'✅ PASS' if ev['gate'] else '🔴 强制进化'}"
          f" | 模式: {mode.get('mode', 'normal')}")
    for c in ev["checks"]:
        print(f"  {'✅' if c['ok'] else '❌'} {c['item']}: {c['detail']}")
    return 0 if ev["gate"] else 1


def cmd_trend() -> int:
    if not AUDIT.exists():
        print("[evolve] 无审计记录")
        return 0
    print("[evolve] 历史趋势 (日期 | 证据项 | 整体):")
    for line in AUDIT.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]:
        if line.strip():
            try:
                e = json.loads(line)
                print(f"  {e['ts'][:10]} | {e['evidence_passed']}/{e['evidence_total']} | {e['overall']} | {e['id'][:16]}")
            except Exception:
                pass
    return 0


def cmd_force() -> int:
    mode = enforce()
    print(f"[evolve] 🔴 强制进化模式已触发 | 提案 {len(mode['proposals'])} 个")
    for p in mode["proposals"]:
        print(f"  {p['sev']} {p['debt']}: {p['desc'][:70]}")
    print(f"[evolve] → {EV / 'enforced_evolution_report.md'}")
    return 2


def cmd_activate() -> int:
    tr = (f'C:\\Users\\ivy\\AppData\\Local\\Programs\\Python\\Python312\\python.exe '
          f'C:\\Users\\ivy\\.aionui-tri-sync\\daemon\\evolve.py report')
    r = subprocess.run(["schtasks", "/create", "/tn", "EVOLVE-DAILY", "/tr", tr,
                        "/sc", "daily", "/st", "23:30", "/f"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print((r.stdout or r.stderr or "").strip())
    return 0 if r.returncode == 0 else 1


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "report":
        r = run_full()
        if not r.get("ok"):
            return 1
        print(f"[evolve] 证据 {r['evidence']}/{r['total']} | 整体 {r['overall']} "
              f"| 模式 {r['mode']} | 回滚 {'🔴' if r['regression'] else '✅'}")
        print(f"[evolve] → {r['report']}")
        return 0 if (r["mode"] == "normal" and not r["regression"]) else 2
    if cmd == "status":
        return cmd_status()
    if cmd == "trend":
        return cmd_trend()
    if cmd == "force":
        return cmd_force()
    if cmd == "activate":
        return cmd_activate()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
