#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRI-SYNC-WATCHDOG v1.0 — 守护进程看门狗
=======================================
检查 daemon.lock 中的 PID 是否存活; 若守护已死则重新拉起 (独立进程)。
配套: 开机自启 (Startup) + 计划任务 (schtasks) 双保险。
用法: python watchdog.py            # 检查一次, 必要时重启
      python watchdog.py --force    # 无条件重启
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

BASE = Path(__file__).resolve().parent.parent
STATE = BASE / "state"
LOGS = BASE / "logs"
DAEMON = BASE / "daemon" / "sync_daemon.py"
CONFIG = BASE / "daemon" / "sync_config.yaml"
PY = Path(r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\pythonw.exe")
LOCK = STATE / "daemon.lock"
WATCH_LOG = LOGS / "watchdog.log"


def log(msg):
    LOGS.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    try:
        with open(WATCH_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def pid_alive(pid):
    if not pid:
        return False
    try:
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    except Exception:
        return False


def start_daemon():
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    out = open(LOGS / "daemon_console.out.log", "a", encoding="utf-8")
    err = open(LOGS / "daemon_console.err.log", "a", encoding="utf-8")
    subprocess.Popen(
        [str(PY), str(DAEMON), "--daemon", "--config", str(CONFIG),
         "--interval", "30"],
        stdout=out, stderr=err, creationflags=flags, close_fds=True)
    log(f"守护进程已重新拉起 ({PY.name} detached)")


def main():
    force = "--force" in sys.argv
    if force:
        start_daemon()
        return 0
    if LOCK.exists():
        try:
            old = json.loads(LOCK.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            old = {}
        if pid_alive(old.get("pid")):
            log(f"守护正常 (PID {old['pid']})")
            return 0
        log(f"守护已死 (PID {old.get('pid')}), 重启中...")
        start_daemon()
        return 1
    log("无锁文件 (守护未运行), 启动中...")
    start_daemon()
    return 1


if __name__ == "__main__":
    sys.exit(main())
