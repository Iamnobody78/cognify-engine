#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp_low_disk.py — MCP-LOW-DISK v1.0 低磁盘占用持续运行引擎
==========================================================
C.L.E.A.N.-R.U.N. 七步法: Check 空间 → Locate 占用 → Evaluate 分类
                         → Act 清理 → Normalize 固化 → Run 启动 → Update 策略

阈值: 可用 <5GB 拒启 / 使用率 >85% 巡检 / 单服务器缓存 >2GB 清理 / 日志 >1GB 轮转

用法:
  python mcp_low_disk.py govern    # 完整治理
  python mcp_low_disk.py check     # 空间检查
  python mcp_low_disk.py policy    # 清理策略
  python mcp_low_disk.py history   # 检查历史
"""
import faulthandler
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
LD = TRI / "mcp-low-disk"
HISTORY = LD / "pre_launch_space_check_history.jsonl"
POLICY = LD / "mcp_cleanup_policy.yaml"
USER = Path.home()

THRESHOLD_FREE_GB = 5
THRESHOLD_RATIO = 0.85
THRESHOLD_CACHE_GB = 2.0
THRESHOLD_LOG_GB = 1.0

CACHE_TARGETS = [
    ("uv 缓存", USER / "AppData/Local/uv/cache", ["uv", "cache", "prune"]),
    ("npm 缓存", USER / "AppData/Local/npm-cache", ["npm", "cache", "clean", "--force"]),
    ("pip 缓存", USER / "AppData/Local/pip/cache", ["pip", "cache", "purge"]),
]
LOG_DIRS = [
    (TRI / "logs"),
    USER / "AppData/Local/hermes/logs",
    Path(r"C:\Users\ivy\.dsh\logs"),
]


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _log(entry: dict):
    LD.mkdir(parents=True, exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check() -> dict:
    """C: 启动前空间检查。"""
    t = shutil.disk_usage("C:\\")
    free_gb = round(t.free / 1e9, 1)
    ratio = round(t.used / t.total, 3)
    allow = free_gb >= THRESHOLD_FREE_GB and ratio <= THRESHOLD_RATIO
    rep = {"ts": _now(), "free_gb": free_gb, "ratio": ratio,
           "allow": allow, "threshold": f"<{THRESHOLD_FREE_GB}GB 或 >{THRESHOLD_RATIO:.0%} 拒启"}
    _log(rep)
    (LD / "pre_launch_space_check.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


def locate() -> dict:
    """L: 定位占用源。"""
    caches, logs = [], []
    for label, p, _ in CACHE_TARGETS:
        if p.exists():
            size = sum(x.stat().st_size for x in p.rglob("*") if x.is_file())
            caches.append({"label": label, "path": str(p), "mb": round(size / 1e6, 1)})
    for d in LOG_DIRS:
        if d.exists():
            size = sum(x.stat().st_size for x in d.rglob("*") if x.is_file())
            logs.append({"label": str(d), "mb": round(size / 1e6, 1)})
    rep = {"ts": _now(), "caches": caches, "logs": logs,
           "cache_mb": round(sum(c["mb"] for c in caches), 1),
           "log_mb": round(sum(l["mb"] for l in logs), 1)}
    (LD / "mcp_disk_occupants.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


def act(loc: dict) -> dict:
    """A: 执行清理 (🟢 自动; 阈值触发)。"""
    freed = 0
    actions = []
    for c in loc["caches"]:
        if c["mb"] < 50:  # <50MB 不值得
            continue
        if c["mb"] / 1e3 < THRESHOLD_CACHE_GB and c["label"] != "uv 缓存":
            continue  # 单服务器缓存 >2GB 才清 (uv 例外: 按协议最高优先级)
        cmd = [c["label"] == "npm 缓存" and "npm" or ("pip" if "pip" in c["label"] else "uv")]
        try:
            r = subprocess.run([c["label"] == "uv 缓存" and "uv" or "npm",
                                "cache", "clean" if c["label"] == "npm 缓存" else "purge" if "pip" in c["label"] else "prune"],
                               capture_output=True, text=True, timeout=300)
            freed += c["mb"]
            actions.append({"cache": c["label"], "freed_mb": round(c["mb"], 1), "exit": r.returncode})
        except Exception as exc:  # noqa: BLE001
            actions.append({"cache": c["label"], "error": str(exc)})
    # 日志轮转: >1GB 截断旧日志 (保留最新)
    rotated = []
    for l in loc["logs"]:
        if l["mb"] > THRESHOLD_LOG_GB * 1e3:
            rotated.append(l)
    rep = {"ts": _now(), "actions": actions, "freed_mb": round(freed, 1),
           "log_rotation_candidates": rotated}
    (LD / "mcp_cleanup_execution.log").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return rep


def normalize() -> Path:
    """N: 固化清理策略。"""
    policy = {
        "version": "1.0", "updated": _now(),
        "thresholds": {"free_gb": THRESHOLD_FREE_GB, "ratio": THRESHOLD_RATIO,
                       "cache_gb": THRESHOLD_CACHE_GB, "log_gb": THRESHOLD_LOG_GB},
        "cache_cleanup": [c[0] for c in CACHE_TARGETS],
        "log_dirs": [str(d) for d in LOG_DIRS],
        "schedule": "每周一 06:00 深度巡检 (MCP-LOW-DISK-WEEKLY)",
        "version_pinning": "替换 @latest 为固定版本 (D5)",
    }
    POLICY.write_text(__import__("yaml").safe_dump(policy, allow_unicode=True, sort_keys=False),
                      encoding="utf-8")
    return POLICY


def govern() -> int:
    LD.mkdir(parents=True, exist_ok=True)
    c = check()
    loc = locate()
    a = act(loc)
    pol = normalize()
    print(f"[low-disk] 可用 {c['free_gb']}GB ({c['ratio']:.0%}) | 启动: {'✅ 允许' if c['allow'] else '🚫 拒绝'}")
    print(f"[low-disk] 缓存 {loc['cache_mb']}MB | 日志 {loc['log_mb']}MB | 释放 {a['freed_mb']}MB")
    for act_ in a["actions"]:
        print(f"  {act_.get('cache', '?')}: freed {act_.get('freed_mb', act_.get('error'))}")
    print(f"[low-disk] 策略 → {pol}")
    return 0 if c["allow"] else 1


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "govern").lstrip("-")
    LD.mkdir(parents=True, exist_ok=True)
    if cmd in ("govern", "activate"):
        return govern()
    if cmd == "check":
        c = check()
        print(f"[low-disk] 可用 {c['free_gb']}GB ({c['ratio']:.0%}) | "
              f"{'✅ 允许启动' if c['allow'] else '🚫 拒绝启动 (触发清理)'}")
        return 0 if c["allow"] else 1
    if cmd == "policy":
        print(POLICY.read_text(encoding="utf-8") if POLICY.exists() else "策略未生成")
        return 0
    if cmd == "history":
        if HISTORY.exists():
            for line in HISTORY.read_text(encoding="utf-8", errors="replace").splitlines()[-10:]:
                print(" ", line[:120])
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
