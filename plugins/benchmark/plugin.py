# -*- coding: utf-8 -*-
"""
Benchmark Controller 插件 (cognify.benchmark)
=============================================
内容: benchmark.py 冻结快照 (BENCHMARK-AUTO + BENCHMARK-CONTINUOUS)。
职责: 8 域健康评分 (元能力/MCP/同步/治理/认知/统一/磁盘/自动化),
      B.E.N.C.H. 五步法 + T.R.E.N.D. 趋势验证与退化警告。
活控制器运行于规范安装 (~/.aionui-tri-sync/daemon/benchmark.py);
本插件为仓库自包含快照, 提供同构接口 (不启动第二份写者)。
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
SNAPSHOT = HERE / "benchmark.py"
PY = os.environ.get("COGNIFY_PY", r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe")


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._snapshot = None

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.benchmark", "name": "Benchmark Controller",
            "version": "0.1.0",
            "capabilities": ["benchmark", "health-score", "trend", "regression-warning"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        if not SNAPSHOT.exists():
            raise FileNotFoundError(f"基准控制器快照缺失: {SNAPSHOT}")
        self._snapshot = SNAPSHOT

    def on_enable(self) -> None:
        if self.bus:
            self.bus.publish("benchmark.ready", {"id": "cognify.benchmark",
                                                  "snapshot": str(self._snapshot)})

    def on_disable(self) -> None:
        self._snapshot = None

    def on_unload(self) -> None:
        self._snapshot = None

    def _run(self, args: list) -> Dict[str, Any]:
        py = self.config.get("python") or PY
        r = subprocess.run([py, str(SNAPSHOT), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=600)
        return {"returncode": r.returncode, "out": r.stdout or "", "err": r.stderr or ""}

    def run_all(self) -> Dict[str, Any]:
        """全量基准: 8 域 + 整体健康评分。"""
        return self._run(["all"])

    def run_score(self) -> Dict[str, Any]:
        return self._run(["score"])

    def run_trend(self) -> Dict[str, Any]:
        return self._run(["trend"])

    def run_warnings(self) -> Dict[str, Any]:
        return self._run(["warnings"])
