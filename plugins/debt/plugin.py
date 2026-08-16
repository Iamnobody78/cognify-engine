# -*- coding: utf-8 -*-
"""
Debt Engine 插件 (cognify.debt)
===============================
内容: debt_engine/debt_miner/debt_library.yaml 冻结快照 (src/, VENDORED.md)。
职责: 债务挖掘 / YAML 驱动偿还 / 验证报告。
"""
import os
import json
from pathlib import Path
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin

HERE = Path(__file__).resolve().parent
SNAP = HERE / "src"
TRI = Path(os.environ.get("COGNIFY_TRI", r"C:\Users\ivy\.aionui-tri-sync"))


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._library = None

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.debt", "name": "Debt Engine",
            "version": "1.1.0",
            "capabilities": ["debt", "mining", "repayment", "verification"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        lib = SNAP / "debt_library.yaml"
        if not lib.exists():
            raise FileNotFoundError(f"债务库缺失: {lib}")
        self._library = lib

    def on_enable(self) -> None:
        inv = self.inventory()
        if self.bus:
            self.bus.publish("debt.ready", {"id": "cognify.debt", **inv})

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        self._library = None

    def inventory(self) -> Dict[str, Any]:
        inv = TRI / "debt/debt_inventory.json"
        if inv.exists():
            d = json.loads(inv.read_text(encoding="utf-8"))
            debts = d.get("debts", [])
            resolved = sum(1 for x in debts if x.get("status") == "已解决")
            return {"total": len(debts), "resolved": resolved}
        return {"error": "debt_inventory.json 缺失"}
