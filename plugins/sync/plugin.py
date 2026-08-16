# -*- coding: utf-8 -*-
"""
Tri-Sync Daemon 插件 (cognify.sync)
===================================
内容: sync_daemon/watchdog/sync_status/trisync_paths 冻结快照 (src/, VENDORED.md)。
职责: 三方同步守护管理。活守护运行于规范安装 (~/.aionui-tri-sync),
      本插件为快照 + 状态委派 (不启动第二份守护 — 防双写漂移)。
"""
import os
import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin

HERE = Path(__file__).resolve().parent
SNAP = HERE / "src"
TRI = Path(os.environ.get("COGNIFY_TRI", r"C:\Users\ivy\.aionui-tri-sync"))
PY = os.environ.get("COGNIFY_PY", r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe")


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._canonical = None

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.sync", "name": "Tri-Sync Daemon",
            "version": "1.1.0",
            "capabilities": ["sync", "daemon", "watchdog", "conflict-resolution"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        if not (SNAP / "sync_daemon.py").exists():
            raise FileNotFoundError(f"快照缺失: {SNAP / 'sync_daemon.py'}")
        canon = TRI / "daemon" / "sync_daemon.py"
        self._canonical = canon if canon.exists() else None

    def on_enable(self) -> None:
        st = self.status()
        if self.bus:
            self.bus.publish("sync.ready", {"id": "cognify.sync", **st})

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        self._canonical = None

    def status(self) -> Dict[str, Any]:
        """守护状态: 规范安装优先, 快照兜底。"""
        if self._canonical and (TRI / "daemon" / "sync_status.py").exists():
            r = subprocess.run([PY, str(TRI / "daemon" / "sync_status.py")],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60)
            return {"mode": "canonical", "returncode": r.returncode,
                    "tail": (r.stdout or r.stderr or "")[-500:]}
        lock = TRI / "state" / "daemon.lock"
        sessions = len(list((TRI / "hub/sessions").rglob("*.zstd"))) \
            if (TRI / "hub/sessions").exists() else 0
        return {"mode": "snapshot", "daemon": bool(lock.exists()),
                "sessions": sessions}

    def watchdog_info(self) -> Dict[str, Any]:
        return {"scheduled": "TRI-SYNC-Watchdog (5min)", "script": str(SNAP / "watchdog.py")}
