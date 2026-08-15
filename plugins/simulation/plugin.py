# -*- coding: utf-8 -*-
"""
BottleSumo Simulation 插件 (cognify.simulation)
===============================================
内容: bottlesumo-pi 全仓库快照 (src/ 子树, git 历史保留)。
职责: 仿真平台 / Renode HIL / firmware 验证入口。
"""
from pathlib import Path
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin

HERE = Path(__file__).resolve().parent
REPO = HERE / "src"


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._runner = None

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.simulation", "name": "BottleSumo Simulation",
            "version": "2.0.0",
            "capabilities": ["simulation", "hil", "firmware"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        runner = REPO / "simulation" / "abdl_runner.py"
        if not runner.exists():
            raise FileNotFoundError(f"仿真运行器缺失: {runner}")
        self._runner = runner

    def on_enable(self) -> None:
        n = len(list((REPO / "simulation").glob("*.py")))
        if self.bus:
            self.bus.publish("simulation.ready", {"id": "cognify.simulation",
                                                  "modules": n})

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        self._runner = None
