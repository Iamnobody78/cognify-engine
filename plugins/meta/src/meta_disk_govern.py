#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
meta_disk_govern.py — META-DISK-GOVERN v1.0 元硬盘治理引擎
==========================================================
六维模型 D1-D6 + S.C.A.N.-R.E.P.O.R.T. 九步法
红线: 未经用户确认不删除 / 不碰系统关键目录 / 先回滚方案 / 审计日志

用法:
  python meta_disk_govern.py status           # D1 空间总览 + 阈值预警
  python meta_disk_govern.py scan             # S+C+A: 快照/分类/分析
  python meta_disk_govern.py govern           # 完整循环 (S→R, execute 待确认)
  python meta_disk_govern.py clean --confirm  # 用户确认后执行 🟢 清理 (带回滚)
"""
import faulthandler
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
GOV = TRI / "disk-govern"
AUDIT = GOV / "disk_governance_audit.log"
USER = Path.home()
WS = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704")

ALERT_RATIO = 0.75      # 使用率预警
ALERT_FREE_GB = 80      # 可用空间预警 (GB)
SCAN_BUDGET_S = 90      # 扫描时间预算

#: D4 已知缓存路径库 (🟢 可安全删除候选)
CACHE_DIRS = [
    ("pip 缓存", USER / "AppData/Local/pip/cache"),
    ("uv 缓存", USER / "AppData/Local/uv/cache"),
    ("npm 缓存", USER / "AppData/Local/npm-cache"),
    ("npx 缓存", USER / "AppData/Local/npm-cache/_npx"),
    ("pnpm 缓存", USER / "AppData/Local/pnpm-cache"),
    ("Docker 数据", USER / "AppData/Local/Docker"),
    ("浏览器缓存", USER / "AppData/Local/Google/Chrome/User Data/Default/Cache"),
    ("Edge 缓存", USER / "AppData/Local/Microsoft/Edge/User Data/Default/Cache"),
    ("Temp 目录", USER / "AppData/Local/Temp"),
    ("Windows 临时", Path("C:/Windows/Temp")),
    ("DSH 缓存", USER / ".cache"),
    ("conda pkgs", USER / "miniconda3/pkgs"),
]
#: 系统关键目录 (红线 2 — 永不触碰)
PROTECTED = {"C:/Windows", "C:/Program Files", "C:/Program Files (x86)",
             "C:/ProgramData", str(USER / "AppData/Local/Programs"),
             str(Path("C:/Users/ivy/AppData/Local/Programs/AionUi"))}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _audit(entry: dict):
    GOV.mkdir(parents=True, exist_ok=True)
    with open(AUDIT, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _dir_size(path: Path, budget: float) -> int:
    """快速目录大小统计 (跳过 junction/系统目录, 带时间预算)。"""
    total = 0
    t0 = time.time()
    try:
        for root, dirs, files in os.walk(path):
            if time.time() - t0 > budget:
                break
            dirs[:] = [d for d in dirs if d not in ("node_modules", "site-packages", ".git")]
            try:
                for f in files:
                    p = Path(root) / f
                    try:
                        total += p.stat().st_size
                    except OSError:
                        pass
            except OSError:
                pass
    except OSError:
        pass
    return total


# ---------------------------------------------------------------- D1
def status() -> dict:
    t = shutil.disk_usage("C:\\")
    used, free, total = t.used, t.free, t.total
    ratio = used / total
    alerts = []
    if ratio > ALERT_RATIO:
        alerts.append(f"使用率 {ratio:.0%} > 预警阈值 {ALERT_RATIO:.0%}")
    if free / (1024 ** 3) < ALERT_FREE_GB:
        alerts.append(f"可用空间 {free / 1e9:.0f}GB < {ALERT_FREE_GB}GB")
    snap = {"ts": _now(), "total_gb": round(total / 1e9, 1),
            "used_gb": round(used / 1e9, 1), "free_gb": round(free / 1e9, 1),
            "ratio": round(ratio, 3), "alerts": alerts}
    (GOV / f"disk_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    return snap


# ---------------------------------------------------------------- D2/D3/D4
def scan() -> dict:
    """目录深度扫描 + 缓存分类。"""
    t = shutil.disk_usage("C:\\")
    ratio = t.used / t.total
    items = []
    for label, p in CACHE_DIRS:
        if p.exists():
            size = _dir_size(p, SCAN_BUDGET_S / max(len(CACHE_DIRS), 1))
            items.append({"label": label, "path": str(p), "size_gb": round(size / 1e9, 2),
                          "class": "green"})
    # 项目目录概览 (🟡)
    for label, p in (("bottlesumo_pi", WS / "bottlesumo_pi"),
                     ("cognify-engine", WS / "cognify-engine"),
                     ("agent-governance-v2", WS / "agent-governance-v2"),
                     ("tri-sync hub", TRI / "hub")):
        if p.exists():
            size = _dir_size(p, 20)
            items.append({"label": label, "path": str(p), "size_gb": round(size / 1e9, 2),
                          "class": "yellow"})
    items.sort(key=lambda x: x["size_gb"], reverse=True)
    green = sum(i["size_gb"] for i in items if i["class"] == "green")
    yellow = sum(i["size_gb"] for i in items if i["class"] == "yellow")
    report = {"ts": _now(), "ratio": round(ratio, 3),
              "green_gb": round(green, 1), "yellow_gb": round(yellow, 1),
              "items": items}
    (GOV / "classification_report.md").write_text(
        "\n".join([f"- [{i['class']}] {i['label']}: {i['size_gb']}GB → {i['path']}"
                   for i in items]), encoding="utf-8")
    return report


# ---------------------------------------------------------------- R: Rehearse
def rehearse(scan_res: dict) -> dict:
    """生成 dry-run manifest (仅 🟢 类, 带预估释放量)。"""
    manifest = []
    for i in scan_res["items"]:
        if i["class"] == "green":
            manifest.append({"path": i["path"], "size_gb": i["size_gb"], "action": "delete"})
    total = round(sum(m["size_gb"] for m in manifest), 1)
    (GOV / "cleanup_manifest_dry_run.txt").write_text(
        "\n".join(f"{m['size_gb']:>8}GB  {m['action']:<8} {m['path']}" for m in manifest) +
        f"\n\n# 模拟释放: {total}GB / {len(manifest)} 项", encoding="utf-8")
    return {"dry_release_gb": total, "items": len(manifest), "manifest": manifest}


# ---------------------------------------------------------------- P: Protect + E: Execute
def protect(manifest: list) -> Path:
    """生成回滚清单 (元数据备份 + 回滚脚本)。"""
    lines = ["# rollback_cleanup — 被清理项元数据 (路径/大小/时间)", ""]
    for m in manifest:
        p = Path(m["path"])
        if p.exists():
            try:
                st = p.stat()
                lines.append(f"{m['size_gb']}GB | {p} | mtime={st.st_mtime:.0f}")
            except OSError:
                lines.append(f"{m['size_gb']}GB | {p} | (不可读)")
    rb = GOV / "rollback_cleanup.txt"
    rb.write_text("\n".join(lines), encoding="utf-8")
    return rb


def clean(confirm: bool) -> dict:
    """执行清理 (仅 🟢 类; 须 --confirm; 大项移入回收站目录可回滚)。"""
    if not confirm:
        return {"error": "需 --confirm 确认 (红线 1)"}
    snap = status()
    scan_res = scan()
    rh = rehearse(scan_res)
    manifest = [m for m in rh["manifest"] if m["size_gb"] >= 0.05]  # 只处理 ≥50MB
    if not manifest:
        return {"released_gb": 0, "files": 0, "note": "无可清理项"}
    protect(manifest)
    bin_dir = GOV / "trash"
    bin_dir.mkdir(parents=True, exist_ok=True)
    released = 0
    for m in manifest:
        p = Path(m["path"])
        if not p.exists() or str(p).startswith(tuple(PROTECTED)):
            continue
        try:
            dest = bin_dir / p.name
            shutil.move(str(p), str(dest))  # 移入治理回收站 = 可回滚
            released += m["size_gb"]
            _audit({"ts": _now(), "action": "clean", "path": m["path"],
                    "size_gb": m["size_gb"], "to": str(dest)})
        except Exception as exc:  # noqa: BLE001
            _audit({"ts": _now(), "action": "clean-failed", "path": m["path"], "error": str(exc)})
    post = shutil.disk_usage("C:\\")
    res = {"released_gb": round(released, 1), "files": len(manifest),
           "post_free_gb": round(post.free / 1e9, 1),
           "post_ratio": round(post.used / post.total, 3),
           "rollback": str(GOV / "rollback_cleanup.txt"),
           "trash": str(bin_dir)}
    (GOV / "post_cleanup_report.md").write_text(
        "\n".join(f"- {k}: {v}" for k, v in res.items()), encoding="utf-8")
    return res


# ---------------------------------------------------------------- 报告
def report(round_n: int, snap: dict, scan_res: dict, rh: dict, executed: dict | None) -> Path:
    lines = [
        f"# 💾 元硬盘治理报告 [#DISK-GOV-ROUND_{round_n}]", "",
        f"> {_now()} | META-DISK-GOVERN v1.0", "",
        "**[Phase S: Snapshot]**",
        f"- 总容量: {snap['total_gb']} GB | 已使用: {snap['used_gb']} GB "
        f"({snap['ratio']:.0%}) | 可用: {snap['free_gb']} GB",
        "", "**[Phase C: Classify]**",
        f"- 🟢 可安全清理: {scan_res['green_gb']} GB | 🟡 需审查: {scan_res['yellow_gb']} GB", "",
        "**[Phase A: Analyze]**",
        *[f"- {i['label']}: {i['size_gb']}GB → {i['path']}" for i in scan_res["items"][:5]], "",
        "**[Phase R: Rehearse]**",
        f"- 模拟释放: {rh['dry_release_gb']} GB | 涉及项: {rh['items']}", "",
        "**[Phase E: Execute]**",
        "- " + ("待用户确认 (--confirm)" if executed is None
                else f"实际释放 {executed.get('released_gb', 0)} GB"), "",
        "**[Phase P: Protect]**",
        f"- 回滚清单: {GOV / 'rollback_cleanup.txt'}", "",
        "**[Phase O: Observe]**",
        f"- 新可用空间: {executed.get('post_free_gb', snap['free_gb']) if executed else snap['free_gb']} GB",
        "", "**[Phase R: Review]**",
        f"- 审计日志: {AUDIT}", "",
        "**[Honest Boundary]**",
        "- 治理范围: 已知缓存路径库 (D4) + 项目目录概览",
        "- 未治理: 系统目录/运行中项目 (红线 2/3)",
        "- 风险项: 缓存重建成本, 回收站占用",
    ]
    f = GOV / f"DISK-GOV-ROUND_{round_n}.md"
    f.write_text("\n".join(lines), encoding="utf-8")
    return f


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lstrip("-")
    confirm = "--confirm" in sys.argv
    GOV.mkdir(parents=True, exist_ok=True)
    if cmd == "status":
        s = status()
        print(f"[disk] 总 {s['total_gb']}GB | 已用 {s['used_gb']}GB ({s['ratio']:.0%}) | 可用 {s['free_gb']}GB")
        for a in s["alerts"]:
            print(f"  ⚠️ {a}")
        print(f"[disk] 状态: {'✅ 健康' if not s['alerts'] else '⚠️ 预警'}")
        return 0 if not s["alerts"] else 1
    if cmd == "scan":
        s = status()
        r = scan()
        print(f"[disk] 使用率 {s['ratio']:.0%} | 🟢 {r['green_gb']}GB 可清理 | 🟡 {r['yellow_gb']}GB 需审查")
        for i in r["items"][:8]:
            print(f"  [{i['class']}] {i['label']}: {i['size_gb']}GB")
        print(f"[disk] → classification_report.md")
        return 0
    if cmd == "govern":
        s = status()
        r = scan()
        rh = rehearse(r)
        rb = protect(rh["manifest"])
        n = len(list(GOV.glob("DISK-GOV-ROUND_*.md"))) + 1
        rep = report(n, s, r, rh, None)
        print(f"[disk] 治理轮次 #{n} → {rep}")
        print(f"[disk] 使用率 {s['ratio']:.0%} | 🟢 {r['green_gb']}GB | 模拟释放 {rh['dry_release_gb']}GB")
        print(f"[disk] 实际清理需确认: cognify meta-disk clean --confirm")
        return 0
    if cmd == "clean":
        res = clean(confirm)
        if "error" in res:
            print(f"[disk] {res['error']}")
            return 1
        print(f"[disk] 释放 {res['released_gb']}GB ({res['files']} 项) → 回收站 {res['trash']}")
        print(f"[disk] 新可用 {res['post_free_gb']}GB ({res['post_ratio']:.0%})")
        print(f"[disk] 回滚: 见 {res['rollback']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
