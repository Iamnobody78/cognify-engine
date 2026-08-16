# -*- coding: utf-8 -*-
"""
Evolve Force 插件 (cognify.evolve)
==================================
内容: EVOLVE-FORCE v1.0 强制进化引擎 (cognify/evolve/engine.py)。
E.V.O.L.V.E. 六步: Evidence 扫描 (5 检查项) → Verify (commit/证据核验) →
Organize (分类+评分) → Log (审计 jsonl 只追加) → Validate (双轨验证+回滚检测)
→ Enforce (门禁失败 → 债务 P0 优先提案)。
活引擎运行于规范安装 (daemon/evolve.py 转发, EVOLVE-DAILY 每日 23:30);
本插件为仓库自包含入口。
"""
import subprocess
from pathlib import Path
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin

HERE = Path(__file__).resolve().parent
PROD = HERE.parents[1]
PY = r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe"
ENGINE = PROD / "cognify" / "evolve" / "engine.py"


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._engine = None

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.evolve", "name": "Evolve Force",
            "version": "0.1.0",
            "capabilities": ["evolve", "evidence-gate", "audit-trail", "force-mode", "rollback-detect"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        if not ENGINE.exists():
            raise FileNotFoundError(f"强制进化引擎缺失: {ENGINE}")
        self._engine = ENGINE

    def on_enable(self) -> None:
        if self.bus:
            self.bus.publish("evolve.ready", {"id": "cognify.evolve",
                                               "engine": str(self._engine)})

    def on_disable(self) -> None:
        self._engine = None

    def on_unload(self) -> None:
        self._engine = None

    def run(self, cmd: str = "report") -> Dict[str, Any]:
        py = self.config.get("python") or PY
        r = subprocess.run([py, str(self._engine), cmd], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=600)
        return {"returncode": r.returncode, "out": r.stdout or "", "err": r.stderr or ""}
