# -*- coding: utf-8 -*-
"""
Self-Validate Iterate 插件 (cognify.self_validate)
==================================================
内容: 双轨验证闭环 (SELF-VALIDATE-ITERATE v1.0):
  - 轨 B: 自使用验证引擎 (cognify/self_validate/engine.py) — 5 场景真实调用
  - 轨 C: 双轨融合分析 (cognify/iterate/fusion.py) — 交叉验证 + 深度审查门禁
  - 轨 D: 每日迭代报告 + 冲刺模式 (cognify/iterate/report.py)
活引擎运行于规范安装 (daemon/self_validate.py + daemon/iterate.py 转发);
本插件为仓库自包含入口 (不启动第二份写者)。
"""
import subprocess
import os
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from pathlib import Path
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin

HERE = Path(__file__).resolve().parent
PROD = HERE.parents[1]  # cognify-engine 仓库根
PY = os.environ.get("COGNIFY_PY", r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe")
SV_ENGINE = PROD / "cognify" / "self_validate" / "engine.py"
IT_ENGINE = PROD / "cognify" / "iterate" / "report.py"


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._engines = {}

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.self_validate", "name": "Self-Validate Iterate",
            "version": "0.1.0",
            "capabilities": ["self-validate", "dual-track-fusion", "iteration-report", "sprint-mode"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        for name, p in (("self_validate", SV_ENGINE), ("iterate", IT_ENGINE)):
            if not p.exists():
                raise FileNotFoundError(f"{name} 引擎缺失: {p}")
            self._engines[name] = p

    def on_enable(self) -> None:
        if self.bus:
            self.bus.publish("self_validate.ready", {"id": "cognify.self_validate",
                                                      "engines": list(self._engines)})

    def on_disable(self) -> None:
        self._engines = {}

    def on_unload(self) -> None:
        self._engines = {}

    def _run(self, engine: str, args: list) -> Dict[str, Any]:
        py = self.config.get("python") or PY
        r = subprocess.run([py, str(self._engines[engine]), *args], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=300)
        return {"returncode": r.returncode, "out": r.stdout or "", "err": r.stderr or ""}

    def run_validation(self, cmd: str = "start") -> Dict[str, Any]:
        return self._run("self_validate", [cmd])

    def run_iteration(self, cmd: str = "report") -> Dict[str, Any]:
        return self._run("iterate", [cmd])
