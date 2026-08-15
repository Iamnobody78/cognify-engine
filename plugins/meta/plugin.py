# -*- coding: utf-8 -*-
"""
Meta Capability Suite 插件 (cognify.meta)
=========================================
内容: meta_capabilities/meta_cognition/meta_decision/meta_architect 冻结快照 (src/, VENDORED.md)。
职责: 25 维元能力自检 / 元认知评估 / 元决策规则 / 能力演进。
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
            "id": "cognify.meta", "name": "Meta Capability Suite",
            "version": "1.0.0",
            "capabilities": ["meta", "metacognition", "metadecision", "selfcheck"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        if not (SNAP / "meta_capabilities.py").exists():
            raise FileNotFoundError(f"快照缺失: {SNAP / 'meta_capabilities.py'}")
        canon = TRI / "daemon" / "meta_capabilities.py"
        self._canonical = canon if canon.exists() else None

    def on_enable(self) -> None:
        st = self.status()
        if self.bus:
            self.bus.publish("meta.ready", {"id": "cognify.meta", **st})

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        self._canonical = None

    def status(self) -> Dict[str, Any]:
        st = TRI / "meta/status.json"
        if st.exists():
            data = json.loads(st.read_text(encoding="utf-8"))
            return {"active": data.get("active_count"),
                    "health": data.get("overall_health")}
        return {"error": "meta/status.json 缺失"}

    def closure(self) -> Dict[str, Any]:
        cl = TRI / "meta/closure/closure_report.json"
        if cl.exists():
            c = json.loads(cl.read_text(encoding="utf-8"))
            return {"rate": c.get("closure_rate"), "closed": c.get("closed"),
                    "total": c.get("total"), "gap": c.get("gap")}
        return {"error": "closure_report.json 缺失"}
