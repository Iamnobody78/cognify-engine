#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRI-SYNC-STATUS v1.0 — 三方同步状态检查
读取 hub/state/{state,heartbeat}.json 与 logs/sync_log.jsonl, 输出人类可读报告。
退出码: 0=正常, 1=任一系统离线或心跳过期, 2=无状态数据。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

HUB = Path(__file__).resolve().parent.parent
STATE = HUB / "state" / "state.json"
HEARTBEAT = HUB / "state" / "heartbeat.json"
SYNCLOG = HUB / "logs" / "sync_log.jsonl"


def read_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main():
    state = read_json(STATE)
    hb = read_json(HEARTBEAT)
    if state is None and hb is None:
        print("❌ 无状态数据 — 守护进程尚未运行。请先执行: python sync_daemon.py --once")
        return 2

    print("=" * 62)
    print("  TRI-SYNC-STATUS — Hermes / AionUi / DSH 三方同步状态")
    print("=" * 62)

    if state:
        print(f"\n[守护进程]")
        print(f"  版本      : {state.get('version', '?')}")
        print(f"  创建时间  : {state.get('created', '?')}")
        print(f"  上次运行  : {state.get('last_run', '?')}")
        s = state.get("stats", {})
        print(f"  累计 tick : {s.get('total_ticks', 0)} | 复制 {s.get('copied', 0)} "
              f"| 冲突 {s.get('conflicts', 0)} | 错误 {s.get('errors', 0)}")

    if hb:
        print(f"\n[三方心跳]")
        all_alive = True
        for name, h in hb.items():
            alive = h.get("alive", False)
            all_alive = all_alive and alive
            mark = "🟢" if alive else "🔴"
            print(f"  {mark} {h.get('label', name):8s} ({h.get('role', '?')}) "
                  f"| 最后心跳 {h.get('seen') or '从未'}")
        if not all_alive:
            print("  ⚠️ 存在离线系统!")

    if state:
        cursors = state.get("cursors", {})
        print(f"\n[镜像统计]")
        for cls in ("conversations", "memory", "sessions", "registry",
                    "workspace", "config"):
            n = len(cursors.get(cls, {}))
            if n:
                print(f"  {cls:15s}: {n} 个条目已跟踪")

    # 最近日志
    if SYNCLOG.exists():
        lines = SYNCLOG.read_text(encoding="utf-8").strip().splitlines()
        print(f"\n[最近同步事件] (共 {len(lines)} 条)")
        for line in lines[-6:]:
            try:
                e = json.loads(line)
                hb_s = e.get("heartbeat")
                if hb_s:
                    print(f"  {e['ts']} tick {e['duration_ms']}ms "
                          f"心跳={hb_s}")
                else:
                    print(f"  {e['ts']} {e.get('class_name','?')} "
                          f"{e.get('action','?')} "
                          f"copied={e.get('copied',0)} conflicts={e.get('conflicts',0)}")
            except json.JSONDecodeError:
                pass

    # 冲突
    conf = HUB / "logs" / "conflicts.jsonl"
    if conf.exists():
        n = len(conf.read_text(encoding="utf-8").strip().splitlines())
        if n:
            print(f"\n⚠️ 冲突记录: {n} 条 (见 logs/conflicts.jsonl, 败者备份在 backup/conflicts/)")

    print("\n" + "=" * 62)
    return 0 if (hb and all_alive) else 1


if __name__ == "__main__":
    sys.exit(main())
