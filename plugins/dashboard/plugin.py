# -*- coding: utf-8 -*-
"""
Governance Dashboard 插件 (cognify.dashboard) — 诚实桩
======================================================
DEBT-016: 治理仪表板尚未实现。本插件只做状态占位,
不伪称具备 Web 服务能力 (honesty_guard 红线)。
"""
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._stub = True

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.dashboard", "name": "Governance Dashboard",
            "version": "0.0.1", "stub": True,
            "capabilities": ["dashboard", "web"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        pass  # 桩: 无资源可初始化

    def on_enable(self) -> None:
        print("[dashboard] ⚠️ 未实现 — DEBT-016 待偿, 当前为诚实桩 (不提供服务)")
        if self.bus:
            self.bus.publish("dashboard.stub", {"id": "cognify.dashboard"})

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        pass
