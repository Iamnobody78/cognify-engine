#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_dev.py — 元层开发引擎 (META-LEVEL-DEV 纲领 P0/P1)
========================================================
1. generate-status — 动态真相源: STATUS.md + certificate.json 从运行时实时采集
2. bootstrap       — 自举校验: manifest.json 资产清单 ↔ 实际文件一致性 + 缺失骨架模板
3. self-analyze    — 认知自省: git 历史分析 → CEE 推演 → 路线图建议

原则: 元数据是动态真相源, 非静态文件; 计算逻辑取代硬编码。
"""
import os
import faulthandler
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))))
import cognify.paths as paths

import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = paths.TRI
PROD = paths.PROD
PY = paths.PY


def _load_version() -> str:
    """A3 版本单一源: 从 pyproject.toml 读取 (cognify/__init__.py 亦同源)。"""
    try:
        import tomllib
        with open(PROD / "pyproject.toml", "rb") as fh:
            return tomllib.load(fh).get("project", {}).get("version", "?")
    except Exception:
        return "?"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


# ---------------------------------------------------------------- generate-status
def _consume(consumer, producer, artifact):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import consumption  # noqa: PLC0415
        consumption.log_consumption(producer, consumer, artifact)
    except Exception:
        pass


def generate_status() -> dict:
    """动态采集运行时数据 → STATUS.md + certificate.json (计算取代硬编码)。"""
    _consume("generate-status", "meta/status", "status.json")
    _consume("generate-status", "debt/debt_inventory", "debt_inventory.json")
    _consume("generate-status", "benchmark/trend_data", "trend_data.json")
    meta = _json(TRI / "meta/status.json", {})
    closure = _json(TRI / "meta/closure/closure_report.json", {})
    debt = _json(TRI / "debt/debt_inventory.json", {}).get("debts", [])
    debt_done = sum(1 for d in debt if d.get("status") == "已解决")
    trend = _json(TRI / "benchmark/trend_data.json", {}).get("runs", [])
    cert = _json(TRI / "meta-call/certification_report.json", None)
    hb = sorted((TRI / "hub/cves/heartbeats").glob("mmce_heartbeat_*.md"))
    plugins = list((PROD / "plugins").glob("*/manifest.json"))
    p_verified = sum(1 for m in plugins if _json(m, {}).get("verified"))
    daemon_alive = (TRI / "state/daemon.lock").exists()
    evolve = None
    ap = TRI / "evolve/evolution_audit.jsonl"
    if ap.exists():
        for line in ap.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                try:
                    evolve = json.loads(line)
                except Exception:
                    pass
    data = {
        "ts": _now(), "version": _load_version(),
        "meta_active": meta.get("active_count"), "meta_health": meta.get("overall_health"),
        "closure_rate": closure.get("closure_rate"),
        "debt": f"{debt_done}/{len(debt)}",
        "daemon": daemon_alive,
        "heartbeats": len(hb), "latest_hb": hb[-1].name if hb else None,
        "call_certified": bool(cert and cert.get("certified")),
        "benchmark_total": trend[-1]["total_score"] if trend else None,
        "plugins": f"{p_verified}/{len(plugins)} verified",
        "evolve_overall": evolve.get("overall") if evolve else None,
    }
    # 2.3 闭环运行时化: 真实消费率 (静态映射降级 fallback) — 须在 lines 构建前
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import consumption  # noqa: PLC0415
        rc = consumption.runtime_closure_rate()
        data["runtime_closure"] = f"{rc['consumed']}/{rc['expected']} (真实消费)"
    except Exception:
        data["runtime_closure"] = "fallback"
    lines = [
        "# Cognify Engine — 产品状态 (动态生成)", "",
        f"> {data['ts']} | 由 `cognify generate-status` 从运行时采集, 非手工维护", "",
        f"## 元能力: {data['meta_active']} active | health={data['meta_health']}",
        f"## 元闭环(静态): {data['closure_rate']*100:.1f}% | 元闭环(运行时): {data.get('runtime_closure', '?')}" if isinstance(data["closure_rate"], (int, float)) else "## 元闭环: ?",
        f"## 债务: {data['debt']} 已解决",
        f"## 同步守护: {'✅ 运行中' if data['daemon'] else '❌ 未运行'}",
        f"## 心跳: {data['heartbeats']} 份 (最新: {data['latest_hb']})",
        f"## 元调用链: {'✅ CERTIFIED' if data['call_certified'] else '❌ 未认证'}",
        f"## 基准: {data['benchmark_total']}/100" if data["benchmark_total"] is not None else "",
        f"## 插件: {data['plugins']}",
        f"## 进化: 最近整体 {data['evolve_overall']}" if data["evolve_overall"] is not None else "",
    ]
    # A1 单一写者 (三期 N1): certificate.json 只由 cert() 写 — generate-status 只读不写
    cert_state = _json(PROD / "certificate.json", None)
    if cert_state is None:
        lines.insert(2, "## ⚠️ 认证状态: 未运行 cert — 请先 `cognify cert` (红线: 无认证不宣称)")
    elif cert_state.get("overall") == "NOT_CERTIFIED":
        lines.insert(2, "## ⚠️ 认证状态: NOT_CERTIFIED — 文档不得宣称 CERTIFIED (红线)")
    else:
        lines.insert(2, f"## 认证: {cert_state.get('overall')} | grade={cert_state.get('grade', '?')} | "
                        f"{cert_state.get('certified_at', '?')[:16]}")
    (PROD / "STATUS.md").write_text("\n".join(l for l in lines if l), encoding="utf-8")
    return data


# ---------------------------------------------------------------- bootstrap
def bootstrap() -> dict:
    """manifest.json 资产清单 ↔ 实际文件一致性校验 + 缺失项模板。"""
    man = _json(PROD / "manifest.json", {})
    assets = man.get("assets", [])
    missing = []
    for a in assets:
        probe = a.get("probe")
        if probe and not Path(probe).exists():
            missing.append({"key": a.get("key"), "label": a.get("label"), "probe": probe})
    # 插件 manifest 与目录一致性
    pm = list((PROD / "plugins").glob("*/manifest.json"))
    orphan_dirs = [p.parent.name for p in (PROD / "plugins").iterdir()
                   if p.is_dir() and not (p / "manifest.json").exists() and p.name != "__pycache__"]
    return {"ts": _now(), "assets_total": len(assets), "assets_missing": missing,
            "plugins_total": len(pm), "plugins_orphan": orphan_dirs,
            "ok": not missing and not orphan_dirs}


# ---------------------------------------------------------------- self-analyze
def self_analyze() -> dict:
    """git 历史分析 → CEE 推演 → 开发路线图建议。"""
    try:
        r = subprocess.run(["git", "-C", str(PROD), "log", "--since=30 days ago",
                            "--pretty=format:%h|%s"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        rows = [l for l in (r.stdout or "").splitlines() if "|" in l]
        feats = [x for x in rows if re.match(r"^\w+\|feat", x)]
        fixes = [x for x in rows if re.match(r"^\w+\|fix", x)]
        docs = [x for x in rows if re.search(r"docs|README|CHANGELOG", x.split("|", 1)[1])]
        # 脆弱模块: 变更最频繁路径
        r2 = subprocess.run(["git", "-C", str(PROD), "log", "--since=30 days ago",
                             "--name-only", "--pretty=format:"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60)
        freq = {}
        for line in (r2.stdout or "").splitlines():
            line = line.strip()
            if line and line.endswith(".py"):
                k = "/".join(line.split("/")[:2])
                freq[k] = freq.get(k, 0) + 1
        hot = sorted(freq.items(), key=lambda x: -x[1])[:5]
        summary = f"30 天: {len(rows)} 提交 | feat {len(feats)} | fix {len(fixes)} | docs {len(docs)}"
        # CEE 推演
        sys.path.insert(0, str(PROD / "plugins/cognitive/src"))
        sys.path.insert(0, str(PROD / "plugins/sync/src"))
        import cve_s  # noqa: PLC0415
        cee = cve_s.cee_plan("基于双轨验证与元能力审计, 规划 cognify-engine 下一阶段路线",
                             cve_s.vce_scan(summary))
        return {"ts": _now(), "summary": summary, "hot_modules": hot,
                "cee_stage1": cee.get("stage_1_survival"),
                "cee_stage2": cee.get("stage_2_sediment"),
                "cee_stage3": cee.get("stage_3_release"),
                "recommendations": [
                    f"脆弱模块 (变更频繁): {m} ×{n}" for m, n in hot
                ] + [f"feat 占比 {(len(feats)/max(len(rows),1)*100):.0f}% — 进化节奏健康" if len(rows) else ""]}
    except Exception as exc:  # noqa: BLE001
        return {"ts": _now(), "error": f"{type(exc).__name__}: {exc}"}


def bootstrap_audit() -> dict:
    """完整性审计: 幽灵资产 (manifest 有但文件无) + 未记录资产 (文件有但 manifest 无)。"""
    man = _json(PROD / "manifest.json", {})
    recorded = {}
    for a in man.get("assets", []):
        probe = a.get("probe")
        if probe:
            recorded[Path(probe)] = a.get("key")
    ghost = [{"key": k, "probe": str(p)} for p, k in recorded.items() if not p.exists()]
    # 未记录资产: 插件目录中存在的 py/md 但 manifest assets 未提及 (按插件 key 粗检)
    unrecorded = []
    for p in (PROD / "plugins").glob("*/src/*.py"):
        rel = str(p)
        if not any(rel in str(rp) for rp in recorded):
            unrecorded.append(rel)
    return {"ts": _now(), "ghost_assets": ghost, "unrecorded_files": unrecorded[:10],
            "ghost_count": len(ghost), "unrecorded_count": len(unrecorded)}


def debt_proposals() -> dict:
    """自省→债务提案: 脆弱模块 (变更 > 阈值) 自动生成 DEBT 提案。"""
    try:
        r = subprocess.run(["git", "-C", str(PROD), "log", "--since=30 days ago",
                            "--name-only", "--pretty=format:"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=60)
        freq = {}
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line and line.endswith(".py"):
                k = "/".join(line.split("/")[:2])
                freq[k] = freq.get(k, 0) + 1
        hot = sorted(freq.items(), key=lambda x: -x[1])
        proposals = []
        for mod, n in hot[:5]:
            if n >= 100:
                proposals.append({"module": mod, "changes_30d": n,
                                  "dim": "D6", "sev": "P1" if n >= 300 else "P2",
                                  "desc": f"模块 {mod} 30 天变更 {n} 次 (脆弱性信号, self-analyze 自动提案)",
                                  "root": "变更频率高可能反映设计不稳定或需求活跃",
                                  "solution": "重构/拆分该模块或补充针对性测试"})
        out = {"ts": _now(), "source": "self-analyze --debt-auto-create", "proposals": proposals}
        p = TRI / "meta-deploy/debt_proposals.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
    except Exception as exc:  # noqa: BLE001
        return {"ts": _now(), "error": str(exc)}


def bootstrap_fix() -> dict:
    """--fix 模式: 自动修复不一致 (缺失资产占位/孤儿目录注册/外部路径依赖告警)。"""
    man = _json(PROD / "manifest.json", {})
    assets = man.get("assets", [])
    fixed, warned = [], []
    for a in assets:
        probe = a.get("probe")
        if probe and not Path(probe).exists():
            p = Path(probe)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("# placeholder (bootstrap --fix 自动创建)\n", encoding="utf-8")
            fixed.append(f"占位创建: {a.get('key')} → {probe}")
    # 孤儿插件目录 → 生成 manifest.json 模板
    for p in (PROD / "plugins").iterdir():
        if p.is_dir() and not (p / "manifest.json").exists() and p.name != "__pycache__":
            (p / "manifest.json").write_text(json.dumps(
                {"id": f"cognify.{p.name}", "name": p.name, "version": "0.1.0",
                 "description": "bootstrap --fix 自动注册", "main": "plugin.py",
                 "verified": False}, ensure_ascii=False, indent=2), encoding="utf-8")
            fixed.append(f"孤儿注册: plugins/{p.name}")
    # 外部路径依赖检测 (插件 src 内引用 TRI/daemon 外部路径)
    for f in (PROD / "plugins").glob("*/src/*.py"):
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
            if r"\.aionui-tri-sync\daemon" in txt or ".aionui-tri-sync/daemon" in txt:
                warned.append(f"外部依赖: {f.relative_to(PROD)} 引用 daemon/ 路径")
        except Exception:
            pass
    return {"ts": _now(), "fixed": fixed, "external_dep_warnings": warned}


def pypi_status() -> dict:
    """发布就绪检查: OIDC workflow / pyproject / 版本冲突 / 最近 tag。"""
    wf = PROD / ".github/workflows/release.yml"
    wf_oidc = wf.exists() and "id-token: write" in wf.read_text(encoding="utf-8", errors="replace")
    pyproject = PROD / "pyproject.toml"
    name = version = None
    if pyproject.exists():
        txt = pyproject.read_text(encoding="utf-8", errors="replace")
        for line in txt.splitlines():
            if line.strip().startswith("name") and "=" in line:
                name = line.split("=", 1)[1].strip().strip('"').strip("'")
            if line.strip().startswith("version") and "=" in line:
                version = line.split("=", 1)[1].strip().strip('"').strip("'")
    # PyPI 已有同名包?
    pypi_exists = False
    try:
        import urllib.request
        urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=15)
        pypi_exists = True
    except Exception:
        pypi_exists = False
    # 最近 tag
    last_tag = ""
    try:
        r = subprocess.run(["git", "-C", str(PROD), "tag", "--sort=-creatordate"],
                           capture_output=True, text=True, timeout=20)
        last_tag = (r.stdout or "").splitlines()[0] if r.stdout.strip() else ""
    except Exception:
        pass
    return {"ts": _now(), "oidc_workflow": wf_oidc, "pyproject": pyproject.exists(),
            "name": name, "version": version, "pypi_exists": pypi_exists,
            "last_tag": last_tag,
            "ready": wf_oidc and pyproject.exists() and not pypi_exists,
            "next_step": "PyPI 后台添加受信任发布者 (Owner: Iamnobody78 / Repo: cognify-engine / Workflow: release.yml) 后打 tag"}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate-status"
    if cmd == "pypi-status":
        p = pypi_status()
        print(f"[meta-dev] PyPI 发布就绪: {'✅ READY' if p['ready'] else '⚠️ 未就绪'}")
        print(f"  OIDC workflow: {'✅' if p['oidc_workflow'] else '❌'} | pyproject: {'✅' if p['pyproject'] else '❌'}"
              f" | 包 {p['name']}@{p['version']}")
        print(f"  PyPI 已有同名包: {'✅ (版本冲突?)' if p['pypi_exists'] else '✅ 未占用'}"
              f" | 最近 tag: {p['last_tag'] or '无'}")
        print(f"  下一步: {p['next_step']}")
        return 0 if p["ready"] else 1
    if cmd == "generate-status":
        d = generate_status()
        print("[meta-dev] STATUS.md 已动态生成 (certificate.json 由 cert 单一写者维护)")
        for k, v in d.items():
            print(f"  {k}: {v}")
        return 0
    if cmd == "bootstrap":
        b = bootstrap()
        print(f"[meta-dev] 资产 {b['assets_total']} | 插件 {b['plugins_total']} | "
              f"缺失资产 {len(b['assets_missing'])} | 孤儿目录 {len(b['plugins_orphan'])}")
        for m in b["assets_missing"]:
            print(f"  ❌ 缺失资产 {m['key']}: {m['probe']}")
        for o in b["plugins_orphan"]:
            print(f"  ⚠️ 孤儿插件目录: {o}")
        print("[meta-dev] ✅ 自举一致性" if b["ok"] else "[meta-dev] ⚠️ 存在不一致")
        return 0 if b["ok"] else 1
    if cmd == "bootstrap-fix":
        f = bootstrap_fix()
        print(f"[meta-dev] 自动修复: {len(f['fixed'])} 项")
        for x in f["fixed"]:
            print(f"  🔧 {x}")
        print(f"[meta-dev] 外部依赖告警: {len(f['external_dep_warnings'])}")
        for w in f["external_dep_warnings"]:
            print(f"  ⚠️ {w}")
        return 0 if not f["external_dep_warnings"] else 1
    if cmd == "audit-debt":
        a = bootstrap_audit()
        print(f"[meta-dev] 完整性审计: 幽灵资产 {a['ghost_count']} | 未记录文件 {a['unrecorded_count']}")
        for g in a["ghost_assets"]:
            print(f"  👻 {g['key']}: {g['probe']}")
        for u in a["unrecorded_files"]:
            print(f"  📄 未记录: {u}")
        return 0 if not a["ghost_assets"] else 1
    if cmd == "self-analyze":
        a = self_analyze()
        print(f"[meta-dev] 自省: {a.get('summary', a.get('error'))}")
        for m, n in a.get("hot_modules", []):
            print(f"  🔥 {m}: {n} 次变更")
        if a.get("cee_stage3"):
            print(f"  推演(阶段三): {a['cee_stage3'][:120]}")
        for rec in a.get("recommendations", []):
            if rec:
                print(f"  建议: {rec}")
        return 0
    if cmd == "debt-auto-create":
        p = debt_proposals()
        print(f"[meta-dev] 债务提案: {len(p.get('proposals', []))} 个")
        for prop in p.get("proposals", []):
            print(f"  {prop['sev']} {prop['module']}: {prop['desc'][:60]}")
        print(f"[meta-dev] → {TRI / 'meta-deploy/debt_proposals.json'}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
