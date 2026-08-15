# -*- coding: utf-8 -*-
"""
Cognitive Engine 插件 (cognify.cognitive)
=========================================
内容: cve_s.py + mmc_agent.py 冻结快照 (src/, 见 VENDORED.md)。
职责: MCE 编译 / VCE 扫描 / CEE 推演 / MMC 代理心跳。
运行模式: 默认委托规范安装 (~/.aionui-tri-sync/daemon) 的活引擎;
          规范安装缺失时使用本插件快照 (只读自检)。
"""
import json
import subprocess
from pathlib import Path
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin

HERE = Path(__file__).resolve().parent
SNAP = HERE / "src"
TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
PY = r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe"


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._canonical = None

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.cognitive", "name": "Cognitive Engine",
            "version": "1.0.0",
            "capabilities": ["cognitive", "mce", "vce", "cee", "heartbeat"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        if not (SNAP / "cve_s.py").exists():
            raise FileNotFoundError(f"快照缺失: {SNAP / 'cve_s.py'}")
        canon = TRI / "daemon" / "mmc_agent.py"
        self._canonical = canon if canon.exists() else None

    def on_enable(self) -> None:
        if self.bus:
            self.bus.publish("cognitive.ready", {"id": "cognify.cognitive",
                                                 "canonical": bool(self._canonical)})

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        self._canonical = None

    def heartbeat(self) -> Dict[str, Any]:
        """MMC 心跳 (委托规范 mmc_agent, 缺失则自检快照)。"""
        if self._canonical:
            r = subprocess.run([PY, str(self._canonical), "heartbeat"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=120)
            return {"mode": "canonical", "returncode": r.returncode,
                    "tail": (r.stdout or r.stderr or "")[-400:]}
        hb = sorted((TRI / "hub/cves/heartbeats").glob("mmce_heartbeat_*.md"))
        return {"mode": "snapshot", "heartbeats": len(hb),
                "latest": hb[-1].name if hb else None}

    def status(self) -> Dict[str, Any]:
        st = TRI / "meta/status.json"
        if st.exists():
            return json.loads(st.read_text(encoding="utf-8"))
        return {"error": "meta/status.json 缺失"}
